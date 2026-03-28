"""
Patch: Create 'Production Manager' role and set permissions on all three DocTypes.
Safe to run multiple times (idempotent).
"""

import frappe


def execute():
    _create_role("Production Manager")
    _set_permissions()
    frappe.db.commit()


def _create_role(role_name):
    if frappe.db.exists("Role", role_name):
        frappe.logger().info(f"[setup_roles] Role '{role_name}' already exists, skipping.")
        return

    try:
        frappe.get_doc({
            "doctype": "Role",
            "role_name": role_name,
            "desk_access": 1,
        }).insert(ignore_permissions=True)
        frappe.logger().info(f"[setup_roles] Created role '{role_name}'.")
    except Exception as e:
        frappe.log_error(f"Failed to create role {role_name}: {e}", "setup_roles patch")


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
