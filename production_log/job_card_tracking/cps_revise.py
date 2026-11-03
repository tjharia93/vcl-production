"""Revise a SUBMITTED Customer Product Specification in place.

Never cancels, never amends. The spec keeps its name, job cards already raised
keep their own snapshot of the old values, and Frappe's Version log records the
diff field by field.

Why in place, and not amend
---------------------------

A Job Card copies the colours it needs off the specification at selection time
into its own child table. It is a snapshot, not a live fetch, so changing the
spec never rewrites an already-raised card - which makes amending pointless, and
expensive: ``check_no_back_links_exist`` refuses to cancel a document a submitted
one links to, so the spec will not cancel until its job card is cancelled first.
CPT-SPEC-00049 was amended once and its job card JC-CPT-2026-00045 is cancelled
to this day. That is the cost, and it is why this exists.

Why this is Python and no longer a Server Script
-------------------------------------------------

This began life as the Server Script ``cps_revise``, which could only revise the
Computer Paper ``colour_of_parts`` table. Extending it to Carton meant giving it
the board-plan geometry, and a Server Script runs under ``safe_exec`` where
imports are forbidden - so the formula would have had to be **inlined**, making a
fourth copy of arithmetic that had already drifted between its existing three
(see :mod:`cps_carton_board`). Moving here lets both product types import their
rules from the one module that owns them.

The Server Script is removed by the patch that installs this, in the same
migrate, so there is never a moment where two things answer to the same name.

What this must validate itself
-------------------------------

On an update-after-submit Frappe does **not** run ``validate()``, and neither
``Before Save`` server scripts nor the controller's own checks fire. Everything
this writes is therefore validated here, in this module, or it is unguarded.
That is the single most important thing to know before adding a field to it.
"""

import json

import frappe

from production_log.job_card_tracking import cps_carton_board as board
from production_log.job_card_tracking import cps_cp_rules
from production_log.job_card_tracking import cps_cp_weight
from production_log.job_card_tracking import cps_revise_rules as rules

COMPUTER_PAPER = "Computer Paper"
CARTON = "Carton"
# Desk-made, in no app repo; what ``artwork_tracker`` links to.
ARTWORK_TRACKER_DOCTYPE = "Design and Artwork Tracker"

# Why each reason is refused, in the operator's words.
_NOT_APPLICABLE = {
	board.SFK: "SFK is an un-glued web - there is no blank to plan.",
	board.DIE_CUT: "Die Cut blanks vary per job, so there is no formula to derive.",
	board.NO_STYLE: "This specification has no carton style, so the blank cannot be derived.",
	board.INCOMPLETE_DIMENSIONS: (
		"This specification is missing a length, width or height, so the blank "
		"cannot be derived. Correct the dimensions first."
	),
}


def _rows(payload):
	"""Parse a JSON payload from the dialog, tolerating an already-parsed value."""
	if not payload:
		return None
	return json.loads(payload) if isinstance(payload, str) else payload


