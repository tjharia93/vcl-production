# VCL PRODUCTION — COMPREHENSIVE UAT

**Custom App: production_log | Modules: Production Log (PPC) + Job Card Tracking**

Test Date: __________ | Tester: __________ | Site: vimitconverters.frappe.cloud

---

## EXECUTIVE SUMMARY

This document covers User Acceptance Testing for the entire production_log custom app: master data setup, Customer Product Specifications, Dies management, all three Job Card types (Computer Paper, Label, Carton), the Carton Job Card print format with SVG visualisation, Daily Production Schedule, Schedule Board, Production Entry, Downtime Entry, reports, dashboard connections, and role-based permissions.

| Suite | Total | Pass | Fail | Skip | Rate (excl skip) |
|-------|-------|------|------|------|-------------------|
| Section 1 — Master Data & Setup | __ | __ | __ | __ | __% |
| Section 2 — Customer Product Specifications | __ | __ | __ | __ | __% |
| Section 3 — Dies & Dies Orders | __ | __ | __ | __ | __% |
| Section 4 — Job Card Computer Paper | __ | __ | __ | __ | __% |
| Section 5 — Job Card Label | __ | __ | __ | __ | __% |
| Section 6 — Job Card Carton | __ | __ | __ | __ | __% |
| Section 7 — Daily Production Schedule | __ | __ | __ | __ | __% |
| Section 8 — Daily Schedule Board | __ | __ | __ | __ | __% |
| Section 9 — Production Entry | __ | __ | __ | __ | __% |
| Section 10 — Downtime Entry | __ | __ | __ | __ | __% |
| Section 11 — Dashboard & Reports | __ | __ | __ | __ | __% |
| Section 12 — Permissions | __ | __ | __ | __ | __% |

---

## CRITICAL DEFECTS FOUND

| Test ID | Severity | Issue | Impact / Action |
|---------|----------|-------|-----------------|
|  |  |  |  |

---

## SECTION 1 — MASTER DATA & SETUP

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-1.01 | Workstation Type | Enumerate all live Workstation Types | Navigate to Workstation Type list | Tester records every type name in Notes. This list becomes source of truth for UT-1.04/1.05 |  |  |
| UT-1.02 | Workstation Type | Verify custom_product_line field | Open any Workstation Type | Select field visible with options: All, Computer Paper, Label, Carton. Default = All |  |  |
| UT-1.03 | Workstation Type | Verify custom_default_stage field | Open any Workstation Type | Link field to Production Stage visible and selectable |  |  |
| UT-1.04 | Workstation Type | Set product_line on a Computer Paper type | Pick a type from UT-1.01 that runs Computer Paper, set custom_product_line = Computer Paper, save | Saves. Value persists on reload |  |  |
| UT-1.05 | Workstation Type | Set product_line on a Label type | Pick a type that runs Label work, set custom_product_line = Label, save | Saves. Value persists on reload |  |  |
| UT-1.06 | Workstation | Verify 5 custom fields on Workstation form | Open any Workstation, scroll to custom section | Visible: custom_product_line, custom_max_width_mm, custom_max_colors, custom_max_speed_per_hour, custom_location_note |  |  |
| UT-1.07 | Workstation | Set custom_max_speed_per_hour on a live workstation | Open an active workstation, enter realistic speed (e.g., 4000), save | Saves. Consumed by DPS estimated_hours calc (UT-7.08) |  |  |
| UT-1.08 | Workstation | Verify max_colors accepts integer only | Type 'abc' into custom_max_colors | Frappe rejects non-integer input |  |  |
| UT-1.09 | Production Stage | Verify full seed list after Phase 2 migration | Navigate to Production Stage list | 20 records: Design, Pre-Press, Printing, Numbering, Collating, Wrapping, Die Cutting, Re-winding, Slitting, Finishing, Corrugating, Pasting, Creasing, Creasing & Slotting, Slotting, Folding & Gluing, Stitching, Gluing, Bundling, Packing |  |  |
| UT-1.10 | Production Stage | Verify Computer Paper flow | Filter by product_line = Computer Paper or All | Design, Pre-Press, Printing, Numbering, Collating, Wrapping, Packing |  |  |
| UT-1.11 | Production Stage | Verify Label flow | Filter by product_line = Label or All | Design, Pre-Press, Printing, Die Cutting, Re-winding, Slitting, Finishing, Packing |  |  |
| UT-1.12 | Production Stage | Verify Carton flow | Filter by product_line = Carton or All | Design, Pre-Press, Printing, Corrugating, Pasting, Creasing, Slotting, Stitching, Gluing, Bundling, Packing (plus legacy Creasing & Slotting, Folding & Gluing) |  |  |
| UT-1.13 | Production Stage | Verify QC points | Open Wrapping, Slitting, Bundling, Packing | is_qc_point = checked on all |  |  |
| UT-1.14 | Production Stage | Duplicate stage name rejected | Try to create a stage named 'Printing' | Frappe rejects; stage_name is unique |  |  |
| UT-1.15 | Workstation Stage | Add workstation to Production Stage | Open Printing, add row: workstation=<any>, is_preferred=checked, hourly_rate=6000, setup_time_mins=30 | Row saves |  |  |
| UT-1.16 | Workstation Stage | Add multiple workstations | Add a second row, is_preferred=unchecked | Both rows saved; only one preferred |  |  |
| UT-1.17 | Workstation Stage | Verify hourly_rate fallback blank | Leave hourly_rate blank on a row, save | Saves. At scheduling, system falls back to Workstation.custom_max_speed_per_hour (UT-7.08) |  |  |
| UT-1.18 | Waste Reason | Verify 8 seed Waste Reasons | Navigate to Waste Reason list | Setup Waste, Misprinted, Off-Register, Torn Web, Material Defect, Wrong Die, Colour Mismatch, Trim Waste |  |  |
| UT-1.19 | Waste Reason | Verify category options | Open any Waste Reason | Options: Setup, Running, Material Defect, Operator Error, Other |  |  |
| UT-1.20 | Waste Reason | Disable a waste reason | Open Trim Waste, uncheck enabled, save | Saves. Should not appear in PE dropdown (UT-9.05) |  |  |
| UT-1.21 | Waste Reason | Create new waste reason | Create: Blade Wear, category=Running, enabled=1 | Saves successfully |  |  |
| UT-1.22 | Downtime Reason | Verify 8 seed Downtime Reasons | Navigate to Downtime Reason list | Mechanical Breakdown, Electrical Fault, Power Outage, Material Shortage, Planned Maintenance, Die Changeover, Operator Unavailable, Waiting for QC |  |  |
| UT-1.23 | Downtime Reason | Verify Planned Maintenance is_planned | Open Planned Maintenance | is_planned = checked |  |  |
| UT-1.24 | Downtime Reason | Verify Mechanical Breakdown is_planned | Open Mechanical Breakdown | is_planned = unchecked |  |  |
| UT-1.25 | Downtime Reason | Create new downtime reason | Create: Ink Shortage, category=Material Shortage, is_planned=0 | Saves successfully |  |  |

