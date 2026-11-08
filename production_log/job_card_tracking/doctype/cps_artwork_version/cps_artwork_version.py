"""CPS Artwork Version - immutable artwork files per specification (Stream A §7, 08/11/2026).

The rules are in :mod:`production_log.job_card_tracking.artwork_rules`; the
whitelisted actions (mark, record a change-request decision) are in
:mod:`production_log.job_card_tracking.cps_artwork`. This controller keeps a
version immutable and supersedes the previous one on insert.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from production_log.job_card_tracking import artwork_rules as rules


class CPSArtworkVersion(Document):
	def before_insert(self):
		existing = frappe.get_all(
			"CPS Artwork Version", filters={"spec": self.spec}, fields=["name", "version", "superseded"]
		)
		spec_revision = frappe.db.get_value("Customer Product Specification", self.spec, "vcl_revision") if frappe.get_meta(
			"Customer Product Specification").get_field("vcl_revision") else 0
		try:
			values = rules.insert_values(self.spec, spec_revision, self.file, frappe.session.user, frappe.utils.now(), existing)
		except ValueError as exc:
			frappe.throw(_(str(exc)), title=_("Artwork Version"))
		for fieldname, value in values.items():
			self.set(fieldname, value)
		self._previous_current = rules.current_version(existing)

	def validate(self):
		if not self.is_new():
			before = self.get_doc_before_save()
			changed = rules.immutable_changes(before, self)
			if changed:
				frappe.throw(
					_("{0} cannot change on an artwork version. Upload a new version instead.").format(", ".join(changed)),
					title=_("Artwork Version Immutable"),
				)
			if not frappe.flags.cps_artwork_server_write:
				for fieldname in rules.server_field_changes(before, self):
					# Discard what a form / REST / import sent; only the actions write these.
					self.set(fieldname, before.get(fieldname))
		self._validate_private_file()

	def _validate_private_file(self):
		if not self.file:
			return
		row = frappe.db.get_value("File", {"file_url": self.file}, ["is_private"], as_dict=True)
		if row is not None and not row.is_private:
			frappe.throw(_("Artwork must be a private file."), title=_("Artwork Version"))

	def after_insert(self):
		from production_log.job_card_tracking import cps_artwork

		cps_artwork.supersede_previous(self, getattr(self, "_previous_current", None))
		cps_artwork.reevaluate(self.spec)

	def on_trash(self):
		if self.approval_state == rules.STATE_CUSTOMER_APPROVED or int(self.superseded or 0):
			frappe.throw(_("An approved or superseded artwork version is history and cannot be deleted."))