@frappe.whitelist()
def revise(spec, reason, parts=None, carton=None, ink=None, packing=None, price=None, build=None,
		size=None, details=None):
	"""Apply a reasoned, versioned revision to a submitted specification.

	Returns ``{"ok": True, "spec": <name>, "changes": [<human summary>, ...]}``.

	A revision with a reason and no field changes is allowed and recorded as a
	note - saying in the record why nothing needed to change is worth having. A
	revision that *supplies* values which turn out to be identical is refused,
	because that is a no-op the operator believed was a change.

	Size, the number of parts and the details (name, item, numbering, printed
	side, notes, artwork) were fixed after submit while a job card read the
	spec live. They no longer do: the Sales Order line freezes a snapshot at
	submit and the job card is built from that, so a revision only reaches
	orders placed after it (decided 03-11-2026).
	"""
	reason = (reason or "").strip()
	if not spec:
		frappe.throw("spec is required.")
	if not reason:
		frappe.throw("A reason for the revision is required.")

	doc = frappe.get_doc("Customer Product Specification", spec)

	if doc.docstatus == 0:
		frappe.throw("This specification is still a Draft - edit it directly, no revision needed.")
	if doc.docstatus == 2:
		frappe.throw("This specification is cancelled and cannot be revised.")

	changes = []
	supplied = False
	weights_before = _weights(doc)

	# Details first: the item a new part count needs may arrive in the same revision.
	details_in = _rows(details)
	if details_in:
		supplied = True
		changes.extend(_apply_details(doc, details_in))

	parts_in = _rows(parts)
	parts_before = len(doc.get("colour_of_parts") or [])
	if parts_in:
		supplied = True
		changes.extend(_apply_parts(doc, parts_in))
		if len(doc.colour_of_parts) != parts_before and not doc.get("linked_item"):
			frappe.throw(
				"Changing the number of parts changes what the specification is, so it must "
				"name its Item. Choose the item in the same revision."
			)

	size_in = _rows(size)
	if size_in:
		supplied = True
		changes.extend(_apply_size(doc, size_in))

	# Size and build first: the board plan below is derived from them.
	build_in = _rows(build)
	moved = set()
	if build_in:
		supplied = True
		build_changes, moved = _apply_build(doc, build_in)
		changes.extend(build_changes)

	# Re-derive the board plan whenever the blank or the board weight can have
	# moved, even if the operator typed nothing in the Board Plan section.
	carton_in = _rows(carton)
	replan = bool(moved & set(rules.GEOMETRY_FIELDS + rules.LAYER_GSM_FIELDS))
	if carton_in is not None or replan:
		supplied = supplied or carton_in is not None
		changes.extend(_apply_carton(
			doc, carton_in or {},
			rebuilt=replan,
			new_flap=bool(moved & set(rules.FLAP_FIELDS)),
		))

	ink_in = _rows(ink)
	if ink_in is not None:
		supplied = True
		changes.extend(_apply_ink(doc, ink_in))

	packing_in = _rows(packing)
	if packing_in is not None:
		_require_packing_write(doc)
		supplied = True
		changes.extend(_apply_packing(doc, packing_in))

	price_in = _rows(price)
	if price_in:
		supplied = True
		changes.extend(_apply_price(doc, price_in))

	if supplied and not changes:
		frappe.throw("Nothing changed - revision not recorded.")

	if changes:
		changes.extend(_recompute_weights(doc, weights_before))

	_stamp(doc, reason, changes)
	doc.save()

	return {"ok": True, "spec": doc.name, "changes": changes}


def _apply_parts(doc, rows):
	"""Change the Colour of Parts table of a Computer Paper specification.

	The same number of rows edits each part in place. A different number
	rebuilds the table to the new count, with Number of Parts to match; paper
	and GSM then follow the new positions (the third ply of a three-part set is
	CF, of a four-part set CFB), which the check below enforces either way.
	"""
	if doc.product_type != COMPUTER_PAPER:
		frappe.throw("Colour of Parts applies to Computer Paper specifications only.")

	count = len(rows)
	error = rules.part_count_error(count, cps_cp_rules.MAX_DEFAULT_PARTS)
	if error:
		frappe.throw(error)

	# validate() does NOT re-run on update-after-submit, so the paper type / GSM
	# rule is enforced here against the same positions the controller uses.
	expected = cps_cp_rules.part_positions(count)
	for index, row in enumerate(rows):
		paper_type = (row.get("paper_type") or "").strip()
		gsm = int(row.get("gsm") or 0)
		if not (row.get("colour") or "").strip():
			frappe.throw("Part {0} is missing a colour.".format(index + 1))

		if count == 1:
			allowed = list(cps_cp_rules.SINGLE_PART_OPTIONS)
		else:
			allowed = [expected[index]]

		if (paper_type, gsm) not in allowed:
			frappe.throw(
				"Part {0}: invalid paper type / GSM. Expected one of: {1}. Got: {2} ({3} GSM).".format(
					index + 1,
					", ".join("{0} ({1} GSM)".format(p, g) for p, g in allowed),
					paper_type,
					gsm,
				)
			)

	if count != len(doc.colour_of_parts):
		return _rebuild_parts(doc, rows)

	changes = []
	for index, row in enumerate(rows):
		target = doc.colour_of_parts[index]
		label = "Part {0}".format(target.part_number)
		fields = [
			("colour", (row.get("colour") or "").strip().upper()),
			("paper_type", (row.get("paper_type") or "").strip()),
			("gsm", int(row.get("gsm") or 0)),
		]
		# "Used for" is optional in the payload: absent leaves it alone, blank
		# puts back the paper's own description.
		if "purpose" in row:
			fields.append(("purpose", _purpose(row, (row.get("paper_type") or "").strip())))
		for field, new in fields:
			old = target.get(field)
			if field == "colour":
				same = (old or "").strip().upper() == new
			elif field == "gsm":
				same = int(old or 0) == new
			else:
				same = (old or "") == new
			if not same:
				changes.append("{0} {1}: {2} -> {3}".format(label, field, _shown(old), _shown(new)))
				target.set(field, new)
	return changes


