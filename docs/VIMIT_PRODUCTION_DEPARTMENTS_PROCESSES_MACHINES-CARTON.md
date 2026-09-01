# Vimit Converters Ltd — Production Departments, Processes & Machines

**Status:** Working Master
**Department 02:** Corrugation & Carton
**Last Updated:** 01 September 2026

> Companion to *Department 01 — Computer Paper / ETR / Reel-to-Reel Printing*.
> Same modelling conventions apply. Where a fact is not yet confirmed on the
> floor it is marked **⚠ CONFIRM** rather than assumed.

---

# 1. Department Scope

This production area converts **paper reels into corrugated board, and corrugated
board into finished cartons**.

It covers four product/process routes:

1. **RSC Cartons** — 1 Flap / 2 Flap / 3 Flap Regular Slotted Cartons
2. **Trays** — open-top trays, no tab, no slotting
3. **Die Cut** — flatbed die-cut work, including 2-ply coffee cup sleeves
4. **Board / Sheet Supply** — corrugated board produced as sheets, not converted in-house

Routes 1–3 share the same front end (corrugation → pasting) and diverge at the
converting stations. Route 4 stops after sheeting.

## The structural difference from Department 01

Computer Paper is a **single machine pass** with many inline capabilities —
printing, perforating, punching and folding happen in one run, and the modelling
warning there is *do not invent separate stages*.

Carton is the opposite. It is a **genuinely multi-stage route with physical
movement and WIP between stations**. Board is corrugated, stacked, moved, pasted,
stacked, moved, creased, moved, printed, moved, stitched, moved, bundled. Each
handover is a real stock point where quantity, waste and WIP must be accounted for.

**So Department 02 must be modelled as a station-by-station route, and Department
01 must not be.** This is the single most important distinction between the two.

---

# 2. Machines & Capabilities

Sourced from the plant KWH/Amps register (`06. PRODUCTION/KWH Machines all.pdf`)
and the live ERPNext `Workstation` registry. Ratings are motor capacity.

## 2.1 Corrugation & Board Preparation

| Machine | kW | Amps | Function | ERPNext Workstation Type |
|---|---|---|---|---|
| **Corrugator 01** (incl. Sheeting Machine) | 7.5 | — | Single-face corrugation + inline sheeting | Corrugation |
| **Corrugator 02** | 4.5 | — | Single-face corrugation | Corrugation |
| **Sheeter 2 — Corrugator** | — | 8.2 | Sheeting | Sheeting |
| **Sheeting 2** | 1.6 | 3.2 | Sheeting | Sheeting |
| **Reel Lifter** | 1.5 | — | Reel handling / loading | — (materials handling) |

ERPNext currently carries `Sheeting Machine 01` and `Sheeting Machine 02` as
Workstations. **⚠ CONFIRM** which physical unit each name refers to — the register
lists sheeting both as part of Corrugator 01 and as two standalone sheeters.

## 2.2 Pasting

| Machine | kW | Amps | Function |
|---|---|---|---|
| **Pasting Machine** | 2.2 | — | Liner pasting / ply build-up |
| **Pressing Machine** | 1.5 | 3.3 | Pressing after pasting **⚠ CONFIRM** it belongs to this route |

## 2.3 Printing & Converting

| Machine | kW | Amps | Function |
|---|---|---|---|
| **Carton Printing Machine** | 11 | 20.4 | Flexo carton printing |
| **Slotter 01** | — | — | Slotting (ERPNext Workstation; net-new station created 2026-05-20) |
| **Slitting Machine** | 7.5 | — | Creasing & slitting **⚠ CONFIRM** whether creasing and slitting are one unit or two |

On the floor the daily sheet treats **Printing + Slotting as one station with one
run log**, while ERPNext models them as two Workstation Types (stage 150 and 155).
Both are correct for their purpose; the system must not force the floor to split a
single physical run into two entries.

