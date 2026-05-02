"""PPC May 26 v1 — JC-CPT field updates.

Adds the priority / hold / completion / reopen / cancel / packing-visibility
fields per ppc_may26_v1 spec page 01, and expands job_status to the 8-value
enum per spec page 02.

Status enum migration:
  'In Progress'         -> 'In Production'
  'Production Completed'-> 'Completed'         (only present if a prior PPC v2 attempt landed)
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


JC = "Job Card Computer Paper"

NEW_STATUS_OPTIONS = "\n".join([
	"Open",
	"Planned",
	"In Production",
	"Packing Pending",
	"Completed",
	"Closed",
	"On Hold",
	"Cancelled",
])


CUSTOM_FIELDS = {
	JC: [
		# Priority
		{
			"fieldname": "ppc_section_priority",
			"label": "Priority",
			"fieldtype": "Section Break",
			"insert_after": "job_status",
			"collapsible": 1,
		},
		{
			"fieldname": "priority",
			"label": "Priority",
			"fieldtype": "Select",
			"options": "Normal\nHigh\nUrgent\nCritical",
			"default": "Normal",
			"insert_after": "ppc_section_priority",
			"in_list_view": 1,
		},
		{
			"fieldname": "priority_reason",
			"label": "Priority Reason",
			"fieldtype": "Small Text",
			"insert_after": "priority",
			"depends_on": "eval:['Urgent','Critical'].includes(doc.priority)",
			"mandatory_depends_on": "eval:['Urgent','Critical'].includes(doc.priority)",
		},
		{
			"fieldname": "priority_changed_by",
			"label": "Priority Changed By",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "priority_reason",
			"read_only": 1,
		},
		{
			"fieldname": "priority_changed_on",
			"label": "Priority Changed On",
			"fieldtype": "Datetime",
			"insert_after": "priority_changed_by",
			"read_only": 1,
		},
		# Hold
		{
			"fieldname": "ppc_section_hold",
			"label": "Hold Control",
			"fieldtype": "Section Break",
			"insert_after": "priority_changed_on",
			"collapsible": 1,
			"depends_on": "eval:doc.job_status=='On Hold' || doc.hold_reason",
		},
		{
			"fieldname": "hold_reason",
			"label": "Hold Reason",
			"fieldtype": "Select",
			"options": "\nMaterial shortage\nPlate / film issue\nMachine issue\nCustomer confirmation pending\nManagement hold\nQuality issue\nCylinder / tooling issue\nOther",
			"insert_after": "ppc_section_hold",
			"mandatory_depends_on": "eval:doc.job_status=='On Hold'",
		},
		{
			"fieldname": "hold_remarks",
			"label": "Hold Remarks",
			"fieldtype": "Small Text",
			"insert_after": "hold_reason",
			"mandatory_depends_on": "eval:doc.job_status=='On Hold'",
		},
		{
			"fieldname": "hold_previous_status",
			"label": "Hold Previous Status",
			"fieldtype": "Data",
			"insert_after": "hold_remarks",
			"read_only": 1,
		},
		{
			"fieldname": "hold_by",
			"label": "Hold By",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "hold_previous_status",
			"read_only": 1,
		},
		{
			"fieldname": "hold_on",
			"label": "Hold On",
			"fieldtype": "Datetime",
			"insert_after": "hold_by",
			"read_only": 1,
		},
		{
			"fieldname": "hold_cleared_by",
			"label": "Hold Cleared By",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "hold_on",
			"read_only": 1,
		},
		{
			"fieldname": "hold_cleared_on",
			"label": "Hold Cleared On",
			"fieldtype": "Datetime",
			"insert_after": "hold_cleared_by",
			"read_only": 1,
		},
		# Completion + Closure
		{
			"fieldname": "ppc_section_close",
			"label": "Completion & Closure",
			"fieldtype": "Section Break",
			"insert_after": "hold_cleared_on",
			"collapsible": 1,
		},
		{
			"fieldname": "production_completed_on",
			"label": "Production Completed On",
			"fieldtype": "Datetime",
			"insert_after": "ppc_section_close",
			"read_only": 1,
		},
		{
			"fieldname": "closed_by",
			"label": "Closed By",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "production_completed_on",
			"read_only": 1,
		},
		{
			"fieldname": "closed_on",
			"label": "Closed On",
			"fieldtype": "Datetime",
			"insert_after": "closed_by",
			"read_only": 1,
		},
		{
			"fieldname": "closing_remarks",
			"label": "Closing Remarks",
			"fieldtype": "Small Text",
			"insert_after": "closed_on",
		},
		# Reopen
		{
			"fieldname": "ppc_section_reopen",
			"label": "Reopen Control",
			"fieldtype": "Section Break",
			"insert_after": "closing_remarks",
			"collapsible": 1,
			"depends_on": "eval:doc.reopened_on",
		},
		{
			"fieldname": "reopened_by",
			"label": "Reopened By",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "ppc_section_reopen",
			"read_only": 1,
		},
		{
			"fieldname": "reopened_on",
			"label": "Reopened On",
			"fieldtype": "Datetime",
			"insert_after": "reopened_by",
			"read_only": 1,
		},
		{
			"fieldname": "reopen_reason",
			"label": "Reopen Reason",
			"fieldtype": "Small Text",
			"insert_after": "reopened_on",
		},
		# Cancel
		{
			"fieldname": "ppc_section_cancel",
			"label": "Cancellation Control",
			"fieldtype": "Section Break",
			"insert_after": "reopen_reason",
			"collapsible": 1,
			"depends_on": "eval:doc.job_status=='Cancelled' || doc.cancel_reason",
		},
		{
			"fieldname": "cancel_reason",
			"label": "Cancel Reason",
			"fieldtype": "Small Text",
			"insert_after": "ppc_section_cancel",
			"mandatory_depends_on": "eval:doc.job_status=='Cancelled'",
		},
		{
			"fieldname": "cancel_remarks",
			"label": "Cancel Remarks",
			"fieldtype": "Small Text",
			"insert_after": "cancel_reason",
		},
		{
			"fieldname": "cancelled_by",
			"label": "Cancelled By",
			"fieldtype": "Link",
			"options": "User",
			"insert_after": "cancel_remarks",
			"read_only": 1,
		},
		{
			"fieldname": "cancelled_on",
			"label": "Cancelled On",
			"fieldtype": "Datetime",
			"insert_after": "cancelled_by",
			"read_only": 1,
		},
		# Packing visibility
		{
			"fieldname": "ppc_section_packing",
			"label": "Packing Visibility",
			"fieldtype": "Section Break",
			"insert_after": "cancelled_on",
			"collapsible": 1,
		},
		{
			"fieldname": "loose_balance_sets",
			"label": "Loose Balance Sets",
			"fieldtype": "Float",
			"insert_after": "ppc_section_packing",
			"description": "Sets produced but not yet packed into good cartons.",
		},
		{
			"fieldname": "rejected_cartons",
			"label": "Rejected Cartons",
			"fieldtype": "Int",
			"insert_after": "loose_balance_sets",
		},
		{
			"fieldname": "rejected_quantity",
			"label": "Rejected Quantity",
			"fieldtype": "Float",
			"insert_after": "rejected_cartons",
		},
		{
			"fieldname": "packing_pending",
			"label": "Packing Pending",
			"fieldtype": "Check",
			"insert_after": "rejected_quantity",
			"read_only": 1,
			"description": "Set when production exists but packing is not fully complete.",
		},
	]
}


def execute():
	# 1. Expand job_status options.
	make_property_setter(
		JC,
		"job_status",
		"options",
		NEW_STATUS_OPTIONS,
		"Text",
		validate_fields_for_doctype=False,
	)

	# 2. Migrate any pre-existing values that are no longer valid.
	frappe.db.sql(
		f"UPDATE `tab{JC}` SET job_status = 'In Production' WHERE job_status = 'In Progress'"
	)
	frappe.db.sql(
		f"UPDATE `tab{JC}` SET job_status = 'Completed' WHERE job_status = 'Production Completed'"
	)

	# 3. Add custom fields (idempotent — Frappe handles the existence check).
	create_custom_fields(CUSTOM_FIELDS, update=True)

	frappe.db.commit()
