# VCL Production Planner — Developer Handover (FINAL)
**App:** `production_log` (repo: `tjharia93/vcl-production`)  
**Prepared:** 2026-04-21  
**Prepared by:** Tanuj Haria (VCL) / Claude (Technical PM)  
**Supersedes:** `dev_production_planner_notes.md` (earlier draft — ignore that file)  
**Prototype:** `C:\Claude\VCL ERPNext Apps\vcl_production\vcl_production_planner_v3.html`  
**UAT doc:** `C:\Claude\VCL ERPNext Apps\vcl_production\uat_production_planner.md`  
**Scope:** Production Planning Board only — job card creation and CPS creation are separate sprints

---

## How to use this document

Open `vcl_production_planner_v3.html` in a browser first. Every architectural decision below maps directly to something visible in that prototype. The prototype is the reference implementation; the ERPNext build is a direct translation into Frappe's page structure.

---

## Part A — ERPNext Data Setup (do before writing any code)

### A1 — Workstation Type vs Workstation — what these are

This distinction is the most important concept to understand before touching the planner.

**Workstation Type = the stage of work** — a category that describes *what kind of work* happens.  
**Workstation = the physical machine or desk** — a specific piece of equipment that sits under a Workstation Type.

VCL's real machines map like this:

| Workstation Type | Workstation (physical machine) | Notes |
|---|---|---|
| Design | Design Desk | One desk currently; add more if headcount grows |
| Printing | Miyakoshi 01 | Rotary press — shared across CP and ETR |
| Printing | Miyakoshi 02 | Rotary press — shared across CP and ETR |
| Printing | Hamada 01 | Flatbed press — CP only |
| Collation | Collator 1 | CP-only stage |
| Collation | Collator 2 | CP-only stage |
| Slitting | Slitter 1 | ETR-only stage |
| Slitting | Slitter 2 | ETR-only stage |

The planning board uses the Workstation Type to determine *which column group to render* and uses the Workstation to determine *which sub-column (machine lane) to render inside it*. A Workstation Type can have 1 machine (Design Desk) or many (all the printing presses).

---

### A2 — The multi-product-line problem and the solution

**The problem:** Miyakoshi 01 prints both Computer Paper jobs and ETR/Thermal jobs. In the native ERPNext Workstation DocType, `custom_product_line` is a single Select field — it can only hold one value. This means you cannot correctly express "Miyakoshi 01 belongs to both CP and ETR", which breaks column filtering.

**The solution (confirmed by Tanuj):** Replace `custom_product_line` with a child DocType called `Workstation Product Line Tag`. This lets you add one row per product line the machine serves.

**Child DocType: `Workstation Product Line Tag`**

| Field | Type | Options |
|---|---|---|
| `parent` | (auto) | Links back to Workstation |
| `parenttype` | (auto) | = "Workstation" |
| `parentfield` | (auto) | = "custom_product_line_tags" |
| `product_line` | Select | `All`, `Computer Paper`, `ETR / Thermal` |

Add this child table to the **Workstation** DocType as a Table field named `custom_product_line_tags`.

**How to tag machines:**

| Workstation | Tags to add |
|---|---|
| Design Desk | `All` |
| Miyakoshi 01 | `Computer Paper`, `ETR / Thermal` |
| Miyakoshi 02 | `Computer Paper`, `ETR / Thermal` |
| Hamada 01 | `Computer Paper` |
| Collator 1 | `Computer Paper` |
| Collator 2 | `Computer Paper` |
| Slitter 1 | `ETR / Thermal` |
| Slitter 2 | `ETR / Thermal` |

**Workstation Type** does NOT need the child table — it still uses a single `custom_product_line` Select field with options `All`, `Computer Paper`, `ETR / Thermal`. Workstation Types are broad stages that belong to one product line or all. Only Workstations (machines) need multi-tagging.

---

### A3 — Design stage setup (confirmed: Option A)

Create a Workstation Type called **"Design"** in ERPNext:
- `custom_product_line` = `All`

Create one Workstation under it called **"Design Desk"**:
- `workstation_type` = Design
- `custom_product_line_tags` → add one row: `All`

This means Design appears automatically on both the CP tab and ETR tab without any special-casing in JavaScript. If VCL adds a second designer later, just add another Workstation under the Design Workstation Type.

