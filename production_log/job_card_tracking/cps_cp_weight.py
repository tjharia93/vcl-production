"""Pure weight arithmetic for the Computer Paper Customer Product Specification.

Frappe-free, on exactly the terms :mod:`cps_cp_rules`, :mod:`cps_rules` and
:mod:`cps_pricing` are: every function takes plain data (dicts, lists, numbers,
``None``) and returns plain data or an untranslated reason, so the whole
calculation can be unit tested without a bench, a site or a database. The
Frappe-bound caller is the DocType controller
``customer_product_specification.py``; the Compass mirror is
``vcl_compass.api.cps_core``, which is kept in step with this module and never
allowed to be more permissive than it.

Why this exists
---------------

A Computer Paper carton has two weights that get quoted, planned and shipped
against, and until now neither was calculated — a single free-text
``standard_weight_per_carton`` was typed in by hand and meant whatever the
person typing it meant:

* the **net product weight** of the paper in the carton, and
* the **gross packed weight** including the outer packing carton it ships in.

Both are derivable from things the specification already records — the finished
sheet size, the GSM of every ply, how many sets go in a carton, and the tare of
the carton itself — so they are derived here rather than trusted from an input a
Desk user or an API caller can set to anything.

The one thing this module refuses to pretend
--------------------------------------------

Printing adds ink, and ink has weight, but the weight of ink on a press sheet is
not something a specification knows exactly — it depends on coverage, on the ink
system and on the press. So it is **not** modelled as a fact. A Printed
specification may carry an optional *printing allowance* — a percentage uplift on
the substrate weight — and it is labelled as an allowance everywhere it appears.
A Plain specification carries no allowance at all: unprinted paper is just paper.

What is structured, and what is not
-----------------------------------

The finished width and length are their own numeric fields
(:data:`WIDTH_FIELD`, :data:`LENGTH_FIELD`) and the calculation reads *only*
those. ``job_size`` is free text ("241 x 279", "241x279mm", "9.5 x 11") and the
Item name is worse; :func:`suggest_dimensions` will parse one into an editable
suggestion for the screen to prefill, but nothing here computes a weight from it.
A suggestion the user has not confirmed into the structured fields is never a
number this module will multiply.

Units: entered in inches, calculated in millimetres
---------------------------------------------------

Computer paper is specified, quoted, ordered and talked about in **inches** —
"9.5 x 8", "9.5 x 11", "14.5 x 11". Nobody on the sales side or the shop floor
says 241.3 mm. So inches are what gets *entered* (:data:`WIDTH_IN_FIELD`,
:data:`LENGTH_IN_FIELD`) and millimetres are *derived* from them
(:func:`derived_dimensions`, ``× 25.4``), because the arithmetic needs mm² → m²
in :func:`area_m2` and a second unit in the middle of a weight calculation is a
factor-of-25.4 error waiting to happen.

The millimetre fields therefore stay exactly what they were — the one thing the
weight is computed from — and are read-only on every surface. Nothing about a
record written before inches were captured changes: :func:`effective_dimensions`
falls back to the stored millimetres when a record carries no inches, so the
legacy specifications keep the size and the weight they already had.
"""

from collections import namedtuple

# The only product type this module speaks for. A Carton and a Label are packed
# and weighed too, but a box's weight comes from its board make-up and a label's
# from its reel — different arithmetic, different inputs, a separate decision.
COMPUTER_PAPER = "Computer Paper"

PRINT_TYPE_PLAIN = "Plain"
PRINT_TYPE_PRINTED = "Printed"

# --- Structured inputs ------------------------------------------------------
#
# The finished sheet of one set, in inches. This is the entry: computer paper is
# ordered in inches and every quote, LPO and job size is written that way, so the
# number a person types is the number they were given. Never parsed from
# ``job_size`` — see :func:`suggest_dimensions` for why the free-text size is a
# suggestion and not a source.
WIDTH_IN_FIELD = "finished_width_in"
LENGTH_IN_FIELD = "finished_length_in"

# The same sheet in millimetres, derived from the inches above and read-only
# everywhere. Still the ONLY thing the weight is computed from — see
# :func:`area_m2`, which is mm² → m². Retained rather than replaced because the
# specifications written before inches were captured store real millimetres here
# and reading those as inches would make every one of their cartons 25.4× heavy.
WIDTH_FIELD = "finished_width_mm"
LENGTH_FIELD = "finished_length_mm"

