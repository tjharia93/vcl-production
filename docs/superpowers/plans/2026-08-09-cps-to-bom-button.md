# Create BOM from CPS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a *Create BOM* button on Customer Product Specification that generates the ERPNext BOM currently built by hand, resolving each paper part to a real Item from existing Item Variant Attribute data.

**Architecture:** Pure decision rules (width, type mapping, quantities) live in `cps_cp_rules.py`, which imports nothing from Frappe and is unit-tested without a bench. A new `cps_bom.py` holds the Frappe-bound half — an attribute query to resolve items, and the BOM builder — exposed as one whitelisted method. A Client Script adds the toolbar button.

**Tech Stack:** Frappe/ERPNext 16 on Frappe Cloud, Python 3.14 live (3.12 locally for the pure tests), plain `unittest`, no bench.

**Design spec:** `docs/superpowers/specs/2026-08-09-cps-to-bom-button-design.md` (rev B, commit `d8ed5e6`). It is the source of truth. Read it before starting.

---

## Global Constraints

- **Deploy contract: Claude pushes code, Tanuj deploys.** Never run `bench`, never `bench migrate`. When a deploy is needed, say "deploy X" and stop.
- **`cps_cp_rules.py` must stay importable without Frappe.** No `import frappe` in it, ever. That is why its 128 tests run with no bench.
- **Patches are the only sanctioned way to change production data.** Do not modify live records over REST.
- **Most patches in this app run `post_model_sync`.** `patches.txt` has BOTH headers: only three legacy entries sit under `[pre_model_sync]`; v9_2 through v9_5 are all under `[post_model_sync]`, which is where a Custom-Field-only patch belongs. (An older note claiming "all pre_model_sync" predates the `[post_model_sync]` header being added and is stale.)
- **Patch series is v9_6** (v9_5 is the last used).
- **CPS Custom Fields and Client Scripts are in the `hooks.py` fixtures list.** Any live change must also be written to `production_log/fixtures/custom_field.json` / `client_script.json`, or the next deploy silently reverts it. This trap bit v9_5.
- **`get_meta` does not return Custom Fields.** Query the `Custom Field` doctype by `dt` + `fieldname`.
- **MCP `sql_query` is dead** on this instance. Child-table doctypes often 403 over REST — read them via their parent document.
- Existing test file: `production_log/job_card_tracking/test_cps_cp_rules.py`, run with
  `python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules` from the repo root. 128 tests pass today; that number must only go up.

---

## Two sequencing findings that override the usual method

**1. The API cannot be a Server Script, so there is a hard deploy gate.**

VCL has two patterns for whitelisted endpoints. `cps_revise` is a **Server Script** (live, no deploy) but runs in `safe_exec`, which forbids `import` — so it could never import `cps_cp_rules`. `approve_cps_price` is **app Python** called by dotted path, which is the pattern this must follow.

Consequence: **the button will not work until Tanuj deploys.** Tasks 1–7 are all code and live config; Task 8 is the acceptance test and can only run after a deploy. This is called out again at the gate.

**2. The `colour` Select must NOT go live before the data is normalised.**

Live data holds `WHITE` and `white`. Frappe validates a Select on save. If the field becomes a Select while rows still hold `WHITE`, **every affected CPS becomes unsaveable** — exactly the v9_5 Workstation freeze, which took a patch to undo.

Consequence: **Task 6 is patch-only and deliberately breaks the live-first habit.** The patch normalises the data *first*, then sets the options, in that order within one `execute()`. Do not apply that field change live.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `production_log/job_card_tracking/cps_cp_rules.py` | *(modify)* pure rules: type map, reel width, part quantities | 1, 2 |
| `production_log/job_card_tracking/test_cps_cp_rules.py` | *(modify)* unit tests for the above | 1, 2 |
| `production_log/job_card_tracking/cps_bom.py` | *(create)* item resolution + BOM builder + whitelisted API | 3, 4 |
| `production_log/patches/v9_6/__init__.py` | *(create)* empty | 5 |
| `production_log/patches/v9_6/add_cps_linked_bom.py` | *(create)* `linked_bom` Custom Field | 5 |
| `production_log/patches/v9_6/normalise_part_colours.py` | *(create)* normalise colour data, then set Select options | 6 |
| `production_log/patches.txt` | *(modify)* register both patches under `[pre_model_sync]` | 5, 6 |
| `production_log/fixtures/custom_field.json` | *(modify)* mirror `linked_bom` and the `colour` change | 5, 6 |
| `production_log/fixtures/client_script.json` | *(modify)* mirror the new Client Script | 7 |

---

### Task 1: Paper-type map and reel-width rule

**Files:**
- Modify: `production_log/job_card_tracking/cps_cp_rules.py`
- Test: `production_log/job_card_tracking/test_cps_cp_rules.py`

**Interfaces:**
- Consumes: `_text` and `_int` helpers already in `cps_cp_rules.py`
- Produces:
  - `PAPER_TYPE_TO_ATTRIBUTE: dict[str, str]`
  - `REEL_WIDTH_TOLERANCE_MM: int = 25`
  - `BOM_ORIGIN: str = "Indonesia"`
  - `paper_type_attribute(paper_type) -> str | None`
  - `reel_width_for(finished_width_mm, available_widths) -> int | None`

- [ ] **Step 1: Write the failing tests**

Append to `test_cps_cp_rules.py`, just above `class TestSaveBlockOrdering`:

