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

### 2026-04-15 — Job Card Carton + VCL Production workspace rename

**Patches that will run on `bench migrate`:**

* `production_log.patches.v1_0.setup_roles_and_permissions`
* `production_log.patches.v1_0.remove_job_card_production_entry`
  — purges stale `Job Card Production Entry` workspace shortcut and doctype
    references.
* `production_log.patches.v1_0.rename_workspace_to_vcl_production`
  — drops the old `Job Card Tracking` Workspace record so the new
    `VCL Production` workspace gets installed cleanly from JSON.

**Fixtures synced:**

* Print Format `Carton Job Card` (placeholder — not yet a real Jinja template).

**Hook changes:**

* `hooks.py` now declares a `fixtures` list for the Carton Job Card print
  format. On first deploy this will emit one `Print Format` record.

**New doctypes:**

* `Job Card Carton`
* `Carton Job Type UPS` (child table)

**Expanded doctypes:**

* `Customer Product Specification` — 23 new carton fields.
* `Department Daily Plan` — now supports `Carton` as a Job Card Type.
* `Department Daily Plan Line` — gained a carton-facing link.

**Workspace URL change:**

* `/app/job-card-tracking` → `/app/vcl-production`. Any bookmarks / shortcut
  buttons / external links pointing to the old URL will 404. Notify the
  factory team before deploy.

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
- [ ] `bench build --app production_log` (if any JS/CSS changed — confirm
      from the PR diff).
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
- [ ] All three sections render (Customer Specifications / Job Card
      Tracking / Daily Planning).
- [ ] Every shortcut tile is visible — count them and compare against
      Scenario H in `uat-plan.md` (8 tiles expected for this release).
- [ ] `/app/job-card-tracking` no longer resolves to the old workspace.

### 3. Doctype list views

Open each of these list views and confirm no 500 / traceback:

- [ ] `/app/customer-product-specification`
- [ ] `/app/dies`
- [ ] `/app/job-card-computer-paper`
- [ ] `/app/job-card-label`
- [ ] `/app/job-card-carton`  ← **new this release**
- [ ] `/app/department-daily-plan`

### 4. Patch application

- [ ] `bench --site <site> execute "frappe.db.get_all('Patch Log', filters={'patch': 'production_log.patches.v1_0.rename_workspace_to_vcl_production'}, pluck='name')"`
      returns one row. If it returns zero, the patch did not run and the
      deploy is not complete.
- [ ] Same check for
      `production_log.patches.v1_0.remove_job_card_production_entry`.
- [ ] `frappe.db.exists('Workspace', 'Job Card Tracking')` returns **None**.
- [ ] `frappe.db.exists('Workspace', 'VCL Production')` returns a string.

### 5. Roles and permissions

- [ ] Switch to a non-Administrator user (use the test user account the
      factory team has).
- [ ] That user can open `/app/vcl-production`.
- [ ] That user can open `New Carton Job Card` without a permission error.
- [ ] That user **cannot** edit a submitted Job Card Carton (submit
      workflow still enforced).

### 6. Fixture sync

- [ ] `frappe.db.exists('Print Format', 'Carton Job Card')` returns the
      string name. If it returns None the fixture did not sync — rerun
      `bench --site <site> migrate`.

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
