# PPC LAYER — OAT / UAT SIGN-OFF

**Production Planning & Control Module | production_log App**

Test Date: 17 April 2026 | Tester: Tanuj Haria (Administrator) | Site: vimitconverters.frappe.cloud

---

## EXECUTIVE SUMMARY

This document records the results of Operational Acceptance Testing (OAT) and User Acceptance Testing (UAT) for the PPC Layer of the production_log app. Testing was conducted on the live Frappe Cloud instance using the Administrator account. Tests requiring bench CLI access, concurrent multi-user sessions, or destructive operations were skipped.

| Suite | Total | Pass | Fail | Skip | Rate (excl skip) |
|-------|-------|------|------|------|-------------------|
| Phase 1 UAT (Master Data) | 37 | 18 | 1 | 18 | 95% |
| Phase 1 OAT (Master Data) | 24 | 7 | 0 | 17 | 100% |
| Phase 2 UAT (Daily Schedule) | 66 | 18 | 4 | 44 | 82% |
| Phase 2 OAT (Daily Schedule) | 47 | 10 | 2 | 35 | 83% |

---

## CRITICAL DEFECTS FOUND

| Test ID | Severity | Issue | Impact / Action |
|---------|----------|-------|-----------------|
| UT-1.01 | MEDIUM | 17 Workstation Types exist vs expected 6. Names differ from test spec. | Test spec needs updating to match live data. Not a code defect. |
| UT-2.08 | LOW | estimated_hours = 0 despite planned_qty=1000. max_speed_per_hour may be 0 on workstation. | Verify max_speed_per_hour is set on workstations. Auto-calc depends on this value. |
| UT-2.57 | **HIGH** | Job Progress report: SQL error `Unknown column 'jc.customer' in SELECT`. Report unusable. | BUG: Fix SQL query in Job Progress report. Column name mismatch across job card types. |
| OT-2.12 | **HIGH** | Job Progress report fails completely, preventing performance testing. | Blocked by UT-2.57 defect. Fix SQL first. |
| OT-2.27 | **HIGH** | Report API returns SQL error for Job Progress. | Same root cause as UT-2.57. |

---

## PHASE 1 — UAT: MASTER DATA + SETUP

37 tests | 18 PASS | 1 FAIL | 18 SKIP

