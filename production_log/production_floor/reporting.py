"""Report text, day summary and exception detection for VCL Production Lite.

Everything in this module is deliberately free of Frappe imports. It works on
plain dicts, so the wording of a report and the rules for what counts as a
missing update can be read - and tested - without a bench, a site or a
database. `api.py` is the thin layer that turns Frappe documents into the
dicts these functions expect.
"""

import re
from datetime import date, datetime
from urllib.parse import quote

DEFAULT_DEPARTMENTS = ["Computer", "Offset", "Carton", "Labels", "Monobox", "Reel to Reel"]
DEFAULT_UNITS = ["pcs", "cartons", "reels", "reams", "sheets", "kg", "metres"]

STATUSES = [
	"Planned",
	"Not Started",
	"Running",
	"Paused",
	"Completed",
	"Carried Forward",
]

_MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def to_date(value):
	"""Accept a date, a datetime or an ISO string and return a date."""
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	if not value:
		return None
	return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def format_date_long(value):
	"""2026-08-26 -> '26 AUGUST 2026'."""
	d = to_date(value)
	if not d:
		return ""
	return "{0} {1} {2}".format(d.day, _MONTHS[d.month - 1].upper(), d.year)


def format_date_short(value):
	"""2026-08-26 -> '26 Aug 2026'."""
	d = to_date(value)
	if not d:
		return ""
	return "{0} {1} {2}".format(d.day, _MONTHS[d.month - 1][:3], d.year)


def format_qty(value):
	"""Render a quantity the way the floor writes it: 1, 0.5, 1031, 2.25.

	Trailing zeros are dropped so a whole number never reads as '3.000'.
	"""
	if value in (None, ""):
		return ""
	try:
		number = float(value)
	except (TypeError, ValueError):
		return ""
	if number == int(number):
		return str(int(number))
	return ("%.3f" % number).rstrip("0").rstrip(".")


def has_qty(value):
	"""A quantity counts as entered only when it is a real number above zero."""
	if value in (None, ""):
		return False
	try:
		return float(value) > 0
	except (TypeError, ValueError):
		return False


def format_unit(quantity, unit):
	"""'1 reel', but '3 reels' and always '1031 pcs'.

	The floor says "one reel", so the report does too. Only units that are a
	plain English plural are touched; 'pcs' and 'kg' are abbreviations and
	stay exactly as they are.
	"""
	unit = (unit or "").strip()
	if not unit or unit in ("pcs", "kg"):
		return unit
	try:
		number = float(quantity)
	except (TypeError, ValueError):
		return unit
	if number == 1 and unit.endswith("s"):
		return unit[:-1]
	return unit


def qty_with_unit(quantity, unit):
	"""'3 reels' / '1 reel' / '' when there is no quantity at all."""
	rendered = format_qty(quantity)
	if rendered == "":
		return ""
	return "{0} {1}".format(rendered, format_unit(quantity, unit)).strip()


def job_title(row):
	"""'Chandaria Yellow Copy' - customer and job, without doubling up.

	Rows are entered by hand, so 'Chandaria' / 'Chandaria' happens. When the
	job repeats the customer verbatim only one of them is printed.
	"""
	customer = (row.get("customer_name") or "").strip()
	job = (row.get("job_name") or "").strip()
	if customer and job and job.lower() != customer.lower():
		return "{0} {1}".format(customer, job)
	return customer or job


def qty_pair(row):
	"""'1 / 3 reels', or '1 reel' shapes used across the two report styles."""
	unit = (row.get("uom") or "").strip()
	actual = format_qty(row.get("actual_quantity")) or "0"
	planned = format_qty(row.get("planned_quantity"))
	if planned:
		body = "{0} / {1}".format(actual, planned)
	else:
		body = actual
	return "{0} {1}".format(body, unit).strip()


