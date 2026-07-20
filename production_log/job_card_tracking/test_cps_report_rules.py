"""Unit tests for the CPS migration/readiness report shaping.

Plain ``unittest``: no bench, no site, no database. What is under test is the
report's *judgement* — which problems block enforcement and which are merely
untidy, when ``ready_to_enforce`` is allowed to be true, and whether a row
survives the trip through CSV intact.

The Frappe-bound half (``cps_migration_report``) is not covered here; it reads
documents and is verified by reading it against the contract, not by these.
"""

import csv
import io
import unittest

from production_log.job_card_tracking import cps_report_rules as rules
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
		"current_rate": None,
		"current_uom": None,
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


def decide(s, items=(), history=None):
	return cps_rules.resolve_item_link(s, list(items), history or set())


def row_for(s, items=(), history=None, priced=True, customer_exists=True, duplicates=None):
	return rules.build_spec_row(
		s,
		decide(s, items, history),
		has_approved_price=priced,
		customer_exists=customer_exists,
		duplicate_keys=duplicates or {},
	)


class TestEnforceability(unittest.TestCase):
	def test_submitted_active_spec_is_enforceable(self):
		self.assertTrue(rules.is_enforceable(spec()))

	def test_draft_spec_is_not_enforceable(self):
		self.assertFalse(rules.is_enforceable(spec(docstatus=0)))

	def test_cancelled_spec_is_not_enforceable(self):
		self.assertFalse(rules.is_enforceable(spec(docstatus=2)))

	def test_discontinued_spec_is_not_enforceable(self):
		self.assertFalse(rules.is_enforceable(spec(status="Discontinued")))

	def test_docstatus_labels_cover_all_three_states(self):
		self.assertEqual(rules.docstatus_label(0), "Draft")
		self.assertEqual(rules.docstatus_label(1), "Submitted")
		self.assertEqual(rules.docstatus_label(2), "Cancelled")

	def test_unknown_docstatus_does_not_explode(self):
		self.assertEqual(rules.docstatus_label("banana"), "Unknown")


class TestIssueDetection(unittest.TestCase):
	def test_unlinked_spec_is_flagged(self):
		s = spec(linked_item=None)
		issues = rules.detect_spec_issues(s, decide(s), True, True)
		self.assertIn(rules.ISSUE_UNLINKED, issues)

	def test_linked_spec_is_not_flagged_unlinked(self):
		s = spec(linked_item="CP-3PT-A4")
		issues = rules.detect_spec_issues(s, decide(s, [item("CP-3PT-A4")]), True, True)
		self.assertNotIn(rules.ISSUE_UNLINKED, issues)

	def test_missing_price_is_flagged(self):
		s = spec(linked_item="CP-3PT-A4")
		issues = rules.detect_spec_issues(s, decide(s), has_approved_price=False, customer_exists=True)
		self.assertIn(rules.ISSUE_MISSING_PRICE, issues)

	def test_blank_customer_is_flagged(self):
		s = spec(customer="")
		issues = rules.detect_spec_issues(s, decide(s), True, True)
		self.assertIn(rules.ISSUE_MISSING_CUSTOMER, issues)

	def test_customer_that_no_longer_exists_is_flagged(self):
		"""A named-but-deleted Customer can never match an order. Same blocker."""
		s = spec(customer="Ghost Ltd")
		issues = rules.detect_spec_issues(s, decide(s), True, customer_exists=False)
		self.assertIn(rules.ISSUE_MISSING_CUSTOMER, issues)

	def test_cancelled_is_reported_without_also_reporting_draft(self):
		s = spec(docstatus=2, status="Active")
		issues = rules.detect_spec_issues(s, decide(s), True, True)
		self.assertIn(rules.ISSUE_CANCELLED, issues)
		self.assertNotIn(rules.ISSUE_DRAFT, issues)

	def test_draft_is_reported(self):
		s = spec(docstatus=0)
		issues = rules.detect_spec_issues(s, decide(s), True, True)
		self.assertIn(rules.ISSUE_DRAFT, issues)

	def test_inactive_status_is_reported(self):
		s = spec(status="Inactive")
		issues = rules.detect_spec_issues(s, decide(s), True, True)
		self.assertIn(rules.ISSUE_INACTIVE, issues)

	def test_cancelled_spec_is_not_also_called_inactive(self):
		"""Cancelled already says it. Two codes for one fact double the count."""
		s = spec(docstatus=2, status="Inactive")
		issues = rules.detect_spec_issues(s, decide(s), True, True)
		self.assertIn(rules.ISSUE_CANCELLED, issues)
		self.assertNotIn(rules.ISSUE_INACTIVE, issues)


