"""
Patch v5_2: Workstation Type-level tagging + 6-product-line taxonomy.

This is the architectural follow-up to patch_v5_0 / patch_v5_1. Two things
change together because they touch the same custom-field stack:

1. Source of truth for `product_line` tagging moves from Workstation to
   Workstation Type. The existing `Workstation Product Line Tag` child
   DocType is reused verbatim — only the parent field location changes.
   After this patch runs, `get_workstation_columns` in the planner page
   reads tags off Workstation Type instead of Workstation, and the old
   per-Workstation Table field goes away.

2. The product-line Select options expand from
   `All / Computer Paper / ETR / Thermal / Label / Carton`
   to
   `All / Computer Paper / ETR / Label /
    General Stationery and Exercise Book / Mono Boxes /
    Corrugation and Carton Department`.
   Note `ETR / Thermal` is renamed to just `ETR` — the legacy value is
   rewritten on every PSL / PE / tag row.

Idempotent. A second `bench migrate` picks up the post-migration state
(Workstation field already deleted, tags already rolled up) and short-
circuits through Phases 4–5 while Phases 1–3 stay safely re-runnable.
"""

from collections import defaultdict

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


PRODUCT_LINE_OPTIONS = (
	"All\n"
	"Computer Paper\n"
	"ETR\n"
	"Label\n"
	"General Stationery and Exercise Book\n"
	"Mono Boxes\n"
	"Corrugation and Carton Department"
)


def execute():
	# Phase 1 — pick up the updated Select options on the child table.
	frappe.reload_doc("production_log", "doctype", "workstation_product_line_tag")

	# Phase 2 — add WT tag table + widen the legacy single-Select options
	# on both WT and WS.
	_install_custom_fields()

	# Phase 3 — rename `ETR / Thermal` → `ETR` everywhere it lingers.
	_rename_etr_thermal()

	# Phase 4 — roll per-Workstation tags up to their Workstation Type.
	_rollup_ws_tags_to_wt()

	# Phase 5 — drop the per-Workstation child table field + its rows.
	_drop_ws_tag_field()

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
			{
				"fieldname": "custom_product_line_tags",
				"fieldtype": "Table",
				"label": "Product Line Tags",
				"options": "Workstation Product Line Tag",
				"insert_after": "custom_product_line",
			},
		],
		"Workstation": [
			# Kept for back-compat on admin-edited rows; planner no longer
			# reads this value after v5_2.
			{
				"fieldname": "custom_product_line",
				"fieldtype": "Select",
				"label": "Product Line",
				"options": PRODUCT_LINE_OPTIONS,
				"default": "All",
				"insert_after": "workstation_type",
			},
		],
	}
	create_custom_fields(custom_fields, update=True)


def _rename_etr_thermal():
	# PSL + PE rows.
	for doctype in ("Production Schedule Line", "Production Entry"):
		frappe.db.sql(
			f"UPDATE `tab{doctype}` SET product_line = 'ETR' WHERE product_line = 'ETR / Thermal'"
		)

	# Legacy single-Select values on WT + WS.
	for doctype in ("Workstation", "Workstation Type"):
		frappe.db.sql(
			f"UPDATE `tab{doctype}` SET custom_product_line = 'ETR' WHERE custom_product_line = 'ETR / Thermal'"
		)

	# Child table rows — catches WS-parent rows pre-rollup AND any
	# WT-parent rows a pre-patch admin already created manually.
	frappe.db.sql(
		"""
		UPDATE `tabWorkstation Product Line Tag`
		SET product_line = 'ETR'
		WHERE product_line = 'ETR / Thermal'
		"""
	)


def _rollup_ws_tags_to_wt():
	# Short-circuit if the WS field is already gone — this is the re-run
	# idempotency check.
	if not frappe.db.exists(
		"Custom Field",
		{"dt": "Workstation", "fieldname": "custom_product_line_tags"},
	):
		return

	rows = frappe.db.sql(
		"""
		SELECT ws.workstation_type AS wt, tag.product_line AS pl
		FROM `tabWorkstation` ws
		INNER JOIN `tabWorkstation Product Line Tag` tag
			ON tag.parent = ws.name
			AND tag.parenttype = 'Workstation'
			AND tag.parentfield = 'custom_product_line_tags'
		""",
		as_dict=True,
	)

	rollup = defaultdict(set)
	for row in rows:
		if row.wt and row.pl:
			rollup[row.wt].add(row.pl)

	for wt_name, pls in rollup.items():
		if not frappe.db.exists("Workstation Type", wt_name):
			continue
		wt = frappe.get_doc("Workstation Type", wt_name)
		existing = {r.product_line for r in wt.get("custom_product_line_tags", [])}
		to_add = pls - existing
		if not to_add:
			continue
		for pl in sorted(to_add):
			wt.append("custom_product_line_tags", {"product_line": pl})
		wt.save(ignore_permissions=True)


def _drop_ws_tag_field():
	# Delete the child rows first so the Custom Field delete doesn't
	# leave orphans.
	frappe.db.sql(
		"""
		DELETE FROM `tabWorkstation Product Line Tag`
		WHERE parenttype = 'Workstation'
		AND parentfield = 'custom_product_line_tags'
		"""
	)

	cf_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "Workstation", "fieldname": "custom_product_line_tags"},
		"name",
	)
	if cf_name:
		frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True)
