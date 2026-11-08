"""Unit tests for the §5 price semantics. Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import cps_price_rules as rules
from production_log.job_card_tracking import cps_rules


def row(**kw):
	base = {
		"name": "row-1",
		"approval_status": "Approved",
		"valid_from": "2026-10-01",
		"approved_on": "2026-10-01 09:00:00",
		"rate": 5.172413793,
		"uom": "Nos",
		"currency": "KES",
		"conversion_factor": 1.0,
	}
	base.update(kw)
	return base


class TestAllowance(unittest.TestCase):
	def test_one_kes_applies_above_one_hundred(self):
		self.assertAlmostEqual(rules.rounding_allowance(3965.5172), 1.0)

	def test_one_percent_applies_below_one_hundred(self):
		self.assertAlmostEqual(rules.rounding_allowance(0.39), 0.0039)
		self.assertAlmostEqual(rules.rounding_allowance(50), 0.5)

	def test_zero_rate_allows_nothing(self):
		self.assertEqual(rules.rounding_allowance(0), 0.0)

	def test_settings_override_defaults(self):
		self.assertAlmostEqual(rules.rounding_allowance(1000, allowance_kes=2, allowance_pct=5), 2.0)
		self.assertAlmostEqual(rules.rounding_allowance(10, allowance_kes=2, allowance_pct=5), 0.5)

	def test_blank_settings_fall_back_to_defaults(self):
		self.assertAlmostEqual(rules.rounding_allowance(1000, None, None), 1.0)


class TestCheckLineRate(unittest.TestCase):
	def test_exact_match_passes(self):
		check = rules.check_line_rate(5.172413793, 1.0, "KES", row())
		self.assertTrue(check.ok)
		self.assertEqual(check.code, rules.PRICE_OK)

	def test_rounded_line_rate_within_allowance_passes(self):
		# 5.17 against 5.172413793: 0.0024 off, allowance 0.0517.
		self.assertTrue(rules.check_line_rate(5.17, 1.0, "KES", row()).ok)

	def test_label_price_cannot_fall_to_zero(self):
		# The Codex case: KES 0.39 approved, 0 typed. KES 1 alone would pass it.
		check = rules.check_line_rate(0, 1.0, "KES", row(rate=0.39))
		self.assertFalse(check.ok)
		self.assertEqual(check.code, rules.PRICE_OUTSIDE_ALLOWANCE)

	def test_one_kes_on_a_large_rate(self):
		self.assertTrue(rules.check_line_rate(3966.5, 1.0, "KES", row(rate=3965.5172)).ok)
		self.assertFalse(rules.check_line_rate(3966.6, 1.0, "KES", row(rate=3965.5172)).ok)

	def test_zero_approved_requires_exact(self):
		self.assertTrue(rules.check_line_rate(0, 1.0, "KES", row(rate=0)).ok)
		check = rules.check_line_rate(0.01, 1.0, "KES", row(rate=0))
		self.assertFalse(check.ok)
		self.assertEqual(check.code, rules.PRICE_ZERO_NOT_EXACT)

	def test_uom_conversion_uses_frozen_factors(self):
		# Row priced per Carton of 1000 (cf 1000); line sold per Nos (cf 1).
		check = rules.check_line_rate(5.1724, 1.0, "KES", row(rate=5172.413793, uom="Carton", conversion_factor=1000))
		self.assertTrue(check.ok)
		self.assertAlmostEqual(check.normalised_rate, 5172.4)
		# The allowance is struck in the row's UOM: 5.17 per piece is 2.41 off per carton.
		self.assertFalse(rules.check_line_rate(5.17, 1.0, "KES", row(rate=5172.413793, uom="Carton", conversion_factor=1000)).ok)

	def test_missing_factor_is_a_block(self):
		check = rules.check_line_rate(5.17, None, "KES", row(conversion_factor=1000))
		self.assertEqual(check.code, rules.PRICE_UOM_UNCONVERTIBLE)

	def test_legacy_row_without_factor_compares_directly(self):
		self.assertTrue(rules.check_line_rate(5.17, None, None, row(conversion_factor=None, currency=None)).ok)

	def test_currency_mismatch_is_a_block(self):
		self.assertEqual(rules.check_line_rate(5, 1, "USD", row()).code, rules.PRICE_CURRENCY)

	def test_no_row_is_a_block(self):
		self.assertEqual(rules.check_line_rate(5, 1, "KES", None).code, rules.PRICE_NO_ROW)

	def test_variance_is_signed(self):
		self.assertLess(rules.check_line_rate(5.0, 1, "KES", row()).variance, 0)


class TestSelectPriceRow(unittest.TestCase):
	def test_greatest_valid_from_wins(self):
		rows = [row(name="a", valid_from="2026-01-01"), row(name="b", valid_from="2026-06-01")]
		self.assertEqual(rules.select_price_row(rows, "KES", "2026-07-01")["name"], "b")

	def test_future_row_is_invisible(self):
		rows = [row(name="a", valid_from="2026-01-01"), row(name="b", valid_from="2026-12-01")]
		self.assertEqual(rules.select_price_row(rows, "KES", "2026-07-01")["name"], "a")

	def test_a_row_approved_today_does_not_resolve_an_older_order(self):
		rows = [row(name="old", valid_from="2026-01-01", approved_on="2026-01-01 09:00:00"),
		        row(name="new", valid_from="2026-11-08", approved_on="2026-11-08 09:00:00")]
		self.assertEqual(rules.select_price_row(rows, "KES", "2026-10-01")["name"], "old")

	def test_tie_on_valid_from_goes_to_latest_approval(self):
		rows = [row(name="a", approved_on="2026-10-01 09:00:00"), row(name="b", approved_on="2026-10-02 09:00:00")]
		self.assertEqual(rules.select_price_row(rows, "KES", "2026-10-05")["name"], "b")

	def test_other_currency_and_unapproved_rows_are_skipped(self):
		rows = [row(name="usd", currency="USD"), row(name="draft", approval_status="Draft")]
		self.assertIsNone(rules.select_price_row(rows, "KES", "2026-10-05"))

	def test_blank_currency_means_kes(self):
		self.assertEqual(rules.select_price_row([row(currency=None)], None, "2026-10-05")["name"], "row-1")

	def test_agrees_with_resolve_eligible_price_on_legacy_shapes(self):
		rows = [row(name="a", valid_from="2026-01-01"), row(name="b", valid_from="2026-06-01")]
		self.assertEqual(
			rules.select_price_row(rows, "KES", "2026-07-01")["name"],
			cps_rules.resolve_eligible_price(rows, "2026-07-01")["name"],
		)


class TestGrossNet(unittest.TestCase):
	def test_gross_divides_by_1_16_at_9dp(self):
		self.assertEqual(rules.net_from_gross(6.0, 16), 5.172413793)
		self.assertEqual(rules.gross_entry_values(6.0, rules.TAX_BASIS_GROSS_VAT)["rate"], 5.172413793)

	def test_exempt_gross_is_the_net(self):
		values = rules.gross_entry_values(6.0, rules.TAX_BASIS_GROSS_EXEMPT)
		self.assertEqual(values["rate"], 6.0)
		self.assertEqual(values["tax_rate"], 0.0)

	def test_unknown_basis_is_refused(self):
		with self.assertRaises(ValueError):
			rules.gross_entry_values(6.0, "Gross")

	def test_entered_fields_are_immutable_once_set(self):
		before = {"entered_gross": 6.0, "tax_basis": rules.TAX_BASIS_GROSS_VAT, "tax_rate": 16}
		self.assertEqual(rules.immutable_fields_changed(before, dict(before)), [])
		self.assertEqual(rules.immutable_fields_changed(before, dict(before, entered_gross=6.5)), ["entered_gross"])
		# Setting them for the first time is allowed.
		self.assertEqual(rules.immutable_fields_changed({"entered_gross": None}, {"entered_gross": 6}), [])


class TestIQTransfer(unittest.TestCase):
	def iq(self, **kw):
		base = {
			"name": "IQ-2026-00012",
			"status": "Approved",
			"approval_status": "OK",
			"customer_price": 11.6,
			"management_price": 10.0,
			"cost_price": 7.0,
			"vcl_uom": "Nos",
			"vcl_currency": "KES",
			"vcl_tax_basis": "Gross",
		}
		base.update(kw)
		return base

	def test_missing_uom_or_basis_blocks_transfer(self):
		self.assertFalse(rules.iq_transfer_ready(self.iq(vcl_uom=None)))
		self.assertFalse(rules.iq_transfer_ready(self.iq(vcl_tax_basis="")))
		self.assertIn("vcl_tax_basis", " ".join(rules.iq_transfer_errors(self.iq(vcl_tax_basis=""))))

	def test_unapproved_iq_does_not_transfer(self):
		self.assertFalse(rules.iq_transfer_ready(self.iq(status="Quoted")))
		self.assertTrue(rules.iq_transfer_ready(self.iq()))

	def test_gross_customer_price_is_divided(self):
		r = rules.price_row_from_iq(self.iq(), 1.0, "2026-11-08 10:00:00", "neema@vimit.com")
		self.assertEqual(r["rate"], 10.0)
		self.assertEqual(r["entered_gross"], 11.6)
		self.assertEqual(r["tax_basis"], rules.TAX_BASIS_GROSS_VAT)
		self.assertEqual(r["source"], rules.SOURCE_INTERNAL_QUOTATION)
		self.assertEqual(r["source_ref"], "IQ-2026-00012")
		self.assertEqual(r["approval_status"], "Approved")
		self.assertEqual(r["approved_via"], rules.APPROVED_VIA_IQ)
		self.assertEqual(r["rule_benchmark"], 10.0)
		self.assertEqual(str(r["valid_from"]), "2026-11-08")
		self.assertIn("OK", r["approval_notes"])

	def test_net_customer_price_is_taken_as_is(self):
		r = rules.price_row_from_iq(self.iq(vcl_tax_basis="Net"), 1.0, "2026-11-08 10:00:00", "u")
		self.assertEqual(r["rate"], 11.6)
		self.assertIsNone(r["entered_gross"])

	def test_transfer_without_preconditions_raises(self):
		with self.assertRaises(ValueError):
			rules.price_row_from_iq(self.iq(vcl_uom=""), 1.0, "2026-11-08", "u")

	def test_idempotency_key(self):
		rows = [{"source": "Internal Quotation", "source_ref": "IQ-2026-00012"}, {"source": "LPO", "source_ref": "IQ-2026-00012"}]
		self.assertIs(rules.find_transferred_row(rows, "IQ-2026-00012"), rows[0])
		self.assertIsNone(rules.find_transferred_row(rows, "IQ-2026-00013"))

	def test_revocation_rejects_with_note(self):
		values = rules.iq_revocation_values("IQ-2026-00012")
		self.assertEqual(values["approval_status"], "Rejected")
		self.assertIn("IQ-2026-00012", values["approval_notes"])


class TestApprovalResetExtended(unittest.TestCase):
	def test_currency_and_factor_changes_reset_approval(self):
		before = row()
		self.assertTrue(cps_rules.price_approval_reset_required(before, row(currency="USD")))
		self.assertTrue(cps_rules.price_approval_reset_required(before, row(conversion_factor=12)))

	def test_legacy_blank_currency_gaining_kes_does_not_reset(self):
		# Every row written before §5 has no currency; the first save after the
		# deploy fills KES in. That must not revoke 70 approvals.
		self.assertFalse(cps_rules.price_approval_reset_required(row(currency=None), row(currency="KES")))
		self.assertFalse(cps_rules.price_approval_reset_required(row(conversion_factor=None), row(conversion_factor=1)))


if __name__ == "__main__":
	unittest.main()
