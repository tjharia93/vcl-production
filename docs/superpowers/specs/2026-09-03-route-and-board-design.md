# The route and the board — design

**Date:** 2026-09-03
**Status:** design, approved in principle; awaiting spec review
**Origin:** *"When we are doing lets say computer paper there is already a set
process flow and a set machine flow, right? But it's not flowing the same way
when the daily production plan goes."* — Tanuj

---

## 1. The problem, proven

There are **two models of the same work** and they do not touch.

- The **job card** models a **route** — an ordered list of stages.
- The **daily board** models a **machine-hour** — one row, one machine, one day.

Nothing connects them in either direction, and the connection that *does* exist
in code is unreachable and, where reachable, broken.

### The test

`plan_lines` was run against the real route of `JC-CPT-2026-00080` and the live
`VCL Production Machine` stage map:

```
BLOCKED  Design
BLOCKED  Pending Films
BLOCKED  Printing   [Part 1 · CB · White · 55gsm]   machines = —
BLOCKED  Printing   [Part 2 · CF · Pink · 55gsm]    machines = —
TICKED   Collation                                  machines = ['Collator']
BLOCKED  Pack

1 of 6 lines can actually be planned.
```

**Two findings, and they are different problems.**

1. **The part-splitting is sound.** It derived `Part 1 · CB · White · 55gsm` and
   `Part 2 · CF · Pink · 55gsm` from the card — which is exactly the "3rd copy
   pink" the floor names in every message, already structured. Nothing needs
   building here.
2. **The vocabularies do not meet.** No machine offers a stage called
   `Printing`. They offer `Reel to Reel Printing`, `Sheet to Sheet Printing`,
   `Carton Printing`, `Label Printing`. One word apart, and the route fails.

### And Carton cannot be planned at all

`JC-CORR-2026-0077` carries a complete route — `applies_corrugated` ✓
`applies_pasting` ✓ `applies_creasing` ✓ `applies_printing` ✓ `applies_diecut` ✗
`applies_slotting` ✓ `applies_stitching` ✓ `applies_bundling` ✓, joint
`Stitched`. But it has **no `production_stages` field and no route method**, so
`_route_for()` returns `[]` and `plan_job` throws *"Tick at least one station."*

### The third finding, which the test exposed

**The route mixes two kinds of step.** `Design` and `Pending Films` are office
work. They will never have a machine and must never appear on a machine board.
`Printing`, `Collation` and `Pack` are floor steps. So this is not only a naming
problem: the route has to say which stages belong on the floor at all.

---

## 2. What already exists, and is good

Almost all of the hard work is done. This design mostly connects it.

| Piece | What it does | State |
|---|---|---|
| `get_production_stage_route()` | CP's route, dropping Numbering when not required | Live, Computer Paper only |
| `plan_lines(route, parts)` | One line per station, Printing expanded per part | Live, tested |
| `get_plan_template(job_card)` | Route + machines + tickable lines | Live, **not whitelisted** |
| `plan_job(date, card, lines)` | Lays every ticked station on the board in one call | Live, whitelisted, **unreachable from the phone** |
| `roll_up_stages(rows, stage_of_machine)` | Board rows gathered into stages, per unit | Live, tested |
| `get_job_progress(job_card)` | Per-stage totals, status, % of order, flow | Live, **not whitelisted** |
| `stage_flow(stages)` | Refuses to compare stages counted in different units | Live, tested |

**Progress-up needs no schema change.** `roll_up_stages` derives the stage from
the **machine**, through `VCL Production Machine.stage` → Workstation Type. An
earlier draft of this design proposed adding a `production_stage` field to the
daily row. **It is not needed and must not be added** — it would be a second,
divergent source for something the machine already says.

---

## 3. Route sources differ by card, and that is correct

The four department masters state four genuinely different shapes, and warn
against forcing them into one:

| Department | Shape |
|---|---|
| 01 Computer Paper | One machine pass, many inline capabilities — *do not invent stages* |
| 02 Carton | Serial ladder of 7+ stations with WIP between each — *do not collapse them* |
| 03 Labels | One inline press pass → **parallel bank of six rewind stations** |
| 04 Monobox | Serial sheet-fed, and **the route itself varies job to job** |

Which is why the cards carry route data in three different ways:

| Card | Route lives in | Usable today |
|---|---|---|
| Computer Paper | `production_stages` child rows + route method | Yes |
| Carton | eight `applies_*` flags + `joint_type` | **No** — no table, no method |
| Monobox | `stage_summary` (a summary of stages, not a route) | **No** |
| Label | — | **No** |
| ETR | — | **No** |

**The design does not unify these.** Each card keeps describing its own
department's shape. A single function per card type turns whatever it carries
into an ordered list of stage names.

---

## 4. The design

Three parts. Only the third is genuinely new code.

### 4.1 A route registry — derive, then translate

One module, `production_log/production_floor/routes.py`, containing **pure
functions with no Frappe imports**, so it is unit-testable without a bench —
the same rule `reporting.py` already follows.

It does two jobs:

**Derive** — turn a card into an ordered route.

```python
def route_for_carton(flags: dict, joint_type: str) -> list[str]:
    """Carton's route from its eight flags. The joint is derived from
    joint_type, not flagged - there is no applies_gluing."""
```

Computer Paper keeps its existing method; the registry simply reads it.

**Translate** — resolve a route stage to the Workstation Types that can serve
it, per product type, and say whether it belongs on the floor at all.

```python
STAGE_MAP = {
    "Computer Paper": {
        "Design":        Office,
        "Pending Films": Office,
        "Printing":      ("Reel to Reel Printing", "Sheet to Sheet Printing"),
        "Collation":     ("Collation",),
        "Numbering":     ("Collation",),      # Collator 01 numbers; 02 does not
        "Pack":          Unstaffed,            # a real floor step with no station yet
    },
    "Carton": { "Printing": ("Carton Printing",), ... },
}
```

Three kinds of stage, and the distinction is the point:

- **Office** — never on the board. `Design`, `Pending Films`.
- **Floor, mapped** — one or more Workstation Types serve it.
- **Floor, unstaffed** — a real step with no station yet (`Pack`, all six
  Monobox stages, `Pasting`). Shown, **not silently dropped**, so the gap is
  visible. `roll_up_stages` already returns unstaged work under a `None` stage
  for exactly this reason.

**Why a table and not a rename.** `Printing` means a Miyakoshi on a Computer
Paper card and a flexo press on a Carton card. Renaming the machines' stages
would collide, and renaming the cards' stages would print ERPNext's vocabulary
on a traveller the floor reads. The mapping is genuinely many-to-one per product
type, so it is data.

### 4.2 Plan down — a card lands on the board

`get_plan_template` becomes whitelisted, and the phone gains a screen: pick an
open job card, see its route with a machine against each floor stage, untick
what does not apply, plan it. `plan_job` already writes every ticked line in one
call.

Office stages are absent. Unstaffed floor stages appear unticked with the reason
shown, rather than missing.

**Carton becomes plannable** the moment 4.1 derives its route from the flags —
no change to the card itself.

### 4.3 Progress up — the board advances the card

The only new write. After a day's rows change, roll the card's rows up with
`roll_up_stages` and set `stage_status` on the matching `production_stages` row.

- Only for cards that HAVE a stage table — Computer Paper today.
- **Derived, never typed.** `stage_status` becomes a projection of the board, so
  the two can no longer disagree. A stage with no rows stays `Not Started`.
- Runs on the day document's `on_update`, not on every keystroke.

Carton, Label, ETR and Monobox get progress through `get_job_progress` (a read)
until they have a stage table to write into. **That is deliberate**: giving them
a stage table is a bigger decision than this design, and reading works today.

---

## 5. Scope

**In:** the registry (4.1), plan-down for Computer Paper and Carton (4.2),
progress-up for Computer Paper (4.3), and whitelisting the two read endpoints.

**Out, and why:**
- **Label, ETR, Reel-to-Reel routes.** They have none, and there is live work on
  both right now. Defining them is a floor decision, not a coding one. ETR is
  `Printing → Slitting`; R2R is `Printing → Reel output`; neither is written
  down as a card route yet.
- **Monobox.** Its route genuinely varies job to job, so a template is the wrong
  shape until the per-job mechanism is decided.
- **A stage table for Carton.** Reading progress covers it for now.
- **The Labels parallel rewind bank.** It falls out for free — six rows against
  one stage, which `roll_up_stages` already sums — so it needs nothing here.

---

## 6. Testing

Everything in 4.1 is pure, so it is plain `unittest`, no bench, matching the 165
tests already in `test_reporting.py`.

The cases that must exist, each pinned to something this design got wrong first:

