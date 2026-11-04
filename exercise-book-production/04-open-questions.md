# Exercise books: open questions

- How are finished books received into stock in ERPNext? Until they are, stock reads 0.
- Who on the floor sets the order stage on Compass? (The role list includes Sales Manager,
  which every rep holds.)
- Deploying Compass Exercise Book Orders: it needs a migrate and the `compass_exercise_books`
  site config.
- Still to finish on the item master: packing for the 100-page books (45 items), the FNB
  ruling (14 items), the price for Prince A5 48 half-line, packing for A4 60-page Hi5 school,
  and every cover that is not chipboard (MNL/MGC).
- Is there going to be an Exercise Book Job Card / CPS? The tracker lists Exercise Books
  (and Monobox) as "still to build".
- Valuation: the opening finished stock (MAT-RECO-2026-00003) is at zero cost.
- Make packing a shared record, not browser-only: push `a84ef92` (PC only) and build its screen.
- Should "Required" reserve stock per order instead of reading all physical stock?
- SFS (SAL-ORD-2026-00175) is in Nos and carries legacy generic items.
- Put the dev pages in git. Live REST edits from several sessions have overwritten each other.
- Floor: where stitching and trimming sit, owners per handover, and wastage points.

## From Tanuj's comments, 04/11/2026 (see the "Your comments" tab)
- Add a **Folds** stage (input). Covers + folds inserted together = inserts. Today's Repack takes out the cover only.
- Paper → ruling moves to **phase 2/3**, together with school and customised exercise-book orders.
- The Mahavir order SAL-ORD-2026-00199 is confirmed demand.
- Empty-carton stock: the team counts on 05/11.
- Needed: flow by item type per stage, and brand and customer filters (data requested from the PC).
- **Cover unit:** the 30/10 opening (MAT-STE-2026-00007, 483,600, 91% of cover stock) is labelled "single covers", while later entries count sheets. As recorded, covers = 1,260,230 books. As single covers = 539,580. Books still to make: 1,085,336 vs 1,155,976. Tanuj to confirm.
- Inserts Repack today: COV out, INS in, 1:1, zero cost. No fold or inner item exists. Proposed `FLD-<PNC|SWR>-<A4|A5>-<PPP>PG-<RULING>`.

## School vs brand mis-selection (Tanuj, 04/11/2026)
People pick school items (Bank Paper / Newsprint, no brand) when they mean Prince / Swara. Sent to the PC session:
1. Rename the school item names to "School Exercise Book - <Paper> - <Size> - <Pages> Pages - <Ruling> - <Cover>". Codes unchanged.
2. A confirm prompt on Quotation and Sales Order lines ("Is this a school order?" / switch to the matching brand item, SCH-BP-EB → PNCEB, SCH-NP-EB → SWREB). Plus a server-side "School order confirmed" check.
The PC does a read-only analysis and a dry run first. Nothing goes live until Tanuj approves.

## Rate entered per Nos at the carton price (Tanuj, 04/11/2026)
Users enter e.g. 3,000/= for 1 Nos when they mean 1 Carton, on Opportunity, Quotation and Sales Order. The earlier request to "show the UOM on Quotation and Sales Order" is NOT in vcl-production (no Property Setter or Client Script in its fixtures). If it exists at all, it is live-only or in another app; the PC is checking.
Proposed control (sent to the PC as a dry-run pack together with the school guard):
1. Exercise-book items default to sales UOM = Carton, and UOM is visible and mandatory on the line.
2. A server-side validate on rate per stock unit vs the Standard Selling price per stock unit ("Did you mean 1 Carton?"), on every write path.
3. The same check in Compass and Android.
4. Clean the Standard Selling price list first (duplicate Carton rows, Nos prices at carton level). Related: TRK-00363.
The school prompt also applies everywhere an item is picked (Opportunity, Quotation, SO, Invoice, DN, Compass, Android, API), with a server guard as the backstop.
- **Decided (Tanuj, 04/11):** the default sales UOM for exercise books is **Carton**. The PC is preparing the change (dry-run count + backup) and applies it when Tanuj says go.
- **Rate band logic (Tanuj):** 1 book is about 100/=, and a carton is much higher. A Nos line priced in the carton range should prompt "Did you mean Carton?", and a Carton line priced in the per-book range should prompt "Did you mean Nos?". The bands come from real invoiced and price-list rates by size and pages, and act as a fallback while the price list is being cleaned.
- The PC is checking ALL git repos for the earlier "show UOM" change, every place lines are entered, and any existing price/UOM validation.