def order_departments(rows, departments=None):
	"""Departments in configured order, then anything unexpected, by name."""
	preferred = list(departments or DEFAULT_DEPARTMENTS)
	present = []
	for row in rows:
		dept = (row.get("department") or "").strip() or "Unassigned"
		if dept not in present:
			present.append(dept)
	ordered = [d for d in preferred if d in present]
	ordered += sorted(d for d in present if d not in preferred)
	return ordered


def rows_for_department(rows, department):
	out = []
	for row in rows:
		dept = (row.get("department") or "").strip() or "Unassigned"
		if dept == department:
			out.append(row)
	return out


def machine_label(row):
	return (row.get("machine") or "").strip() or "Unassigned"


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------

def summarise(rows):
	"""Counts behind the cards at the top of the production screen."""
	counts = {status: 0 for status in STATUSES}
	for row in rows:
		status = row.get("status") or "Planned"
		if status in counts:
			counts[status] += 1
		else:
			counts[status] = counts.get(status, 0) + 1
	counts["Total"] = len(rows)
	return counts


# --------------------------------------------------------------------------
# exceptions
# --------------------------------------------------------------------------

def find_exceptions(rows):
	"""What the day is still missing.

	Two severities. `critical` blocks closing the day; `warning` is shown as
	ATTENTION REQUIRED but never stops anyone mid-shift. Nothing here fires
	while a row is simply being typed - these run on the day as a whole.
	"""
	found = []

	def add(row, index, severity, code, message):
		found.append({
			"severity": severity,
			"code": code,
			"message": message,
			"idx": row.get("idx") or index + 1,
			"row_name": row.get("name"),
			"department": row.get("department"),
			"machine": machine_label(row),
			"customer_name": row.get("customer_name"),
			"job_name": row.get("job_name"),
			"label": "{0} - {1}".format(machine_label(row), job_title(row)),
		})

	for index, row in enumerate(rows):
		status = row.get("status") or "Planned"
		reason = (row.get("reason") or "").strip()

		if status == "Carried Forward" and not reason:
			add(row, index, "critical", "carried_forward_no_reason",
				"Carried forward with no reason given")

		if status == "Paused" and not reason:
			add(row, index, "critical", "paused_no_reason",
				"Paused with no reason given")

		if status == "Completed" and not has_qty(row.get("actual_quantity")):
			add(row, index, "critical", "completed_no_actual",
				"Completed but no actual quantity entered")

		if status == "Planned":
			add(row, index, "warning", "planned_no_update",
				"Planned all day with no update")

		if status == "Not Started":
			add(row, index, "warning", "not_started",
				"Planned but never started")

		if status == "Running" and not has_qty(row.get("actual_quantity")):
			add(row, index, "warning", "running_no_actual",
				"Running with no actual quantity yet")

		if status == "Carried Forward" and not has_qty(row.get("actual_quantity")):
			add(row, index, "warning", "carried_forward_no_actual",
				"Carried forward with no actual quantity")

	return found


def critical_exceptions(rows):
	return [e for e in find_exceptions(rows) if e["severity"] == "critical"]


def exception_summary(rows):
	found = find_exceptions(rows)
	critical = [e for e in found if e["severity"] == "critical"]
	warnings = [e for e in found if e["severity"] == "warning"]
	return {
		"all": found,
		"critical": critical,
		"warnings": warnings,
		"critical_count": len(critical),
		"warning_count": len(warnings),
		"jobs_needing_attention": len({e["idx"] for e in found}),
	}


# --------------------------------------------------------------------------
# report text
# --------------------------------------------------------------------------

def _end_block(lines):
	"""Collapse whatever blank lines a block left behind into nothing.

	Both builders end every job with a blank line, so without this the gap
	before the next department heading doubles up - which WhatsApp renders
	as a visible hole in the middle of the message.
	"""
	while lines and lines[-1] == "":
		lines.pop()


