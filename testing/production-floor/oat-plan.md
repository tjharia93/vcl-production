# OAT Plan — Production Floor (`production_log`, module `Production Floor`)

**Operational Acceptance Testing.** Run by whoever performs the deploy. This
checks the *deploy itself* is healthy — the migrate completes, the patch runs,
the desk still loads, and **the rest of `production_log` is untouched** —
independent of the functional scenarios in [`uat-plan.md`](./uat-plan.md).

This is **not a separate app.** Production Floor ships as a module inside
`production_log`, which is already installed on VCL's site. There is nothing
to install: it arrives on the next deploy of an app that is already there.

Run OAT **first**, UAT **second**. If OAT fails, UAT cannot begin.

---

## Deployment focus

> **Update this section in every PR.** Note anything the deployer must watch
> for: new patches, fixtures, hooks, role changes, route changes.

### 2026-08-28 — The To Plan strip, and a Monobox department

**Behaviour change plus one new DocField, no patch.**

- `VCL Daily Production Item` gains `job_card_instructions` (Small Text,
  read-only). New DocField, applies at model sync.
- **Monobox** is added to `DEFAULT_DEPARTMENTS` and to the three `department`
  Select lists. The live options are driven by Property Setters that
  `install.after_migrate → apply_select_options()` rewrites on every migrate,
  so the JSON change and the Property Setter agree after one migrate.
- `after_migrate` now also calls `seed_machines()`, which adds the six Monobox
  stages. It only ever adds what is missing. **Retire a machine by unticking
  `active`, not by deleting it**, or the next migrate brings it back.
- `list_open_job_cards()` is renamed `list_to_plan()` and now covers Computer
  Paper, Carton and Monobox, filtered to `job_status = "Open"`.

**The one thing to watch:** planning a job from the strip **writes** to a Job
Card Tracking document — `job_status: Open → Planned`. It runs after the
production row is saved and swallows its own failures, so the worst case is a
card that stays on the strip, never a row that is lost.

**Also worth knowing:** `special_instructions` / `order_comments` are empty on
every currently open card, so the "From the Job Card" box will render blank
until someone starts filling them in. The plumbing is there; the data is not.

**Test counts move:** bench-free 41 → **60**, bench 13 → **15**.

### 2026-08-27 — Add Job can pick an open Computer Paper job card

**Behaviour change, no patch.** Two read-only `Data` fields are added
(`production_job_card` on `VCL Daily Production Item` and `VCL Production
Job`) and `source` gains a `Job Card` option. New DocFields and a changed
Select option list both apply at model sync, so there is nothing to run.

**The one thing to watch:** the floor screen now reads a **Job Card Tracking**
DocType. `list_open_job_cards()` (since renamed `list_to_plan()`) queries
`Job Card Computer Paper` read-only,
returns `[]` when the DocType is absent, and swallows `PermissionError` so a
supervisor without read on Job Card Tracking still gets a working dialog —
just without the shortcut. Section 11 checks this.

**Test counts move:** bench-free 27 → **41**, bench 8 → **13**.

### 2026-08-26 — Production Floor arrives inside `production_log`

**This is a new module in an installed app, not a new app.** It first shipped
as a `vcl_production/` subdirectory of this repo and appeared to deploy with
commit `7ff5719` — but Frappe Cloud builds the app at the repo *root*, which
is `production_log`, so those files reached the bench inert and no DocType was
ever created. It is now the `Production Floor` module and deploys normally.

**What the deployer does:** deploy `production_log` as usual. No new app, no
new repo, no dashboard change.

**Patches that will run on `bench migrate`:**

* `production_log.patches.v10_0.seed_production_floor` — idempotent, safe to
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

## 2. Deploy

- [ ] **2.1** Deploy `production_log` the way you always do — on Frappe Cloud
      the bench picks up `main` and you release the candidate. There is no new
      app to add and no `install-app` step.
- [ ] **2.2** Confirm the bench has the module:
      `ls ~/frappe-bench/apps/production_log/production_log/production_floor/`
      — must contain `doctype/`, `page/`, `report/` and `workspace/`.
