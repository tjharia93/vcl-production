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

## Units (Tanuj, 05/11/2026)
Cartons are the main figure everywhere, with books in small print underneath.
- A book's cartons = books ÷ its Carton UOM conversion (books per carton).
- Covers, folds and inserts: sheets (or sets) × up-count = books, then ÷ books per carton.
- A line or item without a Carton UOM shows books and is flagged ("no carton unit"). It stays in the book totals and is left out of the carton totals.
- Capture entries are still keyed and posted in sheets, sets and books. Cartons are shown beside them.

## Look
Salesforce Lightning (SLDS) structure:
- page header with an icon tile;
- tabs for the three screens;
- bordered white cards on #F3F3F3;
- labels above the fields;
- neutral and brand buttons;
- a chevron path for the stations;
- Lightning data tables, badges, scoped notifications, and a modal for the two confirmations.

It's themed with VCL Blue #2B3990 as the brand colour and Calibri text. Touch targets stay at 44px or more for the floor tablets.
