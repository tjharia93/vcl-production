"""Iteration-two Custom Fields for CPS control (WBS-25, WBS-27).

A *follow-up* patch rather than an edit to ``add_cps_control_custom_fields``:
that one has already run, and Frappe records a patch as executed by name, so
amending it in place would land these fields on no site at all.

Everything here is idempotent by construction and safe to run repeatedly:

* ``create_custom_fields`` inserts a Custom Field that is absent and updates the
  properties of one that is present, so a re-run reconciles rather than
  duplicates. That is also what re-asserts ``read_only`` on
  ``Item.custom_requires_cps`` — the flag is derived, and a site where someone
  has cleared that property by hand needs it put back.
* The backfill writes only where the stored flag actually disagrees with what
  the rules compute, and touches only Items carrying an explicit override. On
  the first run there are none, so it writes nothing.

Schema only. ``Item.custom_cps_control_mode`` and ``Item.custom_cps_product_type``
are read by ``so_spec_control``, and every rule that acts on a Sales Order line
is gated on ``Selling Settings.custom_cps_control_enabled``, which ships off.

The one rule that is *not* gated on that flag is
``so_spec_control.validate_item_config``: an Item that says ``Require CPS``
without naming a product type is refused on save from the moment these fields
land. That is deliberate and cannot bite an existing record — no Item carries an
explicit mode until someone sets one, and the mode ships as Inherit.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_rules, so_spec_control

CONTROL_MODE_OPTIONS = "\n".join(cps_rules.CONTROL_MODES)

# Leading blank so "no answer" is selectable: an Item that inherits its group's
# product type must be able to say nothing at all.
CPS_PRODUCT_TYPE_OPTIONS = "\n".join(("",) + cps_rules.CPS_PRODUCT_TYPES)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	backfill_explicit_overrides()
	frappe.clear_cache()


def get_custom_fields():
	return {
		"Item Group": [
			{
				# Re-asserted, not introduced. Item and Item Group now answer the
				# same question at two altitudes, and ``cps_rules.CPS_PRODUCT_TYPES``
				# is the one definition of the answers — so the group's option list
				# is rewritten from it rather than left as a literal that has to be
				# remembered and edited twice.
				"fieldname": cps_rules.PRODUCT_TYPE_FIELD,
				"label": "CPS Product Type",
				"fieldtype": "Select",
				"options": CPS_PRODUCT_TYPE_OPTIONS,
				"insert_after": "custom_requires_cps",
				"depends_on": "eval:doc.custom_requires_cps",
				"description": "Which kind of specification these items need. Required when the box above is ticked.",
			},
		],
		"Item": [
			{
				"fieldname": cps_rules.CONTROL_MODE_FIELD,
				"label": "CPS Control",
				"fieldtype": "Select",
				"options": CONTROL_MODE_OPTIONS,
				"default": cps_rules.CONTROL_MODE_DEFAULT,
				"insert_after": "item_group",
				"description": (
					"Inherit from Item Group is the default and the safe answer. Require CPS "
					"controls this Item alone, without controlling its group; Exempt from CPS "
					"releases this Item from a group that is controlled. An explicit answer "
					"always wins over the Item Group tree."
				),
			},
			{
				# Which kind of specification an explicitly controlled Item needs.
				# Without it, Require CPS outside a controlled Item Group left no
				# expected product type at all, and a Label specification would
				# pass on a Computer Paper Item.
				#
				# mandatory_depends_on is the form affordance only; the rule is
				# enforced in so_spec_control.validate_item_config, which REST,
				# Data Import and the Compass API cannot step around.
				"fieldname": cps_rules.PRODUCT_TYPE_FIELD,
				"label": "CPS Product Type",
				"fieldtype": "Select",
				"options": CPS_PRODUCT_TYPE_OPTIONS,
				"insert_after": cps_rules.CONTROL_MODE_FIELD,
				"depends_on": "eval:doc.{0}!='{1}'".format(
					cps_rules.CONTROL_MODE_FIELD, cps_rules.CONTROL_MODE_EXEMPT
				),
				"mandatory_depends_on": "eval:doc.{0}=='{1}'".format(
					cps_rules.CONTROL_MODE_FIELD, cps_rules.CONTROL_MODE_REQUIRE
				),
				"description": (
					"Which kind of specification this Item needs. Required when CPS Control "
					"is Require CPS. Leave blank to take the controlling Item Group's answer; "
					"set it to correct that answer for this Item alone."
				),
			},
			{
				# Re-asserted, not introduced. This is the indexed denormalisation
				# Sales Order validation reads per line; it is an output of the
				# control mode and the Item Group tree, never an input, so it must
				# stay read-only however the site has been edited since.
				"fieldname": "custom_requires_cps",
				"label": "Requires CPS",
				"fieldtype": "Check",
				"default": "0",
				"read_only": 1,
				"in_standard_filter": 1,
				"insert_after": cps_rules.PRODUCT_TYPE_FIELD,
				"description": (
					"Derived. Set from CPS Control above when that is Require or Exempt, "
					"otherwise inherited from the Item Group tree. Not editable here."
				),
			},
			{
				"fieldname": so_spec_control.CONTROL_SOURCE_FIELD,
				"label": "CPS Control Source",
				"fieldtype": "Small Text",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "custom_requires_cps",
				"description": (
					"Why the box above holds the value it does. Rewritten every time the Item "
					"is saved and whenever its Item Group's configuration changes."
				),
			},
		],
		"Sales Order Item": [
			{
				# Re-asserted to put the specification in the grid itself. The
				# Customer Product Specification DocType carries
				# show_title_field_in_link, so the column reads as the
				# specification name with the CPT-SPEC id beneath it rather than
				# as an opaque document number (WBS-25).
				"fieldname": "custom_cps",
				"label": "Customer Product Specification",
				"fieldtype": "Link",
				"options": "Customer Product Specification",
				"in_list_view": 1,
				"insert_after": "custom_cps_section",
				"description": (
					"Required for specification-controlled items. Must belong to this customer "
					"and be submitted and Active. The list is filtered to this order's customer "
					"and this line's Item."
				),
			},
		],
	}


def backfill_explicit_overrides():
	"""Reconcile ``custom_requires_cps`` for Items carrying an explicit override.

	Scoped to Items whose control mode is Require or Exempt, because blank and
	Inherit both mean "behave exactly as before" and their stored flag is already
	correct by construction. On the first run that set is empty and this is a
	single indexed read.

	Writes with ``update_modified=False``: this corrects a derived value, and
	bumping ``modified`` on a few thousand Items would make every one of them
	look edited to anyone reading the audit trail.
	"""
	if not _has_field("Item", cps_rules.CONTROL_MODE_FIELD):
		return

	has_source = _has_field("Item", so_spec_control.CONTROL_SOURCE_FIELD)

	overridden = frappe.get_all(
		"Item",
		filters={
			cps_rules.CONTROL_MODE_FIELD: [
				"in",
				[cps_rules.CONTROL_MODE_REQUIRE, cps_rules.CONTROL_MODE_EXEMPT],
			]
		},
		fields=["name", "item_group", "custom_requires_cps", cps_rules.CONTROL_MODE_FIELD],
	)
	if not overridden:
		return

	controlling_by_group = {}
	corrected = 0

	for item in overridden:
		group = item.get("item_group")
		if group not in controlling_by_group:
			controlling_by_group[group] = so_spec_control.item_group_requires_cps(group)
		controlling = controlling_by_group[group]

		mode = item.get(cps_rules.CONTROL_MODE_FIELD)
		expected = 1 if cps_rules.item_requires_cps(mode, controlling) else 0
		source = cps_rules.item_control_source_text(mode, controlling)

		values = {}
		if int(item.get("custom_requires_cps") or 0) != expected:
			values["custom_requires_cps"] = expected
		if has_source:
			values[so_spec_control.CONTROL_SOURCE_FIELD] = source

		if values:
			frappe.db.set_value("Item", item.name, values, update_modified=False)
			corrected += 1

	if corrected:
		print(
			"add_cps_iteration_two_fields: reconciled CPS control on {0} Item(s).".format(
				corrected
			)
		)


def _has_field(doctype, fieldname):
	try:
		return bool(frappe.get_meta(doctype).get_field(fieldname))
	except Exception:
		return False
