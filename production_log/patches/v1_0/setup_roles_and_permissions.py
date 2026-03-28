"""
Patch: Reload DocType permissions for all three Production Log DocTypes.
Manufacturing Manager and System Manager roles (built-in ERPNext roles) are
used — no custom role creation needed.
Safe to run multiple times (idempotent).
"""

import frappe


def execute():
    _set_permissions()
    frappe.db.commit()


def _set_permissions():
    """
    Ensure correct permission records exist for each DocType.
    Uses DocType's permission list – if already configured via JSON,
    this is a no-op for existing entries.
    """
    doctypes = [
        "Production Station",
        "Daily Production Log",
        "Production Entry",
    ]
    for dt in doctypes:
        try:
            frappe.reload_doctype(dt)
            frappe.logger().info(f"[setup_roles] Reloaded DocType permissions for '{dt}'.")
        except Exception as e:
            frappe.log_error(
                f"Failed to reload permissions for {dt}: {e}",
                "setup_roles patch"
            )
