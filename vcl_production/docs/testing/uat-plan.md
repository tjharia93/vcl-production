# UAT Plan — VCL Production Lite (`vcl_production`)

**User Acceptance Testing.** Run by a production supervisor **on their own
phone**, with a manager watching. This is the last check before merge to
`main`.

**Rules for this document:**

1. Work top to bottom. Tick each checkbox as it passes.
2. **Run this on a phone first.** A desktop pass afterwards is fine, but if
   it only ever gets tested on a laptop the test has not been run.
3. If anything fails: stop, screenshot, flag the manager.
4. **Do not enter test production against today's real date on the live
   site.** Scenario 1 sets up a safe test date.
5. Time yourself where the plan asks you to. Speed is a requirement here, not
   a nice-to-have.

---

## Deployment focus

> **Update this section in every PR that changes behaviour.** Add a dated
> entry at the top; older entries stay so the trail is visible.

### 2026-08-26 — First release of `vcl_production`

Everything is new. Run every scenario.

The single most important outcome is **Scenario 3**: a supervisor records
`M1 → Chandaria → Yellow Copy → 3 reels` in about ten seconds. If that takes
thirty seconds the app has failed its purpose regardless of what else passes.

---

## Before you start

- [ ] **0.1** OAT is complete and signed. UAT does not begin otherwise.
- [ ] **0.2** You have a login with the **VCL Production User** role, and the
      manager has one with **VCL Production Manager**.
- [ ] **0.3** You are on a phone, in a browser, logged in.
- [ ] **0.4** Bookmark / add to home screen: `/app/vcl-production-lite`.
- [ ] **0.5** Agree the **test date** with the manager and write it here:

      TEST DATE: ....................

      On a staging site, use today. On the live site, use a date at least a
      week in the future so it cannot be mistaken for real production.

---

## Scenario 1 — Opening the screen

- [ ] **1.1** Open `/app/vcl-production-lite`. It loads in under 3 seconds on
      mobile data.
- [ ] **1.2** The date bar shows today. Use `‹` / `›` or the date box to move
      to your **test date** from 0.5.
- [ ] **1.3** You did **not** have to create anything. Opening the date is what
      creates the day.
- [ ] **1.4** Five summary cards show: Planned, Running, Completed, Not
      Started, Carried Forward — all 0.
- [ ] **1.5** The empty state reads "Nothing entered yet".
- [ ] **1.6** A large **+ Add Job** button is obvious without scrolling.

## Scenario 2 — Nothing is remembered yet

- [ ] **2.1** Tap **+ Add Job**. Under Recent Jobs it says there are no
      remembered jobs yet.
- [ ] **2.2** Close the dialog. This is the baseline for Scenario 5.

## Scenario 3 — The ten-second test ⏱

**This is the scenario the whole app exists for.**

- [ ] **3.1** Have the manager start a stopwatch as you tap **+ Add Job**.
- [ ] **3.2** Enter: Department `Computer`, Machine `M1`, Customer
      `Chandaria`, Job `Yellow Copy`, Planned `3`, Unit `reels`. Tap **Add**.
- [ ] **3.3** Stop the clock. **Record the time: .......... seconds**
- [ ] **3.4** Target is ~10 seconds. Over 20 seconds is a **fail** — note
      exactly which field slowed you down.
- [ ] **3.5** The card appears immediately under a **COMPUTER** heading,
      showing `M1`, `Chandaria`, `Yellow Copy`, `0 / 3 reels`, status
      **Planned**.
- [ ] **3.6** You never had to open a Job Card, a Work Order, or any master.

## Scenario 4 — Machine list is filtered and complete

- [ ] **4.1** Tap **+ Add Job**. With Department `Computer`, the Machine list
      offers exactly: M1, M2, M3, M4, Collator.
- [ ] **4.2** Switch to `Offset` → Solna, Miller, Miyakoshi.
- [ ] **4.3** Switch to `Carton` → Printing, Die Cutting, Slotting,
      Stitching, Bundling, Gluing.
- [ ] **4.4** Switch to `Labels` → Propheteer.
- [ ] **4.5** Close the dialog without adding.

## Scenario 5 — The job was remembered by itself

- [ ] **5.1** Tap **+ Add Job**. Under **Recent Jobs**, a chip now reads
      **Chandaria — Yellow Copy**.