---

## SECTION 2 — CUSTOMER PRODUCT SPECIFICATIONS

Templates per customer + product line, reused when creating job cards.

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-2.01 | CPS Create | Create spec for Computer Paper | New CPS: product_type=Computer Paper, specification_name=<name>, customer=<customer>, status=Active, fill CP-specific fields | Saves. CP-only fields visible (ply, board_type, flute_type hidden or N/A) |  |  |
| UT-2.02 | CPS Create | Create spec for Label | New CPS: product_type=Label, fill label dims, dies reference | Saves. Label fields visible: label_length, label_width, dies |  |  |
| UT-2.03 | CPS Create | Create spec for Carton | New CPS: product_type=Carton, fill ply, board_type, flute_type, ctn_length/width/height, printing_or_plain | Saves. Carton fields visible |  |  |
| UT-2.04 | CPS Dynamic | Verify field visibility toggles by product_type | Change product_type on a draft CPS | Form re-renders: CP fields show for Computer Paper, Label fields for Label, Carton fields for Carton |  |  |
| UT-2.05 | CPS Link | Verify customer field links to Customer master | Click customer dropdown | Shows Customer records. Search works |  |  |
| UT-2.06 | CPS Status | Set status to Inactive | Change status from Active to Inactive, save | Saves. Inactive specs should not appear in Job Card customer_product_spec filter (UT-4.02) |  |  |
| UT-2.07 | CPS List | Filter list by product_type | On CPS list, filter product_type=Carton | Only Carton specs shown |  |  |
| UT-2.08 | CPS Duplicate | Duplicate CPS to make variant | Open an existing CPS, click Menu → Duplicate, modify a field, save | New CPS created with new name; original unchanged |  |  |
| UT-2.09 | CPS Delete | Delete an unreferenced CPS | Create a throwaway CPS, click Delete | Deletes cleanly |  |  |
| UT-2.10 | CPS Delete Blocked | Delete a CPS referenced by a Job Card | Try to delete a CPS that's linked to a submitted Job Card | Frappe blocks with LinkExistsError |  |  |

---

