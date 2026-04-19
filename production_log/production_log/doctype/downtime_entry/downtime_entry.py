import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_seconds


class DowntimeEntry(Document):
    def validate(self):
        self.validate_times()
        self.calculate_duration()
        self.auto_link_dps()

    def before_submit(self):
        if not self.end_time:
            frappe.throw("End Time is required before submitting a Downtime Entry")

    def validate_times(self):
        if self.start_time and self.end_time:
            if self.end_time < self.start_time:
                frappe.throw("End Time must be after Start Time")

    def calculate_duration(self):
        if self.start_time and self.end_time:
            diff_seconds = time_diff_in_seconds(self.end_time, self.start_time)
            self.duration_minutes = diff_seconds / 60
        else:
            self.duration_minutes = 0

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
