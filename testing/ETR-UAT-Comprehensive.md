# VCL PRODUCTION — ETR (REEL-TO-REEL PRINTING) UAT

**Custom App: production_log | Modules: Job Card Tracking**

**Scope:** Customer Product Specification extension for ETR product type, new `Job Card ETR` doctype (with child tables `ETR Plate Detail` and `ETR Print Reel Output`), and status-field standardization across existing Job Cards (Computer Paper / Label / Carton).

Test Date: __________ | Tester: __________ | Site: vimitconverters.frappe.cloud

---

## EXECUTIVE SUMMARY

| Suite | Total | Pass | Fail | Skip | Rate (excl skip) |
|-------|-------|------|------|------|-------------------|
| Section 1 — CPS ETR extension | 18 | __ | __ | __ | __% |
| Section 2 — Job Card ETR creation & spec link | 14 | __ | __ | __ | __% |
| Section 3 — Job Card ETR printing workflow | 16 | __ | __ | __ | __% |
| Section 4 — Job Card ETR slitting workflow | 12 | __ | __ | __ | __% |
| Section 5 — Job Card ETR submission & status | 10 | __ | __ | __ | __% |
| Section 6 — Status standardization regression (Carton/Label/CP) | 15 | __ | __ | __ | __% |
| Section 7 — Permissions (Job Card ETR roles) | 8 | __ | __ | __ | __% |

---

## CRITICAL DEFECTS FOUND

| Test ID | Severity | Issue | Impact / Action |
|---------|----------|-------|-----------------|
|  |  |  |  |

---

## SECTION 1 — CPS ETR EXTENSION

Verifies that the existing Customer Product Specification doctype correctly handles the new `ETR (Reel to Reel Printing)` product type, the new `ETR-SPEC-.#####` naming series, the ETR-specific field section, extended shared print-colour / spot-colour sections, and the new Water Based / Solvent Based ink types.

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-1.01 | Enum | ETR option present in Product Type dropdown | New CPS → open Product Type Select | `ETR (Reel to Reel Printing)` listed after Exercise Books |  |  |
| UT-1.02 | Enum | ETR naming series auto-selected | Set Product Type = ETR | `naming_series` auto-sets to `ETR-SPEC-.#####` |  |  |
| UT-1.03 | Enum | ETR ink default auto-applied | Set Product Type = ETR with blank Ink Type | Ink Type auto-sets to `Water Based` |  |  |
| UT-1.04 | Enum | Existing ink types still present | Set Product Type = CP / Carton / Label | Ink Type dropdown still shows `Process Offset` / `Process UV` |  |  |
| UT-1.05 | Enum | New ink types available | Open Ink Type dropdown on ETR spec | `Water Based` and `Solvent Based` both selectable |  |  |
| UT-1.06 | UI | ETR section appears only for ETR | Set Product Type = ETR | ETR / Reel to Reel Printing Specification section visible; Computer Paper / Carton / Label / Exercise Books sections hidden |  |  |
| UT-1.07 | UI | Print Colours shared with ETR | Set Product Type = ETR | Print Colours section visible; CMYK checkboxes + Number of Colours + Full CMYK button shown |  |  |
| UT-1.08 | UI | Spot Colours shared with ETR | Set Product Type = ETR | Spot Colours section visible; spot_colours table editable |  |  |
| UT-1.09 | UI | Substrate Other conditional | Substrate = `Other` on ETR | `Substrate (Other)` Data field appears |  |  |
| UT-1.10 | UI | Substrate Other hidden otherwise | Substrate = `Thermal Paper` | `Substrate (Other)` hidden |  |  |
| UT-1.11 | UI | Roll dimensions shown for ETR Plain Rolls | Output Type = `ETR Plain Rolls` | `Finished Width` + `Finished Diameter` visible; `Finished Reel Length` hidden |  |  |
| UT-1.12 | UI | Roll dimensions shown for ETR Printed Rolls | Output Type = `ETR Printed Rolls` | `Finished Width` + `Finished Diameter` visible; `Finished Reel Length` hidden; ETR Print Detail section visible |  |  |
| UT-1.13 | UI | Reel length shown for Printed Reel | Output Type = `Printed Reel` | `Finished Reel Length` visible; Width + Diameter hidden; ETR Print Detail section visible |  |  |
| UT-1.14 | UI | Print Detail hidden for Plain Rolls | Output Type = `ETR Plain Rolls` | ETR Print Detail section + Print Type hidden |  |  |
| UT-1.15 | Validation | Substrate required | Save ETR spec without Substrate | Throw: "Substrate is required for ETR (Reel to Reel Printing)." |  |  |
| UT-1.16 | Validation | Jumbo width > 0 | Save ETR spec with Jumbo Width = 0 | Throw: "Jumbo Roll Width (mm) must be greater than 0 for ETR." |  |  |
| UT-1.17 | Validation | Output Type dimensions enforced | Output Type = `ETR Plain Rolls`, Finished Width blank, save | Throw: "Finished Width (mm) must be greater than 0 for roll output." |  |  |
| UT-1.18 | Naming | Submit produces ETR-SPEC- name | Save a complete ETR spec | `name` is `ETR-SPEC-00001` (or next in series) |  |  |

