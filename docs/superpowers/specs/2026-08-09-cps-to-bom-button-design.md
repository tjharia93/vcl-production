# Create BOM from Customer Product Specification — design

**Date:** 2026-08-09 · **Product line:** Computer Paper · **App:** `vcl-production` (`production_log`)
**Status:** design agreed, not built
**Revision:** rev B — supersedes rev A of the same date after review comments on the PDF

---

## Revision note

Rev A proposed adding four custom fields to the Item master and creating a Paper Colour DocType.
**Both were unnecessary.** Review comment: *"Can we not use the default colour doctype?"* — and the
answer is yes. `Colour` already exists as an **Item Attribute**, and every NCR reel is already a variant
of `NCR-Reel` carrying `Colour`, `GSM`, `Reel Width (mm)`, `Country` and `Type` as attribute values.

Rev A's entire §1 (item tagging), its Paper Colour master and its backfill patch are deleted. The
resolver reads `Item Variant Attribute` instead. That was the largest single piece of work in the plan.

Also from review: Bond deferred to v2 (§10), the packing carton made configurable rather than literal
(§4.2), and the 11.7in width case confirmed as a v2 problem (§10).

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

Confirmed by Tanuj on 2026-08-09.

| # | Decision | Chosen | Rejected |
|---|---|---|---|
| D1 | Reel width | 9.5in → 250mm, via a tolerance rule (§5.1). 11.7in refuses — see D7 | Hardcoding a width table |
| D2 | Parts & colours | Normalise `colour` to a controlled value, resolve to an item at generation time | Direct Item link per part row; hybrid auto-suggest field |
| D3 | Origin | **Indonesia** as standing default; `Item Alternative` covers the rest | Per-spec origin choice; highest-stock-at-runtime |
| D4 | Re-clicking | Create once. If a BOM already exists, the button opens it and generates nothing | Versioned regeneration; update-draft-in-place |
| D5 | Packing carton | One carton for all Computer Paper, held as **configuration not code** so it can change without a deploy | Per-spec carton field; derive from size |
| D6 | Item identification | **Use the existing `Item Variant Attribute` data.** No new fields, no new master, no backfill | Adding custom fields (rev A); parsing item codes |
| D7 | Bond, and 11.7in | **Deferred to v2.** Both refuse with a clear message in v1 | Supporting them now |

### Why D6 changed

Rev A argued for tagging because parsing item codes is unsafe — the stock recon found nine duplicate
`-ID-`/`-Rainbow-` code families and a `BLU`/`BLUE` collision one letter apart. **That reasoning still
holds: the resolver must never parse an item code.** What changed is that the structured data already
exists, so tagging was solving a solved problem.

Verified on `NCR-Reel-250-55-WHI-ID-CB`:

```
variant_of: NCR-Reel   variant_based_on: Item Attribute
  Reel Width (mm) = 250      GSM = 55       Colour = White
  Country = Indonesia        Type = Coated Back
```

---

## 3. Architecture

```
Item Variant Attribute (existing) ──> resolver ──> BOM builder ──> button
```

| Unit | Lives in | Depends on | Frappe? |
|---|---|---|---|
| Resolver rules | `cps_cp_rules.py` | nothing | **no** — pure, unit-tested |
| Item lookup | `cps_bom.py` | resolver, Item Variant Attribute | yes |
| BOM builder | `cps_bom.py` | lookup, CPS | yes |
| Button | Client Script | whitelisted API | yes |

Every rule decidable from plain data stays in `cps_cp_rules.py`, which imports nothing from Frappe and
is tested without a bench (128 tests today). Only the attribute query and document creation are
Frappe-bound.

---

## 4. Data model changes

Far smaller than rev A. **Nothing on Item changes at all.**

### 4.1 Colour of Parts — `colour` becomes controlled

`colour` is `Data` today and holds both `WHITE` and `white` in live data (`CPT-SPEC-00063` uppercase,
`CPT-SPEC-00038-1` lowercase). It becomes a **Select**, options seeded from the live `Colour` Item
Attribute values: White, Pink, Blue, Yellow, Green, Red, Black.

`Item Attribute Value` is a child table (`istable = 1`) and therefore cannot be a Link target — a
Select is the closest native equivalent. The Item Attribute remains the single source of truth; the
Select is seeded from it by patch and re-seeding is idempotent.

A patch normalises existing values to the canonical casing first (`WHITE` → `White`). The field is
`reqd = 1` today and stays so.

### 4.2 Packing carton — configuration, not a literal

Held as a setting rather than hardcoded in the builder, so *"in the future we can change it"* needs no
deploy. Default `COMPUTER PAPER TOP AND BOTTOM`, 1 Nos per carton.

### 4.3 CPS — `linked_bom`

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

