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


class JsRoleListInStep(unittest.TestCase):
	def test_form_script_lists_the_same_roles(self):
		import pathlib
		import re

		js = (pathlib.Path(p.__file__).parent / "doctype/job_card_computer_paper/job_card_computer_paper.js").read_text()
		block = re.search(r"CP_PRODUCTION_COPY_ROLES = \[(.*?)\];", js, re.S).group(1)
		self.assertEqual(set(re.findall(r'"([^"]+)"', block)), set(p.PRODUCTION_COPY_ROLES))


class RepUser(unittest.TestCase):
	NEEMA = [
		{"user": "neema.test@vimit.com", "full_name": "Neema Test"},
		{"user": "neema@vimit.com", "full_name": "Neema"},
		{"user": "judy.test@vimit.com", "full_name": "Judy Test"},
		{"user": "judith.avuzika@vimit.com", "full_name": "Judy"},
	]

	def test_live_neema_permissions_resolve_to_neema_not_the_order_desk(self):
		# The real User Permission set on Sales Person "Neema", read 29/10/2026.
		self.assertEqual(p.pick_rep_user("Neema", self.NEEMA), "neema@vimit.com")

	def test_single_candidate_wins(self):
		self.assertEqual(p.pick_rep_user("X", [{"user": "a@vimit.com", "full_name": "A"}]), "a@vimit.com")

	def test_ambiguous_is_none_not_a_guess(self):
		c = [{"user": "a@vimit.com", "full_name": "Sam One"}, {"user": "b@vimit.com", "full_name": "Sam Two"}]
		self.assertIsNone(p.pick_rep_user("Sam", c))

	def test_no_candidates(self):
		self.assertIsNone(p.pick_rep_user("Neema", []))


class SpecPrintValues(unittest.TestCase):
	SPEC_00082 = {"print_type": "Printed", "print_side": "Front Only", "printed_weight": 0.3}

	def test_pre_d4_snapshot_falls_back_to_spec(self):
		# JC-CPT-2026-00092's real snapshot (v2) has none of the three keys.
		snap = {"_snapshot_version": 2, "job_size": "9.5 X 11", "standard_packing": "450"}
		self.assertEqual(p.spec_print_values(snap, self.SPEC_00082), self.SPEC_00082)

	def test_snapshot_wins_over_a_since_edited_spec(self):
		snap = {"print_type": "Plain", "print_side": "N/A", "printed_weight": 0}
		self.assertEqual(p.spec_print_values(snap, self.SPEC_00082), snap)

	def test_missing_everywhere_is_left_out(self):
		self.assertEqual(p.spec_print_values({}, {}), {})


class SnapshotCarriesPrintBlock(unittest.TestCase):
	def test_cp_snapshot_freezes_print_block_but_not_tare(self):
		from production_log.job_card_tracking import cps_rules

		spec = {"product_type": "Computer Paper", "name": "CPT-SPEC-00082", **SpecPrintValues.SPEC_00082,
		        "empty_carton_weight": 300}
		snap = cps_rules.build_spec_snapshot(spec, [], [], "2026-10-29 12:00:00")
		for f in p.SPEC_PRINT_FIELDS:
			self.assertEqual(snap[f], spec[f])
		self.assertNotIn("empty_carton_weight", snap)
		self.assertEqual(snap["_snapshot_version"], 2)


if __name__ == "__main__":
	unittest.main()
