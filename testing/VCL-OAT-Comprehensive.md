# VCL PRODUCTION — COMPREHENSIVE OAT

**Custom App: production_log | Modules: Production Log (PPC) + Job Card Tracking**

Test Date: __________ | Tester: __________ | Site: vimitconverters.frappe.cloud

---

## EXECUTIVE SUMMARY

Operational Acceptance Testing for the entire production_log app. Covers installation, migrations, fixtures, performance, data integrity, concurrency, API, browser/mobile compatibility, security, backup & recovery, and audit/logging. Most of these tests require bench CLI access, multi-user sessions, or separate role logins.

| Suite | Total | Pass | Fail | Skip | Rate (excl skip) |
|-------|-------|------|------|------|-------------------|
| Section 1 — Installation & Migration | __ | __ | __ | __ | __% |
| Section 2 — Fixtures & Seed Data | __ | __ | __ | __ | __% |
| Section 3 — Performance | __ | __ | __ | __ | __% |
| Section 4 — Data Integrity | __ | __ | __ | __ | __% |
| Section 5 — Concurrency & Multi-User | __ | __ | __ | __ | __% |
| Section 6 — API | __ | __ | __ | __ | __% |
| Section 7 — Browser & Mobile | __ | __ | __ | __ | __% |
| Section 8 — Security | __ | __ | __ | __ | __% |
| Section 9 — Backup, Recovery, Rollback | __ | __ | __ | __ | __% |
| Section 10 — Logging & Audit | __ | __ | __ | __ | __% |

---

## CRITICAL DEFECTS FOUND

| Test ID | Severity | Issue | Impact / Action |
|---------|----------|-------|-----------------|
|  |  |  |  |

---

## SECTION 1 — INSTALLATION & MIGRATION

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-1.01 | Install | Fresh install | bench get-app production_log; bench --site [site] install-app production_log | Install succeeds; app listed in Installed Apps |  |  |
| OT-1.02 | Install | Install on existing site with Job Card data | Install on a site that already has Job Card Label/Carton/Computer Paper records | Install succeeds; existing JCs gain custom_production_status=Not Started; no data loss |  |  |
| OT-1.03 | Migrate | bench migrate runs clean | bench --site [site] migrate | Zero errors. All doctypes created; custom fields applied; all patches in patches.txt executed |  |  |
| OT-1.04 | Migrate | Idempotent migrate | Run bench migrate twice | Second run: zero errors, no duplicate seed data |  |  |
| OT-1.05 | Patches | v1_0.setup_roles_and_permissions | Check Error Log after migrate | No errors; roles (Mfg Manager/User, Prod Log User) exist with correct permissions |  |  |
| OT-1.06 | Patches | v1_0.remove_job_card_production_entry | Check that legacy doctype (if it existed) is removed | No residual tables; no orphan references |  |  |
| OT-1.07 | Patches | v1_0.rename_workspace_to_vcl_production | Open workspace list | "VCL Production" workspace exists; old workspace name not present |  |  |
| OT-1.08 | Patches | v1_0.remove_production_execution_layer | Check for any removed legacy doctype | No residual tables |  |  |
| OT-1.09 | Patches | v2_0.setup_ppc_custom_fields | Inspect Custom Field list for Workstation Type, Workstation, Job Card Computer Paper/Label/Carton | All 16 custom fields present |  |  |
| OT-1.10 | Patches | v2_0.add_carton_sfk_flag | Inspect Custom Field list for Job Card Carton | custom_is_sfk field present, Check type, default 0, inserted after quantity_ordered |  |  |
| OT-1.11 | Patches | after_migrate seeds run | Check Production Stage, Waste Reason, Downtime Reason lists after migrate | 20 Production Stages, 8 Waste Reasons, 8 Downtime Reasons present |  |  |
| OT-1.12 | Patches | after_migrate idempotent | Run bench migrate again after seeds exist | No duplicate inserts (uses exists() guard) |  |  |
| OT-1.13 | Upgrade | Upgrade from a prior commit | git checkout <prior>; install; git checkout main; bench migrate | Migration succeeds from prior state; new stages/fields added; existing data preserved |  |  |
| OT-1.14 | Install | after_install hook runs | Install on fresh site | after_install msgprint/setup completes without errors |  |  |