The tolerance is what keeps v1 safe. Without it, an 11.7in form (297.18mm) would match the 625mm
jumbo — 328mm too wide — and silently produce a BOM consuming a reel nobody slits for that job.

| Form | mm | Result |
|---|---|---|
| 9.5in | 241.3 | **250** (8.7mm trim) |
| 11.7in | 297.18 | **None** — 625 is 328mm wider, correctly rejected (v2, D7) |

The 25mm figure is a judgement, not a measurement: the only real data point is 250 − 241.3 = 8.7mm. It
is wide enough to admit the one real case and narrow enough to exclude every jumbo. Revisit with §10's
11.7in work.

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

This rule assumes the material is bought by weight. Bond is bought by **Ream**, which is why it is
deferred (D7, §10).

### 5.3 Item lookup (Frappe-bound)

Query `Item Variant Attribute` for items whose attribute values all match, then intersect:

| Attribute | From | Example |
|---|---|---|
| `Type` | part `paper_type`, mapped | `CB` → `Coated Back` |
| `GSM` | part `gsm` | `55` |
| `Colour` | part `colour` | `White` |
| `Reel Width (mm)` | §5.1 | `250` |
| `Country` | D3 constant | `Indonesia` |

Two details that matter:

- **`Type` needs a map.** The CPS says `CB` / `CF` / `CFB`; the attribute says `Coated Back` /
  `Coated Front` / `Coated Front and Back`. A three-entry constant in `cps_cp_rules.py`, not a guess.
- **Attribute values are strings.** All five attributes have `numeric_values = 0`, so `GSM` is `"55"`
  and `Reel Width (mm)` is `"250"`. Compare as strings, or normalise both sides — do not assume ints.

**GSM is filtered on, not inferred.** Rev A argued coating type determines GSM (CFB⇒50, CF⇒55, CB⇒55)
and skipped the field. That inference happens to hold across every 250mm item today but would break
silently the day a 53gsm CFB is stocked — and `NCR-Reel-250-53-WHITE-CFB` already exists, unstocked.
Since GSM is right there as an attribute, filter on it.

Candidates are then narrowed to `disabled = 0` and `is_stock_item = 1`. Exactly one → use it. Zero or
several → refuse and say which (§7).

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

returning `{"bom": <name>, "created": bool}`. The client routes to the BOM either way, so pressing it
twice is harmless.

The BOM it builds:

| Field | Value |
|---|---|
| `item` | `CPS.linked_item` |
| `quantity` / `uom` | 1 / Carton |
| `company` | Vimit Converters Limited |
| paper lines | resolved item, computed kg, `allow_alternative_item = 1` |
| packing line | configured carton (§4.2), 1 Nos, `allow_alternative_item = 0` |
| `with_operations` | 1 |
| `routing` | `Computer Paper - Print and Collate` |
| `rm_cost_as_per` | Valuation Rate |
| `docstatus` | **0 — left as draft** |

Draft is deliberate. A BOM is a costing statement; a human looks at cost-per-carton before it becomes
the basis for a Work Order.

### Idempotency (D4)

If `CPS.linked_bom` is set and that BOM exists and is not cancelled, return it with `created = False`.
Otherwise build, then write `linked_bom` back.

`linked_bom` is the only source of truth for "does this spec have a BOM". Searching BOMs by item would
be wrong — several specs share one `linked_item` with different recipes, which is the whole reason
`is_default` is meaningless here.

---

## 7. Failure modes

Every refusal names the row and the reason. **No partial BOM is ever created** — the builder resolves
every line before writing anything.

| Condition | Message |
|---|---|
| Not Computer Paper | Names the product type; only Computer Paper is supported |
| Draft or cancelled | Says the spec must be submitted first |
| No `linked_item` | Points at the Item field |
| Weights not computed | Names the empty field (`paper_weight_per_set_g` / `sets_per_carton`) |
| No reel width matches | States the finished width and the widths available; notes 11.7in is not yet supported |
| **Bond paper type** | Names the part and says Bond is not yet supported — it is bought by Ream, not weight (D7) |
| Part resolves to nothing | Names the part and the full spec sought — e.g. *"Part 1 needs Coated Back / 55 GSM / White / 250mm / Indonesia; no such item"* |
| Part resolves to several | Lists the candidates rather than picking |
| BOM already exists | Not an error — returns it |

Known live cases that will refuse, **correctly**:

- **CB 55gsm Yellow** — `CPT-SPEC-00014` (Classic Ironmongers). No CB-Yellow exists in the item master,
  and the 31 Jul physical count found none in any width or origin.
- **70 GSM Bond** — `CPT-SPEC-00004`, `CPT-SPEC-00051`. Deferred (D7).
- **11.7in** — `CPT-SPEC-00024`. Deferred (D7).

