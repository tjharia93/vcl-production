"""
Patch v4_0: Set Label Job Traveller as the default print format for Job Card Label.

Creates (or updates) a Property Setter so opening a Label job card and
hitting Print selects the traveller without the user having to pick it
every time.

Runs after the Print Format fixture has been synced, which happens on
every migrate cycle. Safe to run multiple times.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


DOCTYPE       = "Job Card Label"
PRINT_FORMAT  = "Label Job Traveller"


def execute():
	# Only apply if the Print Format record exists (guards against running
	# before fixture sync on a fresh install).
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		return

	make_property_setter(
		doctype        = DOCTYPE,
		fieldname      = "",
		property       = "default_print_format",
		value          = PRINT_FORMAT,
		property_type  = "Data",
		for_doctype    = True,
		validate_fields_for_doctype = False,
	)

	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
