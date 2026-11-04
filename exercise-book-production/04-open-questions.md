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
