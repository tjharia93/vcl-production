import frappe
from frappe.model.document import Document


class JobCardProductionEntry(Document):
	def validate(self):
		self.validate_actual_lines()
		self.calculate_totals()
		self.calculate_running_balances()

	def validate_actual_lines(self):
		for row in self.actual_lines:
			if not row.job_card:
				frappe.throw(f"Row {row.idx} in Actual Lines: Job Card is required.")

			jc = frappe.get_doc("Job Card Computer Paper", row.job_card)
			if jc.docstatus != 1:
				frappe.throw(
					f"Row {row.idx}: Job Card {row.job_card} must be submitted before recording production."
				)

			# Populate read-only fields from Job Card
			row.order_qty = jc.quantity_ordered or 0
			row.produced_qty = jc.total_actual_good_qty or 0
			row.balance_qty = jc.balance_qty or 0

		for row in self.planning_lines:
			if not row.job_card:
				frappe.throw(f"Row {row.idx} in Planning Lines: Job Card is required.")

			jc = frappe.get_doc("Job Card Computer Paper", row.job_card)
			row.order_qty = jc.quantity_ordered or 0
			row.produced_qty = jc.total_actual_good_qty or 0
			row.balance_qty = jc.balance_qty or 0

	def calculate_totals(self):
		self.total_good_qty = sum(row.good_qty or 0 for row in self.actual_lines)
		self.total_waste_qty = sum(row.waste_qty or 0 for row in self.actual_lines)

	def calculate_running_balances(self):
		for row in self.actual_lines:
			row.running_balance = (row.balance_qty or 0) - (row.good_qty or 0)

	def on_submit(self):
		self.update_linked_job_cards()

	def on_cancel(self):
		self.update_linked_job_cards()

	def update_linked_job_cards(self):
		job_cards = set()
		for row in self.actual_lines:
			if row.job_card:
				job_cards.add(row.job_card)
		for jc_name in job_cards:
			update_job_card_totals(jc_name)


def update_job_card_totals(job_card_name):
	"""Aggregate totals from ALL submitted Job Card Production Entries for a Job Card."""
	totals = frappe.db.sql("""
		SELECT
			COALESCE(SUM(pal.good_qty), 0) as total_good,
			COALESCE(SUM(pal.waste_qty), 0) as total_waste
		FROM `tabProduction Actual Line` pal
		JOIN `tabJob Card Production Entry` pe ON pe.name = pal.parent
		WHERE pal.job_card = %s AND pe.docstatus = 1
	""", job_card_name, as_dict=True)[0]

	order_qty = frappe.db.get_value(
		"Job Card Computer Paper", job_card_name, "quantity_ordered"
	) or 0
	produced = totals.total_good
	balance = max(0, order_qty - produced)

	if produced == 0:
		status = "Not Started"
	elif produced >= order_qty:
		status = "Completed"
	else:
		status = "In Production"

	frappe.db.set_value("Job Card Computer Paper", job_card_name, {
		"total_actual_good_qty": produced,
		"total_waste_qty": totals.total_waste,
		"balance_qty": balance,
		"production_status": status,
	}, update_modified=False)