def build_report_text(day, departments=None):
	"""The full-width report, as read on a desktop or printed.

	VCL PRODUCTION REPORT
	26 AUGUST 2026

	COMPUTER

	M1 - Chandaria Yellow Copy
	Plan: 3 reels
	Actual: 1 reel
	Status: Running
	"""
	rows = day.get("items") or []
	lines = ["VCL PRODUCTION REPORT", format_date_long(day.get("production_date"))]

	if not rows:
		lines += ["", "No production entered for this day."]
		return "\n".join(lines)

	for dept in order_departments(rows, departments):
		_end_block(lines)
		lines += ["", dept.upper(), ""]
		for row in rows_for_department(rows, dept):
			unit = (row.get("uom") or "").strip()
			lines.append("{0} - {1}".format(machine_label(row), job_title(row)))
			lines.append("Plan: {0}".format(
				qty_with_unit(row.get("planned_quantity"), unit) or "-"))
			lines.append("Actual: {0}".format(
				qty_with_unit(row.get("actual_quantity"), unit) or "0 {0}".format(unit).strip()))
			lines.append("Status: {0}".format(row.get("status") or "Planned"))
			reason = (row.get("reason") or "").strip()
			if reason:
				lines.append("Reason: {0}".format(reason))
			lines.append("")

	_end_block(lines)

	summary = summarise(rows)
	lines += ["", "SUMMARY"]
	for status in STATUSES:
		if summary.get(status):
			lines.append("{0}: {1}".format(status, summary[status]))

	exceptions = exception_summary(rows)
	if exceptions["all"]:
		lines += ["", "ATTENTION REQUIRED"]
		for item in exceptions["all"]:
			lines.append("{0}{1} - {2}".format(
				"! " if item["severity"] == "critical" else "- ",
				item["label"],
				item["message"],
			))

	notes = (day.get("notes") or "").strip()
	if notes:
		lines += ["", "NOTES", notes]

	return "\n".join(lines)


def build_whatsapp_start_text(day, departments=None, to_plan=None):
	"""The MORNING message: what each machine is set to run today.

	The evening report answers "what happened". This answers "what is on",
	which is a different question with a different audience — it is read
	before the shift, by people deciding where to stand.

	So it deliberately leaves out everything that can only be known later:
	no actuals, no exceptions, no ATTENTION REQUIRED. A morning report that
	says nothing was produced is noise, because nothing has been produced yet.

	What it adds instead is the two things a morning needs: work carried over
	from yesterday, and job cards received but not yet on any machine.
	"""
	rows = day.get("items") or []
	header = "*VCL Production Plan - {0}*".format(format_date_short(day.get("production_date")))
	lines = [header]

	if not rows:
		lines += ["", "Nothing planned yet."]
	else:
		for dept in order_departments(rows, departments):
			_end_block(lines)
			lines += ["", "*{0}*".format(dept.upper()), ""]
			for row in rows_for_department(rows, dept):
				lines.append("{0} - {1}".format(machine_label(row), job_title(row)))
				detail = planned_pair(row)
				carried = format_qty(row.get("carried_quantity"))
				if carried and float(row.get("carried_quantity") or 0) > 0:
					detail = "{0} (incl. {1} carried)".format(detail, carried) if detail else \
						"{0} carried over".format(carried)
				if detail:
					lines.append(detail)
				lines.append("")

		_end_block(lines)

	# Received but not yet on a machine. Morning is exactly when this is
	# actionable; by the evening report it is too late to matter.
	waiting = list(to_plan or [])
	if waiting:
		lines += ["", "*STILL TO PLAN*", ""]
		for chip in waiting[:12]:
			label = "{0} {1}".format(
				(chip.get("customer_name") or "").strip(),
				(chip.get("job_name") or "").strip(),
			).strip()
			ref = (chip.get("ref") or chip.get("job_card") or "").strip()
			line = "{0} - {1}".format(ref, label) if ref else label
			if chip.get("overdue"):
				days = chip.get("days_late")
				line += " ({0} days late)".format(days) if days else " (late)"
			lines.append(line)
		if len(waiting) > 12:
			lines.append("+ {0} more".format(len(waiting) - 12))

	notes = (day.get("notes") or "").strip()
	if notes:
		lines += ["", "*NOTES*", notes]

	return "\n".join(lines).rstrip()


