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

# Client Scripts on core DocTypes
# -------------------------------
# Desk-side CPS behaviour: the filtered specification list and price preview on
# Sales Order lines, and the control explanation and specification navigation on
# Item. Both are advisory — every value they set is re-derived server-side by
# so_spec_control on save and submit — and both are inert on a site where the
# custom fields have not landed yet.
doctype_js = {
	"Sales Order": "public/js/sales_order_cps.js",
	"Item": "public/js/item_cps.js",
}

# Document Events
# ---------------
# Hook on document methods and events
# CPS control over Sales Order lines lives here, not in the Compass API, because
# Compass is only one of four write paths - Desk, REST and Data Import must hit
# the same rules. Every handler is inert until Selling Settings
# custom_cps_control_enabled is ticked.
doc_events = {
	"Workstation Type": {
		"validate": "production_log.api.workstation_type.validate_stage_position",
	},
	"Sales Order": {
		"validate": "production_log.job_card_tracking.so_spec_control.validate",
		"on_submit": "production_log.job_card_tracking.so_spec_control.on_submit",
		"on_cancel": "production_log.job_card_tracking.so_spec_control.on_cancel",
	},
	"Item": {
		"validate": [
			# Config first: an Item that requires a specification without naming
			# which kind is refused before anything is derived from it.
			"production_log.job_card_tracking.so_spec_control.validate_item_config",
			"production_log.job_card_tracking.so_spec_control.derive_item_control_flag",
		],
	},
	"Item Group": {
		"validate": "production_log.job_card_tracking.so_spec_control.validate_item_group_config",
		"on_update": "production_log.job_card_tracking.so_spec_control.enqueue_group_rederive",
	},
}

# Scheduled Tasks
# ---------------
scheduler_events = {
	# EOD Gemba PDF auto-generated at 17:00 EAT daily + pushed to Telegram.
	# Per White Paper v4 §4.4. Cron in EAT = UTC+3.
	"cron": {
		"0 14 * * *": [  # 14:00 UTC = 17:00 EAT
			"production_log.api.gemba.scheduled_eod_run",
		],
	},
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
fixtures = [
	{
		"dt": "Print Format",
		"filters": [
			[
				"name", "in", [
					"Carton Job Card",
					# v2 is the reworked carton traveller. Source of truth for the markup is
					# carton_jobcard_v2.html alongside this doctype; the fixture is what a
					# deploy actually applies.
					"Carton Jobcard v2",
					"Label Job Traveller",
					"Computer Paper Job Traveller",
					# NOTE: "ETR Job Traveller" is declared here but has never been
					# exported into fixtures/print_format.json. Left as-is rather than
					# silently starting to overwrite the live copy.
					"ETR Job Traveller",
					# Monobox: source of truth is monobox_job_traveller.html alongside
					# the doctype, exported here by scripts/build_monobox_print_format.py.
					"Monobox Job Traveller",
					"Customer Product Spec",
					"Customer Product Spec (Calculated)",
				]
			]
		],
	},
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
					"Job Card ETR",
					# CPS carried 17 Custom Fields that existed only in the database —
					# linked_item, the unified print_type/print_side (White Paper v4
					# §2.1), the two weight fields, revision_notes, and the Board Plan.
					# Rebuilding the site from this app would not have reproduced them.
					"Customer Product Specification",
				]
			]
		],
	},
	{
		# CPS form behaviour that lives as Client Script records rather than in the
		# bundled JS. The Board Plan script is deliberately NOT here — it moved into
		# customer_product_specification.js so it has a single source of truth.
		# Being a fixture means migrate overwrites Desk edits to these two.
		"dt": "Client Script",
		"filters": [["dt", "in", ["Customer Product Specification"]]],
	},
]

# Boot Session
# ------------
# boot_session = "production_log.boot.boot_session"
