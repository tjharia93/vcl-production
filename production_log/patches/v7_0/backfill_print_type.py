"""S1 patch — backfill print_type values across existing records.

Mapping per Sprint-0 audit (msg 267) §3:
  Carton:           printing_or_plain literal → print_type (1:1, "Plain"/"Printed")
  Computer Paper:   number_of_colours==0 and no spot_colours → "Plain", else "Printed"
  Label:            same as CP
  ETR (any home):   etr_output_type "ETR Plain Rolls" → "Plain"
                    etr_output_type in ("ETR Printed Rolls","Printed Reel") → "Printed"
                    (Printed Reel cases flagged for R2R migration in S5)
"""

import frappe


CPS = "Customer Product Specification"
JC_CARTON = "Job Card Carton"
JC_CP = "Job Card Computer Paper"
JC_LABEL = "Job Card Label"
JC_ETR = "Job Card ETR"


def execute():
	_backfill_carton_cps()
	_backfill_etr_cps()
	_backfill_colour_driven_cps(JC_CP_PRODUCT_TYPE="Computer Paper")
	_backfill_colour_driven_cps(JC_CP_PRODUCT_TYPE="Label")

	# JCLs — snapshot from parent CPS where possible
	for jc in (JC_CARTON, JC_CP, JC_LABEL):
		_snapshot_jcl_from_cps(jc)
	if frappe.db.exists("DocType", JC_ETR):
		_snapshot_jcl_from_cps(JC_ETR)


def _backfill_carton_cps():
	"""Carton CPS already has printing_or_plain — copy to print_type."""
	rows = frappe.db.get_all(
		CPS,
		filters={"product_type": "Carton"},
		fields=["name", "printing_or_plain"],
	)
	for r in rows:
		value = r.printing_or_plain or "Plain"
		if value not in ("Plain", "Printed"):
			value = "Plain"
		frappe.db.set_value(CPS, r.name, "print_type", value, update_modified=False)


def _backfill_etr_cps():
	"""ETR CPS — map etr_output_type to print_type."""
	rows = frappe.db.get_all(
		CPS,
		filters={"product_type": ["in", ("ETR", "ETR (Reel to Reel Printing)")]},
		fields=["name", "etr_output_type"],
	)
	for r in rows:
		eot = r.etr_output_type or ""
		print_type = "Plain" if eot == "ETR Plain Rolls" else "Printed"
		frappe.db.set_value(CPS, r.name, "print_type", print_type, update_modified=False)


def _backfill_colour_driven_cps(JC_CP_PRODUCT_TYPE):
	"""CP/Label CPS — derive print_type from colour usage."""
	rows = frappe.db.get_all(
		CPS,
		filters={"product_type": JC_CP_PRODUCT_TYPE},
		fields=[
			"name",
			"number_of_colours",
			"uses_c",
			"uses_m",
			"uses_y",
			"uses_k",
		],
	)
	for r in rows:
		has_process = any((r.uses_c, r.uses_m, r.uses_y, r.uses_k))
		spot_count = frappe.db.count(
			"Spot Colour", filters={"parent": r.name, "parenttype": CPS}
		)
		print_type = (
			"Printed"
			if (has_process or (r.number_of_colours or 0) > 0 or spot_count > 0)
			else "Plain"
		)
		frappe.db.set_value(CPS, r.name, "print_type", print_type, update_modified=False)


def _snapshot_jcl_from_cps(jcl_doctype):
	"""Copy parent CPS.print_type into JCL.print_type for all existing records."""
	# Job Card Carton uses customer_product_spec; some others may differ
	link_field = _find_cps_link_field(jcl_doctype)
	if not link_field:
		return

	rows = frappe.db.sql(
		f"""
		SELECT jc.name, cps.print_type
		FROM `tab{jcl_doctype}` jc
		LEFT JOIN `tab{CPS}` cps ON cps.name = jc.`{link_field}`
		""",
		as_dict=True,
	)
	for r in rows:
		if r.print_type:
			frappe.db.set_value(jcl_doctype, r.name, "print_type", r.print_type, update_modified=False)


def _find_cps_link_field(jcl_doctype):
	"""Heuristic: most JCLs use customer_product_spec; fall back to any Link to CPS."""
	if frappe.db.has_column(jcl_doctype, "customer_product_spec"):
		return "customer_product_spec"

	meta = frappe.get_meta(jcl_doctype)
	for f in meta.fields:
		if f.fieldtype == "Link" and f.options == CPS:
			return f.fieldname
	return None
