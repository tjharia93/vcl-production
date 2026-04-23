# OAT Plan — VCL Production

**Operational Acceptance Testing** is run by whoever performs the deploy
(currently Tanuj). It is the check that the *deploy itself* is healthy —
migrations land cleanly, patches run, the desk still loads, roles still
work — independent of the functional scenarios in `uat-plan.md`.

Run OAT **first**, UAT **second**. If OAT fails, UAT cannot begin.

---

## Deployment focus

> **Update this section in every PR.** Note anything the deployer needs to
> watch for: new patches, new fixtures, new hooks, role changes, etc.

### 2026-04-26 — Workstation Type-level tagging + 6 product lines (Phase 7)

**Patches that will run on `bench migrate`:**

* `production_log.patches.patch_v5_2` — idempotent, safe to re-run.
  Does five things in order:
  1. Reloads the `Workstation Product Line Tag` child DocType JSON so
     its `product_line` Select picks up the expanded 7-value option
     list (`All / Computer Paper / ETR / Label / General Stationery
     and Exercise Book / Mono Boxes / Corrugation and Carton
     Department`).
  2. Installs a new Table custom field `custom_product_line_tags` on
     **Workstation Type** (pointing at the same child DocType), and
     widens the legacy `custom_product_line` Select options on both
     Workstation and Workstation Type to the same 7-value list.
  3. Renames every `ETR / Thermal` to `ETR` across Production Schedule
     Line, Production Entry, Workstation Product Line Tag child rows,
     and the legacy `custom_product_line` fields on WT + WS.
  4. Rolls the per-Workstation tags up to their Workstation Type (set
     union). So if a site had Miyakoshi 01 tagged `Computer Paper` +
     `ETR` (post-rename), the `Reel to Reel Printing` WT ends up
     tagged `Computer Paper` + `ETR`. Re-running after the field is
     gone is a no-op.
  5. Deletes all per-Workstation `custom_product_line_tags` rows and
     removes the Custom Field. After this patch runs, the planner's
     `get_workstation_columns` reads tags off Workstation Type only.

**DocType schema changes (picked up via `bench migrate`):**

* `Workstation Product Line Tag` child DocType — `product_line`
  Select `options` changed from `All\nComputer Paper\nETR / Thermal`
  to the full 7-value list.
* `Production Schedule Line` — `product_line` Select `options`
  updated to the 6-value planner set (blank-first for mandatory).
* `Production Entry` — same change.

**Workspace / hooks / fixtures:** no changes.

**Assets (requires `bench build`):** JS + CSS both modified; header
subtitle should show `build 2026-04-26-phase7-wt-tagging` after
deploy.

**Other watch-outs:**

* The header bar is now allowed to wrap (six dept tabs + view buttons
  + week nav + Print Daily is too wide for narrow desktops). Verify
  on the target viewport.
* `+ Add Job` is disabled on ETR / General Stationery / Mono Boxes /
  Corrugation tabs (no Job Card doctype mapped yet). The button
  surfaces the reason in its `title` attribute on hover.

---

### 2026-04-21 — Production Planner (cp_planning_board) first cut

**Patches that will run on `bench migrate`:**

* `production_log.patches.patch_v5_0` — idempotent, safe to re-run.
  Does three things:
  1. Extends the `custom_product_line` Select options on Workstation
     Type and Workstation to `All / Computer Paper / ETR / Thermal
     / Label / Carton` via `create_custom_fields(..., update=True)`.
     Existing data is preserved (same field name + Select type).
  2. Adds a Table field `custom_product_line_tags` on Workstation
     pointing at the new `Workstation Product Line Tag` child
     DocType.
  3. Seeds a `Design` Workstation Type (`custom_product_line=All`)
     and a `Design Desk` Workstation tagged `All`. Then loops every
     existing Workstation and inserts a matching `custom_product_line_tags`
     row from its legacy single-Select value (skips `Label` /
     `Carton` tags — those aren't valid child-table options in the
     Phase 1 planner scope).

