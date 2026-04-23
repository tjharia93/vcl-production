import frappe
from frappe import _
from frappe.model.document import Document


class ProductionScheduleLine(Document):
	def before_save(self):
		if not (self.product_line or "").strip():
			# Belt-and-braces: UI stamps product_line from the active dept
			# tab. If a save path ever forgets to set it, fail loudly rather
			# than let orphaned rows pile up.
			frappe.throw(_("Product Line is required."))

		if self.is_manual:
			if not (self.description or "").strip():
				frappe.throw(_("Description is required for manual entries."))
			self.job_card_doctype = None
			self.job_card = None
		else:
			if not self.job_card_doctype or not self.job_card:
				frappe.throw(_("Job Card is required unless this is a manual entry."))
