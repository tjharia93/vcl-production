"""PPC Computer Paper — whitelisted backend methods.

Per ppc_may26_v1: the board, reports, hold/cancel/close/reopen workflows,
manual carry-forward, and dashboard data all flow through here.
"""

import frappe
from frappe import _

from production_log.ppc.stage_mapping import (
	STAGES,
	POOL_STATUSES,
	finished_sets_required,
	customer_completion,
	printing_readiness,
	get_part_labels,
	_to_float,
	_to_int,
)


CLOSE_ROLES = {"Production Manager", "Production Supervisor", "System Manager", "Fully Loaded"}
REOPEN_ROLES = {"Production Manager", "System Manager", "Fully Loaded"}
HOLD_ROLES = {"Production Manager", "Production Supervisor", "System Manager", "Fully Loaded"}
CANCEL_ROLES = {"Production Manager", "System Manager", "Fully Loaded"}
PRIORITY_REASON_REQUIRED = {"Urgent", "Critical"}


def _has_role(roles):
	user_roles = set(frappe.get_roles(frappe.session.user))
	return bool(user_roles & roles)


def _require_role(roles, action):
	if not _has_role(roles):
		frappe.throw(
			_("You do not have permission to {0}. Required role: {1}.")
			.format(action, " / ".join(sorted(roles))),
			frappe.PermissionError,
		)


def _get_jc(jc_name):
	doc = frappe.get_doc("Job Card Computer Paper", jc_name)
	return doc


# ---------------------------------------------------------------------------
# Job Pool / Daily Plan helpers
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_open_job_pool(filters=None):
	"""Return open Computer Paper jobs available for planning."""
	rows = frappe.db.sql(
		"""
		SELECT
			jc.name,
			jc.customer,
			jc.specification_name,
			jc.customer_product_spec,
			jc.due_date,
			jc.lpo_number,
			jc.quantity_ordered,
			jc.packing,
			jc.number_of_parts,
			jc.numbering_required,
			jc.printed_quantity,
			jc.collated_quantity,
			jc.numbered_quantity,
			jc.packed_cartons,
			jc.good_quantity,
			jc.waste_quantity,
			jc.job_status,
			jc.priority,
			jc.plate_status,
			jc.plates_confirmed
		FROM `tabJob Card Computer Paper` jc
		WHERE jc.docstatus < 2
		  AND jc.job_status IN %(s)s
		ORDER BY
			CASE jc.priority WHEN 'Critical' THEN 1 WHEN 'Urgent' THEN 2 WHEN 'High' THEN 3 ELSE 4 END,
			CASE jc.job_status WHEN 'In Production' THEN 1 WHEN 'Packing Pending' THEN 2 WHEN 'Planned' THEN 3 WHEN 'On Hold' THEN 5 ELSE 4 END,
			jc.due_date ASC,
			jc.creation DESC
		""",
		{"s": POOL_STATUSES},
		as_dict=True,
	)
	for r in rows:
		r["finished_sets_required"] = finished_sets_required(r)
		r["customer_completion_pct"] = round(customer_completion(r) * 100, 1)
	return rows


@frappe.whitelist()
def get_daily_plan(planning_date, shift=None, workstation=None):
	filters = {"planning_date": planning_date, "department": "Computer Paper"}
	if shift:
		filters["shift"] = shift
	if workstation:
		filters["workstation"] = workstation
	plans = frappe.get_all(
		"PPC Daily Plan",
		filters=filters,
		fields=["name", "planning_date", "shift", "workstation", "status", "prepared_by"],
		order_by="workstation asc, shift asc",
	)
	for p in plans:
		p["items"] = frappe.get_all(
			"PPC Daily Plan Item",
			filters={"parent": p.name, "parenttype": "PPC Daily Plan"},
			fields=[
				"name", "sequence", "source_job_card", "customer", "specification_name",
				"stage", "workstation", "planned_qty", "planned_uom",
				"remaining_balance", "priority", "due_date", "line_status",
				"carry_forward_from", "carry_forward_pending",
			],
			order_by="sequence asc, idx asc",
		)
	return plans


