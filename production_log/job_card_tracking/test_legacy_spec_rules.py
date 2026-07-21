"""Unit tests for the legacy ``vcl_spec`` / ``vcl_spec_rev`` retirement verdict.

Plain ``unittest``: no bench, no site, no database.

The verdict under test authorises deleting a field, and the field is the only
surviving record of what a historical order was specified as. So the tests are
weighted towards the ways this could wrongly say yes — an uncountable table read
as empty, a row set that is empty only because nobody looked, an in-use field
whose usage sits on submitted documents.
"""

import unittest

from production_log.job_card_tracking import cps_report_rules
from production_log.job_card_tracking import legacy_spec_rules as legacy


def row(**kw):
	base = {
		"doctype": "Sales Order Item",
		"fieldname": "vcl_spec",
		"origin": legacy.ORIGIN_CUSTOM_FIELD,
		"total_rows": 4120,
		"rows_with_value": 0,
	}
	base.update(kw)
	return legacy.build_field_row(**base)


class TestFieldVerdict(unittest.TestCase):
	def test_zero_usage_is_unused(self):
		self.assertEqual(legacy.field_verdict(0), legacy.VERDICT_UNUSED)

	def test_any_usage_is_in_use(self):
		self.assertEqual(legacy.field_verdict(1), legacy.VERDICT_IN_USE)
		self.assertEqual(legacy.field_verdict(4120), legacy.VERDICT_IN_USE)

	def test_an_uncountable_field_is_unknown_rather_than_empty(self):
		# "Empty" is the verdict that authorises deletion, so a count that
		# failed must never collapse into it.
		self.assertEqual(legacy.field_verdict(None), legacy.VERDICT_UNKNOWN)
		self.assertEqual(legacy.field_verdict("not a number"), legacy.VERDICT_UNKNOWN)

	def test_unknown_blocks_exactly_as_in_use_does(self):
		self.assertTrue(legacy.is_blocking(legacy.VERDICT_UNKNOWN))
		self.assertTrue(legacy.is_blocking(legacy.VERDICT_IN_USE))
		self.assertFalse(legacy.is_blocking(legacy.VERDICT_UNUSED))


class TestFieldRow(unittest.TestCase):
	def test_a_row_is_scalar_only(self):
		built = row(rows_with_value=3, submitted_rows_with_value=2)
		self.assertEqual(set(built), set(legacy.REPORT_COLUMNS))
		for value in built.values():
			self.assertNotIsInstance(value, (list, dict))

	def test_the_retirement_action_depends_on_where_the_field_lives(self):
		# A Custom Field can be deleted from the Desk; a standard DocField comes
		# back on the next migrate, which is a different job entirely.
		custom = row(origin=legacy.ORIGIN_CUSTOM_FIELD)["retirement_action"]
		standard = row(origin=legacy.ORIGIN_STANDARD_FIELD)["retirement_action"]
		self.assertNotEqual(custom, standard)
		self.assertIn("migrate", standard)

	def test_each_legacy_field_explains_what_it_was_for(self):
		for fieldname in legacy.LEGACY_FIELDNAMES:
			self.assertIn("Legacy", row(fieldname=fieldname)["purpose"])

	def test_an_unrecognised_fieldname_still_gets_a_purpose(self):
		self.assertTrue(row(fieldname="vcl_something_else")["purpose"])

	def test_counts_that_cannot_be_read_stay_none(self):
		built = row(rows_with_value=None, total_rows="?")
		self.assertIsNone(built["rows_with_value"])
		self.assertIsNone(built["total_rows"])
		self.assertTrue(built["is_blocking"])


class TestBlockerReason(unittest.TestCase):
	def test_an_empty_field_is_not_a_blocker(self):
		self.assertIsNone(legacy.blocker_reason(row(rows_with_value=0)))

	def test_usage_on_submitted_documents_is_called_out(self):
		# A legacy value on a draft line is a typo someone can delete. The same
		# value on a submitted line is part of a document sent to a customer.
		reason = legacy.blocker_reason(row(rows_with_value=9, submitted_rows_with_value=7))
		self.assertIn("submitted", reason)
		self.assertIn("7", reason)

	def test_usage_with_no_submitted_rows_is_still_a_blocker(self):
		reason = legacy.blocker_reason(row(rows_with_value=9, submitted_rows_with_value=0))
		self.assertIn("9", reason)
		self.assertNotIn("submitted", reason)

	def test_an_uncountable_field_says_so(self):
		reason = legacy.blocker_reason(row(rows_with_value=None))
		self.assertIn("could not be counted", reason)

	def test_every_reason_names_the_field_it_is_about(self):
		for built in (row(rows_with_value=3), row(rows_with_value=None)):
			reason = legacy.blocker_reason(built)
			self.assertIn(built["doctype"], reason)
			self.assertIn(built["fieldname"], reason)


