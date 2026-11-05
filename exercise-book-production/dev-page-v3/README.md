# Exercise Book Production v3: capture page

Route `/exercise-book-production-v3-dev`, Web Page `exercise-book-production-v3-dev`, title "Exercise Book Production v3 (preview)". This page is new. It does not touch `exercise-book-production-v2-dev` or `/production-dev`.

## What it does
The stations run Covers → Folds → Inserts → Packing → Finished Goods, with the process flowchart on top. Ruling is greyed out (Phase 2/3).

| Station | Entry posted | Rows |
|---|---|---|
| Covers | Material Receipt | COV-x sheets into Stores - VCL. Spoiled sheets are recorded, not added |
| Folds | Material Receipt | FLD-x sets into Stores - VCL. Rejects are recorded, and an opening count is offered |
| Inserts | Repack, no BOM (P11) | COV-x out and FLD-x out (× sets), INS-x in (× sets). Blocked when short; the fold check can be held off, and that is logged |
| Packing | Manufacture | INS-x out = ceil((books + rejects) ÷ ups); empty cartons out; book into Finished Goods - VCL. Spot-weigh 1 in 20 at ±5% |
| Finished Goods | view | Finished Goods - VCL only, with open orders earliest-delivery first and the shortfall |

Covers, folds and inserts count in sets with the same up-count: A4 2-up, A5 3-up, read from the item name. Only packing counts books.

## Screens (05/11/2026)
Three screens, chosen with the switch at the top (`?view=capture|orders|orderstock`, remembered per browser):
- **Capture**: the stations above.
- **Orders**: the v1 "Orders Pending" screen. Covers all exercise-book item groups (Prince, Swara, Hi5, School), except Covers, Inserts and Folds.
  - Grid of ordered / delivered / pending per brand, as size × pages rows and ruling columns. It counts confirmed orders only: no drafts, cancelled or closed.
  - List of open lines, or all non-cancelled lines, earliest delivery first.
  - Filters: search, brand, customer, size, pages, ruling. Books or Cartons switch. Excel download (ExcelJS from `/files/vcl-exceljs-4.4.0.js`, or CSV if that file is missing). Print / PDF.
  - Reads everything in one `get_list` on Sales Order child rows, instead of v1's one fetch per order.
- **Order & stock**: the v1 comparison, rebuilt on the sheet/set model. Each book type shows pending, Finished Goods (Finished Goods - VCL only), still to make, inserts / covers / folds in Stores (sets or sheets × up-count), short, sheets to print, and empty cartons (a shared pool per size and brand).
  - Short = still to make − (inserts + covers) × up-count. Folds aren't counted yet, because there's no fold count.
  - School and Hi5 have no cover/fold/insert items yet, so only their orders and Finished Goods are compared.
  - Fixes these v1 faults: covers were counted as books instead of sheets; Repacks were missing from inserts; finished stock came from every warehouse.
- Left out of v1: the aging board and the Packing/Materials modes. They read one person's browser storage only.

## Look
Material 3, using the VCL Android app's own tokens and shapes (`ui/theme/Color.kt`, `Shapes.kt`):
- VCL Blue #2B3990 primary on cool tinted surfaces (#F4F6FA page, white cards).
- Carlito/Calibri text.
- Outlined fields with the label on the outline.
- Pill buttons and segmented buttons.
- 16px cards, 12px fields, 28px dialogs.

## Posting (Tanuj, 04/11/2026)
- Every post is **confirmed twice**: "Is this correct?" (every row) and then "Post to ERPNext now?" (totals). Post now is never pre-focused, and Enter does nothing.
- Undo is open to the same user for 10 minutes, and is also confirmed twice.
- The server is `production_log/production_floor/eb_capture.py` (`get_mode`, `post_entry`, `undo_entry`).
  - It is whitelisted and limited to Stock and Manufacturing roles.
  - It re-plans each entry against live stock using `eb_capture_rules.py`, then inserts and submits in one request.
  - It refuses anything that hasn't been confirmed twice (`confirmed=2`).
  - Site config `eb_capture_disabled = 1` switches all posting off.
- The remarks start with: `Capture v3 · run <run> · confirmed twice by <user> at <time>`.
- Until vcl-production is deployed and migrated, the page says **"Server update needed"** and posts nothing.

## Config to revisit
- **Carton per size + brand** (`CARTONS` in `page.js` and in `eb_capture_rules.py`): this is the P12 proposal, still open for Tanuj.
- **A5 carton item** (`PNCSWR-EMPTY-CARTON-A5-PLAINF-DPL`) is disabled. Until it is enabled, A5 packing doesn't take out cartons, and the page warns about it.
- **Run number**: carried in the remarks. It also goes in `custom_eb_run` once that field exists.

## Deploy (only with Tanuj's go)
```bash
py -3 scripts/deploy_eb_dev_page.py --page v3 --check
py -3 scripts/deploy_eb_dev_page.py --page v3 --create
```
- **First deploy** creates the Web Page and writes `deploy-stamp.json`; commit that file.
- **Later deploys** run without `--create`. The script refuses if the live page changed since the last stamp.
- The server methods arrive only with a vcl-production deploy and migrate on Frappe Cloud.

## Tests
- `production_floor/tests/test_eb_capture_rules.py` (rules) and `tests/test_receiving_books.py` (spot-weigh, from a84ef92).
- `page.js` mirrors the rules. It was checked by hand against live stock through a local read-only harness on 04/11 (screenshots are outside git, in `C:\Second_Brain\output\eb_capture_v3_screenshots\`).
