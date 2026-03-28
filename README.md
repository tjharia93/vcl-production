# Production Log — VCL (Vimit Converters Ltd)

A custom Frappe/ERPNext v16 app for capturing daily production data from the
shop floor at Vimit Converters Ltd, Nairobi. Tracks multiple workstations
running 1–4 paper reels simultaneously.

---

## Features

- Uses ERPNext's built-in **Workstation** DocType for station management.
- **Workstation Type** selector on each entry row — the Workstation dropdown
  filters automatically to show only matching stations.
- **Daily Production Log** (submittable, amendable) capturing all entries for a
  date + shift combination.
- **Production Entry** child table with full reel data (GSM, weight, cut size,
  reams) for up to 4 reels per station run.
- Conditional field visibility — Reel 2/3/4 sections only appear when the
  selected reel count requires them.
- Python validation: weight checks, time checks, station capacity checks,
  duplicate log prevention.
- Auto-calculated summary fields (totals recalculated on every save).
- 4 built-in reports: Production Summary by Station, Operator Performance,
  Incomplete Reels Tracker, Daily Production Summary.
- A4 landscape print format.
- Production Management workspace with shortcuts and reports.
- Daily email summary (scheduled task).

---

## Roles and Permissions

This app uses ERPNext's built-in roles — no custom roles are created.

| Role | Access |
|---|---|
| Manufacturing Manager | Full access — create, read, write, delete, submit, cancel, amend |
| System Manager | Full access — create, read, write, delete, submit, cancel, amend |
| Manufacturing User | Create and read only (no submit/cancel) |

Assign these roles to users via **Setup > Users > [user] > Roles**.

---

## Installation

### On Frappe Cloud or self-hosted bench

```bash
# 1. Get the app
bench get-app https://github.com/tjharia93/vcl-production.git

# 2. Install on your site
bench --site [your-site] install-app production_log

# 3. Run migrations (runs patches automatically)
bench --site [your-site] migrate
```

---

## Post-Installation Steps

1. Go to **Manufacturing > Workstation Type** and create types for your shop
   floor (e.g. *Ruling*, *Sheeting*).
2. Go to **Manufacturing > Workstation** and create a Workstation for each
   physical machine.
   - Set **Workstation Type** so the cascading filter works.
   - Set **Job Capacity** to the maximum number of reels that station can run
     simultaneously (1–4).
3. Assign the **Manufacturing Manager** or **System Manager** role to
   supervisors, and **Manufacturing User** to data-entry operators.
4. Navigate to **Production Management** workspace in the sidebar.
5. Create a test **Daily Production Log** to verify everything works.
6. Review the print format by opening a submitted log and clicking **Print**.

---

## DocTypes

| DocType | Type | Purpose |
|---|---|---|
| Daily Production Log | Transaction (submittable) | Header record for a date + shift |
| Production Entry | Child Table | Per-workstation reel production data |

> **Note:** Production Station has been replaced by ERPNext's built-in
> **Workstation** DocType. Configure workstations in
> **Manufacturing > Workstation**.

---

## Workstation Setup

Each Workstation record needs two fields populated for this app to work
correctly:

| Field | Location in ERPNext | Purpose |
|---|---|---|
| Workstation Type | Workstation form > Details | Drives the cascading filter on Production Entry |
| Job Capacity | Workstation form > Details | Max reels this station can run (1–4). Enforced on data entry and on save. |

---

## Material Types

| Code | Full Name |
|---|---|
| NP | Newsprint |
| BP | Bond Paper |
| AP | Art Paper |
| CP | Coated Paper |

---

## Output Types

| Code | Description |
|---|---|
| A1 | Standard A1 output |
| A2 | Standard A2 output |
| BT | Business Tablet |

---

## Reports

| Report | Type | Description |
|---|---|---|
| Production Summary by Station | Script | Daily entries grouped by workstation |
| Operator Performance | Script | Aggregated metrics per operator |
| Incomplete Reels Tracker | Script | All carry-forward reels (last 7 days default) |
| Daily Production Summary | Script | Yesterday's summary with bar chart |

---

## Development

```bash
# Run bench in dev mode
bench start

# Reload DocType after JSON changes
bench --site [your-site] migrate

# Reload a single DocType (no migration needed for cosmetic changes)
bench --site [your-site] reload-doctype "Daily Production Log"
bench --site [your-site] reload-doctype "Production Entry"
```

---

## License

MIT — see `license.txt`.
