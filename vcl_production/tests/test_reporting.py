"""Tests for the report text and the exception rules.

These run on plain Python - no bench, no site, no database - because the
wording of the WhatsApp message and the definition of "missing information"
are the two things most likely to be argued about, and they should be
arguable against a test rather than against a live site.

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vcl_production.reporting import (  # noqa: E402
	QuantityError,
	format_unit,
	build_report_text,
	build_whatsapp_text,
	exception_summary,
	find_exceptions,
	format_date_long,
	format_date_short,
	format_qty,
	job_title,
	normalise_key,
	order_departments,
	parse_quantity,
	summarise,
)


def row(**overrides):
	base = {
		"department": "Computer",
		"machine": "M1",
		"customer_name": "Chandaria",
		"job_name": "Yellow Copy",
		"planned_quantity": 3,
		"actual_quantity": 1,
		"uom": "reels",
		"status": "Running",
		"reason": "",
		"notes": "",
	}
	base.update(overrides)
	return base


# The shift described in the brief, as it would have come off WhatsApp.
SHIFT = [
	row(machine="M1", customer_name="Chandaria", job_name="Yellow Copy",
		planned_quantity=3, actual_quantity=1, uom="reels", status="Running"),
	row(machine="M3", customer_name="KCB", job_name="Computer Paper",
		planned_quantity=3, actual_quantity=0.5, uom="reels", status="Carried Forward",
		reason="Reel change took the afternoon"),
	row(machine="M4", customer_name="NHIF", job_name="3-Part Payslip",
		planned_quantity=2, actual_quantity=0, uom="reels", status="Running"),
	row(machine="Collator", customer_name="Chandaria", job_name="Yellow Copy",
		planned_quantity=12, actual_quantity=9, uom="cartons", status="Running"),
	row(department="Offset", machine="Solna", customer_name="Prince", job_name="3 Quire",
		planned_quantity=2000, actual_quantity=2000, uom="pcs", status="Completed"),
	row(department="Offset", machine="Miller", customer_name="Prince", job_name="1 Quire",
		planned_quantity=1500, actual_quantity=1500, uom="pcs", status="Completed"),
	row(department="Carton", machine="Stitching", customer_name="E.W.A.L", job_name="Carton",
		planned_quantity=1000, actual_quantity=1031, uom="pcs", status="Completed"),
	row(department="Carton", machine="Bundling", customer_name="E.W.A.L", job_name="Carton",
		planned_quantity=1000, actual_quantity=47, uom="pcs", status="Carried Forward",
		reason="Board ran out at 3pm"),
]

DAY = {"production_date": "2026-08-26", "status": "Open", "notes": "", "items": SHIFT}


class TestFormatting(unittest.TestCase):
	def test_dates(self):
		self.assertEqual(format_date_long("2026-08-26"), "26 AUGUST 2026")
		self.assertEqual(format_date_short("2026-08-26"), "26 Aug 2026")

	def test_quantities_read_the_way_the_floor_writes_them(self):
		self.assertEqual(format_qty(1), "1")
		self.assertEqual(format_qty(0.5), "0.5")
		self.assertEqual(format_qty(1031), "1031")
		self.assertEqual(format_qty(2.250), "2.25")
		self.assertEqual(format_qty(None), "")

	def test_units_go_singular_at_exactly_one(self):
		self.assertEqual(format_unit(1, "reels"), "reel")
		self.assertEqual(format_unit(3, "reels"), "reels")
		self.assertEqual(format_unit(0.5, "reels"), "reels")
		self.assertEqual(format_unit(1, "cartons"), "carton")
		# Abbreviations are left alone - "1 pc" and "1 kgs" are both wrong.
		self.assertEqual(format_unit(1, "pcs"), "pcs")
		self.assertEqual(format_unit(1, "kg"), "kg")

	def test_job_title_does_not_repeat_the_customer(self):
		self.assertEqual(job_title({"customer_name": "Chandaria", "job_name": "Yellow Copy"}),
			"Chandaria Yellow Copy")
		self.assertEqual(job_title({"customer_name": "E.W.A.L", "job_name": "E.W.A.L"}), "E.W.A.L")
		self.assertEqual(job_title({"customer_name": "KCB", "job_name": ""}), "KCB")


class TestQuantityInput(unittest.TestCase):
	def test_decimals_are_accepted(self):
		self.assertEqual(parse_quantity("0.5"), 0.5)
		self.assertEqual(parse_quantity("1031"), 1031.0)
		self.assertEqual(parse_quantity(9), 9.0)

	def test_blank_stays_blank_rather_than_becoming_zero(self):
		self.assertIsNone(parse_quantity(""))
		self.assertIsNone(parse_quantity(None))
		self.assertIsNone(parse_quantity("   "))

	def test_arithmetic_is_refused(self):
		for bad in ("41+6", "1 reel", "3-1", "9 ctns", "two"):
			with self.assertRaises(QuantityError):
				parse_quantity(bad)

	def test_negative_is_refused(self):
		with self.assertRaises(QuantityError):
			parse_quantity("-4")


class TestRememberedJobDedupe(unittest.TestCase):
	def test_punctuation_and_case_collapse(self):
		self.assertEqual(normalise_key("E.W.A.L", "Carton"), normalise_key("ewal", "carton"))
		self.assertEqual(normalise_key("Chandaria", "Yellow Copy"),
			normalise_key(" chandaria ", "yellowcopy"))

	def test_different_jobs_stay_different(self):
		self.assertNotEqual(normalise_key("Prince", "1 Quire"), normalise_key("Prince", "3 Quire"))


class TestSummary(unittest.TestCase):
	def test_counts(self):
		summary = summarise(SHIFT)
		self.assertEqual(summary["Running"], 3)
		self.assertEqual(summary["Completed"], 3)
		self.assertEqual(summary["Carried Forward"], 2)
		self.assertEqual(summary["Total"], 8)

	def test_departments_keep_the_configured_order(self):
		self.assertEqual(order_departments(SHIFT), ["Computer", "Offset", "Carton"])

	def test_unknown_department_still_appears(self):
		rows = SHIFT + [row(department="Guillotine", machine="G1")]
		self.assertEqual(order_departments(rows), ["Computer", "Offset", "Carton", "Guillotine"])


class TestExceptions(unittest.TestCase):
	def test_carried_forward_without_reason_is_critical(self):
		found = find_exceptions([row(status="Carried Forward", reason="")])
		codes = {e["code"]: e["severity"] for e in found}
		self.assertEqual(codes["carried_forward_no_reason"], "critical")

	def test_paused_without_reason_is_critical(self):
		found = find_exceptions([row(status="Paused", reason="")])
		self.assertIn("paused_no_reason", {e["code"] for e in found})

	def test_completed_without_actual_is_critical(self):
		found = find_exceptions([row(status="Completed", actual_quantity=0)])
		codes = {e["code"]: e["severity"] for e in found}
		self.assertEqual(codes["completed_no_actual"], "critical")

	def test_still_planned_and_never_started_are_warnings(self):
		found = find_exceptions([row(status="Planned"), row(status="Not Started")])
		self.assertEqual({e["severity"] for e in found}, {"warning"})
		self.assertEqual({e["code"] for e in found}, {"planned_no_update", "not_started"})

	def test_running_with_no_actual_is_a_warning_not_a_block(self):
		found = find_exceptions([row(status="Running", actual_quantity=0)])
		self.assertEqual([e["severity"] for e in found], ["warning"])

	def test_a_complete_shift_has_nothing_critical(self):
		self.assertEqual(exception_summary(SHIFT)["critical"], [])

	def test_the_reference_shift_flags_only_the_one_real_gap(self):
		# Both carry-forwards have a reason and a quantity, so the only thing
		# the day is missing is M4: running since morning with nothing
		# produced against it. Worth a nudge, not worth blocking the day.
		summary = exception_summary(SHIFT)
		self.assertEqual(summary["critical_count"], 0)
		self.assertEqual([e["code"] for e in summary["warnings"]], ["running_no_actual"])
		self.assertEqual(summary["warnings"][0]["machine"], "M4")


class TestReportText(unittest.TestCase):
	def test_full_report_shape(self):
		text = build_report_text(DAY)
		self.assertIn("VCL PRODUCTION REPORT", text)
		self.assertIn("26 AUGUST 2026", text)
		self.assertIn("COMPUTER", text)
		self.assertIn("M1 - Chandaria Yellow Copy", text)
		self.assertIn("Plan: 3 reels", text)
		self.assertIn("Actual: 1 reel", text)
		self.assertIn("Actual: 1031 pcs", text)
		self.assertIn("Status: Running", text)
		self.assertIn("Stitching - E.W.A.L Carton", text)
		# Departments in configured order, not alphabetical.
		self.assertLess(text.index("COMPUTER"), text.index("OFFSET"))
		self.assertLess(text.index("OFFSET"), text.index("CARTON"))

	def test_full_report_carries_reasons_and_attention(self):
		text = build_report_text(DAY)
		self.assertIn("Reason: Board ran out at 3pm", text)
		self.assertIn("ATTENTION REQUIRED", text)

	def test_empty_day_says_so(self):
		text = build_report_text({"production_date": "2026-08-26", "items": []})
		self.assertIn("No production entered", text)

	def test_whatsapp_shape(self):
		text = build_whatsapp_text(DAY)
		lines = text.splitlines()
		self.assertEqual(lines[0], "*VCL Production Report - 26 Aug 2026*")
		self.assertIn("*COMPUTER*", text)
		self.assertIn("M1 - Chandaria Yellow Copy", text)
		self.assertIn("1 / 3 reels - Running", text)
		self.assertIn("1031 / 1000 pcs - Completed", text)
		self.assertIn("47 / 1000 pcs - Carried Forward", text)
		self.assertIn("*CARRIED FORWARD*", text)
		self.assertIn("2 jobs", text)
		self.assertIn("*ATTENTION REQUIRED*", text)

	def test_whatsapp_singular_wording(self):
		text = build_whatsapp_text({
			"production_date": "2026-08-26",
			"items": [row(status="Running", actual_quantity=0)],
		})
		self.assertIn("1 job requires an update", text)

	def test_neither_report_doubles_up_blank_lines(self):
		# A department break is one blank line. Two reads as a hole in the
		# middle of the WhatsApp message.
		for text in (build_whatsapp_text(DAY), build_report_text(DAY)):
			self.assertFalse(text.endswith("\n"))
			self.assertNotIn("\n\n\n", text)

	def test_day_notes_reach_both_reports(self):
		day = dict(DAY, notes="Power cut 11:00-12:30")
		self.assertIn("Power cut 11:00-12:30", build_report_text(day))
		self.assertIn("Power cut 11:00-12:30", build_whatsapp_text(day))


if __name__ == "__main__":
	unittest.main()
