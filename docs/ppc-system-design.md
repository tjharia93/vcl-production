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

### 3.4 Daily Schedule Board (Custom Frappe Page)

The Daily Schedule Board is the primary planner interface — a custom Frappe
Page (not a doctype view) that renders a Kanban-by-machine-by-day layout.
It provides drag-and-drop dispatching without requiring planners to open
individual DPS documents.

#### Page Details

```
Page Name:      daily-schedule-board
Module:         Production Log
Route:          /app/daily-schedule-board
Type:           Custom Frappe Page (Python + JS)
```

#### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Daily Schedule Board              [◀ 2026-04-16 ▶]  [+ Add Job]  │
├─────────────────┬─────────────────┬─────────────────┬───────────────┤
│ Flexo Press #1  │ Flexo Press #2  │ Die Cutter #1   │ Collator #1  │
│ (Label)         │ (Carton)        │ (Label)         │ (Comp Paper) │
│ 6.5h / 8h = 81% │ 7.2h / 8h = 90%│ 4.0h / 8h = 50%│ 3.5h / 8h   │
├─────────────────┼─────────────────┼─────────────────┼───────────────┤
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────┐ │ ┌───────────┐│
│ │ JC-L-00042  │ │ │ JC-C-00018  │ │ │ JC-L-00042  │ │ │ JC-CP-031 ││
│ │ Acme Ltd    │ │ │ Bidco       │ │ │ Acme Ltd    │ │ │ KCB Bank  ││
│ │ Printing    │ │ │ Printing    │ │ │ Die Cutting │ │ │ Collating ││
│ │ 5,000 pcs   │ │ │ 2,000 pcs   │ │ │ 5,000 pcs   │ │ │ 10,000   ││
│ │ ~2.5h       │ │ │ ~3.0h       │ │ │ ~2.0h       │ │ │ ~2.0h    ││
│ │ ● Pending   │ │ │ ● Pending   │ │ │ ● Pending   │ │ │ ● Pending││
│ └─────────────┘ │ └─────────────┘ │ └─────────────┘ │ └───────────┘│
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────┐ │              │
│ │ JC-L-00039  │ │ │ JC-C-00015  │ │ │ JC-L-00039  │ │              │
│ │ Unilever    │ │ │ EABL        │ │ │ Unilever    │ │              │
│ │ Printing    │ │ │ Printing    │ │ │ Die Cutting │ │              │
│ │ 8,000 pcs   │ │ │ 4,200 pcs   │ │ │ 8,000 pcs   │ │              │
│ │ ~4.0h       │ │ │ ~4.2h       │ │ │ ~2.0h       │ │              │
│ │ ● Pending   │ │ │ ● Pending   │ │ │ ● Pending   │ │              │
│ └─────────────┘ │ └─────────────┘ │ └─────────────┘ │              │
│   [+ Add Line]  │   [+ Add Line]  │   [+ Add Line]  │  [+ Add Line]│
└─────────────────┴─────────────────┴─────────────────┴───────────────┘
```

#### Key Interactions

| Action                  | Behaviour                                       |
|-------------------------|-------------------------------------------------|
| **Date navigation**     | ◀ / ▶ arrows or date picker. Loads/creates DPS  |
|                         | documents for each visible workstation on that   |
|                         | date. Missing DPS docs are created as Draft.     |
| **Drag card vertically**| Reorders within the same machine column.         |
|                         | Updates `sequence_order` on Schedule Line rows.  |
| **Drag card across**    | Moves job to a different machine. Removes the    |
|                         | Schedule Line from source DPS and adds to target |
|                         | DPS. Validates machine capability (product_line, |
|                         | max_width_mm, max_colors) before allowing drop.  |
| **Click card**          | Opens a side panel with Schedule Line details,   |
|                         | job card summary, and quick-edit for planned_qty,|
|                         | notes, and status.                               |
| **+ Add Job**           | Opens a dialog to search submitted Job Cards     |
|                         | (filtered by product line matching the machine). |
|                         | Selecting a job adds a Schedule Line to the      |
|                         | machine's DPS with the next sequence_order.      |
| **+ Add Line**          | Same as + Add Job but scoped to that column's    |
|                         | machine.                                         |
| **Status change**       | Click status badge to cycle: Pending → In        |
|                         | Progress → Done. Skipped available via dropdown. |
| **Utilization bar**     | Each column header shows a progress bar:         |
|                         | total_planned_hours / available_hours. Turns     |
|                         | amber > 85%, red > 100%.                         |

#### Filters & Controls

- **Product line filter:** Show only machines for a specific product line
  (Computer Paper, Label, Carton, or All).
- **Workstation type filter:** Show only specific machine types (e.g., only
  Flexo Presses).
- **Status filter:** Hide completed/skipped lines to focus on pending work.
- **Search:** Filter cards by job card ID or customer name.

#### Technical Implementation Notes

- Built as a Frappe Page (`production_log/production_log/page/daily_schedule_board/`).
- Uses `frappe.call` to load DPS documents for the selected date.
- Drag-and-drop via SortableJS (already bundled with Frappe).
- Each card mutation fires a debounced API call to update the underlying
  DPS document — no explicit save button needed.
- Column widths are equal; horizontal scroll if > 6 machines visible.
- Mobile-responsive: collapses to single-column with machine tabs.

#### Permissions

Page visibility follows the same roles as Daily Production Schedule:
Manufacturing Manager and Manufacturing User can interact; Production Log
User gets read-only view (drag disabled, status badges non-clickable).

### 3.5 Phase 3: Gantt View & Machine Queue Page

> **Phase 3 — Future.** These views are planned but not part of the initial
> PPC deliverable. They are documented here to ensure the data model
> supports them without schema changes.

#### 3.5.1 Gantt View

A time-axis Gantt chart showing Production Operations (Section 3.3) as
horizontal bars on a workstation-per-row grid. This requires Phase 2's
Production Operation doctype with `planned_start` and `planned_end`
timestamps.

```
Machine        │ 06:00  08:00  10:00  12:00  14:00  16:00  18:00
───────────────┼──────────────────────────────────────────────────
Flexo Press #1 │ ██JC-L-042██  ████JC-L-039████      ░░░░░░░░
Flexo Press #2 │ ████████JC-C-018████████  ██JC-C-015██████████
Die Cutter #1  │ ░░░░░░  ██JC-L-042██  ██JC-L-039██  ░░░░░░░░
Collator #1    │ ██JC-CP-031██  ░░░░░░░░░░░░░░░░░░░░  ░░░░░░░░
───────────────┼──────────────────────────────────────────────────
                 █ = Scheduled job    ░ = Available capacity
