import frappe
from frappe import _
from frappe.model.document import Document

from production_log.ppc.stage_mapping import (
	STAGES,
	PRINTING,
	COLLATION_NUMBERING,
	PACKING,
	finished_sets_required,
	collated_sets_from_cartons,
	numbering_range_count,
	evaluate_completion_gates,
	_to_float,
	_to_int,
)


PLANNED_TOLERANCE = 1.10  # 10% over planned_qty allowed without reason
OVERRIDE_ROLES = {"Production Manager", "System Manager", "Fully Loaded"}
JC_FROZEN_STATUSES = ("Completed", "Closed", "Cancelled")


class PPCProductionActual(Document):
	def validate(self):
		if not self.items:
			frappe.throw(_("At least one production actual line is required."))
		self._validate_each_row()
		self._validate_jc_state()
		self._validate_tolerances()

	def on_submit(self):
		self.db_set("status", "Submitted", update_modified=False)
		self._apply_to_jobcards()
		self._advance_plan_items()

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)
		self._reverse_jobcards()

	# ----------------------------------------------------- validations

	def _validate_each_row(self):
		for row in self.items or []:
			if not row.stage or row.stage not in STAGES:
				frappe.throw(_("Row {0}: stage must be one of {1}.").format(row.idx, ", ".join(STAGES)))
			if (row.good_quantity or 0) < 0:
				frappe.throw(_("Row {0}: Good Qty cannot be negative.").format(row.idx))
			if (row.rejected_quantity or 0) < 0:
				frappe.throw(_("Row {0}: Rejected Qty cannot be negative.").format(row.idx))
			if (row.waste_quantity or 0) < 0:
				frappe.throw(_("Row {0}: Waste Qty cannot be negative.").format(row.idx))

			if (row.rejected_quantity or 0) > 0 and not (row.rejection_reason or "").strip():
				frappe.throw(_("Row {0}: Rejection Reason is required when Rejected Qty > 0.").format(row.idx))
			if (row.waste_quantity or 0) > 0 and not (row.waste_reason or "").strip():
				frappe.throw(_("Row {0}: Waste Reason is required when Waste Qty > 0.").format(row.idx))
			if (row.downtime_minutes or 0) > 0 and not row.downtime_reason:
				frappe.throw(_("Row {0}: Downtime Reason is required when Downtime > 0.").format(row.idx))
			if row.qc_status in ("Hold", "Rejected") and not (row.qc_comments or "").strip():
				frappe.throw(_("Row {0}: QC Comments are required when QC = {1}.").format(row.idx, row.qc_status))
			if row.stage == PRINTING and not (row.part_label or "").strip():
				frappe.throw(_("Row {0}: Part is required for Printing by Part actuals.").format(row.idx))

			if row.stage == COLLATION_NUMBERING:
				self._validate_numbering_range(row)

	def _validate_numbering_range(self, row):
		if row.number_from is None and row.number_to is None:
			return
		if row.number_from is None or row.number_to is None:
			frappe.throw(_("Row {0}: both Number From and Number To must be set.").format(row.idx))
		count = numbering_range_count(row.number_from, row.number_to)
		jc = frappe.db.get_value(
			row.source_doctype,
			row.source_job_card,
			["packing", "numbering_required"],
			as_dict=True,
		)
		if not jc or not jc.numbering_required:
			return
		expected = collated_sets_from_cartons(row.numbered_cartons or 0, jc.packing or 0)
		if expected and abs(count - expected) > 0.5:
			user_roles = set(frappe.get_roles(frappe.session.user))
			if not (user_roles & OVERRIDE_ROLES):
				frappe.throw(
					_("Row {0}: number range count {1} does not match {2} cartons × {3} packing = {4} sets. Manager override required.")
					.format(row.idx, count, row.numbered_cartons, jc.packing, expected)
				)

	def _validate_jc_state(self):
		for row in self.items or []:
			if not (row.source_doctype and row.source_job_card):
				frappe.throw(_("Row {0}: Job Card is required.").format(row.idx))
			jc = frappe.db.get_value(
				row.source_doctype,
				row.source_job_card,
				["job_status"],
				as_dict=True,
			)
			if not jc:
				frappe.throw(_("Row {0}: Job Card {1} not found.").format(row.idx, row.source_job_card))
			if jc.job_status in JC_FROZEN_STATUSES:
				frappe.throw(
					_("Row {0}: Job Card {1} is {2} and cannot accept new actuals. Reopen it first.")
					.format(row.idx, row.source_job_card, jc.job_status)
				)

	def _validate_tolerances(self):
		"""10% over planned_qty (warn / require manager); strict block above remaining job balance."""
		user_roles = set(frappe.get_roles(frappe.session.user))
		can_override = bool(user_roles & OVERRIDE_ROLES)

		for row in self.items or []:
			good = _to_float(row.good_quantity)

			# Daily-plan tolerance (only when this row links to a plan item)
			if row.daily_plan_item:
				planned = frappe.db.get_value("PPC Daily Plan Item", row.daily_plan_item, "planned_qty")
				planned = _to_float(planned)
				if planned > 0 and good > planned * PLANNED_TOLERANCE:
					if not can_override:
						frappe.throw(
							_("Row {0}: actual {1} exceeds planned {2} by more than {3:.0%}. Manager override required.")
							.format(row.idx, good, planned, PLANNED_TOLERANCE - 1)
						)

			# Hard cap vs remaining job balance (strict, irrespective of plan tolerance)
			balance = self._jc_remaining_balance(row)
			if balance is not None and good > balance:
				if not can_override:
					frappe.throw(
						_("Row {0}: actual {1} exceeds remaining job balance {2}. Manager override required.")
						.format(row.idx, good, balance)
					)

	def _jc_remaining_balance(self, row):
		"""Remaining balance in the row's good_uom for the JC at this stage."""
		jc = frappe.db.get_value(
			row.source_doctype,
			row.source_job_card,
			["quantity_ordered", "packing", "packed_cartons", "collated_quantity", "number_of_parts"],
			as_dict=True,
		)
		if not jc:
			return None
		uom = (row.good_uom or "Cartons").lower()
		ordered = _to_float(jc.quantity_ordered)
		packing = _to_float(jc.packing)

		if row.stage == PACKING:
			balance_cartons = max(0.0, ordered - _to_float(jc.packed_cartons))
			if uom == "cartons":
				return balance_cartons
			if uom == "sets":
				return balance_cartons * packing
			return balance_cartons
		# Collation+Numbering and Printing reason in sets
		required_sets = ordered * packing
		balance_sets = max(0.0, required_sets - _to_float(jc.collated_quantity))
		if uom == "cartons" and packing > 0:
			return balance_sets / packing
		if uom == "sheets":
			return balance_sets * _to_int(jc.number_of_parts or 1)
		return balance_sets

	# ------------------------------------------------------ side effects

	def _apply_to_jobcards(self):
		"""Write back per-stage quantities and re-evaluate completion gates."""
		touched = set()
		for row in self.items or []:
			if row.source_doctype != "Job Card Computer Paper":
				continue
			self._write_stage_to_jc(row)
			touched.add(row.source_job_card)
		for jc_name in touched:
			self._refresh_jc_status(jc_name)

	def _write_stage_to_jc(self, row):
		jc_doc = frappe.get_doc(row.source_doctype, row.source_job_card)
		good = _to_float(row.good_quantity)
		waste = _to_float(row.waste_quantity)
		rejected = _to_float(row.rejected_quantity)

		# Common: accumulate good_quantity / waste / rejected
		jc_doc.good_quantity = _to_float(jc_doc.good_quantity) + good
		jc_doc.waste_quantity = _to_float(jc_doc.waste_quantity) + waste
		try:
			jc_doc.rejected_quantity = _to_float(jc_doc.rejected_quantity) + rejected
		except AttributeError:
			pass  # custom field may not yet be present in older docs

		if row.stage == PRINTING:
			jc_doc.printed_quantity = _to_float(jc_doc.printed_quantity) + good
		elif row.stage == COLLATION_NUMBERING:
			# Collation actuals come in as cartons → convert to sets for collated_quantity
			packing = _to_float(jc_doc.packing)
			added_sets = good * packing if (row.good_uom or "Cartons").lower() == "cartons" else good
			jc_doc.collated_quantity = _to_float(jc_doc.collated_quantity) + added_sets
			if jc_doc.numbering_required and (row.numbered_cartons or 0):
				jc_doc.numbered_quantity = _to_float(jc_doc.numbered_quantity) + (
					_to_float(row.numbered_cartons) * packing
				)
		elif row.stage == PACKING:
			jc_doc.packed_cartons = _to_float(jc_doc.packed_cartons) + good
			try:
				jc_doc.rejected_cartons = _to_int(jc_doc.rejected_cartons) + (
					_to_int(rejected) if (row.good_uom or "Cartons").lower() == "cartons" else 0
				)
			except AttributeError:
				pass
			try:
				jc_doc.loose_balance_sets = _to_float(row.loose_balance_sets)
			except AttributeError:
				pass

		if jc_doc.job_status in ("Open", "Planned"):
			jc_doc.job_status = "In Production"

		jc_doc.production_notes = ((jc_doc.production_notes or "") + (
			f"\n[{frappe.utils.now()}] {row.stage} via {self.name}: good {good} {row.good_uom or ''}; "
			f"waste {waste}; rejected {rejected}; op {row.operator or ''}"
		)).strip()
		jc_doc.flags.ignore_permissions = True
		jc_doc.flags.ignore_validate_update_after_submit = True
		jc_doc.save()

	def _refresh_jc_status(self, jc_name):
		"""Re-evaluate completion gates and set Completed / Packing Pending."""
		jc = frappe.db.get_value(
			"Job Card Computer Paper",
			jc_name,
			[
				"quantity_ordered",
				"packing",
				"number_of_parts",
				"packed_cartons",
				"collated_quantity",
				"numbered_quantity",
				"loose_balance_sets",
				"numbering_required",
				"customer_product_spec",
				"job_status",
			],
			as_dict=True,
		)
		if not jc:
			return
		new_status, reason = evaluate_completion_gates(jc, jc_name)
		if not new_status or new_status == jc.job_status:
			return
		updates = {"job_status": new_status}
		if new_status == "Completed":
			updates["production_completed_on"] = frappe.utils.now()
		if new_status == "Packing Pending":
			updates["packing_pending"] = 1
		frappe.db.set_value("Job Card Computer Paper", jc_name, updates)
		try:
			frappe.get_doc("Job Card Computer Paper", jc_name).add_comment(
				"Comment",
				_("PPC: status auto-updated to {0} ({1}).").format(new_status, reason),
			)
		except Exception:
			pass

	def _advance_plan_items(self):
		for row in self.items or []:
			if not row.daily_plan_item:
				continue
			item = frappe.db.get_value(
				"PPC Daily Plan Item",
				row.daily_plan_item,
				["planned_qty", "remaining_balance", "line_status"],
				as_dict=True,
			)
			if not item:
				continue
			balance = _to_float(
				item.remaining_balance if item.remaining_balance is not None else item.planned_qty
			)
			balance = max(0.0, balance - _to_float(row.good_quantity))
			if balance <= 0:
				new_status = "Completed"
			elif balance < _to_float(item.planned_qty):
				new_status = "Partially Completed"
			else:
				new_status = "In Progress"
			frappe.db.set_value(
				"PPC Daily Plan Item",
				row.daily_plan_item,
				{"remaining_balance": balance, "line_status": new_status},
			)

	def _reverse_jobcards(self):
		"""On cancel, subtract this actual's contribution from the JC."""
		for row in self.items or []:
			if row.source_doctype != "Job Card Computer Paper":
				continue
			try:
				jc_doc = frappe.get_doc(row.source_doctype, row.source_job_card)
			except Exception:
				continue
			good = _to_float(row.good_quantity)
			waste = _to_float(row.waste_quantity)
			rejected = _to_float(row.rejected_quantity)
			jc_doc.good_quantity = max(0.0, _to_float(jc_doc.good_quantity) - good)
			jc_doc.waste_quantity = max(0.0, _to_float(jc_doc.waste_quantity) - waste)
			try:
				jc_doc.rejected_quantity = max(0.0, _to_float(jc_doc.rejected_quantity) - rejected)
			except AttributeError:
				pass
			if row.stage == PRINTING:
				jc_doc.printed_quantity = max(0.0, _to_float(jc_doc.printed_quantity) - good)
			elif row.stage == COLLATION_NUMBERING:
				packing = _to_float(jc_doc.packing)
				removed = good * packing if (row.good_uom or "Cartons").lower() == "cartons" else good
				jc_doc.collated_quantity = max(0.0, _to_float(jc_doc.collated_quantity) - removed)
			elif row.stage == PACKING:
				jc_doc.packed_cartons = max(0.0, _to_float(jc_doc.packed_cartons) - good)
			jc_doc.flags.ignore_permissions = True
			jc_doc.flags.ignore_validate_update_after_submit = True
			jc_doc.save()
