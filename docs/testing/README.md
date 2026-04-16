# UAT & OAT Testing

This folder holds the test plans that must be run every time we deploy a new
version of the `production_log` app to a Frappe Cloud site.

## Why this exists

We are still adding and changing job card behaviour almost every week. Before
any change reaches `main` (or the live site) it must be:

1. **Functionally verified** by a real user against real job cards — that is
   *User Acceptance Testing* (UAT).
2. **Operationally verified** by whoever runs the deploy — migrations apply
   cleanly, roles work, nothing regressed on the desk side — that is
   *Operational Acceptance Testing* (OAT).

Only after both sign-offs is the change merged to `main` and promoted to
production.

## The four files

| File | Purpose | Who runs it |
|---|---|---|
| [`uat-plan.md`](./uat-plan.md) | Step-by-step functional scenarios | Production team / factory user |
| [`oat-plan.md`](./oat-plan.md) | Deploy / migrate / rollback checks | Tanuj (or whoever deploys) |
| [`test-data.md`](./test-data.md) | Reference CSV, 10-job order, cherry-picked sample | Both |
| [`sign-off.md`](./sign-off.md) | Blank sign-off sheet — copy per release | Manager |

## Golden rule — nothing is saved without manager review

During UAT the tester **opens** the new form, **fills** it using the test data,
and then **calls the manager over to review the screen**. Only the manager
clicks **Save** or **Submit**. If the manager is not happy the form is
discarded via "Discard" / browser close — never saved, never submitted.

This is non-negotiable for the Carton Job Card right now because the 5-step
calculation pipeline is still being stabilised and we do not want half-tested
records polluting the database.

## How to update these docs on every deployment

Every pull request that changes doctype fields, workflows, calculation logic,
print formats, or permissions **must** also edit:

1. `uat-plan.md` → the **"Deployment focus"** section at the top — add a
   dated entry naming what changed and which scenarios specifically cover it.
2. `oat-plan.md` → the **"Deployment focus"** section — note any new patches,
   fixtures, hooks, or role changes that the deploy will apply.
3. `sign-off.md` is copied by the manager for each release and checked in
   once signed, filed under `docs/testing/sign-offs/<release-tag>.md`.

If you make a code change and **do not** touch these docs, the change is
incomplete. Reviewers should block the PR.

## Quick start for a tester

1. Open `test-data.md` and keep it open side by side.
2. Open `uat-plan.md`.
3. Work top to bottom, ticking the checkbox as each step passes. If a step
   fails, stop, screenshot it, flag the manager.
4. Do **not** click Save on any record until the manager is at your desk.
5. When all scenarios pass, copy `sign-off.md` and fill it in.

## Quick start for a deployer

1. Open `oat-plan.md`.
2. Run the pre-deployment checks (backup, patch review).
3. Run `bench migrate` on the target site.
4. Run the smoke tests.
5. Hand over to the UAT tester.
6. Countersign `sign-off.md` once UAT is done.
