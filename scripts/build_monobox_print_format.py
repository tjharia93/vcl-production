"""Export the Monobox Job Traveller into production_log/fixtures/print_format.json.

The template file is the source of truth. Run this after editing it:

    python3 scripts/build_monobox_print_format.py

Editing the fixture by hand, or the copy in Desk, loses the change on the next
migrate — fixtures overwrite the site.
"""

import json
import pathlib
import sys

TEMPLATE = pathlib.Path(
    "production_log/job_card_tracking/doctype/job_card_monobox/monobox_job_traveller.html"
)
FIXTURE = pathlib.Path("production_log/fixtures/print_format.json")

NAME = "Monobox Job Traveller"

RECORD = {
    "custom_format": 1,
    "doc_type": "Job Card Monobox",
    "doctype": "Print Format",
    "module": "Job Card Tracking",
    "name": NAME,
    "pdf_generator": "wkhtmltopdf",
    "print_format_type": "Jinja",
    "raw_printing": 0,
    "standard": "No",
}


def main():
    html = TEMPLATE.read_text()

    # The trap that costs a whole render: wkhtmltopdf silently drops 8-digit
    # #RRGGBBAA, taking every fill with it, while Chrome shows it fine.
    import re

    bad = re.findall(r"#[0-9A-Fa-f]{8}\b", html)
    if bad:
        print(f"8-digit hex found (wkhtmltopdf drops these silently): {set(bad)}")
        sys.exit(1)

    records = json.loads(FIXTURE.read_text())
    record = dict(RECORD, html=html)

    for i, existing in enumerate(records):
        if existing.get("name") == NAME:
            records[i] = record
            print(f"updated {NAME} ({len(html)} chars of html)")
            break
    else:
        records.append(record)
        print(f"added {NAME} ({len(html)} chars of html)")

    FIXTURE.write_text(json.dumps(records, indent=1) + "\n")


if __name__ == "__main__":
    main()
