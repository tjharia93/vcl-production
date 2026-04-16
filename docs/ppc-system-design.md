# PPC System Design Document — Vimit Converters Ltd

## Section 1: Executive Summary & Architecture Overview

### 1.1 Purpose

This document defines the Production Planning & Control (PPC) layer for the
VCL Production app. The PPC layer sits on top of the existing Job Card
doctypes (Computer Paper, Label, Carton) and adds production execution,
scheduling, and tracking without replacing or duplicating the job card data
model.

### 1.2 Core Design Principle

> **The Job Card IS the production order.**
> Production Operations hang off the Job Card via Dynamic Link — not the
> other way around.

A Job Card already captures customer, specification, quantity, and due date.
Rather than creating a separate "Production Order" doctype that duplicates
this data, the PPC layer treats each submitted Job Card as the authoritative
production order. Production Operations — the individual manufacturing steps
(printing, slitting, collating, die-cutting, etc.) — reference back to their
parent Job Card through Frappe's Dynamic Link mechanism, allowing a single
Production Operation doctype to serve all three product-type job cards.

### 1.3 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    PPC LAYER (new)                           │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  Production  │  │  Production  │  │    PPC Dashboard  │  │
│  │  Operation   │  │  Schedule    │  │  & Reports        │  │
│  └──────┬───┬──┘  └──────┬───────┘  └───────────────────┘  │
│         │   │             │                                  │
│   Dynamic   Dynamic       │ (references operations)         │
│   Link      Link          │                                 │
├─────────┼───┼─────────────┼─────────────────────────────────┤
│         │   │             │   EXISTING JOB CARD LAYER       │
│         ▼   ▼             ▼                                 │
│  ┌────────────┐ ┌───────────┐ ┌──────────────┐             │
│  │ Job Card   │ │ Job Card  │ │ Job Card     │             │
│  │ Computer   │ │ Label     │ │ Carton       │             │
│  │ Paper      │ │           │ │              │             │
│  └─────┬──────┘ └─────┬────┘ └──────┬───────┘             │
│        │              │              │                      │
│        ▼              ▼              ▼                      │
│  ┌──────────────────────────────────────────┐              │
│  │   Customer Product Specification         │              │
│  │   (Computer Paper | Label | Carton)      │              │
│  └──────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 Section Roadmap

The remaining sections of this document cover:

**Section 2 — Production Operation Doctype:** Defines the single unified
doctype that represents one manufacturing step. Covers fields, Dynamic Link
configuration, status workflow (Not Started → In Progress → Completed → QC
Passed), and how operation templates vary by product type.

**Section 3 — Operation Templates & Sequences:** Describes predefined
operation sequences for each product type (e.g., Computer Paper: printing →
numbering → collating → wrapping; Label: printing → die-cutting → finishing)
and how they auto-generate when a Job Card is submitted.

**Section 4 — Scheduling & Capacity:** Covers machine and workstation
modelling, time estimation per operation, Gantt-based visual scheduling, and
capacity conflict detection across concurrent job cards.

**Section 5 — Status Tracking & Shop Floor Interface:** Defines the
operator-facing UI for starting/completing operations, recording actual
quantities and waste, and real-time status rollup from operations back to the
parent Job Card.

**Section 6 — Quality Control Integration:** Describes inline QC checkpoints
attached to specific operations, pass/fail/hold decisions, and how QC
failures trigger rework operations that link back to the original job card.

**Section 7 — Reporting & Analytics:** Covers production dashboards, job card
progress views, on-time delivery metrics, waste analysis, and machine
utilisation reports.

**Section 8 — Migration & Rollout Plan:** Details the phased rollout
strategy, data migration from any existing tracking spreadsheets, user
training plan, and rollback procedures.

---

## Section 2: Master Data — Extending ERPNext + New Doctypes

This section defines the foundational master data that the PPC layer depends
on. The strategy is: extend ERPNext's built-in Workstation and Workstation
Type doctypes with Custom Fields for VCL-specific machine attributes, and
create a small set of new doctypes for concepts ERPNext does not cover
(production stages, waste reasons, downtime reasons).

### 2.1 Extending ERPNext Workstation Type

ERPNext ships a `Workstation Type` doctype that groups machines by category.
VCL uses this as-is but populates it with the following machine categories:

