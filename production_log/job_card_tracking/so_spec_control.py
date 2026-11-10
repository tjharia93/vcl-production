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

from production_log.job_card_tracking import cps_first_order_price, cps_price_rules, cps_pricing, cps_rules

CONTROL_FLAG = "custom_cps_control_enabled"

# §4 / checklist D: the SO-submit block (V1/V5/V7...) stays as the belt behind
# the job-card gate, behind an Off / Warn / Enforce switch so it can be removed
# in the deploy that enforces Print. Blank falls back to the original tick.
SO_MODE_FIELD = "custom_cps_so_mode"
QUOTE_MODE_FIELD = "custom_cps_quotation_mode"

# §7 / Codex r5: the job-card gate has its own switch. Off: no holds, no
# evaluation. Observe: evaluate and record, never hold or block print (the two
# weeks' observation mode in §9). Enforce: hold on insert, refuse print.
GATE_MODE_FIELD = "custom_cps_gate_mode"
GATE_OFF = "Off"
GATE_OBSERVE = "Observe"
GATE_ENFORCE = "Enforce"
GATE_MODES = (GATE_OFF, GATE_OBSERVE, GATE_ENFORCE)

# Read-only explanation of why Item.custom_requires_cps holds the value it does.
# Written alongside the flag, because a derived read-only Check with no stated
# reason is a value the user can neither change nor understand.
CONTROL_SOURCE_FIELD = "custom_cps_control_source"

# Job Card DocTypes that consume a Sales Order line, by CPS product type.
# Exercise Books and ETR are one registry entry each when their cards gain the
# order-derived field block.
#
# Registration is what wires ``on_cancel`` below: a Sales Order with a submitted
# card of any registered kind cannot be cancelled out from under it (V14). Label
# is registered here in the same release that gives Job Card Label the
# order-derived fields, because the two are one guarantee — a registry entry for
# a card type with no ``sales_order`` column would filter on nothing, and a card
# type with the column and no registry entry would leave its orders cancellable
# while production was live on them.
JOB_CARD_DOCTYPES = {
	"Computer Paper": "Job Card Computer Paper",
	"Carton": "Job Card Carton",
	"Label": "Job Card Label",
}

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


def so_mode():
	"""Off / Warn / Enforce on submit for Sales Order lines (§4, checklist D).

	Blank (the field has not landed, or nobody chose) falls back to the
	original ``custom_cps_control_enabled`` tick: ticked = Enforce, else Off.
	"""
	if _has_field("Selling Settings", SO_MODE_FIELD):
		value = frappe.db.get_single_value("Selling Settings", SO_MODE_FIELD)
		if (value or "").strip():
			return cps_rules.normalise_quote_mode(value)
	return cps_rules.QUOTE_MODE_ENFORCE if frappe.db.get_single_value("Selling Settings", CONTROL_FLAG) else cps_rules.QUOTE_MODE_OFF


def quotation_mode():
	"""Off / Warn / Enforce on submit for Quotation lines. Ships as Warn."""
	if not _has_field("Selling Settings", QUOTE_MODE_FIELD):
		return cps_rules.QUOTE_MODE_OFF
	return cps_rules.normalise_quote_mode(frappe.db.get_single_value("Selling Settings", QUOTE_MODE_FIELD))


def gate_mode():
	"""Off / Observe / Enforce for the job-card release gate. Ships Off."""
	if not _has_field("Selling Settings", GATE_MODE_FIELD):
		return GATE_OFF
	value = (frappe.db.get_single_value("Selling Settings", GATE_MODE_FIELD) or "").strip()
	return value if value in GATE_MODES else GATE_OFF


def control_enabled():
	"""Whether CPS control on Sales Orders is live at all (Warn or Enforce)."""
	return so_mode() != cps_rules.QUOTE_MODE_OFF


def rounding_allowance_settings():
	"""The two §5 allowance numbers, defaults when the fields have not landed."""
	kes = pct = None
	if _has_field("Selling Settings", cps_price_rules.ALLOWANCE_FIELD):
		kes = frappe.db.get_single_value("Selling Settings", cps_price_rules.ALLOWANCE_FIELD)
	if _has_field("Selling Settings", cps_price_rules.ALLOWANCE_PCT_FIELD):
		pct = frappe.db.get_single_value("Selling Settings", cps_price_rules.ALLOWANCE_PCT_FIELD)
	return (
		cps_price_rules.ALLOWANCE_DEFAULT_KES if kes in (None, "") else float(kes),
		cps_price_rules.ALLOWANCE_DEFAULT_PCT if pct in (None, "") else float(pct),
	)


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

	control = resolve_item_control_for(
		doc.get("item_group"),
		doc.get(cps_rules.CONTROL_MODE_FIELD) if _has_control_mode() else None,
		doc.get(cps_rules.PRODUCT_TYPE_FIELD) if _has_item_product_type() else None,
	)
	doc.custom_requires_cps = 1 if control.controlled else 0

	if _has_field("Item", CONTROL_SOURCE_FIELD):
		doc.set(CONTROL_SOURCE_FIELD, _(control.reason))


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


