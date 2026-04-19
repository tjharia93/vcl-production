import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "workstation", "label": "Workstation", "fieldtype": "Link", "options": "Workstation", "width": 160},
        {"fieldname": "workstation_type", "label": "Type", "fieldtype": "Data", "width": 130},
        {"fieldname": "available_hours", "label": "Available Hrs", "fieldtype": "Float", "width": 110},
        {"fieldname": "run_hours", "label": "Run Hrs", "fieldtype": "Float", "width": 90},
        {"fieldname": "downtime_unplanned", "label": "Downtime (Unplanned)", "fieldtype": "Float", "width": 140},
        {"fieldname": "downtime_planned", "label": "Downtime (Planned)", "fieldtype": "Float", "width": 130},
        {"fieldname": "idle_hours", "label": "Idle Hrs", "fieldtype": "Float", "width": 90},
        {"fieldname": "utilization_pct", "label": "Utilization %", "fieldtype": "Percent", "width": 100},
    ]


def get_data(filters):
    conditions = "dps.docstatus = 1"
    values = {}

    if filters and filters.get("from_date"):
        conditions += " AND dps.schedule_date >= %(from_date)s"
        values["from_date"] = filters["from_date"]
    if filters and filters.get("to_date"):
        conditions += " AND dps.schedule_date <= %(to_date)s"
        values["to_date"] = filters["to_date"]
    if filters and filters.get("workstation"):
        conditions += " AND dps.workstation = %(workstation)s"
        values["workstation"] = filters["workstation"]

    dps_data = frappe.db.sql(
        f"""
        SELECT
            dps.workstation,
            dps.workstation_type,
            SUM(dps.available_hours) AS available_hours,
            SUM(dps.total_planned_hours) AS planned_hours
        FROM `tabDaily Production Schedule` dps
        WHERE {conditions}
        GROUP BY dps.workstation, dps.workstation_type
        ORDER BY dps.workstation
        """,
        values,
        as_dict=True,
    )

    data = []
    for row in dps_data:
        ws = row.workstation
        pe_conditions = "pe.docstatus = 1 AND pe.workstation = %(ws)s"
        pe_values = {"ws": ws}
        if filters and filters.get("from_date"):
            pe_conditions += " AND DATE(pe.start_time) >= %(from_date)s"
            pe_values["from_date"] = filters["from_date"]
        if filters and filters.get("to_date"):
            pe_conditions += " AND DATE(pe.start_time) <= %(to_date)s"
            pe_values["to_date"] = filters["to_date"]

        run_hours = frappe.db.sql(
            f"SELECT COALESCE(SUM(pe.duration_hours), 0) FROM `tabProduction Entry` pe WHERE {pe_conditions}",
            pe_values,
        )[0][0]

        dt_conditions = "dt.docstatus = 1 AND dt.workstation = %(ws)s"
        dt_values = {"ws": ws}
        if filters and filters.get("from_date"):
            dt_conditions += " AND DATE(dt.start_time) >= %(from_date)s"
            dt_values["from_date"] = filters["from_date"]
        if filters and filters.get("to_date"):
            dt_conditions += " AND DATE(dt.start_time) <= %(to_date)s"
            dt_values["to_date"] = filters["to_date"]

        downtime = frappe.db.sql(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN dt.is_planned = 0 THEN dt.duration_minutes ELSE 0 END), 0) / 60 AS unplanned,
                COALESCE(SUM(CASE WHEN dt.is_planned = 1 THEN dt.duration_minutes ELSE 0 END), 0) / 60 AS planned
            FROM `tabDowntime Entry` dt
            WHERE {dt_conditions}
            """,
            dt_values,
            as_dict=True,
        )[0]

        available = row.available_hours or 0
        idle = max(0, available - (run_hours or 0) - (downtime.unplanned or 0) - (downtime.planned or 0))
        utilization = ((run_hours or 0) / available * 100) if available else 0

        data.append({
            "workstation": ws,
            "workstation_type": row.workstation_type,
            "available_hours": round(available, 1),
            "run_hours": round(run_hours or 0, 1),
            "downtime_unplanned": round(downtime.unplanned or 0, 1),
            "downtime_planned": round(downtime.planned or 0, 1),
            "idle_hours": round(idle, 1),
            "utilization_pct": round(utilization, 1),
        })

    return data