| Workstation Type Name   | Description                              |
|-------------------------|------------------------------------------|
| Flexo Press             | Flexographic printing machines           |
| Corrugator              | Corrugated board production lines        |
| Folder Gluer            | Folding and gluing machines for cartons  |
| Numbering Machine       | Sequential numbering for computer paper  |
| Collator                | Collating/gathering for computer paper   |
| Die Cutter              | Die-cutting machines for labels/cartons  |

These are data records, not schema changes — they are created as Workstation
Type documents during setup. They become the foreign key that every physical
Workstation references.

#### 2.1.1 Custom Fields on Workstation Type

Two Custom Fields are added to the standard ERPNext `Workstation Type`
doctype via `fixtures` in `hooks.py`:

```
Doctype: Workstation Type
┌──────────────────┬───────────┬──────────────────────────────────────────┐
│ Field Name       │ Type      │ Purpose                                  │
├──────────────────┼───────────┼──────────────────────────────────────────┤
│ product_line     │ Select    │ Which product lines this type serves.    │
│                  │           │ Options: Computer Paper, Label, Carton,  │
│                  │           │ All                                      │
│                  │           │ Default: All                             │
├──────────────────┼───────────┼──────────────────────────────────────────┤
│ default_stage    │ Link      │ Link to Production Stage.                │
│                  │           │ The stage this machine type most commonly │
│                  │           │ performs (e.g., Flexo Press → Printing). │
│                  │           │ Used to pre-fill the stage field when    │
│                  │           │ assigning a workstation to an operation. │
└──────────────────┴───────────┴──────────────────────────────────────────┘
```

**Insert after field:** `description` (standard ERPNext field)
**Module:** Production Log (VCL app module)

Fixture declaration in `hooks.py`:
```python
fixtures = [
    {"dt": "Print Format", "filters": [["name", "=", "Carton Job Card"]]},
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ["Workstation Type", "Workstation"]]
        ],
    },
]
```

### 2.2 Extending ERPNext Workstation

Each physical machine on the VCL shop floor is a `Workstation` document in
ERPNext. The standard Workstation doctype already provides: name, workstation
type (Link), holiday list, working hours, and hourly cost fields. VCL adds
five Custom Fields to capture machine-specific production capabilities:

```
Doctype: Workstation
┌──────────────────────┬───────────┬──────────────────────────────────────┐
│ Field Name           │ Type      │ Purpose                              │
├──────────────────────┼───────────┼──────────────────────────────────────┤
│ product_line         │ Select    │ Which product line this machine      │
│                      │           │ serves. Options: Computer Paper,     │
│                      │           │ Label, Carton, All                   │
│                      │           │ Default: All                         │
├──────────────────────┼───────────┼──────────────────────────────────────┤
│ max_width_mm         │ Int       │ Maximum web/sheet width in mm.       │
│                      │           │ Used by scheduling to validate that  │
│                      │           │ a job's material width fits this     │
│                      │           │ machine.                             │
├──────────────────────┼───────────┼──────────────────────────────────────┤
│ max_colors           │ Int       │ Maximum number of colour stations.   │
│                      │           │ Relevant for Flexo Press machines.   │
│                      │           │ A 4-colour job cannot be assigned    │
│                      │           │ to a 2-colour press.                 │
├──────────────────────┼───────────┼──────────────────────────────────────┤
│ max_speed_per_hour   │ Int       │ Rated output per hour (sheets or     │
│                      │           │ metres depending on machine type).   │
│                      │           │ Used for time estimation in the      │
│                      │           │ scheduling engine.                   │
├──────────────────────┼───────────┼──────────────────────────────────────┤
│ location_note        │ Small Text│ Free-text note describing physical   │
│                      │           │ location on the shop floor           │
│                      │           │ (e.g., "Bay 3, near loading dock").  │
└──────────────────────┴───────────┴──────────────────────────────────────┘
```

**Insert after field:** `workstation_type` (standard ERPNext field)
**Permissions:** Inherits from Workstation — Manufacturing Manager (full),
Manufacturing User (read/write), all others (read).

### 2.3 New Doctype: Production Stage

A Production Stage represents a distinct manufacturing step in a product
line's process flow. Unlike ERPNext's Operation doctype (which is a generic
label), Production Stage is a fixture-controlled master list that encodes
the sequence position and product-line applicability of each step.

