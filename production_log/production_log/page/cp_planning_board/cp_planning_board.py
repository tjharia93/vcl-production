"""Server-side API for the Production Planner page."""

import json

import frappe
from frappe import _


# Workstation Types where one workstation can be tagged for more than one
# product line (e.g. shared presses). Used to scope conflict detection.
# Verbatim ERPNext Workstation Type name on the VCL site — not the
# shorthand "Printing" from the handover/prototype.
SHARED_WORKSTATION_TYPES = ["Reel to Reel Printing"]

# Product lines that appear in the planner UI. After patch_v5_5 the
# `All` synthetic tag is gone — every WT carries explicit per-PL rows.
# Order here is the dept-tab order the client renders. `Trading` is in
# the Select option list but skipped here because it has no operations
# stages; admins can add it back if a Trading-bound WT shows up.
PLANNER_PRODUCT_LINES = [
	"Computer Paper",
	"ETR",
	"Self Adhesive Label",
	"General Stationery and Exercise Book",
	"Mono Boxes",
	"Corrugation and Carton Department",
	"R2R",
]

# Left-panel Job Card doctype per planner dept. Only product lines with
# a dedicated Job Card doctype appear here — everything else falls
# through `.get()` → None → `get_job_cards` returns [] → the left panel
# renders its empty state. The `Job Card Label` doctype keeps its name
# under the rename — only the product-line key changes.
JOB_CARD_DOCTYPE_BY_PRODUCT_LINE = {
	"Computer Paper": "Job Card Computer Paper",
	"ETR": "Job Card ETR",
	"Self Adhesive Label": "Job Card Label",
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
	        "stage_position": 20,
	        "workstation": "Miyakoshi 01",
	        "is_shared": 1
	    }

	`product_line` may be None (returns all lines) or one of the values
	in `PLANNER_PRODUCT_LINES`. A workstation matches when its
	Workstation Type carries a `custom_product_line_tags` row for that
	product_line, or for the synthetic `All` tag. Tagging moved from
	Workstation to Workstation Type in patch_v5_2; v5_5 keeps the
	`All` match in place so admins can migrate WTs from `All` to
	explicit per-PL rows manually without losing planner coverage in
	the meantime.
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
			wt.custom_stage_position AS stage_position,
			ws.name AS workstation
		FROM `tabWorkstation` ws
		INNER JOIN `tabWorkstation Type` wt
			ON wt.name = ws.workstation_type
		INNER JOIN `tabWorkstation Product Line Tag` tag
			ON tag.parent = wt.name
			AND tag.parenttype = 'Workstation Type'
			AND tag.parentfield = 'custom_product_line_tags'
		{where_clause}
		ORDER BY wt.custom_stage_position ASC, wt.name ASC, ws.name ASC
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
		_enrich_job_card_details(rows)
		result[dept] = rows

	return result


def _enrich_job_card_details(rows):
	"""
	Attach `customer` and `customer_product_spec` to each row whose
	`job_card_doctype` + `job_card` resolves. The printed daily schedule
	renders the job name underneath the JC id, so a handoff to the floor
	reads as "JC-CPT-2026-00014 / Excel Chemicals Ltd · CPT-SPEC-00024"
	instead of just the opaque id.

	Cached per (doctype, name) so a schedule with many rows pointing at
	the same job card only hits the DB once. Carton's customer field is
	named `customer_name`, not `customer` — branch accordingly.
	"""
	cache = {}
	for row in rows:
		row["customer"] = ""
		row["customer_product_spec"] = ""
		dt = (row.get("job_card_doctype") or "").strip()
		name = (row.get("job_card") or "").strip()
		if not dt or not name:
			continue
		key = (dt, name)
		if key not in cache:
			customer_field = "customer_name" if dt == "Job Card Carton" else "customer"
			try:
				vals = frappe.db.get_value(
					dt,
					name,
					[customer_field, "customer_product_spec"],
					as_dict=True,
				) or {}
			except Exception:
				vals = {}
			cache[key] = {
				"customer": vals.get(customer_field) or "",
				"customer_product_spec": vals.get("customer_product_spec") or "",
			}
		row["customer"] = cache[key]["customer"]
		row["customer_product_spec"] = cache[key]["customer_product_spec"]