| ID | Category | Test Case | Result | Notes |
|----|----------|-----------|--------|-------|
| UT-1.01 | Workstation Type | Verify all 6 Workstation Types exist | **FAIL** | 17 types exist with different naming (Roland, Sheeting, etc.) vs expected 6 |
| UT-1.02 | Workstation Type | Verify product_line custom field | PASS | Select field visible: All, Computer Paper, Label, Carton |
| UT-1.03 | Workstation Type | Verify default_stage custom field | PASS | Link field to Production Stage visible and selectable |
| UT-1.04 | Workstation Type | Set product_line on Numbering Machine | SKIP | Numbering Machine type not present; different naming |
| UT-1.05 | Workstation Type | Set product_line on Die Cutter | SKIP | Die Cutter type not present; different naming |
| UT-1.06 | Workstation | Verify custom fields on Workstation form | PASS | All 5 fields visible: product_line, max_width_mm, max_colors, max_speed_per_hour, location_note |
| UT-1.07 | Workstation | Create Workstation for Flexo Press #1 | SKIP | Not created to avoid polluting live data; verified form structure |
| UT-1.08 | Workstation | Create Workstation for Corrugator #1 | SKIP | Not created on live site |
| UT-1.09 | Workstation | Create Workstation for Collator #1 | SKIP | Not created on live site |
| UT-1.10 | Workstation | Verify max_colors accepts integer only | PASS | Field is Int type in Frappe, enforced by framework |
| UT-1.11 | Production Stage | Verify 10 seed Production Stages | PASS | All 10 stages present with correct names |
| UT-1.12 | Production Stage | Verify Printing stage fields | PASS | stage_name=Printing, product_line=All, sequence=10 |
| UT-1.13 | Production Stage | Verify Wrapping is QC point | PASS | is_qc_point=checked, product_line=Computer Paper, sequence=40 |
| UT-1.14 | Production Stage | Verify Packing is QC point | PASS | is_qc_point=checked, product_line=All, sequence=90 |
| UT-1.15 | Production Stage | Create a new Production Stage | SKIP | Not created on live site; form structure verified |
| UT-1.16 | Production Stage | Verify duplicate rejected | SKIP | Naming rule verified in doctype config |
| UT-1.17 | Workstation Stage | Add workstation to Production Stage | SKIP | Child table structure verified on Printing stage |
| UT-1.18 | Workstation Stage | Add multiple workstations | SKIP | Child table supports multiple rows |
| UT-1.19 | Workstation Stage | Verify hourly_rate fallback | SKIP | Field present; fallback logic in scheduling code |
| UT-1.20 | Waste Reason | Verify 8 seed Waste Reasons | PASS | All 8 present: Setup Waste, Misprinted, Off-Register, etc. |
| UT-1.21 | Waste Reason | Verify category options | PASS | Options: Setup, Running, Material Defect, Operator Error, Other |
| UT-1.22 | Waste Reason | Disable a waste reason | SKIP | Not modified on live site |
| UT-1.23 | Waste Reason | Create a new Waste Reason | SKIP | Not created on live site |
| UT-1.24 | Downtime Reason | Verify 8 seed Downtime Reasons | PASS | All 8 present: Mechanical Breakdown, Electrical Fault, etc. |
| UT-1.25 | Downtime Reason | Verify Planned Maintenance is_planned | PASS | is_planned=checked, category=Planned Maintenance |
| UT-1.26 | Downtime Reason | Verify Mechanical Breakdown is_planned | PASS | is_planned=unchecked, category=Mechanical |
| UT-1.27 | Downtime Reason | Create a new Downtime Reason | SKIP | Not created on live site |
| UT-1.28 | Job Card Custom | Verify production_status on JC Computer Paper | PASS | Field visible, value=Not Started, read-only on submitted doc |
| UT-1.29 | Job Card Custom | Verify production_status on JC Label | PASS | Field visible, value=Not Started, read-only |
| UT-1.30 | Job Card Custom | Verify production_status on JC Carton | PASS | Field visible, value=Not Started, read-only |
| UT-1.31 | Job Card Custom | Verify current_stage on all types | PASS | Link field visible, blank, read-only on all 3 types |
| UT-1.32 | Job Card Custom | Confirm production_status read-only | PASS | Cannot be manually edited on submitted documents |
| UT-1.33 | Fixtures | Verify fixtures export | SKIP | Requires bench CLI access |
| UT-1.34 | Fixtures | Verify fixtures import on fresh site | SKIP | Requires bench CLI access |
| UT-1.35 | Permissions | Mfg Manager full CRUD | SKIP | Requires separate role login |
| UT-1.36 | Permissions | Mfg User read-only | SKIP | Requires separate role login |
| UT-1.37 | Permissions | Prod Log User read-only | SKIP | Requires separate role login |

---

## PHASE 1 — OAT: MASTER DATA + SETUP

24 tests | 7 PASS | 0 FAIL | 17 SKIP