```python
class TestPaperTypeAttribute(unittest.TestCase):
	def test_the_three_coating_types_map_to_attribute_values(self):
		self.assertEqual(r.paper_type_attribute("CB"), "Coated Back")
		self.assertEqual(r.paper_type_attribute("CF"), "Coated Front")
		self.assertEqual(r.paper_type_attribute("CFB"), "Coated Front and Back")

	def test_bond_does_not_map(self):
		# Bond is deferred to v2: bought by Ream, and BOND 70 GSM carries no
		# attributes at all, so there is nothing for the resolver to match on.
		self.assertIsNone(r.paper_type_attribute("60 GSM Bond"))
		self.assertIsNone(r.paper_type_attribute("70 GSM Bond"))

	def test_unknown_and_blank_return_none_rather_than_guessing(self):
		for value in ("Litho", "", None, "cb"):
			self.assertIsNone(r.paper_type_attribute(value), value)


class TestReelWidthFor(unittest.TestCase):
	WIDTHS = [250, 625, 750]

	def test_the_9_5_inch_anchor(self):
		# 9.5in = 241.3mm, run on a 250mm reel: 8.7mm of trim.
		self.assertEqual(r.reel_width_for(241.3, self.WIDTHS), 250)

	def test_11_7_inch_finds_nothing_rather_than_matching_a_jumbo(self):
		# 297.18mm. 625 fits "wider than" but is 328mm too wide - it is a jumbo
		# nobody slits for this job. Deferred to v2; must refuse, not guess.
		self.assertIsNone(r.reel_width_for(297.18, self.WIDTHS))

	def test_narrowest_wins_when_several_fit(self):
		self.assertEqual(r.reel_width_for(241.3, [250, 260, 270]), 250)

	def test_exact_fit_is_accepted(self):
		self.assertEqual(r.reel_width_for(250, self.WIDTHS), 250)

	def test_tolerance_boundary(self):
		# Exactly 25mm over is in; a hair more is out.
		self.assertEqual(r.reel_width_for(225, [250]), 250)
		self.assertIsNone(r.reel_width_for(224.9, [250]))

	def test_no_widths_or_no_size_returns_none(self):
		self.assertIsNone(r.reel_width_for(241.3, []))
		self.assertIsNone(r.reel_width_for(0, self.WIDTHS))
		self.assertIsNone(r.reel_width_for(None, self.WIDTHS))
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/tanujharia/projects/worktrees/cps-artwork-tracker
python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules -v 2>&1 | tail -20
```

Expected: FAIL — `AttributeError: module ... has no attribute 'paper_type_attribute'`

- [ ] **Step 3: Implement**

In `cps_cp_rules.py`, add after the `LINKED_ITEM_FIELD` / `ITEM_GROUP_PRINT_TYPE` block near the top:

```python
# --- BOM generation: turning a part row into a real Item -------------------
#
# The NCR reels are already ERPNext variants of `NCR-Reel` and carry Type, GSM,
# Colour, Reel Width (mm) and Country as Item Attribute values. The resolver
# reads those; it must never parse an item code. The master holds nine
# duplicate `-ID-`/`-Rainbow-` code families and a `BLU`/`BLUE` pair one letter
# apart, so any string matching would eventually resolve onto the wrong item.

# The CPS says CB / CF / CFB; the Item Attribute says the words. Three entries,
# stated rather than derived, because a wrong guess here picks the wrong paper.
PAPER_TYPE_TO_ATTRIBUTE = {
	"CB": "Coated Back",
	"CF": "Coated Front",
	"CFB": "Coated Front and Back",
}

# The standing origin for a generated BOM line. Every other origin is reachable
# at issue time through Item Alternative, so this decides the default only.
BOM_ORIGIN = "Indonesia"

# How much wider than the finished form a reel may be and still be the right
# reel. 9.5in (241.3mm) runs on a 250mm reel, so 8.7mm of trim is real; 25mm is
# a judgement wide enough to admit that and narrow enough to exclude a 625mm
# jumbo, which is 328mm over and is slit down rather than run as-is.
REEL_WIDTH_TOLERANCE_MM = 25


def paper_type_attribute(paper_type):
	"""The Item Attribute ``Type`` value for a CPS paper type, or None.

	Blank, unknown and the two Bond types all return None. Bond is not a
	coating at all — it is uncoated stock bought by the ream — so there is no
	NCR reel for it to name, and returning None sends it to the "cannot
	resolve" path rather than silently onto a coated reel.
	"""
	return PAPER_TYPE_TO_ATTRIBUTE.get(_text(paper_type))


def reel_width_for(finished_width_mm, available_widths):
	"""The reel width to run a form of ``finished_width_mm`` on, or None.

	The narrowest available width that is at least as wide as the form and no
	more than :data:`REEL_WIDTH_TOLERANCE_MM` wider.

	The upper bound is the whole point. Without it a 297.18mm form would match
	a 625mm jumbo — technically "wide enough" — and the BOM would call for a
	reel the floor never puts on that machine. Refusing is the correct answer
	until the jumbo-slitting case is designed.
	"""
	try:
		width = float(finished_width_mm)
	except (TypeError, ValueError):
		return None
	if width <= 0:
		return None

	fits = []
	for candidate in available_widths or []:
		try:
			value = float(candidate)
		except (TypeError, ValueError):
			continue
		if width <= value <= width + REEL_WIDTH_TOLERANCE_MM:
			fits.append(value)

	if not fits:
		return None
	return int(min(fits))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules 2>&1 | tail -4
```

Expected: `OK`, 137 tests (128 + 9 new).

- [ ] **Step 5: Commit**

