"""Pure decision rules for the Computer Paper Customer Product Specification.

Frappe-free, on exactly the terms :mod:`cps_rules` and :mod:`cps_desk_rules`
are: every function takes plain data (dicts, lists, ``None``) and returns plain
data or an untranslated reason, so the whole ruleset can be unit tested without
a bench, a site or a database. The Frappe-bound caller is the DocType controller
``customer_product_specification.py``; the Compass mirror is
``vcl_compass.api.cps_core``, which is kept in step with this module and never
allowed to be more permissive than it.

Four things a Computer Paper specification must not be able to skip, and one
thing it must not be able to lose:

* **Numbering.** ``numbering_required`` has always been a Check, and a Check has
  no third state — an unticked box means "No" and "nobody was asked" identically.
  Fifty-nine live records reach this release with that ambiguity baked in. So the
  answer is not made mandatory (that would be a lie about the legacy rows); a
  second, additive Check records that a human actually *gave* the answer, and it
  is that flag which is demanded of anything new.

* **Print colour.** A Printed job with no ink recorded is a job the floor cannot
  run. A Plain job carrying ink is a job that will be quoted, planned and plated
  for colours nobody sells.

* **Colour of parts.** Pre-tinted paper, not ink. The two are separate physical
  things and the form has always shown them in one undifferentiated block.

* **Artwork.** Where the artwork is, when anybody knows. Retired as a *rule* on
  2026-08-07 — see :func:`artwork_evidence`. Thirty-nine of the forty-three
  submitted Printed specifications say nothing at all about their artwork, and a
  gate that the live estate fails ninety per cent of is not describing how VCL
  works. The artwork lives in the Design and Artwork Tracker; a weekly chase on
  what is still unanswered is the control, not a refusal at submit.

* And the one thing it must not lose: a legacy record that nobody has
  deliberately changed must keep saving. Twenty-one live Printed records hold no
  ink at all and all nine Plain records hold ink; blocking their unrelated edits
  would make this release a data-cleanup project nobody asked for.

Every rule below is therefore written as a *transition* rule — it looks at the
stored version and the incoming one and asks whether this particular save is one
that has to meet the new standard.
"""

from collections import namedtuple

# The only product type this module speaks for. Numbering, print colour, parts
# and artwork all mean something on every product line VCL sells, but what they
# mean differs — a Carton has no parts and a Label's artwork is its die. Widening
# these rules to another type is a separate decision with its own discovery, so
# the type is checked explicitly rather than assumed.
COMPUTER_PAPER = "Computer Paper"

PRINT_TYPE_PLAIN = "Plain"
PRINT_TYPE_PRINTED = "Printed"
PRINT_TYPES = (PRINT_TYPE_PLAIN, PRINT_TYPE_PRINTED)

# The business Yes/No, unchanged. This is the field production, the Job Card and
# the frozen order snapshot have always read, and it keeps its meaning exactly.
NUMBERING_FIELD = "numbering_required"

# The additive Check that separates "No" from "not asked". It is deliberately
# NOT a second business answer: nothing downstream reads it, no snapshot freezes
# it, and no Job Card is shaped by it. It records only that a person answered.
NUMBERING_CONFIRMED_FIELD = "numbering_confirmed"

NUMBERING_NOTES_FIELD = "numbering_notes"

# The Desk input. A Check cannot express "not answered", which is the whole
# reason NUMBERING_CONFIRMED_FIELD exists — but that flag is hidden provenance,
# not something to tick by hand, so Desk had no way to answer the question at
# all and every new Computer Paper specification written there was refused.
# This Select has the three states the question actually has; blank is "not
# answered". It is an input only: it writes the two stored fields above, which
# remain what production, the Job Card and the order snapshot read.
NUMBERING_ANSWER_FIELD = "numbering_answer"

NUMBERING_ANSWER_YES = "Yes"
NUMBERING_ANSWER_NO = "No"

# The four process inks, as Checks on the specification.
CMYK_FIELDS = ("uses_c", "uses_m", "uses_y", "uses_k")

SPOT_COLOURS_FIELD = "spot_colours"
COLOUR_OF_PARTS_FIELD = "colour_of_parts"

PRINT_TYPE_FIELD = "print_type"
PRINT_SIDE_FIELD = "print_side"

ARTWORK_FIELD = "artwork"
ARTWORK_NOTES_FIELD = "artwork_notes"

