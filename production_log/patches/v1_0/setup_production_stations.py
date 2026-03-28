"""
Patch: Create default production stations for VCL.
Safe to run multiple times (idempotent).
"""

import frappe


def execute():
    stations = [
        {"station_code": "R.O.1", "station_name": "Ruling Operator 1", "max_reels": 4},
        {"station_code": "R.O.2", "station_name": "Ruling Operator 2", "max_reels": 4},
        {"station_code": "R.O.3", "station_name": "Ruling Operator 3", "max_reels": 4},
        {"station_code": "R.D.3", "station_name": "Ruling Duplex 3",   "max_reels": 2},
        {"station_code": "R.S.3", "station_name": "Ruling Simplex 3",  "max_reels": 1},
    ]

    for s in stations:
        if frappe.db.exists("Production Station", s["station_code"]):
            frappe.logger().info(
                f"[setup_production_stations] Skipping '{s['station_code']}' – already exists."
            )
            continue

        try:
            doc = frappe.get_doc({
                "doctype": "Production Station",
                "station_code": s["station_code"],
                "station_name": s["station_name"],
                "max_reels": s["max_reels"],
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)
            frappe.logger().info(
                f"[setup_production_stations] Created station '{s['station_code']}'."
            )
        except Exception as e:
            frappe.log_error(
                f"Failed to create station {s['station_code']}: {e}",
                "setup_production_stations patch"
            )

    frappe.db.commit()
