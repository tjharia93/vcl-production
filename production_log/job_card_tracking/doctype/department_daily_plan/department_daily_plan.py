import frappe
from frappe import _
from frappe.model.document import Document


class DepartmentDailyPlan(Document):
	def validate(self):
		self.check_duplicate()
		self.validate_lines()
		self.calculate_manual_pending()

	def before_save(self):
		self.enforce_closed_lock()

	def check_duplicate(self):
		filters = {
			"plan_date": self.plan_date,
			"department": self.department,
			"status": ["!=", "Cancelled"],
		}

		if self.shift:
			filters["shift"] = self.shift

		if not self.is_new():
			filters["name"] = ["!=", self.name]

		existing = frappe.db.get_value("Department Daily Plan", filters, "name")
		if existing:
			shift_label = f" ({self.shift} shift)" if self.shift else ""
			frappe.throw(
				_("A plan already exists for {0} - {1}{2}: {3}").format(
					self.plan_date, self.department, shift_label, existing
				)
			)

	def validate_lines(self):
		for row in self.plan_lines:
			if row.entry_type == "Job Card":
				if not row.job_card_type:
					frappe.throw(
						_("Row {0}: Job Card Type is required when Entry Type is Job Card.").format(row.idx)
					)
				if row.job_card_type == "Computer Paper" and not row.computer_paper_job_card:
					frappe.throw(
						_("Row {0}: Computer Paper Job Card is required.").format(row.idx)
					)
				if row.job_card_type == "Label" and not row.label_job_card:
					frappe.throw(
						_("Row {0}: Label Job Card is required.").format(row.idx)
					)
				if row.job_card_type == "Carton" and not row.carton_job_card:
					frappe.throw(
						_("Row {0}: Carton Job Card is required.").format(row.idx)
					)

			elif row.entry_type == "Manual":
				if not row.manual_job_type:
					frappe.throw(
						_("Row {0}: Manual Job Type is required when Entry Type is Manual.").format(row.idx)
					)

	def calculate_manual_pending(self):
		for row in self.plan_lines:
			if row.entry_type == "Manual":
				row.manual_pending_qty = (row.manual_ordered_qty or 0) - (row.manual_completed_qty or 0)

	def enforce_closed_lock(self):
		if self.is_new():
			return

		db_status = frappe.db.get_value(self.doctype, self.name, "status")

		if db_status in ("Closed", "Cancelled"):
			privileged = {"System Manager", "Production Manager"}
			user_roles = set(frappe.get_roles(frappe.session.user))

			if not user_roles.intersection(privileged):
				frappe.throw(
					_("This plan is {0}. Only System Manager or Production Manager "
					  "can reopen it.").format(db_status)
				)


@frappe.whitelist()
def fetch_job_card_details(job_card_type, job_card_name):
	"""Fetch snapshot details from a Job Card for use in planning lines."""
	if job_card_type == "Computer Paper":
		doctype = "Job Card Computer Paper"
	elif job_card_type == "Label":
		doctype = "Job Card Label"
	elif job_card_type == "Carton":
		doctype = "Job Card Carton"
	else:
		return {}

	if job_card_type == "Carton":
		fields = ["name", "customer_name", "job_description", "quantity_ordered"]
		doc = frappe.db.get_value(doctype, job_card_name, fields, as_dict=True)
		if not doc:
			return {}

		return {
			"customer_name": doc.customer_name,
			"job_name": doc.job_description or doc.name,
			"ordered_qty": doc.quantity_ordered or 0,
			"completed_qty_snapshot": 0,
			"pending_qty_snapshot": 0,
		}

	fields = ["name", "customer", "specification_name", "quantity_ordered",
			  "qty_completed", "qty_pending"]
	doc = frappe.db.get_value(doctype, job_card_name, fields, as_dict=True)
	if not doc:
		return {}

	return {
		"customer_name": doc.customer,
		"job_name": doc.specification_name or doc.name,
		"ordered_qty": doc.quantity_ordered or 0,
		"completed_qty_snapshot": doc.qty_completed or 0,
		"pending_qty_snapshot": doc.qty_pending or 0,
	}