## SECTION 3 — DIES & DIES ORDERS

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-3.01 | Dies Create | Create a new die | New Dies: die_number=<num>, die_size, length, width, shape, across_ups, round_ups, plate_code | Saves. All fields persist |  |  |
| UT-3.02 | Dies Unique | Duplicate die_number rejected | Try creating another die with the same die_number | Frappe rejects if die_number is set unique; otherwise records with same number coexist (record in Notes) |  |  |
| UT-3.03 | Dies Shape | Verify shape options | Open shape dropdown | Shape options visible (e.g., Rectangle, Round, Oval, Custom) |  |  |
| UT-3.04 | Dies UPS | Verify across_ups × round_ups | Create die with across_ups=4, round_ups=6 | Both fields save as integers |  |  |
| UT-3.05 | Dies Notes | Add multi-line notes | Enter multi-line text in notes field | Wraps and saves |  |  |
| UT-3.06 | Dies in Label CPS | Link a die from a Label CPS | On a Label CPS, pick a die from the dies link | Die selected and persisted |  |  |
| UT-3.07 | Dies Order Create | Create a Dies Order | New Dies Order: order_date=today, order_number=<num>, quantity=1, status=Ordered | Saves |  |  |
| UT-3.08 | Dies Order Status | Update status through lifecycle | Change status: Ordered → In Production → Delivered → Closed | Each save persists |  |  |
| UT-3.09 | Dies Order List | Filter by status | Filter Dies Order list by status=In Production | Only matching records shown |  |  |
| UT-3.10 | Dies Delete Blocked | Delete a die referenced by a Job Card | Try to delete a die linked to a submitted Job Card Label | Frappe blocks with LinkExistsError |  |  |

---

## SECTION 4 — JOB CARD COMPUTER PAPER

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-4.01 | JC-CP Create | Create a new Job Card Computer Paper | New JC-CP: customer, customer_product_spec=<CP spec>, quantity_ordered=10000, job_size, pay_slip_size, number_of_colours, number_of_parts=3 | Saves as Draft |  |  |
| UT-4.02 | JC-CP CPS Filter | CPS dropdown filters to Computer Paper specs | On JC-CP, click customer_product_spec dropdown | Only CPS with product_type=Computer Paper and status=Active shown |  |  |
| UT-4.03 | JC-CP Spec Fetch | Spec auto-populate | Pick a CPS on a fresh JC-CP | Defaults populate from spec (paper_type, gsm, pay_slip_size, etc. depending on mappings) |  |  |
| UT-4.04 | JC-CP Colour Of Parts | Add rows to colour_of_parts child table | Add 3 rows: part_number 1/2/3, paper_type, gsm, colour, purpose per row | All 3 rows saved; grid displays them |  |  |
| UT-4.05 | JC-CP Numbering | Enable numbering | Set numbering_required=checked, fill numbering_prefix, start, end, format | Saves. Fields show as required when numbering_required=1 |  |  |
| UT-4.06 | JC-CP Plate Status | Cycle plate_status | Change plate_status through states (e.g., To Order / Ordered / Received) | Each state saves |  |  |
| UT-4.07 | JC-CP Submit | Submit JC-CP | Click Submit on a completed JC-CP | docstatus=1. Fields lock |  |  |
| UT-4.08 | JC-CP Custom Fields | Verify production tracking fields appear | Open submitted JC-CP, scroll to Production Tracking section | Section visible; custom_production_status=Not Started (read-only); custom_current_stage=blank (read-only) |  |  |
| UT-4.09 | JC-CP Custom Fields | Confirm custom_production_status read-only | Click custom_production_status dropdown | Field is read-only; cannot be manually changed |  |  |
| UT-4.10 | JC-CP Amend | Amend a submitted JC-CP | Click Amend on a submitted JC-CP | New Draft created with amended_from pointing to original |  |  |
| UT-4.11 | JC-CP Cancel | Cancel a submitted JC-CP | Click Cancel on a submitted JC-CP | docstatus=2. Cannot reference in new Production Entries |  |  |
| UT-4.12 | JC-CP Print | Print/Preview standard print format | Open a submitted JC-CP, click Print | Print preview renders without errors |  |  |

---

## SECTION 5 — JOB CARD LABEL

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-5.01 | JC-L Create | Create a new Job Card Label | New JC-L: customer, customer_product_spec=<Label spec>, quantity_ordered=50000, job_size | Saves as Draft |  |  |
| UT-5.02 | JC-L CPS Filter | CPS dropdown filters to Label specs | On JC-L, click customer_product_spec dropdown | Only CPS with product_type=Label and status=Active shown |  |  |
| UT-5.03 | JC-L Spec Fetch | Spec auto-populate | Pick a Label CPS on a fresh JC-L | label_length, label_width, dies, material defaults populate |  |  |
| UT-5.04 | JC-L Dies | Link a die | Pick an existing Dies record via the dies link | Die selected. label_length/width may auto-populate from die |  |  |
| UT-5.05 | JC-L Plate | Set plate_status and plate_code | Change plate_status to 'Received', enter plate_code | Saves |  |  |
| UT-5.06 | JC-L Cylinder | Set cylinder_teeth | Enter cylinder_teeth (e.g., 96) | Saves as integer |  |  |
| UT-5.07 | JC-L Packing | Set packing_up and packing_pieces | Enter values | Saves |  |  |
| UT-5.08 | JC-L Submit | Submit JC-L | Click Submit | docstatus=1. Fields lock |  |  |
| UT-5.09 | JC-L Custom Fields | Verify production tracking fields | Open submitted JC-L | custom_production_status=Not Started (read-only); custom_current_stage=blank |  |  |
| UT-5.10 | JC-L Amend | Amend submitted JC-L | Click Amend | New Draft with amended_from |  |  |
| UT-5.11 | JC-L Cancel | Cancel submitted JC-L | Click Cancel | docstatus=2 |  |  |
| UT-5.12 | JC-L Print | Print/Preview standard print format | Open a submitted JC-L, click Print | Preview renders without errors |  |  |