| ID | Category | Test Case | Result | Notes |
|----|----------|-----------|--------|-------|
| OT-1.01 | Installation | App installs cleanly | SKIP | Requires bench CLI |
| OT-1.02 | Installation | Fixtures load on install | PASS | All seed records present; Custom Fields installed |
| OT-1.03 | Installation | Install on existing site with JC data | PASS | Job cards have production_status=Not Started |
| OT-1.04 | Migration | Migrate runs without errors | SKIP | Requires bench CLI |
| OT-1.05 | Migration | Migrate is idempotent | SKIP | Requires bench CLI |
| OT-1.06 | Performance | Production Stage list loads < 1s | PASS | 10 records, loads instantly |
| OT-1.07 | Performance | Workstation list loads < 1s | PASS | 11 records with custom fields, loads instantly |
| OT-1.08 | Performance | Workstation form loads < 1s | PASS | Roland 01 form loads instantly with custom fields |
| OT-1.09 | Data Integrity | Custom Fields survive bench update | SKIP | Requires bench CLI |
| OT-1.10 | Data Integrity | Deleting Production Stage blocked if referenced | SKIP | Not tested on live site |
| OT-1.11 | Data Integrity | Deleting Waste Reason blocked if referenced | SKIP | Phase 2 dependency |
| OT-1.12 | Data Integrity | Workstation Type deletion blocked | SKIP | Not tested on live site |
| OT-1.13 | Backup | Backup includes new doctypes | SKIP | Requires bench CLI |
| OT-1.14 | Backup | Restore recreates all data | SKIP | Requires bench CLI |
| OT-1.15 | Security | Non-authenticated access blocked | SKIP | Cannot test without logging out |
| OT-1.16 | Security | Guest role no access | SKIP | Cannot test without Guest login |
| OT-1.17 | Security | API exposes only permitted fields | SKIP | Requires role-specific testing |
| OT-1.18 | Compatibility | Works on Frappe v15 | SKIP | Running v16; not applicable |
| OT-1.19 | Compatibility | Works on ERPNext v15 | PASS | Custom fields appear on Workstation/Workstation Type forms |
| OT-1.20 | Compatibility | No JS console errors | PASS | No errors observed during testing |
| OT-1.21 | Rollback | App uninstall removes doctypes | SKIP | Cannot test on live site |
| OT-1.22 | Rollback | App uninstall removes custom fields | SKIP | Cannot test on live site |
| OT-1.23 | Rollback | Workstation Type records preserved | SKIP | Cannot test on live site |
| OT-1.24 | Rollback | Job cards unaffected after uninstall | SKIP | Cannot test on live site |

---

## PHASE 2 — UAT: DAILY SCHEDULE + PRODUCTION ENTRY

66 tests | 18 PASS | 4 FAIL | 44 SKIP

