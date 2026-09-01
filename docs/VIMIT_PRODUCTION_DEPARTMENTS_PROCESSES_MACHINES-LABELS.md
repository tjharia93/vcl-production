# Vimit Converters Ltd — Production Departments, Processes & Machines

**Status:** Working Master — expected to change
**Department 03:** Labels (Self-Adhesive / Flexo)
**Last Updated:** 01 September 2026

> Third in the series, after *Department 01 — Computer Paper / ETR / Reel-to-Reel*
> and *Department 02 — Corrugation & Carton*. This department is being documented
> **incrementally by agreement** — the machine and process picture will be corrected
> as the floor is walked. Items marked **⚠ CONFIRM** are open, not blocking.

---

# 1. Department Scope

This department converts **self-adhesive substrate reels into finished label rolls**
on rotary flexo presses.

It is a **single product family**, not several routes:

- **Printed roll labels** — 1 to n colours, process and/or spot
- **Plain (unprinted) die-cut labels** — same route, printing stage idle
- **Numbered labels** — the same route plus a numbering requirement

Substrates in the die register: **PP White · PP Clear · PP Silver · Thermal ·
Semi-Gloss**.

## The structural difference from Departments 01 and 02

Three departments, three different shapes — and getting the shape right is the
whole point of these documents.

| Department | Shape |
|---|---|
| **01 — Computer Paper** | One machine pass, many inline capabilities. *Do not invent separate stages.* |
| **02 — Carton** | Serial ladder of seven-plus real stations with WIP between each. *Do not collapse them.* |
| **03 — Labels** | **One inline press pass, then a parallel bank of six rewind stations.** |

Labels are **like Department 01 at the press** — print, varnish, die-cut and strip
all happen inline in one pass, so they must not be modelled as separate stages.

But they are **unlike both** after the press. The press produces **master reels**,
which then fan out across **six independent rewinding stations working in
parallel**. That is a shape neither of the other departments has, and it is where
the department's real capacity constraint lives.

---

# 2. Machines & Capabilities

## 2.1 Presses

| Machine | kW | Amps | Notes |
|---|---|---|---|
| **Propheteer 01** | 15 | 21.7 | Second motor 11 kW |
| **KDO 02** | 4 | — | |
| **KDO 03** | 5.5 | 11.3 | Second motor 0.85 kW |

ERPNext carries `Profeteer 01` and `KDO 01` as Workstations of type
**Label Printing**; `VCL Production Machine` carries only `Propheteer` under
department **Labels**.

**⚠ CONFIRM:** `KDO 01` exists in ERPNext but not in the plant KWH register, while
`KDO 02` and `KDO 03` are in the register but not in ERPNext. Either the registry
or the register is behind. Also note the spelling split — **Propheteer** in the
register versus **Profeteer** in ERPNext; one should win.

## 2.2 Rewinding

| Station | Count | Notes |
|---|---|---|
| **Rewinding stations** | **6** | Confirmed on the floor. The KWH register lists a single unrated "Rewinding Machine" and does not reflect six. |

These are the **finishing and inspection bank**. Master reels off the press are
slit and rewound here into customer roll counts, and this is where the labels are
actually looked at.

**⚠ CONFIRM:** individual station identities and whether any is specialised
(numbering, inspection-only, doctoring).

## 2.3 Machines NOT claimed for this department

The plant register holds several machines that could plausibly be label-related but
have **not** been confirmed as label machines and are therefore excluded:

`Relo Die Cut Machine` · `Slitting` / `Slitting Machine` · `Nebiolo` · `Mercedes` ·
`Letter Press` · `Bobst` (×3) · `Cutting 01–06` · `Tinting Machine 01–05` ·
`Shredding Machine`

**⚠ CONFIRM** which, if any, serve labels. They are listed here so the question is
recorded rather than silently dropped.

---

# 3. Production Architecture

