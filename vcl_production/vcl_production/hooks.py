from . import __version__ as app_version

app_name = "vcl_production"
app_title = "VCL Production"
app_publisher = "VCL"
app_description = "VCL Production Lite — structured daily production entry and reporting for Vimit Converters Ltd"
app_email = "admin@vcl.co.ke"
app_license = "MIT"
app_version = app_version

# Required Apps
# -------------
# Deliberately empty. This app runs on plain Frappe. ERPNext may well be
# installed on the same site — it is on VCL's — but nothing here reads it,
# links to it, or breaks without it. When the integration lands it arrives as
# optional Link fields, not as a dependency.
required_apps = []

# Includes in <head>
# ------------------
# Plain file rather than a bundle, so the screen works on a site that has not
# had `bench build` run since the app was installed.
app_include_css = "/assets/vcl_production/css/vcl_production.css"

# Installation
# ------------
after_install = "vcl_production.install.after_install"
after_migrate = "vcl_production.install.after_migrate"

# Uninstallation
# --------------
before_uninstall = "vcl_production.install.before_uninstall"
