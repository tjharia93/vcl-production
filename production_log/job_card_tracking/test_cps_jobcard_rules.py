"""Unit tests for the Job-Card-against-Sales-Order-line rules.

These run under plain ``unittest`` with no bench, no site and no database. The
Frappe-bound half — the row lock, the parent check, the throws — lives in
``doctype/job_card_computer_paper/job_card_computer_paper.py`` and needs a
bench; what is testable without one is the decision itself, which is here.

Test case IDs reference the Phase 2 solution design (§8.2, §11.3).
"""

import json
import unittest

from production_log.job_card_tracking import cps_rules

SNAPSHOT = json.dumps({"_snapshot_version": 1, "product_type": "Computer Paper", "job_size": "A4"})


def line(**overrides):
	"""A submitted, specification-controlled Sales Order line."""
	values = {
		"name": "SOI-0001",
		"parent": "SAL-ORD-0001",
		"parenttype": "Sales Order",
		"parentfield": "items",
		"item_code": "CPT-3PT-A4",
		"qty": 500.0,
		"rate": 5.172413793,
		"custom_cps": "CPT-SPEC-00001",
		"custom_cps_rate": 5.172413793,
		"custom_price_source": cps_rules.SOURCE_CPS_PRICE,
		"custom_spec_snapshot": SNAPSHOT,
		"custom_spec_snapshot_at": "2026-07-19 11:02:07",
	}
	values.update(overrides)
	return values


def order(**overrides):
	# ``transaction_date`` and ``po_no`` are on the fixture because they are on
	# the read: the card's order_date and lpo_number are proved against them,
	# and an order fixture that omitted them would make those two checks pass by
	# comparing nothing to nothing.
	values = {
		"name": "SAL-ORD-0001",
		"docstatus": 1,
		"customer": "CUST-0001",
		"transaction_date": "2026-07-19",
		"po_no": "LPO-4471",
	}
	values.update(overrides)
	return values


def card(**overrides):
	"""A Job Card faithfully copied from :func:`line`."""
	values = {
		"customer": "CUST-0001",
		"item_code": "CPT-3PT-A4",
		"customer_product_spec": "CPT-SPEC-00001",
		"rate": 5.172413793,
		"price_source": cps_rules.SOURCE_CPS_PRICE,
		"so_qty": 500.0,
		"spec_snapshot": SNAPSHOT,
		"spec_snapshot_at": "2026-07-19 11:02:07",
		"order_date": "2026-07-19",
		"lpo_number": "LPO-4471",
	}
	values.update(overrides)
	return values


def fields(mismatches):
	return sorted(m.field for m in mismatches)


class TestSnapshotProductType(unittest.TestCase):
	def test_reads_the_frozen_product_type(self):
		self.assertEqual(
			cps_rules.snapshot_product_type({"product_type": "Computer Paper"}),
			"Computer Paper",
		)

	def test_strips_surrounding_whitespace(self):
		self.assertEqual(cps_rules.snapshot_product_type({"product_type": " Label "}), "Label")

	def test_missing_blank_and_non_dict_are_none(self):
		self.assertIsNone(cps_rules.snapshot_product_type({}))
		self.assertIsNone(cps_rules.snapshot_product_type({"product_type": ""}))
		self.assertIsNone(cps_rules.snapshot_product_type({"product_type": "   "}))
		self.assertIsNone(cps_rules.snapshot_product_type(None))
		self.assertIsNone(cps_rules.snapshot_product_type("Computer Paper"))
		self.assertIsNone(cps_rules.snapshot_product_type([]))


