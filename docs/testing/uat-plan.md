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

### 2026-04-21 — Production Planner (cp_planning_board) first cut

**What changed since the previous deploy:**

* New `cp_planning_board` Frappe page under the VCL Production
  workspace, with a scoped shell (header + left panel + right panel
  + modals).
* Three server-driven view modes — Week (default), Job Card, Station
  — all powered by six whitelisted methods on the page:
  * `get_workstation_columns(product_line)` — stage/machine columns
    filtered by dept tag on Workstation.
  * `get_schedule_entries(date_from, date_to, product_line)` — PSL +
    PE rows for the visible week.
  * `save_schedule_entry(entry)` / `save_production_entry(entry)` —
    create / update PSL and PE.
  * `get_machine_conflicts(date_from, date_to)` — cross-dept double
    bookings on shared presses (Printing, module constant
    `SHARED_WORKSTATION_TYPES`).
  * `get_daily_schedule(date, depts)` — rows for the printed
    schedule.
* Dept tabs — six in total (`Computer Paper`, `ETR`, `Label`,
  `General Stationery and Exercise Book`, `Mono Boxes`,
  `Corrugation and Carton Department`) — switch the column set +
  entry list; prev/next arrows + `<input type="week">` navigate
  the Mon–Sat window. Tagging lives on Workstation Type
  (`custom_product_line_tags`), so a workstation inherits its
  parent WT's product-line coverage; there is no per-workstation
  override.
* Entry modal (add / edit / delete) with stage-specific qty fields
  (Design → days, Printing → reels + sheets planned / sheets
  actual, Collation → sets, Slitting → rolls). Status dropdown
  (`Draft` / `Confirmed` / `Cancelled`). Actual toggle creates a
  PE linked to the PSL via `schedule_line`. Manual-entry path (no
  job card) shows the ⚡ banner and requires a Description.
* Conflict highlighting on shared presses: amber cell bg,
  `.conflict-chip` reading "Double-booked · Computer Paper + ETR",
  `.entry-block.conflicted` outline on each involved
  tile, header pill "⚠ N conflict(s)". Saving into a conflict
  triggers a red toast — the save itself still succeeds (warn +
  allow, matches FINAL handover §F5).
* Print Daily: day-picker modal → `get_daily_schedule` → A4
  landscape HTML blob → `window.open` with `<a download>` fallback
  when popups are blocked. Self-contained HTML (no external
  assets), signature lines at the foot.
* New DocTypes: `Workstation Product Line Tag` (child), `Production
  Schedule Line` (non-submittable, `PSL-YYYY-#####` naming),
  `Production Entry` (submittable, `PE-YYYY-#####` naming).
* Patch `patch_v5_0`:
  * Extends `custom_product_line` Select options on Workstation
    Type and Workstation to include `ETR` (`Label` /
    `Carton` kept).
  * Adds `custom_product_line_tags` Table field on Workstation.
  * Seeds `Design` Workstation Type + `Design Desk` Workstation
    (tagged `All`).
  * Migrates each Workstation's legacy single-Select value into a
    matching child-table row. Idempotent.
* VCL Production workspace gets a `Production Planning` header
  with three shortcuts: Production Planner, Production Schedule
  Lines, Production Entries.

**Scenarios below that specifically cover this deployment:**

* Scenario J — Planner loads + dept/column fetch per product line
* Scenario K — Entry modal: add, edit, delete, manual-entry path
* Scenario L — Status flow + Actual toggle → PE creation
* Scenario M — Cross-dept conflict on shared press
* Scenario N — Print Daily (A4 landscape, all dept / current dept)
* Scenario O — Views: Week, Job Card, Station

### 2026-04-16 — Live SVG die-cut visualization in Carton Job Card

**What changed since the previous deploy:**

* A new `html_board_visualization` HTML field added to the Board Plan
  section of Job Card Carton, immediately below the existing formula
  reference box.
* The carton visualization renders a live SVG die-cut diagram that
  updates in real-time as dimensions, product type, or joint type change.
  It is wired as Step 6 in the existing 5-step calculation pipeline.
