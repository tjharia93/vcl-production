"""Unit tests for the CPS -> Item link rules.

Like ``test_cps_rules``, these run under plain ``unittest`` with no bench, no
site and no database. The rules under test decide three things:

* whether a specification names the Item on a Sales Order line (eligibility),
* whether a specification is allowed to be saved without an Item (transition),
* which Item an unlinked specification probably means (migration readiness),

and the third of those must never guess. 53 of the 56 live Computer Paper
specifications have no ``linked_item``; auto-mapping the ambiguous ones would
silently attach the wrong customer's price to the wrong product.
"""

import unittest

from production_log.job_card_tracking import cps_rules


def spec(**kw):
	base = {
		"name": "CPT-SPEC-00001",
		"customer": "ACME Ltd",
		"product_type": "Computer Paper",
		"specification_name": "Delivery Note 3 Part A4",
		"job_size": "A4",
		"linked_item": None,
		"docstatus": 1,
		"status": "Active",
	}
	base.update(kw)
	return base


def item(code, **kw):
	base = {
		"item_code": code,
		"item_name": code,
		"item_group": "Computer Paper",
		"cps_product_type": "Computer Paper",
	}
	base.update(kw)
	return base


class TestSpecServesItem(unittest.TestCase):
	"""Eligibility: exact Customer + Item + CPS (no fuzzy fallback)."""

	def test_matching_item_serves(self):
		self.assertTrue(cps_rules.spec_serves_item(spec(linked_item="CP-3PT-A4"), "CP-3PT-A4"))

	def test_different_item_does_not_serve(self):
		self.assertFalse(cps_rules.spec_serves_item(spec(linked_item="CP-3PT-A4"), "CP-2PT-A4"))

	def test_unlinked_spec_never_serves(self):
		# The whole point: a spec with no Item is not "compatible with everything".
		self.assertFalse(cps_rules.spec_serves_item(spec(linked_item=None), "CP-3PT-A4"))

	def test_blank_item_never_serves(self):
		self.assertFalse(cps_rules.spec_serves_item(spec(linked_item="CP-3PT-A4"), None))

	def test_whitespace_is_not_a_difference(self):
		self.assertTrue(cps_rules.spec_serves_item(spec(linked_item=" CP-3PT-A4 "), "CP-3PT-A4"))

	def test_many_specs_may_share_one_item(self):
		"""Items are generic; the customer is what makes a spec specific."""
		a = spec(name="CPT-SPEC-1", customer="ACME Ltd", linked_item="CP-3PT-A4")
		b = spec(name="CPT-SPEC-2", customer="Beta Ltd", linked_item="CP-3PT-A4")

		self.assertTrue(cps_rules.spec_serves_item(a, "CP-3PT-A4"))
		self.assertTrue(cps_rules.spec_serves_item(b, "CP-3PT-A4"))


class TestItemLinkRequired(unittest.TestCase):
	"""Transition rule: required for new and materially edited specs only."""

	def test_new_spec_requires_a_link(self):
		self.assertTrue(cps_rules.item_link_required(before=None, after=spec()))

	def test_legacy_spec_untouched_is_grandfathered(self):
		before = spec(linked_item=None)
		self.assertFalse(cps_rules.item_link_required(before=before, after=dict(before)))

	def test_legacy_spec_cosmetic_edit_is_grandfathered(self):
		before = spec(linked_item=None, internal_notes="old")
		after = spec(linked_item=None, internal_notes="new")

		self.assertFalse(cps_rules.item_link_required(before=before, after=after))

	def test_material_edit_forces_the_link(self):
		before = spec(linked_item=None, job_size="A4")
		after = spec(linked_item=None, job_size="A5")

		self.assertTrue(cps_rules.item_link_required(before=before, after=after))

	def test_material_edit_on_already_linked_spec_is_satisfied(self):
		before = spec(linked_item="CP-3PT-A4", job_size="A4")
		after = spec(linked_item="CP-3PT-A4", job_size="A5")

		self.assertFalse(cps_rules.item_link_required(before=before, after=after))

	def test_clearing_the_link_is_itself_material(self):
		before = spec(linked_item="CP-3PT-A4")
		after = spec(linked_item=None)

		self.assertTrue(cps_rules.item_link_required(before=before, after=after))


