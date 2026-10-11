#!/usr/bin/env python3
"""Render CP travellers and measure every .page-container against A4 printable height.
Decomposes the Printing page into its constituent blocks so we can see what drives height."""
import sys, pathlib, urllib.parse, requests
from playwright.sync_api import sync_playwright

A4_MM = 297 - 10          # 5mm top + 5mm bottom margin
PX_PER_MM = 3.7795
A4 = A4_MM * PX_PER_MM
W = (210 - 10) * PX_PER_MM

cfg = {}
for l in pathlib.Path("/home/tanujharia/projects/vcl-erpnext-mcp/.env").read_text().splitlines():
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
B = cfg["ERPNEXT_URL"].rstrip("/")
H = {"Authorization": f"token {cfg['ERPNEXT_API_KEY']}:{cfg['ERPNEXT_API_SECRET']}"}

OUT = pathlib.Path(__file__).parent / "measure"
OUT.mkdir(exist_ok=True)

def fetch(jc, tries=4):
    p = OUT / f"{jc}.html"
    if "--fresh" not in sys.argv and p.exists() and "page-container" in p.read_text():
        return p, True
    q = urllib.parse.urlencode({"doctype": "Job Card Computer Paper", "name": jc,
                                "format": "Computer Paper Job Traveller v2",
                                "no_letterhead": "1", "_lang": "en"})
    last = ""
    for n in range(tries):
        try:
            r = requests.get(f"{B}/printview?{q}", headers=H, timeout=300)
            if r.status_code == 200 and "page-container" in r.text:
                p.write_text(r.text)
                return p, True
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = type(e).__name__
        print(f"   retry {jc} ({last})")
    return p, False

jobs = [a for a in sys.argv[1:] if not a.startswith("--")] or ["JC-CPT-2026-00048", "JC-CPT-2026-00014", "JC-CPT-2026-00030",
                        "JC-CPT-2026-00028", "JC-CPT-2026-00047", "JC-CPT-2026-00057"]

paths = {}
for jc in jobs:
    p, ok = fetch(jc)
    if ok:
        paths[jc] = p
    else:
        print(f"{jc}: NOT RENDERABLE (permission/docstatus) — skipped")

worst = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": int(W), "height": 1400})
    for jc, p in paths.items():
        pg.goto("file://" + str(p.resolve()))
        pg.wait_for_timeout(1200)
        els = pg.query_selector_all(".page-container")
        print(f"\n=== {jc}  ({len(els)} page-containers)")
        for i, el in enumerate(els):
            h = el.bounding_box()["height"]
            hm = (A4 - h) / PX_PER_MM
            tag = "  <== OVERFLOW" if hm < 0 else ""
            title = (el.query_selector(".company-title") or el).inner_text()[:44].replace("\n", " ")
            print(f"   p{i+1}: {h:7.1f}px  headroom {hm:7.1f}mm  {title}{tag}")
            if hm < 0:
                worst.append((jc, i + 1, hm))
    b.close()

print("\n" + "=" * 60)
if worst:
    print("OVERFLOWING PAGES:")
    for jc, pn, hm in sorted(worst, key=lambda x: x[2]):
        print(f"  {jc}  page {pn}  {hm:7.1f}mm")
    print(f"\nFAIL: {len(worst)} overflowing page(s)")
    sys.exit(1)
print("PASS: no page exceeds A4 printable height")