```
Doctype:        Production Stage
Module:         Production Log
Naming Rule:    Set by user (field: stage_name)
Is Submittable: No
Is Tree:        No
Track Changes:  Yes
```

#### Fields

```
┌──────────────────┬───────────┬────────┬──────────────────────────────────┐
│ Field Name       │ Type      │ Reqd   │ Purpose                          │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ stage_name       │ Data      │ Yes    │ Unique name (e.g., "Printing",   │
│                  │           │        │ "Die Cutting", "Collating").     │
│                  │           │        │ This IS the document name.       │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ product_line     │ Select    │ Yes    │ Options: Computer Paper, Label,  │
│                  │           │        │ Carton, All                      │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ sequence         │ Int       │ Yes    │ Default ordering position within │
│                  │           │        │ the product line (10, 20, 30…).  │
│                  │           │        │ Gaps allow future insertions.    │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ description      │ Small Text│ No     │ What happens at this stage.      │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ is_qc_point      │ Check     │ No     │ If checked, completing this      │
│                  │           │        │ stage requires a QC sign-off     │
│                  │           │        │ before the next stage can start. │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ workstation_stages│ Table    │ No     │ Child table: Workstation Stage.  │
│                  │           │        │ Lists workstations capable of    │
│                  │           │        │ performing this stage.           │
└──────────────────┴───────────┴────────┴──────────────────────────────────┘
```

#### Fixture Data (initial seed)

| stage_name          | product_line    | sequence | is_qc_point |
|---------------------|-----------------|----------|-------------|
| Printing            | All             | 10       | 0           |
| Numbering           | Computer Paper  | 20       | 0           |
| Collating           | Computer Paper  | 30       | 0           |
| Wrapping            | Computer Paper  | 40       | 1           |
| Die Cutting         | Label           | 20       | 0           |
| Finishing           | Label           | 30       | 1           |
| Corrugating         | Carton          | 10       | 0           |
| Creasing & Slotting | Carton          | 20       | 0           |
| Folding & Gluing    | Carton          | 30       | 0           |
| Packing             | All             | 90       | 1           |

#### Relationships

- **Linked FROM:** Production Operation (Link field → Production Stage)
- **Linked FROM:** Workstation Type (Custom Field `default_stage` → Production Stage)
- **Contains:** Workstation Stage child table rows

#### Permissions

| Role                 | Read | Write | Create | Delete | Submit |
|----------------------|------|-------|--------|--------|--------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      | —      |
| Manufacturing User   | ✓    | —     | —      | —      | —      |
| Production Log User  | ✓    | —     | —      | —      | —      |

### 2.4 New Doctype: Workstation Stage (Child Table)

This child table lives inside Production Stage and maps which physical
workstations (machines) can perform that stage. It enables the scheduling
engine to find eligible machines for a given operation.

```
Doctype:        Workstation Stage
Module:         Production Log
Is Child Table: Yes
Parent Doctype: Production Stage (field: workstation_stages)
```

#### Fields

```
┌──────────────────┬───────────┬────────┬──────────────────────────────────┐
│ Field Name       │ Type      │ Reqd   │ Purpose                          │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ workstation      │ Link      │ Yes    │ Link to Workstation.             │
│                  │           │        │ The physical machine that can    │
│                  │           │        │ perform this production stage.   │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ is_preferred     │ Check     │ No     │ If checked, this workstation is  │
│                  │           │        │ the default choice when auto-    │
│                  │           │        │ assigning machines to operations │
│                  │           │        │ at this stage.                   │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ hourly_rate      │ Int       │ No     │ Override speed for this specific │
│                  │           │        │ workstation at this stage        │
│                  │           │        │ (sheets or metres/hr). Falls     │
│                  │           │        │ back to workstation's            │
│                  │           │        │ max_speed_per_hour if blank.     │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ setup_time_mins  │ Int       │ No     │ Typical setup/changeover time in │
│                  │           │        │ minutes for this workstation at  │
│                  │           │        │ this stage.                      │
└──────────────────┴───────────┴────────┴──────────────────────────────────┘
```

#### Permissions

Inherits from parent doctype (Production Stage).

### 2.5 New Doctype: Waste Reason