* `production_log.patches.patch_v5_1` — idempotent, safe to re-run.
  Realigns the `custom_product_line_tags` child rows on the eight
  canonical workstations from FINAL §A2 (Design Desk, Miyakoshi 01/02,
  Hamada 01, Collator 1/2, Slitter 1/2). Needed because `patch_v5_0`
  preserved the legacy site default `custom_product_line = 'All'`
  on every workstation, so both dept tabs in the planner were
  showing every workstation. After this patch runs, only Design
  Desk carries `All`; each press/collator/slitter has its specific
  product-line tags. Any workstation **not** in the canonical table
  is left untouched — custom workstations Tanuj adds later stay
  under his control.

**New DocTypes:**

* `Workstation Product Line Tag` (child table, module Production Log)
* `Production Schedule Line` (standard DocType, autoname
  `PSL-YYYY-#####`, non-submittable, `title_field: job_card`)
* `Production Entry` (standard DocType, autoname `PE-YYYY-#####`,
  submittable, `title_field: job_card`, has `amended_from` field)

**New permissions (declared in the DocType JSONs, applied on sync):**

* Production Manager: full rights on PSL and PE, including Submit +
  Cancel + Amend on PE.
* Production User: create/read/write/submit on both (no cancel).
* System Manager: read-only + export/share (no write).

The Production Manager and Production User roles ship with ERPNext.
No custom role creation needed.

**Workspace change:**

* `VCL Production` workspace JSON picks up a new `Production Planning`
  header with three shortcuts: Production Planner (Page), Production
  Schedule Lines (DocType), Production Entries (DocType).

**Hooks / fixtures:**

* No changes to `hooks.py` fixtures list (the existing `Custom Field`
  filter already covers Workstation + Workstation Type, so any
  future `bench export-fixtures` will pick up the new Table field).
* No new print formats, no new scheduler events.

**Assets (requires `bench build`):**

* New stylesheet `production_log/public/css/cp_planning_board.css`
  served from `/assets/production_log/css/cp_planning_board.css`.
  The page loads it via `frappe.require` inside `on_page_load` —
  without `bench build` the page will render unstyled.

**Other watch-outs:**

* The page is scoped under `#cp-planner-root`; no global CSS
  pollution. The modal animation keyframe is `cpPlannerPopIn` (also
  scoped) so it can't collide with anything else on the desk.
* Print Daily opens in a new window via `Blob` + `URL.createObjectURL`
  + `window.open`. If popup blockers are aggressive, the user sees a
  fallback `<a download>` + toast. Verify the browser's popup
  settings on the test station before UAT.

### 2026-04-16 — Live SVG die-cut visualization in Carton Job Card

**Patches that will run on `bench migrate`:**

* No new patches. Existing patches are idempotent and will no-op on re-run.

**DocType changes:**

* `Job Card Carton` — new HTML field `html_board_visualization` added to
  the Board Plan section. `bench migrate` will add this column/field
  automatically.

**Client script changes:**

* `job_card_carton.js` — significant additions (~320 lines): SVG
  generation functions, board visualization rendering step (Step 6 in the
  pipeline), and two new pipeline triggers (`product_type`, `joint_type`).
* **`bench build --app production_log` is required** for this release
  because client-side JS has changed.

**Fixtures synced:**

* No new fixtures.

**Hook changes:**

* No hook changes.

### 2026-04-15 — Hard reset of production execution layer

**Patches that will run on `bench migrate`:**

* `production_log.patches.v1_0.setup_roles_and_permissions`
* `production_log.patches.v1_0.remove_job_card_production_entry`
  — purges stale `Job Card Production Entry` workspace shortcut and doctype
    references.
* `production_log.patches.v1_0.rename_workspace_to_vcl_production`
  — drops the old `Job Card Tracking` Workspace record so the new
    `VCL Production` workspace gets installed cleanly from JSON.