def _purpose(row, paper_type, previous=None):
	"""A part's "Used for": as given, else what it said before, else the paper's own words.

	A previous purpose that is only the old position's paper description is not
	carried, because the position may just have changed underneath it.
	"""
	given = (row.get("purpose") or "").strip()[:140]
	if given:
		return given
	previous = (previous or "").strip()
	if previous and previous not in cps_cp_rules.PART_PURPOSE.values():
		return previous
	return cps_cp_rules.PART_PURPOSE.get(paper_type, "")


def _rebuild_parts(doc, rows):
	"""Replace the parts table with ``rows`` and set Number of Parts to match."""
	old = [r.as_dict() for r in doc.colour_of_parts]
	old_count = len(old)
	changes = ["Number of parts: {0} -> {1}".format(doc.number_of_parts or old_count, len(rows))]

	doc.set("colour_of_parts", [])
	for index, row in enumerate(rows):
		paper_type = (row.get("paper_type") or "").strip()
		previous = old[index] if index < old_count else {}
		new = {
			"part_number": index + 1,
			"colour": (row.get("colour") or "").strip().upper(),
			"paper_type": paper_type,
			"gsm": int(row.get("gsm") or 0),
			"purpose": _purpose(row, paper_type, previous.get("purpose")),
		}
		doc.append("colour_of_parts", new)
		shown = "{0} {1} ({2} GSM)".format(new["colour"], new["paper_type"], new["gsm"])
		if not previous:
			changes.append("Part {0} added: {1}".format(index + 1, shown))
			continue
		was = "{0} {1} ({2} GSM)".format(
			(previous.get("colour") or "").strip().upper(), previous.get("paper_type"), int(previous.get("gsm") or 0))
		if was != shown:
			changes.append("Part {0}: {1} -> {2}".format(index + 1, was, shown))
	for index in range(len(rows), old_count):
		changes.append("Part {0} removed: {1} {2}".format(
			index + 1, (old[index].get("colour") or "").strip().upper(), old[index].get("paper_type")))
	doc.number_of_parts = len(rows)
	return changes


def _apply_size(doc, requested):
	"""Change the finished size (Computer Paper) and the Job Size.

	The millimetres and every weight are derived from the inches; they are
	recomputed by :func:`_recompute_weights` once all sections are applied.
	"""
	changes = []
	for field, value in requested.items():
		new, error = rules.coerce_size(field, value, doc.product_type)
		if error:
			frappe.throw(error)
		old = doc.get(field)
		same = float(old or 0) == new if isinstance(new, float) else (old or "").strip() == new
		if not same:
			changes.append("{0}: {1} -> {2}".format(doc.meta.get_label(field) or field, _shown(old), new))
			doc.set(field, new)
	return changes


def _apply_details(doc, requested):
	"""Change the name, item, notes, numbering, printed side or artwork link."""
	changes = []
	for field, value in requested.items():
		new, error = rules.coerce_detail(field, value, doc.product_type, doc.print_type)
		if error:
			frappe.throw(error)
		old = (doc.get(field) or "").strip() if isinstance(doc.get(field), str) else doc.get(field)
		if (old or "") == new:
			continue
		if field == "linked_item":
			_check_item(doc, new)
		elif field == "artwork_tracker" and new:
			if not frappe.db.exists(ARTWORK_TRACKER_DOCTYPE, new):
				frappe.throw("There is no Design and Artwork job called {0}.".format(new))
		elif field == "numbering_answer":
			for fieldname, stored in (cps_cp_rules.numbering_answer_fields(new) or {}).items():
				doc.set(fieldname, stored)
		changes.append("{0}: {1} -> {2}".format(doc.meta.get_label(field) or field, _shown(old), _shown(new)))
		doc.set(field, new)
		if field == "artwork_tracker" and new and doc.get(cps_cp_rules.ARTWORK_NOT_READY_FIELD):
			# A linked job is the answer the "not ready yet" flag was waiting for.
			doc.set(cps_cp_rules.ARTWORK_NOT_READY_FIELD, 0)
			changes.append("Artwork not ready yet: on -> off")
	return changes


def _check_item(doc, item_code):
	"""The new Item must exist, be enabled and, for Computer Paper, match the print type."""
	item = frappe.db.get_value("Item", item_code, ["name", "disabled", "item_group"], as_dict=True)
	if not item:
		frappe.throw("There is no Item called {0}.".format(item_code))
	if item.disabled:
		frappe.throw("Item {0} is disabled. Choose an enabled item.".format(item_code))
	if doc.product_type == COMPUTER_PAPER:
		expected = cps_cp_rules.ITEM_GROUP_PRINT_TYPE.get(item.item_group)
		if expected and expected != doc.print_type:
			frappe.throw(
				"Item {0} is a {1} item, but this specification is {2}. Choose an item that "
				"matches the print type.".format(item_code, item.item_group, doc.print_type)
			)