# ---------------------------------------------------------------------------
# Plan vs Actuals (for the Print v2 flow)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_plan_vs_actuals(date, depts=None):
	"""Return PSL plan rows for `date` joined with submitted PE actuals.

	One row per PSL (the spine). Submitted Production Entries pointing
	at the same `(workstation_type, workstation, job_card, date)` as
	the PSL are summed into `actual_qty_total` / `actual_sheets_total`,
	and a `variance_pct` is computed against the planned qty so the
	print template can colour-code without re-doing the math.

	`depts` is an optional JSON list (same shape as `get_daily_schedule`).
	"""
	if isinstance(depts, str):
		try:
			depts = json.loads(depts)
		except ValueError:
			depts = [d.strip() for d in depts.split(",") if d.strip()]

	if not depts:
		depts = PLANNER_PRODUCT_LINES

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
		"shift",
		"operator",
		"planned_reels",
		"planned_sheets",
		"planned_qty",
		"notes",
	]

	# Aggregate submitted PE rows up-front, keyed on the same tuple the
	# PSL identifies. `is_manual` PSLs match on description+stage rather
	# than job_card.
	pe_rows = frappe.db.sql(
		"""
		SELECT
			workstation_type,
			workstation,
			COALESCE(job_card, '') AS job_card,
			COALESCE(description, '') AS description,
			COALESCE(is_manual, 0) AS is_manual,
			SUM(COALESCE(actual_qty, 0))    AS actual_qty_total,
			SUM(COALESCE(actual_sheets, 0)) AS actual_sheets_total
		FROM `tabProduction Entry`
		WHERE date = %(date)s
		  AND docstatus = 1
		  AND product_line IN %(depts)s
		GROUP BY workstation_type, workstation, job_card, description, is_manual
		""",
		{"date": date, "depts": tuple(depts) or ("",)},
		as_dict=True,
	)

	pe_index = {}
	for row in pe_rows:
		key = (
			row["workstation_type"] or "",
			row["workstation"] or "",
			row["job_card"] or "",
			row["description"] or "" if row["is_manual"] else "",
		)
		pe_index[key] = row

	result = {}
	for dept in depts:
		psls = frappe.get_all(
			"Production Schedule Line",
			fields=psl_fields,
			filters={"date": date, "product_line": dept, "status": ["!=", "Cancelled"]},
			order_by="workstation_type, workstation, shift",
		)
		_enrich_job_card_details(psls)

		for psl in psls:
			key = (
				psl.get("workstation_type") or "",
				psl.get("workstation") or "",
				psl.get("job_card") or "",
				psl.get("description") or "" if psl.get("is_manual") else "",
			)
			actual = pe_index.get(key, {})
			actual_qty = float(actual.get("actual_qty_total") or 0)
			actual_sheets = float(actual.get("actual_sheets_total") or 0)

			# Planned baseline: prefer planned_sheets when the WT tracks
			# sheets (R2R press, Ruling, Sheeting), else fall back to
			# planned_qty. The client's UOM map decides which actual
			# value to display, but we expose both totals.
			planned_sheets = float(psl.get("planned_sheets") or 0)
			planned_qty = float(psl.get("planned_qty") or 0)
			if planned_sheets > 0 and actual_sheets > 0:
				baseline_planned, baseline_actual = planned_sheets, actual_sheets
			elif planned_qty > 0 and actual_qty > 0:
				baseline_planned, baseline_actual = planned_qty, actual_qty
			elif planned_sheets > 0:
				baseline_planned, baseline_actual = planned_sheets, actual_sheets
			else:
				baseline_planned, baseline_actual = planned_qty, actual_qty

			variance_pct = None
			if baseline_planned > 0:
				variance_pct = round(
					(baseline_actual - baseline_planned) / baseline_planned * 100.0, 1
				)

			psl["actual_qty_total"] = actual_qty
			psl["actual_sheets_total"] = actual_sheets
			psl["variance_pct"] = variance_pct

		result[dept] = psls

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
