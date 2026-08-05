"""Patch v9_0: finish the Monobox line off after its doctypes sync.

The doctypes, the CPS fields and the print format all arrive through the normal
migrate — DocType JSON syncs, fixtures overwrite. Two things do not, and they are
what this patch is for:

  1. the default print format Property Setter, so hitting Print on a Monobox job
     card gives the traveller without anyone picking it from a list;
  2. the workspace links, so the new doctypes are reachable without knowing the
     URL.

Idempotent, and safe to run before the fixtures land: everything is guarded on
the target existing. Also called from ``after_install`` — installing an app
stamps every patch as done WITHOUT running it, so a fresh site would otherwise
be built without any of this and migrate would never retry.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from production_log.job_card_tracking.cps_rules import CPS_PRODUCT_TYPES, PRODUCT_TYPE_FIELD

WORKSPACE = "VCL Production"

LINKS = [
	{
		"label": "Job Card Monobox",
		"link_to": "Job Card Monobox",
		"link_type": "DocType",
		"type": "Link",
		"onboard": 0,
	},
	{
		"label": "Monobox Die",
		"link_to": "Monobox Die",
		"link_type": "DocType",
		"type": "Link",
		"onboard": 0,
	},
]


def execute():
	widen_cps_product_type_options()
	set_default_print_format()
	add_workspace_links()
	frappe.db.commit()


def widen_cps_product_type_options():
	"""Teach Item Group and Item that Monobox exists.

	``cps_rules`` states the invariant plainly: Item Group, Item and the
	specification's own ``product_type`` must agree on this list, or a
	specification could be of a kind no Item can ever ask for. The CPS side
	arrives with the DocType JSON; the other two are Custom Fields created by
	v8_0, so their options only move when something moves them.

	Query the Custom Field doctype directly — ``get_meta`` returns standard
	DocFields only, so a custom_* field reads as missing when it is right there.
	"""
	options = "\n" + "\n".join(CPS_PRODUCT_TYPES)

	for name in frappe.get_all(
		"Custom Field",
		filters={"fieldname": PRODUCT_TYPE_FIELD},
		pluck="name",
	):
		field = frappe.get_doc("Custom Field", name)
		if field.options == options:
			continue
		field.options = options
		field.save(ignore_permissions=True)
		frappe.clear_cache(doctype=field.dt)


def set_default_print_format():
	if not frappe.db.exists("DocType", "Job Card Monobox"):
		return

	if not frappe.db.exists("Print Format", "Monobox Job Traveller"):
		# Fixtures sync AFTER post_model_sync patches, so on the migrate that
		# first ships the format this is always false and this function always
		# skips — which is what happened on the 2026-08-05 deploy. The real
		# caller is ``install.after_migrate``; leaving the call here as well is
		# harmless and keeps a fresh install working.
		return

	make_property_setter(
		doctype="Job Card Monobox",
		fieldname="",
		property="default_print_format",
		value="Monobox Job Traveller",
		property_type="Data",
		for_doctype=True,
		validate_fields_for_doctype=False,
	)

	frappe.clear_cache(doctype="Job Card Monobox")


def add_workspace_links():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	workspace = frappe.get_doc("Workspace", WORKSPACE)
	existing = {row.link_to for row in workspace.links if row.link_to}

	added = False
	for link in LINKS:
		if link["link_to"] in existing:
			continue
		if not frappe.db.exists("DocType", link["link_to"]):
			continue
		workspace.append("links", link)
		added = True

	if added:
		workspace.save(ignore_permissions=True)