---

## SECTION 2 — FIXTURES & SEED DATA

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-2.01 | Fixtures Export | bench export-fixtures | bench --site [site] export-fixtures --app production_log | fixtures/ directory contains Custom Fields, Print Format, Production Stage, Waste Reason, Downtime Reason |  |  |
| OT-2.02 | Fixtures Import | Fresh site fixture import | Install app on clean site; migrate | All fixtures loaded: seed master data, custom fields, Carton Job Card print format |  |  |
| OT-2.03 | Print Format | Carton Job Card print format installed | Open Print Format list | "Carton Job Card" exists; doctype=Job Card Carton; Jinja-based |  |  |
| OT-2.04 | Seeds | 20 Production Stages seeded | Inspect list | Design, Pre-Press, Printing, Numbering, Collating, Wrapping, Die Cutting, Re-winding, Slitting, Finishing, Corrugating, Pasting, Creasing, Creasing & Slotting, Slotting, Folding & Gluing, Stitching, Gluing, Bundling, Packing |  |  |
| OT-2.05 | Seeds | 8 Waste Reasons seeded | Inspect list | Setup Waste, Misprinted, Off-Register, Torn Web, Material Defect, Wrong Die, Colour Mismatch, Trim Waste |  |  |
| OT-2.06 | Seeds | 8 Downtime Reasons seeded | Inspect list | Mechanical Breakdown, Electrical Fault, Power Outage, Material Shortage, Planned Maintenance, Die Changeover, Operator Unavailable, Waiting for QC |  |  |
| OT-2.07 | Custom Fields | Survive bench update | bench update on the site | All 17 custom fields still present on Workstation Type, Workstation, and the 3 Job Card types |  |  |
| OT-2.08 | Jinja Method | get_carton_svg registered | Render Carton Job Card print format | SVG renders inline; no Jinja exception in error log |  |  |
| OT-2.09 | Hooks | Doc events registered | bench console: check frappe.get_hooks('doc_events') | Production Entry on_submit/on_cancel and Downtime Entry on_submit/on_cancel all wired |  |  |
| OT-2.10 | Fixtures Reapply | Reapply fixtures without duplicates | bench --site [site] install-app production_log (already installed) or bench execute | No duplicate seed rows created |  |  |

---

## SECTION 3 — PERFORMANCE

