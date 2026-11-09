"""Provision the shared folder master without a full app deploy. --check is read-only.

Uses the same schema as after_install/after_migrate and the standard permission-checked
Frappe API. No Server Script, custom executable endpoint or stock entry is created.
"""
import argparse
import importlib.util
import pathlib
import re

import deploy_eb_dev_page as api

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("folder_schema", ROOT / "production_log/production_floor/setup/folder_registry.py")
schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)


def main():
	ap = argparse.ArgumentParser(description=__doc__)
	mode = ap.add_mutually_exclusive_group(required=True)
	mode.add_argument("--check", action="store_true")
	mode.add_argument("--apply", action="store_true")
	args = ap.parse_args()
	api.BASE = api.env("FRAPPE_URL").rstrip("/")
	api.AUTH = "token " + api.env("FRAPPE_API_KEY") + ":" + api.env("FRAPPE_API_SECRET")
	doc = api.call("frappe.client.get", {"doctype": "DocType", "name": schema.FOLDER_DOCTYPE}, get=True)
	if doc:
		field = next((f for f in doc.get("fields", []) if f.get("fieldname") == "folder_name"), {})
		if field.get("fieldtype") != "Data" or doc.get("autoname") != "field:folder_name":
			raise SystemExit("Existing VCL EB Folder has a different schema; refused to change it.")
		print("Shared folder master exists with the expected schema.")
	elif args.check:
		print("Shared folder master is not provisioned yet.")
		return
	else:
		api.call("frappe.client.insert", {"doc": schema.folder_schema()})
		print("Created shared folder master.")
	if args.check:
		return
	names = set()
	start = 0
	while True:
		rows = api.call("frappe.client.get_list", {"doctype": "Stock Entry", "fields": ["remarks"],
			"filters": [["docstatus", "=", 1], ["stock_entry_type", "=", "Material Receipt"], ["remarks", "like", "%Station folds%"]],
			"order_by": "name asc", "limit_start": start, "limit_page_length": 500}, get=True)
		for row in rows:
			remarks = row.get("remarks") or ""
			match = re.match(r"^Capture v3 · run (.+?) · confirmed twice by ", remarks)
			if match and re.search(r"(?:^| · )Station folds(?: · |$)", remarks):
				name = re.sub(r"\s+(?:-\s*)?(?:day|night)(?:\s+shift)?$", "", match[1], flags=re.I)
				name = " ".join(name.split())
				if name and len(name) <= 80 and not re.search(r"[\x00-\x1f\x7f·<>]", name):
					names.add(name[0].upper() + name[1:])
		if len(rows) < 500:
			break
		start += len(rows)
	existing = api.call("frappe.client.get_list", {"doctype": schema.FOLDER_DOCTYPE,
		"fields": ["folder_name"], "limit_page_length": 0}, get=True)
	known = {r["folder_name"].casefold() for r in existing}
	added = 0
	for name in sorted(names):
		if name.casefold() not in known:
			api.call("frappe.client.insert", {"doc": {"doctype": schema.FOLDER_DOCTYPE, "folder_name": name}})
			known.add(name.casefold())
			added += 1
	print(f"Shared names ready: {len(known)}; added from folding history: {added}. No stock entries changed.")


if __name__ == "__main__":
	main()
