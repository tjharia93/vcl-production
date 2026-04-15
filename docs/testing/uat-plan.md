# UAT Plan — VCL Production

**User Acceptance Testing** is run by the factory/production team on a staging
or pre-production site every time a new version of `production_log` is
deployed. It is the last check before we merge to `main`.

**Rules for this document:**

1. Work top to bottom.
2. Tick each checkbox as it passes.
3. **Do not Save or Submit any record until a manager is physically at the
   desk reviewing the screen.**
4. If anything fails: stop, screenshot, flag the manager.
5. Keep [`test-data.md`](./test-data.md) open in a second window — you will
   need to refer to CSV row numbers constantly.

---

## Deployment focus

> **Update this section in every PR that changes behaviour.** Add a dated
> entry at the top. Older entries stay so we can see the trail of what was
> tested when.

### 2026-04-15 — Job Card Carton + VCL Production workspace rename

**What changed since the previous deploy:**

* Workspace renamed from `Job Card Tracking` to `VCL Production`
  (URL now `/app/vcl-production`).
* Sidebar restructured into Customer Specifications / Job Card Tracking /
  Daily Planning sections.
* Stale `Job Card Production Entry` references purged.
* **Job Card Carton** doctype added, with the 5-step calculation pipeline
  (ply rules → SFK UI rules → flap auto-calc → board sizes → weight calc).
* Customer Product Specification expanded with 23 new carton fields
  (dimensions, layer GSMs, layer materials, joint type, box layout).
* Department Daily Plan now supports `Carton` as a job card type.
* New `Print Format` fixture placeholder for "Carton Job Card".

**Scenarios below that specifically cover this deployment:**

* Scenario A — Customer Product Specification carton section
* Scenario D — Carton Job Card create + auto-populate
* Scenario E — SFK layer visibility
* Scenario F — 3-ply path
* Scenario G — 3-ply → 5-ply conversion
* Scenario H — Workspace & sidebar layout
* Scenario I — Department Daily Plan carton linkage

---

## Pre-flight

Before starting, confirm with the deployer:

- [ ] Which site am I testing on? (staging URL)
- [ ] Has `bench migrate` finished and OAT smoke tests passed?
- [ ] Have the previous test records been cleaned? (search for `TEST-` prefix)
- [ ] Is the manager available for sign-off calls?
- [ ] I have the CSV open at the OneDrive path.
- [ ] The manager has told me which CSV row number is this cycle's
      "3-ply → 5-ply conversion" row. Row number: _________

---

## Scenario A — Customer Product Specification (carton section)

Goal: create one Customer Product Specification per CSV row before any Job
Card is opened. The auto-populate path depends on this.

For **CSV row 1** (the SFK job):

- [ ] From the VCL Production workspace, click **Customer Product Specifications**.
- [ ] Click **New**.
- [ ] Name the spec `TEST-CSV01-<customer name from row 1>`.
- [ ] Fill the carton section from the CSV row:
  - [ ] `ply` field set to match the CSV value (SFK / 3 / 5)
  - [ ] Length / width / height / flap mm
  - [ ] Layer GSMs — only the ones that apply for the row's ply
  - [ ] Layer materials — only the ones that apply
  - [ ] Flute type (if 3-ply or 5-ply)
  - [ ] Joint type
  - [ ] IDOD
  - [ ] Product type
- [ ] Hidden layer fields for higher plies should **not** be visible on screen
      (e.g. for SFK, layers 3 / 4 / 5 should be hidden).
- [ ] **Stop. Call the manager over. Do not Save.**
- [ ] Manager reviews and clicks Save.

Repeat the above for CSV rows 2, 3, 4 and the chosen conversion row.

---

## Scenario B — Computer Paper Job Card (regression only)

Goal: confirm the existing computer paper flow has not broken after the
workspace rename and patch run.

- [ ] From the VCL Production workspace, click **New Computer Paper Job Card**.
- [ ] The form should open in create mode (not list view, not a 404).
- [ ] Fill a smoke-test record with any one existing customer spec.
- [ ] **Stop. Call manager. Do not Save.**
- [ ] Manager confirms layout, closes the form via Discard / browser close.

- [ ] From the workspace, click **Computer Paper Job Cards**.
- [ ] The list view should load and show existing historical records.

---

## Scenario C — Label Job Card (regression only)

Same as Scenario B but for Label:

- [ ] Workspace → **New Label Job Card** opens a create form.
- [ ] Fill smoke-test values, call manager, discard.
- [ ] Workspace → **Label Job Cards** list loads.

---

## Scenario D — Carton Job Card create + auto-populate

This is the main event for this deployment.

For **CSV row 1** (SFK), after its Customer Product Specification has been
saved by the manager in Scenario A:

- [ ] Workspace → **New Carton Job Card**.
- [ ] The form opens in create mode on the "JOB CARD CREATION" tab.
- [ ] In **Customer Product Specification**, search for and select
      `TEST-CSV01-<customer>`.
- [ ] As soon as the link is chosen, the form should auto-populate:
  - [ ] Customer name, specification name, ply
  - [ ] All five layer GSM fields (populated with the spec values, hidden
        ones zero)
  - [ ] All five layer material fields
  - [ ] Flute type
  - [ ] Joint type
  - [ ] IDOD
  - [ ] Product type
  - [ ] Length / width / height / flap dimensions
- [ ] Fill **quantity ordered** from the CSV row.
- [ ] Fill **due date** from the CSV row.
- [ ] **Stop. Call manager.**
- [ ] Manager checks the board plan HTML preview renders something sensible
      (not blank, not `undefined`).