---

## SECTION 6 — JOB CARD CARTON

Covers all 4 product_types (2-Flap RSC, 1-Flap RSC, Tray / FTD, Die Cut), the SFK flag, UPS table, board auto-calc, and the Carton Job Card print format with SVG visualisation.

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-6.01 | JC-C Create | Create a Job Card Carton (2-Flap RSC) | New JC-C: customer, customer_product_spec=<Carton spec>, quantity_ordered=1000, product_type=2 Flap RSC, ctn_length_mm=300, ctn_width_mm=200, ctn_height_mm=150, ply=3, flute_type=C | Saves as Draft |  |  |
| UT-6.02 | JC-C CPS Filter | CPS dropdown filters to Carton specs | Click customer_product_spec dropdown | Only CPS with product_type=Carton and status=Active |  |  |
| UT-6.03 | JC-C Spec Fetch | Spec auto-populate | Pick a Carton CPS | ply, board_type, flute_type, ctn dimensions auto-populate |  |  |
| UT-6.04 | JC-C Flap Calc | ctn_flap_mm auto-calculates | Leave ctn_flap_mm blank; W=200 | ctn_flap_mm = ceil((200+5)/2) = 103 (or equivalent formula) |  |  |
| UT-6.05 | JC-C Board Calc | Board width/length auto-calculate | With L=300, W=200, H=150, observe board_width_planned_mm / board_length_planned_mm | Values computed per blank size formula; read-only fields |  |  |
| UT-6.06 | JC-C Weight | Board weight auto-calculates | With gsm and board dims set | Weight populated (kg/100 sheets or equivalent) |  |  |
| UT-6.07 | JC-C UPS Table | Add a carton_ups_selection row | Add row: ups_across=2, ups_along=3, rotation=Board Width | Row saves; planned_board_width_mm / planned_board_length_mm computed |  |  |
| UT-6.08 | JC-C UPS Multiple | Add multiple UPS options | Add 2–3 rows with different across/along/rotation | Grid saves all rows; planner can compare |  |  |
| UT-6.09 | JC-C Joint Gluing | Set joint_type=Gluing | Change joint_type to Gluing, save | Saves. Print format will render glue dashes on tab (UT-6.23) |  |  |
| UT-6.10 | JC-C Joint Stitched | Set joint_type=Stitched | Change joint_type to Stitched | Saves. Print format will render stitch X's (UT-6.24) |  |  |
| UT-6.11 | JC-C Colours | Printing_or_plain=Printing with 4 colours | Set printing_or_plain=Printing, no_of_colours=4 | Saves. Colour details section becomes relevant |  |  |
| UT-6.12 | JC-C Plain | Printing_or_plain=Plain | Set printing_or_plain=Plain | Saves. no_of_colours should be 0 or hidden |  |  |
| UT-6.13 | JC-C Product Type 1-Flap RSC | Create a 1 Flap RSC carton | product_type=1 Flap RSC, full dims | Saves. Top flap absent in print (UT-6.25) |  |  |
| UT-6.14 | JC-C Product Type Tray | Create a Tray (FTD) | product_type=Tray (FTD), fill dims | Saves. Print format renders ear tabs + 5 walls (UT-6.26) |  |  |
| UT-6.15 | JC-C Product Type Die Cut | Create a Die Cut carton | product_type=Die Cut | Saves. Die Cut cartons may use Dies reference for shape |  |  |
| UT-6.16 | JC-C SFK Flag | Toggle custom_is_sfk on | Check custom_is_sfk, save | Saves. ctn_height_mm may hide or become optional; flow limited to Corrugating at schedule time |  |  |
| UT-6.17 | JC-C SFK Print | SFK print format behaviour | Open print preview for an SFK carton | No die-cut SVG rendered (SFK returns empty) |  |  |
| UT-6.18 | JC-C Submit | Submit a Carton job card | Click Submit on a complete JC-C | docstatus=1 |  |  |
| UT-6.19 | JC-C Custom Fields | Verify production tracking fields | Open submitted JC-C | custom_production_status=Not Started; custom_current_stage=blank; both read-only |  |  |
| UT-6.20 | JC-C Custom Fields | Verify custom_is_sfk visible | Scroll after quantity_ordered | Checkbox "Is SFK (Single-Face Kraft)" visible |  |  |
| UT-6.21 | JC-C Print Page 1 | Print Page 1 renders commercial + specs + board plan | Open Print Preview, select Carton Job Card format, navigate to page 1 | Shows customer commercial terms, carton specs, planned board dims, SVG die-cut layout |  |  |
| UT-6.22 | JC-C Print SVG 2-Flap | SVG for 2-Flap RSC | Print preview for UT-6.01 record | SVG shows tab + L-W-L-W panels + top AND bottom flaps, fold/cut/glue markers |  |  |
| UT-6.23 | JC-C Print SVG Glue | Glue tab rendering | Print preview for UT-6.09 record (Gluing) | Glue dashes (3 rows) rendered on tab |  |  |
| UT-6.24 | JC-C Print SVG Stitch | Stitch tab rendering | Print preview for UT-6.10 record (Stitched) | Stitch X's (25mm spacing) on tab |  |  |
| UT-6.25 | JC-C Print SVG 1-Flap | 1-Flap RSC SVG | Print preview for UT-6.13 record | SVG shows bottom flaps only, no top flap |  |  |
| UT-6.26 | JC-C Print SVG Tray | Tray SVG | Print preview for UT-6.14 record | SVG shows ear tabs + base + 4 side walls |  |  |
| UT-6.27 | JC-C Print Page 2 | Print Page 2 renders reel/sheeting/reconciliation/dispatch | Navigate to page 2 | Reel tracking, sheeting output, material reconciliation, dispatch tally tables visible |  |  |
| UT-6.28 | JC-C Print Page 3 | Print Page 3 renders 5-day QC checklist | Navigate to page 3 | 5-day QC checklist table visible |  |  |
| UT-6.29 | JC-C Amend | Amend submitted JC-C | Click Amend | New Draft with amended_from |  |  |
| UT-6.30 | JC-C Cancel | Cancel submitted JC-C | Click Cancel | docstatus=2 |  |  |

