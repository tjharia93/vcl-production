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


def after_migrate():
	"""Run at the end of every migrate, after fixtures have synced.

	The default print format Property Setter cannot be set from a patch. Frappe
	runs post_model_sync patches BEFORE sync_fixtures, so on the migrate that
	first ships a Print Format the patch looks for a record that does not exist
	yet, skips, and is then marked done forever. That is exactly what happened
	to the Monobox traveller on the 2026-08-05 deploy: the doctypes, workspace
	links and Custom Field options all landed, and the one step gated on the
	fixture silently did not.

	Idempotent — make_property_setter overwrites, and the guards make a missing
	target a no-op.
	"""
	from production_log.patches.v9_0 import setup_monobox

	setup_monobox.set_default_print_format()
	frappe.db.commit()
