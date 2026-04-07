import frappe
from frappe.model.document import Document


class Dies(Document):
	"""
	Dies DocType for managing printing die specifications.

	This DocType stores master data for printing dies including dimensions,
	printing configuration, material specifications, and associated orders.
	Used for auto-populating label specifications in Customer Product Specification.
	
	Die numbers are auto-generated using naming series format: DIE-00001, DIE-00002, etc.
	"""

	def validate(self):
		"""Main validation method called before saving."""
		self.validate_dimensions()

	def validate_dimensions(self):
		"""Validate that length and width are positive values."""
		if self.length and self.length <= 0:
			frappe.throw("Length must be greater than zero.")

		if self.width and self.width <= 0:
			frappe.throw("Width must be greater than zero.")
