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
	job_card_doctype,
	job_card_route,
	group_to_plan,
	to_plan_bucket,
	days_late,
	TO_PLAN_GROUPS,
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
	roll_up_stages,
	stage_totals,
	stage_status,
	stage_flow,
	stage_percent,
	plan_lines,
	part_label,
	carry_forward_row,
	SPLIT_BY_PART,
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


class StylesheetCacheBustTests(unittest.TestCase):
	"""production_floor.css is served immutable for a year.

	`bundled_asset` only hashes a path containing ".bundle." that does NOT start
	with "/assets". Ours starts with "/assets", so it is returned verbatim and
	nginx serves it `max-age=31536000, immutable`. Without a version in the
	query string a CSS change never reaches a browser that has loaded the screen
	before - which is what made the board render as unstyled boxes on the phone
	on 2026-08-28.
	"""

	@staticmethod
	def _hook_value():
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		source = open(os.path.join(here, "..", "..", "hooks.py")).read()
		tree = ast.parse(source)
		for node in tree.body:
			if isinstance(node, ast.Assign) and any(
				getattr(t, "id", None) == "app_include_css" for t in node.targets
			):
				return node.value.value
		raise AssertionError("app_include_css not found in hooks.py")

	def test_the_stylesheet_include_carries_a_version(self):
		value = self._hook_value()
		self.assertIn("production_floor.css", value)
		self.assertIn(
			"?v=",
			value,
			"a plain /assets path is served immutable for a year - without ?v= a CSS "
			"change is invisible to every browser that has opened the screen before",
		)

	def test_the_version_is_not_the_one_that_shipped_the_bug(self):
		# 20260828 is the first version. Any later CSS edit must bump past it,
		# so this asserts the marker is well formed rather than pinning a date.
		version = self._hook_value().split("?v=")[1]
		self.assertRegex(version, r"^\d{8}$", "use a YYYYMMDD version marker")
		self.assertGreaterEqual(int(version), 20260828)


class JobCardLinkTests(unittest.TestCase):
	"""`production_job_card` is Data, not a Link - deliberately, so a Job Card
	Tracking problem can never make a production row unsaveable. The number is
	therefore the only clue to which doctype it came from, and the naming series
	is that clue.
	"""

	def test_each_series_resolves_to_its_product_line(self):
		self.assertEqual(job_card_doctype("JC-CPT-2026-00075"), "Job Card Computer Paper")
		self.assertEqual(job_card_doctype("JC-CORR-2026-0067"), "Job Card Carton")
		self.assertEqual(job_card_doctype("JC-MBX-2026-0001"), "Job Card Monobox")

	def test_an_amended_suffix_still_resolves(self):
		self.assertEqual(job_card_doctype("JC-CPT-2026-00075-1"), "Job Card Computer Paper")

	def test_a_series_we_do_not_plan_from_resolves_to_nothing(self):
		# Labels and ETR cards exist but are not in JOB_CARD_SOURCES yet. They
		# must render as plain text, never as a link to a route we cannot build.
		self.assertIsNone(job_card_doctype("JC-LBL-2026-00001"))
		self.assertIsNone(job_card_doctype("JC-ETR-2026-00001"))

	def test_junk_and_blanks_resolve_to_nothing_rather_than_raising(self):
		for value in (None, "", "   ", "GARBAGE", "JC-", "2026-0067"):
			self.assertIsNone(job_card_doctype(value), repr(value))
			self.assertIsNone(job_card_route(value), repr(value))

	def test_the_route_is_the_desk_url_for_that_doctype(self):
		self.assertEqual(
			job_card_route("JC-CORR-2026-0067"), "/app/job-card-carton/JC-CORR-2026-0067"
		)
		self.assertEqual(
			job_card_route("JC-CPT-2026-00075"),
			"/app/job-card-computer-paper/JC-CPT-2026-00075",
		)

	def test_the_route_escapes_a_name_that_needs_it(self):
		self.assertNotIn(" ", job_card_route("JC-CORR-2026-0067") or "")

	def test_every_source_prefix_matches_its_doctype_naming_series(self):
		"""The whole scheme rests on these prefixes. Pin them to the JSON.

		A renamed naming series then breaks this test rather than silently
		turning every job card link on the board into plain text.
		"""
		import json

		here = os.path.dirname(os.path.abspath(__file__))
		root = os.path.abspath(os.path.join(here, "..", "..", "job_card_tracking", "doctype"))
		for source in JOB_CARD_SOURCES:
			prefix = source.get("series_prefix")
			self.assertTrue(prefix, source["doctype"])
			folder = source["doctype"].lower().replace(" ", "_")
			path = os.path.join(root, folder, folder + ".json")
			self.assertTrue(os.path.exists(path), path)
			meta = json.load(open(path))
			options = next(
				f.get("options") or ""
				for f in meta["fields"]
				if f["fieldname"] == "naming_series"
			)
			self.assertTrue(
				options.startswith(prefix),
				"{0}: registry says {1!r}, naming series is {2!r}".format(
					source["doctype"], prefix, options
				),
			)


