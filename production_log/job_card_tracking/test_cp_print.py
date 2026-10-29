"""Unit tests for the Computer Paper print rules. Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import cp_print as p


class CsraRep(unittest.TestCase):
	def test_open_ended_row_applies(self):
		rows = [{"sales_representative": "Neema", "effective_from": "2025-07-01", "effective_to": None}]
		self.assertEqual(p.pick_csra_rep(rows, "2026-10-29"), "Neema")

	def test_latest_start_wins(self):
		rows = [
			{"sales_representative": "Old", "effective_from": "2024-01-01", "effective_to": None},
			{"sales_representative": "New", "effective_from": "2026-01-01", "effective_to": None},
		]
		self.assertEqual(p.pick_csra_rep(rows, "2026-10-29"), "New")

	def test_order_date_before_handover_keeps_old_rep(self):
		rows = [
			{"sales_representative": "Old", "effective_from": "2024-01-01", "effective_to": "2025-12-31"},
			{"sales_representative": "New", "effective_from": "2026-01-01", "effective_to": None},
		]
		self.assertEqual(p.pick_csra_rep(rows, "2025-06-30"), "Old")

	def test_expired_row_ignored(self):
		rows = [{"sales_representative": "Gone", "effective_from": "2024-01-01", "effective_to": "2025-01-01"}]
		self.assertIsNone(p.pick_csra_rep(rows, "2026-10-29"))

	def test_no_rows(self):
		self.assertIsNone(p.pick_csra_rep([], "2026-10-29"))


class ProductionCopyAccess(unittest.TestCase):
	def test_sales_user_refused(self):
		self.assertFalse(p.may_print_production_copy("judy.test@vimit.com", ["Sales User", "Sales Manager", "All"]))

	def test_release_role_allowed(self):
		self.assertTrue(p.may_print_production_copy("x@vimit.com", ["Sales User", "Release to Production"]))

	def test_production_role_allowed(self):
		self.assertTrue(p.may_print_production_copy("x@vimit.com", ["Manufacturing User"]))

	def test_management_allowed(self):
		self.assertTrue(p.may_print_production_copy("x@vimit.com", ["VCL Management Team"]))

	def test_administrator_allowed(self):
		self.assertTrue(p.may_print_production_copy("Administrator", []))


class Releaser(unittest.TestCase):
	def test_release_role_is_releaser(self):
		self.assertTrue(p.is_releaser("x@vimit.com", ["Release to Production"]))

	def test_production_reprint_is_not_releaser(self):
		self.assertFalse(p.is_releaser("x@vimit.com", ["Manufacturing User"]))


class PrintSideDisplay(unittest.TestCase):
	def test_plain_card_on_printed_spec_shows_the_spec(self):
		self.assertEqual(p.print_side_display("Plain", "N/A", "Printed", "Front Only"), ("Printed", "Front Only"))

	def test_printed_card_keeps_its_own_side(self):
		self.assertEqual(p.print_side_display("Printed", "Front and Back", "Printed", "Front Only"), ("Printed", "Front and Back"))

	def test_printed_with_no_side_anywhere_says_so(self):
		self.assertEqual(p.print_side_display("Plain", "N/A", "Printed", "N/A"), ("Printed", p.PRINT_SIDE_UNSET))

	def test_plain_stays_plain(self):
		self.assertEqual(p.print_side_display("Plain", "N/A", "Plain", "N/A"), ("Plain", "Plain (not printed)"))

	def test_blank_type_on_printed_spec_is_printed(self):
		self.assertEqual(p.print_side_display("", "", "Printed", "Back Only"), ("Printed", "Back Only"))


class TemplateGate(unittest.TestCase):
	"""The one print format: sales page first, production pages only behind the role check."""

	def setUp(self):
		import pathlib

		here = pathlib.Path(p.__file__).parent / "doctype/job_card_computer_paper/computer_paper_job_traveller_v2.html"
		self.html = here.read_text()
		self.gate = "{% if cp_production_copy_allowed() %}"
		self.gate_at = self.html.index(self.gate)

	def test_production_block_is_gated_and_closed(self):
		self.assertIn("{% endif %}", self.html[self.gate_at:])
		self.assertNotIn("ACCESS DENIED", self.html)

	def test_nothing_about_packing_or_tare_is_outside_the_gate(self):
		before = self.html[: self.gate_at]
		for token in ("doc.packing", "doc.weight_per_carton", "empty_carton_weight", "packed_cartons",
		              "standard_packing", "sets_per_carton", "packing_carton_tare"):
			self.assertNotIn(token, before, token)

	def test_sales_page_comes_first_and_is_marked(self):
		self.assertLess(self.html.index("sales-page"), self.gate_at)
		self.assertIn("SALES COPY", self.html[: self.gate_at])

	def test_no_html_comments_leak_to_the_page(self):
		self.assertNotIn("<!--", self.html)

	def test_sales_page_uses_the_card_print_side_helper(self):
		self.assertIn("cp_print_side(doc)", self.html[: self.gate_at])


if __name__ == "__main__":
	unittest.main()
