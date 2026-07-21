"""Pure decision rules for CPS pricing and CPS-controlled Sales Order lines.

This module deliberately imports nothing from Frappe. Every function takes plain
data (dicts, dates, numbers) and returns plain data, so the rules can be unit
tested without a bench, a site or a database. The Frappe-bound callers live in
``cps_pricing.py`` and ``so_spec_control.py`` and are responsible for reading
documents, raising ``frappe.throw`` and writing fields.

Phase 2 solution design references are quoted in each function docstring.
"""

from collections import namedtuple
from datetime import date, datetime

# Rates round-trip at 9 decimal places end to end (design §5.1): the live label
# rate 5.172413793 is 9 dp and any lower precision silently rounds it, which
# would then fail the exact-match test in §9.1 forever.
RATE_PRECISION = 9

# Every rate VCL has ever agreed is in Kenyan Shillings, but a price row is a
# commercial commitment and a bare number is not one — the currency has to be
# recorded, not assumed at read time. KES is the fallback only when there is
# nothing safer to derive it from (see :func:`default_price_currency`).
DEFAULT_CURRENCY = "KES"

APPROVAL_DRAFT = "Draft"
APPROVAL_APPROVED = "Approved"
APPROVAL_REJECTED = "Rejected"

# Writing any of these on an Approved row resets it to Draft (design §5.3).
PRICE_APPROVAL_RESET_FIELDS = ("rate", "uom", "valid_from")

SOURCE_CPS_PRICE = "CPS Price"
SOURCE_ITEM_PRICE = "Item Price"
SOURCE_MANUAL_OVERRIDE = "Manual Override"

JC_NOT_STARTED = "Not Started"
JC_PARTIAL = "Partial"
JC_FULLY_CARDED = "Fully Carded"


PriceDecision = namedtuple(
	"PriceDecision",
	("source", "variance_pct", "requires_override", "below_floor"),
)

# --- CPS -> Item link -------------------------------------------------------
#
# Every CPS names exactly one Item. Items are generic and shared: "Computer
# Paper 3 Part A4" is one Item that many customers buy, and each of those
# customers has their own specification against it. So the link is
# many-CPS-to-one-Item, and creating an Item per CPS would be wrong.
#
# Editing a specification's shape is what forces the link, so a legacy record
# nobody has touched keeps working while anything materially edited is brought
# up to standard.
ITEM_LINK_FIELD = "linked_item"

# Changing any of these changes what the specification *is*, so the Item it
# names has to be stated. Notes, status and pricing are deliberately absent.
MATERIAL_SPEC_FIELDS = (
	"product_type",
	"specification_name",
	"customer",
	"job_size",
	"pay_slip_size",
	"number_of_parts",
	ITEM_LINK_FIELD,
)

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_NONE = "none"

_CONFIDENCE_RANK = {
	CONFIDENCE_HIGH: 3,
	CONFIDENCE_MEDIUM: 2,
	CONFIDENCE_LOW: 1,
	CONFIDENCE_NONE: 0,
}

MATCH_ALREADY_LINKED = "already-linked"
MATCH_EXACT_SOLE = "exact-sole"
MATCH_AMBIGUOUS = "ambiguous"
MATCH_NONE = "none"

# Words that carry no discriminating power when comparing a specification name
# to an item name - every Computer Paper record contains most of them.
_STOP_WORDS = frozenset(
	("computer", "paper", "part", "parts", "ply", "the", "and", "of", "for", "with", "")
)

ItemCandidate = namedtuple("ItemCandidate", ("item_code", "confidence", "reasons"))
ItemLinkDecision = namedtuple("ItemLinkDecision", ("match", "auto_item", "candidates"))


def to_date(value):
	"""Normalise a date-ish value to ``datetime.date``, or None.

	Accepts ``date``, ``datetime`` and ISO-ish strings, because Frappe hands
	back any of the three depending on whether a value came from the database,
	from a form submission or from a fixture.
	"""
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	if isinstance(value, str):
		return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
	raise TypeError("Cannot interpret {0!r} as a date".format(value))