* `production_log.patches.v1_0.remove_production_execution_layer`
  — **new this release.** Drops `Department Daily Plan` and
    `Department Daily Plan Line` doctypes / tables, removes the
    Production Control columns from `Job Card Computer Paper` and
    `Job Card Label`, and clears any execution-layer workspace links,
    custom fields, reports, and print formats from previous attempts.
    Idempotent and safe to re-run.

**Fixtures synced:**

* Print Format `Carton Job Card` (placeholder — not yet a real Jinja template).

**Hook changes:**

* No new hooks. `hooks.py` has no scheduler entries, no doc events, and
  no override classes — it ships only the Carton Job Card print-format
  fixture and the install message.

**Removed doctypes:**

* `Department Daily Plan`
* `Department Daily Plan Line`

**Stripped fields (Job Card Computer Paper + Job Card Label):**

* `production_status`, `production_stage`, `planned_for_date`, `priority`,
  `qty_completed`, `qty_pending`, `last_production_update`, `completed_on`,
  `hold_reason`, `production_comments`, and the `Production Control`
  section break that contained them.

**Workspace changes:**

* The `Daily Planning` header and its `New Daily Plan` / `Daily Plan List`
  tiles have been removed from the VCL Production workspace.
* `/app/department-daily-plan` will 404 after migrate.

---

## Pre-deployment

Before running anything on the target site:

- [ ] The pull request has been reviewed and approved.
- [ ] `uat-plan.md` and `oat-plan.md` both have a dated "Deployment focus"
      entry describing the change. If they do not, block the deploy and
      send the PR back.
- [ ] Staging site is reachable and logged in as Administrator.
- [ ] **Database backup taken** on the target site:
      `bench --site <site> backup --with-files`
      and the backup file path is recorded below.
      Backup path: ________________________________
- [ ] **Frappe Cloud snapshot taken** (if deploying to Frappe Cloud — use
      the UI "Take Backup" button). Snapshot timestamp: ____________
- [ ] A rollback plan is written down: which commit to revert to, which
      backup file to restore, who authorises rollback.

---

## Deployment steps

- [ ] Fetch the target commit:
      `cd frappe-bench/apps/production_log && git fetch origin && git checkout <commit>`
- [ ] `bench build --app production_log` (**required for 2026-04-16 release**
      — `job_card_carton.js` has significant client-side changes).
- [ ] `bench --site <site> migrate`
- [ ] Migrate output is **clean** — no tracebacks, no "could not apply
      patch" lines, no "skipping …" that looks suspicious. Paste the tail
      of the migrate log into the sign-off sheet if anything looks off.
- [ ] `bench --site <site> clear-cache`
- [ ] `bench restart`

---

## Smoke tests (post-deploy, pre-UAT)

These are the minimum checks that must pass before handing over to the UAT
tester.

### 1. Desk loads

- [ ] Browse to `/app`. Login page → Administrator login works.
- [ ] No Frappe error toasts on the dashboard.
- [ ] The sidebar shows **VCL Production** and **not** the old
      "Job Card Tracking".

### 2. Workspace loads

- [ ] `/app/vcl-production` loads without a 404 or traceback.
- [ ] Both sections render (Customer Specifications / Job Card Tracking).
- [ ] There is **no** "Daily Planning" header.
- [ ] Every shortcut tile is visible — count them and compare against
      Scenario H in `uat-plan.md` (8 tiles expected for this release).
- [ ] `/app/job-card-tracking` no longer resolves to the old workspace.

### 3. Doctype list views

Open each of these list views and confirm no 500 / traceback:

- [ ] `/app/customer-product-specification`
- [ ] `/app/dies`
- [ ] `/app/dies-order`
- [ ] `/app/job-card-computer-paper`
- [ ] `/app/job-card-label`
- [ ] `/app/job-card-carton`
- [ ] `/app/department-daily-plan` should **404** (doctype removed).

### 4. Patch application

- [ ] `bench --site <site> execute "frappe.db.get_all('Patch Log', filters={'patch': 'production_log.patches.v1_0.rename_workspace_to_vcl_production'}, pluck='name')"`
      returns one row. If it returns zero, the patch did not run and the
      deploy is not complete.
