# Production Log — VCL (Vimit Converters Ltd)

A custom Frappe/ERPNext v16 app for capturing daily production data from the
shop floor at Vimit Converters Ltd, Nairobi. Tracks multiple production stations
running 1–4 reels simultaneously.

---

## Features

- **Production Station** master with max-reel capacity (1–4).
- **Daily Production Log** (submittable, amendable) capturing all entries for a
  date + shift combination.
- **Production Entry** child table with full reel data (GSM, weight, cut size,
  reams) for up to 4 reels per station run.
- Conditional field visibility — Reel 2/3/4 sections only appear when needed.
- Python validation: weight checks, time checks, station capacity checks,
  duplicate log prevention.
- Auto-calculated summary fields (totals on save).
- 4 built-in reports: Production Summary by Station, Operator Performance,
  Incomplete Reels Tracker, Daily Production Summary.
- A4 landscape print format.
- Production Management workspace with shortcuts and reports.
- Daily email summary (scheduled task).
- Fixtures + patches for first-install data.

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

# 4. (Optional) Reload fixtures manually
bench --site [your-site] reload-doctype "Production Station"
```

---

## Post-Installation Steps

1. Verify the **Production Manager** role was created (`Setup > Roles`).
2. Assign the **Production Manager** role to relevant users
   (`Setup > Users > [user] > Roles`).
3. Navigate to **Production Management** workspace in the sidebar.
4. Review the 5 default production stations
   (`Production Management > Production Station List`).
5. Create a test **Daily Production Log** to verify everything works.
6. Review the print format by opening a submitted log and clicking **Print**.

---

## DocTypes

| DocType | Type | Purpose |
|---|---|---|
| Production Station | Master | Define stations and their max-reel capacity |
| Daily Production Log | Transaction (submittable) | Header record for a date + shift |
| Production Entry | Child Table | Per-station reel production data |

---

## Default Production Stations

| Code | Name | Max Reels |
|---|---|---|
| R.O.1 | Ruling Operator 1 | 4 |
| R.O.2 | Ruling Operator 2 | 4 |
| R.O.3 | Ruling Operator 3 | 4 |
| R.D.3 | Ruling Duplex 3 | 2 |
| R.S.3 | Ruling Simplex 3 | 1 |

---

## Reports

| Report | Type | Description |
|---|---|---|
| Production Summary by Station | Script | Daily entries grouped by station |
| Operator Performance | Script | Aggregated metrics per operator |
| Incomplete Reels Tracker | Script | All carry-forward reels (last 7 days default) |
| Daily Production Summary | Script | Yesterday's summary with bar chart |

---

## Development

```bash
# Lint Python
cd /path/to/frappe-bench
bench --site [your-site] console

# Run bench in dev mode
bench start
```

---

## License

MIT — see `license.txt`.