def _get(row, key):
	"""Read a key from a dict or an attribute from a Frappe child row."""
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def round_rate(value):
	"""Round to the 9 dp the CPS Price / SO Item / Job Card fields all carry."""
	if value is None:
		return None
	return round(float(value), RATE_PRECISION)


def resolve_eligible_price(rows, on_date):
	"""Return the eligible CPS Price row for ``on_date``, or None (design §5.2).

	The eligible price is the row with ``approval_status == "Approved"`` and the
	greatest ``valid_from`` that is ``<= on_date``. Draft and Rejected rows are
	invisible, and so are future-dated rows — that is what makes a price
	increase schedulable.

	``on_date`` is the Sales Order ``transaction_date``, never ``today()``, so a
	backdated order prices at the rate agreed on the order date and a
	re-submitted amendment reproduces the original rate.
	"""
	on_date = to_date(on_date)
	if on_date is None:
		return None

	eligible = None
	eligible_from = None
	for row in rows or []:
		if _get(row, "approval_status") != APPROVAL_APPROVED:
			continue
		valid_from = to_date(_get(row, "valid_from"))
		if valid_from is None or valid_from > on_date:
			continue
		if eligible_from is None or valid_from > eligible_from:
			eligible, eligible_from = row, valid_from

	return eligible


def find_duplicate_valid_from(rows):
	"""Return ``valid_from`` dates used by more than one non-Rejected row.

	Ties among eligible rows must be impossible by construction (design §5.2),
	otherwise ``resolve_eligible_price`` would pick arbitrarily. Rejected rows
	are excluded from the comparison so a rejected row can be superseded by a
	corrected one carrying the same date.
	"""
	seen = set()
	duplicates = []
	for row in rows or []:
		if _get(row, "approval_status") == APPROVAL_REJECTED:
			continue
		valid_from = to_date(_get(row, "valid_from"))
		if valid_from is None:
			continue
		if valid_from in seen:
			if valid_from not in duplicates:
				duplicates.append(valid_from)
		else:
			seen.add(valid_from)
	return sorted(duplicates)


def price_approval_reset_required(before, after):
	"""True when an edit must knock an Approved row back to Draft (design §5.3).

	Approval is a rubber stamp on a mutable number unless changing the rate, the
	UOM or the effective date revokes it.
	"""
	if before is None or after is None:
		return False
	if _get(before, "approval_status") != APPROVAL_APPROVED:
		return False

	for fieldname in PRICE_APPROVAL_RESET_FIELDS:
		old, new = _get(before, fieldname), _get(after, fieldname)
		if fieldname == "valid_from":
			old, new = to_date(old), to_date(new)
		elif fieldname == "rate":
			old, new = round_rate(old), round_rate(new)
		if old != new:
			return True

	return False


def variance_pct(line_rate, cps_rate):
	"""Signed percentage the line rate deviates from the CPS rate.

	Returns None when the CPS rate is zero or missing — a percentage against
	zero is not a number anyone should act on.
	"""
	cps_rate = round_rate(cps_rate)
	if not cps_rate:
		return None
	return (round_rate(line_rate) - cps_rate) / cps_rate * 100.0


def is_exact_match(line_rate, cps_rate, tolerance_pct=None):
	"""Whether the line rate passes without an override (design §9.1).

	``tolerance_pct`` is unset by default (DN-5): matching is exact-match-only
	until management supplies a real value, so 5.17 typed against 5.172413793
	is a deviation, not a rounding nicety.
	"""
	line_rate, cps_rate = round_rate(line_rate), round_rate(cps_rate)
	if line_rate == cps_rate:
		return True
	if tolerance_pct is None:
		return False

	deviation = variance_pct(line_rate, cps_rate)
	if deviation is None:
		return False
	return abs(deviation) <= float(tolerance_pct)


def is_below_floor(line_rate, cps_rate, floor_pct=None):
	"""Whether the line rate breaches a configured floor (design §9.1 V10).

	The floor ships disabled (DN-5). Once management sets a real value nobody
	clears it, including System Manager — a floor with an escape hatch is not a
	floor.
	"""
	if floor_pct is None:
		return False
	cps_rate = round_rate(cps_rate)
	if not cps_rate:
		return False
	return round_rate(line_rate) < round_rate(cps_rate * float(floor_pct) / 100.0)


