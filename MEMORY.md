# MEMORY — read this first

Last updated: **2026-10-28** (stores receiving merged to main; machine made optional on the receipt)

## State — 2026-10-28
- App version in code: 1.0.0. Which commit is live on the site: unknown.
- Migrate pending: likely yes. The stores receiving merge (5b4bdca, 28/10) and 2169b95 (28/10) both
  say "Needs a migrate" (three new DocTypes, a new field, machine no longer required). Deployed: unknown.
- CP Job Traveller v2 TRK-00142 page-one changes (9741384, 27/10) are on main. No migrate; they go
  live only when `scripts/deploy_cp_traveller_v2.py` is run. Run: unknown.
- The transitional live Server Script `cps_revise_build` (14/10) is to be deleted from the site after
  deploy + migrate. Deleted: unknown.
- Production Floor CSS version in `hooks.py`: `?v=20260904`.
- Open items from `CHANGELOG_DAILY.md` (20/05): Telegram config for the 17:00 Gemba push; Hamada 01
  reclassification; renaming Slotter 01 / Bundler 01. Current status: unknown.
- `PROJECT_STATUS.md`, `BLOCKERS.md`, `DECISIONS.md`, `NEXT_ACTIONS.md` are a PMO pass of 07/06. Stale.

## What happened in dev
- 2026-10-28 Stores receipt: machine optional; an open receipt is found by weigher and day; a job card
  can be set at the start or later with `set_job_card` (Tanuj, 28 Oct).
- 2026-10-28 Merged `feat/stores-receiving`: VCL Stores Receipt, VCL Stores Receipt Carton, VCL Carton
  Standard, `stores.*` endpoints, `receiving.py` rules with tests (TRK-00279, built 17/10 and 19/10).
- 2026-10-27 CP Job Traveller v2 TRK-00142: Sales Rep from CSRA on the order date, Created by in the
  footer, page one at 9pt, packing printed divided by 10. Spec in `docs/superpowers/specs/`.
- 2026-10-09 to 10-14 Revise Customer Spec takes print colours, packing, a new price (v10_6), and a
  carton's size and build.
- 2026-09-15 Job Card Label Run Log: one row per design run on the press.
- 2026-09-12 to 09-14 CPS price mirror (spec prices the job, price list follows; v10_4, v10_5); price
  basis shown; specs shown on the Item form.
- 2026-09-01 to 09-05 Production Floor: start-of-day report, what yesterday left behind, route-to-board
  design and build, board advances job card stages, carry-forward duplicate fix (4b75480).
- 2026-08-26 to 08-30 Production Floor folded into this app as a module (PR #41); To Plan strip,
  Monobox and Reel to Reel departments, machines aligned to ERPNext Workstations, phone layout.
- 2026-08-15 to 08-18 Board Plan revise for old carton specs (v9_7); Dies naming, status, preview.
- 2026-08-05 to 08-09 Monobox job card and traveller; Flatbed Die; artwork tracker and weekly chase;
  CPS Create BOM button (v9_6); Print Type must agree with the linked Item.
- 2026-07-20 to 07-31 CPS controls on Sales Orders and job cards; carton and label order flows; Board
  Plan versioned; Carton Jobcard v2 under the app; CP finished size in inches; fixture repairs.
- 2026-07-01 to 07-11 QR scan-to-capture on the CP traveller; CP production stages; machine link on all
  job cards; CP traveller v2 sign-offs.
- 2026-05-19 to 05-28 S1 + S2: Job Traveller Run, Job Resource Consumption, carton workstations,
  Carton Layout page, ETR fix, status report.
- 2026-04-15 Hard reset: the production execution / planning layer removed (patch v1_0). PPC design
  and planner followed 16/04 to 05/05.
- 2026-03-28 First commits (README, `modules.txt`).

## Decisions
- D-01 Production execution layer removed for a clean restart (2026-04-15, README).
- D-02 Production Floor ships as a module of this app, not its own app; it keeps its own `VCL *`
  DocTypes with no Link to ERPNext documents (2026-08-26, `docs/production-floor/architecture.md`).
- D-03 A patch may only set values on rows that exist; creating a machine belongs in `after_migrate`,
  after `apply_select_options` and `seed_machines` (2026-08-30, a0e6d38).
- D-04 The specification prices the job; the price list follows. The mirror only touches Item Price
  rows carrying its CPS field (2026-09-12, 1f358bb; v10_4).
- D-05 A new price from Revise adds a Draft row only; approval stays with Sales Master Manager (2026-10-09).
- D-06 On a submitted carton spec, size and build change only through Revise (2026-10-14, a0d9900).
- D-07 Stores receiving: 2% tolerance by default; Red cartons are rejections, weighed but never posted;
  items post with zero valuation for now, quantity is the point of the trial (2026-10-17, ff351b7).
- D-08 Weighing does not need a machine; the board and the weighing are not connected yet (Tanuj, 2026-10-28).

## Traps
1. A throw inside `after_migrate` or a patch aborts the migrate for every app on the bench. The
   28/08 deploy failed this way (Monobox not yet a Select option) and the site was recovered.
2. `install_app()` stamps every patch as done without running it. Anything outside the app's own
   DocTypes must also be in `after_install` (see `install.py`).
3. `/assets` files are cached for a year as immutable. Bump `?v=` on `production_floor.css` (28/08).
4. Fixtures without a `doctype` key kill `sync_fixtures` with `KeyError: 'doctype'` (dab745f, 24/07).
   `test_fixture_integrity.py` guards it.
5. Do not `bench export-fixtures` against the live site before deploying a transitional fix; the
   live Client Script would overwrite the committed one (`docs/transitional/README.md`).
6. `validate()` does not run on update-after-submit. Revise re-checks its own rules on the server.
7. `try/except: pass` in patch v7_1 hid failed inserts; the records were made by hand (20/05).
8. The CP traveller Print Format is the live default. The repo HTML is the source of truth; change it
   only through `scripts/deploy_cp_traveller_v2.py`, then run `check_cp_traveller_pagination.py`.
9. `list_to_plan()` reads Job Card Tracking cards and writes one field (`job_status` Open to Planned).
   It is the one place Production Floor reaches out; it fails soft.
10. Carry-forward identity is machine + job card + job name only. Status decides whether the planned
   figure may change, not whether the row exists (4b75480).
