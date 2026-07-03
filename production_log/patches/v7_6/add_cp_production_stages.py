"""Add Computer Paper per-stage production tracking table.

This intentionally attaches only to Job Card Computer Paper. The existing
traveller_runs and resource_consumption child tables remain separate per-run
output/resource logs and are not modified here.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


JC_CP = "Job Card Computer Paper"
JSTAGE = "Job Production Stage"


def execute():
	if not frappe.db.exists("DocType", JC_CP):
		return

	create_custom_fields(
		{
			JC_CP: [
				{
					"fieldname": "section_production_stages",
					"label": "Production Stages",
					"fieldtype": "Section Break",
					"insert_after": "production_notes",
					"collapsible": 1,
				},
				{
					"fieldname": "production_stages",
					"label": "Production Stages",
					"fieldtype": "Table",
					"options": JSTAGE,
					"insert_after": "section_production_stages",
					"allow_on_submit": 1,
					"description": (
						"One row per Computer Paper route stage. Machine Asset is optional "
						"and is category-limited to Plant & Machinery."
					),
				},
			],
		},
		ignore_validate=True,
	)
	frappe.clear_cache()
