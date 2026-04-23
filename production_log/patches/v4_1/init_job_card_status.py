"""
Patch v4_1: Initialise the new `status` field on existing Job Card Carton and
Job Card Computer Paper rows.

Before this release, neither doctype had a status field. After the JSON is synced
by bench migrate, the column will exist but every historical row will be NULL.
This patch backfills values so downstream filters, reports, and set_status()
logic behave consistently from day one:

  - docstatus == 0  →  status = 'Draft'
  - docstatus == 1  →  status = 'In Progress'
  - docstatus == 2  →  status = 'Cancelled'

Idempotent — only touches rows where status IS NULL or empty.
"""

import frappe


# (DocType name, snake-case module-relative folder name)
DOCTYPES = (
	("Job Card Carton",         "job_card_carton"),
	("Job Card Computer Paper", "job_card_computer_paper"),
)


def execute():
	# Reload the DocType JSON first so the newly-added `status` column is
	# present on the DB table before we UPDATE it. This runs in the
	# pre_model_sync phase where the schema sync hasn't yet applied our JSON.
	for _, folder in DOCTYPES:
		frappe.reload_doc("job_card_tracking", "doctype", folder)

	for doctype, _ in DOCTYPES:
		if not frappe.db.table_exists(doctype):
			continue
		if not frappe.db.has_column(doctype, "status"):
			# Defensive: if reload_doc didn't add the column for any reason,
			# skip rather than blow up. A later migrate will pick it up.
			continue

		table = f"tab{doctype}"

		frappe.db.sql(
			f"""
			UPDATE `{table}`
			SET status = 'Draft'
			WHERE (status IS NULL OR status = '')
			  AND docstatus = 0
			"""
		)
		frappe.db.sql(
			f"""
			UPDATE `{table}`
			SET status = 'In Progress'
			WHERE (status IS NULL OR status = '')
			  AND docstatus = 1
			"""
		)
		frappe.db.sql(
			f"""
			UPDATE `{table}`
			SET status = 'Cancelled'
			WHERE (status IS NULL OR status = '')
			  AND docstatus = 2
			"""
		)

	frappe.db.commit()
