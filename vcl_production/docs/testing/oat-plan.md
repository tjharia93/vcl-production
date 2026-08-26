# OAT Plan — VCL Production Lite (`vcl_production`)

**Operational Acceptance Testing.** Run by whoever performs the deploy. This
checks the *deploy itself* is healthy — the app installs, patches run, the
desk still loads, and **`production_log` is untouched** — independent of the
functional scenarios in [`uat-plan.md`](./uat-plan.md).

Run OAT **first**, UAT **second**. If OAT fails, UAT cannot begin.

---

## Deployment focus

> **Update this section in every PR.** Note anything the deployer must watch
> for: new patches, fixtures, hooks, role changes, route changes.

### 2026-08-26 — First install of `vcl_production`

**This is a brand new app, not a change to `production_log`.** It is installed
alongside it on the same site. Nothing in `production_log` is modified.

**Patches that will run on `bench migrate`:**

* `vcl_production.patches.v0_1.seed_initial_data` — idempotent, safe to
  re-run. Creates the two roles, materialises the Settings Single, seeds any
  missing machine, and applies the department/unit Property Setters. On a site
  that already has all four, it does nothing.

**DocTypes created (5):**

| DocType | Kind | Naming |
|---|---|---|
| `VCL Daily Production` | standard, not submittable | `format:VCL-PROD-{production_date}` |
| `VCL Daily Production Item` | child table | — |
| `VCL Production Job` | standard | `VPJ-.YYYY.-.#####` |
| `VCL Production Machine` | standard | `field:machine_name` |
| `VCL Production Settings` | **Single** | — |

**Roles created (2):** `VCL Production User`, `VCL Production Manager`.

**Unique constraints — the two most likely install failures:**

* `VCL Daily Production.production_date` is `unique: 1`.
* `VCL Production Job.normalised_key` is `unique: 1`.

Both are new tables on a fresh install, so neither can collide. If this app is
ever reinstalled over existing data, these are the two to check first.

**Routes claimed:**

| Route | What |
|---|---|
| `/app/vcl-production-lite` | Frappe Page (the floor screen) |
| `/app/production-floor` | Workspace |

**`/app/vcl-production` is NOT claimed** — that stays `production_log`'s
workspace. Step 5.2 below verifies this.

**Hooks:** `after_install`, `after_migrate`, `before_uninstall`,
`app_include_css`. **No `doc_events`, no `scheduler_events`, no
`doctype_js`, no fixtures.** This app hooks nothing belonging to ERPNext or
`production_log`.

**Assets:** `app_include_css` points at a plain file, not a bundle, so the
screen works without `bench build`. Running `bench build` is still
recommended and harmless.

**Property Setters:** the patch writes system-generated Property Setters on
the `department` and `uom`/`default_uom` Select fields of three DocTypes, all
owned by this app. None touch a `production_log` or ERPNext DocType.

---

## 1. Pre-deployment

- [ ] **1.1** Take a full site backup with files:
      `bench --site <site> backup --with-files`
- [ ] **1.2** Record the current app list and versions:
      `bench --site <site> list-apps` — screenshot it.
- [ ] **1.3** Confirm the site is currently healthy: log in as Administrator,
      open `/app/vcl-production` (the existing `production_log` workspace) and
      `/app/ppc`. Both must load. Screenshot both.
- [ ] **1.4** Note the current row count of the busiest existing table, for
      comparison after install:
      `bench --site <site> mariadb -e "SELECT COUNT(*) FROM \`tabCustomer Product Specification\`"`
- [ ] **1.5** Confirm no existing DocType name starts with `VCL Production` or
      `VCL Daily Production`:
      `bench --site <site> mariadb -e "SELECT name FROM tabDocType WHERE name LIKE 'VCL %'"`
      Expected: empty. If not empty, **stop** — investigate before installing.

## 2. Install

