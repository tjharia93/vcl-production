"""Shared helpers for the Job Card Tracking module."""

import frappe
from frappe import _

ALLOWED_DOCTYPES = {
	"Job Card Computer Paper",
	"Job Card Label",
	"Job Card Carton",
}

ALLOWED_STATUSES = {"Open", "In Progress", "Completed", "Closed"}


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
	if status == "In Progress" and not doc.get("production_started_date"):
		if hasattr(doc, "production_started_date"):
			doc.db_set("production_started_date", today, update_modified=False)

	doc.add_comment("Info", _("Job status changed: {0} → {1}").format(previous, status))
	return status
