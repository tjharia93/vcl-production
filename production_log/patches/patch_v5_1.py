"""
Patch v5_1: Realign Workstation Product Line tags to FINAL §A2.

Why this exists
---------------
`patch_v5_0._migrate_legacy_tags` copies every Workstation's legacy
single-Select `custom_product_line` value into a matching child row on
`custom_product_line_tags`. Before Phase 5 shipped, every Workstation on
the live site sat at the v2_0 default `custom_product_line = 'All'`, so
the migration tagged every workstation `All`. The planner's
`get_workstation_columns(product_line)` matches on
`(tag.product_line = <dept> OR tag.product_line = 'All')`, so the board
currently shows every workstation on both dept tabs — the user-visible
symptom that prompted this patch.

Per FINAL §A2 only `Design Desk` legitimately carries `All`. Every press,
collator, and slitter has a specific product-line tag set. This patch
replaces the tags on exactly the eight canonical workstations; any other
workstation (whether site-specific or added later by Tanuj) is left
untouched.

Idempotent: re-running on an already-aligned workstation short-circuits.
"""

import frappe


CANONICAL_TAGS = {
	"Design Desk":  ["All"],
	"Miyakoshi 01": ["Computer Paper", "ETR / Thermal"],
	"Miyakoshi 02": ["Computer Paper", "ETR / Thermal"],
	"Hamada 01":    ["Computer Paper"],
	"Collator 1":   ["Computer Paper"],
	"Collator 2":   ["Computer Paper"],
	"Slitter 1":    ["ETR / Thermal"],
	"Slitter 2":    ["ETR / Thermal"],
}


def execute():
	for ws_name, canonical in CANONICAL_TAGS.items():
		if not frappe.db.exists("Workstation", ws_name):
			continue

		ws = frappe.get_doc("Workstation", ws_name)
		existing = [row.product_line for row in ws.get("custom_product_line_tags", [])]
		if set(existing) == set(canonical):
			continue

		ws.set("custom_product_line_tags", [])
		for tag in canonical:
			ws.append("custom_product_line_tags", {"product_line": tag})
		ws.save(ignore_permissions=True)

	frappe.db.commit()
