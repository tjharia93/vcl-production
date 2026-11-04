# Exercise books: what has been built

From the PC session (TMP-M034) on 04/11/2026. **The dev pages are not in git.** They are edited live over REST by several sessions. Pull the live page before you change one.

| What | Where | Writes | State |
|---|---|---|---|
| Exercise Book Production V2 | `/exercise-book-production-dev?mod=exercise` (Web Page `exercise-book-production-v2-dev`). Tabs: Orders Pending, Order & stock, Finished Stock, Cover Stock + Quick entry, Empty Cartons, Inserts, Packing; Excel/PDF exports | Covers: Material Receipt/Issue. Inserts: Repack. Packing: nothing (localStorage) | Live dev. PC snapshot `scratch\production-dev\live-exercise-book-production-dev.json` (04/11 09:27) |
| Production (dev) EB tracker | `/production-dev` | As above | Live dev. On 03/11 it was deployed from a stale copy, which reverted Receive 3 times, so Receive moved to `/receiving-dev`. `~/projects/vcl_production_dev` on Linux is STALE |
| Receiving (dev) | `/receiving-dev` | Computer paper only. Exercise books show "Coming later" | Live dev |
| EB stores receiving backend | vcl-production `feat/exercise-book-receiving` `a84ef92` (03/11): `production_floor/receiving_books.py` + tests, child doctype `VCL Stores Receipt Book Line`. Counts cartons + loose books, books/carton from the Carton UOM, spot-weighs ~5% of cartons and flags >5% off | Not yet | **Local only on the PC, not pushed.** No endpoints or screens |
| Print format "Prod Exercise Book" | Sales Order, Jinja, SL/SQ side by side | - | Deployed (02/11 16:18) |
| Compass Exercise Book Orders | `/compass/exercise-books`, vcl_compass main `5709b0a` | SO `vcl_eb_stage`/`_by`/`_on` + a Comment | Merged, not deployed. Needs a migrate + `compass_exercise_books` |
| Exercise Book department | vcl-production `71590c8` (02/09), branch `feat/departments-etr-sheeting-gs-exercise-tinting` | - | No machines. Merge not verified |
| Opening finished stock | `MAT-RECO-2026-00003` | Stock Reconciliation | Submitted 04/11, zero valuation |
| ESGA fixes | `SAL-ORD-2026-00195` amended twice. Generic "Prince Exe A5 48pgs Bank CB" disabled | SO, Item | Done 03/11 |