Targets: list views < 1s, forms < 1s, reports < 3s, Schedule Board < 2s, drag API < 500ms.

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-3.01 | List | Workstation list < 1s with 20+ records | Open list; measure | Page load < 1s |  |  |
| OT-3.02 | List | Workstation Type list < 1s | Open list | < 1s |  |  |
| OT-3.03 | List | Production Stage list < 1s (20 records) | Open list | < 1s |  |  |
| OT-3.04 | List | Waste / Downtime Reason list < 1s | Open each | < 1s |  |  |
| OT-3.05 | List | CPS list < 1s | Open CPS list | < 1s |  |  |
| OT-3.06 | List | Dies list < 1s | Open Dies list | < 1s |  |  |
| OT-3.07 | List | Job Card Carton list < 1s with 100+ records | Open list | < 1s |  |  |
| OT-3.08 | List | Job Card Label list < 1s with 100+ records | Open list | < 1s |  |  |
| OT-3.09 | List | Job Card Computer Paper list < 1s | Open list | < 1s |  |  |
| OT-3.10 | List | DPS list < 1s with 100+ records | Open list | < 1s |  |  |
| OT-3.11 | List | Production Entry list < 1s with 500+ records | Open list | < 1s |  |  |
| OT-3.12 | List | Downtime Entry list < 1s | Open list | < 1s |  |  |
| OT-3.13 | Form | Workstation form < 1s with 5+ Workstation Stage rows | Open form | < 1s |  |  |
| OT-3.14 | Form | Production Stage form < 1s with workstation_stages rows | Open form | < 1s |  |  |
| OT-3.15 | Form | DPS form < 1s with 20 Schedule Lines | Open form | < 1s |  |  |
| OT-3.16 | Form | JC-Carton form < 1s with UPS rows + client scripts | Open a Carton JC with 3+ UPS rows | < 1s |  |  |
| OT-3.17 | Form | JC-Computer Paper form < 1s with 5 colour_of_parts rows | Open form | < 1s |  |  |
| OT-3.18 | Board | Schedule Board < 2s with 10 machines × 5 jobs | Open board on a populated date | < 2s render |  |  |
| OT-3.19 | Board | Drag-and-drop round-trip < 500ms | Drag a card; measure server response | < 500ms |  |  |
| OT-3.20 | Rollup | PE submit → job card progress rollup < 500ms | Submit a PE; measure time until job card status updates | < 500ms |  |  |
| OT-3.21 | Report | Daily Production Summary < 3s (30-day range, 1000+ PEs) | Run with wide range | < 3s |  |  |
| OT-3.22 | Report | Job Progress < 3s (200+ job cards across 3 types) | Run no filter | < 3s |  |  |
| OT-3.23 | Report | Machine Utilization < 3s (30-day range, all machines) | Run with wide range | < 3s |  |  |
| OT-3.24 | Print | Carton Job Card print render < 2s | Click Print Preview | < 2s; SVG renders inline |  |  |

---

## SECTION 4 — DATA INTEGRITY

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-4.01 | Unique | DPS unique(workstation, schedule_date) | Try two DPS for same machine+date | Second rejected with clear error |  |  |
| OT-4.02 | Unique | Production Stage unique stage_name | Try to duplicate 'Printing' | Rejected |  |  |
| OT-4.03 | Unique | Waste Reason unique reason_name | Try to duplicate a reason | Rejected |  |  |
| OT-4.04 | Unique | Downtime Reason unique reason_name | Try to duplicate a reason | Rejected |  |  |
| OT-4.05 | Links | Deleting Production Stage blocked if referenced | Create a Schedule Line referencing a stage; try delete | LinkExistsError |  |  |
| OT-4.06 | Links | Deleting Workstation Type blocked if Workstations exist | Attempt | LinkExistsError |  |  |
| OT-4.07 | Links | Deleting Waste Reason blocked if referenced by PE | Submit PE with that reason; try delete | LinkExistsError |  |  |
| OT-4.08 | Links | Deleting Downtime Reason blocked if referenced by DT | Attempt | LinkExistsError |  |  |
| OT-4.09 | Links | Deleting CPS blocked if Job Card references | Attempt on a referenced CPS | LinkExistsError |  |  |
| OT-4.10 | Links | Deleting Dies blocked if JC-Label references | Attempt | LinkExistsError |  |  |
| OT-4.11 | Links | Deleting DPS blocked if PE linked | Submit PE linked to a DPS; try delete the DPS | LinkExistsError |  |  |
| OT-4.12 | Docstatus | Deleting submitted PE blocked | Attempt | Frappe blocks — cancel first |  |  |
| OT-4.13 | Rollup | PE submit transactional | Submit PE; if the rollup throws, entire transaction rolls back | Job card unchanged; PE not submitted |  |  |
| OT-4.14 | Rollup | PE cancel fully reverses rollup | Submit 3 PEs totalling 9000; cancel one for 3000 | Job card qty_produced = 6000; custom_production_status correct |  |  |
| OT-4.15 | Rollup | Schedule Line status regression on PE cancel | Line went In Progress after PE submit; cancel the PE | Line reverts to Pending (or Done if other PEs satisfy qty) |  |  |
| OT-4.16 | Validation | Cancelled Job Card blocks new PEs | Cancel a JC; try to create a PE for it | PE validate() rejects |  |  |
| OT-4.17 | Validation | Schedule Line sequence_order integrity | Reorder cards via board | sequence_order values updated; no duplicates within the same DPS |  |  |
| OT-4.18 | Totals | DPS totals recalc on line add/remove | Add then delete a line | total_planned_qty, total_planned_hours, utilization_pct all correct |  |  |
| OT-4.19 | estimated_hours | Soft-fallback leaves DPS submittable | Submit a DPS where one line had no rate data | DPS submits; affected line's estimated_hours=0; banner was shown on save |  |  |
| OT-4.20 | Custom Fields | custom_is_sfk default 0 on new Carton JC | Create new JC-C | Checkbox unchecked by default |  |  |

