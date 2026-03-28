import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
    filters = filters or {}
    if not filters.get("report_date"):
        filters["report_date"] = add_days(today(), -1)

    columns = get_columns()
    data, chart = get_data_and_chart(filters)
    return columns, data, None, chart


def get_columns():
    return [
        {"label": _("Station"), "fieldname": "station", "fieldtype": "Link",
         "options": "Production Station", "width": 130},
        {"label": _("Shift"), "fieldname": "shift", "fieldtype": "Data", "width": 80},
        {"label": _("Entries"), "fieldname": "entries", "fieldtype": "Int", "width": 80},
        {"label": _("Reels Run"), "fieldname": "reels_run", "fieldtype": "Int", "width": 90},
        {"label": _("Full Reams"), "fieldname": "full_reams", "fieldtype": "Int", "width": 100},
        {"label": _("Incomplete"), "fieldname": "incomplete_reels", "fieldtype": "Int", "width": 100},
        {"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "precision": 2, "width": 80},
    ]


def get_data_and_chart(filters):
    report_date = filters["report_date"]

    rows = frappe.db.sql(
        """
        SELECT
            pe.station,
            dpl.shift,
            COUNT(pe.name)                                             AS entries,
            SUM(pe.number_of_reels)                                    AS reels_run,
            SUM(
              COALESCE(pe.r1_full_reams, 0)
              + COALESCE(pe.r2_full_reams, 0)
              + COALESCE(pe.r3_full_reams, 0)
              + COALESCE(pe.r4_full_reams, 0)
            )                                                           AS full_reams,
            SUM(
              COALESCE(pe.r1_incomplete_reel, 0)
              + COALESCE(pe.r2_incomplete_reel, 0)
              + COALESCE(pe.r3_incomplete_reel, 0)
              + COALESCE(pe.r4_incomplete_reel, 0)
            )                                                           AS incomplete_reels,
            SUM(COALESCE(pe.duration_hours, 0))                        AS hours
        FROM
            `tabProduction Entry` pe
            INNER JOIN `tabDaily Production Log` dpl ON pe.parent = dpl.name
        WHERE
            dpl.docstatus = 1
            AND dpl.production_date = %(report_date)s
        GROUP BY
            pe.station, dpl.shift
        ORDER BY
            pe.station, dpl.shift
        """,
        {"report_date": report_date},
        as_dict=True,
    )

    # Build bar chart: reams by station
    station_reams = {}
    for row in rows:
        station_reams[row.station] = station_reams.get(row.station, 0) + row.full_reams

    chart = {
        "data": {
            "labels": list(station_reams.keys()),
            "datasets": [
                {
                    "name": _("Full Reams"),
                    "values": list(station_reams.values()),
                }
            ],
        },
        "type": "bar",
        "title": _("Reams by Station – {0}").format(report_date),
    }

    return rows, chart