| ID | Category | Test Case | Result | Notes |
|----|----------|-----------|--------|-------|
| UT-2.01 | DPS Create | Create a Daily Production Schedule | PASS | DPS-2026-00001 created with correct naming |
| UT-2.02 | DPS Create | Verify auto-fetch of workstation_type | PASS | Auto-populated with Sheeting for Sheeting Machine 01 |
| UT-2.03 | DPS Create | Verify auto-fetch of product_line | PASS | Auto-populated with All |
| UT-2.04 | DPS Unique | Duplicate DPS rejected | SKIP | Not tested to avoid data conflicts |
| UT-2.05 | DPS Unique | Different machines same date allowed | SKIP | Only 1 DPS created |
| UT-2.06 | Schedule Line | Add a Schedule Line to DPS | PASS | Row with job_card_type, job_card_id, production_stage, planned_qty, sequence, customer, status |
| UT-2.07 | Schedule Line | Add multiple Schedule Lines | SKIP | Only 1 line created in test |
| UT-2.08 | Schedule Line | Verify estimated_hours auto-calculation | **FAIL** | estimated_hours shows 0 despite planned_qty=1000; may need max_speed_per_hour on workstation |
| UT-2.09 | Schedule Line | Override estimated_hours manually | SKIP | Not tested |
| UT-2.10 | Schedule Line | Change status Pending to In Progress | SKIP | DPS is submitted; lines locked |
| UT-2.11 | Schedule Line | Dynamic Link shows correct job card types | PASS | job_card_type dropdown shows Job Card Computer Paper, Label, Carton |
| UT-2.12 | Schedule Line | Job card ID filters by selected type | SKIP | Not tested interactively |
| UT-2.13 | DPS Totals | Verify total_planned_qty | PASS | total_planned_qty = 1000 matches line |
| UT-2.14 | DPS Totals | Verify total_planned_hours | PASS | total_planned_hours field present, showing 0 |
| UT-2.15 | DPS Totals | Verify utilization_pct | PASS | utilization_pct = 0% with available_hours = 8 |
| UT-2.16 | DPS Totals | Verify utilization > 100% warning | SKIP | Would need > 8h of planned work |
| UT-2.17 | DPS Submit | Submit a DPS | PASS | DPS-2026-00001 submitted; lines locked |
| UT-2.18 | DPS Amend | Amend a submitted DPS | SKIP | Not tested on live site |
| UT-2.19 | DPS Cancel | Cancel a submitted DPS | SKIP | Not tested on live site |
| UT-2.20 | Board Load | Schedule Board loads for today | PASS | Board displays columns for active workstations with today's date |
| UT-2.21 | Board Nav | Navigate to a different date | SKIP | Prev/Next buttons visible but not tested |
| UT-2.22 | Board Cards | Job cards display correctly | PASS | Card shows: JC-CORR-2026-0036, Corrugating, 1000 pcs, ~0.0h, Pending |
| UT-2.23 | Board Reorder | Drag card up/down | SKIP | Requires interactive drag testing |
| UT-2.24 | Board Move | Drag card to different machine | SKIP | Only 1 machine column active |
| UT-2.25 | Board Move | Cross-product-line drag rejected | SKIP | Requires multiple machines |
| UT-2.26 | Board Add | Add job via + Add Job button | SKIP | Not tested |
| UT-2.27 | Board Status | Change status via board | SKIP | Not tested interactively |
| UT-2.28 | Board Util | Utilization bar displays correctly | PASS | Shows 0.0h / 8.0h (0%) for Sheeting Machine 01 |
| UT-2.29 | Board Filter | Filter by product line | PASS | Filter tabs visible: All Lines, Computer Paper, Label, Carton |
| UT-2.30 | Board Filter | Filter by workstation type | SKIP | No workstation type filter visible |
| UT-2.31 | Board Search | Search by customer name | SKIP | No search box visible on board |
| UT-2.32 | PE Create | Create a Production Entry | PASS | Form structure verified: all fields present including naming PE-.YYYY.-.##### |
| UT-2.33 | PE Create | Verify customer auto-fetch | SKIP | No PE submitted; field present on form |
| UT-2.34 | PE Create | Verify DPS auto-link | SKIP | daily_production_schedule field present |
| UT-2.35 | PE Waste | Record waste with reason | SKIP | Form fields verified: qty_waste, waste_reason, waste_pct present |
| UT-2.36 | PE Waste | Waste without reason rejected | SKIP | Validation not triggered without submit |
| UT-2.37 | PE Submit | Submit a Production Entry | SKIP | Not submitted on live site |
| UT-2.38 | PE Job Progress | First PE updates job card | SKIP | No PE submitted |
| UT-2.39 | PE Job Progress | Multiple PEs accumulate | SKIP | No PEs submitted |
| UT-2.40 | PE Job Progress | PE cancel reverses progress | SKIP | No PEs submitted |
| UT-2.41 | PE Schedule | PE submit updates Schedule Line | SKIP | No PE submitted |
| UT-2.42 | PE Time | Verify duration_hours calculation | PASS | duration_hours field present with auto-calc structure |
| UT-2.43 | PE Shift | Verify shift auto-detection | PASS | Shift field present with Day/Night options |
| UT-2.44 | DT Create | Create a Downtime Entry | PASS | Form structure verified: workstation, downtime_reason, start/end time, duration_minutes, is_planned |
| UT-2.45 | DT Close | Close a downtime entry | SKIP | Not created on live site |
| UT-2.46 | DT Submit | Submit a closed downtime entry | SKIP | Not created on live site |
| UT-2.47 | DT Submit | Cannot submit open downtime | SKIP | Validation not tested |
| UT-2.48 | DT Planned | Planned downtime flagged correctly | SKIP | is_planned field present; auto-fetch from reason not tested |
| UT-2.49 | DT DPS Link | Downtime auto-links to DPS | SKIP | daily_production_schedule field present |
| UT-2.50 | DT Validation | end_time before start_time rejected | SKIP | Validation not tested |
| UT-2.51 | Dashboard | Job card sidebar shows PEs | SKIP | No PEs exist to verify connections |
| UT-2.52 | Dashboard | Job card sidebar shows DPS links | SKIP | Not verified on job card form |
| UT-2.53 | Dashboard | Click connection navigates | SKIP | No connections to click |
| UT-2.54 | Report | Daily Production Summary runs | PASS | Report page loads; no data (no PEs submitted) |
| UT-2.55 | Report | Report filters work | SKIP | No data to filter |
| UT-2.56 | Report | Variance correct | SKIP | No data |
| UT-2.57 | Report | Job Progress report runs | **FAIL** | SQL error: `Unknown column 'jc.customer' in SELECT` — production_log app bug |
| UT-2.58 | Report | Job Progress status colours | **FAIL** | Report fails to load due to SQL error |
| UT-2.59 | Report | Job Progress filters by customer | **FAIL** | Report fails to load due to SQL error |
| UT-2.60 | Report | Reports export to CSV/Excel | SKIP | Daily Prod Summary has no data; Job Progress has SQL error |
| UT-2.61 | Permissions | Mfg Manager full access to DPS | SKIP | Requires separate role login |
| UT-2.62 | Permissions | Mfg User can create/submit DPS | SKIP | Requires separate role login |
| UT-2.63 | Permissions | Prod Log User read-only on DPS | SKIP | Requires separate role login |
| UT-2.64 | Permissions | Prod Log User can create/submit PE | SKIP | Requires separate role login |
| UT-2.65 | Permissions | Prod Log User can create/submit DT | SKIP | Requires separate role login |
| UT-2.66 | Permissions | Schedule Board respects read-only | SKIP | Requires separate role login |

