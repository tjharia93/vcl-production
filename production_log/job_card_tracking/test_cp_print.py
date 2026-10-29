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


if __name__ == "__main__":
	unittest.main()
