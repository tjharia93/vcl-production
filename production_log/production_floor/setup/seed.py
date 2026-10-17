"""Seed data.

Two very different things live here, kept apart on purpose.

`seed_machines` is configuration: the plant's machine list. It runs on
install because a production screen with no machines is useless, and it only
ever adds what is missing.

`seed_demo_jobs` and `seed_demo_day` are sample data for a demo or a test
site. They refuse to run on a site that is not in developer mode unless
explicitly forced, and everything they create is flagged `is_demo` so a real
report can never quietly include it.
"""

import frappe
from frappe.utils import today

# Stage and Workstation live in the alignment patch (v10_1), not here: this
# list is what a machine IS, and the ERPNext mapping is a decision about a
# particular site's masters. A fresh site gets the mapping from the patch on its
# first migrate, same as an existing one.
MACHINES = [
	# (machine_name, department, machine_type, display_order)
	("M1", "Computer", "Machine", 10),
	("M2", "Computer", "Machine", 20),
	("M3", "Computer", "Machine", 30),
	("M4", "Computer", "Machine", 40),
	("Collator", "Computer", "Process", 50),
	("Solna", "Offset", "Machine", 10),
	("Miller", "Offset", "Machine", 20),
	("Miyakoshi", "Offset", "Machine", 30),
	("Printing", "Carton", "Process", 10),
	("Die Cutting", "Carton", "Process", 20),
	("Slotting", "Carton", "Process", 30),
	("Stitching", "Carton", "Process", 40),
	("Bundling", "Carton", "Process", 50),
	("Gluing", "Carton", "Process", 60),
	("Propheteer", "Labels", "Machine", 10),
	# Reel to Reel shares the four Miyakoshis with Computer Paper - that is
	# handled by `also_serves` on those machines, not by listing them twice.
	# The Slitter is the one machine only this department uses: ETR is printed
	# reel-to-reel and THEN slit, while KCB-type work finishes on the press.
	("Slitter", "Reel to Reel", "Machine", 10),
	# Monobox runs as six in-house stages, not machines - the same six the
	# Monobox job traveller is built around. Names are spelled out in full so
	# they do not collide with the Carton processes ("Die Cutting", "Bundling").
	("Board Prep & Printing", "Monobox", "Process", 10),
	("Coating", "Monobox", "Process", 20),
	("Die-cutting & Stripping", "Monobox", "Process", 30),
	("Window Patching", "Monobox", "Process", 40),
	("Folding & Gluing", "Monobox", "Process", 50),
	("Bundling & Packing", "Monobox", "Process", 60),
]

DEMO_JOBS = [
	# (customer_name, job_name, department, default_uom)
	("Chandaria", "Yellow Copy", "Computer", "reels"),
	("KCB", "Computer Paper", "Computer", "reels"),
	("Stanbic Bank", "Computer Paper", "Computer", "reels"),
	("Lijaque Stationers", "Computer Paper", "Computer", "reels"),
	("Prince", "1 Quire", "Offset", "pcs"),
	("Prince", "2 Quire", "Offset", "pcs"),
	("Prince", "3 Quire", "Offset", "pcs"),
	("Prince", "4 Quire", "Offset", "pcs"),
	("E.W.A.L", "Carton", "Carton", "pcs"),
	("Vajas", "Carton", "Carton", "pcs"),
]


def seed_machines():
	"""Add any missing machine. Never touches one that already exists."""
	created = []
	for machine_name, department, machine_type, display_order in MACHINES:
		if frappe.db.exists("VCL Production Machine", machine_name):
			continue
		frappe.get_doc({
			"doctype": "VCL Production Machine",
			"machine_name": machine_name,
			"department": department,
			"machine_type": machine_type,
			"display_order": display_order,
			"active": 1,
		}).insert(ignore_permissions=True)
		created.append(machine_name)
	return created


# Carton standards for stores receiving - read off the printed Daily Stores
# Receiving Sheet (house standards) and the October 2026 sheets (Green, which
# is per customer). Tanuj confirmed 17/10/2026 that the payslip colours (Pink,
# Blue) weigh the same as the normal ones (Yellow, Purple). Red is a rejection
# and has no standard. Add-only: a standard someone has edited live is never
# overwritten, so correct a weight on the record, not here.
#
# The item is what a carton posts to stock as. The payslip (5.5") items exist
# for 2 and 3 part only; 4-part payslip falls back to the plain 4 part item
# until an item is made for it - that is a question for Tanuj, not a guess
# baked in silently, so it is said on the record's notes.
_CP = "Computer Paper Plain-9.5 x 11-{parts} Part"
_PSLIP = "Computer Paper Plain-9.5 x 11 x 5.5-{parts} Part-PSLIP"
CARTON_STANDARDS = [
	# (colour, parts, customer, sheets_per_pack, standard_kg, item, notes)
	("Yellow", 2, None, 500, 3.95, _CP, None),
	("Yellow", 3, None, 300, 3.55, _CP, None),
	("Yellow", 4, None, 300, 4.55, _CP, None),
	("Purple", 2, None, 600, 4.80, _CP, None),
	("Purple", 3, None, 400, 4.60, _CP, None),
	("Purple", 4, None, 400, 6.00, _CP, None),
	("Pink", 2, None, 500, 3.95, _PSLIP, None),
	("Pink", 3, None, 300, 3.55, _PSLIP, None),
	("Pink", 4, None, 300, 4.55, _CP, "No 4-part payslip item in ERPNext yet; posts as the plain 4 part item."),
	("Blue", 2, None, 600, 4.80, _PSLIP, None),
	("Blue", 3, None, 400, 4.60, _PSLIP, None),
	("Blue", 4, None, 400, 6.00, _CP, "No 4-part payslip item in ERPNext yet; posts as the plain 4 part item."),
	# Green: per customer, from the October 2026 sheets. Full Channel is not a
	# customer in ERPNext yet, so its 3-part 5.70 kg standard waits until the
	# customer exists - it will be added on the live record, not here.
	("Green", 2, "MAGUNAS SUPER STORES (K) LTD", None, 6.55, _CP, "From the 13-16 Oct 2026 receiving sheets."),
]