---

## SECTION 7 — DAILY PRODUCTION SCHEDULE

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-7.01 | DPS Create | Create a DPS | New DPS: workstation=<any>, schedule_date=today | Saved as Draft with naming DPS-YYYY-##### |  |  |
| UT-7.02 | DPS Fetch | Verify workstation_type auto-fetch | After picking workstation | workstation_type populates; read-only |  |  |
| UT-7.03 | DPS Fetch | Verify product_line auto-fetch | After picking workstation | product_line populates from Workstation.custom_product_line; read-only |  |  |
| UT-7.04 | DPS Unique | Duplicate DPS for same machine+date rejected | Create two DPS for same workstation on same date | Second save fails with clear duplicate error |  |  |
| UT-7.05 | DPS Unique | Different machines same date allowed | Create DPS for two different workstations on same date | Both save |  |  |
| UT-7.06 | Schedule Line | Add a Schedule Line | Add row: job_card_type=Job Card Label, job_card_id=<submitted>, production_stage=Printing, planned_qty=5000, sequence_order=10 | Row saves. customer auto-fetched from job card. status=Pending |  |  |
| UT-7.07 | Schedule Line | Add multiple Schedule Lines | Add 3 rows with sequence_order 10, 20, 30 | All three visible, ordered by sequence_order |  |  |
| UT-7.08 | Schedule Line | estimated_hours auto-calculation | Line with planned_qty=1000 on a workstation where custom_max_speed_per_hour=500 | estimated_hours ≈ 2.0 (plus setup time if applicable) after save |  |  |
| UT-7.09 | Schedule Line | Fallback via Workstation Stage hourly_rate | Line where Workstation Stage for that stage + workstation has hourly_rate=250 (and workstation max_speed=500) | estimated_hours uses 250 (Stage wins over Workstation) |  |  |
| UT-7.10 | Schedule Line | Soft-warning when rate missing | Workstation with no custom_max_speed_per_hour and no matching Workstation Stage; add a line, save | DPS saves; orange banner "Missing Workstation Speed" lists affected lines; estimated_hours stays 0 |  |  |
| UT-7.11 | Schedule Line | Manual override of estimated_hours | Type 3.5 into estimated_hours, save | Manual value persists; not overwritten by auto-calc (honours UT-2.09 intent) |  |  |
| UT-7.12 | Schedule Line | Change status Pending → In Progress | On a draft DPS, change a line status via the child table | Saves |  |  |
| UT-7.13 | Schedule Line | Dynamic Link shows only 3 job card types | Click job_card_type dropdown | Shows Job Card Computer Paper, Job Card Label, Job Card Carton |  |  |
| UT-7.14 | Schedule Line | Job card filter by type | Set job_card_type=Job Card Label; click job_card_id | Only Label job cards shown |  |  |
| UT-7.15 | DPS Totals | total_planned_qty | 3 lines: 5000+3000+2000 | total_planned_qty = 10000 |  |  |
| UT-7.16 | DPS Totals | total_planned_hours | 3 lines with estimated_hours 2.0+1.5+1.0 | total_planned_hours = 4.5 |  |  |
| UT-7.17 | DPS Totals | utilization_pct | total_planned_hours=6.5, available_hours=8 | utilization_pct = 81.25% |  |  |
| UT-7.18 | DPS Totals | Over-utilisation shown | Lines totalling 10 h on 8-h day | utilization_pct = 125%; displayed in red |  |  |
| UT-7.19 | DPS Submit | Submit DPS | Click Submit on a DPS with at least one line | docstatus=1; lines locked |  |  |
| UT-7.20 | DPS Amend | Amend submitted DPS | Click Amend | New Draft with amended_from |  |  |
| UT-7.21 | DPS Cancel | Cancel submitted DPS | Click Cancel | docstatus=2 |  |  |

