"""Additive Custom Fields for the Computer Paper carton-weight calculation.

Two weights get quoted, planned and shipped against on a Computer Paper carton,
and until now a single free-text ``standard_weight_per_carton`` was typed by hand
and meant whichever of them the typist meant:

* the **net product weight** of the paper in the carton, and
* the **gross packed weight** including the outer packing carton.

Both are derivable from things the specification already records, so this lands
the structured inputs they are derived from and the read-only results they are
derived into. Nothing here changes the meaning of an existing field, and nothing
is backfilled: every legacy record legitimately has these blank, and the
controller leaves a legacy record's hand-typed ``standard_weight_per_carton``
exactly where it is until somebody enters the structured inputs.

Structured inputs (editable, Computer Paper only)
    ``finished_width_mm`` / ``finished_length_mm``
        The finished sheet of one set, in millimetres, as their own numeric
        fields. The calculation reads only these — ``job_size`` is free text and
        is never parsed into a weight, only offered as an editable suggestion on
        the Compass screen.
    ``sets_per_carton``
        How many finished sets are packed into one carton. A whole number.
    ``packing_carton_tare_kg``
        The empty outer carton, in kilograms. The whole of the difference between
        the net and the gross weight.
    ``print_weight_allowance_pct``
        An optional percentage uplift on the substrate weight for a Printed job,
        labelled as an *allowance* rather than an ink weight because the weight of
        ink on a sheet is not something a specification knows exactly. Plain jobs
        carry none.

Derived results (read-only, recomputed server-side on every save)
    ``cp_total_gsm`` — the grammage of one complete set (the sum of every ply).
    ``paper_weight_per_set_g`` — one set as it ships, in grams.
    ``net_product_weight_per_carton_kg`` — the paper only, in kilograms.
    ``gross_packed_weight_per_carton_kg`` — the paper plus the carton, in
    kilograms. Also mirrored into ``standard_weight_per_carton`` when the inputs
    are complete, which is the field the order snapshot freezes and the Job Card
    reads as ``weight_per_carton`` — so the gross reaches production with no
    snapshot version bump and no mapping change.

Idempotent by construction: ``create_custom_fields`` inserts what is absent and
reconciles the properties of what is present, so a re-run corrects a hand-edited
site rather than duplicating a field. The same fields are exported into
``fixtures/custom_field.json`` so a site rebuilt from this app reproduces them.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_cp_weight as w

# Every weight field is shown for Computer Paper alone. The stored columns exist
# for every product type — a Custom Field is a column on the table — and widening
# the display later is a property change rather than a migration.
_CP_ONLY = "eval:doc.product_type=='{0}'".format(w.COMPUTER_PAPER)

# The allowance is an ink-weight estimate, so it is shown only when there is ink:
# a Printed Computer Paper record.
_CP_PRINTED_ONLY = "eval:doc.product_type=='{0}' && doc.{1}=='{2}'".format(
	w.COMPUTER_PAPER, w.PRINT_TYPE_FIELD, w.PRINT_TYPE_PRINTED
)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache(doctype="Customer Product Specification")


def get_custom_fields():
	return {
		"Customer Product Specification": [
			{
				"fieldname": "cp_weight_section",
				"label": "Weight",
				"fieldtype": "Section Break",
				"insert_after": w.STANDARD_WEIGHT_FIELD,
				"depends_on": _CP_ONLY,
				"description": (
					"Net product weight and gross packed weight, calculated from the finished "
					"size, the parts and the pack. The Standard Weight Per Carton above is set "
					"from the gross result and is not entered by hand for Computer Paper."
				),
			},
			{
				"fieldname": w.WIDTH_FIELD,
				"label": "Finished Width (mm)",
				"fieldtype": "Float",
				"precision": "1",
				"non_negative": 1,
				"insert_after": "cp_weight_section",
				"depends_on": _CP_ONLY,
				"description": (
					"The finished width of one set, in millimetres. Entered here, not read "
					"from the job size text."
				),
			},
			{
				"fieldname": w.LENGTH_FIELD,
				"label": "Finished Length (mm)",
				"fieldtype": "Float",
				"precision": "1",
				"non_negative": 1,
				"insert_after": w.WIDTH_FIELD,
				"depends_on": _CP_ONLY,
				"description": (
					"The finished length of one set, in millimetres. Entered here, not read "
					"from the job size text."
				),
			},
			{
				"fieldname": w.SETS_PER_CARTON_FIELD,
				"label": "Sets per Carton",
				"fieldtype": "Int",
				"non_negative": 1,
				"insert_after": w.LENGTH_FIELD,
				"depends_on": _CP_ONLY,
				"description": "How many finished sets are packed into one carton.",
			},
			{
				"fieldname": w.TARE_FIELD,
				"label": "Packing Carton Tare (kg)",
				"fieldtype": "Float",
				"precision": "3",
				"non_negative": 1,
				"insert_after": w.SETS_PER_CARTON_FIELD,
				"depends_on": _CP_ONLY,
				"description": (
					"The weight of the empty outer packing carton, in kilograms. This is the "
					"difference between the net and the gross weight."
				),
			},
			{
				"fieldname": w.ALLOWANCE_FIELD,
				"label": "Printing Allowance (%)",
				"fieldtype": "Float",
				"precision": "2",
				"non_negative": 1,
				"insert_after": w.TARE_FIELD,
				"depends_on": _CP_PRINTED_ONLY,
				"description": (
					"Optional. A percentage uplift on the paper weight to allow for ink on a "
					"Printed job. This is an allowance, not an exact ink weight - the weight of "
					"ink on a sheet depends on coverage and press. Leave blank for no uplift. "
					"Ignored on Plain jobs."
				),
			},
			{
				"fieldname": "cp_weight_results_col",
				"fieldtype": "Column Break",
				"insert_after": w.ALLOWANCE_FIELD,
				"depends_on": _CP_ONLY,
			},
			{
				"fieldname": w.TOTAL_GSM_FIELD,
				"label": "Total GSM (all parts)",
				"fieldtype": "Float",
				"precision": "1",
				"read_only": 1,
				"insert_after": "cp_weight_results_col",
				"depends_on": _CP_ONLY,
				"description": "The grammage of one complete set: the sum of every part's GSM. Derived.",
			},
			{
				"fieldname": w.PER_SET_FIELD,
				"label": "Paper Weight per Set (g)",
				"fieldtype": "Float",
				"precision": "2",
				"read_only": 1,
				"insert_after": w.TOTAL_GSM_FIELD,
				"depends_on": _CP_ONLY,
				"description": (
					"The weight of one set as it ships, in grams. For a Printed job this "
					"includes the printing allowance. Derived."
				),
			},
			{
				"fieldname": w.NET_FIELD,
				"label": "Net Product Weight / Carton (kg)",
				"fieldtype": "Float",
				"precision": "3",
				"read_only": 1,
				"insert_after": w.PER_SET_FIELD,
				"depends_on": _CP_ONLY,
				"description": "The paper in one carton, in kilograms, excluding the carton itself. Derived.",
			},
			{
				"fieldname": w.GROSS_FIELD,
				"label": "Gross Packed Weight / Carton (kg)",
				"fieldtype": "Float",
				"precision": "3",
				"read_only": 1,
				"insert_after": w.NET_FIELD,
				"depends_on": _CP_ONLY,
				"description": (
					"The paper plus the empty carton, in kilograms - the weight the carton "
					"ships at. Mirrored into Standard Weight Per Carton, which is what the "
					"order snapshot and the Job Card read. Derived."
				),
			},
		],
	}