UNCONTROLLED = cps_rules.ItemControl(False, None, cps_rules.SOURCE_UNCONTROLLED, None, "Item not found.")


def resolve_item_control_for(item_group, control_mode, item_product_type):
	"""The §4 resolver over already-read Item values."""
	return cps_rules.resolve_item_control(
		control_mode, item_product_type, item_group_requires_cps(item_group)
	)


def resolve_item_control(item_code):
	"""THE shared item-control resolver (§4).

	One function behind ``Quotation.validate``, ``Sales Order.validate``,
	``release.evaluate`` and the Desk preview, so a line cannot be previewed as
	clean and then refused on — or, worse, checked against two different
	expected types. Returns a :class:`cps_rules.ItemControl`.

	Item mode wins both ways, then the nearest controlled Item Group, else
	uncontrolled. Reads only the fields that have landed on this site, so it
	degrades to the pure Item Group answer before the Item-level fields exist.
	``Item.custom_requires_cps`` is the indexed cache of ``controlled`` and is
	written only from :func:`derive_item_control_flag`.
	"""
	if not item_code:
		return UNCONTROLLED

	fields = ["item_group"]
	if _has_control_mode():
		fields.append(cps_rules.CONTROL_MODE_FIELD)
	if _has_item_product_type():
		fields.append(cps_rules.PRODUCT_TYPE_FIELD)

	item = frappe.db.get_value("Item", item_code, fields, as_dict=True)
	if not item:
		return UNCONTROLLED

	return resolve_item_control_for(
		item.get("item_group"),
		item.get(cps_rules.CONTROL_MODE_FIELD),
		item.get(cps_rules.PRODUCT_TYPE_FIELD),
	)


def expected_product_type_for_item(item_code):
	"""Which kind of specification this Item's order lines need, or None.

	Kept for existing callers; the answer is :func:`resolve_item_control`'s.
	"""
	return resolve_item_control(item_code).product_type


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
		control = cps_rules.resolve_item_control(mode, None, controlling)
		values = {"custom_requires_cps": 1 if control.controlled else 0}
		if has_source:
			values[CONTROL_SOURCE_FIELD] = control.reason

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
	mode = so_mode()
	if mode == cps_rules.QUOTE_MODE_OFF:
		return

	if not (
		_has_field("Item", "custom_requires_cps")
		and _has_field("Sales Order Item", "custom_cps")
	):
		# The flag was ticked on a site where the fields have not landed yet.
		# Stay inert rather than throwing on every order.
		return

	submitting = doc.docstatus == 1
	allowance = rounding_allowance_settings()

	# Warn mode: every refusal below becomes a message. The flag is read by
	# ``_throw`` so the line checks stay written once.
	frappe.flags.cps_control_warn_only = mode == cps_rules.QUOTE_MODE_WARN
	try:
		locked = None
		if submitting and _has_field("Customer Product Specification", cps_first_order_price.CLAIM_FIELD):
			# The sorted CPS locks serialize the first-use check across orders.
			# Keep them until the normal SO transaction commits/rolls back.
			locked = cps_first_order_price.lock_specs(
				frappe.db, [line.get("custom_cps") for line in doc.get("items") or []]
			)
		for line in doc.get("items") or []:
			_validate_line(doc, line, submitting, allowance, locked)

		if submitting:
			_validate_qty_against_job_cards(doc)
	finally:
		frappe.flags.cps_control_warn_only = False


