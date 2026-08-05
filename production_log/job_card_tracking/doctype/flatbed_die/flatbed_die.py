import frappe
from frappe.model.document import Document


class FlatbedDie(Document):
	"""A flatbed cutting-and-creasing die — a steel rule die, or cutting forme.

	Deliberately separate from ``Dies``, which is the flexo label register —
	its fields (across ups, round ups, teeth, PP materials) describe a ROTARY
	tool, cut into a cylinder and running against a reel. A flatbed die is
	steel rule bent into a plywood forme and struck against a stack of sheets.
	Different tool, different geometry, different register.

	Product-neutral on purpose. The same flatbed die cuts a monobox, a die-cut
	carton and a 2-ply cup sleeve, so the register is named for the tool rather
	than for whichever product first needed one.

	The geometry here is the planning master: a Customer Product Specification
	links a die and inherits blank size, ups and sheet size from it, so the
	spec and the tool cannot silently disagree.
	"""

	def validate(self):
		self.validate_geometry()
		self.validate_window()

	def validate_geometry(self):
		for fieldname, label in (
			("blank_length", "Flat Blank Length (mm)"),
			("blank_width", "Flat Blank Width (mm)"),
			("ups_per_sheet", "Ups per Sheet"),
		):
			if not self.get(fieldname) or self.get(fieldname) <= 0:
				frappe.throw(f"{label} must be greater than zero.")

		if self.sheet_size == "Other":
			if not self.sheet_length or not self.sheet_width:
				frappe.throw(
					"Sheet Size is 'Other' — enter the Sheet Length and Sheet Width in mm."
				)

	def validate_window(self):
		if not self.has_window:
			return

		if not self.window_width or not self.window_height:
			frappe.throw(
				"This die is marked as having a window — enter the aperture width and height."
			)

		# A window cannot be larger than the blank it is cut into. Caught here
		# because the error is silent downstream: the spec inherits the numbers
		# and nothing else ever compares them.
		if self.window_width >= self.blank_width or self.window_height >= self.blank_length:
			frappe.throw(
				"The window aperture is larger than the flat blank. "
				"Check the window and blank dimensions."
			)
