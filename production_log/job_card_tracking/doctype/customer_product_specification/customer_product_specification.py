import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from production_log.job_card_tracking import cps_cp_rules
from production_log.job_card_tracking import cps_cp_weight
from production_log.job_card_tracking import cps_pricing
from production_log.job_card_tracking import cps_rules


INK_TYPE_DEFAULTS = {
	"Computer Paper":               "Process Offset",
	"Carton":                       "Process Offset",
	"Label":                        "Process UV",
	"ETR (Reel to Reel Printing)":  "Water Based",
}


class CustomerProductSpecification(Document):
	"""
	Customer Product Specification DocType for managing detailed product requirements.

	Handles specifications for Computer Paper, Carton, Label, and Exercise Books
	with intelligent validation, auto-population from Dies for label products,
	and shared Print Colours block across CP / Label / Carton.
	"""

	def validate(self):
		self.validate_product_type()
		self.set_naming_series()
		self.apply_ink_type_default()
		self.recalculate_number_of_colours()
		# Before validate_computer_paper, deliberately. This asks the identity
		# questions - is the job Printed, was Numbering actually answered - and a
		# reader who has not said whether the job is printed is not helped by
		# being told about part three's GSM first. For a NEW record it also
		# reports the parts grid in full, so a five-part set is corrected in one
		# pass rather than five; validate_computer_paper below then re-checks the
		# same conditions and finds nothing left to say.
		self.validate_computer_paper_capture()
		self.validate_computer_paper()
		# After validate_computer_paper, so the parts grid is known good before its
		# GSM is summed into a weight.
		self.apply_computer_paper_weights()
		self.validate_carton()
		self.validate_label()
		self.validate_exercise_books()
		self.validate_etr()
		self.validate_linked_item()
		cps_pricing.validate_pricing(self)

	def before_submit(self):
		"""Rules that only bite when the specification becomes real.

		Artwork is the whole of it, and it is deliberately here rather than in
		``validate``: the file frequently arrives after the sizes, the parts and
		the colours are known, and refusing the *draft* would mean none of that
		could be recorded until the customer sent a PDF.

		Two questions, not one. First that a Printed specification *has* artwork,
		and then that what it has is really artwork — see
		:meth:`validate_artwork_integrity`, which is the half that makes the
		attach control, a REST write and a Data Import obey the same rules as the
		Compass uploader.

		Skipped entirely on a site where the ``artwork`` field has not landed yet.
		That is the window between a deploy and its migrate, and in it the rule
		would refuse every Printed submission for want of a field with nowhere to
		put a value.

		Existing submitted records are untouched by any of this: ``before_submit``
		fires once, on the transition out of draft, and never again on a record
		that made that transition before this release.

		Weight is the second submit rule, and stands on exactly the same ground: a
		draft may be recorded before the finished size and the pack are known, but a
		specification going to production must carry a real carton weight. Its own
		``has_field`` guard, independent of artwork, so a site that has one column
		and not the other still checks whichever it has.
		"""
		self._before_submit_weight()
		if not self.meta.has_field(cps_cp_rules.ARTWORK_FIELD):
			return
		reason = cps_cp_rules.artwork_submit_block_reason(self)
		if reason is not None:
			frappe.throw(_(reason.template).format(*reason.args))
		self.validate_artwork_integrity()

	def _before_submit_weight(self):
		"""Refuse a Computer Paper submission with incomplete weight inputs.

		A submit rule, not a save rule, on the same terms as artwork: the size and
		the pack often settle after the parts and the colours, so the draft is left
		alone and the completed submission is required to carry them. Guarded on the
		field's existence for the deploy-before-migrate window, and naturally
		frozen for the 46 already-submitted records, which never re-run this.
		"""
		if not self.meta.has_field(cps_cp_weight.GROSS_FIELD):
			return
		reason = cps_cp_weight.weight_submit_block_reason(self)
		if reason is not None:
			frappe.throw(_(reason.template).format(*reason.args))

	def validate_artwork_integrity(self):
		"""Prove the stored artwork File, rather than trusting the field.

		``artwork`` is an Attach, and an Attach is a Data field holding a path.
		Anything that can write the document can write that path: Desk's attach
		control, a REST ``PUT``, a Data Import, an amendment. Only the Compass
		upload endpoint has ever been past an extension allowlist, a size cap and
		a private-only rule, so on every other route those three were intentions
		rather than rules.

		This is where they become rules, for all four routes at once. The File row
		is resolved from the stored URL and *it* is asked whether it exists, is
		private, belongs to this specification, is a kind of artwork we accept and
		has a sane size. A path that names no File, or somebody else's File, is
		refused here even though it is a perfectly well-formed string — which is
		the whole point: a URL is not evidence of anything.

		Printed only, on the same terms as the requirement itself. A Plain job
		does not need artwork, so it has nothing to prove.
		"""
		if not cps_cp_rules.artwork_required(self):
			return

		url = (self.get(cps_cp_rules.ARTWORK_FIELD) or "").strip()
		reason = cps_cp_rules.artwork_file_error(
			self._stored_artwork_file(url), self.doctype, self.name
		)
		if reason is not None:
			frappe.throw(_(reason.template).format(*reason.args))

	def _stored_artwork_file(self, url):
		"""The File row behind a stored artwork URL, or None.

		Looked up by URL alone and *then* filtered to this document, rather than
		queried with the binding in the filter. The difference matters for the
		message: a query that included the binding would return nothing for
		another document's file, and the user would be told the file does not
		exist when in fact it exists and belongs to somebody else. The row bound
		to this document wins when several share the URL — Frappe de-duplicates
		identical content by hash, so an amendment and its original legitimately
		point at the same path.
		"""
		if not url:
			return None
		rows = frappe.get_all(
			"File",
			filters={"file_url": url},
			fields=[
				"name", "file_name", "file_url", "is_private", "file_size",
				"attached_to_doctype", "attached_to_name",
			],
			order_by="creation desc",
			limit_page_length=20,
		)
		if not rows:
			return None
		for row in rows:
			if (
				row.get("attached_to_doctype") == self.doctype
				and row.get("attached_to_name") == self.name
			):
				return self._with_real_size(row)
		return self._with_real_size(rows[0])

	@staticmethod
	def _with_real_size(row):
		"""Fill in ``file_size`` from disk when the row does not carry one.

		Frappe does not always store it. ``copy_attachments_from_amended_from``
		creates the successor's File rows without a size, and an amendment of a
		Printed specification would otherwise be refused for holding an "empty"
		file that is nothing of the kind. The bytes on disk are the truth; a path
		that cannot be read at all is a size of zero, and is refused as empty,
		which is the honest answer for a File whose content has gone.
		"""
		if cint(row.get("file_size")) > 0:
			return row
		try:
			row["file_size"] = os.path.getsize(frappe.get_doc("File", row["name"]).get_full_path())
		except Exception:
			row["file_size"] = 0
		return row

	def validate_computer_paper_capture(self):
		"""Numbering, print colour and print side on a Computer Paper record.

		Every rule is a *transition* rule (see :mod:`cps_cp_rules`): it fires for
		a new record, and for an existing one only when somebody has deliberately
		moved the thing the rule is about. Fifty-nine legacy Computer Paper
		specifications reach this release — twenty-one Printed with no ink
		recorded and all nine Plain ones carrying ink — and every one of them must
		keep saving for reasons that have nothing to do with colour.

		The parts grid is reported as a list rather than one reason at a time: a
		five-part set otherwise takes five saves to fill in correctly.
		"""
		if self.product_type != cps_cp_rules.COMPUTER_PAPER:
			return

		before = self.get_doc_before_save()

		# The Numbering half is skipped on a site whose ``numbering_confirmed``
		# column has not landed yet - the window between a deploy and its migrate.
		# Without this it would demand a confirmation with nowhere to be recorded
		# and refuse every new Computer Paper specification with an error nobody
		# could clear. The colour half needs no such guard: it reads only fields
		# that already existed.
		reason = cps_cp_rules.save_block_reason(
			before,
			self,
			numbering_available=self.meta.has_field(cps_cp_rules.NUMBERING_CONFIRMED_FIELD),
		)
		if reason is not None:
			frappe.throw(_(reason.template).format(*reason.args))

		# Only the *new* standard is reported as a list here. The long-standing
		# paper type / GSM / sequence rules stay where they are, in
		# validate_computer_paper, so nothing about an existing record's failure
		# messages changes.
		if cps_cp_rules.is_new(before):
			errors = [
				_(e.template).format(*e.args)
				for e in cps_cp_rules.part_row_errors(
					self.number_of_parts, self.colour_of_parts
				)
			]
			if errors:
				frappe.throw("<br>".join(errors))

	def apply_computer_paper_weights(self):
		"""Recompute the carton weights server-side, so no route can spoof them.

		The four derived weights (:data:`cps_cp_weight.DERIVED_FIELDS`) are read-only
		on every surface, but ``artwork`` taught us that read-only on a form stops a
		Desk user and stops nothing else — a REST write or a Data Import posts
		whatever it likes into a read-only field. So the values are not trusted from
		the payload at all: they are recomputed here from the structured inputs and
		the parts grid, and whatever was posted is overwritten with the truth.

		The gross is also mirrored into ``standard_weight_per_carton`` — the field
		the order snapshot freezes and the Job Card reads — but only when the inputs
		are complete enough to produce one. A legacy record with no structured inputs
		computes no gross, so its hand-typed ``standard_weight_per_carton`` is left
		exactly where it is: this recompute never turns a legacy weight into a blank.

		A *present* input that is zero or negative is refused here, on a draft as
		much as at submit, because it is not an incomplete specification but an
		impossible one — reported as a list, like the parts grid, so the four
		dimensions are corrected in one pass. A blank input is not an error; it is
		incompleteness, and :meth:`before_submit` is where that bites.

		Skipped entirely on a site whose weight columns have not landed yet — the
		window between a deploy and its migrate — for the same reason the numbering
		and artwork rules are: demanding or writing a field that does not exist would
		refuse every Computer Paper save with an error nobody could clear.
		"""
		if self.product_type != cps_cp_weight.COMPUTER_PAPER:
			return
		if not self.meta.has_field(cps_cp_weight.GROSS_FIELD):
			return

		# Hard errors only. The allowance-on-a-Plain-record advisory is deliberately
		# not thrown: the calculation already ignores a Plain job's allowance, so
		# refusing the save would block a correction rather than help it. Compass
		# shows it as a warning; here it is left to the arithmetic to disregard.
		errors = [
			_(e.template).format(*e.args)
			for e in cps_cp_weight.weight_field_errors(self)
			if e.code != cps_cp_weight.BLOCK_ALLOWANCE_ON_PLAIN
		]
		if errors:
			frappe.throw("<br>".join(errors))

		for fieldname, value in cps_cp_weight.compute_weights(self).items():
			self.set(fieldname, value)

		standard = cps_cp_weight.standard_weight_value(self)
		if standard is not None:
			self.standard_weight_per_carton = standard

	def validate_linked_item(self):
		"""Require an exact Item on new or materially changed specifications."""
		before = self.get_doc_before_save()
		if cps_rules.item_link_required(before, self) and not self.get("linked_item"):
			frappe.throw(
				"Item is required for a new or materially changed Customer Product Specification."
			)

	def before_update_after_submit(self):
		"""Prices change on submitted specs; validate() does not run for those.

		A price change is a new CPS Price row on the same specification, never
		an amendment (design §6.2 rule 3), so this is the normal write path for
		pricing and needs the same rules as validate().
		"""
		# Reset the allow-on-submit snapshot carrier to the server-calculated gross,
		# so Desk/REST cannot make it diverge after submission.
		self.apply_computer_paper_weights()
		cps_pricing.validate_pricing(self)

	def validate_product_type(self):
		if not self.product_type:
			frappe.throw("Product Type is required. Please select a product type.")

	def set_naming_series(self):
		if self.product_type and not self.naming_series:
			series_map = {
				"Computer Paper":               "CPT-SPEC-.#####",
				"Carton":                       "CTN-SPEC-.#####",
				"Label":                        "LBL-SPEC-.#####",
				"Exercise Books":               "EXB-SPEC-.#####",
				"ETR (Reel to Reel Printing)": "ETR-SPEC-.#####",
			}
			self.naming_series = series_map.get(self.product_type)

	def apply_ink_type_default(self):
		if self.product_type in INK_TYPE_DEFAULTS and not self.ink_type:
			self.ink_type = INK_TYPE_DEFAULTS[self.product_type]

	def recalculate_number_of_colours(self):
		ticks = sum(1 for f in ("uses_c", "uses_m", "uses_y", "uses_k") if getattr(self, f))
		spots = len(self.spot_colours or [])
		self.number_of_colours = ticks + spots

	def validate_carton(self):
		if self.product_type != "Carton":
			return

		if not self.ply:
			frappe.throw("Ply is required for Carton product type.")

		if not self.ctn_length_mm or self.ctn_length_mm <= 0:
			frappe.throw("Carton Length (mm) must be greater than 0.")

		if not self.ctn_width_mm or self.ctn_width_mm <= 0:
			frappe.throw("Carton Width (mm) must be greater than 0.")

		if self.ply != "SFK":
			if not self.ctn_height_mm or self.ctn_height_mm <= 0:
				frappe.throw(
					"Carton Height (mm) must be greater than 0 unless Ply is SFK."
				)

	def validate_computer_paper(self):
		if self.product_type != "Computer Paper":
			return

		if not self.number_of_parts:
			frappe.throw("Number of Parts is required for Computer Paper.")

		parts = self.colour_of_parts or []
		if len(parts) != self.number_of_parts:
			frappe.throw(
				f"Colour of Parts table must have exactly {self.number_of_parts} row(s), "
				f"but {len(parts)} row(s) found."
			)

		for i, part in enumerate(parts, start=1):
			if int(part.part_number or 0) != i:
				frappe.throw(
					f"Part numbers must be sequential. "
					f"Row {i}: expected part number {i}, got {part.part_number}."
				)
			if not part.colour:
				frappe.throw(f"Row {i} in Colour of Parts is missing a colour.")

		self._validate_paper_type_and_gsm(parts)

	def validate_label(self):
		if self.product_type != "Label":
			return

		required_fields = [
			("label_length",  "Label Length"),
			("label_width",   "Label Width"),
			("material_type", "Material Type"),
		]
		for field_name, field_label in required_fields:
			if not getattr(self, field_name, None):
				frappe.throw(f"{field_label} is required for Label product type.")

	def validate_etr(self):
		if self.product_type != "ETR (Reel to Reel Printing)":
			return

		if not self.etr_substrate:
			frappe.throw("Substrate is required for ETR (Reel to Reel Printing).")

		if self.etr_substrate == "Other" and not self.etr_substrate_other:
			frappe.throw("When Substrate is 'Other', please specify the substrate name in 'Substrate (Other)'.")

		if not self.etr_gsm or self.etr_gsm <= 0:
			frappe.throw("GSM must be greater than 0 for ETR (Reel to Reel Printing).")

		if not self.etr_jumbo_width or self.etr_jumbo_width <= 0:
			frappe.throw("Jumbo Roll Width (mm) must be greater than 0 for ETR.")

		if not self.etr_output_type:
			frappe.throw("Output Type is required for ETR (Reel to Reel Printing).")

		if self.etr_output_type in ("ETR Plain Rolls", "ETR Printed Rolls"):
			if not self.etr_finished_width or self.etr_finished_width <= 0:
				frappe.throw("Finished Width (mm) must be greater than 0 for roll output.")
			if not self.etr_finished_diameter or self.etr_finished_diameter <= 0:
				frappe.throw("Finished Diameter (mm) must be greater than 0 for roll output.")

		if self.etr_output_type == "Printed Reel":
			if not self.etr_finished_reel_length or self.etr_finished_reel_length <= 0:
				frappe.throw("Finished Reel Length (m) must be greater than 0 for Printed Reel output.")

	def validate_exercise_books(self):
		if self.product_type != "Exercise Books":
			return

		if not self.number_of_pages:
			frappe.throw("Number of Pages is required for Exercise Books.")

		if self.number_of_pages % 4 != 0:
			frappe.throw(
				f"Number of Pages must be a multiple of 4. Got {self.number_of_pages}."
			)

	def _validate_paper_type_and_gsm(self, parts):
		n = len(parts)

		valid_single = [("60 GSM Bond", 60), ("CB", 55), ("70 GSM Bond", 70)]
		valid_first  = [("CB", 55)]
		valid_middle = [("CFB", 50)]
		valid_last   = [("CF", 55)]

		def check(part, valid_options, position_label):
			for paper_type, gsm in valid_options:
				if part.paper_type == paper_type and int(part.gsm or 0) == gsm:
					return
			options_str = ", ".join(f"{pt} ({g} GSM)" for pt, g in valid_options)
			frappe.throw(
				f"Part {part.part_number} ({position_label}): invalid paper type/GSM. "
				f"Expected one of: {options_str}. "
				f"Got: {part.paper_type} ({part.gsm} GSM)."
			)

		if n == 1:
			check(parts[0], valid_single, "single part")
		else:
			check(parts[0], valid_first, "first part")
			for part in parts[1:-1]:
				check(part, valid_middle, "middle part")
			check(parts[-1], valid_last, "last part")
