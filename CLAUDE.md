# VCL Production (`production_log`) — start here

A Frappe app on ERPNext for Vimit Converters Ltd. It holds the master data and job cards for
the factory: Customer Product Specifications (CPS), the Job Card types (Computer Paper, Label,
Carton, ETR, Monobox), Dies, the PPC planning layer, the print-format travellers, and the
Production Floor module (daily production entry and stores receiving, `/app/vcl-production-lite`).

**Read `MEMORY.md` next**: current state, decisions and traps.

## Where it runs
- Site: https://vimitconverters.frappe.cloud
- Deploys from branch: `main` (the default branch). Pushing to main does NOT deploy. Tanuj
  deploys on Frappe Cloud, and runs a migrate when a DocType or patch changes.
- Frappe Cloud builds the app at the repo ROOT. A second app in a subfolder ships as inert files.
- Some things deploy outside the migrate: the CP Job Traveller v2 print format goes live only with
  `scripts/deploy_cp_traveller_v2.py` (`--check` diffs live against the repo).
- Desk hooks into ERPNext: `doc_events` on Sales Order, Item, Item Group and Workstation Type;
  three daily/weekly scheduler jobs (Gemba EOD, artwork chase, CPS price mirror) in `hooks.py`.

## Working rules
- Commit as `-c user.name=Claude -c user.email=noreply@anthropic.com`.
- Never put an API key, token or password in the repo or in chat.
- A patch may only `db.set_value` on rows that already exist. Anything that creates a record goes
  in `after_migrate` / `after_install` (see `install.py`, `production_floor/install.py`).
- Bump the `?v=` on `app_include_css` in `hooks.py` on every change to `production_floor.css`.
- Tests are plain `unittest`, no bench, no site:
  `python3 -m unittest discover -s production_log/production_floor/tests -t .` and
  `python3 -m unittest discover -s production_log/job_card_tracking -p 'test_*.py' -t .`.
  Four modules import `frappe` and error without a bench. How those run: unknown.
- OAT/UAT plans: `docs/testing/`, `testing/`, `testing/production-floor/`.

## Map
| Path | What lives there |
|---|---|
| `production_log/job_card_tracking/` | CPS, Job Card DocTypes, Dies; `*_rules.py` = pure logic with `test_*.py` beside it |
| `production_log/production_floor/` | daily production board, routes, stores receiving (`stores.py`, `receiving.py`) |
| `production_log/ppc/` | PPC Daily Plan / Production Actual DocTypes, page, report |
| `production_log/production_log/` | Production Entry, Schedule Line, Workstation Product Line Tag, CP planning board |
| `production_log/api/` | `gemba.py`, `artwork_chase.py`, `release_plan.py`, `workstation_type.py` |
| `production_log/patches/`, `patches.txt` | migrate patches (v1_0 to v10_6), each explained in `patches.txt` |
| `production_log/fixtures/` | Print Formats, Custom Fields, Client Script that a deploy applies |
| `scripts/` | traveller deploy and pagination checks; `transitional/` Server Script builders |
| `docs/` | design specs and plans (`docs/superpowers/`), department process docs, `production-floor/architecture.md` |
| `docs/transitional/` | copies of live-only Server Scripts and when to retire them |
| `CHANGELOG_DAILY.md` | direct live ERPNext changes (Custom Fields, Workstations) recorded by hand |
