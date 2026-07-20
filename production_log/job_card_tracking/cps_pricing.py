"""Approval, effective dating and current-rate derivation for CPS Price rows.

This is the app-code home of what would otherwise be a live Server Script. It
holds the Frappe-bound half only — every decision it makes comes from the pure
functions in :mod:`production_log.job_card_tracking.cps_rules`, so the rules
themselves are unit testable without a bench.

Design references: §5.1 schema, §5.2 eligibility, §5.3 approval, DN-2 (approval
gate approved), DN-3 (self-approval permitted, logged).
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_rules

APPROVER_ROLE = "Sales Master Manager"


def validate_pricing(doc):
	"""Enforce the CPS Price table rules and refresh the derived current rate.

	Called from both ``validate`` and ``before_update_after_submit`` on the
	specification: a price row added to an already-submitted spec is the normal
	case, and only the second of those two hooks fires for it.
	"""
	rows = doc.get("pricing") or []
	if not rows and not doc.get("current_rate"):
		return

	validate_no_duplicate_effective_dates(doc, rows)
	revoke_approval_on_edit(doc, rows)
	set_current_rate(doc, rows)


def validate_no_duplicate_effective_dates(doc, rows):
	"""Two live rows may not share an effective date (design §5.2).

	Otherwise eligibility resolution would pick arbitrarily between them.
	Rejected rows are excluded, so a rejected row can be superseded by a
	corrected one carrying the same date.
	"""
	duplicates = cps_rules.find_duplicate_valid_from(rows)
	if not duplicates:
		return

	frappe.throw(
		_("Two price rows share the effective date {0}. Supersede a price by adding a row with a later Effective From, or reject the row being replaced.").format(
			frappe.utils.formatdate(duplicates[0])
		),
		title=_("Duplicate Effective Date"),
	)


def revoke_approval_on_edit(doc, rows):
	"""Editing rate, UOM or effective date returns an Approved row to Draft.

	Without this, approval is a one-time rubber stamp on a mutable number
	(design §5.3).
	"""
	before = doc.get_doc_before_save()
	if not before:
		return

	previous_rows = {row.name: row for row in (before.get("pricing") or [])}
	for row in rows:
		previous = previous_rows.get(row.name)
		if not cps_rules.price_approval_reset_required(previous, row):
			continue

		row.approval_status = cps_rules.APPROVAL_DRAFT
		row.approved_by = None
		row.approved_on = None
		frappe.msgprint(
			_("Price row effective {0} was changed and needs approval again.").format(
				frappe.utils.formatdate(row.valid_from)
			),
			indicator="orange",
			alert=True,
		)


def set_current_rate(doc, rows):
	"""Derive the list-view rate from the row in effect today (design §5.2).

	Same eligibility rule as a Sales Order line, with ``today()`` in place of
	the order's ``transaction_date``. Filtering on Approved matters here too, or
	the list view advertises prices nobody has approved.
	"""
	eligible = cps_rules.resolve_eligible_price(rows, frappe.utils.today())
	doc.current_rate = cps_rules.round_rate(eligible.rate) if eligible else None
	doc.current_uom = eligible.uom if eligible else None


def get_eligible_price(cps, on_date):
	"""Return the eligible CPS Price row for a specification on a given date.

	``on_date`` is the Sales Order ``transaction_date``, never ``today()`` — see
	:func:`cps_rules.resolve_eligible_price`.
	"""
	rows = frappe.get_all(
		"CPS Price",
		filters={
			"parent": cps,
			"parenttype": "Customer Product Specification",
			"parentfield": "pricing",
			"approval_status": cps_rules.APPROVAL_APPROVED,
		},
		fields=["name", "valid_from", "rate", "uom", "approval_status"],
		order_by="valid_from asc",
	)
	return cps_rules.resolve_eligible_price(rows, on_date)


@frappe.whitelist()
def approve_cps_price(cps, row, action="approve", notes=None):
	"""Approve or reject a CPS Price row (design §5.3, §10.5).

	Only a Sales Master Manager may call this. Self-approval is permitted
	(DN-3) — blocking it would deadlock a two-person sales office — and is
	logged rather than refused.
	"""
	if action not in ("approve", "reject"):
		frappe.throw(_("Unknown action {0}. Use 'approve' or 'reject'.").format(action))

	if APPROVER_ROLE not in frappe.get_roles():
		frappe.throw(
			_("{0} role required to approve a price.").format(APPROVER_ROLE),
			frappe.PermissionError,
		)

	doc = frappe.get_doc("Customer Product Specification", cps)
	target = next((r for r in (doc.get("pricing") or []) if r.name == row), None)
	if not target:
		frappe.throw(_("Price row {0} not found on {1}.").format(row, cps))

	new_status = (
		cps_rules.APPROVAL_APPROVED if action == "approve" else cps_rules.APPROVAL_REJECTED
	)
	if target.approval_status == new_status:
		frappe.throw(_("Row is already {0}.").format(new_status))

	target.approval_status = new_status
	target.approved_by = frappe.session.user
	target.approved_on = frappe.utils.now()
	if notes:
		target.approval_notes = notes

	set_current_rate(doc, doc.get("pricing") or [])
	doc.save()

	_log_approval(doc, target, action)

	return {
		"cps": doc.name,
		"row": target.name,
		"approval_status": target.approval_status,
		"approved_by": target.approved_by,
		"approved_on": target.approved_on,
		"current_rate": doc.current_rate,
		"current_uom": doc.current_uom,
	}


def _log_approval(doc, row, action):
	"""Leave a visible audit trail, flagging self-approval explicitly (DN-3)."""
	self_approved = row.owner == frappe.session.user
	doc.add_comment(
		"Comment",
		_("Price row effective {0} at {1} was {2} by {3}.{4}").format(
			frappe.utils.formatdate(row.valid_from),
			row.rate,
			"approved" if action == "approve" else "rejected",
			frappe.session.user,
			_(" Self-approved by the row's author.") if self_approved else "",
		),
	)