* Supported product types:
  * **2 Flap RSC** — panels (Tab, Side, Front, Side, Back) with
    top/bottom flaps, fold lines, stitch/glue markers, dimension labels.
  * **3 Flap RSC** — same blank shape as 2 Flap RSC.
  * **Tray** — cross/plus-shaped layout with base, 4 walls, triangular
    corner ear tabs.
  * **Die Cut** — shows an amber info message (custom shapes can't be
    generalized).
* `product_type` and `joint_type` are now pipeline triggers — changing
  them re-runs the full calculation pipeline (previously they did not).
* When ply is SFK, the visualization area is blank (SFK has no board
  plan).
* Color-coded legend strip displayed below the SVG.

**Scenarios below that specifically cover this deployment:**

* Scenario D — updated to check the SVG visualization renders alongside
  the formula reference box
* Scenario I (new) — Board Visualization across all product types
* Scenario E — SFK visibility (confirms visualization is hidden for SFK)

### 2026-04-15 — Hard reset of production execution layer

**What changed since the previous deploy:**

* The full production execution / planning layer has been removed for a
  clean restart. Specifically:
  * `Department Daily Plan` and `Department Daily Plan Line` doctypes
    deleted.
  * Production Control section (production_status, production_stage,
    planned_for_date, priority, qty_completed, qty_pending,
    last_production_update, completed_on, hold_reason, production_comments)
    stripped from `Job Card Computer Paper` and `Job Card Label`.
  * `Daily Planning` sidebar group removed from the VCL Production
    workspace.
  * New patch `remove_production_execution_layer` drops the deleted
    doctypes, their tables, and the orphan job-card columns from sites
    that previously had them.
* Carton Job Card creation flow and the existing Customer Product
  Specification / Computer Paper / Label / Dies / Dies Order / Colour of
  Parts setup all stay intact.

**Scenarios below that specifically cover this deployment:**

* Scenario A — Customer Product Specification carton section
* Scenario B — Computer Paper Job Card regression (now confirms the
  Production Control section is gone)
* Scenario C — Label Job Card regression (same)
* Scenario D — Carton Job Card create + auto-populate
* Scenario E — SFK layer visibility
* Scenario F — 3-ply path
* Scenario G — 3-ply → 5-ply conversion
* Scenario H — Workspace & sidebar layout (now expects no Daily Planning
  group and no Department Daily Plan tiles)

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
production-layer removal, and that the Production Control section is no
longer present.

- [ ] From the VCL Production workspace, click **New Computer Paper Job Card**.
- [ ] The form should open in create mode (not list view, not a 404).
- [ ] Confirm the form has these sections only: Product Specification,
      Job-Specific Details, Numbering, Plate Information, Approvals.
- [ ] Confirm there is **no** Production Control section and **no**
      production_status / production_stage / qty_completed / qty_pending /
      planned_for_date / hold_reason / production_comments fields anywhere
      on the form.
- [ ] Fill a smoke-test record with any one existing customer spec.
- [ ] **Stop. Call manager. Do not Save.**
- [ ] Manager confirms layout, closes the form via Discard / browser close.

- [ ] From the workspace, click **Computer Paper Job Cards**.
- [ ] The list view should load and show existing historical records.

---

## Scenario C — Label Job Card (regression only)

Same as Scenario B but for Label:

- [ ] Workspace → **New Label Job Card** opens a create form.
- [ ] Confirm there is **no** Production Control section on the form.
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
- [ ] Manager checks the **formula reference box** is visible in the Board
      Plan section (blue left-border box with calculation formulas).
- [ ] Manager checks the **SVG die-cut diagram** is visible below the formula
      box — it should show color-coded panels, fold lines, dimension labels,
      and a "Blank: …mm x …mm" summary at the bottom.
- [ ] Manager checks a **legend strip** appears below the SVG (Fold line,
      Front/Back, Side, Flaps, and joint marker legend).
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
  - [ ] The SVG die-cut visualization area is **empty/hidden** (SFK has
        no board plan).
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
- [ ] Sidebar/content shows two headers in this order:
  - [ ] **Customer Specifications**
  - [ ] **Job Card Tracking**
