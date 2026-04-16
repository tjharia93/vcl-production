# Test Data Reference

All UAT scenarios pull from a single source of truth: the Carton Job Card
sample CSV on the internal OneDrive.

## Source file

```
C:\ONEDRIVE\Documents\CLAUDE\Projects\ERPNext Development\Carton Job Card\carton job card.csv
```

This file contains **10 historical job cards** that have already been run on
the factory floor. It is the reference set for every UAT cycle. **Do not edit
the CSV.** If a row is wrong, flag it to the manager and leave it alone.

## Sequence must be preserved

The 10 jobs in the CSV are ordered deliberately. Every UAT cycle must walk
through them in the **same order** they appear in the file — rows 1 through
10, top to bottom. Do not re-sort, do not skip rows (unless a scenario
explicitly says "cherry-pick"), do not swap rows between testers.

This matters because:

* Some jobs are variants of earlier jobs (same customer, different run) — the
  later row depends on the earlier row having been seen by the tester first.
* Bug reproductions are easier when every tester is looking at the same row
  in the same position.
* Regression diffs between releases are only meaningful if everyone walks
  the list in the same order.

If anyone needs to add a new row, it is **appended to the bottom**, never
inserted in the middle.

## The cherry-picked 5 for initial UAT

For the first pass after a deploy, testers only need to cover **5 rows** out
of the 10. These five are chosen to exercise every branch of the calculation
pipeline without taking all day. They are (in this order):

| # | Row in CSV | Purpose | What it exercises |
|---|---|---|---|
| 1 | Row 1 | First SFK job (2-layer) | SFK layer visibility, layers 3–5 hidden, no-flute path |
| 2 | Row 2 | First 3-ply job | 3-ply layer visibility, flute_type populated, board plan calc |
| 3 | Row 3 | Second 3-ply job with different flute | Flute variation, weight calc, board size variant |
| 4 | Row 4 | First 5-ply job | 5-ply layer visibility, all 5 GSM fields populated, heavier weight calc |
| 5 | **Row X — 3-ply → 5-ply conversion test** | Start as 3-ply, switch to 5-ply mid-form | Pipeline re-run on ply change, re-show of layers 4 & 5, recalculated board plan |

> **Pick the exact rows before UAT starts.** The manager decides which CSV
> row number becomes the "convert 3-ply to 5-ply" row for each UAT cycle —
> usually it is whichever row looks simplest so the tester is not fighting
> two variables at once. Write the chosen row number into `sign-off.md`
> before the UAT session starts.

## The other 5 — full regression pass

Rows 6 through 10 are the **full regression pass**. They are run once the
cherry-picked 5 are green, still in CSV order, to confirm nothing edge-casey
has broken. They usually catch:

* Unusual customer names with punctuation
* Very large quantities that stress `approximate_weight_grams`
* UPS layouts that require the child table
* Die-linked jobs (where `Dies` is referenced)

If a deploy only touches one area (e.g. print format), the manager may sign
off after the cherry-picked 5 and skip rows 6–10. This decision is recorded
on the sign-off sheet.

## Customer Product Specification test records

Every Carton Job Card in the CSV references a `Customer Product Specification`.
For UAT, testers **create the Customer Product Specification first** using the
dimensions and ply information from the CSV row, then open a new Carton Job
Card and link it — the auto-populate should then fill most fields for them.

This is deliberate: it exercises the auto-populate path, which is where most
regressions hide after a deploy.

## Things testers must not do

* Do not save or submit any test record until a manager is watching the screen.
* Do not edit the source CSV.
* Do not re-order the 10 rows.
* Do not test on live customer data — stick to the CSV.
* Do not create new Customer Product Specifications with customer names from
  real current orders — prefix test specs with `TEST-` so they can be cleaned
  up later.
