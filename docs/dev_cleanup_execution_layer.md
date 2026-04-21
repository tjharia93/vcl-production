# VCL Production Log — Execution Layer Cleanup
**App:** `production_log` (repo: `tjharia93/vcl-production`)
**Prepared:** 2026-04-20
**Prepared by:** Tanuj Haria (VCL) / Claude (Technical PM)
**Status:** Ready for developer — do STEP 0 first before touching anything else

---

## Decision

Strip the entire production execution layer from the app. The workflow was
built before it was properly defined and needs to be redesigned from scratch.

**What stays:** The three job card DocTypes (Computer Paper, Label, Carton)
and their supporting master data (Customer Product Specification, Dies,
Carton Job Type UPS, Colour of Parts).

**What goes:** Everything in the `Production Log` module — all 8 DocTypes,
3 reports, the Daily Schedule Board page, and the custom tracking fields
that v2_0 added to the job cards.

---

## STEP 0 — CRITICAL: Back up the CP Planning Board before touching anything

The CP Planning Board page (`cp_planning_board`) **exists in the live
instance but is NOT in the repo.** It was built and deployed directly. If
you run `bench migrate` or reset the app before extracting it, you will lose
the page.

**Do this first:**

SSH into the server and copy the page files out of the Frappe apps directory:

```bash
# On the server (paths will vary by bench name)
cd /home/frappe/frappe-bench/apps/production_log/production_log/production_log/page/

# Confirm the folder exists
ls cp_planning_board/

# Copy the files you need into the repo
cp -r cp_planning_board/ /path/to/your/local/repo/production_log/production_log/page/
```

The files to pull are:
- `cp_planning_board.json`
- `cp_planning_board.py`
- `cp_planning_board.js`
- `cp_planning_board.css` (if it exists)
- `__init__.py`

Commit these to the repo before proceeding. The CP Planning Board is the
starting point for the new planning workflow — it must be preserved.

---

## STEP 1 — Delete these files and folders from the repo

### Entire DocType folders to delete

```
production_log/production_log/doctype/production_entry/
production_log/production_log/doctype/daily_production_schedule/
production_log/production_log/doctype/schedule_line/
production_log/production_log/doctype/downtime_entry/
production_log/production_log/doctype/downtime_reason/
production_log/production_log/doctype/waste_reason/
production_log/production_log/doctype/production_stage/
production_log/production_log/doctype/workstation_stage/
```

### Page folder to delete

```
production_log/production_log/page/daily_schedule_board/
```

### Report folders to delete

```
production_log/production_log/report/daily_production_summary/
production_log/production_log/report/job_progress/
production_log/production_log/report/machine_utilization/
```

### Event files to delete

```
production_log/events/production_entry.py
production_log/events/downtime_entry.py
```

### Patch files — do NOT delete

Leave `patches/v2_0/seed_ppc_master_data.py` and
`patches/v2_0/setup_ppc_custom_fields.py` in place. They are already
recorded in `patches.txt` and have run on the live site. Deleting them
would cause Frappe to complain about missing patch modules on any site
where they have already executed.

---

## STEP 2 — Edit `hooks.py`

File: `production_log/hooks.py`

Make three changes:

**Remove the `after_migrate` hook** (seeds Production Stage / Waste Reason
/ Downtime Reason data — these tables are being dropped):

```python
# DELETE this line:
after_migrate = "production_log.patches.v2_0.seed_ppc_master_data.execute"
```

**Remove the `doc_events` block** entirely:

```python
# DELETE this entire block:
doc_events = {
    "Production Entry": {
        "on_submit": "production_log.events.production_entry.on_submit",
        "on_cancel": "production_log.events.production_entry.on_cancel",
    },
    "Downtime Entry": {
        "on_submit": "production_log.events.downtime_entry.on_submit",
        "on_cancel": "production_log.events.downtime_entry.on_cancel",
    },
}
```

**Edit the `fixtures` list** — remove the three master-data entries:

```python
# BEFORE:
fixtures = [
    {"dt": "Print Format", "filters": [["name", "in", ["Carton Job Card"]]]},
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", [
                "Workstation Type",
                "Workstation",
                "Job Card Computer Paper",
                "Job Card Label",
                "Job Card Carton",
            ]]
        ],
    },
    {"dt": "Production Stage"},
    {"dt": "Waste Reason"},
    {"dt": "Downtime Reason"},
]

# AFTER:
fixtures = [
    {"dt": "Print Format", "filters": [["name", "in", ["Carton Job Card"]]]},
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", [
                "Workstation Type",
                "Workstation",
                "Job Card Computer Paper",
                "Job Card Label",
                "Job Card Carton",
            ]]
        ],
    },
]
```

Note: The Custom Field fixture entry stays because we still have legitimate
custom fields on Workstation and Workstation Type (product line, machine
specs). The patch in STEP 3 will remove the production-tracking custom
fields from the live site; the fixture filter will then only export what
remains.

