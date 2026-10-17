"""Whitelisted endpoints behind the Receive tab on the production floor page.

Daily stores receiving of computer paper: cartons weighed off the machine,
checked against the carton standard, and on Received posted into Finished
Goods as one Stock Entry (Material Receipt). Red (rejection) cartons are
counted and weighed but never posted.

Every call is small enough for a phone on the floor: start a receipt, add a
carton, undo a carton, hand over. The rules themselves are in receiving.py.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, today

from production_log.production_floor.receiving import (
	COLOUR_MEANING,
	COLOURS,
	DEFAULT_TOLERANCE_PCT,
	RUN_LIGHT_STREAK,
	WeightError,
	describe_flag,
	flag_for,
	light_streak,
	match_standard,
	needs_customer,
	parse_weight,
	standard_name,
	stock_lines,
	tally,
	tolerance_kg,
	variance_kg,
)

FLOOR_ROLES = ("VCL Production User", "VCL Production Manager", "Stock User", "Stock Manager", "System Manager")
MANAGER_ROLES = ("VCL Production Manager", "Stock Manager", "System Manager")
DEFAULT_WAREHOUSE = "Finished Goods - VCL"
DEFAULT_WEIGHERS = "Gloria\nPeter Kombo\nNadeem"
DEFAULT_RECEIVERS = "Richard"
PRODUCT_TYPE = "Computer paper"

ROW_FIELDS = [
	"name", "seq", "colour", "parts", "customer", "carton_standard", "item",
	"standard_kg", "tolerance_kg", "weight_kg", "variance_kg", "flag", "weighed_at", "weighed_by",
]


def _require(roles=FLOOR_ROLES):
	user_roles = set(frappe.get_roles())
	if user_roles.isdisjoint(roles):
		frappe.throw(_("You do not have access to stores receiving."), frappe.PermissionError)


def _lines(text, fallback):
	values = [v.strip() for v in (text or "").splitlines() if v.strip()]
	return values or [v for v in fallback.splitlines() if v]


def _settings():
	s = frappe.get_cached_doc("VCL Production Settings") if frappe.db.exists("DocType", "VCL Production Settings") else None
	return {
		"weighers": _lines(getattr(s, "stores_weighers", None), DEFAULT_WEIGHERS),
		"receivers": _lines(getattr(s, "stores_receivers", None), DEFAULT_RECEIVERS),
		"warehouse": (getattr(s, "stores_receipt_warehouse", None) or DEFAULT_WAREHOUSE),
	}


def _standards():
	rows = frappe.get_all(
		"VCL Carton Standard",
		filters={"active": 1},
		fields=["name", "colour", "parts", "customer", "item", "sheets_per_pack", "standard_kg", "tolerance_pct", "tolerance_kg", "active"],
		order_by="colour asc, parts asc, customer asc",
	)
	for r in rows:
		r["parts"] = cint(r["parts"])
		r["customer"] = r.get("customer") or None
		r["standard_kg"] = flt(r["standard_kg"])
		r["tolerance_kg"] = flt(r["tolerance_kg"]) or tolerance_kg(r["standard_kg"], r.get("tolerance_pct"))
		if r.get("customer"):
			r["customer_name"] = frappe.db.get_value("Customer", r["customer"], "customer_name") or r["customer"]
	return rows


def _machines():
	rows = frappe.get_all(
		"VCL Production Machine",
		filters={"active": 1, "department": "Computer", "machine_type": "Machine"},
		fields=["name", "machine_name", "display_order", "erpnext_workstation"],
	)
	rows.sort(key=lambda r: (cint(r.get("display_order")) or 999, r["name"]))
	return rows


def _row_payload(row):
	d = {k: row.get(k) for k in ROW_FIELDS}
	d["parts"] = cint(d["parts"])
	for k in ("standard_kg", "tolerance_kg", "weight_kg", "variance_kg"):
		d[k] = flt(d[k])
	d["verdict"] = describe_flag(d["flag"], d["variance_kg"] if d["standard_kg"] else None)
	d["weighed_at"] = str(d["weighed_at"]) if d["weighed_at"] else None
	return d


def _payload(doc):
	rows = [_row_payload(r) for r in doc.cartons]
	return {
		"name": doc.name,
		"receipt_date": str(doc.receipt_date),
		"machine": doc.machine,
		"weigher": doc.weigher,
		"receiver": doc.receiver,
		"status": doc.status,
		"stock_entry": doc.stock_entry,
		"warehouse": doc.warehouse,
		"unposted_note": doc.unposted_note,
		"cartons": rows,
		"tally": tally(rows),
		"run_light": light_streak(rows),
		"streak": RUN_LIGHT_STREAK,
	}


def _open_receipt(name):
	doc = frappe.get_doc("VCL Stores Receipt", name)
	if doc.status != "Open":
		frappe.throw(_("{0} is {1}. Start a new receipt for more cartons.").format(doc.name, doc.status.lower()))
	return doc


@frappe.whitelist()
def get_setup():
	"""Everything the Receive tab needs before the first tap."""
	_require()
	s = _settings()
	return {
		"machines": _machines(),
		"weighers": s["weighers"],
		"receivers": s["receivers"],
		"warehouse": s["warehouse"],
		"colours": [{"name": c, "meaning": COLOUR_MEANING[c], "customer": needs_customer(c), "reject": c == "Red"} for c in COLOURS],
		"standards": _standards(),
		"default_tolerance_pct": DEFAULT_TOLERANCE_PCT,
		"streak": RUN_LIGHT_STREAK,
		"today": today(),
		"user": frappe.session.user,
	}


@frappe.whitelist()
def start_receipt(machine=None, weigher=None, product_type=PRODUCT_TYPE):
	"""Today's open receipt for this machine, or a new one.

	One machine, one day, one receipt: if the weigher puts the phone down
	and comes back, they carry on where they were.
	"""
	_require()
	machine = (machine or "").strip()
	weigher = (weigher or "").strip()
	if not machine or not frappe.db.exists("VCL Production Machine", machine):
		frappe.throw(_("Which machine?"))
	if not weigher:
		frappe.throw(_("Who is weighing?"))
	existing = frappe.db.get_value(
		"VCL Stores Receipt",
		{"receipt_date": today(), "machine": machine, "status": "Open"},
		"name",
	)
	if existing:
		doc = frappe.get_doc("VCL Stores Receipt", existing)
		if doc.weigher != weigher:
			doc.weigher = weigher
			doc.save(ignore_permissions=True)
		return _payload(doc)
	doc = frappe.get_doc({
		"doctype": "VCL Stores Receipt",
		"receipt_date": today(),
		"product_type": product_type or PRODUCT_TYPE,
		"machine": machine,
		"weigher": weigher,
		"status": "Open",
		"started_at": now_datetime(),
	})
	doc.insert(ignore_permissions=True)
	return _payload(doc)


@frappe.whitelist()
def add_carton(receipt=None, colour=None, parts=None, weight_kg=None, customer=None):
	"""Weigh one carton onto the receipt. Returns the verdict for the screen."""
	_require()
	doc = _open_receipt(receipt)
	if colour not in COLOURS:
		frappe.throw(_("{0} is not a label colour.").format(colour))
	parts = cint(parts)
	if parts < 1:
		frappe.throw(_("How many parts?"))
	customer = (customer or "").strip() or None
	if needs_customer(colour):
		if not customer:
			frappe.throw(_("A Green carton is a customer pack. Which customer?"))
		if not frappe.db.exists("Customer", customer):
			frappe.throw(_("{0} is not a customer in ERPNext.").format(customer))
	else:
		customer = None
	try:
		weight = parse_weight(weight_kg)
	except WeightError as exc:
		frappe.throw(str(exc), title=_("Check the Weight"))

	std = match_standard(_standards(), colour, parts, customer)
	standard_kg = flt(std["standard_kg"]) if std else 0.0
	tol = flt(std["tolerance_kg"]) if std else 0.0
	row = doc.append("cartons", {
		"colour": colour,
		"parts": parts,
		"customer": customer,
		"carton_standard": std["name"] if std else None,
		"item": std["item"] if std else None,
		"standard_kg": standard_kg,
		"tolerance_kg": tol,
		"weight_kg": weight,
		"variance_kg": variance_kg(standard_kg, weight),
		"flag": flag_for(colour, standard_kg, tol, weight),
		"weighed_at": now_datetime(),
		"weighed_by": doc.weigher,
	})
	doc.save(ignore_permissions=True)
	out = _payload(doc)
	out["row"] = _row_payload(row)
	return out


@frappe.whitelist()
def remove_carton(receipt=None, row=None):
	"""Undo: take a carton off an open receipt."""
	_require()
	doc = _open_receipt(receipt)
	target = next((r for r in doc.cartons if r.name == row), None)
	if not target:
		frappe.throw(_("That carton is no longer on this receipt."))
	doc.remove(target)
	doc.save(ignore_permissions=True)
	return _payload(doc)


@frappe.whitelist()
def receive_receipt(receipt=None, receiver=None):
	"""Hand over to stores: post the non-Red cartons into Finished Goods.

	One Stock Entry (Material Receipt), one line per item, cartons as the
	quantity. If the entry cannot be made the whole call fails and the
	receipt stays Open - nothing is half-received.
	"""
	_require()
	doc = _open_receipt(receipt)
	receiver = (receiver or "").strip()
	if not receiver:
		frappe.throw(_("Who in stores is receiving?"))
	if not doc.cartons:
		frappe.throw(_("Nothing has been weighed yet."))

	rows = [r.as_dict() for r in doc.cartons]
	lines, skipped = stock_lines(rows)
	warehouse = _settings()["warehouse"]

	stock_entry = None
	if lines:
		stock_entry = _make_stock_entry(doc, lines, warehouse, receiver)

	doc.flags.allow_received_edit = True
	doc.status = "Received"
	doc.receiver = receiver
	doc.received_at = now_datetime()
	doc.stock_entry = stock_entry
	doc.warehouse = warehouse if stock_entry else None
	if skipped:
		doc.unposted_note = "\n".join(
			f"#{cint(r.get('seq'))} {standard_name(r.get('colour'), r.get('parts'), r.get('customer'))} "
			f"{flt(r.get('weight_kg')):.2f} kg - no ERPNext item on the standard"
			for r in skipped
		)
	else:
		doc.unposted_note = None
	doc.save(ignore_permissions=True)
	out = _payload(doc)
	out["posted_lines"] = lines
	out["skipped"] = len(skipped)
	return out


def _make_stock_entry(doc, lines, warehouse, receiver):
	if not frappe.db.exists("Warehouse", warehouse):
		frappe.throw(_("Warehouse {0} does not exist. Set the stores receipt warehouse in VCL Production Settings.").format(warehouse))
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	se = frappe.new_doc("Stock Entry")
	se.company = company
	se.stock_entry_type = "Material Receipt"
	se.purpose = "Material Receipt"
	se.to_warehouse = warehouse
	se.posting_date = doc.receipt_date
	se.set_posting_time = 1
	se.remarks = (
		f"Stores receipt {doc.name}: {doc.machine}, {doc.product_type}. "
		f"Weighed by {doc.weigher}, received by {receiver}. "
		f"{sum(l['qty'] for l in lines)} carton(s), {sum(l['kg'] for l in lines):.2f} kg."
	)
	for line in lines:
		item = frappe.db.get_value("Item", line["item"], ["stock_uom", "valuation_rate", "disabled"], as_dict=True)
		if not item:
			frappe.throw(_("Item {0} on the carton standard does not exist.").format(line["item"]))
		if item.disabled:
			frappe.throw(_("Item {0} is disabled. Fix the carton standard.").format(line["item"]))
		rate = flt(item.valuation_rate)
		se.append("items", {
			"item_code": line["item"],
			"qty": line["qty"],
			"uom": item.stock_uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": 1,
			"t_warehouse": warehouse,
			"basic_rate": rate,
			# The computer paper items carry no valuation rate yet (FG ledger
			# was empty before this). Zero value in, rather than refusing the
			# receipt - the quantity is the point of the trial.
			"allow_zero_valuation_rate": 1 if not rate else 0,
		})
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se.name


@frappe.whitelist()
def reopen_receipt(receipt=None):
	"""Manager only: cancel the Stock Entry and put the receipt back to Open."""
	_require(MANAGER_ROLES)
	doc = frappe.get_doc("VCL Stores Receipt", receipt)
	if doc.status != "Received":
		frappe.throw(_("{0} is not received.").format(doc.name))
	if doc.stock_entry and frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus") == 1:
		se = frappe.get_doc("Stock Entry", doc.stock_entry)
		se.flags.ignore_permissions = True
		se.cancel()
	doc.flags.allow_received_edit = True
	doc.status = "Open"
	doc.stock_entry = None
	doc.warehouse = None
	doc.received_at = None
	doc.unposted_note = None
	doc.save(ignore_permissions=True)
	return _payload(doc)


@frappe.whitelist()
def get_receipt(receipt=None):
	_require()
	return _payload(frappe.get_doc("VCL Stores Receipt", receipt))


@frappe.whitelist()
def list_receipts(receipt_date=None, limit=20):
	"""Today's receipts for the hand-over screen, newest first."""
	_require()
	rows = frappe.get_all(
		"VCL Stores Receipt",
		filters={"receipt_date": receipt_date or today()},
		fields=[
			"name", "machine", "weigher", "receiver", "status", "stock_entry", "started_at", "received_at",
			"carton_count", "ok_count", "light_count", "heavy_count", "unchecked_count", "reject_count",
			"received_cartons", "total_kg", "received_kg",
		],
		order_by="started_at desc",
		limit=cint(limit) or 20,
	)
	for r in rows:
		r["started_at"] = str(r["started_at"]) if r["started_at"] else None
		r["received_at"] = str(r["received_at"]) if r["received_at"] else None
	return rows
