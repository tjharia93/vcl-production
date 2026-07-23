"""Additive Custom Fields for the Computer Paper specification capture.

Four fields, none of which changes the meaning of anything that already exists:

``numbering_confirmed``
	The whole point of the release. ``numbering_required`` is a Check and a Check
	has two states, so an unticked box has always meant "No" and "nobody was
	asked" at the same time. Fifty-nine live Computer Paper records reach this
	release with that ambiguity in them and there is no way to tell them apart
	retrospectively — so this flag records, from now on, that a person actually
	gave the answer. It is not a second business answer: nothing downstream reads
	it, no order snapshot freezes it and no Job Card is shaped by it.

	Hidden on the ordinary Desk layout. It is a provenance flag rather than an
	input, and a Desk user who ticks it by hand without answering the question
	beside it has recorded a confirmation that never happened. Compass sets it
	from the explicit Yes/No control, and ``cps_cp_rules`` is what demands it.

``numbering_notes``
	What is numbered and how, when the answer is Yes. The start and end of a
	range are job-specific and belong on the Job Card, which is said in the
	description so the two are never confused.

``artwork`` / ``artwork_notes``
	The file the job is plated from, and what to know about it. ``artwork`` is an
	Attach, which stores a file URL; everything that makes that URL safe - private
	only, bound to this document, an allowed kind, a sane size - lives in
	``cps_cp_rules`` and in the Compass endpoints that call it. The field is
	deliberately NOT read-only: Desk has always been able to attach a file to a
	document and taking that away here would buy nothing, since Desk enforces its
	own permissions on the attachment.

Idempotent by construction: ``create_custom_fields`` inserts what is absent and
reconciles the properties of what is present, so a re-run corrects a site where
somebody has edited one of these by hand rather than duplicating it.

The same four fields are also exported into ``fixtures/custom_field.json``,
which is what a Frappe Cloud ``bench migrate`` syncs and what makes a site
rebuilt from this app reproduce them. The patch is what lands them on the
existing site immediately; the fixture is what stops them existing only in one
database. Both are needed - CPS already carried seventeen Custom Fields that
lived nowhere but the database, which is the reason the fixture list exists.

No backfill. Every existing record legitimately has ``numbering_confirmed``
unset, because nobody confirmed anything on it, and writing 1 across the estate
would destroy the one fact this field is for.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_cp_rules

# Only Computer Paper is asked these questions in this release, so the two
# Numbering companions and the artwork pair are shown for it alone. The stored
# columns exist for every product type - a Custom Field is a column on the table
# - and widening the display later is a property change rather than a migration.
_COMPUTER_PAPER_ONLY = "eval:doc.product_type=='{0}'".format(cps_cp_rules.COMPUTER_PAPER)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache(doctype="Customer Product Specification")


def get_custom_fields():
	return {
		"Customer Product Specification": [
			{
				"fieldname": cps_cp_rules.NUMBERING_CONFIRMED_FIELD,
				"label": "Numbering Answer Confirmed",
				"fieldtype": "Check",
				"default": "0",
				"hidden": 1,
				"no_copy": 0,
				"insert_after": cps_cp_rules.NUMBERING_FIELD,
				"description": (
					"Records that a person actually answered the Numbering question, so an "
					"explicit No can be told apart from a question nobody was asked. Set by "
					"the Computer Paper Specification screen; not an input."
				),
			},
			{
				"fieldname": cps_cp_rules.NUMBERING_NOTES_FIELD,
				"label": "Numbering Notes",
				"fieldtype": "Small Text",
				"insert_after": cps_cp_rules.NUMBERING_CONFIRMED_FIELD,
				"depends_on": "eval:doc.{0}".format(cps_cp_rules.NUMBERING_FIELD),
				"description": cps_cp_rules.NUMBERING_RANGE_NOTICE,
			},
			{
				"fieldname": "artwork_section",
				"label": "Artwork",
				"fieldtype": "Section Break",
				"insert_after": "standard_weight_per_carton",
				"depends_on": _COMPUTER_PAPER_ONLY,
			},
			{
				"fieldname": cps_cp_rules.ARTWORK_FIELD,
				"label": "Artwork",
				"fieldtype": "Attach",
				"insert_after": "artwork_section",
				"depends_on": _COMPUTER_PAPER_ONLY,
				"description": (
					"The file this job is plated from. Private attachments only. A Printed "
					"specification cannot be submitted without one; a Plain one does not need one."
				),
			},
			{
				"fieldname": cps_cp_rules.ARTWORK_NOTES_FIELD,
				"label": "Artwork Notes",
				"fieldtype": "Small Text",
				"insert_after": cps_cp_rules.ARTWORK_FIELD,
				"depends_on": _COMPUTER_PAPER_ONLY,
				"description": (
					"Anything the file does not say for itself - which revision it is, what the "
					"customer approved, what to ignore on it."
				),
			},
		],
	}
