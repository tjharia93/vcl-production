import frappe
from frappe import _
from frappe.model.document import Document


PLANNED_STATUSES_BLOCKED = ("Completed", "Closed", "Cancelled")
OVERRIDE_ROLES = {"Production Manager", "System Manager", "Fully Loaded"}


class PPCDailyPlan(Document):
	def validate(self):
		self._block_invalid_jobcards()
		self._check_plate_readiness()
		self._check_planned_above_balance()
		self._compute_remaining_balance()

	def on_submit(self):
		if not self.items:
			frappe.throw(_("Cannot release a Daily Plan with no items."))
		self.db_set("status", "Released", update_modified=False)
		self.db_set("released_by", frappe.session.user, update_modified=False)
		self.db_set("released_on", frappe.utils.now(), update_modified=False)
		self._mark_jobcards_planned()

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)

	# ------------------------------------------------------ validations

	def _block_invalid_jobcards(self):
		for row in self.items or []:
			if not (row.source_doctype and row.source_job_card):
				continue
			jc = frappe.db.get_value(
				row.source_doctype,
				row.source_job_card,
				["job_status", "plate_status", "plates_confirmed"],
				as_dict=True,
			)
			if not jc:
				frappe.throw(_("Row {0}: Job Card {1} not found.").format(row.idx, row.source_job_card))
			if jc.job_status in PLANNED_STATUSES_BLOCKED:
				frappe.throw(
					_("Row {0}: Job Card {1} is {2} and cannot be planned.")
					.format(row.idx, row.source_job_card, jc.job_status)
				)
			if jc.job_status == "On Hold":
				frappe.throw(
					_("Row {0}: Job Card {1} is On Hold. Clear the hold before planning.")
					.format(row.idx, row.source_job_card)
				)

	def _check_plate_readiness(self):
		"""Hard-block Printing release if plate_status=New and plates_confirmed=0."""
		for row in self.items or []:
			if row.stage != "Printing by Part":
				continue
			if not (row.source_doctype and row.source_job_card):
				continue
			jc = frappe.db.get_value(
				row.source_doctype,
				row.source_job_card,
				["plate_status", "plates_confirmed"],
				as_dict=True,
			)
			if not jc:
				continue
			if jc.plate_status == "New" and not jc.plates_confirmed:
				frappe.throw(
					_("Row {0}: Job Card {1} has plate_status=New but plates_confirmed=0. Plates must be confirmed before Printing can be planned.")
					.format(row.idx, row.source_job_card)
				)
			if jc.plate_status == "Old" and not jc.plates_confirmed:
				frappe.msgprint(
					_("Row {0}: Job Card {1} has Old plates not yet confirmed. Planning allowed but verify before printing.")
					.format(row.idx, row.source_job_card),
					indicator="orange",
					alert=True,
				)

	def _check_planned_above_balance(self):
		"""If planned_qty > remaining_balance, require manager override or remarks."""
		user_roles = set(frappe.get_roles(frappe.session.user))
		can_override = bool(user_roles & OVERRIDE_ROLES)
		for row in self.items or []:
			if row.remaining_balance is None:
				continue
			planned = float(row.planned_qty or 0)
			balance = float(row.remaining_balance or 0)
			if planned > balance:
				if not can_override and not (row.remarks or "").strip():
					frappe.throw(
						_("Row {0}: planned qty {1} exceeds remaining balance {2}. Add remarks or get manager override.")
						.format(row.idx, planned, balance)
					)

	def _compute_remaining_balance(self):
		"""Compute remaining_balance from job-level state if not provided."""
		for row in self.items or []:
			if row.remaining_balance is not None and row.remaining_balance != 0:
				continue
			if not (row.source_doctype and row.source_job_card):
				continue
			row.remaining_balance = self._jc_remaining_balance(row)

	def _jc_remaining_balance(self, row):
		"""Return remaining balance in row.planned_uom for the JC at this stage."""
		from production_log.ppc.stage_mapping import (
			finished_sets_required,
			_to_float,
		)

		jc = frappe.db.get_value(
			row.source_doctype,
			row.source_job_card,
			["quantity_ordered", "packing", "packed_cartons", "collated_quantity"],
			as_dict=True,
		)
		if not jc:
			return 0
		ordered = _to_float(jc.quantity_ordered)
		packed = _to_float(jc.packed_cartons)

		uom = (row.planned_uom or "Cartons").lower()
		if row.stage == "Packing":
			balance_cartons = max(0.0, ordered - packed)
			if uom == "cartons":
				return balance_cartons
			if uom == "sets":
				return balance_cartons * _to_float(jc.packing)
			return balance_cartons
		# Collation + Numbering / Printing — work in sets
		req_sets = finished_sets_required(jc)
		done_sets = _to_float(jc.collated_quantity)
		balance_sets = max(0.0, req_sets - done_sets)
		if uom == "cartons" and _to_float(jc.packing) > 0:
			return balance_sets / _to_float(jc.packing)
		return balance_sets

	# --------------------------------------------------------- side effects

	def _mark_jobcards_planned(self):
		for row in self.items or []:
			if row.source_doctype != "Job Card Computer Paper":
				continue
			current = frappe.db.get_value(row.source_doctype, row.source_job_card, "job_status")
			if current == "Open":
				frappe.db.set_value(row.source_doctype, row.source_job_card, "job_status", "Planned")
				try:
					frappe.get_doc(row.source_doctype, row.source_job_card).add_comment(
						"Comment",
						_("Added to PPC Daily Plan {0} (workstation: {1}, stage: {2}, planned: {3} {4}).")
						.format(self.name, self.workstation, row.stage, row.planned_qty, row.planned_uom or ""),
					)
				except Exception:
					pass