# The conversion. Exact by definition — an inch *is* 25.4 mm — so this is not a
# rounded constant and the round trip in → mm → in is exact at three decimals.
MM_PER_INCH = 25.4

# How many finished sets are packed into one carton. An integer: half a set is
# not a thing that ships.
SETS_PER_CARTON_FIELD = "sets_per_carton"

# The empty outer packing carton, in kilograms. This is the whole difference
# between the net and the gross weight, so it is required for the gross to mean
# "including the carton" rather than "the same as net".
TARE_FIELD = "packing_carton_tare_kg"

# The optional printing allowance, as a percentage uplift on the substrate
# weight. Printed only, and honestly labelled as an allowance rather than an ink
# weight. Blank means zero — a Printed job may decline to estimate ink at all.
ALLOWANCE_FIELD = "print_weight_allowance_pct"

# Every structured input, and the subset that must be positive for a complete
# calculation. The allowance is deliberately absent from the required set: it is
# optional by design and defaults to zero.
#
# These are the millimetre fields, not the inch ones, because they are what the
# calculation consumes — a record is complete when a size in millimetres can be
# had, whether it was derived from inches today or stored in millimetres in April.
WEIGHT_INPUT_FIELDS = (WIDTH_FIELD, LENGTH_FIELD, SETS_PER_CARTON_FIELD, TARE_FIELD)

# What a person can type. Wider than the required set: an inch entry counts as
# having started on the weights even before its millimetres have been derived, so
# :func:`weight_inputs_present` sees a half-filled form as opted in.
WEIGHT_ENTRY_FIELDS = (WIDTH_IN_FIELD, LENGTH_IN_FIELD) + WEIGHT_INPUT_FIELDS

# --- Derived outputs --------------------------------------------------------
#
# Read-only on every surface. Recomputed server-side on save from the inputs
# above, so a value posted into one of these by Desk, REST or a Data Import is
# overwritten with the truth rather than trusted.
TOTAL_GSM_FIELD = "cp_total_gsm"
PER_SET_FIELD = "paper_weight_per_set_g"
NET_FIELD = "net_product_weight_per_carton_kg"
GROSS_FIELD = "gross_packed_weight_per_carton_kg"

DERIVED_FIELDS = (TOTAL_GSM_FIELD, PER_SET_FIELD, NET_FIELD, GROSS_FIELD)

# The existing field the gross weight is *also* written into. It is a v1 snapshot
# scalar (``cps_rules.SNAPSHOT_V1_SCALARS``) that already freezes onto every
# Sales Order line and already maps onto the Job Card as ``weight_per_carton``
# (both in production's ``*_SNAPSHOT_JC_MAP`` and in Compass's
# ``jobcards_core.SNAPSHOT_SCALAR_MAP``). Storing the derived gross there means
# the shipping weight reaches the order snapshot and the shop floor with no
# snapshot version bump and no mapping change — the narrowest compatible carrier
# there is. :data:`GROSS_FIELD` is the labelled, user-facing copy; this is the
# plumbing. They are set together, in one place, and cannot drift.
STANDARD_WEIGHT_FIELD = "standard_weight_per_carton"

# The GSM column on each Colour of Parts row. Its sum across the plies is the
# grammage of one complete set, which is what a set's area is multiplied by.
PART_GSM_FIELD = "gsm"
COLOUR_OF_PARTS_FIELD = "colour_of_parts"

PRINT_TYPE_FIELD = "print_type"

# Rounding. Kilograms to three decimals (a gram), grams per set to two, GSM to
# one. ``standard_weight_per_carton`` itself is a precision-2 Float, so the gross
# is rounded to that when written there and kept at three here for display.
KG_PRECISION = 3
GRAMS_PRECISION = 2
GSM_PRECISION = 1
STANDARD_WEIGHT_PRECISION = 2
# Millimetres and inches to three decimals each — a micron and a ten-thousandth of
# an inch. Both far finer than anything a guillotine can hold; the point of the
# precision is that in → mm → in comes back as the number that was typed.
MM_PRECISION = 3
INCH_PRECISION = 3


