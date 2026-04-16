import frappe
from frappe import _
from frappe.model.document import Document


class JobCardCarton(Document):
	def validate(self):
		self.validate_customer_product_spec()
		self.validate_dimensions()
		self.validate_quantity()

	def validate_customer_product_spec(self):
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer_name:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer_name}."
			)

		if spec.product_type != "Carton":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not a Carton specification "
				f"(found: {spec.product_type})."
			)

		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active (current status: {spec.status}). "
				"Please select an Active specification."
			)

	def validate_dimensions(self):
		if not self.ctn_length_mm or self.ctn_length_mm <= 0:
			frappe.throw(_("Carton Length (mm) must be greater than 0."))

		if not self.ctn_width_mm or self.ctn_width_mm <= 0:
			frappe.throw(_("Carton Width (mm) must be greater than 0."))

		if self.ply != "SFK":
			if not self.ctn_height_mm or self.ctn_height_mm <= 0:
				frappe.throw(
					_("Carton Height (mm) must be greater than 0 unless Ply is SFK.")
				)

	def validate_quantity(self):
		if not self.quantity_ordered:
			frappe.throw(_("Quantity Ordered is required."))

		try:
			qty = int(self.quantity_ordered)
		except (ValueError, TypeError):
			frappe.throw(_("Quantity Ordered must be a valid number."))

		if qty <= 0:
			frappe.throw(_("Quantity Ordered must be greater than 0."))


@frappe.whitelist()
def get_carton_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer and product type Carton"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Carton'
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
