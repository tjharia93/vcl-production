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


DOCTYPES = ("Job Card Carton", "Job Card Computer Paper")


def execute():
	for doctype in DOCTYPES:
		if not frappe.db.table_exists(doctype):
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
