# VCL Production · Daily Change Log

Direct ERPNext changes (Desk-side · MCP-side · or live-only). Recorded here as they happen.
At 16:30 daily, sync to git via `bench export-fixtures` + commit + push.

Format: `[YYYY-MM-DD HH:MM] TYPE · DOCTYPE · DESCRIPTION`

Types:
- **CF** — Custom Field added/modified
- **PS** — Property Setter
- **CS** — Client Script
- **SS** — Server Script
- **DR** — Direct Record (create/update on existing doctype)
- **WS** — Workstation / Workstation Type
- **TAG** — Workstation Product Line Tag
- **HOTFIX** — manual fix after a failed patch

---

## 2026-05-20 (S1 + S2 deploy day)

### Direct MCP fixes after Build #5 — v7_1 patch silent failure

The v7_1 patch (`production_log.patches.v7_1.add_carton_workstations`) executed and was recorded in Patch Log, but a `try/except frappe.NameError: pass` block silently swallowed insert failures for the 2 new Workstation Types and 2 Workstations. Fixed manually via MCP create_doc calls. To be properly resolved by a follow-up v7_3 patch.

```
[2026-05-20 02:36] WS · Workstation Type · Slotting (custom_stage_position=155, product_line=Corrugation and Carton Department)
[2026-05-20 02:37] WS · Workstation Type · Bundling (custom_stage_position=170, product_line=Corrugation and Carton Department)
[2026-05-20 02:42] WS · Workstation · Slotter 01 (workstation_type=Slotting)
[2026-05-20 02:42] WS · Workstation · Bundler 01 (workstation_type=Bundling)
[2026-05-20 02:44] TAG · Plate Making · added "Corrugation and Carton Department" (was tagged "All" only)
[2026-05-20 02:44] TAG · Sheeting · added "Corrugation and Carton Department" (was tagged "General Stationery and Exercise Book" only)
```

### Confirmed live (from S1 + S2 deploy build #5)

```
[2026-05-19 23:26] DOCTYPE · Job Traveller Run (Job Card Tracking module) — child doctype, 14 fields
[2026-05-19 23:26] DOCTYPE · Job Resource Consumption (Job Card Tracking module) — child doctype, 15 fields with variance_pct auto-calc
[2026-05-19 23:26] CF · Customer Product Specification · print_type (Select: Plain · Printed)
[2026-05-19 23:26] CF · Job Card Carton · print_type (Select, in_list_view)
[2026-05-19 23:26] CF · Job Card Computer Paper · print_type (Select, in_list_view)
[2026-05-19 23:26] CF · Job Card ETR · print_type (Select, in_list_view)
[2026-05-19 23:26] CF · Job Card Label · print_type (Select, in_list_view)
[2026-05-19 23:26] CF · Job Card Carton · traveller_runs (Table → Job Traveller Run)
[2026-05-19 23:26] CF · Job Card Computer Paper · traveller_runs (Table → Job Traveller Run)
[2026-05-19 23:26] CF · Job Card ETR · traveller_runs (Table → Job Traveller Run)
[2026-05-19 23:26] CF · Job Card Label · traveller_runs (Table → Job Traveller Run)
[2026-05-19 23:26] CF · Job Card Carton · resource_consumption (Table → Job Resource Consumption)
[2026-05-19 23:26] CF · Job Card Computer Paper · resource_consumption (Table → Job Resource Consumption)
[2026-05-19 23:26] CF · Job Card ETR · resource_consumption (Table → Job Resource Consumption)
[2026-05-19 23:26] CF · Job Card Label · resource_consumption (Table → Job Resource Consumption)
[2026-05-19 23:26] BACKFILL · CPS print_type — 14 Carton CPS records, mix of Plain/Printed mapped from printing_or_plain or colour usage
[2026-05-19 23:26] CF · Job Card Carton · plate_ready · material_in_stock · customer_hold · artwork_approved · plates_lead_time_clear (Check fields, readiness flags for Release Plan)
[2026-05-19 23:26] CF · Job Card Computer Paper · same 5 readiness Check fields
[2026-05-19 23:26] CF · Job Card ETR · same 5 readiness Check fields
[2026-05-19 23:26] CF · Job Card Label · same 5 readiness Check fields
[2026-05-19 23:26] PRINT FORMAT · Carton Job Card · pages 2-3 redesigned with JTRun/JResource Jinja loops, 8 stations, plain auto-skip
[2026-05-20 00:55] PRINT FORMAT · Carton Job Card · live record html updated to traveller v4 (23097 -> 39035 chars · v3 Reel Tracking removed · v4 Station Log + Resources added). fixtures/print_format.json also synced (commit 3b629b7).
```

### Follow-up TODOs

- [x] Write `v7_3.finish_carton_workstations` patch — DONE 2026-05-20. Idempotent: no-op on current prod (records exist), creates them on fresh installs.
- [ ] Configure `telegram_bot_token` and `gemba_channel_chat_id` in `site_config.json` on prod to enable 17:00 EAT EOD Gemba auto-push.
- [ ] Investigate the stage_position 999 collision (Corrugation + ETR Slitting + others all at 999) — not from my work, but blocks future WT saves until fixed.
- [ ] Hamada 01 reclassification — currently `Reel to Reel Printing`, likely should be `Sheet to Sheet Printing`.
- [ ] Floor: rename Slotter 01 / Bundler 01 to actual equipment IDs after S3 install.
