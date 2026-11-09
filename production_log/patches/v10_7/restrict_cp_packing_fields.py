"""Keep Computer Paper packing away from sales roles (CR21, TRK-00342).

Packing (sets per carton), the weight per carton derived from it and the
carton tare are production facts. Sales sees the job card through the Sales
Copy, which never prints them. This patch closes the other routes: the Desk
form, the Standard print, list/report views and frappe.client.get, all of
which honour field permlevels.

Three things, all idempotent:

1. Packing fields move to permlevel 1. DocFields are set in the DocType JSON,
   which model sync applies. Custom Fields are set here AND in
   fixtures/custom_field.json, because fixtures sync AFTER this patch and
   would otherwise put permlevel 0 back.
2. Permlevel-1 Custom DocPerm rows go to the management, release and
   production roles. The live site already has Custom DocPerm on both
   doctypes, and Frappe then ignores the JSON permissions entirely, so the
   JSON rows alone would do nothing live. Frappe refuses a level-1 rule for a
   role with no level-0 rule, so VCL Management Team and Release to
   Production also get level-0 read/print. Rows are only ever ADDED: an
   existing row is left exactly as it is, so a hand-tuned permission survives
   a re-run.
3. The two other Computer Paper print formats that print packing are
   disabled. "Computer Paper Job Traveller" (v1) has been unused since v2
   became the default, and "Computer Paper Job Card" (May 2026, live only)
   would let any reader print packing. A Jinja print format reads ``doc``
   directly, so permlevels do not hide what it prints. The Sales Copy and
   Production Copy replace both.

Also called from install.after_install, so the install-stamping trap cannot
leave a fresh site unrestricted.
"""

import frappe

from production_log.job_card_tracking.cp_print import MANAGEMENT_ROLE, RELEASE_ROLE

JC = "Job Card Computer Paper"
CPS = "Customer Product Specification"

# Custom Fields moved to permlevel 1 (DocFields are in the JSON).
CUSTOM_FIELDS = {
	JC: ("empty_carton_weight",),
	CPS: (
		"sets_per_carton",
		"packing_carton_tare_kg",
		"net_product_weight_per_carton_kg",
		"gross_packed_weight_per_carton_kg",
	),
}

# The DocFields the JSON moves to permlevel 1, listed so verify() can check
# the effect on the live meta.
DOC_FIELDS = {
	JC: ("packing", "weight_per_carton"),
	CPS: ("standard_packing", "standard_weight_per_carton"),
}

_LEVEL0_VIEW = {"read": 1, "print": 1, "report": 1, "export": 0, "email": 1}
_RW = {"read": 1, "write": 1}
_R = {"read": 1}

# (doctype, role, permlevel, rights). A row whose role does not exist on the
# site is skipped with a message rather than failing the migrate.
RULES = (
	(JC, MANAGEMENT_ROLE, 0, _LEVEL0_VIEW),
	(JC, RELEASE_ROLE, 0, _LEVEL0_VIEW),
	(JC, "System Manager", 1, _RW),
	(JC, MANAGEMENT_ROLE, 1, _RW),
	(JC, RELEASE_ROLE, 1, _RW),
	(JC, "Manufacturing Manager", 1, _RW),
	(JC, "Manufacturing User", 1, _R),
	(CPS, MANAGEMENT_ROLE, 0, _LEVEL0_VIEW),
	(CPS, RELEASE_ROLE, 0, _LEVEL0_VIEW),
	(CPS, "System Manager", 1, _RW),
	(CPS, MANAGEMENT_ROLE, 1, _RW),
	(CPS, RELEASE_ROLE, 1, _RW),
	(CPS, "Manufacturing Manager", 1, _R),
)

FORMATS_TO_DISABLE = ("Computer Paper Job Traveller", "Computer Paper Job Card")


def execute():
	set_custom_field_permlevels()
	add_permission_rules()
	disable_leaking_print_formats()


def set_custom_field_permlevels():
	for dt, fields in CUSTOM_FIELDS.items():
		for fieldname in fields:
			name = f"{dt}-{fieldname}"
			if frappe.db.exists("Custom Field", name) and frappe.db.get_value("Custom Field", name, "permlevel") != 1:
				frappe.db.set_value("Custom Field", name, "permlevel", 1, update_modified=False)
		frappe.clear_cache(doctype=dt)


def add_permission_rules():
	from frappe.permissions import setup_custom_perms

	for dt in {r[0] for r in RULES}:
		# Copies the JSON DocPerm into Custom DocPerm if the site has none, so
		# adding one row never silently drops every other permission.
		setup_custom_perms(dt)

	# Level 0 before level 1: Frappe refuses a higher level for a role with no
	# level-0 rule.
	for dt, role, level, rights in sorted(RULES, key=lambda r: r[2]):
		if not frappe.db.exists("Role", role):
			print(f"restrict_cp_packing_fields: role {role!r} missing, rule on {dt} level {level} skipped")
			continue
		if frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role, "permlevel": level, "if_owner": 0}):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": dt,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": level,
				"if_owner": 0,
				**rights,
			}
		).insert(ignore_permissions=True)

	for dt in {r[0] for r in RULES}:
		frappe.clear_cache(doctype=dt)


def disable_leaking_print_formats():
	for name in FORMATS_TO_DISABLE:
		if frappe.db.exists("Print Format", name) and not frappe.db.get_value("Print Format", name, "disabled"):
			frappe.db.set_value("Print Format", name, "disabled", 1, update_modified=False)


def verify():
	"""What is still open. Run from a bench console after migrate; an empty list means closed."""
	problems = []
	for dt, fields in {**DOC_FIELDS}.items():
		meta = frappe.get_meta(dt)
		for f in fields + CUSTOM_FIELDS.get(dt, ()):
			df = meta.get_field(f)
			if df and (df.permlevel or 0) != 1:
				problems.append(f"{dt}.{f} permlevel {df.permlevel}")
	for name in FORMATS_TO_DISABLE:
		if frappe.db.exists("Print Format", name) and not frappe.db.get_value("Print Format", name, "disabled"):
			problems.append(f"Print Format {name} still enabled")
	return problems
