import frappe


def after_install():
    """Run after app installation."""
    frappe.msgprint(
        "Production Log installed. "
        "Please configure your Workstations in Manufacturing > Workstation "
        "and set 'Job Capacity' to the maximum number of reels each station can run."
    )
