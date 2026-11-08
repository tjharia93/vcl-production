"""Copy the legacy ``vat_inclusive`` ticks into the §5 tax-basis fields.

Three live rows carry the tick (all Rejected: CTN-SPEC-00025-1, CPT-SPEC-00079,
CPT-SPEC-00010) plus BAHATI's sleeve flagged by v10_5. Each becomes
``tax_basis`` = "Gross entered — VAT 16%" with ``entered_gross`` = the stored
``rate`` as legacy evidence. The ``rate`` itself is NOT recomputed: those rows
were approved or rejected as they stand and the figure is the record.

The field is hidden by the doctype JSON, not dropped: no data is lost and the
column stays for the audit. Idempotent - a row with ``tax_basis`` set is left
alone. Post-model-sync because it writes columns this migrate adds.
"""

import frappe

from production_log.job_card_tracking import cps_price_rules


def execute():
	if not (frappe.db.has_column("CPS Price", "vat_inclusive") and frappe.db.has_column("CPS Price", "tax_basis")):
		return
	rows = frappe.db.sql(
		"""SELECT name, parent, rate, uom FROM `tabCPS Price`
		WHERE vat_inclusive = 1 AND (tax_basis IS NULL OR tax_basis = '')""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value(
			"CPS Price",
			row.name,
			{
				"tax_basis": cps_price_rules.TAX_BASIS_GROSS_VAT,
				"entered_gross": row.rate,
				"entered_uom": row.uom,
				"tax_rate": cps_price_rules.VAT_RATE_PCT,
				"rounding_method": "legacy vat_inclusive tick; rate not recomputed",
			},
			update_modified=False,
		)
		print("CPS Price {0} on {1}: vat_inclusive copied to tax_basis".format(row.name, row.parent))
	if rows:
		frappe.db.commit()
