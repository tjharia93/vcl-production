"""Give Reel to Reel work its own department without cloning the presses.

KCB-type reel work and ETR are both printed on the Miyakoshis - the same four
presses that print Computer Paper. The floor wants to see that work separately,
but a press must not become two records: that splits one machine's history in
half and shows it twice on the board.

So `also_serves` widens where an existing machine can be picked, rather than a
duplicate being created. M1..M4 stay Computer Paper's machines and become
selectable under Reel to Reel too.

The Slitter is the one machine only this department uses. ETR is printed
reel-to-reel and THEN slit; KCB-type work finishes on the press. That single
extra stage is the whole difference between the two, which is why they are one
department with two routes rather than two departments.

Idempotent: adds a department to `also_serves` only when it is not already
listed, and never removes one.
"""

import frappe

DEPARTMENT = "Reel to Reel"

# The presses shared with Computer Paper.
SHARED = ["M1", "M2", "M3", "M4"]

# Only this department slits. Stage and Workstation match the v10_1 mapping.
SLITTER = {
	"machine_name": "Slitter",
	"department": DEPARTMENT,
	"machine_type": "Machine",
	"display_order": 10,
	"stage": "ETR Slitting",
	"erpnext_workstation": "Slitter 01",
}


def execute():
	if not frappe.db.exists("DocType", "VCL Production Machine"):
		return

	for machine in SHARED:
		_also_serve(machine, DEPARTMENT)

	_ensure_slitter()
	frappe.db.commit()


def _also_serve(machine, department):
	if not frappe.db.exists("VCL Production Machine", machine):
		return
	current = frappe.db.get_value("VCL Production Machine", machine, "also_serves") or ""
	listed = [line.strip() for line in current.splitlines() if line.strip()]
	if department in listed:
		return
	listed.append(department)
	frappe.db.set_value(
		"VCL Production Machine", machine, "also_serves", "\n".join(listed)
	)


def _ensure_slitter():
	name = SLITTER["machine_name"]
	if frappe.db.exists("VCL Production Machine", name):
		# Someone may have added it by hand already; fill only what is blank.
		for field in ("stage", "erpnext_workstation"):
			value = SLITTER[field]
			if frappe.db.get_value("VCL Production Machine", name, field):
				continue
			if field == "stage" and not frappe.db.exists("Workstation Type", value):
				continue
			if field == "erpnext_workstation" and not frappe.db.exists("Workstation", value):
				continue
			frappe.db.set_value("VCL Production Machine", name, field, value)
		return

	doc = {
		"doctype": "VCL Production Machine",
		"machine_name": name,
		"department": SLITTER["department"],
		"machine_type": SLITTER["machine_type"],
		"display_order": SLITTER["display_order"],
		"active": 1,
	}
	if frappe.db.exists("Workstation Type", SLITTER["stage"]):
		doc["stage"] = SLITTER["stage"]
	if frappe.db.exists("Workstation", SLITTER["erpnext_workstation"]):
		doc["erpnext_workstation"] = SLITTER["erpnext_workstation"]
	frappe.get_doc(doc).insert(ignore_permissions=True)
