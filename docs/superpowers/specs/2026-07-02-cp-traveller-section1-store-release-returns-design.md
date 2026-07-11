# CP Job Traveller — Section 1 "Store Release & Returns" redesign

**Date:** 2026-07-02
**Doctype:** `Job Card Computer Paper`
**Print format (source):** `production_log/job_card_tracking/doctype/job_card_computer_paper/computer_paper_job_traveller.html`
**Scope:** Replace **only** Page 2 · Section 1 ("STORE RELEASE EXISTING RM"). Everything else on Pages 1–3 (including the QR block injected by `vcl_compass/patches/add_cp_traveller_qr.py`) stays byte-for-byte identical.

## Problem

Today's Section 1 is **issue-only**: a per-part matrix (columns 1PT–5PT) with manual rows *Reels Issued / Reel Width / Stock Floor*. It cannot record **returns of unused stock to the store**, so material consumption never reconciles, and a single "Reels Issued" cell cannot represent **multiple reels per part** issued/returned across a run.

## Solution — combined Issue + Return, reconciling block

New section title: **"Store Release & Returns (Existing RM)"**. Two stacked parts:

### 1. Per-part balance strip (summary)
Per-part matrix, columns 1PT–5PT (print `number_of_parts` columns, up to 5):
- Row `Colour / Type / GSM` — **pre-filled** from `colour_of_parts` child table (grey).
- Row `Total Issued (Σ)` — hand-filled.
- Row `Total Remaining (Σ)` — hand-filled.
- Row `Net Consumed` — hand-filled, highlighted (`#FFF8E1`).

### 2. Reel issue / return log (detail)
Grouped **per part**, each part introduced by a navy sub-header row (`PART 1 · White · CB · 56 gsm`, drawn from `colour_of_parts`). Columns:

`Date Out · Reel # · Width · Wt Out · Date Back · Remaining · Sign`

Each reel is one line, so any number of reels is captured with its own out-weight and remaining (return) weight. The per-part totals in the log roll up into the balance strip.

### Rows-per-part rule
```
rows_per_part = 2 if quantity_ordered < 50 else 3
```
`quantity_ordered` **is the carton count** (confirmed by Tanuj 2026-07-02), so the rule reads straight off the field — no derivation. Rows are **fixed** at 2 or 3 per part; no overflow/spare lines.

### Sign-off strip
`Issued by (store): ____   Returns received by: ____`

All cells are **hand-filled** (paper form) — no computed values in the print format.

## Delivery

- Build a **new print format** = exact clone of `Computer Paper Job Traveller` with **only Section 1 swapped**. Working name: `Computer Paper Job Traveller v2` (final name TBC with Tanuj).
- The existing `Computer Paper Job Traveller` stays live and unchanged.
- Tanuj reviews the rendered new format; **only then** do we switch the `Job Card Computer Paper` default print format over (single `set_default_print_formats`-style change), retiring the old one.

## Styling

Reuse existing print-format CSS verbatim: `#2B3990` navy section headers, `.vcl-table-compact` (0.7pt borders), `.label-cell` grey `#F4F4F4`, `.greyed-out` `#E9E9E9` pre-filled, `.manual-row` blanks. New helpers: `.band` (per-part sub-band) and `.part-hd` (navy per-part header row). 8pt Helvetica, A4.

## Out of scope

Page 1, Page 2 Sections 2–3, Page 3, the QR block, and the `Job Card Computer Paper` schema — all unchanged. No new doctype fields; no autocapture/Compass wiring (paper form only).