```text
                          DEPARTMENT
                              |
                  Substrate Reels (Jumbo, metres)
                              |
                              v
                   +---------------------+
                   |    LABEL PRESS      |
                   | Propheteer / KDO    |
                   |                     |
                   |  ONE INLINE PASS:   |
                   |   - Flexo printing  |
                   |   - Varnish / UV    |
                   |   - Rotary die-cut  |
                   |   - Matrix strip    |
                   |   - Slit to lanes   |
                   +---------------------+
                              |
                              v
                       MASTER REELS
                     (reel ID, metres)
                              |
        +--------+--------+---+----+--------+--------+
        |        |        |        |        |        |
        v        v        v        v        v        v
      RW 1     RW 2     RW 3     RW 4     RW 5     RW 6
        |        |        |        |        |        |
        +--------+--------+---+----+--------+--------+
                              |
                              v
                    Slit / Rewound Rolls
                   (labels per roll count)
                              |
                              v
                     Packing per Standard
                              |
                              v
                      QC Final Release
                              |
                              v
                    Finished Goods / Dispatch
```

**Capacity note:** because six rewind stations feed off one press pass, the
department's throughput ceiling is normally **rewinding, not printing**. Any
planning model that schedules only the press will mis-state capacity.

---

# 4. The Press Pass — What Happens Inline

Everything below occurs in **one pass**, on one machine, and must not be recorded
as separate production movements:

- Flexo printing, up to the colours on the specification
- Varnish / UV curing where the ink type calls for it
- Rotary die-cutting against the mounted die
- Matrix (waste web) stripping
- Slitting to lanes
- Rewinding to master reel

The output of the press is a **master reel**, not a finished product.

---

# 5. Tooling — The Heart of the Department

Three tooling objects govern a label job. Getting one wrong scraps the run.

## 5.1 The Die — rotary, and a separate register

The cutting tool is a **`Dies` record (`DIE-.#####`)** — a **rotary** tool cut into
a cylinder and run against a moving web.

> **Do not confuse the two die registers.**
> `Dies` = **rotary**, for labels: `across_ups`, `round_ups`, `teeth`, PP/thermal materials.
> `Flatbed Die` (`FBD-DIE-.#####`) = **flatbed** steel rule, for Carton Die Cut and Monobox.
> They are different tools, different machines, different geometry. Never reuse one for the other.

Die fields: `die_number` · `die_size` · `length` · `width` · `shape`
(Square / Rectangle / Circle / Semi Circle / Irregular / Oval) · `across_ups` ·
`round_ups` · `teeth` · `material` · `orders` (child table of `Dies Order`).

**`die_size` is unreliable.** It is free text and does not consistently mean what it
appears to mean. Work from `length`, `width`, `across_ups`, `round_ups` and `teeth`.

## 5.2 Geometry — the rule that matters

```text
width   = ACROSS the web
length  = AROUND the cylinder

repeat  = teeth × 3.175 mm
```

`teeth` is the gear pitch of the magnetic cylinder, at 1/8 inch (3.175 mm) per
tooth. The repeat it gives is what determines whether a die physically fits a
cylinder — which is why the operator SOP requires confirming cylinder teeth against
the job card before the run.

Related job card fields: `plate_up` · `plate_round` · `packing_up` ·
`packing_pieces` · `gap_between` · `side_trim` · `label_length` · `label_width`.

## 5.3 The Plate

`plate_status` is **New** or **Old**, with `plate_code`:

| plate_status | plate_code |
|---|---|
| **New** | **Empty** — the plate does not exist yet and must be made |
| **Old** | **Non-empty** — the plate exists and is pulled from the plate store by code |

This is a hard rule, not a convention. A New job with a plate code, or an Old job
without one, is a data error that will send someone to the plate store for a plate
that isn't there.

Post-run, the SOP requires plates to be **washed and returned to the plate store
against the job reference and plate code** — the register only stays true if that
happens.

## 5.4 The Cylinder