- [ ] **2.3** `bench --site <site> migrate` — **completes with no traceback.**
      This is the step that now matters most. The migrate that creates these
      DocTypes is the same migrate the live app runs, so a failure here is a
      failed deploy of PPC and Job Cards too, not just of the floor screen.
- [ ] **2.4** Confirm the patch ran:
      `bench --site <site> mariadb -e "SELECT patch FROM \`tabPatch Log\` WHERE patch LIKE '%seed_production_floor%'"`
      — expect one row.
- [ ] **2.5** `bench build --app production_log` — completes (optional but do it).
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

**This is the check that matters most, and folding the module in raised its
stakes: this code now deploys inside the live app rather than beside it.**

- [ ] **5.1** `bench --site <site> list-apps` lists exactly what it listed at
      step 1.2 — **no new app.** `production_log`'s version may have moved.
- [ ] **5.2** **`/app/vcl-production` still opens the "VCL Production"
      workspace**, with its Customer Specifications / Job Card Tracking /
      Production Planning shortcuts — *not* the floor screen. Compare against
      the screenshot from step 1.3. `/app/production-floor` is a second,
      separate workspace.
- [ ] **5.3** `/app/ppc` loads unchanged. Compare against step 1.3.
- [ ] **5.4** Open one existing Customer Product Specification and one Job
      Card Computer Paper. Both load and their fields are unchanged.
- [ ] **5.5** Row count from step 1.4 is identical.
- [ ] **5.6** No Property Setter, Custom Field or Client Script was created
      against a DocType outside this module:
      `SELECT doc_type FROM \`tabProperty Setter\` WHERE modified > '<deploy timestamp>'`
      — every row must start with `VCL `.
- [ ] **5.7** The `production_log` scheduler jobs (Gemba EOD 17:00 EAT,
      artwork chase Friday) are still registered:
      `bench --site <site> doctor` or check **Scheduled Job Type**.
- [ ] **5.8** **The desk-wide stylesheet did not restyle anything.** Production
      Floor's CSS is now loaded on every desk page via `app_include_css`. Open
      a Job Card and the PPC board and confirm they look exactly as they did in
      step 1.3. Every selector in the file is namespaced under `.vcl-`, so a
      visible change here means that namespacing was broken:
      `grep -oE '^[.#][a-zA-Z0-9_-]+' ~/frappe-bench/apps/production_log/production_log/public/css/production_floor.css | sort -u`
      — every line must begin `.vcl-`.
- [ ] **5.9** The module's four existing modules are intact:
      `bench --site <site> mariadb -e "SELECT name FROM \`tabModule Def\` WHERE app_name='production_log'"`
      — `Production Log`, `Job Card Tracking`, `PPC`, plus `Production Floor`.

## 6. Independence from ERPNext — what it does and does not mean

Production Floor no longer claims to install without ERPNext; it ships inside
an app that requires it. What must still hold is the **data-model**
independence, which is the part that keeps the floor unblocked.

- [ ] **6.1** No Link field in this module targets an ERPNext DocType. Every
      `erpnext_*` field is a read-only `Data`:
      `grep -h '"fieldtype": "Link"' -A2 -B4 ~/frappe-bench/apps/production_log/production_log/production_floor/doctype/*/*.json | grep '"options"'`
      — no `Item`, `Work Order`, `Sales Order`, `Job Card`, `Workstation` or
      `Customer` among them.
- [ ] **6.2** No module code imports or reads ERPNext:
      `grep -rn "erpnext" ~/frappe-bench/apps/production_log/production_log/production_floor --include=*.py`
      — reserved field names and comments only, no `import`, no
      `frappe.get_doc("Item"...)`.
