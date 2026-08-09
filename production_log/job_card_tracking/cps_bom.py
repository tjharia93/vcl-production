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


# The packing carton, held here rather than inline so it can be changed
# without touching the builder. One carton serves every Computer Paper job:
# it is a telescoping two-piece box, and the other carton items in the master
# are legacy or customer-specific.
PACKING_ITEM = "COMPUTER PAPER TOP AND BOTTOM"
PACKING_QTY = 1

DEFAULT_ROUTING = "Computer Paper - Print and Collate"
LINKED_BOM_FIELD = "linked_bom"


def _existing_bom(spec):
	"""The BOM this spec already has, or None.

	Read from ``linked_bom`` rather than searched by item. Several
	specifications share one ``linked_item`` with different colour recipes —
	that is the whole reason ``is_default`` is meaningless here — so finding a
	BOM by item would happily return another customer's recipe.
	"""
	name = spec.get(LINKED_BOM_FIELD)
	if not name:
		return None
	if not frappe.db.exists("BOM", name):
		return None
	if frappe.db.get_value("BOM", name, "docstatus") == 2:
		return None
	return name


def _company_for(item_code):
	"""The company this BOM belongs to.

	Read from the Item's own defaults rather than the acting user's default
	company. The site carries four companies, so keying off the user would
	put the BOM in whichever books that person happens to default to — and
	a BOM in the wrong company does not look wrong until its cost surfaces
	somewhere nobody expected.
	"""
	company = frappe.db.get_value(
		"Item Default", {"parent": item_code, "parenttype": "Item"}, "company"
	)
	return company or frappe.defaults.get_user_default("Company")


@frappe.whitelist()
def create_bom_from_cps(cps):
	"""Create the draft BOM for a Computer Paper specification.

	Returns ``{"bom": <name>, "created": <bool>}``. Pressing the button twice
	is harmless: the second press returns the first BOM with ``created`` False.

	Every part is resolved before anything is written, so a specification that
	cannot be fully resolved leaves no half-built document behind.
	"""
	spec = frappe.get_doc("Customer Product Specification", cps)
	# Write, not read: this function stamps linked_bom onto the spec via
	# db_set below, which writes straight to the database and bypasses
	# document-level permission checks. Gating on read would let a user who
	# cannot edit this spec through the form cause a field write on it here.
	spec.check_permission("write")

	if spec.product_type != cps_cp_rules.COMPUTER_PAPER:
		frappe.throw(_(
			"{0} is a {1} specification. Only Computer Paper can generate a BOM today."
		).format(spec.name, spec.product_type))

	if spec.docstatus != 1:
		frappe.throw(_(
			"{0} is {1}. Submit the specification before generating a BOM — its weights "
			"are not final until then."
		).format(spec.name, _("still a draft") if spec.docstatus == 0 else _("cancelled")))

	if not spec.get("linked_item"):
		frappe.throw(_(
			"{0} has no Item linked. The BOM is built for that Item, so it must be set first."
		).format(spec.name))

	existing = _existing_bom(spec)
	if existing:
		return {"bom": existing, "created": False}

	parts = [
		{
			"part_number": row.part_number,
			"paper_type": row.paper_type,
			"gsm": row.gsm,
			"colour": row.colour,
		}
		for row in (spec.colour_of_parts or [])
	]

	quantities = cps_cp_rules.part_quantities(
		spec.get("paper_weight_per_set_g"), spec.get("sets_per_carton"), parts
	)
	if not quantities:
		frappe.throw(_(
			"{0} has no computed paper weight. Paper Weight per Set and Sets per Carton "
			"must both be set before a BOM can be built."
		).format(spec.name))

	resolved, errors = [], []
	for row, qty in zip(parts, quantities):
		item_code, error = resolve_part_item(row, spec.get("finished_width_mm"))
		if error:
			errors.append(error)
		else:
			resolved.append((item_code, qty))

	if errors:
		frappe.throw("<br>".join(errors), title=_("Cannot build the BOM"))

	company = _company_for(spec.linked_item)
	if not company:
		frappe.throw(_(
			"{0} has no default company set for Item {1}, and the acting user has no "
			"default company either. Set one before a BOM can be built."
		).format(spec.name, spec.linked_item))

	bom = frappe.new_doc("BOM")
	bom.item = spec.linked_item
	bom.company = company
	bom.quantity = 1
	bom.uom = frappe.db.get_value("Item", spec.linked_item, "stock_uom")
	bom.rm_cost_as_per = "Valuation Rate"
	bom.is_active = 1
	bom.is_default = 1
	bom.allow_alternative_item = 1

	for item_code, qty in resolved:
		bom.append("items", {
			"item_code": item_code,
			"qty": qty,
			"uom": frappe.db.get_value("Item", item_code, "stock_uom"),
			"allow_alternative_item": 1,
		})

	bom.append("items", {
		"item_code": PACKING_ITEM,
		"qty": PACKING_QTY,
		"uom": frappe.db.get_value("Item", PACKING_ITEM, "stock_uom"),
		"allow_alternative_item": 0,
	})

	if frappe.db.exists("Routing", DEFAULT_ROUTING):
		bom.with_operations = 1
		bom.routing = DEFAULT_ROUTING
		for op in frappe.get_doc("Routing", DEFAULT_ROUTING).operations:
			bom.append("operations", {
				"sequence_id": op.sequence_id,
				"operation": op.operation,
				"workstation": op.workstation,
				"time_in_mins": op.time_in_mins,
				"hour_rate": op.hour_rate,
				"description": op.description,
			})

	bom.insert()

	spec.db_set(LINKED_BOM_FIELD, bom.name, update_modified=False)

	return {"bom": bom.name, "created": True}
