"""
Patch v5_0: Planner prerequisites.

- Extend the `custom_product_line` Select options on Workstation Type and
  Workstation to include `ETR / Thermal` (keeping the existing options:
  All, Computer Paper, Label, Carton).
- Add a Table field `custom_product_line_tags` on Workstation pointing at
  the new `Workstation Product Line Tag` child DocType.
- Seed a `Design` Workstation Type and a `Design Desk` Workstation tagged
  with `All`, so the planner always has a design column.
- Migrate the legacy single-Select `custom_product_line` value on every
  existing Workstation into a matching child-table row (preserves data
  while the planner switches to reading the tag table).

Idempotent: re-running produces no duplicate rows or duplicate field
creates.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


PRODUCT_LINE_OPTIONS = "All\nComputer Paper\nETR / Thermal\nLabel\nCarton"
TAG_VALID_VALUES = {"All", "Computer Paper", "ETR / Thermal"}


def execute():
	# 1. Sync the new child DocType into the DB before we point a custom
	#    field at it.
	frappe.reload_doc("production_log", "doctype", "workstation_product_line_tag")

	# 2. Extend Select options and add the tags Table field.
	_install_custom_fields()

	# 3. Seed Design WT + Design Desk workstation.
	_seed_design()

	# 4. Migrate legacy single-Select values into the tags table.
	_migrate_legacy_tags()

	frappe.db.commit()


def _install_custom_fields():
	custom_fields = {
		"Workstation Type": [
			{
				"fieldname": "custom_product_line",
				"fieldtype": "Select",
				"label": "Product Line",
				"options": PRODUCT_LINE_OPTIONS,
				"default": "All",
				"insert_after": "description",
			},
		],
		"Workstation": [
			{
				"fieldname": "custom_product_line",
				"fieldtype": "Select",
				"label": "Product Line",
				"options": PRODUCT_LINE_OPTIONS,
				"default": "All",
				"insert_after": "workstation_type",
			},
			{
				"fieldname": "custom_product_line_tags",
				"fieldtype": "Table",
				"label": "Product Line Tags",
				"options": "Workstation Product Line Tag",
				"insert_after": "custom_product_line",
			},
		],
	}
	create_custom_fields(custom_fields, update=True)


def _seed_design():
	# Workstation Type on this ERPNext build has a regular field
	# literally called `name` (label "Workstation Type") plus an
	# autoname of `field:name`. `wt = frappe.new_doc(...); wt.name =
	# "Design"` only sets the Document primary key, leaving the
	# namesake field empty — which makes set_name_from_naming_options
	# throw "Workstation Type is required" at insert time. Building
	# the doc from a dict routes every key through Document.update /
	# Document.set, which populates the field attribute as well, so
	# naming resolves cleanly.
	if not frappe.db.exists("Workstation Type", "Design"):
		wt = frappe.get_doc({
			"doctype": "Workstation Type",
			"name": "Design",
			"custom_product_line": "All",
		})
		wt.insert(ignore_permissions=True)

	if not frappe.db.exists("Workstation", "Design Desk"):
		ws = frappe.get_doc({
			"doctype": "Workstation",
			"workstation_name": "Design Desk",
			"workstation_type": "Design",
		})
		ws.insert(ignore_permissions=True)

	ws = frappe.get_doc("Workstation", "Design Desk")
	existing_tags = {row.product_line for row in ws.get("custom_product_line_tags", [])}
	if "All" not in existing_tags:
		ws.append("custom_product_line_tags", {"product_line": "All"})
		ws.save(ignore_permissions=True)


def _migrate_legacy_tags():
	rows = frappe.db.get_all(
		"Workstation",
		fields=["name", "custom_product_line"],
		filters=[["custom_product_line", "!=", ""]],
	)
	for row in rows:
		old = (row.get("custom_product_line") or "").strip()
		if not old or old not in TAG_VALID_VALUES:
			# Label / Carton / unexpected values have no planner column yet;
			# skip them so the tag table's Select constraint isn't violated.
			continue

		ws = frappe.get_doc("Workstation", row["name"])
		existing = {r.product_line for r in ws.get("custom_product_line_tags", [])}
		if old in existing:
			continue

		ws.append("custom_product_line_tags", {"product_line": old})
		ws.save(ignore_permissions=True)