```bash
git add production_log/job_card_tracking/cps_cp_rules.py production_log/job_card_tracking/test_cps_cp_rules.py
git commit -m "feat(cps): paper-type attribute map and reel-width rule

Two pure rules for BOM generation. paper_type_attribute maps the CPS's
CB/CF/CFB onto the Item Attribute Type values; Bond and anything unknown
return None so they reach the cannot-resolve path rather than a wrong reel.

reel_width_for takes the narrowest reel that fits within 25mm of the form.
The upper bound is what stops a 297mm form matching a 625mm jumbo, which is
wide enough on paper and wrong in the factory."
```

---

### Task 2: Part quantities

**Files:**
- Modify: `production_log/job_card_tracking/cps_cp_rules.py`
- Test: `production_log/job_card_tracking/test_cps_cp_rules.py`

**Interfaces:**
- Consumes: `_int`, `part()` test helper (already defined at the top of the test file)
- Produces: `part_quantities(paper_weight_per_set_g, sets_per_carton, parts) -> list[float]` — kg per part, same order as `parts`, `[]` when inputs are incomplete

- [ ] **Step 1: Write the failing tests**

Append to `test_cps_cp_rules.py` after `class TestReelWidthFor`:

```python
class TestPartQuantities(unittest.TestCase):
	def test_the_gilanis_anchor(self):
		# CPT-SPEC-00063: 5.39 g/set x 500 sets = 2,695 g, split 55/55.
		# Reproduces the 1.3475 kg lines built by hand on 2026-08-08.
		parts = [part(1, "CB", 55), part(2, "CF", 55)]
		qtys = r.part_quantities(5.39, 500, parts)
		self.assertEqual(qtys, [1.3475, 1.3475])
		self.assertAlmostEqual(sum(qtys), 2.695, places=4)

	def test_a_four_part_set_splits_by_gsm_not_evenly(self):
		# CPT-SPEC-00065: 55/50/50/55 = 210 total, 14.16 g/set x 500 sets.
		parts = [part(1, "CB", 55), part(2, "CFB", 50),
		         part(3, "CFB", 50), part(4, "CF", 55)]
		qtys = r.part_quantities(14.16, 500, parts)
		self.assertAlmostEqual(sum(qtys), 7.08, places=2)
		# The 50gsm plies draw less than the 55gsm ones.
		self.assertGreater(qtys[0], qtys[1])
		self.assertEqual(qtys[0], qtys[3])
		self.assertEqual(qtys[1], qtys[2])

	def test_incomplete_inputs_give_nothing_rather_than_zeros(self):
		parts = [part(1, "CB", 55), part(2, "CF", 55)]
		self.assertEqual(r.part_quantities(0, 500, parts), [])
		self.assertEqual(r.part_quantities(5.39, 0, parts), [])
		self.assertEqual(r.part_quantities(None, 500, parts), [])
		self.assertEqual(r.part_quantities(5.39, 500, []), [])

	def test_parts_with_no_gsm_give_nothing(self):
		# Dividing by a zero total would raise; refuse instead.
		self.assertEqual(r.part_quantities(5.39, 500, [part(1, "CB", 0)]), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules -v 2>&1 | tail -20
```

Expected: FAIL — `AttributeError: ... has no attribute 'part_quantities'`

- [ ] **Step 3: Implement**

Add to `cps_cp_rules.py` directly below `reel_width_for`:

```python
def part_quantities(paper_weight_per_set_g, sets_per_carton, parts):
	"""Kilograms of paper per part for one carton, in ``parts`` order.

	The carton's whole paper weight is ``paper_weight_per_set_g x
	sets_per_carton``, and each ply takes its share of that by GSM. Both inputs
	are already computed and stored on the specification, so this reads what
	the spec proved rather than deriving a weight a second way — the two could
	then disagree, and the spec is the one production reads.

	The share is taken against the sum of the parts' own GSM rather than the
	stored ``cp_total_gsm``. They are the same number on a valid record, and
	using the parts keeps the split internally consistent even if the stored
	total is stale.

	Returns ``[]`` — not a list of zeros — when anything needed is missing. A
	zero quantity is a claim that the job consumes no paper; an empty list is
	the honest "this cannot be computed", and the caller refuses on it.
	"""
	try:
		per_set = float(paper_weight_per_set_g)
		sets = float(sets_per_carton)
	except (TypeError, ValueError):
		return []

	rows = _rows(parts)
	if per_set <= 0 or sets <= 0 or not rows:
		return []

	gsms = [_int(_get(row, "gsm"), 0) for row in rows]
	total_gsm = sum(gsms)
	if total_gsm <= 0:
		return []

	total_kg = (per_set * sets) / 1000.0
	# 4 dp is what the BOM Item qty field carries and what the hand-built BOM
	# stored; rounding here keeps the generated document byte-identical to it.
	return [round(total_kg * (gsm / total_gsm), 4) for gsm in gsms]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules 2>&1 | tail -4
```

