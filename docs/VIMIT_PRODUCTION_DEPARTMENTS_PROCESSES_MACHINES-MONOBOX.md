# Vimit Converters Ltd — Production Departments, Processes & Machines

**Status:** Working Master
**Department 04:** Monobox (Custom Printed Folding Cartons, with Window)
**Last Updated:** 01 September 2026

> Fourth in the series, after Computer Paper, Carton and Labels. This department is
> the **newest and the best modelled in ERPNext** — and, as at this date, the least
> used. Both facts are recorded below.

---

# 1. Department Scope

This department makes **custom-printed monoboxes, typically with a clear window**,
from **flat duplex board** — not corrugated.

Until 5 August 2026 this was **the only VCL product line running entirely
off-system**: no CPS type, no job card, no production tracking. No route was
recorded, no waste or yield captured, output could not be tied to an order, and film
consumption was estimated rather than known.

## What a monobox is not

**Job Card Carton cannot absorb this product.** Its stage list is
corrugated-specific (Corrugated → Pasting → Creasing/Slitting → Printing → Slotting
→ Stitching → Bundling) and its specification fields — flute type, ply count, liner
materials — are meaningless for flat board. A monobox has **no ply and no flute at
all**.

The reverse trap matters just as much:

> **2-ply coffee cup sleeves are CARTON, not Monobox.**
> Single-face corrugated = `ply = SFK` + `flute = E` + `product_type_carton = Die Cut`.
> They are die-cut on the same flatbed tooling, which is exactly why they get
> misfiled. The test is the material, not the tool.

## The structural difference from Departments 01–03

| Department | Shape |
|---|---|
| **01 — Computer Paper** | One machine pass, many inline capabilities |
| **02 — Carton** | Serial ladder of fixed stations, WIP between each |
| **03 — Labels** | One inline press pass → parallel bank of six rewind stations |
| **04 — Monobox** | **Serial sheet-fed route where the route itself is genuinely variable job to job** |

Carton's route varies a little; monobox's varies a lot. Coating and window patching
are real either/or decisions taken per job, not per product family. That is why the
route is explicit data here, and why this is the one department where **per-stage
capture is already structured in ERPNext**.

---

# 2. Machines & Capabilities

**This department has no equipment register.** That is the single largest gap in
this document, and it is stated plainly rather than filled with guesses.

`VCL Production Machine` carries six entries under department **Monobox**:

| Entry | What it actually is |
|---|---|
| Board Prep & Printing | A **stage**, not a machine |
| Coating | A stage |
| Die-cutting & Stripping | A stage |
| Window Patching | A stage |
| Folding & Gluing | A stage |
| Bundling & Packing | A stage |

These were seeded so the Production Floor board could accept monobox entries. They
name the **six stages of the route**, not physical equipment.

**⚠ CONFIRM — the whole machine picture:**
- Which press prints monobox board? The department has no press of its own, so this
  is presumably shared with Offset / General Printing (Kord, Solna, Miller) — **not
  asserted here**.
- Which machine die-cuts? Flatbed work implies a platen — plausibly a Bobst — but
  the same open question sits in the Carton document and should be answered once for
  both.
- Is window patching manual or machine?
- Is folding & gluing manual, machine, or both? The carton side distinguishes
  *Gluing - Manual* from *Gluing - Machine*; monobox does not yet.
- Is coating done in-house or bought out?

Until these are answered, monobox capacity cannot be planned, only recorded.

---

# 3. Production Architecture

```text
                        DEPARTMENT
                            |
                  Duplex Board — SHEETS
                            |
                            v
              +-----------------------------+
              |  1  BOARD PREP & PRINTING   |
              +-----------------------------+
                            |
                            v
              +-----------------------------+
              |  2  COATING        [optional]|
              |  Gloss / Matt Lam            |
              |  UV / Aqueous Varnish        |
              +-----------------------------+
                            |
                            v
              +-----------------------------+
              |  3  DIE-CUTTING & STRIPPING |
              |     against a Flatbed Die    |
              +-----------------------------+
                            |
                            v
              +-----------------------------+
              |  4  WINDOW PATCHING [optional]|
              |     Film — KG                 |
              +-----------------------------+
                            |
                            v
              +-----------------------------+
              |  5  FOLDING & GLUING        |
              +-----------------------------+
                            |
                            v
              +-----------------------------+
              |  6  BUNDLING & PACKING      |
              |  boxes/bundle, bundles/carton|
              +-----------------------------+
                            |
                            v
                     Finished Goods
                            |
                            v
              Close-Out & Reconciliation (A–E)
```

Two material streams meet in this route: **board in sheets** through the whole
line, and **window film in kilograms** entering only at stage 4.

---

# 4. The Route Model

## 4.1 Six stages, chosen per job, all in-house

