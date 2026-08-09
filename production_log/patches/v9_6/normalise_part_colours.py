"""Patch v9_6: normalise part colours before the field becomes a Select.

Ordering is the entire point of this patch, and it is why it is registered under
``[pre_model_sync]`` rather than beside its v9_6 sibling.

``Colour of Parts.colour`` is free text today and the live estate holds both
``WHITE`` (CPT-SPEC-00063) and ``white`` (CPT-SPEC-00038-1). The same release
turns that field into a Select in the doctype JSON, and Frappe validates a
Select against its options on every save - so a specification still holding
``WHITE`` when the Select lands becomes **unsaveable**. Not read-only:
unsaveable, with an error naming the allowed values and no hint that the stored
one used to be legal.

That is not hypothetical. It is exactly what v9_5 had to undo on Workstation,
where narrowing a Select's options without migrating the rows froze nine records.

The doctype JSON change applies during the model sync. ``[pre_model_sync]`` runs
before it - which is precisely what that section is for, in its own words: "work
that must happen while a column still has its old type". So the rows are
rewritten while ``colour`` is still a Data field, and the Select arrives to find
every value already legal.

The canonical spellings come from the live ``Colour`` Item Attribute - the same
master the BOM resolver matches against - so the specification and the item
master cannot drift into two vocabularies.

Idempotent: rows already canonical are skipped, and a second run finds nothing
to do.
"""

import frappe

COLOUR_ATTRIBUTE = "Colour"
CHILD_DOCTYPE = "Colour of Parts"
FIELDNAME = "colour"


def execute():
	canonical = _canonical_colours()
	if not canonical:
		return

	rows = frappe.get_all(CHILD_DOCTYPE, fields=["name", FIELDNAME], limit_page_length=0)
	for row in rows:
		stored = (row.get(FIELDNAME) or "").strip()
		if not stored:
			continue
		target = canonical.get(stored.lower())
		if target and target != row.get(FIELDNAME):
			frappe.db.set_value(
				CHILD_DOCTYPE, row["name"], FIELDNAME, target, update_modified=False
			)


def _canonical_colours():
	"""Lowercased stored colour -> the Item Attribute's own spelling.

	Read from the master rather than hardcoded so the specification and the item
	master cannot drift apart. An empty result means the attribute is missing and
	the patch does nothing rather than guessing at spellings.
	"""
	if not frappe.db.exists("Item Attribute", COLOUR_ATTRIBUTE):
		return {}
	attr = frappe.get_doc("Item Attribute", COLOUR_ATTRIBUTE)
	return {
		row.attribute_value.strip().lower(): row.attribute_value
		for row in attr.item_attribute_values
		if row.attribute_value
	}