Expected: `OK`, 141 tests (137 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add production_log/job_card_tracking/cps_cp_rules.py production_log/job_card_tracking/test_cps_cp_rules.py
git commit -m "feat(cps): part_quantities - kg per ply for one carton

Splits the carton's paper weight across plies by GSM share. Anchored on
CPT-SPEC-00063, which reproduces the 1.3475 kg lines built by hand, and on
the 4-part CPT-SPEC-00065 to prove the split is by GSM rather than even.

Returns [] rather than zeros when inputs are incomplete: a zero quantity
claims the job consumes no paper, an empty list says it cannot be computed,
and only the second is true."
```

---

### Task 3: Resolve a part to an Item

**Files:**
- Create: `production_log/job_card_tracking/cps_bom.py`

**Interfaces:**
- Consumes: `cps_cp_rules.paper_type_attribute`, `.reel_width_for`, `.BOM_ORIGIN`
- Produces:
  - `ATTR_TYPE`, `ATTR_GSM`, `ATTR_COLOUR`, `ATTR_WIDTH`, `ATTR_COUNTRY` — attribute-name constants
  - `available_reel_widths(type_attr, gsm, colour) -> list[int]`
  - `resolve_part_item(part, finished_width_mm) -> tuple[str | None, str | None]` — `(item_code, error_message)`; exactly one is non-None

- [ ] **Step 1: Create the module**

```python
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
	"""Reel widths stocked for this paper, as ints, ascending.

	Asked of the item master rather than hardcoded, so the day a 300mm reel is
	stocked the 11.7in specs start resolving without a code change.
	"""
	candidates = _items_with_attribute(ATTR_TYPE, type_attr)
	candidates = _items_with_attribute(ATTR_GSM, gsm, candidates)
	candidates = _items_with_attribute(ATTR_COLOUR, colour, candidates)
	if not candidates:
		return []

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
	return sorted(widths)


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

	widths = available_reel_widths(type_attr, gsm, colour)
	if not widths:
		return None, _(
			"Part {0} needs {1} / {2} GSM / {3} paper. No item in the master carries that "
			"combination in any reel width."
		).format(number, type_attr, gsm, colour)

	width = cps_cp_rules.reel_width_for(finished_width_mm, widths)
	if not width:
		return None, _(
			"Part {0}: no reel fits a {1} mm form. Stocked widths for {2} / {3} GSM / {4} "
			"are {5} mm. Wider forms are cut from jumbo reels, which is not supported yet."
		).format(number, finished_width_mm, type_attr, gsm, colour,
		         ", ".join(str(w) for w in widths))

	candidates = _items_with_attribute(ATTR_TYPE, type_attr)
	candidates = _items_with_attribute(ATTR_GSM, gsm, candidates)
	candidates = _items_with_attribute(ATTR_COLOUR, colour, candidates)
	candidates = _items_with_attribute(ATTR_WIDTH, width, candidates)
	candidates = _items_with_attribute(ATTR_COUNTRY, cps_cp_rules.BOM_ORIGIN, candidates)

	if not candidates:
		return None, _(
			"Part {0} needs {1} / {2} GSM / {3} / {4} mm from {5}. No such item exists."
		).format(number, type_attr, gsm, colour, width, cps_cp_rules.BOM_ORIGIN)

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
		).format(number, ", ".join(sorted(candidates)), type_attr, gsm, colour, width,
		         cps_cp_rules.BOM_ORIGIN)

	if len(usable) > 1:
		return None, _(
			"Part {0} matches {1} items — {2}. The item master has duplicates for this "
			"paper; retire one before generating a BOM."
		).format(number, len(usable), ", ".join(row["name"] for row in usable))

	return usable[0]["name"], None
```

- [ ] **Step 2: Verify it imports and stays Frappe-free where it must**

```bash
cd /home/tanujharia/projects/worktrees/cps-artwork-tracker
python3 -m py_compile production_log/job_card_tracking/cps_bom.py && echo "COMPILES"
grep -c "^import frappe" production_log/job_card_tracking/cps_cp_rules.py
```

Expected: `COMPILES`, then `0` — `cps_cp_rules.py` must still import no Frappe.

- [ ] **Step 3: Re-run the pure tests to confirm nothing regressed**

```bash
python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules 2>&1 | tail -4
```

Expected: `OK`, 141 tests (137 + 4 new).

- [ ] **Step 4: Commit**

```bash
git add production_log/job_card_tracking/cps_bom.py
git commit -m "feat(cps): resolve a Colour of Parts row to a real Item

Reads Item Variant Attribute - Type, GSM, Colour, Reel Width (mm), Country -
and never parses an item code. The master holds nine duplicate -ID-/-Rainbow-
families and a BLU/BLUE pair one letter apart, so string matching would
eventually pick a zero-stock phantom.

Attribute values are stringified before comparison: all five attributes have
numeric_values = 0, so GSM is the string '55' and an int comparison silently
matches nothing.

Stocked widths are asked of the master rather than hardcoded, so a 300mm reel
appearing in stock makes 11.7in specs resolve with no code change."
```

---

### Task 4: Build the BOM, and expose the button's endpoint

**Files:**
- Modify: `production_log/job_card_tracking/cps_bom.py`

**Interfaces:**
- Consumes: `resolve_part_item` (Task 3), `cps_cp_rules.part_quantities` (Task 2)
- Produces: `create_bom_from_cps(cps: str) -> dict` with keys `bom` (str) and `created` (bool). Whitelisted; called by dotted path from the Client Script.

- [ ] **Step 1: Append the builder**

```python
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


@frappe.whitelist()
def create_bom_from_cps(cps):
	"""Create the draft BOM for a Computer Paper specification.

	Returns ``{"bom": <name>, "created": <bool>}``. Pressing the button twice
	is harmless: the second press returns the first BOM with ``created`` False.

	Every part is resolved before anything is written, so a specification that
	cannot be fully resolved leaves no half-built document behind.
	"""
	spec = frappe.get_doc("Customer Product Specification", cps)
	spec.check_permission("read")

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

	bom = frappe.new_doc("BOM")
	bom.item = spec.linked_item
	bom.company = frappe.defaults.get_user_default("Company") or spec.get("company")
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
```

- [ ] **Step 2: Verify it compiles**

```bash
python3 -m py_compile production_log/job_card_tracking/cps_bom.py && echo "COMPILES"
```

Expected: `COMPILES`

- [ ] **Step 3: Commit**

```bash
git add production_log/job_card_tracking/cps_bom.py
git commit -m "feat(cps): create_bom_from_cps - build the draft BOM

