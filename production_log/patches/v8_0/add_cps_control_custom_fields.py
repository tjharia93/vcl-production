"""Custom Fields for CPS control of Sales Order lines.

Schema only - this patch adds no behaviour. Every rule that reads these fields
is gated on Selling Settings custom_cps_control_enabled, which ships off, so
this can land well ahead of the cutover and be rolled back by deleting the
fields (design §15 steps 2, 5 and 7).

Core DocTypes cannot take DocField writes on Frappe Cloud (403), so Item, Item
Group, Sales Order Item and Selling Settings change by Custom Field. The
app-owned DocTypes - Customer Product Specification, CPS Price and Job Card
Computer Paper - change by git deploy plus migrate instead.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking.so_spec_control import CONTROL_FLAG

CPS = "Customer Product Specification"

CPS_PRODUCT_TYPES = "\nComputer Paper\nCarton\nLabel\nExercise Books\nETR (Reel to Reel Printing)"
PRICE_SOURCES = "\nCPS Price\nItem Price\nManual Override"


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache()


def get_custom_fields():
	return {
		"Item Group": [
			{
				"fieldname": "custom_spec_control_section",
				"label": "Specification Control",
				"fieldtype": "Section Break",
				"insert_after": "is_group",
			},
			{
				"fieldname": "custom_requires_cps",
				"label": "Requires Customer Product Specification",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "custom_spec_control_section",
				"description": (
					"Items in this group, and in every group beneath it, must carry a "
					"Customer Product Specification on a Sales Order line."
				),
			},
			{
				"fieldname": "custom_cps_product_type",
				"label": "CPS Product Type",
				"fieldtype": "Select",
				"options": CPS_PRODUCT_TYPES,
				"insert_after": "custom_requires_cps",
				"depends_on": "eval:doc.custom_requires_cps",
				"description": "Which kind of specification these items need. Required when the box above is ticked.",
			},
		],
		"Item": [
			{
				"fieldname": "custom_requires_cps",
				"label": "Requires CPS",
				"fieldtype": "Check",
				"default": "0",
				"read_only": 1,
				"insert_after": "item_group",
				"description": "Derived from the Item Group tree. Configure this on the Item Group, not here.",
			},
		],
		"Selling Settings": [
			{
				"fieldname": "custom_cps_control_section",
				"label": "Customer Product Specification Control",
				"fieldtype": "Section Break",
				"insert_after": "maintain_same_sales_rate",
			},
			{
				"fieldname": CONTROL_FLAG,
				"label": "Enforce CPS Control on Sales Orders",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "custom_cps_control_section",
				"description": (
					"Off by default. While off, every specification and pricing rule on "
					"Sales Order lines is inert and ordering behaves exactly as it does today."
				),
			},
			{
				"fieldname": "custom_cps_price_tolerance_pct",
				"label": "CPS Price Tolerance (%)",
				"fieldtype": "Percent",
				"insert_after": CONTROL_FLAG,
				"description": (
					"Leave blank for exact-match-only: any deviation from the approved rate "
					"needs an authorised override. Set a value only if management agrees one."
				),
			},
			{
				"fieldname": "custom_cps_price_floor_pct",
				"label": "CPS Price Floor (%)",
				"fieldtype": "Percent",
				"insert_after": "custom_cps_price_tolerance_pct",
				"description": (
					"Leave blank to disable the floor. Once set, no role may submit below "
					"this percentage of the approved rate - including System Manager."
				),
			},
		],
		"Customer Product Specification": [
			{
				"fieldname": "linked_item",
				"label": "Item",
				"fieldtype": "Link",
				"options": "Item",
				"insert_after": "customer",
				"search_index": 1,
				"description": "Shared sellable Item described by this customer-specific specification.",
			},
		],
		"Sales Order Item": _sales_order_item_fields(),
	}


def _sales_order_item_fields():
	"""The CPS link, the two immutable snapshots and the Job Card rollups.

	Everything except custom_cps and custom_price_override_reason is read_only
	and server-written. Only the two rollups carry allow_on_submit, because they
	must change while the order is submitted; both are written by the Job Card
	hooks and are never accepted from input.
	"""
	return [
		{
			"fieldname": "custom_cps_section",
			"label": "Specification & Controlled Price",
			"fieldtype": "Section Break",
			"insert_after": "item_group",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_cps",
			"label": "Customer Product Specification",
			"fieldtype": "Link",
			"options": CPS,
			"insert_after": "custom_cps_section",
			"description": "Required for specification-controlled items. Must belong to this customer and be submitted and Active.",
		},
		{
			"fieldname": "custom_cps_rate",
			"label": "CPS Rate (net, ex-VAT)",
			"fieldtype": "Currency",
			"precision": "9",
			"read_only": 1,
			"insert_after": "custom_cps",
		},
		{
			"fieldname": "custom_cps_uom",
			"label": "CPS UOM",
			"fieldtype": "Link",
			"options": "UOM",
			"read_only": 1,
			"insert_after": "custom_cps_rate",
		},
		{
			"fieldname": "custom_cps_valid_from",
			"label": "CPS Price Effective From",
			"fieldtype": "Date",
			"read_only": 1,
			"insert_after": "custom_cps_uom",
		},
		{
			"fieldname": "custom_cps_price_row",
			"label": "CPS Price Row ID",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_cps_valid_from",
		},
		{
			"fieldname": "custom_cps_col_break_1",
			"fieldtype": "Column Break",
			"insert_after": "custom_cps_price_row",
		},
		{
			"fieldname": "custom_price_source",
			"label": "Price Source",
			"fieldtype": "Select",
			"options": PRICE_SOURCES,
			"read_only": 1,
			"insert_after": "custom_cps_col_break_1",
		},
		{
			"fieldname": "custom_price_variance_pct",
			"label": "Variance vs CPS Rate",
			"fieldtype": "Percent",
			"precision": "2",
			"read_only": 1,
			"insert_after": "custom_price_source",
		},
		{
			"fieldname": "custom_price_override_reason",
			"label": "Override Reason",
			"fieldtype": "Small Text",
			"insert_after": "custom_price_variance_pct",
			"description": "Required when the rate deviates from the approved CPS rate in either direction.",
		},
		{
			"fieldname": "custom_price_approved_by",
			"label": "Override Approved By",
			"fieldtype": "Link",
			"options": "User",
			"read_only": 1,
			"insert_after": "custom_price_override_reason",
		},
		{
			"fieldname": "custom_spec_snapshot_section",
			"label": "Specification Snapshot",
			"fieldtype": "Section Break",
			"insert_after": "custom_price_approved_by",
			"collapsible": 1,
			"depends_on": "eval:doc.custom_cps",
		},
		{
			"fieldname": "custom_spec_name",
			"label": "Specification Name",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_spec_snapshot_section",
		},
		{
			"fieldname": "custom_job_size",
			"label": "Job Size",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_spec_name",
		},
		{
			"fieldname": "custom_number_of_parts",
			"label": "Number of Parts",
			"fieldtype": "Int",
			"read_only": 1,
			"insert_after": "custom_job_size",
		},
		{
			"fieldname": "custom_number_of_colours",
			"label": "Number of Colours",
			"fieldtype": "Int",
			"read_only": 1,
			"insert_after": "custom_number_of_parts",
		},
		{
			"fieldname": "custom_spec_snapshot_at",
			"label": "Snapshot Taken At",
			"fieldtype": "Datetime",
			"read_only": 1,
			"insert_after": "custom_number_of_colours",
		},
		{
			"fieldname": "custom_spec_snapshot",
			"label": "Specification Snapshot (JSON)",
			"fieldtype": "Long Text",
			"read_only": 1,
			"insert_after": "custom_spec_snapshot_at",
			"description": "The specification exactly as it stood when this order was submitted. Product-type agnostic, so Label, Carton and ETR snapshot through the same field.",
		},
		{
			"fieldname": "custom_jc_section",
			"label": "Job Cards",
			"fieldtype": "Section Break",
			"insert_after": "custom_spec_snapshot",
			"collapsible": 1,
			"depends_on": "eval:doc.custom_cps",
		},
		{
			"fieldname": "custom_jc_qty",
			"label": "Qty on Job Cards",
			"fieldtype": "Float",
			"precision": "3",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"insert_after": "custom_jc_section",
			"description": "Includes draft Job Cards - a draft reserves quantity.",
		},
		{
			"fieldname": "custom_jc_status",
			"label": "Job Card Status",
			"fieldtype": "Select",
			"options": "\nNot Started\nPartial\nFully Carded",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"insert_after": "custom_jc_qty",
		},
	]