## 2.4 Die Cutting

| Machine | kW | Amps | Function |
|---|---|---|---|
| **Bobst** | 3.6 | 11.2 | Platen die cutting |
| **Bobst** | — | 49 | Platen die cutting |
| **Bobst** | — | 2.5 | Platen die cutting |
| **Relo Die Cut Machine** | 4 | 9.4 | Die cutting |

The register lists three Bobst entries. **⚠ CONFIRM** how many Bobst machines
exist, which are live, and which serve Carton versus Label/General Printing.

## 2.5 Stitching & Gluing

| Machine | kW | Amps |
|---|---|---|
| **Stitching Machine 01** | 2.5 | — |
| **Stitching Machine 02** | — | 2.5 |
| **Stitching Machine 03** | — | 2.5 |
| **Stitching Machine 04** | — | 2.5 |
| **Stitching Machine 06** | — | 2.5 |

**Stitching Machine 05 does not appear in the register. ⚠ CONFIRM** whether it was
retired, renumbered, or simply omitted.

Gluing is **⚠ CONFIRM** — the register lists no carton gluing machine, but ERPNext
carries a `Carton Gluing` Workstation Type and the job card offers *Gluing -
Machine* as a joint type. Either the machine is unregistered or machine gluing is
in fact manual.

## 2.6 Finishing

| Station | Function |
|---|---|
| **Bundler 01** | Bundling / strapping (ERPNext Workstation, net-new 2026-05-20) |

## 2.7 Machine Notes

- Corrugator 01 has **inline sheeting**; Corrugator 02 **⚠ CONFIRM** whether it feeds
  a standalone sheeter.
- Sheeting is a **shared capability** — it also serves the Trading/board-supply route.
- Die Cutting is **shared across three product lines** — Carton, Monobox and Label.
  Scheduling must treat it as a contended resource, not a carton-owned station.
- `Lamination` and `Plate Making` are tagged to this department in ERPNext as
  **optional cross-line stations**, not part of the standard route.

---

# 3. Production Architecture

The department is **one shared front end feeding four divergent finishing routes**.

```text
                              DEPARTMENT
                                  |
                          Paper Reels (Kg)
                                  |
                                  v
                            CORRUGATION
                                  |
                                  v
                             SHEETING
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
                 PASTING                 BOARD / SHEET
              (ply build-up)                SUPPLY
                    |                    (Route D — ends here)
                    v
            +-------+-------+---------------+
            |               |               |
            v               v               v
        RSC CARTON        TRAY          DIE CUT
      (Route A)        (Route B)       (Route C)
            |               |               |
            v               v               v
      Creasing &       Creasing &       Die-cutting
       Slitting         Slitting        & Stripping
            |               |               |
            v               v               v
        Printing        Printing        Printing
      (if printed)    (if printed)    (before or after
            |               |          die-cut per job)
            v               |               |
        Slotting            |               |
            |               |               |
            v               v               v
      Stitching /       Stitching /     (usually no
        Gluing            Gluing         joint)
            |               |               |
            +-------+-------+---------------+
                            |
                            v
                    Bundling / Packing
                            |
                            v
                     Finished Goods
                            |
                            v
              Production Reconciliation
```

---

# 4. The Standard Station Ladder

ERPNext models the route as a **numbered ladder of Workstation Types** tagged to
the product line *Corrugation and Carton Department*:

| # | Stage | Workstation Type | Stage Position |
|---|---|---|---|
| 7 | Corrugated | Corrugation | — |
| — | Sheeting | Sheeting (shared) | — |
| 8 | Pasting | Carton Pasting | — |
| 9 | Creasing and Slitting | Creasing | — |
| 10 | Printing | Carton Printing | 150 |
| 11 | Die-cutting and Stripping | Die Cutting | — |
| 12 | Slotting | Slotting | 155 |
| 13 | Stitching | Carton Stitching | 160 |
| — | Gluing | Carton Gluing | — |
| 14 | Bundling | Bundling | 170 |

