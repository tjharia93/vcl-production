"""Tests for the Job Card Label Run Log.

Plain ``unittest``, no bench. Two halves:

* the arithmetic in ``label_run_rules`` — minutes from stamps, and the rollups;
* the DocType JSON, read as files, for the one property that fails quietly:
  ``allow_on_submit``. The card is submitted before it reaches the press, so
  any Run Log field without it makes the floor's save throw "Not allowed to
  change X after submission" — and only on a row that already exists, which is
  the second time anyone touches it.

Run with ``python3 -m unittest production_log.job_card_tracking.test_label_run_rules``.
"""

import json
import unittest
from datetime import datetime
from pathlib import Path

from production_log.job_card_tracking import label_run_rules

DOCTYPE_DIR = Path(__file__).resolve().parent / "doctype"
BREAKS = ("Section Break", "Column Break", "Tab Break")


def load(folder):
	return json.loads((DOCTYPE_DIR / folder / f"{folder}.json").read_text(encoding="utf-8"))


def at(hh, mm, day=15):
	return datetime(2026, 9, day, hh, mm)


class TestRunMinutes(unittest.TestCase):
	def test_all_three_segments(self):
		minutes, out_of_order = label_run_rules.run_minutes({
			"setup_start": at(8, 0),
			"first_good_label": at(8, 42),
			"run_end": at(8, 55),
			"washup_end": at(9, 10),
		})

		self.assertEqual(out_of_order, [])
		self.assertEqual(minutes, {"setup_mins": 42.0, "run_mins": 13.0, "washup_mins": 15.0})

	def test_a_missing_stamp_leaves_only_its_segments_empty(self):
		minutes, out_of_order = label_run_rules.run_minutes({
			"setup_start": at(8, 0),
			"first_good_label": at(8, 30),
			"run_end": None,
			"washup_end": at(9, 0),
		})

		self.assertEqual(out_of_order, [])
		self.assertEqual(minutes, {"setup_mins": 30.0, "run_mins": None, "washup_mins": None})

	def test_an_end_before_its_start_is_reported_never_negative(self):
		minutes, out_of_order = label_run_rules.run_minutes({
			"setup_start": at(9, 0),
			"first_good_label": at(8, 0),
			"run_end": at(9, 30),
			"washup_end": None,
		})

		self.assertEqual(out_of_order, [("setup_start", "first_good_label")])
		self.assertIsNone(minutes["setup_mins"])
		self.assertEqual(minutes["run_mins"], 90.0)

	def test_a_run_across_midnight(self):
		minutes, _ = label_run_rules.run_minutes({
			"setup_start": at(23, 50, day=15),
			"first_good_label": at(0, 20, day=16),
		})

		self.assertEqual(minutes["setup_mins"], 30.0)

	def test_seconds_round_to_one_decimal(self):
		minutes, _ = label_run_rules.run_minutes({
			"setup_start": datetime(2026, 9, 15, 8, 0, 0),
			"first_good_label": datetime(2026, 9, 15, 8, 0, 20),
		})

		self.assertEqual(minutes["setup_mins"], 0.3)


class TestRunLogTotals(unittest.TestCase):
	def test_sums_with_empty_values_as_zero(self):
		rows = [
			{"good_labels": 250, "setup_waste_m": 18.5, "setup_mins": 42.0, "run_mins": 13.0},
			{"good_labels": 250, "setup_waste_m": None, "setup_mins": None, "run_mins": 11.5},
			{},
		]

		self.assertEqual(label_run_rules.run_log_totals(rows), {
			"total_good_labels": 500,
			"total_setup_waste_m": 18.5,
			"total_setup_mins": 42.0,
			"total_run_mins": 24.5,
		})

	def test_no_rows(self):
		self.assertEqual(label_run_rules.run_log_totals([]), {
			"total_good_labels": 0,
			"total_setup_waste_m": 0.0,
			"total_setup_mins": 0.0,
			"total_run_mins": 0.0,
		})


class TestRunLogSchema(unittest.TestCase):
	def setUp(self):
		self.child = load("job_card_label_run")
		self.parent = load("job_card_label")
		self.parent_fields = {f["fieldname"]: f for f in self.parent["fields"]}
		self.child_fields = {f["fieldname"]: f for f in self.child["fields"]}

	def test_child_is_a_table_in_this_module(self):
		self.assertEqual(self.child["name"], "Job Card Label Run")
		self.assertEqual(self.child["istable"], 1)
		self.assertEqual(self.child["module"], "Job Card Tracking")

	def test_child_folder_has_all_three_files(self):
		folder = DOCTYPE_DIR / "job_card_label_run"
		for name in ("__init__.py", "job_card_label_run.py", "job_card_label_run.json"):
			self.assertTrue((folder / name).is_file(), name)

	def test_every_child_data_field_is_editable_after_submit(self):
		missing = [
			f["fieldname"] for f in self.child["fields"]
			if f["fieldtype"] not in BREAKS and not f.get("allow_on_submit")
		]
		self.assertEqual(missing, [])

	def test_parent_table_and_rollups_are_editable_after_submit(self):
		for fieldname in ("run_log",) + tuple(total for total, _ in label_run_rules.TOTALS):
			self.assertEqual(self.parent_fields[fieldname].get("allow_on_submit"), 1, fieldname)

		self.assertEqual(self.parent_fields["run_log"]["options"], "Job Card Label Run")

	def test_computed_fields_are_read_only(self):
		for minutes_field, start, end in label_run_rules.SEGMENTS:
			self.assertEqual(self.child_fields[minutes_field].get("read_only"), 1, minutes_field)
			self.assertEqual(self.child_fields[start]["fieldtype"], "Datetime")
			self.assertEqual(self.child_fields[end]["fieldtype"], "Datetime")

		for total, row_field in label_run_rules.TOTALS:
			self.assertEqual(self.parent_fields[total].get("read_only"), 1, total)
			self.assertIn(row_field, self.child_fields)

	def test_child_matches_the_card_it_sits_on(self):
		self.assertEqual(
			self.child_fields["machine"]["options"], self.parent_fields["machine"]["options"]
		)
		self.assertEqual(
			self.child_fields["die"]["options"], self.parent_fields["dies"]["options"]
		)
		self.assertEqual(
			set(filter(None, self.child_fields["plate_status"]["options"].split("\n"))),
			set(filter(None, self.parent_fields["plate_status"]["options"].split("\n"))),
		)

	def test_field_order_matches_fields(self):
		for doc in (self.child, self.parent):
			self.assertEqual(doc["field_order"], [f["fieldname"] for f in doc["fields"]], doc["name"])


if __name__ == "__main__":
	unittest.main()
