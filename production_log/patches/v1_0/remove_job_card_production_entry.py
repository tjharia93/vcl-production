"""
Patch: Remove lingering references to the deleted Job Card Production Entry doctype.

The Job Card Production Entry child table was removed when the production
execution layer was stripped out, but installations that had it previously
still carry database records (DocType row, DB table, workspace shortcuts,
custom fields) that cause a "Page job-card-production-entry not found" error
in the desk UI.

This patch cleans those leftovers. It is idempotent and safe to run when the
doctype was never installed.
"""

import frappe


DOCTYPE_NAME = "Job Card Production Entry"
TABLE_NAME = "tabJob Card Production Entry"


def execute():
    # 1. Remove the DocType record (and its database table) if it still exists.
    if frappe.db.exists("DocType", DOCTYPE_NAME):
        try:
            frappe.delete_doc(
                "DocType",
                DOCTYPE_NAME,
                force=True,
                ignore_missing=True,
                ignore_permissions=True,
            )
        except Exception:
            # Fall back to a raw delete if the doctype class can't be loaded
            # (the python module no longer ships with the app).
            frappe.db.delete("DocType", {"name": DOCTYPE_NAME})

    # 2. Make sure the backing table is gone even if the DocType row was
    #    already deleted in an earlier migration attempt.
    frappe.db.sql(f"DROP TABLE IF EXISTS `{TABLE_NAME}`")

    # 3. Clean up any workspace shortcuts / links still pointing at the doctype
    #    so the sidebar and workspace pages don't try to route to it.
    for child_dt in ("Workspace Shortcut", "Workspace Link"):
        if frappe.db.exists("DocType", child_dt):
            frappe.db.delete(child_dt, {"link_to": DOCTYPE_NAME})

    # 4. Drop any Custom Fields or Property Setters that targeted the doctype.
    frappe.db.delete("Custom Field", {"dt": DOCTYPE_NAME})
    frappe.db.delete("Property Setter", {"doc_type": DOCTYPE_NAME})

    # 5. Clear cached metadata so the desk stops serving the old page.
    frappe.clear_cache()
    frappe.db.commit()
