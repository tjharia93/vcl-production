"""
Patch v4_0: Set default print formats for the three Job Card types.

Creates a Property Setter per DocType so opening a job card and hitting
Print selects the custom traveller without the user having to pick it.

Runs after the Print Format fixtures have synced on each migrate cycle.
Safe to run multiple times.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


DEFAULTS = [
	("Job Card Computer Paper", "Computer Paper Job Traveller"),
	("Job Card Label",          "Label Job Traveller"),
	("Job Card Carton",         "Carton Job Card"),
]


def execute():
	for doctype, print_format in DEFAULTS:
		# Only apply if the Print Format record exists (guards against running
		# before fixture sync on a fresh install).
		if not frappe.db.exists("Print Format", print_format):
			continue

		make_property_setter(
			doctype        = doctype,
			fieldname      = "",
			property       = "default_print_format",
			value          = print_format,
			property_type  = "Data",
			for_doctype    = True,
			validate_fields_for_doctype = False,
		)

		frappe.clear_cache(doctype=doctype)

	frappe.db.commit()
