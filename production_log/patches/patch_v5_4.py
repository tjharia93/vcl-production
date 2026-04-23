"""
Patch v5_4: Repair the stale `VCL Production` Workspace row.

Observed on vimitconverters.frappe.cloud on 2026-04-23: every desk route
renders an empty `#body` because `make_sidebar` → `get_path(item.icon)`
throws `TypeError: Cannot read properties of undefined (reading 'public')`.
Root cause: the `tabWorkspace` row `"VCL Production"` still carries
`app = "vcl_job_cards"` (the pre-rename app) and `type = null`.
`vcl_job_cards` is not installed, so `frappe.boot.desktop_icon_urls`
has no entry for it, and the sidebar builder crashes.

The prior rename patch (v1_0.rename_workspace_to_vcl_production) did
`frappe.rename_doc` but never rewrote `app` or `type`, and the on-disk
workspace JSON historically omitted both keys, so `bench migrate` /
`reload_doc` had nothing to overwrite them with. The JSON is corrected
in the same commit as this patch (adds `"app": null` + `"type": "Workspace"`).

This patch unblocks existing sites by setting the two columns directly,
then reloads the now-complete JSON and clears cache so bootinfo stops
handing the stale app name to `make_sidebar`.

Idempotent: `set_value` on already-correct values is a no-op; re-running
is safe.
"""

import frappe


def execute():
	if frappe.db.exists("Workspace", "VCL Production"):
		frappe.db.set_value(
			"Workspace",
			"VCL Production",
			{"app": None, "type": "Workspace"},
		)

	frappe.reload_doc("production_log", "workspace", "vcl_production")
	frappe.clear_cache()
	frappe.db.commit()