class TestDuplicateDetection(unittest.TestCase):
	def test_two_active_specs_on_one_customer_item_pair_are_duplicates(self):
		specs = [
			spec(name="A", customer="ACME Ltd", linked_item="CP-3PT-A4"),
			spec(name="B", customer="ACME Ltd", linked_item="CP-3PT-A4"),
		]
		self.assertEqual(
			rules.duplicate_customer_item_keys(specs),
			{("ACME Ltd", "CP-3PT-A4"): ["A", "B"]},
		)

	def test_same_item_for_different_customers_is_the_normal_case(self):
		"""Items are generic; many customers legitimately share one."""
		specs = [
			spec(name="A", customer="ACME Ltd", linked_item="CP-3PT-A4"),
			spec(name="B", customer="Beta Ltd", linked_item="CP-3PT-A4"),
		]
		self.assertEqual(rules.duplicate_customer_item_keys(specs), {})

	def test_a_cancelled_twin_is_not_a_duplicate(self):
		specs = [
			spec(name="A", linked_item="CP-3PT-A4"),
			spec(name="B", linked_item="CP-3PT-A4", docstatus=2),
		]
		self.assertEqual(rules.duplicate_customer_item_keys(specs), {})

	def test_a_discontinued_twin_is_not_a_duplicate(self):
		specs = [
			spec(name="A", linked_item="CP-3PT-A4"),
			spec(name="B", linked_item="CP-3PT-A4", status="Discontinued"),
		]
		self.assertEqual(rules.duplicate_customer_item_keys(specs), {})

	def test_unlinked_specs_are_never_duplicates_of_each_other(self):
		specs = [spec(name="A"), spec(name="B")]
		self.assertEqual(rules.duplicate_customer_item_keys(specs), {})

	def test_duplicate_key_surfaces_as_an_issue_on_the_row(self):
		specs = [
			spec(name="A", linked_item="CP-3PT-A4"),
			spec(name="B", linked_item="CP-3PT-A4"),
		]
		dupes = rules.duplicate_customer_item_keys(specs)
		row = row_for(specs[0], [item("CP-3PT-A4")], duplicates=dupes)
		self.assertIn(rules.ISSUE_DUPLICATE, row["issues"])


class TestBlocking(unittest.TestCase):
	def test_unlinked_active_spec_blocks(self):
		row = row_for(spec())
		self.assertTrue(row["is_blocking"])

	def test_unlinked_cancelled_spec_does_not_block(self):
		"""It cannot be ordered against, so enforcement is safe regardless."""
		row = row_for(spec(docstatus=2))
		self.assertFalse(row["is_blocking"])

	def test_unlinked_discontinued_spec_does_not_block(self):
		self.assertFalse(row_for(spec(status="Discontinued"))["is_blocking"])

	def test_linked_and_priced_active_spec_does_not_block(self):
		row = row_for(spec(linked_item="CP-3PT-A4"), [item("CP-3PT-A4")])
		self.assertFalse(row["is_blocking"])

	def test_missing_price_blocks_an_otherwise_ready_spec(self):
		row = row_for(spec(linked_item="CP-3PT-A4"), [item("CP-3PT-A4")], priced=False)
		self.assertTrue(row["is_blocking"])

	def test_draft_status_alone_is_not_a_blocking_issue(self):
		self.assertNotIn(rules.ISSUE_DRAFT, rules.BLOCKING_ISSUES)


