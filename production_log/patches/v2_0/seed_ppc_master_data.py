import frappe


def execute():
    seed_production_stages()
    seed_waste_reasons()
    seed_downtime_reasons()


def seed_production_stages():
    stages = [
        {"stage_name": "Printing", "product_line": "All", "sequence": 10, "is_qc_point": 0},
        {"stage_name": "Numbering", "product_line": "Computer Paper", "sequence": 20, "is_qc_point": 0},
        {"stage_name": "Collating", "product_line": "Computer Paper", "sequence": 30, "is_qc_point": 0},
        {"stage_name": "Wrapping", "product_line": "Computer Paper", "sequence": 40, "is_qc_point": 1},
        {"stage_name": "Die Cutting", "product_line": "Label", "sequence": 20, "is_qc_point": 0},
        {"stage_name": "Finishing", "product_line": "Label", "sequence": 30, "is_qc_point": 1},
        {"stage_name": "Corrugating", "product_line": "Carton", "sequence": 10, "is_qc_point": 0},
        {"stage_name": "Creasing & Slotting", "product_line": "Carton", "sequence": 20, "is_qc_point": 0},
        {"stage_name": "Folding & Gluing", "product_line": "Carton", "sequence": 30, "is_qc_point": 0},
        {"stage_name": "Packing", "product_line": "All", "sequence": 90, "is_qc_point": 1},
    ]
    for stage in stages:
        if not frappe.db.exists("Production Stage", stage["stage_name"]):
            doc = frappe.get_doc({"doctype": "Production Stage", **stage})
            doc.insert(ignore_permissions=True)

    frappe.db.commit()


def seed_waste_reasons():
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
            doc = frappe.get_doc({"doctype": "Waste Reason", "enabled": 1, **reason})
            doc.insert(ignore_permissions=True)

    frappe.db.commit()


def seed_downtime_reasons():
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
            doc = frappe.get_doc({"doctype": "Downtime Reason", "enabled": 1, **reason})
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
