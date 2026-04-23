import frappe
from frappe.model.document import Document


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
		self.validate_computer_paper()
		self.validate_carton()
		self.validate_label()
		self.validate_exercise_books()
		self.validate_etr()

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
