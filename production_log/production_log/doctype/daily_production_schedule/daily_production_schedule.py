import frappe
from frappe.model.document import Document


class DailyProductionSchedule(Document):
    def validate(self):
        self.validate_unique_machine_day()
        self.calculate_totals()

    def validate_unique_machine_day(self):
        if not self.workstation or not self.schedule_date:
            return
        existing = frappe.db.exists(
            "Daily Production Schedule",
            {
                "workstation": self.workstation,
                "schedule_date": self.schedule_date,
                "name": ("!=", self.name),
                "docstatus": ("!=", 2),
            },
        )
        if existing:
            frappe.throw(
                f"A schedule already exists for {self.workstation} on {self.schedule_date}: {existing}"
            )

    def calculate_totals(self):
        self.total_planned_qty = sum(
            (row.planned_qty or 0) for row in self.schedule_lines
        )
        self.total_planned_hours = sum(
            (row.estimated_hours or 0) for row in self.schedule_lines
        )
        if self.available_hours:
            self.utilization_pct = (
                self.total_planned_hours / self.available_hours
            ) * 100
        else:
            self.utilization_pct = 0
