import frappe


def execute():
	if not frappe.db.exists("Role", "PPC Planner"):
		frappe.get_doc({
			"doctype": "Role",
			"role_name": "PPC Planner",
			"desk_access": 1,
		}).insert(ignore_permissions=True)
		frappe.db.commit()
