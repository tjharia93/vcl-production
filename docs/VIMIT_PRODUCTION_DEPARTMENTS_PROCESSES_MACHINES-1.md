# Vimit Converters Ltd — Production Departments, Processes & Machines

**Status:** Working Master  
**Department 01:** Computer Paper / ETR / Reel-to-Reel Printing  
**Last Updated:** 01 September 2026

---

# 1. Department Scope

This production area covers three main product/process routes:

1. **Computer Paper** — Dot Matrix / Continuous Computer Paper
2. **ETR**
3. **Reel-to-Reel Printing**

These routes share some production machinery but do not necessarily follow the same finishing process.

---

# 2. Machines & Capabilities

| Machine | Printing | Z / Pan Fold | Reel-to-Reel | Other Confirmed Capabilities |
|---|---|---|---|---|
| **Miyakoshi 1 (M1)** | 4 Colour | Yes | Yes — rarely used | Inline computer-paper converting |
| **Miyakoshi 2 (M2)** | 2 Colour | Yes | Yes — rarely used | Inline computer-paper converting |
| **Miyakoshi 3 (M3)** | 4 Colour | Yes | **Yes — preferred** | Main R2R machine; can also do sheeting when required |
| **Miyakoshi 4 (M4)** | Plain | Yes | **No** | Can collate 2-part simultaneously |
| **Roland** | 1 Colour | Yes | **No** | 1-part punching |
| **Collator 01** | — | — | — | Collation + numbering |
| **Collator 02** | — | — | — | Collation only |

## Machine Notes

- M3 is the preferred machine for Reel-to-Reel production.
- M1 and M2 are Reel-to-Reel capable, but this capability is not used often.
- M4 cannot perform Reel-to-Reel printing.
- M3 can perform sheeting when required.
- Roland cannot perform Reel-to-Reel production.
- The main computer-paper machines produce the standard Z / Pan Fold format.

---

# 3. Production Architecture

The department should **not** be represented as one single linear production flow.

There are three principal production routes:

```text
                         DEPARTMENT
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
      COMPUTER PAPER         ETR         REEL-TO-REEL
             |                |                |
             v                v                v
       Printing &          Printing         Printing
       Converting             |                |
             |                v                v
             |             Slitting       Reel Output
             v
       Z / Pan Fold
             |
             +----> Collation / Numbering
             |      where required
             v
       Packing according
       to Packing Instructions
```

---

# 4. Route A — Computer Paper

## Product

Dot Matrix / Continuous Computer Paper.

## Standard High-Level Flow

```text
Job / Production Order
        |
        v
Raw Material Issue
Paper Reel(s)
        |
        v
Printing & Converting
        |
        v
Z / Pan Fold
        |
        +----> Collation / Numbering (if required)
        |
        v
Packing as per Packing Instructions
        |
        v
Finished Goods
        |
        v
Production Reconciliation / Job Close-Out
```

## Printing & Converting

Several operations can occur **inline during the same machine run**.

Depending on the job, these can include:

- Printing
- Side perforation / tractor-feed hole preparation
- Punching
- Cross perforation / half perforation
- Z / Pan folding
- Other format-specific converting requirements

These should therefore not automatically be treated as separate physical production stages.

### Example

A job requiring a size such as **9.5 × 11 × 5.5** can include the required half perforation as part of the converting operation.

The exact setup is determined by the job specification.

---

# 5. Collation & Numbering

Collation is used where multiple parts need to be brought together into the required finished product.

## Collator 01

Capabilities:

- Collation
- Numbering

## Collator 02

Capabilities:

- Collation
- No numbering

## Miyakoshi 4

M4 can produce/collate **2-part simultaneously** during production.

This means collation does not always have to occur as a separate downstream production operation.

## Important Process Principle

**Printing and collation can happen together** depending on the machine and product configuration.

The system should therefore distinguish between:

- Production process
- Machine
- Operations/capabilities used during the machine run

rather than assuming that every capability represents a separate movement between production stages.

---

# 6. Computer Paper Packing

Packing should follow the specific **Packing Instructions** for the job.

For collated products:

> **Collation packs as per Packing Instructions.**

Potential production close-out information includes:

- Good quantity
- Waste
- Returned material
- Packs produced
- Boxes produced
- Quantity per pack / box
- Number range where applicable
- Finished Goods quantity

---

# 7. Route B — ETR

ETR follows a different production route from standard Computer Paper.

## High-Level Flow

```text
Job / Production Order
        |
        v
Raw Material Issue
        |
        v
Printing
        |
        v
Slitting
        |
        v
Packing / Finished Product
        |
        v
Finished Goods
        |
        v
Production Reconciliation
```

### Confirmed Principle

**ETR: Printing → Slitting**

Further ETR machine/process detail will be added when this route is reviewed in depth.

---

# 8. Route C — Reel-to-Reel Printing

Reel-to-Reel does not follow the standard Computer Paper folding/collation route.

## High-Level Flow

```text
Job / Production Order
        |
        v
Input Reel
        |
        v
Printing / Machine Run
        |
        v
Output Reel
        |
        v
Finished / Intermediate Reel
        |
        v
Production Reconciliation
```

## Machine Preference

1. **M3 — Preferred Reel-to-Reel machine**
2. M1 — Capable, rarely used
3. M2 — Capable, rarely used
4. M4 — Not capable
5. Roland — Not capable

---

# 9. Proposed Production Process Structure

For future production tracking / ERPNext design, avoid creating unnecessary artificial operations.

## A. Computer Paper — Printing & Converting

Possible inline operations:

- Printing
- Punching
- Side perforation / tractor-feed preparation
- Cross perforation / half perforation
- Z / Pan folding
- Sheeting where applicable
- Inline 2-part collation where applicable

## B. Collation & Numbering

Where required:

- Multipart collation
- Numbering
- Packing according to Packing Instructions

## C. ETR Production

- Printing
- Slitting
- Packing / finishing

## D. Reel-to-Reel Production

- Printing
- Rewinding / Reel output
- Reel reconciliation

---

# 10. Production Reconciliation Principle

Every production job should ultimately reconcile:

```text
Material Issued
      =
Good Production
    + Waste
    + Returned Material
```

Where reels are involved, the eventual production system should preserve reel traceability and account for material issued, consumed, returned and converted into finished/intermediate output.

---

# 11. Modelling Principle

For the production system, maintain a clear distinction between:

### Process
What manufacturing activity is being performed.

### Machine
The physical equipment performing the work.

### Capability / Operation
What the machine can perform during that production run.

Example:

```text
PROCESS:
Computer Paper Printing & Converting

MACHINE:
Miyakoshi 3

OPERATIONS USED:
- 4 Colour Printing
- Side Perforation
- Half Perforation
- Z / Pan Fold
```

This prevents inline operations from being incorrectly represented as separate production movements.

---

# 12. Items for Later Confirmation

- Exact detailed production route for each major Computer Paper product type.
- Exact ETR machines and slitting equipment.
- Detailed ETR packing process.
- Exact reel-to-reel close-out and packing requirements.
- Machine-specific size limitations.
- Machine speeds and capacities.
- Operator requirements.
- Setup / make-ready requirements.
- Waste categories by machine/process.
- Downtime categories.
- Quality-control checkpoints.
- Production data required from operators.

---

# 13. Department Status

**Computer Paper / ETR / Reel-to-Reel:** Initial process mapping completed.

This remains a **working master** and will be expanded as each production department is reviewed.
