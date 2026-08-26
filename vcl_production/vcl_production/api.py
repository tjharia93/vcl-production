"""Whitelisted endpoints behind the VCL Production Lite screen.

The desk forms still work and are the fallback for anything unusual, but the
production floor only ever talks to this module. Every call is small enough
to survive a phone on a weak connection.
"""

import frappe
from frappe import _
from frappe.utils import cint, today

from vcl_production.reporting import (
	QuantityError,
	build_report_text,
	build_whatsapp_text,
	exception_summary,
	order_departments,
	parse_quantity,
	summarise,
)
from vcl_production.vcl_production.doctype.vcl_daily_production.vcl_daily_production import (
	MANAGER_ROLE,
	get_or_create_day,
)
from vcl_production.vcl_production.doctype.vcl_production_job.vcl_production_job import (
	build_label,
	remember_job,
)
from vcl_production.vcl_production.doctype.vcl_production_settings.vcl_production_settings import (
	get_departments,
	get_units,
)

ROW_FIELDS = [
	"name",
	"idx",
	"department",
	"machine",
	"production_job",
	"customer_name",
	"job_name",
	"planned_quantity",
	"actual_quantity",
	"uom",
	"status",
	"reason",
	"notes",
	"start_time",
	"completed_time",
	"source",
	"erpnext_job_card",
]


def _day_payload(doc):
	rows = [{field: row.get(field) for field in ROW_FIELDS} for row in doc.items]
	for row in rows:
		row["start_time"] = str(row["start_time"]) if row["start_time"] else None
		row["completed_time"] = str(row["completed_time"]) if row["completed_time"] else None

	departments = get_departments()
	return {
		"name": doc.name,
		"production_date": str(doc.production_date),
		"status": doc.status,
		"notes": doc.notes,
		"closed_by": doc.closed_by,
		"closed_at": str(doc.closed_at) if doc.closed_at else None,
		"is_demo": cint(doc.is_demo),
		"items": rows,
		"summary": summarise(rows),
		"exceptions": exception_summary(rows),
		"departments": departments,
		"department_order": order_departments(rows, departments),
	}


@frappe.whitelist()
def get_board(production_date=None):
	"""Everything the production screen needs for one day, in one round trip."""
	production_date = production_date or today()
	doc = get_or_create_day(production_date)
	roles = frappe.get_roles()
	return {
		"day": _day_payload(doc),
		"machines": get_machines(),
		"units": get_units(),
		"departments": get_departments(),
		"today": today(),
		"is_manager": MANAGER_ROLE in roles or "System Manager" in roles,
	}


def get_machines(department=None):
	"""Not whitelisted: the board already ships the machine list, so there is
	no reason for this to be reachable from a browser on its own."""
	filters = {"active": 1}
	if department:
		filters["department"] = department
	return frappe.get_all(
		"VCL Production Machine",
		filters=filters,
		fields=["name", "machine_name", "department", "machine_type", "display_order"],
		order_by="department asc, display_order asc, machine_name asc",
	)


@frappe.whitelist()
def suggest_jobs(txt=None, department=None, limit=12):
	"""Autocomplete for the Customer / Job pair.

	Ordered by what was used most recently, because the same twenty jobs
	account for almost every shift.
	"""
	txt = (txt or "").strip()
	conditions = ["active = 1"]
	values = {"limit": cint(limit) or 12}
	if txt:
		conditions.append("(customer_name LIKE %(txt)s OR job_name LIKE %(txt)s OR full_label LIKE %(txt)s)")
		values["txt"] = "%{0}%".format(txt)
	if department:
		conditions.append("(department = %(department)s OR department IS NULL OR department = '')")
		values["department"] = department

	return frappe.db.sql(
		"""
		SELECT name, customer_name, job_name, full_label, department, default_uom
		FROM `tabVCL Production Job`
		WHERE {conditions}
		ORDER BY (last_used_date IS NULL), last_used_date DESC, times_used DESC, customer_name ASC
		LIMIT %(limit)s
		""".format(conditions=" AND ".join(conditions)),
		values,
		as_dict=True,
	)


def _open_day(production_date):
	doc = get_or_create_day(production_date or today())
	if doc.status == "Closed":
		frappe.throw(
			_("{0} is closed. A manager must reopen it before it can be changed.").format(doc.name),
			title=_("Day Closed"),
		)
	return doc


def _quantity(value, label):
	try:
		return parse_quantity(value, label)
	except QuantityError as exc:
		frappe.throw(str(exc), title=_("Check the Quantity"))


@frappe.whitelist()
def add_item(
	production_date=None,
	department=None,
	machine=None,
	customer_name=None,
	job_name=None,
	planned_quantity=None,
	uom=None,
	production_job=None,
	status="Planned",
	notes=None,
	remember=1,
):
	"""Add one job to a day. This is the ten-second path."""
	doc = _open_day(production_date)

	customer_name = (customer_name or "").strip()
	job_name = (job_name or "").strip()
	if not (department and machine):
		frappe.throw(_("Department and machine are both needed."))
	if not (customer_name and job_name):
		frappe.throw(_("Customer and job are both needed."))

	doc.append("items", {
		"department": department,
		"machine": machine,
		"production_job": production_job or None,
		"customer_name": customer_name,
		"job_name": job_name,
		"planned_quantity": _quantity(planned_quantity, _("Planned Quantity")),
		"uom": uom,
		"status": status or "Planned",
		"notes": notes,
		"remember_job": cint(remember),
		"source": "Manual",
	})
	doc.save()
	frappe.db.commit()
	return _day_payload(doc)