---

## STEP 3 — Write a new cleanup patch `v3_0`

This patch cleans up the live site. The v2_0 patch already installed
Production Stage data, Downtime Reason data, and the custom tracking fields
on all three job cards. Removing the DocType folders from the repo is not
enough — the database tables and custom fields still exist in production.

Create the file:
`production_log/patches/v3_0/remove_execution_layer.py`

And create `production_log/patches/v3_0/__init__.py` (empty).

```python
"""
Patch v3_0: Remove the production execution layer from the live site.

Drops all eight DocTypes introduced in v2_0 and removes the production-
tracking custom fields from the three job card DocTypes. The job card
DocTypes themselves and their native fields are untouched.

Safe to run multiple times (idempotent). Each operation checks for
existence before acting.
"""

import frappe


# ── 1. DocTypes to delete ────────────────────────────────────────────────────

# Delete children first so parent deletes don't block on FK constraints.
CHILD_DOCTYPES = [
    "Schedule Line",
    "Workstation Stage",
]

PARENT_DOCTYPES = [
    "Production Entry",
    "Daily Production Schedule",
    "Downtime Entry",
    "Downtime Reason",
    "Waste Reason",
    "Production Stage",
]


def _delete_doctype(name):
    if not frappe.db.exists("DocType", name):
        return
    try:
        frappe.delete_doc(
            "DocType", name,
            force=True,
            ignore_missing=True,
            ignore_permissions=True,
        )
    except Exception:
        frappe.db.delete("DocType", {"name": name})

    table_name = "tab" + name
    frappe.db.commit()
    frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table_name}`")


# ── 2. Custom fields to remove from job cards ────────────────────────────────

# These were added by patches/v2_0/setup_ppc_custom_fields.py
CUSTOM_FIELDS_TO_REMOVE = [
    # Section break + two tracking fields, on all three job cards
    ("Job Card Computer Paper", "custom_production_tracking_sb"),
    ("Job Card Computer Paper", "custom_production_status"),
    ("Job Card Computer Paper", "custom_current_stage"),
    ("Job Card Label",          "custom_production_tracking_sb"),
    ("Job Card Label",          "custom_production_status"),
    ("Job Card Label",          "custom_current_stage"),
    ("Job Card Carton",         "custom_production_tracking_sb"),
    ("Job Card Carton",         "custom_production_status"),
    ("Job Card Carton",         "custom_current_stage"),
    # Workstation Type: default stage linked to Production Stage (being deleted)
    ("Workstation Type",        "custom_default_stage"),
]


def _remove_custom_fields():
    for doctype, fieldname in CUSTOM_FIELDS_TO_REMOVE:
        cf_name = frappe.db.get_value(
            "Custom Field", {"dt": doctype, "fieldname": fieldname}
        )
        if cf_name:
            frappe.delete_doc(
                "Custom Field", cf_name,
                force=True,
                ignore_permissions=True,
            )

        # Also drop the column from the database table if it exists
        table = "tab" + doctype
        if frappe.db.table_exists(table):
            existing_cols = {
                row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")
            }
            if fieldname in existing_cols:
                frappe.db.commit()
                frappe.db.sql_ddl(
                    f"ALTER TABLE `{table}` DROP COLUMN `{fieldname}`"
                )


# ── 3. Pages and reports to clean up ────────────────────────────────────────

PAGES_TO_DELETE = ["daily-schedule-board"]
REPORTS_TO_DELETE = [
    "Daily Production Summary",
    "Job Progress",
    "Machine Utilization",
]


def _cleanup_pages_and_reports():
    for page in PAGES_TO_DELETE:
        if frappe.db.exists("Page", page):
            try:
                frappe.delete_doc(
                    "Page", page,
                    force=True,
                    ignore_permissions=True,
                )
            except Exception:
                frappe.db.delete("Page", {"name": page})

    for report in REPORTS_TO_DELETE:
        if frappe.db.exists("Report", report):
            try:
                frappe.delete_doc(
                    "Report", report,
                    force=True,
                    ignore_permissions=True,
                )
            except Exception:
                frappe.db.delete("Report", {"name": report})


# ── 4. Workspace shortcuts ───────────────────────────────────────────────────

WORKSPACE_LINK_TARGETS = [
    "Production Entry",
    "Daily Production Schedule",
    "Downtime Entry",
    "Production Stage",
    "Waste Reason",
    "Downtime Reason",
    "daily-schedule-board",
]


def _cleanup_workspace_links():
    for target in WORKSPACE_LINK_TARGETS:
        for child_dt in ("Workspace Shortcut", "Workspace Link"):
            if frappe.db.exists("DocType", child_dt):
                frappe.db.delete(child_dt, {"link_to": target})