Captures the standard reasons for material waste during production. Used by
Production Operation to categorize waste for reporting and analysis.

```
Doctype:        Waste Reason
Module:         Production Log
Naming Rule:    Set by user (field: reason_name)
Is Submittable: No
Track Changes:  Yes
```

#### Fields

```
┌──────────────────┬───────────┬────────┬──────────────────────────────────┐
│ Field Name       │ Type      │ Reqd   │ Purpose                          │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ reason_name      │ Data      │ Yes    │ Short label (e.g., "Setup        │
│                  │           │        │ Waste", "Misprinted", "Torn",    │
│                  │           │        │ "Off-Register"). This IS the     │
│                  │           │        │ document name.                   │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ category         │ Select    │ Yes    │ Options: Setup, Running, Material│
│                  │           │        │ Defect, Operator Error, Other    │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ description      │ Small Text│ No     │ Detailed explanation of when     │
│                  │           │        │ this reason applies.             │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ applicable_stages│ Table     │ No     │ Child table (link to Production  │
│                  │ MultiSel. │        │ Stage) limiting which stages     │
│                  │           │        │ this reason appears for. If      │
│                  │           │        │ empty, applies to all stages.    │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ enabled          │ Check     │ No     │ Default: 1. Uncheck to retire a  │
│                  │           │        │ reason without deleting it.      │
└──────────────────┴───────────┴────────┴──────────────────────────────────┘
```

#### Fixture Data (initial seed)

| reason_name      | category        |
|------------------|-----------------|
| Setup Waste      | Setup           |
| Misprinted       | Running         |
| Off-Register     | Running         |
| Torn Web         | Running         |
| Material Defect  | Material Defect |
| Wrong Die        | Operator Error  |
| Colour Mismatch  | Running         |
| Trim Waste       | Setup           |

#### Relationships

- **Linked FROM:** Production Operation waste log entries (Link → Waste Reason)

#### Permissions

| Role                 | Read | Write | Create | Delete |
|----------------------|------|-------|--------|--------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      |
| Manufacturing User   | ✓    | —     | —      | —      |
| Production Log User  | ✓    | —     | —      | —      |

### 2.6 New Doctype: Downtime Reason

Captures the standard reasons for machine downtime. Used by Production
Operation to record and categorize unplanned (and planned) stoppages.

```
Doctype:        Downtime Reason
Module:         Production Log
Naming Rule:    Set by user (field: reason_name)
Is Submittable: No
Track Changes:  Yes
```

#### Fields

```
┌──────────────────┬───────────┬────────┬──────────────────────────────────┐
│ Field Name       │ Type      │ Reqd   │ Purpose                          │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ reason_name      │ Data      │ Yes    │ Short label (e.g., "Mechanical   │
│                  │           │        │ Breakdown", "Power Outage",      │
│                  │           │        │ "Planned Maintenance"). This IS  │
│                  │           │        │ the document name.               │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ category         │ Select    │ Yes    │ Options: Mechanical, Electrical, │
│                  │           │        │ Material Shortage, Planned       │
│                  │           │        │ Maintenance, Operator Unavailable│
│                  │           │        │ Other                            │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ is_planned       │ Check     │ No     │ Default: 0. Check if this is a   │
│                  │           │        │ planned/scheduled stoppage (e.g.,│
│                  │           │        │ preventive maintenance). Planned │
│                  │           │        │ downtime is excluded from OEE    │
│                  │           │        │ availability calculations.       │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ description      │ Small Text│ No     │ Detailed explanation.            │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ enabled          │ Check     │ No     │ Default: 1. Uncheck to retire    │
│                  │           │        │ without deleting.                │
└──────────────────┴───────────┴────────┴──────────────────────────────────┘
```

#### Fixture Data (initial seed)

| reason_name            | category              | is_planned |
|------------------------|-----------------------|------------|
| Mechanical Breakdown   | Mechanical            | 0          |
| Electrical Fault       | Electrical            | 0          |
| Power Outage           | Electrical            | 0          |
| Material Shortage      | Material Shortage     | 0          |
| Planned Maintenance    | Planned Maintenance   | 1          |
| Die Changeover         | Planned Maintenance   | 1          |
| Operator Unavailable   | Operator Unavailable  | 0          |
| Waiting for QC         | Other                 | 0          |

