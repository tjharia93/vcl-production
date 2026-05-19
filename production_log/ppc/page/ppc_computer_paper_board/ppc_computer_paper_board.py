import frappe


@frappe.whitelist()
def list_workstations():
	"""Return workstations relevant to Computer Paper PPC."""
	relevant = [
		"Miyakoshi 01",
		"Miyakoshi 2",
		"Miyakoshi 3",
		"Collater 01",
		"Collater 02",
		"Packing Station",
	]
	rows = frappe.get_all(
		"Workstation",
		filters={"name": ["in", relevant]},
		fields=["name", "workstation_type"],
		order_by="name asc",
	)
	if rows:
		return rows
	# Fallback: all workstations if the named ones don't exist on this site.
	return frappe.get_all(
		"Workstation",
		fields=["name", "workstation_type"],
		order_by="name asc",
		limit=20,
	)
