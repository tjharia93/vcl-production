"""S1 patch — seed Carton Workstation Types and Workstations.

Per Sprint-0 audit (msg 267) §5.5: live registry has 18 Workstations covering
CP + ETR + Label + GS + Design but ZERO Carton-specific machines. This patch
seeds the 7 net-new Workstation Types needed to render the Carton planner tab
and Heijunka board, plus one placeholder Workstation per type.

Existing Workstation Types that Carton also uses (no seeding needed):
  Sheeting (already exists, hosts Sheeting Machine 01/02)

Naming follows: <Process> · placeholder machines named <Process>er 01.
Floor will rename machines per their actual equipment ID after S3 install.
"""

import frappe


PRODUCT_LINE = "Corrugation and Carton Department"

WORKSTATION_TYPES = [
	# (name, stage_position) — 10-spaced ladder per patch_v5_5 convention
	("Corrugation (SFK)", 110),
	("Pasting", 120),
	("Creasing", 130),
	("Printing (Carton)", 140),
	("Slotting", 150),
	("Stitching / Gluing", 160),
	("Bundling", 170),
]

# placeholder Workstation per Workstation Type
WORKSTATIONS = [
	("Corrugator 01", "Corrugation (SFK)"),
	("Paster 01", "Pasting"),
	("Creaser 01", "Creasing"),
	("Carton Printer 01", "Printing (Carton)"),
	("Slotter 01", "Slotting"),
	("Stitcher 01", "Stitching / Gluing"),
	("Gluer 01", "Stitching / Gluing"),
	("Bundler 01", "Bundling"),
]


def execute():
	for ws_type, stage_pos in WORKSTATION_TYPES:
		_create_or_update_workstation_type(ws_type, stage_pos)

	for ws, ws_type in WORKSTATIONS:
		_create_or_update_workstation(ws, ws_type)

	frappe.clear_cache()


def _create_or_update_workstation_type(name, stage_position):
	if frappe.db.exists("Workstation Type", name):
		# Already there — just ensure product_line tag exists
		_ensure_product_line_tag(name, PRODUCT_LINE)
		return

	doc = frappe.new_doc("Workstation Type")
	doc.name = name
	if hasattr(doc, "custom_product_line"):
		doc.custom_product_line = PRODUCT_LINE
	if hasattr(doc, "custom_stage_position"):
		doc.custom_stage_position = stage_position
	doc.flags.ignore_permissions = True
	doc.insert()
	_ensure_product_line_tag(name, PRODUCT_LINE)


def _ensure_product_line_tag(workstation_type, product_line):
	"""Append a Workstation Product Line Tag child row if missing.

	Patch_v5_2 moved tagging from Workstation up to Workstation Type via
	the custom_product_line_tags child table.
	"""
	wt = frappe.get_doc("Workstation Type", workstation_type)
	tags_field = getattr(wt, "custom_product_line_tags", None)
	if tags_field is None:
		return
	if any(getattr(row, "product_line", None) == product_line for row in tags_field):
		return
	wt.append("custom_product_line_tags", {"product_line": product_line})
	wt.flags.ignore_permissions = True
	wt.save()


def _create_or_update_workstation(name, workstation_type):
	if frappe.db.exists("Workstation", name):
		return

	doc = frappe.new_doc("Workstation")
	doc.workstation_name = name
	doc.workstation_type = workstation_type
	if hasattr(doc, "custom_product_line"):
		# Legacy single-value field retained for back-compat per v5_2
		doc.custom_product_line = PRODUCT_LINE
	doc.flags.ignore_permissions = True
	doc.insert()
