import frappe


def after_install():
	"""Run after app installation.

	Anything the app needs at install time belongs here, not in a patch:
	``install_app()`` marks every line of patches.txt as completed WITHOUT
	running it, so a patch that reaches outside the app's own doctypes never
	executes on a fresh site and migrate will never retry it — the Patch Log
	already says it is done.
	"""
	from production_log.patches.v9_0 import setup_monobox

	setup_monobox.execute()

	frappe.msgprint(
		"Production Log installed. "
		"Open the VCL Production workspace to start creating Customer "
		"Product Specifications and Job Cards."
	)