---

### A4 — `product_line` stored values (confirmed exact strings)

These strings must be used exactly — case and spacing matter — everywhere they appear: DocType fields, Python filters, JavaScript comparisons, and ERPNext data entry.

| Concept | Stored value |
|---|---|
| Computer Paper department | `Computer Paper` |
| ETR/Thermal department | `ETR / Thermal` |
| Applies to all departments | `All` |

---

## Part B — DocTypes to create

### B1 — `Production Schedule Line` (PSL) — non-submittable

This is the plan record. One PSL per job × stage × workstation × date.

| Field | Type | Options / Notes |
|---|---|---|
| `job_card_doctype` | Select | `Job Card Computer Paper`, `Job Card Label`, `Job Card Carton` |
| `job_card` | Dynamic Link → `job_card_doctype` | |
| `product_line` | Select | `Computer Paper`, `ETR / Thermal` — stamped on save from the active dept tab |
| `workstation_type` | Link → Workstation Type | |
| `workstation` | Link → Workstation | |
| `date` | Date | |
| `shift` | Select | `Day`, `Evening`, `Night` |
| `operator` | Data | Person's name |
| `planned_reels` | Float | Printing stage only (input material) |
| `planned_sheets` | Float | Printing stage only (expected yield) |
| `planned_qty` | Float | Primary qty for Design (Days), Collation (Sets), Slitting (Rolls) |
| `notes` | Small Text | |
| `status` | Select | `Draft`, `Confirmed`, `Cancelled` |

PSL is **non-submittable** (Tanuj confirmed). It can be edited freely.

---

### B2 — `Production Entry` (PE) — submittable

PE records what actually happened. One PE per production run. Can also record maintenance, machine trials, or other non-job-linked events.

| Field | Type | Options / Notes |
|---|---|---|
| All PSL fields | — | Same structure as PSL |
| `actual_sheets` | Float | Printing stage — actual sheets off the machine |
| `actual_qty` | Float | Other stages — actuals for Design/Collation/Slitting |
| `is_manual` | Check | 1 = not linked to any job card (maintenance, trial, etc.) |
| `description` | Small Text | Required when `is_manual = 1` |

PE is **submittable**. Submitted PEs cannot be edited — they become the audit trail.

---

### B3 — UOM per stage — field-level spec

This is a critical UOM detail. Printing is different from all other stages.

| Stage | Planned fields | Actual fields | Why |
|---|---|---|---|
| Design | `planned_qty` (Days) | `actual_qty` (Days) | Days of design time |
| Printing | `planned_reels` + `planned_sheets` | `actual_sheets` only | Reels = paper consumed (input); Sheets = output. Actuals only track the machine's output. |
| Collation | `planned_qty` (Sets) | `actual_qty` (Sets) | |
| Slitting | `planned_qty` (Rolls) | `actual_qty` (Rolls) | |

In the planning modal, the JS renders different input fields based on `stageId`. This logic is already built into the prototype's `STAGE_QTY` config and `buildQtySection()` function. Port that directly.

---

## Part C — Frappe Page architecture

### C1 — Page file structure

```
production_log/production_log/page/cp_planning_board/
  cp_planning_board.json       ← page definition
  cp_planning_board.py         ← all whitelisted API methods
  cp_planning_board.js         ← all UI logic (port from prototype)
  cp_planning_board.html       ← minimal scaffold; JS renders everything
  cp_planning_board.css        ← styles (port from prototype)
```

**IMPORTANT — backup first:** The page `cp_planning_board` already exists on the live site from a previous incomplete build. Before making any changes: export the existing page files from the server and commit them as a backup branch. Then overwrite in-place.

---

### C2 — Scaffold HTML (cp_planning_board.html)

```html
<div id="planning-board-root"></div>
```

Everything else is rendered by JavaScript. Do not put layout in the HTML file.

---

## Part D — Python API methods (cp_planning_board.py)

All methods are `@frappe.whitelist()`. All date parameters are strings in `YYYY-MM-DD` format.

### D1 — `get_workstation_columns(product_line=None)`

This method drives dynamic column rendering. It must query the child table (`Workstation Product Line Tag`) rather than a single Select field.