class TestSpecRowShape(unittest.TestCase):
	def test_every_value_is_a_scalar(self):
		"""CSV-friendliness is the contract, so no lists or dicts may leak out."""
		row = row_for(spec(), [item("CP-3PT-A4"), item("CP-2PT-A4")], history={"CP-3PT-A4"})
		for key, value in row.items():
			self.assertIsInstance(
				value, (str, int, float, bool, type(None)), "{0} is not a scalar".format(key)
			)

	def test_row_covers_every_declared_column(self):
		row = row_for(spec())
		self.assertEqual(set(rules.REPORT_COLUMNS) - set(row), set())

	def test_reports_current_link_and_identity_verbatim(self):
		row = row_for(
			spec(linked_item="CP-3PT-A4", customer="ACME Ltd", status="Active", docstatus=1),
			[item("CP-3PT-A4")],
		)
		self.assertEqual(row["linked_item"], "CP-3PT-A4")
		self.assertEqual(row["customer"], "ACME Ltd")
		self.assertEqual(row["product_type"], "Computer Paper")
		self.assertEqual(row["specification_name"], "Delivery Note 3 Part A4")
		self.assertEqual(row["status"], "Active")
		self.assertEqual(row["docstatus"], 1)
		self.assertEqual(row["docstatus_label"], "Submitted")
		self.assertTrue(row["is_linked"])

	def test_sole_candidate_is_reported_as_a_proposal(self):
		row = row_for(spec(), [item("CP-3PT-A4"), item("CP-2PT-A4")], history={"CP-3PT-A4"})
		self.assertEqual(row["match"], cps_rules.MATCH_EXACT_SOLE)
		self.assertEqual(row["proposed_item"], "CP-3PT-A4")
		self.assertEqual(row["proposed_confidence"], cps_rules.CONFIDENCE_HIGH)

	def test_ambiguous_spec_proposes_nothing_but_still_ranks(self):
		row = row_for(
			spec(), [item("CP-3PT-A4"), item("CP-2PT-A4")], history={"CP-3PT-A4", "CP-2PT-A4"}
		)
		self.assertEqual(row["match"], cps_rules.MATCH_AMBIGUOUS)
		self.assertIsNone(row["proposed_item"])
		self.assertEqual(row["candidate_count"], 2)
		self.assertIn("CP-3PT-A4", row["top_candidates"])
		self.assertIn("CP-2PT-A4", row["top_candidates"])

	def test_reasons_are_carried_for_every_ranked_candidate(self):
		row = row_for(spec(), [item("CP-3PT-A4")], history={"CP-3PT-A4"})
		self.assertIn("previously transacted", row["top_candidate_reasons"])

	def test_already_linked_spec_proposes_nothing(self):
		row = row_for(spec(linked_item="CP-3PT-A4"), [item("CP-3PT-A4")])
		self.assertEqual(row["match"], cps_rules.MATCH_ALREADY_LINKED)
		self.assertIsNone(row["proposed_item"])

	def test_candidate_list_is_capped_but_the_count_is_not(self):
		items = [item("CP-{0}".format(n)) for n in range(6)]
		row = row_for(spec(), items)
		self.assertEqual(row["candidate_count"], 6)
		self.assertEqual(row["top_candidates"].count(";"), 2)

	def test_no_candidates_renders_empty_strings_not_none(self):
		ranked, reasons = rules.format_candidates([])
		self.assertEqual((ranked, reasons), ("", ""))