```

**Data source:** Production Operation documents filtered by date range.
**Interaction:** Click bar to open operation details; drag bar ends to
adjust planned_start / planned_end; drag entire bar to move to different
machine (same validation as Schedule Board).
**Implementation:** Frappe Gantt library (built-in) or frappe.ui.GanttChart.
**Prerequisite:** Phase 2 Production Operation doctype must be live.

#### 3.5.2 Machine Queue Page

A per-machine view showing all upcoming work across multiple days — the
"order book" for a single workstation. Useful for operators and supervisors
who manage one machine or area.

```
Machine Queue: Flexo Press #1
┌──────────┬────────────────┬──────────┬──────────┬─────────┬────────┐
│ Date     │ Job Card       │ Customer │ Stage    │ Qty     │ Status │
├──────────┼────────────────┼──────────┼──────────┼─────────┼────────┤
│ Today    │ JC-L-00042     │ Acme Ltd │ Printing │ 5,000   │Pending │
│ Today    │ JC-L-00039     │ Unilever │ Printing │ 8,000   │Pending │
│ Tomorrow │ JC-L-00045     │ KWAL     │ Printing │ 3,000   │Pending │
│ Tomorrow │ JC-C-00020     │ Bidco    │ Printing │ 6,000   │Pending │
│ 18 Apr   │ JC-L-00041     │ BAT      │ Printing │ 12,000  │Pending │
└──────────┴────────────────┴──────────┴──────────┴─────────┴────────┘
```

**Data source:** Schedule Lines from DPS documents where `workstation`
matches, ordered by `schedule_date` then `sequence_order`.
**Implementation:** Script Report or custom Frappe Page with list view.
**Prerequisite:** Only requires Phase 1 DPS — no dependency on Phase 2.

### 3.6 Section 3 Summary: Phased Delivery

| Phase   | Deliverable                  | Depends On     | Status    |
|---------|------------------------------|----------------|-----------|
| Phase 1 | Daily Production Schedule    | Section 2 done | Priority  |
| Phase 1 | Schedule Line child table    | DPS doctype    | Priority  |
| Phase 1 | Daily Schedule Board page    | DPS doctype    | Priority  |
| Phase 2 | Production Operation doctype | Phase 1 live   | Planned   |
| Phase 3 | Gantt View                   | Phase 2 live   | Future    |
| Phase 3 | Machine Queue Page           | Phase 1 live   | Future    |

---

## Section 4: Production Actuals + Tracking

The scheduling layer (Section 3) answers "what should run where today." This
section defines how the shop floor records **what actually happened** —
quantities produced, waste generated, and downtime incurred. These actuals
feed back into job card progress, machine utilization metrics, and the KPI
dashboard.

Two submittable doctypes capture actuals: **Production Entry** (output per
job per machine) and **Downtime Entry** (stoppages per machine). Both link
back to the Daily Production Schedule that governs the machine-day, creating
a clean planned-vs-actual comparison.

### 4.1 Production Entry Doctype

A Production Entry records the actual output of one job on one machine for
one shift or time window. Operators create these as work progresses — either
via the Shop Floor Terminal (Phase 2) or directly in the Frappe desk.

```
Doctype:        Production Entry
Module:         Production Log
Naming Rule:    Expression: PE-.YYYY.-.#####
Is Submittable: Yes
Track Changes:  Yes
```

#### Fields

```
┌───────────────────────┬───────────┬────────┬─────────────────────────────┐
│ Field Name            │ Type      │ Reqd   │ Purpose                     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ section_job           │ Section   │ —      │ — Job Reference —           │
│                       │ Break     │        │                             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ job_card_type         │ Link      │ Yes    │ Link to DocType. Options:   │
│                       │           │        │ Job Card Computer Paper,    │
│                       │           │        │ Job Card Label,             │
│                       │           │        │ Job Card Carton.            │
│                       │           │        │ First half of Dynamic Link. │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ job_card_id           │ Dynamic   │ Yes    │ The specific job card this  │
│                       │ Link      │        │ entry records output for.   │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ production_stage      │ Link      │ Yes    │ Link to Production Stage.   │
│                       │           │        │ Which step was performed    │
│                       │           │        │ (e.g., Printing, Collating).│
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ customer              │ Data      │ No     │ Fetched from job card.      │
│                       │           │        │ Read-only display field.    │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ section_machine       │ Section   │ —      │ — Machine & Schedule —      │
│                       │ Break     │        │                             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ workstation           │ Link      │ Yes    │ Link to Workstation.        │
│                       │           │        │ The machine that produced   │
│                       │           │        │ this output.                │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ daily_production      │ Link      │ No     │ Link to Daily Production    │
│ _schedule             │           │        │ Schedule. Auto-set if a DPS │
│                       │           │        │ exists for this workstation │
│                       │           │        │ + date. Links actual back   │
│                       │           │        │ to planned.                 │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ section_time          │ Section   │ —      │ — Time & Shift —            │
│                       │ Break     │        │                             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ start_time            │ Datetime  │ Yes    │ When the run started.       │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ end_time              │ Datetime  │ Yes    │ When the run ended.         │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ duration_hours        │ Float     │ No     │ Calculated: (end_time -     │
│                       │           │        │ start_time) in hours.       │
│                       │           │        │ Read-only.                  │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ shift                 │ Select    │ No     │ Options: Day, Night.        │
│                       │           │        │ Auto-detected from          │
│                       │           │        │ start_time or set manually. │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ operator              │ Link      │ No     │ Link to Employee (ERPNext). │
│                       │           │        │ The machine operator for    │
│                       │           │        │ this run.                   │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ section_output        │ Section   │ —      │ — Output & Waste —          │
│                       │ Break     │        │                             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ qty_produced          │ Int       │ Yes    │ Good output quantity.       │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ qty_waste             │ Int       │ No     │ Waste quantity. Default: 0. │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ waste_reason          │ Link      │ No     │ Link to Waste Reason.       │
│                       │           │        │ Required if qty_waste > 0.  │
│                       │           │        │ Enforced in validate().     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ waste_pct             │ Percent   │ No     │ Calculated: qty_waste /     │
│                       │           │        │ (qty_produced + qty_waste)  │
│                       │           │        │ × 100. Read-only.           │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ section_notes         │ Section   │ —      │ — Notes —                   │
│                       │ Break     │        │                             │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ notes                 │ Small Text│ No     │ Operator remarks (e.g.,     │
│                       │           │        │ "Ink change mid-run",       │
│                       │           │        │ "Paper jam at 2,500 pcs").  │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ amended_from          │ Link      │ No     │ Standard amended_from.      │
│                       │           │        │ Read-only.                  │
└───────────────────────┴───────────┴────────┴─────────────────────────────┘
```

#### Auto-Update: Job Card Progress

On submit, the Production Entry controller rolls up totals to the parent
job card. A virtual (non-stored) or Custom Field `total_qty_produced` on
each job card type aggregates all submitted Production Entries for that
job card and stage:

```python
# production_entry.py — on_submit / on_cancel
def update_job_card_progress(self):
    total = frappe.db.sql("""
        SELECT SUM(qty_produced) FROM `tabProduction Entry`
        WHERE job_card_type = %s AND job_card_id = %s
          AND production_stage = %s AND docstatus = 1
    """, (self.job_card_type, self.job_card_id, self.production_stage))
    # Update progress field on the job card
