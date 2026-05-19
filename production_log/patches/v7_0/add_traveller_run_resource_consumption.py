"""S1 patch — attach the two new child doctypes (Job Traveller Run +
Job Resource Consumption) to the existing 3 Job Card doctypes via
Table custom fields.

Once attached, parent JCLs can render the per-station-burst grid
and the per-resource consumption grid via Jinja loops in their travellers.

Adds:
  - <JCL>.traveller_runs (Table → Job Traveller Run)
  - <JCL>.resource_consumption (Table → Job Resource Consumption)

Existing JCLs in scope:
  Job Card Carton (S1 — Carton traveller v4 uses these)
  Job Card Computer Paper (wired now, used by CP traveller redesign in S4)
  Job Card Label (wired now, used by Label traveller refinement in S6)
  Job Card ETR (if exists — wired now, used in S5)
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


JTRUN = "Job Traveller Run"
JRES = "Job Resource Consumption"

JCLS = [
	"Job Card Carton",
	"Job Card Computer Paper",
	"Job Card Label",
	"Job Card ETR",
]


def execute():
	for jcl in JCLS:
		if not frappe.db.exists("DocType", jcl):
			continue
		_attach_child_tables(jcl)
	frappe.clear_cache()


def _attach_child_tables(jcl_doctype):
	create_custom_fields(
		{
			jcl_doctype: [
				{
					"fieldname": "section_traveller_runs",
					"label": "Station-by-Station Production Log",
					"fieldtype": "Section Break",
					"insert_after": "job_status",
					"collapsible": 1,
				},
				{
					"fieldname": "traveller_runs",
					"label": "Traveller Runs",
					"fieldtype": "Table",
					"options": JTRUN,
					"insert_after": "section_traveller_runs",
					"allow_on_submit": 1,
					"description": (
						"One row per continuous production burst at a station. "
						"Multi-day jobs have multiple rows per station (RUN 1, RUN 2, …)."
					),
				},
				{
					"fieldname": "section_resource_consumption",
					"label": "Resource Consumption",
					"fieldtype": "Section Break",
					"insert_after": "traveller_runs",
					"collapsible": 1,
				},
				{
					"fieldname": "resource_consumption",
					"label": "Resource Consumption",
					"fieldtype": "Table",
					"options": JRES,
					"insert_after": "section_resource_consumption",
					"allow_on_submit": 1,
					"description": (
						"Reels, adhesive, glue, ink, plates, stitching wire, die, "
						"bundling strap — material variance feeds Gemba yield section."
					),
				},
			],
		},
		ignore_validate=True,
	)
