import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Date"), "fieldname": "production_date", "fieldtype": "Date", "width": 100},
        {"label": _("Log"), "fieldname": "log_name", "fieldtype": "Link",
         "options": "Daily Production Log", "width": 180},
        {"label": _("Station"), "fieldname": "station", "fieldtype": "Link",
         "options": "Production Station", "width": 120},
        {"label": _("Operator"), "fieldname": "operator", "fieldtype": "Link",
         "options": "Employee", "width": 140},
        {"label": _("Reel #"), "fieldname": "reel_number", "fieldtype": "Data", "width": 70},
        {"label": _("Material Type"), "fieldname": "material_type", "fieldtype": "Data", "width": 100},
        {"label": _("GSM"), "fieldname": "gsm", "fieldtype": "Float", "precision": 1, "width": 70},
        {"label": _("Start Weight (kg)"), "fieldname": "start_weight", "fieldtype": "Float",
         "precision": 2, "width": 130},
        {"label": _("End Weight (kg)"), "fieldname": "end_weight", "fieldtype": "Float",
         "precision": 2, "width": 130},
        {"label": _("Notes"), "fieldname": "notes", "fieldtype": "Data", "width": 200},
    ]


def get_data(filters):
    from_date = filters.get("from_date") or add_days(today(), -7)
    to_date = filters.get("to_date") or today()

    # Query each reel separately via UNION
    query = f"""
        SELECT
            dpl.production_date,
            dpl.name AS log_name,
            pe.station,
            pe.operator,
            '1'          AS reel_number,
            pe.material_type,
            pe.r1_gsm    AS gsm,
            pe.r1_start_weight AS start_weight,
            pe.r1_end_weight   AS end_weight,
            pe.notes
        FROM `tabProduction Entry` pe
        INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE dpl.docstatus = 1
          AND dpl.production_date BETWEEN %(from_date)s AND %(to_date)s
          AND pe.r1_incomplete_reel = 1

        UNION ALL

        SELECT
            dpl.production_date,
            dpl.name AS log_name,
            pe.station,
            pe.operator,
            '2'          AS reel_number,
            pe.material_type,
            pe.r2_gsm    AS gsm,
            pe.r2_start_weight AS start_weight,
            pe.r2_end_weight   AS end_weight,
            pe.notes
        FROM `tabProduction Entry` pe
        INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE dpl.docstatus = 1
          AND dpl.production_date BETWEEN %(from_date)s AND %(to_date)s
          AND pe.number_of_reels >= 2
          AND pe.r2_incomplete_reel = 1

        UNION ALL

        SELECT
            dpl.production_date,
            dpl.name AS log_name,
            pe.station,
            pe.operator,
            '3'          AS reel_number,
            pe.material_type,
            pe.r3_gsm    AS gsm,
            pe.r3_start_weight AS start_weight,
            pe.r3_end_weight   AS end_weight,
            pe.notes
        FROM `tabProduction Entry` pe
        INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE dpl.docstatus = 1
          AND dpl.production_date BETWEEN %(from_date)s AND %(to_date)s
          AND pe.number_of_reels >= 3
          AND pe.r3_incomplete_reel = 1

        UNION ALL

        SELECT
            dpl.production_date,
            dpl.name AS log_name,
            pe.station,
            pe.operator,
            '4'          AS reel_number,
            pe.material_type,
            pe.r4_gsm    AS gsm,
            pe.r4_start_weight AS start_weight,
            pe.r4_end_weight   AS end_weight,
            pe.notes
        FROM `tabProduction Entry` pe
        INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE dpl.docstatus = 1
          AND dpl.production_date BETWEEN %(from_date)s AND %(to_date)s
          AND pe.number_of_reels >= 4
          AND pe.r4_incomplete_reel = 1

        ORDER BY production_date DESC, log_name, reel_number
    """

    return frappe.db.sql(
        query,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
