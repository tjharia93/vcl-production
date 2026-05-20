"""S2 follow-up patch — per-line production routing model.

Adds `process_number` to the Workstation Product Line Tag child table and
seeds each of the 8 product lines' production routes.

Background
----------
A station's place in the workflow is NOT a property of the station — it
depends on which product line's job is passing through it. Sheeting is
step 1 of the Trading route but step ~5 of the Exercise Book route. So the
route position is modelled as data on the per-line tag row, not baked into
a station code.

    Workstation Type             = a production stage
    Workstation Product Line Tag = (stage, product_line) membership row
    process_number  (new field)  = that stage's step number in that line

A line's route = all its tag rows across every stage, sorted by
process_number. `custom_stage_position` on Workstation Type stays as the
master planner-board column order; process_number is the per-line refinement.

Applied live on the prod site 2026-05-20 via REST (see CHANGELOG_DAILY.md).
This patch codifies it so a fresh install (staging / disaster recovery)
reproduces it. Fully idempotent:
  - prod → field + every row already exist → set_value no-ops.
  - fresh install → field created, rows inserted.

Child rows are written directly with explicit parent fields so the parent
Workstation Type's validate_stage_position hook is not triggered.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CHILD_DT = "Workstation Product Line Tag"

# stage (Workstation Type) -> {product_line: process_number}
ROUTES = {
	"Design":                        {"All": 10},
	"Plate Making":                  {"All": 20, "Corrugation and Carton Department": 20},
	"Reel to Reel Printing":         {"Computer Paper": 30, "ETR": 30, "R2R": 30},
	"Sheet to Sheet Printing":       {"General Stationery and Exercise Book": 30, "Mono Boxes": 30},
	"Flexo Label Printing":          {"Self Adhesive Label": 30},
	"Label Printing":                {"Self Adhesive Label": 30},
	"Ruling":                        {"General Stationery and Exercise Book": 40},
	"Sheeting":                      {"Corrugation and Carton Department": 40, "General Stationery and Exercise Book": 50, "Trading": 10},
	"Collation":                     {"Computer Paper": 40, "General Stationery and Exercise Book": 60},
	"Corrugation":                   {"Corrugation and Carton Department": 30},
	"Carton Printing":               {"Corrugation and Carton Department": 50},
	"Lamination":                    {"Corrugation and Carton Department": 60, "Mono Boxes": 40},
	"Creasing":                      {"Corrugation and Carton Department": 70},
	"Die Cutting":                   {"Corrugation and Carton Department": 80, "Mono Boxes": 50, "Self Adhesive Label": 40},
	"Slotting":                      {"Corrugation and Carton Department": 90},
	"Carton Pasting":                {"Corrugation and Carton Department": 100},
	"Carton Stitching":              {"Corrugation and Carton Department": 110},
	"Carton Gluing":                 {"Corrugation and Carton Department": 120, "Mono Boxes": 60},
	"Bundling":                      {"Corrugation and Carton Department": 130},
	"ETR Slitting":                  {"ETR": 40},
	"Label Slitting and Re-Winding": {"Self Adhesive Label": 50, "R2R": 40},
}


def execute():
	_ensure_field()
	for stage, spec in ROUTES.items():
		if not frappe.db.exists("Workstation Type", stage):
			continue
		for product_line, process_number in spec.items():
			_ensure_route_row(stage, product_line, process_number)
	frappe.clear_cache()


def _ensure_field():
	create_custom_fields(
		{
			CHILD_DT: [
				{
					"fieldname": "process_number",
					"label": "Process No.",
					"fieldtype": "Int",
					"insert_after": "product_line",
					"in_list_view": 1,
					"description": (
						"Step order within this product line's production route "
						"(lower = earlier). The line's route = its tag rows sorted "
						"by this number."
					),
				},
			],
		},
		ignore_validate=True,
	)


def _ensure_route_row(stage, product_line, process_number):
	"""Create or update the (stage, product_line) tag row with its
	process_number, without re-saving the parent Workstation Type."""
	name = frappe.db.exists(
		CHILD_DT,
		{
			"parent":       stage,
			"parenttype":   "Workstation Type",
			"parentfield":  "custom_product_line_tags",
			"product_line": product_line,
		},
	)
	if name:
		frappe.db.set_value(CHILD_DT, name, "process_number", process_number)
		return

	row = frappe.get_doc({
		"doctype":        CHILD_DT,
		"parent":         stage,
		"parenttype":     "Workstation Type",
		"parentfield":    "custom_product_line_tags",
		"product_line":   product_line,
		"process_number": process_number,
	})
	row.insert(ignore_permissions=True)