---

## SECTION 8 — DAILY SCHEDULE BOARD

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-8.01 | Board Load | Navigate to Schedule Board | /app/daily-schedule-board | Board loads. Columns = active Workstations; today's date shown |  |  |
| UT-8.02 | Board Nav | Navigate to a different date | Click ▶ next / ◀ prev / pick a date | Board reloads showing DPS data for that date. Missing DPS auto-created as Draft per machine |  |  |
| UT-8.03 | Board Cards | Job cards render correctly | Look at a machine column with schedule lines | Card shows: job_card_id, customer, stage, planned_qty, estimated_hours, status badge |  |  |
| UT-8.04 | Board Reorder | Drag a card up/down within a column | Drag the 2nd card above the 1st | Cards reorder. Underlying sequence_order values updated on save |  |  |
| UT-8.05 | Board Move | Drag a card to a different machine | Drag a line from Machine A column to Machine B | Schedule Line removed from source DPS, added to target DPS |  |  |
| UT-8.06 | Board Move Validation | Cross-product-line drag rejected | Drag a Label card to a Computer Paper-only machine | Drop rejected with validation; card snaps back |  |  |
| UT-8.07 | Board Add | Add job via + Add Job | Click + Add Job, pick a submitted job card, choose target machine | New Schedule Line appended to target DPS; card appears |  |  |
| UT-8.08 | Board Status | Toggle status via card | Click status badge; cycle Pending → In Progress → Done | Status updates on card and on Schedule Line |  |  |
| UT-8.09 | Board Utilization | Utilization bar | Header of a column with 6 h planned on 8 h available | Bar shows 75%. Text shows 6.0h / 8.0h |  |  |
| UT-8.10 | Board Filter | Filter by product line | Select product_line=Label from filter | Only Label + All machines shown |  |  |
| UT-8.11 | Board Filter | Filter by workstation type | Select workstation_type filter (if available) | Only matching machines shown |  |  |
| UT-8.12 | Board Search | Search by customer name | Type a customer substring | Only cards for that customer visible |  |  |
| UT-8.13 | Board Read-only | Board respects submitted DPS | Open board on a date whose DPS is submitted | Cards shown as locked; drag disabled on submitted lines |  |  |

---

## SECTION 9 — PRODUCTION ENTRY

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-9.01 | PE Create | Create a Production Entry | New PE: job_card_type=Job Card Label, job_card_id=<submitted>, production_stage=Printing, workstation=<any>, start_time=08:00, end_time=10:00, qty_produced=3000, shift=Day | Saved as Draft. naming PE-YYYY-#####. duration_hours=2.0 auto-calc. waste_pct=0% |  |  |
| UT-9.02 | PE Create | Customer auto-fetch | Pick a job card; check customer field | Customer auto-fetched from the job card (handles both customer and customer_name per type) |  |  |
| UT-9.03 | PE Create | DPS auto-link | Create PE for a workstation+date that has a DPS | daily_production_schedule auto-populated |  |  |
| UT-9.04 | PE Waste | Record waste with reason | qty_produced=4500, qty_waste=500, waste_reason=Setup Waste | waste_pct = 10% auto-calc. Saves |  |  |
| UT-9.05 | PE Waste | Disabled waste reasons hidden | Check waste_reason dropdown | Does NOT list reasons where enabled=0 (UT-1.20) |  |  |
| UT-9.06 | PE Waste | Waste without reason rejected | qty_waste=200, waste_reason blank, try to save | Validation: Waste Reason is required when qty_waste > 0 |  |  |
| UT-9.07 | PE Submit | Submit PE | Click Submit | docstatus=1. Fields lock. on_submit fires update_job_card_progress() |  |  |
| UT-9.08 | PE Rollup First | First PE updates job card to In Progress | Submit PE against a job card whose custom_production_status=Not Started; re-open that job card | custom_production_status → In Progress; custom_current_stage = the PE's production_stage |  |  |
| UT-9.09 | PE Rollup Accumulate | Multiple PEs accumulate | Submit 3 PEs for same job card: 3000+2000+1500 = 6500; quantity_ordered=5000 | Job card shows qty_produced totals. If total ≥ ordered, custom_production_status=Completed |  |  |
| UT-9.10 | PE Rollup Cancel | PE cancel reverses rollup | Cancel one of the PEs from UT-9.09 | Job card totals recalculated; custom_production_status may revert to In Progress |  |  |
| UT-9.11 | PE Schedule Line | PE submit updates Schedule Line status | Submit PE whose fields match a Pending Schedule Line on a submitted DPS | Schedule Line status → In Progress (or Done if qty met) |  |  |
| UT-9.12 | PE Time | duration_hours calc | start_time=06:00, end_time=14:30 | duration_hours = 8.5 |  |  |
| UT-9.13 | PE Shift | Shift auto-detect / manual | start_time=22:00 | shift auto-sets Night (if logic present) or is manually selectable |  |  |
| UT-9.14 | PE Carton | PE for a Carton job card | job_card_type=Job Card Carton, job_card_id=<submitted Carton>, submit | customer fetched from customer_name on Carton (regression guard for UT-2.57 fix) |  |  |