def evaluate_price(line_rate, cps_rate, tolerance_pct=None, floor_pct=None):
	"""Classify a controlled line's rate against its eligible CPS rate.

	Returns a :class:`PriceDecision`. Both directions deviate — charging more
	and charging less than the agreed rate each require an explicit override
	reason and the Sales Master Manager role (design §9.1).
	"""
	if is_exact_match(line_rate, cps_rate, tolerance_pct):
		return PriceDecision(SOURCE_CPS_PRICE, 0.0, False, False)

	return PriceDecision(
		SOURCE_MANUAL_OVERRIDE,
		variance_pct(line_rate, cps_rate),
		True,
		is_below_floor(line_rate, cps_rate, floor_pct),
	)


def remaining_qty(so_qty, carded_qty):
	"""Quantity still available to card on a Sales Order line (design §11.2).

	Draft Job Cards count towards ``carded_qty``: a draft reserves quantity, or
	two people raise two full-quantity job cards in the same minute and neither
	validation fires.
	"""
	return float(so_qty or 0) - float(carded_qty or 0)


def derive_jc_status(carded_qty, so_qty):
	"""Job Card rollup status for a Sales Order line (design §11.2 rule 5)."""
	carded_qty, so_qty = float(carded_qty or 0), float(so_qty or 0)
	if carded_qty <= 0:
		return JC_NOT_STARTED
	if so_qty and carded_qty >= so_qty:
		return JC_FULLY_CARDED
	return JC_PARTIAL


# --- Job Card provenance against its Sales Order line (design §11.3) --------
#
# A Job Card raised from an order is a copy of what that order froze, not a
# fresh read of the specification. The specification may since have been
# amended, re-priced or deactivated, and none of that may reach a job that has
# already been sold. So every identifying, commercial and technical value on
# the card is checked back against the line it claims to come from: the Desk
# and REST paths can post whatever they like into read-only fields, and the
# only thing that makes those fields trustworthy is comparing them server-side.

JCMismatch = namedtuple("JCMismatch", ("field", "label", "found", "expected"))

# Card field -> Sales Order line field, for the values copied verbatim.
JC_LINE_FIELD_MAP = (
	("item_code", "item_code", "Item"),
	("customer_product_spec", "custom_cps", "Customer Product Specification"),
	("price_source", "custom_price_source", "Price Source"),
)


def snapshot_product_type(snapshot):
	"""Product type as frozen on the order line, never from the current CPS."""
	if not isinstance(snapshot, dict):
		return None
	value = snapshot.get("product_type")
	if isinstance(value, str):
		value = value.strip()
	return value or None


def expected_jc_rate(line):
	"""The actual Sales Order line rate carried to the Job Card.

	The approved CPS reference rate remains separately frozen on the Sales Order
	Item for override audit; production must see the rate that was actually sold.
	"""
	return round_rate(_num(_get(line, "rate")))


def _num(value):
	"""Numeric fields default to zero, so blank and zero are the same value."""
	return float(value or 0)


def _text(value):
	"""Compare long text by content, ignoring surrounding whitespace."""
	if value is None:
		return None
	return str(value).strip() or None


def _stamp(value):
	"""Compare a timestamp to the second, however it was serialised."""
	if value in (None, ""):
		return None
	return str(value).strip()[:19]


def _same(found, expected):
	"""Blank is blank: ``None`` and empty string are not a disagreement."""
	if found in (None, ""):
		found = None
	if expected in (None, ""):
		expected = None
	return found == expected


