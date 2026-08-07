"""Which specifications the weekly artwork chase picks up, and which it leaves.

The exclusions carry as much of the design as the inclusions — a chase that
nags about cancelled records, or about specifications written before anybody
was asked for artwork, is one people stop opening. Each is pinned here so
"deliberately excluded" cannot be mistaken for an oversight later.
"""

import unittest
from datetime import date

from production_log.job_card_tracking import artwork_chase_rules as r


def row(**overrides):
	"""A submitted, Printed Computer Paper specification with no artwork."""
	base = {
		"name": "CPT-SPEC-00065",
		"specification_name": "ADVANCE PLASTICS LTD - INVOICE",
		"customer": "ADVANCE PLASTICS LIMITED",
		"product_type": r.COMPUTER_PAPER,
		"print_type": r.PRINT_TYPE_PRINTED,
		"docstatus": 1,
		"creation": "2026-08-06 18:40:42.776845",
		"artwork": None,
		"artwork_tracker": None,
		"artwork_not_ready": 0,
	}
	base.update(overrides)
	return base


class TestArtworkState(unittest.TestCase):
	def test_nothing_said(self):
		self.assertIsNone(r.artwork_state(row()))

	def test_file(self):
		self.assertEqual(r.artwork_state(row(artwork="/private/files/a.pdf")), "file")

	def test_tracker(self):
		self.assertEqual(
			r.artwork_state(row(artwork_tracker="ADVANCE PLASTICS LTD - 00001")), "tracker"
		)

	def test_deferred(self):
		self.assertEqual(r.artwork_state(row(artwork_not_ready=1)), "deferred")

	def test_whitespace_is_not_an_answer(self):
		self.assertIsNone(r.artwork_state(row(artwork="   ", artwork_tracker="  ")))

	def test_a_file_outranks_a_tracker_job(self):
		self.assertEqual(
			r.artwork_state(row(artwork="/private/files/a.pdf", artwork_tracker="X")), "file"
		)


class TestOutstanding(unittest.TestCase):
	def test_submitted_printed_with_nothing_said_is_chased(self):
		self.assertTrue(r.is_outstanding(row()))

	def test_a_file_is_not_chased(self):
		self.assertFalse(r.is_outstanding(row(artwork="/private/files/a.pdf")))

	def test_a_tracker_job_is_not_chased(self):
		self.assertFalse(r.is_outstanding(row(artwork_tracker="ADVANCE PLASTICS LTD - 00001")))

	def test_deferred_is_answered_and_so_not_chased(self):
		# "Not yet" is an answer. Chasing it weekly is how the report becomes
		# noise; it is counted in the summary instead so it cannot be forgotten.
		self.assertFalse(r.is_outstanding(row(artwork_not_ready=1)))

	def test_drafts_are_not_chased(self):
		self.assertFalse(r.is_outstanding(row(docstatus=0)))

	def test_cancelled_are_not_chased(self):
		# CPT-SPEC-00059 is exactly this: cancelled, post-cutoff, no artwork.
		self.assertFalse(r.is_outstanding(row(docstatus=2)))

	def test_plain_jobs_are_not_chased(self):
		self.assertFalse(r.is_outstanding(row(print_type="Plain")))

	def test_other_product_lines_are_not_chased(self):
		self.assertFalse(r.is_outstanding(row(product_type="Label")))

	def test_specs_written_before_anybody_was_asked_are_not_chased(self):
		# The whole March-to-June estate. Nobody was asked for artwork until
		# v8_3 landed on 2026-07-23, so this is not a backlog, it is a
		# different era.
		self.assertFalse(r.is_outstanding(row(creation="2026-03-22 09:00:00")))

	def test_the_cutoff_day_itself_is_in_scope(self):
		self.assertTrue(r.is_outstanding(row(creation=r.ARTWORK_CHASE_FROM + " 09:00:00")))

	def test_the_cutoff_is_movable(self):
		old = row(creation="2026-03-22 09:00:00")
		self.assertTrue(r.is_outstanding(old, cutoff="2026-01-01"))


class TestSelect(unittest.TestCase):
	def test_oldest_first(self):
		rows = [
			row(name="CPT-SPEC-00003", creation="2026-08-05 09:00:00"),
			row(name="CPT-SPEC-00001", creation="2026-07-24 09:00:00"),
			row(name="CPT-SPEC-00002", creation="2026-07-30 09:00:00"),
		]
		self.assertEqual(
			[x["name"] for x in r.select_outstanding(rows)],
			["CPT-SPEC-00001", "CPT-SPEC-00002", "CPT-SPEC-00003"],
		)

	def test_an_empty_week_is_empty_not_an_error(self):
		self.assertEqual(r.select_outstanding([row(artwork="/private/files/a.pdf")]), [])

	def test_no_rows_at_all(self):
		self.assertEqual(r.select_outstanding([]), [])


class TestSummarise(unittest.TestCase):
	def test_counts_the_whole_in_scope_population(self):
		rows = [
			row(name="A", artwork="/private/files/a.pdf"),
			row(name="B", artwork_tracker="JOB - 00001"),
			row(name="C", artwork_not_ready=1),
			row(name="D"),
			row(name="E", creation="2026-03-01 09:00:00"),   # before the cutoff
			row(name="F", docstatus=2),                       # cancelled
			row(name="G", product_type="Carton"),             # another line
		]
		self.assertEqual(
			r.summarise(rows),
			{"in_scope": 4, "file": 1, "tracker": 1, "deferred": 1, "outstanding": 1},
		)

	def test_the_denominator_survives_an_empty_chase(self):
		# The failure mode this guards: a silent Friday that cannot be told from
		# a broken scheduler. in_scope stays non-zero even when nothing is due.
		counts = r.summarise([row(artwork="/private/files/a.pdf")])
		self.assertEqual(counts["outstanding"], 0)
		self.assertEqual(counts["in_scope"], 1)


class TestAge(unittest.TestCase):
	def test_days_waiting(self):
		self.assertEqual(
			r.age_in_days(row(creation="2026-07-24 09:00:00"), date(2026, 8, 7)), 14
		)

	def test_created_today(self):
		self.assertEqual(
			r.age_in_days(row(creation="2026-08-07 09:00:00"), date(2026, 8, 7)), 0
		)

	def test_missing_creation_does_not_throw(self):
		self.assertEqual(r.age_in_days(row(creation=None), date(2026, 8, 7)), 0)


if __name__ == "__main__":
	unittest.main()