# ---------------------------------------------------------------------------
# Carry forward (manual)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def mark_carry_forward(plan_item_name, target_date, target_workstation=None, target_shift=None):
	"""Mark a Daily Plan Item as carry-forward.

	Creates a new Draft 'PPC Daily Plan' for target_date+workstation if one
	doesn't already exist, then adds a Carry Forward Pending line with the
	remaining balance.
	"""
	src = frappe.get_doc("PPC Daily Plan Item", plan_item_name)
	parent = frappe.get_doc("PPC Daily Plan", src.parent)
	target_ws = target_workstation or parent.workstation
	target_sh = target_shift or parent.shift

	plan_name = frappe.db.get_value(
		"PPC Daily Plan",
		{
			"planning_date": target_date,
			"workstation": target_ws,
			"shift": target_sh,
			"department": "Computer Paper",
			"docstatus": 0,
		},
		"name",
	)
	if not plan_name:
		new_plan = frappe.get_doc({
			"doctype": "PPC Daily Plan",
			"planning_date": target_date,
			"shift": target_sh,
			"workstation": target_ws,
			"department": "Computer Paper",
			"prepared_by": frappe.session.user,
		})
		new_plan.insert(ignore_permissions=False)
		plan_name = new_plan.name

	plan_doc = frappe.get_doc("PPC Daily Plan", plan_name)
	balance = _to_float(src.remaining_balance) or _to_float(src.planned_qty)
	plan_doc.append("items", {
		"sequence": (plan_doc.items[-1].sequence + 1) if plan_doc.items else 1,
		"source_doctype": src.source_doctype,
		"source_job_card": src.source_job_card,
		"stage": src.stage,
		"workstation": target_ws,
		"planned_qty": balance,
		"planned_uom": src.planned_uom,
		"remaining_balance": balance,
		"priority": src.priority,
		"due_date": src.due_date,
		"line_status": "Carry Forward Pending",
		"carry_forward_from": src.name,
		"carry_forward_pending": 1,
	})
	plan_doc.save()
	frappe.db.set_value("PPC Daily Plan Item", src.name, {
		"line_status": "Carry Forward",
		"carry_forward_to": plan_doc.items[-1].name,
	})
	return {"plan": plan_name, "item": plan_doc.items[-1].name}


@frappe.whitelist()
def confirm_carry_forward(plan_item_name):
	"""PPC confirms a Carry Forward Pending line — flips it to Planned."""
	frappe.db.set_value("PPC Daily Plan Item", plan_item_name, {
		"line_status": "Planned",
		"carry_forward_pending": 0,
	})
	return {"ok": True}


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

@frappe.whitelist()
def set_priority(jc_name, priority, reason=None):
	if priority not in ("Normal", "High", "Urgent", "Critical"):
		frappe.throw(_("Invalid priority {0}.").format(priority))
	if priority in PRIORITY_REASON_REQUIRED and not (reason or "").strip():
		frappe.throw(_("Priority Reason is required for {0}.").format(priority))
	jc = _get_jc(jc_name)
	jc.priority = priority
	jc.priority_reason = reason
	jc.priority_changed_by = frappe.session.user
	jc.priority_changed_on = frappe.utils.now()
	jc.flags.ignore_permissions = True
	jc.save()
	jc.add_comment("Comment", _("Priority set to {0} by {1}. Reason: {2}").format(
		priority, frappe.session.user, reason or "-"
	))
	return {"ok": True}


# ---------------------------------------------------------------------------
# Hold
# ---------------------------------------------------------------------------

