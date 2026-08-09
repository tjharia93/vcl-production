# Create BOM from Customer Product Specification — design

**Date:** 2026-08-09 · **Product line:** Computer Paper · **App:** `vcl-production` (`production_log`)
**Status:** design agreed, not built

---

## 1. What this is

A **Create BOM** button on Customer Product Specification that generates the ERPNext BOM which is
today built by hand.

The manual build happened on 2026-08-08 for `CPT-SPEC-00063` (Gilani's Distributors, 9.5 × 8, 2-part)
and produced `BOM-Computer Paper Pre-Printed-9.5 x 8-2 Part-001`:

| Line | Item | Qty | Rate | Amount |
|---|---|---|---|---|
| 1 | `NCR-Reel-250-55-WHI-ID-CB` | 1.3475 Kg | 194.25 | 261.75 |
| 2 | `NCR-Reel-250-55-YLW-ID-CF` | 1.3475 Kg | 180.94 | 243.82 |
| 3 | `COMPUTER PAPER TOP AND BOTTOM` | 1 Nos | 63.00 | 63.00 |
| | | | **Materials** | **568.56** |
| 10 | Printing — Miyakoshi, 7.5 min @ 208.51/hr | | | 26.06 |
| 20 | Collation — Collater, 15 min @ 118.46/hr | | | 29.62 |
| | | | **Operating** | **55.68** |
| | | | **Total / carton** | **624.24** |

That output is the acceptance test: the button must reproduce it from the spec alone.

### Why it matters beyond convenience

The NCR stock reconciliation of 2026-08-09 (`~/projects/ncr_stock_recon/`) established that **ERPNext
has never recorded a single issue of NCR paper** — 27 stock ledger entries, all positive receipts, the
last dated 2025-02-28. The KES 15.9m NCR "balance" is four supplier invoices carried forward untouched
for 17 months.

Production consumption never reaches ERPNext because there is no BOM and no Work Order to carry it.
This button is the first link in the chain that closes that gap. It is not a data-entry shortcut.

---

## 2. Decisions taken

All confirmed by Tanuj on 2026-08-09 unless noted.

| # | Decision | Chosen | Rejected |
|---|---|---|---|
| D1 | Reel width | 9.5in → 250mm. Resolver picks the narrowest tagged reel ≥ finished width, within a tolerance. 11.7in is a one-off and stays unsupported. | Hardcoding a width table; supporting jumbo slitting |
| D2 | Parts & colours | Normalise `colour` to a Link master, resolve to an item at generation time | Direct Item link per part row; hybrid auto-suggest field |
| D3 | Origin | **Indonesia** as standing default; `Item Alternative` covers the rest | Per-spec origin choice; highest-stock-at-runtime |
| D4 | Re-clicking | Create once. If a BOM already exists, the button opens it and generates nothing | Versioned regeneration; update-draft-in-place |
| D5 | Packing carton | One generic item (`COMPUTER PAPER TOP AND BOTTOM`) for all Computer Paper | Per-spec carton field; derive from size |
| D6 | Item master | **Tag the NCR items** with structured fields; do not parse item codes | Parsing item codes at resolve time |

D6 was initially offered as optional. The stock recon independently found nine duplicate
`-ID-`/`-Rainbow-` code families for the same material, a `BLU`/`BLUE` collision one letter apart, and
concluded *"fuzzy matching across this master is unsafe"*. A parser would eventually resolve a BOM line
onto a zero-stock phantom code. Tagging is therefore treated as necessary.

---

## 3. Architecture

Four units, each independently testable:

```
Item master tagging  ──┐
                       ├──> resolver ──> BOM builder ──> button
Paper Colour master  ──┘
```

| Unit | Lives in | Depends on | Frappe? |
|---|---|---|---|
| Item tagging | patch + Custom Fields | — | data only |
| Paper Colour master | new DocType + patch | — | data only |
| Resolver rules | `cps_cp_rules.py` | nothing | **no** — pure, unit-tested |
| Item lookup | `cps_bom.py` | resolver, Item | yes |
| BOM builder | `cps_bom.py` | lookup, CPS | yes |
| Button | Client Script | whitelisted API | yes |

The split matters: every rule that can be decided from plain data stays in `cps_cp_rules.py`, which
imports nothing from Frappe and is tested without a bench (128 tests today). Only the item query and
document creation are Frappe-bound.

---

## 4. Data model changes

### 4.1 Item — four tagging fields

Custom Fields on `Item`, meaningful only for NCR raw materials:

| Field | Type | Example |
|---|---|---|
| `custom_paper_type` | Select: CB / CF / CFB | `CB` |
| `custom_paper_colour` | Link → Paper Colour | `White` |
| `custom_reel_width_mm` | Int | `250` |
| `custom_origin` | Select: China / Indonesia / Korea / Thailand | `Indonesia` |

Backfilled by patch from the existing codes. **Anything ambiguous is left blank and reported, never
guessed** — the `-Rainbow-` duplicates and the legacy origin-less `NCR-250-55-WHI-CB` are expected to
land in that bucket, and an untagged item is simply invisible to the resolver rather than wrongly
matched.

GSM is *not* a new field — `Item.gsm` equivalents already resolve deterministically from coating type
at 250mm (CFB ⇒ 50, CF ⇒ 55, CB ⇒ 55; verified across every 250mm item in the master).

### 4.2 Paper Colour — new master

Small DocType, seeded with the five colours that exist as items: **White, Pink, Blue, Yellow, Green**.

`cps_cp_rules.DEFAULT_PART_COLOURS` also lists Buff, Lilac and Grey. No items exist for those, so they
are seeded `disabled = 1` — present for history, not offered on new specs.

### 4.3 Colour of Parts — colour becomes a Link

`Colour of Parts.colour` changes `Data` → `Link → Paper Colour`.

A patch normalises the existing free text first (`WHITE` / `white` → `White`). Live data confirms both
cases are present (`CPT-SPEC-00063` uppercase, `CPT-SPEC-00038-1` lowercase). The field is `reqd = 1`
today and stays so.

### 4.4 CPS — `linked_bom`

Custom Field on Customer Product Specification, `Link → BOM`, **`allow_on_submit = 1`**.

Submitted specs must be able to receive it — the revise-in-place rule this doctype already follows for
its weight and artwork fields.

---

## 5. The resolver

### 5.1 Reel width (pure rule)

```
reel_width_for(finished_width_mm, available_widths) -> int | None
```

The narrowest available width `w` where `w >= finished_width_mm` **and** `w - finished_width_mm <= 25`.

The tolerance is what makes it safe. Without it, an 11.7in form (297.18mm) would match the 625mm
jumbo — 328mm too wide — and silently produce a BOM consuming a reel nobody slits for that job.

| Form | mm | Result |
|---|---|---|
| 9.5in | 241.3 | **250** (8.7mm trim) |
| 11.7in | 297.18 | **None** — 625 is 328mm wider, correctly rejected |

### 5.2 Part quantities (pure rule)

```
part_quantities(paper_weight_per_set_g, sets_per_carton, parts) -> [kg per part]
```

Total paper = `paper_weight_per_set_g × sets_per_carton`, split by each part's `gsm` share of
`cp_total_gsm`.

For `CPT-SPEC-00063`: 5.39 g × 500 = 2,695 g; each part 55/110 → **1.3475 kg**. Sums to 2.695 kg
against the spec's own `net_product_weight_per_carton_kg` of 2.697.

All inputs are already server-computed and read-only on the CPS. **The BOM never recomputes a weight —
it reads what the spec already proved.**

### 5.3 Item lookup (Frappe-bound)

Exact filtered query on the tagged fields — no string matching:

```
custom_paper_type = <part.paper_type>
custom_paper_colour = <part.colour>
custom_reel_width_mm = <resolved width>
custom_origin = "Indonesia"
disabled = 0
```

Exactly one match → use it. Zero or several → refuse and say which (§7).

**GSM is deliberately not in the filter.** The CPS controller's `_validate_paper_type_and_gsm` already
refuses to save any part outside CB/55, CFB/50 or CF/55 (and the Bond options for a single-part set),
so paper type and GSM cannot disagree on a saved spec — filtering on both would be redundant, and
matching the item's GSM against a value the spec is incapable of getting wrong adds a failure mode
without adding safety.

**The two Bond paper types do not resolve, by design.** `custom_paper_type` offers CB / CF / CFB only.
A single-part spec using `60 GSM Bond` or `70 GSM Bond` has no NCR reel to point at — bond is not
carbonless paper — so it falls into the "resolves to nothing" path in §7 with a message naming the
paper type. `CPT-SPEC-00004` and `CPT-SPEC-00051` are the live cases.

---

## 6. The button

**Client Script** on Customer Product Specification adds a toolbar button *Create BOM*, shown only when:

- `product_type = "Computer Paper"`, and
- `docstatus = 1` (submitted — a draft spec's numbers are not yet final), and
- `linked_item` is set

It calls a whitelisted method:

```python
production_log.job_card_tracking.cps_bom.create_bom_from_cps(cps: str) -> dict
```

which returns `{"bom": <name>, "created": bool}`. The client routes to the BOM either way, so pressing
it twice is harmless.

The BOM it builds:

| Field | Value |
|---|---|
| `item` | `CPS.linked_item` |
| `quantity` / `uom` | 1 / Carton |
| `company` | Vimit Converters Limited |
| paper lines | resolved item, computed kg, `allow_alternative_item = 1` |
| packing line | `COMPUTER PAPER TOP AND BOTTOM`, 1 Nos, `allow_alternative_item = 0` |
| `with_operations` | 1 |
| `routing` | `Computer Paper - Print and Collate` |
| `rm_cost_as_per` | Valuation Rate |
| `docstatus` | **0 — left as draft** |

Draft is deliberate. A BOM is a costing statement; a human looks at cost-per-carton before it becomes
the basis for a Work Order.

### Idempotency (D4)

If `CPS.linked_bom` is set and that BOM exists and is not cancelled, return it with
`created = False`. Otherwise build, then write `linked_bom` back.

`linked_bom` is the only source of truth for "does this spec have a BOM". Searching BOMs by item would
be wrong — several specs share one `linked_item` with different recipes, which is the whole reason
`is_default` is meaningless here.

---

## 7. Failure modes

Every refusal names the row and the reason. **No partial BOM is ever created** — the builder resolves
every line before writing anything.

| Condition | Message |
|---|---|
| Not Computer Paper | Names the product type and that only Computer Paper is supported |
| Draft or cancelled | Says the spec must be submitted first |
| No `linked_item` | Points at the Item field |
| Weights not computed | Names the empty field (`paper_weight_per_set_g` / `sets_per_carton`) |
| No reel width matches | States the finished width and the widths available |
| Part resolves to nothing | Names the part number and the full spec sought — e.g. *"Part 1 needs a 55gsm CB White reel at 250mm from Indonesia; no such item exists"* |
| Part resolves to several | Lists the candidates rather than picking |
| BOM already exists | Not an error — returns it |

Two known live cases will hit the "resolves to nothing" path immediately, and **that is correct
behaviour, not a defect**:

- **CB 55gsm Yellow** — referenced by `CPT-SPEC-00014` (Classic Ironmongers). No CB-Yellow exists in
  the item master, and the 31 Jul physical count shows none in any width or origin.
- **70 GSM Bond White** — referenced by `CPT-SPEC-00004` and `CPT-SPEC-00051`.

---

## 8. Testing

**Pure rules** — `test_cps_cp_rules.py`, plain `unittest`, no bench, matching the existing 128 tests:

- width: 241.3 → 250; 297.18 → None; empty width list → None; exact-fit; tolerance boundary at 25mm
- quantities: the `CPT-SPEC-00063` anchor (1.3475 × 2, sums to 2.695); a 4-part 55/50/50/55 split
  (`CPT-SPEC-00065`, sums to its own 7.079); zero/missing inputs → no quantities rather than zeros

**Frappe-bound** — resolver and builder tested against the live instance before the patch lands, per
the established live-first method. The acceptance test is reproducing
`BOM-Computer Paper Pre-Printed-9.5 x 8-2 Part-001` line for line and cost for cost from
`CPT-SPEC-00063` alone.

---

## 9. Rollout

Follows `skill vcl-frappe-app` and the method used for v9_2 and v9_5:

1. Custom Fields, Paper Colour master and Client Script applied **live first**
2. Mirrored into `fixtures/` — CPS **and** Item Custom Fields are in the `hooks.py` fixtures list, so
   without the fixture edit the next deploy re-imports the old definition and reverts the change
3. Patch series **v9_6**, `pre_model_sync` like every patch in this app
4. **live == fixture == patch verified three ways before commit**
5. Push to `main`; Tanuj deploys. Merging is not deploying — patches only run on migrate.

Patch content: create the fields, seed Paper Colour, backfill Item tags, normalise existing part
colours. All idempotent.

---

## 10. Out of scope

**Phase 2 — `linked_bom` → `Sales Order Item.bom_no`.** `bom_no` is a real native field the
Create-Work-Order-from-Sales-Order flow already reads, so propagating it means a job inherits the right
recipe with nobody choosing from a list of identically-named BOMs. It is the payoff for
multiple-BOMs-per-item, but it touches the order flow and deserves its own pass once BOMs exist.

**Not in this design at all:**

- **Strapping** — dropped on instruction; the route is Printing → Collation only
- **Make-ready / `setup_time`** — not captured; printing is run-time only, which understates short runs
- **Design, films and plates** — one-off per artwork, not per carton. Films are bought from Geeprints,
  who **does not exist as a Supplier**, so that cost cannot be posted at all today
- **Machine cost beyond labour** — `Wages` is populated on the workstations; Electricity, Consumables
  and Rent are empty, so operating cost is labour only
- **Product lines other than Computer Paper** — Carton, Label, ETR and Monobox have different part
  structures and are separate work
- **The NCR stock findings** — parked by decision on 2026-08-09; report preserved at
  `~/projects/ncr_stock_recon/`. They need production output records, which ERPNext does not hold by
  definition, and this project is what will start producing them

---

## 11. Open items

| # | Item | Blocks |
|---|---|---|
| O1 | Miyakoshi 2 and 3 have no `custom_max_speed_per_hour`; only Miyakoshi 01 (4,000/hr) does. Treated as equal for now | Routing accuracy if they differ |
| O2 | Nine Workstations still hold `custom_product_line = "All"`. Legal again after v9_5, but real per-line scheduling would need each tagged | Nothing today |
| O3 | Miyakoshi labour assumes David and Nelson sit in Hillary Nganga's band (20,330/month); only Nganga was looked up | Rate precision |
| O4 | Charles Wandera (23,100) assumed to be the collator operator over Charles Kyalo Mutiso (93,900) | Rate precision |