- [ ] **5.2** Nobody visited a master screen to make that happen.
- [ ] **5.3** Tap the chip. Customer, Job and Unit fill in automatically.
- [ ] **5.4** Change Machine to `Collator`, set Planned `12`, Unit `cartons`,
      tap **Add**.
- [ ] **5.5** The new card appears. This took noticeably fewer taps than
      Scenario 3.

## Scenario 6 — Autocomplete on a partial name

- [ ] **6.1** Tap **+ Add Job**, then tap **Search Remembered Jobs** and type
      `Cha`.
- [ ] **6.2** The suggestion list offers **Chandaria — Yellow Copy**.
- [ ] **6.3** Clear it and type `Yellow` instead. The same job is suggested —
      searching works on the job as well as the customer.
- [ ] **6.4** Close the dialog without adding.

## Scenario 7 — A brand new customer is never blocked

- [ ] **7.1** Tap **+ Add Job**. **Ignore** the search box entirely.
- [ ] **7.2** Department `Computer`, Machine `M3`, and **type** Customer
      `KCB` and Job `Computer Paper` — neither has ever been entered.
- [ ] **7.3** Planned `3`, Unit `reels`. Tap **Add**. It saves with no
      complaint about a missing master.
- [ ] **7.4** Add another with a customer that will never exist in ERPNext,
      e.g. Machine `M4`, Customer `NHIF`, Job `3-Part Payslip`, Planned `2`,
      Unit `reels`.
      > The original WhatsApp message said only *"M4 running 3-Part Payslip"* —
      > no customer at all. Note whether the supervisor knows who it is for.
      > This is the gap structured entry is meant to close.
- [ ] **7.5** Both appear on the board.

## Scenario 8 — Quantities

- [ ] **8.1** Tap the `M3 / KCB` card. Set Actual to `0.5`. Save. The card
      reads `0.5 / 3 reels`. **Decimals work.**
- [ ] **8.2** Tap the `M1 / Chandaria` card. Set Actual `1`, Save. Card reads
      `1 / 3 reels`.
- [ ] **8.3** Tap the `Collator` card. Set Actual `9`, Save. Reads
      `9 / 12 cartons`.
- [ ] **8.4** **Arithmetic is refused.** Open any card and try to type `41+6`
      into Actual.
      > On most phones the numeric keypad will not let you type `+` at all —
      > **that is a pass**, note it and move on. If your keyboard does allow
      > it, tap Save: you get a message telling you to add it up and enter the
      > total, and the value is **not** saved as 47 and **not** saved as 41.
- [ ] **8.5** On the phone, the quantity field brings up the **numeric
      keypad**, not the full alphabet keyboard.
- [ ] **8.6** A negative number (`-5`) is refused.
- [ ] **8.7** Clearing Actual back to blank is allowed — blank means "nobody
      has said yet", not zero.

## Scenario 9 — Status buttons

- [ ] **9.1** Tap the `M1` card. Five large status buttons are visible:
      NOT STARTED / RUNNING / PAUSED / COMPLETED / CARRY FORWARD.
- [ ] **9.2** They are big enough to hit with a thumb without zooming.
- [ ] **9.3** Tap **RUNNING**, then Save. The card badge turns green and reads
      Running.
- [ ] **9.4** Do the same for `M3`, `M4` and `Collator` — all Running.
- [ ] **9.5** Reopen the `M1` card and confirm **Started At** has been filled
      in automatically. You never typed a time.

## Scenario 10 — Reasons are enforced where they matter

- [ ] **10.1** Tap the `M4 / NHIF` card, tap **PAUSED**, leave Reason blank,
      tap Save. **It is refused** with "A job marked Paused needs a reason."
- [ ] **10.2** Type a reason (`Waiting for artwork`) and Save. It saves.
- [ ] **10.3** Tap it again, tap **RUNNING**, Save. Allowed — a reason is not
      demanded for a normal status.
- [ ] **10.4** Confirm with the manager: **at no point during the shift were
      you blocked from recording what was actually happening.**

## Scenario 11 — The reference shift

Enter the rest of the shift so the day matches the real example. Add:

| Dept | Machine | Customer | Job | Plan | Actual | Unit | Status |
|---|---|---|---|---|---|---|---|
| Offset | Solna | Prince | 3 Quire | 2000 | 2000 | pcs | Completed |
| Offset | Miller | Prince | 1 Quire | 1500 | 1500 | pcs | Completed |
| Carton | Stitching | E.W.A.L | Carton | 1000 | 1031 | pcs | Completed |
| Carton | Bundling | E.W.A.L | Carton | 1000 | 47 | pcs | Carried Forward |

