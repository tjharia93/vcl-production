"""Add-only Hi5 stage-item setup. Never creates or changes stock transactions."""
import re

BOOK = re.compile(r"^Hi5-(A4|A5)-(\d+)PGS-([A-Z]+)-BP-([A-Z0-9]+)$")
STAGES = (("COV", "Exercise Book Covers", "Cover sheets"), ("FLD", "Folds", "Folds"), ("INS", "Exercise Book Inserts", "Inserts"))


def planned_items(books):
	"""One set of stage items per active size/pages/lines combination, across covers."""
	out = {}
	for book in books:
		match = BOOK.fullmatch(book.get("name", ""))
		if book.get("disabled") or not match:
			continue
		size, pages, cover, ruling = match.groups()
		ups = 2 if size == "A4" else 3
		for prefix, group, label in STAGES:
			code = f"{prefix}-HI5-{size}-{int(pages):03d}PG-{ruling}"
			out[code] = {"doctype": "Item", "item_code": code,
				"item_name": f"Hi5 {label} - {size} - {int(pages)} pages - {ruling} - {ups} up",
				"item_group": group, "stock_uom": "Nos", "is_stock_item": 1,
				"is_sales_item": 0, "is_purchase_item": 0, "include_item_in_manufacturing": 1}
	return [out[key] for key in sorted(out)]


def ensure_hi5_items():
	import frappe
	books = frappe.get_all("Item", filters={"name": ["like", "Hi5-A%"], "disabled": 0}, fields=["name", "disabled"])
	for doc in planned_items(books):
		if not frappe.db.exists("Item", doc["item_code"]):
			frappe.get_doc(doc).insert(ignore_permissions=True)
