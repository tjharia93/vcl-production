"""Pure rules for the colour, packing and price sections of a CPS revision.

No Frappe import, so these are unit testable without a bench. ``cps_revise``
applies them; it owns every write.

On an update-after-submit Frappe does not run ``validate()``, so each rule here
is the only guard on its field. Add a revisable field and its rule together.
"""

# Product types that carry print inks at all (the Print Colours section).
INK_PRODUCT_TYPES = ("Computer Paper", "Label", "Carton", "ETR (Reel to Reel Printing)")

PROCESS_INKS = ("uses_c", "uses_m", "uses_y", "uses_k")

PRINT_TYPE_PLAIN = "Plain"
PRINT_TYPE_PRINTED = "Printed"

# Packing fields a revision may touch, per product type: field -> kind.
# "text" is a Data field, "number" a non-negative Int/Float.
_COMMON_PACKING = {"standard_packing": "text"}
PACKING_FIELDS = {
	"Computer Paper": {
		**_COMMON_PACKING,
		"sets_per_carton": "number",
		"packing_carton_tare_kg": "number",
		"print_weight_allowance_pct": "number",
	},
	"Carton": {**_COMMON_PACKING, "standard_weight_per_carton": "number"},
	"Label": {"packing_up": "text", "packing_pieces": "number"},
}


def packing_fields(product_type):
	"""The packing fields a revision may change on this product type."""
	return dict(PACKING_FIELDS.get(product_type, _COMMON_PACKING))


def ink_error(print_type, process_count, spot_count):
	"""Why an ink set is unusable for this print type, or None.

	Same two rules as ``cps_cp_rules.colour_block_reason``: Printed needs at
	least one ink, Plain can carry none. Restated here because that function is
	a save-time transition rule and does not run on update-after-submit.
	"""
	total = process_count + spot_count
	if print_type == PRINT_TYPE_PRINTED and total == 0:
		return (
			"A Printed specification must record at least one print colour: tick a "
			"process ink or add a spot colour."
		)
	if print_type == PRINT_TYPE_PLAIN and total > 0:
		return (
			"A Plain specification cannot carry print inks. Change the print type to "
			"Printed first, or leave the inks empty."
		)
	return None


def coerce_packing(field, kind, value):
	"""``(clean_value, error)`` for one packing entry."""
	if kind == "text":
		return (str(value).strip() if value is not None else ""), None
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None, "{0} must be a number.".format(field)
	if number < 0:
		return None, "{0} cannot be negative.".format(field)
	return (int(number) if number == int(number) else number), None


def price_row_error(row):
	"""Why a proposed price row is unusable, or None."""
	if not row.get("valid_from"):
		return "A price needs an Effective From date."
	if not row.get("uom"):
		return "A price needs a unit of measure."
	try:
		rate = float(row.get("rate"))
	except (TypeError, ValueError):
		return "A price needs a rate."
	if rate <= 0:
		return "The rate must be greater than zero."
	return None


# ── Carton size and build ────────────────────────────────────────────────────
#
# What a carton IS: its three dimensions and the board it is made of. Revising
# these changes the carton itself, so every one is checked here and the board
# plan is re-derived from the result by the caller.

LAYER_MATERIALS = ("Test Liner", "Kraft", "White Test Liner")