class TestScoreItemCandidate(unittest.TestCase):
	def test_wrong_product_type_scores_none(self):
		result = cps_rules.score_item_candidate(
			spec(), item("LBL-WHITE", cps_product_type="Label")
		)

		self.assertEqual(result.confidence, cps_rules.CONFIDENCE_NONE)
		self.assertIn("product type", " ".join(result.reasons).lower())

	def test_traded_item_scores_high(self):
		result = cps_rules.score_item_candidate(
			spec(), item("CP-3PT-A4"), customer_item_history={"CP-3PT-A4"}
		)

		self.assertEqual(result.confidence, cps_rules.CONFIDENCE_HIGH)

	def test_untraded_but_right_type_scores_low(self):
		result = cps_rules.score_item_candidate(spec(), item("CP-3PT-A4"))

		self.assertEqual(result.confidence, cps_rules.CONFIDENCE_LOW)

	def test_name_overlap_lifts_an_untraded_item_to_medium(self):
		result = cps_rules.score_item_candidate(
			spec(specification_name="Delivery Note 3 Part A4"),
			item("CP-3PT-A4", item_name="Computer Paper 3 Part A4"),
		)

		self.assertEqual(result.confidence, cps_rules.CONFIDENCE_MEDIUM)

	def test_reasons_are_always_populated(self):
		result = cps_rules.score_item_candidate(spec(), item("CP-3PT-A4"))
		self.assertTrue(result.reasons)


class TestResolveItemLink(unittest.TestCase):
	def test_sole_high_confidence_candidate_auto_maps(self):
		decision = cps_rules.resolve_item_link(
			spec(),
			[item("CP-3PT-A4"), item("CP-2PT-A4")],
			customer_item_history={"CP-3PT-A4"},
		)

		self.assertEqual(decision.auto_item, "CP-3PT-A4")
		self.assertEqual(decision.match, cps_rules.MATCH_EXACT_SOLE)

	def test_two_traded_items_are_ambiguous_and_never_auto_map(self):
		decision = cps_rules.resolve_item_link(
			spec(),
			[item("CP-3PT-A4"), item("CP-2PT-A4")],
			customer_item_history={"CP-3PT-A4", "CP-2PT-A4"},
		)

		self.assertIsNone(decision.auto_item)
		self.assertEqual(decision.match, cps_rules.MATCH_AMBIGUOUS)
		self.assertEqual(len(decision.candidates), 2)

	def test_no_candidate_of_the_right_type_reports_none(self):
		decision = cps_rules.resolve_item_link(
			spec(), [item("LBL-WHITE", cps_product_type="Label")]
		)

		self.assertIsNone(decision.auto_item)
		self.assertEqual(decision.match, cps_rules.MATCH_NONE)

	def test_a_name_match_alone_does_not_auto_map(self):
		"""Medium confidence is a suggestion for a human, not a mapping."""
		decision = cps_rules.resolve_item_link(
			spec(specification_name="Delivery Note 3 Part A4"),
			[item("CP-3PT-A4", item_name="Computer Paper 3 Part A4")],
		)

		self.assertIsNone(decision.auto_item)
		self.assertEqual(decision.match, cps_rules.MATCH_AMBIGUOUS)
		self.assertEqual(decision.candidates[0].item_code, "CP-3PT-A4")

	def test_already_linked_spec_is_left_alone(self):
		decision = cps_rules.resolve_item_link(
			spec(linked_item="CP-3PT-A4"), [item("CP-3PT-A4")]
		)

		self.assertEqual(decision.match, cps_rules.MATCH_ALREADY_LINKED)
		self.assertIsNone(decision.auto_item)

	def test_candidates_are_ranked_best_first(self):
		decision = cps_rules.resolve_item_link(
			spec(specification_name="Delivery Note 3 Part A4"),
			[
				item("CP-1PT-A4", item_name="Computer Paper 1 Part A4"),
				item("CP-3PT-A4", item_name="Computer Paper 3 Part A4"),
			],
			customer_item_history={"CP-3PT-A4"},
		)

		self.assertEqual(decision.candidates[0].item_code, "CP-3PT-A4")


class TestReadinessSummary(unittest.TestCase):
	def test_counts_by_match_class(self):
		decisions = [
			cps_rules.resolve_item_link(spec(linked_item="X"), [item("X")]),
			cps_rules.resolve_item_link(spec(), [item("A")], customer_item_history={"A"}),
			cps_rules.resolve_item_link(spec(), [item("A"), item("B")],
			                            customer_item_history={"A", "B"}),
			cps_rules.resolve_item_link(spec(), []),
		]

		summary = cps_rules.summarise_readiness(decisions)

		self.assertEqual(summary["total"], 4)
		self.assertEqual(summary[cps_rules.MATCH_ALREADY_LINKED], 1)
		self.assertEqual(summary[cps_rules.MATCH_EXACT_SOLE], 1)
		self.assertEqual(summary[cps_rules.MATCH_AMBIGUOUS], 1)
		self.assertEqual(summary[cps_rules.MATCH_NONE], 1)

	def test_ready_only_when_nothing_is_unresolved(self):
		linked = cps_rules.resolve_item_link(spec(linked_item="X"), [item("X")])
		unresolved = cps_rules.resolve_item_link(spec(), [])

		self.assertTrue(cps_rules.summarise_readiness([linked])["ready_to_enforce"])
		self.assertFalse(cps_rules.summarise_readiness([linked, unresolved])["ready_to_enforce"])


if __name__ == "__main__":
	unittest.main()