def jc_line_mismatches(card, order, line, qty_precision=3):
	"""Every Job Card value that disagrees with its Sales Order and line.

	Returns a list of :class:`JCMismatch`. An empty list means the card is a
	faithful copy of the order line; anything else is a forged or stale
	document and must not be saved.

	``customer`` is checked against the *order*, not against the snapshot's own
	customer key — the order is what was sold, and the snapshot is a record of
	the specification rather than of the counterparty.
	"""
	checks = [
		("customer", "Customer", _get(card, "customer"), _get(order, "customer")),
	]
	for card_field, line_field, label in JC_LINE_FIELD_MAP:
		checks.append((card_field, label, _get(card, card_field), _get(line, line_field)))

	checks += [
		(
			"spec_snapshot",
			"Specification Snapshot",
			_text(_get(card, "spec_snapshot")),
			_text(_get(line, "custom_spec_snapshot")),
		),
		(
			"spec_snapshot_at",
			"Snapshot Taken At",
			_stamp(_get(card, "spec_snapshot_at")),
			_stamp(_get(line, "custom_spec_snapshot_at")),
		),
	]

	mismatches = [
		JCMismatch(field, label, found, expected)
		for field, label, found, expected in checks
		if not _same(found, expected)
	]

	found_rate, expected_rate = round_rate(_num(_get(card, "rate"))), expected_jc_rate(line)
	if found_rate != expected_rate:
		mismatches.append(JCMismatch("rate", "Rate", found_rate, expected_rate))

	found_qty = round(_num(_get(card, "so_qty")), qty_precision)
	expected_qty = round(_num(_get(line, "qty")), qty_precision)
	if found_qty != expected_qty:
		mismatches.append(JCMismatch("so_qty", "SO Line Quantity", found_qty, expected_qty))

	return mismatches


def spec_serves_item(spec, item_code):
	"""Whether ``spec`` is declared for exactly this Item.

	There is no fuzzy fallback and no "unlinked means compatible" case. An
	unlinked specification serves nothing: treating a missing link as a wildcard
	is how the wrong customer's agreed rate reaches the wrong product.
	"""
	linked = _get(spec, ITEM_LINK_FIELD)
	if not linked or not item_code:
		return False
	return str(linked).strip() == str(item_code).strip()


def item_link_required(before, after):
	"""Whether this save must carry an Item link (the transition rule).

	Required for a new specification, and for any edit that changes what the
	specification *is*. A legacy record that nobody has materially touched is
	grandfathered, so 53 unlinked live records do not become 53 blocked saves on
	the day this lands.
	"""
	if after is None:
		return False
	if (_get(after, ITEM_LINK_FIELD) or "").strip():
		return False
	if before is None:
		return True

	for fieldname in MATERIAL_SPEC_FIELDS:
		if _get(before, fieldname) != _get(after, fieldname):
			return True

	return False


def _name_tokens(value):
	"""Discriminating lowercase word/number tokens from a name."""
	if not value:
		return set()
	cleaned = "".join(c if c.isalnum() else " " for c in str(value).lower())
	return {t for t in cleaned.split() if t not in _STOP_WORDS}


def score_item_candidate(spec, item, customer_item_history=None):
	"""Rate one Item as the specification's likely subject.

	Product type is a gate, not a score: an Item controlled by a different kind
	of specification is not a weak candidate, it is not a candidate. Above that
	gate, actually having sold the Item to this customer outranks any amount of
	name similarity, because a name match is a coincidence and an invoice is
	evidence.
	"""
	item_code = _get(item, "item_code")
	spec_type = _get(spec, "product_type")
	item_type = _get(item, "cps_product_type")

	if spec_type and item_type and spec_type != item_type:
		return ItemCandidate(
			item_code,
			CONFIDENCE_NONE,
			["Item is controlled as {0}, not product type {1}".format(item_type, spec_type)],
		)

	reasons = ["Item group {0} matches product type {1}".format(
		_get(item, "item_group"), spec_type
	)]

	if item_code in (customer_item_history or set()):
		reasons.append("Customer has previously transacted this Item")
		return ItemCandidate(item_code, CONFIDENCE_HIGH, reasons)

	# Two shared tokens, not one: nearly every Computer Paper record mentions a
	# sheet size, so a lone "a4" in common is noise rather than a resemblance.
	shared = _name_tokens(_get(spec, "specification_name")) & _name_tokens(_get(item, "item_name"))
	if len(shared) >= 2:
		reasons.append("Specification and item names share: {0}".format(
			", ".join(sorted(shared))
		))
		return ItemCandidate(item_code, CONFIDENCE_MEDIUM, reasons)

	reasons.append("No transaction history and no distinguishing name overlap")
	return ItemCandidate(item_code, CONFIDENCE_LOW, reasons)