- [ ] **11.1** All four entered.
- [ ] **11.2** On Bundling, **CARRY FORWARD** with a blank reason is refused.
      Enter `Board ran out at 3pm` and save.
- [ ] **11.3** Then set `M3 / KCB` to **CARRY FORWARD** with reason
      `Reel change took the afternoon`.
- [ ] **11.4** Departments appear in the order **COMPUTER, OFFSET, CARTON** —
      not alphabetically.
- [ ] **11.5** Summary cards now read: Running 3, Completed 3, Carried
      Forward 2.
- [ ] **11.6** `1031 / 1000 pcs` displays correctly — **over**-production is
      shown, not clamped or flagged as an error.

## Scenario 12 — Attention Required

- [ ] **12.1** An **ATTENTION REQUIRED** panel is visible on the board.
- [ ] **12.2** It names `M4` — running with no actual quantity yet.
- [ ] **12.3** Set `M4` Actual to `0.25` and Save. That warning disappears.
- [ ] **12.4** Now add a job and leave it **Planned** with no update. It
      appears under Attention Required as "Planned all day with no update".
- [ ] **12.5** Set it to **NOT STARTED**. It still appears, now as "Planned
      but never started". Both are warnings, in amber, not blockers.

## Scenario 13 — Closing the day (manager)

**The manager does this part on their own phone.**

- [ ] **13.1** As the **supervisor**, confirm you do **not** see a **Close
      Production Day** button.
- [ ] **13.2** As the **manager**, you do.
- [ ] **13.3** First, set one Completed job's Actual to blank (open Solna,
      clear Actual, Save — status stays Completed). Then tap **Close
      Production Day**. **Closure is refused**, and the message names Solna
      and says "Completed but no actual quantity entered".
- [ ] **13.4** Put `2000` back on Solna. Save.
- [ ] **13.5** Tap **Close Production Day** again. You now get a confirmation
      that **lists the outstanding warnings** (the Not Started job) and lets
      you proceed anyway. Confirm.
- [ ] **13.6** The day badge turns to **Closed** and shows who closed it.
- [ ] **13.7** As the **supervisor**, try to add a job to the closed day. It
      is refused: "A manager must reopen it".
- [ ] **13.8** As the **manager**, tap **Reopen Day**. Editing works again.
      Close it again afterwards.

## Scenario 14 — The report

- [ ] **14.1** Tap the **Report** tab. It matches the day, in department
      order, with Plan / Actual / Status per machine.
- [ ] **14.2** `Actual: 1 reel` reads **singular**, `Plan: 3 reels` plural,
      and `1031 pcs` stays `pcs`.
- [ ] **14.3** Carry-forward reasons appear under their jobs.
- [ ] **14.4** A SUMMARY block and an ATTENTION REQUIRED block are at the
      bottom.
- [ ] **14.5** Tap **Copy Full Report**, paste into Notes. It pastes complete.

## Scenario 15 — The WhatsApp report

**This is what replaces the current thread. Test it in WhatsApp itself.**

- [ ] **15.1** Tap **Copy WhatsApp Report**. You get a "copied" confirmation.
- [ ] **15.2** Open WhatsApp, open a chat **with yourself**, paste.
- [ ] **15.3** The heading renders **bold**, with your test date:
      *VCL Production Report – 26 Aug 2026*.
- [ ] **15.4** Department headings render bold: *COMPUTER*, *OFFSET*, *CARTON*.
- [ ] **15.5** Each job is two short lines — machine and job, then
      `actual / plan unit – Status`.
- [ ] **15.6** **Nothing wraps badly** on your phone. No line runs off, no
      half-empty line, no double blank line mid-message.
- [ ] **15.7** The tail has *CARRIED FORWARD*, *NOT STARTED* and
      *ATTENTION REQUIRED* counts.
- [ ] **15.8** Show it to the manager side by side with a real WhatsApp
      message from last week. **Ask directly: is this better, and would you
      send this?** Record the answer:

      .....................................................................

- [ ] **15.9** Confirm nothing was sent automatically — you pasted it
      yourself. There is no WhatsApp integration yet, by design.

## Scenario 16 — Day notes

- [ ] **16.1** Reopen the day. Tap **Add Day Notes**, enter
      `Power cut 11:00–12:30`, Save.
- [ ] **16.2** The note appears at the end of both the full report and the
      WhatsApp report.