def _validate_line(doc, line, submitting, allowance, locked=None):
	controlled = resolve_item_control(line.item_code).controlled

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
	ledger_ready = _has_field("Customer Product Specification", cps_first_order_price.CLAIM_FIELD)
	if ledger_ready:
		if submitting:
			version = (locked or {}).get(spec.name)
			if not version or frappe.utils.get_datetime(version["modified"]) != frappe.utils.get_datetime(spec.modified):
				# Do not freeze a spec from an older repeatable-read snapshot.
				frappe.throw(_("Specification {0} changed while this order was being submitted. Reload and try again.").format(spec.name))
			claim = version.get(cps_first_order_price.CLAIM_FIELD)
		else:
			claim = spec.get(cps_first_order_price.CLAIM_FIELD)
		price, draft = cps_pricing.get_order_price_candidates(
			spec.name, doc.transaction_date, doc.get("currency"), lock=submitting
		)
	else:
		# Deploy-before-migrate window: retain the Approved-only rule.
		price = cps_pricing.get_eligible_price(spec.name, doc.transaction_date, doc.get("currency"))
		draft = None
	if not price:
		if draft:
			if cps_first_order_price.blocks_draft_price(claim, doc.name):
				message = _("The one Draft-price order for {0} was already used by {1}. Approve its CPS price before submitting another order.").format(spec.name, claim)
				if submitting:
					_throw(line, message)
				else:
					_warn(line, message)
				_clear_snapshot(line)
				return
			price = draft
			_warn(line, _("One-time Draft CPS price for {0}: approval is pending and another Sales Order will require an approved price.").format(spec.name))

	if not price:
		# V7 - warn on save, throw on submit.
		message = _("No eligible CPS price for {0} effective {1}. Enter a CPS Price row; after the first submitted order its price must be Approved.").format(
			spec.name, frappe.utils.formatdate(doc.transaction_date)
		)
		if submitting:
			_throw(line, message)
		_warn(line, message)
		_clear_snapshot(line)
		return

	if submitting:
		_validate_price(doc, line, spec, price, allowance)
		_stamp_snapshot(doc, line, spec, price, allowance)
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

	expected_type = resolve_item_control(line.item_code).product_type
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


def _price_check(doc, line, price, allowance):
	"""§5: the line rate against the eligible row, inside min(KES 1, 1%)."""
	return cps_price_rules.check_line_rate(
		line.rate,
		line.get("conversion_factor"),
		doc.get("currency"),
		price,
		allowance_kes=allowance[0],
		allowance_pct=allowance[1],
	)


def _validate_price(doc, line, spec, price, allowance):
	"""V8-V11 under §5: within the allowance, or an explained override.

	The Sales Master Manager requirement leaves SO submit (approved 08/11/2026):
	any rep may submit outside the allowance with a reason, and the job card
	holds on checks 9-10 until the Release screen drafts and approves a new row.
	"""
	if not price.get("conversion_factor") and price.get("uom") and line.uom and price["uom"] != line.uom:
		# A row that froze no factor (written before §5) is priced per its own
		# UOM and cannot be converted; the line must be in that UOM (V8).
		_throw(
			line,
			_("Line is priced per {0} but the CPS reference price for {1} is per {2}.").format(
				line.uom, spec.name, price["uom"]
			),
		)

	check = _price_check(doc, line, price, allowance)
	if check.ok:
		return

	if check.code in (cps_price_rules.PRICE_UOM_UNCONVERTIBLE, cps_price_rules.PRICE_CURRENCY):
		_throw(
			line,
			_("Rate {0} cannot be compared with the CPS reference price for {1}: {2}.").format(
				line.rate, spec.name, check.code.replace("-", " ")
			),
		)

	if not (line.get("custom_price_override_reason") or "").strip():
		_throw(
			line,
			_("Rate {0} is outside the allowance of {1} around the CPS reference rate {2} for {3}. Enter an Override Reason, or use the reference rate.").format(
				line.rate, check.allowance, check.approved_rate, spec.name
			),
		)

	_log_override(doc, line, spec, price, check)


