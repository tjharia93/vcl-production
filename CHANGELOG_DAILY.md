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
- [x] Investigate the stage_position 999 collision — DONE 2026-05-20. Stage ladder applied (see below).
- [ ] Hamada 01 reclassification — currently `Reel to Reel Printing`, likely should be `Sheet to Sheet Printing`.
- [ ] Floor: rename Slotter 01 / Bundler 01 to actual equipment IDs after S3 install.

### Afternoon — stage ladder + per-line production routing model

The stage_position 999 collision is resolved, and the workflow position of
each stage is now modelled as data per product line (not in a station code).
A station's place in the flow depends on which line's job passes through it
— Sheeting is step 1 of Trading but step 5 of Exercise Books — so the route
position lives on the `(stage, product_line)` tag row.

```
[2026-05-20 18:24] WS  · Workstation Type · custom_stage_position ladder set on 14 types (Plate Making 15 … Carton Gluing 165) — resolves the 999 collision
[2026-05-20 18:29] CF  · Workstation Product Line Tag · process_number (Int) — step order within a product line's route
[2026-05-20 18:29] TAG · 26 existing tag rows numbered with process_number across the 8 line routes
[2026-05-20 18:29] TAG · 7 new tag rows added — R2R → Reel to Reel Printing + Label Slitting; Trading → Sheeting; GSE → Collation; Mono Boxes → Lamination + Carton Gluing; Self Adhesive Label → Die Cutting
```

Codified in patch `v7_4.add_process_number_routes` (idempotent — no-op on
this prod site, full effect on fresh installs). Deploy: next GitHub push
(morning of 2026-05-21).

Open route questions for Tanuj to confirm before the push:
- Sheet-to-Sheet Printing keeps a `Corrugation and Carton Department` tag
  with no process_number (offset-printed carton exception) — keep or drop?
- Trading route is Sheeting only — any other stage?
- R2R route = Reel to Reel Printing → Label Slitting & Re-Winding — correct?
- Computer Paper has no punching/perforation stage — needed?

Confirmed by Tanuj 2026-05-20: Trading = Sheeting only; R2R = R2R Printing →
Label Slitting & Re-Winding; Computer Paper punching not needed. The S2S
Printing carton-tag exception is still open.

### Evening — EOD Gemba Telegram delivery via n8n webhook

The 17:00 EOD Gemba PDF could not reach Telegram: `gemba.py` looked for the
bot token in site_config / env / `/etc/vcl/telegram.env`, none of which exist
on Frappe Cloud. Reworked so Frappe POSTs the PDF to an n8n webhook — the
Telegram bot token stays in n8n, never in Frappe.

```
[2026-05-20 19:05] N8N  · workflow vclGembaTelegram001 (gemba_telegram.json) deployed live — Webhook → Code (multipart sendDocument) → Respond. URL https://vcl-intranet.tailb2b755.ts.net/webhook/gemba-telegram
[2026-05-20 19:10] CODE · production_log/api/gemba.py · _push_to_telegram rewired to POST {pdf_base64, filename, caption, chat_id} to the n8n webhook; _resolve_telegram_credentials + /etc/vcl/telegram.env fallback removed
```

The n8n workflow is already live and verified (webhook receive, body parse,
`$env` token read, and multipart `sendDocument` to Telegram all confirmed via
smoke tests). The `gemba.py` change deploys on the next GitHub push (morning
2026-05-21).

Destination chat: `GEMBA_CHAT_ID` defaults to `8566637123` (Tanuj's personal
chat) in gemba.py — site_config key `gemba_chat_id` still overrides. No
site_config change needed.

Verified live 2026-05-20 19:xx — `gemba_eod.pdf` POSTed to the webhook was
delivered to the chat (Telegram message_id 144, n8n execution `success`).

Follow-up fix — a live run of `generate_eod_report` crashed: it filtered
every JCL on `job_status`, but Job Card ETR is a different schema —
`status` / `delivery_date` / `order_qty`, status vocabulary Draft / In
Progress / Completed / Cancelled. (CP and Label also have no
`customer_name` — they use the `customer` link.) Added `JCL_PROFILE`, a
per-doctype column + status-set map; the report queries alias the real
columns to the logical names the template expects. Pushed for redeploy.

---

## 2026-05-21 — Notebook 32 (Carton Job Card / CPS review)

Tanuj's reMarkable "Notebook 32" — a 5-point review of the carton Customer
Product Specification + Job Card traveller. Applied live, mirrored to git.

```
[2026-05-21 12:20] PS  · CPS · board_type hidden (point 1 — Board Type removed)
[2026-05-21 12:20] PS  · CPS + Job Card Carton · printing_or_plain hidden (point 2 — legacy field retired; print_type kept)
[2026-05-21 12:20] CF  · CPS · print_type moved to the form header (insert_after job_size)
[2026-05-21 12:20] PS  · CPS + Job Card Carton · 3/4/5-ply GSM + material fields depends_on doc.ply (point 3 — GSM layers toggle by ply: 3->1-3, 5->1-5, SFK->1-2)
[2026-05-21 12:20] PS  · CPS · packing_section hidden for Carton, kept for other product types (point 4)
[2026-05-21 12:20] PRINT FORMAT · Carton Job Card · carton layout (die-cut SVG) moved to its own page 2; Station Log -> p3, Resources -> p4 (point 5). Live record + fixtures/print_format.json synced (39035 -> 41076 chars).
[2026-05-21 12:20] N8N · jcl_submitted_notify (vclJclSubmittedNotify001) · buildCartonSubmitLines repointed doc.printing_or_plain -> doc.print_type (point 2 cascade)
```

16 Property Setters + the print_type reposition codified in patch
`v7_5.notebook_32_carton_review` (idempotent). Print-format render verified
live against JC-CORR-2026-0053 — 4-page traveller, Carton Layout on its own
page. n8n rollback backup: `jcl_submitted_notify.json.bak.20260521`.

### Follow-up — Carton Layout page refinements

Tanuj review of the new Carton Layout page:
- Full board **Width & Length** (planned + actual) table added to the page — done, verified live (renders 540 x 1540 for JC-CORR-2026-0053).
- `get_carton_svg` (utils.py) now emits a `viewBox` so the die-cut SVG
  scales reliably — wkhtmltopdf collapses a no-viewBox SVG under CSS width.
- `@page` landscape CSS + `.layout-page` added for the carton-layout page.

OPEN (needs Tanuj decision) — true per-page **landscape** and removing the
**Station-Log overflow page** both require the **Chrome PDF generator**.
This Frappe build has no per-print-format `pdf_generator` field — switching
is a site-wide `pdf_generator` config change. wkhtmltopdf (current engine)
ignores named `@page` orientation and did not honour the row-height
tightening. Recommend switching the site to the Chrome generator.