# A refusal, carried as an untranslated template plus its arguments so this
# module stays Frappe-free and the caller can do ``_(reason.template).format()``.
# The same shape as :class:`cps_cp_rules.CPSBlock`.
WeightBlock = namedtuple("WeightBlock", ("code", "template", "args"))

BLOCK_WIDTH = "weight-width"
BLOCK_LENGTH = "weight-length"
BLOCK_SETS = "weight-sets-per-carton"
BLOCK_TARE = "weight-carton-tare"
BLOCK_ALLOWANCE = "weight-allowance"
BLOCK_ALLOWANCE_ON_PLAIN = "weight-allowance-on-plain"
BLOCK_GSM = "weight-total-gsm"
BLOCK_INCOMPLETE = "weight-incomplete"


def _get(row, key):
	"""Read a key from a dict or an attribute from a Frappe document/child row."""
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def _rows(value):
	"""A child table as a plain list, however it arrived (or was omitted)."""
	if isinstance(value, (list, tuple)):
		return list(value)
	return []


def _text(value):
	"""Trimmed text, or None. Blank and absent are the same absence."""
	if value is None:
		return None
	value = str(value).strip()
	return value or None


def _num(value):
	"""A number, or None when the value is blank or not numeric.

	Distinct from ``float(value or 0)``: the difference between "nobody entered a
	width" and "the width is zero" is the whole of the completeness check, and
	collapsing a missing value to zero would hide an unfinished specification
	behind a plausible-looking zero.
	"""
	if value is None or value == "":
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def is_computer_paper(doc):
	"""Whether these rules speak for this record at all."""
	return _text(_get(doc, "product_type")) == COMPUTER_PAPER


def normalise_print_type(value):
	"""A stored print type, trimmed, or None. Not filtered against the two known
	values: an unrecognised type is handled by :mod:`cps_cp_rules`, and here it
	simply is not Printed, so it carries no allowance."""
	return _text(value)


def is_printed(doc):
	return normalise_print_type(_get(doc, PRINT_TYPE_FIELD)) == PRINT_TYPE_PRINTED


# ---------------------------------------------------------------------------
# The arithmetic — each step its own function, so each is testable alone
# ---------------------------------------------------------------------------


def mm_from_inches(value):
	"""Millimetres from an inch entry, or None.

	None for anything not a positive number, so a blank, a zero, a negative and a
	typo all mean "no size here" to the caller rather than a plausible-looking 0.0
	that would multiply out to a carton weighing nothing.

	Rounded to :data:`MM_PRECISION` — a thousandth of a millimetre is a micron,
	finer than any guillotine, and it makes in → mm → in return the number that
	was typed.
	"""
	inches = _num(value)
	if inches is None or inches <= 0:
		return None
	return round(inches * MM_PER_INCH, MM_PRECISION)


def inches_from_mm(value):
	"""Inches from a stored millimetre value, or None.

	The reverse of :func:`mm_from_inches`, used once per record: to give a
	specification written in millimetres an inch entry it can be edited in. Not
	used by the calculation — nothing here converts backwards on the way to a
	weight.
	"""
	mm = _num(value)
	if mm is None or mm <= 0:
		return None
	return round(mm / MM_PER_INCH, INCH_PRECISION)


def derived_dimensions(doc):
	"""The millimetre fields to write on save, keyed by fieldname.

	Empty when neither inch field is filled: a legacy record's stored millimetres
	are left exactly where they are rather than blanked by the conversion of
	nothing. A record that *does* carry inches has its millimetres overwritten
	from them on every save, so the two cannot drift and a REST caller cannot post
	a width in millimetres that disagrees with the inches beside it.
	"""
	derived = {}
	for inch_field, mm_field in (
		(WIDTH_IN_FIELD, WIDTH_FIELD),
		(LENGTH_IN_FIELD, LENGTH_FIELD),
	):
		mm = mm_from_inches(_get(doc, inch_field))
		if mm is not None:
			derived[mm_field] = mm
	return derived