| # | Stage | Flag |
|---|---|---|
| 1 | Board Prep & Printing | `applies_printing` |
| 2 | Coating | `applies_coating` |
| 3 | Die-cutting & Stripping | `applies_diecut` |
| 4 | Window Patching | `applies_window_patch` |
| 5 | Folding & Gluing | `applies_gluing` |
| 6 | Bundling & Packing | `applies_bundling` |

## 4.2 The CPS decides; the job card inherits and may override

Route flags live on the **Customer Product Specification**. The job card inherits
them **on first link only**, then owns them.

This is deliberate. A genuine one-off — skip lamination on a rush job — must not
require a specification revision, which under VCL convention would be a
**revise-in-place**, not an amend. The spec describes the product; the job card
describes this run of it.

## 4.3 Struck through, never dropped

The traveller prints applicable stages normally and prints excluded stages **struck
through**. The floor must be able to see that a stage was *consciously excluded*
rather than forgotten. Same convention as Printing on a plain carton job.

## 4.4 Same pattern, three departments

This inherit-once + strike-through pattern was designed for Monobox and then
**back-ported to Carton** (which gained eight flags and a Die-cutting & Stripping
stage on the same day). Labels do not have it yet. Treat it as the VCL standard for
variable routes.

---

# 5. The Cutting Die

The tool is a **`Flatbed Die` (`FBD-DIE-.#####`)** — a steel rule die, also called a
cutting forme, run flat against a sheet.

## 5.1 One register, three product lines

The register was **renamed from `Monobox Die` to `Flatbed Die`** on 2026-08-05,
because the same physical tool cuts a monobox, a **Die Cut carton**, and a **2-ply
cup sleeve**. It is a shared, contended asset register.

> **Never use the `Dies` doctype for this work.** `Dies` (`DIE-.#####`) is the flexo
> **label** register — `across_ups`, `round_ups`, `teeth`, PP materials — a **rotary**
> tool cut into a cylinder and run against a reel. Different tool, different machine,
> different geometry.

## 5.2 What the register holds

**Planning geometry:** `blank_length` · `blank_width` · `ups_per_sheet` ·
`sheet_size` (610 × 860 / 914 × 1220 / Other) · `sheet_length` · `sheet_width` ·
`has_window` · `window_width` · `window_height` · `window_offset_bottom` ·
`window_offset_left`

**Physical asset:** `die_number` · `customer` · `status` (Active / Worn / Retired /
Lost) · `storage_location` · `maker` · `date_made` · `cost` · `notes`

Plus `die_layout_image` — a layout drawing or photo of the tool, which prints on the
job card.

## 5.3 Sheet requirement

```text
sheets_required = ceil(quantity_ordered / ups_per_sheet)
```

`ups_per_sheet` comes from the die, not from the operator. It is the number that
converts an order in **boxes** into a material requirement in **sheets**.

---

# 6. Board and Film

## 6.1 Board — issued in SHEETS

Stocked board today is **Chipboard (Duplex Board)**, reels and sheets, at
**180 / 220 / 230 / 290 GSM**, sheet sizes **610 × 860** and **914 × 1220**.
No SBS, FBB or art card items exist.

> **The stock UOM is Kg, but the floor counts SHEETS — and the conversion is written
> down nowhere.** This is the standing trap of this department. Never invent a
> sheets↔Kg factor; where the number is needed it must be derived from sheet area and
> GSM, or measured.

`print_side` is **White Side / Grey Side** — duplex board is not symmetrical, and
printing the wrong face is a scrap event.

## 6.2 Film — issued in KG

Window film enters only at stage 4: `film_material` · `film_micron` ·
`film_patch_width` · `film_patch_height`.

The patch is sized to overlap the window aperture, so patch dimensions are larger
than window dimensions and the two must not be conflated.

## 6.3 Window geometry

`window_width` · `window_height` · `window_panel` (Front / Back / Top / Side /
Other) · `window_offset_bottom` · `window_offset_left` — offsets measured from the
panel edges.

`has_window` gates both the window field group and close-out block C, so a
no-window job never asks for film figures.

---

# 7. Job Card & Close-Out

- **Doctype:** `Job Card Monobox`, series `JC-MBX-.YYYY.-.####.`, submittable
- **Specification:** `MBX-SPEC-.#####` on the CPS, `product_type = Monobox`
- **Sales Order:** **optional and encouraged, not enforced.** Monobox is not
  order-derived, which is why it is deliberately *not* registered in
  `so_spec_control.JOB_CARD_DOCTYPES`.

## 7.1 Capture is paper-first, by decision

The traveller is filled on the floor; its close-out is keyed back into ERPNext.
Digital/QR capture was explicitly deferred — **the form has to settle on the floor
before capture is built on top of it.**

## 7.2 The close-out blocks