Optional cross-line: **Lamination**, **Plate Making**.

The numbering 7–14 is not arbitrary — it is the section numbering on the printed
Carton Job Traveller, which is why a new stage must be **appended, never inserted**.

---

# 5. Route Flags — How a Job Selects Its Stations

Not every carton visits every station. The route is **explicit data, not inference**.

## 5.1 Where the flags live

Eight checkboxes exist on both the specification and the job card:

| Job Card Carton | Customer Product Specification | Default |
|---|---|---|
| `applies_corrugated` | `carton_applies_corrugated` | On |
| `applies_pasting` | `carton_applies_pasting` | On |
| `applies_creasing` | `carton_applies_creasing` | On |
| `applies_printing` | `carton_applies_printing` | On |
| `applies_diecut` | `carton_applies_diecut` | **Off** |
| `applies_slotting` | `carton_applies_slotting` | On |
| `applies_stitching` | `carton_applies_stitching` | On |
| `applies_bundling` | `carton_applies_bundling` | On |

## 5.2 The inherit-once rule

The job card inherits the route from the specification **on first link only**, then
owns it. A one-off variation must never require a spec revision.

## 5.3 Struck through, never dropped

A stage that is switched off **prints struck through on the traveller**. It is not
removed. The operator sees the whole ladder and sees explicitly what this job skips
— which is what stops a station being missed by accident.

## 5.4 The legacy guard

Historic job cards were created before the flags existed and carry all eight as
zero. **An all-zero route means "no route recorded"**, not "no stages" — the
traveller falls back to the classic seven stages, with Printing struck through on a
plain job. Without this guard every historic card prints struck through end to end.

## 5.5 Gluing is derived, not flagged

There is no `applies_gluing`. Gluing is derived from **`joint_type`**:

| joint_type | Joint station |
|---|---|
| `Stitched` | Stitching |
| `Gluing - Manual` | Gluing (manual) |
| `Gluing - Machine` | Gluing (machine) |

## 5.6 Example routes

```text
2 FLAP RSC, PRINTED, STITCHED
Corrugated · Pasting · Creasing & Slitting · Printing · Slotting · Stitching · Bundling
Die-cutting OFF

2-PLY CUP SLEEVE (SFK, E flute, Die Cut)
Corrugated · Pasting · Printing · Die-cutting & Stripping · Bundling
Creasing & Slitting OFF · Slotting OFF · Stitching OFF

PLAIN TRAY, GLUED
Corrugated · Pasting · Creasing & Slitting · Gluing · Bundling
Printing OFF · Slotting OFF · Die-cutting OFF
```

---

# 6. Route A — RSC Cartons

## Product

1 Flap / 2 Flap / 3 Flap Regular Slotted Cartons, 3-ply or 5-ply, B / C / E flute.

## High-Level Flow

```text
Job / Production Order (JC-CORR-YYYY-####)
        |
        v
Raw Material Issue — Paper Reels (Kg)
        |
        v
Corrugation  -->  single-face board
        |
        v
Sheeting  -->  board sheets
        |
        v
Pasting  -->  3 ply / 5 ply board
        |
        v
Creasing & Slitting
        |
        v
Printing (if printed)
        |
        v
Slotting
        |
        v
Stitching  or  Gluing   (per joint_type)
        |
        v
Bundling / Packing
        |
        v
Finished Goods
        |
        v
Production Reconciliation / Job Close-Out
```

## Board Geometry

The blank is **derived, not typed**. Formulas are 1-UP, no trim:

| Product type | blank_width | blank_length |
|---|---|---|
| Tray | `W + 2H` | `L + 2H` (no tab) |
| 1 Flap RSC | `H + flap` | `2L + 2W + tab` |
| 2 / 3 Flap RSC | `flap + H + flap` | `2L + 2W + tab` |