---

## SECTION 10 — DOWNTIME ENTRY

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-10.01 | DT Create | Create a Downtime Entry | New DT: workstation=<any>, downtime_reason=Mechanical Breakdown, start_time=10:00 | Saved as Draft. end_time and duration_minutes blank |  |  |
| UT-10.02 | DT Close | Close a downtime entry | Set end_time=10:45, save | duration_minutes = 45 auto-calc. is_planned=0 auto-fetched from Mechanical Breakdown |  |  |
| UT-10.03 | DT Planned Fetch | Planned downtime auto-flag | New DT with downtime_reason=Planned Maintenance, save | is_planned = checked (fetched from Downtime Reason) |  |  |
| UT-10.04 | DT DPS Link | Downtime auto-links to DPS | Create DT for a machine+date that has a DPS | daily_production_schedule auto-populated |  |  |
| UT-10.05 | DT Operator | Operator field | Enter operator name or link | Saves |  |  |
| UT-10.06 | DT Validation | Submit open downtime rejected | Try to Submit a DT with end_time blank | Validation: End Time is required before submitting |  |  |
| UT-10.07 | DT Validation | End before Start rejected | start_time=14:00, end_time=13:00, save | Validation: End Time must be after Start Time |  |  |
| UT-10.08 | DT Submit | Submit a closed downtime | Click Submit on a DT with end_time set | docstatus=1 |  |  |
| UT-10.09 | DT Cancel | Cancel a submitted DT | Click Cancel | docstatus=2 |  |  |
| UT-10.10 | DT List | Filter by is_planned | Filter list: is_planned=1 | Only planned entries shown |  |  |
| UT-10.11 | DT List | Filter by workstation | Filter list: workstation=<any> | Only entries for that machine |  |  |

---

