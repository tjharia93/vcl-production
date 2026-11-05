"""Exercise-book capture v3: server side of /exercise-book-production-v3-dev.

Tanuj, 04/11/2026: every post is confirmed TWICE on the page and then posts for real
(no Preview/Live switch). The page sends confirmed=2 only after both confirmations;
anything else is refused here. Every post is re-planned against live stock
(eb_capture_rules.plan), refused if short, and inserted + submitted in one request, so
a failure rolls the whole entry back. The remarks start with the audit line
"Capture v3 · run <run> · confirmed twice by <user> at <time>".

Kill switch: site config eb_capture_disabled = 1 refuses every post and undo.
Undo: the same user may cancel an entry this page posted within 10 minutes (also
confirmed twice on the page).
"""

import json

import frappe
from frappe.utils import cint, format_datetime, getdate, now_datetime, nowdate, nowtime, time_diff_in_seconds

from production_log.production_floor import eb_capture_rules as rules

OFF_KEY = "eb_capture_disabled"
ROLES = {"Stock Manager", "Stock User", "Manufacturing Manager", "Manufacturing User", "System Manager"}
UNDO_SECONDS = 600
RUN_FIELD = "custom_eb_run"  # used when it exists on Stock Entry; the run is in remarks either way
SHIFT_FIELD = "custom_eb_shift"  # same: used when it exists; the date and shift are in remarks either way
MACHINE_FIELD = "custom_eb_machine"  # added by production_floor.install; the machine and its asset are in remarks either way


def _check_open(confirmed):
	if cint(frappe.conf.get(OFF_KEY) or 0):
		frappe.throw("Capture posting is switched off on this site (site config eb_capture_disabled).")
	if cint(confirmed) != 2:
		frappe.throw("Not posted: the entry has to be confirmed twice on the page first.")


def _require_role():
	if not ROLES.intersection(frappe.get_roles()):
		frappe.throw("Posting exercise-book stock needs a Stock or Manufacturing role.", frappe.PermissionError)


def _bin(item, warehouse):
	if not item:
		return 0
	return frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty") or 0


def _group_context(group, book=None):
	g = rules.parse_group(group)
	c = rules.codes(g)
	if book:
		c["book"] = book
	for key in ("cov", "fld", "ins", "book"):
		if not frappe.db.exists("Item", c[key]):
			frappe.throw(f"Item {c[key]} does not exist, so this group can't be captured.")
	ups = rules.ups_from_name(frappe.db.get_value("Item", c["ins"], "item_name"), g["size"])
	cpc = frappe.db.get_value("UOM Conversion Detail", {"parenttype": "Item", "parent": c["book"], "uom": "Carton"}, "conversion_factor")
	carton_enabled = bool(c["carton"]) and frappe.db.get_value("Item", c["carton"], "disabled") == 0
	stock = {
		"cov": _bin(c["cov"], rules.STORES),
		"fld": _bin(c["fld"], rules.STORES),
		"ins": _bin(c["ins"], rules.STORES),
		"fg": _bin(c["book"], rules.FG),
		"carton": _bin(c["carton"], rules.STORES),
	}
	return g, c, ups, int(cpc or 0), carton_enabled, stock


def _machines():
	"""Active machines per station, from VCL Production Machine. Adding one is data, never code."""
	if not frappe.get_meta("VCL Production Machine").has_field("eb_stations"):
		return {}
	return rules.machines_by_station(frappe.get_all("VCL Production Machine", filters={"active": 1},
		fields=["name", "asset", "eb_stations", "display_order"]))


@frappe.whitelist()
def get_mode():
	"""For the page: is live posting on, and may this user post?"""
	return {"server": True, "disabled": bool(cint(frappe.conf.get(OFF_KEY) or 0)),
		"can_post": bool(ROLES.intersection(frappe.get_roles())),
		"run_field": bool(frappe.get_meta("Stock Entry").has_field(RUN_FIELD)),
		"shift_field": bool(frappe.get_meta("Stock Entry").has_field(SHIFT_FIELD)),
		"shifts": list(rules.SHIFTS), "backdate_days": rules.BACKDATE_DAYS, "today": nowdate(), "user": frappe.session.user,
		"machines": _machines()}


