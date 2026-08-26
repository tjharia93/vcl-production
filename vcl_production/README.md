# VCL Production Lite

A standalone Frappe app for Vimit Converters Ltd that replaces the WhatsApp
production thread with structured daily entry — without asking the production
floor to do any more typing than they do now.

The target is unchanged from the brief: a supervisor opens the site on their
phone and records

> M1 → Chandaria → Yellow Copy → 3 reels

in about ten seconds.

## What it is not

This is not an MRP. There is no BOM, no material consumption, no costing, no
stock movement, no scheduling engine, no OEE, no attendance. A production day
is a list of "this machine is running this job, here is the plan and here is
what actually came off it".

## Running on plain Frappe

`hooks.py` declares `required_apps = []`. Nothing in this app reads ERPNext,
links to an ERPNext DocType, or breaks if ERPNext is absent. It happily shares
a site with ERPNext and with the `production_log` app — see
[docs/architecture.md](docs/architecture.md) for how the two relate and what
changes when the ERPNext integration lands.

## Install

```bash
cd ~/frappe-bench

# The app lives in a subdirectory of the vcl-production repo for now.
git clone -b claude/vcl-production-lite-app-vdyitz \
    https://github.com/tjharia93/vcl-production /tmp/vcl-src

bench get-app /tmp/vcl-src/vcl_production
bench --site <your-site> install-app vcl_production
bench --site <your-site> migrate
bench build --app vcl_production      # optional; the page works without it
```

Install seeds the two roles and the machine list. It does not create any
production data.

Open **`/app/vcl-production-lite`** on a phone. (`/app/vcl-production` is
already taken by the `production_log` app's workspace on VCL's site, so this
app uses its own route — nothing of the existing app is touched.)

## Screens

| Route | What it is |
| --- | --- |
| `/app/vcl-production-lite` | The production floor screen — today, report, history |
| `/app/production-floor` | Desk workspace with shortcuts to the masters |
| `/app/vcl-daily-production` | The day documents, as ordinary Frappe forms |
| `/app/vcl-production-job` | Remembered jobs |
| `/app/vcl-production-machine` | Machines and processes |
| Report → *VCL Daily Production Report* | Tabular view, filterable by date range |

## Data model

```
VCL Daily Production            one document per production date
  └── VCL Daily Production Item (child table) one row per machine × job
VCL Production Job              remembered customer + job pairs
VCL Production Machine          machines and processes, by department
VCL Production Settings         departments, units, closing behaviour
```

Customer and job are **snapshotted** onto every row. Renaming or deactivating
a remembered job later never rewrites what actually ran.

## Roles

| Role | Can |
| --- | --- |
| VCL Production User | Enter and update today's production |
| VCL Production Manager | The above, plus close/reopen the day and edit the masters |

## Closing the day

Six checks run against every day. Three are **critical** and block closing:

- carried forward with no reason
- paused with no reason
- completed with no actual quantity

Three are **warnings** shown as ATTENTION REQUIRED but never block anything:

- still Planned at the end of the day
- never started
- running with no actual quantity yet

A manager can turn the blocking off in **VCL Production Settings**. Nothing is
enforced mid-shift beyond a reason when a job is actually marked paused or
carried forward, so a busy afternoon is never blocked by a validation.

## Testing before a release

Deploy and functional plans, in the same shape as the `production_log` ones:

- [`docs/testing/oat-plan.md`](docs/testing/oat-plan.md) — install, migrate,
  rollback, and the checks that `production_log` is untouched. Run first.
- [`docs/testing/uat-plan.md`](docs/testing/uat-plan.md) — 24 scenarios run by
  a supervisor on a phone. Run second.
- [`docs/testing/sign-off.md`](docs/testing/sign-off.md) — copy per release.

### Automated tests

The report wording and the exception rules need no bench:

```bash
cd vcl_production
python3 -m unittest discover -s tests
```

The parts that need a database:

```bash
bench --site <your-site> run-tests --app vcl_production
```

## Demo data

```bash
bench --site <your-site> console
>>> from vcl_production.setup.seed import seed_demo_jobs, seed_demo_day
>>> seed_demo_jobs()
>>> seed_demo_day()
```

Both refuse to run unless the site is in developer mode (pass `force=True` to
override). Everything they create is flagged `is_demo`, is excluded from the
report by default, and is labelled **Demo** on screen.