- [ ] There is **no** "Daily Planning" header and **no** "New Daily Plan"
      / "Daily Plan List" tiles anywhere on the workspace.
- [ ] Under **Customer Specifications**: Customer Product Specifications, Dies List.
- [ ] Under **Job Card Tracking**:
  - [ ] New Computer Paper Job Card
  - [ ] Computer Paper Job Cards
  - [ ] New Label Job Card
  - [ ] Label Job Cards
  - [ ] New Carton Job Card
  - [ ] Carton Job Cards
- [ ] `/app/job-card-tracking` should no longer resolve (404 or redirect is
      both acceptable — it must not show the *old* workspace).
- [ ] Search the desk for `Department Daily Plan`. **No result** should
      appear in the search dropdown.
- [ ] `/app/department-daily-plan` should 404.

---

## Scenario I — Board Visualization across product types

Goal: confirm the SVG die-cut visualization renders correctly for each
product type and updates when inputs change.

Starting from a fresh new Carton Job Card:

- [ ] Set ply to **3**, enter L=300, W=200, H=150 (arbitrary test values).
- [ ] Set product type to **2 Flap RSC**, joint type to **Stitched**.
  - [ ] SVG shows panels: Tab (40mm), Side, Front, Side, Back — with
        top and bottom flaps.
  - [ ] Red **X stitch marks** are visible on the tab panel.
  - [ ] Orange dashed fold lines are visible between panels and at
        flap boundaries.
  - [ ] Dimension labels (L, W, H, flap, tab width in mm) appear on edges.
  - [ ] "Blank: …mm x …mm" summary line appears at the bottom.
  - [ ] Legend strip shows: Fold line, Front/Back, Side, Flaps,
        Stitch marks.
- [ ] Change joint type to **Gluing - Manual**.
  - [ ] SVG updates: tab panel shrinks to 30mm, stitch X marks are
        replaced by green dashed glue lines.
  - [ ] Legend changes from "Stitch marks" to "Glue lines".
- [ ] Change product type to **3 Flap RSC**.
  - [ ] SVG shows same layout as 2 Flap RSC (same blank shape).
- [ ] Change product type to **Tray**.
  - [ ] SVG changes to a cross/plus shape: central base with 4 walls.
  - [ ] Triangular corner ear tabs visible at all 4 corners (dashed
        outline).
  - [ ] No glue tab or joint markers.
  - [ ] Legend changes to: Fold line, Base, Walls, Corner tabs.
- [ ] Change product type to **Die Cut**.
  - [ ] SVG area replaced by an amber-styled message: "Die Cut —
        Visualization not available. Custom die shapes vary per job."
- [ ] Clear product type (set to blank).
  - [ ] SVG area shows: "Select a product type to see the blank layout."
- [ ] Change dimensions (increase height by 50mm).
  - [ ] After selecting a product type again, confirm the SVG resizes
        and dimension labels update to match the new values.
- [ ] **Discard the form.** Do not Save.

---

## Scenario J — Production Planner loads + dept / column fetch

**Prerequisite:** `patch_v5_0` has run (check the Patch Log shows it
executed once) and `Design Desk` exists as a Workstation under the
`Design` Workstation Type, tagged `All`. The Phase 1 Workstation
tagging table (FINAL §A2) has been applied manually.

- [ ] Open VCL Production workspace. The new **Production Planning**
      header appears with three shortcuts: **Production Planner**,
      **Production Schedule Lines**, **Production Entries**.
- [ ] Click **Production Planner**. The page at `/app/cp_planning_board`
      loads with the scoped shell (blue header, left job-card panel,
      right stage/grid area). Browser console shows no JS errors.
- [ ] The Week view is active by default. Today's ISO week is shown in
      the week input. The **Computer Paper** dept tab is active.
- [ ] Stage header shows at least these columns, in order: **Design**
      (Design Desk), **Printing** (Miyakoshi 01, Miyakoshi 02, Hamada
      01), **Collation** (Collator 1, Collator 2).
