import frappe
from frappe.utils import now


def execute():
    seed_production_stages()
    seed_waste_reasons()
    seed_downtime_reasons()


def seed_production_stages():
    if not frappe.db.table_exists("Production Stage"):
        return

    stages = [
        {"stage_name": "Design", "product_line": "All", "sequence": 1, "is_qc_point": 0},
        {"stage_name": "Pre-Press", "product_line": "All", "sequence": 5, "is_qc_point": 0},
        {"stage_name": "Printing", "product_line": "All", "sequence": 10, "is_qc_point": 0},
        {"stage_name": "Numbering", "product_line": "Computer Paper", "sequence": 20, "is_qc_point": 0},
        {"stage_name": "Collating", "product_line": "Computer Paper", "sequence": 30, "is_qc_point": 0},
        {"stage_name": "Wrapping", "product_line": "Computer Paper", "sequence": 40, "is_qc_point": 1},
        {"stage_name": "Die Cutting", "product_line": "Label", "sequence": 20, "is_qc_point": 0},
        {"stage_name": "Re-winding", "product_line": "Label", "sequence": 25, "is_qc_point": 0},
        {"stage_name": "Slitting", "product_line": "Label", "sequence": 28, "is_qc_point": 1},
        {"stage_name": "Finishing", "product_line": "Label", "sequence": 30, "is_qc_point": 1},
        {"stage_name": "Corrugating", "product_line": "Carton", "sequence": 10, "is_qc_point": 0},
        {"stage_name": "Pasting", "product_line": "Carton", "sequence": 15, "is_qc_point": 0},
        {"stage_name": "Creasing", "product_line": "Carton", "sequence": 20, "is_qc_point": 0},
        {"stage_name": "Creasing & Slotting", "product_line": "Carton", "sequence": 22, "is_qc_point": 0},
        {"stage_name": "Slotting", "product_line": "Carton", "sequence": 25, "is_qc_point": 0},
        {"stage_name": "Folding & Gluing", "product_line": "Carton", "sequence": 30, "is_qc_point": 0},
        {"stage_name": "Stitching", "product_line": "Carton", "sequence": 35, "is_qc_point": 0},
        {"stage_name": "Gluing", "product_line": "Carton", "sequence": 37, "is_qc_point": 0},
        {"stage_name": "Bundling", "product_line": "Carton", "sequence": 45, "is_qc_point": 1},
        {"stage_name": "Packing", "product_line": "All", "sequence": 90, "is_qc_point": 1},
    ]
    for stage in stages:
        if not frappe.db.exists("Production Stage", stage["stage_name"]):
            frappe.db.sql(
                """
                INSERT INTO `tabProduction Stage`
                    (name, creation, modified, modified_by, owner,
                     stage_name, product_line, sequence, is_qc_point)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    stage["stage_name"], now(), now(), "Administrator", "Administrator",
                    stage["stage_name"], stage["product_line"], stage["sequence"],
                    stage["is_qc_point"],
                ),
            )

    frappe.db.commit()


def seed_waste_reasons():
    if not frappe.db.table_exists("Waste Reason"):
        return

    reasons = [
        {"reason_name": "Setup Waste", "category": "Setup"},
        {"reason_name": "Misprinted", "category": "Running"},
        {"reason_name": "Off-Register", "category": "Running"},
        {"reason_name": "Torn Web", "category": "Running"},
        {"reason_name": "Material Defect", "category": "Material Defect"},
        {"reason_name": "Wrong Die", "category": "Operator Error"},
        {"reason_name": "Colour Mismatch", "category": "Running"},
        {"reason_name": "Trim Waste", "category": "Setup"},
    ]
    for reason in reasons:
        if not frappe.db.exists("Waste Reason", reason["reason_name"]):
            frappe.db.sql(
                """
                INSERT INTO `tabWaste Reason`
                    (name, creation, modified, modified_by, owner,
                     reason_name, category, enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    reason["reason_name"], now(), now(), "Administrator", "Administrator",
                    reason["reason_name"], reason["category"], 1,
                ),
            )

    frappe.db.commit()


def seed_downtime_reasons():
    if not frappe.db.table_exists("Downtime Reason"):
        return

    reasons = [
        {"reason_name": "Mechanical Breakdown", "category": "Mechanical", "is_planned": 0},
        {"reason_name": "Electrical Fault", "category": "Electrical", "is_planned": 0},
        {"reason_name": "Power Outage", "category": "Electrical", "is_planned": 0},
        {"reason_name": "Material Shortage", "category": "Material Shortage", "is_planned": 0},
        {"reason_name": "Planned Maintenance", "category": "Planned Maintenance", "is_planned": 1},
        {"reason_name": "Die Changeover", "category": "Planned Maintenance", "is_planned": 1},
        {"reason_name": "Operator Unavailable", "category": "Operator Unavailable", "is_planned": 0},
        {"reason_name": "Waiting for QC", "category": "Other", "is_planned": 0},
    ]
    for reason in reasons:
        if not frappe.db.exists("Downtime Reason", reason["reason_name"]):
            frappe.db.sql(
                """
                INSERT INTO `tabDowntime Reason`
                    (name, creation, modified, modified_by, owner,
                     reason_name, category, is_planned, enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    reason["reason_name"], now(), now(), "Administrator", "Administrator",
                    reason["reason_name"], reason["category"], reason["is_planned"], 1,
                ),
            )

    frappe.db.commit()
