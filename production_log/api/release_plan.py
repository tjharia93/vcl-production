"""S2 — Daily Release Plan generator.

Generates an A4 portrait PDF listing every open Job Card for the selected
product line, sorted by due date with readiness flags + sequence# column.

Per White Paper v4 §4.2 and §11 (Plates Annex):
  Readiness signals = 5
    plate_ready
    material_in_stock
    customer_hold
    artwork_approved  (Designers Tracker · S4+)
    plates_lead_time_clear (Designers Tracker · S4+)

Per Sprint-2 paper §C1 sort logic:
  Overdue + Plate Ready  → top
  Due today + Plate Ready
  Due soon + Plate Ready
  Plate Pending          → shown but un-sequenced
  Plate Issue            → flagged for escalation

Usage:
  /api/method/production_log.api.release_plan.generate_release_plan
    ?product_line=Corrugation%20and%20Carton%20Department
    &date=2026-05-20
"""

import os
from datetime import datetime, date as date_cls

import frappe
from frappe import _


# Map product_line stored string → JCL doctype name.
# Per patch_v5_5 canonical taxonomy.
PRODUCT_LINE_JCL = {
	"Corrugation and Carton Department": "Job Card Carton",
	"Computer Paper":                    "Job Card Computer Paper",
	"ETR":                               "Job Card ETR",
	"Self Adhesive Label":               "Job Card Label",
	# Future (S5+): R2R, Mono Boxes, General Stationery and Exercise Book, Trading
}

# Statuses considered "open" for Release Plan inclusion.
# Excludes Completed/Closed/Cancelled. Includes 8-state v6_0 enum subset.
OPEN_STATUSES = ("Open", "Planned", "In Progress", "In Production", "Packing Pending", "On Hold")


@frappe.whitelist()
def generate_release_plan(product_line, date=None):
	"""Render the Release Plan PDF for one product line on one date.

	Returns:
		Frappe response object — PDF binary attached to the response.
	"""
	if product_line not in PRODUCT_LINE_JCL:
		frappe.throw(_("Unknown product_line: {0}").format(product_line))

	target_date = _parse_date(date) if date else frappe.utils.today()
	jcl_doctype = PRODUCT_LINE_JCL[product_line]

	if not frappe.db.exists("DocType", jcl_doctype):
		frappe.throw(_("Job Card doctype not yet built for {0}").format(product_line))

	jobs = _query_open_jobs(jcl_doctype, target_date)
	jobs_sorted = _sort_for_release(jobs, target_date)

	html = _render_release_plan_html(
		product_line=product_line,
		target_date=target_date,
		jobs=jobs_sorted,
	)

	pdf_bytes = frappe.utils.pdf.get_pdf(html)
	frappe.local.response.filename = (
		f"release-plan-{product_line.replace(' ', '_')}-{target_date}.pdf"
	)
	frappe.local.response.filecontent = pdf_bytes
	frappe.local.response.type = "download"
	return


# ──────────────────────────────────────────────────────────────────────────
# internal helpers
# ──────────────────────────────────────────────────────────────────────────


def _parse_date(value):
	if isinstance(value, (date_cls, datetime)):
		return value
	return frappe.utils.getdate(value)


def _query_open_jobs(jcl_doctype, target_date):
	"""Pull all open JCLs with the readiness signals we know about.

	Some fields (artwork_approved, plates_lead_time_clear) are added in S4
	via Designers Tracker linkage; until then they default to None.
	"""
	fields = [
		"name",
		"customer_name",
		"job_description",
		"quantity_ordered",
		"due_date",
		"job_status",
		"creation",
	]
	# Optional fields — only request if the doctype has them
	meta = frappe.get_meta(jcl_doctype)
	meta_fields = {f.fieldname for f in meta.fields}
	for opt in ("print_type", "plate_ready", "material_in_stock", "customer_hold"):
		if opt in meta_fields:
			fields.append(opt)

	return frappe.db.get_all(
		jcl_doctype,
		filters={
			"docstatus": 1,
			"job_status": ("in", OPEN_STATUSES),
		},
		fields=fields,
		order_by="due_date asc, creation asc",
		limit=500,
	)


def _sort_for_release(jobs, target_date):
	"""Return jobs in the order they should appear on the Release Plan.

	Bucket 1: Overdue + plate_ready
	Bucket 2: Due today + plate_ready
	Bucket 3: Due soon + plate_ready
	Bucket 4: Plate Pending (no sequence# suggested)
	Bucket 5: Plate Issue (flag for escalation)
	"""
	out = []
	for j in jobs:
		j["_bucket"] = _bucket_for(j, target_date)
		j["_age_days"] = (target_date - frappe.utils.getdate(j.due_date)).days if j.due_date else None
		out.append(j)
	out.sort(key=lambda j: (j["_bucket"], j["due_date"] or "9999-12-31"))
	return out


def _bucket_for(job, target_date):
	plate_ready = bool(job.get("plate_ready"))
	customer_hold = bool(job.get("customer_hold"))
	if customer_hold:
		return 5  # held — flag
	if not plate_ready:
		return 4  # awaiting plate
	if job.due_date and frappe.utils.getdate(job.due_date) < target_date:
		return 1  # overdue
	if job.due_date and frappe.utils.getdate(job.due_date) == target_date:
		return 2  # due today
	return 3      # due soon


def _render_release_plan_html(product_line, target_date, jobs):
	template_path = os.path.join(
		frappe.get_app_path("production_log"),
		"templates",
		"includes",
		"release_plan.html",
	)
	with open(template_path) as f:
		template_src = f.read()

	# Pre-compute summary counters
	summary = {
		"total":      len(jobs),
		"overdue":    sum(1 for j in jobs if j["_bucket"] == 1),
		"due_today":  sum(1 for j in jobs if j["_bucket"] == 2),
		"due_soon":   sum(1 for j in jobs if j["_bucket"] == 3),
		"plate_pending": sum(1 for j in jobs if j["_bucket"] == 4),
		"on_hold":    sum(1 for j in jobs if j["_bucket"] == 5),
	}

	return frappe.render_template(template_src, {
		"product_line": product_line,
		"target_date":  target_date,
		"jobs":         jobs,
		"summary":      summary,
	})