- [ ] Switch to **ETR**. Columns change to **Design** (Design
      Desk), **Printing** (Miyakoshi 01, Miyakoshi 02 only), **Slitting**
      (Slitter 1, Slitter 2). No Hamada 01, no Collators.
- [ ] Switch back to **Computer Paper**. Columns return to CP set.
- [ ] Click the left arrow once; week input decrements by 1 week.
      Click the right arrow twice; week advances 1 week past today.
- [ ] Type a future week directly into the week input. Grid reloads to
      that week (empty if no entries).

## Scenario K — Entry modal (add, edit, delete, manual path)

**Prerequisite:** Scenario J completed. At least one open `Job Card
Computer Paper` exists on the site for linking.

- [ ] In Week view on CP dept, click the `+` in a cell under **Printing
      · Miyakoshi 01** for today.
- [ ] Modal opens titled **Add Entry**. Stage reads `Printing`,
      Workstation defaults to `Miyakoshi 01`, Date is today, Shift is
      `Day Shift`, Status is `Draft`. Quantities section shows
      **Planned Reels** and **Planned Sheets** inputs.
- [ ] Select `Job Card Computer Paper` as Job Card Type, type an
      existing Job Card name into the Job Card field, fill Planned
      Reels = 5, Planned Sheets = 10000, Operator = "TEST UAT-K1".
      Save.
- [ ] Toast shows "Entry saved ✓". Modal closes. A blue `.entry-block`
      tile appears in the cell with the job card tail as `.eb-id`,
      "PLAN · Draft" as type, "5 reels" as qty, "Day · TEST UAT-K1"
      as meta.
- [ ] Click the tile. Modal re-opens in **Edit Entry** mode with every
      field pre-filled and the **Delete Entry** button visible.
- [ ] Change Planned Reels to 7, Save. Tile updates to "7 reels",
      toast "Entry updated ✓".
- [ ] Click the tile again, click **Delete Entry**, confirm. Toast
      "Deleted". Tile disappears from the grid.
- [ ] Click `+` in a Printing cell again. Clear the Job Card Type
      dropdown → ⚡ purple "Manual entry — no job card linked" banner
      appears, Description field reveals, Job Card input disables.
- [ ] Leave Description blank, click Save. Red toast "Description is
      required for manual entries." No entry saved.
- [ ] Fill Description = "Plate change test", Planned Reels = 0,
      Operator = "TEST UAT-K2", Save. Purple `.entry-block.manual` tile
      appears, eb-id reads "MANUAL".
- [ ] Delete the manual tile via its modal.

## Scenario L — Status flow + Actual toggle → PE creation

**Prerequisite:** Scenario K completed; create a PSL the same way as
K1 with Planned Reels = 4, Status = `Draft`, Operator = "TEST UAT-L".

- [ ] Tile shows "PLAN · Draft". Open the tile. Change Status to
      `Confirmed`. Save. Tile now reads "PLAN · Confirmed". PSL list
      view (`/app/production-schedule-line`) confirms the status
      change.
- [ ] Open the tile again. Toggle **Actual recorded** on. Qty section
      now shows **Planned Reels**, **Planned Sheets**, **Actual
      Sheets** (all three in one row).
- [ ] Fill Actual Sheets = 4300. Save. Toast "Entry updated ✓". The
      grid now shows two tiles in that cell: the blue plan tile (still
      shows "4 reels") **and** a green `.entry-block.actual` tile
      ("ACTUAL · Draft", "4,300 sheets").
- [ ] Open Production Entry list view. The new PE has `schedule_line`
      set to the PSL's name. Open the PE form — `schedule_line` field
      is visible and populated.
- [ ] Click the green actual tile. Modal re-opens with the toggle
      already on, Actual Sheets pre-filled.
- [ ] Delete the PE via the modal's Delete button. Green tile
      disappears; blue plan tile remains.
- [ ] Delete the blue plan tile. Both list views confirm the rows are
      gone.

## Scenario M — Cross-dept machine conflict

- [ ] On **Computer Paper**, add a PSL on **Printing · Miyakoshi 01**
      for a test day (e.g. Wednesday of this week). Status Draft,
      planned reels 3, operator "TEST UAT-M-CP".
