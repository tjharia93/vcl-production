"""Report text, day summary and exception detection for VCL Production Lite.

Everything in this module is deliberately free of Frappe imports. It works on
plain dicts, so the wording of a report and the rules for what counts as a
missing update can be read - and tested - without a bench, a site or a
database. `api.py` is the thin layer that turns Frappe documents into the
dicts these functions expect.
"""

import re
from datetime import date, datetime

DEFAULT_DEPARTMENTS = ["Computer", "Offset", "Carton", "Labels", "Monobox"]
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
		"department": "Computer",
		"customer_field": "customer",
		"instructions_field": "order_comments",
	},
	{
		"doctype": "Job Card Carton",
		"department": "Carton",
		"customer_field": "customer_name",
		"instructions_field": "special_instructions",
	},
	{
		"doctype": "Job Card Monobox",
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
