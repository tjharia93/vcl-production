"""Whitelisted endpoints behind the VCL Production Lite screen.

The desk forms still work and are the fallback for anything unusual, but the
production floor only ever talks to this module. Every call is small enough
to survive a phone on a weak connection.
"""

import frappe
from frappe import _
from frappe.utils import cint, today

from production_log.production_floor.reporting import (
	QuantityError,
	JOB_CARD_SOURCES,
	OPEN_JOB_CARD_STATUSES,
	PLANNED_JOB_CARD_STATUS,
	RECEIVED_JOB_CARD_STATUS,
	build_report_text,
	build_whatsapp_text,
	exception_summary,
	job_card_chip,
	group_to_plan,
	job_card_route,
	order_departments,
	parse_quantity,
	summarise,
)
from production_log.production_floor.doctype.vcl_daily_production.vcl_daily_production import (
	MANAGER_ROLE,
	get_or_create_day,
)
from production_log.production_floor.doctype.vcl_production_job.vcl_production_job import (
	build_label,
	remember_job,
)
from production_log.production_floor.doctype.vcl_production_settings.vcl_production_settings import (
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
	"job_card_instructions",
	"start_time",
	"completed_time",
	"source",
	"production_job_card",
	"erpnext_job_card",
]


def _day_payload(doc):
	rows = [{field: row.get(field) for field in ROW_FIELDS} for row in doc.items]
	for row in rows:
		row["start_time"] = str(row["start_time"]) if row["start_time"] else None
		row["completed_time"] = str(row["completed_time"]) if row["completed_time"] else None
		# Built here rather than on the phone, so the screen never has to know
		# how a job card number maps to a doctype or a desk URL.
		row["job_card_route"] = job_card_route(row.get("production_job_card"))

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
	to_plan = list_to_plan()
	return {
		"day": _day_payload(doc),
		"machines": get_machines(),
		"units": get_units(),
		"departments": get_departments(),
		"to_plan": to_plan,
		# Grouped here rather than on the phone: "how late is it" is a rule, and
		# rules for this screen live in reporting.py where they are unit tested.
		"to_plan_groups": group_to_plan(to_plan, today()),
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
def add_machine(machine_name=None, department=None, machine_type="Machine"):
	"""Create a machine from the floor screen, without leaving it.

	A machine missing from the master stops the entry dead - the supervisor
	cannot record what actually ran. Sending them to the desk form mid-shift is
	the friction this screen exists to remove, so the picker offers it inline.

	Managers only, and by the same role the masters already require: this
	writes to a master, and a user who may not edit it there may not edit it
	from here either.
	"""
	roles = frappe.get_roles()
	if MANAGER_ROLE not in roles and "System Manager" not in roles:
		frappe.throw(
			_("Only a production manager can add a machine."), frappe.PermissionError
		)

	machine_name = (machine_name or "").strip()
	if not machine_name:
		frappe.throw(_("Give the machine or process a name."))
	if not department:
		frappe.throw(_("A machine has to belong to a department."))
	if department not in get_departments():
		frappe.throw(_("{0} is not one of the departments.").format(department))
	if machine_type not in ("Machine", "Process"):
		machine_type = "Machine"

	if frappe.db.exists("VCL Production Machine", machine_name):
		existing = frappe.db.get_value(
			"VCL Production Machine", machine_name, ["department", "active"], as_dict=True
		)
		# Deactivated rather than deleted is how this master retires things, so
		# a name coming back usually means someone is reinstating it.
		if not existing.active:
			frappe.db.set_value("VCL Production Machine", machine_name, "active", 1)
			frappe.db.commit()
			return {"name": machine_name, "reactivated": 1, "machines": get_machines()}
		frappe.throw(
			_("{0} already exists, under {1}.").format(machine_name, existing.department)
		)

	# Sorted to the end of its own department rather than the middle of it.
	last = frappe.db.get_value(
		"VCL Production Machine",
		{"department": department},
		"display_order",
		order_by="display_order desc",
	)
	frappe.get_doc({
		"doctype": "VCL Production Machine",
		"machine_name": machine_name,
		"department": department,
		"machine_type": machine_type,
		"display_order": (cint(last) or 0) + 10,
		"active": 1,
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"name": machine_name, "reactivated": 0, "machines": get_machines()}


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
	job_card=None,
	job_card_doctype=None,
	job_card_instructions=None,
):
	"""Add one job to a day. This is the ten-second path.

	`job_card` is optional and always will be. A supervisor whose job has no
	card yet types the customer and job themselves, exactly as before - the
	guard below is unchanged.
	"""
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
		"source": "Job Card" if job_card else "Manual",
		"production_job_card": (job_card or "").strip() or None,
		# Kept apart from `notes` on purpose. This is what the office asked for
		# and it is read-only on the row; `notes` stays the floor's own.
		"job_card_instructions": (job_card_instructions or "").strip() or None,
	})
	doc.save()

	# Only after the row is safely saved. The board is the record that matters.
	if job_card:
		_mark_job_card_planned(job_card, job_card_doctype)

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


