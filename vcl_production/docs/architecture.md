# VCL Production Lite — architecture and the ERPNext path

## Why a separate app

`production_log` is the master-data and job-card app: Customer Product
Specifications, the four Job Card types, Dies, and the PPC planning layer.
It declares `required_apps = ["erpnext"]` and its planning documents hang off
ERPNext Workstations and its own Job Cards.

That is the right shape for planning. It is the wrong shape for the thing this
app does, because it makes a production entry impossible until a Job Card
exists. The floor cannot wait for that. So `vcl_production` is its own app
with its own DocTypes and no ERPNext dependency at all — a production entry
needs a machine and two lines of typing, and nothing else.

The two apps coexist on one site. They share no DocTypes, no fixtures, no
Custom Fields, and no routes:

| | `production_log` | `vcl_production` |
| --- | --- | --- |
| Requires ERPNext | yes | no |
| Workspace | `/app/vcl-production`, `/app/ppc` | `/app/production-floor` |
| Main screen | desk forms, PPC board | `/app/vcl-production-lite` |
| DocType prefix | `Job Card *`, `PPC *`, `Customer Product Specification` | `VCL Production *`, `VCL Daily Production *` |

Nothing in this app hooks a `production_log` or ERPNext document event.

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

They are `Data` and not `Link` on purpose: a `Link` to `Work Order` makes the
DocType unloadable on a site without ERPNext, which would quietly reintroduce
the dependency this app exists to avoid.

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
