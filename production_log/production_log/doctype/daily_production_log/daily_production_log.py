import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class DailyProductionLog(Document):
    def validate(self):
        self._set_defaults()
        self._check_duplicate()
        self._calculate_summaries()

    def on_submit(self):
        self.status = "Submitted"
        self.db_set("status", "Submitted")
        frappe.msgprint(_("Production Log {0} has been submitted.").format(self.name))
        self._send_submit_notification()

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_defaults(self):
        if not self.production_date:
            self.production_date = today()
        if not self.production_manager:
            self.production_manager = frappe.session.user
        if not self.status:
            self.status = "Draft"

    def _check_duplicate(self):
        """Prevent two non-cancelled logs for the same date + shift."""
        filters = {
            "production_date": self.production_date,
            "shift": self.shift,
            "docstatus": ["!=", 2],
        }
        if not self.is_new():
            filters["name"] = ["!=", self.name]

        existing = frappe.db.get_value("Daily Production Log", filters, "name")
        if existing:
            frappe.throw(
                _("Production log for {0} - {1} shift already exists: {2}").format(
                    self.production_date, self.shift, existing
                )
            )

    def _calculate_summaries(self):
        entries = self.production_entries or []
        self.total_entries = len(entries)

        total_reels = 0
        total_full_reams = 0
        total_incomplete = 0

        for entry in entries:
            num_reels = int(entry.number_of_reels or 1)
            total_reels += num_reels

            # Sum full reams across active reels
            for i in range(1, num_reels + 1):
                full_reams = entry.get(f"r{i}_full_reams") or 0
                total_full_reams += int(full_reams)

                incomplete = entry.get(f"r{i}_incomplete_reel") or 0
                total_incomplete += int(incomplete)

        self.total_reels_processed = total_reels
        self.total_full_reams = total_full_reams
        self.total_incomplete_reels = total_incomplete

    def _send_submit_notification(self):
        try:
            recipients = _get_production_manager_emails()
            if not recipients:
                return

            subject = _("Production Log Submitted: {0}").format(self.name)
            message = _(
                """
                <p>Production Log <strong>{name}</strong> has been submitted.</p>
                <ul>
                    <li>Date: {date}</li>
                    <li>Shift: {shift}</li>
                    <li>Manager: {manager}</li>
                    <li>Total Entries: {entries}</li>
                    <li>Total Reels: {reels}</li>
                    <li>Total Full Reams: {reams}</li>
                    <li>Incomplete Reels: {incomplete}</li>
                </ul>
                """
            ).format(
                name=self.name,
                date=self.production_date,
                shift=self.shift,
                manager=self.production_manager,
                entries=self.total_entries,
                reels=self.total_reels_processed,
                reams=self.total_full_reams,
                incomplete=self.total_incomplete_reels,
            )

            frappe.sendmail(
                recipients=recipients,
                subject=subject,
                message=message,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Production Log Submit Notification")


# ------------------------------------------------------------------
# Module-level hooks (used in hooks.py doc_events)
# ------------------------------------------------------------------

def validate(doc, method=None):
    doc.validate()


def on_submit(doc, method=None):
    doc.on_submit()


def on_cancel(doc, method=None):
    doc.on_cancel()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_production_manager_emails():
    users = frappe.db.sql(
        """
        SELECT DISTINCT u.email
        FROM `tabUser` u
        INNER JOIN `tabHas Role` hr ON hr.parent = u.name
        WHERE hr.role = 'Production Manager'
          AND u.enabled = 1
          AND u.email IS NOT NULL
          AND u.email != ''
        """,
        as_dict=True,
    )
    return [u.email for u in users]