| Block | Captures |
|---|---|
| **A. Output vs Order** | Boxes produced · delivered · invoiced · difference vs ordered · reason for over-run or short-fall |
| **B. Board Consumed vs Planned (Sheets)** | Planned sheets · issued · used · returned to store · waste sheets · **yield %** · explanation |
| **C. Window Film Consumed (Kg)** | Film type · issued · used · returned · consumed |
| **D. Time & Labour per Stage** | `Monobox Stage Summary` child table · total hours |
| **E. Sign-off** | Job complete · date completed · keyed in by · date keyed |

## 7.3 Per-stage capture — unique to this department

`Monobox Stage Summary` holds one row per applicable stage:

`stage` · `machine` · `total_hours` · `operators` · `output_qty` · `waste_sheets` ·
`stage_notes`

**This is the only VCL job card with a structured per-stage child table.** Carton
captures its stages on paper only; labels the same. If per-stage capture is ever
wanted elsewhere, this is the working model to copy.

## 7.4 Waste is derived, never typed

```text
Waste  =  Issued  −  Used  −  Returned
```

Deliberately a **residual**, so that an unbalanced material account **shows** rather
than being written to square. A yield figure that looks wrong is the point of the
block, not a defect in it.

---

# 8. Iteration One Is Deliberately Loose

The following were left soft on purpose, and should not be "fixed" without cause:

| Left loose | Why |
|---|---|
| `board_grade`, `board_gsm` free text | Constrain to Selects only once real usage is visible |
| `film_material` free text | Same |
| Blank size typed in, not derived | Where a die is linked it defaults from the die; a derived layout drawing would be decorative, not load-bearing |
| No layout drawing | Page 1 of the traveller carries a hand-sketch box instead |
| `coating_type` a short Select | Coating is used infrequently |

**Iteration two** tightens grade, GSM and film to Selects and adds digital/QR
capture.

---

# 9. Modelling Principle

### Process · Machine · Capability

```text
PROCESS:
Die-cutting and Stripping

MACHINE:
(unregistered — see section 2)

OPERATIONS USED:
- Flatbed die cut against FBD-DIE-#####
- Stripping
```

The honest example above is the state of this department: **the process model is
complete and the machine model is empty.** Monobox is the inverse of Labels, where
the machines are known and the route flags do not exist.

---

# 10. Deployment & Usage Status

Recorded plainly, because it is easy to mistake "built" for "in use".

| | |
|---|---|
| `Job Card Monobox` doctype | **Live** |
| Job cards raised to date | **Zero** |
| `Flatbed Die` records | **Two** — FBD-DIE-00001 (4 ups) and FBD-DIE-00002 (12 ups), both Bahati Ventures Ltd |
| What those dies are actually cutting | **Carton die-cut work**, not monobox |

So the monobox system is **deployed but unexercised**. The die register it
introduced is in daily use — by the carton department.

**⚠ Two live traps recorded from the build:**

1. **Select options must be widened before rows are seeded.** Adding a department
   value and seeding machines that use it in the same migrate throws
   `ValidationError: Department cannot be "Monobox"` — and a throw inside
   `after_migrate` **aborts the migrate for every app on the bench**. Widen first,
   seed second.
2. **Retire a machine by unticking `active`, never by deleting it**, or the next
   migrate resurrects it.

**Monobox is the 5th department on the Production Floor board and was APPENDED, not
inserted** — the evening WhatsApp report's department order is what the floor reads,
so the first four keep their positions.

---

# 11. Items for Later Confirmation

**Machines — the priority**
- Which press prints monobox board (shared with Offset?)
- Which machine performs flatbed die-cutting — and settle it jointly with the same
  open question in the Carton document
- Window patching: manual or machine?
- Folding & gluing: manual, machine, or both — and should it split the way carton's
  `joint_type` does?
- Is coating in-house or bought out?
- Register whatever is confirmed as real Workstations, replacing the six
  stage-named placeholders

**Process**
- Standard waste / yield % by stage, especially stripping and patching
- Make-ready time per stage
- Whether coating is ever applied after die-cutting rather than before

**Data**
- The sheets ↔ Kg treatment for duplex board at stock level
- Film Kg per patch, so film requirement can be planned rather than reconciled
- Realistic ups-per-sheet ranges by sheet size

**System**
- Move board grade / GSM / film material to Selects (iteration two)
- Digital / QR floor capture (iteration two)
- Whether to bring the per-stage summary pattern across to Carton and Labels

---

# 12. Department Status

**Monobox:** Process mapping complete; machine mapping absent; usage nil.

This is the **most completely modelled department in ERPNext** — job card, spec
type, die register, route flags, per-stage close-out and traveller all exist and are
deployed. It is also the **only department with zero recorded production**.

The gap to close is not design. It is (a) naming the physical machines behind the
six stages, and (b) putting the first real job through the card so the form can be
corrected against reality — which was always the stated plan: *paper first, and the
form has to settle on the floor before capture is built on top of it.*

This remains a **working master**.
