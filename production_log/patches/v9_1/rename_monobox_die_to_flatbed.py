"""Patch v9_1: rename ``Monobox Die`` to ``Flatbed Die``.

The register was named after the first product that needed it, which was wrong
by the second. The same tool — steel rule bent into a plywood forme, struck
against a stack of sheets — cuts a monobox, a die-cut carton and a 2-ply cup
sleeve. Naming it for the tool rather than the product is what lets Carton link
it without anyone wondering why a carton points at something called Monobox.

MUST run before the model sync. ``production_log/patches.txt`` carries no
``[post_model_sync]`` header, so Frappe falls back to old-format parsing and
every patch in this app is pre_model_sync — which is exactly what a rename
needs. If section headers are ever added, this patch belongs above the
``[post_model_sync]`` line: let the sync run first and it creates a second,
empty ``Flatbed Die`` while ``tabMonobox Die`` lingers with its rows.

Idempotent, and safe on a site that never had the old name.
"""

import frappe

OLD = "Monobox Die"
NEW = "Flatbed Die"


def execute():
	rename_doctype()
	repoint_workspace_links()
	frappe.db.commit()


def rename_doctype():
	if not frappe.db.exists("DocType", OLD):
		# Fresh site, or already renamed. Either way there is nothing to move.
		return

	if frappe.db.exists("DocType", NEW):
		# Both names present means the sync already created the new one — the
		# ordering this patch depends on did not hold. Say so loudly rather
		# than merging two tables on a guess.
		frappe.log_error(
			title="Flatbed Die rename skipped",
			message=(
				f"Both '{OLD}' and '{NEW}' exist. The rename ran after the model "
				"sync, so the old table still holds any rows. Merge by hand."
			),
		)
		return

	frappe.rename_doc("DocType", OLD, NEW, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype=NEW)


def repoint_workspace_links():
	"""Workspace Link rows store the doctype name as data, not as a Link.

	``rename_doc`` rewrites Link *fields* that point at the renamed doctype;
	``Workspace Link.link_to`` is a Data column holding a doctype name, so it is
	invisible to that sweep and would be left pointing at a name that no longer
	resolves — a dead sidebar entry with no error anywhere.
	"""
	for name in frappe.get_all(
		"Workspace Link",
		filters={"link_to": OLD},
		pluck="name",
	):
		frappe.db.set_value("Workspace Link", name, "link_to", NEW, update_modified=False)
		frappe.db.set_value("Workspace Link", name, "label", NEW, update_modified=False)

	for name in frappe.get_all(
		"Workspace Shortcut",
		filters={"link_to": OLD},
		pluck="name",
	):
		frappe.db.set_value("Workspace Shortcut", name, "link_to", NEW, update_modified=False)

	frappe.clear_cache()
