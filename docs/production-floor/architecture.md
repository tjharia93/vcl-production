# VCL Production Lite — architecture and the ERPNext path

## Why a separate module, not a separate app

The rest of `production_log` is the master-data and job-card layer: Customer
Product Specifications, the four Job Card types, Dies, and the PPC planning
layer. Its planning documents hang off ERPNext Workstations and its own Job
Cards.

That is the right shape for planning. It is the wrong shape for the thing this
module does, because it makes a production entry impossible until a Job Card
exists. The floor cannot wait for that. So Production Floor keeps **its own
DocTypes with no link to an ERPNext document at all** — a production entry
needs a machine and two lines of typing, and nothing else.

That independence is a property of the **data model**, and it is the one that
matters. It is not a claim about packaging.

This module briefly shipped as its own app, `vcl_production`. It did not work:
Frappe Cloud builds the app at the *root* of a repo, which here is
`production_log`, so the subdirectory reached the bench as inert files and no
DocType was ever created. Folding it in as a module means it deploys with the
app that is already on the bench, and there is one repo, one migrate and one
rollback instead of two.

The cost of folding in is honest and worth stating: Production Floor now
inherits `required_apps = ["erpnext"]`, and its patch runs inside the live
app's migrate. A broken patch here would block a `production_log` migrate. The
mitigation is that the patch touches nothing outside its own DocTypes.

The two halves share no DocTypes, no fixtures, no Custom Fields, and no routes:

| | rest of `production_log` | Production Floor module |
| --- | --- | --- |
| Links to ERPNext documents | yes | **no** |
| Workspace | `/app/vcl-production`, `/app/ppc` | `/app/production-floor` |
| Main screen | desk forms, PPC board | `/app/vcl-production-lite` |
| DocType prefix | `Job Card *`, `PPC *`, `Customer Product Specification` | `VCL Production *`, `VCL Daily Production *` |
| Module | `Production Log`, `Job Card Tracking`, `PPC` | `Production Floor` |

Nothing in this module hooks a `production_log` or ERPNext document event.

### The one place it reaches out (2026-08-27)

`list_open_job_cards()` reads `Job Card Computer Paper`, a Job Card Tracking
DocType, to offer the Add Job dialog an optional chip row. **This is a genuine
loosening of the boundary above and it should be read as one**, not waved
through because the two now ship in the same app.

Three things keep it honest, and all three are load-bearing:

1. **Read-only, and optional.** The chips fill Customer and Job. They set no
   machine, no quantity, no unit, and `add_item` still refuses an entry
   without a customer and a job typed or filled. A supervisor whose job has no
   card ignores the row.
2. **It fails soft.** A missing DocType returns `[]`; a `PermissionError`
   returns `[]`. The dialog renders and saves either way. A Job Card Tracking
   problem is never allowed to stop production being recorded.
3. **Nothing is linked.** `production_job_card` is `Data`, so the reference
   cannot make a row unsaveable later. It is provenance, not a foreign key.

What must not creep in: reading a job card to *populate* quantity, machine or
unit, or requiring a card before an entry is accepted. Either would make the
floor wait on Job Card Tracking, which is the thing this module exists to
avoid.

## Why "Production Job" and not "Job Card"

A **VCL Production Job** is what the factory means by a job: a customer and a
thing being made for them, remembered so it can be picked next time.

An **ERPNext Job Card** is a manufacturing transaction against a Work Order.

They are not the same object and conflating them now would cost a rebuild
later. Keeping the names apart means an ERPNext Job Card can later *feed* a
VCL Production Job without either one having to become the other.

## The integration path

```
ERPNext Job Card ──┐
Work Order ────────┤
Sales Order ───────┼──▶ VCL Production Job ──▶ VCL Daily Production Item
Item ──────────────┤          ▲
Customer ──────────┘          │
                     Manual entry (today, and after)
```

Every DocType already carries the fields the integration will use, as
read-only `Data`:

| DocType | Reserved fields |
| --- | --- |
| VCL Production Job | `erpnext_customer`, `erpnext_item`, `erpnext_sales_order`, `erpnext_work_order`, `erpnext_job_card`, `erpnext_workstation` |
| VCL Daily Production Item | `erpnext_job_card`, `erpnext_work_order`, `erpnext_sales_order`, `erpnext_item`, `erpnext_workstation` |
| VCL Production Machine | `erpnext_workstation` |

They are `Data` and not `Link` on purpose. The original reason — a `Link` to
`Work Order` makes the DocType unloadable without ERPNext — no longer applies
now that this ships inside `production_log`. The reason that does still apply
is stronger: a `Link` validates on every save, so a row pointing at a Work
Order that was later cancelled, renamed or deleted becomes unsaveable, and the
supervisor is blocked by an ERPNext data problem they cannot see or fix. A
`Data` field records what it recorded. Keep them `Data`.

Both `VCL Production Job` and `VCL Daily Production Item` also carry a
`source` field — `Manual` or `ERPNext`.

### What switching it on looks like

1. Convert the reserved `Data` fields to `Link` fields via Custom Fields on
   sites that have ERPNext, leaving the DocType JSON alone.
2. Add a sync that creates or updates a `VCL Production Job` from a submitted
   Job Card, setting `source = "ERPNext"` and filling the links.
3. On `VCL Daily Production Item`, copy the same links across when a row is
   created from an ERPNext-sourced job.
4. Optionally map `VCL Production Machine.erpnext_workstation` so a machine
   resolves to a Workstation.

### What must not change

- **Manual creation stays.** `add_item` requires a department, a machine, a
  customer and a job — never a `production_job`, never a Job Card. The floor
  is never blocked because ERPNext data is incomplete.
- **The floor screen does not care where a job came from.** It renders
  `customer_name` and `job_name` off the row. Both sources produce identical
  rows, so the UI needs no branch and no second code path.
- **Rows stay snapshots.** `customer_name`, `job_name`, `department` and `uom`
  are copied onto the row on the way in and are never re-read from the master.
  An ERPNext sync that renames an Item cannot rewrite last month's report.

## Where the rules live

`vcl_production/reporting.py` imports nothing from Frappe. Report wording,
department ordering, quantity parsing, remembered-job de-duplication and the
definition of "missing information" all live there and are unit-tested with
plain `unittest`, no site required. `api.py` is the thin layer that turns
Frappe documents into the dicts those functions take.

Two consequences worth keeping:

- The Script Report's *Attention* column and the phone's ATTENTION REQUIRED
  banner call the same function, so the desk and the floor can never disagree
  about what a day is missing.
- Changing the WhatsApp format is a change to one file with a test around it.

## Quantities

Quantities are `Float` with three decimals — 0.5 reels and 1031 pcs are both
first-class. Arithmetic text such as `41+6` is refused, on the phone by a
numeric input and a regex, and on the server by `parse_quantity`. A total the
system guessed at is worse than one it asked for. A blank quantity stays
blank; it does not become zero.

## Departments and units

Both are Select fields, but their options are driven from **VCL Production
Settings** and pushed onto every field as Property Setters on save and on
`bench migrate`. Adding a department or a unit is a Settings edit, not a
schema change, and survives an app upgrade.