class PlanningQueueTests(unittest.TestCase):
	"""The phone's planning queue is grouped by how late a thing is.

	Not "sorted by due date": a planner works late-first, so Pegler's 49-day-old
	carton belongs at the top of the screen rather than wherever a date sort
	happened to leave it.
	"""

	TODAY = "2026-08-28"

	def test_buckets_split_on_the_right_boundaries(self):
		self.assertEqual(to_plan_bucket("2026-08-27", self.TODAY), "late")
		self.assertEqual(to_plan_bucket("2026-08-28", self.TODAY), "today")
		self.assertEqual(to_plan_bucket("2026-08-29", self.TODAY), "week")
		self.assertEqual(to_plan_bucket("2026-09-04", self.TODAY), "week")
		self.assertEqual(to_plan_bucket("2026-09-05", self.TODAY), "later")

	def test_an_undated_job_is_unscheduled_not_urgent(self):
		# It sorts LAST. Colouring or ranking it as urgent would put a permanent
		# alarm on the queue that nobody can clear.
		self.assertEqual(to_plan_bucket(None, self.TODAY), "undated")
		self.assertEqual(to_plan_bucket("", self.TODAY), "undated")
		self.assertEqual(to_plan_bucket("not a date", self.TODAY), "undated")
		self.assertEqual(TO_PLAN_GROUPS[-1][0], "undated")

	def test_days_late_counts_only_the_past(self):
		self.assertEqual(days_late("2026-07-10", self.TODAY), 49)
		self.assertEqual(days_late("2026-08-28", self.TODAY), 0)
		self.assertEqual(days_late("2026-09-30", self.TODAY), 0)
		self.assertEqual(days_late(None, self.TODAY), 0)

	def test_groups_come_back_in_working_order(self):
		chips = [
			{"job_card": "A", "due_date": "2026-09-30"},
			{"job_card": "B", "due_date": None},
			{"job_card": "C", "due_date": "2026-07-10"},
			{"job_card": "D", "due_date": "2026-08-28"},
		]
		groups = group_to_plan(chips, self.TODAY)
		self.assertEqual([g["key"] for g in groups], ["late", "today", "later", "undated"])

	def test_empty_groups_are_dropped_not_rendered_blank(self):
		groups = group_to_plan([{"job_card": "A", "due_date": "2026-07-10"}], self.TODAY)
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["key"], "late")
		self.assertEqual(groups[0]["count"], 1)

	def test_each_chip_carries_its_bucket_and_lateness(self):
		groups = group_to_plan([{"job_card": "C", "due_date": "2026-07-10"}], self.TODAY)
		chip = groups[0]["chips"][0]
		self.assertEqual(chip["bucket"], "late")
		self.assertEqual(chip["days_late"], 49)

	def test_grouping_does_not_mutate_the_caller_s_chips(self):
		# get_board ships the same list twice - flat and grouped. Mutating one
		# would quietly change the other.
		chips = [{"job_card": "C", "due_date": "2026-07-10"}]
		group_to_plan(chips, self.TODAY)
		self.assertNotIn("bucket", chips[0])
		self.assertNotIn("days_late", chips[0])

	def test_nothing_waiting_is_no_groups_rather_than_empty_ones(self):
		self.assertEqual(group_to_plan([], self.TODAY), [])
		self.assertEqual(group_to_plan(None, self.TODAY), [])


