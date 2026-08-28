"""Install and migrate hooks.

Everything here is idempotent. `bench migrate` runs it on every deploy, and
on a site that already has real production data it must change nothing but
the things this module owns: the two roles, the machine master's initial contents, and
the Select options driven by Settings.
"""

import frappe

from production_log.production_floor.setup.seed import seed_machines

ROLES = [
	("VCL Production User", "Enters and updates today's production."),
	("VCL Production Manager", "Everything a user can do, plus closing the day and the masters."),
]


# ⛔ ORDER IS LOAD-BEARING: apply_select_options() BEFORE seed_machines().
#
# The live `department` options are Property Setters, not the DocType JSON.
# `seed_machines` inserts a VCL Production Machine, and `_validate_selects`
# checks the value against the CURRENT meta - so seeding a machine in a
# department the Property Setter has not been widened to yet throws, and a
# throw inside `after_migrate` aborts the whole migrate for every app.
#
# This is not hypothetical. Reversing these two lines took the production site
# down on 2026-08-28:
#
#   ValidationError: Department cannot be "Monobox".
#                    It should be one of "Computer", "Offset", "Carton", "Labels"
#
# `apply_select_options()` ends with `frappe.clear_cache()`, which is what makes
# the widened options visible to the insert that follows.
def after_install():
	create_roles()
	ensure_settings()
	apply_select_options()
	seed_machines()
	frappe.db.commit()


def after_migrate():
	create_roles()
	ensure_settings()
	apply_select_options()
	# Seeding on migrate too, not just install. `seed_machines` only ever adds
	# what is missing, and without this a department added in a later release
	# (Monobox, 2026-08) reaches an existing site with no machines under it -
	# which shows as a department you cannot add a job to. Retire a machine by
	# unticking `active`, not by deleting it, or this will bring it back.
	seed_machines()
	frappe.db.commit()


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
	from production_log.production_floor.doctype.vcl_production_settings.vcl_production_settings import (
		apply_select_options as apply,
	)

	apply()
