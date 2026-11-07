# Exercise Book Production v3: capture page

Route `/exercise-book-production-v3-dev`, Web Page `exercise-book-production-v3-dev`, title "Exercise Book Production v3 (preview)". This page is new. It does not touch `exercise-book-production-v2-dev` or `/production-dev`.

## What it does
The stations run Covers → Folds → Inserts → Packing → Finished Goods, on the path at the top of Capture. Ruling is Phase 2/3.

| Station | Entry posted | Rows |
|---|---|---|
| Covers | Material Receipt | COV-x sheets into Stores - VCL. Spoiled sheets are recorded, not added |
| Folds | Material Receipt | FLD-x sets into Stores - VCL. Rejects are recorded, and an opening count is offered |
| Inserts | Repack, no BOM (P11) | COV-x out and FLD-x out (× sets), INS-x in (× sets). Blocked when short; the fold check can be held off, and that is logged |
| Packing | Manufacture | INS-x out = ceil((books + rejects) ÷ ups); empty cartons out; book into Finished Goods - VCL. Spot-weigh 1 in 20 at ±5% |
| Finished Goods | view | Finished Goods - VCL only, with open orders earliest-delivery first and the shortfall |

Covers, folds and inserts count in sets with the same up-count: A4 2-up, A5 3-up, read from the item name. Only packing counts books.

## Screens (05/11/2026)
Four screens, chosen on the navigation bar (`?view=capture|production|orders|orderstock`, remembered per browser):
- **Capture**: the stations above, laid out for one person entering one count.
  - The item comes first, then the station, run, date and shift, then the count. Post stays in a bar fixed to the bottom of the screen.
  - The item choice sits on the screen, not in a dropdown: brand or school, pages, size and ruling as chips, with a search box beside them. Tap a chip to change from that step. A step with one choice is skipped. While an item is half chosen, the count, preview and Post are hidden, and Cancel keeps the current item. Recent items show under the brand tiles. Hi5 and School show greyed out until they have cover, fold and insert items.
  - "Already posted" lists what ERPNext holds for this station and item on the chosen date, from every tablet. It refreshes every minute and again when Post is pressed. The same count for the same item and date gives a duplicate warning, which also shows at step 1. It warns; it doesn't block.
- **Production**: what each process made, one week at a time (Monday to Sunday).
  - Headline cards: each process's week total, today and a seven-day trend.
  - By date: a chart of cartons per day for each process, with a Table switch for the exact figures. Tapping a day narrows the item list to it.
  - By item: the same four processes per book type. Tapping a row shows that type's days. Filters: brand, size, pages, ruling. Excel lists every entry.
  - Reads submitted Stock Entries: COV-/FLD- Material Receipts and INS- Repacks into Stores, book Manufactures into Finished Goods. Remarks containing "opening" are left out, and so are book stock-ins for goods already delivered, because they aren't Manufactures.
- **Orders**: the v1 "Orders Pending" screen. Covers all exercise-book item groups (Prince, Swara, Hi5, School), except Covers, Inserts and Folds.
  - Grid of ordered / delivered / pending per brand, as size × pages rows and ruling columns. It counts confirmed orders only: no drafts, cancelled or closed.
  - List of open lines, or all non-cancelled lines, earliest delivery first.
  - Filters: search, brand, customer, size, pages, ruling. Books or Cartons switch. Excel download (ExcelJS from `/files/vcl-exceljs-4.4.0.js`, or CSV if that file is missing). Print / PDF.
  - Reads everything in one `get_list` on Sales Order child rows, instead of v1's one fetch per order.
- **Order & stock**: the v1 comparison, rebuilt on the sheet/set model. Each book type shows pending, Finished Goods (Finished Goods - VCL only), still to make, inserts / covers / folds in Stores (sets or sheets × up-count), short, sheets to print, and empty cartons (a shared pool per size and brand).
  - Layout: the shortfall as one headline, a bar splitting open orders into Finished Goods, inserts and covers, short, and not tracked, then one row per book type. Tapping a row opens its inserts, covers, folds, empty cartons, order lines and item codes.
  - Short = still to make − (inserts + covers) × up-count. Folds aren't counted yet, because there's no fold count.
  - School and Hi5 have no cover/fold/insert items yet, so only their orders and Finished Goods are compared.
  - Fixes these v1 faults: covers were counted as books instead of sheets; Repacks were missing from inserts; finished stock came from every warehouse.
- Left out of v1: the aging board and the Packing/Materials modes. They read one person's browser storage only.

## Units (Tanuj, 05/11/2026)
Cartons are the main figure everywhere, with books in small print underneath.
- A book's cartons = books ÷ its Carton UOM conversion (books per carton).
- Covers, folds and inserts: sheets (or sets) × up-count = books, then ÷ books per carton.
- A line or item without a Carton UOM shows books and is flagged ("no carton unit"). It stays in the book totals and is left out of the carton totals.
- Capture entries are still keyed and posted in sheets, sets and books. Cartons are shown beside them.

