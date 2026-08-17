import frappe
from frappe.model.document import Document
from frappe.utils import flt


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
		self.set_die_name()

	def validate_dimensions(self):
		"""Validate that length and width are positive values."""
		if self.length and self.length <= 0:
			frappe.throw("Length must be greater than zero.")

		if self.width and self.width <= 0:
			frappe.throw("Width must be greater than zero.")

	def set_die_name(self):
		"""Derive the Die Name label — "L:70 W:45" — from the dimensions.

		die_size is free text and inconsistent across the master: some records
		read "45 x 70" (width first), others "60 x 20" (length first), a few
		carry units or a shape. This field is the one that can be trusted,
		which is why it is derived here rather than typed.

		Custom Field (fixtures/custom_field.json), so guard on the field
		existing — a site whose fixtures have not synced yet must still save.
		"""
		if not self.meta.has_field("custom_die_name"):
			return

		self.custom_die_name = get_die_name(self.length, self.width)


def get_die_name(length, width):
	"""Return "L:70 W:45", or "" when neither dimension is set."""
	length = flt(length)
	width = flt(width)
	if length <= 0 and width <= 0:
		return ""

	def fmt(value):
		return f"{value:g}"

	return f"L:{fmt(length)} W:{fmt(width)}"