---

## SECTION 5 — CONCURRENCY & MULTI-USER

Requires two browser sessions (different users or incognito + primary) hitting the same data.

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-5.01 | DPS | Two planners edit same DPS | User A and User B both open DPS; A saves, B saves | B gets TimestampMismatchError; prompted to reload |  |  |
| OT-5.02 | DPS | Unique constraint under race | Two users try to create DPS for same machine+date simultaneously | Only one succeeds; other gets duplicate error |  |  |
| OT-5.03 | Board | Two planners use board for same date | A drags a card; B adds a job on another machine | Both operations persist; board reflects both on refresh |  |  |
| OT-5.04 | PE vs DPS | Operator submits PE while planner edits DPS | Operator submits PE; planner had DPS open | PE submits; planner sees updated totals on next reload |  |  |
| OT-5.05 | Job Card | Two operators submit PEs for same job card simultaneously | Submit two PEs with overlapping stages at the same time | Both persist; final qty_produced = sum of both |  |  |
| OT-5.06 | Downtime | Two operators log DT for same machine | Same machine, overlapping times | Both records saved; planner/report surfaces overlap |  |  |

---

## SECTION 6 — API

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-6.01 | REST | Workstation list | GET /api/resource/Workstation | 200; array of records with custom fields |  |  |
| OT-6.02 | REST | Production Stage list | GET /api/resource/Production%20Stage | 200; 20 seed records |  |  |
| OT-6.03 | REST | Job Card Carton detail | GET /api/resource/Job%20Card%20Carton/<name> | 200; full doc including custom_is_sfk, custom_production_status |  |  |
| OT-6.04 | REST | DPS detail | GET /api/resource/Daily%20Production%20Schedule/<name> | 200; includes schedule_lines child table |  |  |
| OT-6.05 | REST | Create PE via POST | POST /api/resource/Production%20Entry with valid payload | 201; doc returned; docstatus=0 |  |  |
| OT-6.06 | REST | Submit PE via POST | PUT /api/resource/Production%20Entry/<name> with docstatus=1 | 200; on_submit fires; job card rolls up |  |  |
| OT-6.07 | Board | Schedule Board data endpoint | Call frappe.call used by the board JS (page method) | Returns DPS data grouped by workstation for the given date |  |  |
| OT-6.08 | Board | Reorder endpoint | Call reorder_schedule_lines with new order | Sequence updates persisted |  |  |
| OT-6.09 | Board | Status toggle endpoint | Call update_line_status | Schedule Line status persisted |  |  |
| OT-6.10 | Report | Report API returns data | GET /api/method/frappe.desk.query_report.run?report_name=Job%20Progress | 200; data array no SQL error (regression guard for OT-2.27) |  |  |
| OT-6.11 | Report | DPS Summary via API | Same for Daily Production Summary | 200; data with expected columns |  |  |
| OT-6.12 | Report | Machine Utilization via API | Same for Machine Utilization | 200 |  |  |
| OT-6.13 | Permissions | Whitelisted methods enforce permissions | Call a whitelisted method as Prod Log User | Permission checks run server-side; unauthorized operations rejected |  |  |