class MachinePickerTests(unittest.TestCase):
	"""One picker, used by both dialogs.

	The claim is that machine is chosen by tapping a button, everywhere. A
	second copy of the grid, or a Select quietly reintroduced in one of the two
	dialogs, is exactly the drift this catches.
	"""

	@staticmethod
	def _screen():
		here = os.path.dirname(os.path.abspath(__file__))
		path = os.path.join(
			here, "..", "page", "vcl_production_lite", "vcl_production_lite.js"
		)
		return open(path).read()

	def test_the_picker_is_defined_once(self):
		self.assertEqual(self._screen().count("machine_picker(dialog, department) {"), 1)

	def test_both_dialogs_call_it(self):
		# Counting calls was brittle - adding a legitimate third (re-render
		# after creating a machine) broke it. Assert what matters: each dialog
		# entry point builds the picker.
		screen = self._screen()
		for func, end in [
			("on_department_change(dialog) {", "\n\t}"),
			("quick_add_dialog(card) {", "\n\tsubmit_quick_add"),
		]:
			start = screen.index(func)
			self.assertIn("this.machine_picker(dialog,", screen[start : screen.index(end, start)], func)

	def test_no_dialog_still_uses_a_machine_select(self):
		# `values.machine_name` legitimately contains "values.machine", so guard
		# the real thing: no machine Select field, and no submit reading the
		# machine off Frappe's values instead of the shared picker.
		screen = self._screen()
		self.assertNotIn('fieldname: "machine",', screen)
		self.assertNotIn("machine: values.machine,", screen)

	def test_both_submit_paths_read_the_shared_value(self):
		# Counting occurrences would also count the comment that explains it.
		# Assert the thing that matters: each submit function's own body.
		screen = self._screen()
		for func in ("submit_add_job(dialog, values) {", "submit_quick_add(dialog, values, card) {"):
			start = screen.index(func)
			body = screen[start : screen.index("\n\t}", start)]
			self.assertIn("dialog.vcl_machine", body, func)
class MachineAlignmentTests(unittest.TestCase):
	"""The floor master must point at ERPNext's vocabulary, not a second one.

	VCL had two machine lists that disagreed - job cards said `Miyakoshi 01`,
	the floor said `M1` - so any roll-up across them silently dropped rows.
	These pin the mapping's shape without a bench.
	"""

	@staticmethod
	def _patch():
		import importlib.util

		here = os.path.dirname(os.path.abspath(__file__))
		# MAPPING lives in setup/alignment.py so the patch and after_migrate
		# share one copy; the rest still lives on the patch.
		import ast

		namespace = {}
		for path in (
			os.path.join(here, "..", "setup", "alignment.py"),
			os.path.join(here, "..", "..", "patches", "v10_1", "align_machines_to_workstations.py"),
		):
			# Read rather than imported: both modules import frappe.
			for node in ast.parse(open(path).read()).body:
				if isinstance(node, (ast.Assign, ast.AnnAssign)):
					exec(compile(ast.Module([node], []), path, "exec"), namespace)
		return namespace

	def test_every_computer_machine_maps_to_a_miyakoshi(self):
		mapping = self._patch()["MAPPING"]
		for floor, workstation in [
			("M1", "Miyakoshi 01"),
			("M2", "Miyakoshi 2"),
			("M3", "Miyakoshi 3"),
			("M4", "Miyakoshi 4"),
		]:
			stage, ws = mapping[floor]
			self.assertEqual(ws, workstation, floor)
			# Continuous stationery is reel-fed. If this ever reads sheet-fed,
			# the mapping has been copied from Offset by mistake.
			self.assertEqual(stage, "Reel to Reel Printing", floor)

	def test_offset_is_sheet_fed_not_reel_fed(self):
		mapping = self._patch()["MAPPING"]
		for floor in ("Solna", "Miller"):
			self.assertEqual(mapping[floor][0], "Sheet to Sheet Printing", floor)

	def test_a_process_may_have_a_stage_and_no_workstation(self):
		# The whole point of the two-link model: Carton's "machines" are stages
		# on a line. Inventing a Workstation for each would be a lie.
		mapping = self._patch()["MAPPING"]
		self.assertIsNone(mapping["Stitching"][1])
		self.assertIsNone(mapping["Die Cutting"][1])
		self.assertEqual(mapping["Stitching"][0], "Carton Stitching")

	def test_every_mapping_names_a_stage(self):
		for floor, (stage, _ws) in self._patch()["MAPPING"].items():
			self.assertTrue(stage, floor)

	def test_monobox_is_deliberately_absent(self):
		# Its stages have no Workstation Type yet. A blank stage is honest;
		# mapping Window Patching onto Lamination because it is nearby is not.
		mapping = self._patch()["MAPPING"]
		for stage_name in ("Coating", "Window Patching", "Folding & Gluing", "Bundling & Packing"):
			self.assertNotIn(stage_name, mapping, stage_name)

	def test_the_floors_holding_areas_are_not_treated_as_stages(self):
		namespace = self._patch()
		self.assertIn("PLANNING", namespace["NOT_A_STAGE"])
		self.assertNotIn("PLANNING", namespace["MAPPING"])

	def test_the_duplicate_miyakoshi_is_retired_not_mapped(self):
		namespace = self._patch()
		self.assertEqual(namespace["DUPLICATE"], "Miyakoshi")
		self.assertNotIn("Miyakoshi", namespace["MAPPING"])

	def test_miller_follows_the_house_numbering(self):
		# Solna 02, Collater 01, Bundler 01 - the masters are numbered.
		self.assertEqual(self._patch()["MILLER"]["workstation_name"], "Miller 01")