# The Design and Artwork Tracker job this specification is plated from. VCL's
# artwork already lives there — it is where the design is drawn, revised and
# approved — so copying the file onto the specification made a second, staler
# copy of something the business already tracks. A link says which job, and the
# tracker stays the one place the artwork is.
#
# It does NOT replace ARTWORK_FIELD. Sixty-five live specifications carry an
# attached file and removing the field would strand every one of them, so both
# are accepted and the attach route keeps working.
ARTWORK_TRACKER_FIELD = "artwork_tracker"

# A deliberate deferral: the specification is complete in every other respect
# and the artwork is genuinely still being drawn. Ticking it is what lets a
# Printed specification submit without either a file or a tracker job.
#
# This is an unguarded bypass, and knowingly so — anybody who can edit the
# specification can tick it. It is a record of a decision, not a control.
ARTWORK_NOT_READY_FIELD = "artwork_not_ready"

# What counts as somebody deliberately touching the colour of this record, and
# therefore as the save that has to meet the new standard.
#
# ``colour_notes`` and ``ink_type`` are deliberately ABSENT. Neither states which
# inks the job runs: one is free text and the other is which ink *system* is
# used. Including them would mean that correcting a typo in a note on one of the
# nine Plain records that carry legacy ink data refuses the save — which is the
# precise failure this release is written to avoid.
COLOUR_TOUCH_FIELDS = (PRINT_TYPE_FIELD,) + CMYK_FIELDS

# The spot-colour row fields compared when deciding whether the grid was edited.
# Same set the order snapshot freezes (``cps_rules.SNAPSHOT_SPOT_FIELDS``), so
# "the colours changed" means the same thing here and on a sold order.
SPOT_ROW_FIELDS = (
	"pantone_code",
	"pantone_name",
	"hex_preview",
	"cmyk_c",
	"cmyk_m",
	"cmyk_y",
	"cmyk_k",
	"notes",
)

PART_ROW_FIELDS = ("part_number", "paper_type", "gsm", "colour", "purpose")


# A refusal, carried as an untranslated template plus its arguments so this
# module stays Frappe-free and the caller can do ``_(reason.template).format()``.
# Same shape as :class:`cps_rules.SpecBlock`, and named differently only because
# it answers a different question — this is "why this save is refused", not "why
# this specification cannot be ordered against".
CPSBlock = namedtuple("CPSBlock", ("code", "template", "args"))

BLOCK_NUMBERING_UNCONFIRMED = "numbering-unconfirmed"
BLOCK_NUMBERING_UNCONFIRMABLE = "numbering-unconfirmable"
BLOCK_PRINTED_NO_INK = "printed-no-ink"
BLOCK_PLAIN_HAS_INK = "plain-has-ink"
BLOCK_PRINT_TYPE_MISSING = "print-type-missing"
BLOCK_PRINT_TYPE_UNKNOWN = "print-type-unknown"
BLOCK_PRINT_SIDE_ON_PLAIN = "print-side-on-plain"
BLOCK_ARTWORK_NOT_PRIVATE = "artwork-not-private"
BLOCK_ARTWORK_WRONG_DOC = "artwork-wrong-document"
BLOCK_ARTWORK_EXTENSION = "artwork-extension"
BLOCK_ARTWORK_TOO_LARGE = "artwork-too-large"
BLOCK_ARTWORK_EMPTY = "artwork-empty"


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


def _checked(value):
	"""A Frappe Check read as a real boolean.

	``0``, ``"0"``, ``""``, ``None`` and ``False`` are all "unticked". Frappe
	hands back any of them depending on whether the value came from the database,
	from a form submission or from a JSON payload, and a rule that branched on
	truthiness alone would treat the string ``"0"`` as ticked.
	"""
	if isinstance(value, bool):
		return value
	if value is None or value == "":
		return False
	if isinstance(value, str):
		return value.strip() not in ("", "0", "false", "False", "No")
	try:
		return bool(int(value))
	except (TypeError, ValueError):
		return bool(value)


def _text(value):
	"""Trimmed text, or None. Blank and absent are the same absence."""
	if value is None:
		return None
	value = str(value).strip()
	return value or None


def _int(value, default=0):
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def is_computer_paper(doc):
	"""Whether these rules speak for this record at all."""
	return _text(_get(doc, "product_type")) == COMPUTER_PAPER


def is_new(before):
	"""Whether this save is creating the record rather than editing one.

	``before`` is the stored version — ``get_doc_before_save()`` in the
	controller, ``None`` on insert. Everything in this module keys off it, because
	"is this a new record" and "did somebody deliberately change this" are the two
	questions that separate a rule worth enforcing from a legacy record worth
	leaving alone.
	"""
	return before is None


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------