---

## SECTION 2 — JOB CARD ETR CREATION & SPEC LINK

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-2.01 | Availability | New Job Card ETR form opens | Navigate to Job Card ETR → New | Form renders; naming series defaults to `JC-ETR-.YYYY.-.#####`; Job Date defaults to today |  |  |
| UT-2.02 | Link filter | Spec picker filters by customer | Set Customer → click Customer Product Specification picker | Only CPS rows where product_type=ETR AND customer matches AND status=Active appear |  |  |
| UT-2.03 | Link filter | Non-ETR specs excluded | Create a Carton spec for same customer; open ETR spec picker | Carton spec NOT shown |  |  |
| UT-2.04 | Link filter | Inactive specs excluded | Set spec status = Inactive; open picker | That spec NOT shown |  |  |
| UT-2.05 | Link filter | No customer → empty picker | Clear Customer; open spec picker | Returns zero results |  |  |
| UT-2.06 | Snapshot | Field copy on spec select | Select an ETR spec | Substrate, GSM, Core ID, Jumbo Width, Output Type, Finished Width/Diameter/Reel Length, Print Type, Ink Type, CMYK checkboxes, Number of Colours, Colour Notes all populated from spec |  |  |
| UT-2.07 | Snapshot | Spot colours deep-copied | Spec has 2 spot colour rows; select spec | Job Card ETR `spot_colours` table has 2 rows with identical Pantone/hex/CMYK values |  |  |
| UT-2.08 | Snapshot | Operation flags auto-set for Plain Rolls | Spec Output Type = `ETR Plain Rolls`; select spec | Printing Required = 0; Slitting Required = 1 |  |  |
| UT-2.09 | Snapshot | Operation flags auto-set for Printed Rolls | Spec Output Type = `ETR Printed Rolls`; select spec | Printing Required = 1; Slitting Required = 1 |  |  |
| UT-2.10 | Snapshot | Operation flags auto-set for Printed Reel | Spec Output Type = `Printed Reel`; select spec | Printing Required = 1; Slitting Required = 0 |  |  |
| UT-2.11 | Snapshot | Customer change clears spec | Select spec, then change Customer | `customer_product_spec` blanked; snapshot fields cleared; spot_colours emptied |  |  |
| UT-2.12 | Validation | Spec customer mismatch | Manually set spec from another customer (via dev tools) | Throw: "does not belong to customer <X>" |  |  |
| UT-2.13 | Validation | Wrong product_type rejected | Manually link a non-ETR spec | Throw: "is not an ETR (Reel to Reel Printing) specification" |  |  |
| UT-2.14 | Validation | Inactive spec rejected | Link a spec whose status=Inactive | Throw: "is not Active (current status: Inactive)" |  |  |

---

## SECTION 3 — JOB CARD ETR PRINTING WORKFLOW

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-3.01 | UI | Printing section hidden when unchecked | Printing Required = 0 | Print Colours, Printing, Plate Details, Print Output Reels sections hidden |  |  |
| UT-3.02 | UI | Printing section visible when checked | Printing Required = 1 | Print Colours, Printing, Plate Details, Print Output Reels sections visible |  |  |
| UT-3.03 | Plates | Plate row requires Colour # | Add a Plate Detail row, leave Colour # blank, save | Row-level required validation triggers |  |  |
| UT-3.04 | Plates | Plate row requires Plate Code | Leave Plate Code blank, save | Row-level required validation triggers |  |  |
| UT-3.05 | Plates | Plate row requires Condition Before | Leave Condition Before blank, save | Row-level required validation triggers |  |  |
| UT-3.06 | Plates | Condition After optional | Leave Condition After blank, save | Save succeeds |  |  |
| UT-3.07 | Plates | Max 4 colours per Select | Open Colour # dropdown | Options: 1, 2, 3, 4 |  |  |
| UT-3.08 | Colour count | CMYK tick updates count | Tick `uses_c`, `uses_m` | `number_of_colours` = 2 |  |  |
| UT-3.09 | Colour count | Spot row bumps count | Add 1 spot colour row on top of 2 CMYK | `number_of_colours` = 3 |  |  |
| UT-3.10 | Colour count | Printing unchecked zeroes count | Tick 2 CMYK, then Printing Required = 0 | `number_of_colours` = 0 |  |  |
| UT-3.11 | Output reels | Metres_printed updates totals | Enter metres_printed = 500 on row 1 | `print_total_metres_out` = 500; `print_total_reels_out` = 1 |  |  |
| UT-3.12 | Output reels | Second row sums | Add row 2 with metres_printed = 700 | `print_total_metres_out` = 1200; `print_total_reels_out` = 2 |  |  |
| UT-3.13 | Output reels | Row removal updates | Delete row 1 | `print_total_metres_out` = 700; `print_total_reels_out` = 1 |  |  |
| UT-3.14 | Validation | Plate Details required when printing | Printing Required = 1, empty plate_details, save | Throw: "Printing section: At least one row in Plate Details is required." |  |  |
| UT-3.15 | Output type | Plain Rolls + only Printing rejected | Output Type = ETR Plain Rolls; Printing = 1; Slitting = 0 | Throw: "Plain rolls require Slitting" |  |  |
| UT-3.16 | Print detail | Print Type selectable | With printing on, open Print Type dropdown | Options: Back Print, Front Print, Front and Back |  |  |