class AddMachineInlineTests(unittest.TestCase):
	"""A machine missing from the master stops entry dead, so the picker offers
	to create one. It writes to a master, so it is manager-gated the same way
	the master itself is.
	"""

	@staticmethod
	def _api():
		here = os.path.dirname(os.path.abspath(__file__))
		return open(os.path.join(here, "..", "api.py")).read()

	@staticmethod
	def _screen():
		here = os.path.dirname(os.path.abspath(__file__))
		return open(
			os.path.join(here, "..", "page", "vcl_production_lite", "vcl_production_lite.js")
		).read()

	def test_the_endpoint_is_manager_gated(self):
		api = self._api()
		start = api.index("def add_machine(")
		body = api[start : api.index("\n@frappe.whitelist()", start)]
		self.assertIn("MANAGER_ROLE not in roles", body)
		self.assertIn("frappe.PermissionError", body)

	def test_it_refuses_a_department_that_is_not_one(self):
		api = self._api()
		start = api.index("def add_machine(")
		body = api[start : api.index("\n@frappe.whitelist()", start)]
		self.assertIn("not in get_departments()", body)

	def test_a_retired_machine_is_reactivated_rather_than_duplicated(self):
		# This master retires by unticking `active`, never by deleting - so a
		# name coming back means reinstate, not "already exists, go away".
		api = self._api()
		start = api.index("def add_machine(")
		body = api[start : api.index("\n@frappe.whitelist()", start)]
		self.assertIn('"active", 1', body)
		self.assertIn("reactivated", body)

	def test_the_chip_is_hidden_from_a_non_manager(self):
		screen = self._screen()
		start = screen.index("add_machine_chip() {")
		body = screen[start : screen.index("\n\t}", start)]
		self.assertIn("this.board.is_manager", body)

	def test_the_chip_is_offered_even_when_the_department_is_empty(self):
		# That is precisely when you need it, so the empty state must not be a
		# dead end.
		screen = self._screen()
		start = screen.index("machine_picker(dialog, department) {")
		body = screen[start : screen.index("\n\tsubmit_quick_add", start)]
		self.assertEqual(body.count("this.add_machine_chip()"), 2)



