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
#
# "What the specification is" is product-type-specific. ``pay_slip_size`` and
# ``number_of_parts`` say what a Computer Paper record is and mean nothing on a
# Carton one; the box's dimensions, ply, style and board make-up say what a
# Carton record is and mean nothing on a Computer Paper one. Holding one flat
# list made the Carton half unenforced: a live Carton specification's box size
# could be changed without the Item link being forced, and — far worse — without
# the change counting as material anywhere else it is asked about.
SHARED_MATERIAL_SPEC_FIELDS = (
	"product_type",
	"specification_name",
	"customer",
	"job_size",
	ITEM_LINK_FIELD,
)

# The Carton geometry, style and board make-up. Every one of these changes what
# will physically be produced, so each is material in exactly the way
# ``number_of_parts`` is material to Computer Paper.
CARTON_DIMENSION_FIELDS = (
	"ctn_length_mm",
	"ctn_width_mm",
	"ctn_height_mm",
)

CARTON_STYLE_FIELDS = (
	"ply",
	"flute_type",
	"printing_or_plain",
	"joint_type",
	# The carton *style* (Tray / Die Cut / n-Flap RSC). Note the name: on the
	# specification ``product_type`` is the kind of specification and
	# ``product_type_carton`` is the style. On Job Card Carton the style is
	# called ``product_type``. The rename belongs in the snapshot -> Job Card
	# mapping and nowhere else; see :func:`build_spec_snapshot`.
	"product_type_carton",
	"idod",
)

CARTON_MATERIAL_LAYER_FIELDS = (
	"1_ply_top_layer_gsm",
	"1_ply_top_layer_material",
	"2_ply_fluting_gsm",
	"2_ply_top_layer_material",
	"3_ply_bottom_gsm",
	"3_ply_top_layer_material",
	"4_ply_fluting_gsm",
	"4_ply_top_layer_material",
	"5_ply_fluting_gsm",
	"5_ply_top_layer_material",
)

CARTON_MATERIAL_SPEC_FIELDS = (
	CARTON_DIMENSION_FIELDS + CARTON_STYLE_FIELDS + CARTON_MATERIAL_LAYER_FIELDS
)

COMPUTER_PAPER_MATERIAL_SPEC_FIELDS = ("pay_slip_size", "number_of_parts")

# The label's own geometry. ``gap_between`` and ``side_trim`` sit here rather
# than with the tooling because they are what the web is *cut* to: change either
# and the same die produces a different label across the same reel.
LABEL_DIMENSION_FIELDS = (
	"label_length",
	"label_width",
	"gap_between",
	"side_trim",
)

# What the job is physically made *on*. ``dies`` is carried as the Dies record's
# name and nothing more — the die's own geometry is not dereferenced anywhere in
# this module (discovery §6.2). A die can be reground, retired or renumbered
# after an order is placed, and a specification that silently followed it would
# be a different specification without anybody editing it.
LABEL_TOOLING_FIELDS = (
	"dies",
	"cylinder_teeth",
	"plate_up",
	"plate_round",
	"packing_up",
)

# What it is printed on.
LABEL_SUBSTRATE_FIELDS = ("material_type",)

# ``packing_pieces`` is deliberately absent: it says how many labels go in a
# pack, which is the same kind of statement as ``standard_packing`` — and
# ``standard_packing`` has never been material for any product type. It is still
# *frozen* (see :data:`LABEL_SNAPSHOT_SCALARS`); freezing and materiality are
# different questions and this is the one case where they diverge.
LABEL_MATERIAL_SPEC_FIELDS = (
	LABEL_DIMENSION_FIELDS + LABEL_TOOLING_FIELDS + LABEL_SUBSTRATE_FIELDS
)

PRODUCT_TYPE_MATERIAL_SPEC_FIELDS = {
	"Computer Paper": COMPUTER_PAPER_MATERIAL_SPEC_FIELDS,
	"Carton": CARTON_MATERIAL_SPEC_FIELDS,
	"Label": LABEL_MATERIAL_SPEC_FIELDS,
}

# Kept as a module constant, and kept identical to what it has always held, so
# nothing that imports it changes meaning. New code should call
# :func:`material_spec_fields`.
MATERIAL_SPEC_FIELDS = (
	"product_type",
	"specification_name",
	"customer",
	"job_size",
	"pay_slip_size",
	"number_of_parts",
	ITEM_LINK_FIELD,
)


def material_spec_fields(product_type=None):
	"""Fields whose change makes this save a material change.

	The shared set plus whatever the product type adds. An unrecognised or blank
	product type gets the shared set only — a record of a kind this module does
	not know about must still have its name, customer, job size and link
	watched, and inventing fields for it would compare columns that do not
	exist.
	"""
	extra = PRODUCT_TYPE_MATERIAL_SPEC_FIELDS.get(normalise_product_type(product_type) or "", ())
	return SHARED_MATERIAL_SPEC_FIELDS + tuple(
		f for f in extra if f not in SHARED_MATERIAL_SPEC_FIELDS
	)

# --- Item-level control mode (design §4.2, iteration 2) ---------------------
#
# Item Group inheritance answers "is this whole family controlled", which is the
# right default and wrong for the exceptions: one sample item inside a
# controlled group, or one bespoke item in a group nobody wants to control
# wholesale. So an Item may state its own answer, and an explicit answer wins
# over whatever the tree says.
#
# ``Item.custom_requires_cps`` stays read-only and derived — it is the indexed
# denormalisation Sales Order validation reads per line, never an input.
CONTROL_MODE_FIELD = "custom_cps_control_mode"

# Which kind of specification a controlled Item needs. The same field name and
# the same option list as on Item Group, because it answers the same question at
# a more specific altitude.
PRODUCT_TYPE_FIELD = "custom_cps_product_type"

# The one definition of the valid product types. Item Group, Item and the
# Customer Product Specification's own ``product_type`` must agree on this list,
# or a specification could be of a kind no Item can ever ask for.
CPS_PRODUCT_TYPES = (
	"Computer Paper",
	"Carton",
	"Label",
	"Exercise Books",
	"ETR (Reel to Reel Printing)",
)

CONTROL_MODE_INHERIT = "Inherit from Item Group"
CONTROL_MODE_REQUIRE = "Require CPS"
CONTROL_MODE_EXEMPT = "Exempt from CPS"

CONTROL_MODES = (CONTROL_MODE_INHERIT, CONTROL_MODE_REQUIRE, CONTROL_MODE_EXEMPT)

# Blank is Inherit. An existing row has no value for a field that did not exist
# when it was written, and "unset" must mean "behave exactly as before".
CONTROL_MODE_DEFAULT = CONTROL_MODE_INHERIT