@frappe.whitelist(methods=["POST"])
def post_entry(payload):
	"""payload = {station, group, book?, run, date, shift, machine?, inputs:{...}, weights?, note?, confirmed: 2}. Returns the posted entry."""
	data = json.loads(payload) if isinstance(payload, str) else (payload or {})
	_check_open(data.get("confirmed"))
	_require_role()
	station, group, run = data.get("station"), data.get("group"), (data.get("run") or "").strip()
	if not run:
		frappe.throw("Enter the run number.")
	today = getdate(nowdate())
	try:
		date, shift = rules.check_when(data.get("date"), data.get("shift"), today)
		machine = rules.check_machine(station, data.get("machine"), _machines())
	except rules.CaptureError as e:
		frappe.throw(str(e))
	g, c, ups, cpc, carton_enabled, stock = _group_context(group, data.get("book"))
	try:
		p = rules.plan(station, ups, stock, data.get("inputs") or {}, books_per_carton=cpc,
			carton_enabled=carton_enabled, item=c)
	except rules.CaptureError as e:
		frappe.throw(str(e))
	if not p["ok"]:
		frappe.throw("<br>".join(m[1] for m in p["msgs"] if m[0] == "bad") or "Nothing to post.")
	extra = dict(p["extra"])
	if data.get("weights"):
		extra["weights"] = str(data["weights"])[:200]
	if machine:
		extra["machine"], extra["asset"] = machine["name"], machine["asset"]

	se = frappe.new_doc("Stock Entry")
	se.company = rules.COMPANY
	se.stock_entry_type = p["type"]
	se.purpose = p["type"]
	se.set_posting_time = 1
	se.posting_date = date
	se.posting_time = rules.posting_time(date, shift, today, nowtime())
	se.remarks = rules.remarks(station, group, run, extra, data.get("note"), user=frappe.session.user,
		at=format_datetime(now_datetime(), "dd-MM-yyyy HH:mm"), date=date, shift=shift)
	if se.meta.has_field(RUN_FIELD):
		se.set(RUN_FIELD, run)
	if se.meta.has_field(SHIFT_FIELD):
		se.set(SHIFT_FIELD, shift)
	if machine and se.meta.has_field(MACHINE_FIELD):
		se.set(MACHINE_FIELD, machine["name"])
	if station == "packing":
		se.fg_completed_qty = extra["books"]
		bom = frappe.db.get_value("BOM", {"item": c["book"], "is_active": 1, "is_default": 1, "docstatus": 1}, "name")
		if bom:
			se.bom_no = bom
	for r in p["rows"]:
		qty = abs(r["qty"])
		if not qty:
			continue
		line = {"item_code": r["item"], "qty": qty, "uom": "Nos", "conversion_factor": 1, "allow_zero_valuation_rate": 1}
		if r["dir"] == "out":
			line["s_warehouse"] = r["warehouse"]
		else:
			line["t_warehouse"] = r["warehouse"]
			if station in ("inserts", "packing"):
				line["is_finished_item"] = 1
		se.append("items", line)
	se.insert()
	se.submit()
	return {"name": se.name, "type": p["type"], "posting_date": str(date), "shift": shift, "machine": machine["name"] if machine else None, "rows": p["rows"], "msgs": p["msgs"], "remarks": se.remarks}


@frappe.whitelist(methods=["POST"])
def undo_entry(name, confirmed=None):
	"""Cancel an entry this page posted, by the same user, within 10 minutes (confirmed twice)."""
	_check_open(confirmed)
	_require_role()
	se = frappe.get_doc("Stock Entry", name)
	if se.docstatus != 1 or rules.MARKER not in (se.remarks or ""):
		frappe.throw(f"{name} is not a submitted capture-v3 entry.")
	if se.owner != frappe.session.user:
		frappe.throw("Only the person who posted it can undo it here.")
	if time_diff_in_seconds(now_datetime(), se.creation) > UNDO_SECONDS:
		frappe.throw("Undo is only open for 10 minutes. Ask a Stock Manager to cancel it in Desk.")
	se.cancel()
	return {"name": name, "cancelled": True}