---

## SECTION 7 — BROWSER & MOBILE COMPATIBILITY

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-7.01 | Browser | Chrome latest | Exercise DPS, Schedule Board, PE, DT, reports, JC-Carton print preview | Every interaction works; no JS console errors |  |  |
| OT-7.02 | Browser | Firefox latest | Same | Works |  |  |
| OT-7.03 | Browser | Safari latest | Same | Works |  |  |
| OT-7.04 | Browser | Edge latest | Same | Works |  |  |
| OT-7.05 | Mobile | Schedule Board on tablet (~768px) | Open board on iPad or responsive emulator | Columns scrollable/tabbed; touch drag works |  |  |
| OT-7.06 | Mobile | PE form on phone | Create a PE from a phone | All fields accessible; form submittable |  |  |
| OT-7.07 | Mobile | JC-Carton form on tablet | Open a Carton JC | UPS child table usable on touch |  |  |
| OT-7.08 | Print | Carton Job Card print on Chrome | Print preview + download PDF | All 3 pages render; SVG visible in downloaded PDF |  |  |
| OT-7.09 | Print | Carton print on Safari | Print preview | Same; no missing fonts or broken SVG |  |  |
| OT-7.10 | JS Console | No errors on any page/form | Open each page/form with devtools open | Zero JS errors across all browsers tested |  |  |

---

## SECTION 8 — SECURITY

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-8.01 | Auth | Unauthenticated API blocked | GET /api/resource/Daily%20Production%20Schedule without session | 403 Forbidden |  |  |
| OT-8.02 | Auth | Guest role has no access | Log in as Guest; try /app/daily-production-schedule | Permission denied |  |  |
| OT-8.03 | Auth | Non-permitted role blocked from write | Prod Log User tries to POST a new DPS via API | 403 |  |  |
| OT-8.04 | CSRF | Board mutations require CSRF token | Replay a board drag call without X-Frappe-CSRF-Token | Rejected |  |  |
| OT-8.05 | SQL Injection | Report filter sanitisation | Pass `2026-01-01'; DROP TABLE--` into a report filter | Query parameterised; no SQL injection; report returns empty/error |  |  |
| OT-8.06 | SQL Injection | Job Progress customer filter | Pass a payload through customer filter | Parameterised via whitelist (CUSTOMER_FIELD_BY_TYPE); no injection |  |  |
| OT-8.07 | XSS | Schedule Line notes field | Enter `<script>alert(1)</script>` in notes | Escaped on board card rendering; no alert |  |  |
| OT-8.08 | XSS | Customer name with HTML | Customer containing `<img onerror=alert(1)>` rendered in JC / board | Escaped; no script execution |  |  |
| OT-8.09 | XSS | Carton print format | Carton JC with HTML-like customer / notes | Jinja autoescape renders as text |  |  |
| OT-8.10 | Perms | PE submit respects role | Login as Guest; POST submit PE | 403 |  |  |
| OT-8.11 | Perms | Read-only fields honoured server-side | Attempt to set custom_production_status via API as Mfg User | Rejected or ignored (field is read_only) |  |  |
| OT-8.12 | Perms | Amend/Cancel guarded | Mfg User tries to amend a DPS | Per role config: permitted or blocked (document result) |  |  |
| OT-8.13 | Perms | Role inheritance | Ensure no role grants unintended access to financial customer data | Sales User cannot delete JC-Carton; Prod Log User cannot edit JC |  |  |
| OT-8.14 | Secrets | No secrets in repo | grep for hardcoded passwords/keys in app code | None found |  |  |

---

