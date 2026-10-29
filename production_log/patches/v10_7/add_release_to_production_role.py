"""Create the "Release to Production" role (TRK-00342, Option A).

Its holders, VCL Management and the delegates Tanuj names, release a Computer
Paper job card to the floor. Only they and the production roles may print the
Production Copy or read the packing fields. See
production_log.job_card_tracking.cp_print.

This creates the role and nothing else. No user is granted it here: Tanuj
assigns the holders.

Idempotent. Also called from install.after_install, because install_app()
stamps every patch done without running it (the install-stamping trap).
"""

import frappe

ROLE = "Release to Production"


def execute():
	if frappe.db.exists("Role", ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": ROLE,
			"desk_access": 1,
			"is_custom": 0,
		}
	).insert(ignore_permissions=True)
	print(f"Created role: {ROLE}")
