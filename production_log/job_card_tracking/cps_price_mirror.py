"""Push approved CPS prices into the ERPNext price list.

The Frappe-bound half of :mod:`cps_price_mirror_rules` — it reads documents,
writes Item Price rows and sends the refusal mail. Every decision it makes comes
from the pure module, so the rules stay testable without a bench.

Decision record, 2026-09-12 (Tanuj): the price is typed and approved on the
Customer Product Specification; the price list is kept in step by a script. The
CPS is the authority and Item Price is derived. Standard Selling with the
customer set; any spec carrying an approved price, not printed-only; refusals
email Tanuj rather than sitting in an unowned queue.

Two safety rules this module will not bend
------------------------------------------
1. **It only touches rows it owns.** ``custom_cps`` on Item Price is both the
   record of which specification supplied the rate — the "store the detail in
   the price list as well" half of the ask — and the ownership mark. A row
   without one was made by a person and is never modified.
2. **Dry run is the default.** :func:`run` reports and writes nothing unless it
   is told to. The first live write happens after a human has read the report.
"""

import frappe
from frappe.utils import add_days, getdate, today

from production_log.job_card_tracking import cps_price_mirror_rules as rules
from production_log.job_card_tracking import cps_rules

REFUSAL_EMAIL = "tanuj.haria@vimit.com"

# The last refusal set we mailed about, kept in Frappe's DefaultValue store so
# the daily sweep can tell "something changed" from "still the same one".
DIGEST_KEY = "cps_price_mirror_refusal_digest"


# ── reading ──────────────────────────────────────────────────────────────────

def collect(on_date=None):
	"""Build the plan from live specifications. Reads only.

	``on_date`` is the date the price must be in effect on — ``today()`` for the
	sweep. A forward-dated price is invisible until its date arrives, which is
	precisely why the sweep exists: nothing fires on the day a price becomes
	effective, so without it the price list lags by the length of every
	scheduled increase.
	"""
	on_date = getdate(on_date or today())

	specs = frappe.get_all(
		"Customer Product Specification",
		filters={"status": "Active", "docstatus": ["<", 2]},
		fields=["name", "customer", "linked_item"],
		limit_page_length=0,
	)
	if not specs:
		return rules.plan_mirror([])

	# One query for every price row rather than one per spec. Read through the
	# parent filter, which is how CPS Price is reachable at all.
	price_rows = frappe.get_all(
		"CPS Price",
		filters={
			"parent": ["in", [s.name for s in specs]],
			"parenttype": "Customer Product Specification",
			"parentfield": "pricing",
			"approval_status": cps_rules.APPROVAL_APPROVED,
		},
		fields=["name", "parent", "valid_from", "rate", "uom", "approval_status",
		        "vat_inclusive"],
		limit_page_length=0,
	)
	by_spec = {}
	for row in price_rows:
		by_spec.setdefault(row.parent, []).append(row)

	priced, unmappable = [], 0
	for spec in specs:
		eligible = cps_rules.resolve_eligible_price(by_spec.get(spec.name) or [], on_date)
		if not eligible:
			continue
		if not spec.linked_item:
			# An approved price with nowhere in the price list to put it. This is
			# the data job, not an error — counted so the report can say how big
			# it is rather than quietly reporting good coverage of a small set.
			unmappable += 1
			continue
		priced.append({
			"cps": spec.name,
			"customer": spec.customer,
			"item_code": spec.linked_item,
			"uom": eligible.get("uom"),
			"rate": eligible.get("rate"),
			"valid_from": eligible.get("valid_from"),
			# The specification's rate may be gross; the price list has one basis
			# and it is ex-VAT. The conversion happens in the rules.
			"vat_inclusive": eligible.get("vat_inclusive"),
		})

	return rules.plan_mirror(priced, unmappable=unmappable)


