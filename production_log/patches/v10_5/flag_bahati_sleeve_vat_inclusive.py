"""Declare the one CPS Price row that is a GROSS figure.

CPS Price labels its rate "Rate (net, ex-VAT)" and all but one live row obeys
that. The exception is deliberate and is documented on the specification itself
(`CTN-SPEC-00025-1`, BAHATI VENTURES, coffee cup sleeve):

    "Rate restated as 1.70 VAT-INCLUSIVE so the order bills exactly 85,000 for
     50,000 pcs; the previous 1.4655 ex-VAT rounded to 1.47 on submit and the
     Sales Order re-fetched it, billing 73,500."

The live orders agree: SAL-ORD-2026-00122 carries rate 1.47 / net 1.2672 (the
failure), SAL-ORD-2026-00122-1 carries 1.70 / net 1.4655 (the fix).

So the gross rate is correct where it sits and must not be changed. What was
missing was any way for the data to SAY it is gross — which the new
`vat_inclusive` field now provides, and which the CPS price mirror needs before
it can publish an ex-VAT price list without putting this customer 16% high.

Data-only, and the only sanctioned way to touch a submitted record. Not in
`install.py`: a fresh site has no such row, and inventing one would be worse
than the gap.
"""

import frappe

SPEC = "CTN-SPEC-00025-1"
GROSS_RATE = 1.7


def execute():
	if not frappe.db.has_column("CPS Price", "vat_inclusive"):
		# The field ships in the same deploy; if the model has not synced, do
		# nothing rather than half-apply. Re-runnable, so the next migrate gets it.
		return

	rows = frappe.get_all(
		"CPS Price",
		filters={
			"parent": SPEC,
			"parenttype": "Customer Product Specification",
			"parentfield": "pricing",
			"rate": GROSS_RATE,
		},
		fields=["name", "vat_inclusive"],
	)
	# Deliberately narrow. If the spec has been revised and no longer carries
	# exactly one row at this rate, a human should look rather than a patch guess.
	if len(rows) != 1:
		frappe.log_error(
			f"Expected exactly one CPS Price row on {SPEC} at {GROSS_RATE}, found "
			f"{len(rows)}. VAT basis not flagged; the price mirror will publish "
			f"this customer's rate as if it were net.",
			"v10_5 flag_bahati_sleeve_vat_inclusive",
		)
		return

	if rows[0].vat_inclusive:
		return

	frappe.db.set_value(
		"CPS Price", rows[0].name, "vat_inclusive", 1, update_modified=False
	)