class TestSummary(unittest.TestCase):
	def test_all_empty_fields_are_safe_to_retire(self):
		summary = legacy.summarise_audit([row(fieldname="vcl_spec"), row(fieldname="vcl_spec_rev")])
		self.assertTrue(summary["safe_to_retire"])
		self.assertEqual(summary["fields_found"], 2)
		self.assertEqual(summary["fields_unused"], 2)
		self.assertEqual(summary["blockers"], [])

	def test_one_field_still_in_use_holds_the_whole_retirement(self):
		summary = legacy.summarise_audit(
			[row(fieldname="vcl_spec"), row(fieldname="vcl_spec_rev", rows_with_value=12)]
		)
		self.assertFalse(summary["safe_to_retire"])
		self.assertEqual(summary["fields_in_use"], 1)
		self.assertEqual(summary["rows_with_value"], 12)
		self.assertEqual(len(summary["blockers"]), 1)

	def test_one_uncountable_field_holds_it_too(self):
		summary = legacy.summarise_audit([row(rows_with_value=None)])
		self.assertFalse(summary["safe_to_retire"])
		self.assertEqual(summary["fields_unknown"], 1)

	def test_finding_nothing_is_not_the_same_as_finding_nothing_in_use(self):
		# A site with no legacy fields has nothing to retire. Reporting it as
		# "safe to retire" would send someone looking for fields to delete that
		# were never there.
		summary = legacy.summarise_audit([])
		self.assertTrue(summary["nothing_to_retire"])
		self.assertFalse(summary["safe_to_retire"])

	def test_affected_doctypes_are_counted_once_each(self):
		summary = legacy.summarise_audit(
			[
				row(doctype="Sales Order Item", fieldname="vcl_spec"),
				row(doctype="Sales Order Item", fieldname="vcl_spec_rev"),
				row(doctype="Delivery Note Item", fieldname="vcl_spec"),
			]
		)
		self.assertEqual(summary["doctypes_affected"], 2)


class TestRetirementPlan(unittest.TestCase):
	def test_nothing_found_produces_a_one_line_plan(self):
		plan = legacy.retirement_plan([], legacy.summarise_audit([]))
		self.assertEqual(len(plan), 1)
		self.assertIn("Nothing to do", plan[0])

	def test_a_blocked_plan_refuses_to_delete_and_says_why(self):
		rows = [row(rows_with_value=12, submitted_rows_with_value=12)]
		plan = legacy.retirement_plan(rows, legacy.summarise_audit(rows))
		joined = " ".join(plan)
		self.assertIn("Do not retire anything yet", plan[0])
		self.assertIn("12", joined)
		self.assertNotIn("Take a site backup", joined)

	def test_a_blocked_plan_insists_the_value_is_preserved_first(self):
		rows = [row(rows_with_value=1)]
		joined = " ".join(legacy.retirement_plan(rows, legacy.summarise_audit(rows)))
		self.assertIn("before the field is removed", joined)
		self.assertIn("Re-run this audit", joined)

	def test_a_clear_plan_backs_up_before_it_deletes(self):
		rows = [row(fieldname="vcl_spec"), row(fieldname="vcl_spec_rev")]
		plan = legacy.retirement_plan(rows, legacy.summarise_audit(rows))
		joined = " ".join(plan)
		self.assertIn("Take a site backup", joined)
		backup_at = next(i for i, step in enumerate(plan) if "site backup" in step)
		first_delete_at = next(i for i, step in enumerate(plan) if "Delete the Custom Field" in step)
		self.assertLess(backup_at, first_delete_at)

	def test_a_clear_plan_names_every_field_it_would_retire(self):
		rows = [
			row(doctype="Sales Order Item", fieldname="vcl_spec"),
			row(doctype="Sales Order Item", fieldname="vcl_spec_rev"),
		]
		joined = " ".join(legacy.retirement_plan(rows, legacy.summarise_audit(rows)))
		for fieldname in ("vcl_spec", "vcl_spec_rev"):
			self.assertIn(fieldname, joined)

	def test_the_plan_is_computed_when_no_summary_is_supplied(self):
		rows = [row(rows_with_value=5)]
		self.assertEqual(
			legacy.retirement_plan(rows, None), legacy.retirement_plan(rows, legacy.summarise_audit(rows))
		)


class TestCSVRoundTrip(unittest.TestCase):
	def test_a_row_survives_the_trip_through_csv(self):
		# Shares the report writer with the migration report, so specification
		# names containing commas cannot corrupt either export.
		rows = [row(rows_with_value=3, submitted_rows_with_value=2)]
		text = cps_report_rules.to_csv(rows, legacy.REPORT_COLUMNS)
		header = text.splitlines()[0].split(",")
		self.assertEqual(header, list(legacy.REPORT_COLUMNS))
		self.assertIn("vcl_spec", text)


if __name__ == "__main__":
	unittest.main()
