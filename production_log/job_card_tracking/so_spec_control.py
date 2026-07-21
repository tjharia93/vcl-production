"""CPS control over Sales Order lines, enforced for every write path.

These handlers are wired as ``doc_events`` rather than into the Compass API
because Compass is only one of four write paths — Desk, REST and Data Import
must hit the same rules (design D8, §7). ``ignore_permissions=True`` bypasses
the permission check only, not ``doc_events``, so an API caller cannot opt out.

Everything here is inert until ``Selling Settings.custom_cps_control_enabled``
is ticked (design §15 step 10). The flag ships off: every schema change is
additive and changes no existing behaviour until that single checkbox flips.
"""

import json

import frappe
from frappe import _

from production_log.job_card_tracking import cps_pricing, cps_rules

OVERRIDE_ROLE = "Sales Master Manager"
CONTROL_FLAG = "custom_cps_control_enabled"
TOLERANCE_FIELD = "custom_cps_price_tolerance_pct"
FLOOR_FIELD = "custom_cps_price_floor_pct"

# Read-only explanation of why Item.custom_requires_cps holds the value it does.
# Written alongside the flag, because a derived read-only Check with no stated
# reason is a value the user can neither change nor understand.
CONTROL_SOURCE_FIELD = "custom_cps_control_source"

# Job Card DocTypes that consume a Sales Order line, by CPS product type.
# Phase 2 is Computer Paper only (DN-7); Label, Carton, Exercise Books and ETR
# are one registry entry each in Phase 3.
JOB_CARD_DOCTYPES = {"Computer Paper": "Job Card Computer Paper"}

