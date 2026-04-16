import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours


class ProductionEntry(Document):
    def validate(self):
        self.validate_job_card_not_cancelled()
        self.validate_waste_reason()
        self.calculate_duration()
        self.calculate_waste_pct()
        self.fetch_customer()
        self.auto_link_dps()

    def validate_job_card_not_cancelled(self):
        if not self.job_card_type or not self.job_card_id:
            return
        docstatus = frappe.db.get_value(self.job_card_type, self.job_card_id, "docstatus")
        if docstatus == 2:
            frappe.throw(
                f"Cannot create Production Entry for cancelled {self.job_card_type}: {self.job_card_id}"
            )

    def validate_waste_reason(self):
        if (self.qty_waste or 0) > 0 and not self.waste_reason:
            frappe.throw("Waste Reason is required when Qty Waste is greater than 0")

    def calculate_duration(self):
        if self.start_time and self.end_time:
            self.duration_hours = time_diff_in_hours(self.end_time, self.start_time)

    def calculate_waste_pct(self):
        total = (self.qty_produced or 0) + (self.qty_waste or 0)
        if total > 0:
            self.waste_pct = ((self.qty_waste or 0) / total) * 100
        else:
            self.waste_pct = 0

    def fetch_customer(self):
        if self.job_card_type and self.job_card_id:
            self.customer = frappe.db.get_value(
                self.job_card_type, self.job_card_id, "customer"
            )

    def auto_link_dps(self):
        if self.daily_production_schedule or not self.workstation or not self.start_time:
            return
        posting_date = frappe.utils.getdate(self.start_time)
        dps = frappe.db.exists(
            "Daily Production Schedule",
            {
                "workstation": self.workstation,
                "schedule_date": posting_date,
                "docstatus": ("!=", 2),
            },
        )
        if dps:
            self.daily_production_schedule = dps

    def on_submit(self):
        self.update_job_card_progress()

    def on_cancel(self):
        self.update_job_card_progress()

    def update_job_card_progress(self):
        if not self.job_card_type or not self.job_card_id:
            return

        total_produced = frappe.db.sql(
            """
            SELECT COALESCE(SUM(qty_produced), 0)
            FROM `tabProduction Entry`
            WHERE job_card_type = %s AND job_card_id = %s AND docstatus = 1
            """,
            (self.job_card_type, self.job_card_id),
        )[0][0]

        quantity_ordered = frappe.db.get_value(
            self.job_card_type, self.job_card_id, "quantity_ordered"
        ) or 0

        if total_produced <= 0:
            status = "Not Started"
        elif total_produced >= quantity_ordered and quantity_ordered > 0:
            status = "Completed"
        else:
            status = "In Progress"

        latest_stage = frappe.db.sql(
            """
            SELECT production_stage FROM `tabProduction Entry`
            WHERE job_card_type = %s AND job_card_id = %s AND docstatus = 1
            ORDER BY end_time DESC LIMIT 1
            """,
            (self.job_card_type, self.job_card_id),
        )
        current_stage = latest_stage[0][0] if latest_stage else None

        frappe.db.set_value(
            self.job_card_type,
            self.job_card_id,
            {
                "custom_production_status": status,
                "custom_current_stage": current_stage,
            },
            update_modified=False,
        )
