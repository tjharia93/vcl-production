import frappe
from frappe.model.document import Document


SNAPSHOT_FIELDS = (
	("specification_name",      "specification_name"),
	("etr_substrate",           "substrate"),
	("etr_substrate_other",     "substrate_other"),
	("etr_gsm",                 "gsm"),
	("etr_core_id",             "core_id"),
	("etr_jumbo_width",         "jumbo_width"),
	("etr_output_type",         "output_type"),
	("etr_finished_width",      "finished_width"),
	("etr_finished_diameter",   "finished_diameter"),
	("etr_finished_reel_length", "finished_reel_length"),
	("etr_print_type",          "print_type"),
	("ink_type",                "ink_type"),
	("uses_c",                  "uses_c"),
	("uses_m",                  "uses_m"),
	("uses_y",                  "uses_y"),
	("uses_k",                  "uses_k"),
	("number_of_colours",       "number_of_colours"),
	("colour_notes",            "colour_notes"),
)

SPOT_COLOUR_FIELDS = (
	"pantone_code", "pantone_name", "hex_preview",
	"cmyk_c", "cmyk_m", "cmyk_y", "cmyk_k", "notes",
)


class JobCardETR(Document):

	def validate(self):
		self.validate_customer_product_spec()
		self.populate_specification_snapshot()
		self.validate_operations()
		self.validate_output_type_vs_operations()
		self.validate_printing_fields()
		self.validate_slitting_fields()
		self.recalculate_number_of_colours()
		self.calculate_print_totals()
		self.set_status()

	def on_submit(self):
		self.set_status()

	def on_cancel(self):
		self.set_status()

	# ── Validation ────────────────────────────────────────────────────────────

	def validate_customer_product_spec(self):
		if not self.customer_product_spec:
			return
		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)
		if spec.customer != self.customer:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer}."
			)
		if spec.product_type != "ETR (Reel to Reel Printing)":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not an ETR (Reel to Reel Printing) "
				f"specification (found: {spec.product_type})."
			)
		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active "
				f"(current status: {spec.status}). Please select an Active specification."
			)

	def validate_operations(self):
		if not self.printing_required and not self.slitting_required:
			frappe.throw(
				"At least one operation must be selected: Printing Required or Slitting Required."
			)

	def validate_output_type_vs_operations(self):
		if not self.output_type:
			return
		if self.output_type == "ETR Plain Rolls" and self.printing_required and not self.slitting_required:
			frappe.throw(
				"Output Type is 'ETR Plain Rolls' but only Printing is selected. "
				"Plain rolls require Slitting. Either enable Slitting or change the Output Type."
			)
		if self.output_type == "Printed Reel" and self.slitting_required and not self.printing_required:
			frappe.throw(
				"Output Type is 'Printed Reel' but only Slitting is selected. "
				"A Printed Reel requires Printing. Either enable Printing or change the Output Type."
			)

	def validate_printing_fields(self):
		if not self.printing_required:
			return
		if not (self.plate_details or []):
			frappe.throw("Printing section: At least one row in Plate Details is required.")

	def validate_slitting_fields(self):
		if not self.slitting_required:
			return
		if not self.slit_output_width or self.slit_output_width <= 0:
			frappe.throw("Slitting section: Output Width (mm) must be greater than 0.")
		if not self.slit_output_diameter or self.slit_output_diameter <= 0:
			frappe.throw("Slitting section: Output Diameter (mm) must be greater than 0.")

	# ── Snapshot from CPS ─────────────────────────────────────────────────────

	def populate_specification_snapshot(self):
		"""Copy spec fields onto this job card so it is self-contained at print time."""
		if not self.customer_product_spec:
			return
		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		for spec_field, jc_field in SNAPSHOT_FIELDS:
			value = getattr(spec, spec_field, None)
			if value is not None and value != "":
				setattr(self, jc_field, value)

		# Spot colours: replace job-card table with a deep copy of the spec table.
		self.spot_colours = []
		for src in (spec.spot_colours or []):
			row = self.append("spot_colours", {})
			for f in SPOT_COLOUR_FIELDS:
				setattr(row, f, getattr(src, f, None))

	# ── Computed Fields ───────────────────────────────────────────────────────

	def recalculate_number_of_colours(self):
		if not self.printing_required:
			self.number_of_colours = 0
			return
		ticks = sum(1 for f in ("uses_c", "uses_m", "uses_y", "uses_k") if getattr(self, f))
		spots = len(self.spot_colours or [])
		self.number_of_colours = ticks + spots

	def calculate_print_totals(self):
		if not self.printing_required:
			self.print_total_metres_out = 0
			self.print_total_reels_out = 0
			return
		rows = self.print_reel_output or []
		self.print_total_metres_out = sum((row.metres_printed or 0) for row in rows)
		self.print_total_reels_out  = len(rows)

	# ── Status sync ───────────────────────────────────────────────────────────

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			# On submit, default to In Progress unless user has already advanced to Completed.
			if self.status not in ("In Progress", "Completed"):
				self.status = "In Progress"
		elif self.docstatus == 2:
			self.status = "Cancelled"


# ── Whitelisted query for the customer_product_spec link (JSON get_query) ─────

@frappe.whitelist()
def get_etr_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer, ETR product type, and Active status."""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}
	if not filters.get("customer"):
		return []
	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		  AND product_type = 'ETR (Reel to Reel Printing)'
		  AND status = 'Active'
		  AND (name LIKE %(txt)s OR specification_name LIKE %(txt)s)
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"customer":  filters["customer"],
			"txt":       f"%{txt or ''}%",
			"start":     int(start or 0),
			"page_len":  int(page_len or 20),
		},
	)