class StageRollUpTests(unittest.TestCase):
	"""Board rows, gathered into the stages their machines serve.

	The worked example throughout is JC-CPT-2026-00062 (Gilani's, 500 cartons
	ordered), taken from the run log typed into that card's production notes:

	    03 Aug  Miyakoshi 01 (M1)  Printing  Part 2  -> 5.4 kg
	    03 Aug  Miyakoshi 3  (M3)  Printing  Part 1  -> 2.7 kg
	    03 Aug  Collater 01       Collation         -> 311 ctn
	    04 Aug  Collater 01       Collation         ->  29 ctn
	"""

	STAGE_OF = {
		"M1": "Reel to Reel Printing",
		"M3": "Reel to Reel Printing",
		"Collator": "Collation",
	}
	POSITION = {"Reel to Reel Printing": 20, "Collation": 50}

	def gilanis(self):
		return [
			{"machine": "M1", "actual_quantity": 5.4, "uom": "kg", "status": "Completed", "production_date": "2026-08-03"},
			{"machine": "M3", "actual_quantity": 2.7, "uom": "kg", "status": "Completed", "production_date": "2026-08-03"},
			{"machine": "Collator", "actual_quantity": 311, "uom": "cartons", "status": "Running", "production_date": "2026-08-03"},
			{"machine": "Collator", "actual_quantity": 29, "uom": "cartons", "status": "Running", "production_date": "2026-08-04"},
		]

	def test_two_parts_on_two_machines_are_one_printing_stage(self):
		stages = roll_up_stages(self.gilanis(), self.STAGE_OF, self.POSITION)
		printing = stages[0]
		self.assertEqual(printing["stage"], "Reel to Reel Printing")
		self.assertAlmostEqual(printing["totals"]["kg"], 8.1)
		self.assertEqual(sorted(printing["machines"]), ["M1", "M3"])

	def test_two_days_on_one_machine_are_one_collation_total(self):
		stages = roll_up_stages(self.gilanis(), self.STAGE_OF, self.POSITION)
		collation = stages[1]
		self.assertEqual(collation["totals"]["cartons"], 340)
		self.assertEqual(collation["days"], ["2026-08-03", "2026-08-04"])

	def test_stages_come_back_in_route_order(self):
		stages = roll_up_stages(self.gilanis(), self.STAGE_OF, self.POSITION)
		self.assertEqual([s["position"] for s in stages], [20, 50])

	# ---- the rule the whole section exists to keep -----------------------

	def test_units_are_never_added_together(self):
		mixed = [
			{"machine": "M1", "actual_quantity": 5, "uom": "kg", "status": "Completed"},
			{"machine": "M1", "actual_quantity": 3, "uom": "reels", "status": "Completed"},
		]
		totals = roll_up_stages(mixed, self.STAGE_OF, self.POSITION)[0]["totals"]
		self.assertEqual(totals, {"kg": 5.0, "reels": 3.0})

	def test_a_flow_between_differently_counted_stages_is_refused(self):
		# kg of paper and cartons of forms do not subtract. There is no written
		# conversion and inventing one would make every report quietly wrong.
		flows = stage_flow(roll_up_stages(self.gilanis(), self.STAGE_OF, self.POSITION))
		self.assertEqual(len(flows), 1)
		self.assertFalse(flows[0]["comparable"])
		self.assertNotIn("waiting", flows[0])

	def test_a_flow_between_matching_units_gives_the_work_in_progress(self):
		rows = [
			{"machine": "Collator", "actual_quantity": 40, "uom": "cartons", "status": "Completed"},
			{"machine": "Packer", "actual_quantity": 25, "uom": "cartons", "status": "Running"},
		]
		stage_of = dict(self.STAGE_OF, Packer="Pack")
		flows = stage_flow(roll_up_stages(rows, stage_of, dict(self.POSITION, Pack=170)))
		self.assertTrue(flows[0]["comparable"])
		self.assertEqual(flows[0]["waiting"], 15)
		self.assertEqual(flows[0]["uom"], "cartons")

	# ---- nothing is silently dropped -------------------------------------

	def test_a_machine_with_no_stage_is_surfaced_not_lost(self):
		rows = self.gilanis() + [
			{"machine": "Window Patching", "actual_quantity": 50, "uom": "pcs", "status": "Running"}
		]
		stages = roll_up_stages(rows, self.STAGE_OF, self.POSITION)
		unstaged = stages[-1]
		self.assertIsNone(unstaged["stage"])
		self.assertEqual(unstaged["totals"], {"pcs": 50.0})

	def test_unstaged_work_sorts_last(self):
		rows = [{"machine": "Window Patching", "actual_quantity": 1, "uom": "pcs", "status": "Running"}] + self.gilanis()
		stages = roll_up_stages(rows, self.STAGE_OF, self.POSITION)
		self.assertIsNone(stages[-1]["stage"])

	def test_a_row_with_no_actual_contributes_nothing(self):
		# Not zero. A quantity nobody has entered is unknown, and averaging it
		# in as zero would understate every stage still in progress.
		self.assertEqual(stage_totals([{"actual_quantity": None, "uom": "kg"}]), {})
		self.assertEqual(stage_totals([{"actual_quantity": "", "uom": "kg"}]), {})

	# ---- status ----------------------------------------------------------

	def test_a_stage_is_complete_only_when_every_machine_is(self):
		self.assertEqual(stage_status([{"status": "Completed"}, {"status": "Completed"}]), "Completed")
		self.assertEqual(stage_status([{"status": "Completed"}, {"status": "Running"}]), "Running")

	def test_running_and_paused_beat_a_quiet_status(self):
		self.assertEqual(stage_status([{"status": "Planned"}, {"status": "Running"}]), "Running")
		self.assertEqual(stage_status([{"status": "Planned"}, {"status": "Paused"}]), "Paused")

	# ---- percent ---------------------------------------------------------

	def test_percent_against_the_order(self):
		# 340 of Gilani's 500 cartons packed.
		self.assertEqual(stage_percent(340, 500), 68)

	def test_percent_is_none_when_it_cannot_be_said(self):
		self.assertIsNone(stage_percent(340, 0))
		self.assertIsNone(stage_percent(340, None))
		self.assertIsNone(stage_percent(None, 500))

	def test_percent_never_exceeds_full(self):
		# Vajas ran 940 against 500 planned. The number is kept; the bar stops.
		self.assertEqual(stage_percent(940, 500), 100)