@frappe.whitelist()
def set_on_hold(jc_name, hold_reason, hold_remarks):
	_require_role(HOLD_ROLES, "place a job on hold")
	if not hold_reason:
		frappe.throw(_("Hold reason is required."))
	if not (hold_remarks or "").strip():
		frappe.throw(_("Hold remarks are required."))
	jc = _get_jc(jc_name)
	if jc.job_status == "On Hold":
		frappe.throw(_("Job is already On Hold."))
	if jc.job_status in ("Closed", "Cancelled"):
		frappe.throw(_("Cannot place {0} job on hold.").format(jc.job_status))
	jc.hold_previous_status = jc.job_status
	jc.hold_reason = hold_reason
	jc.hold_remarks = hold_remarks
	jc.hold_by = frappe.session.user
	jc.hold_on = frappe.utils.now()
	jc.job_status = "On Hold"
	jc.flags.ignore_permissions = True
	jc.save()
	jc.add_comment("Comment", _("On Hold ({0}): {1}").format(hold_reason, hold_remarks))
	return {"ok": True}


@frappe.whitelist()
def clear_hold(jc_name):
	_require_role(HOLD_ROLES, "clear a hold")
	jc = _get_jc(jc_name)
	if jc.job_status != "On Hold":
		frappe.throw(_("Job is not On Hold."))
	# Per spec: actuals before hold → In Production; planned before → Planned; never planned → Open
	prior = (jc.hold_previous_status or "").strip()
	has_actuals = frappe.db.exists("PPC Production Actual Item", {
		"source_job_card": jc.name,
		"docstatus": 1,
	})
	if has_actuals or prior == "In Production":
		new_status = "In Production"
	elif prior == "Planned":
		new_status = "Planned"
	else:
		new_status = "Open"
	jc.job_status = new_status
	jc.hold_cleared_by = frappe.session.user
	jc.hold_cleared_on = frappe.utils.now()
	jc.flags.ignore_permissions = True
	jc.save()
	jc.add_comment("Comment", _("Hold cleared → {0}").format(new_status))
	return {"ok": True, "new_status": new_status}


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

@frappe.whitelist()
def cancel_job(jc_name, cancel_reason, cancel_remarks):
	_require_role(CANCEL_ROLES, "cancel a job")
	if not (cancel_reason or "").strip():
		frappe.throw(_("Cancel reason is required."))
	jc = _get_jc(jc_name)
	if jc.job_status in ("Cancelled", "Closed"):
		frappe.throw(_("Job is already {0}.").format(jc.job_status))
	jc.job_status = "Cancelled"
	jc.cancel_reason = cancel_reason
	jc.cancel_remarks = cancel_remarks
	jc.cancelled_by = frappe.session.user
	jc.cancelled_on = frappe.utils.now()
	jc.flags.ignore_permissions = True
	jc.save()
	jc.add_comment("Comment", _("Cancelled: {0} — {1}").format(cancel_reason, cancel_remarks or ""))
	return {"ok": True}


# ---------------------------------------------------------------------------
# Close / Reopen
# ---------------------------------------------------------------------------

@frappe.whitelist()
def close_job(jc_name, closing_remarks):
	_require_role(CLOSE_ROLES, "close a job")
	if not (closing_remarks or "").strip():
		frappe.throw(_("Closing remarks are mandatory."))
	jc = _get_jc(jc_name)
	if jc.job_status == "Closed":
		frappe.throw(_("Job is already Closed."))
	if jc.job_status in ("Cancelled",):
		frappe.throw(_("Cannot close a Cancelled job."))
	jc.job_status = "Closed"
	jc.closed_by = frappe.session.user
	jc.closed_on = frappe.utils.now()
	jc.closing_remarks = closing_remarks
	jc.flags.ignore_permissions = True
	jc.save()
	jc.add_comment("Comment", _("Closed by {0}: {1}").format(frappe.session.user, closing_remarks))
	return {"ok": True}


