import frappe
from frappe import _
from frappe.model.document import Document

CP_PRODUCTION_STAGE_STATUSES = {
	"Not Started",
	"Ready",
	"In Progress",
	"Done",
	"Blocked",
	"Skipped",
}


class JobCardComputerPaper(Document):
	def validate(self):
		self.validate_customer_product_spec()
		self.validate_spec_fields()
		self.validate_numbering()
		self.validate_plate()
		self.validate_quantity()
		self.validate_production_stage_assets()
		self.set_sales_rep_info()
		self.set_status()

	def after_insert(self):
		self.reseed_production_stages(save=True)

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

	def get_production_stage_route(self):
		route = ["Design", "Pending Films", "Printing", "Collation"]
		if self.numbering_required:
			route.append("Numbering")
		route.append("Pack")
		return route

	def reseed_production_stages(self, save=False):
		"""Rebuild Computer Paper route rows without duplicating stages.

		Existing matching stage rows keep their status, machine, timing, quantity,
		and notes. Rows outside the current route are dropped from the rebuilt
		table, for example Numbering when numbering_required is cleared.
		"""
		existing_by_stage = {}
		for row in self.get("production_stages") or []:
			if row.stage and row.stage not in existing_by_stage:
				existing_by_stage[row.stage] = row

		self.set("production_stages", [])
		for sequence, stage in enumerate(self.get_production_stage_route(), start=1):
			existing = existing_by_stage.get(stage)
			row = self.append("production_stages", {})
			row.stage = stage
			row.stage_status = (existing.stage_status if existing else None) or "Not Started"
			row.machine_asset = existing.machine_asset if existing else None
			row.started_on = existing.started_on if existing else None
			row.completed_on = existing.completed_on if existing else None
			row.quantity = existing.quantity if existing else None
			row.notes = existing.notes if existing else None
			row.sequence = sequence

		if save:
			self.save()

		return self.get("production_stages")

	def validate_production_stage_assets(self):
		for row in self.get("production_stages") or []:
			if row.stage_status and row.stage_status not in CP_PRODUCTION_STAGE_STATUSES:
				frappe.throw(_("Invalid stage status: {0}").format(row.stage_status))
			if not row.machine_asset:
				continue

			asset_category = frappe.db.get_value("Asset", row.machine_asset, "asset_category")
			if asset_category != "Plant & Machinery":
				frappe.throw(
					_("Row {0}: Machine Asset must be in Asset Category 'Plant & Machinery'.").format(
						row.idx
					),
					title=_("Invalid Machine Asset"),
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


@frappe.whitelist()
def get_plant_machinery_asset_query(doctype, txt, searchfield, start, page_len, filters):
	return frappe.db.sql(
		"""
		SELECT name, asset_name, asset_category
		FROM `tabAsset`
		WHERE asset_category = 'Plant & Machinery'
		AND (name LIKE %(txt)s OR asset_name LIKE %(txt)s)
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"txt": "%%" + txt + "%%",
			"start": int(start),
			"page_len": int(page_len),
		},
	)


@frappe.whitelist()
def reseed_production_stages(name):
	doc = frappe.get_doc("Job Card Computer Paper", name)
	doc.check_permission("write")
	doc.reseed_production_stages(save=True)
	return doc.get("production_stages")