- [ ] Same check for
      `production_log.patches.v1_0.remove_job_card_production_entry`.
- [ ] Same check for
      `production_log.patches.v1_0.remove_production_execution_layer`.
- [ ] `frappe.db.exists('Workspace', 'Job Card Tracking')` returns **None**.
- [ ] `frappe.db.exists('Workspace', 'VCL Production')` returns a string.
- [ ] `frappe.db.exists('DocType', 'Department Daily Plan')` returns **None**.
- [ ] `frappe.db.exists('DocType', 'Department Daily Plan Line')` returns **None**.

### 5. Roles and permissions

- [ ] Switch to a non-Administrator user (use the test user account the
      factory team has).
- [ ] That user can open `/app/vcl-production`.
- [ ] That user can open `New Carton Job Card` without a permission error.
- [ ] That user **cannot** edit a submitted Job Card Carton (submit
      workflow still enforced).

### 6. Carton visualization field exists

- [ ] Open any existing Carton Job Card (or create a new one).
- [ ] In the Board Plan section, confirm two HTML areas exist:
  - [ ] The static **formula reference box** (blue left-border, shows
        calculation formulas).
  - [ ] Below it, the **visualization area** (either an SVG diagram, a
        placeholder message, or empty depending on product type / dimensions).
- [ ] Open browser DevTools → Console. No JavaScript errors related to
      `html_board_visualization`, `vcl_render_board_visualization`, or
      `VCL_COLORS` should appear.

### 7. Fixture sync

- [ ] `frappe.db.exists('Print Format', 'Carton Job Card')` returns the
      string name. If it returns None the fixture did not sync — rerun
      `bench --site <site> migrate`.

### 8. Production Planner page + DocTypes load

- [ ] `bench --site <site> execute 'frappe.reload_doctype' --kwargs "{'doctype': 'Production Schedule Line'}"`
      completes without errors. Same for `Production Entry` and
      `Workstation Product Line Tag`.
- [ ] `frappe.db.exists('Workstation Type', 'Design')` returns `'Design'`.
      If it returns `None`, patch_v5_0 didn't run — rerun
      `bench --site <site> migrate`.
- [ ] `frappe.db.exists('Workstation', 'Design Desk')` returns
      `'Design Desk'`. Pull the row:
      `frappe.get_doc('Workstation', 'Design Desk').custom_product_line_tags`
      returns a list with at least one entry whose `product_line`
      is `'All'`.
- [ ] `frappe.db.get_value('Custom Field', {'dt': 'Workstation', 'fieldname': 'custom_product_line_tags'}, 'options')`
      returns `'Workstation Product Line Tag'`. If blank, the
      Table field wasn't installed.
- [ ] `frappe.db.get_value('Custom Field', {'dt': 'Workstation Type', 'fieldname': 'custom_product_line'}, 'options')`
      contains `'ETR / Thermal'` (and still contains `Label` /
      `Carton`). Same check on Workstation's `custom_product_line`.
- [ ] After `patch_v5_1` runs (pre-v5_2 only — v5_2 deletes these
      rows): for each of the eight canonical workstations,
      `frappe.get_doc('Workstation', <name>).custom_product_line_tags`
      yielded the FINAL §A2 tag set. On a post-v5_2 site this field
      is gone; see the v5_2 smoke checks below.
- [ ] After `patch_v5_2` runs:
      `frappe.db.exists('Custom Field', {'dt': 'Workstation', 'fieldname': 'custom_product_line_tags'})`
      returns `None` (per-WS Table field removed).
- [ ] `frappe.db.get_value('Custom Field', {'dt': 'Workstation Type', 'fieldname': 'custom_product_line_tags'}, 'options')`
      returns `'Workstation Product Line Tag'` (new WT Table field
      installed).