@frappe.whitelist()
def update_item(
	production_date=None,
	row=None,
	status=None,
	actual_quantity=None,
	planned_quantity=None,
	uom=None,
	reason=None,
	notes=None,
):
	"""The quick-update path: status, actual quantity, and why."""
	doc = _open_day(production_date)
	target = None
	for item in doc.items:
		if item.name == row:
			target = item
			break
	if not target:
		frappe.throw(_("That production row is no longer on this day."))

	if status:
		target.status = status
	if actual_quantity is not None:
		target.actual_quantity = _quantity(actual_quantity, _("Actual Quantity"))
	if planned_quantity is not None:
		target.planned_quantity = _quantity(planned_quantity, _("Planned Quantity"))
	if uom:
		target.uom = uom
	if reason is not None:
		target.reason = reason
	if notes is not None:
		target.notes = notes

	# Enforced here rather than in the DocType, because this is the screen
	# where the status is actually chosen - the person is looking at the
	# reason box as they tap it.
	if target.status in ("Paused", "Carried Forward") and not (target.reason or "").strip():
		frappe.throw(
			_("A job marked {0} needs a reason.").format(_(target.status)),
			title=_("Reason Needed"),
		)

	doc.save()
	frappe.db.commit()
	return _day_payload(doc)


@frappe.whitelist()
def remove_item(production_date=None, row=None):
	doc = _open_day(production_date)
	doc.items = [item for item in doc.items if item.name != row]
	for index, item in enumerate(doc.items):
		item.idx = index + 1
	doc.save()
	frappe.db.commit()
	return _day_payload(doc)


@frappe.whitelist()
def set_day_notes(production_date=None, notes=None):
	doc = _open_day(production_date)
	doc.notes = notes
	doc.save()
	frappe.db.commit()
	return _day_payload(doc)


@frappe.whitelist()
def remember_current_job(customer_name=None, job_name=None, department=None, uom=None):
	"""The explicit 'Remember this Job' button."""
	name = remember_job(customer_name, job_name, department=department, uom=uom)
	if not name:
		frappe.throw(_("Customer and job are both needed to remember a job."))
	frappe.db.commit()
	return {"name": name, "label": build_label(customer_name, job_name)}


@frappe.whitelist()
def close_day(production_date=None, force=0):
	doc = get_or_create_day(production_date or today(), create=False)
	if not doc:
		frappe.throw(_("There is no production entered for that date."))
	exceptions = doc.close_day(force=cint(force))
	frappe.db.commit()
	return {"day": _day_payload(doc), "exceptions": exceptions}


@frappe.whitelist()
def reopen_day(production_date=None):
	doc = get_or_create_day(production_date or today(), create=False)
	if not doc:
		frappe.throw(_("There is no production entered for that date."))
	doc.reopen_day()
	frappe.db.commit()
	return _day_payload(frappe.get_doc("VCL Daily Production", doc.name))


@frappe.whitelist()
def get_report(production_date=None):
	"""Both report renderings plus the numbers behind them."""
	production_date = production_date or today()
	doc = get_or_create_day(production_date, create=False)
	if not doc:
		empty = {"production_date": str(production_date), "items": []}
		departments = get_departments()
		return {
			"exists": False,
			"production_date": str(production_date),
			"text": build_report_text(empty, departments),
			"whatsapp": build_whatsapp_text(empty, departments),
			"summary": summarise([]),
			"exceptions": exception_summary([]),
		}

	departments = get_departments()
	payload = _day_payload(doc)
	return {
		"exists": True,
		"production_date": str(doc.production_date),
		"status": doc.status,
		"text": doc.report_text(departments),
		"whatsapp": doc.whatsapp_text(departments),
		"summary": payload["summary"],
		"exceptions": payload["exceptions"],
		"day": payload,
	}


@frappe.whitelist()
def get_history(limit=30):
	"""Previous production days, newest first."""
	days = frappe.get_all(
		"VCL Daily Production",
		fields=["name", "production_date", "status", "is_demo"],
		order_by="production_date desc",
		limit_page_length=cint(limit) or 30,
	)
	if not days:
		return []

	counts = frappe.db.sql(
		"""
		SELECT parent, status, COUNT(*) AS n
		FROM `tabVCL Daily Production Item`
		WHERE parent IN %(parents)s AND parenttype = 'VCL Daily Production'
		GROUP BY parent, status
		""",
		{"parents": [d.name for d in days]},
		as_dict=True,
	)
	by_parent = {}
	for entry in counts:
		by_parent.setdefault(entry.parent, {})[entry.status] = entry.n

	for day in days:
		day["production_date"] = str(day["production_date"])
		day["counts"] = by_parent.get(day["name"], {})
		day["total"] = sum(day["counts"].values())
	return days
