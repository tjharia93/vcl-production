"""
Patch v3_0: Remove the production execution layer from the live site.

Drops all eight DocTypes introduced in v2_0 and removes the production-
tracking custom fields from the three job card DocTypes. The job card
DocTypes themselves and their native fields are untouched.

Safe to run multiple times (idempotent). Each operation checks for
existence before acting.
"""

import frappe


# ── 1. DocTypes to delete ────────────────────────────────────────────────────

# Delete children first so parent deletes don't block on FK constraints.
CHILD_DOCTYPES = [
    "Schedule Line",
    "Workstation Stage",
]

PARENT_DOCTYPES = [
    "Production Entry",
    "Daily Production Schedule",
    "Downtime Entry",
    "Downtime Reason",
    "Waste Reason",
    "Production Stage",
]


def _delete_doctype(name):
    if not frappe.db.exists("DocType", name):
        return
    try:
        frappe.delete_doc(
            "DocType", name,
            force=True,
            ignore_missing=True,
            ignore_permissions=True,
        )
    except Exception:
        frappe.db.delete("DocType", {"name": name})

    table_name = "tab" + name
    frappe.db.commit()
    frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table_name}`")


# ── 2. Custom fields to remove from job cards ────────────────────────────────

# These were added by patches/v2_0/setup_ppc_custom_fields.py
CUSTOM_FIELDS_TO_REMOVE = [
    # Section break + two tracking fields, on all three job cards
    ("Job Card Computer Paper", "custom_production_tracking_sb"),
    ("Job Card Computer Paper", "custom_production_status"),
    ("Job Card Computer Paper", "custom_current_stage"),
    ("Job Card Label",          "custom_production_tracking_sb"),
    ("Job Card Label",          "custom_production_status"),
    ("Job Card Label",          "custom_current_stage"),
    ("Job Card Carton",         "custom_production_tracking_sb"),
    ("Job Card Carton",         "custom_production_status"),
    ("Job Card Carton",         "custom_current_stage"),
    # Workstation Type: default stage linked to Production Stage (being deleted)
    ("Workstation Type",        "custom_default_stage"),
]


def _remove_custom_fields():
    for doctype, fieldname in CUSTOM_FIELDS_TO_REMOVE:
        cf_name = frappe.db.get_value(
            "Custom Field", {"dt": doctype, "fieldname": fieldname}
        )
        if cf_name:
            frappe.delete_doc(
                "Custom Field", cf_name,
                force=True,
                ignore_permissions=True,
            )

        # Also drop the column from the database table if it exists
        table = "tab" + doctype
        if frappe.db.table_exists(table):
            existing_cols = {
                row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")
            }
            if fieldname in existing_cols:
                frappe.db.commit()
                frappe.db.sql_ddl(
                    f"ALTER TABLE `{table}` DROP COLUMN `{fieldname}`"
                )


# ── 3. Pages and reports to clean up ────────────────────────────────────────

PAGES_TO_DELETE = ["daily-schedule-board"]
REPORTS_TO_DELETE = [
    "Daily Production Summary",
    "Job Progress",
    "Machine Utilization",
]


def _cleanup_pages_and_reports():
    for page in PAGES_TO_DELETE:
        if frappe.db.exists("Page", page):
            try:
                frappe.delete_doc(
                    "Page", page,
                    force=True,
                    ignore_permissions=True,
                )
            except Exception:
                frappe.db.delete("Page", {"name": page})

    for report in REPORTS_TO_DELETE:
        if frappe.db.exists("Report", report):
            try:
                frappe.delete_doc(
                    "Report", report,
                    force=True,
                    ignore_permissions=True,
                )
            except Exception:
                frappe.db.delete("Report", {"name": report})


# ── 4. Workspace shortcuts ───────────────────────────────────────────────────

WORKSPACE_LINK_TARGETS = [
    "Production Entry",
    "Daily Production Schedule",
    "Downtime Entry",
    "Production Stage",
    "Waste Reason",
    "Downtime Reason",
    "daily-schedule-board",
]


def _cleanup_workspace_links():
    for target in WORKSPACE_LINK_TARGETS:
        for child_dt in ("Workspace Shortcut", "Workspace Link"):
            if frappe.db.exists("DocType", child_dt):
                frappe.db.delete(child_dt, {"link_to": target})


# ── Main ─────────────────────────────────────────────────────────────────────

def execute():
    # 1. Remove custom fields first so DocType deletes don't leave orphan columns
    _remove_custom_fields()

    # 2. Delete child DocTypes
    for child in CHILD_DOCTYPES:
        _delete_doctype(child)

    # 3. Delete parent DocTypes
    for parent in PARENT_DOCTYPES:
        _delete_doctype(parent)

    # 4. Clean up pages, reports, workspace links
    _cleanup_pages_and_reports()
    _cleanup_workspace_links()

    # 5. Clear cache
    frappe.clear_cache()
    frappe.db.commit()