- `flap` defaults to `ceil((W + 5) / 2)`
- `tab` comes from the joint configuration — **30 mm** for Stitched
- SFK ply skips the calculation entirely

## Trim and Reel Width

**Trim is per outer edge**, not total. VCL standard is **10 mm per edge**.

```text
planned      = blank + 2 × trim_per_edge
reel_width(n) = blank × n + knife_gap × (n − 1) + 2 × trim_per_edge
```

`knife_gap` sits between adjacent blanks; trim applies only to the outer web edges.
A warning fires when `planned_width > max_reel_width` (default 1500 mm).

## UPS Forecast

The job card computes reel width per UPS for both orientations and flags the
**OPTIMAL** layout. It is **advisory** — the chosen UPS is not stored. `ups_along`
is operator-set and bounded by corrugator cutoff, which the widget does not model.

## Unit Weight

```text
effective_gsm = g1 + g2×f + g3 + g4×f + g5
                where f = 1.7 for E flute, else 1.5

unit_weight   = area_m² × effective_gsm
```

The formula is product-type agnostic — it applies to trays and die-cut work equally.

---

# 7. Route B — Tray

Trays follow the RSC route but **skip slotting**, have **no tab**, and use the
tray blank formula.

```text
Corrugation → Sheeting → Pasting → Creasing & Slitting → Printing (if printed)
   → Stitching / Gluing → Bundling
```

**⚠ Known defect:** the traveller's *Panel & Flap Dimensions* section is
RSC-hardcoded — flap/H breakdown and a 30 mm tab. **For a tray these printed
numbers are wrong.** The Planned Board Size box is correct. Section 4 needs
branching on `product_type` so a tray renders Base / Wall / Ear.

---

# 8. Route C — Die Cut

## Product

Flatbed die-cut cartons, and **2-ply coffee cup sleeves** — which are Carton, not
Monobox: `ply = SFK` + `flute = E` + `product_type = Die Cut`.

## High-Level Flow

```text
Corrugation → Sheeting → Pasting → Printing (per job)
   → Die-cutting & Stripping → Bundling
```

## The Tool