def numbering_answer(doc):
	"""The business Yes/No, as a boolean."""
	return _checked(_get(doc, NUMBERING_FIELD))


def numbering_confirmed(doc):
	"""Whether a person is recorded as having actually answered."""
	return _checked(_get(doc, NUMBERING_CONFIRMED_FIELD))


def numbering_answer_fields(answer):
	"""The two stored numbering fields implied by a Desk answer, or None.

	Blank is not an answer and returns None rather than 0/0. The difference
	matters: a legacy record edited for an unrelated reason carries no answer in
	the Select, and writing 0/0 for it would withdraw a confirmation nobody
	touched — refused by :func:`numbering_block_reason`, and rightly.
	"""
	value = _text(answer)
	if value not in (NUMBERING_ANSWER_YES, NUMBERING_ANSWER_NO):
		return None
	return {
		NUMBERING_FIELD: 1 if value == NUMBERING_ANSWER_YES else 0,
		NUMBERING_CONFIRMED_FIELD: 1,
	}


def numbering_changed(before, after):
	"""Whether this save moves the business Yes/No.

	Compared as booleans rather than as stored values, so a legacy ``None``
	becoming a stored ``0`` is not a change — that is a column being written for
	the first time, not somebody re-answering the question.
	"""
	if before is None or after is None:
		return False
	return numbering_answer(before) != numbering_answer(after)


def numbering_block_reason(before, after):
	"""Why this save's Numbering answer is refused, or None.

	Three cases, in the order they are worth reporting:

	1. A **new** record with no confirmation. There is no legacy to protect and
	   no excuse for an unanswered question, so the flag is required outright.
	2. An **existing** record whose answer is being *changed* without
	   confirmation. Changing the answer is the deliberate act; an unrelated edit
	   to a legacy row is not, and is left alone.
	3. An existing record whose confirmation is being **withdrawn**. Once a person
	   has answered, un-answering is not an edit anybody needs — it can only make
	   a complete record incomplete again — so it is refused rather than obeyed.

	Everything else passes, including the whole of the legacy estate saving for
	unrelated reasons.
	"""
	if after is None or not is_computer_paper(after):
		return None

	if is_new(before):
		if not numbering_confirmed(after):
			return CPSBlock(
				BLOCK_NUMBERING_UNCONFIRMED,
				"Answer the Numbering question before saving: choose Yes or No. "
				"Leaving it blank is not the same as No, and production cannot tell the two apart later.",
				(),
			)
		return None

	if numbering_confirmed(before) and not numbering_confirmed(after):
		return CPSBlock(
			BLOCK_NUMBERING_UNCONFIRMABLE,
			"The Numbering answer on {0} has already been given and cannot be un-answered. "
			"Change it to Yes or No instead.",
			(_text(_get(after, "name")) or "this specification",),
		)

	if numbering_changed(before, after) and not numbering_confirmed(after):
		return CPSBlock(
			BLOCK_NUMBERING_UNCONFIRMED,
			"Numbering is being changed from {0} to {1}. Confirm the answer before saving.",
			(
				"Yes" if numbering_answer(before) else "No",
				"Yes" if numbering_answer(after) else "No",
			),
		)

	return None


# Said once, here, so the Desk description, the Compass hint and the job-card
# screen cannot drift into three different accounts of the same rule.
NUMBERING_RANGE_NOTICE = (
	"Numbering start and end are job-specific and are entered on the Job Card, not here. "
	"This answer says only whether the product is numbered at all."
)


# ---------------------------------------------------------------------------
# Print colour (ink) — separate from colour of parts (pre-tinted paper)
# ---------------------------------------------------------------------------


def cmyk_ticked(doc):
	"""Which of the four process inks are ticked, in CMYK order."""
	return [f for f in CMYK_FIELDS if _checked(_get(doc, f))]


def spot_rows(doc):
	"""The spot colour rows, as a plain list."""
	return _rows(_get(doc, SPOT_COLOURS_FIELD))


def ink_count(doc):
	"""Total plates: ticked process inks plus spot colour rows.

	The same arithmetic the controller writes into the read-only
	``number_of_colours``. Kept here so the count has one definition and the
	front-end can show it without inventing a second.
	"""
	return len(cmyk_ticked(doc)) + len(spot_rows(doc))