```python
SHARED_WORKSTATION_TYPES = ['Printing']   # stages where machines are shared across depts

@frappe.whitelist()
def get_workstation_columns(product_line=None):
    """
    Returns Workstation Types and their Workstations, filtered by product_line.
    
    A Workstation Type with custom_product_line = 'All' appears in every dept tab.
    A Workstation appears if any row in its custom_product_line_tags child table
    matches the requested product_line OR is 'All'.
    """
    # 1. Get Workstation Types for this product line
    wt_filters = {}
    if product_line:
        wt_filters['custom_product_line'] = ['in', ['All', product_line]]

    workstation_types = frappe.db.get_all(
        'Workstation Type',
        filters=wt_filters,
        fields=['name', 'custom_product_line'],
        order_by='name'
    )

    result = []
    for wt in workstation_types:
        # 2. Get Workstations for this type that serve this product line
        # Query via the child table — a machine qualifies if it has a tag
        # matching 'All' or the requested product_line
        if product_line:
            workstations = frappe.db.sql("""
                SELECT DISTINCT w.name
                FROM `tabWorkstation` w
                INNER JOIN `tabWorkstation Product Line Tag` tag
                    ON tag.parent = w.name
                WHERE w.workstation_type = %(wt)s
                  AND tag.product_line IN ('All', %(pl)s)
                ORDER BY w.name
            """, {'wt': wt['name'], 'pl': product_line}, as_dict=True)
        else:
            workstations = frappe.db.get_all(
                'Workstation',
                filters={'workstation_type': wt['name']},
                fields=['name'],
                order_by='name'
            )

        result.append({
            'workstation_type':  wt['name'],
            'product_line':      wt['custom_product_line'],
            'workstations':      [w['name'] for w in workstations],
            'is_shared':         wt['name'] in SHARED_WORKSTATION_TYPES,
        })

    return result
```

**What the client does with this response:**
- Maps each entry to a stage column group
- `workstations` array = sub-columns (machine lanes) within that group
- If `workstations` is empty for a type → mark that column as disabled (greyed out)
- `is_shared = True` → conflict detection applies to this stage's machines

---

### D2 — `get_schedule_entries(date_from, date_to, product_line=None)`

```python
@frappe.whitelist()
def get_schedule_entries(date_from, date_to, product_line=None):
    """
    Returns all PSL and PE records in the date range,
    optionally filtered by product_line.
    """
    filters = [['date', 'between', [date_from, date_to]]]
    if product_line:
        filters.append(['product_line', '=', product_line])

    psl = frappe.db.get_all('Production Schedule Line', filters=filters, fields='*')
    pe  = frappe.db.get_all('Production Entry',         filters=filters, fields='*')
    return {'schedule': psl, 'actuals': pe}
```

Call this on page load and on every week change. Merge the results into the client-side `entries` object keyed by `name` (the Frappe document name, e.g. `PSL-0001`).

---

### D3 — `save_schedule_entry(entry)`

```python
@frappe.whitelist()
def save_schedule_entry(entry):
    """
    Create or update a Production Schedule Line.
    'entry' is a JSON dict. If entry['name'] is set, update; else create.
    Stamps product_line from the client (dept tab) on save.
    """
    entry = frappe.parse_json(entry)
    if entry.get('name'):
        doc = frappe.get_doc('Production Schedule Line', entry['name'])
        doc.update(entry)
    else:
        doc = frappe.new_doc('Production Schedule Line')
        doc.update(entry)
    doc.save()
    frappe.db.commit()
    return doc.name
```

The client must include `product_line` in the entry dict (stamped from the active dept tab at the moment of saving).

---

### D4 — `get_machine_conflicts(date_from, date_to)`

Conflict detection checks **only shared machines** (Printing). A conflict = same workstation + same date booked more than once across any department.