def effective_dimensions(doc):
	"""The finished size the weight is calculated from, as ``(width_mm, length_mm)``.

	The inches when the record carries them, the stored millimetres when it does
	not. Either may be None.

	The fallback is what keeps this change invisible to the 46 submitted
	specifications: they carry millimetres and no inches, and they go on being
	measured from exactly the numbers they were submitted with. It also makes the
	arithmetic correct *before* the controller has written the derived
	millimetres — a Compass preview computes from a form that has only inches on
	it, and it must get the same answer the save will.
	"""
	width = mm_from_inches(_get(doc, WIDTH_IN_FIELD))
	if width is None:
		width = _num(_get(doc, WIDTH_FIELD))
	length = mm_from_inches(_get(doc, LENGTH_IN_FIELD))
	if length is None:
		length = _num(_get(doc, LENGTH_FIELD))
	return width, length


def total_gsm(colour_of_parts):
	"""Grammage of one complete set: the sum of every ply's GSM.

	A three-part set of 55 + 50 + 55 weighs 160 g per square metre of set, not 55.
	This is where the multi-part nature of Computer Paper enters the weight — one
	"set" is several sheets and every one of them is on the scale.

	Rows with no GSM contribute nothing rather than raising: an incomplete parts
	grid is reported by :func:`weight_block_reasons` as an incomplete weight, and
	by :mod:`cps_cp_rules` as an invalid grid, and neither is served by a
	traceback here.
	"""
	total = 0.0
	for row in _rows(colour_of_parts):
		gsm = _num(_get(row, PART_GSM_FIELD))
		if gsm and gsm > 0:
			total += gsm
	return round(total, GSM_PRECISION)


def area_m2(width_mm, length_mm):
	"""The area of one finished set, in square metres, or None.

	``width_mm * length_mm / 1_000_000`` — the ``1e6`` is mm² to m². None when
	either dimension is missing or not positive, because an area is not defined
	without both.
	"""
	width, length = _num(width_mm), _num(length_mm)
	if not width or not length or width <= 0 or length <= 0:
		return None
	return width * length / 1_000_000.0


def substrate_g_per_set(width_mm, length_mm, gsm_total):
	"""The unprinted paper weight of one set, in grams, or None.

	``area_m2 * total_gsm``. This is the Plain weight — just the paper — and the
	base the printing allowance (if any) is applied on top of.
	"""
	area = area_m2(width_mm, length_mm)
	gsm_total = _num(gsm_total)
	if area is None or not gsm_total or gsm_total <= 0:
		return None
	return area * gsm_total


def allowance_multiplier(print_type, allowance_pct):
	"""The uplift applied to the substrate weight, as a plain multiplier.

	``1 + allowance_pct/100`` for a Printed job, and exactly ``1.0`` for a Plain
	one — a Plain specification is unprinted paper and carries no ink weight, so
	its allowance is ignored even if a stale value is present on the record. A
	blank or negative-free allowance on a Printed job is ``1.0`` too: declining to
	estimate ink is allowed and means "no uplift".
	"""
	if normalise_print_type(print_type) != PRINT_TYPE_PRINTED:
		return 1.0
	pct = _num(allowance_pct)
	if not pct or pct <= 0:
		return 1.0
	return 1.0 + pct / 100.0


def paper_weight_per_set_g(width_mm, length_mm, gsm_total, print_type, allowance_pct):
	"""The weight of one set as it ships, in grams, or None.

	The substrate weight for a Plain job; the substrate weight times the printing
	allowance for a Printed one. None when the substrate weight is undefined.
	"""
	substrate = substrate_g_per_set(width_mm, length_mm, gsm_total)
	if substrate is None:
		return None
	return substrate * allowance_multiplier(print_type, allowance_pct)


def net_weight_per_carton_kg(per_set_g, sets_per_carton):
	"""The net product weight of one carton, in kilograms, or None.

	``per_set_g * sets_per_carton / 1000``. The paper only — no carton.
	"""
	per_set_g = _num(per_set_g)
	sets = _num(sets_per_carton)
	if per_set_g is None or not sets or sets <= 0:
		return None
	return per_set_g * sets / 1000.0


def gross_weight_per_carton_kg(net_kg, tare_kg):
	"""The gross packed weight of one carton, in kilograms, or None.

	``net_kg + tare_kg`` — the paper plus the empty carton it ships in. None when
	the net is undefined; a missing tare is treated as its own incompleteness by
	:func:`weight_block_reasons`, so it is not silently read as zero here.
	"""
	net_kg = _num(net_kg)
	tare = _num(tare_kg)
	if net_kg is None or tare is None or tare < 0:
		return None
	return net_kg + tare


