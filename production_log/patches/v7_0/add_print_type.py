"""S1 patch — add unified print_type field across CPS + JCL doctypes.

Per White Paper v4 §2.1: replaces Carton's `printing_or_plain` Select and ETR's
3-value `etr_output_type` Select with a single `print_type` field
(values: Plain, Printed) on CPS and on all Job Card doctypes.

Also adds `print_side` Select on CPS + JC Computer Paper / JC ETR for the
Front-only vs Front&Back distinction (v3 markup p.24).

Carton's existing `printing_or_plain` field is left in place by this patch;
v7_0/backfill_print_type.py copies its values into `print_type`. A later patch
(post-S2) may drop `printing_or_plain` once all reports + Jinja have been
re-pointed.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CPS = "Customer Product Specification"
JC_CARTON = "Job Card Carton"
JC_CP = "Job Card Computer Paper"
JC_LABEL = "Job Card Label"
JC_ETR = "Job Card ETR"

PRINT_TYPE_OPTIONS = "\n".join(["Plain", "Printed"])
PRINT_SIDE_OPTIONS = "\n".join(["N/A", "Front Only", "Front and Back", "Back Only"])


def execute():
	# print_type on CPS — applies to all product_type sections
	create_custom_fields(
		{
			CPS: [
				{
					"fieldname": "print_type",
					"label": "Print Type",
					"fieldtype": "Select",
					"options": PRINT_TYPE_OPTIONS,
					"insert_after": "printing_or_plain",
					"description": (
						"Unified Plain/Printed flag across all product lines. "
						"Replaces Carton's printing_or_plain and ETR's etr_output_type "
						"(per White Paper v4 §2.1)."
					),
				},
			],
		},
		ignore_validate=True,
	)

	# print_type snapshot on each JCL (snapshots from CPS on create)
	for jc in (JC_CARTON, JC_CP, JC_LABEL):
		_safely_add_print_type(jc)

	# JC ETR exists too — add print_type there (S5 will wire UI fully)
	if frappe.db.exists("DocType", JC_ETR):
		_safely_add_print_type(JC_ETR)

	# print_side on CP + ETR (and CPS for spec)
	for dt in (CPS, JC_CP):
		_safely_add_print_side(dt)
	if frappe.db.exists("DocType", JC_ETR):
		_safely_add_print_side(JC_ETR)

	frappe.clear_cache()


def _safely_add_print_type(doctype):
	create_custom_fields(
		{
			doctype: [
				{
					"fieldname": "print_type",
					"label": "Print Type",
					"fieldtype": "Select",
					"options": PRINT_TYPE_OPTIONS,
					"insert_after": "specification_name",
					"description": "Snapshot from CPS / VPT. Drives traveller station rendering.",
					"in_list_view": 1,
				},
			],
		},
		ignore_validate=True,
	)


def _safely_add_print_side(doctype):
	create_custom_fields(
		{
			doctype: [
				{
					"fieldname": "print_side",
					"label": "Print Side",
					"fieldtype": "Select",
					"options": PRINT_SIDE_OPTIONS,
					"default": "N/A",
					"insert_after": "print_type",
					"depends_on": "eval:doc.print_type == 'Printed'",
					"description": (
						"For Printed jobs only — Front Only vs Front and Back vs Back Only. "
						"N/A when Plain (v3 markup p.24)."
					),
				},
			],
		},
		ignore_validate=True,
	)
