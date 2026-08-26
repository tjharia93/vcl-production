# Release Sign-off — VCL Production Lite (`vcl_production`)

> Copy this file per release, fill it in, and file it as
> `sign-offs/<release-tag>.md`.

**Release / branch:** ....................................................

**Site tested:** .........................................................

**Date:** ................................................................

---

## 1. OAT — deployer

Plan: [`oat-plan.md`](./oat-plan.md)

| Section | Passed |
|---|---|
| 1. Pre-deployment | ☐ |
| 2. Install | ☐ |
| 3. Post-install verification | ☐ |
| 4. Smoke tests | ☐ |
| 5. **Non-interference with `production_log`** | ☐ |
| 6. Independence from ERPNext | ☐ |
| 7. Idempotency | ☐ |
| 8. Automated tests | ☐ |
| 9. Permissions spot-check | ☐ |
| 10. Rollback rehearsed | ☐ |

Backup taken before install (file name): .................................

Issues found and how they were resolved:

..........................................................................

..........................................................................

**Deployer:** ............................  **Signed:** ..................

---

## 2. UAT — production team

Plan: [`uat-plan.md`](./uat-plan.md)

| Scenario | Passed |
|---|---|
| 1–2 Opening the screen | ☐ |
| 3 **Ten-second test** | ☐ |
| 4 Machine lists | ☐ |
| 5–6 Jobs remembered, autocomplete | ☐ |
| 7 New customer never blocked | ☐ |
| 8 Quantities | ☐ |
| 9–10 Status and reasons | ☐ |
| 11–12 Reference shift, Attention Required | ☐ |
| 13 Closing the day | ☐ |
| 14 Report | ☐ |
| 15 **WhatsApp report** | ☐ |
| 16–17 Day notes, history | ☐ |
| 18–19 Next day, corrections | ☐ |
| 20 Desk report | ☐ |
| 21 Mobile layout | ☐ |
| 22 Survives restart | ☐ |
| 23 Nothing else broke | ☐ |
| 24 Clean up | ☐ |

**Ten-second test (UAT 3.3):** .......... seconds  — target ~10, fail >20

**Phone(s) tested on:** ..................................................

**Would you use this instead of the WhatsApp group tomorrow morning?**

..........................................................................

If no — what stops you:

..........................................................................

**Supervisor / tester:** ............................  **Signed:** ........

---

## 3. Manager approval

Confirmed: no existing `production_log` or ERPNext process changed. ☐

Confirmed: any test production entered on the live site was deleted. ☐

Outstanding items accepted for this release:

..........................................................................

..........................................................................

**Approved for merge to `main`:** ☐

**Manager:** ............................  **Signed:** ...................
