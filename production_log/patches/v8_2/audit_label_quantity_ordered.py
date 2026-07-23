"""Audit ``Job Card Label.quantity_ordered`` before it is retyped as a Float.

The field shipped as ``Int``. Every quantity rule the order-derived path needs —
remaining, carded, the Sales Order rollup — is stated to three decimal places
because that is what a Sales Order line carries, and an ``Int`` cannot express
a comparison it is asked to take part in.

``Int`` to ``Float`` is a widening conversion and MariaDB performs it exactly:
``int(11)`` to ``decimal(21,9)`` cannot lose a value that fits, and every value
in an ``Int`` column fits. That is a claim, though, and this release makes a
point of not shipping claims about live data — so the claim is *measured*. This
patch runs **pre_model_sync**, which is the only moment the old column still
exists, and records the census the post-sync half compares against:

* how many rows hold a value,
* their exact sum,
* and the smallest and largest of them.

If a single row changed across the ``ALTER``, ``verify_label_order_migration``
stops the migrate and says which figure moved.

Nothing is rewritten. Unlike the Carton patch this one has no text to canonicalise
— the column is already numeric, which is exactly why it is an audit and not a
normalisation. Any value that is somehow not a number is reported and the
migrate is refused rather than rounded into one.

Idempotent: it reads and records, and writes nothing to the job cards at all.
"""

import json

import frappe

DOCTYPE = "Job Card Label"
FIELD = "quantity_ordered"

# Where the pre-migration census is left for ``verify_label_order_migration``.
CENSUS_KEY = "vcl_label_quantity_census"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return
	if FIELD not in frappe.db.get_table_columns(DOCTYPE):
		return

	rows = frappe.db.sql(
		"""
		SELECT `name`, `{field}` AS value
		FROM `tab{doctype}`
		""".format(field=FIELD, doctype=DOCTYPE),
		as_dict=True,
	)

	unreadable = [row for row in rows if not _is_number(row.value)]
	if unreadable:
		frappe.throw(
			"Job Card Label.{field} cannot be audited because {count} row(s) hold "
			"a value that is not a number:\n\n{rows}\n\n"
			"Correct each one on the Desk (or with a Data Import) and run the "
			"migrate again. Nothing has been changed.".format(
				field=FIELD,
				count=len(unreadable),
				rows="\n".join(
					"  {0}: {1!r}".format(row.name, row.value) for row in unreadable[:50]
				),
			),
			title="Label Quantity Cannot Be Audited",
		)

	values = [float(row.value) for row in rows if row.value not in (None, "")]
	census = {
		"rows": len(rows),
		"populated": len(values),
		# Rounded to the precision the new column carries, so the comparison is
		# stated in the same terms the column will answer in.
		"sum": round(sum(values), 3),
		"min": round(min(values), 3) if values else None,
		"max": round(max(values), 3) if values else None,
	}

	frappe.db.set_default(CENSUS_KEY, json.dumps(census, default=str))

	print(
		"audit_label_quantity_ordered: {rows} row(s) read, {populated} populated, "
		"sum {sum}, range {min}..{max}. Nothing rewritten.".format(**census)
	)


def _is_number(value):
	"""Whether a stored quantity survives the conversion as a number.

	Deliberately narrow. An ``Int`` column can only hold integers and NULL, so
	anything else means the column is not the column this patch was written
	against, and guessing at it is how a commitment to a customer turns into a
	different commitment.
	"""
	if value is None:
		return True
	if isinstance(value, bool):
		return False
	if isinstance(value, (int, float)):
		return True
	try:
		float(str(value).strip())
	except (TypeError, ValueError):
		return False
	return True