Resolves every part before writing anything, so a spec that cannot be fully
resolved leaves no half-built document. Left as a draft deliberately: a BOM
is a costing statement and a human should see cost-per-carton before it
becomes the basis for a Work Order.

Idempotency reads linked_bom rather than searching BOMs by item. Several
specs share one linked_item with different colour recipes - the reason
is_default is meaningless here - so a search by item would return another
customer's recipe."
```

---

### Task 5: `linked_bom` Custom Field — live, fixture, patch

**Files:**
- Create: `production_log/patches/v9_6/__init__.py` (empty)
- Create: `production_log/patches/v9_6/add_cps_linked_bom.py`
- Modify: `production_log/patches.txt`
- Modify: `production_log/fixtures/custom_field.json`

**Interfaces:**
- Produces: Custom Field `Customer Product Specification-linked_bom`, consumed by `cps_bom._existing_bom`

- [ ] **Step 1: Create the field live**

Use the MCP tools. `allow_on_submit` is essential — every CPS this runs on is already submitted.

```
mcp__vcl-erpnext__create_doc  doctype="Custom Field"  payload={
  "dt": "Customer Product Specification",
  "fieldname": "linked_bom",
  "label": "Linked BOM",
  "fieldtype": "Link",
  "options": "BOM",
  "insert_after": "linked_item",
  "allow_on_submit": 1,
  "read_only": 1,
  "depends_on": "eval:doc.product_type=='Computer Paper'",
  "description": "The BOM generated from this specification. Set by the Create BOM button; several specifications share one Item with different recipes, so this is what tells them apart."
}
```

- [ ] **Step 2: Verify it exists live**

`get_meta` does not return Custom Fields — query the doctype:

```
mcp__vcl-erpnext__list_docs  doctype="Custom Field"
  filters=[["dt","=","Customer Product Specification"],["fieldname","=","linked_bom"]]
  fields=["name","fieldtype","options","allow_on_submit","read_only"]
```

Expected: one row, `fieldtype` Link, `options` BOM, `allow_on_submit` 1.

- [ ] **Step 3: Write the patch**

`production_log/patches/v9_6/add_cps_linked_bom.py`:

```python
"""Patch v9_6: the ``linked_bom`` field on Customer Product Specification.

Records which BOM was generated from a specification. It is not a
convenience: several specifications share one ``linked_item`` with different
colour recipes — ``Computer Paper Pre-Printed-9.5 x 8-2 Part`` serves
Gilani's White/Yellow, Classic Ironmongers Yellow/White reversed and two
Mikeline White/Pink specs — so ``is_default`` on the BOM cannot say which
recipe belongs to which job, and searching by item would return somebody
else's.

``allow_on_submit`` because every specification this will ever run on is
already submitted; the same revise-in-place rule this doctype follows for its
weight and artwork fields.

Read-only on the form: it is written by the Create BOM button, and a hand-typed
value would point a job at the wrong recipe with no way to tell.

Also mirrored into ``fixtures/custom_field.json``. CPS Custom Fields are in the
``fixtures`` list in ``hooks.py``, so the fixture is what a deploy applies —
without it the next migrate would drop this field.

Idempotent: ``create_custom_fields`` inserts what is absent and reconciles what
is present.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_cp_rules

_COMPUTER_PAPER_ONLY = "eval:doc.product_type=='{0}'".format(cps_cp_rules.COMPUTER_PAPER)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache(doctype="Customer Product Specification")


def get_custom_fields():
	return {
		"Customer Product Specification": [
			{
				"fieldname": "linked_bom",
				"label": "Linked BOM",
				"fieldtype": "Link",
				"options": "BOM",
				"insert_after": "linked_item",
				"allow_on_submit": 1,
				"read_only": 1,
				"depends_on": _COMPUTER_PAPER_ONLY,
				"description": (
					"The BOM generated from this specification. Set by the Create BOM "
					"button; several specifications share one Item with different "
					"recipes, so this is what tells them apart."
				),
			},
		],
	}
```

- [ ] **Step 4: Register the patch**

Append to `production_log/patches.txt`, under `[pre_model_sync]`, after the v9_5 line:

```
# The BOM generated from a specification. Not a convenience: several specs
# share one linked_item with different colour recipes, so is_default on the
# BOM cannot say which recipe belongs to which job.
production_log.patches.v9_6.add_cps_linked_bom
```

- [ ] **Step 5: Mirror into the fixture**

Export the live field into `fixtures/custom_field.json`. Read the live record and insert it in the same shape as its neighbours, keeping the file's existing key ordering and indentation:

```bash
cd /home/tanujharia/projects/worktrees/cps-artwork-tracker
python3 -c "
import json
d = json.load(open('production_log/fixtures/custom_field.json'))
print('linked_bom in fixture:',
      any(r.get('fieldname') == 'linked_bom' for r in d))
"
```

Expected after the edit: `True`.

- [ ] **Step 6: Verify live == fixture == patch**

```bash
python3 - <<'EOF'
import ast, json
src = open('production_log/patches/v9_6/add_cps_linked_bom.py').read()
tree = ast.parse(src)
fx = json.load(open('production_log/fixtures/custom_field.json'))
row = [r for r in fx if r.get('fieldname') == 'linked_bom'][0]
print('fixture fieldtype:', row['fieldtype'], '| options:', row['options'],
      '| allow_on_submit:', row['allow_on_submit'])
EOF
```

Compare all three against the live query from Step 2. They must agree on `fieldtype`, `options` and `allow_on_submit`.

- [ ] **Step 7: Commit**

```bash
git add production_log/patches/v9_6/ production_log/patches.txt production_log/fixtures/custom_field.json
git commit -m "feat(cps): linked_bom field, live + fixture + patch v9_6

Records which BOM came from which specification. Several specs share one
linked_item with different colour recipes, so is_default on the BOM cannot
say which recipe belongs to which job and a search by item would return
somebody else's.

allow_on_submit because every spec this runs on is already submitted.
Read-only because a hand-typed value would point a job at the wrong recipe.

Mirrored into fixtures/custom_field.json - CPS custom fields are in the
hooks.py fixtures list, so without it the next deploy drops the field."
```

---

### Task 6: Normalise part colours, then make `colour` a Select

**Files:**
- Create: `production_log/patches/v9_6/normalise_part_colours.py`
- Modify: `production_log/patches.txt`
- Modify: `production_log/fixtures/custom_field.json`

> **This task deliberately does NOT follow the live-first method.** `colour`
> holds `WHITE` and `white` in live data. Frappe validates a Select on save, so
> changing the field to a Select while those values are stored makes every
> affected CPS **unsaveable** — the exact v9_5 Workstation freeze. Data must be
> normalised first, and data may only be changed by a patch. So both halves live
> in one patch, in order, and neither is applied live by hand.

**Interfaces:**
- Consumes: the live `Colour` Item Attribute values
- Produces: `Colour of Parts.colour` as a Select

- [ ] **Step 1: Check what the live data actually holds**

`Colour of Parts` is a child table and 403s over REST, so read it through its parents:

```
mcp__vcl-erpnext__get_doc  doctype="Customer Product Specification"  name="CPT-SPEC-00063"
mcp__vcl-erpnext__get_doc  doctype="Customer Product Specification"  name="CPT-SPEC-00038-1"
```

Expected: `00063` holds `WHITE` / `YELLOW`, `00038-1` holds `white` / `pink` — both cases present, confirming the freeze risk is real.

- [ ] **Step 2: Write the patch**

`production_log/patches/v9_6/normalise_part_colours.py`:

```python
"""Patch v9_6: normalise part colours, then constrain the field to a Select.

