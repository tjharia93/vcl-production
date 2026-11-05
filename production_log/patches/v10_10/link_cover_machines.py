"""Solna and Miller print exercise-book covers (Tanuj, 05/11/2026).

Sets each machine's Asset and lists Covers in Exercise Book Stations, so Capture shows
them on the Covers station. Later machines need no patch: fill the two fields in on the
machine record. Only ever updates a row that exists, and leaves a field someone has
already filled in alone.
"""

import frappe

COVER_MACHINES = {
	"Solna": "ACC-ASS-2024-00010",  # Solna 425 (New)
	"Miller": "PRINTING MACHINE 05",  # MILLER, still a Draft asset on 05/11/2026
}


def execute():
	for machine, asset in COVER_MACHINES.items():
		if not frappe.db.exists("VCL Production Machine", machine):
			continue
		current = frappe.db.get_value("VCL Production Machine", machine, ["asset", "eb_stations"], as_dict=True)
		if not current.asset and frappe.db.exists("Asset", asset):
			frappe.db.set_value("VCL Production Machine", machine, "asset", asset)
		if not current.eb_stations:
			frappe.db.set_value("VCL Production Machine", machine, "eb_stations", "Covers")