def planned_pair(row):
	"""'3 reels planned', or '' when no figure was given.

	Deliberately NOT qty_pair: that renders '0 / 3 reels', and a zero in the
	morning is not a measurement, it is the absence of one.
	"""
	planned = format_qty(row.get("planned_quantity"))
	if not planned:
		return ""
	unit = (row.get("uom") or "").strip()
	return "{0} {1} planned".format(planned, unit).strip()


def build_whatsapp_text(day, departments=None):
	"""The message that gets pasted into the group.

	Short lines, WhatsApp bold with single asterisks, no tables, and nothing
	that survives badly when a phone re-wraps it.
	"""
	rows = day.get("items") or []
	header = "*VCL Production Report - {0}*".format(format_date_short(day.get("production_date")))
	lines = [header]

	if not rows:
		lines += ["", "No production entered."]
		return "\n".join(lines)

	for dept in order_departments(rows, departments):
		_end_block(lines)
		lines += ["", "*{0}*".format(dept.upper()), ""]
		for row in rows_for_department(rows, dept):
			lines.append("{0} - {1}".format(machine_label(row), job_title(row)))
			lines.append("{0} - {1}".format(qty_pair(row), row.get("status") or "Planned"))
			reason = (row.get("reason") or "").strip()
			if reason:
				lines.append("({0})".format(reason))
			lines.append("")

	_end_block(lines)

	summary = summarise(rows)
	for status in ("Not Started", "Carried Forward"):
		if summary.get(status):
			lines += ["", "*{0}*".format(status.upper()), "{0} {1}".format(
				summary[status], "job" if summary[status] == 1 else "jobs")]

	exceptions = exception_summary(rows)
	needing = exceptions["jobs_needing_attention"]
	if needing:
		lines += ["", "*ATTENTION REQUIRED*", "{0} {1} require{2} an update".format(
			needing,
			"job" if needing == 1 else "jobs",
			"s" if needing == 1 else "",
		)]

	notes = (day.get("notes") or "").strip()
	if notes:
		lines += ["", "*NOTES*", notes]

	return "\n".join(lines)


# --------------------------------------------------------------------------
# quantity input
# --------------------------------------------------------------------------

class QuantityError(ValueError):
	pass


def parse_quantity(value, field_label="Quantity"):
	"""Turn what someone typed into a number, or refuse it.

	Decimals are wanted ("0.5 reels"). Arithmetic is not: "41+6" has to be
	added up by the person, not guessed at by the system, because a report
	that silently turns a typo into a number is worse than one that asks.
	Blank stays blank - a quantity nobody has entered yet is not zero.
	"""
	if value is None:
		return None
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		number = float(value)
		if number < 0:
			raise QuantityError("{0} cannot be negative.".format(field_label))
		return number

	text = str(value).strip()
	if not text:
		return None

	try:
		number = float(text)
	except ValueError:
		raise QuantityError(
			"{0} must be a plain number such as 0.5, 9 or 1031. "
			"'{1}' is not - please add it up and enter the total.".format(field_label, text)
		)

	if number != number or number in (float("inf"), float("-inf")):
		raise QuantityError("{0} must be a plain number.".format(field_label))
	if number < 0:
		raise QuantityError("{0} cannot be negative.".format(field_label))
	return number


def normalise_key(customer_name, job_name):
	"""Dedupe key for remembered jobs.

	'E.W.A.L' and 'ewal' are the same customer to the floor, so they are the
	same remembered job here. Case, punctuation and repeated spaces are all
	discarded; the display value keeps whatever was typed first.
	"""
	def scrub(text):
		return "".join(c for c in (text or "").lower() if c.isalnum())

	return "{0}::{1}".format(scrub(customer_name), scrub(job_name))