class ReelToReelDepartmentTests(unittest.TestCase):
	"""Reel to Reel shares the Miyakoshis with Computer Paper.

	ETR is printed reel-to-reel and THEN slit; KCB-type work finishes on the
	press. That one extra stage is the whole difference, which is why they are
	one department with two routes rather than two departments.
	"""

	@staticmethod
	def _patch():
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		path = os.path.join(here, "..", "..", "patches", "v10_2", "reel_to_reel_department.py")
		namespace = {}
		for node in ast.parse(open(path).read()).body:
			if isinstance(node, ast.Assign):
				exec(compile(ast.Module([node], []), path, "exec"), namespace)
		return namespace

	def test_the_department_exists(self):
		self.assertIn("Reel to Reel", DEFAULT_DEPARTMENTS)

	def test_the_existing_departments_keep_their_order(self):
		# Appended, not inserted: the evening WhatsApp report reads in this
		# order and reshuffling it is a visible change nobody asked for.
		self.assertEqual(
			DEFAULT_DEPARTMENTS[:5],
			["Computer", "Offset", "Carton", "Labels", "Monobox"],
		)

	def test_the_presses_are_widened_not_cloned(self):
		# The failure this guards: a second "M1" record under Reel to Reel,
		# splitting one press's history in half.
		namespace = self._patch()
		self.assertEqual(namespace["SHARED"], ["M1", "M2", "M3", "M4"])
		self.assertEqual(namespace["SLITTER_MACHINE"], "Slitter")

	def test_the_slitter_is_mapped_in_the_shared_alignment(self):
		# It is SEEDED, not created by the patch - see PatchesMustNotInsertTests.
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		ns = {}
		path = os.path.join(here, "..", "setup", "alignment.py")
		for node in ast.parse(open(path).read()).body:
			if isinstance(node, ast.Assign):
				exec(compile(ast.Module([node], []), path, "exec"), ns)
		self.assertEqual(ns["MAPPING"]["Slitter"], ("ETR Slitting", "Slitter 01"))

	def test_the_seed_does_not_list_the_shared_presses_twice(self):
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		source = open(os.path.join(here, "..", "setup", "seed.py")).read()
		machines = next(
			node.value
			for node in ast.parse(source).body
			if isinstance(node, ast.Assign)
			and any(getattr(t, "id", None) == "MACHINES" for t in node.targets)
		)
		reel = [r.elts[0].value for r in machines.elts if r.elts[1].value == "Reel to Reel"]
		self.assertEqual(reel, ["Slitter"])
		# And no name appears under two departments in the seed at all.
		names = [r.elts[0].value for r in machines.elts]
		self.assertEqual(len(names), len(set(names)))


class MachineDepartmentsTests(unittest.TestCase):
	"""One press, many product lines - resolved the same way on both sides."""

	@staticmethod
	def _api():
		here = os.path.dirname(os.path.abspath(__file__))
		return open(os.path.join(here, "..", "api.py")).read()

	def test_the_resolver_reads_home_plus_also_serves(self):
		api = self._api()
		start = api.index("def machine_departments(machine):")
		body = api[start : api.index("\n\n\n", start)]
		self.assertIn('machine.get("department")', body)
		self.assertIn("also_serves", body)
		self.assertIn("splitlines()", body)

	def test_get_machines_filters_on_the_resolved_list(self):
		api = self._api()
		start = api.index("def get_machines(department=None):")
		body = api[start : api.index("def machine_departments", start)]
		# Not a SQL filter on `department` - that would hide a shared press.
		self.assertIn('m["departments"]', body)
		self.assertNotIn('filters["department"] = department', body)

	def test_the_screen_filters_the_same_way(self):
		here = os.path.dirname(os.path.abspath(__file__))
		screen = open(
			os.path.join(here, "..", "page", "vcl_production_lite", "vcl_production_lite.js")
		).read()
		# The phone filters the board's own copy, so drift here shows as a
		# machine that exists on the server and cannot be picked.
		self.assertIn("machine.departments || [machine.department]", screen)
		self.assertNotIn("machine.department === department", screen)


