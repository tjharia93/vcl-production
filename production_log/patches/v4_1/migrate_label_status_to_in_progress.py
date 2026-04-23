"""
Patch v4_1: Migrate Job Card Label status values to the new standardized vocabulary.

Job Card Label previously used status options: Draft / Submitted / Cancelled.
The standardized vocabulary is: Draft / In Progress / Completed / Cancelled.

This patch rewrites any existing `status = 'Submitted'` row to `status = 'In Progress'`
so that the new set_status() logic and the extended Select options stay consistent.

Idempotent — safe to re-run; the UPDATE becomes a no-op once values are migrated.
"""

import frappe


def execute():
	if not frappe.db.table_exists("Job Card Label"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabJob Card Label`
		SET status = 'In Progress'
		WHERE status = 'Submitted'
		"""
	)
	frappe.db.commit()
