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
	from production_log.production_floor import install as production_floor

	setup_monobox.execute()

	# The Production Floor module seeds its own roles, Settings Single, machine
	# master and Select options. Called here rather than left to its patch for
	# the reason in this function's docstring: on a fresh install the patch is
	# stamped done without running.
	production_floor.after_install()

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
	from production_log.production_floor import install as production_floor

	setup_monobox.set_default_print_format()
	backfill_die_names()
	backfill_die_setup_status()
	retire_dies_stopgap_client_script()
	production_floor.after_migrate()


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
	fields = ["name", "length", "width", "across_ups", "round_ups", "teeth", "custom_die_name"]
	for die in frappe.get_all("Dies", fields=fields):
		derived = get_die_name(die.length, die.width, die.across_ups, die.round_ups, die.teeth)
		if (die.custom_die_name or "") == derived:
			continue
		frappe.db.set_value("Dies", die.name, "custom_die_name", derived, update_modified=False)
		updated += 1

	if updated:
		print(f"Dies: Die Name backfilled on {updated} record(s)")


def backfill_die_setup_status():
	"""Fill Setup Status on dies saved before the field existed.

	Same reasoning as backfill_die_names: the field arrives with
	sync_fixtures, which runs after post_model_sync patches, so a patch
	cannot do this.
	"""
	if not frappe.db.has_column("Dies", "custom_setup_status"):
		return

	from production_log.job_card_tracking.doctype.dies.dies import get_setup_status

	updated = 0
	fields = ["name", "length", "across_ups", "round_ups", "teeth", "custom_setup_status"]
	for die in frappe.get_all("Dies", fields=fields):
		derived = get_setup_status(die.length, die.across_ups, die.round_ups, die.teeth)
		if (die.custom_setup_status or "") == derived:
			continue
		frappe.db.set_value("Dies", die.name, "custom_setup_status", derived, update_modified=False)
		updated += 1

	if updated:
		print(f"Dies: Setup Status backfilled on {updated} record(s)")


def retire_dies_stopgap_client_script():
	"""Delete the transitional Client Scripts now that dies.js ships in the app.

	Created live on 2026-08-17 so the preview, layout and list status worked
	before this deploy. They carry the same code, guarded by
	``window.__VCL_DIES_VIZ__`` / ``window.__VCL_DIES_LIST__``,
	so leaving it would be harmless but duplicated — and a second copy of a
	form script is exactly how the two versions drift.
	"""
	names = [
		"Dies — Die Name, Preview & Layout (stopgap)",
		"Dies — List status (stopgap)",
	]
	for name in names:
		if frappe.db.exists("Client Script", name):
			frappe.delete_doc("Client Script", name, ignore_permissions=True)
			print(f"Deleted transitional Client Script: {name}")
	frappe.db.commit()
