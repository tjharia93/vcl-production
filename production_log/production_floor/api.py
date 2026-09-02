"""Whitelisted endpoints behind the VCL Production Lite screen.

The desk forms still work and are the fallback for anything unusual, but the
production floor only ever talks to this module. Every call is small enough
to survive a phone on a weak connection.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, today

from production_log.production_floor.reporting import (
	QuantityError,
	JOB_CARD_SOURCES,
	OPEN_JOB_CARD_STATUSES,
	PLANNED_JOB_CARD_STATUS,
	RECEIVED_JOB_CARD_STATUS,
	build_report_text,
	build_whatsapp_text,
	build_whatsapp_start_text,
	exception_summary,
	job_card_chip,
	group_to_plan,
	job_card_doctype,
	job_card_route,
	roll_up_stages,
	stage_flow,
	stage_percent,
	carry_forward_row,
	plan_lines,
	order_departments,
	parse_quantity,
	summarise,
	unfinished_rows,
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
	"carried_quantity",
	"part_label",
	"part_number",
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
		# Same round trip as everything else: the floor's link drops for
		# minutes, and a second call to answer "what did yesterday leave?"
		# would be the one that fails.
		"unfinished": list_unfinished(production_date),
		# Grouped here rather than on the phone: "how late is it" is a rule, and
		# rules for this screen live in reporting.py where they are unit tested.
		"to_plan_groups": group_to_plan(to_plan, today()),
		"today": today(),
		"is_manager": MANAGER_ROLE in roles or "System Manager" in roles,
	}


def get_machines(department=None):
	"""Not whitelisted: the board already ships the machine list, so there is
	no reason for this to be reachable from a browser on its own.

	A machine can serve more than one department - M1 prints Computer Paper and
	Reel to Reel on the same press - so filtering is done here rather than in
	the query. One press must never become two records: that splits its history
	in half and shows the same machine twice on the board.
	"""
	machines = frappe.get_all(
		"VCL Production Machine",
		filters={"active": 1},
		fields=[
			"name", "machine_name", "department", "machine_type",
			"display_order", "also_serves",
		],
		order_by="department asc, display_order asc, machine_name asc",
	)
	for machine in machines:
		machine["departments"] = machine_departments(machine)
	if not department:
		return machines
	return [m for m in machines if department in m["departments"]]


def machine_departments(machine):
	"""Every department a machine can be picked under, home first."""
	departments = [machine.get("department")] if machine.get("department") else []
	for line in (machine.get("also_serves") or "").splitlines():
		name = line.strip()
		if name and name not in departments:
			departments.append(name)
	return departments


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
def get_job_progress(job_card=None):
	"""Every board row stamped with this job card, gathered into its stages.

	Nothing new is recorded to produce this. The floor already enters
	(machine, quantity, unit) every day; the machine says which stage it
	serves, and ERPNext's Workstation Type already sequences the stages. This
	only reads back what is there.
	"""
	job_card = (job_card or "").strip()
	if not job_card:
		frappe.throw(_("Which job card?"))

	rows = _rows_for_job_card(job_card)
	stage_of_machine, position_of_stage = _stage_maps()
	stages = roll_up_stages(rows, stage_of_machine, position_of_stage)

	ordered, unit = _order_size(job_card)
	for stage in stages:
		# Only against the unit the order was placed in. A stage counted in kg
		# has no percentage of an order counted in cartons, and saying so is
		# the whole point of this section.
		total = stage["totals"].get(unit) if unit else None
		stage["percent"] = stage_percent(total, ordered)

	return {
		"job_card": job_card,
		"doctype": job_card_doctype(job_card),
		"ordered_quantity": ordered,
		"ordered_uom": unit,
		"stages": stages,
		"flows": stage_flow(stages),
		"entries": len(rows),
	}


def _rows_for_job_card(job_card):
	"""The production rows for one card, across every day, dated."""
	rows = frappe.get_all(
		"VCL Daily Production Item",
		filters={"production_job_card": job_card, "parenttype": "VCL Daily Production"},
		fields=["parent", "machine", "department", "actual_quantity", "uom", "status", "idx"],
	)
	if not rows:
		return []

	# The date lives on the parent, and a stage total spanning two days is the
	# normal case - Collation ran on the 3rd and the 4th for one job.
	dates = dict(
		frappe.get_all(
			"VCL Daily Production",
			filters={"name": ["in", list({r.parent for r in rows})]},
			fields=["name", "production_date"],
			as_list=True,
		)
	)
	for row in rows:
		row["production_date"] = str(dates.get(row.parent) or "")
	return rows


def _stage_maps():
	"""machine -> stage, and stage -> where it sits in the route."""
	stage_of_machine = {
		m.name: m.stage
		for m in frappe.get_all("VCL Production Machine", fields=["name", "stage"])
		if m.stage
	}
	position_of_stage = {}
	if frappe.db.exists("DocType", "Workstation Type"):
		try:
			position_of_stage = {
				t.name: t.get("custom_stage_position")
				for t in frappe.get_all(
					"Workstation Type", fields=["name", "custom_stage_position"]
				)
			}
		except Exception:
			# A site without the custom field still gets its stages, just in
			# name order rather than route order.
			position_of_stage = {}
	return stage_of_machine, position_of_stage


def _order_size(job_card):
	"""How much was ordered, and in what - or (None, None) if we cannot tell."""
	doctype = job_card_doctype(job_card)
	if not doctype or not frappe.db.exists("DocType", doctype):
		return None, None
	try:
		ordered = frappe.db.get_value(doctype, job_card, "quantity_ordered")
	except Exception:
		return None, None
	if ordered in (None, ""):
		return None, None
	try:
		ordered = float(ordered)
	except (TypeError, ValueError):
		# Carton stores quantity_ordered as Data, so it is not always a number.
		return None, None
	# Computer Paper and Carton are both ordered in cartons, and the floor
	# counts the finishing stages the same way - which is what makes a
	# percentage meaningful at all.
	return ordered, "cartons"
def get_plan_template(job_card=None):
	"""Every station a job will pass through, ready to be planned in one go.

	The route comes from the job card itself where it has one - Computer Paper
	already carries Design / Pending Films / Printing / Collation / Numbering /
	Pack, with Numbering dropped when the card says it is not needed. Printing
	is expanded to one line per part, because each part prints on its own press.
	"""
	job_card = (job_card or "").strip()
	doctype = job_card_doctype(job_card)
	if not job_card or not doctype:
		frappe.throw(_("That job card is not one we can plan from."))

	card = frappe.get_doc(doctype, job_card)
	route = _route_for(card)
	parts = [
		{
			"part_number": row.get("part_number"),
			"paper_type": row.get("paper_type"),
			"colour": row.get("colour"),
			"gsm": row.get("gsm"),
		}
		for row in (card.get("colour_of_parts") or [])
	]

	machines = get_machines()
	by_stage = {}
	for machine in machines:
		if machine.get("stage"):
			by_stage.setdefault(machine["stage"], []).append(machine["name"])

	lines = plan_lines(route, parts)
	for line in lines:
		line["machines"] = by_stage.get(line["stage"], [])
		line["machine"] = line["machines"][0] if line["machines"] else None
		# Ticked only where we can actually put the work somewhere. A stage with
		# no machine is shown, unticked, so the gap is visible rather than the
		# stage silently missing from the plan.
		line["include"] = bool(line["machines"])

	return {
		"job_card": job_card,
		"doctype": doctype,
		"customer_name": card.get("customer") or card.get("customer_name"),
		"job_name": card.get("specification_name"),
		"ordered_quantity": card.get("quantity_ordered"),
		"instructions": card.get("special_instructions") or card.get("order_comments"),
		"lines": lines,
		"units": get_units(),
	}


def _route_for(card):
	"""The stages this job runs, in order.

	Read off the card rather than assumed: Computer Paper builds its own route
	and already drops Numbering when numbering_required is off.
	"""
	stages = card.get("production_stages") or []
	if stages:
		ordered = sorted(stages, key=lambda row: row.get("sequence") or 0)
		return [row.get("stage") for row in ordered if row.get("stage")]
	if hasattr(card, "get_production_stage_route"):
		try:
			return card.get_production_stage_route()
		except Exception:
			pass
	return []


@frappe.whitelist()
def plan_job(production_date=None, job_card=None, lines=None):
	"""Put every chosen station on the board in one action.

	One call rather than one per station: a five-stage job is five rows, and
	making a planner tap Add Job five times is how a plan stops being made.
	"""
	doc = _open_day(production_date)
	job_card = (job_card or "").strip()
	if isinstance(lines, str):
		lines = json.loads(lines)
	lines = [line for line in (lines or []) if line.get("include")]
	if not lines:
		frappe.throw(_("Tick at least one station."))

	for line in lines:
		machine = (line.get("machine") or "").strip()
		if not machine:
			frappe.throw(
				_("{0} has no machine chosen.").format(line.get("stage") or _("A stage"))
			)
		department = frappe.db.get_value("VCL Production Machine", machine, "department")
		doc.append("items", {
			"department": line.get("department") or department,
			"machine": machine,
			"customer_name": (line.get("customer_name") or "").strip(),
			"job_name": (line.get("job_name") or "").strip(),
			"part_label": line.get("part_label"),
			"part_number": line.get("part_number"),
			"planned_quantity": _quantity(line.get("planned_quantity"), _("Planned Quantity")),
			"uom": line.get("uom"),
			"status": "Planned",
			"source": "Job Card" if job_card else "Manual",
			"production_job_card": job_card or None,
			"job_card_instructions": (line.get("instructions") or "").strip() or None,
			"remember_job": 1,
		})

	doc.save()
	if job_card:
		_mark_job_card_planned(job_card, line.get("doctype"))
	frappe.db.commit()
	return _day_payload(doc)


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
	carried_quantity=None,
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
	if carried_quantity is not None:
		target.carried_quantity = _quantity(carried_quantity, _("Carry Forward"))
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

	# Carrying work forward creates tomorrow's row, so the morning board already
	# knows what is owed and nobody re-types it. After the save, because the row
	# being carried has to be safely recorded first.
	carried_to = None
	if target.carried_quantity:
		carried_to = _carry_forward(doc, target)

	frappe.db.commit()
	payload = _day_payload(doc)
	payload["carried_to"] = carried_to
	return payload


def _carry_forward(doc, row):
	"""Put the unfinished balance on the next day's board.

	Idempotent by machine + job card + job name: editing today's carry figure
	twice must not leave two rows waiting tomorrow. The existing row's planned
	quantity is corrected instead.
	"""
	values = dict(row.as_dict())
	values["production_date"] = str(doc.production_date)
	next_date = add_days(doc.production_date, 1)
	template = carry_forward_row(values, str(next_date))
	if not template:
		return None

	tomorrow = get_or_create_day(next_date)
	if tomorrow.status == "Closed":
		return None

	for existing in tomorrow.items:
		same_job = (
			existing.machine == template["machine"]
			and (existing.production_job_card or "") == (template["production_job_card"] or "")
			and (existing.job_name or "") == (template["job_name"] or "")
			and (existing.part_label or "") == (template["part_label"] or "")
		)
		if same_job and existing.status == "Planned":
			existing.planned_quantity = template["planned_quantity"]
			tomorrow.save()
			return {"date": str(next_date), "created": 0}

	template.pop("production_date", None)
	tomorrow.append("items", dict(template, remember_job=1))
	tomorrow.save()
	return {"date": str(next_date), "created": 1}


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
	"""Every report rendering plus the numbers behind them.

	`whatsapp_start` and `whatsapp` are the two ends of the day and are
	deliberately different messages, not one message at two times:

	  - START answers "what is on" - planned figures, work carried over, and
	    the cards still to plan. Read before the shift, by people deciding
	    where to stand.
	  - END answers "what happened" - actuals, statuses, reasons, exceptions.

	Both are returned every call rather than gated behind a parameter, so a
	caller can offer the two buttons without a second round trip on a link
	that drops for minutes at a time.
	"""
	production_date = production_date or today()
	doc = get_or_create_day(production_date, create=False)
	departments = get_departments()

	# Never fatal: a Job Card Tracking problem must not cost the floor its
	# morning report. An absent queue simply omits the STILL TO PLAN block.
	try:
		# Grouped, then flattened: group_to_plan is what stamps `days_late` on
		# each chip. Without it every overdue card reads a bare "(late)" and
		# the morning report loses the one number that ranks them.
		waiting = [
			chip
			for group in group_to_plan(list_to_plan(), today())
			for chip in group["chips"]
		]
	except Exception:
		waiting = []

	if not doc:
		empty = {"production_date": str(production_date), "items": []}
		return {
			"exists": False,
			"production_date": str(production_date),
			"text": build_report_text(empty, departments),
			"whatsapp": build_whatsapp_text(empty, departments),
			"whatsapp_start": build_whatsapp_start_text(empty, departments, waiting),
			"summary": summarise([]),
			"exceptions": exception_summary([]),
		}

	payload = _day_payload(doc)
	return {
		"exists": True,
		"production_date": str(doc.production_date),
		"status": doc.status,
		"text": doc.report_text(departments),
		"whatsapp": doc.whatsapp_text(departments),
		"whatsapp_start": build_whatsapp_start_text(payload, departments, waiting),
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
def list_unfinished(production_date=None, look_back_days=7):
	"""What the LAST working day left behind, for today's board to offer.

	Deliberately not "yesterday": a Monday must see Saturday's leftovers, and a
	day nobody closed must not hide behind a day nobody opened. This walks back
	from the given date to the most recent day that actually had rows on it.

	Read-only. It suggests; it never creates a row. Bringing one forward is the
	existing carry - `update_item` with a `carried_quantity` - which is already
	idempotent, so offering the same job twice cannot double it.
	"""
	production_date = production_date or today()

	for step in range(1, cint(look_back_days) + 1):
		previous = add_days(production_date, -step)
		doc = get_or_create_day(previous, create=False)
		if not doc or not doc.items:
			continue

		rows = [{field: row.get(field) for field in ROW_FIELDS} for row in doc.items]
		return {
			"source_date": str(doc.production_date),
			"source_status": doc.status,
			"rows": unfinished_rows(rows),
		}

	return {"source_date": None, "source_status": None, "rows": []}


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
