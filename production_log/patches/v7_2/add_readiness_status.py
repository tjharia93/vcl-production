"""S2 patch — add readiness flag fields on Job Card doctypes.

Per White Paper v4 §4.2 + §11 (Plates Annex):
  plate_ready          (Check) — Designers Tracker confirms plate ready
  material_in_stock    (Check) — board grade / face stock in inventory
  customer_hold        (Check) — customer has paused, do not release
  artwork_approved     (Check) — S4+ Designers Tracker link (placeholder now)
  plates_lead_time_clear (Check) — S4+ supplier ETA acceptable (placeholder)

Release Plan generator reads these to decide bucket (overdue / due / pending).
Set by hand initially; S4 wires Designers Tracker linkage for plate flags.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


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
		create_custom_fields(
			{
				jcl: [
					{
						"fieldname": "section_readiness",
						"label": "Release Readiness",
						"fieldtype": "Section Break",
						"insert_after": "job_status",
						"collapsible": 1,
					},
					{
						"fieldname": "plate_ready",
						"label": "Plate Ready",
						"fieldtype": "Check",
						"insert_after": "section_readiness",
						"description": "Plate is in-house and mounted-ready. S4+: managed by Designers Tracker.",
					},
					{
						"fieldname": "material_in_stock",
						"label": "Material in Stock",
						"fieldtype": "Check",
						"insert_after": "plate_ready",
						"description": "Board grade / face stock / paper reels confirmed in inventory.",
					},
					{
						"fieldname": "col_break_readiness",
						"fieldtype": "Column Break",
						"insert_after": "material_in_stock",
					},
					{
						"fieldname": "customer_hold",
						"label": "Customer Hold",
						"fieldtype": "Check",
						"insert_after": "col_break_readiness",
						"description": "Customer has paused this job — do not release until cleared.",
					},
					{
						"fieldname": "artwork_approved",
						"label": "Artwork Approved",
						"fieldtype": "Check",
						"insert_after": "customer_hold",
						"description": "S4+: linked to Designers Tracker design_status = Approved.",
					},
					{
						"fieldname": "plates_lead_time_clear",
						"label": "Plates Lead Time Clear",
						"fieldtype": "Check",
						"insert_after": "artwork_approved",
						"description": "S4+: linked to Designers Tracker expected_ready_date ≤ planned release date.",
					},
				],
			},
			ignore_validate=True,
		)
	frappe.clear_cache()
