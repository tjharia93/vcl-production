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
