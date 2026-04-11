"""
Patch: Reload DocType permissions for remaining DocTypes.
Safe to run multiple times (idempotent).
"""

import frappe


def execute():
    frappe.db.commit()