class TestSummary(unittest.TestCase):
	def _rows(self):
		specs = [
			spec(name="A", linked_item="CP-A"),
			spec(name="B"),
			spec(name="C", docstatus=2),
		]
		return [
			row_for(specs[0], [item("CP-A")]),
			row_for(specs[1]),
			row_for(specs[2]),
		]

	def test_counts_totals_and_link_state(self):
		summary = rules.summarise_report(self._rows())
		self.assertEqual(summary["total"], 3)
		self.assertEqual(summary["linked"], 1)
		self.assertEqual(summary["unlinked"], 2)

	def test_counts_enforceable_separately_from_total(self):
		summary = rules.summarise_report(self._rows())
		self.assertEqual(summary["enforceable"], 2)

	def test_counts_issues_by_code(self):
		summary = rules.summarise_report(self._rows())
		self.assertEqual(summary[rules.ISSUE_COUNT_PREFIX + rules.ISSUE_UNLINKED], 2)
		self.assertEqual(summary[rules.ISSUE_COUNT_PREFIX + rules.ISSUE_CANCELLED], 1)

	def test_issue_counters_do_not_collide_with_headline_counts(self):
		"""``unlinked`` is both an issue code and a headline count."""
		summary = rules.summarise_report(self._rows())
		self.assertEqual(summary["unlinked"], 2)
		self.assertEqual(summary[rules.ISSUE_COUNT_PREFIX + rules.ISSUE_UNLINKED], 2)

	def test_counts_proposed_mappings(self):
		rows = [row_for(spec(), [item("CP-A"), item("CP-B")], history={"CP-A"})]
		self.assertEqual(rules.summarise_report(rows)["proposed_mappings"], 1)

	def test_ready_to_enforce_when_everything_is_clean(self):
		rows = [row_for(spec(linked_item="CP-A"), [item("CP-A")])]
		summary = rules.summarise_report(rows)
		self.assertEqual(summary["blocking"], 0)
		self.assertTrue(summary["ready_to_enforce"])

	def test_not_ready_while_an_active_spec_is_unlinked(self):
		self.assertFalse(rules.summarise_report(self._rows())["ready_to_enforce"])

	def test_not_ready_while_a_controlled_order_line_has_no_spec(self):
		"""Links can all be resolved and enforcement still break a live order."""
		rows = [row_for(spec(linked_item="CP-A"), [item("CP-A")])]
		summary = rules.summarise_report(rows, [{"sales_order": "SO-0001", "idx": 1}])
		self.assertEqual(summary["open_so_lines_without_cps"], 1)
		self.assertFalse(summary["ready_to_enforce"])

	def test_cancelled_and_inactive_specs_alone_do_not_block(self):
		rows = [
			row_for(spec(name="C", docstatus=2)),
			row_for(spec(name="D", status="Discontinued")),
		]
		self.assertTrue(rules.summarise_report(rows)["ready_to_enforce"])

	def test_empty_report_is_ready_and_does_not_divide_by_zero(self):
		summary = rules.summarise_report([])
		self.assertEqual(summary["total"], 0)
		self.assertTrue(summary["ready_to_enforce"])


class TestCsvExport(unittest.TestCase):
	def test_header_matches_declared_columns(self):
		reader = csv.reader(io.StringIO(rules.to_csv([row_for(spec())])))
		self.assertEqual(next(reader), list(rules.REPORT_COLUMNS))

	def test_a_comma_in_a_specification_name_survives_the_round_trip(self):
		row = row_for(spec(specification_name="Invoice, 3 Part, A4"))
		parsed = list(csv.DictReader(io.StringIO(rules.to_csv([row]))))
		self.assertEqual(parsed[0]["specification_name"], "Invoice, 3 Part, A4")

	def test_open_so_lines_export_under_their_own_columns(self):
		line = {
			"sales_order": "SO-0001",
			"transaction_date": "2026-07-01",
			"customer": "ACME Ltd",
			"status": "To Deliver and Bill",
			"idx": 1,
			"item_code": "CP-3PT-A4",
			"item_name": "Computer Paper 3 Part A4",
			"qty": 10,
			"rate": 5.172413793,
			"issue": "controlled-line-without-cps",
		}
		parsed = list(
			csv.DictReader(io.StringIO(rules.to_csv([line], rules.OPEN_SO_LINE_COLUMNS)))
		)
		self.assertEqual(parsed[0]["sales_order"], "SO-0001")
		self.assertEqual(parsed[0]["issue"], "controlled-line-without-cps")

	def test_unknown_keys_on_a_row_do_not_break_the_export(self):
		row = row_for(spec())
		row["something_new"] = ["not", "a", "scalar"]
		self.assertIn("CPT-SPEC-00001", rules.to_csv([row]))

	def test_empty_report_still_emits_a_header(self):
		self.assertEqual(
			rules.to_csv([]).strip().split("\r\n")[0], ",".join(rules.REPORT_COLUMNS)
		)


if __name__ == "__main__":
	unittest.main()
