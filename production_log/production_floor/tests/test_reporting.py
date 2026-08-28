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
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_log.production_floor.reporting import (  # noqa: E402
	QuantityError,
	format_unit,
	build_report_text,
	build_whatsapp_text,
	exception_summary,
	find_exceptions,
	format_date_long,
	format_date_short,
	short_job_name,
	job_card_is_open,
	job_card_chip,
	is_overdue,
	OPEN_JOB_CARD_STATUSES,
	DEFAULT_DEPARTMENTS,
	JOB_CARD_SOURCES,
	PLANNED_JOB_CARD_STATUS,
	RECEIVED_JOB_CARD_STATUS,
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


class TestShortJobName(unittest.TestCase):
	"""A job card's specification_name repeats the customer name.

	Left alone the chip reads the customer twice and will not fit a phone, so
	the leading customer prefix is stripped for display. Display only - the
	stored job_name is whatever the supervisor confirms.
	"""

	def test_strips_the_customer_prefix(self):
		self.assertEqual(
			short_job_name("CHANDARIA INDUSTRIES LIMITED", "CHANDARIA INDUSTRIES - INVOICE"),
			"INVOICE",
		)

	def test_strips_when_the_customer_matches_in_full(self):
		self.assertEqual(
			short_job_name("GILANI'S DISTRIBUTORS LTD", "GILANI'S DISTRIBUTORS LTD - 9.5 X 8 2 PART"),
			"9.5 X 8 2 PART",
		)

	def test_tolerates_a_double_space_before_the_dash(self):
		self.assertEqual(short_job_name("SUBARU KENYA", "SUBARU KENYA  - INVOICE"), "INVOICE")

	def test_tolerates_a_missing_space_after_the_dash(self):
		self.assertEqual(
			short_job_name("EXCEL CHEMICALS LTD", "EXCEL CHEMICALS LTD -CASH SALE"),
			"CASH SALE",
		)

	def test_leaves_an_unrelated_job_name_alone(self):
		self.assertEqual(
			short_job_name("DELIGHT PRINTERS AND STATIONERS LIMITED", "IMARIKA SACCO"),
			"IMARIKA SACCO",
		)

	def test_never_returns_empty_when_the_job_is_only_the_customer(self):
		self.assertEqual(
			short_job_name("RECON STEEL LIMITED", "RECON STEEL LIMITED"),
			"RECON STEEL LIMITED",
		)

	def test_handles_missing_values(self):
		self.assertEqual(short_job_name("", ""), "")
		self.assertEqual(short_job_name(None, None), "")
		self.assertEqual(short_job_name(None, "INVOICE"), "INVOICE")


class TestOpenJobCardStatuses(unittest.TestCase):
	"""Which Job Card Computer Paper records belong on the chip row."""

	def test_work_not_yet_finished_is_open(self):
		for status in ("Open", "Planned", "In Production", "Packing Pending"):
			self.assertTrue(job_card_is_open(status, 0), status)

	def test_finished_or_abandoned_work_is_not(self):
		for status in ("Completed", "Closed", "On Hold", "Cancelled"):
			self.assertFalse(job_card_is_open(status, 0), status)

	def test_a_cancelled_document_is_never_open(self):
		self.assertFalse(job_card_is_open("In Production", 2))

	def test_an_unknown_status_is_not_open(self):
		self.assertFalse(job_card_is_open("", 0))
		self.assertFalse(job_card_is_open(None, 0))


class TestJobCardChip(unittest.TestCase):
	"""What the phone shows for one job card, and what it fills in."""

	def test_builds_the_two_display_lines_and_the_reference(self):
		chip = job_card_chip(
			"CHANDARIA INDUSTRIES LIMITED",
			"CHANDARIA INDUSTRIES - INVOICE",
			"JC-CPT-2026-00079",
			"2026-09-02",
		)
		self.assertEqual(chip["customer_name"], "CHANDARIA INDUSTRIES LIMITED")
		self.assertEqual(chip["job_name"], "INVOICE")
		self.assertEqual(chip["ref"], "00079")
		self.assertEqual(chip["job_card"], "JC-CPT-2026-00079")

	def test_keeps_the_amended_suffix_in_the_reference(self):
		chip = job_card_chip("V P P SHAH DISTRIBUTORS LIMITED", "VPP SHAH DISTRIBUTORS LTD - MERU",
			"JC-CPT-2026-00075-1", "2026-09-01")
		self.assertEqual(chip["ref"], "00075-1")

	def test_falls_back_to_the_whole_name_when_it_does_not_match_the_series(self):
		chip = job_card_chip("ACME", "ACME - THING", "SOMETHING-ELSE", None)
		self.assertEqual(chip["ref"], "SOMETHING-ELSE")


class ToPlanStripTests(unittest.TestCase):
	"""The To Plan strip is derived from the job card's own status vocabulary.

	These lock the two facts the strip depends on: "received" means Open, and
	planning a job means moving it to Planned. If either drifts, the strip
	either never fills or never drains.
	"""

	def test_received_is_open_and_planned_is_planned(self):
		self.assertEqual(RECEIVED_JOB_CARD_STATUS, "Open")
		self.assertEqual(PLANNED_JOB_CARD_STATUS, "Planned")

	def test_both_are_real_job_card_statuses(self):
		# Open and Planned are both in the open set, so a card cannot fall off
		# the floor's radar just by being planned.
		self.assertIn(RECEIVED_JOB_CARD_STATUS, OPEN_JOB_CARD_STATUSES)
		self.assertIn(PLANNED_JOB_CARD_STATUS, OPEN_JOB_CARD_STATUSES)

	def test_every_source_names_a_known_department(self):
		for source in JOB_CARD_SOURCES:
			self.assertIn(source["department"], DEFAULT_DEPARTMENTS, source["doctype"])

	def test_every_source_declares_the_fields_the_query_needs(self):
		for source in JOB_CARD_SOURCES:
			for key in ("doctype", "department", "customer_field", "instructions_field"):
				self.assertIn(key, source, source.get("doctype"))

	def test_computer_paper_uses_order_comments_not_production_notes(self):
		# production_notes is the floor's own commentary; putting it in the
		# read-only "From the Job Card" box would blur the very line we drew.
		cp = next(s for s in JOB_CARD_SOURCES if s["doctype"] == "Job Card Computer Paper")
		self.assertEqual(cp["instructions_field"], "order_comments")

	def test_carton_customer_field_differs_from_the_others(self):
		by_doctype = {s["doctype"]: s for s in JOB_CARD_SOURCES}
		self.assertEqual(by_doctype["Job Card Carton"]["customer_field"], "customer_name")
		self.assertEqual(by_doctype["Job Card Computer Paper"]["customer_field"], "customer")


class ChipExtrasTests(unittest.TestCase):
	def test_chip_carries_what_the_quick_add_sheet_prefills(self):
		chip = job_card_chip(
			"EXCEL CHEMICALS LTD",
			"EXCEL CHEMICALS LTD - CASH SALE",
			"JC-CPT-2026-00077",
			"2026-09-03",
			doctype="Job Card Computer Paper",
			department="Computer",
			quantity=12,
			instructions="  Deliver Friday AM  ",
			as_of="2026-08-28",
		)
		self.assertEqual(chip["department"], "Computer")
		self.assertEqual(chip["doctype"], "Job Card Computer Paper")
		self.assertEqual(chip["quantity"], 12)
		self.assertEqual(chip["instructions"], "Deliver Friday AM")
		self.assertFalse(chip["overdue"])

	def test_blank_instructions_become_none_not_empty_string(self):
		# So the phone can test truthiness and not render an empty grey box.
		chip = job_card_chip("ACME", "ACME - THING", "JC-CORR-2026-0079", None, instructions="   ")
		self.assertIsNone(chip["instructions"])

	def test_chip_still_works_with_the_original_four_arguments(self):
		chip = job_card_chip("ACME", "ACME - THING", "JC-CORR-2026-0079", "2026-08-29")
		self.assertEqual(chip["ref"], "0079")
		self.assertIsNone(chip["department"])
		self.assertIsNone(chip["instructions"])


class OverdueTests(unittest.TestCase):
	def test_a_due_date_in_the_past_is_overdue(self):
		self.assertTrue(is_overdue("2026-07-10", "2026-08-28"))

	def test_today_is_not_yet_overdue(self):
		self.assertFalse(is_overdue("2026-08-28", "2026-08-28"))

	def test_a_future_due_date_is_not_overdue(self):
		self.assertFalse(is_overdue("2026-09-03", "2026-08-28"))

	def test_no_due_date_is_not_overdue(self):
		# An undated card is unscheduled, not late. Colouring it red would put
		# a permanent row of alarm on the strip that nobody can clear.
		self.assertFalse(is_overdue(None, "2026-08-28"))
		self.assertFalse(is_overdue("", "2026-08-28"))

	def test_an_unparseable_date_is_not_overdue(self):
		self.assertFalse(is_overdue("not a date", "2026-08-28"))

	def test_accepts_a_datetime_string(self):
		self.assertTrue(is_overdue("2026-07-10 00:00:00", "2026-08-28"))

	def test_accepts_real_date_objects(self):
		self.assertTrue(is_overdue(date(2026, 7, 10), date(2026, 8, 28)))


class MonoboxDepartmentTests(unittest.TestCase):
	def test_monobox_is_a_department(self):
		self.assertIn("Monobox", DEFAULT_DEPARTMENTS)

	def test_the_existing_four_keep_their_order(self):
		# Monobox is appended, not inserted: the WhatsApp report's department
		# order is what the floor reads every evening, and reordering it would
		# be a visible change nobody asked for.
		self.assertEqual(DEFAULT_DEPARTMENTS[:4], ["Computer", "Offset", "Carton", "Labels"])

	def test_a_monobox_row_lands_in_its_own_section(self):
		rows = [row(department="Computer"), row(department="Monobox")]
		self.assertEqual(order_departments(rows, DEFAULT_DEPARTMENTS), ["Computer", "Monobox"])


class InstallHookOrderTests(unittest.TestCase):
	"""The one ordering bug that can take the whole site down.

	`seed_machines` inserts against the CURRENT Select options, which live in
	Property Setters that `apply_select_options` writes. Seed first and a
	machine in a newly added department fails `_validate_selects` - and a throw
	inside `after_migrate` aborts the migrate for every app on the bench, not
	just this one. That is exactly what happened on 2026-08-28.

	Parsed rather than imported: install.py and seed.py both import frappe, and
	this suite runs without a bench.
	"""

	@staticmethod
	def _call_order(func_name):
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		source = open(os.path.join(here, "..", "install.py")).read()
		tree = ast.parse(source)
		func = next(
			node for node in tree.body
			if isinstance(node, ast.FunctionDef) and node.name == func_name
		)
		return [
			node.func.id
			for node in ast.walk(func)
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
		]

	def test_after_migrate_widens_the_selects_before_it_seeds(self):
		calls = self._call_order("after_migrate")
		self.assertIn("apply_select_options", calls)
		self.assertIn("seed_machines", calls)
		self.assertLess(
			calls.index("apply_select_options"),
			calls.index("seed_machines"),
			"apply_select_options must run BEFORE seed_machines, or a machine in a "
			"newly added department throws and aborts the migrate for every app",
		)

	def test_after_install_uses_the_same_order(self):
		calls = self._call_order("after_install")
		self.assertLess(
			calls.index("apply_select_options"), calls.index("seed_machines")
		)


class SeedDataTests(unittest.TestCase):
	def test_every_seeded_machine_is_in_a_known_department(self):
		"""A machine seeded into a department that does not exist cannot insert.

		Same failure as above, reached a different way - so it is worth its own
		check rather than relying on the ordering test.
		"""
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		source = open(os.path.join(here, "..", "setup", "seed.py")).read()
		tree = ast.parse(source)
		machines = next(
			node.value
			for node in tree.body
			if isinstance(node, ast.Assign)
			and any(getattr(t, "id", None) == "MACHINES" for t in node.targets)
		)
		departments = [row.elts[1].value for row in machines.elts]
		self.assertTrue(departments)
		for department in departments:
			self.assertIn(department, DEFAULT_DEPARTMENTS, department)

	def test_monobox_stages_are_seeded(self):
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		source = open(os.path.join(here, "..", "setup", "seed.py")).read()
		tree = ast.parse(source)
		machines = next(
			node.value
			for node in tree.body
			if isinstance(node, ast.Assign)
			and any(getattr(t, "id", None) == "MACHINES" for t in node.targets)
		)
		monobox = [r.elts[0].value for r in machines.elts if r.elts[1].value == "Monobox"]
		self.assertEqual(len(monobox), 6, monobox)
		# Spelled out in full so they do not collide with the Carton processes,
		# which already own the names "Die Cutting" and "Bundling".
		carton = [r.elts[0].value for r in machines.elts if r.elts[1].value == "Carton"]
		self.assertFalse(set(monobox) & set(carton))

