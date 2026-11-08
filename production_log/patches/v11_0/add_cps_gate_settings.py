"""Selling Settings and Internal Quotation fields for the CPS release gate (§4, §5).

Core and site-owned DocTypes cannot take DocField writes on Frappe Cloud, so
these are Custom Fields. Reaches outside the app, so it is ALSO called from
``install.after_install`` (runbook trap 7: install stamps patches without
running them). Idempotent: ``create_custom_fields`` updates in place.

Also retires the two thresholds §5 replaces - ``custom_cps_price_tolerance_pct``
and ``custom_cps_price_floor_pct`` - both 0 on the live site on 08/11/2026.
Deleted rather than hidden: nothing reads them after this release.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_lifecycle, cps_price_rules, cps_rules, so_spec_control

RETIRED_SELLING_SETTINGS_FIELDS = ("custom_cps_price_tolerance_pct", "custom_cps_price_floor_pct")


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	initialise_settings()
	retire_thresholds()
	frappe.clear_cache()


def initialise_settings():
	"""Write the intended values into tabSingles explicitly (Codex r5).

	A Custom Field default is metadata; it does not populate an existing
	Single. Each value is written only when blank, so a configured value -
	including a deliberate zero - survives a re-run. The SO mode is derived
	from the live tick so behaviour does not change on deploy.
	"""
	current = {
		f: frappe.db.get_single_value("Selling Settings", f)
		for f in (
			so_spec_control.CONTROL_FLAG, so_spec_control.SO_MODE_FIELD, so_spec_control.QUOTE_MODE_FIELD,
			so_spec_control.GATE_MODE_FIELD, cps_price_rules.ALLOWANCE_FIELD, cps_price_rules.ALLOWANCE_PCT_FIELD,
			cps_lifecycle.MIGRATION_AUTHORITY_FIELD,
		)
	}
	intended = {
		so_spec_control.SO_MODE_FIELD: cps_rules.QUOTE_MODE_ENFORCE if current[so_spec_control.CONTROL_FLAG] else cps_rules.QUOTE_MODE_OFF,
		so_spec_control.QUOTE_MODE_FIELD: cps_rules.QUOTE_MODE_WARN,
		so_spec_control.GATE_MODE_FIELD: so_spec_control.GATE_OFF,
		cps_price_rules.ALLOWANCE_FIELD: cps_price_rules.ALLOWANCE_DEFAULT_KES,
		cps_price_rules.ALLOWANCE_PCT_FIELD: cps_price_rules.ALLOWANCE_DEFAULT_PCT,
		cps_lifecycle.MIGRATION_AUTHORITY_FIELD: cps_lifecycle.DEFAULT_MIGRATION_AUTHORITY if frappe.db.exists("User", cps_lifecycle.DEFAULT_MIGRATION_AUTHORITY) else None,
	}
	for fieldname, value in intended.items():
		if current.get(fieldname) in (None, "") and value not in (None, ""):
			frappe.db.set_single_value("Selling Settings", fieldname, value)
			print("Selling Settings.{0} initialised to {1}".format(fieldname, value))


def retire_thresholds():
	for fieldname in RETIRED_SELLING_SETTINGS_FIELDS:
		name = "Selling Settings-{0}".format(fieldname)
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def get_custom_fields():
	fields = {
		"Selling Settings": [
			{
				"fieldname": so_spec_control.SO_MODE_FIELD,
				"label": "CPS Control on Sales Orders",
				"fieldtype": "Select",
				"options": "\n".join(("",) + cps_rules.QUOTE_MODES),
				"default": cps_rules.QUOTE_MODE_OFF,
				"insert_after": so_spec_control.CONTROL_FLAG,
				"description": (
					"Off: inert. Warn: every V1-V11 failure is shown but nothing is refused. "
					"Enforce on submit: the belt behind the job-card gate (checklist D) - refuses on submit. "
					"Blank falls back to the tick above (ticked = Enforce)."
				),
			},
			{
				"fieldname": so_spec_control.GATE_MODE_FIELD,
				"label": "Job Card Release Gate",
				"fieldtype": "Select",
				"options": "\n".join(("",) + so_spec_control.GATE_MODES),
				"default": so_spec_control.GATE_OFF,
				"insert_after": so_spec_control.SO_MODE_FIELD,
				"description": (
					"Off: cards are never held by the gate. Observe: every card is evaluated and the "
					"result recorded, but nothing is held and Print is never refused (observation mode). "
					"Enforce: a card from a controlled order line is held until every check passes."
				),
			},
			{
				"fieldname": so_spec_control.QUOTE_MODE_FIELD,
				"label": "CPS Control on Quotations",
				"fieldtype": "Select",
				"options": "\n".join(("",) + cps_rules.QUOTE_MODES),
				"default": cps_rules.QUOTE_MODE_WARN,
				"insert_after": so_spec_control.GATE_MODE_FIELD,
				"description": "Ships as Warn: a quotation line for a controlled Item with no specification is flagged and logged, never refused.",
			},
			{
				"fieldname": cps_price_rules.ALLOWANCE_FIELD,
				"label": "CPS Rounding Allowance (KES)",
				"fieldtype": "Currency",
				"default": "1.00",
				"insert_after": so_spec_control.QUOTE_MODE_FIELD,
				"description": "A Sales Order line matches the approved price when it is within min(this, approved rate x the percentage below). Zero approved rate = exact.",
			},
			{
				"fieldname": cps_price_rules.ALLOWANCE_PCT_FIELD,
				"label": "CPS Rounding Allowance (%)",
				"fieldtype": "Percent",
				"default": "1",
				"insert_after": cps_price_rules.ALLOWANCE_FIELD,
			},
			{
				"fieldname": cps_lifecycle.MIGRATION_AUTHORITY_FIELD,
				"label": "CPS Migration Authority",
				"fieldtype": "Link",
				"options": "User",
				"default": cps_lifecycle.DEFAULT_MIGRATION_AUTHORITY,
				"insert_after": cps_price_rules.ALLOWANCE_PCT_FIELD,
				"description": (
					"The user recorded as approver on every specification grandfathered by the "
					"revision migration. Defaults to Tanuj (08/11/2026); change it here to override. "
					"The stamp runs on the next migrate once the lifecycle fields have landed."
				),
			},
		],
	}
	if frappe.db.exists("DocType", "Internal Quotation"):
		fields["Internal Quotation"] = [
			{
				"fieldname": "vcl_price_basis_section",
				"label": "Price Basis (confirmed before transfer to the specification)",
				"fieldtype": "Section Break",
				"insert_after": "customer_price",
			},
			{
				"fieldname": "vcl_uom",
				"label": "Price UOM",
				"fieldtype": "Link",
				"options": "UOM",
				"insert_after": "vcl_price_basis_section",
				"allow_on_submit": 1,
				"description": "The unit customer_price is per. Nothing is inferred from the product type.",
			},
			{
				"fieldname": "vcl_currency",
				"label": "Price Currency",
				"fieldtype": "Link",
				"options": "Currency",
				"default": "KES",
				"insert_after": "vcl_uom",
				"allow_on_submit": 1,
			},
			{
				"fieldname": "vcl_tax_basis",
				"label": "Price Tax Basis",
				"fieldtype": "Select",
				"options": "\nNet\nGross",
				"insert_after": "vcl_currency",
				"allow_on_submit": 1,
				"description": "Net = ex-VAT. Gross = incl. 16% VAT; the specification stores rate = price / 1.16 and keeps the gross figure.",
			},
		]
	return fields