def _weights(doc):
	"""The weight figures a revision can move, as they stand."""
	return {f: doc.get(f) for f in _WEIGHT_FIELDS if doc.meta.has_field(f)}


_WEIGHT_FIELDS = (cps_cp_weight.PER_SET_FIELD, cps_cp_weight.GROSS_FIELD, cps_cp_weight.STANDARD_WEIGHT_FIELD)


def _recompute_weights(doc, before):
	"""Re-derive a Computer Paper spec's millimetres and weights; report what moved.

	``before_update_after_submit`` would do the same on save, but only after the
	revision note is written, so it is done here first to put the new weights
	in the record of why they moved.
	"""
	if doc.product_type != COMPUTER_PAPER:
		return []
	doc.apply_computer_paper_weights()
	changes = []
	for field, old in before.items():
		new = doc.get(field)
		if float(old or 0) != float(new or 0):
			changes.append("{0}: {1} -> {2} (recomputed)".format(
				doc.meta.get_label(field) or field, old or 0, new or 0))
	return changes


def _shown(value):
	return "empty" if value in (None, "") else value


def _apply_build(doc, requested):
	"""Change a carton's size and build: dimensions, style, ply, flute, joint, layers.

	Each value is coerced and the resulting carton checked as a whole, because
	validate() does not run on update-after-submit. Job Size is rewritten from
	the dimensions when they move, so the size a rep sees on an order line is the
	size the board plan is struck from.
	"""
	if doc.product_type != CARTON:
		frappe.throw("Size and build apply to Carton specifications only.")

	clean = {}
	for field, value in requested.items():
		new, error = rules.coerce_build(field, value)
		if error:
			frappe.throw(error)
		clean[field] = new

	after = doc.as_dict()
	after.update(clean)
	error = rules.build_error(after)
	if error:
		frappe.throw(error)

	changes = []
	moved = set()
	for field in rules.CARTON_BUILD_FIELDS:
		if field not in clean:
			continue
		old = doc.get(field)
		new = clean[field]
		same = int(old or 0) == new if isinstance(new, int) else (old or "") == new
		if not same:
			changes.append("{0}: {1} -> {2}".format(doc.meta.get_label(field) or field, _shown(old), _shown(new)))
			doc.set(field, new)
			moved.add(field)

	if changes:
		size = rules.job_size_text(doc.ctn_length_mm, doc.ctn_width_mm, doc.ctn_height_mm, doc.ply)
		if any(f in clean for f in ("ctn_length_mm", "ctn_width_mm", "ctn_height_mm", "ply")) and doc.job_size != size:
			changes.append("Job Size: {0} -> {1}".format(doc.job_size or "empty", size))
			doc.job_size = size
	return changes, moved


def _apply_carton(doc, requested, rebuilt=False, new_flap=False):
	"""Fill in the Board Plan of a Carton specification.

	Every derived figure is recomputed here from the specification's own
	dimensions rather than taken from ``requested``, so a caller cannot post a
	board plan that does not follow from the carton it describes. Only the flap
	and the two actual board sizes are the operator's to state.
	"""
	if doc.product_type != CARTON:
		frappe.throw("The Board Plan applies to Carton specifications only.")

	flap = requested.get("ctn_flap_mm")
	# A flap measured for the old width or style does not fit the new carton:
	# re-derive it unless the operator states one for the new carton.
	if new_flap and not flap and doc.product_type_carton != board.STYLE_TRAY:
		flap = board.auto_flap(doc.ctn_width_mm)

	values, reason = board.revisable_changes(doc.as_dict(), requested, flap_override=flap)
	if reason:
		if rebuilt and not requested:
			# The new build has no plannable blank (SFK, Die Cut): nothing to derive.
			return []
		frappe.throw(_NOT_APPLICABLE.get(reason, "The board plan cannot be derived."))

	changes = []
	for field in sorted(values):
		old = doc.get(field)
		changes.append(
			"{0}: {1} -> {2}".format(
				doc.meta.get_label(field) or field, old or 0, values[field]
			)
		)
		doc.set(field, values[field])
	return changes


