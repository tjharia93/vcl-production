"""The job-card release gate: eleven yes/no checks as pure functions (Stream A §7b).

No Frappe import. ``evaluate`` takes a context dict assembled by
:mod:`production_log.job_card_tracking.release` from the card, its Sales Order
line, the specification, the BOUND revision payload, the BOUND price row and
the artwork state, and returns one :class:`CheckResult` per check. Numbering
matches ``jobcard_release_checklist.html`` (approved 08/11/2026): 1-6 and 8-11
required, 7 a warning printed on the card.

Codex r4, point 1: approval, price and snapshot are evaluated against the
revision, price row and artwork version bound to the card - never the spec's
current ones. "Refresh to the latest revision" is a separate, explicit action.

Context keys (all plain dicts / values):
  order        {docstatus, status, customer, transaction_date, currency}
  line         {name, custom_cps, qty, rate, uom, conversion_factor, custom_cps_price_row} or None
  other_cards_qty  quantity on other live cards for the same line
  card         {quantity_ordered, customer_product_spec, item_code, spec_snapshot (dict|None),
                customer_hold, artwork_approved}
  spec         the specification's fields incl. vcl_* (current record)
  bound_revision   int - the revision this card is bound to
  bound_payload    the stored payload for that revision, or None
  item_control     cps_rules.ItemControl
  price_row    the bound / selected CPS Price row, or None
  allowance    (kes, pct)
  artwork      {"state": Customer-approved | Not applicable | Pending | None, "version": str|None}
  stored_fingerprint   dict or None
"""

from collections import namedtuple

from production_log.job_card_tracking import cps_lifecycle_rules, cps_price_rules, cps_rules

CheckResult = namedtuple("CheckResult", ("number", "name", "passed", "required", "overridable", "message"))

STATE_HELD = "Held"
STATE_RELEASED = "Released"
STATE_RELEASED_OVERRIDE = "Released (override)"
STATE_REHELD = "Re-held"
RELEASE_STATES = (STATE_HELD, STATE_RELEASED, STATE_RELEASED_OVERRIDE, STATE_REHELD)

HOLD_REASON_AWAITING = "Awaiting release"
HOLD_REASON_SPEC_CHANGED = "Spec changed after release"
RELEASE_HOLD_REASONS = (HOLD_REASON_AWAITING, HOLD_REASON_SPEC_CHANGED)

OVERRIDE_ROLE = "VCL Management Team"
SYSTEM_USER = "Administrator"

CLOSED_ORDER_STATUSES = ("Closed", "Cancelled")
ARTWORK_OK_STATES = ("Customer-approved", "Not applicable")

CHECK_NAMES = {
	1: "Live order line",
	2: "Right spec for the line",
	3: "Spec revision orderable",
	4: "Construction complete",
	5: "Print defined",
	6: "Artwork",
	7: "Packing defined",
	8: "Technical approval for this revision",
	9: "Approved price row",
	10: "Rate within allowance",
	11: "Inputs unchanged",
}
WARNING_ONLY = frozenset({7})
NON_OVERRIDABLE = frozenset({1})