- [ ] **2.1** Fetch the app:
      ```
      cd ~/frappe-bench
      git clone -b claude/vcl-production-lite-app-vdyitz \
          https://github.com/tjharia93/vcl-production /tmp/vcl-src
      bench get-app /tmp/vcl-src/vcl_production
      ```
- [ ] **2.2** Confirm bench sees it as its own app, named `vcl_production`:
      `ls ~/frappe-bench/apps/vcl_production/` — must contain `pyproject.toml`
      and a `vcl_production/` package.
- [ ] **2.3** `bench --site <site> install-app vcl_production` — completes with
      no traceback.
- [ ] **2.4** `bench --site <site> migrate` — completes with no traceback.
- [ ] **2.5** `bench build --app vcl_production` — completes (optional but do it).
- [ ] **2.6** `bench restart` (or `bench --site <site> clear-cache` on Frappe Cloud).

## 3. Post-install verification

- [ ] **3.1** All five DocTypes exist:
      `bench --site <site> mariadb -e "SELECT name, issingle, istable FROM tabDocType WHERE module='VCL Production' ORDER BY name"`
      Expected 5 rows, with `VCL Production Settings` `issingle=1` and
      `VCL Daily Production Item` `istable=1`.
- [ ] **3.2** Both roles exist:
      `bench --site <site> mariadb -e "SELECT name FROM tabRole WHERE name LIKE 'VCL Production%'"`
      Expected: `VCL Production Manager`, `VCL Production User`.
- [ ] **3.3** Machines seeded — expect **15**:
      `bench --site <site> mariadb -e "SELECT department, COUNT(*) FROM \`tabVCL Production Machine\` GROUP BY department"`
      Expected: Carton 6, Computer 5, Labels 1, Offset 3.
- [ ] **3.4** Settings Single is materialised and populated:
      open `/app/vcl-production-settings`. Departments and Units are both
      filled in. Both checkboxes are ticked.
- [ ] **3.5** Property Setters landed:
      `bench --site <site> mariadb -e "SELECT doc_type, field_name FROM \`tabProperty Setter\` WHERE doc_type LIKE 'VCL %'"`
      Expected 5 rows across `VCL Production Machine`,
      `VCL Daily Production Item`, `VCL Production Job`.
- [ ] **3.6** **No production data was created by the install.** Both must
      return 0:
      `SELECT COUNT(*) FROM \`tabVCL Daily Production\`` and
      `SELECT COUNT(*) FROM \`tabVCL Production Job\``.
      A non-zero count here means demo data ran on a live site — **stop and
      investigate.**

## 4. Smoke tests

- [ ] **4.1** As Administrator, open **`/app/vcl-production-lite`**. The page
      renders: date bar, three tabs, five summary cards all showing 0, and an
      empty state reading "Nothing entered yet".
- [ ] **4.2** The stylesheet loaded — the summary cards have coloured left
      borders and the tabs are underlined, not unstyled browser defaults. If
      they look unstyled, `bench build` and hard-refresh.
- [ ] **4.3** Open **`/app/production-floor`**. Six shortcuts render and each
      one opens its target.
- [ ] **4.4** Open **Report → VCL Daily Production Report**. It loads with a
      From/To date filter defaulting to today and returns an empty result.
- [ ] **4.5** Open the list views for `VCL Production Job` and
      `VCL Production Machine`. Both load. The machine list shows 15 rows.
- [ ] **4.6** Browser console is free of 404s and JS errors on
      `/app/vcl-production-lite`.

## 5. Non-interference — the critical section

**This is the check that matters most. `production_log` is live.**

- [ ] **5.1** `bench --site <site> list-apps` still lists every app it listed
      at step 1.2, plus `vcl_production`.
- [ ] **5.2** **`/app/vcl-production` still opens `production_log`'s "VCL
      Production" workspace**, with its Customer Specifications / Job Card
      Tracking / Production Planning shortcuts — *not* the new app. Compare
      against the screenshot from step 1.3.