```python
@frappe.whitelist()
def get_machine_conflicts(date_from, date_to):
    """
    Returns workstation+date combos booked more than once in PSL,
    limited to shared workstation types (Printing).
    Checks ALL departments — CP and ETR share physical presses.
    """
    placeholders = ', '.join(['%s'] * len(SHARED_WORKSTATION_TYPES))
    sql = f"""
        SELECT
            psl.workstation,
            psl.date,
            COUNT(*) AS cnt,
            GROUP_CONCAT(DISTINCT psl.name ORDER BY psl.name) AS entry_ids,
            GROUP_CONCAT(DISTINCT psl.product_line ORDER BY psl.product_line) AS depts
        FROM `tabProduction Schedule Line` psl
        WHERE psl.date BETWEEN %(from_date)s AND %(to_date)s
          AND psl.workstation_type IN ({placeholders})
          AND psl.workstation IS NOT NULL
          AND psl.docstatus < 2
        GROUP BY psl.workstation, psl.date
        HAVING cnt > 1
    """
    # Build args: named params first, then positional for the IN clause
    args = [date_from, date_to] + SHARED_WORKSTATION_TYPES
    return frappe.db.sql(
        sql.replace('%(from_date)s', '%s').replace('%(to_date)s', '%s'),
        args,
        as_dict=True
    )
```

**Conflict behaviour (confirmed):** Warn + allow. Saving a double-booked entry fires a red toast ("⚠ Machine conflict — Miyakoshi 01 already booked on this date") but does NOT block the save. The production manager resolves conflicts manually.

---

### D5 — `get_daily_schedule(date, depts=None)`

```python
@frappe.whitelist()
def get_daily_schedule(date, depts=None):
    """
    Returns all PSL records for a specific date for the print-daily feature.
    depts: JSON list of product_line values, or None for all.
    """
    depts = frappe.parse_json(depts) if depts else None
    filters = [['date', '=', date], ['docstatus', '<', 2]]
    if depts:
        filters.append(['product_line', 'in', depts])
    return frappe.db.get_all(
        'Production Schedule Line',
        filters=filters,
        fields='*',
        order_by='product_line, workstation_type, workstation'
    )
```

---

## Part E — JavaScript architecture (cp_planning_board.js)

Port directly from the prototype. Key structures below.

### E1 — Stage config (built dynamically, not hardcoded)

```javascript
// Called on page load and on every dept tab switch
frappe.call({
    method: 'production_log.production_log.page.cp_planning_board.cp_planning_board.get_workstation_columns',
    args: { product_line: currentDeptProductLine },  // 'Computer Paper' or 'ETR / Thermal'
    callback: (r) => {
        STAGES = buildStageConfig(r.message);
        renderBoard();
    }
});

const UOM_BY_STAGE = {
    'Design':    'days',
    'Printing':  'reels/sheets',
    'Collation': 'sets',
    'Slitting':  'rolls',
};

function buildStageConfig(columns) {
    return columns.map(col => ({
        id:       col.workstation_type.toLowerCase().replace(/ /g, '_'),
        name:     col.workstation_type,
        sub:      col.workstations.length > 0 ? col.workstations : null,
        disabled: col.workstations.length === 0,   // grey out if no machines for this dept
        uom:      UOM_BY_STAGE[col.workstation_type] || '',
        isShared: col.is_shared,
    }));
}
```

---

### E2 — Entry storage principle

**Never store entries by row key.** Each entry carries all its own context. This is what makes an entry created in Week view automatically appear in Job Card view and Station view.

```javascript
// All entries keyed by unique local ID (replaced by Frappe name after save)
let entries = {};  // { 'e-1234-abc': { jobCard, stageId, mach, date, dept, ... }, ... }

// Cross-view filter — not a key lookup
function getEntriesFor(filters) {
    return Object.entries(entries).filter(([id, e]) => {
        if (filters.dept    !== undefined && e.dept    !== filters.dept)    return false;
        if (filters.stageId !== undefined && e.stageId !== filters.stageId) return false;
        if (filters.mach    !== undefined && (e.mach||'_') !== (filters.mach||'_')) return false;
        if (filters.jobCard !== undefined && e.jobCard !== filters.jobCard) return false;
        if (filters.date    !== undefined && e.date    !== filters.date)    return false;
        return true;
    });
}
```

**How each view queries entries:**

| View | Filter used |
|---|---|
| Week view | `{ dept, stageId, mach, date: isoDateString }` |
| Job Card view | `{ dept, stageId, mach, jobCard: 'CP-2026-041' }` |
| Station view | `{ dept, stageId, mach }` — all dates for this machine |

