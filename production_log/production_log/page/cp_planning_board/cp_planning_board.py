"""Server-side API for the Production Planner page."""

import json

import frappe
from frappe import _


# Workstation Types where one workstation can be tagged for more than one
# product line (e.g. shared presses). Used to scope conflict detection.
# Verbatim ERPNext Workstation Type name on the VCL site — not the
# shorthand "Printing" from the handover/prototype.
SHARED_WORKSTATION_TYPES = ["Reel to Reel Printing"]

# Product lines that ever appear in the planner UI. `All` is a passthrough
# tag — any workstation tagged `All` is reachable from every dept.
PLANNER_PRODUCT_LINES = ["Computer Paper", "ETR / Thermal"]

# Left-panel Job Card doctype per planner dept. Carton is intentionally
# absent — no carton workstations are in Phase 1 scope, so the panel has
# nothing to render for it. The entry modal's Job Card Type dropdown
# still offers all three for manual reassignment.
JOB_CARD_DOCTYPE_BY_PRODUCT_LINE = {
	"Computer Paper": "Job Card Computer Paper",
	"ETR / Thermal": "Job Card Label",
}


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_workstation_columns(product_line=None):
	"""
	Return the ordered list of Workstation Types + their Workstations that
	the board should render as columns for the given product line.

	Each row:
	    {
	        "workstation_type": "Printing",
	        "product_line_on_type": "All",
	        "workstation": "Miyakoshi 01",
	        "is_shared": 1
	    }

	`product_line` may be None (returns all lines) or one of
	`Computer Paper` / `ETR / Thermal`. A workstation matches if it has a
	`custom_product_line_tags` row for that product_line or for `All`.
	"""
	conditions = []
	values = {}

	if product_line:
		conditions.append("(tag.product_line = %(pl)s OR tag.product_line = 'All')")
		values["pl"] = product_line

	where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT
			ws.workstation_type AS workstation_type,
			wt.custom_product_line AS product_line_on_type,
			ws.name AS workstation
		FROM `tabWorkstation` ws
		INNER JOIN `tabWorkstation Type` wt
			ON wt.name = ws.workstation_type
		INNER JOIN `tabWorkstation Product Line Tag` tag
			ON tag.parent = ws.name
			AND tag.parenttype = 'Workstation'
			AND tag.parentfield = 'custom_product_line_tags'
		{where_clause}
		ORDER BY wt.name, ws.name
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		row["is_shared"] = 1 if row["workstation_type"] in SHARED_WORKSTATION_TYPES else 0

	return rows


# ---------------------------------------------------------------------------
# Job Card list (left panel)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_job_cards(product_line, search=None, limit=200):
	"""
	Return recent, non-cancelled Job Cards for the planner's left panel.

	Picks the Job Card doctype from `JOB_CARD_DOCTYPE_BY_PRODUCT_LINE`;
	returns `[]` if the caller passes an unknown product line. The Select
	picker in the entry modal still offers every Job Card doctype for
	manual reassignment — this method only feeds the browse panel.

	Each row: `name`, `customer`, `customer_product_spec`, `docstatus`,
	`creation`, plus a derived `badge` (`"active"` when submitted, else
	`"open"`) and `doctype` so the client can route Add Entry pre-fill
	without another round-trip.
	"""
	doctype = JOB_CARD_DOCTYPE_BY_PRODUCT_LINE.get(product_line)
	if not doctype:
		return []

	try:
		limit = max(1, min(int(limit), 500))
	except (TypeError, ValueError):
		limit = 200

	filters = {"docstatus": ["!=", 2]}
	or_filters = None
	if search:
		pattern = f"%{search}%"
		or_filters = {
			"name": ["like", pattern],
			"customer": ["like", pattern],
			"customer_product_spec": ["like", pattern],
		}

	rows = frappe.get_all(
		doctype,
		fields=["name", "customer", "customer_product_spec", "docstatus", "creation"],
		filters=filters,
		or_filters=or_filters,
		order_by="creation desc",
		limit_page_length=limit,
	)

	for row in rows:
		row["doctype"] = doctype
		row["badge"] = "active" if row.get("docstatus") == 1 else "open"

	return rows


# ---------------------------------------------------------------------------
# Entries (plan + actual)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_schedule_entries(date_from, date_to, product_line=None):
	"""
	Return every PSL and PE that falls in the date window. `product_line`
	filters both collections; pass None to get everything.
	"""
	filters = {"date": ["between", [date_from, date_to]]}
	if product_line:
		filters["product_line"] = product_line

	psl_fields = [
		"name",
		"job_card_doctype",
		"job_card",
		"is_manual",
		"description",
		"product_line",
		"status",
		"workstation_type",
		"workstation",
		"date",
		"shift",
		"operator",
		"planned_reels",
		"planned_sheets",
		"planned_qty",
		"notes",
	]

	pe_fields = psl_fields + [
		"schedule_line",
		"actual_sheets",
		"actual_qty",
		"docstatus",
	]

	schedule = frappe.get_all(
		"Production Schedule Line",
		fields=psl_fields,
		filters=filters,
		order_by="date, workstation_type, workstation",
	)

	actuals = frappe.get_all(
		"Production Entry",
		fields=pe_fields,
		filters={**filters, "docstatus": ["!=", 2]},
		order_by="date, workstation_type, workstation",
	)

	return {"schedule": schedule, "actuals": actuals}