- [ ] **5.3** `/app/ppc` loads unchanged. Compare against step 1.3.
- [ ] **5.4** Open one existing Customer Product Specification and one Job
      Card Computer Paper. Both load and their fields are unchanged.
- [ ] **5.5** Row count from step 1.4 is identical.
- [ ] **5.6** No Property Setter, Custom Field or Client Script was created
      against a non-`VCL ` DocType by this install:
      `SELECT doc_type FROM \`tabProperty Setter\` WHERE modified > '<install timestamp>'`
      — every row must start with `VCL `.
- [ ] **5.7** The `production_log` scheduler jobs (Gemba EOD 17:00 EAT,
      artwork chase Friday) are still registered:
      `bench --site <site> doctor` or check **Scheduled Job Type**.

## 6. Independence from ERPNext

- [ ] **6.1** `grep -r "erpnext" ~/frappe-bench/apps/vcl_production --include=*.py --include=*.json -il`
      returns only the reserved-field definitions and the docs — no import, no
      `frappe.get_doc("Item"...)`, no Link with an ERPNext target.
- [ ] **6.2** `required_apps` is empty:
      `grep required_apps ~/frappe-bench/apps/vcl_production/vcl_production/hooks.py`
- [ ] **6.3** *(Optional but worth doing once)* Install `vcl_production` on a
      scratch site that has **no ERPNext**. Install, migrate, and open
      `/app/vcl-production-lite`. If this fails, the app has grown a
      dependency it is not supposed to have.

## 7. Idempotency

- [ ] **7.1** Run `bench --site <site> migrate` a second time. No traceback.
- [ ] **7.2** Machine count is still **15** — the seed did not duplicate.
- [ ] **7.3** Manually deactivate one machine (untick Active on `M2`), then
      `bench migrate` again. `M2` is **still deactivated** — the seed does not
      resurrect or overwrite an existing machine.
- [ ] **7.4** Add a department (`Guillotine`) in Settings, save, then
      `bench migrate`. The department is still there and still appears in the
      dropdown on `VCL Production Machine`.

## 8. Automated tests

- [ ] **8.1** Bench-side tests pass:
      `bench --site <site> run-tests --app vcl_production`
      Expected: 8 tests in `TestVCLDailyProduction`, all passing.
      > These create and delete a production day dated **400 days in the
      > future**, precisely so they cannot collide with real data. If you see
      > a `VCL-PROD-` document for a date about 13 months out afterwards, the
      > teardown failed — delete it.
- [ ] **8.2** Bench-free tests pass:
      `cd ~/frappe-bench/apps/vcl_production && python3 -m unittest discover -s tests`
      Expected: 27 tests, all passing.

## 9. Permissions spot-check

- [ ] **9.1** Create a throwaway user with **only** `VCL Production User`.
- [ ] **9.2** They can open `/app/vcl-production-lite` and add a job.
- [ ] **9.3** The **Close Production Day** button is **not shown** to them.
- [ ] **9.4** They cannot create or edit a `VCL Production Machine` (no
      Create/Write on the list view).
- [ ] **9.5** Add `VCL Production Manager` to the same user. **Close
      Production Day** now appears and machines become editable.
- [ ] **9.6** Delete the throwaway user.

## 10. Rollback

Rehearse this before you need it.

- [ ] **10.1** `bench --site <site> uninstall-app vcl_production --dry-run`
      first, and read what it intends to drop.
- [ ] **10.2** Full uninstall on a **scratch** site:
      `bench --site <scratch> uninstall-app vcl_production`
      Confirm `production_log` and ERPNext still work afterwards.
- [ ] **10.3** Note: `before_uninstall` deletes the two roles. It does **not**
      delete production data — the tables go with the DocTypes as Frappe drops
      them. **If there is real production data you want to keep, back up
      first.** Rolling back after a week of live use loses that week.
- [ ] **10.4** Worst case, restore the step 1.1 backup.

---

## Sign-off

Deployer: ............................  Date: ..............

All sections above complete and passing: ☐

Handed to UAT tester: ☐    Name: ............................