# ── Main ─────────────────────────────────────────────────────────────────────

def execute():
    # 1. Remove custom fields first so DocType deletes don't leave orphan columns
    _remove_custom_fields()

    # 2. Delete child DocTypes
    for child in CHILD_DOCTYPES:
        _delete_doctype(child)

    # 3. Delete parent DocTypes
    for parent in PARENT_DOCTYPES:
        _delete_doctype(parent)

    # 4. Clean up pages, reports, workspace links
    _cleanup_pages_and_reports()
    _cleanup_workspace_links()

    # 5. Clear cache
    frappe.clear_cache()
    frappe.db.commit()
```

---

## STEP 4 — Register the patch in `patches.txt`

Add one line at the bottom of `production_log/patches.txt`:

```
production_log.patches.v3_0.remove_execution_layer
```

---

## STEP 5 — Deploy and migrate

```bash
cd /home/frappe/frappe-bench
bench --site vimitconverters.frappe.cloud migrate
```

The patch will run automatically as part of migrate. Watch the output for
any errors. If a DocType table doesn't exist the patch will skip it cleanly.

---

## STEP 6 — Post-migration checks

Verify the following in the live UI at `vimitconverters.frappe.cloud`:

| Check | Expected |
|---|---|
| `/app/production-entry` | 404 — page not found |
| `/app/daily-production-schedule` | 404 — page not found |
| `/app/downtime-entry` | 404 — page not found |
| `/app/production-stage` | 404 — page not found |
| `/app/waste-reason` | 404 — page not found |
| `/app/downtime-reason` | 404 — page not found |
| `/app/daily-schedule-board` | 404 — page not found |
| `/app/cp-planning-board` | Loads correctly (must have been preserved from STEP 0) |
| Open any CP Job Card | No "Production Tracking" section visible |
| Open any Label Job Card | No "Production Tracking" section visible |
| Open any Carton Job Card | No "Production Tracking" section visible |
| VCL Production workspace | No broken shortcuts to deleted DocTypes |
| Carton Job Card print format | Still renders SVG correctly (utils.py untouched) |
| Customer Product Specification | Opens normally |
| Dies List | Opens normally |

---

## What is NOT changing

These are explicitly kept and should not be touched:

| Item | Reason |
|---|---|
| `Job Card Computer Paper` — all native fields | Pure order/spec data |
| `Job Card Label` — all native fields | Pure order/spec data (note: `production_remarks` field can be renamed to `internal_remarks` in a future sprint but is not blocking) |
| `Job Card Carton` — all native fields | Pure order/spec data + board plan |
| `Customer Product Specification` | Sales team uses daily |
| `Dies` / `Dies Order` | Spec master data |
| `Carton Job Type UPS` | Child table on Carton Job Card |
| `Colour of Parts` | Child table on CP Job Card |
| `utils.py` (`get_carton_svg`) | Powers the Carton Job Card print format |
| `Carton Job Card` print format fixture | Still needed |
| `custom_product_line` on Workstation + Workstation Type | Used for planning board column filtering |
| `custom_max_width_mm`, `custom_max_colors`, `custom_max_speed_per_hour`, `custom_location_note` on Workstation | Machine spec metadata |
| `CP Planning Board` page | The starting point for all future planning work |

---

## Summary of all file changes

| Action | Path |
|---|---|
| DELETE folder | `production_log/production_log/doctype/production_entry/` |
| DELETE folder | `production_log/production_log/doctype/daily_production_schedule/` |
| DELETE folder | `production_log/production_log/doctype/schedule_line/` |
| DELETE folder | `production_log/production_log/doctype/downtime_entry/` |
| DELETE folder | `production_log/production_log/doctype/downtime_reason/` |
| DELETE folder | `production_log/production_log/doctype/waste_reason/` |
| DELETE folder | `production_log/production_log/doctype/production_stage/` |
| DELETE folder | `production_log/production_log/doctype/workstation_stage/` |
| DELETE folder | `production_log/production_log/page/daily_schedule_board/` |
| DELETE folder | `production_log/production_log/report/daily_production_summary/` |
| DELETE folder | `production_log/production_log/report/job_progress/` |
| DELETE folder | `production_log/production_log/report/machine_utilization/` |
| DELETE file | `production_log/events/production_entry.py` |
| DELETE file | `production_log/events/downtime_entry.py` |
| EDIT | `production_log/hooks.py` (3 changes — see STEP 2) |
| EDIT | `production_log/patches.txt` (add v3_0 line) |
| CREATE folder | `production_log/patches/v3_0/` |
| CREATE file | `production_log/patches/v3_0/__init__.py` (empty) |
| CREATE file | `production_log/patches/v3_0/remove_execution_layer.py` (see STEP 3) |
| ADD to repo | `production_log/production_log/page/cp_planning_board/` (from live — STEP 0) |

*End of document.*
