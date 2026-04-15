# Release Sign-off Sheet

**Copy this file to `docs/testing/sign-offs/<release-tag>.md` at the start
of every release cycle.** Fill it in as OAT and UAT progress. Commit the
completed sheet to the repo so we have an audit trail.

---

## Release

| Field | Value |
|---|---|
| Release tag | |
| Commit hash | |
| Target site | |
| Frappe Cloud snapshot ID | |
| DB backup file path | |
| Date started | |
| Date finished | |

## Manager pre-brief

| Field | Value |
|---|---|
| UAT cherry-picked rows (should be 5) | rows 1, 2, 3, 4, __ |
| Conversion test row (3-ply → 5-ply) | row __ |
| Rows 6–10 regression required? | Yes / No |
| If No — why not? | |

---

## OAT — Operational Acceptance Testing

Deployer: ________________

### Pre-deployment

- [ ] PR reviewed and approved
- [ ] `uat-plan.md` deployment-focus entry present and dated
- [ ] `oat-plan.md` deployment-focus entry present and dated
- [ ] DB backup taken
- [ ] Frappe Cloud snapshot taken
- [ ] Rollback plan written

### Deploy

- [ ] `git checkout <commit>` clean
- [ ] `bench build` clean (or skipped because no assets changed)
- [ ] `bench migrate` clean — paste tail of output if anything looked off:

```
(paste any suspicious lines here, or "clean" if fine)
```

- [ ] `bench clear-cache` + `bench restart` run

### Smoke tests

- [ ] 1. Desk loads
- [ ] 2. Workspace loads at `/app/vcl-production` with correct tiles
- [ ] 3. All list views load with no 500s
- [ ] 4. Patch Log confirms all new patches ran
- [ ] 5. Non-admin user can access and create (but not edit submitted records)
- [ ] 6. Fixture sync — print formats present

### OAT outcome

- [ ] **GREEN** — handed over to UAT tester.
- [ ] **RED** — rolled back.

If rolled back, root cause: _______________________________________________

Signed (Deployer): __________________________  Date: _________________

---

## UAT — User Acceptance Testing

Tester: ________________  Manager: ________________

### Cherry-picked 5

- [ ] Scenario A — Customer Product Spec for all 5 cherry-picked rows
- [ ] Scenario B — Computer Paper smoke test
- [ ] Scenario C — Label smoke test
- [ ] Scenario D — Carton auto-populate (5 rows)
- [ ] Scenario E — SFK layer visibility
- [ ] Scenario F — 3-ply calculation path
- [ ] Scenario G — 3-ply → 5-ply conversion (row __)
- [ ] Scenario H — Workspace & sidebar layout
- [ ] Scenario I — Department Daily Plan with Carton

### Full regression (rows 6 – 10)

- [ ] Row 6
- [ ] Row 7
- [ ] Row 8
- [ ] Row 9
- [ ] Row 10

### Anomalies observed

| # | Scenario / row | Description | Screenshot link | Severity (block / minor) | Status |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

### UAT outcome

- [ ] **GREEN** — safe to merge to `main` and promote.
- [ ] **GREEN-WITH-NOTES** — minor anomalies logged, safe to merge; issues
      filed as follow-ups.
- [ ] **RED** — block the release. Open a bug ticket per anomaly and
      revert the staging deploy.

Signed (Tester): __________________________  Date: _________________

Signed (Manager): _________________________  Date: _________________