The magnetic cylinder carries the die. Cylinder release is a **separate
authorisation signature** on the traveller, alongside plate release — because the
cylinder is a shared, contended resource across jobs.

---

# 6. Rewinding & Slitting

Section 7 of the traveller. This is the department's second half.

| Captured per pass | |
|---|---|
| Date | Master reel ID |
| No. of passes | Rolls per pass |
| Total rolls | Remarks · Sign |

**Lanes = `plate_up`.** The number of lanes a master reel yields is the across-web
ups on the plate. A 12-pass master at *n* lanes gives 12 × *n* rolls.

Six stations run this in parallel. Each master reel is tracked by **reel ID** from
the press through to the rolls it produced, which is what makes the count
defensible when a customer queries a short roll.

---

# 7. Numbering

Where `numbering_required` is set, the job carries:

`numbering_prefix` · `numbering_start` · `numbering_end` · `numbering_format`

**⚠ CONFIRM** whether numbering is applied inline on the press or at a rewind
station, and whether any of the six stations is the designated numbering station.

The start/end range is a **control total** — the numbers issued must reconcile to
the labels produced, the same way a cheque range does.

---

# 8. Quality Regime

Labels carry the tightest QC of the three departments, and the standards are
already written into the traveller.

## 8.1 First-off — before the main run may start

Every item must pass and be signed:

- Plate condition / verification
- Shade matching vs. approved sample
- Barcode / text clarity
- Registration & colour alignment
- Die-cut shape & dimensions
- Adhesive / release liner integrity

**Four authorising signatures** are then required to run: Sales/Accounts ·
Production Manager · **Plate Release** · **Cylinder Release**.

## 8.2 Standards

| Measure | Tolerance |
|---|---|
| Registration | **≤ 0.15 mm** |
| Colour, first-off | **ΔE ≤ 2.0** vs approved swatch, per spot colour |
| Colour, in-process | **ΔE ≤ 3.0** — retighten if exceeded |
| Barcode | **ANSI grade B or better**, every SKU |
| AQL | **Critical 0.0 · Major 1.0 · Minor 2.5** |

## 8.3 In-process cadence

- **Every reel change:** record start/end metres, operator, time
- **Every 30 min or every reel:** visual — streaks, ghosting, misregistration, splice breaks
- **Every 60 min:** densitometer spot-check per ink; full QC log row
- **Downtime > 5 min:** logged with a cause code
- **Waste reels:** tagged and separated — never released into finished stock
- **Retention:** 3 sample labels held in the QC file for **minimum 12 months**

## 8.4 Press setup requirements

