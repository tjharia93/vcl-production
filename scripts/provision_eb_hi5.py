"""Add Hi5 COV/FLD/INS items for active finished books; never posts stock.

--check is read-only. --apply uses the same add-only setup as after_migrate.
"""
import argparse
import importlib.util
import pathlib

import deploy_eb_dev_page as api

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("hi5_item_setup", ROOT / "production_log/production_floor/setup/hi5_items.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def main():
	ap = argparse.ArgumentParser(description=__doc__)
	mode = ap.add_mutually_exclusive_group(required=True)
	mode.add_argument("--check", action="store_true")
	mode.add_argument("--apply", action="store_true")
	args = ap.parse_args()
	api.BASE = api.env("FRAPPE_URL").rstrip("/")
	api.AUTH = "token " + api.env("FRAPPE_API_KEY") + ":" + api.env("FRAPPE_API_SECRET")
	books = api.call("frappe.client.get_list", {"doctype": "Item", "fields": ["name", "disabled"],
		"filters": [["name", "like", "Hi5-A%"], ["disabled", "=", 0]], "limit_page_length": 0}, get=True)
	docs = setup.planned_items(books)
	existing = api.call("frappe.client.get_list", {"doctype": "Item", "fields": ["name", "item_group", "stock_uom", "is_stock_item", "disabled"],
		"or_filters": [["name", "like", "COV-HI5-%"], ["name", "like", "FLD-HI5-%"], ["name", "like", "INS-HI5-%"]], "limit_page_length": 0}, get=True)
	known = {d["name"]: d for d in existing}
	for doc in docs:
		old = known.get(doc["item_code"])
		if old and (old["item_group"] != doc["item_group"] or old["stock_uom"] != "Nos" or not old["is_stock_item"] or old["disabled"]):
			raise SystemExit("Existing stage item differs from the expected active Nos stock item: " + doc["item_code"])
	missing = [d for d in docs if d["item_code"] not in known]
	print(f"Hi5 active finished books: {len(books)}; stage items: {len(docs)}; missing: {len(missing)}.", flush=True)
	if args.check:
		return
	for index, doc in enumerate(missing, 1):
		api.call("frappe.client.insert", {"doc": doc})
		if index % 30 == 0 or index == len(missing):
			print(f"Created {index}/{len(missing)} stage item masters.", flush=True)
	print("Hi5 item masters ready. No stock entries or empty-carton items created.")


if __name__ == "__main__":
	main()