#### Relationships

- **Linked FROM:** Production Operation downtime log entries (Link → Downtime Reason)

#### Permissions

| Role                 | Read | Write | Create | Delete |
|----------------------|------|-------|--------|--------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      |
| Manufacturing User   | ✓    | —     | —      | —      |
| Production Log User  | ✓    | —     | —      | —      |

### 2.7 Master Data Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MASTER DATA LAYER                               │
│                                                                     │
│  ┌───────────────────┐         ┌──────────────────────┐            │
│  │ Workstation Type   │         │ Production Stage     │            │
│  │ (ERPNext + custom) │         │ (new doctype)        │            │
│  │                    │         │                      │            │
│  │ + product_line     │         │  stage_name          │            │
│  │ + default_stage ───┼────────▶│  product_line        │            │
│  │                    │         │  sequence             │            │
│  └────────┬───────────┘         │  is_qc_point         │            │
│           │                     │                      │            │
│           │ type link           │  ┌────────────────┐  │            │
│           ▼                     │  │Workstation Stage│  │            │
│  ┌────────────────────┐        │  │(child table)    │  │            │
│  │ Workstation         │◀───────┤  │                │  │            │
│  │ (ERPNext + custom)  │        │  │ workstation ───┼──┘            │
│  │                     │        │  │ is_preferred   │               │
│  │ + product_line      │        │  │ hourly_rate    │               │
│  │ + max_width_mm      │        │  │ setup_time_mins│               │
│  │ + max_colors        │        │  └────────────────┘               │
│  │ + max_speed_per_hour│                                            │
│  │ + location_note     │                                            │
│  └─────────────────────┘                                            │
│                                                                     │
│  ┌───────────────────┐         ┌──────────────────────┐            │
│  │ Waste Reason       │         │ Downtime Reason      │            │
│  │ (new doctype)      │         │ (new doctype)        │            │
│  │                    │         │                      │            │
│  │  reason_name       │         │  reason_name         │            │
│  │  category          │         │  category            │            │
│  │  enabled           │         │  is_planned          │            │
│  │                    │         │  enabled             │            │
│  └───────────────────┘         └──────────────────────┘            │
│           │                              │                          │
│           │    (both linked FROM          │                          │
│           │     Production Operation)     │                          │
│           ▼                              ▼                          │
│  ┌──────────────────────────────────────────────────────┐          │
│  │            Production Operation (Section 3)          │          │
│  └──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Section 3: Daily Production Schedule + Dispatching

The Daily Production Schedule (DPS) is the priority deliverable of the PPC
layer. It answers the single most important shop-floor question every morning:
**"What runs on which machine today, and in what order?"**

The design follows a document-per-machine-per-day pattern. Each DPS document
is a sequenced list of jobs assigned to one workstation for one calendar day.
This keeps the data model flat, auditable, and easy to query — no complex
calendar engine required.

### 3.1 Daily Production Schedule Doctype

```
Doctype:        Daily Production Schedule
Module:         Production Log
Naming Rule:    Expression: DPS-.YYYY.-.#####
Is Submittable: Yes
Track Changes:  Yes
```

A submitted DPS represents the locked plan for that machine-day. Draft DPS
documents can be freely edited by planners. Amending a submitted DPS creates
a new version while preserving the audit trail of what was originally planned.

#### Fields