# How many leading characters of the Customer name must appear at the head of
# the spec name before it counts as a repeat worth stripping.
PREFIX_MATCH_CHARS = 10


def short_job_name(customer_name, job_name):
	"""Drop a leading customer-name prefix from a job card's spec name.

	Display only. `specification_name` on a Job Card Computer Paper almost
	always opens with the customer, so a chip showing both reads the customer
	twice and overflows a 360px screen.
	"""
	job = (job_name or "").strip()
	cust = (customer_name or "").strip()
	if not job or not cust:
		return job
	# Match on the customer's opening words, not the whole name: the spec name
	# routinely drops the LTD / LIMITED the Customer record carries, and writes
	# INDUSTRIES where the Customer says INDUSTRIES LIMITED.
	if not job.upper().startswith(cust.upper()[:PREFIX_MATCH_CHARS]):
		return job
	# Whatever follows the first dash. The separator is written every way there
	# is on the live cards - " - ", "  - " and " -" with nothing after it.
	match = re.match(r"^[^-]*-\s*(.+)$", job)
	if match and match.group(1).strip():
		return match.group(1).strip()
	return job


# A job card still worth showing the floor. Everything else is either
# finished, abandoned, or waiting on a decision nobody makes at a machine.
OPEN_JOB_CARD_STATUSES = ("Open", "Planned", "In Production", "Packing Pending")

# Received, but nobody has put it on a machine yet. This is the whole basis of
# the To Plan strip: the job card vocabulary already draws the line we want, so
# the strip is derived and there is nothing extra for a supervisor to key in.
# Adding a job to the board flips the card to "Planned", which drains the strip.
RECEIVED_JOB_CARD_STATUS = "Open"
PLANNED_JOB_CARD_STATUS = "Planned"

# Which job card doctype feeds which department, and what its fields are called.
# The three product lines disagree, so it is recorded here rather than guessed at
# the call site:
#   - customer:     Carton says `customer_name`, the other two say `customer`
#   - instructions: Computer Paper has no `special_instructions` at all; its
#                   nearest equivalent is `order_comments`. Both are what the
#                   OFFICE wrote about the order, which is the side of the line
#                   we want - `production_notes` is the floor's own and belongs
#                   in the row's Notes, not here.
#
# Labels and ETR are deliberately absent: their cards exist, but the floor does
# not plan from them yet. Adding one is a line in this list and nothing else.
JOB_CARD_SOURCES = [
	{
		"doctype": "Job Card Computer Paper",
		"series_prefix": "JC-CPT-",
		"department": "Computer",
		"customer_field": "customer",
		"instructions_field": "order_comments",
	},
	{
		"doctype": "Job Card Carton",
		"series_prefix": "JC-CORR-",
		"department": "Carton",
		"customer_field": "customer_name",
		"instructions_field": "special_instructions",
	},
	{
		"doctype": "Job Card Monobox",
		"series_prefix": "JC-MBX-",
		"department": "Monobox",
		"customer_field": "customer",
		"instructions_field": "special_instructions",
	},
]


def job_card_is_open(job_status, docstatus=0):
	"""True when this job card should appear on the floor screen's chip row."""
	if docstatus and int(docstatus) >= 2:
		return False
	return (job_status or "") in OPEN_JOB_CARD_STATUSES


# How the phone's planning queue is grouped. Not "sorted by due date": a
# planner works in order of how late a thing is, so the 49-day-old Pegler
# carton belongs at the top of the screen rather than wherever a date sort
# happened to leave it. Undated jobs go LAST - unscheduled is not urgent.
TO_PLAN_GROUPS = [
	("late", "Late"),
	("today", "Due today"),
	("week", "This week"),
	("later", "Later"),
	("undated", "No due date"),
]