---

## SECTION 4 — JOB CARD ETR SLITTING WORKFLOW

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-4.01 | UI | Slitting section hidden when unchecked | Slitting Required = 0 | Slitting section + Slitting Output section hidden |  |  |
| UT-4.02 | UI | Slitting section visible when checked | Slitting Required = 1 | Slitting + Slitting Output sections visible |  |  |
| UT-4.03 | Input source | Jumbo Roll source hides reel ID | Slit Input Source = Jumbo Roll (direct) | `slit_input_reel_id` hidden |  |  |
| UT-4.04 | Input source | Printed Reel source shows reel ID | Slit Input Source = Printed Reel (from print section) | `slit_input_reel_id` visible |  |  |
| UT-4.05 | Validation | Output Width required | Slitting=1, Output Width blank, save | Throw: "Output Width (mm) must be greater than 0." |  |  |
| UT-4.06 | Validation | Output Diameter required | Slitting=1, Output Diameter blank, save | Throw: "Output Diameter (mm) must be greater than 0." |  |  |
| UT-4.07 | Output type | Printed Reel + only Slitting rejected | Output Type = Printed Reel; Slitting=1; Printing=0 | Throw: "A Printed Reel requires Printing" |  |  |
| UT-4.08 | Fields | Cartons packed editable | Enter Cartons Packed = 5, Rolls per Carton = 20 | Values persist on save |  |  |
| UT-4.09 | Fields | Waste fields editable | Enter Slit Waste (metres) + Slit Waste (kg) | Values persist on save |  |  |
| UT-4.10 | Signoff | Operator + Supervisor + Time editable | Enter all three signoff fields | Values persist on save |  |  |
| UT-4.11 | Combined | Printed Rolls runs both sections | Output Type = ETR Printed Rolls; Printing=1; Slitting=1 | Both Printing and Slitting sections visible + save-able |  |  |
| UT-4.12 | Allow-on-submit | Slit totals editable after submit | Submit a card; edit Total Weight Out | Edit persists (allow_on_submit=1) |  |  |

---

## SECTION 5 — JOB CARD ETR SUBMISSION & STATUS LIFECYCLE

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-5.01 | Validation | No operation selected rejected | Printing=0, Slitting=0, save | Throw: "At least one operation must be selected" |  |  |
| UT-5.02 | Status | Draft on new record | Save new record (docstatus=0) | Status = Draft |  |  |
| UT-5.03 | Status | In Progress on submit | Save, then Submit | Status = In Progress |  |  |
| UT-5.04 | Status | Completed preserves on re-save | After submit, status set to Completed manually (via server script or admin), then trigger validate | Status stays Completed (not reverted to In Progress) |  |  |
| UT-5.05 | Status | Cancelled on cancel | Submit, then Cancel | Status = Cancelled |  |  |
| UT-5.06 | Naming | First submitted name | Submit first ever Job Card ETR | `name` is `JC-ETR-YYYY-00001` |  |  |
| UT-5.07 | Amended from | Amended doc links back | Cancel a submitted card, amend | `amended_from` points to the original name |  |  |
| UT-5.08 | Allow-on-submit | Status editable post-submit | Submit, then try to set status = Completed via backend | Frappe allows (allow_on_submit=1) |  |  |
| UT-5.09 | Print | Print menu accessible | Open a submitted card, click Print | Print dialog opens (no default format yet — ETR Job Traveller deferred) |  |  |
| UT-5.10 | Submit | Final Remarks editable after submit | Edit Final Remarks on submitted card | Value persists (allow_on_submit=1) |  |  |