```
┌───────────────────────┬───────────┬────────┬─────────────────────────────┐
│ Field Name            │ Type      │ Reqd   │ Purpose                     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ workstation           │ Link      │ Yes    │ Link to Workstation.        │
│                       │           │        │ The physical machine this   │
│                       │           │        │ schedule is for.            │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ schedule_date         │ Date      │ Yes    │ The calendar day this       │
│                       │           │        │ schedule covers.            │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ workstation_type      │ Link      │ No     │ Link to Workstation Type.   │
│                       │           │        │ Auto-fetched from           │
│                       │           │        │ workstation. Read-only.     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ product_line          │ Select    │ No     │ Auto-fetched from           │
│                       │           │        │ workstation. Read-only.     │
│                       │           │        │ Options: Computer Paper,    │
│                       │           │        │ Label, Carton, All          │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ schedule_lines        │ Table     │ Yes    │ Child table: Schedule Line. │
│                       │           │        │ The ordered list of jobs    │
│                       │           │        │ for this machine-day.       │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ section_totals        │ Section   │ —      │ — Section Break —           │
│                       │ Break     │        │                             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ total_planned_qty     │ Int       │ No     │ Sum of planned_qty across   │
│                       │           │        │ all schedule lines.         │
│                       │           │        │ Read-only, calculated.      │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ total_planned_hours   │ Float     │ No     │ Sum of estimated_hours      │
│                       │           │        │ across all schedule lines.  │
│                       │           │        │ Read-only, calculated.      │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ available_hours       │ Float     │ No     │ Working hours for this      │
│                       │           │        │ workstation on this day     │
│                       │           │        │ (fetched from Workstation   │
│                       │           │        │ working hours / holiday     │
│                       │           │        │ list). Read-only.           │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ utilization_pct       │ Percent   │ No     │ total_planned_hours /       │
│                       │           │        │ available_hours × 100.      │
│                       │           │        │ Read-only, calculated.      │
│                       │           │        │ Turns red when > 100%.      │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ amended_from          │ Link      │ No     │ Standard amended_from field │
│                       │           │        │ for submittable doctypes.   │
│                       │           │        │ Read-only.                  │
└───────────────────────┴───────────┴────────┴─────────────────────────────┘
```

#### Unique Constraint

A composite unique key on (`workstation`, `schedule_date`) ensures only one
schedule document exists per machine per day. Enforced via controller
`validate()` — Frappe does not support multi-column unique constraints
natively, so this is a Python-level check with a clear error message.

#### Permissions

| Role                 | Read | Write | Create | Delete | Submit | Amend |
|----------------------|------|-------|--------|--------|--------|-------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      | ✓      | ✓     |
| Manufacturing User   | ✓    | ✓     | ✓      | —      | ✓      | —     |
| Production Log User  | ✓    | —     | —      | —      | —      | —     |

### 3.2 Schedule Line (Child Table)

Each row in the Schedule Line table represents one job assigned to the
parent DPS's machine for that day. The `sequence_order` field controls
the run order. Dynamic Link fields allow referencing any of the three
job card types without separate columns.

```
Doctype:        Schedule Line
Module:         Production Log
Is Child Table: Yes
Parent Doctype: Daily Production Schedule (field: schedule_lines)
```

#### Fields

```
┌───────────────────────┬───────────┬────────┬─────────────────────────────┐
│ Field Name            │ Type      │ Reqd   │ Purpose                     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ sequence_order        │ Int       │ Yes    │ Run order on the machine.   │
│                       │           │        │ 10, 20, 30… with gaps for   │
│                       │           │        │ reordering. The Schedule    │
│                       │           │        │ Board UI sets this via      │
│                       │           │        │ drag-and-drop.              │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ job_card_type         │ Link      │ Yes    │ Link to DocType. Options:   │
│                       │           │        │ Job Card Computer Paper,    │
│                       │           │        │ Job Card Label,             │
│                       │           │        │ Job Card Carton.            │
│                       │           │        │ First half of Dynamic Link. │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ job_card_id           │ Dynamic   │ Yes    │ The specific job card       │
│                       │ Link      │        │ document. References the    │
│                       │           │        │ doctype set in              │
│                       │           │        │ job_card_type.              │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ production_stage      │ Link      │ Yes    │ Link to Production Stage.   │
│                       │           │        │ Which manufacturing step    │
│                       │           │        │ this line represents        │
│                       │           │        │ (e.g., Printing, Die        │
│                       │           │        │ Cutting).                   │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ customer              │ Data      │ No     │ Fetched from job card.      │
│                       │           │        │ Read-only display field     │
│                       │           │        │ so planner sees the         │
│                       │           │        │ customer without opening    │
│                       │           │        │ the job card.               │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ planned_qty           │ Int       │ Yes    │ Quantity planned for this   │
│                       │           │        │ machine-day. May be less    │
│                       │           │        │ than total job qty if the   │
│                       │           │        │ job spans multiple days.    │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ estimated_hours       │ Float     │ No     │ Estimated run time in       │
│                       │           │        │ hours. Auto-calculated:     │
│                       │           │        │ planned_qty /               │
│                       │           │        │ workstation.max_speed_per   │
│                       │           │        │ _hour + setup_time. Can be  │
│                       │           │        │ manually overridden.        │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ status               │ Select    │ Yes    │ Options: Pending,           │
│                       │           │        │ In Progress, Done, Skipped. │
│                       │           │        │ Default: Pending.           │
│                       │           │        │ Updated by shop floor       │
│                       │           │        │ entries or manually.        │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ notes                 │ Small Text│ No     │ Planner notes for the       │
│                       │           │        │ operator (e.g., "Use cyan   │
│                       │           │        │ ink from batch #42",        │
│                       │           │        │ "Customer priority rush").  │
└───────────────────────┴───────────┴────────┴─────────────────────────────┘
```

