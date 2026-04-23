"""
Patch v4_0: Backfill `job_status = 'Open'` on existing job cards.

The new `job_status` field defaults to "Open" for new records, but
existing submitted job cards will have NULL until they are touched.
Set them to "Open" so the Production Planner filter
(`job_status NOT IN ('Completed', 'Closed')`) includes them.

Idempotent — only updates rows where job_status is NULL or empty.
"""

import frappe


JOB_CARD_DOCTYPES = (
	"Job Card Computer Paper",
	"Job Card Label",
	"Job Card Carton",
)


def execute():
	for doctype in JOB_CARD_DOCTYPES:
		table = f"tab{doctype}"
		if not frappe.db.table_exists(doctype):
			continue
		if not frappe.db.has_column(doctype, "job_status"):
			continue

		frappe.db.sql(
			f"""
			UPDATE `{table}`
			SET job_status = 'Open'
			WHERE job_status IS NULL OR job_status = ''
			"""
		)

	frappe.db.commit()
