"""Patch v9_2: the artwork tracker link, the deferral flag, and a Desk
control for the Numbering question.

Two problems, both of them the same shape — a rule that could not be satisfied
from the form it was enforced on.

**Numbering.** ``v8_3`` made ``numbering_confirmed`` mandatory on every new
Computer Paper specification and left it ``hidden``, because it is provenance
rather than an input: a Desk user who ticks it by hand without answering the
question beside it has recorded a confirmation that never happened. Compass
asks the question with an explicit Yes/No control and stamps the flag. Desk
never got one. The result was a form that looked usable and could not be
saved at all — the only visible control was the ``numbering_required`` Check,
and no state of a Check records that a person answered. CPT-SPEC-00059 was
cancelled over it and the same wall was hit again on 2026-08-06.

``numbering_answer`` is the missing control: a Select with the three states
the question actually has, blank being "not answered". It writes the two
stored fields, which keep their meanings exactly — ``numbering_required``
remains what production, the Job Card and the frozen order snapshot read, and
is set read-only on the form so there is one input rather than two that can
disagree.

**Artwork.** ``v8_3`` also made an attached file the price of submitting a
Printed specification. But VCL's artwork already lives in the Design and
Artwork Tracker — that is where it is drawn, revised and approved — so
attaching it to the specification made a second and staler copy of something
the business already tracks, and a specification whose design was genuinely
still being drawn could not be submitted at all.

``artwork_tracker`` links the tracker job instead. ``artwork_not_ready``
records the deferral when there is no artwork yet. Neither replaces
``artwork``: sixty-five live specifications carry an attached file and
removing the field would strand every one of them, so all three routes are
accepted by ``cps_cp_rules.artwork_evidence``.

``artwork_not_ready`` is an unguarded bypass and knowingly so — anybody who
can edit the specification can tick it. It is a record of a decision, not a
control. If that proves too loose the answer is to require a reason in
``artwork_notes``, which is an additive rule and not a migration.

All three fields are ``allow_on_submit``. A specification is submitted long
before its artwork lands, and the tracker job has to be linkable to a closed
spec without cancelling it — the revise-in-place rule this doctype already
follows for its weight section.

**No backfill.** Every existing record legitimately has all three unset: no
tracker was linked because the field did not exist, and nobody deferred
anything. The estate is untouched by design — ``numbering_block_reason`` only
bites a new record or a changed answer, and ``before_submit`` never re-runs on
a record that left draft before this release.

Idempotent by construction. ``create_custom_fields`` inserts what is absent
and reconciles the properties of what is present; ``make_property_setter``
replaces any setter for the same property. Both are also exported into
``fixtures/`` — the patch lands them on the existing site immediately, the
fixture is what stops them existing only in one database.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_cp_rules

# Only Computer Paper is asked any of this, on the same terms as v8_3. The
# stored columns exist for every product type — a Custom Field is a column on
# the table — and widening the display later is a property change, not a
# migration.
_COMPUTER_PAPER_ONLY = "eval:doc.product_type=='{0}'".format(cps_cp_rules.COMPUTER_PAPER)

_TRACKER_DOCTYPE = "Design and Artwork Tracker"

# The tracker is named ``<customer> - <job card number>``, which is not what
# anybody looking for a job knows it by. Frappe's Link search covers the name
# plus whatever ``search_fields`` names, so without this the new link is
# searchable only by a string the user does not have.
_TRACKER_SEARCH_FIELDS = "job_name,customer_name,department"

PROPERTY_SETTERS = (
	# One input, not two. numbering_answer is what a person sets; the Check is
	# left visible so the recorded answer can still be read off the form, but
	# editing it directly would set the business answer without recording that
	# anybody gave it — which is the exact ambiguity v8_3 exists to end.
	{
		"doctype": "Customer Product Specification",
		"fieldname": cps_cp_rules.NUMBERING_FIELD,
		"property": "read_only",
		"property_type": "Check",
		"value": "1",
	},
)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)

	for setter in PROPERTY_SETTERS:
		if not frappe.db.exists("DocType", setter["doctype"]):
			continue
		frappe.make_property_setter(setter)

	set_tracker_search_fields()

	frappe.clear_cache(doctype="Customer Product Specification")


def set_tracker_search_fields():
	"""Make the tracker findable by job name from the specification's Link.

	Guarded on the doctype existing rather than assumed: ``Design and Artwork
	Tracker`` is a Desk-created doctype (``custom: 1``) that lives in no app
	repo, so a site rebuilt from this app alone will not have it. The Custom
	Field is still created — a Link whose target is absent is inert rather than
	broken, and the tracker is restored by a fixture import, not by this patch.
	"""
	if not frappe.db.exists("DocType", _TRACKER_DOCTYPE):
		return
	frappe.make_property_setter({
		"doctype": _TRACKER_DOCTYPE,
		"doctype_or_field": "DocType",
		"property": "search_fields",
		"property_type": "Data",
		"value": _TRACKER_SEARCH_FIELDS,
	})


def get_custom_fields():
	return {
		"Customer Product Specification": [
			{
				"fieldname": cps_cp_rules.NUMBERING_ANSWER_FIELD,
				"label": "Numbering",
				"fieldtype": "Select",
				"options": "\n{0}\n{1}".format(
					cps_cp_rules.NUMBERING_ANSWER_YES,
					cps_cp_rules.NUMBERING_ANSWER_NO,
				),
				"insert_after": cps_cp_rules.NUMBERING_FIELD,
				"depends_on": _COMPUTER_PAPER_ONLY,
				"allow_on_submit": 1,
				"description": (
					"Is this product numbered? Leaving it blank is not the same as No - "
					"production cannot tell the two apart later. Sets Numbering Required and "
					"records that a person answered. " + cps_cp_rules.NUMBERING_RANGE_NOTICE
				),
			},
			{
				"fieldname": cps_cp_rules.ARTWORK_TRACKER_FIELD,
				"label": "Design & Artwork Job",
				"fieldtype": "Link",
				"options": _TRACKER_DOCTYPE,
				"insert_after": cps_cp_rules.ARTWORK_FIELD,
				"depends_on": _COMPUTER_PAPER_ONLY,
				"allow_on_submit": 1,
				"description": (
					"The Design and Artwork Tracker job this specification is plated from. "
					"Search by job name. Use this instead of attaching a file - the tracker "
					"holds the final design and its approval state."
				),
			},
			{
				"fieldname": cps_cp_rules.ARTWORK_NOT_READY_FIELD,
				"label": "Artwork Not Yet Ready",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": cps_cp_rules.ARTWORK_TRACKER_FIELD,
				"depends_on": _COMPUTER_PAPER_ONLY,
				"allow_on_submit": 1,
				"description": (
					"Tick to submit a Printed specification whose artwork is still "
					"outstanding. Say why in Artwork Notes. Untick and link the tracker job "
					"once the design is ready - the field stays editable after submit."
				),
			},
		],
	}
