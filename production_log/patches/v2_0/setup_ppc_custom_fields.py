import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    custom_fields = {
        "Workstation Type": [
            {
                "fieldname": "custom_product_line",
                "fieldtype": "Select",
                "label": "Product Line",
                "options": "All\nComputer Paper\nLabel\nCarton",
                "default": "All",
                "insert_after": "description",
            },
            {
                "fieldname": "custom_default_stage",
                "fieldtype": "Link",
                "label": "Default Stage",
                "options": "Production Stage",
                "insert_after": "custom_product_line",
            },
        ],
        "Workstation": [
            {
                "fieldname": "custom_product_line",
                "fieldtype": "Select",
                "label": "Product Line",
                "options": "All\nComputer Paper\nLabel\nCarton",
                "default": "All",
                "insert_after": "workstation_type",
            },
            {
                "fieldname": "custom_max_width_mm",
                "fieldtype": "Int",
                "label": "Max Width (mm)",
                "insert_after": "custom_product_line",
            },
            {
                "fieldname": "custom_max_colors",
                "fieldtype": "Int",
                "label": "Max Colors",
                "insert_after": "custom_max_width_mm",
            },
            {
                "fieldname": "custom_max_speed_per_hour",
                "fieldtype": "Int",
                "label": "Max Speed (per hour)",
                "insert_after": "custom_max_colors",
            },
            {
                "fieldname": "custom_location_note",
                "fieldtype": "Small Text",
                "label": "Location Note",
                "insert_after": "custom_max_speed_per_hour",
            },
        ],
        "Job Card Computer Paper": [
            {
                "fieldname": "custom_production_tracking_sb",
                "fieldtype": "Section Break",
                "label": "Production Tracking",
                "insert_after": "quantity_ordered",
            },
            {
                "fieldname": "custom_production_status",
                "fieldtype": "Select",
                "label": "Production Status",
                "options": "Not Started\nIn Progress\nCompleted",
                "default": "Not Started",
                "read_only": 1,
                "insert_after": "custom_production_tracking_sb",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "custom_current_stage",
                "fieldtype": "Link",
                "label": "Current Stage",
                "options": "Production Stage",
                "read_only": 1,
                "insert_after": "custom_production_status",
            },
        ],
        "Job Card Label": [
            {
                "fieldname": "custom_production_tracking_sb",
                "fieldtype": "Section Break",
                "label": "Production Tracking",
                "insert_after": "quantity_ordered",
            },
            {
                "fieldname": "custom_production_status",
                "fieldtype": "Select",
                "label": "Production Status",
                "options": "Not Started\nIn Progress\nCompleted",
                "default": "Not Started",
                "read_only": 1,
                "insert_after": "custom_production_tracking_sb",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "custom_current_stage",
                "fieldtype": "Link",
                "label": "Current Stage",
                "options": "Production Stage",
                "read_only": 1,
                "insert_after": "custom_production_status",
            },
        ],
        "Job Card Carton": [
            {
                "fieldname": "custom_production_tracking_sb",
                "fieldtype": "Section Break",
                "label": "Production Tracking",
                "insert_after": "quantity_ordered",
            },
            {
                "fieldname": "custom_production_status",
                "fieldtype": "Select",
                "label": "Production Status",
                "options": "Not Started\nIn Progress\nCompleted",
                "default": "Not Started",
                "read_only": 1,
                "insert_after": "custom_production_tracking_sb",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "custom_current_stage",
                "fieldtype": "Link",
                "label": "Current Stage",
                "options": "Production Stage",
                "read_only": 1,
                "insert_after": "custom_production_status",
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)
