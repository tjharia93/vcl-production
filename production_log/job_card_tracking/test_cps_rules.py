"""Unit tests for the pure CPS rules.

These run under plain ``unittest`` with no bench, no site and no database,
because ``cps_rules`` imports nothing from Frappe. Test case IDs reference the
Phase 2 solution design test matrix (§16).
"""

import unittest
from datetime import date

from production_log.job_card_tracking import cps_rules


def price(valid_from, rate, status=cps_rules.APPROVAL_APPROVED, uom="Nos", name=None):
	return {
		"name": name or "row-{0}-{1}".format(valid_from, rate),
		"valid_from": valid_from,
		"rate": rate,
		"uom": uom,
		"approval_status": status,
	}


class TestToDate(unittest.TestCase):
	def test_accepts_date_datetime_and_string(self):
		self.assertEqual(cps_rules.to_date(date(2026, 7, 19)), date(2026, 7, 19))
		self.assertEqual(cps_rules.to_date("2026-07-19"), date(2026, 7, 19))
		self.assertEqual(cps_rules.to_date("2026-07-19 11:02:07"), date(2026, 7, 19))

	def test_blank_values_are_none(self):
		self.assertIsNone(cps_rules.to_date(None))
		self.assertIsNone(cps_rules.to_date(""))

	def test_rejects_nonsense(self):
		with self.assertRaises(TypeError):
			cps_rules.to_date(object())


class TestResolveEligiblePrice(unittest.TestCase):
	def test_tc013_picks_greatest_valid_from_at_or_before_order_date(self):
		rows = [price("2026-01-01", 10.0), price("2026-06-01", 12.5)]

		eligible = cps_rules.resolve_eligible_price(rows, "2026-07-19")

		self.assertEqual(eligible["rate"], 12.5)

	def test_tc014_backdated_order_prices_at_the_older_row(self):
		rows = [price("2026-01-01", 10.0), price("2026-06-01", 12.5)]

		eligible = cps_rules.resolve_eligible_price(rows, "2026-03-01")

		self.assertEqual(eligible["rate"], 10.0)

	def test_tc015_draft_rows_are_invisible(self):
		rows = [price("2026-01-01", 10.0, status=cps_rules.APPROVAL_DRAFT)]

		self.assertIsNone(cps_rules.resolve_eligible_price(rows, "2026-07-19"))

	def test_rejected_rows_are_invisible(self):
		rows = [price("2026-01-01", 10.0, status=cps_rules.APPROVAL_REJECTED)]

		self.assertIsNone(cps_rules.resolve_eligible_price(rows, "2026-07-19"))

	def test_tc016_future_dated_row_is_not_yet_eligible(self):
		rows = [price("2026-09-01", 15.0)]

		self.assertIsNone(cps_rules.resolve_eligible_price(rows, "2026-07-19"))

	def test_row_effective_on_the_order_date_itself_is_eligible(self):
		rows = [price("2026-07-19", 15.0)]

		self.assertEqual(cps_rules.resolve_eligible_price(rows, "2026-07-19")["rate"], 15.0)

	def test_no_rows_and_no_date_resolve_to_none(self):
		self.assertIsNone(cps_rules.resolve_eligible_price([], "2026-07-19"))
		self.assertIsNone(cps_rules.resolve_eligible_price(None, "2026-07-19"))
		self.assertIsNone(cps_rules.resolve_eligible_price([price("2026-01-01", 1.0)], None))

	def test_approved_row_without_valid_from_is_ignored(self):
		rows = [price(None, 10.0), price("2026-01-01", 12.0)]

		self.assertEqual(cps_rules.resolve_eligible_price(rows, "2026-07-19")["rate"], 12.0)


class TestDuplicateValidFrom(unittest.TestCase):
	def test_tc017_two_live_rows_sharing_a_date_are_flagged(self):
		rows = [price("2026-01-01", 10.0), price("2026-01-01", 11.0, status=cps_rules.APPROVAL_DRAFT)]

		self.assertEqual(cps_rules.find_duplicate_valid_from(rows), [date(2026, 1, 1)])

	def test_tc018_a_rejected_row_may_be_superseded_on_the_same_date(self):
		rows = [
			price("2026-01-01", 10.0, status=cps_rules.APPROVAL_REJECTED),
			price("2026-01-01", 11.0),
		]

		self.assertEqual(cps_rules.find_duplicate_valid_from(rows), [])

	def test_distinct_dates_are_clean(self):
		rows = [price("2026-01-01", 10.0), price("2026-06-01", 11.0)]

		self.assertEqual(cps_rules.find_duplicate_valid_from(rows), [])