SNAPSHOT_FIELDS = (
	"custom_cps_rate",
	"custom_cps_uom",
	"custom_cps_valid_from",
	"custom_cps_price_row",
	"custom_price_source",
	"custom_price_variance_pct",
	"custom_price_approved_by",
	"custom_spec_name",
	"custom_job_size",
	"custom_number_of_parts",
	"custom_number_of_colours",
	"custom_spec_snapshot_at",
	"custom_spec_snapshot",
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def control_enabled():
	"""Whether CPS control is live. Ships off (design §15 step 10)."""
	return bool(frappe.db.get_single_value("Selling Settings", CONTROL_FLAG))


def _threshold(fieldname):
	"""Read a pricing threshold, treating unset as genuinely unset.

	Both ``tolerance_pct`` and ``floor_pct`` ship with no default (DN-5):
	matching is exact-match-only and the floor is disabled until management
	supplies real values. ``None`` means "no threshold", which is different
	from zero.
	"""
	value = frappe.db.get_single_value("Selling Settings", fieldname)
	if value in (None, ""):
		return None
	return float(value)


# ---------------------------------------------------------------------------
# Controlled-item derivation (design §4.2)
# ---------------------------------------------------------------------------


def item_group_requires_cps(item_group):
	"""Nearest ancestor Item Group that turns CPS control on, or None.

	Walks the nested set upward so a controlled parent group covers everything
	beneath it without per-group configuration.
	"""
	if not item_group:
		return None

	bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return None

	ancestors = frappe.get_all(
		"Item Group",
		filters={"lft": ["<=", bounds.lft], "rgt": [">=", bounds.rgt]},
		fields=["name", "lft", "custom_requires_cps", "custom_cps_product_type"],
		order_by="lft desc",
	)
	for group in ancestors:
		if group.get("custom_requires_cps"):
			return group
	return None


def derive_item_control_flag(doc, method=None):
	"""Denormalise controlled-ness onto the Item (``Item.validate``).

	Sales Order validation runs on every line of every order; a single indexed
	Check read beats a nested-set walk per line, and it makes "which items are
	controlled" a filterable list view.

	The Item's own control mode wins over the Item Group tree in both directions
	(design §4.2, iteration 2), so a single Item can be piloted without turning
	control on for the 46 Items in its group — and one sample Item inside a
	controlled group can be released without turning the group off. The mode is
	the input; ``custom_requires_cps`` remains read-only and derived.
	"""
	if not _has_field("Item", "custom_requires_cps"):
		return

	controlling_group = item_group_requires_cps(doc.get("item_group"))
	mode = doc.get(cps_rules.CONTROL_MODE_FIELD) if _has_control_mode() else None

	doc.custom_requires_cps = 1 if cps_rules.item_requires_cps(mode, controlling_group) else 0

	if _has_field("Item", CONTROL_SOURCE_FIELD):
		source = cps_rules.item_control_source(mode, controlling_group)
		doc.set(CONTROL_SOURCE_FIELD, _(source.template).format(*source.args))


def validate_item_config(doc, method=None):
	"""An Item that requires a specification must say which kind (``Item.validate``).

	The Item Group half of this has been enforced since iteration one; without
	the Item half, ``Require CPS`` on an Item outside any controlled group left
	the expected product type unresolved, and a Label specification would pass on
	a Computer Paper Item.

	Enforced server-side rather than left to ``mandatory_depends_on``, which is
	an assist on the Desk form and nothing at all to REST, Data Import or the
	Compass API.
	"""
	if not _has_control_mode():
		return

	error = cps_rules.item_config_error(
		doc.get(cps_rules.CONTROL_MODE_FIELD),
		doc.get(cps_rules.PRODUCT_TYPE_FIELD) if _has_item_product_type() else None,
	)
	if error:
		frappe.throw(
			_(error.template).format(*error.args), title=_("CPS Product Type Required")
		)


def expected_product_type_for_item(item_code):
	"""Which kind of specification this Item's order lines need, or None.

	The single resolver behind both the Desk preview and submit validation, so
	V4 cannot be previewed as clean and then thrown on — or, worse, previewed and
	enforced against two different expected types.

	Item override first, controlling Item Group second (design §4.2, iteration
	two). Reads only the fields that have actually landed on this site, so it
	degrades to the pure Item Group answer before the iteration-two patch runs.
	"""
	if not item_code:
		return None

	fields = ["item_group"]
	if _has_control_mode():
		fields.append(cps_rules.CONTROL_MODE_FIELD)
	if _has_item_product_type():
		fields.append(cps_rules.PRODUCT_TYPE_FIELD)

	item = frappe.db.get_value("Item", item_code, fields, as_dict=True)
	if not item:
		return None

	return cps_rules.expected_product_type(
		item.get(cps_rules.CONTROL_MODE_FIELD),
		item.get(cps_rules.PRODUCT_TYPE_FIELD),
		item_group_requires_cps(item.get("item_group")),
	)


def validate_item_group_config(doc, method=None):
	"""A controlled Item Group must say which product type it controls.

	``mandatory_depends_on`` is unreliable for a Check-driven Select, so this is
	enforced server-side (design §4.2).
	"""
	if not _has_field("Item Group", "custom_requires_cps"):
		return

	if doc.get("custom_requires_cps") and not doc.get("custom_cps_product_type"):
		frappe.throw(
			_("Select a CPS Product Type - an Item Group cannot require a specification without naming which kind."),
			title=_("CPS Product Type Required"),
		)


def enqueue_group_rederive(doc, method=None):
	"""Re-derive the Item flag across a group's subtree after a config change."""
	if not _has_field("Item", "custom_requires_cps"):
		return

	frappe.enqueue(
		"production_log.job_card_tracking.so_spec_control.rederive_items_for_group",
		queue="long",
		item_group=doc.name,
	)


def rederive_items_for_group(item_group):
	"""Background re-derivation of ``Item.custom_requires_cps`` for a subtree.

	Each Item's own control mode is re-applied here, not just the group's answer.
	Without that, ticking a parent group would quietly overwrite every explicit
	exemption beneath it — and an exemption that a routine group edit revokes is
	not an exemption.
	"""
	bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return

	descendants = frappe.get_all(
		"Item Group",
		filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
		pluck="name",
	)
	if not descendants:
		return

	has_mode = _has_control_mode()
	has_source = _has_field("Item", CONTROL_SOURCE_FIELD)

	fields = ["name", "item_group"]
	if has_mode:
		fields.append(cps_rules.CONTROL_MODE_FIELD)

	# One nested-set walk per distinct group rather than per Item: a controlled
	# group can hold thousands of Items and the answer is identical for all of
	# them.
	controlling_by_group = {}

	for item in frappe.get_all(
		"Item", filters={"item_group": ["in", descendants]}, fields=fields
	):
		group = item.get("item_group")
		if group not in controlling_by_group:
			controlling_by_group[group] = item_group_requires_cps(group)
		controlling = controlling_by_group[group]

		mode = item.get(cps_rules.CONTROL_MODE_FIELD) if has_mode else None
		values = {"custom_requires_cps": 1 if cps_rules.item_requires_cps(mode, controlling) else 0}
		if has_source:
			values[CONTROL_SOURCE_FIELD] = cps_rules.item_control_source_text(mode, controlling)

		frappe.db.set_value("Item", item.name, values, update_modified=False)

	frappe.db.commit()


# ---------------------------------------------------------------------------
# Sales Order validation (design §7)
# ---------------------------------------------------------------------------


def validate(doc, method=None):
	"""Enforce V1-V13 on every Sales Order line.

	Draft-permissive, submit-strict: V1 and V7 warn while the order is a draft
	so a rep can capture an order for a product whose price is still being
	approved. The gate is submit, which is when ``docstatus`` is already 1.
	"""
	if not control_enabled():
		return

	if not (
		_has_field("Item", "custom_requires_cps")
		and _has_field("Sales Order Item", "custom_cps")
	):
		# The flag was ticked on a site where the fields have not landed yet.
		# Stay inert rather than throwing on every order.
		return

	submitting = doc.docstatus == 1
	tolerance_pct = _threshold(TOLERANCE_FIELD)
	floor_pct = _threshold(FLOOR_FIELD)

	for line in doc.get("items") or []:
		_validate_line(doc, line, submitting, tolerance_pct, floor_pct)

	if submitting:
		_validate_qty_against_job_cards(doc)


def _validate_line(doc, line, submitting, tolerance_pct, floor_pct):
	controlled = bool(frappe.db.get_value("Item", line.item_code, "custom_requires_cps"))

	if not controlled:
		# V6 - a specification on an uncontrolled line is a mistake, not a note.
		if line.get("custom_cps"):
			_throw(
				line,
				_("{0} is not a specification-controlled item, so it must not carry a Customer Product Specification.").format(
					line.item_code
				),
			)
		return

	if not line.get("custom_cps"):
		# V1 - warn on save, throw on submit.
		message = _("{0} requires a Customer Product Specification.").format(line.item_code)
		if submitting:
			_throw(line, message)
		_warn(line, message)
		_clear_snapshot(line)
		return

	spec = _load_and_validate_spec(doc, line)
	price = cps_pricing.get_eligible_price(spec.name, doc.transaction_date)

	if not price:
		# V7 - warn on save, throw on submit.
		message = _("No approved price for {0} effective {1}. Add a CPS Price row and have it approved.").format(
			spec.name, frappe.utils.formatdate(doc.transaction_date)
		)
		if submitting:
			_throw(line, message)
		_warn(line, message)
		_clear_snapshot(line)
		return

	if submitting:
		_validate_price(doc, line, spec, price, tolerance_pct, floor_pct)
		_stamp_snapshot(doc, line, spec, price, tolerance_pct, floor_pct)
	else:
		_clear_snapshot(line)


def _load_and_validate_spec(doc, line):
	"""V2-V5: the specification must belong here and be orderable."""
	spec = frappe.get_doc("Customer Product Specification", line.custom_cps)

	if spec.customer != doc.customer:
		_throw(
			line,
			_("Specification {0} belongs to {1}, not to {2}.").format(
				spec.name, spec.customer, doc.customer
			),
		)

	if not cps_rules.spec_serves_item(spec, line.item_code):
		_throw(
			line,
			_("Specification {0} is linked to Item {1}, not to {2}.").format(
				spec.name, spec.get("linked_item") or _("no Item"), line.item_code
			),
		)

	expected_type = expected_product_type_for_item(line.item_code)
	if expected_type and spec.product_type != expected_type:
		_throw(
			line,
			_("Specification {0} is a {1} specification, but {2} needs a {3} specification.").format(
				spec.name, spec.product_type, line.item_code, expected_type
			),
		)

	if spec.docstatus != 1:
		state = _("still a draft") if spec.docstatus == 0 else _("cancelled")
		_throw(
			line,
			_("Specification {0} is {1} and cannot be ordered against. Submit it, or select its amendment.").format(
				spec.name, state
			),
		)

	if spec.status != "Active":
		_throw(
			line,
			_("Specification {0} is {1}, not Active, and cannot be ordered against.").format(
				spec.name, spec.status
			),
		)

	return spec


def _validate_price(doc, line, spec, price, tolerance_pct, floor_pct):
	"""V8-V11: rate matches exactly, or is an authorised override."""
	if price.get("uom") and line.uom and price["uom"] != line.uom:
		_throw(
			line,
			_("Line is priced per {0} but the approved price for {1} is per {2}.").format(
				line.uom, spec.name, price["uom"]
			),
		)

	decision = cps_rules.evaluate_price(line.rate, price.get("rate"), tolerance_pct, floor_pct)
	if not decision.requires_override:
		return

	if decision.below_floor:
		# V10 - a floor with an escape hatch is not a floor. No role clears it.
		_throw(
			line,
			_("Rate {0} is below the configured floor of {1}% of the specification rate {2}. This cannot be overridden.").format(
				line.rate, floor_pct, price.get("rate")
			),
		)

	if not (line.get("custom_price_override_reason") or "").strip():
		_throw(
			line,
			_("Rate {0} does not match the approved rate {1} for {2}. Enter an Override Reason, or use the approved rate.").format(
				line.rate, price.get("rate"), spec.name
			),
		)

	if OVERRIDE_ROLE not in frappe.get_roles():
		_throw(
			line,
			_("Rate {0} deviates from the approved rate {1} for {2}. Only a {3} can submit an overridden price.").format(
				line.rate, price.get("rate"), spec.name, OVERRIDE_ROLE
			),
		)

	_log_override(doc, line, spec, price, decision)


def _stamp_snapshot(doc, line, spec, price, tolerance_pct, floor_pct):
	"""Freeze the commercial and technical snapshots onto the line (design §8).

	Written during the submit pass rather than in ``on_submit`` so the snapshot
	lands in the same write as the submit itself. The snapshot fields are
	``read_only`` and carry no ``allow_on_submit``, so nothing can edit them
	afterwards - including Data Import in update-existing mode.

	Every value is taken server-side from the specification and the approved
	price. Whatever the caller supplied in these fields is discarded (V12).
	"""
	decision = cps_rules.evaluate_price(line.rate, price.get("rate"), tolerance_pct, floor_pct)
	taken_at = frappe.utils.now()

	line.custom_cps_rate = cps_rules.round_rate(price.get("rate"))
	line.custom_cps_uom = price.get("uom")
	line.custom_cps_valid_from = price.get("valid_from")
	line.custom_cps_price_row = price.get("name")
	line.custom_price_source = decision.source
	line.custom_price_variance_pct = decision.variance_pct
	line.custom_price_approved_by = (
		frappe.session.user if decision.source == cps_rules.SOURCE_MANUAL_OVERRIDE else None
	)

	line.custom_spec_name = spec.specification_name
	line.custom_job_size = spec.get("job_size")
	line.custom_number_of_parts = spec.get("number_of_parts")
	line.custom_number_of_colours = spec.get("number_of_colours")
	line.custom_spec_snapshot_at = taken_at
	line.custom_spec_snapshot = json.dumps(
		cps_rules.build_spec_snapshot(
			spec, spec.get("colour_of_parts"), spec.get("spot_colours"), taken_at
		),
		default=str,
		indent=1,
	)


def _clear_snapshot(line):
	"""Discard any snapshot value supplied from input on an unsubmitted line.

	Snapshots are outputs of validation, never inputs to it (V12). The one
	exception is ``custom_price_override_reason``, which is a genuine input.
	"""
	for fieldname in SNAPSHOT_FIELDS:
		line.set(fieldname, None)


def _validate_qty_against_job_cards(doc):
	"""An amendment may not cut a line below what is already on Job Cards."""
	for line in doc.get("items") or []:
		carded = float(line.get("custom_jc_qty") or 0)
		if carded and float(line.qty or 0) < carded:
			_throw(
				line,
				_("Cannot reduce quantity to {0} - {1} is already on Job Cards.").format(
					line.qty, carded
				),
			)


def on_submit(doc, method=None):
	"""Reserved for post-submit side effects.

	Snapshots are stamped during the submit validation pass (see
	``_stamp_snapshot``) so they are written atomically with the submit, rather
	than as a second ``db_set`` update afterwards.
	"""
	return


def on_cancel(doc, method=None):
	"""V14: an order with live Job Cards cannot be cancelled out from under them."""
	if not control_enabled():
		return

	blocking = []
	for doctype in JOB_CARD_DOCTYPES.values():
		if not frappe.db.exists("DocType", doctype):
			continue
		blocking += frappe.get_all(
			doctype,
			filters={"sales_order": doc.name, "docstatus": 1},
			pluck="name",
		)

	if blocking:
		frappe.throw(
			_("Cancel the Job Cards first: {0}.").format(", ".join(blocking)),
			title=_("Job Cards Still Open"),
		)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_field(doctype, fieldname):
	"""Whether a Custom Field has landed yet.

	Schema and behaviour deploy in separate steps (design §15), so the hooks
	must be inert on a site where the fields do not exist.
	"""
	return bool(frappe.get_meta(doctype).get_field(fieldname))


def _has_control_mode():
	"""Whether the Item-level control override has landed on this site.

	The iteration-two patch may not have run yet, and an Item with no mode field
	behaves exactly as it did before: pure Item Group inheritance.
	"""
	return _has_field("Item", cps_rules.CONTROL_MODE_FIELD)


def _has_item_product_type():
	"""Whether the Item-level expected product type has landed on this site."""
	return _has_field("Item", cps_rules.PRODUCT_TYPE_FIELD)


def _throw(line, message):
	frappe.throw(_("Line {0}: {1}").format(line.idx, message), title=_("Specification Control"))


def _warn(line, message):
	frappe.msgprint(
		_("Line {0}: {1}").format(line.idx, message),
		title=_("Specification Control"),
		indicator="orange",
	)


def _log_override(doc, line, spec, price, decision):
	"""Audit an authorised price override (design §9.3).

	The same facts land on the immutable snapshot; this makes them greppable
	independently of the order.
	"""
	frappe.log_error(
		title="vcl_price_override",
		message=json.dumps(
			{
				"sales_order": doc.name,
				"line": line.idx,
				"item_code": line.item_code,
				"cps": spec.name,
				"cps_rate": price.get("rate"),
				"line_rate": line.rate,
				"variance_pct": decision.variance_pct,
				"reason": line.get("custom_price_override_reason"),
				"user": frappe.session.user,
			},
			default=str,
			indent=1,
		),
	)
