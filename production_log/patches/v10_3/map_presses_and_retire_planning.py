"""Map the two unmapped presses, and take planning off the machine list.

Decisions from Tanuj, 2026-09-03:
  - Roland maps like M4, so reel-fed printing.
  - Kord is a printing machine, so sheet-fed like Solna and Miller beside it.
  - Pasting gets the Carton Pasting type that already exists.
  - The two PLANNING entries stop being pickable. Planning is a process; it is
    not something production is recorded against.

⛔ This patch NEVER creates a machine. `seed_machines` owns creation, and a
machine inserted here would fail `_validate_selects` if its department Select
had not been widened yet - which is how five lines of seed data once took the
whole site down.

Retiring is `active = 0`, never a delete: `seed_machines` runs from
after_migrate and puts a deleted machine straight back, losing its history with
it.
"""

import frappe

STAGES = {
	# Reel-FED printing. Says nothing about whether the press can produce a
	# finished reel - per the department master, Roland and M4 cannot.
	"Roland": "Reel to Reel Printing",
	"Kord": "Sheet to Sheet Printing",
	"Pasting": "Carton Pasting",
}

RETIRE = ("PLANNING", "PLANNING STAGE - PRINTING")


def execute():
	if not frappe.db.exists("DocType", "VCL Production Machine"):
		return

	for machine, stage in STAGES.items():
		if not frappe.db.exists("VCL Production Machine", machine):
			continue
		if not frappe.db.exists("Workstation Type", stage):
			continue
		if frappe.db.get_value("VCL Production Machine", machine, "stage"):
			# Already mapped, by hand or by an earlier run. Leave it alone.
			continue
		frappe.db.set_value("VCL Production Machine", machine, "stage", stage)

	for machine in RETIRE:
		if frappe.db.exists("VCL Production Machine", machine):
			frappe.db.set_value("VCL Production Machine", machine, "active", 0)

	frappe.db.commit()