From the operator SOP: substrate reel matched by material, width and batch; plates
mounted by code and checked for damage or residual ink; **UV jobs require lamp
hours < 1200 h** and clean dichroic reflectors; anilox set by BCM / screen count per
deck and recorded; inks mixed to recipe with viscosity (Zahn #2) and tack verified;
die tooling loaded with **cylinder teeth confirmed against the job card**.

---

# 9. Material Accounting

Labels account in **metres**, which no other department does.

| Point | Unit |
|---|---|
| Substrate issued (jumbo) | **Metres** (batch ID) |
| Press consumption | **Start metres → end metres → used metres** |
| Press output | **Master reels** (reel ID) |
| Rewind output | **Rolls**, and labels per roll |
| Dispatch | **Rolls / cartons**, `standard_packing`, `weight_per_carton` |

Section 4 of the traveller captures raw batch, start metres, end metres, used
metres, assigned reel ID and waste per master reel.

Reconciliation principle, unchanged across all departments:

```text
Material Issued  =  Good Production  +  Waste  +  Returned Material
```

For labels this must hold **in metres at the press** and **in rolls at rewinding**,
with the reel ID as the link between the two.

---

# 10. Job Card & Traveller

- **Doctype:** `Job Card Label`, series `JC-LBL-.YYYY.-.#####`
- **Origin:** customer LPO → Sales Order → Job Card Label. Item is created per CPS.
  **A customer is never auto-created** from an LPO.
- **Specification:** linked `Customer Product Specification`, with a frozen
  `spec_snapshot` (JSON) and `spec_snapshot_at` — the job runs against what was
  approved, not against later edits to the spec.
- **Pricing:** `rate` (net, ex-VAT) with `price_source` = CPS Price / Item Price /
  Manual Override.
- **Traveller:** `label_job_traveller.html`, **three A4 pages**:

| Page | Sections |
|---|---|
| 1 | 1 Job Information · 2 Product Specification · 3 Pre-production QC approval (first-off) + authorisations |
| 2 | 4 Material usage & printed output (master reels) · 5 Labour & operator timings · 6 Operator SOP (label press) |
| 3 | 7 Slitting & rewinding · 8 In-process QC log · QC & dispatch authorisation |

---

# 11. Modelling Principle

Same three-way distinction as the other departments:

### Process · Machine · Capability

```text
PROCESS:
Label Printing and Converting

MACHINE:
Propheteer 01

OPERATIONS USED:
- 4 Colour Flexo Printing
- UV Varnish
- Rotary Die-cut
- Matrix Strip
- Slit to Lanes
```

Then, and separately:

```text
PROCESS:
Slitting and Rewinding

MACHINE:
Rewind Station 1..6  (parallel)
```

**Two processes, not nine.** The press pass is one process no matter how many
capabilities it uses; rewinding is a second process that happens to run six-wide.

---

# 12. Not Yet Modelled in ERPNext

Recorded plainly so the gap is visible:

- **No production route flags** on `Job Card Label` — Carton has eight (`applies_*`),
  labels have none. Route variation is currently carried only on paper.
- **No per-run child table** — the traveller's Sections 4, 5, 7 and 8 are captured on
  paper and nothing feeds back into ERPNext.
- **The six rewind stations do not exist as Workstations.**
- **Labels are deliberately excluded** from the Production Floor "to plan" board —
  `JOB_CARD_SOURCES` covers Computer Paper, Carton and Monobox only.
- **Only one label machine** is registered in `VCL Production Machine`.

None of these are urgent. They are listed so that when the department is next
touched, the shape of the work is already known.

---

# 13. Items for Later Confirmation

**Machines**
- Reconcile `KDO 01` (in ERPNext, not in the register) against `KDO 02` / `KDO 03`
  (in the register, not in ERPNext)
- Settle the **Propheteer / Profeteer** spelling
- Identify the six rewind stations individually; note any specialisation
- Confirm which register machines (Relo, Slitting, Nebiolo, Mercedes, Letter Press,
  Bobst, Cutting, Tinting) serve labels, if any
- Press speeds, maximum web width, and repeat range per press

**Process**
- Is numbering inline or at a rewind station?
- Is any slitting done off-press, or always inline plus rewind?
- Where does matrix waste go — is the Shredding Machine part of this route?
- Lamination / over-varnish as a separate operation?

**Data**
- Standard waste percentage: setup vs run, by press
- Make-ready time per press, by colour count and by New vs Old plate
- Realistic rewind throughput per station per hour
- Downtime cause codes
- Metres ↔ labels ↔ rolls conversion treatment at stock level

**System**
- Whether to add route flags and a per-run child table to `Job Card Label`
- Whether to register the six rewind stations as Workstations
- Whether to bring Labels onto the Production Floor board

---

# 14. Department Status

**Labels:** Initial process mapping completed.

The **order-to-job-card system is mature** — job card, die register, plate control,
spec snapshot, pricing and a detailed three-page traveller with a full QC regime all
exist and are in use. The **shop-floor system side is the least developed of the
three departments** — no route flags, no run capture, most machines unregistered.

The department's defining shape is now recorded: **one inline press pass feeding a
parallel bank of six rewind stations**, with rewinding as the likely capacity
constraint.

By agreement this document is **updated as we go along**. It is expected to be
wrong in places and corrected on the next floor walk.