Order matters and is the whole point of this patch.

``Colour of Parts.colour`` is free text and the live estate holds both
``WHITE`` (CPT-SPEC-00063) and ``white`` (CPT-SPEC-00038-1). Frappe validates
a Select against its options on every save, so turning the field into a Select
while those values are stored would make every affected specification
**unsaveable** — not read-only, unsaveable, with an error naming the allowed
values and no hint that the stored one used to be legal.

That is not hypothetical: it is exactly what v9_5 had to undo on Workstation,
where narrowing a Select's options without migrating the rows froze nine
records.

So the data is normalised first and the options are set second, in one
``execute()``. Neither half is applied live by hand.

The canonical spellings come from the live ``Colour`` Item Attribute — the same
master the BOM resolver matches against — so the specification and the item
master cannot drift into two vocabularies.

Idempotent: rows already canonical are skipped, and re-setting identical
options is a no-op.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

COLOUR_ATTRIBUTE = "Colour"
CHILD_DOCTYPE = "Colour of Parts"
FIELDNAME = "colour"


def execute():
	options = _canonical_colours()
	if not options:
		return

	_normalise_existing(options)
	_constrain_field(options)

	frappe.clear_cache(doctype=CHILD_DOCTYPE)


def _canonical_colours():
	"""The Colour Item Attribute's values, in their stored order."""
	if not frappe.db.exists("Item Attribute", COLOUR_ATTRIBUTE):
		return []
	attr = frappe.get_doc("Item Attribute", COLOUR_ATTRIBUTE)
	return [row.attribute_value for row in attr.item_attribute_values if row.attribute_value]


def _normalise_existing(options):
	"""Rewrite stored colours to canonical casing.

	Matched case-insensitively and trimmed. A value that matches nothing is
	left exactly as it is — it will fail the Select on its next save, which is
	the correct outcome for a colour nobody stocks, and silently rewriting it
	to something plausible would be inventing data.
	"""
	canonical = {value.strip().lower(): value for value in options}

	rows = frappe.get_all(
		CHILD_DOCTYPE,
		fields=["name", FIELDNAME],
		limit_page_length=0,
	)
	for row in rows:
		stored = (row.get(FIELDNAME) or "").strip()
		if not stored:
			continue
		target = canonical.get(stored.lower())
		if target and target != row.get(FIELDNAME):
			frappe.db.set_value(
				CHILD_DOCTYPE, row["name"], FIELDNAME, target, update_modified=False
			)