def has_ink(doc):
	"""Whether this record records any print ink at all."""
	return ink_count(doc) > 0


def normalise_print_type(value):
	"""A stored print type, trimmed, or None.

	Deliberately not filtered against :data:`PRINT_TYPES`: an unrecognised value
	must be reported as unrecognised rather than silently read as Plain, which is
	the reading that would let a Printed job through with no ink.
	"""
	return _text(value)


def _spot_row_key(row):
	return tuple(_text(_get(row, f)) for f in SPOT_ROW_FIELDS)


def spot_rows_changed(before, after):
	"""Whether the spot colour grid was edited, row for row and in order.

	Order is part of the value: two Pantones swapped between rows one and two is
	a different plate sequence, and comparing them as an unordered bag would call
	that identical.
	"""
	if before is None or after is None:
		return False
	first = [_spot_row_key(r) for r in spot_rows(before)]
	second = [_spot_row_key(r) for r in spot_rows(after)]
	return first != second


def colour_touched(before, after):
	"""Whether this save deliberately changes what the job is printed in.

	The trigger for the colour rules on an existing record. See
	:data:`COLOUR_TOUCH_FIELDS` for why notes and ink system are not in the set.
	"""
	if before is None or after is None:
		return False
	for fieldname in COLOUR_TOUCH_FIELDS:
		if fieldname in CMYK_FIELDS:
			if _checked(_get(before, fieldname)) != _checked(_get(after, fieldname)):
				return True
		elif _text(_get(before, fieldname)) != _text(_get(after, fieldname)):
			return True
	return spot_rows_changed(before, after)


def colour_rules_apply(before, after):
	"""Whether the colour consistency rules bind this particular save.

	New records always. Existing records only when somebody has deliberately
	moved the print type or the inks — which is what keeps twenty-one inkless
	Printed records and nine inked Plain records saving for every other reason.
	"""
	if after is None or not is_computer_paper(after):
		return False
	return is_new(before) or colour_touched(before, after)


def colour_block_reason(before, after):
	"""Why this save's print colours are refused, or None.

	Reported in the order a reader can act on: an unusable print type first,
	because neither ink rule means anything until the record says which kind of
	job it is; then the two consistency rules.
	"""
	if not colour_rules_apply(before, after):
		return None

	print_type = normalise_print_type(_get(after, PRINT_TYPE_FIELD))

	if not print_type:
		return CPSBlock(
			BLOCK_PRINT_TYPE_MISSING,
			"Choose Plain or Printed before saving. Everything about the colours of this "
			"specification depends on which one it is.",
			(),
		)

	if print_type not in PRINT_TYPES:
		return CPSBlock(
			BLOCK_PRINT_TYPE_UNKNOWN,
			"{0} is not a print type. Choose one of: {1}.",
			(print_type, ", ".join(PRINT_TYPES)),
		)

	if print_type == PRINT_TYPE_PRINTED and not has_ink(after):
		return CPSBlock(
			BLOCK_PRINTED_NO_INK,
			"A Printed specification must record at least one print colour: tick a CMYK "
			"process ink or add a spot colour row. These are inks - the Colour of Parts "
			"table below is pre-tinted paper and is not a substitute.",
			(),
		)

	if print_type == PRINT_TYPE_PLAIN and has_ink(after):
		return CPSBlock(
			BLOCK_PLAIN_HAS_INK,
			"A Plain specification cannot carry print inks. Remove {0} process ink(s) and "
			"{1} spot colour row(s), or change the print type to Printed. Pre-tinted paper "
			"belongs in Colour of Parts, which is not affected by this.",
			(len(cmyk_ticked(after)), len(spot_rows(after))),
		)

	return None


def print_side_block_reason(before, after):
	"""Why this save's Print Side is refused, or None.

	``print_side`` ships with a default of ``"N/A"`` and is hidden on the Desk
	form unless the job is Printed, so a Plain record legitimately carries either
	``"N/A"`` or nothing at all. Anything else on a Plain record is a leftover
	from a job that used to be Printed, and it will be read off the specification
	by whoever plates the job.

	Gated on the same trigger as the colour rules for the same reason: a legacy
	Plain record whose print side was never cleared must keep saving until
	somebody actually touches its colour.
	"""
	if not colour_rules_apply(before, after):
		return None

	if normalise_print_type(_get(after, PRINT_TYPE_FIELD)) != PRINT_TYPE_PLAIN:
		return None

	side = _text(_get(after, PRINT_SIDE_FIELD))
	if side in (None, "N/A"):
		return None

	return CPSBlock(
		BLOCK_PRINT_SIDE_ON_PLAIN,
		"Print Side is {0} on a Plain specification. A Plain job is not printed, so it has "
		"no printed side - set it to N/A or change the print type to Printed.",
		(side,),
	)


