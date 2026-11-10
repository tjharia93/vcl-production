"""One submitted Sales Order per CPS pending price approval (10-Nov-2026).

The claim is server owned and survives cancellation, price-row replacement and
revision. Draft saves do not claim it. An eligible Approved price bypasses the
allowance; a missing price is never a Draft price. Callers own the transaction.

Use a current, locking read of the CPS counter, rather than counting orders
under InnoDB's repeatable-read snapshot. No existing SO rows are locked after
CPS rows: that would invert the Release screen's SO -> CPS lock order.
"""

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


def blocks_draft_price(claim, current_order):
	return bool(claim and claim != current_order)


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