## Look
Salesforce Lightning (SLDS) structure:
- page header with an icon tile;
- a navigation bar with app launcher, app name and tabs for the four screens;
- bordered white cards on the Lightning blue-grey backdrop;
- labels above the fields;
- neutral and brand buttons;
- a chevron path for the stations;
- Lightning data tables, badges, scoped notifications, and a modal for the two confirmations.

Production also trials the newer Lightning style: soft shadows, rounder corners and fewer lines, scoped with `[data-view="production"]`. It uses the Lightning brand blue #0176D3 and a Salesforce Sans / Segoe UI font stack, with no Salesforce logos. Touch targets stay at 44px or more for the floor tablets.

## Date and shift (Tanuj, 05/11/2026)
- Every capture has a **production date** and a **shift**, next to the run number.
  - The date defaults to today. It can go back up to 7 days, never ahead.
  - The shift is Day Shift or Night Shift, the same as PPC. It's remembered per browser.
- A back-dated entry shows a warning. The date and shift appear in the preview and in both confirmations.
- The server checks them again (`eb_capture_rules.check_when`), then posts the Stock Entry on that date with `set_posting_time`.
  - Today's entries post at the current time.
  - Back-dated ones post at the shift's set time: Day 17:00, Night 23:00.
- Both go in the remarks ("Production 04-11-2026 Night Shift"). The shift also goes in `custom_eb_shift` when that field exists on Stock Entry. It isn't created yet.

## Machines (Tanuj, 05/11/2026)
- The list lives on **VCL Production Machine**: `asset` links to the Asset, and `eb_stations` lists the Capture stations it runs, one per line.
- **To add a machine:** fill those two fields on its record. To retire one, untick Active; never delete it. Neither needs code or a deploy.
- Each active machine listed for a station shows as a tile beside run, date and shift. A station with machines needs one on every entry, and the server checks it (`eb_capture_rules.check_machine`). A station with none, or a server without `get_mode.machines`, shows no tiles and posts as before.
- The machine and its asset go in the remarks, and the machine goes in `custom_eb_machine` on the Stock Entry (created in `production_floor/install.py`).
- Solna and Miller are set for Covers by patch `v10_10.link_cover_machines`.

## Posting (Tanuj, 04/11/2026)
- Every post is **confirmed twice**: "Is this correct?" (every row) and then "Post to ERPNext now?" (totals). Post now is never pre-focused, and Enter does nothing.
- Undo is open to the same user for 10 minutes, and is also confirmed twice.
- The server is `production_log/production_floor/eb_capture.py` (`get_mode`, `post_entry`, `undo_entry`).
  - It is whitelisted and limited to Stock and Manufacturing roles.
  - It re-plans each entry against live stock using `eb_capture_rules.py`, then inserts and submits in one request.
  - It refuses anything that hasn't been confirmed twice (`confirmed=2`).
  - Site config `eb_capture_disabled = 1` switches all posting off.
- The remarks start with: `Capture v3 · run <run> · confirmed twice by <user> at <time>`.
- If the server methods are missing, the page says **"Server update needed"** and posts nothing.
- The server on the site can be older than the page. `get_mode` returning `shifts` is how the page knows it handles date and shift. Without it, a past date blocks Post, and today's entries post with a warning that the shift isn't saved.

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

## Stock recon / true-up (07/11/2026)

Open `?view=recon`. Choose a brand, then count cover sheets, fold sets, insert sets,
finished books or shared empty cartons. Finished books accept full cartons plus loose
books using the exact item's Carton conversion. Other stages use their native sheet/set
count. Cover variants and warehouses are kept separate. Batch/serial items and stock
units other than Nos are referred to Desk. Disabled items are excluded.

Blank means uncounted; an explicit zero means none found. Counts survive switching
filters and screens during the current page visit. Leaving/reloading warns about unsaved
counts. The review covers every counted item with a variance, including hidden filters;
matching counts are omitted. ERP quantities and Bin modification times are checked again
before review. A movement requires another review. Catalog and balance reads paginate.

**Create draft** uses standard `frappe.client.insert` for a Stock Reconciliation with
absolute counted quantities, the company and warehouse, and server-default posting time.
It never submits or creates a production receipt. ERPNext enforces document permissions
and stock/accounting validation. Valuation is passed as null so ERPNext resolves its
existing rate; the count screen does not fetch rates. Allowing a zero derived rate is an
explicit opt-in and does not overwrite an existing rate. The required reason is added as
a Comment on the draft; if that fails, the draft link stays visible with the reason to
add before submission. A lost/malformed response locks out duplicate creation.

Review posting date/time, rates, difference account and any stock movements since the
count in **ERPNext**, then Submit there. Submission is the step that changes stock.
The page makes no assumption that capture kill-switch/roles grant reconciliation rights.
No Frappe Cloud backend deploy or migration is needed for this screen.

Offline browser checks (requires Playwright and Chrome):
```bash
python scripts/test_eb_stock_recon.py
```
These intercept every API call and check blank/zero/matching counts, carton conversion,
exact cover variants, filters, stale balances, draft/comment failure, duplicate prevention,
permission refusal, pagination beyond 500 items, and phone layout. No live stock is written.