def _stamp_snapshot(doc, line, spec, price, allowance):
	"""Freeze the commercial and technical snapshots onto the line (design §8).

	Written during the submit pass rather than in ``on_submit`` so the snapshot
	lands in the same write as the submit itself. The snapshot fields are
	``read_only`` and carry no ``allow_on_submit``, so nothing can edit them
	afterwards - including Data Import in update-existing mode.

	Every value is taken server-side from the specification and the selected
	price (Approved, or the one-order Draft exception). Caller-supplied snapshot
	values are discarded (V12); the exception never approves the price.
	"""
	check = _price_check(doc, line, price, allowance)
	source = cps_rules.SOURCE_CPS_PRICE if check.ok else cps_rules.SOURCE_MANUAL_OVERRIDE
	taken_at = frappe.utils.now()

	line.custom_cps_rate = cps_rules.round_rate(price.get("rate"))
	line.custom_cps_uom = price.get("uom")
	line.custom_cps_valid_from = price.get("valid_from")
	# The row the gate's checks 9-10 will validate and Release will bind
	# (Codex r4 point 3): one selection, written here, read by the card.
	line.custom_cps_price_row = price.get("name")
	line.custom_price_source = source
	line.custom_price_variance_pct = (
		cps_rules.variance_pct(check.normalised_rate, price.get("rate"))
		if check.normalised_rate is not None else None
	)
	line.custom_price_approved_by = (
		frappe.session.user if source == cps_rules.SOURCE_MANUAL_OVERRIDE else None
	)

	line.custom_spec_name = spec.specification_name
	line.custom_job_size = spec.get("job_size")
	line.custom_number_of_parts = spec.get("number_of_parts")
	line.custom_number_of_colours = spec.get("number_of_colours")
	line.custom_spec_snapshot_at = taken_at
	snapshot = cps_rules.build_spec_snapshot(
		spec, spec.get("colour_of_parts"), spec.get("spot_colours"), taken_at
	)
	if price.get("approval_status") == cps_rules.APPROVAL_DRAFT:
		# Immutable audit marker, not a price approval or a customer memo.
		snapshot["_draft_price_first_order"] = {"sales_order": doc.name, "price_row": price.get("name")}
	line.custom_spec_snapshot = json.dumps(
		snapshot,
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
	"""Claim each CPS's first submitted order in the same SO transaction.

	Snapshots are stamped during the submit validation pass (see
	``_stamp_snapshot``) so they are written atomically with the submit, rather
	than as a second ``db_set`` update afterwards. The CPS locks taken there are
	still held here. Any later submit-hook failure rolls this claim back too.
	Approved-price orders also count as an existing first order; replacing a
	price row later must not create a fresh Draft-price allowance.
	"""
	if not control_enabled() or not _has_field("Customer Product Specification", cps_first_order_price.CLAIM_FIELD):
		return
	locked = cps_first_order_price.lock_specs(
		frappe.db, [line.get("custom_cps") for line in doc.get("items") or []]
	)
	cps_first_order_price.claim_locked_specs(frappe.db, locked, doc.name)


def on_cancel(doc, method=None):
	"""V14: an order with live Job Cards cannot be cancelled out from under them."""
	if not control_enabled():
		return

	blocking = []
	for doctype in JOB_CARD_DOCTYPES.values():
		if not frappe.db.exists("DocType", doctype):
			continue
		# A card type registered here before its order-derived fields have
		# landed on this site has nothing to filter on. Querying a column that
		# does not exist would throw on every cancel of every order, which is a
		# far worse failure than not blocking on a card that cannot exist yet.
		if not _has_field(doctype, "sales_order"):
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
	if frappe.flags.cps_control_warn_only:
		# Warn mode (§4, checklist D): say it, refuse nothing.
		_warn(line, message)
		return
	frappe.throw(_("Line {0}: {1}").format(line.idx, message), title=_("Specification Control"))


def _warn(line, message):
	frappe.msgprint(
		_("Line {0}: {1}").format(line.idx, message),
		title=_("Specification Control"),
		indicator="orange",
	)


def _log_override(doc, line, spec, price, check):
	"""Audit an explained price override (design §9.3).

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
				"price_row": price.get("name"),
				"cps_rate": price.get("rate"),
				"line_rate": line.rate,
				"normalised_rate": check.normalised_rate,
				"allowance": check.allowance,
				"variance": check.variance,
				"reason": line.get("custom_price_override_reason"),
				"user": frappe.session.user,
			},
			default=str,
			indent=1,
		),
	)


# ---------------------------------------------------------------------------
# Quotation validation (§4) - Warn only until Tanuj changes the mode
# ---------------------------------------------------------------------------


def validate_quotation(doc, method=None):
	"""A quotation line for a controlled Item should name its specification.

	Mode from ``Selling Settings.custom_cps_quotation_mode``: Off is inert,
	Warn (the shipped value) shows the line and logs it to Error Log
	``vcl_quote_control`` with the creator and route, Enforce refuses only when
	the quotation is being submitted. Reads ``Quotation Item.custom_cps`` when
	that field exists (plan Part II) and otherwise only reports.
	"""
	mode = quotation_mode()
	if mode == cps_rules.QUOTE_MODE_OFF:
		return
	if not _has_field("Item", "custom_requires_cps"):
		return

	has_cps_field = _has_field("Quotation Item", "custom_cps")
	submitting = doc.docstatus == 1
	hits = []
	for line in doc.get("items") or []:
		control = resolve_item_control(line.item_code)
		if not control.controlled:
			continue
		if has_cps_field and line.get("custom_cps"):
			continue
		hits.append({
			"idx": line.idx,
			"item_code": line.item_code,
			"product_type": control.product_type,
			"reason": control.reason,
		})
		message = _("Line {0}: {1} is specification-controlled ({2}) and names no Customer Product Specification.").format(
			line.idx, line.item_code, control.product_type or _("type unresolved")
		)
		if mode == cps_rules.QUOTE_MODE_ENFORCE and submitting:
			frappe.throw(message, title=_("Specification Control"))
		frappe.msgprint(message, title=_("Specification Control"), indicator="orange")

	if hits:
		request = getattr(frappe.local, "request", None)
		frappe.log_error(
			title="vcl_quote_control",
			message=json.dumps(
				{
					"quotation": doc.name,
					"docstatus": doc.docstatus,
					"mode": mode,
					"creator": frappe.session.user,
					"route": request.path if request is not None else "server",
					"lines": hits,
				},
				default=str,
				indent=1,
			),
		)
