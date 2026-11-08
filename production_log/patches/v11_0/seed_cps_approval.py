"""The CPS Approver role and the eight CPS Approval Rule rows (§6, final 08/11/2026).

Safe to re-run: the role is created only if missing; a rule row is created
only if no row of that name exists, so a row Tanuj has since edited by hand is
never overwritten. Reaches outside the app's own doctypes (Role), so it is also
called from ``install.after_install`` - runbook trap 7.

Neema's ``CPS Approver`` role is NOT granted here: adding a role to a live user
is a decision for Tanuj in the UI, and the role grants nothing on Desk anyway
(her rules name her as ``approver_user``).
"""

import frappe

from production_log.job_card_tracking import cps_approval_rules as rules

RULE = "CPS Approval Rule"


def execute():
	ensure_role(rules.APPROVER_ROLE, "Marker role: may be named as approver by a CPS Approval Rule. Grants nothing on Desk.")
	ensure_role(rules.DEFAULT_MANAGEMENT_ROLE)
	seed_rules()
	frappe.db.commit()


def ensure_role(role_name, description=None):
	if frappe.db.exists("Role", role_name):
		return
	role = frappe.new_doc("Role")
	role.role_name = role_name
	role.desk_access = 1
	if description and role.meta.has_field("description"):
		role.description = description
	role.insert(ignore_permissions=True)
	print("Role created: {0}".format(role_name))


def seed_rules():
	if not frappe.db.exists("DocType", RULE):
		return
	for values in rules.seeded():
		if frappe.db.exists(RULE, values["rule_name"]):
			continue
		row = dict(values)
		# A named approver who does not exist on this site becomes "absent" and
		# the rule's fallback applies - record the row anyway, blank the link.
		if row.get("approver_user") and not frappe.db.exists("User", row["approver_user"]):
			print("CPS Approval Rule {0}: approver {1} not on this site, left blank".format(row["rule_name"], row["approver_user"]))
			row["approver_user"] = None
		doc = frappe.new_doc(RULE)
		doc.update(row)
		doc.insert(ignore_permissions=True)
		print("CPS Approval Rule created: {0}".format(row["rule_name"]))
