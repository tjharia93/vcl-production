"""Hand the Label order-reference fields from Custom Field metadata to the app.

``Job Card Label`` carries two Custom Fields on the live site that this release
declares as DocFields in ``job_card_label.json``:

* ``Job Card Label-sales_order`` — Link, Sales Order, 20 rows populated
* ``Job Card Label-sales_order_item`` — Link, Sales Order Item, 7 rows populated

Somebody created them by hand to record which order a job belonged to. Nothing
in this app has ever written them, no patch creates them, and no fixture file
exists to reinstate them (``hooks.fixtures`` names the DocType but the repo
holds no ``custom_field.json``), so retiring them here is final.

They cannot simply be left in place. A DocField and a Custom Field sharing a
fieldname is a duplicate in the assembled meta, and ``bench migrate`` refuses
the DocType sync outright — which is why this runs **pre_model_sync**, in the
last moment before the DocType is rewritten.

**The values are not touched.** Deleting Custom Field metadata does not drop the
column: the row goes from ``tabCustom Field`` and ``tabJob Card Label`` keeps
both columns and every value in them. Immediately afterwards the model sync
declares the same two columns from the DocType JSON — ``sales_order`` as a Link
of the same width, ``sales_order_item`` as ``Data``, which is the same
``varchar(140)`` — and the historical links come back attached to fields the app
now owns. ``verify_label_order_migration`` proves that afterwards rather than
asserting it here.

The delete is written as ``frappe.db.delete`` rather than ``frappe.delete_doc``
deliberately. ``CustomField.on_trash`` differs between Frappe versions and this
patch must be exactly one thing — remove a metadata row — on every one of them.
The Property Setters that belong to those fields are removed explicitly for the
same reason: left behind they are orphans pointing at a field that is no longer
custom, and Frappe would apply them to the new DocField.

Idempotent: a second run finds no matching Custom Field and writes nothing.
"""

import json

import frappe

DOCTYPE = "Job Card Label"

# Every fieldname ``job_card_label.json`` declares in this release that could
# plausibly already exist as a Custom Field. Broader than the two that actually
# do, on purpose: a site that has been hand-patched differently from the audited
# one must migrate rather than fail, and a fieldname that turns out not to
# collide costs one indexed lookup.
MIGRATING_FIELDNAMES = (
	"section_sales_order",
	"sales_order",
	"sales_order_item",
	"item_code",
	"legacy_order_reference",
	"column_break_sales_order",
	"rate",
	"price_source",
	"so_qty",
	"section_spec_snapshot",
	"spec_snapshot_at",
	"spec_snapshot",
)

# Where the pre-migration census is left for ``verify_label_order_migration``.
CENSUS_KEY = "vcl_label_order_ref_census"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	census = {"retired": {}, "populated": {}}
	retired = []

	for fieldname in MIGRATING_FIELDNAMES:
		# Count before deleting anything, so the census describes the site as it
		# was found even if this patch is interrupted halfway through.
		if _column_exists(fieldname):
			census["populated"][fieldname] = _populated_rows(fieldname)

		custom_field = frappe.db.get_value(
			"Custom Field",
			{"dt": DOCTYPE, "fieldname": fieldname},
			["name", "fieldtype", "options"],
			as_dict=True,
		)
		if not custom_field:
			continue

		census["retired"][fieldname] = {
			"custom_field": custom_field.name,
			"fieldtype": custom_field.fieldtype,
			"options": custom_field.options,
		}

		frappe.db.delete("Property Setter", {"doc_type": DOCTYPE, "field_name": fieldname})
		frappe.db.delete("Custom Field", {"name": custom_field.name})
		retired.append(fieldname)

	# Recorded even when nothing was retired: "this site had no Custom Fields to
	# migrate" is a finding, and the verification step needs the row counts
	# either way.
	frappe.db.set_default(CENSUS_KEY, json.dumps(census, default=str))

	if retired:
		# Greppable independently of the migrate log, because this is the one
		# step in the release that deletes metadata over live data.
		frappe.log_error(
			title="vcl_label_order_cf_retire",
			message=json.dumps(census, default=str, indent=1),
		)
		frappe.clear_cache(doctype=DOCTYPE)

	print(
		"retire_label_order_custom_fields: {0} Custom Field(s) retired ({1}); "
		"row counts recorded for {2} column(s). No column dropped.".format(
			len(retired),
			", ".join(retired) or "none",
			len(census["populated"]),
		)
	)


def _column_exists(fieldname):
	return fieldname in frappe.db.get_table_columns(DOCTYPE)


def _populated_rows(fieldname):
	"""Rows holding a non-blank value in ``fieldname``.

	The number ``verify_label_order_migration`` compares against afterwards. It
	is the only assertion that matters here: the point of the whole exercise is
	that not one historical link is lost on the way past the model sync.
	"""
	return frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tab{doctype}`
		WHERE `{fieldname}` IS NOT NULL AND TRIM(`{fieldname}`) != ''
		""".format(doctype=DOCTYPE, fieldname=fieldname)
	)[0][0]
