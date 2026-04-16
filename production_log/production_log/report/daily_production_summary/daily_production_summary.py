import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "workstation", "label": "Workstation", "fieldtype": "Link", "options": "Workstation", "width": 150},
        {"fieldname": "job_card_id", "label": "Job Card", "fieldtype": "Data", "width": 150},
        {"fieldname": "customer", "label": "Customer", "fieldtype": "Data", "width": 140},
        {"fieldname": "production_stage", "label": "Stage", "fieldtype": "Link", "options": "Production Stage", "width": 120},
        {"fieldname": "planned_qty", "label": "Planned Qty", "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_qty", "label": "Actual Qty", "fieldtype": "Int", "width": 100},
        {"fieldname": "waste_qty", "label": "Waste Qty", "fieldtype": "Int", "width": 90},
        {"fieldname": "waste_pct", "label": "Waste %", "fieldtype": "Percent", "width": 80},
        {"fieldname": "variance", "label": "Variance", "fieldtype": "Int", "width": 90},
        {"fieldname": "duration_hours", "label": "Duration (hrs)", "fieldtype": "Float", "width": 110},
    ]


def get_data(filters):
    conditions = "pe.docstatus = 1"
    values = {}

    if filters and filters.get("from_date"):
        conditions += " AND DATE(pe.start_time) >= %(from_date)s"
        values["from_date"] = filters["from_date"]
    if filters and filters.get("to_date"):
        conditions += " AND DATE(pe.start_time) <= %(to_date)s"
        values["to_date"] = filters["to_date"]
    if filters and filters.get("workstation"):
        conditions += " AND pe.workstation = %(workstation)s"
        values["workstation"] = filters["workstation"]

    data = frappe.db.sql(
        f"""
        SELECT
            DATE(pe.start_time) AS posting_date,
            pe.workstation,
            pe.job_card_id,
            pe.customer,
            pe.production_stage,
            SUM(pe.qty_produced) AS actual_qty,
            SUM(pe.qty_waste) AS waste_qty,
            SUM(pe.duration_hours) AS duration_hours
        FROM `tabProduction Entry` pe
        WHERE {conditions}
        GROUP BY DATE(pe.start_time), pe.workstation, pe.job_card_id, pe.production_stage
        ORDER BY DATE(pe.start_time) DESC, pe.workstation
        """,
        values,
        as_dict=True,
    )

    for row in data:
        total = (row.actual_qty or 0) + (row.waste_qty or 0)
        row.waste_pct = ((row.waste_qty or 0) / total * 100) if total else 0
        row.planned_qty = get_planned_qty(
            row.posting_date, row.workstation, row.job_card_id
        )
        row.variance = (row.actual_qty or 0) - (row.planned_qty or 0)

    return data


def get_planned_qty(posting_date, workstation, job_card_id):
    result = frappe.db.sql(
        """
        SELECT SUM(sl.planned_qty)
        FROM `tabSchedule Line` sl
        JOIN `tabDaily Production Schedule` dps ON sl.parent = dps.name
        WHERE dps.schedule_date = %s AND dps.workstation = %s
          AND sl.job_card_id = %s AND dps.docstatus != 2
        """,
        (posting_date, workstation, job_card_id),
    )
    return result[0][0] if result and result[0][0] else 0
