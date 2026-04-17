import frappe
from frappe.utils import getdate, date_diff


JOB_CARD_TYPES = [
    "Job Card Computer Paper",
    "Job Card Label",
    "Job Card Carton",
]

CUSTOMER_FIELD_BY_TYPE = {
    "Job Card Computer Paper": "customer",
    "Job Card Label": "customer",
    "Job Card Carton": "customer_name",
}


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "job_card_id", "label": "Job Card", "fieldtype": "Data", "width": 160},
        {"fieldname": "job_card_type", "label": "Type", "fieldtype": "Data", "width": 140},
        {"fieldname": "customer", "label": "Customer", "fieldtype": "Data", "width": 140},
        {"fieldname": "quantity_ordered", "label": "Order Qty", "fieldtype": "Int", "width": 90},
        {"fieldname": "qty_produced", "label": "Qty Produced", "fieldtype": "Int", "width": 100},
        {"fieldname": "qty_remaining", "label": "Remaining", "fieldtype": "Int", "width": 90},
        {"fieldname": "progress_pct", "label": "Progress %", "fieldtype": "Percent", "width": 90},
        {"fieldname": "total_waste", "label": "Total Waste", "fieldtype": "Int", "width": 90},
        {"fieldname": "due_date", "label": "Due Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "days_remaining", "label": "Days Left", "fieldtype": "Int", "width": 80},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100},
    ]


def get_data(filters):
    data = []
    today = getdate()

    for jc_type in JOB_CARD_TYPES:
        short_type = jc_type.replace("Job Card ", "")
        customer_col = CUSTOMER_FIELD_BY_TYPE[jc_type]
        conditions = "jc.docstatus = 1"
        values = {}

        if filters and filters.get("customer"):
            conditions += f" AND jc.{customer_col} = %(customer)s"
            values["customer"] = filters["customer"]

        job_cards = frappe.db.sql(
            f"""
            SELECT jc.name,
                   jc.{customer_col} AS customer,
                   jc.quantity_ordered,
                   jc.due_date
            FROM `tab{jc_type}` jc
            WHERE {conditions}
            ORDER BY jc.due_date ASC
            """,
            values,
            as_dict=True,
        )

        for jc in job_cards:
            pe_totals = frappe.db.sql(
                """
                SELECT COALESCE(SUM(qty_produced), 0) as produced,
                       COALESCE(SUM(qty_waste), 0) as waste
                FROM `tabProduction Entry`
                WHERE job_card_type = %s AND job_card_id = %s AND docstatus = 1
                """,
                (jc_type, jc.name),
                as_dict=True,
            )[0]

            qty_produced = pe_totals.produced
            total_waste = pe_totals.waste
            qty_ordered = jc.quantity_ordered or 0
            qty_remaining = max(0, qty_ordered - qty_produced)
            progress_pct = (qty_produced / qty_ordered * 100) if qty_ordered else 0
            days_remaining = date_diff(jc.due_date, today) if jc.due_date else None

            if qty_produced >= qty_ordered and qty_ordered > 0:
                status = "Completed"
            elif jc.due_date and getdate(jc.due_date) < today:
                status = "Overdue"
            elif progress_pct < 50 and days_remaining is not None and days_remaining < 3:
                status = "At Risk"
            else:
                status = "On Track"

            data.append(
                {
                    "job_card_id": jc.name,
                    "job_card_type": short_type,
                    "customer": jc.customer,
                    "quantity_ordered": qty_ordered,
                    "qty_produced": qty_produced,
                    "qty_remaining": qty_remaining,
                    "progress_pct": progress_pct,
                    "total_waste": total_waste,
                    "due_date": jc.due_date,
                    "days_remaining": days_remaining,
                    "status": status,
                }
            )

    return data
