"""Render the Monobox Job Traveller to real PDFs and check them.

A clean template says nothing about the PDF. wkhtmltopdf drops 8-digit hex
silently, ignores named @page rules, and will happily spill a section onto an
unheaded continuation sheet. So this renders the format against stub documents
that exercise the branches which change the page height — window on/off, stages
excluded — then measures the result:

    * page count == the number of .page-container blocks emitted
    * every page carries ink (a page can be present and blank)
    * nothing overflows the A4 printable box

Run from the repo root:  python3 scripts/check_monobox_traveller.py
Exits 1 on any failure, so it can gate a change to the layout.
"""

import pathlib
import re
import subprocess
import sys
import tempfile

TEMPLATE = pathlib.Path(
    "production_log/job_card_tracking/doctype/job_card_monobox/monobox_job_traveller.html"
)

A4_HEIGHT_PX = 1169  # A4 at 100 dpi
MARGIN_PX = 35       # 9mm top+bottom margin at 100 dpi, rounded up


class StubDoc(dict):
    """Enough of a Frappe Document for the template: attribute and .get access."""

    def __getattr__(self, item):
        return self.get(item)


def stub(**overrides):
    doc = StubDoc(
        name="JC-MBX-2026-0001",
        customer="Demo Customer Ltd",
        date_created="2026-08-05",
        due_date="2026-08-19",
        repeat_job="New",
        customer_lpo="LPO-88213",
        sales_order="SAL-ORD-2026-00123",
        quantity_ordered=25000,
        specification_name="250g Duplex Monobox 120x60x180 window",
        customer_product_spec="MBX-SPEC-00001",
        job_description="Custom printed monobox, 4 colour process, front panel window.",
        board_grade="Duplex Grey Back",
        board_gsm=250,
        print_side="White Side",
        sheet_size="914 x 1220",
        sheet_length=None,
        sheet_width=None,
        mbx_length=120,
        mbx_width=60,
        mbx_height=180,
        tuck_flap=25,
        glue_flap=15,
        dust_flap=20,
        blank_length=430,
        blank_width=395,
        ups_per_sheet=6,
        has_window=1,
        window_width=70,
        window_height=90,
        window_panel="Front",
        window_offset_bottom=40,
        window_offset_left=25,
        film_material="PET Clear",
        film_micron=30.0,
        film_patch_width=85,
        film_patch_height=105,
        cutting_die="MBX-DIE-00001",
        die_notes="Shared with the 180ml variant.",
        printing_or_plain="Printed",
        ink_type="Process Offset",
        number_of_colours=5,
        uses_c=1, uses_m=1, uses_y=1, uses_k=1,
        spot_colours=[StubDoc(pantone_code="PMS 485 C", pantone_name="Red")],
        coating_type="Gloss Lamination",
        applies_printing=1,
        applies_coating=1,
        applies_diecut=1,
        applies_window_patch=1,
        applies_gluing=1,
        applies_bundling=1,
        special_instructions="Bundle in 50s, shrink wrap each bundle.",
        planned_sheets=4200,
    )
    doc.update(overrides)
    return doc


CASES = {
    # Every stage, window on — the tallest page 3 and the tallest page 4.
    "full": stub(),
    # Plain box, no window, three stages excluded — exercises every struck-through
    # branch at once and the film blocks disappearing.
    "plain_no_window": stub(
        has_window=0,
        printing_or_plain="Plain",
        number_of_colours=0,
        uses_c=0, uses_m=0, uses_y=0, uses_k=0,
        spot_colours=[],
        coating_type="None",
        applies_printing=0,
        applies_coating=0,
        applies_window_patch=0,
        sales_order=None,
        customer_lpo=None,
        planned_sheets=None,
    ),
    # Sheet size Other, no order, minimum viable route.
    "other_sheet_no_order": stub(
        sheet_size="Other",
        sheet_length=700,
        sheet_width=1000,
        sales_order=None,
        quantity_ordered=500,
        applies_coating=0,
        applies_bundling=0,
        spot_colours=[],
    ),
}


class FrappeStub:
    """The two frappe helpers the template touches."""

    @staticmethod
    def format(value, spec=None):
        return "" if value is None else str(value)


def render(template_text, doc):
    import jinja2

    env = jinja2.Environment(undefined=jinja2.ChainableUndefined)
    return env.from_string(template_text).render(doc=doc, frappe=FrappeStub())


def to_pdf(body_html, out_path):
    page = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        f"<body>{body_html}</body></html>"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(page)
        src = fh.name

    subprocess.run(
        [
            "wkhtmltopdf", "-q", "--page-size", "A4",
            "--margin-top", "9mm", "--margin-bottom", "9mm",
            "--margin-left", "9mm", "--margin-right", "9mm",
            "--enable-local-file-access", src, str(out_path),
        ],
        check=True,
    )


def pdf_pages(path):
    out = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, check=True
    ).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


def page_ink(path):
    """Return (ink_fraction, lowest_ink_row_fraction) per page."""
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-r", "100", "-png", str(path), f"{tmp}/pg"], check=True
        )
        results = []
        for png in sorted(pathlib.Path(tmp).glob("pg-*.png")):
            im = Image.open(png).convert("L")
            px, (w, h) = im.load(), im.size
            dark = sum(
                1 for y in range(0, h, 3) for x in range(0, w, 3) if px[x, y] < 200
            )
            total = (h // 3 + 1) * (w // 3 + 1)
            last = 0
            for y in range(h - 1, -1, -2):
                if any(px[x, y] < 200 for x in range(0, w, 4)):
                    last = y
                    break
            results.append((dark / total, last / h))
        return results


def main():
    template_text = TEMPLATE.read_text()
    out_dir = pathlib.Path("testing/monobox_traveller")
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    for case, doc in CASES.items():
        body = render(template_text, doc)
        containers = body.count('class="page-container"')

        pdf = out_dir / f"{case}.pdf"
        to_pdf(body, pdf)
        pages = pdf_pages(pdf)
        ink = page_ink(pdf)

        print(f"\n{case}: {containers} containers -> {pages} PDF pages")
        for n, (frac, reach) in enumerate(ink, 1):
            print(f"   page {n}: ink {frac * 100:5.2f}%  reaches {reach * 100:5.1f}%")
            if frac < 0.005:
                failures.append(f"{case} page {n} is effectively blank")
            if reach > (A4_HEIGHT_PX - MARGIN_PX) / A4_HEIGHT_PX:
                failures.append(f"{case} page {n} runs into the bottom margin")

        if pages != containers:
            failures.append(
                f"{case}: {containers} page containers but {pages} PDF pages "
                "— something split or a blank sheet was emitted"
            )

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        sys.exit(1)

    print(f"OK — {len(CASES)} cases, no blank pages, no overflow.")
    print(f"PDFs in {out_dir}/")


if __name__ == "__main__":
    main()