def normalise_control_mode(value):
	"""Coerce a stored control mode to one of :data:`CONTROL_MODES`.

	Anything unrecognised — blank, ``None``, or a value left behind by a renamed
	Select option — falls back to Inherit rather than to a control decision
	nobody configured.
	"""
	value = (value or "").strip()
	return value if value in CONTROL_MODES else CONTROL_MODE_DEFAULT


def item_requires_cps(control_mode, controlling_group):
	"""Whether an Item is specification-controlled (the precedence rule).

	Explicit beats inherited, in both directions:

	* ``Require CPS`` controls the Item even when no ancestor group does.
	* ``Exempt from CPS`` releases the Item even when an ancestor group does.
	* ``Inherit from Item Group`` (and blank) defers to the nested-set walk.

	``controlling_group`` is the nearest ancestor group that turns control on,
	or None — the return value of ``so_spec_control.item_group_requires_cps``.
	"""
	mode = normalise_control_mode(control_mode)
	if mode == CONTROL_MODE_REQUIRE:
		return True
	if mode == CONTROL_MODE_EXEMPT:
		return False
	return bool(controlling_group)


def normalise_product_type(value):
	"""A stored product type, trimmed, or None when there is none.

	Deliberately *not* filtered against :data:`CPS_PRODUCT_TYPES`. An
	unrecognised value — a Select option renamed underneath stored data, a Data
	Import typo — must keep blocking every specification it does not match rather
	than quietly disabling the check; :func:`item_config_error` is what refuses
	to let such a value be saved in the first place.
	"""
	value = (value or "").strip()
	return value or None


def expected_product_type(control_mode, item_product_type, controlling_group):
	"""Which kind of specification this Item's order lines need, or None.

	Explicit beats inherited here for the same reason it does in
	:func:`item_requires_cps`: the Item is the more specific statement. So the
	Item's own product type answers first, and the controlling Item Group's
	answers only when the Item has nothing to say.

	Without the Item half, ``Require CPS`` on an Item outside any controlled
	group produced *no* expected type at all — and a Label specification would
	pass on a Computer Paper Item, which is precisely what control is for.

	An Exempt Item expects nothing: it is not controlled, so there is no
	specification for it to need.
	"""
	if normalise_control_mode(control_mode) == CONTROL_MODE_EXEMPT:
		return None

	explicit = normalise_product_type(item_product_type)
	if explicit:
		return explicit

	if controlling_group:
		return normalise_product_type(_get(controlling_group, PRODUCT_TYPE_FIELD))
	return None


# Why an Item's CPS configuration cannot be saved. Same untranslated-template
# shape as the reasons below, for the same reason: this module stays Frappe-free.
ConfigError = namedtuple("ConfigError", ("code", "template", "args"))

CONFIG_PRODUCT_TYPE_REQUIRED = "product-type-required"
CONFIG_PRODUCT_TYPE_UNKNOWN = "product-type-unknown"


def item_config_error(control_mode, item_product_type):
	"""Why an Item's CPS control configuration is incomplete, or None.

	``Require CPS`` is the only mode that has to name a product type. Inherit
	takes the controlling group's, and Exempt has no lines to check — so neither
	is an incomplete configuration, and neither becomes one by being left blank.

	A value outside :data:`CPS_PRODUCT_TYPES` is reported before a missing one:
	when someone has typed something, naming what they typed is more useful than
	telling them they typed nothing.
	"""
	mode = normalise_control_mode(control_mode)
	value = normalise_product_type(item_product_type)

	if value and value not in CPS_PRODUCT_TYPES:
		return ConfigError(
			CONFIG_PRODUCT_TYPE_UNKNOWN,
			"{0} is not a CPS Product Type. Choose one of: {1}.",
			(value, ", ".join(CPS_PRODUCT_TYPES)),
		)

	if mode == CONTROL_MODE_REQUIRE and not value:
		return ConfigError(
			CONFIG_PRODUCT_TYPE_REQUIRED,
			"Select a CPS Product Type - an Item cannot require a specification without naming which kind. Choose one of: {0}.",
			(", ".join(CPS_PRODUCT_TYPES),),
		)

	return None


# Why an Item ended up controlled or not. Carried as an untranslated template
# plus its arguments, for the same reason :class:`SpecBlock` is: this module
# stays Frappe-free, and the caller does ``_(source.template).format(*args)``.
ControlSource = namedtuple("ControlSource", ("code", "template", "args"))

SOURCE_EXPLICIT_REQUIRE = "explicit-require"
SOURCE_EXPLICIT_EXEMPT = "explicit-exempt"
SOURCE_INHERITED = "inherited"
SOURCE_UNCONTROLLED = "uncontrolled"


def item_control_source(control_mode, controlling_group):
	"""Why an Item is (or is not) specification-controlled.

	The derived flag is read-only, so the only way a user can tell why it holds
	the value it does is to be told. Shown on the Item form and available to the
	migration report.
	"""
	mode = normalise_control_mode(control_mode)
	group = _get(controlling_group, "name") if controlling_group else None

	if mode == CONTROL_MODE_REQUIRE:
		return ControlSource(
			SOURCE_EXPLICIT_REQUIRE,
			"Required explicitly on this Item, overriding the Item Group tree.",
			(),
		)

	if mode == CONTROL_MODE_EXEMPT:
		if group:
			return ControlSource(
				SOURCE_EXPLICIT_EXEMPT,
				"Exempted explicitly on this Item, overriding Item Group {0}.",
				(group,),
			)
		return ControlSource(
			SOURCE_EXPLICIT_EXEMPT, "Exempted explicitly on this Item.", ()
		)

	if group:
		return ControlSource(SOURCE_INHERITED, "Inherited from Item Group {0}.", (group,))

	return ControlSource(
		SOURCE_UNCONTROLLED,
		"Not controlled: no ancestor Item Group requires a specification.",
		(),
	)


def item_control_source_text(control_mode, controlling_group):
	"""The same explanation as one untranslated sentence."""
	source = item_control_source(control_mode, controlling_group)
	return source.template.format(*source.args)


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


def _date(value):
	"""Compare a date by its calendar day, however it was serialised.

	``transaction_date`` comes back from the database as a ``datetime.date`` and
	off a REST payload as ``"2026-07-02"``; a card saved through Desk may carry
	either. Taking the first ten characters of the string form makes all three
	the same value, and makes a card dated a day earlier than its order a
	mismatch rather than a formatting difference.
	"""
	if value in (None, ""):
		return None
	return str(value).strip()[:10]


def _same(found, expected):
	"""Blank is blank: ``None`` and empty string are not a disagreement."""
	if found in (None, ""):
		found = None
	if expected in (None, ""):
		expected = None
	return found == expected


