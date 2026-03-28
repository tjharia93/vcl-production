import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Workstation"), "fieldname": "station", "fieldtype": "Link",
         "options": "Workstation", "width": 120},
        {"label": _("Date"), "fieldname": "production_date", "fieldtype": "Date", "width": 100},
        {"label": _("Shift"), "fieldname": "shift", "fieldtype": "Data", "width": 70},
        {"label": _("Operator"), "fieldname": "operator", "fieldtype": "Link",
         "options": "Employee", "width": 140},
        {"label": _("Reels Run"), "fieldname": "reels_run", "fieldtype": "Int", "width": 80},
        {"label": _("Full Reams"), "fieldname": "full_reams", "fieldtype": "Int", "width": 90},
        {"label": _("Incomplete Reels"), "fieldname": "incomplete_reels", "fieldtype": "Int", "width": 120},
        {"label": _("Hours Worked"), "fieldname": "hours_worked", "fieldtype": "Float",
         "precision": 2, "width": 100},
    ]


def get_data(filters):
    conditions = _build_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            pe.station,
            dpl.production_date,
            dpl.shift,
            pe.operator,
            pe.number_of_reels                                        AS reels_run,
            COALESCE(pe.r1_full_reams, 0)
              + COALESCE(pe.r2_full_reams, 0)
              + COALESCE(pe.r3_full_reams, 0)
              + COALESCE(pe.r4_full_reams, 0)                         AS full_reams,
            (COALESCE(pe.r1_incomplete_reel, 0)
              + COALESCE(pe.r2_incomplete_reel, 0)
              + COALESCE(pe.r3_incomplete_reel, 0)
              + COALESCE(pe.r4_incomplete_reel, 0))                   AS incomplete_reels,
            COALESCE(pe.duration_hours, 0)                            AS hours_worked
        FROM
            `tabProduction Entry` pe
            INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE
            dpl.docstatus = 1
            {conditions}
        ORDER BY
            pe.station, dpl.production_date DESC, dpl.shift
        """,
        filters,
        as_dict=True,
    )
    return rows


def _build_conditions(filters):
    conditions = ""
    if filters.get("from_date"):
        conditions += " AND dpl.production_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND dpl.production_date <= %(to_date)s"
    if filters.get("station"):
        conditions += " AND pe.station = %(station)s"
    if filters.get("shift"):
        conditions += " AND dpl.shift = %(shift)s"
    return conditions
