"""One submitted Sales Order per CPS pending spec/price approval (10-Nov-2026).

The claim is server owned and survives cancellation, price-row replacement and
revision. Draft saves do not claim it. A Submitted CPS with an eligible Approved
price bypasses the allowance. Callers own the transaction.

Use a current, locking read of the CPS counter, rather than counting orders
under InnoDB's repeatable-read snapshot. No existing SO rows are locked after
CPS rows: that would invert the Release screen's SO -> CPS lock order.
"""

import math

from production_log.job_card_tracking import cps_rules

DOCTYPE = "Customer Product Specification"
CLAIM_FIELD = "first_submitted_sales_order"


def lock_specs(db, names):
	locked = {}
	for name in sorted(set(filter(None, names))):
		rows = db.sql(
			"SELECT name, modified, first_submitted_sales_order "
			"FROM `tabCustomer Product Specification` WHERE name = %s FOR UPDATE",
			(name,), as_dict=True,
		)
		if rows:
			locked[name] = rows[0]
	return locked


def blocks_first_order(claim, current_order):
	return bool(claim and claim != current_order)


def draft_price_values(order, line):
	"""Propose the actual SO's net rate, never an approval or a gross conversion."""
	rate = float(line.get("rate"))
	factor = float(line.get("conversion_factor"))
	if not math.isfinite(rate) or rate < 0 or not math.isfinite(factor) or factor <= 0:
		raise ValueError("A finite non-negative rate and positive conversion factor are required")
	if not line.get("uom") or not order.get("currency") or not cps_rules.to_date(order.get("transaction_date")):
		raise ValueError("Order currency, UOM and effective date are required")
	return {
		"rate": cps_rules.round_rate(rate), "uom": line.get("uom"),
		"currency": order.get("currency"), "conversion_factor": factor,
		"valid_from": order.get("transaction_date"), "source": "Sales Order",
		"source_ref": order.get("name"), "tax_basis": "Net", "tax_rate": 0,
		"approval_status": cps_rules.APPROVAL_DRAFT,
		"notes": "Proposed from the first Sales Order {0}, line {1}; awaiting approval.".format(
			order.get("name"), line.get("name") or line.get("idx") or "?"),
	}


def claim_locked_specs(db, locked, order):
	"""Record first submission only; never replace an earlier order's claim."""
	if not order:
		raise ValueError("A submitted order must have a name")
	for name, row in locked.items():
		if not row.get(CLAIM_FIELD):
			db.set_value(DOCTYPE, name, CLAIM_FIELD, order, update_modified=False)
			row[CLAIM_FIELD] = order


def preserve_claim(doc, db):
	"""Discard client-supplied claims, including stale saves after SO submit.

	Called on validate, update-after-submit AND cancellation of the CPS. The
	field is no_copy, so a newly amended specification starts with its own claim.
	"""
	if doc.is_new():
		doc.set(CLAIM_FIELD, None)
		return
	row = lock_specs(db, [doc.name]).get(doc.name)
	if row:
		doc.set(CLAIM_FIELD, row.get(CLAIM_FIELD))


def after_migrate():
	"""Existing submitted/cancelled orders must not gain a fresh allowance.

	Only existing CPS rows are updated. Idempotent, no commits, no new business
	records or approval changes. A cancelled SO has already used a submission.
	"""
	import frappe
	if not (frappe.db.has_column(DOCTYPE, CLAIM_FIELD)
	        and frappe.db.has_column("Sales Order Item", "custom_cps")):
		return
	rows = frappe.db.sql(
		"""SELECT item.custom_cps AS cps, so.name AS sales_order
		FROM `tabSales Order Item` item
		INNER JOIN `tabSales Order` so ON so.name = item.parent
		WHERE item.parenttype = 'Sales Order' AND so.docstatus IN (1, 2)
		  AND COALESCE(item.custom_cps, '') != ''
		ORDER BY so.creation ASC, so.name ASC""", as_dict=True,
	)
	first = {}
	for row in rows:
		first.setdefault(row.cps, row.sales_order)
	for name in sorted(first):
		claim_locked_specs(frappe.db, lock_specs(frappe.db, [name]), first[name])