---

### E3 — Stage-specific quantity config (STAGE_QTY)

Port this exactly. The modal renders different input fields depending on the stage.

```javascript
const STAGE_QTY = {
    design: {
        planned: [{ id:'fPlannedDays',   label:'Planned Days',   uom:'days'   }],
        actual:  [{ id:'fActualDays',    label:'Actual Days',    uom:'days'   }],
    },
    printing: {
        // Two planned fields: input material + expected yield
        planned: [
            { id:'fPlannedReels',  label:'Planned Reels',  uom:'reels'  },
            { id:'fPlannedSheets', label:'Planned Sheets',  uom:'sheets' },
        ],
        // Actuals: only sheets — machine output is what gets measured
        actual:  [{ id:'fActualSheets', label:'Actual Sheets', uom:'sheets' }],
    },
    collation: {
        planned: [{ id:'fPlannedSets',   label:'Planned Sets',   uom:'sets'   }],
        actual:  [{ id:'fActualSets',    label:'Actual Sets',    uom:'sets'   }],
    },
    slitting: {
        planned: [{ id:'fPlannedRolls',  label:'Planned Rolls',  uom:'rolls'  }],
        actual:  [{ id:'fActualRolls',   label:'Actual Rolls',   uom:'rolls'  }],
    },
};
```

Note: the prototype uses shortened stage IDs (`print`, `collate`, `slit`). When porting to ERPNext, use the full Workstation Type names lowercased and underscored as the key, or keep a mapping between the two. The `buildStageConfig()` function already builds the `id` field using `.toLowerCase().replace(/ /g,'_')` — so "Printing" becomes `printing`, "Workstation Type" becomes `workstation_type`. Match your `STAGE_QTY` keys to this.

---

### E4 — Machine conflict detection (client-side)

```javascript
const SHARED_MACHINES = ['printing'];  // stage IDs where conflicts matter

function buildConflictMap() {
    const map = new Map();
    Object.entries(entries).forEach(([id, e]) => {
        if (!SHARED_MACHINES.includes(e.stageId)) return;
        if (!e.date || e.isManual) return;
        const key = `${e.stageId}__${e.mach}__${e.date}`;
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(id);
    });
    const conflicts = new Map();
    map.forEach((ids, key) => { if (ids.length > 1) conflicts.set(key, ids); });
    return conflicts;
}
```

After every save, call `buildConflictMap()` and re-render. Conflicted cells get amber background + "Double-booked · CP + ETR" chip. Conflicted entry blocks get amber outline. A conflict badge appears in the header.

---

### E5 — Print daily schedule

Use `URL.createObjectURL(blob)` — NOT `window.open(url)` with a direct blob string, which gets popup-blocked.

```javascript
function printSchedule(date, depts) {
    frappe.call({
        method: 'production_log.production_log.page.cp_planning_board.cp_planning_board.get_daily_schedule',
        args: { date, depts: JSON.stringify(depts) },
        callback: (r) => {
            const html = buildPrintHTML(date, r.message);
            const blob = new Blob([html], { type: 'text/html' });
            const url  = URL.createObjectURL(blob);
            const w    = window.open(url, '_blank');
            if (w) {
                w.addEventListener('load', () => { w.print(); URL.revokeObjectURL(url); });
            } else {
                // Fallback if popup blocked — download instead
                const a = document.createElement('a');
                a.href = url;
                a.download = `VCL_Schedule_${date}.html`;
                a.click();
                URL.revokeObjectURL(url);
            }
        }
    });
}
```

The `buildPrintHTML()` function generates an A4 landscape document with: VCL letterhead, one section per department, columns for Stage / Machine / Job Card / Planned Qty / Shift / Operator / Type / Notes / Sign-off box, plus signature lines for Production Manager and Floor Supervisor. Refer to the prototype's `buildPrintHTML()` function for the full template.

---

## Part F — Open questions — all confirmed

These were the open questions from the original draft. All resolved.