def _constrain_field(options):
	create_custom_fields(
		{
			CHILD_DOCTYPE: [
				{
					"fieldname": FIELDNAME,
					"label": "Colour",
					"fieldtype": "Select",
					"options": "\n".join(options),
					"reqd": 1,
					"in_list_view": 1,
					"description": (
						"Pre-tinted paper colour, not print ink. The list is the Colour "
						"Item Attribute, which is what the BOM resolver matches against."
					),
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
```

- [ ] **Step 3: Register the patch**

Append to `production_log/patches.txt` under `[pre_model_sync]`, directly after the `add_cps_linked_bom` line:

```
# Normalise part colours to the Colour Item Attribute's spellings, THEN make
# the field a Select. Order matters: live data holds both WHITE and white, and
# constraining the field first would freeze every spec holding the wrong case -
# the same failure v9_5 had to undo on Workstation.
production_log.patches.v9_6.normalise_part_colours
```

- [ ] **Step 4: Mirror the field into the fixture**

Add the `Colour of Parts-colour` Custom Field entry to `fixtures/custom_field.json` with the same options string the patch writes.

```bash
python3 -c "
import json
d = json.load(open('production_log/fixtures/custom_field.json'))
rows = [r for r in d if r.get('dt') == 'Colour of Parts' and r.get('fieldname') == 'colour']
print('rows:', len(rows))
print('options:', repr(rows[0]['options']) if rows else 'MISSING')
"
```

Expected: `rows: 1`, options containing `White`, `Pink`, `Blue`, `Yellow`, `Green`, `Red`, `Black`.

- [ ] **Step 5: Verify the patch compiles and tests still pass**

```bash
python3 -m py_compile production_log/patches/v9_6/normalise_part_colours.py && echo "COMPILES"
python3 -m unittest production_log.job_card_tracking.test_cps_cp_rules 2>&1 | tail -4
```

Expected: `COMPILES`, then `OK` with 145 tests.

- [ ] **Step 6: Commit**

```bash
git add production_log/patches/v9_6/normalise_part_colours.py production_log/patches.txt production_log/fixtures/custom_field.json
git commit -m "feat(cps): normalise part colours, then constrain to a Select

Order is the point. colour is free text and live data holds both WHITE and
white. Frappe validates a Select on save, so constraining the field first
would make every affected spec unsaveable - the same freeze v9_5 had to undo
on Workstation, where narrowing options without migrating rows froze nine
records.

Data is normalised first and options set second, in one execute(), and
neither half is applied live by hand - which is why this task deliberately
departs from the live-first method used elsewhere in this series.

Canonical spellings come from the Colour Item Attribute, the same master the
BOM resolver matches against, so spec and item master cannot drift apart. A
colour matching nothing is left alone rather than rewritten to something
plausible."
```

---

### Task 7: The Create BOM button

**Files:**
- Modify: `production_log/fixtures/client_script.json`

**Interfaces:**
- Consumes: `production_log.job_card_tracking.cps_bom.create_bom_from_cps`

- [ ] **Step 1: Create the Client Script live**

Follows the `CPS Price Approval Toolbar` pattern — a dotted app path, not a Server Script name.

```
mcp__vcl-erpnext__create_doc  doctype="Client Script"  payload={
  "name": "CPS — Create BOM Button",
  "dt": "Customer Product Specification",
  "view": "Form",
  "enabled": 1,
  "script": "<the script below>"
}
```

```javascript
frappe.ui.form.on("Customer Product Specification", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;
        if (frm.doc.product_type !== "Computer Paper") return;
        if (!frm.doc.linked_item) return;

        if (frm.doc.linked_bom) {
            frm.add_custom_button(__("Open BOM"), () => {
                frappe.set_route("Form", "BOM", frm.doc.linked_bom);
            }, __("BOM"));
            return;
        }

        frm.add_custom_button(__("Create BOM"), () => {
            frappe.confirm(
                __("Build a draft BOM for {0} from this specification? Nothing is submitted — you will see the cost per carton before anything uses it.", [frm.doc.linked_item]),
                () => frappe.call({
                    method: "production_log.job_card_tracking.cps_bom.create_bom_from_cps",
                    args: { cps: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Resolving parts and building the BOM…"),
                    callback(r) {
                        const m = (r && r.message) || {};
                        if (!m.bom) return;
                        frm.reload_doc();
                        frappe.show_alert({
                            message: m.created
                                ? __("BOM {0} created as a draft.", [m.bom])
                                : __("This specification already has BOM {0}.", [m.bom]),
                            indicator: "green",
                        }, 7);
                        frappe.set_route("Form", "BOM", m.bom);
                    },
                })
            );
        }, __("BOM")).addClass("btn-primary");
    },
});
```

- [ ] **Step 2: Verify it exists live**

```
mcp__vcl-erpnext__list_docs  doctype="Client Script"
  filters=[["dt","=","Customer Product Specification"],["name","like","%Create BOM%"]]
  fields=["name","dt","view","enabled"]
```

Expected: one row, `enabled` 1, `view` Form.

- [ ] **Step 3: Mirror into the fixture**

Add the script to `fixtures/client_script.json` alongside the four existing CPS scripts.

```bash
python3 -c "
import json
d = json.load(open('production_log/fixtures/client_script.json'))
names = [r['name'] for r in d if r.get('dt') == 'Customer Product Specification']
print(names)
"
```

Expected: five names, including `CPS — Create BOM Button`.

- [ ] **Step 4: Commit**

```bash
git add production_log/fixtures/client_script.json
git commit -m "feat(cps): Create BOM toolbar button

Follows the CPS Price Approval Toolbar pattern - a dotted app path to a
whitelisted method, not a Server Script. The builder has to import
cps_cp_rules and safe_exec forbids imports, so a Server Script was never an
option and the endpoint must be deployed app Python.

Shows Create BOM when there is none and Open BOM when there is, so the button
is never a way to make a second one. Gated on Computer Paper, submitted, and
an Item being linked - the three things the endpoint would refuse anyway,
refused earlier where the user can see why."
```

---

### ⛔ DEPLOY GATE

**Everything above is code and live configuration. The button cannot work until Frappe Cloud runs a deploy and migrate**, because `create_bom_from_cps` is app Python and the two v9_6 patches only run on migrate.

- [ ] **Step 1: Push**

```bash
git push origin main
git log --oneline -7
```

- [ ] **Step 2: Hand over and stop**

Tell Tanuj: **"Deploy `vcl-production` on Frappe Cloud — app code plus migrate. The Create BOM button and the two v9_6 patches need it."**

Do not proceed to Task 8 until he confirms the deploy is done. Do not run `bench` or `bench migrate`.

---

### Task 8: Acceptance — reproduce the hand-built BOM

**Files:** none — verification only.

- [ ] **Step 1: Confirm the patches actually ran**

Do not trust the Patch Log; verify the effect (installing an app marks patches done without running them).

```
mcp__vcl-erpnext__list_docs  doctype="Custom Field"
  filters=[["dt","=","Customer Product Specification"],["fieldname","=","linked_bom"]]
  fields=["name","fieldtype","options"]

mcp__vcl-erpnext__get_doc  doctype="Customer Product Specification"  name="CPT-SPEC-00038-1"
```

Expected: the field exists; `00038-1`'s parts now read `White` / `Pink` in canonical casing.

- [ ] **Step 2: Clear the hand-built BOM out of the way**

`CPT-SPEC-00063` already has `BOM-Computer Paper Pre-Printed-9.5 x 8-2 Part-001` from 2026-08-08, built by hand and still a draft. The generated BOM must be compared against it, not confused with it.

Ask Tanuj whether to delete the hand-built draft first or generate alongside it. **Do not delete it unilaterally** — it is the reference the acceptance test is measured against, and it is the only record of the manual working.

- [ ] **Step 3: Run the button's endpoint on the pilot spec**

```
mcp__vcl-erpnext__run_method  dotted_path="production_log.job_card_tracking.cps_bom.create_bom_from_cps"
  kwargs={"cps": "CPT-SPEC-00063"}
```

Expected: `{"bom": "BOM-Computer Paper Pre-Printed-9.5 x 8-2 Part-00X", "created": true}`

- [ ] **Step 4: Compare it line for line against the hand-built BOM**

```
mcp__vcl-erpnext__get_doc  doctype="BOM"  name="<the new BOM>"
```

Every one of these must match:

| Field | Expected |
|---|---|
| `items[0].item_code` | `NCR-Reel-250-55-WHI-ID-CB` |
| `items[0].qty` | `1.3475` |
| `items[1].item_code` | `NCR-Reel-250-55-YLW-ID-CF` |
| `items[1].qty` | `1.3475` |
| `items[2].item_code` | `COMPUTER PAPER TOP AND BOTTOM` |
| `items[2].qty` | `1` |
| `raw_material_cost` | `568.5628` |
| `operating_cost` | `55.67875` |
| `total_cost` | `624.24155` |
| `with_operations` | `1` |
| `routing` | `Computer Paper - Print and Collate` |
| `allow_alternative_item` (both paper lines) | `1` |
| `docstatus` | `0` |

Any mismatch is a failure. Report the exact difference rather than adjusting the expectation to fit.

- [ ] **Step 5: Verify idempotency**

Run Step 3 again, unchanged.

Expected: `{"bom": "<the same name>", "created": false}` — and no second BOM in the list.

- [ ] **Step 6: Verify the three refusals, which are live specs not hypotheticals**

```
run_method ... {"cps": "CPT-SPEC-00014"}   # Classic Ironmongers - CB 55gsm Yellow
run_method ... {"cps": "CPT-SPEC-00004"}   # 70 GSM Bond
run_method ... {"cps": "CPT-SPEC-00024"}   # 11.7in
```

Expected, in order:
- `00014` — names Part 1 and says no item carries Coated Back / 55 GSM / Yellow in any width
- `00004` — names the part and says Bond is bought by the ream and is not supported yet
- `00024` — names the 297.18mm form and lists the stocked widths

Each must throw, and **no BOM may be created for any of them.** Confirm by listing BOMs for their `linked_item` afterwards.

- [ ] **Step 7: Look at the button in the browser**

A clean API result says nothing about whether the button renders. Open `CPT-SPEC-00063` in Desk and confirm the *Open BOM* button appears under the BOM group (since `linked_bom` is now set), and that a spec without a BOM shows *Create BOM* instead.

If the browser tooling is unavailable, **say so plainly rather than implying it was checked.**

- [ ] **Step 8: Report**

Summarise: what matched, what did not, what was verified in the browser versus by API, and anything left open. Do not claim the acceptance test passed unless every row in Step 4 matched.

---

## Self-review

**Spec coverage** — §4.1 colour Select → Task 6. §4.2 packing carton as configuration → Task 4 (`PACKING_ITEM`). §4.3 `linked_bom` → Task 5. §5.1 width rule → Task 1. §5.2 quantities → Task 2. §5.3 attribute lookup incl. the string-comparison trap and the Type map → Tasks 1, 3. §6 button and idempotency → Tasks 4, 7. §7 every failure mode → Tasks 3, 4, verified in Task 8 Step 6. §8 testing → Tasks 1, 2 and Task 8. §9 rollout, live == fixture == patch → Tasks 5, 6, 7 and the deploy gate. §10 out of scope — Bond and 11.7in are refusals, not features, verified in Task 8.

**Type consistency** — `paper_type_attribute`, `reel_width_for`, `part_quantities`, `resolve_part_item`, `available_reel_widths`, `create_bom_from_cps`, `PACKING_ITEM`, `DEFAULT_ROUTING`, `LINKED_BOM_FIELD` are each defined once and used with the same names and signatures throughout.

**Known gap, stated rather than hidden:** Tasks 3 and 4 are Frappe-bound and cannot be executed until the deploy gate. Their only verification before that point is `py_compile` and review. That is a real limitation of the deploy contract, not an oversight — it is why the acceptance test is a task of its own and why the gate is explicit.
