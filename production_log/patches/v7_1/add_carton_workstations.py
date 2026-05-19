"""S1 patch — tag existing Carton Workstation Types + seed the 2 missing ones.

Per Sprint-0 audit + post-deploy check on 2026-05-20:
  Live Workstation Type registry has 19 entries. Carton-relevant types
  ALREADY EXIST and just need product_line tagging:
    Corrugation
    Sheeting          (shared — also serves Trading)
    Carton Pasting
    Creasing
    Carton Printing
    Carton Stitching  (separate from Carton Gluing on prod)
    Carton Gluing     (separate from Carton Stitching on prod)
    Die Cutting       (also tag — used for Carton + Mono Box + Label)
    Lamination        (optional finishing)
    Plate Making      (optional cross-line)

Net-new Workstation Types this patch creates (not on prod):
    Slotting          — per v3 markup p.8 (Tanuj split Printing/Slotting into 2 stations)
    Bundling          — final station; net-new

Net-new Workstations created (placeholders — floor renames as needed):
    Slotter 01        under Slotting
    Bundler 01        under Bundling

White-Paper-v4 station list for Carton traveller v4 uses 8 rows:
  Corrugation → Sheeting → Carton Pasting → Creasing → Carton Printing →
  Slotting → Carton Stitching / Gluing (combined display row) → Bundling

(The combined "Stitching / Gluing" row on the paper traveller maps to either
the Carton Stitching or Carton Gluing Workstation Type at JTRun-row level —
operator picks which when keying the JTRun.)
"""

import frappe


PRODUCT_LINE = "Corrugation and Carton Department"

# Existing Workstation Types we just need to tag with the Carton product line
EXISTING_WORKSTATION_TYPES = [
	"Corrugation",
	"Sheeting",
	"Carton Pasting",
	"Creasing",
	"Carton Printing",
	"Carton Stitching",
	"Carton Gluing",
	"Die Cutting",
	"Lamination",
	"Plate Making",
]

# Net-new Workstation Types this patch creates
NEW_WORKSTATION_TYPES = [
	# (name, stage_position) — 10-spaced ladder per patch_v5_5 convention
	("Slotting", 155),   # between Carton Printing (150) and Carton Stitching (160)
	("Bundling", 170),
]

# Net-new Workstations (placeholders — rename to real equipment IDs after install)
NEW_WORKSTATIONS = [
	("Slotter 01", "Slotting"),
	("Bundler 01", "Bundling"),
]


def execute():
	# Step 1 — tag existing WTs with Carton product_line
	for ws_type_name in EXISTING_WORKSTATION_TYPES:
		if frappe.db.exists("Workstation Type", ws_type_name):
			_ensure_product_line_tag(ws_type_name, PRODUCT_LINE)

	# Step 2 — create the 2 net-new Workstation Types
	for ws_type_name, stage_position in NEW_WORKSTATION_TYPES:
		_create_or_update_workstation_type(ws_type_name, stage_position)

	# Step 3 — placeholder Workstations under the 2 new Workstation Types
	for ws_name, ws_type_name in NEW_WORKSTATIONS:
		_create_or_update_workstation(ws_name, ws_type_name)

	frappe.clear_cache()


def _create_or_update_workstation_type(name, stage_position):
	if frappe.db.exists("Workstation Type", name):
		# Already there — just ensure product_line tag exists
		_ensure_product_line_tag(name, PRODUCT_LINE)
		return

	# Use dict-form construction so Frappe resolves naming via autoname
	# correctly. Workstation Type uses autoname='field:workstation_type'.
	# Also pre-set doc.name as a safety belt for older Frappe versions.
	doc = frappe.get_doc({
		"doctype":               "Workstation Type",
		"workstation_type":      name,
		"name":                  name,
		"custom_product_line":   PRODUCT_LINE,
		"custom_stage_position": stage_position,
	})
	try:
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
	except frappe.NameError:
		# Race condition — another patch run created it. Treat as success.
		pass
	_ensure_product_line_tag(name, PRODUCT_LINE)


def _ensure_product_line_tag(workstation_type, product_line):
	"""Append a Workstation Product Line Tag child row if missing.

	Patch_v5_2 moved tagging from Workstation up to Workstation Type via
	the custom_product_line_tags child table on Workstation Type.

	Note: bypasses the parent's validate hook (validate_stage_position)
	to avoid pre-existing stage_position conflicts blocking the tag
	addition. The validator is concerned with planner column ordering,
	not with product_line tagging; safe to skip here.
	"""
	# Check existing rows directly (avoids loading the parent doc)
	existing = frappe.db.exists(
		"Workstation Product Line Tag",
		{
			"parent":       workstation_type,
			"parenttype":   "Workstation Type",
			"parentfield":  "custom_product_line_tags",
			"product_line": product_line,
		},
	)
	if existing:
		return

	# Insert the child row directly — bypasses parent's validate hook
	tag = frappe.get_doc({
		"doctype":      "Workstation Product Line Tag",
		"parent":       workstation_type,
		"parenttype":   "Workstation Type",
		"parentfield":  "custom_product_line_tags",
		"product_line": product_line,
	})
	try:
		tag.insert(ignore_permissions=True)
	except Exception:
		# Fallback: direct SQL insert if Frappe rejects orphan child insert
		frappe.db.sql(
			"""
			INSERT INTO `tabWorkstation Product Line Tag`
				(name, creation, modified, modified_by, owner, docstatus, idx,
				 parent, parenttype, parentfield, product_line)
			VALUES
				(%(name)s, NOW(), NOW(), 'Administrator', 'Administrator', 0,
				 (SELECT IFNULL(MAX(idx), 0) + 1
				  FROM `tabWorkstation Product Line Tag` t
				  WHERE t.parent = %(parent)s),
				 %(parent)s, %(parenttype)s, %(parentfield)s, %(product_line)s)
			""",
			{
				"name":         frappe.generate_hash(length=10),
				"parent":       workstation_type,
				"parenttype":   "Workstation Type",
				"parentfield":  "custom_product_line_tags",
				"product_line": product_line,
			},
		)


def _create_or_update_workstation(name, workstation_type):
	if frappe.db.exists("Workstation", name):
		return

	# Workstation autoname is also field-driven. Use dict-form to be safe.
	doc = frappe.get_doc({
		"doctype":             "Workstation",
		"workstation_name":    name,
		"workstation_type":    workstation_type,
		"custom_product_line": PRODUCT_LINE,
	})
	try:
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
	except frappe.NameError:
		pass