| # | Question | Decision |
|---|---|---|
| F1 | Where to store `product_line`? On PSL/PE or derive at read time? | **Store on PSL/PE.** Stamp from the active dept tab on save. Simpler and works cleanly with SQL filters. |
| F2 | Should PSL be submittable? | **No — non-submittable.** PSL is a planning aid, editable at any time. Only PE (actuals) is submittable. |
| F3 | Who can edit/delete entries? | **Production Users:** create and edit PSL. **Production Manager:** additionally can delete PSL and submit/cancel PE. Set via Frappe Role Permissions on both DocTypes. |
| F4 | Manual entries visible to all users or managers only? | **All production users** can see and create manual entries. The `is_manual` flag is just for display/reporting purposes. |
| F5 | Conflict detection — block save or warn? | **Warn + allow.** Non-blocking red toast fires immediately on save if a conflict is detected. Easier on the production floor. |
| F6 | Exact stored string for ETR/Thermal? | **`ETR / Thermal`** — with a space before and after the slash. Use this exact string everywhere: DocType options, Python filters, JS comparisons, and when entering data in ERPNext. |

---

## Part G — Corrections to the developer's earlier plan

If you received a separate implementation plan document, note these corrections:

**G1 — Child table, not single Select, for Workstation multi-tagging**  
The earlier plan mentioned `custom_product_line = ['in', ['All', product_line]]` on the Workstation DocType. This only works if a workstation belongs to one product line. Miyakoshi 01 belongs to two (`Computer Paper` and `ETR / Thermal`). Replace the single Select with the `Workstation Product Line Tag` child table. The updated `get_workstation_columns()` in Part D1 above handles this correctly via a JOIN on the child table.

**G2 — `SHARED_WORKSTATION_TYPES` constant, not hardcoded string**  
The earlier plan had `workstation_type = 'Printing'` hardcoded in the SQL for conflict detection. Use the `SHARED_WORKSTATION_TYPES = ['Printing']` Python constant so it's easy to extend if VCL adds more shared stages later.

**G3 — ETR / Thermal option string**  
The earlier plan listed `ETR / Thermal` as two separate options in some places. It is a single option string: `ETR / Thermal` (with spaces around the slash). Confirm this matches exactly what is already in ERPNext's Workstation DocType options before writing any data.

**G4 — Design Workstation Type tagged `All`, not `Computer Paper`**  
Design work applies to both departments. The Design Workstation Type must have `custom_product_line = All`. If it is set to `Computer Paper`, it will not appear on the ETR tab.

**G5 — `get_workstation_columns` must return `is_shared` flag**  
The client uses this to know which stages to run conflict detection on. Add `'is_shared': wt['name'] in SHARED_WORKSTATION_TYPES` to the result dict as shown in Part D1.

---

## Part H — Database migration / patch (patch_v5_0.py)

This patch creates the new child DocType and migrates existing data. Run after deploying the new DocType JSON files.

```python
# File: production_log/patches/patch_v5_0.py
import frappe

def execute():
    # 1. Seed the Design Workstation Type if it doesn't exist
    if not frappe.db.exists('Workstation Type', 'Design'):
        wt = frappe.new_doc('Workstation Type')
        wt.name = 'Design'
        wt.custom_product_line = 'All'
        wt.insert(ignore_permissions=True)

    # 2. Seed the Design Desk workstation if it doesn't exist
    if not frappe.db.exists('Workstation', 'Design Desk'):
        ws = frappe.new_doc('Workstation')
        ws.workstation_name = 'Design Desk'
        ws.workstation_type = 'Design'
        ws.insert(ignore_permissions=True)
        # Add the 'All' product line tag
        ws.append('custom_product_line_tags', {'product_line': 'All'})
        ws.save(ignore_permissions=True)

    # 3. Migrate existing Workstations that have custom_product_line set as a Data field
    # (only needed if an older version of the customisation stored a single value)
    existing_ws = frappe.db.get_all(
        'Workstation',
        fields=['name', 'custom_product_line'],
        filters=[['custom_product_line', '!=', '']]
    )
    for ws_data in existing_ws:
        ws = frappe.get_doc('Workstation', ws_data['name'])
        existing_tags = [row.product_line for row in ws.get('custom_product_line_tags', [])]
        old_val = ws_data.get('custom_product_line', '')
        if old_val and old_val not in existing_tags:
            ws.append('custom_product_line_tags', {'product_line': old_val})
            ws.save(ignore_permissions=True)

    frappe.db.commit()
```

