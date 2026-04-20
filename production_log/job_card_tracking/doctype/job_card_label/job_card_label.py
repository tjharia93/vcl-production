import frappe
from frappe.model.document import Document


class JobCardLabel(Document):
	def validate(self):
		self.validate_customer_product_spec()
		self.populate_specification_snapshot()
		self.validate_spec_fields()
		self.validate_quantity()
		self.validate_plate()
		self.validate_numbering()
		self.set_sales_rep_info()
		self.set_status()

	def validate_customer_product_spec(self):
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer}."
			)

		if spec.product_type != "Label":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not a Label specification "
				f"(found: {spec.product_type})."
			)

		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active (current status: {spec.status}). "
				"Please select an Active specification."
			)

	def populate_specification_snapshot(self):
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		self.specification_name = spec.specification_name
		self.job_size = spec.job_size
		self.dies = spec.dies
		self.label_length = spec.label_length
		self.label_width = spec.label_width
		self.cylinder_teeth = spec.cylinder_teeth
		self.plate_up = spec.plate_up
		self.plate_round = spec.plate_round
		self.packing_up = spec.packing_up
		self.material_type = spec.material_type
		self.packing_pieces = spec.packing_pieces
		self.gap_between = spec.gap_between
		self.side_trim = spec.side_trim
		self.numbering_required = spec.numbering_required
		self.standard_packing = spec.standard_packing
		self.weight_per_carton = spec.standard_weight_per_carton

		# Print colours block (shared with CP and Carton)
		for f in ("ink_type", "uses_c", "uses_m", "uses_y", "uses_k",
				  "number_of_colours", "colour_notes"):
			self.set(f, spec.get(f))

		self.spot_colours = []
		for sc in spec.get("spot_colours") or []:
			self.append("spot_colours", {
				"pantone_code": sc.pantone_code,
				"pantone_name": sc.pantone_name,
				"hex_preview":  sc.hex_preview,
				"cmyk_c":       sc.cmyk_c,
				"cmyk_m":       sc.cmyk_m,
				"cmyk_y":       sc.cmyk_y,
				"cmyk_k":       sc.cmyk_k,
				"notes":        sc.notes,
			})

	def validate_spec_fields(self):
		required_fields = {
			"label_length":  "Label Length",
			"label_width":   "Label Width",
			"material_type": "Material Type",
		}

		for fieldname, label in required_fields.items():
			if not self.get(fieldname):
				frappe.throw(f"{label} is required for Label Job Card.")

	def validate_quantity(self):
		if not self.quantity_ordered or self.quantity_ordered <= 0:
			frappe.throw("Quantity Ordered must be greater than 0.")

	def validate_plate(self):
		if not self.plate_status:
			frappe.throw("Plate Status is required. Please select New or Old.")

		if self.plate_status == "Old" and not self.plate_code:
			frappe.throw("Plate Code is required when Plate Status is 'Old'.")

		if self.plate_status == "New" and self.plate_code:
			frappe.throw("Plate Code must be empty when Plate Status is 'New'.")

	def validate_numbering(self):
		if not self.numbering_required:
			return

		if not self.numbering_start:
			frappe.throw("Numbering Start is required when Numbering Required is checked.")

		if not self.numbering_end:
			frappe.throw("Numbering End is required when Numbering Required is checked.")

	def set_sales_rep_info(self):
		if self.sales_rep:
			return

		current_user = frappe.session.user
		user_roles = frappe.get_roles(current_user)

		if "Sales User" in user_roles or "Sales Manager" in user_roles:
			self.sales_rep = current_user

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			self.status = "Submitted"
		elif self.docstatus == 2:
			self.status = "Cancelled"


@frappe.whitelist()
def get_label_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer and product type Label"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Label'
		AND status = 'Active'
		AND (name LIKE %(txt)s OR specification_name LIKE %(txt)s)
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
	""",
		{
			"customer": filters.get("customer"),
			"txt": "%%" + txt + "%%",
			"start": int(start),
			"page_len": int(page_len),
		},
	)
