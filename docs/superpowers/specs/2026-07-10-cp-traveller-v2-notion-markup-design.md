# CP Job Traveller v2 — Notion markup pass (Sections 1–3)

**Date:** 2026-07-10
**Doctype:** `Job Card Computer Paper`
**Print format:** `Computer Paper Job Traveller v2` — **currently the live default** (Property Setter `Job Card Computer Paper-main-default_print_format`)
**Source of truth (new):** `production_log/job_card_tracking/doctype/job_card_computer_paper/computer_paper_job_traveller_v2.html`
**Origin:** Tanuj's markup on Notion page *Computer Paper Job Card* (`3998e0265cd5806e80c4ff53ca5fe2e5`)

## Context correction

The prior spec (`2026-07-02-...`) recorded the default swap as *pending*. It has since happened: v2 **is** the default the shop floor prints today. Every change here lands on a live production form, so the HTML is now version-controlled in-repo and deployed from the repo, not string-swapped in a scratch script.

## The notes, verbatim

1. Reel Issuance is okay — but we need guidance notes, and remove Net Consumed (already assumed).
2. Section 2 Printing — summary table at the top; production inputs Total Sets Produced, packing in each set, total sheets produced. Keep the weight-by-set table but constrain it to the maximum number of boxes allowed.
3. Printing Labour — make this table simple: `Date | Operator Name(s) (multiple) | Machine | Start | End | Printed Sheets`.
4. Collection and Packing is okay.

## Decisions taken (Tanuj, 2026-07-10)

- **Box cap rule:** round the printed SET/BOX columns up to the nearest 10 — `show = max(10, ceil(sets/10) * 10)`. Every matrix block is now a full 10 columns, which also fixes the known cosmetic bug where a partial trailing block rendered wider than its siblings.
- **The inherited hard cap of 60 columns was a latent defect and is removed.** Two live jobs plan more than 60 sets — `JC-CPT-2026-00014` (68) and `JC-CPT-2026-00048` (156) — so under the old cap, boxes 61+ had *no weight cell at all* and were dropped silently. The rounding rule now sizes the matrix to the job. A safety ceiling of 20 blocks (200 boxes) remains, but breaching it prints a red **continuation sheet** warning naming the missing box range rather than truncating quietly. No current job reaches it.
- **Net Consumed removal:** remove *every* net field in Section 1 — the balance-strip `Net Consumed` row, the `NET` column in the reel log, the `NET` column in the ink log, and the per-part `Part N net →` roll-up row. Issued and Remaining stay; consumption is derived. The balance strip already carries per-part totals, so the roll-up row was redundant.

## Changes

### Section 1 · Store Release & Returns
- Delete the highlighted `Net Consumed` row from the per-part balance strip.
- Reel log drops the `NET` column (10 → 9 columns); the freed width goes to `REEL #` and `SIGN`.
- Ink log drops the `NET` column (7 → 6 columns).
- Delete the per-part `Part N net →` roll-up row.
- **New:** a `.guide-note` block directly under the section header — numbered fill-in rules (one line per reel; weigh out on release, weigh back on return; a reel not returned is fully consumed, leave Date Back/Remaining blank; roll part totals into the balance strip; inks follow the same weigh-out/weigh-back rule; both store and receiver sign).

### Section 2 · Printing
- **New summary table at the top — per part, pivoted.** Parts are **columns** (`1 PT · 2 PT · …`, one per `number_of_parts`) with a `TOTAL` column on the right; metrics are **rows**. This matches the per-part balance strip on Page 2, so both pages read the same way.

  | Row | Source |
  |---|---|
  | `Colour / Type / GSM` | pre-filled grey from `colour_of_parts` |
  | `Planned Sets` | pre-filled grey — `ceil(quantity_ordered × packing / 2000)` |
  | `Planned Sheets` | pre-filled grey — `sets × 2000` |
  | `Actual Sets Produced` | hand-filled |
  | `Packing per Set (sheets)` | hand-filled |
  | `Actual Sheets Produced` | hand-filled |

  **Per part, not job-level.** A single job-level figure (e.g. one "6,000 sheets" total) cannot be reconciled — each part must tie out on its own column. The `Planned` rows are an addition to the literal note: they cost nothing (already derived for the matrix) and give production the target to reconcile against, which is the point of capturing actuals.
