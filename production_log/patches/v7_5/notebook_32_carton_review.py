"""Notebook 32 (2026-05-20) — Carton Job Card / CPS review.

Codifies Tanuj's reMarkable "Notebook 32" review of the carton Customer
Product Specification + Job Card. Five points:

  1. Remove Board Type             -> hide board_type on CPS
  2. printing_or_plain vs print_type -> keep print_type, retire (hide)
     printing_or_plain on CPS + Job Card Carton, move print_type to the
     form header (insert_after job_size)
  3. GSM layers toggle by Ply      -> depends_on on the 3/4/5-ply gsm +
     material fields, gated on doc.ply (3 -> layers 1-3, 5 -> 1-5,
     SFK -> 1-2)
  4. Packing not required (carton) -> hide the Packing section for Carton
  5. Carton layout on its own page -> handled in carton_job_traveller.html
     (the print format), not this patch

Applied live on prod 2026-05-20 via REST (see CHANGELOG_DAILY.md). This
patch reproduces points 1-4 on a fresh install. Idempotent —
frappe.make_property_setter replaces any existing setter for the same
(doctype, fieldname, property).
"""

import frappe

# ply Select values are "SFK", "3", "5" (blank = unset)
GSM3 = "doc.ply=='3' || doc.ply=='5'"   # layer 3 — 3-ply and 5-ply
GSM5 = "doc.ply=='5'"                    # layers 4 & 5 — 5-ply only

# (doctype, fieldname, property, property_type, value)
PROPERTY_SETTERS = [
	# point 1 — remove Board Type. Hide it AND clear its conditional-mandatory
	# rule — a hidden field that is still mandatory blocks the Carton spec from
	# saving (the user cannot fill a field they cannot see).
	("Customer Product Specification", "board_type", "hidden", "Check", 1),
	("Customer Product Specification", "board_type", "mandatory_depends_on", "Code", ""),
	# point 2 — retire legacy printing_or_plain (print_type is the keeper)
	("Customer Product Specification", "printing_or_plain", "hidden", "Check", 1),
	("Job Card Carton",                "printing_or_plain", "hidden", "Check", 1),
	# point 4 — hide Packing section for Carton, keep it for other types
	("Customer Product Specification", "packing_section", "depends_on", "Code", "eval:doc.product_type!='Carton'"),
	# point 3 — GSM layers toggle by ply — CPS (also gated on product_type)
	("Customer Product Specification", "3_ply_bottom_gsm",         "depends_on", "Code", f"eval:doc.product_type=='Carton' && ({GSM3})"),
	("Customer Product Specification", "3_ply_top_layer_material", "depends_on", "Code", f"eval:doc.product_type=='Carton' && ({GSM3})"),
	("Customer Product Specification", "4_ply_fluting_gsm",        "depends_on", "Code", f"eval:doc.product_type=='Carton' && {GSM5}"),
	("Customer Product Specification", "4_ply_top_layer_material", "depends_on", "Code", f"eval:doc.product_type=='Carton' && {GSM5}"),
	("Customer Product Specification", "5_ply_fluting_gsm",        "depends_on", "Code", f"eval:doc.product_type=='Carton' && {GSM5}"),
	("Customer Product Specification", "5_ply_top_layer_material", "depends_on", "Code", f"eval:doc.product_type=='Carton' && {GSM5}"),
	# point 3 — GSM layers toggle by ply — Job Card Carton (always carton)
	("Job Card Carton", "3_ply_bottom_gsm",         "depends_on", "Code", f"eval:{GSM3}"),
	("Job Card Carton", "3_ply_top_layer_material", "depends_on", "Code", f"eval:{GSM3}"),
	("Job Card Carton", "4_ply_fluting_gsm",        "depends_on", "Code", f"eval:{GSM5}"),
	("Job Card Carton", "4_ply_top_layer_material", "depends_on", "Code", f"eval:{GSM5}"),
	("Job Card Carton", "5_ply_fluting_gsm",        "depends_on", "Code", f"eval:{GSM5}"),
	("Job Card Carton", "5_ply_top_layer_material", "depends_on", "Code", f"eval:{GSM5}"),
]


def execute():
	for doctype, fieldname, prop, ptype, value in PROPERTY_SETTERS:
		if not frappe.db.exists("DocType", doctype):
			continue
		frappe.make_property_setter({
			"doctype":       doctype,
			"fieldname":     fieldname,
			"property":      prop,
			"value":         value,
			"property_type": ptype,
		})

	# point 2 — move print_type to the form header (after job_size on CPS)
	cf = "Customer Product Specification-print_type"
	if frappe.db.exists("Custom Field", cf):
		frappe.db.set_value("Custom Field", cf, "insert_after", "job_size")

	frappe.clear_cache()