- [ ] Manager checks `approximate_weight_grams` has a non-zero value.
- [ ] Manager clicks Save, then Submit (if happy).

Repeat for CSV rows 2, 3, 4 (3-ply and 5-ply variants).

---

## Scenario E — SFK layer visibility rules

Goal: prove the ply rules step of the pipeline correctly hides unused layers.

Starting from a fresh new Carton Job Card (do not use the one from Scenario D):

- [ ] Open **New Carton Job Card**.
- [ ] In the **ply** dropdown, choose **SFK**.
- [ ] On screen:
  - [ ] Layer 1 GSM / material → **visible**
  - [ ] Layer 2 GSM / material → **visible**
  - [ ] Layer 3 GSM / material → **hidden**
  - [ ] Layer 4 GSM / material → **hidden**
  - [ ] Layer 5 GSM / material → **hidden**
  - [ ] Flute type → **hidden** (SFK has no flute)
- [ ] Change **ply** to **3**.
  - [ ] Layers 1, 2, 3 → visible; layers 4, 5 → hidden
  - [ ] Flute type → visible again
- [ ] Change **ply** to **5**.
  - [ ] All five layers → visible
  - [ ] Flute type → visible
- [ ] Change **ply** back to **SFK**.
  - [ ] Layers 3 / 4 / 5 hide again
  - [ ] Values previously entered in layers 3 / 4 / 5 are cleared, not
        carried over invisibly.
- [ ] **Discard the form.** Do not Save.

---

## Scenario F — 3-ply calculation path

Using **CSV row 2** (first 3-ply job) and its spec from Scenario A:

- [ ] New Carton Job Card → link to `TEST-CSV02-*`.
- [ ] Auto-populate should show ply = 3, layers 1–3 populated, layers 4–5 hidden.
- [ ] Enter quantity from CSV row 2.
- [ ] Confirm that the following have been auto-calculated (not empty):
  - [ ] `board_length_planned_mm`
  - [ ] `board_width_planned_mm`
  - [ ] `approximate_weight_grams`
- [ ] **Stop. Call manager.** Manager checks the calculated values match the
      historical values recorded in CSV row 2 (within a few mm tolerance for
      rounding).
- [ ] Manager Saves if happy, otherwise Discard.

---

## Scenario G — 3-ply → 5-ply conversion

This scenario uses the conversion row the manager picked in Pre-flight.

- [ ] New Carton Job Card → link to `TEST-CSV<row>-*` (the conversion row's
      spec, which is 3-ply).
- [ ] Auto-populate fills the form as a 3-ply job.
- [ ] Note the current values of:
  - [ ] Visible layer GSMs
  - [ ] Board plan width / length
  - [ ] Approximate weight
- [ ] Change **ply** from `3` to `5`.
- [ ] Layers 4 and 5 GSM / material fields must **re-appear**.
- [ ] Enter plausible values for layers 4 and 5 (take them from any 5-ply
      row in the CSV — the exact values do not matter, only that the
      pipeline re-runs).
- [ ] Confirm:
  - [ ] Board plan recalculated (different from before)
  - [ ] Approximate weight recalculated (higher than before)
  - [ ] No error toasts / console errors
- [ ] **Stop. Call manager.**
- [ ] Manager Discards. **This record must not be saved** — it is a
      hypothetical "what if we converted this job" exploration.

---

## Scenario H — Workspace & sidebar layout

- [ ] Browse to `/app/vcl-production`. The workspace loads.
- [ ] Sidebar/content shows three headers in this order:
  - [ ] **Customer Specifications**
  - [ ] **Job Card Tracking**
  - [ ] **Daily Planning**
- [ ] Under **Customer Specifications**: Customer Product Specifications, Dies List.
- [ ] Under **Job Card Tracking**:
  - [ ] New Computer Paper Job Card
  - [ ] Computer Paper Job Cards
  - [ ] New Label Job Card
  - [ ] Label Job Cards
  - [ ] New Carton Job Card
  - [ ] Carton Job Cards
- [ ] Under **Daily Planning**: New Daily Plan, Daily Plan List.
- [ ] `/app/job-card-tracking` should no longer resolve (404 or redirect is
      both acceptable — it must not show the *old* workspace).

---

## Scenario I — Department Daily Plan with Carton

- [ ] Workspace → **New Daily Plan**.
- [ ] Add a line where **Job Card Type** = `Carton`.
- [ ] The **Job Card** lookup on that line should filter to Job Card Carton
      records only.
- [ ] Pick one of the cards Scenario D saved.
- [ ] **Stop. Call manager. Do not Save** unless the manager wants to keep
      the planning entry for the next test cycle.

---

## Full regression pass — CSV rows 6 through 10

Once the cherry-picked 5 have all ticked green, walk rows 6 → 10 through
Scenarios A + D in sequence (nothing else needed). Note any anomalies on the
sign-off sheet.

- [ ] Row 6 spec + card
- [ ] Row 7 spec + card
- [ ] Row 8 spec + card
- [ ] Row 9 spec + card
- [ ] Row 10 spec + card

---

## Sign-off

When every box above is ticked, complete `sign-off.md` with:

* Release tag / commit hash
* Tester name
* Manager name
* Date
* Any anomalies observed
* Rows skipped and why

File the signed sheet under `docs/testing/sign-offs/<release-tag>.md` in the
repo so we have an audit trail.
