import frappe
from frappe.utils import add_days, getdate, today


def send_daily_production_summary():
    """
    Scheduled daily task: send summary email of previous day's production
    to all users with the Production Manager role.
    """
    yesterday = add_days(today(), -1)

    logs = frappe.get_all(
        "Daily Production Log",
        filters={"production_date": yesterday, "docstatus": 1},
        fields=["name", "shift", "production_manager", "total_entries",
                "total_reels_processed", "total_full_reams", "total_incomplete_reels"],
    )

    if not logs:
        return

    recipients = _get_production_manager_emails()
    if not recipients:
        return

    subject = f"Production Summary – {yesterday}"
    rows = ""
    for log in logs:
        rows += f"""
        <tr>
            <td>{log.name}</td>
            <td>{log.shift}</td>
            <td>{log.production_manager}</td>
            <td>{log.total_entries}</td>
            <td>{log.total_reels_processed}</td>
            <td>{log.total_full_reams}</td>
            <td>{log.total_incomplete_reels}</td>
        </tr>"""

    message = f"""
    <h3>Daily Production Summary for {yesterday}</h3>
    <table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">
        <thead>
            <tr>
                <th>Log</th><th>Shift</th><th>Manager</th>
                <th>Entries</th><th>Reels</th><th>Full Reams</th><th>Incomplete</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
    )


def _get_production_manager_emails():
    """Return email list of all active Production Manager users."""
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