def resolve_item_link(spec, items, customer_item_history=None):
	"""Decide whether an unlinked specification can be mapped without a human.

	Auto-mapping happens only when exactly one Item reaches high confidence and
	nothing else comes close - a *provably* unambiguous mapping. Everything else
	is reported with its candidates and reasons for someone to decide, because a
	plausible guess here is indistinguishable from a correct one until it has
	already mispriced an order.
	"""
	if _get(spec, ITEM_LINK_FIELD):
		return ItemLinkDecision(MATCH_ALREADY_LINKED, None, [])

	scored = [score_item_candidate(spec, item, customer_item_history) for item in items or []]
	candidates = sorted(
		(c for c in scored if c.confidence != CONFIDENCE_NONE),
		key=lambda c: (-_CONFIDENCE_RANK[c.confidence], c.item_code or ""),
	)

	if not candidates:
		return ItemLinkDecision(MATCH_NONE, None, [])

	high = [c for c in candidates if c.confidence == CONFIDENCE_HIGH]
	contenders = [c for c in candidates if c.confidence in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM)]
	if len(high) == 1 and len(contenders) == 1:
		# One Item this customer actually buys, and nothing else that even
		# resembles the specification by name. That is the only shape safe to
		# map unattended; a second contender of any strength goes to a human.
		return ItemLinkDecision(MATCH_EXACT_SOLE, high[0].item_code, candidates)

	return ItemLinkDecision(MATCH_AMBIGUOUS, None, candidates)


def summarise_readiness(decisions):
	"""Aggregate link decisions into a go/no-go for strict enforcement.

	``ready_to_enforce`` is the gate on turning Sales Order Item validation
	strict: while any specification is still unresolved, enforcing would block
	real orders for a data problem the user cannot fix from the order screen.
	"""
	summary = {
		"total": 0,
		MATCH_ALREADY_LINKED: 0,
		MATCH_EXACT_SOLE: 0,
		MATCH_AMBIGUOUS: 0,
		MATCH_NONE: 0,
	}
	for decision in decisions or []:
		summary["total"] += 1
		summary[decision.match] += 1

	summary["unresolved"] = summary[MATCH_AMBIGUOUS] + summary[MATCH_NONE]
	summary["ready_to_enforce"] = summary["unresolved"] == 0
	return summary


def build_spec_snapshot(spec, colour_of_parts, spot_colours, taken_at):
	"""Build the immutable technical snapshot payload (design §8.2).

	Keys are CPS fieldnames verbatim so the mapping onto the Job Card is an
	identity, and values are recorded as they were — a snapshot must survive a
	Select option being renamed later.
	"""
	scalar_fields = (
		"product_type",
		"specification_name",
		"customer",
		"job_size",
		"pay_slip_size",
		"number_of_parts",
		"numbering_required",
		"standard_packing",
		"standard_weight_per_carton",
		"ink_type",
		"uses_c",
		"uses_m",
		"uses_y",
		"uses_k",
		"number_of_colours",
		"colour_notes",
	)
	part_fields = ("part_number", "paper_type", "gsm", "colour", "purpose")
	spot_fields = (
		"pantone_code",
		"pantone_name",
		"hex_preview",
		"cmyk_c",
		"cmyk_m",
		"cmyk_y",
		"cmyk_k",
		"notes",
	)

	snapshot = {
		"_snapshot_version": 1,
		"_cps": _get(spec, "name"),
		"_cps_modified": str(_get(spec, "modified") or ""),
		"_taken_at": str(taken_at),
	}
	for fieldname in scalar_fields:
		snapshot[fieldname] = _get(spec, fieldname)

	snapshot["colour_of_parts"] = [
		{f: _get(row, f) for f in part_fields} for row in colour_of_parts or []
	]
	snapshot["spot_colours"] = [
		{f: _get(row, f) for f in spot_fields} for row in spot_colours or []
	]
	return snapshot
