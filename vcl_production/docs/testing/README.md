# UAT & OAT Testing — VCL Production Lite

These plans cover the **`vcl_production`** app only. The `production_log`
plans live in `../../../docs/testing/` and are unaffected by anything here —
the two apps share no DocTypes, fixtures, hooks or routes.

Same rules as the parent app:

1. **OAT first, UAT second.** If OAT fails, UAT does not begin.
2. Every PR that changes behaviour updates the **Deployment focus** section at
   the top of both plans. A code change without a docs change is incomplete.
3. `sign-off.md` is copied per release and filed under `sign-offs/<tag>.md`.

| File | Purpose | Who runs it |
|---|---|---|
| [`oat-plan.md`](./oat-plan.md) | Install / migrate / rollback / non-interference | Tanuj (or whoever deploys) |
| [`uat-plan.md`](./uat-plan.md) | Functional scenarios on a phone | Production supervisor + manager |
| [`sign-off.md`](./sign-off.md) | Blank sign-off sheet | Manager |

## One difference from the `production_log` plans

The parent UAT rule — *nothing is saved without a manager physically at the
desk* — exists because the Carton Job Card calculation pipeline is still being
stabilised and half-tested records would pollute real data.

That rule does **not** apply here, and applying it would invalidate the test.
The entire point of this app is that a supervisor enters production alone, in
ten seconds, without asking anyone. Instead:

- **UAT runs on a staging site, or on a live site using a future date.**
  Scenario 1 tells you which. Never enter test production against today's real
  date on the live site.
- Anything seeded by `seed_demo_jobs()` / `seed_demo_day()` is flagged
  `is_demo`, is excluded from the Script Report by default, and shows a
  **Demo** badge on screen.
- The manager's job in UAT is to **watch and countersign**, not to click Save.