@frappe.whitelist()
def list_to_plan(department=None, limit=60):
	"""Job cards that have been received but not yet planned onto a machine.

	"Received but not planned" is not a new state anybody keys in - it is the
	job card's own `job_status` of "Open". Putting the job on the board flips
	the card to "Planned" (see `add_item`), so this strip drains itself and
	there is no second list to keep in step with the first.

	Read-only and deliberately forgiving. The floor screen calls this to fill
	one optional strip; if a query fails that product line is simply absent and
	the board carries on, because a Job Card Tracking problem must never stop a
	supervisor recording what ran.
	"""
	today_value = today()
	chips = []

	for source in JOB_CARD_SOURCES:
		if department and source["department"] != department:
			continue
		chips.extend(_received_cards(source, today_value))

	# Soonest due first, and anything with no due date last - a card nobody has
	# dated is not more urgent than one due tomorrow, it is just unscheduled.
	chips.sort(key=lambda chip: (chip["due_date"] is None, chip["due_date"] or "", chip["job_card"]))
	return chips[: cint(limit) or 60]


def _received_cards(source, today_value):
	"""One product line's received cards. Never raises."""
	doctype = source["doctype"]
	if not frappe.db.exists("DocType", doctype):
		return []

	customer_field = source["customer_field"]
	instructions_field = source.get("instructions_field")
	fields = ["name", customer_field, "specification_name", "due_date", "quantity_ordered"]
	if instructions_field:
		fields.append(instructions_field)
	try:
		cards = frappe.get_all(
			doctype,
			filters={
				"docstatus": ["<", 2],
				"job_status": RECEIVED_JOB_CARD_STATUS,
			},
			fields=fields,
			order_by="due_date asc, name asc",
		)
	except Exception:
		# Deliberately broad. A supervisor without read on Job Card Tracking
		# still gets the board, just without the shortcut - and a product line
		# whose card is not deployed on this site is simply absent. Nothing
		# about Job Card Tracking may stop the floor recording what ran.
		return []

	return [
		job_card_chip(
			card.get(customer_field),
			card.get("specification_name"),
			card.get("name"),
			str(card.get("due_date")) if card.get("due_date") else None,
			doctype=doctype,
			department=source["department"],
			quantity=card.get("quantity_ordered"),
			instructions=card.get(instructions_field) if instructions_field else None,
			as_of=today_value,
		)
		for card in cards
	]


def _mark_job_card_planned(job_card, doctype=None):
	"""Flip a received card to Planned once it is on the board.

	Best effort by design. The production row is the thing that matters and it
	is already saved by the time this runs; a card that cannot be updated - no
	permission, status moved on underneath us - must not undo that.
	"""
	job_card = (job_card or "").strip()
	if not job_card:
		return None

	candidates = [doctype] if doctype else [s["doctype"] for s in JOB_CARD_SOURCES]
	for candidate in candidates:
		if not candidate or not frappe.db.exists("DocType", candidate):
			continue
		try:
			if not frappe.db.exists(candidate, job_card):
				continue
			current = frappe.db.get_value(candidate, job_card, "job_status")
			if current != RECEIVED_JOB_CARD_STATUS:
				return None
			frappe.db.set_value(
				candidate, job_card, "job_status", PLANNED_JOB_CARD_STATUS, update_modified=False
			)
			return candidate
		except Exception:
			return None
	return None