class TestApprovalResetOnEdit(unittest.TestCase):
	def test_tc019_rate_edit_revokes_approval(self):
		before = price("2026-01-01", 10.0)
		after = price("2026-01-01", 11.0)

		self.assertTrue(cps_rules.price_approval_reset_required(before, after))

	def test_uom_and_valid_from_edits_also_revoke(self):
		before = price("2026-01-01", 10.0)

		self.assertTrue(
			cps_rules.price_approval_reset_required(before, price("2026-01-01", 10.0, uom="Box"))
		)
		self.assertTrue(
			cps_rules.price_approval_reset_required(before, price("2026-02-01", 10.0))
		)

	def test_untouched_row_keeps_its_approval(self):
		before = price("2026-01-01", 10.0)
		after = price("2026-01-01", 10.0)

		self.assertFalse(cps_rules.price_approval_reset_required(before, after))

	def test_date_type_change_alone_is_not_an_edit(self):
		before = price(date(2026, 1, 1), 10.0)
		after = price("2026-01-01", 10.0)

		self.assertFalse(cps_rules.price_approval_reset_required(before, after))

	def test_editing_a_draft_row_needs_no_reset(self):
		before = price("2026-01-01", 10.0, status=cps_rules.APPROVAL_DRAFT)
		after = price("2026-01-01", 99.0, status=cps_rules.APPROVAL_DRAFT)

		self.assertFalse(cps_rules.price_approval_reset_required(before, after))


class TestPriceEvaluation(unittest.TestCase):
	def test_tc021_nine_decimal_rate_matches_exactly(self):
		decision = cps_rules.evaluate_price(5.172413793, 5.172413793)

		self.assertEqual(decision.source, cps_rules.SOURCE_CPS_PRICE)
		self.assertFalse(decision.requires_override)

	def test_tc033_rounded_rate_is_an_override_not_a_match(self):
		decision = cps_rules.evaluate_price(5.17, 5.172413793)

		self.assertEqual(decision.source, cps_rules.SOURCE_MANUAL_OVERRIDE)
		self.assertTrue(decision.requires_override)
		self.assertFalse(decision.below_floor)

	def test_a_configured_tolerance_admits_the_rounded_rate(self):
		decision = cps_rules.evaluate_price(5.17, 5.172413793, tolerance_pct=1)

		self.assertEqual(decision.source, cps_rules.SOURCE_CPS_PRICE)
		self.assertFalse(decision.requires_override)

	def test_tc034_rate_above_the_cps_rate_still_requires_an_override(self):
		decision = cps_rules.evaluate_price(11.0, 10.0)

		self.assertEqual(decision.source, cps_rules.SOURCE_MANUAL_OVERRIDE)
		self.assertTrue(decision.requires_override)
		self.assertAlmostEqual(decision.variance_pct, 10.0)

	def test_tc035_rate_below_the_cps_rate_requires_an_override(self):
		decision = cps_rules.evaluate_price(9.0, 10.0)

		self.assertTrue(decision.requires_override)
		self.assertAlmostEqual(decision.variance_pct, -10.0)

	def test_dn5_floor_is_disabled_by_default(self):
		self.assertFalse(cps_rules.evaluate_price(1.0, 10.0).below_floor)

	def test_tc038_a_configured_floor_refuses_the_line(self):
		self.assertTrue(cps_rules.evaluate_price(8.0, 10.0, floor_pct=85).below_floor)

	def test_a_rate_exactly_on_the_floor_passes_the_floor(self):
		self.assertFalse(cps_rules.evaluate_price(8.5, 10.0, floor_pct=85).below_floor)

	def test_variance_against_a_zero_cps_rate_is_undefined(self):
		self.assertIsNone(cps_rules.variance_pct(5.0, 0))
		self.assertFalse(cps_rules.is_below_floor(5.0, 0, floor_pct=85))


