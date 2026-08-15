"""Pure board-plan arithmetic for the Carton Customer Product Specification.

Frappe-free, on exactly the terms :mod:`cps_cp_weight`, :mod:`cps_cp_rules` and
:mod:`cps_rules` are: every function takes plain data and returns plain data or
an untranslated reason, so the whole calculation can be unit tested without a
bench, a site or a database.

Why this exists
---------------

Until now the board plan lived **only in JavaScript**, and in two copies —
``customer_product_specification.js`` and ``job_card_carton.js`` — with a third,
partial copy of the same geometry in :mod:`production_log.utils` for the
traveller's die-cut SVG. Three copies of one formula is three chances to drift,
and they had already drifted: the stitch flap was reduced from 40 mm to 30 mm on
2026-07-23 in both JS copies and **not** in ``utils.py``, so the traveller drew a
40 mm flap next to board figures computed with 30.

The immediate reason it had to become Python is ``cps_revise``. A specification
that was submitted before the Board Plan fields existed (2026-07-23) carries
zeroes for all six, and a client script cannot write to a submitted document —
so the values can only be persisted by the server, on an update-after-submit,
where ``validate()`` does **not** run. Anything the server stores there it must
therefore derive and check itself. This module is what it derives them with.

What is an input and what is derived
------------------------------------

Only two things here are typed by a person:

* the **flap**, which defaults to :func:`auto_flap` but is regularly overridden
  because the auto value is a formula, not a measurement; and
* the **actual** board sizes, which default to the blank but are overridden when
  the board actually run differs from the blank the geometry implies.

Everything else — blank sizes, planned sizes, approximate weight — is derived,
and is stored only so a submitted specification reads the same as one created
after the fields existed. Both CPS print formats recompute rather than trust the
stored values, and that stays true: storing them is for parity and for reporting,
never for authority.

The one thing this module does not pretend to know
---------------------------------------------------

:func:`approximate_weight_grams` sums the raw GSM of every ply and multiplies by
the planned board area. It does **not** model **flute take-up** — the fluting
medium consumes roughly 1.35–1.4x its flat area on B flute, so the true weight of
a corrugated board is materially higher than the sum of its plies. CPT-SPEC-00058
computes 172.8 g against a stated ``empty_carton_weight`` of 300 g, and that gap
is mostly this.

It is left unmodelled deliberately: the Job Card has printed this same
understated figure since long before the specification carried it, and correcting
it here alone would put two different weights for one carton on two documents.
Fixing it is a decision about every carton figure VCL has quoted, not a change to
this module. Until that decision is taken, the number is called *approximate*
everywhere it appears and ``empty_carton_weight`` remains the weighed truth.
"""

# The VCL standard joint tab, every joint type, since 2026-07-23 — the stitch
# flap was reduced from 40 mm on that date. Kept as one constant rather than a
# per-joint map precisely because they are all the same now: a map invites the
# three copies to drift apart again the next time one of them changes.
TAB_WIDTH_MM = 30

# Per OUTER edge, so a full axis gains twice this.
TRIM_PER_EDGE_MM = 10

CARTON = "Carton"

# Styles whose blank this module can draw. "Die Cut" is deliberately absent:
# custom die shapes vary per job and no formula describes them.
STYLE_TRAY = "Tray"
STYLE_ONE_FLAP = "1 Flap RSC"
STYLE_DIE_CUT = "Die Cut"

# An un-glued web. There is no blank to plan.
PLY_SFK = "SFK"

# Reasons a board plan is not applicable. Untranslated, on the terms of the
# sibling rules modules — the caller decides how to say them.
NOT_CARTON = "not-carton"
SFK = "sfk"
DIE_CUT = "die-cut"
NO_STYLE = "no-style"
INCOMPLETE_DIMENSIONS = "incomplete-dimensions"


def _int(value):
	"""Coerce to a non-negative int, treating None/"" /junk as 0."""
	try:
		out = int(float(value))
	except (TypeError, ValueError):
		return 0
	return out if out > 0 else 0


def auto_flap(width_mm):
	"""The flap VCL uses when nobody has said otherwise: ``ceil((W + 5) / 2)``.

	Half the carton width plus a 5 mm allowance, rounded up, so two opposing
	flaps meet across the width with a little to spare. Integer arithmetic
	rather than ``math.ceil`` so the identical expression is legal inside a
	Frappe Server Script, where imports are not.
	"""
	width_mm = _int(width_mm)
	if width_mm <= 0:
		return 0
	return (width_mm + 6) // 2


def total_gsm(spec):
	"""Sum the GSM of the plies this carton actually has.

	Plies 1 and 2 always; ply 3 on a 3- or 5-ply board; plies 4 and 5 only on a
	5-ply. Reading ply 3 on a 2-ply board would pick up a stale value left
	behind by an earlier edit.
	"""
	ply = str(spec.get("ply") or "").strip()
	gsm = _int(spec.get("1_ply_top_layer_gsm")) + _int(spec.get("2_ply_fluting_gsm"))
	if ply in ("3", "5"):
		gsm += _int(spec.get("3_ply_bottom_gsm"))
	if ply == "5":
		gsm += _int(spec.get("4_ply_fluting_gsm")) + _int(spec.get("5_ply_fluting_gsm"))
	return gsm