# field -> ("int", None) or ("select", allowed values). A select may be blank
# only where the doctype allows it; required selects are in BUILD_REQUIRED.
CARTON_BUILD_FIELDS = {
	"ctn_length_mm": ("int", None),
	"ctn_width_mm": ("int", None),
	"ctn_height_mm": ("int", None),
	"idod": ("select", ("", "ID", "OD")),
	"product_type_carton": ("select", ("", "Tray", "Die Cut", "1 Flap RSC", "2 Flap RSC", "3 Flap RSC")),
	"ply": ("select", ("SFK", "3", "5")),
	"flute_type": ("select", ("B", "C", "E")),
	"joint_type": ("select", ("", "Gluing - Manual", "Gluing - Machine", "Stitched")),
	"1_ply_top_layer_gsm": ("int", None),
	"1_ply_top_layer_material": ("select", ("",) + LAYER_MATERIALS),
	"2_ply_fluting_gsm": ("int", None),
	"2_ply_top_layer_material": ("select", ("",) + LAYER_MATERIALS),
	"3_ply_bottom_gsm": ("int", None),
	"3_ply_top_layer_material": ("select", ("",) + LAYER_MATERIALS),
	"4_ply_fluting_gsm": ("int", None),
	"4_ply_top_layer_material": ("select", ("",) + LAYER_MATERIALS),
	"5_ply_fluting_gsm": ("int", None),
	"5_ply_top_layer_material": ("select", ("",) + LAYER_MATERIALS),
}

# Any of these changing moves the blank, so the board plan must be re-derived.
GEOMETRY_FIELDS = ("ctn_length_mm", "ctn_width_mm", "ctn_height_mm", "product_type_carton", "ply")
# These move the auto flap; a flap measured for the old carton no longer applies.
FLAP_FIELDS = ("ctn_width_mm", "product_type_carton")

LAYER_GSM_FIELDS = ("1_ply_top_layer_gsm", "2_ply_fluting_gsm", "3_ply_bottom_gsm", "4_ply_fluting_gsm", "5_ply_fluting_gsm")


def coerce_build(field, value):
	"""``(clean_value, error)`` for one size/build entry."""
	if field not in CARTON_BUILD_FIELDS:
		return None, "{0} is not part of a carton's size or build.".format(field)
	kind, allowed = CARTON_BUILD_FIELDS[field]
	if kind == "int":
		try:
			number = float(value if value not in (None, "") else 0)
		except (TypeError, ValueError):
			return None, "{0} must be a whole number.".format(field)
		if number < 0 or number != int(number):
			return None, "{0} must be a whole number, not negative.".format(field)
		return int(number), None
	text = str(value or "").strip()
	if text not in allowed:
		return None, "{0}: '{1}' is not one of {2}.".format(field, text, ", ".join(a for a in allowed if a))
	return text, None


def active_layers(ply):
	"""The GSM fields a board of this ply actually has (same as total_gsm)."""
	ply = str(ply or "").strip()
	if ply == "5":
		return LAYER_GSM_FIELDS
	if ply == "3":
		return LAYER_GSM_FIELDS[:3]
	return LAYER_GSM_FIELDS[:2]


def build_error(spec):
	"""Why the size/build of ``spec`` (after the revision) is unusable, or None.

	The same rules ``validate_carton`` and the form enforce, restated because
	validate() does not run on update-after-submit — plus a GSM on every layer
	the board has, since the weight is struck from them.
	"""
	ply = str(spec.get("ply") or "").strip()
	if not ply:
		return "Ply is required for a carton."
	if not str(spec.get("flute_type") or "").strip():
		return "Flute Type is required for a carton."
	if int(spec.get("ctn_length_mm") or 0) <= 0:
		return "Carton Length (mm) must be greater than 0."
	if int(spec.get("ctn_width_mm") or 0) <= 0:
		return "Carton Width (mm) must be greater than 0."
	if ply != "SFK" and int(spec.get("ctn_height_mm") or 0) <= 0:
		return "Carton Height (mm) must be greater than 0 unless Ply is SFK."
	for field in active_layers(ply):
		if int(spec.get(field) or 0) <= 0:
			return "A {0}-ply board needs a GSM on layer {1}.".format(ply, field[0])
	return None


def job_size_text(length, width, height, ply):
	"""The Job Size the carton specs are written with: ``L X W X H``."""
	if str(ply or "").strip() == "SFK" or not int(height or 0):
		return "{0} X {1}".format(int(length or 0), int(width or 0))
	return "{0} X {1} X {2}".format(int(length or 0), int(width or 0), int(height or 0))
