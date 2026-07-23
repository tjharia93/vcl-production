"""Record which Job Card Label rows named a Sales Order before order control.

Twenty ``Job Card Label`` rows name a Sales Order and seven name a Sales Order
line. Every one was written by hand, long before specifications were frozen onto
order lines, and not one carries a snapshot — there was nothing to freeze.

From this release those two fields mean something stronger: a card that names an
order is a card that must prove itself against the order's frozen line, field by
field. Applied to the twenty, that rule would demand a snapshot none of them can
have and twenty historical, mostly submitted job cards would stop saving.

The three ways out of that were considered in the discovery report (§5.3) and
two of them are worse than the problem:

* Clearing the links loses the only record of which order a job belonged to.
* Writing a snapshot today records a specification state that was never frozen
  and never true.

So the third is taken: the difference is *recorded*. This patch stamps
``legacy_order_reference`` on exactly the rows that (a) exist now, (b) name an
order or a line, and (c) hold no snapshot. Nothing else about them changes — not
the links, not the quantities, not ``modified``, not the docstatus.

After this runs, "legacy" is a fact in a column rather than an inference from a
shape, and that is the whole point. A card posted tomorrow with a Sales Order
and no snapshot has the same *shape* as these twenty and is refused, because it
has no stamp and cannot earn one: the only new document that may carry the flag
is the amendment of a card that already does, proved against the cancelled row
it amends (``cps_rules.legacy_flag_earned``). Forged and historical stop being
the same document.

Runs **post_model_sync** — the column it writes is declared by the DocType sync
immediately before it.

Idempotent: rows already stamped are not rewritten, and a row that has since
acquired a snapshot is not stamped. A second run reports zero.
"""

import json

import frappe

from production_log.job_card_tracking import cps_rules

DOCTYPE = "Job Card Label"
FLAG = cps_rules.LEGACY_ORDER_REF_FIELD

# Where the stamped set is left for ``verify_label_order_migration``.
CENSUS_KEY = "vcl_label_legacy_stamp_census"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	columns = frappe.db.get_table_columns(DOCTYPE)
	required = {FLAG, "sales_order", "sales_order_item", "spec_snapshot"}
	if not required.issubset(set(columns)):
		# The DocType sync has not landed the order-derived block on this site.
		# Stamping a column that does not exist is not a recoverable error worth
		# throwing over: there is also nothing to stamp, because without those
		# columns no row can have a legacy reference.
		print(
			"stamp_legacy_label_order_references: skipped, {0} is missing {1}.".format(
				DOCTYPE, ", ".join(sorted(required - set(columns)))
			)
		)
		return

	rows = frappe.db.sql(
		"""
		SELECT `name`, `docstatus`, `sales_order`, `sales_order_item`,
		       `spec_snapshot`, `{flag}` AS flag
		FROM `tab{doctype}`
		""".format(flag=FLAG, doctype=DOCTYPE),
		as_dict=True,
	)

	stamped = []
	already = []
	for row in rows:
		qualifies = cps_rules.legacy_order_reference_qualifies(
			row.sales_order, row.sales_order_item, row.spec_snapshot
		)
		if not qualifies:
			continue
		if row.flag:
			already.append(row.name)
			continue
		stamped.append(row.name)

	for name in stamped:
		# update_modified=False: this records a fact about a card nobody edited.
		# Bumping ``modified`` would make twenty historical job cards look
		# touched to anybody reading the audit trail, on the exact release whose
		# purpose is to leave them alone.
		frappe.db.set_value(DOCTYPE, name, FLAG, 1, update_modified=False)

	census = {
		"total": len(rows),
		"stamped": sorted(stamped),
		"already_stamped": sorted(already),
		"with_order": sum(
			1
			for row in rows
			if cps_rules.has_order_reference(row.sales_order, row.sales_order_item)
		),
		"with_snapshot": sum(
			1 for row in rows if cps_rules.has_frozen_snapshot(row.spec_snapshot)
		),
	}
	frappe.db.set_default(CENSUS_KEY, json.dumps(census, default=str))

	if stamped:
		frappe.log_error(
			title="vcl_label_legacy_order_refs",
			message=json.dumps(census, default=str, indent=1),
		)

	print(
		"stamp_legacy_label_order_references: {0} row(s) read, {1} name an order, "
		"{2} carry a snapshot, {3} stamped legacy ({4} already were).".format(
			census["total"],
			census["with_order"],
			census["with_snapshot"],
			len(stamped),
			len(already),
		)
	)
