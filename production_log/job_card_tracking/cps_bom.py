"""Turning a Customer Product Specification into an ERPNext BOM.

The Frappe-bound half of the job. Every decision that can be made from plain
data lives in :mod:`cps_cp_rules`, which imports nothing from Frappe and is
tested without a bench; this module does the two things that genuinely need a
site — asking the item master what exists, and writing the document.

Item resolution reads ``Item Variant Attribute``. It never parses an item
code, and that is deliberate: the master carries nine duplicate
``-ID-``/``-Rainbow-`` code families for the same physical paper and a
``BLU``/``BLUE`` pair one letter apart, so string matching would eventually
resolve a BOM line onto a zero-stock phantom.
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_cp_rules

ATTR_TYPE = "Type"
ATTR_GSM = "GSM"
ATTR_COLOUR = "Colour"
ATTR_WIDTH = "Reel Width (mm)"
ATTR_COUNTRY = "Country"


def _items_with_attribute(attribute, value, candidates=None):
	"""Item codes carrying ``attribute = value``, optionally within a set.

	Attribute values are stored as strings — every one of these attributes has
	``numeric_values = 0``, so GSM is ``"55"`` and the width is ``"250"``.
	Comparing an int against them silently matches nothing, so the value is
	always stringified here rather than at each call site.
	"""
	filters = {"attribute": attribute, "attribute_value": str(value)}
	if candidates is not None:
		if not candidates:
			return set()
		filters["parent"] = ["in", list(candidates)]

	rows = frappe.get_all(
		"Item Variant Attribute",
		filters=filters,
		fields=["parent"],
		limit_page_length=0,
	)
	return {row["parent"] for row in rows}


def available_reel_widths(type_attr, gsm, colour):
	"""Reel widths stocked for this paper, and the candidates carrying them.

	Returns a tuple of (widths, candidates):
	- widths: reel widths as ints, ascending
	- candidates: item codes carrying these Type/GSM/Colour attributes

	Widths are asked of the item master rather than hardcoded, so the day a
	300mm reel is stocked the 11.7in specs start resolving without a code change.
	"""
	candidates = _items_with_attribute(ATTR_TYPE, type_attr)
	candidates = _items_with_attribute(ATTR_GSM, gsm, candidates)
	candidates = _items_with_attribute(ATTR_COLOUR, colour, candidates)
	if not candidates:
		return [], set()

	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"attribute": ATTR_WIDTH, "parent": ["in", list(candidates)]},
		fields=["attribute_value"],
		limit_page_length=0,
	)

	widths = set()
	for row in rows:
		try:
			widths.add(int(float(row["attribute_value"])))
		except (TypeError, ValueError):
			continue
	return sorted(widths), candidates


def resolve_part_item(part, finished_width_mm):
	"""``(item_code, error)`` for one Colour of Parts row.

	Exactly one of the two is set. The error is a finished sentence naming the
	part and what was sought, because the person who presses the button is not
	the person who knows the item master.
	"""
	number = part.get("part_number")
	paper_type = (part.get("paper_type") or "").strip()
	colour = (part.get("colour") or "").strip()
	gsm = part.get("gsm")

	type_attr = cps_cp_rules.paper_type_attribute(paper_type)
	if not type_attr:
		return None, _(
			"Part {0} is {1}, which cannot be resolved to a reel. Bond is bought by the "
			"ream rather than by weight and is not supported yet."
		).format(number, paper_type or _("blank"))

	widths, candidates = available_reel_widths(type_attr, gsm, colour)
	if not widths:
		return None, _(
			"Part {0} needs {1} / {2} GSM / {3} paper. No item in the master carries that "
			"combination in any reel width."
		).format(number, type_attr, gsm or _("blank"), colour or _("blank"))

	width = cps_cp_rules.reel_width_for(finished_width_mm, widths)
	if not width:
		return None, _(
			"Part {0}: no reel fits a {1} mm form. Stocked widths for {2} / {3} GSM / {4} "
			"are {5} mm. Wider forms are cut from jumbo reels, which is not supported yet."
		).format(number, finished_width_mm, type_attr, gsm or _("blank"), colour or _("blank"),
		         ", ".join(str(w) for w in widths))

	candidates = _items_with_attribute(ATTR_WIDTH, width, candidates)
	candidates = _items_with_attribute(ATTR_COUNTRY, cps_cp_rules.BOM_ORIGIN, candidates)

	if not candidates:
		return None, _(
			"Part {0} needs {1} / {2} GSM / {3} / {4} mm from {5}. No such item exists."
		).format(number, type_attr, gsm or _("blank"), colour or _("blank"), width, cps_cp_rules.BOM_ORIGIN)

	usable = frappe.get_all(
		"Item",
		filters={"name": ["in", list(candidates)], "disabled": 0, "is_stock_item": 1},
		fields=["name"],
		order_by="name",
		limit_page_length=0,
	)

	if not usable:
		return None, _(
			"Part {0}: {1} matches {2} / {3} GSM / {4} / {5} mm from {6}, but it is disabled "
			"or not a stock item."
		).format(number, ", ".join(sorted(candidates)), type_attr, gsm or _("blank"), colour or _("blank"), width,
		         cps_cp_rules.BOM_ORIGIN)

	if len(usable) > 1:
		return None, _(
			"Part {0} matches {1} items — {2}. The item master has duplicates for this "
			"paper; retire one before generating a BOM."
		).format(number, len(usable), ", ".join(row["name"] for row in usable))

	return usable[0]["name"], None
