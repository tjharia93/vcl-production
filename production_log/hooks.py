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
jinja = {
    "methods": [
        "production_log.utils.get_carton_svg"
    ]
}

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
# override_doctype_class = {}

# Document Events
# ---------------
# Hook on document methods and events

# Scheduled Tasks
# ---------------
# scheduler_events = {}

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
fixtures = [
	{"dt": "Print Format", "filters": [["name", "in", ["Carton Job Card"]]]},
	{
		"dt": "Custom Field",
		"filters": [
			[
				"dt", "in", [
					"Workstation Type",
					"Workstation",
					"Job Card Computer Paper",
					"Job Card Label",
					"Job Card Carton",
				]
			]
		],
	},
]

# Boot Session
# ------------
# boot_session = "production_log.boot.boot_session"
