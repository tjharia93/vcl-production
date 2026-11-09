"""Schema for the shared folding-name master; also usable by the PC provisioner."""

FOLDER_DOCTYPE = "VCL EB Folder"


def folder_schema():
	return {
		"doctype": "DocType", "name": FOLDER_DOCTYPE, "module": "Production Floor", "custom": 1,
		"autoname": "field:folder_name", "title_field": "folder_name", "search_fields": "folder_name",
		"description": "Shared folding names for exercise-book capture.", "track_changes": 1,
		"field_order": ["folder_name"],
		"fields": [{"fieldname": "folder_name", "label": "Folder name", "fieldtype": "Data",
			"length": 80, "reqd": 1, "unique": 1, "in_list_view": 1}],
		"permissions": [{"role": role, "read": 1, "create": 1, "write": 1, "select": 1}
			for role in ("Stock User", "Stock Manager", "Manufacturing User", "Manufacturing Manager", "System Manager")],
	}


def ensure_folder_registry():
	"""Add-only: keep an existing shared master and its names untouched."""
	import frappe
	if not frappe.db.exists("DocType", FOLDER_DOCTYPE):
		frappe.get_doc(folder_schema()).insert(ignore_permissions=True)
