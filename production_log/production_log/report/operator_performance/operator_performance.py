import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Operator"), "fieldname": "operator", "fieldtype": "Link",
         "options": "Employee", "width": 160},
        {"label": _("Total Shifts"), "fieldname": "total_shifts", "fieldtype": "Int", "width": 100},
        {"label": _("Total Hours"), "fieldname": "total_hours", "fieldtype": "Float",
         "precision": 2, "width": 100},
        {"label": _("Reels Completed"), "fieldname": "reels_completed", "fieldtype": "Int", "width": 120},
        {"label": _("Full Reams Produced"), "fieldname": "full_reams", "fieldtype": "Int", "width": 140},
        {"label": _("Avg Reams / Hour"), "fieldname": "avg_reams_per_hour", "fieldtype": "Float",
         "precision": 2, "width": 130},
    ]


def get_data(filters):
    conditions = _build_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            pe.operator,
            COUNT(DISTINCT pe.parent)                                 AS total_shifts,
            SUM(COALESCE(pe.duration_hours, 0))                       AS total_hours,
            SUM(pe.number_of_reels)                                   AS reels_completed,
            SUM(
              COALESCE(pe.r1_full_reams, 0)
              + COALESCE(pe.r2_full_reams, 0)
              + COALESCE(pe.r3_full_reams, 0)
              + COALESCE(pe.r4_full_reams, 0)
            )                                                          AS full_reams
        FROM
            `tabProduction Entry` pe
            INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE
            dpl.docstatus = 1
            {conditions}
        GROUP BY
            pe.operator
        ORDER BY
            full_reams DESC
        """,
        filters,
        as_dict=True,
    )

    for row in rows:
        if row.total_hours and row.total_hours > 0:
            row.avg_reams_per_hour = round(row.full_reams / row.total_hours, 2)
        else:
            row.avg_reams_per_hour = 0

    return rows


def _build_conditions(filters):
    conditions = ""
    if filters.get("from_date"):
        conditions += " AND dpl.production_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND dpl.production_date <= %(to_date)s"
    if filters.get("operator"):
        conditions += " AND pe.operator = %(operator)s"
    return conditions