def _get(row, key):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def _num(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def _blank(value):
	return value in (None, "") or (isinstance(value, str) and not value.strip())


def _result(number, passed, message="", note=""):
	"""``message`` explains a failure; ``note`` is kept on a pass (e.g. which fallback was used)."""
	return CheckResult(
		number, CHECK_NAMES[number], bool(passed), number not in WARNING_ONLY,
		number not in NON_OVERRIDABLE, message if not passed else note,
	)


# --- Individual checks --------------------------------------------------------


def check_live_order_line(ctx):
	order, line, card = ctx.get("order"), ctx.get("line"), ctx.get("card") or {}
	if not order or int(_get(order, "docstatus") or 0) != 1:
		return _result(1, False, "Sales Order is not submitted")
	if (_get(order, "status") or "") in CLOSED_ORDER_STATUSES:
		return _result(1, False, "Sales Order is {0}".format(_get(order, "status")))
	if not line:
		return _result(1, False, "Sales Order line not found")
	available = _num(_get(line, "qty")) - _num(ctx.get("other_cards_qty"))
	if _num(_get(card, "quantity_ordered")) > available + 1e-9:
		return _result(1, False, "card quantity {0} exceeds {1} left on the line".format(
			_get(card, "quantity_ordered"), round(available, 3)))
	return _result(1, True)


def check_right_spec(ctx):
	order, line, card, spec = ctx.get("order"), ctx.get("line"), ctx.get("card") or {}, ctx.get("spec")
	control = ctx.get("item_control")
	if not spec:
		return _result(2, False, "specification not found")
	if line is not None and (_get(card, "customer_product_spec") or "") != (_get(line, "custom_cps") or ""):
		return _result(2, False, "card spec {0} is not the line's {1}".format(
			_get(card, "customer_product_spec"), _get(line, "custom_cps")))
	if order is not None and (_get(spec, "customer") or "") != (_get(order, "customer") or ""):
		return _result(2, False, "spec belongs to {0}, order to {1}".format(_get(spec, "customer"), _get(order, "customer")))
	if not cps_rules.spec_serves_item(spec, _get(card, "item_code")):
		return _result(2, False, "spec is linked to {0}, not {1}".format(_get(spec, "linked_item") or "no Item", _get(card, "item_code")))
	expected = _get(control, "product_type") if control is not None else None
	if expected and cps_rules.normalise_product_type(_get(spec, "product_type")) != expected:
		return _result(2, False, "{0} needs a {1} specification, this is {2}".format(
			_get(card, "item_code"), expected, _get(spec, "product_type")))
	return _result(2, True)


def check_orderable(ctx):
	spec = ctx.get("spec")
	if not spec or int(_get(spec, "docstatus") or 0) != 1:
		return _result(3, False, "specification is not submitted")
	status = _get(spec, "status") or ""
	if status not in cps_lifecycle_rules.ORDERABLE_STATUSES:
		return _result(3, False, "specification is {0}".format(status))
	return _result(3, True)


def _bound_fields(ctx):
	"""The revision the card is bound to: its payload when stored, else the spec."""
	return ctx.get("bound_payload") or ctx.get("spec") or {}


def snapshot_mismatches(snapshot, payload):
	"""Keys present in BOTH the card's snapshot and the bound payload that disagree."""
	if not isinstance(snapshot, dict) or not isinstance(payload, dict):
		return []
	out = []
	for key, expected in payload.items():
		if key.startswith("_") or key not in snapshot:
			continue
		found = snapshot.get(key)
		if isinstance(expected, list) or isinstance(found, list):
			if _rows(found) != _rows(expected):
				out.append(key)
			continue
		if cps_lifecycle_rules._norm(found) != cps_lifecycle_rules._norm(expected):
			out.append(key)
	return out


def _rows(value):
	return [
		{k: cps_lifecycle_rules._norm(v) for k, v in sorted((r or {}).items())}
		for r in (value or [])
	]


def check_construction(ctx):
	spec = ctx.get("spec") or {}
	bound = _bound_fields(ctx)
	product_type = _get(spec, "product_type")
	# Subtype decisions (ply, the die-cut route) come from the bound payload
	# first and the spec for anything the payload does not carry.
	subtype = dict(spec) if isinstance(spec, dict) else {}
	if isinstance(bound, dict):
		subtype.update({k: v for k, v in bound.items() if not k.startswith("_")})
	missing = [f for f in cps_rules.mandatory_fields(product_type, subtype) if _blank(_get(bound, f))]
	if cps_rules.normalise_product_type(product_type) == "Computer Paper":
		parts = int(_num(_get(bound, "number_of_parts")))
		rows = _get(bound, "colour_of_parts") or []
		if parts and len(rows) < parts:
			missing.append("colour_of_parts ({0} of {1} parts)".format(len(rows), parts))
		for row in rows:
			if _blank(_get(row, "paper_type")) or _blank(_get(row, "gsm")):
				missing.append("colour_of_parts part {0} paper/GSM".format(_get(row, "part_number")))
				break
	if missing:
		return _result(4, False, "construction incomplete: {0}".format(", ".join(missing)))

	mismatches = snapshot_mismatches(_get(ctx.get("card"), "spec_snapshot"), ctx.get("bound_payload"))
	if mismatches:
		return _result(4, False, "card snapshot differs from revision {0}: {1}".format(
			ctx.get("bound_revision"), ", ".join(mismatches)))
	return _result(4, True)


def _is_printed(fields):
	return (_get(fields, "print_type") or _get(fields, "printing_or_plain") or "") == "Printed"


def check_print_defined(ctx):
	bound = _bound_fields(ctx)
	print_type = _get(bound, "print_type") or _get(bound, "printing_or_plain")
	if _blank(print_type):
		return _result(5, False, "print type not set")
	if print_type == "Printed" and int(_num(_get(bound, "number_of_colours"))) <= 0:
		return _result(5, False, "Printed with no colours")
	return _result(5, True)


def check_artwork(ctx):
	"""Printed jobs need the artwork version BOUND to the card Customer-approved or N/A.

	Falls back to the Design and Artwork Tracker / the card's ``artwork_approved``
	tick ONLY when the specification has no artwork versions at all, and the
	result says so. A bound version that has been superseded fails: the card
	re-holds (unissued) or is flagged superseded (issued).
	"""
	bound = _bound_fields(ctx)
	if not _is_printed(bound):
		return _result(6, True, note="Plain - artwork not applicable")
	artwork = ctx.get("artwork") or {}
	if _get(artwork, "versions_exist"):
		if _get(artwork, "superseded"):
			return _result(6, False, _get(artwork, "note") or "bound artwork version superseded")
		if _get(artwork, "state") in ARTWORK_OK_STATES:
			return _result(6, True, note="artwork version {0} {1}".format(_get(artwork, "version"), _get(artwork, "state")))
		return _result(6, False, "artwork version {0} is {1}".format(_get(artwork, "version") or "?", _get(artwork, "state") or "Pending"))
	# No versions on the specification: legacy evidence, and say so.
	fallback = "no artwork versions on the specification - "
	card = ctx.get("card") or {}
	if int(_num(_get(card, "artwork_approved"))):
		return _result(6, True, note=fallback + "card artwork_approved tick used")
	spec = ctx.get("spec") or {}
	if _get(spec, "artwork_tracker") and not int(_num(_get(spec, "artwork_not_ready"))):
		return _result(6, True, note=fallback + "Design and Artwork Tracker {0} used".format(_get(spec, "artwork_tracker")))
	return _result(6, False, fallback + "no customer-approved artwork for a Printed job")


def check_packing(ctx):
	bound = _bound_fields(ctx)
	spec = ctx.get("spec") or {}
	defined = not _blank(_get(bound, "standard_packing")) or _num(_get(bound, "packing_pieces")) > 0 or _num(_get(bound, "sets_per_carton")) > 0
	if not defined:
		return _result(7, False, "packing not defined")
	if cps_rules.normalise_product_type(_get(spec, "product_type")) == "Carton" and _num(_get(bound, "standard_weight_per_carton")) <= 0:
		return _result(7, False, "carton weight not defined")
	return _result(7, True)


def check_technical_approval(ctx):
	spec = ctx.get("spec")
	revision = ctx.get("bound_revision")
	if not spec or not revision:
		return _result(8, False, "no revision bound")
	if not cps_lifecycle_rules.revision_is_approved(spec, revision):
		return _result(8, False, "revision {0} is not technically approved (approved: {1}, state: {2})".format(
			revision, _get(spec, "vcl_approved_rev") or "none", _get(spec, "vcl_approval_state") or "none"))
	return _result(8, True)


def check_price_row(ctx):
	row, order, line = ctx.get("price_row"), ctx.get("order") or {}, ctx.get("line") or {}
	if not row:
		return _result(9, False, "no approved price row")
	if _get(row, "approval_status") != cps_rules.APPROVAL_APPROVED:
		return _result(9, False, "price row is {0}".format(_get(row, "approval_status")))
	if cps_price_rules.row_currency(row) != ((_get(order, "currency") or "").strip() or cps_price_rules.DEFAULT_CURRENCY):
		return _result(9, False, "price row currency {0} is not the order's".format(cps_price_rules.row_currency(row)))
	valid_from = cps_rules.to_date(_get(row, "valid_from"))
	on_date = cps_rules.to_date(_get(order, "transaction_date"))
	if valid_from and on_date and valid_from > on_date:
		return _result(9, False, "price row effective {0} is after the order date".format(valid_from))
	if not _get(row, "conversion_factor") and _get(row, "uom") and _get(line, "uom") and _get(row, "uom") != _get(line, "uom"):
		return _result(9, False, "line is per {0}, price row per {1} with no conversion".format(_get(line, "uom"), _get(row, "uom")))
	return _result(9, True)


def check_rate(ctx):
	row, order, line = ctx.get("price_row"), ctx.get("order") or {}, ctx.get("line")
	if not row or not line:
		return _result(10, False, "nothing to compare")
	kes, pct = ctx.get("allowance") or (cps_price_rules.ALLOWANCE_DEFAULT_KES, cps_price_rules.ALLOWANCE_DEFAULT_PCT)
	check = cps_price_rules.check_line_rate(
		_get(line, "rate"), _get(line, "conversion_factor"), _get(order, "currency"), row, kes, pct,
	)
	if check.ok:
		return _result(10, True)
	return _result(10, False, "line rate {0} vs approved {1}: {2} (allowance {3})".format(
		_get(line, "rate"), check.approved_rate, check.code.replace("-", " "), check.allowance))


# --- Fingerprint (check 11) ---------------------------------------------------


def build_fingerprint(ctx):
	"""Everything checks 1-10 read, as JSON-safe scalars."""
	line, order, spec, row, card = ctx.get("line") or {}, ctx.get("order") or {}, ctx.get("spec") or {}, ctx.get("price_row") or {}, ctx.get("card") or {}
	artwork = ctx.get("artwork") or {}

	def s(value):
		return None if value in (None, "") else str(value)

	return {
		"so_line": s(_get(line, "name")),
		"qty": _num(_get(line, "qty")),
		"rate": cps_rules.round_rate(_get(line, "rate")) if _get(line, "rate") not in (None, "") else None,
		"currency": s(_get(order, "currency")),
		"conversion_factor": _num(_get(line, "conversion_factor")) or None,
		"order_status": s(_get(order, "status")),
		"spec": s(_get(spec, "name")),
		"spec_revision": int(_num(ctx.get("bound_revision"))),
		"spec_current_revision": int(_num(_get(spec, "vcl_revision"))),
		"spec_approved_rev": int(_num(_get(spec, "vcl_approved_rev"))),
		"spec_status": s(_get(spec, "status")),
		"spec_approval_state": s(_get(spec, "vcl_approval_state")),
		"price_row": s(_get(row, "name")),
		"price_rate": cps_rules.round_rate(_get(row, "rate")) if _get(row, "rate") not in (None, "") else None,
		"price_uom": s(_get(row, "uom")),
		"price_currency": cps_price_rules.row_currency(row) if row else None,
		"price_conversion_factor": _num(_get(row, "conversion_factor")) or None,
		"price_valid_from": s(cps_rules.to_date(_get(row, "valid_from"))) if row else None,
		"price_approval_status": s(_get(row, "approval_status")),
		"artwork_state": s(_get(artwork, "state")),
		"artwork_version": s(_get(artwork, "version")),
		"customer_hold": int(_num(_get(card, "customer_hold"))),
	}


def fingerprint_changes(stored, current):
	"""Keys whose value differs. An empty or missing stored fingerprint = nothing to compare."""
	if not isinstance(stored, dict) or not stored:
		return []
	return sorted(k for k in set(stored) | set(current) if stored.get(k) != current.get(k))


def is_stale(stored, current):
	return bool(fingerprint_changes(stored, current))


def check_freshness(ctx, current_fingerprint):
	card = ctx.get("card") or {}
	if int(_num(_get(card, "customer_hold"))):
		# Non-overridable by §7b: a customer hold is not a check anyone clears.
		return CheckResult(11, CHECK_NAMES[11], False, True, False, "customer hold is set")
	changes = fingerprint_changes(ctx.get("stored_fingerprint"), current_fingerprint)
	if changes:
		return _result(11, False, "inputs changed since the last evaluation: {0}".format(", ".join(changes)))
	return _result(11, True)


# --- The gate -----------------------------------------------------------------

CHECKS = (
	check_live_order_line,
	check_right_spec,
	check_orderable,
	check_construction,
	check_print_defined,
	check_artwork,
	check_packing,
	check_technical_approval,
	check_price_row,
	check_rate,
)


def evaluate(ctx):
	"""Run checks 1-11. Returns (results, fingerprint). Check 11 compares the
	stored fingerprint with the one built from THIS evaluation's inputs; the
	caller stores the new one, so a re-run after a change passes 11 and the
	other ten decide."""
	results = [check(ctx) for check in CHECKS]
	fingerprint = build_fingerprint(ctx)
	results.append(check_freshness(ctx, fingerprint))
	return results, fingerprint


def failing(results, required_only=True):
	return [r for r in results if not r.passed and (r.required or not required_only)]


def all_required_pass(results):
	return not failing(results)


def non_overridable_failures(results):
	return [r for r in results if not r.passed and r.required and not r.overridable]


def can_override(results):
	"""Management may override only when nothing failing is non-overridable."""
	return bool(failing(results)) and not non_overridable_failures(results)


def failing_numbers(results):
	return [r.number for r in failing(results)]


def warnings(results):
	return [r for r in results if not r.passed and not r.required]


def results_payload(results):
	"""JSON per check for ``release_checks``."""
	return [
		{"n": r.number, "name": r.name, "passed": r.passed, "required": r.required,
		 "overridable": r.overridable, "message": r.message}
		for r in results
	]


def summary(results):
	"""One line for the board and the Print refusal: 'Held — check 9 failed: ...'."""
	fails = failing(results)
	if not fails:
		return STATE_RELEASED
	first = fails[0]
	more = " (+{0} more)".format(len(fails) - 1) if len(fails) > 1 else ""
	return "Held — check {0} failed: {1}{2}".format(first.number, first.message or first.name, more)


# --- Issuance (Codex r4 point 2) ---------------------------------------------


def manual_hold_active(card):
	"""A PPC / customer hold that is NOT the gate's own. Blocks issuance independently."""
	if int(_num(_get(card, "customer_hold"))):
		return "customer hold"
	if (_get(card, "job_status") or "") == "On Hold" and (_get(card, "hold_reason") or "") not in RELEASE_HOLD_REASONS:
		return "on hold: {0}".format(_get(card, "hold_reason") or "manual")
	return None


def issuance_block_reason(card, stale):
	"""Why a card may not be rendered: not Released, stale, or held by a person."""
	manual = manual_hold_active(card)
	if manual:
		return manual
	state = _get(card, "release_state") or STATE_HELD
	if state not in (STATE_RELEASED, STATE_RELEASED_OVERRIDE):
		return "release state is {0}".format(state)
	if stale:
		return "inputs changed since release"
	if int(_num(_get(card, "print_superseded"))):
		return "print superseded — withdraw and reprint"
	return None


def override_refusal(results, roles, user, owners, reason):
	"""Why ``release.override`` must refuse, or None."""
	if OVERRIDE_ROLE not in set(roles or ()):
		return "{0} role required".format(OVERRIDE_ROLE)
	if user in set(o for o in owners if o):
		return "the card's or order's owner may not override their own card"
	if not (reason or "").strip():
		return "a reason is required"
	blocked = non_overridable_failures(results)
	if blocked:
		return "check {0} cannot be overridden".format(", ".join(str(r.number) for r in blocked))
	if not failing(results):
		return "nothing to override — every check passes"
	return None
