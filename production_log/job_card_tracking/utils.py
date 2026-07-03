"""Shared helpers for the Job Card Tracking module."""

import frappe
from frappe import _

ALLOWED_DOCTYPES = {
	"Job Card Computer Paper",
	"Job Card Label",
	"Job Card Carton",
}

# Expanded in v7_0 patch (May 2026) to match the 8-value enum live on
# JC Computer Paper since v6_0 (Property Setter). Older 4-value callers
# remain backward compatible because the old values are a subset.
ALLOWED_STATUSES = {
	"Open",
	"Planned",
	"In Progress",       # legacy synonym retained for back-compat
	"In Production",     # canonical mid-state per v6_0 PPC v2
	"Packing Pending",
	"Completed",
	"Closed",
	"On Hold",
	"Cancelled",
}

ALLOWED_STAGE_STATUSES = {
	"Not Started",
	"Ready",
	"In Progress",
	"Done",
	"Blocked",
	"Skipped",
}

STAGE_TRACKING_DOCTYPES = {
	"Job Card Computer Paper",
}


@frappe.whitelist()
def set_job_status(doctype, name, status):
	"""Update the `job_status` field on a submitted job card.

	The Production Planner filters out job cards whose `job_status` is
	`Completed` or `Closed`, so this is the entry point used by the
	Close / Reopen buttons on the job card form.
	"""
	if doctype not in ALLOWED_DOCTYPES:
		frappe.throw(_("Job status can only be set on a job card."))

	if status not in ALLOWED_STATUSES:
		frappe.throw(_("Invalid job status: {0}").format(status))

	doc = frappe.get_doc(doctype, name)

	if doc.docstatus != 1:
		frappe.throw(_("Job status can only be changed on submitted job cards."))

	doc.check_permission("submit")

	previous = doc.get("job_status") or "Open"
	doc.db_set("job_status", status, update_modified=True)

	today = frappe.utils.today()
	if status in ("Completed", "Closed") and not doc.get("production_completed_date"):
		if hasattr(doc, "production_completed_date"):
			doc.db_set("production_completed_date", today, update_modified=False)
	if status in ("In Progress", "In Production") and not doc.get("production_started_date"):
		if hasattr(doc, "production_started_date"):
			doc.db_set("production_started_date", today, update_modified=False)

	doc.add_comment("Info", _("Job status changed: {0} → {1}").format(previous, status))
	return status


@frappe.whitelist()
def set_stage_status(doctype, name, stage_row, status):
	"""Set one Computer Paper production stage row status.

	`stage_row` may be either the child row `name` or its visible grid `idx`.
	"""
	if doctype not in STAGE_TRACKING_DOCTYPES:
		frappe.throw(_("Stage status can only be set on a Computer Paper job card."))

	if status not in ALLOWED_STAGE_STATUSES:
		frappe.throw(_("Invalid stage status: {0}").format(status))

	doc = frappe.get_doc(doctype, name)
	_check_stage_write_permission(doc)

	row = _get_stage_row(doc, stage_row)
	previous = row.stage_status or "Not Started"
	row.stage_status = status
	doc.save()

	doc.add_comment(
		"Info",
		_("Production stage {0} status changed: {1} → {2}").format(
			row.stage, previous, status
		),
	)
	return status


@frappe.whitelist()
def assign_stage_machine(doctype, name, stage_row, asset):
	"""Assign a Plant & Machinery Asset to one Computer Paper stage row.

	`stage_row` may be either the child row `name` or its visible grid `idx`.
	"""
	if doctype not in STAGE_TRACKING_DOCTYPES:
		frappe.throw(_("Stage machines can only be set on a Computer Paper job card."))

	if asset:
		_validate_plant_machinery_asset(asset)

	doc = frappe.get_doc(doctype, name)
	_check_stage_write_permission(doc)

	row = _get_stage_row(doc, stage_row)
	# Soft affinity only: Printing -> Miyakoshi 01/02/03; Collation/Numbering
	# -> Collator and Numbering 01. Do not hard-restrict beyond category.
	row.machine_asset = asset
	doc.save()

	doc.add_comment(
		"Info",
		_("Production stage {0} machine assigned: {1}").format(row.stage, asset or _("None")),
	)
	return asset


def _check_stage_write_permission(doc):
	if doc.docstatus == 1:
		doc.check_permission("submit")
	else:
		doc.check_permission("write")


def _get_stage_row(doc, stage_row):
	stage_row = str(stage_row)
	for row in doc.get("production_stages") or []:
		if row.name == stage_row or str(row.idx) == stage_row:
			return row

	frappe.throw(_("Production stage row not found: {0}").format(stage_row))


def _validate_plant_machinery_asset(asset):
	asset_category = frappe.db.get_value("Asset", asset, "asset_category")
	if asset_category != "Plant & Machinery":
		frappe.throw(
			_("Machine Asset must be in Asset Category 'Plant & Machinery'."),
			title=_("Invalid Machine Asset"),
		)
