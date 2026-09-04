# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

"""The desk-side view of the same data the floor screen shows.

Defaults to today, and to a single day, because that is what gets read. A
date range is there for the week-in-review conversation.
"""

import frappe
from frappe import _
from frappe.utils import today

from production_log.production_floor.reporting import day_in_progress, find_exceptions

def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "production_date", "fieldtype": "Date", "width": 100},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 110},
		{
			"label": _("Machine / Process"),
			"fieldname": "machine",
			"fieldtype": "Link",
			"options": "VCL Production Machine",
			"width": 140,
		},
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
		{"label": _("Job"), "fieldname": "job_name", "fieldtype": "Data", "width": 170},
		{"label": _("Plan"), "fieldname": "planned_quantity", "fieldtype": "Float", "precision": 3, "width": 90},
		{"label": _("Actual"), "fieldname": "actual_quantity", "fieldtype": "Float", "precision": 3, "width": 90},
		{"label": _("Unit"), "fieldname": "uom", "fieldtype": "Data", "width": 80},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 200},
		{"label": _("Attention"), "fieldname": "attention", "fieldtype": "Data", "width": 220},
		{"label": _("Notes"), "fieldname": "notes", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	from_date = filters.get("from_date") or filters.get("production_date") or today()
	to_date = filters.get("to_date") or from_date

	conditions = ["day.production_date BETWEEN %(from_date)s AND %(to_date)s"]
	values = {"from_date": from_date, "to_date": to_date}

	if filters.get("department"):
		conditions.append("item.department = %(department)s")
		values["department"] = filters.get("department")
	if filters.get("status"):
		conditions.append("item.status = %(status)s")
		values["status"] = filters.get("status")
	if not filters.get("include_demo"):
		conditions.append("day.is_demo = 0")

	rows = frappe.db.sql(
		"""
		SELECT
			day.production_date, day.name AS day_name, day.status AS day_status,
			item.name, item.idx, item.department, item.machine,
			item.customer_name, item.job_name,
			item.planned_quantity, item.actual_quantity, item.uom,
			item.status, item.reason, item.notes
		FROM `tabVCL Daily Production Item` item
		INNER JOIN `tabVCL Daily Production` day ON day.name = item.parent
		WHERE {conditions}
		ORDER BY day.production_date DESC, item.department ASC, item.idx ASC
		""".format(conditions=" AND ".join(conditions)),
		values,
		as_dict=True,
	)

	# Attention text comes from the same rules the floor screen uses, so the
	# desk and the phone can never disagree about what is missing. Run PER DAY,
	# because whether a day is still in progress is a property of that day - a
	# range that includes today must not flag today's open rows as overdue for
	# an update while flagging last week's correctly.
	by_day = {}
	for row in rows:
		by_day.setdefault(row["day_name"], []).append(row)

	notes_by_row = {}
	for day_rows in by_day.values():
		first = day_rows[0]
		in_progress = day_in_progress({
			"status": first.get("day_status"),
			"production_date": first.get("production_date"),
		})
		for exception in find_exceptions([dict(r) for r in day_rows], in_progress=in_progress):
			notes_by_row.setdefault(exception["row_name"], []).append(exception["message"])

	for row in rows:
		row["attention"] = "; ".join(notes_by_row.get(row["name"], []))
	return rows