## SECTION 11 — DASHBOARD CONNECTIONS & REPORTS

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-11.01 | Dashboard | Job card sidebar shows Production Entries | Open a Job Card with submitted PEs | Connections section shows Production Entry count with link |  |  |
| UT-11.02 | Dashboard | Job card sidebar shows DPS links | Open a job card referenced by a Schedule Line | Connections section shows Daily Production Schedule count |  |  |
| UT-11.03 | Dashboard | Click connection → filtered list | Click Production Entry count from sidebar | Navigates to Production Entry list filtered by that job card |  |  |
| UT-11.04 | Report — DPS | Daily Production Summary runs | Navigate to Daily Production Summary; from_date=today, to_date=today | Report renders. Columns: posting_date, workstation, job_card_id, customer, production_stage, actual_qty, waste_qty, waste_pct, variance, duration_hours |  |  |
| UT-11.05 | Report — DPS | Filter by workstation | Apply workstation filter | Only rows for that workstation |  |  |
| UT-11.06 | Report — DPS | waste_pct correct | Row with actual=4500, waste=500 | waste_pct = 10% |  |  |
| UT-11.07 | Report — DPS | variance correct | Row with planned=5000, actual=4500 | variance = -500 |  |  |
| UT-11.08 | Report — JP | Job Progress runs across all 3 types | Navigate to Job Progress; no filter | Report renders rows across Computer Paper, Label, Carton with no SQL error (regression guard for UT-2.57) |  |  |
| UT-11.09 | Report — JP | Customer column populated for Carton | Look at Carton rows in the report | Customer value shown (from customer_name on Carton) |  |  |
| UT-11.10 | Report — JP | Filter by customer | Apply customer filter | Only rows for that customer, including Carton entries |  |  |
| UT-11.11 | Report — JP | Status colours | Check a job overdue (due_date < today, progress < 100) | Status shows Overdue (red) |  |  |
| UT-11.12 | Report — JP | Status At Risk | Check a job with progress_pct<50 and days_remaining<3 | Status shows At Risk (amber) |  |  |
| UT-11.13 | Report — JP | Status Completed | Job whose qty_produced ≥ quantity_ordered | Status shows Completed |  |  |
| UT-11.14 | Report — JP | Status On Track | Job with neither Overdue nor At Risk triggers | Status shows On Track |  |  |
| UT-11.15 | Report — MU | Machine Utilization runs | Navigate to Machine Utilization; set date range | Renders. Columns: workstation, workstation_type, available_hours, run_hours, downtime_unplanned, downtime_planned, idle_hours, utilization_pct |  |  |
| UT-11.16 | Report — MU | Planned vs unplanned split | Machine with 1 Planned Maintenance DT and 1 Mechanical Breakdown DT | downtime_planned and downtime_unplanned columns each populated correctly |  |  |
| UT-11.17 | Report — MU | utilization_pct formula | Machine with run_hours=6, available_hours=8 | utilization_pct = 75% |  |  |
| UT-11.18 | Report Export | Export any report to CSV/Excel | Click Menu → Export on each of the 3 reports | Spreadsheet downloads; formatted correctly |  |  |
| UT-11.19 | Workspace | VCL Production workspace loads | Navigate to the VCL Production workspace | Workspace renders shortcuts for CPS, Dies, Job Card New/List for all 3 types |  |  |
| UT-11.20 | Report — JP | Regression: handles string-encoded quantity_ordered | Run Job Progress on a site where quantity_ordered is returned from DB as string | No TypeError; qty_remaining and progress_pct render numerically (regression guard for flt() coercion fix) |  |  |

---

## SECTION 12 — PERMISSIONS

Run each row after logging in with the specified role (typically a separate browser profile or incognito session).

| ID | Role | Test Case | Steps | Expected Result | Result | Notes |
|----|------|-----------|-------|-----------------|--------|-------|
| UT-12.01 | Mfg Manager | Full CRUD on master data | Create/read/update/delete a Production Stage, Waste Reason, Downtime Reason | All 4 operations succeed on all 3 doctypes |  |  |
| UT-12.02 | Mfg Manager | Full CRUD on DPS | Create, edit, submit, amend, cancel a DPS | All operations succeed |  |  |
| UT-12.03 | Mfg Manager | Full CRUD on PE | Create, submit, cancel a Production Entry | All succeed |  |  |
| UT-12.04 | Mfg Manager | Full CRUD on Downtime | Create, submit, cancel a Downtime Entry | All succeed |  |  |
| UT-12.05 | Mfg User | Create + submit DPS | Create DPS, add lines, submit | Create + submit work; Delete button hidden |  |  |
| UT-12.06 | Mfg User | Read-only master data | Try to create a Production Stage | Create blocked; list still readable |  |  |
| UT-12.07 | Mfg User | Create + submit PE and DT | Create a Production Entry and a Downtime Entry | Both succeed |  |  |
| UT-12.08 | Prod Log User | Read-only on DPS | Try to create a DPS | Blocked; New button hidden or action denied |  |  |
| UT-12.09 | Prod Log User | Create + submit PE | Create a Production Entry | Succeeds (operators need this) |  |  |
| UT-12.10 | Prod Log User | Create + submit DT | Create a Downtime Entry | Succeeds |  |  |
| UT-12.11 | Prod Log User | Read-only on master data | Try to create a Waste Reason | Blocked |  |  |
| UT-12.12 | Prod Log User | Schedule Board read-only | Open /app/daily-schedule-board | Board loads; drag disabled; status badges not clickable |  |  |
| UT-12.13 | Sales User | Create + submit + cancel Job Card Carton | New JC-C, fill, submit, then cancel | All three actions succeed; Delete hidden |  |  |
| UT-12.14 | Sales User | Create CPS | New Customer Product Specification | Succeeds (if role configured); otherwise blocked — record which |  |  |
| UT-12.15 | Sales User | No access to PE/DPS/DT | Navigate to Production Entry list | Permission denied or empty list per permission rules |  |  |
| UT-12.16 | System Manager | Full CRUD everything | Open any doctype, test all actions | All operations succeed |  |  |
| UT-12.17 | Guest | No access | Log out; try /api/resource/Production Stage | 403 Forbidden |  |  |

---

## OUTCOME & SIGN-OFF

**Overall Outcome:** ______________

| | | | |
|---|---|---|---|
| **Tester:** | __________ | **Date:** | __________ |
| **Role:** | __________ | **Outcome:** | __________ |
| **Signature:** | ___________________ | **Approved by:** | ___________________ |