def _apply_ink(doc, requested):
	"""Change the print colours: process inks and the spot colour rows.

	``requested`` may carry any of ``uses_c/m/y/k`` and ``spot_colours`` (a list
	of ``{"pantone_code": ...}``); anything absent is left alone. The count is
	recomputed here because the controller's ``recalculate_number_of_colours``
	does not run on update-after-submit.
	"""
	if doc.product_type not in rules.INK_PRODUCT_TYPES:
		frappe.throw("{0} specifications do not carry print colours.".format(doc.product_type))

	changes = []
	for field in rules.PROCESS_INKS:
		if field not in requested:
			continue
		new = 1 if requested[field] else 0
		old = 1 if doc.get(field) else 0
		if new != old:
			changes.append("{0}: {1} -> {2}".format(
				doc.meta.get_label(field) or field, "on" if old else "off", "on" if new else "off"))
			doc.set(field, new)

	if "spot_colours" in requested:
		new_codes = [(r.get("pantone_code") or "").strip() for r in requested["spot_colours"] or []]
		if "" in new_codes:
			frappe.throw("Every spot colour row needs a Pantone colour.")
		old_codes = [r.pantone_code for r in doc.spot_colours]
		if sorted(new_codes) != sorted(old_codes):
			changes.append("Spot colours: {0} -> {1}".format(
				", ".join(old_codes) or "none", ", ".join(new_codes) or "none"))
			doc.set("spot_colours", [])
			for code in new_codes:
				doc.append("spot_colours", {"pantone_code": code})

	process = sum(1 for f in rules.PROCESS_INKS if doc.get(f))
	spots = len(doc.spot_colours)
	if changes:
		error = rules.ink_error(doc.print_type, process, spots)
		if error:
			frappe.throw(error)
	count = process + spots
	if doc.number_of_colours != count:
		doc.number_of_colours = count
		if changes:
			changes.append("Number of colours -> {0}".format(count))
	return changes


def _apply_packing(doc, requested):
	"""Change the packing fields that belong to this product type."""
	allowed = rules.packing_fields(doc.product_type)
	unknown = sorted(set(requested) - set(allowed))
	if unknown:
		frappe.throw("{0} cannot be revised on a {1} specification.".format(
			", ".join(unknown), doc.product_type))

	changes = []
	for field, kind in allowed.items():
		if field not in requested:
			continue
		new, error = rules.coerce_packing(field, kind, requested[field])
		if error:
			frappe.throw(error)
		old = doc.get(field)
		same = (str(old or "").strip() == str(new)) if kind == "text" else (float(old or 0) == float(new))
		if not same:
			changes.append("{0}: {1} -> {2}".format(doc.meta.get_label(field) or field, old or "empty", new))
			doc.set(field, new)
	return changes


def _apply_price(doc, row):
	"""Add a new price row. Never edits one, never approves one.

	A price change is a new row with a later Effective From, not an edit
	(design 6.2). The row lands as Draft: approval stays with a Sales Master
	Manager through ``approve_cps_price``, so revising a spec cannot be a way
	round it. Duplicate effective dates are refused by ``validate_pricing`` in
	``before_update_after_submit``.
	"""
	error = rules.price_row_error(row)
	if error:
		frappe.throw(error)
	doc.append("pricing", {
		"valid_from": row["valid_from"],
		"rate": float(row["rate"]),
		"uom": row["uom"],
		"vat_inclusive": 1 if row.get("vat_inclusive") else 0,
		"source": "Manual",
		"notes": (row.get("notes") or "").strip(),
		"approval_status": "Draft",
	})
	return ["New price {0} per {1}{2} from {3} (Draft - needs approval)".format(
		float(row["rate"]), row["uom"], ", VAT inclusive" if row.get("vat_inclusive") else "",
		row["valid_from"])]


def _stamp(doc, reason, changes):
	"""Append this revision to the human-readable Revision Notes trail."""
	summary = "; ".join(changes) if changes else "note only (no field changes)"
	entry = "[{0}] {1}\nReason: {2}\nChanged: {3}".format(
		frappe.utils.now()[:16], frappe.session.user, reason, summary
	)
	doc.revision_notes = ((doc.revision_notes or "") + "\n\n" + entry).strip()


def _require_packing_write(doc):
	"""Refuse a packing revision from a user who cannot write packing.

	Packing is permlevel 1 (CR21). Without this check, Frappe would silently
	put the old value back on save while the revision log recorded a change
	that never happened.
	"""
	if not doc.has_permlevel_access_to("standard_packing", permission_type="write"):
		frappe.throw(
			"Packing can only be revised by VCL Management, Release to Production or a manufacturing manager."
		)