def to_plan_bucket(due_date, as_of=None):
	"""Which planning group a due date falls in."""
	parsed = _as_date(due_date)
	if not parsed:
		return "undated"
	today_value = _as_date(as_of) or date.today()
	delta = (parsed - today_value).days
	if delta < 0:
		return "late"
	if delta == 0:
		return "today"
	if delta <= 7:
		return "week"
	return "later"


def days_late(due_date, as_of=None):
	"""How many days past due, or 0 when it is not late."""
	parsed = _as_date(due_date)
	if not parsed:
		return 0
	today_value = _as_date(as_of) or date.today()
	return max(0, (today_value - parsed).days)


def group_to_plan(chips, as_of=None):
	"""The queue as the phone renders it: groups in order, empties dropped.

	Chips arrive already sorted soonest-first with undated last, so within a
	group the order is left alone.
	"""
	buckets = {key: [] for key, _ in TO_PLAN_GROUPS}
	for chip in chips or []:
		key = to_plan_bucket(chip.get("due_date"), as_of)
		chip = dict(chip)
		chip["bucket"] = key
		chip["days_late"] = days_late(chip.get("due_date"), as_of)
		buckets[key].append(chip)

	return [
		{"key": key, "label": label, "chips": buckets[key], "count": len(buckets[key])}
		for key, label in TO_PLAN_GROUPS
		if buckets[key]
	]


# --------------------------------------------------------------------------
# stage roll-up
# --------------------------------------------------------------------------

# ⛔ THE RULE THIS WHOLE SECTION EXISTS TO KEEP: never add across units.
#
# Computer Paper printing is measured in KG, per part - two parts is two
# machine runs. Collation and Pack are counted in CARTONS, which is also the
# unit the order is placed in. There is no written-down kg-to-carton factor and
# guessing one would make every stage report quietly wrong.
#
# So a stage reports its own totals PER UNIT, and a flow between two stages is
# only offered when both sides are counted the same way.

def stage_totals(rows):
	"""What a set of rows adds up to, kept apart by unit.

	Returns {"pcs": 1031.0, ...}. A row with no actual quantity contributes
	nothing - a quantity nobody entered is not zero.
	"""
	totals = {}
	for row in rows or []:
		quantity = row.get("actual_quantity")
		if quantity in (None, ""):
			continue
		unit = (row.get("uom") or "").strip() or "—"
		totals[unit] = totals.get(unit, 0.0) + float(quantity)
	return totals


def roll_up_stages(rows, stage_of_machine, position_of_stage=None):
	"""One job card's board rows, gathered into the stages they belong to.

	`rows` are every production row stamped with that job card, across every
	day. `stage_of_machine` maps a machine name to its Workstation Type. A
	machine with no stage yet - Monobox, the planning areas - is NOT dropped:
	it comes back under a `None` stage so the screen can say "recorded, not yet
	assigned to a stage" rather than silently losing the work.
	"""
	positions = position_of_stage or {}
	buckets = {}
	for row in rows or []:
		stage = stage_of_machine.get(row.get("machine"))
		bucket = buckets.setdefault(stage, {"stage": stage, "rows": [], "machines": []})
		bucket["rows"].append(row)
		machine = row.get("machine")
		if machine and machine not in bucket["machines"]:
			bucket["machines"].append(machine)

	out = []
	for stage, bucket in buckets.items():
		bucket_rows = bucket["rows"]
		out.append({
			"stage": stage,
			"position": positions.get(stage) if stage else None,
			"machines": bucket["machines"],
			"totals": stage_totals(bucket_rows),
			"entries": len(bucket_rows),
			"status": stage_status(bucket_rows),
			"days": sorted({r.get("production_date") for r in bucket_rows if r.get("production_date")}),
		})

	# Unstaged work sorts last: it is a gap to close, not a step in the route.
	out.sort(key=lambda s: (s["position"] is None, s["position"] or 0, s["stage"] or ""))
	return out


