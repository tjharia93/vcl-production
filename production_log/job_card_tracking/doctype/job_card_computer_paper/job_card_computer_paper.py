import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class JobCardComputerPaper(Document):
	def validate(self):
		self.validate_customer_product_spec()
		self.validate_spec_fields()
		self.validate_numbering()
		self.validate_plate()
		self.validate_quantity()
		self.set_sales_rep_info()
		self.calculate_qty_pending()
		self.update_production_timestamps()
		self.warn_completed_under_qty()

	def before_save(self):
		self.enforce_completed_lock()

	def validate_spec_fields(self):
		if self.customer_product_spec and not self.job_size:
			frappe.throw("Job Size is required. Please re-select the Customer Product Specification.")
		if self.customer_product_spec and not self.number_of_colours:
			frappe.throw("Number of Colours is required. Please re-select the Customer Product Specification.")
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

	def calculate_qty_pending(self):
		ordered = self.quantity_ordered or 0
		completed = self.qty_completed or 0
		self.qty_pending = ordered - completed

		if self.qty_pending < 0:
			frappe.msgprint(
				_("Completed quantity ({0}) exceeds ordered quantity ({1}). "
				  "Qty Pending is negative, indicating overproduction.").format(
					completed, ordered
				),
				indicator="orange",
				alert=True,
			)

	def update_production_timestamps(self):
		pc_fields = (
			"production_status", "production_stage", "planned_for_date",
			"priority", "qty_completed", "production_comments",
		)

		if not self.is_new():
			for f in pc_fields:
				if self.has_value_changed(f):
					self.last_production_update = now_datetime()
					break

		if self.production_status == "Completed" and not self.completed_on:
			self.completed_on = now_datetime()
		elif self.production_status != "Completed":
			self.completed_on = None

	def warn_completed_under_qty(self):
		if self.production_status != "Completed":
			return

		ordered = self.quantity_ordered or 0
		completed = self.qty_completed or 0

		if completed < ordered:
			frappe.msgprint(
				_("Production status is Completed but completed quantity ({0}) is still "
				  "less than ordered quantity ({1}). Please confirm this is intentional.").format(
					completed, ordered
				),
				indicator="orange",
				alert=True,
			)

	def enforce_completed_lock(self):
		if self.is_new() or self.docstatus != 1:
			return

		db_status = frappe.db.get_value(self.doctype, self.name, "production_status")

		if db_status in ("Completed", "Cancelled"):
			privileged = {"System Manager", "Production Manager"}
			user_roles = set(frappe.get_roles(frappe.session.user))

			if not user_roles.intersection(privileged):
				frappe.throw(
					_("This Job Card is {0}. Only System Manager or Production Manager "
					  "can reopen it.").format(db_status)
				)


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
