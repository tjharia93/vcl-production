"""Render Carton Jobcard v2 to real PDFs and check them.

The route flags change how many stage blocks page 3 carries, and page 3 was
already the tight one — seven blocks plus the continuation-run slip. Adding
Die-cutting and Stripping makes eight, so this measures rather than hopes.

Cases cover the branches that change page height:
  * a legacy card with no route recorded (all flags 0) — must still print the
    classic seven, not a traveller struck through end to end
  * the same, plain, so Printing strikes
  * a Die Cut carton / cup sleeve — die-cutting on, slotting and stitching off
  * every stage on — the tallest page 3 possible

Run from the repo root:  python3 scripts/check_carton_traveller.py
Exits 1 on a blank page, an overflow, or a page-count change.
"""

import pathlib
import re
import subprocess
import sys
import tempfile

TEMPLATE = pathlib.Path(
    "production_log/job_card_tracking/doctype/job_card_carton/carton_jobcard_v2.html"
)

A4_HEIGHT_PX = 1169
MARGIN_PX = 40
EXPECTED_PAGES = 4


class StubDoc(dict):
    def __getattr__(self, item):
        return self.get(item)


def stub(**overrides):
    doc = StubDoc(
        name="JC-CORR-2026-0042",
        customer_name="Demo Customer Ltd",
        customer_product_spec="CTN-SPEC-00007",
        specification_name="RSC 400x300x250 3ply B",
        job_description="Standard RSC, 2 colour flexo",
        quantity_ordered=5000,
        product_type="2 Flap RSC",
        joint_type="Gluing - Machine",
        print_type="Printed",
        ply="3",
        flute_type="B",
        printing_or_plain="Printed",
        ctn_length_mm=400,
        ctn_width_mm=300,
        ctn_height_mm=250,
        ctn_flap_mm=150,
        idod="ID",
        ink_type="Process Offset",
        number_of_colours=2,
        uses_c=1, uses_k=1,
        spot_colours=[],
        board_width_planned_mm=1200,
        board_length_planned_mm=1600,
        approximate_weight_grams=850.0,
        max_reel_width=1400,
        trim_allowance_width_mm=20,
        trim_allowance_length_mm=20,
        knife_gap_mm=5,
        due_date="2026-08-20",
        date_created="2026-08-05",
        machine="Corrugator 1",
        # No route recorded — the legacy state every existing card is in.
        applies_corrugated=0, applies_pasting=0, applies_creasing=0,
        applies_printing=0, applies_diecut=0, applies_slotting=0,
        applies_stitching=0, applies_bundling=0,
    )
    doc.update(overrides)
    return doc


ALL_ON = dict(
    applies_corrugated=1, applies_pasting=1, applies_creasing=1,
    applies_printing=1, applies_diecut=1, applies_slotting=1,
    applies_stitching=1, applies_bundling=1,
)

CASES = {
    "legacy_no_route_printed": stub(),
    "legacy_no_route_plain": stub(print_type="Plain"),
    # A 2-ply cup sleeve: single face, printed, die-cut, glued, bundled.
    # Nothing to slot and nothing to stitch.
    "diecut_cup_sleeve": stub(
        product_type="Die Cut",
        specification_name="2ply E-flute coffee cup sleeve",
        ply="SFK",
        flute_type="E",
        ctn_height_mm=0,
        applies_corrugated=1, applies_pasting=1, applies_creasing=0,
        applies_printing=1, applies_diecut=1, applies_slotting=0,
        applies_stitching=0, applies_bundling=1,
    ),
    "every_stage_on": stub(**ALL_ON),
}


class _Utils:
    @staticmethod
    def formatdate(value, fmt=None):
        return "" if value is None else str(value)


class FrappeStub:
    utils = _Utils()

    @staticmethod
    def format(value, spec=None):
        return "" if value is None else str(value)

    @staticmethod
    def format_value(value, *a, **kw):
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
        ["wkhtmltopdf", "-q", "--page-size", "A4",
         "--margin-top", "10mm", "--margin-bottom", "10mm",
         "--margin-left", "10mm", "--margin-right", "10mm",
         "--enable-local-file-access", src, str(out_path)],
        check=True,
    )


def pdf_pages(path):
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True,
                         check=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


def page_ink(path):
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "100", "-png", str(path), f"{tmp}/pg"],
                       check=True)
        out = []
        for png in sorted(pathlib.Path(tmp).glob("pg-*.png")):
            im = Image.open(png).convert("L")
            px, (w, h) = im.load(), im.size
            dark = sum(1 for y in range(0, h, 3) for x in range(0, w, 3) if px[x, y] < 200)
            total = (h // 3 + 1) * (w // 3 + 1)
            last = 0
            for y in range(h - 1, -1, -2):
                if any(px[x, y] < 200 for x in range(0, w, 4)):
                    last = y
                    break
            out.append((dark / total, last / h))
        return out


def main():
    template_text = TEMPLATE.read_text()
    out_dir = pathlib.Path("testing/carton_traveller")
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    for case, doc in CASES.items():
        body = render(template_text, doc)
        struck = body.count("not run on this job")

        pdf = out_dir / f"{case}.pdf"
        to_pdf(body, pdf)
        pages = pdf_pages(pdf)
        ink = page_ink(pdf)

        print(f"\n{case}: {pages} pages, {struck} stage(s) struck through")
        for n, (frac, reach) in enumerate(ink, 1):
            flag = ""
            if frac < 0.005:
                flag = "  <-- BLANK"
                failures.append(f"{case} page {n} is blank")
            if reach > (A4_HEIGHT_PX - MARGIN_PX) / A4_HEIGHT_PX:
                flag = "  <-- OVERFLOW"
                failures.append(f"{case} page {n} runs into the bottom margin")
            print(f"   page {n}: ink {frac * 100:5.2f}%  reaches {reach * 100:5.1f}%{flag}")

        if pages != EXPECTED_PAGES:
            failures.append(f"{case}: {pages} pages, expected {EXPECTED_PAGES}")

    # The legacy guard is the whole point. A card with no route recorded must
    # print exactly what it always printed, plus the new Die-cutting block
    # struck through — an RSC does not run a flatbed die, and striking it is
    # how the floor sees that was a decision. Anything more struck than this
    # means the all-zero fallback is not firing and every historic card would
    # come off the printer crossed out end to end.
    expected_struck = {
        "legacy_no_route_printed": {"Die-cutting and Stripping"},
        "legacy_no_route_plain": {"Die-cutting and Stripping", "Printing"},
        "diecut_cup_sleeve": {"Creasing and Slitting", "Slotting", "Stitching"},
        "every_stage_on": set(),
    }

    for case, expected in expected_struck.items():
        body = render(template_text, CASES[case])
        found = set(
            re.findall(
                r'<span style="text-decoration:line-through;">\d+\.\s*([^<]+?)</span>',
                body,
            )
        )
        if found != expected:
            failures.append(
                f"{case}: struck {sorted(found) or 'nothing'}, expected "
                f"{sorted(expected) or 'nothing'}"
            )
        else:
            print(f"route check {case}: struck {sorted(found) or ['nothing']}")

    if "11. Die-cutting and Stripping" not in render(
        template_text, CASES["legacy_no_route_printed"]
    ):
        failures.append("Die-cutting and Stripping missing from the stage list")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        sys.exit(1)

    print(f"OK — {len(CASES)} cases, {EXPECTED_PAGES} pages each, no blanks, no overflow.")
    print(f"PDFs in {out_dir}/")


if __name__ == "__main__":
    main()
