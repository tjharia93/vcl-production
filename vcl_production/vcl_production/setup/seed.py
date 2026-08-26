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
	from vcl_production.vcl_production.doctype.vcl_production_job.vcl_production_job import (
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
		"notes": "Demo data — seeded by vcl_production.setup.seed.seed_demo_day",
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