- [ ] Switch to **ETR**. Verify the conflict badge in the
      header is NOT showing yet.
- [ ] Still on ETR, add a PSL on **Printing · Miyakoshi 01** for the
      same Wednesday. Status Draft, planned reels 2, operator
      "TEST UAT-M-ETR".
- [ ] Save triggers a red toast "⚠ Machine conflict: Miyakoshi 01 is
      also booked for Computer Paper on <date>."
- [ ] The Wednesday Printing·Miyakoshi 01 cell shows amber background,
      an orange "⚠ Double-booked · Computer Paper + ETR"
      chip, and the two tiles each have an amber outline
      (`.entry-block.conflicted`).
- [ ] Header shows "⚠ 1 conflict" pill.
- [ ] Switch back to **Computer Paper**. The same cell on the same day
      is also highlighted (amber bg + chip + outline on the CP tile).
      Header shows "⚠ 1 conflict".
- [ ] Delete the ETR entry. Reload the page. Conflict visuals and
      badge disappear.
- [ ] Delete the CP entry.

## Scenario N — Print Daily

- [ ] Create one CP PSL and one ETR PSL on the same day (today) — any
      stage/machine is fine. Use Operator "TEST UAT-N".
- [ ] From either dept tab, click **Print Daily** in the header.
- [ ] Day picker modal opens. Today's button shows a green dot and the
      `today` highlight. Print Schedule button is disabled.
- [ ] Select today. Print Schedule button enables.
- [ ] Radio **Current dept only** is checked by default. Click **Print
      Schedule**.
- [ ] A new browser tab/window opens with an A4-landscape styled HTML
      page titled "Production Schedule — <day> <date>". The browser's
      print dialog fires automatically.
- [ ] Page header: logo box "VCL" + "Vimit Converters Ltd · Production
      Schedule" + day name + date + timestamp.
- [ ] Only one dept section appears (the one that was active). The
      TEST UAT-N row is in the table with its Stage · Machine, Job
      Card, Planned Qty (reels / sheets or `<qty> <uom>`), Shift,
      Operator, Type ("PLAN" or "MANUAL"), Notes, and an empty
      Sign-off box.
- [ ] Three signature lines at the foot: "Production Manager
      Sign-off", "Floor Supervisor Sign-off", "Date & Time".
- [ ] Close the print tab. Open the day picker again, tick **All
      departments**, select today, Print. Two dept sections now appear
      ("Computer Paper" then "ETR"), each with their own
      title bar and table.
- [ ] Block popups in the browser settings, repeat the print flow. An
      HTML file is downloaded instead; a toast says "Popup blocked —
      schedule downloaded. Open + print manually."
- [ ] Re-enable popups. Delete the two test PSLs.

## Scenario O — Views: Week / Job Card / Station

- [ ] Set up two PSLs on CP: one on Printing · Miyakoshi 01 (today),
      one on Collation · Collator 1 (tomorrow), both linked to the
      same Job Card. Use Operator "TEST UAT-O".
- [ ] **Week view** (default). Rows are Mon–Sat. Both PSLs appear in
      their (day, stage, workstation) cells. Clicking `+` on any cell
      opens the modal with date pre-filled.
- [ ] Click **Job Card**. Rows are now job cards; columns are still
      stage × machine. One row labelled with the test Job Card
      appears. Both PSL tiles are on that row — in Printing·Miyakoshi
      01 and Collation·Collator 1 cells. No `+` button is shown in
      Job Card view cells (expected — date context missing).
- [ ] Add a manual PSL on any day (via Week view). Switch to Job Card
      view. A `MANUAL` row appears at the bottom with the ad-hoc
      entry.
- [ ] Click **Station**. Header changes to Mon–Sat day columns. Rows
      are now each workstation (one per row: Design Desk, Miyakoshi
      01, Miyakoshi 02, Hamada 01, Collator 1, Collator 2). The test
      PSLs appear on their respective (workstation, day) cells. `+`
      buttons are present and work — clicking opens the modal with
      date + stage + workstation pre-filled.
- [ ] Click **Week**. View reverts without refetching.
- [ ] Delete the test PSLs.

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
