# UAT & OAT Testing — Production Floor

These plans cover the **`Production Floor` module** of `production_log` — the
phone screen at `/app/vcl-production-lite` and the five `VCL *` DocTypes
behind it. The plans for the rest of the app are in [`../`](../)
(`VCL-OAT-Comprehensive.md`, `VCL-UAT-Comprehensive.md`, the PPC and ETR
plans) and are unaffected by anything here: this module adds no DocType, no
fixture, no route and no `doc_events` hook that the rest of the app shares.

One thing it *does* share, since it stopped being a separate app: the migrate.
OAT §2.3 and §5 are the sections that matter because of it.

Same rules as the rest of the app:

1. **OAT first, UAT second.** If OAT fails, UAT does not begin.
2. Every PR that changes behaviour updates the **Deployment focus** section at
   the top of both plans. A code change without a docs change is incomplete.
3. `sign-off.md` is copied per release and filed under `sign-offs/<tag>.md`.

| File | Purpose | Who runs it |
|---|---|---|
| [`oat-plan.md`](./oat-plan.md) | Deploy / migrate / rollback / non-interference | Tanuj (or whoever deploys) |
| [`uat-plan.md`](./uat-plan.md) | Functional scenarios on a phone | Production supervisor + manager |
| [`sign-off.md`](./sign-off.md) | Blank sign-off sheet | Manager |

## One difference from the other `production_log` plans

The rule elsewhere in this app — *nothing is saved without a manager
physically at the desk* — exists because the Carton Job Card calculation
pipeline is still being stabilised and half-tested records would pollute real
data.

That rule does **not** apply here, and applying it would invalidate the test.
The entire point of this module is that a supervisor enters production alone,
in ten seconds, without asking anyone. Instead:

- **UAT runs on a staging site, or on a live site using a future date.**
  Scenario 1 tells you which. Never enter test production against today's real
  date on the live site.
- Anything seeded by `seed_demo_jobs()` / `seed_demo_day()` is flagged
  `is_demo`, is excluded from the Script Report by default, and shows a
  **Demo** badge on screen.
- The manager's job in UAT is to **watch and countersign**, not to click Save.
