"""Make ``Job Card Carton.quantity_ordered`` safe to retype as a number.

The field shipped as ``Data`` and was parsed with ``int()`` at validate time.
Every quantity rule the CPS work needs — remaining, carded, the Sales Order
rollup, three-decimal comparison — is arithmetic, so the column becomes a
``Float`` with precision 3 in this release.

That is a column type change over live rows holding arbitrary text, which the
discovery report ranked as the highest-risk single schema change in the project
(§8.3). This patch is what removes the risk, and it runs **pre_model_sync** —
before the schema is rewritten, which is the only moment at which anything can
still be done about a value that will not convert.

It does two things and no more:

1. **Refuses to migrate** if any stored value is not a number. Nothing is
   guessed, rounded or zeroed. A quantity is a commitment to a customer and
   "10,000 pcs" resolved to 10 by a tolerant parser is worse than a stopped
   deploy — the message names every offending row so the fix is a two-minute
   Desk edit, and the migrate is re-run.
2. **Rewrites the survivors as bare decimal text**, so MariaDB's implicit
   conversion during the ``ALTER`` has nothing to interpret. `` 500 `` with
   whitespace converts fine in practice and this makes it certain.

Idempotent: a second run finds every value already canonical and writes
nothing. On the audited live data — 35 rows, every one numeric — it writes
nothing on the first run either.

Legacy cards are preserved exactly. This patch changes the *representation* of
a quantity, never the quantity.
"""

import frappe

DOCTYPE = "Job Card Carton"
FIELD = "quantity_ordered"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	rows = frappe.db.sql(
		"""
		SELECT `name`, `{field}` AS value
		FROM `tab{doctype}`
		WHERE `{field}` IS NOT NULL AND TRIM(`{field}`) != ''
		""".format(field=FIELD, doctype=DOCTYPE),
		as_dict=True,
	)

	unparseable = []
	rewrites = []

	for row in rows:
		canonical = _canonical_number(row.value)
		if canonical is None:
			unparseable.append(row)
		elif canonical != str(row.value):
			rewrites.append((row.name, canonical))

	if unparseable:
		frappe.throw(
			"Job Card Carton.quantity_ordered cannot be converted to a number "
			"because {0} row(s) hold text that is not a quantity:\n\n{1}\n\n"
			"Correct each one on the Desk (or with a Data Import) and run the "
			"migrate again. Nothing has been changed.".format(
				len(unparseable),
				"\n".join(
					"  {0}: {1!r}".format(row.name, row.value) for row in unparseable[:50]
				),
			),
			title="Carton Quantity Cannot Be Converted",
		)

	for name, canonical in rewrites:
		# update_modified=False: this corrects the representation of a value
		# nobody edited, and bumping `modified` would make every one of these
		# cards look touched to anyone reading the audit trail.
		frappe.db.set_value(DOCTYPE, name, FIELD, canonical, update_modified=False)

	print(
		"normalise_carton_quantity_ordered: {0} row(s) checked, {1} rewritten, "
		"0 unparseable.".format(len(rows), len(rewrites))
	)


def _canonical_number(value):
	"""``value`` as bare decimal text, or None if it is not a number.

	Deliberately narrow. Whitespace and thousands separators are formatting and
	are removed; anything else — a unit, a range, a note — is a value somebody
	has to look at, not a parsing problem to be solved with a regex.
	"""
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return _format(float(value))

	text = str(value).strip().replace(",", "").replace(" ", "")
	if not text:
		return None

	try:
		return _format(float(text))
	except (TypeError, ValueError):
		return None


def _format(number):
	"""Three decimal places, matching the field precision, without exponents."""
	return "{0:.3f}".format(round(number, 3))