class TestExpectedJobCardRate(unittest.TestCase):
	def test_uses_the_actual_sold_rate_for_an_override(self):
		self.assertEqual(
			cps_rules.expected_jc_rate(line(custom_cps_rate=5.172413793, rate=9.0)),
			9.0,
		)

	def test_uses_the_line_rate_when_unpriced(self):
		self.assertEqual(cps_rules.expected_jc_rate(line(custom_cps_rate=None, rate=7.5)), 7.5)

	def test_a_genuinely_free_line_is_zero_not_none(self):
		self.assertEqual(cps_rules.expected_jc_rate(line(custom_cps_rate=0, rate=0)), 0.0)

	def test_held_to_nine_decimal_places(self):
		self.assertEqual(
			cps_rules.expected_jc_rate(line(rate=5.1724137931234567)),
			5.172413793,
		)


class TestFaithfulCopy(unittest.TestCase):
	def test_a_copied_card_has_no_mismatches(self):
		self.assertEqual(cps_rules.jc_line_mismatches(card(), order(), line()), [])

	def test_works_on_objects_as_well_as_dicts(self):
		class Doc:
			def __init__(self, values):
				self.__dict__.update(values)

		self.assertEqual(
			cps_rules.jc_line_mismatches(Doc(card()), Doc(order()), Doc(line())), []
		)

	def test_snapshot_whitespace_is_not_a_disagreement(self):
		self.assertEqual(
			cps_rules.jc_line_mismatches(card(spec_snapshot="\n" + SNAPSHOT + "  "), order(), line()),
			[],
		)

	def test_timestamp_compared_to_the_second(self):
		self.assertEqual(
			cps_rules.jc_line_mismatches(
				card(spec_snapshot_at="2026-07-19 11:02:07.412319"), order(), line()
			),
			[],
		)

	def test_blank_and_none_are_the_same_absence(self):
		self.assertEqual(
			cps_rules.jc_line_mismatches(
				card(price_source=None), order(), line(custom_price_source="")
			),
			[],
		)

	def test_rate_within_nine_dp_matches(self):
		self.assertEqual(
			cps_rules.jc_line_mismatches(card(rate=5.1724137930000001), order(), line()), []
		)

	def test_quantity_compared_at_three_dp(self):
		self.assertEqual(
			cps_rules.jc_line_mismatches(card(so_qty=500.0004), order(), line(qty=500.0)), []
		)