## Selling-line guards pack (PC, 04/11/2026), awaiting Tanuj's approval
- Pack: PC `C:\Second_Brain\output\selling_line_guards_pack_2026-11-04.md`. Code on branch `feat/school-item-guard` in vcl-production (from 2fc760d) and vcl_compass (from 35019c3), local and unpushed.
- School rename: 547/554 items; 448 have a brand twin (60 of those twins disabled), 99 have none.
- Guards on Opportunity, Quotation, SO, DN, SI (only new or changed lines are checked). The custom field and Property Setters are created in after_migrate.
- "Show UOM" was NOT done before (only a 02/11 Property Setter on the SO Item list view).
- Carton default: already set on all 455 items with a Carton row. 847 items have no Carton row.
- Rate band 3–150/= per book: it would have caught 72 Opportunity + 74 Quotation + 1 SO lines since 06/08. Check that 150 leaves headroom for the 200pg A4 price.
- Price list: 13 carton prices on Nos, 7 suspect MGC/MNL, 809 items with no price. **937 of 989 Carton invoice lines have conversion factor 1**, which needs its own fix.
- Still to wire for the UI prompt: Compass stock lines, deals, audit, capture; Android (app release); the vcl_sales enquiry page.

## Selling-line guards: status 04/11/2026 (evening)
- **School rename APPLIED live** (Tanuj approved): 547 items renamed "School Exercise Book - <Paper> - …", codes unchanged. Rollback: PC `C:\Second_Brain\output\school_rename_2026-11-04\apply_school_rename.js --rollback`.
- Checks built on branch `feat/school-item-guard` in vcl-production, vcl_compass, vcl_sales and vcl-android-app (PC, uncommitted). Compass: tsc clean, 495 frontend tests pass, pytest 838/839 (one failure, also failing on main). Android: 13 tests not run (no SDK on the PC).
- Deploy order: vcl-production (migrate) → Compass → vcl_sales → Android release. Not yet tried on a site.

## Dev page inventory (PC, 04/11/2026)
- Snapshot + INVENTORY.md on branch `dev-pages/eb-snapshot-2026-11-04` (PC worktree, NOT pushed; awaiting Tanuj's go, same as the four feat/school-item-guard branches).
- Live now and wrong: `/production-dev?mod=exercise` still writes (Material Issue "used in binding", 9-up/4-up options). Order & stock understates cover capacity 2× (A4) and 3× (A5) and can't see Repack inserts.
- Porting order: (1) git + deploy script `scripts/deploy_eb_dev_page.py`, retire the EB module on /production-dev; (2) bug fixes; (3) FLD + run number + Folds + server methods; (4) Packing Manufacture (a84ef92); (5) carton count; (6) plan/tracker/floor today, Compass dashboards; (7) tidy.
- Gap map: on the click-through's Porting tab.

## How the data links (PC answer, 04/11/2026)
- Stored links today: only the Repack (COV out + INS in on one Stock Entry) and SO → DN (so_detail). Everything else joins by parsing item codes and names (COV/FLD/INS/book twins; ups only in the item name).
- No run number anywhere yet. The chain breaks at Inserts → FG (packing not posted) and FG → Delivery (DNs ship from Stores against a same-day receipt).
- Numbers: the dev page computes in the browser (undercounts covers, misses Repacks). Compass EB Orders isn't deployed. The Data flow tab uses one-off pulls. No report exists.
- Recommendation: store the chain on Item (eb_cover_item, eb_fold_item, eb_insert_item, eb_ups; and eb_insert_item on books), or an "Exercise Book Set" doctype. One server-side report in vcl-production feeds the page, Compass and the dashboards.

## BOMs (P11): DECIDED by Tanuj 04/11/2026: no BOM for inserts, BOM per book for packing
- Site is ERPNext 16.53 / Frappe 16.54. No exercise-book BOMs exist (162 BOMs, all CP/labels). The 18/10 BOM master is only in the workbook (195 SKUs).
- On v16, Repack can use a BOM too. Valuation is identical for Repack and Manufacture (FIFO, zero today).
- Recommendation: NO BOM for inserts (fixed 1:1:1; the Repack adds the FLD row). YES a packing BOM per book (qty = books per carton ← INS sets + 1 carton), used as the reference, with a Manufacture of the actual counts.
- First: Carton UOM on the books being made (847 lack one), and a carton item per book or per size and brand (the A5 common carton is disabled).
- Chain stored as Item fields: eb_ups, eb_cover_item, eb_fold_item, eb_insert_item, eb_carton_item.
