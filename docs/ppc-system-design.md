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