# ---------------------------------------------------------------------------
# Parts (pre-tinted paper) — defaults, not new restrictions
# ---------------------------------------------------------------------------
#
# The controller has always enforced the paper type and GSM per position, and
# nothing here loosens or tightens it. What is added is the *defaults*: the
# sequence a person would otherwise retype for every multi-part set, offered so
# the common case needs no typing and the uncommon one is still reachable.
#
# GSM is not free: 55 for CB, 50 for CFB, 55 for CF is what production runs and
# what ``_validate_paper_type_and_gsm`` already refuses to save without. The
# single-part case genuinely has three options, so it is offered as three rather
# than defaulted to one.

# (paper_type, gsm) accepted in a one-part set, in the order they are offered.
SINGLE_PART_OPTIONS = (("60 GSM Bond", 60), ("CB", 55), ("70 GSM Bond", 70))

# A multi-part set is CB on top, CFB for every middle ply, CF at the bottom.
FIRST_PART = ("CB", 55)
MIDDLE_PART = ("CFB", 50)
LAST_PART = ("CF", 55)

# What each ply does, in plain operational words. Written onto the default rows
# as ``purpose`` so a set explains itself on the shop floor.
PART_PURPOSE = {
	"CB": "Coated Back - top copy, transfers to the ply below",
	"CFB": "Coated Front and Back - middle copy, receives and transfers",
	"CF": "Coated Front - bottom copy, receives only",
	"60 GSM Bond": "Plain bond - single part, no carbonless transfer",
	"70 GSM Bond": "Plain bond - single part, no carbonless transfer",
}

# The conventional VCL part colours by position. White first, then the sequence
# the floor recognises. Offered as a default only — the colour is a per-customer
# fact and is always editable. One per position up to :data:`MAX_DEFAULT_PARTS`,
# so the deepest set this generates still names a colour for every ply.
DEFAULT_PART_COLOURS = (
	"White", "Pink", "Blue", "Yellow", "Green", "Buff", "Lilac", "Grey",
)

# A part count nobody at VCL runs is almost certainly a typo. Refused as a
# *shaping* limit on the defaults rather than as a new save rule, so an existing
# record with an unusual count is untouched.
MAX_DEFAULT_PARTS = 8


def part_positions(number_of_parts):
	"""(paper_type, gsm) per position for a set of ``number_of_parts`` plies.

	One part is genuinely ambiguous — three paper types are valid — so the first
	of :data:`SINGLE_PART_OPTIONS` is offered and the other two remain selectable.
	Anything above one is the CB / CFB… / CF sequence with no ambiguity at all.
	"""
	count = _int(number_of_parts, 0)
	if count <= 0:
		return []
	if count == 1:
		return [SINGLE_PART_OPTIONS[0]]
	return [FIRST_PART] + [MIDDLE_PART] * (count - 2) + [LAST_PART]


def default_parts(number_of_parts, existing=None):
	"""The Colour of Parts rows for a set of ``number_of_parts`` plies.

	``existing`` is whatever the record already holds. Its colours and purposes
	are carried forward position by position, so changing a three-part set to a
	four-part one keeps the three colours somebody already chose instead of
	silently resetting them — the single most annoying thing a form can do.

	Paper type and GSM are *not* carried forward, because they are a property of
	the position and the position has just changed: the third ply of a three-part
	set is CF, and the third ply of a four-part set is CFB.
	"""
	existing = _rows(existing)
	rows = []
	for index, (paper_type, gsm) in enumerate(part_positions(number_of_parts)):
		previous = existing[index] if index < len(existing) else None
		colour = _text(_get(previous, "colour")) or _default_colour(index)
		purpose = _text(_get(previous, "purpose")) or PART_PURPOSE.get(paper_type, "")
		rows.append(
			{
				"part_number": index + 1,
				"paper_type": paper_type,
				"gsm": gsm,
				"colour": colour,
				"purpose": purpose,
			}
		)
	return rows


def _default_colour(index):
	if index < len(DEFAULT_PART_COLOURS):
		return DEFAULT_PART_COLOURS[index]
	return ""


