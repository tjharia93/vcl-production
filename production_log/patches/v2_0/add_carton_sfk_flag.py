import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({
        "Job Card Carton": [{
            "fieldname": "custom_is_sfk",
            "fieldtype": "Check",
            "label": "Is SFK (Single-Face Kraft)",
            "default": "0",
            "insert_after": "quantity_ordered",
            "description": "SFK cartons only need the Corrugating stage.",
        }],
    }, update=True)