def compute_weights(doc):
	"""Every derived weight for a specification, as a plain dict.

	Keys are the derived fieldnames (:data:`DERIVED_FIELDS`); a value is None when
	the inputs it needs are absent or not positive. Rounded to the precision each
	field carries so the stored number and the displayed number are the same
	number.

	This is the one authority. The controller writes exactly what this returns and
	the Compass preview echoes exactly what this returns, so Desk, REST and the
	screen cannot disagree about a carton's weight.
	"""
	width, length = effective_dimensions(doc)
	sets = _get(doc, SETS_PER_CARTON_FIELD)
	tare = _get(doc, TARE_FIELD)
	print_type = _get(doc, PRINT_TYPE_FIELD)
	allowance = _get(doc, ALLOWANCE_FIELD)

	gsm_total = total_gsm(_get(doc, COLOUR_OF_PARTS_FIELD))
	per_set = paper_weight_per_set_g(width, length, gsm_total, print_type, allowance)
	net = net_weight_per_carton_kg(per_set, sets)
	gross = gross_weight_per_carton_kg(net, tare)

	return {
		TOTAL_GSM_FIELD: round(gsm_total, GSM_PRECISION) if gsm_total > 0 else None,
		PER_SET_FIELD: _round_or_none(per_set, GRAMS_PRECISION),
		NET_FIELD: _round_or_none(net, KG_PRECISION),
		GROSS_FIELD: _round_or_none(gross, KG_PRECISION),
	}


def _round_or_none(value, precision):
	return None if value is None else round(value, precision)


def standard_weight_value(doc):
	"""The value to mirror into ``standard_weight_per_carton``, or None.

	The gross packed weight, rounded to that field's own precision. None when the
	gross is not derivable — which is the signal the controller uses to leave a
	legacy record's hand-typed weight exactly where it is.
	"""
	gross = compute_weights(doc).get(GROSS_FIELD)
	return None if gross is None else round(gross, STANDARD_WEIGHT_PRECISION)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _positive_block(value, code, template):
	"""A reason if a *present* value is negative or not a number, else None.

	A blank value is not an error here — absence is incompleteness, reported
	separately. **Neither is zero**, and that is a correction rather than a
	loosening: on a Frappe Float or Int column an untouched field loads as ``0``,
	not as ``None``, so "nobody typed a tare" and "the tare is zero" are the same
	stored value and cannot be told apart from in here. Refusing zero therefore
	refused *every save* of every specification whose tare had never been typed —
	including the legacy records this module is otherwise careful never to disturb.
	Reproduced on CPT-SPEC-00063 (2026-07-30): a draft saved without a tare could
	not be re-saved at all, with no way for the reader to clear the error.

	Zero is left to :func:`weight_submit_block_reason`, which already refuses a
	*submission* whose inputs are not positive and names the one that is missing.
	That is where "a packed carton weighs more than its contents" is enforced, and
	it is the right place: a draft may be half-known, a submitted specification may
	not.

	A negative is still refused on sight, on a draft as much as at submit — nobody
	types −5 by accident in a way that time will fix — and so is a value that is
	not a number at all.
	"""
	if value is None or value == "":
		return None
	number = _num(value)
	if number is None:
		return WeightBlock(code, template, (value,))
	if number < 0:
		return WeightBlock(code, template, (value,))
	return None