def _live_item_prices(on_date):
	"""Customer-scoped rows on the mirror's price list that are in effect today.

	Fetched whole and filtered in Python: there are a few dozen of them, and the
	date window reads far more clearly here than as a filter expression.
	"""
	rows = frappe.get_all(
		"Item Price",
		filters={"price_list": rules.PRICE_LIST, "customer": ["is", "set"], "selling": 1},
		fields=["name", "item_code", "customer", "uom", "price_list_rate",
		        "valid_from", "valid_upto", "custom_cps"],
		limit_page_length=0,
	)
	live = {}
	for r in rows:
		if r.valid_from and getdate(r.valid_from) > on_date:
			continue
		if r.valid_upto and getdate(r.valid_upto) < on_date:
			continue
		live[rules.MirrorKey(r.customer, r.item_code, r.uom)] = r
	return live


def _currency(customer):
	return frappe.get_cached_value("Customer", customer, "default_currency") \
		or cps_rules.DEFAULT_CURRENCY


# ── writing ──────────────────────────────────────────────────────────────────

def _close_off(name, on_date):
	"""Date a row off rather than delete it, so the price history stays readable."""
	frappe.db.set_value("Item Price", name, "valid_upto", add_days(on_date, -1))


def _insert(target, on_date, superseded=None):
	others = [c for c in target.agreeing if c != target.cps]
	note = f"Mirrored from {target.cps} on {on_date}."
	if target.gross:
		note += (f" Converted to ex-VAT from the specification's VAT-inclusive "
		         f"{target.gross} at {int(rules.VAT_RATE * 100)}%.")
	if others:
		note += f" {len(others) + 1} specifications agree this rate: {', '.join(target.agreeing)}."
	if superseded:
		note += f" Supersedes {superseded}."
	doc = frappe.get_doc({
		"doctype": "Item Price",
		"item_code": target.key.item_code,
		"uom": target.key.uom,
		"price_list": rules.PRICE_LIST,
		"customer": target.key.customer,
		"selling": 1,
		"buying": 0,
		"currency": _currency(target.key.customer),
		"price_list_rate": target.rate,
		"valid_from": on_date,
		"custom_cps": target.cps,
		"note": note,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def apply_plan(plan, on_date=None, dry_run=True):
	"""Turn a plan into writes. Returns what happened, or what would have.

	Nothing is written when ``dry_run`` — which is the default, deliberately.
	"""
	on_date = getdate(on_date or today())
	live = _live_item_prices(on_date)
	out = {"insert": [], "supersede": [], "unchanged": [], "skip_unowned": [], "withdraw": []}

	for target in plan.targets:
		existing = live.get(target.key)
		decision = rules.decide_write(
			target.rate,
			{"name": existing.name, "price_list_rate": existing.price_list_rate,
			 "cps": existing.custom_cps} if existing else None,
		)
		row = {
			"customer": target.key.customer, "item_code": target.key.item_code,
			"uom": target.key.uom, "rate": decision.rate, "cps": target.cps,
			"existing": decision.supersedes,
			"was": existing.price_list_rate if existing else None,
		}
		if not dry_run:
			if decision.action == rules.ACTION_INSERT:
				row["created"] = _insert(target, on_date)
			elif decision.action == rules.ACTION_SUPERSEDE:
				_close_off(decision.supersedes, on_date)
				row["created"] = _insert(target, on_date, superseded=decision.supersedes)
		out[decision.action].append(row)

	# A key that no longer resolves to a price — withdrawn, rejected, or now in
	# conflict — must not leave its old row standing. Only owned rows qualify.
	owned = [
		{"name": r.name, "customer": r.customer, "item_code": r.item_code, "uom": r.uom}
		for key, r in live.items() if r.custom_cps
	]
	for row in rules.plan_withdrawals(owned, [t.key for t in plan.targets]):
		if not dry_run:
			_close_off(row["name"], on_date)
		out["withdraw"].append(row)

	if not dry_run:
		frappe.db.commit()
	return out


# ── notifying ────────────────────────────────────────────────────────────────

def _notify_refusals(plan, dry_run):
	"""Mail only when the refusal set actually moves.

	A daily mail that says "still Novel" teaches the reader to ignore the one
	that says something new.
	"""
	digest = rules.refusal_digest(plan.refusals)
	previous = frappe.db.get_default(DIGEST_KEY) or ""
	if digest == previous or dry_run:
		return False

	frappe.db.set_default(DIGEST_KEY, digest)
	if not digest:
		subject = "CPS price mirror — all clear"
		body = ("<p>Every customer + item + UOM with an approved CPS price now agrees, "
		        "so the price list carries all of them. Nothing outstanding.</p>")
	else:
		lines = []
		for refusal in plan.refusals:
			rates = "".join(
				f"<li><b>{cps}</b> — {rate}</li>" for cps, rate in refusal.rates
			)
			lines.append(
				f"<p><b>{refusal.key.customer}</b><br>"
				f"<code>{refusal.key.item_code}</code> per {refusal.key.uom}</p><ul>{rates}</ul>"
			)
		subject = f"CPS price mirror — {len(plan.refusals)} price(s) the price list cannot hold"
		body = (
			"<p>These specifications share one customer, item and UOM but disagree on rate. "
			"ERPNext allows one Item Price per that combination, so <b>nothing was written</b> "
			"for them.</p>" + "".join(lines) +
			"<p>The fix is in the item master, not the price: an item carrying two prices for "
			"one customer is describing a construction rather than a product, and wants "
			"splitting into one item per specification — which is what labels already do.</p>"
		)

	frappe.sendmail(recipients=[REFUSAL_EMAIL], subject=subject, message=body)
	return True


# ── entry points ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def run(dry_run=1, on_date=None):
	"""Plan, and write only if explicitly told to.

	``dry_run`` defaults to true. A mirror that writes by default is one keystroke
	away from rewriting a price list nobody asked it to touch.
	"""
	dry_run = frappe.utils.cint(dry_run)
	on_date = getdate(on_date or today())
	plan = collect(on_date)
	result = apply_plan(plan, on_date=on_date, dry_run=bool(dry_run))
	mailed = _notify_refusals(plan, bool(dry_run))

	return {
		"on_date": str(on_date),
		"dry_run": bool(dry_run),
		"targets": len(plan.targets),
		"refusals": [
			{"customer": r.key.customer, "item_code": r.key.item_code,
			 "uom": r.key.uom, "rates": r.rates}
			for r in plan.refusals
		],
		"unmappable": plan.unmappable,
		"counts": {k: len(v) for k, v in result.items()},
		"detail": result,
		"mailed": mailed,
	}


def scheduled_daily_run():
	"""Nightly sweep. Writes.

	Catches the case no event can: a price approved today with an effective date
	of next Monday changes the specification's rate on Monday, and nothing fires
	on Monday.
	"""
	try:
		result = run(dry_run=0)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CPS price mirror: daily sweep failed")
		raise
	frappe.logger().info(f"CPS price mirror: {result['counts']}")
	return result


def mirror_for_spec(cps):
	"""Re-mirror just the keys one specification touches, after its price moves.

	The whole plan is built — 292 specs is cheap — and then narrowed, because the
	agreement test needs every sibling spec on the same key. Narrowing the READ
	instead would let one spec's approval write a rate its sibling disagrees with.
	"""
	spec = frappe.db.get_value(
		"Customer Product Specification", cps, ["customer", "linked_item"], as_dict=True
	)
	if not spec or not spec.linked_item:
		return None

	plan = collect()
	keys = {
		t.key for t in plan.targets
		if t.key.customer == spec.customer and t.key.item_code == spec.linked_item
	} | {
		r.key for r in plan.refusals
		if r.key.customer == spec.customer and r.key.item_code == spec.linked_item
	}
	narrowed = rules.MirrorPlan(
		[t for t in plan.targets if t.key in keys],
		[r for r in plan.refusals if r.key in keys],
		0,
	)
	result = apply_plan(narrowed, dry_run=False)
	_notify_refusals(plan, dry_run=False)
	return result


def mirror_after_approval(cps):
	"""Called from ``approve_cps_price``. Never lets a mirror fault block a price.

	Approving a price is the human act and it has already happened by the time
	this runs. The price list catching up is downstream, and the nightly sweep
	will pick up anything a failure here drops.
	"""
	try:
		return mirror_for_spec(cps)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"CPS price mirror failed for {cps}")
		return None
