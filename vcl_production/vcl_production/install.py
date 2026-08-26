"""Install and migrate hooks.

Everything here is idempotent. `bench migrate` runs it on every deploy, and
on a site that already has real production data it must change nothing but
the things it owns: the two roles, the machine master's initial contents, and
the Select options driven by Settings.
"""

import frappe

from vcl_production.setup.seed import seed_machines

ROLES = [
	("VCL Production User", "Enters and updates today's production."),
	("VCL Production Manager", "Everything a user can do, plus closing the day and the masters."),
]


def after_install():
	create_roles()
	ensure_settings()
	seed_machines()
	apply_select_options()
	frappe.db.commit()


def after_migrate():
	create_roles()
	ensure_settings()
	apply_select_options()
	frappe.db.commit()


def before_uninstall():
	"""Leave the data alone; only drop what only this app could have made."""
	for role, _description in ROLES:
		if frappe.db.exists("Role", role):
			frappe.delete_doc("Role", role, ignore_permissions=True, force=True)


def create_roles():
	for role, description in ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc({
			"doctype": "Role",
			"role_name": role,
			"desk_access": 1,
			"description": description,
		}).insert(ignore_permissions=True)


def ensure_settings():
	"""Materialise the Single so its defaults are readable straight away."""
	if not frappe.db.exists("DocType", "VCL Production Settings"):
		return
	settings = frappe.get_single("VCL Production Settings")
	if not settings.departments or not settings.units:
		settings.save(ignore_permissions=True)


def apply_select_options():
	if not frappe.db.exists("DocType", "VCL Production Settings"):
		return
	from vcl_production.vcl_production.doctype.vcl_production_settings.vcl_production_settings import (
		apply_select_options as apply,
	)

	apply()
