"""Bring an already-installed site up to the same state a fresh install gets.

Idempotent: on a site that already has the roles, the machines and the
Property Setters, this does nothing.
"""

import frappe

from production_log.production_floor.install import apply_select_options, create_roles, ensure_settings
from production_log.production_floor.setup.seed import seed_machines


def execute():
	create_roles()
	ensure_settings()
	seed_machines()
	apply_select_options()
	frappe.db.commit()