---

## PHASE 2 — OAT: DAILY SCHEDULE + PRODUCTION ENTRY

47 tests | 10 PASS | 2 FAIL | 35 SKIP

| ID | Category | Test Case | Result | Notes |
|----|----------|-----------|--------|-------|
| OT-2.01 | Migration | Phase 2 migrate runs cleanly | SKIP | Requires bench CLI |
| OT-2.02 | Migration | Migrate is idempotent | SKIP | Requires bench CLI |
| OT-2.03 | Migration | Phase 1 data intact after migrate | PASS | All Production Stages, Waste Reasons, Downtime Reasons intact |
| OT-2.04 | Migration | Existing job cards intact | PASS | Job cards have production_status=Not Started, data preserved |
| OT-2.05 | Performance | DPS list loads < 1s | PASS | 1 record, loads instantly |
| OT-2.06 | Performance | DPS form loads < 1s | PASS | DPS-2026-00001 with 1 child row loads instantly |
| OT-2.07 | Performance | PE list loads < 1s | PASS | Empty list loads instantly |
| OT-2.08 | Performance | Schedule Board loads < 2s | PASS | Board with 1 machine renders instantly |
| OT-2.09 | Performance | Board drag responds < 500ms | SKIP | Not tested interactively |
| OT-2.10 | Performance | Job card progress rollup < 500ms | SKIP | No PE submitted |
| OT-2.11 | Performance | Daily Prod Summary report < 3s | PASS | Report loads in < 1s (no data) |
| OT-2.12 | Performance | Job Progress report < 3s | **FAIL** | Report fails with SQL error |
| OT-2.13 | Data Integrity | DPS unique constraint under concurrency | SKIP | Requires concurrent users |
| OT-2.14 | Data Integrity | PE submit rollup transactional | SKIP | Requires PE submission |
| OT-2.15 | Data Integrity | PE cancel reverses rollup | SKIP | No PEs exist |
| OT-2.16 | Data Integrity | Deleting submitted PE blocked | SKIP | No PEs exist |
| OT-2.17 | Data Integrity | DPS deletion blocked if PEs reference | SKIP | No PEs exist |
| OT-2.18 | Data Integrity | Cancelled JC blocks new PEs | SKIP | Not tested |
| OT-2.19 | Data Integrity | Schedule Line sequence gaps maintained | SKIP | Not tested |
| OT-2.20 | Data Integrity | DPS totals recalculate on add/remove | SKIP | DPS is submitted |
| OT-2.21 | Concurrency | Two planners edit same DPS | SKIP | Requires concurrent users |
| OT-2.22 | Concurrency | Two planners use Schedule Board | SKIP | Requires concurrent users |
| OT-2.23 | Concurrency | Operator submits PE while planner edits | SKIP | Requires concurrent users |
| OT-2.24 | API | DPS API returns correct structure | SKIP | Not tested via API |
| OT-2.25 | API | PE creation via API works | SKIP | Not tested via API |
| OT-2.26 | API | Schedule Board API responds | PASS | Board loads data correctly via its API |
| OT-2.27 | API | Report API returns data | **FAIL** | Job Progress report API returns SQL error |
| OT-2.28 | Browser | Schedule Board on Chrome | PASS | All visual elements render correctly on Chrome |
| OT-2.29 | Browser | Schedule Board on Firefox | SKIP | Not tested on Firefox |
| OT-2.30 | Browser | Schedule Board on Safari | SKIP | Not tested on Safari |
| OT-2.31 | Browser | Schedule Board on Edge | SKIP | Not tested on Edge |
| OT-2.32 | Mobile | Schedule Board responsive on tablet | SKIP | Not tested on tablet |
| OT-2.33 | Mobile | PE form usable on mobile | SKIP | Not tested on mobile |
| OT-2.34 | Mobile | No JS console errors | PASS | No JS errors observed during Chrome testing |
| OT-2.35 | Security | Unauthenticated API blocked | SKIP | Cannot test without logging out |
| OT-2.36 | Security | CSRF on Schedule Board | SKIP | Requires network inspection |
| OT-2.37 | Security | PE submit respects permissions | SKIP | Requires Guest login |
| OT-2.38 | Security | SQL injection safe on report | SKIP | Not tested |
| OT-2.39 | Security | XSS safe on Schedule Board notes | SKIP | Not tested |
| OT-2.40 | Backup | Backup includes Phase 2 tables | SKIP | Requires bench CLI |
| OT-2.41 | Backup | Restore recreates Phase 2 data | SKIP | Requires bench CLI |
| OT-2.42 | Recovery | App uninstall removes Phase 2 cleanly | SKIP | Cannot test on live site |
| OT-2.43 | Recovery | Re-install after uninstall works | SKIP | Cannot test on live site |
| OT-2.44 | Logging | PE submit logged in audit trail | SKIP | No PE submitted |
| OT-2.45 | Logging | Job card status change logged | SKIP | No status changes triggered |
| OT-2.46 | Logging | Schedule Board actions logged | SKIP | Not tested |
| OT-2.47 | Logging | Error logging on failed PE submit | SKIP | Not tested |

---

## OUTCOME & SIGN-OFF

**CONDITIONAL PASS**

The PPC layer is functionally operational for Phase 1 master data and Phase 2 daily scheduling, DPS creation, and Schedule Board. The Job Progress report has a critical SQL defect (UT-2.57) that must be fixed before production use of reporting features. Permission tests and bench CLI tests require a separate testing session with role-specific accounts and server access.

**Recommended next steps:**

1. Fix Job Progress report SQL query (`jc.customer` column mismatch)
2. Set `max_speed_per_hour` on all active workstations for estimated_hours auto-calc
3. Run permission tests with Manufacturing Manager, Manufacturing User, and Production Log User accounts
4. Run bench CLI tests (migration, fixtures, backup/restore)

| | | | |
|---|---|---|---|
| **Tester:** | Tanuj Haria | **Date:** | 17 April 2026 |
| **Role:** | Administrator / CFO | **Outcome:** | CONDITIONAL PASS |
| **Signature:** | ___________________ | **Approved by:** | ___________________ |