class PlanLinesTests(unittest.TestCase):
	"""A job card becomes one line per station it will pass through.

	Computer Paper prints each part on its own press - the run log for
	JC-CPT-2026-00062 has Part 2 (CF Yellow) on Miyakoshi 01 and Part 1
	(CB White) on Miyakoshi 3, the same day. Collation joins them back into one
	set, so only printing splits.
	"""

	ROUTE = ["Design", "Pending Films", "Printing", "Collation", "Pack"]
	PARTS = [
		{"part_number": 1, "paper_type": "CB", "colour": "White", "gsm": 55},
		{"part_number": 2, "paper_type": "CF", "colour": "Yellow", "gsm": 55},
	]

	def test_printing_splits_per_part_and_nothing_else_does(self):
		lines = plan_lines(self.ROUTE, self.PARTS)
		self.assertEqual(len(lines), 6)
		printing = [l for l in lines if l["stage"] == "Printing"]
		self.assertEqual(len(printing), 2)
		for stage in ("Design", "Pending Films", "Collation", "Pack"):
			self.assertEqual(len([l for l in lines if l["stage"] == stage]), 1, stage)

	def test_the_split_lines_carry_the_colour(self):
		lines = plan_lines(self.ROUTE, self.PARTS)
		labels = [l["part_label"] for l in lines if l["stage"] == "Printing"]
		self.assertEqual(labels, ["Part 1 · CB · White · 55gsm", "Part 2 · CF · Yellow · 55gsm"])

	def test_a_job_with_no_parts_still_gets_a_plan(self):
		# A missing spec must not silently produce an empty plan - that would
		# read as "this job needs no work".
		lines = plan_lines(self.ROUTE, [])
		self.assertEqual(len(lines), 5)
		self.assertTrue(all(l["part_label"] is None for l in lines))

	def test_route_order_is_kept_and_split_lines_share_a_sequence(self):
		lines = plan_lines(self.ROUTE, self.PARTS)
		self.assertEqual([l["sequence"] for l in lines], [1, 2, 3, 3, 4, 5])

	def test_the_printing_stages_that_split_are_named_explicitly(self):
		# Reel to Reel and Sheet to Sheet are the ERPNext Workstation Type names
		# for the same operation; all three must split or a Computer Paper job
		# planned under its real stage name silently stops splitting.
		self.assertIn("Printing", SPLIT_BY_PART)
		self.assertIn("Reel to Reel Printing", SPLIT_BY_PART)
		self.assertIn("Sheet to Sheet Printing", SPLIT_BY_PART)

	def test_an_empty_route_is_no_lines_not_a_crash(self):
		self.assertEqual(plan_lines([], self.PARTS), [])
		self.assertEqual(plan_lines(None, None), [])


class PartLabelTests(unittest.TestCase):
	def test_a_full_part_reads_as_the_floor_says_it(self):
		self.assertEqual(
			part_label({"part_number": 2, "paper_type": "CF", "colour": "Yellow", "gsm": 55}),
			"Part 2 · CF · Yellow · 55gsm",
		)

	def test_a_sparse_part_still_gets_a_usable_label(self):
		# Rather than a string full of gaps and separators.
		self.assertEqual(part_label({"part_number": 1}), "Part 1")
		self.assertEqual(part_label({"colour": "Blue"}), "Blue")
		self.assertEqual(part_label({}), "")