---

## SECTION 6 — STATUS STANDARDIZATION REGRESSION (CARTON / LABEL / CP)

Verifies the changes to existing Job Cards don't break historical records.

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-6.01 | Label data | Existing Submitted → In Progress | Check Job Card Label rows that were `status='Submitted'` pre-patch | After migrate: rows show `status='In Progress'` |  |  |
| UT-6.02 | Label options | New options available | Open a Label job card, view Status field | Dropdown lists Draft / In Progress / Completed / Submitted / Cancelled (Submitted retained for backward compatibility) |  |  |
| UT-6.03 | Label submit | New Label submit → In Progress | Create new Label job card, submit | Status = In Progress (not Submitted) |  |  |
| UT-6.04 | Label amend | Amend path preserved | Cancel, amend a Label job card | New amended doc opens as Draft |  |  |
| UT-6.05 | Label validation | Plate / spec validations still work | Submit a Label card with an Old plate_status but no plate_code | Existing validation still throws |  |  |
| UT-6.06 | Carton data | Existing Carton docs now have status | Check any pre-existing Carton job card | status is backfilled: Draft if docstatus=0, In Progress if docstatus=1, Cancelled if docstatus=2 |  |  |
| UT-6.07 | Carton options | New Status dropdown | New Carton job card, view Status | Draft / In Progress / Completed / Cancelled |  |  |
| UT-6.08 | Carton submit | Submit sets In Progress | Submit a new Carton | status = In Progress |  |  |
| UT-6.09 | Carton calc | Calc pipeline still runs | Change ply / dimensions on a Carton | board_width_planned_mm + board_length_planned_mm + approximate_weight_grams still update |  |  |
| UT-6.10 | Carton SVG | Board visualization renders | Open a Carton with valid dimensions | SVG renders (product_type-specific) |  |  |
| UT-6.11 | CP data | Existing CP docs now have status | Check any pre-existing CP job card | status backfilled per docstatus |  |  |
| UT-6.12 | CP options | New Status dropdown | New CP job card, view Status | Draft / In Progress / Completed / Cancelled |  |  |
| UT-6.13 | CP submit | Submit sets In Progress | Submit a new CP job card | status = In Progress |  |  |
| UT-6.14 | CPS picker | CPS link still filters by customer + type | Open Label / Carton / CP job card, click spec picker | Only specs of the matching product_type AND Active for the customer appear |  |  |
| UT-6.15 | CPS picker | ETR specs excluded from existing Job Cards | Create an ETR spec for customer X; open Label job card for customer X; open spec picker | ETR spec NOT listed |  |  |

---

## SECTION 7 — PERMISSIONS (JOB CARD ETR ROLES)

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| UT-7.01 | System Manager | Full CRUD + submit + cancel + amend | Log in as System Manager | Can create, read, write, delete, submit, cancel, amend Job Card ETR |  |  |
| UT-7.02 | Manufacturing Manager | Write + submit + amend, no delete or cancel | Log in as Manufacturing Manager | Can create/read/write/submit/amend; Delete + Cancel buttons not shown |  |  |
| UT-7.03 | Manufacturing User | Create + write + submit only | Log in as Manufacturing User | Can create/read/write/submit; no delete / cancel / amend |  |  |
| UT-7.04 | Denied role | Sales User has no access | Log in as Sales User | Job Card ETR list not accessible / "Not Permitted" on direct URL |  |  |
| UT-7.05 | Reports | Permission-filtered list view | Log in as each role, open Job Card ETR list | Only records the role can read appear |  |  |
| UT-7.06 | Field-level | Status read-only in UI | Any role, inspect Status field | Field is read-only; only allow_on_submit changes permitted programmatically |  |  |
| UT-7.07 | Allow on submit | Signoff fields editable after submit | Manufacturing User, submit a card, edit `final_operator` | Save succeeds (allow_on_submit=1) |  |  |
| UT-7.08 | Audit | Track Changes enabled | Edit a submitted card, then open activity log | Change entries recorded (track_changes=1) |  |  |

---

## TEST ENVIRONMENT CHECKLIST

Before starting, verify:

- [ ] `bench --site vimitconverters.frappe.cloud migrate` ran successfully against this branch
- [ ] `Customer Product Specification` doctype shows the new Product Type option
- [ ] `Job Card ETR`, `ETR Plate Detail`, `ETR Print Reel Output` appear in the Doctype list under Module = Job Card Tracking
- [ ] Patches `v4_1.migrate_label_status_to_in_progress` and `v4_1.init_job_card_status` executed (visible in Patch Log)
- [ ] At least one Customer exists
- [ ] Role profile for test user contains the role being tested (System Manager / Manufacturing Manager / Manufacturing User / Sales User)