def weight_field_errors(doc):
	"""Every present-but-invalid weight input, as a list of reasons.

	Reported as a list rather than one at a time, like the parts grid: the four
	dimensions are filled in together and a reader fixing a negative width should
	be told about a zero sets-per-carton in the same pass. Absence is not here —
	an empty field is incomplete, not invalid, and :func:`weight_submit_block_reason`
	is where incompleteness bites.
	"""
	if not is_computer_paper(doc):
		return []

	errors = []
	for value, code, template in (
		# The inch entry first: it is what a person typed, so it is what a person
		# needs told about. The millimetre fields are checked too — they are derived
		# on save, but a legacy record stores them directly and a REST caller can
		# still post into them.
		(_get(doc, WIDTH_IN_FIELD), BLOCK_WIDTH,
		 "Finished width (in) cannot be negative. Got {0}."),
		(_get(doc, LENGTH_IN_FIELD), BLOCK_LENGTH,
		 "Finished length (in) cannot be negative. Got {0}."),
		(_get(doc, WIDTH_FIELD), BLOCK_WIDTH,
		 "Finished width (mm) cannot be negative. Got {0}."),
		(_get(doc, LENGTH_FIELD), BLOCK_LENGTH,
		 "Finished length (mm) cannot be negative. Got {0}."),
		(_get(doc, SETS_PER_CARTON_FIELD), BLOCK_SETS,
		 "Sets per carton cannot be negative. Got {0}."),
		# A negative "tare" would make a packed carton lighter than the paper in it.
		# A tare of zero is absence, not a claim that the carton is weightless —
		# see :func:`_positive_block` — and is refused at submit, not on a draft.
		(_get(doc, TARE_FIELD), BLOCK_TARE,
		 "Packing carton tare (kg) cannot be negative - the gross weight has to "
		 "include the carton. Got {0}."),
	):
		reason = _positive_block(value, code, template)
		if reason is not None:
			errors.append(reason)

	# Sets per carton must be whole: 500.5 sets is a typo, not a pack size.
	sets = _get(doc, SETS_PER_CARTON_FIELD)
	if _text(sets) is not None and _num(sets) is not None and float(_num(sets)) != int(_num(sets)):
		errors.append(
			WeightBlock(
				BLOCK_SETS,
				"Sets per carton must be a whole number, not {0}.",
				(sets,),
			)
		)

	# The allowance, when present, must be a non-negative percentage - a negative
	# "allowance" would quietly make a printed carton lighter than the paper in it.
	allowance = _get(doc, ALLOWANCE_FIELD)
	if _text(allowance) is not None:
		pct = _num(allowance)
		if pct is None or pct < 0:
			errors.append(
				WeightBlock(
					BLOCK_ALLOWANCE,
					"The printing allowance must be a percentage of 0 or more. Got {0}.",
					(allowance,),
				)
			)
		elif not is_printed(doc):
			# Not fatal to the arithmetic - a Plain job's allowance is ignored - but
			# worth saying, because a value here means somebody expects ink weight on
			# a job that is not printed.
			errors.append(
				WeightBlock(
					BLOCK_ALLOWANCE_ON_PLAIN,
					"A printing allowance of {0}% is set on a Plain specification. Plain paper "
					"is not printed, so the allowance is ignored - clear it or change the print "
					"type to Printed.",
					(allowance,),
				)
			)

	return errors


def weight_inputs_present(doc):
	"""Whether any structured weight input has been entered at all.

	The legacy signal. A record with none of these is a specification written
	before weights were captured, and nothing here computes or demands a weight
	for it; the moment somebody enters one, the record has opted in and
	completeness starts to matter.
	"""
	for fieldname in WEIGHT_ENTRY_FIELDS:
		if _text(_get(doc, fieldname)) is not None:
			return True
	return False


def weight_inputs_complete(doc):
	"""Whether every input the gross weight needs is present and positive.

	True exactly when :func:`compute_weights` can produce a gross — the four
	dimensions positive and the parts grid carrying GSM. The allowance is not
	required: it is optional and defaults to no uplift.
	"""
	if not is_computer_paper(doc):
		return False
	return standard_weight_value(doc) is not None and total_gsm(
		_get(doc, COLOUR_OF_PARTS_FIELD)
	) > 0


