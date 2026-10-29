#!/usr/bin/env python3
"""Read-only dry run of the D5 print-field correction against live (TRK-00350).

Reads every Computer Paper job card and its specification over REST and prints
exactly what patch v10_8 would change. It writes nothing.

    python3 scripts/dry_run_cp_print_correction.py
"""
import json
import pathlib
import sys
import urllib.parse

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "production_log" / "job_card_tracking"))
import cp_print_correction as c  # noqa: E402  (pure module, no frappe import)

ENV = pathlib.Path.home() / "projects/vcl-erpnext-mcp/.env"


def get_all(s, base, doctype, fields, filters=None):
	params = {"fields": json.dumps(fields), "limit_page_length": 0}
	if filters:
		params["filters"] = json.dumps(filters)
	r = s.get(f"{base}/api/resource/{urllib.parse.quote(doctype)}", params=params, timeout=300)
	r.raise_for_status()
	return r.json()["data"]


def main():
	load_dotenv(ENV)
	import os

	s = requests.Session()
	s.headers["Authorization"] = f"token {os.environ['ERPNEXT_API_KEY']}:{os.environ['ERPNEXT_API_SECRET']}"
	base = os.environ["ERPNEXT_URL"].rstrip("/")

	cards = get_all(s, base, c.CARD,
	                ["name", "docstatus", "print_type", "print_side", "printed_weight", "customer_product_spec"],
	                [["customer_product_spec", "!=", ""]])
	names = sorted({x["customer_product_spec"] for x in cards})
	specs = {x["name"]: x for x in get_all(s, base, c.SPEC,
	                                       ["name", "print_type", "print_side", "printed_weight"],
	                                       [["name", "in", names]])} if names else {}

	total = len(cards)
	plain_on_printed = sum(1 for x in cards
	                       if (x.get("print_type") or "Plain") == "Plain"
	                       and (specs.get(x["customer_product_spec"]) or {}).get("print_type") == "Printed")
	changes, cancelled = c.plan_corrections(cards, specs)

	print(f"Computer Paper job cards with a spec: {total}")
	print(f"Card Plain while spec Printed (before any cancel filter): {plain_on_printed}")
	print(f"Would change: {len(changes)}  (type: {sum(1 for x in changes if x['kind']=='type')}, "
	      f"side only: {sum(1 for x in changes if x['kind']=='side')})")
	print(f"Cancelled, left alone: {len(cancelled)} {cancelled}")
	print()
	print("name                 spec           kind  before (type/side/weight) -> after")
	for ch in changes:
		print(c.describe(ch))


if __name__ == "__main__":
	main()
