"""Point floor machines at ERPNext's Workstation and Workstation Type.

Kept here rather than inside a patch because it has to run in TWO places, and
the reason is an ordering trap that has already taken this site down once:

    frappe migrate:  pre_model_sync patches
                  -> model sync
                  -> post_model_sync patches      <- our patches run HERE
                  -> after_migrate hooks           <- apply_select_options runs HERE

`apply_select_options` is what widens the `department` Select to include a
newly added department. A patch that INSERTS a machine into a new department
therefore throws `_validate_selects` - the option does not exist yet - and a
throw inside migrate aborts it for every app on the bench.

So: patches only ever `db.set_value` on machines that already exist (no
validation), and anything that CREATES a machine happens in `after_migrate`,
after the Selects are widened and after `seed_machines`. This module is the
mapping both routes share, so they cannot drift apart.

Fills blanks only. A mapping someone has corrected by hand survives a re-run.
"""

import frappe

# machine -> (Workstation Type, Workstation or None)
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
	# Carton: stages on a line, not separate machines. Two have a Workstation;
	# the rest legitimately have none.
	"CORRUGATION": ("Corrugation", None),
	"Printing": ("Carton Printing", None),
	"Die Cutting": ("Die Cutting", None),
	"Slotting": ("Slotting", "Slotter 01"),
	"Stitching": ("Carton Stitching", None),
	"Bundling": ("Bundling", "Bundler 01"),
	"Gluing": ("Carton Gluing", None),
	# Reel to Reel. ETR is printed reel-to-reel and THEN slit; KCB-type work
	# finishes on the press. Seeded by seed_machines, mapped here.
	"Slitter": ("ETR Slitting", "Slitter 01"),
}


def align_machines():
	"""Fill in stage and workstation for every machine we have a mapping for."""
	if not frappe.db.exists("DocType", "VCL Production Machine"):
		return

	for machine, (stage, workstation) in MAPPING.items():
		if not frappe.db.exists("VCL Production Machine", machine):
			continue

		current = frappe.db.get_value(
			"VCL Production Machine", machine, ["stage", "erpnext_workstation"], as_dict=True
		)
		if not current.stage and stage and frappe.db.exists("Workstation Type", stage):
			frappe.db.set_value("VCL Production Machine", machine, "stage", stage)
		if workstation and not current.erpnext_workstation:
			if frappe.db.exists("Workstation", workstation):
				frappe.db.set_value(
					"VCL Production Machine", machine, "erpnext_workstation", workstation
				)