def stage_status(rows):
	"""One word for how a stage is going, from the rows that make it up.

	Completed only when every row is - a stage with one machine finished and
	another still running has not finished.
	"""
	statuses = {(row.get("status") or "Planned") for row in rows or []}
	if not statuses:
		return "Not Started"
	if statuses == {"Completed"}:
		return "Completed"
	if "Running" in statuses:
		return "Running"
	if "Paused" in statuses:
		return "Paused"
	if "Carried Forward" in statuses:
		return "Carried Forward"
	if statuses == {"Planned"}:
		return "Planned"
	return "Not Started"


def stage_flow(stages):
	"""What is sitting between one stage and the next, where that is knowable.

	Only offered when both stages carry the SAME unit - otherwise the honest
	answer is that the two numbers do not compare, and the caller is told so
	rather than handed a subtraction that means nothing.
	"""
	flows = []
	staged = [s for s in stages if s["stage"]]
	for upstream, downstream in zip(staged, staged[1:]):
		shared = set(upstream["totals"]) & set(downstream["totals"])
		if not shared:
			flows.append({
				"from": upstream["stage"],
				"to": downstream["stage"],
				"comparable": False,
				"reason": "counted differently",
			})
			continue
		for unit in sorted(shared):
			flows.append({
				"from": upstream["stage"],
				"to": downstream["stage"],
				"comparable": True,
				"uom": unit,
				"waiting": round(upstream["totals"][unit] - downstream["totals"][unit], 4),
			})
	return flows


def stage_percent(total, ordered_quantity):
	"""Percent of the order a stage has done, or None when it cannot be said.

	Needs an order quantity AND the stage counted in the order's own unit; the
	caller decides that, because only it knows what the order was placed in.
	"""
	if not ordered_quantity or ordered_quantity <= 0 or total is None:
		return None
	return max(0, min(100, round((float(total) / float(ordered_quantity)) * 100)))
# planning a job across its stations
# --------------------------------------------------------------------------

# Which stages run once per PART rather than once per job.
#
# Computer Paper prints each part on its own press - the run log for
# JC-CPT-2026-00062 shows Part 2 (CF Yellow) on Miyakoshi 01 and Part 1
# (CB White) on Miyakoshi 3, the same day. Collation is where the parts become
# one set again, so everything from there on is a single line.
SPLIT_BY_PART = {"Printing", "Reel to Reel Printing", "Sheet to Sheet Printing"}


def part_label(part):
	"""How the floor says a part: "Part 2 · CF · Yellow · 55gsm".

	Built from whatever the spec actually has - a part with no paper type or no
	gsm still gets a usable label rather than a string full of gaps.
	"""
	bits = []
	number = part.get("part_number")
	if number:
		bits.append("Part {0}".format(number))
	for key in ("paper_type", "colour"):
		value = (part.get(key) or "").strip()
		if value:
			bits.append(value)
	gsm = part.get("gsm")
	if gsm:
		bits.append("{0}gsm".format(gsm))
	return " · ".join(bits)


def plan_lines(route, parts=None, split_by_part=None):
	"""One line per station a job will pass through, parts expanded.

	`route` is the job's stages in order. A stage in `split_by_part` becomes one
	line per part; every other stage is a single line. A job with no parts
	recorded gets single lines throughout rather than none - a missing spec must
	not silently produce an empty plan.
	"""
	splits = SPLIT_BY_PART if split_by_part is None else split_by_part
	parts = [p for p in (parts or []) if p]

	lines = []
	for sequence, stage in enumerate(route or [], start=1):
		if stage in splits and parts:
			for part in parts:
				lines.append({
					"stage": stage,
					"sequence": sequence,
					"part_number": part.get("part_number"),
					"part_label": part_label(part),
				})
		else:
			lines.append({
				"stage": stage,
				"sequence": sequence,
				"part_number": None,
				"part_label": None,
			})
	return lines


