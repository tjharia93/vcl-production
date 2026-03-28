import frappe
from frappe.model.document import Document


class ProductionStation(Document):
    def validate(self):
        if self.max_reels < 1 or self.max_reels > 4:
            frappe.throw(
                frappe._("Maximum Reels must be between 1 and 4. Got: {0}").format(self.max_reels)
            )