- [ ] For each Workstation Type that had workstations tagged pre-v5_2,
      `frappe.get_doc('Workstation Type', <wt_name>).custom_product_line_tags`
      returns the UNION of its child workstations' old tags, with
      `ETR / Thermal` renamed to `ETR`.
- [ ] `frappe.db.count('Production Schedule Line', {'product_line': 'ETR / Thermal'})`
      returns `0`. Same check on `Production Entry`. Rows with the
      legacy value should all show `ETR` now.
- [ ] `frappe.db.get_value('Custom Field', {'dt': 'Workstation Type', 'fieldname': 'custom_product_line'}, 'options')`
      contains `General Stationery and Exercise Book`, `Mono Boxes`,
      and `Corrugation and Carton Department`.
- [ ] Open `/app/cp_planning_board` in a browser. The page loads with
      the scoped blue header, dept tabs, view buttons, and Print
      Daily button. Browser console shows no JS errors.
- [ ] Open DevTools → Network. Switching dept tabs fires four
      parallel requests to
      `production_log.production_log.page.cp_planning_board.cp_planning_board.get_workstation_columns`,
      `…get_schedule_entries`, `…get_machine_conflicts`, and
      `…get_job_cards`, each returning HTTP 200 with JSON.
- [ ] Left panel populates with Job Card tiles (no more
      "Job card list arrives in Phase 2." placeholder). Typing in
      the search box filters the list client-side; **+ Add Job** is
      enabled and opens a fresh Job Card form in a new tab.
- [ ] Dept tab bar shows **six** buttons in order: `Computer Paper`,
      `ETR`, `Label`, `General Stationery and Exercise Book`,
      `Mono Boxes`, `Corrugation and Carton Department`. On the
      target viewport the bar wraps cleanly onto a second line if it
      can't fit in one row.
- [ ] On the Computer Paper tab the grid shows only those
      workstations whose **Workstation Type** (not individual
      Workstation) is tagged `Computer Paper` or `All`. Workstations
      of an untagged WT don't appear.
- [ ] On the ETR / Label / General Stationery / Mono Boxes /
      Corrugation tabs the grid shows only WTs tagged for that line
      (empty until an admin tags them). **+ Add Job** is disabled on
      every tab except Computer Paper and Label; hovering the button
      surfaces the reason via its `title` attribute.
- [ ] The stylesheet request to
      `/assets/production_log/css/cp_planning_board.css` returns
      HTTP 200. If 404, rerun `bench build` and hard-refresh.
- [ ] Open `/app/production-schedule-line` list view — loads without
      500. Same for `/app/production-entry`.
- [ ] Open the VCL Production workspace — the new **Production
      Planning** header appears with three shortcuts (Production
      Planner, Production Schedule Lines, Production Entries).

---

## Rollback procedure

If any smoke test fails and the issue is not a trivial fix:

1. **Announce** in the team channel: "Rolling back production_log on
   <site> to <previous commit>".
2. Restore the DB backup taken in Pre-deployment:
   `bench --site <site> restore <backup-file>`
3. Check out the previous commit:
   `cd apps/production_log && git checkout <previous-commit>`
4. `bench --site <site> migrate`  (no-op if DB was restored, but run it
   anyway to keep Patch Log aligned).
5. `bench restart`
6. Smoke-test Scenario 1 through 3 above on the restored build.
7. Log the rollback on the sign-off sheet with the failing smoke test as
   the root cause.

---

## Handover to UAT

Once all smoke tests are green:

- [ ] Post in the team channel: "OAT green on <site> for <commit>. UAT
      can begin." tagging the UAT tester and the manager.
- [ ] Copy `sign-off.md` to `docs/testing/sign-offs/<release-tag>.md` and
      fill in the OAT half.
- [ ] Leave the browser tabs open for the tester.

---

## Sign-off

Complete the OAT half of `sign-off.md` with:

* Release tag / commit hash
* Deployer name
* Date and time deploy started / finished
* Backup file path
* Any patches that required manual intervention
* Any smoke tests that failed and how they were resolved
* Rollback: Y/N; if Y, root cause