```

This avoids modifying the existing job card doctype schema — progress is
fetched on demand or cached in a Custom Field added via fixtures.

#### Relationships

- **Links TO:** Job Card (Dynamic Link via job_card_type + job_card_id)
- **Links TO:** Workstation, Production Stage, Waste Reason
- **Links TO:** Daily Production Schedule (optional back-reference)
- **Links TO:** Employee (operator)

#### Permissions

| Role                 | Read | Write | Create | Delete | Submit | Amend |
|----------------------|------|-------|--------|--------|--------|-------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      | ✓      | ✓     |
| Manufacturing User   | ✓    | ✓     | ✓      | —      | ✓      | —     |
| Production Log User  | ✓    | ✓     | ✓      | —      | ✓      | —     |

> Note: Production Log User gets create/submit here — operators on the shop
> floor need to record output without elevated Manufacturing permissions.

### 4.2 Downtime Entry Doctype

A Downtime Entry records a period when a machine was not producing. It is
linked to the machine (not to a specific job card) because downtime affects
the machine's availability regardless of which job was scheduled.

```
Doctype:        Downtime Entry
Module:         Production Log
Naming Rule:    Expression: DT-.YYYY.-.#####
Is Submittable: Yes
Track Changes:  Yes
```

#### Fields

```
┌───────────────────────┬───────────┬────────┬─────────────────────────────┐
│ Field Name            │ Type      │ Reqd   │ Purpose                     │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ workstation           │ Link      │ Yes    │ Link to Workstation.        │
│                       │           │        │ The machine that was down.  │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ downtime_reason       │ Link      │ Yes    │ Link to Downtime Reason.    │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ daily_production      │ Link      │ No     │ Link to Daily Production    │
│ _schedule             │           │        │ Schedule. Auto-set if a DPS │
│                       │           │        │ exists for this workstation │
│                       │           │        │ + date. Used for planned-   │
│                       │           │        │ vs-actual reporting.        │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ start_time            │ Datetime  │ Yes    │ When downtime began.        │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ end_time              │ Datetime  │ No     │ When downtime ended. Blank  │
│                       │           │        │ if machine is still down.   │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ duration_minutes      │ Float     │ No     │ Calculated: (end_time -     │
│                       │           │        │ start_time) in minutes.     │
│                       │           │        │ Read-only. Null while       │
│                       │           │        │ end_time is blank.          │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ is_planned            │ Check     │ No     │ Fetched from downtime_reason│
│                       │           │        │ .is_planned. Read-only.     │
│                       │           │        │ Planned downtime is excluded│
│                       │           │        │ from OEE availability.      │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ operator              │ Link      │ No     │ Link to Employee. Who       │
│                       │           │        │ reported the downtime.      │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ notes                 │ Small Text│ No     │ Details (e.g., "Bearing     │
│                       │           │        │ seized on impression        │
│                       │           │        │ cylinder, maintenance       │
│                       │           │        │ called").                   │
├───────────────────────┼───────────┼────────┼─────────────────────────────┤
│ amended_from          │ Link      │ No     │ Standard amended_from.      │
│                       │           │        │ Read-only.                  │
└───────────────────────┴───────────┴────────┴─────────────────────────────┘
```

#### Validation Rules

- `end_time` must be after `start_time` (if set).
- `end_time` is required before submit — you cannot submit an open downtime
  entry. Draft entries with blank `end_time` represent ongoing downtime.
- `duration_minutes` is recalculated on every save and on submit.

#### Relationships

- **Links TO:** Workstation, Downtime Reason, Daily Production Schedule
- **Links TO:** Employee (operator)
- **Used BY:** OEE calculation, Machine Utilization report

#### Permissions

| Role                 | Read | Write | Create | Delete | Submit | Amend |
|----------------------|------|-------|--------|--------|--------|-------|
| Manufacturing Manager| ✓    | ✓     | ✓      | ✓      | ✓      | ✓     |
| Manufacturing User   | ✓    | ✓     | ✓      | —      | ✓      | —     |
| Production Log User  | ✓    | ✓     | ✓      | —      | ✓      | —     |

### 4.3 Shop Floor Terminal (Phase 2)

> **Phase 2.** A tablet/mobile-optimized custom Frappe Page for operators
> to record production and downtime without navigating full desk forms.

#### Page Details

```
Page Name:      shop-floor-terminal
Module:         Production Log
Route:          /app/shop-floor-terminal
Type:           Custom Frappe Page (Python + JS)
```

#### Wireframe

```
┌─────────────────────────────────────────────────────┐
│  Shop Floor Terminal           Flexo Press #1  [▼]  │
│  Operator: John Kamau          Shift: Day           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Current Job: JC-L-00042 — Acme Ltd — Printing      │
│  Planned: 5,000    Produced so far: 3,200           │
│  ████████████████████████░░░░░░░░  64%              │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │  📦 Log      │  │  ⛔ Report   │                 │
│  │  Output      │  │  Downtime    │                 │
│  └──────────────┘  └──────────────┘                 │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │  ✅ Complete  │  │  ⏭ Next     │                 │
│  │  Job         │  │  Job         │                 │
│  └──────────────┘  └──────────────┘                 │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Recent entries:                                    │
│  PE-2026-00142  1,200 pcs  08:00–10:15  ✓          │
│  PE-2026-00139  2,000 pcs  10:30–13:00  ✓          │
│  DT-2026-00031  15 min     13:00–13:15  Ink change │
└─────────────────────────────────────────────────────┘
```

#### Key Interactions

| Action             | Behaviour                                          |
|--------------------|----------------------------------------------------|
| **Machine select** | Dropdown at top right. Filters today's DPS to show |
|                    | only jobs for this machine. Remembers last choice  |
|                    | via localStorage.                                  |
| **Log Output**     | Opens a simplified dialog: qty_produced, qty_waste, |
|                    | waste_reason (if waste > 0). Start/end time        |
|                    | default to last entry's end_time → now. Creates    |
|                    | and submits a Production Entry.                    |
| **Report Downtime**| Opens dialog: downtime_reason, start_time (defaults |
|                    | to now). end_time left blank (ongoing). Creates a  |
|                    | Draft Downtime Entry. Closing downtime sets        |
|                    | end_time and submits.                              |
| **Complete Job**   | Sets the Schedule Line status to Done. Advances    |
|                    | "Current Job" to the next Pending line.            |
| **Next Job**       | Skips to next Pending Schedule Line without marking |
|                    | current as Done (marks it Skipped instead).        |

#### Technical Notes

- Large touch targets (min 48×48 dp) for gloved-hand operation.
- Auto-refreshes every 60 seconds to pick up schedule changes.
- Works offline-first: queues entries in localStorage, syncs when
  connection returns (Frappe's built-in offline support).
- Operator identified via Frappe session user → Employee link.

### 4.4 Production Dashboard

A Frappe Workspace dashboard providing at-a-glance KPIs via Number Cards
and Charts. Accessible from the Production Log module sidebar.

#### Number Cards

| Card Title              | Value Source                              | Color Logic          |
|-------------------------|------------------------------------------|----------------------|
| Today's Output          | SUM(qty_produced) from Production Entry  | —                    |
|                         | WHERE posting_date = today               |                      |
| Today's Waste %         | SUM(qty_waste) / SUM(qty_produced +      | Green ≤ 3%,          |
|                         | qty_waste) × 100, today                  | Amber ≤ 5%, Red > 5% |
| Machines Running        | COUNT(DISTINCT workstation) from          | —                    |
|                         | Production Entry WHERE today AND         |                      |
|                         | end_time is NULL or within last 2h       |                      |
| Machines Down           | COUNT(DISTINCT workstation) from          | Red if > 0           |
|                         | Downtime Entry WHERE end_time IS NULL    |                      |
| Schedule Adherence      | Schedule Lines with status = Done /      | Green ≥ 90%,         |
|                         | Total Schedule Lines for today × 100     | Amber ≥ 75%          |
| OEE (Today)             | Availability × Performance × Quality     | Green ≥ 85%,         |
|                         | (see formula below)                      | Amber ≥ 65%          |

#### OEE Formula

```
Availability = (available_hours − unplanned_downtime_hours) / available_hours
Performance  = actual_output / (run_time_hours × max_speed_per_hour)
Quality      = qty_produced / (qty_produced + qty_waste)

OEE = Availability × Performance × Quality × 100
```

All values are per-machine, then averaged across active machines for the
dashboard card. Per-machine OEE is available in the Machine Utilization
report (Section 4.5).

#### Charts

| Chart Title             | Type       | Data Source                        |
|-------------------------|------------|------------------------------------|
| Daily Output (7 days)   | Bar        | Production Entry grouped by date   |
| Waste % Trend (30 days) | Line       | Daily waste_pct rolling average    |
| Downtime by Reason      | Pie        | Downtime Entry grouped by reason,  |
|                         |            | last 30 days                       |
| OEE Trend (30 days)     | Line       | Daily OEE averaged across machines |

### 4.5 Reports

Three Script Reports cover the core reporting needs. All are filterable
by date range, workstation, product line, and customer.

#### 4.5.1 Daily Production Summary

```
Report Name:    Daily Production Summary
Module:         Production Log
Report Type:    Script Report
```

| Column           | Source                                              |
|------------------|-----------------------------------------------------|
| Date             | Production Entry posting date                       |
| Workstation      | Production Entry → workstation                      |
| Job Card         | Production Entry → job_card_id                      |
| Customer         | Fetched from job card                               |
| Stage            | Production Entry → production_stage                 |
| Planned Qty      | Schedule Line → planned_qty (matched by job + date) |
| Actual Qty       | SUM(qty_produced)                                   |
| Waste Qty        | SUM(qty_waste)                                      |
| Waste %          | Calculated                                          |
| Variance         | Actual Qty − Planned Qty                            |
| Duration (hrs)   | SUM(duration_hours)                                 |

#### 4.5.2 Machine Utilization

```
Report Name:    Machine Utilization
Module:         Production Log
Report Type:    Script Report
```

| Column              | Source                                          |
|---------------------|-------------------------------------------------|
| Workstation         | Workstation name                                |
| Workstation Type    | Fetched from workstation                        |
| Available Hours     | DPS → available_hours (or working hours config) |
| Run Hours           | SUM(Production Entry duration_hours)            |
| Downtime (Unplanned)| SUM(Downtime Entry duration_minutes / 60)       |
|                     | WHERE is_planned = 0                            |
| Downtime (Planned)  | SUM(Downtime Entry duration_minutes / 60)       |
|                     | WHERE is_planned = 1                            |
| Idle Hours          | Available − Run − Downtime                     |
| Utilization %       | Run Hours / Available Hours × 100               |
| OEE %               | Per-machine OEE (see formula in 4.4)            |

#### 4.5.3 Job Progress

```
Report Name:    Job Progress
Module:         Production Log
Report Type:    Script Report
```

| Column              | Source                                          |
|---------------------|-------------------------------------------------|
| Job Card            | Job card ID (across all three types)            |
| Job Card Type       | Computer Paper / Label / Carton                 |
| Customer            | Fetched from job card                           |
| Order Qty           | Job card → quantity_ordered                     |
| Qty Produced        | SUM(Production Entry qty_produced) for this job |
| Qty Remaining       | Order Qty − Qty Produced                        |
| Progress %          | Qty Produced / Order Qty × 100                  |
| Total Waste         | SUM(Production Entry qty_waste) for this job    |
| Due Date            | Job card → due_date                             |
| Days Remaining      | due_date − today                                |
| Status              | On Track (green) if Progress % ≥ expected pace, |
|                     | At Risk (amber) if behind by > 10%,             |
|                     | Overdue (red) if past due_date                  |

### 4.6 Section 4 Data Flow Diagram

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Shop Floor   │     │ Frappe Desk      │     │ Schedule Board   │
│ Terminal     │     │ (direct entry)   │     │ (status update)  │
│ (Phase 2)    │     │                  │     │                  │
└──────┬───────┘     └────────┬─────────┘     └────────┬─────────┘
       │                      │                        │
       ▼                      ▼                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Production Entry (PE)                         │
│                    Downtime Entry (DT)                           │
├──────────────────────────────────────────────────────────────────┤
│  on_submit:                                                      │
│  ├─ Update job card progress (qty rollup)                        │
│  ├─ Update Schedule Line status (Pending → In Progress → Done)   │
│  └─ Recalculate DPS utilization_pct (actual vs planned)          │
└───────────────┬─────────────────────────────┬────────────────────┘
                │                             │
                ▼                             ▼
┌──────────────────────────┐   ┌──────────────────────────────────┐
│  Dashboard               │   │  Reports                         │
│  (Number Cards + Charts) │   │  Daily Summary / Machine Util /  │
│  Real-time KPIs          │   │  Job Progress                    │
└──────────────────────────┘   └──────────────────────────────────┘
```

---

## Section 5: Integration with Existing Doctypes

The PPC layer must attach to the three existing job card doctypes without
altering their core schema or breaking current workflows. All integration
is achieved through Custom Fields (installed via fixtures) and doctype
event hooks (declared in `hooks.py`).

### 5.1 Custom Fields on Existing Job Cards

Two Custom Fields are added to each of the three job card doctypes. They
are installed via the same fixture mechanism described in Section 2.1.1.

```
Target Doctypes:  Job Card Computer Paper
                  Job Card Label
                  Job Card Carton

┌──────────────────┬───────────┬────────┬──────────────────────────────────┐
│ Field Name       │ Type      │ Reqd   │ Purpose                          │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ production_status│ Select    │ No     │ Options: Not Started,            │
│                  │           │        │ In Progress, Completed.          │
│                  │           │        │ Default: Not Started.            │
│                  │           │        │ Read-only — set automatically    │
│                  │           │        │ by Production Entry on_submit.   │
│                  │           │        │ Not Started → In Progress on     │
│                  │           │        │ first PE submit. In Progress →   │
│                  │           │        │ Completed when total qty_produced│
│                  │           │        │ ≥ quantity_ordered.              │
├──────────────────┼───────────┼────────┼──────────────────────────────────┤
│ current_stage    │ Link      │ No     │ Link to Production Stage.        │
│                  │           │        │ Read-only — set automatically    │
│                  │           │        │ to the stage of the most recent  │
│                  │           │        │ submitted Production Entry for   │
│                  │           │        │ this job card.                   │
└──────────────────┴───────────┴────────┴──────────────────────────────────┘
```

**Insert after field:** `quantity_ordered` (present on all three job cards)
**Section Break:** Added before these fields with label "Production Tracking"

#### Fixture Filter Update

The Custom Field fixture filter in `hooks.py` (Section 2.1.1) is expanded
to include the job card doctypes:

```python
{
    "dt": "Custom Field",
    "filters": [
        [
            "dt", "in", [
                "Workstation Type",
                "Workstation",
                "Job Card Computer Paper",
                "Job Card Label",
                "Job Card Carton",
            ]
        ]
    ],
}
```

### 5.2 Dashboard Connections

Frappe's `get_dashboard_data` hook exposes linked documents in the sidebar
of a doctype's form view. For each job card type, the dashboard shows
related Production Entries and Schedule Lines without any schema change.

Each job card type gets a `{doctype}_dashboard.py` file:

```python
# Example: job_card_label_dashboard.py
def get_data():
    return {
        "fieldname": "job_card_id",
        "dynamic_link_field": "job_card_type",
        "transactions": [
            {
                "label": "Production",
                "items": ["Production Entry"],
            },
            {
                "label": "Schedule",
                "items": ["Daily Production Schedule"],
            },
        ],
    }
```

This surfaces counts and links in the job card form sidebar:

```
┌─────────────────────────────────────┐
│  Job Card Label: JC-L-00042        │
│  ─────────────────────────────────  │
│  Production Tracking                │
│  Status: In Progress                │
│  Current Stage: Printing            │
│  ─────────────────────────────────  │
│  Connections:                       │
│  Production Entry         3         │
│  Daily Production Schedule 2        │
└─────────────────────────────────────┘
```

### 5.3 hooks.py Changes

Below is the complete set of additions to `hooks.py` for the PPC layer.
Existing entries (Print Format fixture) are preserved.

```python
# --- Fixtures ---
fixtures = [
    {"dt": "Print Format", "filters": [["name", "=", "Carton Job Card"]]},
    {
        "dt": "Custom Field",
        "filters": [
            [
                "dt", "in", [
                    "Workstation Type",
                    "Workstation",
                    "Job Card Computer Paper",
                    "Job Card Label",
                    "Job Card Carton",
                ]
            ]
        ],
    },
    {"dt": "Production Stage"},
    {"dt": "Waste Reason"},
    {"dt": "Downtime Reason"},
    {"dt": "Workstation Type", "filters": [
        ["name", "in", [
            "Flexo Press", "Corrugator", "Folder Gluer",
            "Numbering Machine", "Collator", "Die Cutter",
        ]]
    ]},
]

# --- Doctype Events ---
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

#### Event Handler Summary

| Event                              | Action                              |
|------------------------------------|-------------------------------------|
| `Production Entry.on_submit`       | Roll up qty_produced to job card.   |
|                                    | Update production_status and        |
|                                    | current_stage on job card.          |
|                                    | Update Schedule Line status if DPS  |
|                                    | is linked.                          |
| `Production Entry.on_cancel`       | Reverse the rollup: recalculate     |
|                                    | totals, revert production_status    |
|                                    | if needed.                          |
| `Downtime Entry.on_submit`         | Recalculate DPS utilization_pct     |
|                                    | for the linked machine-day.         |
| `Downtime Entry.on_cancel`         | Reverse utilization recalculation.  |

### 5.4 Workflow: Job Card States

The existing job card doctypes use Frappe's built-in submittable states:
**Draft → Submitted → Cancelled** (with Amended). The PPC layer does NOT
add a Frappe Workflow on top of this — the `production_status` Custom Field
handles production-phase tracking independently.

Rationale: Frappe Workflows override the submit/cancel button behaviour and
add state transition permissions. This would complicate the existing job card
creation flow (which works fine) just to surface production status. Instead:

- **Draft / Submitted / Cancelled** = document lifecycle (unchanged)
- **Not Started / In Progress / Completed** = production lifecycle (Custom
  Field, set by event hooks, read-only on the form)

These two axes are independent. A Submitted job card starts at "Not Started"
and progresses to "Completed" as Production Entries accumulate. If the job
card is Cancelled, production_status becomes irrelevant (no new Production
Entries can link to a cancelled job card — enforced in PE validate).

```
Document Lifecycle          Production Lifecycle
(Frappe built-in)           (Custom Field)

  Draft ──► Submitted ──┐     Not Started
                        │         │
                        │    (first PE submitted)
                        │         ▼
                        │     In Progress
                        │         │
                        │    (total qty ≥ ordered qty)
                        │         ▼
                        │     Completed
                        │
                        └──► Cancelled
                             (blocks new PEs)
```