def board_plan(spec, flap_override=None):
	"""Derive the full board plan for ``spec``.

	``spec`` is a plain mapping of the specification's own fieldnames — a
	``frappe`` document works unchanged because ``.get()`` has the same shape.

	Returns a dict that always carries ``ok`` and ``reason``. When ``ok`` is
	False every figure is 0 and ``reason`` is one of the module constants; the
	caller must not store a partial plan.
	"""
	style = str(spec.get("product_type_carton") or "").strip()
	ply = str(spec.get("ply") or "").strip()
	length = _int(spec.get("ctn_length_mm"))
	width = _int(spec.get("ctn_width_mm"))
	height = _int(spec.get("ctn_height_mm"))

	out = {
		"ok": False,
		"reason": "",
		"style": style,
		"flap": 0,
		"blank_width": 0,
		"blank_length": 0,
		"planned_width": 0,
		"planned_length": 0,
		"actual_width": 0,
		"actual_length": 0,
		"total_gsm": 0,
		"weight_g": 0.0,
		"tab": TAB_WIDTH_MM,
		"trim": TRIM_PER_EDGE_MM,
	}

	if str(spec.get("product_type") or "").strip() != CARTON:
		out["reason"] = NOT_CARTON
		return out
	if ply == PLY_SFK:
		out["reason"] = SFK
		return out
	if style == STYLE_DIE_CUT:
		out["reason"] = DIE_CUT
		return out
	if not style:
		out["reason"] = NO_STYLE
		return out

	# A tray has no flaps; everything else does.
	needs_flap = style != STYLE_TRAY
	override = _int(flap_override)
	out["flap"] = override if override > 0 else (auto_flap(width) if needs_flap else 0)

	if length <= 0 or width <= 0 or (needs_flap and (height <= 0 or out["flap"] <= 0)):
		out["reason"] = INCOMPLETE_DIMENSIONS
		return out

	if style == STYLE_TRAY:
		# Corner tabs fold in from the walls, so no joint tab on the length.
		out["blank_width"] = width + 2 * height
		out["blank_length"] = length + 2 * height
	elif style == STYLE_ONE_FLAP:
		out["blank_width"] = height + out["flap"]
		out["blank_length"] = (2 * length) + (2 * width) + TAB_WIDTH_MM
	else:
		# 2 Flap RSC, 3 Flap RSC, and anything else that behaves like an RSC.
		out["blank_width"] = out["flap"] + height + out["flap"]
		out["blank_length"] = (2 * length) + (2 * width) + TAB_WIDTH_MM

	out["planned_width"] = out["blank_width"] + (2 * TRIM_PER_EDGE_MM)
	out["planned_length"] = out["blank_length"] + (2 * TRIM_PER_EDGE_MM)
	out["actual_width"] = out["blank_width"]
	out["actual_length"] = out["blank_length"]
	out["total_gsm"] = total_gsm(spec)
	out["weight_g"] = approximate_weight_grams(
		out["planned_width"], out["planned_length"], out["total_gsm"]
	)
	out["ok"] = True
	return out


def approximate_weight_grams(planned_width_mm, planned_length_mm, gsm):
	"""Board area x GSM. Understated by flute take-up — see the module docstring.

	Struck on the PLANNED size, not the blank: the trim is board that is bought
	and paid for even though it is cut away.
	"""
	area_sq_m = (_int(planned_width_mm) * _int(planned_length_mm)) / 1000000.0
	return round(area_sq_m * _int(gsm), 2)


def revisable_changes(spec, requested, flap_override=None):
	"""The field -> new-value map a revision should apply, and nothing more.

	Takes the specification as it stands and the operator's requested inputs,
	and returns ``(values, reason)``. ``values`` holds only fields whose value
	actually changes, so a revision that changes nothing records nothing.

	``requested`` may carry any of the two real inputs — ``ctn_flap_mm`` and the
	two ``board_*_actual_mm`` overrides — plus the two weights. The derived
	figures are never taken from ``requested``: they are recomputed here, so a
	caller cannot post a board plan that does not follow from the dimensions.

	A flap the record already carries is treated as an override in its own right
	when the caller does not supply one. Without that, revising a specification
	for an unrelated reason would silently reset a hand-measured flap back to
	:func:`auto_flap` — and take the blank, the planned size and the weight with
	it.
	"""
	if not _int(flap_override):
		flap_override = spec.get("ctn_flap_mm")
	plan = board_plan(spec, flap_override=flap_override)
	if not plan["ok"]:
		return {}, plan["reason"]

	proposed = {
		"ctn_flap_mm": plan["flap"],
		"board_width_planned_mm": plan["planned_width"],
		"board_length_planned_mm": plan["planned_length"],
		"approximate_weight_grams": plan["weight_g"],
	}

	# The actuals default to the blank but are the operator's to override, so an
	# explicitly supplied value wins and an omitted one falls back to the blank.
	for field, derived in (
		("board_width_actual_mm", plan["actual_width"]),
		("board_length_actual_mm", plan["actual_length"]),
	):
		supplied = _int(requested.get(field))
		proposed[field] = supplied if supplied > 0 else derived

	# Weights are measurements, never derived. Only carried through when given.
	for field in ("printed_weight", "empty_carton_weight"):
		if requested.get(field) not in (None, ""):
			proposed[field] = float(requested.get(field))

	values = {}
	for field, new in proposed.items():
		old = spec.get(field)
		if isinstance(new, float):
			if round(float(old or 0), 2) != round(new, 2):
				values[field] = new
		elif _int(old) != _int(new):
			values[field] = new

	return values, ""