---

## 8. Testing

**Pure rules** — `test_cps_cp_rules.py`, plain `unittest`, no bench, matching the existing 128 tests:

- width: 241.3 → 250; 297.18 → None; empty width list → None; exact fit; the 25mm boundary
- type map: CB/CF/CFB → the three attribute values; an unknown type → None rather than a wrong guess
- quantities: the `CPT-SPEC-00063` anchor (1.3475 × 2, sums to 2.695); a 4-part 55/50/50/55 split
  (`CPT-SPEC-00065`, sums to its own 7.079); zero/missing inputs → no quantities rather than zeros

**Frappe-bound** — resolver and builder tested against the live instance before the patch lands, per
the established live-first method. The acceptance test is reproducing
`BOM-Computer Paper Pre-Printed-9.5 x 8-2 Part-001` line for line and cost for cost from
`CPT-SPEC-00063` alone.

---

## 9. Rollout

Follows `skill vcl-frappe-app` and the method used for v9_2 and v9_5:

1. Custom Field (`linked_bom`), the `colour` Select and the Client Script applied **live first**
2. Mirrored into `fixtures/` — CPS Custom Fields are in the `hooks.py` fixtures list, so without the
   fixture edit the next deploy re-imports the old definition and reverts the change
3. Patch series **v9_6**, under `[post_model_sync]` like v9_2–v9_5
4. **live == fixture == patch verified three ways before commit**
5. Push to `main`; Tanuj deploys. Merging is not deploying — patches only run on migrate.

Patch content: add `linked_bom`, seed the `colour` Select from the Colour Item Attribute, normalise
existing part colours to canonical casing. All idempotent. **No Item records are touched.**

---

## 10. Out of scope

**v2 — explicitly picked up later:**

- **Bond paper** (D7). Bought by **Ream**, not weight, so §5.2's kg-by-gsm-share rule does not apply;
  needs a sheets → reams derivation. `BOND 70 GSM` also carries **no attributes at all** (it is not a
  variant) and no colour, so the §5.3 resolver cannot see it. Both must be solved together.
- **11.7in forms** (D1, D7). 297.18mm has no stocked reel; whether it is slit from a jumbo or bought at
  its own width is unresolved, and the answer changes the quantity maths.
- **`linked_bom` → `Sales Order Item.bom_no`.** `bom_no` is a real native field the
  Create-Work-Order-from-Sales-Order flow already reads, so propagating it means a job inherits the
  right recipe without anyone choosing from a list of identically-named BOMs. The payoff for
  multiple-BOMs-per-item, but it touches the order flow and deserves its own pass.

**Not planned:**

- **Strapping** — dropped on instruction; the route is Printing → Collation only
- **Make-ready / `setup_time`** — not captured; printing is run-time only, which understates short runs
- **Design, films and plates** — one-off per artwork, not per carton. Films are bought from Geeprints,
  who **does not exist as a Supplier**, so that cost cannot be posted at all today
- **Machine cost beyond labour** — `Wages` is populated on the workstations; Electricity, Consumables
  and Rent are empty, so operating cost is labour only
- **Product lines other than Computer Paper** — Carton, Label, ETR and Monobox have different part
  structures and are separate work
- **The NCR stock findings** — parked 2026-08-09; report at `~/projects/ncr_stock_recon/`. They need
  production output records, which ERPNext does not hold by definition, and this project is what will
  start producing them

---

## 11. Open items

| # | Item | Blocks |
|---|---|---|
| O1 | Miyakoshi 2 and 3 have no `custom_max_speed_per_hour`; only Miyakoshi 01 (4,000/hr) does. Treated as equal | Routing accuracy if they differ |
| O2 | Nine Workstations still hold `custom_product_line = "All"`. Legal again after v9_5, but real per-line scheduling would need each tagged | Nothing today |
| O3 | Miyakoshi labour assumes David and Nelson sit in Hillary Nganga's band (20,330/month); only Nganga was looked up | Rate precision |
| O4 | Charles Wandera (23,100) assumed to be the collator operator over Charles Kyalo Mutiso (93,900) | Rate precision |
| O5 | The `-ID-`/`-Rainbow-` families are one material under two codes. **Issue-time substitution is already covered** — all nine pairs are registered as two-way `Item Alternative`s (verified 2026-08-09, including the `BLU`/`BLUE` pair), so a Work Order nominating the `-ID-` item can consume Rainbow stock. What alternatives do *not* cover is **buying and valuation**: the open POs sit on the Rainbow codes, so future receipts land there while the BOM continues to cost at the `-ID-` rate, and a shortage calculation against `-ID-` will not see Rainbow as supply. The real fix is retiring one code family — item-master hygiene, not BOM work | BOM cost accuracy over time; not correctness today |