@frappe.whitelist()
def reopen_job(jc_name, reopen_reason):
	_require_role(REOPEN_ROLES, "reopen a job")
	if not (reopen_reason or "").strip():
		frappe.throw(_("Reopen reason is required."))
	jc = _get_jc(jc_name)
	if jc.job_status not in ("Completed", "Closed"):
		frappe.throw(_("Only Completed or Closed jobs can be reopened.").format(jc.job_status))
	jc.job_status = "In Production"
	jc.reopened_by = frappe.session.user
	jc.reopened_on = frappe.utils.now()
	jc.reopen_reason = reopen_reason
	jc.flags.ignore_permissions = True
	jc.save()
	jc.add_comment("Comment", _("Reopened by {0}: {1}").format(frappe.session.user, reopen_reason))
	return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_dashboard(date=None):
	date = date or frappe.utils.today()
	def _count(filters):
		return frappe.db.count("Job Card Computer Paper", filters=filters)

	open_jobs = _count({"docstatus": ["!=", 2], "job_status": ["in", POOL_STATUSES]})
	on_hold = _count({"docstatus": ["!=", 2], "job_status": "On Hold"})
	packing_pending = _count({"docstatus": ["!=", 2], "job_status": "Packing Pending"})
	completed_awaiting_closure = _count({
		"docstatus": ["!=", 2], "job_status": "Completed",
	})
	planned_today = frappe.db.count(
		"PPC Daily Plan",
		filters={"planning_date": date, "department": "Computer Paper", "docstatus": 1},
	)

	completed_today = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabJob Card Computer Paper`
		WHERE job_status = 'Completed'
		  AND DATE(production_completed_on) = %(d)s
		""",
		{"d": date},
	)[0][0]

	overdue = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabJob Card Computer Paper`
		WHERE due_date < %(d)s
		  AND job_status IN %(s)s
		""",
		{"d": date, "s": POOL_STATUSES},
	)[0][0]

	totals = frappe.db.sql(
		"""
		SELECT
			SUM(IFNULL(pi.good_quantity, 0))    AS good,
			SUM(IFNULL(pi.waste_quantity, 0))   AS waste,
			SUM(IFNULL(pi.rejected_quantity,0)) AS rejected,
			SUM(IFNULL(pi.downtime_minutes,0))  AS downtime
		FROM `tabPPC Production Actual Item` pi
		INNER JOIN `tabPPC Production Actual` pa
			ON pi.parent = pa.name AND pa.docstatus = 1
		WHERE pa.posting_date = %(d)s
		""",
		{"d": date},
		as_dict=True,
	)
	totals = totals[0] if totals else {}

	return {
		"date": date,
		"open_jobs": open_jobs,
		"on_hold": on_hold,
		"packing_pending": packing_pending,
		"completed_awaiting_closure": completed_awaiting_closure,
		"planned_today": planned_today,
		"completed_today": completed_today,
		"overdue": overdue,
		"good_today": float(totals.get("good") or 0),
		"waste_today": float(totals.get("waste") or 0),
		"rejected_today": float(totals.get("rejected") or 0),
		"downtime_today": float(totals.get("downtime") or 0),
	}


# ---------------------------------------------------------------------------
# Job-card detail for board cards
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_job_progress(jc_name):
	jc = frappe.db.get_value(
		"Job Card Computer Paper",
		jc_name,
		[
			"name", "customer", "specification_name", "customer_product_spec",
			"quantity_ordered", "packing", "number_of_parts",
			"printed_quantity", "collated_quantity", "numbered_quantity",
			"packed_cartons", "good_quantity", "waste_quantity",
			"loose_balance_sets", "rejected_cartons",
			"due_date", "priority", "job_status", "numbering_required",
		],
		as_dict=True,
	)
	if not jc:
		return None
	ready, required, pct = printing_readiness(jc, jc_name)
	jc["printing_ready_sets"] = ready
	jc["finished_sets_required"] = required
	jc["printing_readiness_pct"] = round(pct * 100, 1)
	jc["customer_completion_pct"] = round(customer_completion(jc) * 100, 1)
	jc["part_labels"] = get_part_labels(jc)
	return jc
