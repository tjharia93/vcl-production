import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, get_time


class ProductionEntry(Document):
    def validate(self):
        self._validate_times()
        self._validate_station_capacity()
        self._validate_reel_weights()

    def _validate_times(self):
        if not self.start_time or not self.end_time:
            return

        start = get_time(self.start_time)
        end = get_time(self.end_time)

        # Calculate duration in decimal hours
        # Handle overnight shifts: if end < start, assume next day
        start_seconds = start.hour * 3600 + start.minute * 60 + start.second
        end_seconds = end.hour * 3600 + end.minute * 60 + end.second

        if end_seconds <= start_seconds:
            # Overnight shift: add 24 hours to end
            diff_seconds = (86400 - start_seconds) + end_seconds
        else:
            diff_seconds = end_seconds - start_seconds

        self.duration_hours = round(diff_seconds / 3600, 2)

    def _validate_station_capacity(self):
        if not self.station or not self.number_of_reels:
            return

        max_reels = frappe.db.get_value("Workstation", self.station, "production_capacity")
        if not max_reels:
            return

        if int(self.number_of_reels) > int(max_reels):
            frappe.throw(
                _("Workstation {0} can only run {1} reel(s) simultaneously. You selected {2}.").format(
                    self.station, max_reels, self.number_of_reels
                )
            )

    def _validate_reel_weights(self):
        num_reels = int(self.number_of_reels or 1)
        reel_prefixes = ["r1", "r2", "r3", "r4"]

        for i, prefix in enumerate(reel_prefixes[:num_reels], start=1):
            start_weight = self.get(f"{prefix}_start_weight")
            end_weight = self.get(f"{prefix}_end_weight")

            if start_weight and end_weight:
                if end_weight >= start_weight:
                    frappe.throw(
                        _("Reel {0}: End weight ({1} kg) must be less than start weight ({2} kg).").format(
                            i, end_weight, start_weight
                        )
                    )
