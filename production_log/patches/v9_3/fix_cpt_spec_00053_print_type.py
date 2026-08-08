"""Patch v9_3: correct CPT-SPEC-00053's Print Type, and add the rule that
would have refused it.

CPT-SPEC-00053 (Delight Printers — Imarika Sacco) carries ``print_type =
"Plain"`` while linked to ``Computer Paper Pre-Printed-9.5x11x5.5-2 Part`` and
ticking all four CMYK process inks. Both are contradictions of a Plain
record on their own terms: ``cps_cp_rules.colour_block_reason`` already
refuses a Plain specification carrying ink, and the new
``item_print_type_mismatch_reason`` (this same release) refuses a Print Type
that disagrees with the linked Item's own Plain/Pre-Printed category. Neither
rule caught this record because both are transition rules — they bind a save
that changes the thing they are about, not a record that already carried the
contradiction before either rule existed.

The ink says which correction is right: four process inks is a printed job,
not a blank sheet, so Print Type moves to "Printed" and nothing else on the
record changes.

Checked across the live estate before writing this patch — of 19 Computer
Paper specifications carrying a ``linked_item``, this is the only one where
Print Type disagrees with the Item's group. It is a one-record correction,
not a sweep.

Written to the table directly, on the same terms as every other patch in
this app that corrects a submitted record: patches run below the Document
layer by design, so ``validate()`` — which would refuse this exact write
under the rule this release adds — is not in the way of fixing the row that
predates it. ``update_modified=False`` so the record does not read as
touched today; nothing about the job itself changed.

Idempotent: only writes if the stored value is still "Plain", so re-running
this patch (or running it against a site where the record was already
corrected by hand) does nothing.
"""

import frappe

_SPEC = "CPT-SPEC-00053"
_FIELD = "print_type"
_WRONG = "Plain"
_RIGHT = "Printed"


def execute():
	if not frappe.db.exists("Customer Product Specification", _SPEC):
		return

	current = frappe.db.get_value("Customer Product Specification", _SPEC, _FIELD)
	if current != _WRONG:
		return

	frappe.db.set_value(
		"Customer Product Specification", _SPEC, _FIELD, _RIGHT,
		update_modified=False,
	)