def jc_line_mismatches(card, order, line, qty_precision=3, customer_field="customer"):
	"""Every Job Card value that disagrees with its Sales Order and line.

	Returns a list of :class:`JCMismatch`. An empty list means the card is a
	faithful copy of the order line; anything else is a forged or stale
	document and must not be saved.

	``customer`` is checked against the *order*, not against the snapshot's own
	customer key — the order is what was sold, and the snapshot is a record of
	the specification rather than of the counterparty. ``order`` must therefore
	carry ``customer``, ``transaction_date`` and ``po_no``: a caller that reads
	fewer columns than that does not weaken the check, it inverts it, because a
	column absent from the read is indistinguishable from a blank one on the
	order and every card would be reported as disagreeing with it.

	``customer_field`` names the card's own customer link. Job Card Computer
	Paper calls it ``customer`` and Job Card Carton calls it ``customer_name``;
	renaming a field on a live submittable DocType is not worth the risk (see
	the discovery report §9.4), so the asymmetry is carried as a parameter
	rather than migrated away. The mismatch is still reported against the field
	the card actually has, so the error names something the reader can find.
	"""
	checks = [
		(customer_field, "Customer", _get(card, customer_field), _get(order, "customer")),
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
		# Both of these are copied off the *order header* by the creation path
		# and were, until this release, the only values on an order-derived card
		# that nothing checked. They are not decoration: ``order_date`` is what
		# the due-date rule is measured against and what the shop floor reads as
		# "when was this sold", and ``lpo_number`` is the customer's own
		# reference — the number the delivery note is matched on and the number
		# an invoice is queried by. A card carrying somebody else's LPO is a
		# billing dispute, so it is proved against the order like everything
		# else rather than trusted because a form made it read-only.
		(
			"order_date",
			"Order Date",
			_date(_get(card, "order_date")),
			_date(_get(order, "transaction_date")),
		),
		(
			"lpo_number",
			"LPO Number",
			_text(_get(card, "lpo_number")),
			_text(_get(order, "po_no")),
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


# --- Orderability of one specification against one line (design §7 V2-V5) ---
#
# Sales Order validation throws these; the Desk preview endpoint reports them
# without throwing. One list of reasons in one order, so a rep never sees the
# preview clear a line the submit then refuses.
#
# The message survives as an untranslated template plus its arguments rather
# than as a finished string: the caller does ``_(block.template).format(*args)``
# so the rules stay Frappe-free without losing translation.
SpecBlock = namedtuple("SpecBlock", ("code", "template", "args"))

BLOCK_MISSING = "missing"
BLOCK_CUSTOMER = "wrong-customer"
BLOCK_ITEM = "wrong-item"
BLOCK_PRODUCT_TYPE = "wrong-product-type"
BLOCK_DOCSTATUS = "not-submitted"
BLOCK_STATUS = "not-active"
BLOCK_NO_PRICE = "no-approved-price"


def spec_block_reason(spec, item_code, customer, expected_product_type=None, requested_name=None):
	"""Why ``spec`` cannot be ordered against on this line, or None.

	Checked in the same order as ``so_spec_control._load_and_validate_spec``, so
	when several things are wrong at once both paths name the same one.

	``requested_name`` is the specification the caller asked for. It is the only
	thing worth naming when ``spec`` is None — the record is missing, so there is
	nothing to read the name off, and reporting the Item instead would send the
	reader to the wrong document.
	"""
	if not spec:
		return SpecBlock(
			BLOCK_MISSING,
			"Specification {0} was not found.",
			(requested_name or item_code,),
		)

	name = _get(spec, "name")

	if _get(spec, "customer") != customer:
		return SpecBlock(
			BLOCK_CUSTOMER,
			"Specification {0} belongs to {1}, not to {2}.",
			(name, _get(spec, "customer"), customer),
		)

	if not spec_serves_item(spec, item_code):
		return SpecBlock(
			BLOCK_ITEM,
			"Specification {0} is linked to Item {1}, not to {2}.",
			(name, _get(spec, ITEM_LINK_FIELD) or "no Item", item_code),
		)

	if expected_product_type and _get(spec, "product_type") != expected_product_type:
		return SpecBlock(
			BLOCK_PRODUCT_TYPE,
			"Specification {0} is a {1} specification, but {2} needs a {3} specification.",
			(name, _get(spec, "product_type"), item_code, expected_product_type),
		)

	docstatus = _get(spec, "docstatus")
	if docstatus != 1:
		return SpecBlock(
			BLOCK_DOCSTATUS,
			"Specification {0} is {1} and cannot be ordered against. Submit it, or select its amendment.",
			(name, "still a draft" if docstatus == 0 else "cancelled"),
		)

	if _get(spec, "status") != "Active":
		return SpecBlock(
			BLOCK_STATUS,
			"Specification {0} is {1}, not Active, and cannot be ordered against.",
			(name, _get(spec, "status")),
		)

	return None


def price_block_reason(price, spec_name, on_date):
	"""Why there is no orderable price for ``spec_name`` on ``on_date``, or None.

	Draft and Rejected rows are invisible to :func:`resolve_eligible_price`, so
	"no price at all" and "a price nobody approved" report identically — from an
	order line they are the same problem.
	"""
	if price is not None and _get(price, "rate") not in (None, ""):
		return None
	return SpecBlock(
		BLOCK_NO_PRICE,
		"No approved price for {0} effective {1}. Add a CPS Price row and have it approved.",
		(spec_name, on_date),
	)


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

	return bool(material_spec_changes(before, after))


def material_spec_changes(before, after):
	"""Material fields that differ between two versions of a specification.

	The union of both versions' product types is watched, not just the new
	one's: retyping a Carton record as Computer Paper is itself material, and
	the fields it is abandoning have to be compared before they stop counting.
	"""
	if before is None or after is None:
		return []

	fields = list(material_spec_fields(_get(after, "product_type")))
	for fieldname in material_spec_fields(_get(before, "product_type")):
		if fieldname not in fields:
			fields.append(fieldname)

	return [f for f in fields if _get(before, f) != _get(after, f)]


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


# --- The frozen technical snapshot (design §8.2) ----------------------------
#
# Version 2 adds the Carton half; version 3 adds the Label half. Each is a
# *widening* only: every key version 1 wrote is still written, for every product
# type, whatever that product type is.
#
# That costs a handful of blank keys on a Carton snapshot and buys the one thing
# that matters — no reader of an existing snapshot can break. A Carton snapshot
# that dropped ``pay_slip_size`` because Cartons have no pay slips would raise
# KeyError in any consumer that indexes rather than ``.get()``s, and those
# consumers live in another repository and deploy on their own schedule.
# Additive is the only kind of change that is safe across that boundary.
#
# Version 3 exists so that a Label line frozen by the *previous* release —
# carrying the version-1 scalars and none of the label geometry — is
# distinguishable from a complete one. Without it, a Label job card raised from
# such a line would be refused with a page of "expected blank" mismatches about
# its die, its web and its material rather than with the one sentence that is
# actually true: the order was frozen before Label specifications were captured
# in full. See :data:`PRODUCT_TYPE_MIN_SNAPSHOT_VERSION`.
#
# This is the newest version this code *knows*. It is deliberately not what
# every snapshot is stamped with — see :data:`SNAPSHOT_BASE_WRITE_VERSION` and
# :func:`snapshot_write_version` for why a Computer Paper or Carton line still
# freezes at 2.
SNAPSHOT_VERSION = 3

# Snapshots of an older version stay readable: a job card raised today against
# an order submitted last month must still work. Nothing is *rewritten* — a
# snapshot is a record of what was known then, and upgrading one in place would
# be inventing history.
SUPPORTED_SNAPSHOT_VERSIONS = (1, 2, 3)

# The version a snapshot is *stamped* with when nothing about its product type
# demands a newer one — which is to say, the version this app wrote before Label
# existed.
#
# A snapshot's version number is not only ours to read. It crosses a repository
# boundary: the Compass front end reads these lines and deploys on its own
# schedule, and a release of it that predates version 3 treats an unknown
# version as unreadable rather than as a widening it can ignore. Stamping every
# product type with the newest number this app knows would therefore make a
# Computer Paper or Carton line submitted today unreadable to a Compass that
# has not shipped yet — for a change that alters not one byte of its payload,
# because versions 2 and 3 are identical for both of those types.
#
# So the number written is the oldest one that still tells the whole truth about
# the record: 2 for Computer Paper and Carton, exactly as before this release,
# and 3 for Label, which is the first version that describes a label at all. See
# :func:`snapshot_write_version`.
SNAPSHOT_BASE_WRITE_VERSION = 2

# Exactly what version 1 froze, in its original order. The compatibility floor:
# every snapshot contains at least these keys.
SNAPSHOT_V1_SCALARS = (
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

# Everything on the specification that says what a *box* is. Version 1 froze not
# one of them, so a Carton order captured the customer, the name, the job size,
# the colour block — and nothing at all about the carton.
CARTON_SNAPSHOT_SCALARS = (
	"ply",
	"flute_type",
	"ctn_length_mm",
	"ctn_width_mm",
	"ctn_height_mm",
	"printing_or_plain",
	"joint_type",
	# The carton *style*. Kept under its CPS fieldname, deliberately: the
	# snapshot's ``product_type`` is the routing key that decides which kind of
	# Job Card a line becomes, and writing the style into it would send Carton
	# lines to the wrong card type. The rename to the Job Card's own
	# ``product_type`` happens once, in :data:`CARTON_SNAPSHOT_JC_MAP`.
	"product_type_carton",
	"idod",
	"special_instructions_carton",
	"1_ply_top_layer_gsm",
	"1_ply_top_layer_material",
	"2_ply_fluting_gsm",
	"2_ply_top_layer_material",
	"3_ply_bottom_gsm",
	"3_ply_top_layer_material",
	"4_ply_fluting_gsm",
	"4_ply_top_layer_material",
	"5_ply_fluting_gsm",
	"5_ply_top_layer_material",
)

# Computer Paper's own fields were already inside the version-1 set, so it adds
# nothing here. Named anyway, so "which fields does this product type freeze"
# has one answer per type rather than one answer and one silence.
COMPUTER_PAPER_SNAPSHOT_SCALARS = ("pay_slip_size", "number_of_parts")

# Everything on the specification that says what a *label* is. Version 2 froze
# not one of them, so a Label order captured the customer, the name, the job
# size and the colour block — and nothing at all about the label.
#
# ``dies`` freezes the Dies record's *name*. That is the whole of the intent:
# the name is the shop-floor instruction ("run die D-114") and it is stable,
# whereas the die's own dimensions are live master data that can be corrected
# after the order is sold. The label's geometry is frozen here from the
# specification's own fields, which is why nothing needs to read the Dies record
# at snapshot time, at job card time, or at comparison time.
LABEL_SNAPSHOT_SCALARS = (
	"dies",
	"label_length",
	"label_width",
	"material_type",
	"cylinder_teeth",
	"plate_up",
	"plate_round",
	"packing_up",
	"packing_pieces",
	"gap_between",
	"side_trim",
)

PRODUCT_TYPE_SNAPSHOT_SCALARS = {
	"Computer Paper": COMPUTER_PAPER_SNAPSHOT_SCALARS,
	"Carton": CARTON_SNAPSHOT_SCALARS,
	"Label": LABEL_SNAPSHOT_SCALARS,
}

# The oldest snapshot version that can still describe this product type in full.
#
# A product type absent from this table has no floor: Computer Paper has been
# fully described since version 1 and Carton since version 2, and imposing a
# floor on either would retroactively refuse orders that are complete.
#
# Label appears because version 3 is the first version that freezes a label's
# geometry, tooling and material. A version-2 Label snapshot is readable — it is
# still one of ours, and every key it holds is still trusted — but it cannot
# support a Label job card, and saying so once is better than reporting eleven
# blank fields as eleven disagreements.
PRODUCT_TYPE_MIN_SNAPSHOT_VERSION = {
	"Label": 3,
}

SNAPSHOT_PART_FIELDS = ("part_number", "paper_type", "gsm", "colour", "purpose")
SNAPSHOT_SPOT_FIELDS = (
	"pantone_code",
	"pantone_name",
	"hex_preview",
	"cmyk_c",
	"cmyk_m",
	"cmyk_y",
	"cmyk_k",
	"notes",
)


def snapshot_scalar_fields(product_type=None):
	"""CPS fieldnames frozen onto the order line for this kind of record.

	The version-1 set plus whatever the product type adds, in that order and
	without duplicates. A product type this module does not know about gets the
	version-1 set: freezing fields that do not exist on it would record a column
	of ``None`` and imply knowledge nobody has.
	"""
	fields = list(SNAPSHOT_V1_SCALARS)
	extra = PRODUCT_TYPE_SNAPSHOT_SCALARS.get(normalise_product_type(product_type) or "", ())
	fields += [f for f in extra if f not in fields]
	return tuple(fields)


def snapshot_version(snapshot):
	"""The version a snapshot was written at, or None if it does not say.

	A snapshot with no ``_snapshot_version`` is not corrupt — it is simply not
	one of ours, and is reported as such rather than assumed to be version 1.
	"""
	if not isinstance(snapshot, dict):
		return None
	try:
		return int(snapshot.get("_snapshot_version"))
	except (TypeError, ValueError):
		return None


def snapshot_version_supported(snapshot):
	"""Whether this code knows how to read that snapshot.

	Forward-looking rather than defensive: a site rolled back to this release
	after a later one wrote version 4 snapshots must refuse to card those lines
	rather than read half of one and call it a job.
	"""
	return snapshot_version(snapshot) in SUPPORTED_SNAPSHOT_VERSIONS


def min_snapshot_version(product_type=None):
	"""The oldest snapshot version that describes ``product_type`` in full.

	``None`` when the product type has no floor — which is the answer for every
	type that has been fully frozen since version 1.
	"""
	return PRODUCT_TYPE_MIN_SNAPSHOT_VERSION.get(normalise_product_type(product_type) or "")


def snapshot_write_version(product_type=None):
	"""The version to stamp on a snapshot being frozen for ``product_type``.

	Derived from the floor rather than tabulated beside it, deliberately: a
	second table saying "Label writes 3" next to one already saying "Label needs
	at least 3" is the same fact written twice, and the failure mode of the two
	disagreeing is a Label order that freezes a snapshot its own job card then
	refuses. There is one fact — the oldest version that describes this product
	type in full — and the write version is that, floored at
	:data:`SNAPSHOT_BASE_WRITE_VERSION` so no product type is stamped older than
	the number this app was already writing.

	Computer Paper and Carton therefore keep writing 2, unchanged by the Label
	release; Label writes 3; a product type this module does not know about
	writes 2, which is the honest answer for a record whose extra fields nothing
	here freezes.
	"""
	return max(SNAPSHOT_BASE_WRITE_VERSION, min_snapshot_version(product_type) or 0)


def snapshot_describes_product_type(snapshot, product_type=None):
	"""Whether this snapshot is new enough to describe ``product_type`` in full.

	Separate from :func:`snapshot_version_supported`, and deliberately so. That
	function answers "can this code read the file at all"; this one answers "does
	the file contain the fields this kind of job card is proved against". A
	version-2 Label snapshot is readable and truthful about everything it holds —
	it simply predates the label geometry, and a job card cannot be proved
	against fields the order never froze.
	"""
	minimum = min_snapshot_version(product_type)
	if not minimum:
		return True
	version = snapshot_version(snapshot)
	return version is not None and version >= minimum


# --- Snapshot -> Job Card, for Carton ---------------------------------------
#
# Three-tuples of (snapshot key, Job Card Carton fieldname, human label). The
# same table does two jobs, which is the point: it says what an order-derived
# card must be *populated* with, and it is what that card is later *proved*
# against. One table cannot drift from itself.
CARTON_SNAPSHOT_JC_MAP = (
	("specification_name", "specification_name", "Specification Name"),
	("job_size", "job_size", "Job Size"),
	("numbering_required", "numbering_required", "Numbering Required"),
	("standard_packing", "packing", "Packing"),
	("standard_weight_per_carton", "weight_per_carton", "Weight Per Carton"),
	("ink_type", "ink_type", "Ink Type"),
	("uses_c", "uses_c", "Cyan"),
	("uses_m", "uses_m", "Magenta"),
	("uses_y", "uses_y", "Yellow"),
	("uses_k", "uses_k", "Black"),
	("number_of_colours", "number_of_colours", "Number of Colours"),
	("colour_notes", "colour_notes", "Colour Notes"),
	("ply", "ply", "Ply"),
	("flute_type", "flute_type", "Flute Type"),
	("ctn_length_mm", "ctn_length_mm", "Carton Length (mm)"),
	("ctn_width_mm", "ctn_width_mm", "Carton Width (mm)"),
	("ctn_height_mm", "ctn_height_mm", "Carton Height (mm)"),
	("printing_or_plain", "printing_or_plain", "Printing Or Plain"),
	("joint_type", "joint_type", "Joint Type"),
	# The one rename, and the only place it exists.
	("product_type_carton", "product_type", "Carton Style"),
	("idod", "idod", "ID/OD"),
	("special_instructions_carton", "special_instructions", "Special Instructions"),
	("1_ply_top_layer_gsm", "1_ply_top_layer_gsm", "1 Ply Top Layer"),
	("1_ply_top_layer_material", "1_ply_top_layer_material", "1 Ply Top Layer Material"),
	("2_ply_fluting_gsm", "2_ply_fluting_gsm", "2 Ply Fluting"),
	("2_ply_top_layer_material", "2_ply_top_layer_material", "2 Ply Material"),
	("3_ply_bottom_gsm", "3_ply_bottom_gsm", "3 Ply Bottom"),
	("3_ply_top_layer_material", "3_ply_top_layer_material", "3 Ply Material"),
	("4_ply_fluting_gsm", "4_ply_fluting_gsm", "4 Ply Fluting"),
	("4_ply_top_layer_material", "4_ply_top_layer_material", "4 Ply Material"),
	("5_ply_fluting_gsm", "5_ply_fluting_gsm", "5 Ply Fluting"),
	("5_ply_top_layer_material", "5_ply_top_layer_material", "5 Ply Material"),
)

# --- Snapshot -> Job Card, for Label ----------------------------------------
#
# Same three-tuple shape and same double duty as the Carton map: it says what an
# order-derived Job Card Label must be populated with, and it is what that card
# is later proved against.
#
# Every target below exists on Job Card Label today — the card has carried the
# full label block since it shipped, because its ``populate_specification_snapshot``
# has always copied these values live off the specification. That is what makes
# this a mapping change and not a schema change: the order-derived path writes
# the same fields from a frozen source instead of a live one.
#
# Two mappings are worth reading twice:
#
# ``standard_packing`` -> ``standard_packing``
#     An identity, unlike Carton, which calls the same value ``packing``. The
#     temptation to "harmonise" the two is exactly the mistake: renaming a field
#     on a live submittable DocType with 56 rows, print formats and a traveller
#     behind it buys nothing but symmetry.
#
# ``standard_weight_per_carton`` -> ``weight_per_carton``
#     The one rename, and it is the specification's name that is the odd one:
#     labels are packed in cartons too, and the card has called it
#     ``weight_per_carton`` since it shipped.
LABEL_SNAPSHOT_JC_MAP = (
	("specification_name", "specification_name", "Specification Name"),
	("job_size", "job_size", "Job Size"),
	("numbering_required", "numbering_required", "Numbering Required"),
	("standard_packing", "standard_packing", "Standard Packing"),
	("standard_weight_per_carton", "weight_per_carton", "Weight Per Carton"),
	("ink_type", "ink_type", "Ink Type"),
	("uses_c", "uses_c", "Cyan"),
	("uses_m", "uses_m", "Magenta"),
	("uses_y", "uses_y", "Yellow"),
	("uses_k", "uses_k", "Black"),
	("number_of_colours", "number_of_colours", "Number of Colours"),
	("colour_notes", "colour_notes", "Colour Notes"),
	# The Dies record's name, carried verbatim and never dereferenced.
	("dies", "dies", "Dies"),
	("label_length", "label_length", "Label Length (mm)"),
	("label_width", "label_width", "Label Width (mm)"),
	("material_type", "material_type", "Material Type"),
	# The specification holds these four as ``Data`` and the card as numbers.
	# ``_same_spec_value`` compares anything numeric-looking as a number, so
	# "24" frozen against 24.0 on the card is the same value and not a
	# disagreement. Every one of the 192 live Label specifications was audited
	# as numeric-compatible before this mapping was written (discovery §4.3).
	("cylinder_teeth", "cylinder_teeth", "Cylinder Teeth"),
	("plate_up", "plate_up", "Plate Up"),
	("plate_round", "plate_round", "Plate Round"),
	("packing_up", "packing_up", "Packing Up"),
	("packing_pieces", "packing_pieces", "Packing Pieces"),
	("gap_between", "gap_between", "Gap (between)"),
	("side_trim", "side_trim", "Side Trim (mm)"),
)

# Snapshot keys that are deliberately not carried onto a Job Card, with the
# reason each is exempt. Named explicitly so :func:`unmapped_snapshot_keys` can
# be an equality assertion rather than a judgement call — a key added to the
# snapshot later and forgotten here fails a test instead of going unnoticed.
SNAPSHOT_KEYS_NOT_ON_JOB_CARD = {
	# The routing key. It decides which DocType the card is, and is checked as
	# such; writing it onto the card would collide with the Carton style field.
	"product_type": "routing key, checked not copied",
	# The counterparty comes from the order, not from the specification.
	"customer": "taken from the Sales Order",
	# Version-1 compatibility keys. Neither a Carton nor a Label specification
	# has pay slips or parts, so these are always blank on their snapshots.
	"pay_slip_size": "Computer Paper only",
	"number_of_parts": "Computer Paper only",
}


def unmapped_snapshot_keys(product_type, field_map):
	"""Frozen fields this map neither carries onto the card nor excuses.

	The guarantee behind "the card is proved against everything the order
	froze". An empty list is the only acceptable answer, and it is asserted in
	the tests rather than hoped for.
	"""
	mapped = {snapshot_key for snapshot_key, _card_field, _label in field_map or ()}
	return [
		fieldname
		for fieldname in snapshot_scalar_fields(product_type)
		if fieldname not in mapped and fieldname not in SNAPSHOT_KEYS_NOT_ON_JOB_CARD
	]


# --- Snapshot child tables -> Job Card --------------------------------------
#
# The scalar map above proves what a box *is*. This proves what it is *printed
# in*: the spot colours the order froze, row for row.
#
# Carton and Label both carry a snapshot table, and both carry the same one: a
# Spot Colours grid and no Colour of Parts grid — a box has no parts and neither
# does a label — which is why one entry appears in each map below rather than
# the pair Computer Paper's snapshot carries.
#
# Each row field is named with its label rather than derived from the fieldname,
# because a derived label reads "Cmyk C" and the operator is looking at a column
# headed "CMYK C". The field half is asserted equal to
# :data:`SNAPSHOT_SPOT_FIELDS` in the tests, so a field added to the snapshot and
# forgotten here fails rather than goes unchecked.
SPOT_COLOUR_ROW_FIELDS = (
	("pantone_code", "Pantone Code"),
	("pantone_name", "Pantone Name"),
	("hex_preview", "Hex Preview"),
	("cmyk_c", "CMYK C"),
	("cmyk_m", "CMYK M"),
	("cmyk_y", "CMYK Y"),
	("cmyk_k", "CMYK K"),
	("notes", "Notes"),
)

# Four-tuples of (snapshot key, Job Card table fieldname, row label, row fields).
CARTON_SNAPSHOT_JC_TABLE_MAP = (
	("spot_colours", "spot_colours", "Spot Colour", SPOT_COLOUR_ROW_FIELDS),
)

# Label carries the same one grid and for the same reason. A label has no parts,
# so ``colour_of_parts`` is absent here exactly as it is for Carton; the pair
# only ever appears on Computer Paper.
#
# The grid matters more on a label than on a box. A Pantone is frequently the
# entire brand asset being reproduced, the card's table is ``read_only`` on the
# form — which stops a Desk user and stops nothing else — and a REST POST or a
# Data Import writes read-only child tables perfectly happily.
LABEL_SNAPSHOT_JC_TABLE_MAP = (
	("spot_colours", "spot_colours", "Spot Colour", SPOT_COLOUR_ROW_FIELDS),
)


def _ordered_rows(value):
	"""A child table read as an ordered list, however it arrived.

	Order is part of the value here, not an incidental detail of storage: two
	spot colours swapped between rows one and two is a different print order and
	a different plate sequence, and comparing them as an unordered bag would call
	that identical.

	So the order is made stable on both sides before anything is compared. Card
	rows are ``Document`` children and carry ``idx``, which is their real
	position and survives a payload that lists them out of order; snapshot rows
	are plain dicts with no ``idx`` at all, and their position in the list *is*
	their order. Rows that state an ``idx`` sort by it, rows that do not keep the
	order they arrived in, and the two groups never interleave — so each side is
	sorted by the only thing it actually knows.
	"""
	rows = list(value) if isinstance(value, (list, tuple)) else []

	numbered = []
	for position, row in enumerate(rows):
		try:
			idx = float(_get(row, "idx"))
		except (TypeError, ValueError):
			idx = None
		numbered.append(((1, 0.0, position) if idx is None else (0, idx, position), row))

	numbered.sort(key=lambda item: item[0])
	return [row for _key, row in numbered]


def jc_table_mismatches(card, snapshot, table_map, precision=3):
	"""Every Job Card child-table row that disagrees with what the order froze.

	:func:`jc_snapshot_mismatches` proves the card's scalars against the
	snapshot and stops at the grid, which is exactly where a Carton's — and a
	Label's — colours live. Without this a card could name the right order, the
	right price, the right box and the right board while being printed in a
	Pantone nobody agreed — and the spot colour table being ``read_only`` on the
	form stops a Desk user and stops nothing else, since a REST POST or a Data
	Import writes read-only fields perfectly happily.

	A differing *row count* is reported on its own and the rows are not then
	compared field by field: once the tables are different lengths every row
	after the first insertion or deletion is offset, so the per-field report
	would be a page of noise about rows that are merely shifted. The count is
	the fact the reader can act on.

	Returns an empty list when there is nothing to compare — an empty map
	(Computer Paper) means this check does not apply to that card, which is what
	keeps its behaviour exactly what it was.
	"""
	if not isinstance(snapshot, dict) or not table_map:
		return []

	mismatches = []
	for snapshot_key, card_field, label, row_fields in table_map:
		expected_rows = _ordered_rows(snapshot.get(snapshot_key))
		found_rows = _ordered_rows(_get(card, card_field))

		if len(found_rows) != len(expected_rows):
			mismatches.append(
				JCMismatch(
					card_field,
					"{0} Rows".format(label),
					len(found_rows),
					len(expected_rows),
				)
			)
			continue

		for position, (found_row, expected_row) in enumerate(
			zip(found_rows, expected_rows), start=1
		):
			for row_field, row_label in row_fields:
				found = _get(found_row, row_field)
				expected = _get(expected_row, row_field)
				if not _same_spec_value(found, expected, precision):
					mismatches.append(
						JCMismatch(
							"{0}[{1}].{2}".format(card_field, position, row_field),
							"{0} row {1} {2}".format(label, position, row_label),
							found,
							expected,
						)
					)

	return mismatches


def unmapped_jc_table_targets(table_map, has_field):
	"""Mapped Job Card *table* fields that do not exist on the card.

	The table counterpart of :func:`unmapped_jc_targets`, and separate from it
	because the two maps have different shapes. A missing grid is worse than a
	missing scalar, not better: the card would be proved against a table it does
	not have, every row would read as absent, and a snapshot with colours in it
	would refuse every card forever with a message about rows rather than about
	the DocType being out of step.
	"""
	return [
		card_field
		for _snapshot_key, card_field, _label, _row_fields in table_map or ()
		if not has_field(card_field)
	]


def unmapped_jc_targets(field_map, has_field):
	"""Mapped Job Card fields that do not exist on the card.

	``has_field`` is the caller's meta lookup, kept out here so this stays
	Frappe-free. A missing target must be an error and never a silent skip: a
	card quietly missing its packing, its weight and its box style looks
	complete on screen and is not, and nobody finds out until the box is wrong.
	"""
	return [
		card_field
		for _snapshot_key, card_field, _label in field_map or ()
		if not has_field(card_field)
	]


def _looks_numeric(value):
	if isinstance(value, bool):
		return True
	if isinstance(value, (int, float)):
		return True
	if isinstance(value, str):
		try:
			float(value.strip())
		except (TypeError, ValueError):
			return False
		return True
	return False


def _same_spec_value(found, expected, precision=3):
	"""Whether two frozen-vs-card values are the same value.

	Numbers are compared as numbers, so ``250`` from an Int field and ``250.0``
	read back out of JSON are not a disagreement, and neither are a cleared
	Check and a zero. Everything else is compared as trimmed text, where blank
	and absent are the same absence — the same rule :func:`_same` applies to the
	line-level fields.
	"""
	if _looks_numeric(found) and _looks_numeric(expected):
		return round(float(found), precision) == round(float(expected), precision)
	if found in (None, "", 0) and expected in (None, "", 0):
		return True
	return _same(_text(found), _text(expected))


def jc_snapshot_mismatches(card, snapshot, field_map, precision=3):
	"""Every Job Card field that disagrees with what the order froze.

	The technical half of provenance. :func:`jc_line_mismatches` proves the
	card's identity, price and quantity against the order line; this proves the
	specification it will actually be made to against the snapshot the order
	captured. Without it a Carton card could name the right order, the right
	price and the right customer while being built to a box size nobody sold.

	Returns an empty list when there is nothing to compare — the caller has
	already refused a line with no snapshot, and an empty map (Computer Paper)
	means this check does not apply to that card.
	"""
	if not isinstance(snapshot, dict) or not field_map:
		return []

	mismatches = []
	for snapshot_key, card_field, label in field_map:
		expected = snapshot.get(snapshot_key)
		found = _get(card, card_field)
		if not _same_spec_value(found, expected, precision):
			mismatches.append(JCMismatch(card_field, label, found, expected))
	return mismatches


# --- Legacy order references (discovery §5) ---------------------------------
#
# Job Card Label reaches this release with 20 rows already naming a Sales Order
# and 7 naming a Sales Order line, written by hand long before order control
# existed. Not one of them carries a frozen snapshot, because there was nothing
# to freeze: the specification was read live at save time, which is exactly what
# the order-derived path replaces.
#
# Those rows are the whole difficulty. ``is_order_derived`` — "does this card
# name an order" — is true for all 20, so the strict path would demand a frozen
# snapshot from every one of them and 20 historical, submitted job cards would
# stop saving on the day this lands. And the obvious fixes are both wrong:
# clearing the links destroys the only record of which order a job belonged to,
# and writing a snapshot today is a lie about what was known in April.
#
# So order-derived-ness becomes three states rather than two, and the third one
# is *recorded* rather than inferred. A one-off patch stamps
# ``legacy_order_reference`` on precisely the rows that exist, name an order and
# hold no snapshot; from that moment the flag is an output of validation and
# never an input, on the same terms as the snapshot itself (V12). Nothing an API
# caller posts into it is believed. A new card cannot become legacy, because
# there is no evidence a new card could produce — except one, and it is proved
# rather than trusted: an amendment of a card that is *itself* stamped legacy,
# cancelled, and naming the same order and the same line.
#
# The result is that "partial" and "legacy" stop being the same shape. A card
# posted today with a Sales Order and no snapshot is refused, which is what
# makes the read-only fields on the form mean something. A card that has held
# those values since April keeps saving, and keeps them.

ORDER_REF_NONE = "none"
ORDER_REF_FROZEN = "frozen"
ORDER_REF_LEGACY = "legacy"

LEGACY_ORDER_REF_FIELD = "legacy_order_reference"

LEGACY_FLAG_NOT_EARNED = "legacy-flag-not-earned"
LEGACY_REF_IMMUTABLE = "legacy-ref-immutable"
LEGACY_FLAG_IMMUTABLE = "legacy-flag-immutable"


def has_order_reference(sales_order, sales_order_item):
	"""Whether a card claims to come from a Sales Order line at all.

	Either half counts. A card naming a line and no order is as much a claim on
	an order as one naming both, and the strict path is what refuses it — being
	lenient here would make the incomplete shape the way around the check.
	"""
	return bool((sales_order or "").strip() or (sales_order_item or "").strip())


def has_frozen_snapshot(spec_snapshot):
	"""Whether a card carries the order's frozen specification snapshot."""
	return bool((spec_snapshot or "").strip())


def order_reference_state(sales_order, sales_order_item, legacy_flag=False):
	"""Which of the three order-reference states a card is in.

	:data:`ORDER_REF_LEGACY` is reachable only for a card whose flag has already
	been earned — see :func:`legacy_flag_earned`. Everything else that names an
	order is :data:`ORDER_REF_FROZEN` and is proved against that order in full,
	including a card that names one and carries no snapshot: that is not a third
	kind of card, it is a frozen card missing its snapshot, and it is refused.
	"""
	if not has_order_reference(sales_order, sales_order_item):
		return ORDER_REF_NONE
	if legacy_flag:
		return ORDER_REF_LEGACY
	return ORDER_REF_FROZEN


def legacy_order_reference_qualifies(sales_order, sales_order_item, spec_snapshot):
	"""Whether a *pre-existing* row has the shape the migration stamps.

	Names an order, holds no snapshot. Used by the patch and by nothing else —
	a row that acquires this shape later has not become legacy, it has become
	wrong, and :func:`legacy_flag_earned` is what refuses to promote it.
	"""
	return has_order_reference(sales_order, sales_order_item) and not has_frozen_snapshot(
		spec_snapshot
	)


def legacy_flag_earned(sales_order, sales_order_item, spec_snapshot, amended_from_row):
	"""Whether a *new* card may carry the legacy flag, on proven evidence.

	The only new document that can be legacy is the amendment of one that
	already is. Everything is checked rather than inherited:

	* the new card still has the legacy shape — an order, no snapshot;
	* the amended-from card exists and is itself stamped legacy;
	* it is cancelled, which is the only state a card can be amended from;
	* and it names the same order and the same line, so an amendment cannot
	  repoint a legacy reference at somebody else's order on the way through.

	``amended_from_row`` is the stored row as a dict, or None. Reading it is the
	caller's job; deciding on it is this function's.
	"""
	if not legacy_order_reference_qualifies(sales_order, sales_order_item, spec_snapshot):
		return False
	if not amended_from_row:
		return False
	if not _get(amended_from_row, LEGACY_ORDER_REF_FIELD):
		return False
	if _get(amended_from_row, "docstatus") != 2:
		return False

	return _same(
		_text(_get(amended_from_row, "sales_order")), _text(sales_order)
	) and _same(
		_text(_get(amended_from_row, "sales_order_item")), _text(sales_order_item)
	)


def legacy_order_reference_errors(stored, current):
	"""Why an *existing* legacy card's save must be refused, as a list.

	Two things are immutable on a card the migration stamped, and for the same
	reason: the flag is the only record that the card predates order control,
	and the links are the only record of what it was for.

	Returns :class:`ConfigError` values, untranslated, in the order they are
	worth reporting. An empty list is the normal answer — a legacy card saving
	its production remarks touches none of this.
	"""
	if not stored or not _get(stored, LEGACY_ORDER_REF_FIELD):
		return []

	errors = []

	if not _get(current, LEGACY_ORDER_REF_FIELD):
		errors.append(
			ConfigError(
				LEGACY_FLAG_IMMUTABLE,
				"This job card predates Sales Order control and is recorded as such. The Legacy Order Reference flag cannot be cleared - it is the only record that the card was written before its order was ever frozen.",
				(),
			)
		)

	for fieldname, label in (("sales_order", "Sales Order"), ("sales_order_item", "Sales Order Line")):
		before, after = _text(_get(stored, fieldname)), _text(_get(current, fieldname))
		if not _same(before, after):
			errors.append(
				ConfigError(
					LEGACY_REF_IMMUTABLE,
					"{0} on a legacy job card cannot be changed from {1} to {2}. Raise a new job card from the order instead - repointing this one would rewrite what an already-produced job was for.",
					(label, before or "blank", after or "blank"),
				)
			)

	if has_frozen_snapshot(_get(current, "spec_snapshot")):
		errors.append(
			ConfigError(
				LEGACY_FLAG_NOT_EARNED,
				"A legacy job card cannot be given a specification snapshot. Its order was submitted before specifications were frozen, so any snapshot written onto it now would be a record of something that never happened.",
				(),
			)
		)

	return errors


# FOLLOW-UP, deliberately not done here: `artwork` and `artwork_notes` landed on
# the Computer Paper specification in v8_3 and are NOT frozen below.
#
# Adding a key to this payload is a widening and is safe on its own. Adding one
# that consumers are expected to *act* on is a contract change across a
# repository boundary — vcl-compass reads these snapshots and deploys on its own
# schedule — and it needs answers this release does not have: what an artwork
# reference frozen at order time means when the file behind it can be replaced
# afterwards, whether the Job Card should carry the URL or a copy, whether
# `jc_snapshot_mismatches` should prove a card's artwork against the order's the
# way it proves every other technical value, and what a mismatch means when the
# honest answer is "the artwork was revised". See
# docs/computer_paper_cps_capture.md §6. Until then, artwork lives on the
# specification and is read live from there.
def build_spec_snapshot(spec, colour_of_parts, spot_colours, taken_at):
	"""Build the immutable technical snapshot payload (design §8.2).

	Keys are CPS fieldnames verbatim so the mapping onto the Job Card is an
	identity, and values are recorded as they were — a snapshot must survive a
	Select option being renamed later.

	The scalar set is product-type-aware (see :func:`snapshot_scalar_fields`),
	but it is only ever *wider* than version 1 — never narrower. See
	:data:`SNAPSHOT_V1_SCALARS` for why that matters.

	So is the version stamped on it (see :func:`snapshot_write_version`): a
	Computer Paper or Carton line freezes at 2 exactly as it did before Label
	existed, and only a Label line freezes at 3.
	"""
	product_type = _get(spec, "product_type")
	snapshot = {
		"_snapshot_version": snapshot_write_version(product_type),
		"_cps": _get(spec, "name"),
		"_cps_modified": str(_get(spec, "modified") or ""),
		"_taken_at": str(taken_at),
	}
	for fieldname in snapshot_scalar_fields(product_type):
		snapshot[fieldname] = _get(spec, fieldname)

	snapshot["colour_of_parts"] = [
		{f: _get(row, f) for f in SNAPSHOT_PART_FIELDS} for row in colour_of_parts or []
	]
	snapshot["spot_colours"] = [
		{f: _get(row, f) for f in SNAPSHOT_SPOT_FIELDS} for row in spot_colours or []
	]
	return snapshot
