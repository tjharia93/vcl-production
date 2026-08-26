# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from production_log.production_floor.reporting import DEFAULT_DEPARTMENTS, DEFAULT_UNITS

# Every Select field whose options come from Settings rather than the DocType
# JSON. Adding a department has to change all of them at once, or the machine
# master and the production row disagree about what departments exist.
DEPARTMENT_FIELDS = [
	("VCL Production Machine", "department", False),
	("VCL Daily Production Item", "department", False),
	("VCL Production Job", "department", True),
]

UNIT_FIELDS = [
	("VCL Daily Production Item", "uom", False),
	("VCL Production Job", "default_uom", True),
]


class VCLProductionSettings(Document):
	def on_update(self):
		apply_select_options()


def split_lines(text, fallback):
	values = [line.strip() for line in (text or "").splitlines()]
	values = [v for v in values if v]
	return values or list(fallback)


def get_departments():
	return split_lines(
		frappe.db.get_single_value("VCL Production Settings", "departments"),
		DEFAULT_DEPARTMENTS,
	)


def get_units():
	return split_lines(
		frappe.db.get_single_value("VCL Production Settings", "units"),
		DEFAULT_UNITS,
	)


def apply_select_options():
	"""Push the configured lists onto the Select fields as Property Setters.

	Property Setters rather than edits to the DocType JSON, so a site keeps
	its own departments across an app upgrade instead of having them reset.
	"""
	departments = get_departments()
	units = get_units()

	for doctype, fieldname, allow_blank in DEPARTMENT_FIELDS:
		_set_options(doctype, fieldname, departments, allow_blank)
	for doctype, fieldname, allow_blank in UNIT_FIELDS:
		_set_options(doctype, fieldname, units, allow_blank)

	frappe.clear_cache()


def _set_options(doctype, fieldname, values, allow_blank):
	if not frappe.db.exists("DocType", doctype):
		return
	options = "\n".join(([""] if allow_blank else []) + list(values))
	frappe.make_property_setter(
		{
			"doctype": doctype,
			"fieldname": fieldname,
			"property": "options",
			"value": options,
			"property_type": "Text",
		},
		is_system_generated=True,
	)