- Carton's route from real flags, including `applies_diecut = 0` dropping
  die-cutting and `joint_type = Stitched` adding Stitching.
- CP's `Printing` resolving to `Reel to Reel Printing`.
- An office stage never appearing in a plan.
- An unstaffed floor stage appearing, unticked, with a reason.
- `Numbering` resolving only to a Collator that numbers.
- A stage with no rows leaving `stage_status` at `Not Started`, not blanking it.
- Two rows on one stage (the Labels rewind case) summing rather than conflicting.

---

## 7. Decisions taken

Answered by Tanuj, 2026-09-03.

| # | Decision |
|---|---|
| 1 | **The `STAGE_MAP` approach is right.** Translate per product type; do not rename anything. |
| 2 | **`Pack` — not needed now.** It stays a floor stage with no station. Do **not** add a packing machine. |
| 3 | **Roland maps like M4** → `Reel to Reel Printing`. |
| 4 | **Kord is a printing machine** → `Sheet to Sheet Printing`, matching Solna and Miller. |
| 5 | **The two PLANNING entries come out of the machine master.** Planning is a process, not something production is recorded against. |

### On removing the PLANNING entries

`PLANNING` (Computer) and `PLANNING STAGE - PRINTING` (Offset) are already
`machine_type = Process`; the change is that they stop being **pickable**.

**Untick `active`. Never delete.** `seed_machines` runs from `after_migrate` and
adds back anything missing, so a deleted machine returns on the next deploy. A
deactivated one does not, and its history survives.

---

## 8. Three things the mapping work turned up

None of these block the design, but each will bite whoever writes the map.

### 8.1 There is only one Collator

The Department 01 master describes **two**: Collator 01 collates *and numbers*,
Collator 02 collates only. The live machine master carries a single `Collator`,
stage `Collation`.

So the intended rule — *Numbering runs only on the collator that numbers* —
**cannot be expressed today**. Two ways out, and it is a floor decision:

- Split the master into `Collator 01` and `Collator 02`, matching the plant, and
  map `Numbering` to 01 alone. Correct, and it is what the master already says.
- Map `Numbering` to the single `Collator` and accept that the app cannot tell a
  numbered job from a plain one at the machine.

Until it is resolved, `Numbering` maps to `Collator` and the limitation is
recorded rather than hidden.

### 8.2 "Reel to Reel" means two different things

This will mislead someone, so it is written down.

- In the **Department 01 master**, *Reel-to-Reel* is a **route**: reel in, reel
  out, no folding. By that meaning **M4 cannot do it**, and neither can Roland.
- In **ERPNext**, `Reel to Reel Printing` is a **Workstation Type**: reel-**fed**
  printing. By that meaning M1–M4 and Roland all qualify, because they are web
  presses that print and convert inline from a reel.

Both are true at once. Mapping Roland and M4 to `Reel to Reel Printing` is
correct **as a station type** and says nothing about whether they can produce a
finished reel. The master's capability table remains the authority on that, and
the app must never infer route capability from the station type.

### 8.3 Workstation Types exist for stations the master is missing

The site already defines `Carton Pasting`, `Creasing`, `Sheeting`, `Lamination`,
`Plate Making`, `Ruling`, `Flexo Label Printing` and
`Label Slitting and Re-Winding`.

Two consequences:

- **`Pasting` (Carton) has no stage** but `Carton Pasting` exists — a one-field
  fix, not a modelling question.
- **`Sheeting` and `Creasing` have Workstation Types but no machines at all.**
  Both are named stations in the Department 02 ladder, and their absence from
  the machine master was already recorded as an open finding. A Carton route
  derived from the flags will therefore produce `Creasing and Slitting` as a
  floor stage with nowhere to put it — shown unticked, which is the honest
  outcome and the reason unstaffed stages are a first-class case.

Also note `Design` exists as a Workstation Type. It is still treated as an
**office** stage here: it is a step on the traveller, not a machine the floor
records production against.

---

## 9. Still open

1. **Collator 01 / 02** — split the master, or accept one collator? (§8.1)
2. **Label, ETR and Reel-to-Reel routes.** None exist, and there is live work on
   both ETR and R2R now. ETR is `Printing → Slitting`; R2R is
   `Printing → Reel output`. Writing them down is a floor decision.
3. **Monobox** — its route varies job to job, so a template is the wrong shape
   until the per-job mechanism is decided.
