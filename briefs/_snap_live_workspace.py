#!/usr/bin/env python3
"""Capture screenshots of the deployed VCL Production workspace."""
from pathlib import Path
from playwright.sync_api import sync_playwright

env = {}
for line in open('/opt/vcl/config/.env'):
    if '=' in line and not line.strip().startswith('#'):
        k, _, v = line.strip().partition('=')
        env[k] = v
KEY, SECRET, URL = env['ERPNEXT_API_KEY'], env['ERPNEXT_API_SECRET'], env['ERPNEXT_URL']

REPO = Path('/home/tanujharia/projects/vcl-production')
OUT = REPO / 'briefs/screenshots'
OUT.mkdir(parents=True, exist_ok=True)

def snap(page, name):
    out = OUT / f'{name}.png'
    page.screenshot(path=str(out), full_page=True)
    print(f'{name}: {out.stat().st_size:,} bytes')

targets = [
    ('vcl-production-workspace', f'{URL}/app/vcl-production'),
    ('ppc-workspace',            f'{URL}/app/ppc'),
    ('cps-list',                 f'{URL}/app/customer-product-specification'),
    ('job-card-carton-list',     f'{URL}/app/job-card-carton'),
    ('job-card-label-list',      f'{URL}/app/job-card-label'),
    ('dies-list',                f'{URL}/app/dies'),
    ('ppc-daily-plan-list',      f'{URL}/app/ppc-daily-plan'),
    ('ppc-open-job-pool',        f'{URL}/app/query-report/PPC Open Job Pool'),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(
        viewport={'width': 1440, 'height': 900},
        device_scale_factor=2,
        extra_http_headers={'Authorization': f'token {KEY}:{SECRET}'},
    )
    for name, url in targets:
        page = ctx.new_page()
        try:
            page.goto(url, wait_until='networkidle', timeout=45000)
            page.wait_for_timeout(2200)
            snap(page, name)
        except Exception as e:
            print(f'{name}: FAILED — {e}')
        page.close()
    browser.close()
