"""Patch v9_4: correct every live Computer Paper specification that is
stamped Plain while carrying print ink.

Same defect class as v9_3's ``CPT-SPEC-00053``, missed there because that
sweep only checked records carrying a ``linked_item`` — these seven have
none, so the new ``item_print_type_mismatch_reason`` rule has nothing to
compare against and stays silent on them. The older, always-on signal already
in this module catches them instead: ``cps_cp_rules.colour_block_reason``
refuses "Plain specification cannot carry print inks" — a rule these records
have always violated, and always will keep violating, because it is a
transition rule (see the module docstring) and none of them has had its
Print Type or inks deliberately re-touched since the rule shipped.

Checked against the live estate before writing this patch: every submitted
or draft Computer Paper specification with ``print_type = "Plain"``. Eleven
total. Two (``CPT-SPEC-00066``, ``CPT-SPEC-00068``) are genuinely Plain — no
ink, linked to the real ``Computer Paper Plain`` item — and untouched. One
(``CPT-SPEC-00049``) is cancelled and untouched; nothing reads a cancelled
document. The remaining seven all carry at least one CMYK process ink, which
is the same signal v9_3 used to correct ``CPT-SPEC-00053``: ink recorded
means the job is printed, not blank paper.

Written to the table directly, on the same terms as v9_3 and every other
patch here that corrects a submitted record — patches run below the Document
layer, so ``validate()`` (which would refuse this exact write, correctly, on
a save through the ordinary Desk/REST/Data-Import routes) is not in the way
of fixing rows that predate the rule. ``CPT-SPEC-00051`` is still a draft;
included here anyway rather than left for a human to catch mid-edit, on the
same "correct the record, not just the future" logic as the rest of this
patch. ``update_modified=False`` throughout — nothing about any of these jobs
changed, only how the record describes them.

Idempotent: each write is guarded on the stored value still being "Plain", so
re-running this patch, or running it against a site where a record was
already corrected by hand, does nothing to that record.
"""

import frappe

_FIELD = "print_type"
_WRONG = "Plain"
_RIGHT = "Printed"

_SPECS = (
	"CPT-SPEC-00048",
	"CPT-SPEC-00049-1",
	"CPT-SPEC-00050",
	"CPT-SPEC-00051",
	"CPT-SPEC-00052",
	"CPT-SPEC-00054",
	"CPT-SPEC-00055",
)


def execute():
	for name in _SPECS:
		_correct(name)


def _correct(name):
	if not frappe.db.exists("Customer Product Specification", name):
		return

	current = frappe.db.get_value("Customer Product Specification", name, _FIELD)
	if current != _WRONG:
		return

	frappe.db.set_value(
		"Customer Product Specification", name, _FIELD, _RIGHT,
		update_modified=False,
	)