def part_row_errors(number_of_parts, parts):
	"""Every problem with the Colour of Parts grid, as untranslated reasons.

	A *list* rather than the first reason, unlike everything else in this module,
	because a grid is filled in all at once: reporting "row 2 has no colour" and
	making the user save again to be told about row 4 is how a five-part set takes
	five attempts.

	These mirror ``CustomerProductSpecification.validate_computer_paper`` exactly
	— same conditions, same order, same wording where the wording is the same
	sentence — so the front-end can show them inline before the save and never
	clear a record the server then refuses.
	"""
	count = _int(number_of_parts, 0)
	parts = _rows(parts)
	errors = []

	if count <= 0:
		errors.append(
			CPSBlock(
				"parts-count-missing",
				"Number of Parts is required for Computer Paper, and must be at least 1.",
				(),
			)
		)
		return errors

	if len(parts) != count:
		errors.append(
			CPSBlock(
				"parts-count-mismatch",
				"Colour of Parts must have exactly {0} row(s), but {1} row(s) found.",
				(count, len(parts)),
			)
		)

	expected = part_positions(count)
	for index, part in enumerate(parts):
		position = index + 1
		if _int(_get(part, "part_number"), 0) != position:
			errors.append(
				CPSBlock(
					"parts-out-of-sequence",
					"Part numbers must be sequential. Row {0}: expected part number {0}, got {1}.",
					(position, _get(part, "part_number")),
				)
			)
		if not _text(_get(part, "colour")):
			errors.append(
				CPSBlock(
					"parts-colour-missing",
					"Row {0} in Colour of Parts is missing a colour. "
					"This is the pre-tinted paper for that ply, not a print colour.",
					(position,),
				)
			)
		if index >= len(expected):
			continue
		errors.extend(_paper_errors(part, position, count, index, len(expected)))

	return errors


def _paper_errors(part, position, count, index, expected_len):
	"""Paper type / GSM problems for one row, mirroring the controller."""
	if count == 1:
		valid = SINGLE_PART_OPTIONS
		position_label = "single part"
	elif index == 0:
		valid = (FIRST_PART,)
		position_label = "first part"
	elif index == expected_len - 1:
		valid = (LAST_PART,)
		position_label = "last part"
	else:
		valid = (MIDDLE_PART,)
		position_label = "middle part"

	paper_type = _text(_get(part, "paper_type"))
	gsm = _int(_get(part, "gsm"), 0)
	if any(paper_type == pt and gsm == g for pt, g in valid):
		return []

	return [
		CPSBlock(
			"parts-paper-invalid",
			"Part {0} ({1}): invalid paper type/GSM. Expected one of: {2}. Got: {3} ({4} GSM).",
			(
				position,
				position_label,
				", ".join("{0} ({1} GSM)".format(pt, g) for pt, g in valid),
				paper_type or "nothing",
				gsm,
			),
		)
	]


# ---------------------------------------------------------------------------
# Artwork
# ---------------------------------------------------------------------------
#
# Artwork is a file, and a file is the one thing on this record that can be made
# to point somewhere it should not. Four separate questions have to be answered
# and none of them is answered by the others:
#
#   * may this user write to this specification at all  (the caller's job)
#   * is the file PRIVATE                               (:func:`artwork_binding_error`)
#   * is it bound to THIS document                      (:func:`artwork_binding_error`)
#   * is it a kind and a size we accept                 (:func:`artwork_upload_error`)
#
# The binding question is the one that is easy to get wrong: a caller that
# accepts a ``file_url`` and writes it onto the field has built a way to read any
# private file on the site by guessing its path. So a URL is never trusted — the
# stored File row is read and *it* is asked which document it belongs to.

# Lowercase, with the dot. Deliberately short: this is the artwork a printer
# plates from, and everything VCL has ever received is in this list.
#
# ``.svg`` is deliberately absent. It is XML, not an image: a browser handed one
# from a same-origin path will parse its <script> and its external references,
# and the artwork route serves files back to signed-in staff on the site's own
# origin. Nobody at VCL has ever sent press artwork as an SVG, so the format buys
# nothing that would pay for that.
ARTWORK_EXTENSIONS = (".pdf", ".ai", ".eps", ".png", ".jpg", ".jpeg", ".tif", ".tiff")

# 25 MB. Large enough for a real press-ready PDF, small enough that a phone
# upload on a Nairobi connection is not a silent five-minute hang.
ARTWORK_MAX_BYTES = 25 * 1024 * 1024


