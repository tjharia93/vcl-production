"""Prove the Label order-reference migration did not lose anything.

The two pre-model-sync patches in this release both touch live data at the one
moment it is least observable — the last write before ``bench migrate`` rewrites
the table. ``retire_label_order_custom_fields`` deletes the metadata that owns
two populated columns; ``audit_label_quantity_ordered`` watches an ``Int``
column become a ``Float``. Each recorded a census of what it found. This is the
half that reads those censuses back and refuses to let the migrate finish quietly
if a figure moved.

What is asserted:

1. **No historical link was lost.** Every column the retirement patch counted
   still holds at least as many non-blank values as it did. "At least" and not
   "exactly", because the stamping patch and ordinary traffic may add rows
   between the two halves of a migrate; a link *disappearing* is the failure
   mode, and it is caught exactly.
2. **No quantity changed.** The row count, the sum and the range across
   ``quantity_ordered`` are identical to three decimal places.
3. **No duplicate metadata came back.** No Custom Field on ``Job Card Label``
   shares a fieldname with a DocField — the condition that made the retirement
   necessary must not exist on the far side of it.
4. **Every legacy reference is stamped.** No row names an order, holds no
   snapshot, and lacks the flag; a row in that state would be refused on its
   next save, which is precisely what this release exists to prevent.

Failing here stops the migrate with the figures side by side. That is the right
outcome: a half-migrated Label card table is not something to discover from a
user's failed save three days later.

The censuses are cleared once they have been checked, so a later migrate on the
same site does not re-check numbers from a bench that has moved on. That also
makes this idempotent — a second run finds nothing recorded and reports that it
verified what it could from the live table alone.
"""

import json

import frappe

from production_log.job_card_tracking import cps_rules
from production_log.patches.v8_2 import (
	audit_label_quantity_ordered,
	retire_label_order_custom_fields,
	stamp_legacy_label_order_references,
)

DOCTYPE = "Job Card Label"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	problems = []
	checked = []

	problems += _verify_columns_survived(checked)
	problems += _verify_quantities_unchanged(checked)
	problems += _verify_no_duplicate_metadata(checked)
	problems += _verify_legacy_rows_stamped(checked)

	if problems:
		frappe.throw(
			"The Job Card Label order-reference migration did not complete "
			"cleanly:\n\n{0}\n\nThe migrate has been stopped. Nothing in this "
			"release has dropped a column, so the data is still present - "
			"investigate before re-running.".format("\n".join("  - " + p for p in problems)),
			title="Label Order Migration Verification Failed",
		)

	_clear_censuses()

	print(
		"verify_label_order_migration: {0} check(s) passed - {1}.".format(
			len(checked), "; ".join(checked)
		)
	)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _verify_columns_survived(checked):
	census = _read_census(retire_label_order_custom_fields.CENSUS_KEY)
	if census is None:
		return []

	columns = set(frappe.db.get_table_columns(DOCTYPE))
	problems = []

	for fieldname, before in (census.get("populated") or {}).items():
		if fieldname not in columns:
			problems.append(
				"column `{0}` held {1} value(s) before the sync and no longer exists".format(
					fieldname, before
				)
			)
			continue

		after = _populated_rows(fieldname)
		if after < int(before):
			problems.append(
				"column `{0}` held {1} value(s) before the sync and holds {2} now".format(
					fieldname, before, after
				)
			)

	if not problems:
		checked.append(
			"{0} retired column(s) kept every value".format(len(census.get("populated") or {}))
		)
	return problems