## SECTION 9 — BACKUP, RECOVERY, ROLLBACK

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-9.01 | Backup | bench backup includes app tables | bench --site [site] backup; inspect SQL dump | Tables for DPS, Schedule Line, Production Entry, Downtime Entry, Production Stage, Workstation Stage, Waste Reason, Downtime Reason, JC Carton/Label/Computer Paper, CPS, Dies, Dies Order, Colour Of Parts, Carton Job Type UPS all present |  |  |
| OT-9.02 | Backup | Backup includes custom fields | Inspect dump for Custom Field records | All 17 custom fields present |  |  |
| OT-9.03 | Backup | Backup includes print format | Inspect dump | Carton Job Card print format present |  |  |
| OT-9.04 | Restore | Restore to fresh site | bench --site [fresh] restore <backup> | All PPC data intact; Schedule Board renders |  |  |
| OT-9.05 | Restore | Restore to fresh site with app pre-installed | Install app first, then restore data | Seeds replaced with backup data; no duplicates |  |  |
| OT-9.06 | Rollback | App uninstall removes doctypes | bench --site [site] uninstall-app production_log | Tables for DPS, Schedule Line, PE, DT, Production Stage, Workstation Stage, Waste Reason, Downtime Reason, CPS, Dies, Dies Order, JC variants all removed |  |  |
| OT-9.07 | Rollback | App uninstall removes custom fields | After uninstall, open Workstation form | No custom_product_line / custom_max_* fields present |  |  |
| OT-9.08 | Rollback | App uninstall removes print format | After uninstall | Carton Job Card print format removed |  |  |
| OT-9.09 | Rollback | Workstation Type data preserved | After uninstall | ERPNext's Workstation Type records still present (base ERPNext doctype) |  |  |
| OT-9.10 | Rollback | Reinstall after uninstall | Uninstall then install again | Clean reinstall; all fixtures reload; no migration errors |  |  |
| OT-9.11 | Rollback | Job cards survive uninstall if Sales-owned | After uninstall, open a Job Card Label (base or customised) | Depends on ownership — record what happens |  |  |

---

## SECTION 10 — LOGGING & AUDIT

| ID | Category | Test Case | Steps | Expected Result | Result | Notes |
|----|----------|-----------|-------|-----------------|--------|-------|
| OT-10.01 | Audit | PE submit logged in Version history | Submit a PE; open Version doc | Log entry shows submit action with timestamp and user |  |  |
| OT-10.02 | Audit | Job card status change logged | After PE submit triggers status change; open JC Version history | Entry shows custom_production_status change Not Started → In Progress |  |  |
| OT-10.03 | Audit | Schedule Board drag logged | Drag a card on the board; open DPS Version history | Entry shows schedule_lines modification |  |  |
| OT-10.04 | Audit | DPS submit logged | Submit a DPS; open Version history | Entry with submit timestamp |  |  |
| OT-10.05 | Audit | DT submit logged | Submit a Downtime Entry | Entry logged |  |  |
| OT-10.06 | Audit | CPS change logged | Edit and save a CPS | Version entry with field diffs |  |  |
| OT-10.07 | Audit | JC-Carton field change logged | Change quantity_ordered on a Draft JC-C | Entry logged |  |  |
| OT-10.08 | Error Log | Validation error logged | Trigger a PE validation error (e.g., waste without reason) | Entry in Frappe Error Log with traceback |  |  |
| OT-10.09 | Error Log | SQL / Jinja exception logged | Cause a print format render failure (malformed data) | Error logged with full traceback |  |  |
| OT-10.10 | Error Log | No noise on clean runs | Check Error Log after 1 hour of normal use | No new ERROR-level entries |  |  |

---

## OUTCOME & SIGN-OFF

**Overall Outcome:** ______________

| | | | |
|---|---|---|---|
| **Tester:** | __________ | **Date:** | __________ |
| **Role:** | __________ | **Outcome:** | __________ |
| **Signature:** | ___________________ | **Approved by:** | ___________________ |
