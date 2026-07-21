"""Schema and wiring tests for CPS control of Sales Order lines.

These need a bench, because they assert against live metadata. The decision
rules themselves are covered without a bench in ``test_cps_rules.py``.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from production_log.job_card_tracking import so_spec_control

# DN-1: these lose allow_on_submit, so a change to any of them on a submitted
# specification goes through cancel + amend rather than editing history.
LOCKED_TECHNICAL_FIELDS = (
	"ink_type",
	"uses_c",
	"uses_m",
	"uses_y",
	"uses_k",
	"number_of_colours",
	"spot_colours",
	"colour_notes",
	"standard_packing",
	"standard_weight_per_carton",
)

# The pricing mechanism depends on these staying editable after submit.
PRICING_FIELDS = ("pricing", "current_rate", "current_uom")

SNAPSHOT_FIELDS = (
	"custom_cps_rate",
	"custom_cps_uom",
	"custom_cps_valid_from",
	"custom_cps_price_row",
	"custom_price_source",
	"custom_price_variance_pct",
	"custom_price_approved_by",
	"custom_spec_name",
	"custom_job_size",
	"custom_number_of_parts",
	"custom_number_of_colours",
	"custom_spec_snapshot_at",
	"custom_spec_snapshot",
)


class TestCPSPriceSchema(FrappeTestCase):
	def test_cps_price_is_a_child_table(self):
		meta = frappe.get_meta("CPS Price")

		self.assertTrue(meta.istable)

	def test_tc021_rate_is_held_to_nine_decimal_places(self):
		rate = frappe.get_meta("CPS Price").get_field("rate")

		self.assertEqual(rate.fieldtype, "Currency")
		self.assertEqual(str(rate.precision), "9")

	def test_tc020_every_price_field_survives_submit(self):
		meta = frappe.get_meta("CPS Price")

		for fieldname in (
			"valid_from",
			"rate",
			"uom",
			"source",
			"source_ref",
			"notes",
			"approval_status",
			"approved_by",
			"approved_on",
			"approval_notes",
		):
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, fieldname)
			self.assertTrue(field.allow_on_submit, fieldname)

	def test_tc010_approval_stamps_are_not_hand_editable(self):
		meta = frappe.get_meta("CPS Price")

		for fieldname in ("approval_status", "approved_by", "approved_on"):
			self.assertTrue(meta.get_field(fieldname).read_only, fieldname)

		self.assertEqual(meta.get_field("approval_status").default, "Draft")

	def test_there_is_no_valid_upto(self):
		# Supersession is by the next row's valid_from. A valid_upto would be a
		# second, contradictory control over the same fact.
		self.assertIsNone(frappe.get_meta("CPS Price").get_field("valid_upto"))


class TestSpecificationSchema(FrappeTestCase):
	def test_specification_carries_the_pricing_table(self):
		meta = frappe.get_meta("Customer Product Specification")
		pricing = meta.get_field("pricing")

		self.assertEqual(pricing.fieldtype, "Table")
		self.assertEqual(pricing.options, "CPS Price")

	def test_pricing_fields_remain_editable_after_submit(self):
		meta = frappe.get_meta("Customer Product Specification")

		for fieldname in PRICING_FIELDS:
			self.assertTrue(meta.get_field(fieldname).allow_on_submit, fieldname)

	def test_dn1_technical_fields_are_locked_after_submit(self):
		meta = frappe.get_meta("Customer Product Specification")

		for fieldname in LOCKED_TECHNICAL_FIELDS:
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, fieldname)
			self.assertFalse(field.allow_on_submit, fieldname)


class TestSalesOrderItemSchema(FrappeTestCase):
	def test_specification_link_exists(self):
		field = frappe.get_meta("Sales Order Item").get_field("custom_cps")

		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Customer Product Specification")

	def test_tc044_and_tc050_snapshots_cannot_be_edited_after_submit(self):
		meta = frappe.get_meta("Sales Order Item")

		for fieldname in SNAPSHOT_FIELDS:
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, fieldname)
			self.assertTrue(field.read_only, fieldname)
			self.assertFalse(field.allow_on_submit, fieldname)

	def test_override_reason_is_the_only_writable_field_in_the_block(self):
		field = frappe.get_meta("Sales Order Item").get_field("custom_price_override_reason")

		self.assertFalse(field.read_only)
		self.assertFalse(field.allow_on_submit)

	def test_rollups_are_the_only_fields_that_change_after_submit(self):
		meta = frappe.get_meta("Sales Order Item")

		for fieldname in ("custom_jc_qty", "custom_jc_status"):
			field = meta.get_field(fieldname)
			self.assertTrue(field.allow_on_submit, fieldname)
			self.assertTrue(field.read_only, fieldname)
			self.assertTrue(field.no_copy, fieldname)


class TestJobCardComputerPaperSchema(FrappeTestCase):
	def test_sales_order_traceability_fields_exist_and_are_read_only(self):
		meta = frappe.get_meta("Job Card Computer Paper")

		for fieldname in (
			"sales_order",
			"sales_order_item",
			"item_code",
			"rate",
			"price_source",
			"so_qty",
			"spec_snapshot",
			"spec_snapshot_at",
		):
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, fieldname)
			self.assertTrue(field.read_only, fieldname)

	def test_sales_order_link_is_not_yet_mandatory(self):
		# Historical job cards have no resolvable order. reqd flips only after
		# the backfill lands, and never in the same deploy as the field.
		meta = frappe.get_meta("Job Card Computer Paper")

		self.assertFalse(meta.get_field("sales_order").reqd)
		self.assertFalse(meta.get_field("sales_order_item").reqd)

	def test_tc021_rate_is_held_to_nine_decimal_places(self):
		rate = frappe.get_meta("Job Card Computer Paper").get_field("rate")

		self.assertEqual(str(rate.precision), "9")

	def test_dn4_both_status_fields_are_untouched(self):
		meta = frappe.get_meta("Job Card Computer Paper")

		self.assertIsNotNone(meta.get_field("status"))
		self.assertIsNotNone(meta.get_field("job_status"))

	def test_d11_sales_user_may_create_but_not_submit(self):
		perms = {
			p.role: p for p in frappe.get_meta("Job Card Computer Paper").permissions
		}
		sales_user = perms["Sales User"]

		self.assertTrue(sales_user.create)
		self.assertTrue(sales_user.write)
		self.assertFalse(sales_user.submit)


class TestFeatureFlag(FrappeTestCase):
	def test_tc042_validation_is_inert_while_the_flag_is_off(self):
		doc = frappe.get_doc(
			{"doctype": "Sales Order", "docstatus": 1, "items": [{"item_code": "ANY"}]}
		)

		with (
			patch.object(so_spec_control, "control_enabled", return_value=False),
			patch.object(so_spec_control.frappe.db, "get_value") as get_value,
		):
			so_spec_control.validate(doc)

		get_value.assert_not_called()

	def test_flag_ships_off(self):
		self.assertFalse(
			frappe.db.get_single_value("Selling Settings", so_spec_control.CONTROL_FLAG)
		)

	def test_dn5_thresholds_ship_unset(self):
		# Unset is not zero: exact-match-only, floor disabled, until management
		# supplies real values.
		self.assertIsNone(so_spec_control._threshold(so_spec_control.TOLERANCE_FIELD))
		self.assertIsNone(so_spec_control._threshold(so_spec_control.FLOOR_FIELD))