def artwork_extension(filename):
	"""The lowercase extension of a filename, with its dot, or ``""``."""
	name = _text(filename) or ""
	# rsplit rather than os.path.splitext: this module has no imports for a
	# reason, and the query-string and path handling below is ours to define.
	name = name.split("?", 1)[0].split("#", 1)[0]
	name = name.replace("\\", "/").rsplit("/", 1)[-1]
	if "." not in name:
		return ""
	return "." + name.rsplit(".", 1)[-1].lower()


def artwork_upload_error(filename, size_bytes):
	"""Why an uploaded file cannot be this specification's artwork, or None.

	Checked *before* anything is written, so a rejected upload never becomes a
	File row somebody has to clean up.
	"""
	extension = artwork_extension(filename)
	if not extension or extension not in ARTWORK_EXTENSIONS:
		return CPSBlock(
			BLOCK_ARTWORK_EXTENSION,
			"{0} is not a kind of artwork this form accepts. Upload one of: {1}.",
			(_text(filename) or "That file", " ".join(ARTWORK_EXTENSIONS)),
		)

	size = _int(size_bytes, 0)
	if size <= 0:
		return CPSBlock(
			BLOCK_ARTWORK_EMPTY,
			"{0} is empty. Upload the artwork file itself.",
			(_text(filename) or "That file",),
		)

	if size > ARTWORK_MAX_BYTES:
		return CPSBlock(
			BLOCK_ARTWORK_TOO_LARGE,
			"{0} is {1} MB. The limit is {2} MB - send a flattened or compressed copy.",
			(
				_text(filename) or "That file",
				round(size / (1024.0 * 1024.0), 1),
				ARTWORK_MAX_BYTES // (1024 * 1024),
			),
		)

	return None


def artwork_binding_error(file_row, doctype, name):
	"""Why a stored File may not be used as ``name``'s artwork, or None.

	``file_row`` is the File document as a dict (or None when no such row
	exists). The three things asked of it are the three things a URL cannot tell
	you: that it exists, that it belongs to *this* document rather than to
	somebody else's, and that it is private.

	Ownership is asked before privacy on purpose: when a file is somebody else's,
	*whose* it is is the fact worth reporting, and its privacy is not this
	record's business to comment on. Privacy is asked only once the file is known
	to belong here.

	This is what makes "reject attaching another document's File URL" a rule
	rather than an intention.
	"""
	if not file_row:
		return CPSBlock(
			BLOCK_ARTWORK_WRONG_DOC,
			"That file is not attached to {0}. Upload the artwork here rather than "
			"referencing a file from elsewhere.",
			(_text(name) or "this specification",),
		)

	attached_doctype = _text(_get(file_row, "attached_to_doctype"))
	attached_name = _text(_get(file_row, "attached_to_name"))
	if attached_doctype != _text(doctype) or attached_name != _text(name):
		return CPSBlock(
			BLOCK_ARTWORK_WRONG_DOC,
			"That file belongs to {0} {1}, not to {2}. Upload the artwork here rather than "
			"referencing another document's file.",
			(
				attached_doctype or "no document",
				attached_name or "-",
				_text(name) or "this specification",
			),
		)

	if not _checked(_get(file_row, "is_private")):
		return CPSBlock(
			BLOCK_ARTWORK_NOT_PRIVATE,
			"Artwork must be a private attachment. {0} is public and would be readable "
			"by anyone with the link.",
			(_text(_get(file_row, "file_name")) or "That file",),
		)

	return None


def artwork_file_error(file_row, doctype, name):
	"""Why the File a specification points at may not be its artwork, or None.

	The submit-time counterpart to :func:`artwork_upload_error`, and the reason
	that one is not the whole story: the Compass upload endpoint is only *one* of
	the ways a value reaches ``artwork``. Desk's own attach control, a REST write
	and a Data Import all set the field directly, and none of them has ever been
	past an extension allowlist or a size cap. So at the one moment the record
	stops being a draft, the *stored* File row is asked every question again —
	the three only a stored row can answer (does it exist, is it private, does it
	belong to this document) and then the two the uploader was asked (is it a
	kind we accept, is it a sane size).

	``file_row`` is the File document as a dict, resolved by the caller from the
	stored URL, or None when the URL names no File at all. The extension is read
	from the row's own ``file_name``, falling back to its ``file_url``, and never
	from the value on the specification: the point of this check is that the
	field's value is not evidence of anything.
	"""
	reason = artwork_binding_error(file_row, doctype, name)
	if reason is not None:
		return reason

	filename = _text(_get(file_row, "file_name")) or _text(_get(file_row, "file_url"))
	return artwork_upload_error(filename, _get(file_row, "file_size"))


