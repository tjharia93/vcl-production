"""Point the floor's machine master at ERPNext's own Workstation vocabulary.

VCL had two machine lists that did not agree. The job cards write machine names
straight from ERPNext - `Miyakoshi 01`, `Miyakoshi 3`, `Collater 01` - while the
floor master carried `M1`..`M4`, `Collator`, and a second `Miyakoshi` filed
under Offset. Any roll-up across the two would have silently dropped rows.

ERPNext already holds the whole model:
  * `Workstation`      - the physical machines, named as the job cards name them
  * `Workstation Type` - 21 stages, sequenced by `custom_stage_position`

So nothing new is invented here. Each floor machine is pointed at the stage it
serves, and at the Workstation behind it where one exists.

Two shapes, both legitimate:
  * a real machine       -> stage AND workstation   (M1 -> Reel to Reel Printing / Miyakoshi 01)
  * a process, not a box -> stage only              (Stitching -> Carton Stitching)

Monobox is deliberately left without stages: Coating, Window Patching and
Folding & Gluing have no Workstation Type yet. Those are being built out, and a
blank stage is the honest state until they exist - better than mapping Window
Patching onto Lamination because it is nearby.

Idempotent. Only ever fills a blank; never overwrites a mapping someone has
since corrected by hand.
"""

import frappe

# floor machine -> (Workstation Type, Workstation or None)
MAPPING = {
	# Computer Paper is reel-to-reel, which is what the Miyakoshis are.
	"M1": ("Reel to Reel Printing", "Miyakoshi 01"),
	"M2": ("Reel to Reel Printing", "Miyakoshi 2"),
	"M3": ("Reel to Reel Printing", "Miyakoshi 3"),
	"M4": ("Reel to Reel Printing", "Miyakoshi 4"),
	"Collator": ("Collation", "Collater 01"),
	# Offset is sheet-fed.
	"Solna": ("Sheet to Sheet Printing", "Solna 02"),
	"Miller": ("Sheet to Sheet Printing", "Miller 01"),
	"Propheteer": ("Label Printing", "Profeteer 01"),
	# Carton: these are stages on a line, not separate machines. Two of them do
	# have a Workstation; the rest legitimately have none.
	"CORRUGATION": ("Corrugation", None),
	"Printing": ("Carton Printing", None),
	"Die Cutting": ("Die Cutting", None),
	"Slotting": ("Slotting", "Slotter 01"),
	"Stitching": ("Carton Stitching", None),
	"Bundling": ("Bundling", "Bundler 01"),
	"Gluing": ("Carton Gluing", None),
}

# The floor's own holding areas. They are real to a supervisor - work sits in
# them - but they are not production stages and ERPNext has no type for them.
NOT_A_STAGE = {"PLANNING", "PLANNING STAGE - PRINTING"}

# `Miyakoshi` was filed under Offset, but the Miyakoshis print Computer Paper
# and are already in the master as M1..M4. Deactivated rather than deleted:
# historic production rows point at the name, and seed_machines would recreate
# a deleted row on the next migrate anyway.
DUPLICATE = "Miyakoshi"

# Still running, but never entered in ERPNext. House naming is numbered -
# Solna 02, Collater 01, Bundler 01 - so it joins as Miller 01.
MILLER = {"workstation_name": "Miller 01", "workstation_type": "Sheet to Sheet Printing"}


def execute():
	if not frappe.db.exists("DocType", "VCL Production Machine"):
		return

	_ensure_miller()

	for machine, (stage, workstation) in MAPPING.items():
		if not frappe.db.exists("VCL Production Machine", machine):
			continue

		current = frappe.db.get_value(
			"VCL Production Machine", machine, ["stage", "erpnext_workstation"], as_dict=True
		)

		if not current.stage and frappe.db.exists("Workstation Type", stage):
			frappe.db.set_value("VCL Production Machine", machine, "stage", stage)

		if workstation and not current.erpnext_workstation:
			if frappe.db.exists("Workstation", workstation):
				frappe.db.set_value(
					"VCL Production Machine", machine, "erpnext_workstation", workstation
				)

	_retire_duplicate()
	frappe.db.commit()


def _ensure_miller():
	"""Create the one machine the floor runs that ERPNext never knew about."""
	if frappe.db.exists("Workstation", MILLER["workstation_name"]):
		return
	if not frappe.db.exists("Workstation Type", MILLER["workstation_type"]):
		return
	frappe.get_doc({"doctype": "Workstation", **MILLER}).insert(ignore_permissions=True)


def _retire_duplicate():
	if not frappe.db.exists("VCL Production Machine", DUPLICATE):
		return
	# Only if nothing has been mapped onto it in the meantime - someone may have
	# decided it is a real separate press after all.
	mapped = frappe.db.get_value("VCL Production Machine", DUPLICATE, "erpnext_workstation")
	if mapped:
		return
	frappe.db.set_value("VCL Production Machine", DUPLICATE, "active", 0)
