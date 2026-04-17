import frappe
from frappe.model.document import Document


class DailyProductionSchedule(Document):
    def validate(self):
        self.validate_unique_machine_day()
        self.populate_line_estimates()
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

    def populate_line_estimates(self):
        if not self.workstation:
            return

        ws_max_speed = frappe.db.get_value(
            "Workstation", self.workstation, "custom_max_speed_per_hour"
        ) or 0

        missing_rate_lines = []
        for line in self.schedule_lines:
            if line.estimated_hours:
                continue
            if not line.planned_qty or not line.production_stage:
                continue

            stage_row = frappe.db.get_value(
                "Workstation Stage",
                {"parent": line.production_stage, "workstation": self.workstation},
                ["hourly_rate", "setup_time_mins"],
                as_dict=True,
            ) or {}
            rate = stage_row.get("hourly_rate") or ws_max_speed
            setup_mins = stage_row.get("setup_time_mins") or 0

            if not rate:
                missing_rate_lines.append(line.idx)
                continue

            line.estimated_hours = round(
                (line.planned_qty / rate) + (setup_mins / 60.0), 2
            )

        if missing_rate_lines:
            frappe.msgprint(
                f"Estimated hours not calculated for line(s) "
                f"{', '.join(str(i) for i in missing_rate_lines)}: no Max Speed "
                f"on Workstation {self.workstation} and no Hourly Rate on the "
                f"matching Workstation Stage. DPS saved; update the speed "
                f"values to populate estimates.",
                title="Missing Workstation Speed",
                indicator="orange",
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