- [ ] **6.3** **Add a job for a customer that does not exist in ERPNext.** This
      is the check that replaces the old scratch-site install, and it tests the
      property that actually matters: the screen accepts it, saves it, and puts
      it on the board. UAT Scenario 7 covers this in full.

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
      `bench --site <site> run-tests --module production_log.production_floor.doctype.vcl_daily_production.test_vcl_daily_production`
      Expected: **13** tests in `TestVCLDailyProduction`, all passing.
      > Scoped to the module on purpose. `run-tests --app production_log` now
      > runs the whole app's suite, which is a longer and noisier job than
      > this deploy needs.
      > These create and delete a production day dated **400 days in the
      > future**, precisely so they cannot collide with real data. If you see
      > a `VCL-PROD-` document for a date about 13 months out afterwards, the
      > teardown failed — delete it.
- [ ] **8.2** Bench-free tests pass:
      `cd ~/frappe-bench/apps/production_log && python3 -m unittest discover -s production_log/production_floor/tests -t .`
      Expected: **41** tests, all passing. These import `reporting.py` directly and
      need neither a bench nor a site.

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

Rehearse this before you need it. **Folding the module in changed rollback
more than any other section — read it before you deploy, not after.**

There is no app to uninstall. Rolling back means rolling back `production_log`,
and that takes PPC, Job Cards, Dies and Customer Product Specifications with
it. A floor-screen problem is no longer a reason to roll back on its own.

- [ ] **10.1** Know the previous good deploy candidate before you release the
      new one. On Frappe Cloud: Bench → Deploys, note the current candidate.
      Screenshot it.
- [ ] **10.2** **Prefer rolling forward.** If only the floor screen is broken,
      the contained fix is to hide it, not to revert the app: remove the
      `Production Floor` workspace from the sidebar and tell the floor to stop
      using it. Everything else keeps working and the data stays.
- [ ] **10.3** If you must revert the deploy, know what it does **not** undo.
      Reverting removes the code; it does not drop the DocTypes, the tables,
      the roles or the Property Setters the migrate created. They stay behind,
      orphaned, until deleted by hand:
      the five `VCL *` DocTypes, the `Production Floor` workspace, the
      `vcl-production-lite` Page, the `VCL Daily Production Report`, and the
      two `VCL Production *` roles.
- [ ] **10.4** Production data is **not** deleted by any of the above, and that
      is deliberate. If you do delete the DocTypes by hand, their tables go
      too. **Back up first if the floor has been using it.**
- [ ] **10.5** Worst case, restore the step 1.1 backup — which also reverts
      every other `production_log` change since that backup.

## 11. The job card shortcut

New with the 2026-08-27 release. All of this is about the one place this
module now reaches outside itself.

- [ ] **11.1** Open `/app/vcl-production-lite`, tap **+ Add Job** with
      Department `Computer`. An **Open Job Cards** row appears under Recent
      Jobs, listing job cards soonest-due first.
- [ ] **11.2** Every card listed is genuinely open. Cross-check one against
      the desk: its `job_status` is `Open`, `Planned`, `In Production` or
      `Packing Pending`, and its docstatus is not 2.
- [ ] **11.3** Switch Department to `Offset`. **The row disappears.** Same for
      `Carton` and `Labels`.
- [ ] **11.4** **It fails soft.** As a user with the `VCL Production User`
      role but *no* read permission on Job Card Tracking, open the dialog:
      the Open Job Cards row is empty or absent, and **adding a job typed by
      hand still works.** This is the check that matters — a Job Card Tracking
      problem must never stop production being recorded.
- [ ] **11.5** The stamp lands: pick a card, add the job, then open that row
      on the desk. `Job Card` holds the job card name and `Source` reads
      `Job Card`.
- [ ] **11.6** A job typed by hand still reads `Source = Manual` with `Job
      Card` blank.
- [ ] **11.7** `production_job_card` is a read-only **Data** field on both
      DocTypes, not a Link:
      `bench --site <site> mariadb -e "SELECT fieldtype, options FROM tabDocField WHERE fieldname='production_job_card'"`
      — both rows `Data`, options empty. A Link here would let a cancelled job
      card make an existing production row unsaveable.

---

## Sign-off

Deployer: ............................  Date: ..............

All sections above complete and passing: ☐

Handed to UAT tester: ☐    Name: ............................
