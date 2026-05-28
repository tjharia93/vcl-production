#!/usr/bin/env python3
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path('/home/tanujharia/projects/vcl-production')
src = REPO / 'briefs/VCL-DEV-PROD-001_status_report.html'
out = REPO / 'briefs/VCL-DEV-PROD-001_status_report.pdf'

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(f'file://{src}', wait_until='networkidle')
    page.wait_for_timeout(500)
    page.pdf(path=str(out), format='A4', print_background=True,
             margin={'top':'0mm','right':'0mm','bottom':'0mm','left':'0mm'},
             prefer_css_page_size=True)
    print(f'wrote {out} ({out.stat().st_size:,} bytes)')
    browser.close()
