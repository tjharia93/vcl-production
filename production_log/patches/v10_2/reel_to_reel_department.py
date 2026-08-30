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

# The Slitter belongs to this department alone, but it is created by
# `seed_machines` from after_migrate rather than here - see execute().
SLITTER_MACHINE = "Slitter"


def execute():
	if not frappe.db.exists("DocType", "VCL Production Machine"):
		return

	for machine in SHARED:
		_also_serve(machine, DEPARTMENT)

	# The Slitter is NOT created here. Patches run BEFORE the after_migrate hook
	# that widens the department Select, so inserting a machine into a brand new
	# department throws _validate_selects and aborts the migrate for every app
	# on the bench. `seed_machines` creates it, and `align_machines` maps it,
	# both from after_migrate - after the Select knows the department exists.
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