def _verify_quantities_unchanged(checked):
	census = _read_census(audit_label_quantity_ordered.CENSUS_KEY)
	if census is None:
		return []

	field = audit_label_quantity_ordered.FIELD
	if field not in frappe.db.get_table_columns(DOCTYPE):
		return ["column `{0}` no longer exists".format(field)]

	values = [
		float(value)
		for (value,) in frappe.db.sql(
			"SELECT `{0}` FROM `tab{1}` WHERE `{0}` IS NOT NULL".format(field, DOCTYPE)
		)
	]
	after = {
		"populated": len(values),
		"sum": round(sum(values), 3),
		"min": round(min(values), 3) if values else None,
		"max": round(max(values), 3) if values else None,
	}

	problems = []
	for key in ("populated", "sum", "min", "max"):
		before = census.get(key)
		if before is None and after[key] is None:
			continue
		if before is None or after[key] is None or round(float(before), 3) != after[key]:
			problems.append(
				"`{0}` {1} was {2} before the sync and is {3} now".format(
					field, key, before, after[key]
				)
			)

	if not problems:
		checked.append(
			"{0} quantity value(s) converted exactly (sum {1})".format(
				after["populated"], after["sum"]
			)
		)
	return problems


def _verify_no_duplicate_metadata(checked):
	"""No Custom Field may share a fieldname with a DocField on this DocType.

	Checked over the whole DocType rather than only the fields this release
	migrated. The failure this guards against — an assembled meta carrying two
	entries for one column — is not specific to the two fields that caused it,
	and finding a third one now is far cheaper than finding it during the next
	release's model sync.
	"""
	docfields = set(
		frappe.get_all("DocField", filters={"parent": DOCTYPE}, pluck="fieldname")
	)
	custom = set(
		frappe.get_all("Custom Field", filters={"dt": DOCTYPE}, pluck="fieldname")
	)
	clashes = sorted(f for f in docfields & custom if f)

	if clashes:
		return [
			"Custom Field(s) still shadow a DocField on {0}: {1}".format(
				DOCTYPE, ", ".join(clashes)
			)
		]

	checked.append("no Custom Field shadows a DocField")
	return []


def _verify_legacy_rows_stamped(checked):
	columns = set(frappe.db.get_table_columns(DOCTYPE))
	required = {cps_rules.LEGACY_ORDER_REF_FIELD, "sales_order", "sales_order_item", "spec_snapshot"}
	if not required.issubset(columns):
		return [
			"{0} is missing {1} after the sync".format(
				DOCTYPE, ", ".join(sorted(required - columns))
			)
		]

	rows = frappe.db.sql(
		"""
		SELECT `name`, `sales_order`, `sales_order_item`, `spec_snapshot`, `{flag}` AS flag
		FROM `tab{doctype}`
		""".format(flag=cps_rules.LEGACY_ORDER_REF_FIELD, doctype=DOCTYPE),
		as_dict=True,
	)

	unstamped = [
		row.name
		for row in rows
		if cps_rules.legacy_order_reference_qualifies(
			row.sales_order, row.sales_order_item, row.spec_snapshot
		)
		and not row.flag
	]
	if unstamped:
		return [
			"{0} row(s) name an order, hold no snapshot and are not stamped legacy: {1}".format(
				len(unstamped), ", ".join(unstamped[:20])
			)
		]

	stamped = sum(1 for row in rows if row.flag)
	checked.append("{0} legacy order reference(s) stamped".format(stamped))
	return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _populated_rows(fieldname):
	return frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tab{doctype}`
		WHERE `{fieldname}` IS NOT NULL AND TRIM(`{fieldname}`) != ''
		""".format(doctype=DOCTYPE, fieldname=fieldname)
	)[0][0]


def _read_census(key):
	"""A census left by a pre-model-sync patch, or None if there is none.

	None is not a failure. It means this patch is being re-run on a site whose
	migration already completed, and the live-table checks below still apply.
	"""
	raw = frappe.db.get_default(key)
	if not raw:
		return None
	try:
		return json.loads(raw)
	except (TypeError, ValueError):
		return None


def _clear_censuses():
	for key in (
		retire_label_order_custom_fields.CENSUS_KEY,
		audit_label_quantity_ordered.CENSUS_KEY,
		stamp_legacy_label_order_references.CENSUS_KEY,
	):
		frappe.db.set_default(key, "")
