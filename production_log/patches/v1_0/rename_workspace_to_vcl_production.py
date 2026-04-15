"""
Patch: Rename the 'Job Card Tracking' workspace to 'VCL Production'.

The workspace is being renamed so the desk URL becomes /app/vcl-production
and the sidebar label reads 'VCL Production'. The Frappe module stays as
'Job Card Tracking', so no doctype moves are required.

Strategy: drop the old workspace record. The new JSON definition shipped
with the app will be (re)installed as 'VCL Production' during the normal
workspace sync that runs as part of bench migrate.

Idempotent: safe to run on sites that never had the old workspace, and safe
to re-run after the new workspace is already in place.
"""

import frappe


OLD_NAME = "Job Card Tracking"
NEW_NAME = "VCL Production"


def execute():
    # Nothing to do if the old workspace is already gone.
    if not frappe.db.exists("Workspace", OLD_NAME):
        frappe.clear_cache()
        return

    # If neither name exists yet (fresh install of this patch before sync),
    # rename in-place so any user customisations on the old record carry over.
    if not frappe.db.exists("Workspace", NEW_NAME):
        try:
            frappe.rename_doc(
                "Workspace",
                OLD_NAME,
                NEW_NAME,
                force=True,
                ignore_permissions=True,
                merge=False,
            )
            frappe.db.commit()
            frappe.clear_cache()
            return
        except Exception:
            # Fall through to the delete-and-resync path below.
            pass

    # Both records exist (or the rename failed) — drop the old one so the
    # sidebar doesn't show a duplicate entry. The new workspace is already
    # installed from JSON.
    try:
        frappe.delete_doc(
            "Workspace",
            OLD_NAME,
            force=True,
            ignore_permissions=True,
            ignore_missing=True,
        )
    except Exception:
        frappe.db.delete("Workspace", {"name": OLD_NAME})

    frappe.clear_cache()
    frappe.db.commit()