#### Permissions

Inherits from parent doctype (Daily Production Schedule).

### 3.3 Production Operation Doctype (Phase 2)

> **Phase 2 — Optional.** The Daily Production Schedule (Section 3.1) is the
> Phase 1 scheduling unit. Production Operation is a finer-grained doctype
> planned for Phase 2, when VCL needs individual operation-level tracking
> with precise time windows and cross-day visibility.

Production Operation represents a single manufacturing step for a single job
card, independent of which day it runs. While the DPS groups jobs by
machine-day, a Production Operation tracks one operation across its full
lifecycle — from planned through completed — even if it spans multiple days
or moves between machines.

```
Doctype:        Production Operation
Module:         Production Log
Naming Rule:    Expression: PO-.YYYY.-.#####
Is Submittable: Yes
Track Changes:  Yes
```

#### Fields

```
┌───────────────────────┬───────────┬────────┬─────────────────────────────┐
│ Field Name            │ Type      │ Reqd   │ Purpose                     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ job_card_type         │ Link      │ Yes    │ Link to DocType. First half │
│                       │           │        │ of Dynamic Link.            │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ job_card_id           │ Dynamic   │ Yes    │ The specific job card this  │
│                       │ Link      │        │ operation belongs to.       │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ production_stage      │ Link      │ Yes    │ Link to Production Stage.   │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ workstation           │ Link      │ No     │ Link to Workstation.        │
│                       │           │        │ Assigned machine. May be    │
│                       │           │        │ blank if unscheduled.       │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ priority              │ Select    │ Yes    │ Options: Low, Normal, High, │
│                       │           │        │ Urgent. Default: Normal.    │
│                       │           │        │ Affects sort order on the   │
│                       │           │        │ Schedule Board.             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ planned_start         │ Datetime  │ No     │ Planned start time. Set by  │
│                       │           │        │ scheduler or manually.      │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ planned_end           │ Datetime  │ No     │ Planned end time.           │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ planned_qty           │ Int       │ Yes    │ Total quantity to produce.  │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ actual_start          │ Datetime  │ No     │ Set when operator begins.   │
│                       │           │        │ Read-only on form.          │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ actual_end            │ Datetime  │ No     │ Set when operator completes.│
│                       │           │        │ Read-only on form.          │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ actual_qty            │ Int       │ No     │ Rolled up from Production   │
│                       │           │        │ Entry documents. Read-only. │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ status                │ Select    │ Yes    │ Options: Not Started,       │
│                       │           │        │ In Progress, Completed,     │
│                       │           │        │ QC Passed, On Hold,         │
│                       │           │        │ Cancelled.                  │
│                       │           │        │ Default: Not Started.       │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ amended_from          │ Link      │ No     │ Standard amended_from.      │
│                       │           │        │ Read-only.                  │
└───────────────────────┴───────────┴────────┴─────────────────────────────┘
```

#### Relationships

- **Links TO:** Job Card (Dynamic Link via job_card_type + job_card_id)
- **Links TO:** Production Stage, Workstation
- **Linked FROM:** Production Entry (Section 4), Downtime Entry (Section 4)
- **Linked FROM:** Schedule Line (optional Phase 2 cross-reference)

#### Permissions

| Role                 | Read | Write | Create | Delete | Submit | Amend |
|----------------------|------|-------|--------|--------|--------|-------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      | ✓      | ✓     |
| Manufacturing User   | ✓    | ✓     | ✓      | —      | ✓      | —     |
| Production Log User  | ✓    | —     | —      | —      | —      | —     |
