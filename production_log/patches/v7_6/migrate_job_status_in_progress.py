"""
Patch v7_6: Migrate legacy job_status values to the widened Phase-1 enum.

Job Card Carton, Job Card Computer Paper, and Job Card Label previously allowed
`job_status = 'In Progress'`. The Phase-1 enum replaces that value with
`In Production`, so existing draft records with the legacy value must be
rewritten before their next save.

Idempotent - safe to re-run; each UPDATE only touches rows still holding the
legacy value and becomes a no-op once migrated.
"""

import frappe


DOCTYPES = (
	"Job Card Carton",
	"Job Card Computer Paper",
	"Job Card Label",
)


def execute():
	for doctype in DOCTYPES:
		if not frappe.db.table_exists(doctype):
			continue

		frappe.db.sql(
			f"""
			UPDATE `tab{doctype}`
			SET job_status = 'In Production'
			WHERE job_status = 'In Progress'
			"""
		)

	frappe.db.commit()
