"""Export the app-managed print formats into production_log/fixtures/print_format.json.

The HTML files next to their doctypes are the source of truth. Run this after
editing one:

    python3 scripts/sync_print_format_fixtures.py

Editing the fixture by hand, or the copy in Desk, loses the change on the next
migrate — fixtures overwrite the site.

Replaces the monobox-only script: two formats are now managed this way and a
third would have been a third script.
"""

import json
import pathlib
import re
import sys

FIXTURE = pathlib.Path("production_log/fixtures/print_format.json")
DOCTYPE_DIR = pathlib.Path("production_log/job_card_tracking/doctype")

FORMATS = [
    {
        "name": "Carton Jobcard v2",
        "doc_type": "Job Card Carton",
        "source": DOCTYPE_DIR / "job_card_carton" / "carton_jobcard_v2.html",
    },
    {
        "name": "Monobox Job Traveller",
        "doc_type": "Job Card Monobox",
        "source": DOCTYPE_DIR / "job_card_monobox" / "monobox_job_traveller.html",
    },
]

BASE = {
    "custom_format": 1,
    "doctype": "Print Format",
    "module": "Job Card Tracking",
    "pdf_generator": "wkhtmltopdf",
    "print_format_type": "Jinja",
    "raw_printing": 0,
    "standard": "No",
}


def main():
    records = json.loads(FIXTURE.read_text())
    by_name = {r.get("name"): i for i, r in enumerate(records)}
    changed = False

    for fmt in FORMATS:
        html = fmt["source"].read_text()

        # wkhtmltopdf silently drops 8-digit #RRGGBBAA, taking every fill with
        # it, while Chrome renders it fine. Cheapest possible place to catch it.
        bad = set(re.findall(r"#[0-9A-Fa-f]{8}\b", html))
        if bad:
            print(f"{fmt['name']}: 8-digit hex, invisible in wkhtmltopdf: {bad}")
            sys.exit(1)

        record = dict(BASE, name=fmt["name"], doc_type=fmt["doc_type"], html=html)

        i = by_name.get(fmt["name"])
        if i is None:
            records.append(record)
            print(f"added   {fmt['name']} ({len(html):,} chars)")
            changed = True
        elif records[i].get("html") != html:
            # Preserve anything already on the record that we do not manage.
            records[i] = {**records[i], **record}
            print(f"updated {fmt['name']} ({len(html):,} chars)")
            changed = True
        else:
            print(f"current {fmt['name']}")

    if changed:
        FIXTURE.write_text(json.dumps(records, indent=1) + "\n")


if __name__ == "__main__":
    main()