## Scenario 17 — History

- [ ] **17.1** Tap the **History** tab. Your test date is listed with a job
      count and an Open/Closed badge.
- [ ] **17.2** Tap it. It opens that day's report.
- [ ] **17.3** Repeat Scenario 3 briefly on a **second** date, then confirm
      both dates appear in History, **newest first**.

## Scenario 18 — Yesterday's jobs are still there tomorrow

- [ ] **18.1** Go to your second test date. Tap **+ Add Job**.
- [ ] **18.2** Recent Jobs now shows the jobs from the first day —
      Chandaria, KCB, Prince, E.W.A.L.
- [ ] **18.3** Add `Chandaria — Yellow Copy` on `M1` from the chip. **Count
      the taps** — it should be about four.
- [ ] **18.4** Open **Remembered Jobs** from the menu (⋯). Each customer/job
      pair appears **once**. No duplicates. Confirm specifically that
      `E.W.A.L / Carton` appears once even though it was entered on two
      machines.

## Scenario 19 — Correcting a job

- [ ] **19.1** In **Remembered Jobs**, open one and fix a spelling
      (e.g. `E.W.A.L` → `EWAL`). Save.
- [ ] **19.2** Go back to the **first** test date's report. The old row
      **still says `E.W.A.L`**.
      > This is intended. The row is the record of what ran. Renaming a
      > master must never rewrite a report that has already been sent.
- [ ] **19.3** Deactivate a remembered job. It disappears from the Recent
      Jobs chips and from search, but historic days are unchanged.

## Scenario 20 — Desk report

- [ ] **20.1** On a desktop, open **Report → VCL Daily Production Report**.
- [ ] **20.2** Set From/To to your test dates. Every row appears with
      department, machine, customer, job, plan, actual, unit, status, reason.
- [ ] **20.3** The **Attention** column says the same things the phone's
      ATTENTION REQUIRED panel said.
- [ ] **20.4** Filter by Department, then by Status. Both work.
- [ ] **20.5** Export to Excel. It opens.

## Scenario 21 — Mobile layout

- [ ] **21.1** Portrait, on the smallest phone available (360px wide): **no
      horizontal scrolling anywhere**.
- [ ] **21.2** No dense grid appears anywhere on the production screen.
- [ ] **21.3** Machine name and quantity are the biggest text on each card,
      readable at arm's length next to a running machine.
- [ ] **21.4** Every button is comfortably thumb-sized.
- [ ] **21.5** Rotate to landscape. Still usable.
- [ ] **21.6** Test on a tablet and a desktop. Both usable; the desktop
      spreads the cards wider rather than stretching them.
- [ ] **21.7** Test **on the factory Wi-Fi where it is weakest.** Time a page
      load: .......... seconds.

## Scenario 22 — Data survives a restart

- [ ] **22.1** Ask the deployer to run `bench restart` (or restart the Frappe
      Cloud bench).
- [ ] **22.2** Reload `/app/vcl-production-lite`. Both test days, every job,
      every quantity, every reason and the Closed status are all still there.
- [ ] **22.3** Remembered jobs are still remembered.

## Scenario 23 — Nothing else broke

- [ ] **23.1** Open `/app/vcl-production` (the **existing** workspace). It is
      unchanged — Customer Product Specifications, Job Cards, Dies.
- [ ] **23.2** Open `/app/ppc`. Unchanged.
- [ ] **23.3** Open a real Job Card Computer Paper and a real Customer Product
      Specification. Both behave exactly as before.
- [ ] **23.4** Confirm with the manager that **no existing process changed**.

## Scenario 24 — Clean up

- [ ] **24.1** If this ran on the **live** site with future dates, delete both
      test days: `VCL Daily Production` list → select → Delete.
- [ ] **24.2** Delete or deactivate any remembered job created purely for the
      test that will never be a real job.
- [ ] **24.3** Leave genuine ones (Chandaria, KCB, Prince, E.W.A.L) — they are
      real and will be wanted on day one.

---

## Tester's verdict

The one question that matters:

> **Would you use this instead of the WhatsApp group tomorrow morning?**

Answer: ....................................................................

If no — what specifically stops you?

...........................................................................

...........................................................................

---

## Sign-off

Supervisor / tester: ............................  Date: ..............

Manager: ............................  Date: ..............

Ten-second test result (3.3): .......... seconds

All scenarios passed: ☐    Failures logged and attached: ☐

Approved for merge to `main`: ☐