---

## Part I — Files to create / modify

| Action | File | Notes |
|---|---|---|
| CREATE | `production_log/doctype/workstation_product_line_tag/workstation_product_line_tag.json` | Child DocType |
| CREATE | `production_log/doctype/workstation_product_line_tag/__init__.py` | Empty |
| CREATE | `production_log/doctype/production_schedule_line/production_schedule_line.json` | New PSL DocType |
| CREATE | `production_log/doctype/production_schedule_line/production_schedule_line.py` | Minimal |
| CREATE | `production_log/doctype/production_entry/production_entry.json` | New PE DocType |
| CREATE | `production_log/doctype/production_entry/production_entry.py` | Minimal |
| MODIFY | `production_log/page/cp_planning_board/cp_planning_board.py` | Replace with new API methods |
| MODIFY | `production_log/page/cp_planning_board/cp_planning_board.js` | Replace with port of prototype |
| MODIFY | `production_log/page/cp_planning_board/cp_planning_board.css` | Replace with port of prototype |
| MODIFY | `production_log/page/cp_planning_board/cp_planning_board.html` | Replace with scaffold only |
| CREATE | `production_log/patches/patch_v5_0.py` | Migration patch |
| MODIFY | `production_log/patches.txt` | Add `production_log.patches.patch_v5_0.execute` |

---

## Part J — Sprint order

Execute in this order. Do not skip steps.

| # | Task | Est. | Notes |
|---|---|---|---|
| 1 | **BACKUP** existing `cp_planning_board` page files from live site | 15 min | Non-negotiable first step |
| 2 | Add `Workstation Product Line Tag` child DocType to ERPNext (via JSON) | 30 min | Part H |
| 3 | Add `custom_product_line_tags` Table field to Workstation DocType | 20 min | |
| 4 | Run `patch_v5_0` — seeds Design/Design Desk, migrates existing WS data | 20 min | Verify in ERPNext UI after |
| 5 | Tag all Workstations with correct product line rows (see A2 table) | 30 min | Manual data entry in ERPNext |
| 6 | Confirm exact `product_line` string values on all Workstation Types | 15 min | Must match `Computer Paper` / `ETR / Thermal` / `All` exactly |
| 7 | Create `Production Schedule Line` DocType | 1 hr | Non-submittable |
| 8 | Create `Production Entry` DocType | 1 hr | Submittable |
| 9 | Write all whitelisted Python methods (`get_workstation_columns`, `get_schedule_entries`, `save_schedule_entry`, `get_machine_conflicts`, `get_daily_schedule`) | 2 hr | |
| 10 | Port prototype HTML/JS/CSS to Frappe page | 3–4 hr | Direct translation of `vcl_production_planner_v3.html` |
| 11 | Wire up `get_workstation_columns` → dynamic columns on load + dept switch | 1 hr | |
| 12 | Wire up `save_schedule_entry` → save from modal | 1 hr | |
| 13 | Wire up `get_schedule_entries` → load entries on page load + week change | 1 hr | |
| 14 | Wire up `get_machine_conflicts` → conflict highlighting + badge | 1 hr | |
| 15 | Wire up `get_daily_schedule` → print daily schedule button | 30 min | |
| 16 | Set Frappe Role Permissions on PSL and PE DocTypes | 30 min | Per F3 decision |
| 17 | UAT against live site | See `uat_production_planner.md` | 80 test cases across 17 sections |

---

## Part K — Reference files

| File | Purpose |
|---|---|
| `C:\Claude\VCL ERPNext Apps\vcl_production\vcl_production_planner_v3.html` | **The reference prototype** — open in browser, this is what you are building |
| `C:\Claude\VCL ERPNext Apps\vcl_production\uat_production_planner.md` | 80 UAT test cases — run after build |
| `C:\Claude\VCL ERPNext Apps\vcl_production\dev_cleanup_execution_layer.md` | Earlier sprint — prerequisite cleanup already done |
| `C:\Claude\VCL ERPNext Apps\vcl_production\dev_rebuild_production_workflow.md` | Authoritative field spec for job card DocTypes |

*End of developer handover. Questions → Tanuj Haria (t.haria93@gmail.com).*
