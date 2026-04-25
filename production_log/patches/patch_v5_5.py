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
   `All` is kept in the option list — admins requested manual control
   over migrating WTs from `All` to explicit per-PL rows, so the
   planner SQL still matches `All` until those rows are re-tagged by
   hand. Note: `R2R` is the product-line abbreviation deliberately —
   the `Reel to Reel Printing` Workstation Type keeps its name.

3. Re-install `custom_product_line_tags` on Workstation Type. The
   field has gone missing on at least one site — could be a
   hand-deleted Custom Field row OR a row that's still there but
   `hidden=1` from a stale fixtures import. The spec below pins the
   visibility flags explicitly so `create_custom_fields(update=True)`
   resets a hidden row back to visible, AND remove the legacy
   single-Select `custom_product_line` from Workstation Type entirely.
   The planner only reads the child table.

Idempotent. A second `bench migrate` is a no-op on every phase.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# Authoritative product-line list as of v5_5. PSL / PE / WPLTag Selects
# carry these (PSL / PE prepend a blank option; WPLTag keeps `All` at
# the top of its own list). Order matches what the planner client
# renders as dept tabs, with `Trading` and `R2R` appended.
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
	#   - Workstation Type.custom_product_line_tags (re-install + un-hide)
	#   - Workstation Type.custom_stage_position    (new)
	#   - Workstation.custom_product_line           (option refresh only)
	_install_custom_fields()

	# Phase 3 — rename `Label` → `Self Adhesive Label` everywhere it
	# lives as data.
	_rename_label()

	# Phase 4 — drop the legacy single-Select `custom_product_line` on
	# Workstation Type. The data was already mirrored to the tag table
	# in patch_v5_0/v5_1; nothing to migrate here.
	_drop_wt_single_select()

	# Phase 5 — seed `custom_stage_position` for the six known WTs.
	# Skips any WT whose admin has already set a non-default value.
	_seed_stage_positions()

	frappe.db.commit()


def _install_custom_fields():
	# Visibility flags are pinned (rather than left default) so that a
	# pre-existing Custom Field row that's somehow flipped to hidden /
	# read-only / depends_on=<expr> gets reset back to a visible,
	# editable Table field.
	visibility_pins = {
		"hidden": 0,
		"read_only": 0,
		"depends_on": "",
		"mandatory_depends_on": "",
		"read_only_depends_on": "",
		"permlevel": 0,
	}

	custom_fields = {
		"Workstation Type": [
			# Re-install + un-hide. `create_custom_fields(..., update=True)`
			# merges these props into any existing row with the same
			# fieldname; a missing row gets created from scratch. Either
			# way the form picks the field back up after a desk reload.
			{
				"fieldname": "custom_product_line_tags",
				"fieldtype": "Table",
				"label": "Product Line Tags",
				"options": "Workstation Product Line Tag",
				"insert_after": "description",
				**visibility_pins,
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
				**visibility_pins,
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