class TestJobCardQuantities(unittest.TestCase):
	def test_tc059_partial_carding(self):
		self.assertEqual(cps_rules.remaining_qty(10000, 6000), 4000)
		self.assertEqual(cps_rules.derive_jc_status(6000, 10000), cps_rules.JC_PARTIAL)

	def test_tc060_fully_carded(self):
		self.assertEqual(cps_rules.remaining_qty(10000, 10000), 0)
		self.assertEqual(cps_rules.derive_jc_status(10000, 10000), cps_rules.JC_FULLY_CARDED)

	def test_nothing_carded_yet(self):
		self.assertEqual(cps_rules.derive_jc_status(0, 10000), cps_rules.JC_NOT_STARTED)
		self.assertEqual(cps_rules.derive_jc_status(None, 10000), cps_rules.JC_NOT_STARTED)

	def test_over_carded_quantities_cannot_read_as_partial(self):
		# DN-6 blocks over-carding at insert; if legacy data ever exceeds the
		# line, the rollup must still read as Fully Carded, never Partial.
		self.assertEqual(cps_rules.derive_jc_status(11000, 10000), cps_rules.JC_FULLY_CARDED)


class TestSpecSnapshot(unittest.TestCase):
	def _spec(self):
		return {
			"name": "CPT-SPEC-00038-1",
			"modified": "2026-07-02 09:14:33",
			"product_type": "Computer Paper",
			"specification_name": "Payslip 9.5x8 2-Part",
			"customer": "ACME Ltd",
			"job_size": "9.5 x 8",
			"number_of_parts": 2,
			"ink_type": "Process Offset",
			"number_of_colours": 1,
		}

	def test_tc046_snapshot_pins_the_exact_amended_spec_name(self):
		snapshot = cps_rules.build_spec_snapshot(self._spec(), [], [], "2026-07-19 11:02:07")

		self.assertEqual(snapshot["_cps"], "CPT-SPEC-00038-1")
		# Version 2 added the Carton scalars and version 3 the Label ones. Both
		# are widenings only: a Computer Paper snapshot carries exactly the keys
		# it always did and is still *stamped* 2, because nothing either version
		# added describes a Computer Paper. Version 1 snapshots on live orders
		# stay readable (``cps_rules.SUPPORTED_SNAPSHOT_VERSIONS``). Shape
		# regression is asserted in ``test_carton_cps_rules.TestSnapshotShape``.
		self.assertEqual(snapshot["_snapshot_version"], 2)
		self.assertEqual(snapshot["_taken_at"], "2026-07-19 11:02:07")
		self.assertEqual(snapshot["job_size"], "9.5 x 8")

	def test_a_version_one_snapshot_on_a_live_order_is_still_readable(self):
		self.assertTrue(cps_rules.snapshot_version_supported({"_snapshot_version": 1}))

	def test_tc051_every_child_row_and_column_is_captured(self):
		parts = [
			{"part_number": 1, "paper_type": "CB", "gsm": 55, "colour": "White", "purpose": "Original"},
			{"part_number": 2, "paper_type": "CF", "gsm": 55, "colour": "Pink", "purpose": "Copy"},
		]
		spots = [{"pantone_code": "PMS 485 C", "hex_preview": "#DA291C", "cmyk_m": 95}]

		snapshot = cps_rules.build_spec_snapshot(self._spec(), parts, spots, "2026-07-19 11:02:07")

		self.assertEqual(len(snapshot["colour_of_parts"]), 2)
		self.assertEqual(snapshot["colour_of_parts"][0]["paper_type"], "CB")
		self.assertEqual(snapshot["spot_colours"][0]["pantone_code"], "PMS 485 C")
		self.assertIsNone(snapshot["spot_colours"][0]["pantone_name"])

	def test_tc052_absent_spot_colours_serialise_as_an_empty_list(self):
		snapshot = cps_rules.build_spec_snapshot(self._spec(), [], None, "2026-07-19 11:02:07")

		self.assertEqual(snapshot["spot_colours"], [])
		self.assertEqual(snapshot["colour_of_parts"], [])

	def test_tc053_snapshot_records_the_value_not_the_current_options(self):
		spec = self._spec()
		spec["ink_type"] = "Process Offset"

		snapshot = cps_rules.build_spec_snapshot(spec, [], [], "2026-07-19 11:02:07")
		spec["ink_type"] = "Renamed Offset"

		self.assertEqual(snapshot["ink_type"], "Process Offset")


if __name__ == "__main__":
	unittest.main()
