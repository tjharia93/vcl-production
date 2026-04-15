"""
Patch: Remove the production execution / planning layer.

This patch hard-resets the production execution layer that was added in the
"Phase 1" iteration. It removes the Department Daily Plan parent doctype, its
child (Department Daily Plan Line), and strips the Production Control section
off Job Card Computer Paper and Job Card Label.

Goal: leave the app with only the basic master / job-card creation flow.
The execution / planning layer will be redesigned later as a clean restart.

Idempotent and safe to run multiple times.
"""

import frappe


PARENT_DOCTYPES = (
    "Department Daily Plan",
    # Historical names from earlier iterations of the execution layer.
    "Daily Production Plan",
    "Daily Production Actual",
    "Daily Production Log",
    "Production Entry",
)

CHILD_DOCTYPES = (
    "Department Daily Plan Line",
    # Historical child tables.
    "Daily Production Plan Line",
    "Daily Production Actual Line",
    "Production Actual Line",
    "Production Planning Line",
    "Job Card Production Entry",
)

# Production-tracking fields that lived on Job Card Computer Paper / Label
# during the execution-layer phase. They are dropped from the database here
# so bench migrate doesn't trip over orphan columns when the JSON definitions
# no longer declare them.
JOB_CARD_DOCTYPES = ("Job Card Computer Paper", "Job Card Label")
JOB_CARD_DROP_COLUMNS = (
    "production_status",
    "production_stage",
    "planned_for_date",
    "priority",
    "qty_completed",
    "qty_pending",
    "last_production_update",
    "completed_on",
    "hold_reason",
    "production_comments",
)

REPORT_NAMES = (
    "Daily Production Summary",
    "Incomplete Reels Tracker",
    "Operator Performance",
    "Production Summary by Station",
)

PRINT_FORMAT_NAMES = (
    "Daily Production Plan - Floor Sheet",
)

WORKSPACE_NAMES = (
    "Production Execution Control",
    "Production Management",
)


def _delete_doctype(name):
    if not frappe.db.exists("DocType", name):
        return

    try:
        frappe.delete_doc(
            "DocType",
            name,
            force=True,
            ignore_missing=True,
            ignore_permissions=True,
        )
    except Exception:
        # Fall back to a raw delete if the python class can't be loaded
        # (the module no longer ships with the app).
        frappe.db.delete("DocType", {"name": name})

    table_name = "tab" + name
    frappe.db.sql(f"DROP TABLE IF EXISTS `{table_name}`")


def _purge_workspace_links(target_name):
    for child_dt in ("Workspace Shortcut", "Workspace Link"):
        if frappe.db.exists("DocType", child_dt):
            frappe.db.delete(child_dt, {"link_to": target_name})


def _purge_custom_metadata(target_name):
    if frappe.db.exists("DocType", "Custom Field"):
        frappe.db.delete("Custom Field", {"dt": target_name})
    if frappe.db.exists("DocType", "Property Setter"):
        frappe.db.delete("Property Setter", {"doc_type": target_name})


def _drop_job_card_columns():
    for doctype in JOB_CARD_DOCTYPES:
        table = "tab" + doctype
        if not frappe.db.table_exists(table):
            continue
        existing_cols = {
            row[0]
            for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")
        }
        for col in JOB_CARD_DROP_COLUMNS:
            if col in existing_cols:
                try:
                    frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `{col}`")
                except Exception:
                    # Tolerate column-not-found races on re-runs.
                    pass


def execute():
    # 1. Delete child tables first so parent deletes don't block on FKs.
    for child in CHILD_DOCTYPES:
        _purge_workspace_links(child)
        _purge_custom_metadata(child)
        _delete_doctype(child)

    # 2. Delete parent execution doctypes.
    for parent in PARENT_DOCTYPES:
        _purge_workspace_links(parent)
        _purge_custom_metadata(parent)
        _delete_doctype(parent)

    # 3. Strip production-tracking columns from job card tables so the
    #    DocType JSON (which no longer declares them) matches the DB.
    _drop_job_card_columns()

    # 4. Drop reports / print formats / workspaces tied to the execution
    #    layer so the desk doesn't show broken entries.
    for report in REPORT_NAMES:
        if frappe.db.exists("Report", report):
            try:
                frappe.delete_doc(
                    "Report", report, force=True, ignore_permissions=True
                )
            except Exception:
                frappe.db.delete("Report", {"name": report})

    for pf in PRINT_FORMAT_NAMES:
        if frappe.db.exists("Print Format", pf):
            try:
                frappe.delete_doc(
                    "Print Format", pf, force=True, ignore_permissions=True
                )
            except Exception:
                frappe.db.delete("Print Format", {"name": pf})

    for ws in WORKSPACE_NAMES:
        if frappe.db.exists("Workspace", ws):
            try:
                frappe.delete_doc(
                    "Workspace", ws, force=True, ignore_permissions=True
                )
            except Exception:
                frappe.db.delete("Workspace", {"name": ws})

    # 5. Clear cached metadata so the desk stops serving the old pages.
    frappe.clear_cache()
    frappe.db.commit()
