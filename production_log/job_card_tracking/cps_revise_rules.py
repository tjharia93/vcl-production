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
