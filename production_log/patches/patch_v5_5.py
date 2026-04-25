"""
Patch v5_5: Stage-position field on Workstation Type + product-line
taxonomy refresh.

Three things change together because they all touch the Workstation
Type custom-field stack and the planner's product-line plumbing:

1. Add `custom_stage_position` (Int) on Workstation Type so the planner
   sorts stage columns from this field instead of the hardcoded JS
   `STAGE_ORDER`. Seed the six known stages with a 10-spaced ladder
   so admins can interleave new positions without renumbering.

2. Refresh the product-line option list on PSL / PE / Workstation
   Product Line Tag / Workstation.custom_product_line:
       - Rename `Label` → `Self Adhesive Label` (data + Select options).
       - Add `Trading` and `R2R` (no data to migrate, options only).
       - Drop `All`. Every WT row carrying `All` is expanded to the
         seven concrete product lines that have planner tabs (i.e. the
         full 8-name list minus `Trading`, which doesn't have a tab).
   Note: `R2R` is the product-line abbreviation deliberately — the
   `Reel to Reel Printing` Workstation Type keeps its name.

3. Re-install `custom_product_line_tags` on Workstation Type (the
   child-table field has gone missing on at least one site — admin
   hand-delete or migrate skip) and remove the legacy single-Select
   `custom_product_line` from Workstation Type entirely. The planner
   only reads the child table.

Idempotent. A second `bench migrate` is a no-op on every phase.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# Authoritative product-line list as of v5_5. PSL / PE / WPLTag Selects
# carry these (PSL / PE prepend a blank option). Order matches what the
# planner client renders as dept tabs.
PRODUCT_LINE_OPTIONS = (
	"Computer Paper\n"
	"ETR\n"
	"Self Adhesive Label\n"
	"General Stationery and Exercise Book\n"
	"Mono Boxes\n"
	"Corrugation and Carton Department\n"
	"Trading\n"
	"R2R"
)
PRODUCT_LINE_LIST = PRODUCT_LINE_OPTIONS.split("\n")

# `All` rows on WT tag tables expand into these. Trading has no
# planner tab and no operations stages; expanding `All` into Trading
# would silently put every shared WT under Trading too. Drop it from
# the expansion set — admins can add it explicitly if a Trading-bound
# WT shows up later.
ALL_EXPANSION = [pl for pl in PRODUCT_LINE_LIST if pl != "Trading"]

# Default stage positions for the six known WTs. Spaced by 10 so admins
# can insert a new stage between two existing ones without renumbering.
DEFAULT_STAGE_POSITIONS = {
	"Design": 10,
	"Reel to Reel Printing": 20,
	"Ruling": 30,
	"Sheeting": 40,
	"Collation": 50,
	"Slitting": 60,
}


def execute():
	# Phase 1 — pick up the new Select options on the on-disk doctype JSONs
	# (PSL / PE / Workstation Product Line Tag).
	frappe.reload_doc("production_log", "doctype", "production_schedule_line")
	frappe.reload_doc("production_log", "doctype", "production_entry")
	frappe.reload_doc("production_log", "doctype", "workstation_product_line_tag")

	# Phase 2 — install / refresh custom fields:
	#   - Workstation Type.custom_product_line_tags (re-install if missing)
	#   - Workstation Type.custom_stage_position    (new)
	#   - Workstation.custom_product_line           (option refresh only)
	_install_custom_fields()

	# Phase 3 — rename `Label` → `Self Adhesive Label` everywhere it
	# lives as data.
	_rename_label()

	# Phase 4 — expand `All` tag rows into explicit per-PL rows on
	# Workstation Type, then strip residual `All` rows.
	_expand_all_tags()

	# Phase 5 — drop the legacy single-Select `custom_product_line` on
	# Workstation Type. The data was already mirrored to the tag table
	# in patch_v5_0/v5_1; nothing to migrate here.
	_drop_wt_single_select()

	# Phase 6 — seed `custom_stage_position` for the six known WTs.
	# Skips any WT whose admin has already set a non-default value.
	_seed_stage_positions()

	frappe.db.commit()


def _install_custom_fields():
	custom_fields = {
		"Workstation Type": [
			# Re-install. `create_custom_fields(..., update=True)` is a
			# no-op when the row already matches; this is the recovery
			# path for sites where the field row was hand-deleted.
			{
				"fieldname": "custom_product_line_tags",
				"fieldtype": "Table",
				"label": "Product Line Tags",
				"options": "Workstation Product Line Tag",
				"insert_after": "description",
			},
			{
				"fieldname": "custom_stage_position",
				"fieldtype": "Int",
				"label": "Stage Position",
				"default": 999,
				"insert_after": "custom_product_line_tags",
				"description": (
					"Lower numbers render earlier in the planner. "
					"Must be unique across Workstation Types."
				),
			},
		],
		# Legacy back-compat field on Workstation. Refresh options to
		# match the new taxonomy. Planner doesn't read it after v5_2 but
		# admins may still edit it manually.
		"Workstation": [
			{
				"fieldname": "custom_product_line",
				"fieldtype": "Select",
				"label": "Product Line",
				"options": PRODUCT_LINE_OPTIONS,
				"insert_after": "workstation_type",
			},
		],
	}
	create_custom_fields(custom_fields, update=True)


def _rename_label():
	# PSL + PE rows.
	for doctype in ("Production Schedule Line", "Production Entry"):
		frappe.db.sql(
			f"UPDATE `tab{doctype}` SET product_line = 'Self Adhesive Label' "
			f"WHERE product_line = 'Label'"
		)

	# Workstation Type / Workstation legacy single-Select. WT row gets
	# deleted next phase but we rename first so the cascade reads
	# consistently if anything inspects it mid-migration.
	for doctype in ("Workstation Type", "Workstation"):
		frappe.db.sql(
			f"UPDATE `tab{doctype}` SET custom_product_line = 'Self Adhesive Label' "
			f"WHERE custom_product_line = 'Label'"
		)

	# Child table rows (parent type covers both WT and any lingering WS).
	frappe.db.sql(
		"""
		UPDATE `tabWorkstation Product Line Tag`
		SET product_line = 'Self Adhesive Label'
		WHERE product_line = 'Label'
		"""
	)


def _expand_all_tags():
	# Every WT carrying an `All` tag row.
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT parent
		FROM `tabWorkstation Product Line Tag`
		WHERE parenttype = 'Workstation Type'
		  AND parentfield = 'custom_product_line_tags'
		  AND product_line = 'All'
		""",
		as_dict=True,
	)

	for row in rows:
		wt_name = row.parent
		if not frappe.db.exists("Workstation Type", wt_name):
			continue
		wt = frappe.get_doc("Workstation Type", wt_name)

		existing = {
			r.product_line for r in wt.get("custom_product_line_tags", [])
		}

		# Drop `All` rows in-place by filtering the list.
		wt.set(
			"custom_product_line_tags",
			[
				r for r in wt.get("custom_product_line_tags", [])
				if (r.product_line or "") != "All"
			],
		)

		for pl in ALL_EXPANSION:
			if pl in existing and pl != "All":
				continue
			wt.append("custom_product_line_tags", {"product_line": pl})

		wt.save(ignore_permissions=True)

	# Belt-and-braces: any orphan `All` rows that didn't go through the
	# get_doc path above (e.g. residual WS-parent rows from before v5_2's
	# rollup phase) are deleted here.
	frappe.db.sql(
		"DELETE FROM `tabWorkstation Product Line Tag` WHERE product_line = 'All'"
	)


def _drop_wt_single_select():
	cf_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "Workstation Type", "fieldname": "custom_product_line"},
		"name",
	)
	if cf_name:
		frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True)


def _seed_stage_positions():
	for wt_name, position in DEFAULT_STAGE_POSITIONS.items():
		if not frappe.db.exists("Workstation Type", wt_name):
			continue
		current = frappe.db.get_value(
			"Workstation Type", wt_name, "custom_stage_position"
		)
		# Only seed the field if it's at the default sentinel (999) or
		# unset — admin edits are preserved.
		if current and int(current) != 999:
			continue
		frappe.db.set_value(
			"Workstation Type", wt_name, "custom_stage_position", position
		)
