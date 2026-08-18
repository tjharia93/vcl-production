import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


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

		self.custom_die_name = get_die_name(
			self.length, self.width, self.across_ups, self.round_ups, self.teeth
		)


def get_die_name(length, width, across_ups=0, round_ups=0, teeth=0):
	"""Return "L70 W45 · 4×4 up · 92T" — size, how it runs, which cylinder.

	Size alone does not identify a die: nine of the 86 are 60 × 20, five are
	66 × 66, five are 32 × 32 — 56 records shared a size-only name. Adding ups
	and teeth makes 84 of 86 unique. Parts that are not set drop out rather
	than reading "0", so a die with no cylinder yet is "L60 W20 · 5 up".
	"""
	length, width, teeth = flt(length), flt(width), flt(teeth)
	across_ups, round_ups = cint(across_ups), cint(round_ups)

	def fmt(value):
		return f"{value:g}"

	parts = []
	if length > 0 or width > 0:
		parts.append(f"L{fmt(length)} W{fmt(width)}")
	if across_ups > 0 and round_ups > 0:
		parts.append(f"{across_ups}×{round_ups} up")
	elif across_ups > 0:
		parts.append(f"{across_ups} up")
	elif round_ups > 0:
		parts.append(f"{round_ups} round")
	if teeth > 0:
		parts.append(f"{fmt(teeth)}T")

	return " · ".join(parts)