- Weight-by-set matrix: unchanged in shape, but column count now follows the box-cap rule above instead of `max(sets, 10)` uncapped-to-60.
- **Per-part totals strip rebuilt as a signable table.** Was a thin one-line band with inline `______` underscores and no room to write. Now a bordered table — `SHEETS · TOTAL WEIGHT (KG) · WASTE · SIGNED BY · DATE` — with a tall (32px) entry row. `SHEETS` stays pre-filled.

### Sign-off blocks
Every sign-off on the form was an inline underscore span too short to sign in. All are now bordered tables with tall entry rows:
- Section 1 — `ISSUED BY (STORE) · RETURNS RECEIVED BY · DATE`
- Section 2, per part — `SIGNED BY · DATE` (in the totals strip above)
- Section 3 — `PRINTING SUPERVISOR · DATE`

### Section 3 · Printing Labour
Replace the 10-column table with exactly the six columns from the notes:

`DATE | OPERATOR NAME(S) | MACHINE | START | END | PRINTED SHEETS`

`OPERATOR NAME(S)` is widened (28%) to hold multiple names on one line. The per-row `SIGN` column is dropped in favour of a single supervisor sign-off beneath the table — the notes asked for simple, and a signature per row on a shared-shift table was never being filled honestly anyway.

Dropped columns: `PART`, `SET START`, `SET END`, `SETS`, `SIGN`. `PRINTED SHEETS` is the new output measure, consistent with the Section 2 summary.

### Pagination — Labour gets its own page
The taller signing rows pushed the Labour table into an **orphan split** across a page break. Shaving rows until it fit was rejected as fragile: page 3's height scales with `number_of_parts` (each part carries a matrix + a totals strip), so a 5-part job would break it again.

Section 3 therefore gets **its own page container** with 14 full-height rows. Pagination is now deterministic rather than a function of part count:

`P1 job info + QR · P2 Store Release & Returns · P3 Printing — Sets & Weights · P4 Printing Labour · P5 Collection & Finishing`

Cost: one extra sheet per job. Page 3 still spills to a second sheet on large jobs, because the box matrices genuinely need the room (156-set job → 6pp).

### Section 4 · Collection & Packing
Unchanged (now Page 5). Page 1 (job info + QR) unchanged.

## Non-goals

No schema change — every new cell is hand-filled on paper. No autocapture/Compass wiring. No rename of the format, no retirement of `Computer Paper Job Traveller` (v1).

## Delivery & rollback

- Edit the in-repo HTML, deploy with `scripts/deploy_cp_traveller_v2.py` (idempotent `PUT` to the Print Format record).
- Verify by rendering real PDFs via `frappe.utils.print_format.download_pdf` for anchor jobs **JC-CPT-2026-00044** (1 set/part), **00046** (6), **00047** (20), and reading the rendered pages.
- Rollback: `git checkout` the baseline commit of the HTML and re-run the deploy script.

## Render defects found and fixed during verification

Caught by reading the rendered PDFs, not visible in the HTML:

- The Section 2 guidance note overflowed the right page margin, clipping the word "totals". Fixed with explicit `box-sizing: border-box`, a right-padding gutter, and restructuring the note to the `<b>` + `<ol>` pattern that Section 1 already used.
- The `Weight (kg)` row label rendered centred while every sibling row label was left-aligned — it was the one `.label-cell` missing `text-align:left`.

## Verified

`Computer Paper Job Traveller v2` deployed and re-fetched to confirm byte-match. Rendered PDFs read (not merely generated) for:

| Job | Sets/part | Parts | Pages |
|---|---|---|---|
| JC-CPT-2026-00044 | 1 | 3 | 5 |
| JC-CPT-2026-00046 | 6 | 2 | 5 |
| JC-CPT-2026-00047 | 20 | 3 | 6 |
| JC-CPT-2026-00048 | 156 | 1 | 6 |

The matrix reaches SET 160 on 00048, so all 156 planned boxes have a weight cell. On 00044 the pivoted summary shows 1 set / 2,000 sheets in each of the three part columns and 3 / 6,000 in TOTAL — the per-part reconciliation the notes asked for.

