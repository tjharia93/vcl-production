import frappe


def after_install():
    """Run after app installation."""
    create_default_production_stations()
    frappe.db.commit()


def create_default_production_stations():
    """Create the 5 default production stations."""
    stations = [
        {"station_code": "R.O.1", "station_name": "Ruling Operator 1", "max_reels": 4},
        {"station_code": "R.O.2", "station_name": "Ruling Operator 2", "max_reels": 4},
        {"station_code": "R.O.3", "station_name": "Ruling Operator 3", "max_reels": 4},
        {"station_code": "R.D.3", "station_name": "Ruling Duplex 3", "max_reels": 2},
        {"station_code": "R.S.3", "station_name": "Ruling Simplex 3", "max_reels": 1},
    ]

    for s in stations:
        if not frappe.db.exists("Production Station", s["station_code"]):
            doc = frappe.get_doc({
                "doctype": "Production Station",
                "station_code": s["station_code"],
                "station_name": s["station_name"],
                "max_reels": s["max_reels"],
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)
            frappe.msgprint(f"Created Production Station: {s['station_code']}")
        else:
            frappe.msgprint(f"Production Station '{s['station_code']}' already exists, skipping.")