def artwork_required(doc):
	"""Whether this specification must carry artwork to be submitted.

	Printed only. A Plain Computer Paper job is uncut, untinted white paper with
	nothing on it, and demanding a file for it would teach everybody to attach a
	blank page to get past the check.
	"""
	if not is_computer_paper(doc):
		return False
	return normalise_print_type(_get(doc, PRINT_TYPE_FIELD)) == PRINT_TYPE_PRINTED


def artwork_deferred(doc):
	"""Whether the artwork is recorded as still being drawn."""
	return _checked(_get(doc, ARTWORK_NOT_READY_FIELD))


def artwork_evidence(doc):
	"""What this specification offers about its artwork, or None.

	Three things count, and they are genuinely different claims rather than three
	spellings of one:

	``"file"``
		An attached file, proved by :func:`artwork_file_error` at submit.

	``"tracker"``
		A Design and Artwork Tracker job. The artwork exists and lives there,
		which is where it was drawn and approved in the first place.

	``"deferred"``
		Nobody claims there is artwork. Somebody has said so on the record.

	Returned rather than a bare boolean so a caller — a Job Card, a traveller,
	a report of specifications waiting on design — can tell "the artwork is in
	the tracker" from "there is no artwork yet", which a boolean flattens.
	"""
	if _text(_get(doc, ARTWORK_FIELD)):
		return "file"
	if _text(_get(doc, ARTWORK_TRACKER_FIELD)):
		return "tracker"
	if artwork_deferred(doc):
		return "deferred"
	return None


# ``artwork_submit_block_reason`` lived here until 2026-08-07 and refused any
# Printed specification carrying no artwork. It is gone rather than softened.
#
# The rule was written on the belief that a Printed specification without
# artwork is incomplete. That is true of the artwork; it was not true of the
# *field*. VCL's artwork lives in the Design and Artwork Tracker, where it is
# drawn, revised and approved, so the specification never needed its own copy —
# and the live estate said so plainly: thirty-nine of forty-three submitted
# Printed specifications had nothing in the field, four had a file, and the rule
# had been in force for months. A gate that the work routes around is not a
# control, it is a delay with a message attached.
#
# What replaced it is :func:`artwork_evidence` plus a weekly chase on the
# specifications still saying nothing. Asking later costs a reminder; refusing
# at submit cost the specification.
#
# ``validate_artwork_integrity`` on the controller is deliberately KEPT. It asks
# a different question — whether a file somebody did attach is real, private and
# bound to this document — and that stays worth proving.


def artwork_deletable(file_row, doctype, name, other_references=0):
	"""Whether removing the field may also delete the File itself.

	Only a correctly bound, private File belonging to this document, and only
	when nothing else still points at it. Anything else has the field cleared and
	the row left exactly where it is: an orphaned attachment costs a few
	kilobytes, and deleting a file another record is using costs the artwork.
	"""
	if artwork_binding_error(file_row, doctype, name) is not None:
		return False
	return _int(other_references, 0) <= 0


# ---------------------------------------------------------------------------
# The whole verdict, in one call
# ---------------------------------------------------------------------------


def save_block_reason(before, after, numbering_available=True):
	"""The first reason this Computer Paper save must be refused, or None.

	Ordered the way a person fixes them: the identity question (which kind of job
	is this) is inside the colour rules and comes first, then Numbering, then the
	print side. Parts are reported separately and as a list, because they are a
	grid — see :func:`part_row_errors`.

	``numbering_available`` is whether :data:`NUMBERING_CONFIRMED_FIELD` exists on
	this site yet. It defaults to True because that is the state every site is in
	once the patch has run, and it exists for the window between a deploy and its
	migrate: without it, a site that has the code and not the column would demand
	a confirmation that has nowhere to be recorded, and refuse every new Computer
	Paper specification with an error nobody could clear. The colour rules take no
	such parameter because they read only fields that already existed.
	"""
	if after is None or not is_computer_paper(after):
		return None

	for reason in (
		colour_block_reason(before, after),
		numbering_block_reason(before, after) if numbering_available else None,
		print_side_block_reason(before, after),
	):
		if reason is not None:
			return reason
	return None


def reason_text(reason):
	"""A :class:`CPSBlock` as one finished, untranslated sentence."""
	if reason is None:
		return None
	return reason.template.format(*reason.args)
