from . import __version__ as app_version

app_name = "production_log"
app_title = "Production Log"
app_publisher = "VCL"
app_description = "Production and Job Card Management App for Vimit Converters Ltd"
app_email = "admin@vcl.co.ke"
app_license = "MIT"
app_version = app_version

# Required Apps
# -------------
required_apps = ["erpnext"]

# Includes in <head>
# ------------------
# include_js = {"page,html" : "public/js/file.js"}
# include_css = {"page,html" : "public/css/file.css"}

# Home Pages
# ----------
# home_page = "login"

# Generators
# ----------
# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------
# add methods and filters to jinja environment
# jinja = {
#     "methods": "production_log.utils.jinja_methods",
#     "filters": "production_log.utils.jinja_filters"
# }

# Installation
# ------------
# before_install = "production_log.install.before_install"
after_install = "production_log.install.after_install"

# Uninstallation
# ------------
# before_uninstall = "production_log.install.before_uninstall"
# after_uninstall = "production_log.install.after_uninstall"

# Desk Notifications
# ------------------
# notification_config = "production_log.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways
# permission_query_conditions = {
#     "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
# has_permission = {
#     "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes
override_doctype_class = {
    # Production Log module
    "Daily Production Log": "production_log.production_log.doctype.daily_production_log.daily_production_log.DailyProductionLog",
    "Production Entry": "production_log.production_log.doctype.production_entry.production_entry.ProductionEntry",
    # Job Card Tracking module
    "Job Card Production Entry": "production_log.job_card_tracking.doctype.job_card_production_entry.job_card_production_entry.JobCardProductionEntry",
}

# Document Events
# ---------------
# Hook on document methods and events
doc_events = {
    "Daily Production Log": {
        "validate": "production_log.production_log.doctype.daily_production_log.daily_production_log.validate",
        "on_submit": "production_log.production_log.doctype.daily_production_log.daily_production_log.on_submit",
        "on_cancel": "production_log.production_log.doctype.daily_production_log.daily_production_log.on_cancel",
    }
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "daily": [
        "production_log.tasks.send_daily_production_summary"
    ],
}

# Testing
# -------
# before_tests = "production_log.install.before_tests"

# Overriding Methods
# ------------------------------
# override_whitelisted_methods = {
#     "frappe.desk.doctype.event.event.get_events": "production_log.event.get_events"
# }

# Fixtures
# --------
# No fixtures needed — Production Station replaced by ERPNext Workstation DocType.
# fixtures = []

# Boot Session
# ------------
# boot_session = "production_log.boot.boot_session"