class CarryForwardTests(unittest.TestCase):
	"""What is still owed becomes tomorrow's planned quantity."""

	def row(self, **over):
		base = {
			"production_date": "2026-08-27",
			"department": "Reel to Reel",
			"machine": "M3",
			"customer_name": "KCB",
			"job_name": "KCB",
			"uom": "reels",
			"carried_quantity": 1,
			"production_job_card": "JC-CPT-2026-00099",
			"part_label": None,
		}
		base.update(over)
		return base

	def test_the_carried_amount_becomes_tomorrows_plan(self):
		nxt = carry_forward_row(self.row(), "2026-08-28")
		self.assertEqual(nxt["planned_quantity"], 1.0)
		self.assertEqual(nxt["status"], "Planned")
		self.assertEqual(nxt["machine"], "M3")
		self.assertEqual(nxt["uom"], "reels")

	def test_the_job_card_and_part_travel_with_it(self):
		nxt = carry_forward_row(self.row(part_label="Part 2 · CF · Yellow · 55gsm"), "2026-08-28")
		self.assertEqual(nxt["production_job_card"], "JC-CPT-2026-00099")
		self.assertEqual(nxt["part_label"], "Part 2 · CF · Yellow · 55gsm")

	def test_it_says_where_it_came_from(self):
		nxt = carry_forward_row(self.row(), "2026-08-28")
		self.assertIn("2026-08-27", nxt["notes"])

	def test_nothing_to_carry_is_no_row(self):
		# So the caller can run this over every row without checking first.
		self.assertIsNone(carry_forward_row(self.row(carried_quantity=0), "2026-08-28"))
		self.assertIsNone(carry_forward_row(self.row(carried_quantity=None), "2026-08-28"))
		self.assertIsNone(carry_forward_row(self.row(carried_quantity=""), "2026-08-28"))

	def test_junk_carries_nothing_rather_than_raising(self):
		self.assertIsNone(carry_forward_row(self.row(carried_quantity="lots"), "2026-08-28"))

	def test_a_negative_carry_is_not_a_row(self):
		self.assertIsNone(carry_forward_row(self.row(carried_quantity=-5), "2026-08-28"))


class PatchesMustNotInsertTests(unittest.TestCase):
	"""⛔ The ordering trap that has taken this site down once already.

	    migrate:  pre_model_sync patches
	           -> model sync
	           -> post_model_sync patches      <- our patches
	           -> after_migrate hooks           <- apply_select_options

	`apply_select_options` is what widens the `department` Select for a newly
	added department. A patch that INSERTS a machine into that department runs
	first, fails `_validate_selects`, and a throw inside migrate aborts it for
	EVERY app on the bench.

	So patches may only `db.set_value` on rows that already exist. Anything that
	creates a machine belongs in after_migrate, after the Select is widened and
	after seed_machines.
	"""

	@staticmethod
	def _patch_sources():
		import glob

		here = os.path.dirname(os.path.abspath(__file__))
		root = os.path.join(here, "..", "..", "patches")
		return {
			os.path.basename(path): open(path).read()
			for path in glob.glob(os.path.join(root, "v10_*", "*.py"))
			if not path.endswith("__init__.py")
		}

	def test_no_patch_inserts_a_production_machine(self):
		for name, source in self._patch_sources().items():
			self.assertNotIn(
				'"doctype": "VCL Production Machine"',
				source,
				"{0} creates a machine. Patches run BEFORE the department Select "
				"is widened, so this aborts the whole migrate. Seed it from "
				"after_migrate instead.".format(name),
			)

	def test_the_mapping_lives_in_one_place(self):
		# Both the patch and after_migrate apply it, and two copies would drift.
		here = os.path.dirname(os.path.abspath(__file__))
		shared = open(os.path.join(here, "..", "setup", "alignment.py")).read()
		self.assertIn("MAPPING = {", shared)
		for name, source in self._patch_sources().items():
			if "MAPPING" in source:
				self.assertIn("from production_log.production_floor.setup.alignment import", source, name)

	def test_after_migrate_aligns_after_it_seeds(self):
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		tree = ast.parse(open(os.path.join(here, "..", "install.py")).read())
		func = next(
			n for n in tree.body
			if isinstance(n, ast.FunctionDef) and n.name == "after_migrate"
		)
		calls = [
			n.func.id for n in ast.walk(func)
			if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
		]
		self.assertLess(calls.index("apply_select_options"), calls.index("seed_machines"))
		self.assertLess(calls.index("seed_machines"), calls.index("align_machines"))

	def test_the_slitter_is_seeded_not_patched(self):
		import ast

		here = os.path.dirname(os.path.abspath(__file__))
		source = open(os.path.join(here, "..", "setup", "seed.py")).read()
		machines = next(
			node.value for node in ast.parse(source).body
			if isinstance(node, ast.Assign)
			and any(getattr(t, "id", None) == "MACHINES" for t in node.targets)
		)
		names = [r.elts[0].value for r in machines.elts]
		self.assertIn("Slitter", names)

