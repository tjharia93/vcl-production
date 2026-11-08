"""Unit tests for the §6 approval-rule engine. Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import cps_approval_rules as rules

SEED = rules.seeded()


class TestMarginMarkup(unittest.TestCase):
	def test_thirty_percent_margin_is_forty_three_percent_markup(self):
		self.assertAlmostEqual(rules.margin_on_price_pct(100, 70), 30.0)
		self.assertAlmostEqual(rules.markup_on_cost_pct(100, 70), 42.857, places=2)

	def test_zero_divisors_give_none(self):
		self.assertIsNone(rules.margin_on_price_pct(0, 70))
		self.assertIsNone(rules.markup_on_cost_pct(100, 0))


class TestNormaliseBenchmark(unittest.TestCase):
	def test_same_basis_is_identity(self):
		self.assertEqual(rules.normalise_benchmark(10, "KES", "KES", 1, 1), 10.0)
		self.assertEqual(rules.normalise_benchmark(10, None, None, None, None), 10.0)

	def test_uom_conversion(self):
		# Benchmark per Carton of 1000 (cf 1000) brought to a row priced per Nos (cf 1).
		self.assertEqual(rules.normalise_benchmark(5000, "KES", "KES", 1000, 1), 5.0)
		# And the other way.
		self.assertEqual(rules.normalise_benchmark(5, "KES", "KES", 1, 1000), 5000.0)

	def test_gross_is_netted(self):
		self.assertEqual(rules.normalise_benchmark(11.6, "KES", "KES", 1, 1, gross=True), 10.0)

	def test_incomparable_is_none(self):
		self.assertIsNone(rules.normalise_benchmark(10, "USD", "KES", 1, 1))
		self.assertIsNone(rules.normalise_benchmark(10, "KES", "KES", None, 1000))
		self.assertIsNone(rules.normalise_benchmark(None, "KES", "KES", 1, 1))

	def test_an_underpriced_row_is_not_auto_approved_against_a_per_carton_list_price(self):
		# Item Price 5,000 per Carton (1000 pcs); row 4.9 per Nos.
		bench = rules.normalise_benchmark(5000, "KES", "KES", 1000, 1)
		d = rules.resolve(SEED, "Computer Paper", "Price", rate=4.9, benchmarks={rules.BENCHMARK_STANDARD_SELLING: bench})
		self.assertEqual(d.outcome, rules.OUTCOME_ROUTE)


class TestCandidates(unittest.TestCase):
	def test_customer_specific_beats_generic_whatever_priority(self):
		generic = {"rule_name": "g", "product_type": "Carton", "stage": "Price", "priority": 1, "enabled": 1}
		specific = {"rule_name": "s", "product_type": "Carton", "stage": "Price", "priority": 99, "enabled": 1, "customer": "ACME"}
		out = rules.candidate_rules([generic, specific], "Carton", "Price", customer="ACME")
		self.assertEqual([r["rule_name"] for r in out], ["s", "g"])
		out = rules.candidate_rules([generic, specific], "Carton", "Price", customer="Other")
		self.assertEqual([r["rule_name"] for r in out], ["g"])

	def test_disabled_out_of_date_and_other_stage_are_skipped(self):
		base = {"rule_name": "r", "product_type": "Carton", "stage": "Price", "enabled": 1}
		self.assertEqual(rules.candidate_rules([dict(base, enabled=0)], "Carton", "Price"), [])
		self.assertEqual(rules.candidate_rules([dict(base, stage="Technical")], "Carton", "Price"), [])
		self.assertEqual(rules.candidate_rules([dict(base, valid_to="2026-01-01")], "Carton", "Price", on_date="2026-06-01"), [])
		self.assertEqual(len(rules.candidate_rules([dict(base, valid_from="2026-01-01")], "Carton", "Price", on_date="2026-06-01")), 1)


class TestSeedResolution(unittest.TestCase):
	"""The eight rows (final, 08/11) resolve as the table says."""

	def test_cp_price_at_or_above_list_auto_approves(self):
		d = rules.resolve(SEED, "Computer Paper", "Price", rate=12, benchmarks={rules.BENCHMARK_STANDARD_SELLING: 10})
		self.assertEqual(d.outcome, rules.OUTCOME_AUTO_APPROVE)
		self.assertEqual(d.rule, "CP price — list")
		self.assertEqual(d.benchmark_value, 10)

	def test_cp_price_below_list_routes_to_neema(self):
		d = rules.resolve(SEED, "Computer Paper", "Price", rate=9, benchmarks={rules.BENCHMARK_STANDARD_SELLING: 10})
		self.assertEqual(d.outcome, rules.OUTCOME_ROUTE)
		self.assertEqual(d.approver_user, "neema@vimit.com")
		self.assertEqual(d.fallback, rules.OUTCOME_MANAGEMENT)
		self.assertEqual([t[1] for t in d.trail], [rules.OUTCOME_CONTINUE, rules.OUTCOME_ROUTE])

	def test_cp_price_with_no_list_price_continues_to_neema(self):
		d = rules.resolve(SEED, "Computer Paper", "Price", rate=9, benchmarks={})
		self.assertEqual(d.outcome, rules.OUTCOME_ROUTE)
		self.assertEqual(d.rule, "CP price — Neema")

	def test_cp_technical_routes_to_neema(self):
		d = rules.resolve(SEED, "Computer Paper", "Technical")
		self.assertEqual((d.outcome, d.approver_user), (rules.OUTCOME_ROUTE, "neema@vimit.com"))

	def test_carton_price_markup(self):
		ok = rules.resolve(SEED, "Carton", "Price", rate=13.0, benchmarks={rules.BENCHMARK_IQ_MANAGEMENT: 10})
		self.assertEqual(ok.outcome, rules.OUTCOME_AUTO_APPROVE)
		low = rules.resolve(SEED, "Carton", "Price", rate=12.9, benchmarks={rules.BENCHMARK_IQ_MANAGEMENT: 10})
		self.assertEqual(low.outcome, rules.OUTCOME_MANAGEMENT)
		self.assertEqual(low.rule, "Carton price")

	def test_carton_price_without_iq_falls_back_to_management(self):
		d = rules.resolve(SEED, "Carton", "Price", rate=12.9, benchmarks={})
		self.assertEqual(d.outcome, rules.OUTCOME_MANAGEMENT)
		self.assertIn("fallback", d.trail[-1][1])

	def test_carton_technical_auto_approves(self):
		d = rules.resolve(SEED, "Carton", "Technical")
		self.assertEqual(d.outcome, rules.OUTCOME_AUTO_APPROVE)

	def test_label_price_margin(self):
		ok = rules.resolve(SEED, "Label", "Price", rate=10, benchmarks={rules.BENCHMARK_IQ_COST: 7})
		self.assertEqual(ok.outcome, rules.OUTCOME_AUTO_APPROVE)
		low = rules.resolve(SEED, "Label", "Price", rate=9.9, benchmarks={rules.BENCHMARK_IQ_COST: 7})
		self.assertEqual(low.outcome, rules.OUTCOME_MANAGEMENT)

	def test_label_monobox_etr_technical_route_to_management_role(self):
		for product_type in ("Label", "Monobox", "ETR (Reel to Reel Printing)"):
			d = rules.resolve(SEED, product_type, "Technical")
			self.assertEqual(d.outcome, rules.OUTCOME_ROUTE)
			self.assertEqual(d.approver_role, rules.DEFAULT_MANAGEMENT_ROLE)

	def test_no_rule_at_all_means_management(self):
		d = rules.resolve(SEED, "Exercise Books", "Technical")
		self.assertEqual(d.outcome, rules.OUTCOME_MANAGEMENT)
		self.assertIsNone(d.rule)

	def test_route_with_absent_approver_applies_fallback_at_once(self):
		rule = {"rule_name": "orphan", "product_type": "Carton", "stage": "Technical", "enabled": 1,
		        "test": "Always", "when_met": "Route", "fallback": "Auto-approve"}
		d = rules.resolve([rule], "Carton", "Technical")
		self.assertEqual(d.outcome, rules.OUTCOME_AUTO_APPROVE)

	def test_seed_rows_are_valid_against_the_option_lists(self):
		for row in SEED:
			self.assertIn(row["stage"], rules.STAGES)
			self.assertIn(row["test"], rules.TESTS)
			self.assertIn(row["benchmark"], rules.BENCHMARKS)
			self.assertIn(row["when_met"], rules.WHEN_MET_OPTIONS)
			self.assertIn(row["when_not_met"], rules.WHEN_NOT_MET_OPTIONS)
			self.assertIn(row["fallback"], rules.FALLBACK_OPTIONS)
		self.assertEqual(len({r["rule_name"] for r in SEED}), len(SEED))


class TestAuthority(unittest.TestCase):
	def routed(self, **kw):
		base = dict(outcome="Route", rule="CP technical", rule_modified="x", approver_user="neema@vimit.com",
		            approver_role=None, management_role="VCL Management Team", fallback="Management",
		            benchmark=None, benchmark_value=None, allow_self_approval=False, trail=())
		base.update(kw)
		return rules.Decision(**base)

	def test_named_approver_may_decide(self):
		self.assertTrue(rules.may_decide(self.routed(), "neema@vimit.com", ["Sales User", "CPS Approver"]))

	def test_role_marker_alone_grants_nothing(self):
		self.assertFalse(rules.may_decide(self.routed(), "someone@vimit.com", ["CPS Approver"]))

	def test_management_may_always_decide(self):
		self.assertTrue(rules.may_decide(self.routed(), "tanuj@vimit.com", ["VCL Management Team"]))
		self.assertTrue(rules.may_decide(self.routed(outcome="Management"), "tanuj@vimit.com", ["VCL Management Team"]))
		self.assertFalse(rules.may_decide(self.routed(outcome="Management"), "neema@vimit.com", ["CPS Approver"]))

	def test_approver_role_route(self):
		d = self.routed(approver_user=None, approver_role="CPS Approver")
		self.assertTrue(rules.may_decide(d, "x@vimit.com", ["CPS Approver"]))

	def test_self_approval_refused_unless_allowed(self):
		self.assertFalse(rules.may_decide(self.routed(), "neema@vimit.com", ["CPS Approver"], author="neema@vimit.com"))
		self.assertTrue(rules.may_decide(self.routed(allow_self_approval=True), "neema@vimit.com", ["CPS Approver"], author="neema@vimit.com"))
		# Management is not bound by the self-approval rule.
		self.assertTrue(rules.may_decide(self.routed(), "tanuj@vimit.com", ["VCL Management Team"], author="tanuj@vimit.com"))

	def test_comment_text(self):
		self.assertIn("auto-approved", rules.comment_text(self.routed(outcome="Auto-approve")))
		self.assertIn("routed to neema@vimit.com", rules.comment_text(self.routed()))
		self.assertIn("VCL Management Team", rules.comment_text(rules.resolve([], "Carton", "Price")))


if __name__ == "__main__":
	unittest.main()