def weight_submit_block_reason(doc):
	"""Why a Computer Paper specification cannot be submitted for weight, or None.

	A *submit* rule, not a save rule, on exactly the terms artwork and numbering
	are: the dimensions and the pack size are often settled after the parts and
	the colours, and refusing the draft would stop a specification being recorded
	at all until every millimetre was known. Drafts may be incomplete; a
	submission may not.

	Deliberately with no legacy exemption of its own, matching
	:meth:`before_submit`'s treatment of artwork: an already-submitted record
	never re-runs this, so the 46 live submitted specifications are frozen and
	untouched, while a record being submitted *now* — new or a long-standing draft
	— is one going to production now and needs a real weight on it. The specific
	missing input is named so the reason is actionable rather than a bare refusal.
	"""
	if not is_computer_paper(doc):
		return None

	# The parts grid first: a weight cannot be computed without a grammage, and
	# the reader fixes the parts on a different panel than the dimensions.
	if total_gsm(_get(doc, COLOUR_OF_PARTS_FIELD)) <= 0:
		return WeightBlock(
			BLOCK_GSM,
			"A carton weight cannot be calculated without the GSM of each part. Complete "
			"the Colour of Parts grid before submitting.",
			(),
		)

	# The size is asked for in the unit it is entered in — inches — but judged on
	# whether a millimetre size can be had at all, so a legacy record submitting
	# on its stored millimetres is not asked for inches it never had.
	width, length = effective_dimensions(doc)
	missing = []
	if not (width and width > 0):
		missing.append("finished width (in)")
	if not (length and length > 0):
		missing.append("finished length (in)")
	missing.extend(
		label
		for fieldname, label in (
			(SETS_PER_CARTON_FIELD, "sets per carton"),
			(TARE_FIELD, "packing carton tare (kg)"),
		)
		if not (_num(_get(doc, fieldname)) and _num(_get(doc, fieldname)) > 0)
	)
	if missing:
		return WeightBlock(
			BLOCK_INCOMPLETE,
			"A Computer Paper specification cannot be submitted without its weight inputs. "
			"Enter {0}, or save it as a draft until they are known.",
			(", ".join(missing),),
		)

	return None


# ---------------------------------------------------------------------------
# The advisory suggestion — never a source, only a prefill
# ---------------------------------------------------------------------------

# The letters a written size uses between the two numbers, and the units it may
# carry. Anything else and there is no confident suggestion to offer.
_SIZE_SEPARATORS = ("x", "X", "×", "*", "by")


def suggest_dimensions(job_size, assume_unit=None):
	"""An editable (width, length) suggestion parsed from a free-text size, or None.

	This is the one thing this module does with ``job_size``, and it is
	deliberately weak: it returns a *suggestion* for the screen to prefill into
	the structured fields, which the user then confirms or corrects. Nothing in
	the weight calculation reads ``job_size``; a suggestion the user has not
	accepted into :data:`WIDTH_FIELD`/:data:`LENGTH_FIELD` is never multiplied by
	anything.

	Returns None whenever the text is not two plain numbers separated by a size
	separator — "A4", "241 x 279 x 2", "continuous" and an empty string all get no
	suggestion rather than a guessed one, because a wrong prefill the user does not
	notice is worse than no prefill at all.
	"""
	text = _text(job_size)
	if text is None:
		return None

	# Normalise every accepted separator to a single space, strip a trailing unit,
	# and require exactly two numeric tokens.
	lowered = text
	for sep in _SIZE_SEPARATORS:
		lowered = lowered.replace(sep, " ")
	tokens = [t for t in _tokenise_numbers(lowered)]
	if len(tokens) != 2:
		return None

	width, length = _num(tokens[0]), _num(tokens[1])
	if not width or not length or width <= 0 or length <= 0:
		return None
	lowered = text.lower()
	has_mm = "mm" in lowered
	words = lowered.replace('"', " ").replace("″", " ").split()
	has_inches = '"' in text or "″" in text or any(
		unit in words for unit in ("in", "inch", "inches")
	)
	if has_mm and has_inches:
		return None
	unit = "mm" if has_mm else "in" if has_inches else assume_unit
	if unit not in ("mm", "in"):
		return None
	factor = 25.4 if unit == "in" else 1.0
	return (round(width * factor, 3), round(length * factor, 3))


def _tokenise_numbers(text):
	"""The number-looking tokens in a string, keeping decimal points.

	A tiny hand-rolled scan rather than a regex, to keep this module import-free
	like its siblings. A token is a run of digits and at most the dots inside it;
	units glued to a number ("279mm") split cleanly because the letters end the
	run.
	"""
	tokens = []
	current = ""
	for char in text:
		if char.isdigit() or (char == "." and current):
			current += char
		else:
			if current:
				tokens.append(current)
				current = ""
	if current:
		tokens.append(current)
	return [t.strip(".") for t in tokens if t.strip(".")]


def reason_text(reason):
	"""A :class:`WeightBlock` as one finished, untranslated sentence."""
	if reason is None:
		return None
	return reason.template.format(*reason.args)
