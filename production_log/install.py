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
	backfill_die_names()
	retire_dies_stopgap_client_script()


def backfill_die_names():
	"""Fill Die Name on dies saved before the field existed.

	Runs here, not in a patch: custom_die_name arrives with sync_fixtures,
	which Frappe runs AFTER post_model_sync patches — a patch would look for a
	field that does not exist yet, skip, and be marked done forever.

	Idempotent: only rows whose stored value differs are touched, and the
	write is a plain db_set so nothing re-validates or bumps modified.
	"""
	if not frappe.db.has_column("Dies", "custom_die_name"):
		return

	from production_log.job_card_tracking.doctype.dies.dies import get_die_name

	updated = 0
	for die in frappe.get_all("Dies", fields=["name", "length", "width", "custom_die_name"]):
		derived = get_die_name(die.length, die.width)
		if (die.custom_die_name or "") == derived:
			continue
		frappe.db.set_value("Dies", die.name, "custom_die_name", derived, update_modified=False)
		updated += 1

	if updated:
		print(f"Dies: Die Name backfilled on {updated} record(s)")


def retire_dies_stopgap_client_script():
	"""Delete the transitional Client Script now that dies.js ships in the app.

	Created live on 2026-08-17 so the preview and layout worked before this
	deploy. It carries the same code guarded by ``window.__VCL_DIES_VIZ__``,
	so leaving it would be harmless but duplicated — and a second copy of a
	form script is exactly how the two versions drift.
	"""
	name = "Dies — Die Name, Preview & Layout (stopgap)"
	if frappe.db.exists("Client Script", name):
		frappe.delete_doc("Client Script", name, ignore_permissions=True)
		print(f"Deleted transitional Client Script: {name}")
	frappe.db.commit()