def carry_forward_row(row, next_date):
	"""Tomorrow's row for work that did not finish today.

	The carried quantity becomes tomorrow's PLANNED quantity - that is the whole
	point: the morning board already knows what is owed and nobody re-types it.
	Returns None when there is nothing to carry, so the caller can run this over
	every row without checking first.
	"""
	carried = row.get("carried_quantity")
	try:
		carried = float(carried or 0)
	except (TypeError, ValueError):
		return None
	if carried <= 0:
		return None

	return {
		"production_date": next_date,
		"department": row.get("department"),
		"machine": row.get("machine"),
		"customer_name": row.get("customer_name"),
		"job_name": row.get("job_name"),
		"planned_quantity": carried,
		"uom": row.get("uom"),
		"status": "Planned",
		"production_job_card": row.get("production_job_card"),
		"job_card_instructions": row.get("job_card_instructions"),
		"part_number": row.get("part_number"),
		"part_label": row.get("part_label"),
		"notes": "Carried forward from {0}".format(
			row.get("production_date") or "the previous day"
		),
	}


def job_card_doctype(job_card):
	"""Which product line a job card number belongs to, by its naming series.

	The row stores `production_job_card` as plain Data - provenance, not a
	foreign key, so that a Job Card Tracking problem can never make a
	production row unsaveable. That leaves the number itself as the only clue
	to which doctype it came from, and the naming series is the clue:

	    JC-CPT-....  Computer Paper     JC-CORR-.... Carton
	    JC-MBX-....  Monobox

	`test_every_source_prefix_matches_its_doctype_naming_series` pins these
	against the doctype JSON, so a renamed series breaks a test rather than
	silently breaking every link on the board.
	"""
	name = (job_card or "").strip()
	if not name:
		return None
	for source in JOB_CARD_SOURCES:
		prefix = source.get("series_prefix")
		if prefix and name.startswith(prefix):
			return source["doctype"]
	return None


def job_card_route(job_card):
	"""The desk route for a job card number, or None if we cannot place it.

	Returned to the phone already built, so the screen never has to know how
	doctype names become URLs.
	"""
	doctype = job_card_doctype(job_card)
	if not doctype:
		return None
	slug = doctype.lower().replace(" ", "-")
	return "/app/{0}/{1}".format(slug, quote((job_card or "").strip()))


def job_card_chip(
	customer_name,
	job_name,
	job_card,
	due_date=None,
	doctype=None,
	department=None,
	quantity=None,
	instructions=None,
	as_of=None,
):
	"""The one job card as the phone needs it.

	`job_name` is shortened for display only; `job_card` is carried whole,
	because that is what gets stamped on the production row.
	"""
	name = (job_card or "").strip()
	match = re.match(r"^JC-[A-Z]+-\d{4}-(.+)$", name)
	return {
		"job_card": name,
		"ref": match.group(1) if match else name,
		"customer_name": (customer_name or "").strip(),
		"job_name": short_job_name(customer_name, job_name),
		"due_date": due_date,
		"doctype": doctype,
		"department": department,
		"quantity": quantity,
		"instructions": (instructions or "").strip() or None,
		"overdue": is_overdue(due_date, as_of),
	}


def is_overdue(due_date, as_of=None):
	"""A card is late once its due date has passed. No due date is not late.

	The floor reads this as a red chip, so it has to be quiet about bad data:
	a date it cannot parse is treated as no date rather than raised.
	"""
	if not due_date:
		return False
	parsed = _as_date(due_date)
	if not parsed:
		return False
	today_value = _as_date(as_of) or date.today()
	return parsed < today_value


def _as_date(value):
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = str(value or "").strip()[:10]
	if not text:
		return None
	try:
		return datetime.strptime(text, "%Y-%m-%d").date()
	except ValueError:
		return None