The cutting die is a **`Flatbed Die` (FBD-DIE-.#####)** — a steel rule die or
cutting forme, run flat against a sheet.

> **The `Dies` doctype is the flexo LABEL register** — `across_ups`, `round_ups`,
> `teeth`, PP materials — a **rotary** tool cut into a cylinder and run against a
> reel. **Never reuse it for flatbed work.**

The specification links the tool through `carton_cutting_die`, which is
**editable after submit** — a die is often cut *after* the spec is approved.

## Sheet Requirement

```text
ups           = Flatbed Die.ups_per_sheet
sheets_needed = ceil(quantity_ordered / ups)
```

Worked example (JC-CORR-2026-0080): ups 12, quantity 50,000 → **4,167 sheets**;
board 370 kg, product 254 kg, **skeleton waste 117 kg / 32%**.

Skeleton waste on die-cut work is **structurally high** and must be planned for,
not treated as an exception.

## Known Gap

There is **no sheets-across-web or reel-width field anywhere** for die-cut jobs, so
reel width is still hand-written on the card.

---

# 9. Route D — Board / Sheet Supply

Corrugated board produced and sheeted but **not converted in-house**.

```text
Reels → Corrugation → Sheeting → Board Sheets (Finished Goods)
```

Sheeting is shared with the Trading route. **⚠ CONFIRM** whether this is tracked as
a carton job card at all, or issued straight as a stock item.

---

# 10. Units — The Standing Trap

Three different units are in play down one route, and they do not convert cleanly:

| Point in the route | Unit used |
|---|---|
| Reels issued from stores | **Kg** |
| Board after sheeting | **Sheets** |
| Cartons produced | **Nos** |
| Output handed to stores | **Bundles** (per packing instruction) |

The floor counts **sheets**; stock UOM is **Kg**; and the sheet↔Kg conversion is
computed from board geometry and effective GSM rather than being a stored factor.

**Never guess a conversion factor.** Where the daily sheet asks for both Kgs In and
Kgs Out at a station, that is deliberate — it is the only way the material account
closes.

---

# 11. Shop-Floor Capture — What Each Station Records

From the VCL-PROD-CC-001 daily sheet system, which is the working paper standard.

## Every station's run log

One run = one row:

`Start · End · Run Hrs · Machine · Target (Nos) · Actual (Nos) · Balance ·
Kgs In · Kgs Out · Waste Kgs · Reject Qty · Reject Reason · Remarks · QC Sign`

Plus, at the end of every station: **WIP Qty · Location/Tag · Supervisor Tick**.

## Station-specific additions

| Station | Additional capture |
|---|---|
| **Corrugation** | GSM · Flute · Start Dia · End Dia · Starch/glue opening-added-closing |
| **Pasting** | Glue check Pass/Fail · Bond failure rejects · Glue consumption |
| **Printing + Slotting** | Artwork/design code · Colours · Setup waste (sheets) · Ink used (Kgs) · Registration / Smudge / Shade / Mis-slot checks |
| **Creasing** | Crease quality Pass/Fail · Cracking rejects |
| **Stitching** | Stitch pattern/ref · Open stitch rejects |
| **Gluing** | Glue type/batch · Glue used (Kgs) |
| **Bundling / Packing** | Label & marking check OK / NOT OK |

## Day-level logs

- **Reel / Material Movement Log** — stores ↔ production, by reel ID, with dia in and out
- **Returns / Rejects Back to Stores** — dual-signed, stores + production/QC
- **Waste Log** — time, station, waste type code, Kgs, approver
- **Rejection Log** — time, station, reject code, qty, QC sign
- **Downtime Log** — start, end, station/machine, minutes, code, maintenance needed Y/N
- **Glue Readiness** — corrugation glue Kgs and pasting glue Kgs, checked at start of day
- **Employee Accountability by station** — operator, present, hours, output responsible

## Planning side

The morning sheet plans **Machine Allocation + Staffing**, **Reel Allocation**, and
an **end-of-shift WIP target per station**. WIP is planned, not just observed —
because in a multi-station route the constraint moves.

---

# 12. Proposed Production Process Structure

For production tracking / ERPNext design.

## A. Corrugation
- Reel loading
- Corrugation (single face)
- Inline sheeting where the machine supports it
- Output: board sheets · Capture: Kgs in, sheets out, waste, starch consumed

## B. Sheeting (where separate)
- Sheeting to size
- Shared with the board-supply and trading routes

## C. Pasting
- Ply build-up to 3 ply / 5 ply
- Pressing
- Capture: glue consumed, bond check, sheets in/out

## D. Creasing & Slitting
- Creasing to panel layout
- Slitting to blank width
- Capture: crease quality, cracking rejects

## E. Printing
- Flexo printing, up to the colours on the spec
- Setup waste captured separately from run waste
- Struck through on a plain job

## F. Die-cutting & Stripping
- Flatbed die cut against a registered `Flatbed Die`
- Stripping
- Skeleton waste is expected and should be forecast, not flagged as loss

## G. Slotting
- Slotting to RSC form
- Physically often the same pass as printing — the system must allow one run to
  cover both without forcing an artificial split

## H. Joint — Stitching or Gluing
- Driven by `joint_type`, not by a route flag
- Stitching: pattern/ref, open-stitch rejects
- Gluing: glue type/batch, glue Kgs

## I. Bundling & Packing
- Bundling per packing instruction
- Label and marking check
- Output: bundles, and Nos

---

# 13. Production Reconciliation Principle

Every carton job must reconcile:

```text
Material Issued
      =
Good Production
    + Waste
    + Returned Material
```

Two carton-specific requirements:

1. **Waste is derived as a residual**, not typed. `Issued − Used − Returned`. An
   unbalanced material account must be visible, never written to square.
2. **Reconciliation is per station, not only per job.** In a seven-station route a
   job-level total hides where the loss happened. Kgs In and Kgs Out at each station
   is what localises it.

Reel traceability must survive from stores issue through corrugation to the board
sheet that carries into converting.

---

# 14. Modelling Principle

Maintain the same three-way distinction as Department 01:

### Process
What manufacturing activity is being performed.

### Machine
The physical equipment performing the work.

### Capability / Operation
What the machine performs during that run.

Example:

```text
PROCESS:
Carton Printing and Slotting

MACHINE:
Carton Printing Machine + Slotter 01

OPERATIONS USED:
- 2 Colour Flexo Printing
- Slotting
```

**But note the departmental inversion.** In Department 01 the warning is *do not
split one machine pass into several stages*. In Department 02 the warning is the
reverse: **do not collapse several real stations into one stage**, because each
handover carries WIP, waste and accountability.

The one place the Department 01 rule does apply here is Printing + Slotting, which
the floor runs as a single station and the system models as two.

---

# 15. Job Card & Traveller

- **Doctype:** `Job Card Carton`, series `JC-CORR-.YYYY.-.####.`
- **Default print format:** `Carton Jobcard v3`
- **Alternative:** `Die-Cut Job Traveller` — purpose-built two-page A4 format for
  die-cut work; **the operator must select it manually**, Frappe cannot pick a print
  format by field value
- **Capture is paper-first by decision.** The traveller is filled on the floor and
  the close-out keyed back in. There is no per-run child table on the job card yet —
  the form settles on the floor first.

**⚠ Deploy warning:** `Carton Jobcard v3` and `Die-Cut Job Traveller` are
**database-only** and are not in the repo. `Carton Job Card` and `Carton Jobcard v2`
**are fixtures** and a migrate overwrites Desk edits to them. A site rebuild from
fixtures would lose v3 and the Die-Cut traveller entirely.

---

# 16. Items for Later Confirmation

**Machines**
- Number of live Bobst machines and which serve Carton vs Label
- Whether the Relo die cutter is in carton service
- Fate of Stitching Machine 05
- Whether machine gluing exists as equipment, or gluing is manual only
- Whether the Pressing Machine belongs to the pasting route
- Which physical unit each of `Sheeting Machine 01` / `02` refers to
- Whether creasing and slitting are one machine or two

**Process**
- Corrugator cutoff limits and maximum reel width per corrugator
- Whether Route D (board/sheet supply) is job-carded at all
- Sequence rule for die-cut work: print before or after die cutting
- Lamination — when it is actually used

**Data**
- Machine speeds, capacities and realistic hourly output per station
- Setup / make-ready time per station
- Standard waste percentage by station and by product type
- Waste type codes and reject codes — the daily sheet asks for codes that are not
  yet defined anywhere
- Downtime reason codes
- Board sheet ↔ Kg treatment at stock level
- Operator requirements and manning per station

**System**
- Whether to add a per-run child table to `Job Card Carton`
- Whether to record chosen UPS persistently (`chosen_ups_across`, `chosen_orientation`)
- A sheets-across-web / reel-width field for die-cut jobs
- Fixing the RSC-hardcoded Panel & Flap section for trays
- Getting `Carton Jobcard v3` and `Die-Cut Job Traveller` into the repo

---

# 17. Department Status

**Corrugation & Carton:** Initial process mapping completed.

Route model, station ladder, route flags and geometry are **established and live in
ERPNext**. Machine register is **partially confirmed** — the equipment list comes
from the plant KWH register and needs a floor walk to confirm assignment and status.
Capture standard exists on paper (VCL-PROD-CC-001) but is not yet digital.

This remains a **working master** and will be expanded as each production department
is reviewed.