class TestForgedCard(unittest.TestCase):
	"""Every field a Desk or REST caller could post into a read-only field."""

	def test_customer_is_checked_against_the_order(self):
		found = cps_rules.jc_line_mismatches(card(customer="CUST-9999"), order(), line())

		self.assertEqual(fields(found), ["customer"])
		self.assertEqual(found[0].found, "CUST-9999")
		self.assertEqual(found[0].expected, "CUST-0001")

	def test_item_code_cannot_be_swapped(self):
		found = cps_rules.jc_line_mismatches(card(item_code="CPT-2PT-A5"), order(), line())

		self.assertEqual(fields(found), ["item_code"])

	def test_specification_cannot_be_swapped(self):
		found = cps_rules.jc_line_mismatches(
			card(customer_product_spec="CPT-SPEC-09999"), order(), line()
		)

		self.assertEqual(fields(found), ["customer_product_spec"])

	def test_rate_cannot_be_inflated(self):
		found = cps_rules.jc_line_mismatches(card(rate=99.0), order(), line())

		self.assertEqual(fields(found), ["rate"])
		self.assertEqual(found[0].expected, 5.172413793)

	def test_a_rounded_rate_is_a_mismatch_not_a_nicety(self):
		# 5.17 typed against 5.172413793 is a different number (design §9.1).
		self.assertEqual(fields(cps_rules.jc_line_mismatches(card(rate=5.17), order(), line())), ["rate"])

	def test_price_source_cannot_be_relabelled(self):
		found = cps_rules.jc_line_mismatches(
			card(price_source=cps_rules.SOURCE_CPS_PRICE),
			order(),
			line(custom_price_source=cps_rules.SOURCE_MANUAL_OVERRIDE),
		)

		self.assertEqual(fields(found), ["price_source"])

	def test_so_qty_cannot_be_overstated(self):
		found = cps_rules.jc_line_mismatches(card(so_qty=5000.0), order(), line(qty=500.0))

		self.assertEqual(fields(found), ["so_qty"])
		self.assertEqual(found[0].expected, 500.0)

	def test_snapshot_cannot_be_rewritten(self):
		forged = json.dumps({"product_type": "Computer Paper", "job_size": "A3"})
		found = cps_rules.jc_line_mismatches(card(spec_snapshot=forged), order(), line())

		self.assertEqual(fields(found), ["spec_snapshot"])

	def test_snapshot_timestamp_cannot_be_rewritten(self):
		found = cps_rules.jc_line_mismatches(
			card(spec_snapshot_at="2020-01-01 00:00:00"), order(), line()
		)

		self.assertEqual(fields(found), ["spec_snapshot_at"])

	def test_an_empty_card_disagrees_on_everything(self):
		# A hand-made Desk document that only sets sales_order/sales_order_item
		# must be refused, not quietly completed from the order.
		found = cps_rules.jc_line_mismatches({}, order(), line())

		self.assertEqual(
			fields(found),
			[
				"customer",
				"customer_product_spec",
				"item_code",
				"lpo_number",
				"order_date",
				"price_source",
				"rate",
				"so_qty",
				"spec_snapshot",
				"spec_snapshot_at",
			],
		)

	def test_the_order_header_fields_are_proved_too(self):
		# Both are copied off the Sales Order header by the creation path, are
		# read-only on the form, and were until this release the only values on
		# an order-derived card that nothing checked.
		self.assertEqual(
			fields(cps_rules.jc_line_mismatches(card(order_date="2026-01-01"), order(), line())),
			["order_date"],
		)
		self.assertEqual(
			fields(cps_rules.jc_line_mismatches(card(lpo_number="LPO-9"), order(), line())),
			["lpo_number"],
		)

	def test_an_order_with_no_lpo_expects_a_blank_one(self):
		blank = order(po_no=None)

		self.assertEqual(cps_rules.jc_line_mismatches(card(lpo_number=""), blank, line()), [])
		self.assertEqual(
			fields(cps_rules.jc_line_mismatches(card(), blank, line())), ["lpo_number"]
		)

	def test_every_mismatch_is_reported_not_just_the_first(self):
		found = cps_rules.jc_line_mismatches(
			card(customer="CUST-9999", rate=99.0, so_qty=1.0), order(), line()
		)

		self.assertEqual(fields(found), ["customer", "rate", "so_qty"])

	def test_mismatches_carry_a_human_label(self):
		found = cps_rules.jc_line_mismatches(card(so_qty=1.0), order(), line())

		self.assertEqual(found[0].label, "SO Line Quantity")


class TestHistoricalSnapshotProtection(unittest.TestCase):
	"""The point of the whole mechanism: today's CPS is not consulted.

	A specification deactivated, re-priced or amended after the order was
	submitted must not invalidate a job card for a line already sold. These
	rules read the line and the order only — there is no CPS argument to pass,
	which is what makes that guarantee structural rather than remembered.
	"""

	def test_verification_needs_no_current_specification(self):
		self.assertEqual(cps_rules.jc_line_mismatches(card(), order(), line()), [])

	def test_a_repriced_specification_does_not_disturb_a_sold_line(self):
		# The CPS Price rows moved to 9.99 today; the line stays at what it
		# was submitted at, and so does the card.
		self.assertEqual(
			cps_rules.jc_line_mismatches(card(rate=5.172413793), order(), line()), []
		)

	def test_product_type_is_read_from_the_snapshot(self):
		snapshot = json.loads(SNAPSHOT)

		self.assertEqual(cps_rules.snapshot_product_type(snapshot), "Computer Paper")

	def test_a_line_ordered_as_another_type_is_detectable(self):
		self.assertEqual(
			cps_rules.snapshot_product_type({"product_type": "Label"}), "Label"
		)


if __name__ == "__main__":
	unittest.main()
