import frappe
from frappe.model.document import Document


class JobCardComputerPaper(Document):
	def validate(self):
		self.validate_customer_product_spec()
		self.validate_spec_fields()
		self.validate_numbering()
		self.validate_plate()
		self.validate_quantity()
		self.set_sales_rep_info()
		self.set_status()

	def on_submit(self):
		self.set_status()

	def on_cancel(self):
		self.set_status()

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			if self.status not in ("In Progress", "Completed"):
				self.status = "In Progress"
		elif self.docstatus == 2:
			self.status = "Cancelled"

	def validate_spec_fields(self):
		if self.customer_product_spec and not self.job_size:
			frappe.throw("Job Size is required. Please re-select the Customer Product Specification.")
		if self.customer_product_spec and not self.number_of_parts:
			frappe.throw("Number of Parts is required. Please re-select the Customer Product Specification.")

	def validate_customer_product_spec(self):
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer}."
			)

		if spec.product_type != "Computer Paper":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not a Computer Paper specification "
				f"(found: {spec.product_type})."
			)

		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active (current status: {spec.status}). "
				"Please select an Active specification."
			)

	def validate_numbering(self):
		if not self.numbering_required:
			return

		if not self.numbering_start:
			frappe.throw("Numbering Start is required when Numbering Required is checked.")

		if not self.numbering_end:
			frappe.throw("Numbering End is required when Numbering Required is checked.")

	def validate_plate(self):
		if self.plate_status == "Old" and not self.plate_code:
			frappe.throw("Plate Code is required when Plate Status is 'Old'.")

		if self.plate_status == "New" and self.plate_code:
			frappe.throw("Plate Code must be empty when Plate Status is 'New'.")

	def validate_quantity(self):
		if not self.quantity_ordered or self.quantity_ordered <= 0:
			frappe.throw("Quantity Ordered must be greater than 0.")

	def set_sales_rep_info(self):
		if self.sales_rep:
			return

		current_user = frappe.session.user
		user_roles = frappe.get_roles(current_user)

		if "Sales User" in user_roles or "Sales Manager" in user_roles:
			self.sales_rep = current_user
			self.sales_rep_approval_date = frappe.utils.today()


@frappe.whitelist()
def get_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer and product type"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Computer Paper'
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
