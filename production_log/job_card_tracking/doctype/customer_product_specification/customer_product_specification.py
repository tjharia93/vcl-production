import frappe
from frappe.model.document import Document


class CustomerProductSpecification(Document):
	"""
	Customer Product Specification DocType for managing detailed product requirements.

	This DocType handles specifications for different product types (Computer Paper,
	Carton, Label, Exercise Books) with intelligent validation and auto-population
	from Dies for label products. Includes comprehensive validation rules and
	automatic field management based on product type.
	"""

	def validate(self):
		"""Main validation method called before saving."""
		self.validate_product_type()
		self.set_naming_series()
		self.validate_computer_paper()
		self.validate_label()
		self.validate_exercise_books()

	def validate_product_type(self):
		"""Validate that product type is selected."""
		if not self.product_type:
			frappe.throw("Product Type is required. Please select a product type.")

	def set_naming_series(self):
		"""Automatically set naming series based on product type."""
		if self.product_type and not self.naming_series:
			series_map = {
				"Computer Paper": "CPT-SPEC-.#####",
				"Carton": "CTN-SPEC-.#####",
				"Label": "LBL-SPEC-.#####",
				"Exercise Books": "EXB-SPEC-.#####",
			}
			self.naming_series = series_map.get(self.product_type)

	def validate_computer_paper(self):
		"""Validate computer paper specifications and colour of parts."""
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
			expected_part_no = i
			if int(part.part_number or 0) != expected_part_no:
				frappe.throw(
					f"Part numbers must be sequential. "
					f"Row {i}: expected part number {expected_part_no}, got {part.part_number}."
				)
			if not part.colour:
				frappe.throw(f"Row {i} in Colour of Parts is missing a colour.")

		self._validate_paper_type_and_gsm(parts)

	def validate_label(self):
		"""Validate label specifications and required fields."""
		if self.product_type != "Label":
			return

		required_fields = [
			("label_length", "Label Length"),
			("label_width", "Label Width"),
			("label_number_of_colours", "Number of Colours"),
			("material_type", "Material Type"),
		]

		for field_name, field_label in required_fields:
			if not getattr(self, field_name, None):
				frappe.throw(f"{field_label} is required for Label product type.")

	def validate_exercise_books(self):
		"""Validate exercise books specifications."""
		if self.product_type != "Exercise Books":
			return

		if not self.number_of_pages:
			frappe.throw("Number of Pages is required for Exercise Books.")

		if self.number_of_pages % 4 != 0:
			frappe.throw(
				f"Number of Pages must be a multiple of 4. Got {self.number_of_pages}."
			)

		if not self.number_of_parts:
			frappe.throw("Number of Parts is required for Computer Paper.")

		parts = self.colour_of_parts or []
		if len(parts) != self.number_of_parts:
			frappe.throw(
				f"Colour of Parts table must have exactly {self.number_of_parts} row(s), "
				f"but {len(parts)} row(s) found."
			)

		for i, part in enumerate(parts, start=1):
			expected_part_no = i
			if int(part.part_number or 0) != expected_part_no:
				frappe.throw(
					f"Part numbers must be sequential. "
					f"Row {i}: expected part number {expected_part_no}, got {part.part_number}."
				)
			if not part.colour:
				frappe.throw(f"Row {i} in Colour of Parts is missing a colour.")

		self._validate_paper_type_and_gsm(parts)

	def _validate_paper_type_and_gsm(self, parts):
		n = len(parts)

		valid_single = [("60 GSM Bond", 60), ("CB", 55), ("70 GSM Bond", 70)]
		valid_first = [("CB", 55)]
		valid_middle = [("CFB", 50)]
		valid_last = [("CF", 55)]

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

	def validate_label(self):
		if self.product_type != "Label":
			return

		required_fields = [
			("label_length", "Label Length"),
			("label_width", "Label Width"),
			("label_number_of_colours", "Number of Colours"),
			("material_type", "Material Type"),
		]

		for field_name, field_label in required_fields:
			if not getattr(self, field_name, None):
				frappe.throw(f"{field_label} is required for Label product type.")

	def validate_exercise_books(self):
		if self.product_type != "Exercise Books":
			return

		if not self.number_of_pages:
			frappe.throw("Number of Pages is required for Exercise Books.")

		if self.number_of_pages % 4 != 0:
			frappe.throw(
				f"Number of Pages must be a multiple of 4. Got {self.number_of_pages}."
			)