# ---------------------------------------------------------------------------
# Save (PSL)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def save_schedule_entry(entry):
	"""
	Create or update a Production Schedule Line. Stamps `product_line` from
	the client (dept tab) unconditionally. Callers pass a JSON-encoded
	string or a dict.
	"""
	entry = _parse_entry(entry)

	if not (entry.get("product_line") or "").strip():
		frappe.throw(_("Product Line is required."))

	name = entry.pop("name", None)
	if name:
		doc = frappe.get_doc("Production Schedule Line", name)
		doc.update(entry)
	else:
		doc = frappe.new_doc("Production Schedule Line")
		doc.update(entry)

	doc.save()
	frappe.db.commit()
	return doc.name


# ---------------------------------------------------------------------------
# Save (PE)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def save_production_entry(entry):
	"""
	Create or update a Production Entry. Mirrors `save_schedule_entry` but
	never auto-submits — the user/role controls submission via the PE form
	or an explicit submit action. Optionally links the PE back to its PSL
	via the `schedule_line` field.
	"""
	entry = _parse_entry(entry)

	if not (entry.get("product_line") or "").strip():
		frappe.throw(_("Product Line is required."))

	name = entry.pop("name", None)
	if name:
		doc = frappe.get_doc("Production Entry", name)
		if doc.docstatus == 1:
			frappe.throw(_("Submitted Production Entries cannot be edited."))
		doc.update(entry)
	else:
		doc = frappe.new_doc("Production Entry")
		doc.update(entry)

	doc.save()
	frappe.db.commit()
	return doc.name


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_machine_conflicts(date_from, date_to):
	"""
	Return one row per (workstation, date) that has 2+ PSLs on shared
	workstation types across different product lines. Each row carries the
	list of PSL names involved so the client can tag them.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			psl.workstation AS workstation,
			psl.workstation_type AS workstation_type,
			psl.date AS date,
			GROUP_CONCAT(DISTINCT psl.product_line ORDER BY psl.product_line) AS product_lines,
			GROUP_CONCAT(psl.name) AS psl_names
		FROM `tabProduction Schedule Line` psl
		WHERE psl.workstation_type IN %(shared)s
			AND psl.docstatus < 2
			AND psl.date BETWEEN %(d_from)s AND %(d_to)s
		GROUP BY psl.workstation, psl.workstation_type, psl.date
		HAVING COUNT(DISTINCT psl.product_line) > 1
		""",
		{
			"shared": tuple(SHARED_WORKSTATION_TYPES) or ("",),
			"d_from": date_from,
			"d_to": date_to,
		},
		as_dict=True,
	)

	for row in rows:
		row["product_lines"] = (row.get("product_lines") or "").split(",")
		row["psl_names"] = (row.get("psl_names") or "").split(",")

	return rows


# ---------------------------------------------------------------------------
# Daily schedule (for the Print Daily flow)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_daily_schedule(date, depts=None):
	"""
	Return a dict keyed by product line → list of PSL rows to render on the
	daily print-out. `depts` is an optional JSON list like
	`["Computer Paper", "ETR / Thermal"]`; omit for all planner depts.
	"""
	if isinstance(depts, str):
		try:
			depts = json.loads(depts)
		except ValueError:
			depts = [d.strip() for d in depts.split(",") if d.strip()]

	if not depts:
		depts = PLANNER_PRODUCT_LINES

	fields = [
		"name",
		"job_card_doctype",
		"job_card",
		"is_manual",
		"description",
		"product_line",
		"status",
		"workstation_type",
		"workstation",
		"shift",
		"operator",
		"planned_reels",
		"planned_sheets",
		"planned_qty",
		"notes",
	]

	result = {}
	for dept in depts:
		rows = frappe.get_all(
			"Production Schedule Line",
			fields=fields,
			filters={"date": date, "product_line": dept, "status": ["!=", "Cancelled"]},
			order_by="workstation_type, workstation, shift",
		)
		result[dept] = rows

	return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_entry(entry):
	if isinstance(entry, str):
		entry = json.loads(entry)
	elif isinstance(entry, dict):
		entry = dict(entry)
	else:
		frappe.throw(_("Invalid entry payload."))
	return entry
