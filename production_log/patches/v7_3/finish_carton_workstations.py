"""S1 follow-up patch — codify the 6 manual hotfixes applied on 2026-05-20.

Background
----------
The original v7_1.add_carton_workstations patch wrapped its inserts in a
`try/except frappe.NameError: pass` block. On the live deploy that block
silently swallowed a real error — v7_1 was recorded in Patch Log as
"done" but the 2 net-new Workstation Types and 2 Workstations were never
actually created. They were then created by hand via MCP on 2026-05-20
(see CHANGELOG_DAILY.md).

Because v7_1 is already in Patch Log it will NEVER re-run. So the prod
site has the records (hotfixed) but the git repo has no patch that would
recreate them on a FRESH install (new staging site, disaster recovery).

This patch closes that gap. It is fully idempotent:
  - On the current prod site → every record already exists → no-op.
  - On a fresh install → creates the 6 records cleanly.

Idempotency + reliability notes
-------------------------------
  - Workstation Type autoname is field-driven (field:workstation_type),
    so we set doc.workstation_type, not doc.name.
  - The product_line tag is inserted as a child row directly (explicit
    parent/parenttype/parentfield) to bypass the parent's
    validate_stage_position hook — several existing WTs share
    custom_stage_position=999 which would otherwise block the save.
  - Every step guards with frappe.db.exists() first.
"""

import frappe


PRODUCT_LINE = "Corrugation and Carton Department"

# (workstation_type name, custom_stage_position) — only the 2 net-new ones.
# The other 8 Carton-relevant Workstation Types already existed on prod.
NEW_WORKSTATION_TYPES = [
	("Slotting", 155),
	("Bundling", 170),
]

# (workstation_name, workstation_type)
NEW_WORKSTATIONS = [
	("Slotter 01", "Slotting"),
	("Bundler 01", "Bundling"),
]

# Existing Workstation Types that needed the Carton product_line tag added.
# (Plate Making was "All"-only; Sheeting was "General Stationery..."-only.)
# The other 8 already carried the Carton tag from earlier sessions.
WORKSTATION_TYPES_NEEDING_TAG = [
	"Plate Making",
	"Sheeting",
	# Harmless to list the others — _ensure_tag is a no-op when already tagged:
	"Corrugation",
	"Carton Pasting",
	"Creasing",
	"Carton Printing",
	"Carton Stitching",
	"Carton Gluing",
	"Die Cutting",
	"Lamination",
	"Slotting",
	"Bundling",
]


def execute():
	# Step 1 — net-new Workstation Types
	for ws_type, stage_position in NEW_WORKSTATION_TYPES:
		_create_workstation_type(ws_type, stage_position)

	# Step 2 — net-new Workstations
	for ws_name, ws_type in NEW_WORKSTATIONS:
		_create_workstation(ws_name, ws_type)

	# Step 3 — ensure Carton product_line tag on all Carton-relevant WTs
	for ws_type in WORKSTATION_TYPES_NEEDING_TAG:
		if frappe.db.exists("Workstation Type", ws_type):
			_ensure_product_line_tag(ws_type, PRODUCT_LINE)

	frappe.clear_cache()


def _create_workstation_type(name, stage_position):
	if frappe.db.exists("Workstation Type", name):
		return  # idempotent — already there (prod hotfix or prior run)

	doc = frappe.get_doc({
		"doctype":               "Workstation Type",
		"workstation_type":      name,
		"custom_product_line":   PRODUCT_LINE,
		"custom_stage_position": stage_position,
	})
	doc.insert(ignore_permissions=True, ignore_mandatory=True)


def _create_workstation(name, workstation_type):
	if frappe.db.exists("Workstation", name):
		return  # idempotent

	doc = frappe.get_doc({
		"doctype":             "Workstation",
		"workstation_name":    name,
		"workstation_type":    workstation_type,
		"custom_product_line": PRODUCT_LINE,
	})
	doc.insert(ignore_permissions=True, ignore_mandatory=True)


def _ensure_product_line_tag(workstation_type, product_line):
	"""Add the Workstation Product Line Tag child row if missing.

	Inserts the child row directly with explicit parent fields so the
	parent Workstation Type's validate hook (validate_stage_position) is
	NOT triggered — several WTs share custom_stage_position=999 which the
	validator would reject.
	"""
	already = frappe.db.exists(
		"Workstation Product Line Tag",
		{
			"parent":       workstation_type,
			"parenttype":   "Workstation Type",
			"parentfield":  "custom_product_line_tags",
			"product_line": product_line,
		},
	)
	if already:
		return

	tag = frappe.get_doc({
		"doctype":      "Workstation Product Line Tag",
		"parent":       workstation_type,
		"parenttype":   "Workstation Type",
		"parentfield":  "custom_product_line_tags",
		"product_line": product_line,
	})
	tag.insert(ignore_permissions=True)