def seed_carton_standards():
	"""Add any missing carton standard. Never touches one that already exists.

	A standard whose customer or item is not on the site is skipped with a
	note rather than inserted - an insert that throws inside after_migrate
	takes the whole migrate down (see install.py).
	"""
	if not frappe.db.exists("DocType", "VCL Carton Standard"):
		return []
	from production_log.production_floor.receiving import standard_name

	created = []
	for colour, parts, customer, sheets, kg, item_tpl, notes in CARTON_STANDARDS:
		name = standard_name(colour, parts, customer)
		if frappe.db.exists("VCL Carton Standard", name):
			continue
		if customer and not frappe.db.exists("Customer", customer):
			print(f"Carton standard {name}: customer not on this site, skipped")
			continue
		item = item_tpl.format(parts=parts) if item_tpl else None
		if item and not frappe.db.exists("Item", item):
			print(f"Carton standard {name}: item {item} not on this site, seeded without an item")
			item = None
		frappe.get_doc({
			"doctype": "VCL Carton Standard",
			"colour": colour,
			"parts": parts,
			"customer": customer,
			"sheets_per_pack": sheets,
			"standard_kg": kg,
			"tolerance_pct": 2,
			"item": item,
			"active": 1,
			"notes": notes,
		}).insert(ignore_permissions=True)
		created.append(name)
	return created


def _guard_demo(force):
	if force:
		return
	if not frappe.conf.get("developer_mode"):
		frappe.throw(
			"Demo data is only seeded on a site in developer mode. "
			"Pass force=True if you really mean to put demo rows on this site."
		)


def seed_demo_jobs(force=False):
	"""Sample remembered jobs, flagged as demo."""
	_guard_demo(force)
	from production_log.production_floor.doctype.vcl_production_job.vcl_production_job import (
		find_job,
		remember_job,
	)

	created = []
	for customer_name, job_name, department, uom in DEMO_JOBS:
		if find_job(customer_name, job_name):
			continue
		created.append(remember_job(customer_name, job_name, department, uom, is_demo=1))
	frappe.db.commit()
	return created


DEMO_DAY = [
	# department, machine, customer, job, planned, actual, uom, status, reason
	("Computer", "M1", "Chandaria", "Yellow Copy", 3, 1, "reels", "Running", None),
	("Computer", "M3", "KCB", "Computer Paper", 3, 0.5, "reels", "Running", None),
	("Computer", "M4", "NHIF", "3-Part Payslip", 2, 0, "reels", "Running", None),
	("Computer", "Collator", "Chandaria", "Yellow Copy", 12, 9, "cartons", "Running", None),
	("Offset", "Solna", "Prince", "3 Quire", 2000, 2000, "pcs", "Completed", None),
	("Offset", "Miller", "Prince", "1 Quire", 1500, 1500, "pcs", "Completed", None),
	("Carton", "Stitching", "E.W.A.L", "Carton", 1000, 1031, "pcs", "Completed", None),
	("Carton", "Bundling", "E.W.A.L", "Carton", 1000, 47, "pcs", "Carried Forward", "Board ran out at 3pm"),
]


def seed_demo_day(production_date=None, force=False):
	"""A production day resembling a real shift, flagged as demo."""
	_guard_demo(force)
	seed_demo_jobs(force=True)

	production_date = production_date or today()
	name = frappe.db.get_value("VCL Daily Production", {"production_date": production_date}, "name")
	if name:
		frappe.delete_doc("VCL Daily Production", name, ignore_permissions=True, force=True)

	doc = frappe.get_doc({
		"doctype": "VCL Daily Production",
		"production_date": production_date,
		"status": "Open",
		"is_demo": 1,
		"notes": "Demo data — seeded by production_log.production_floor.setup.seed.seed_demo_day",
	})
	for department, machine, customer, job, planned, actual, uom, status, reason in DEMO_DAY:
		doc.append("items", {
			"department": department,
			"machine": machine,
			"customer_name": customer,
			"job_name": job,
			"planned_quantity": planned,
			"actual_quantity": actual,
			"uom": uom,
			"status": status,
			"reason": reason,
			"remember_job": 1,
		})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name
