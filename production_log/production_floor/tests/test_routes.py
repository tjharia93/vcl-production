"""Pure route logic. No bench, no Frappe - run with:

    python3 -m unittest production_log.production_floor.tests.test_routes
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from production_log.production_floor.routes import (  # noqa: E402
	STAGE_MAP,
	resolve_stage,
)

CP = "Job Card Computer Paper"
CARTON = "Job Card Carton"


class TestResolveStage(unittest.TestCase):

	def test_printing_on_a_cp_card_resolves_to_the_reel_fed_presses(self):
		# The whole reason this module exists: no machine offers a stage
		# called "Printing", so the route silently planned nothing.
		found = resolve_stage(CP, "Printing")
		self.assertFalse(found["office"])
		self.assertIn("Reel to Reel Printing", found["types"])

	def test_printing_means_something_different_on_a_carton_card(self):
		# Same word, different press. This is why the map is per doctype and
		# why renaming the machines would have collided.
		self.assertEqual(("Carton Printing",), resolve_stage(CARTON, "Printing")["types"])

	def test_design_is_office_and_never_reaches_the_board(self):
		found = resolve_stage(CP, "Design")
		self.assertTrue(found["office"])
		self.assertEqual((), found["types"])

	def test_pack_is_a_floor_stage_with_no_station(self):
		# Not office - somebody packs. There is just no machine for it, and
		# Tanuj decided not to add one.
		found = resolve_stage(CP, "Pack")
		self.assertFalse(found["office"])
		self.assertEqual((), found["types"])

	def test_an_unknown_stage_is_floor_and_unstaffed_not_an_error(self):
		# A stage nobody has mapped must still be visible on the plan. Raising
		# here would make one unmapped stage hide a whole route.
		found = resolve_stage(CP, "Something New")
		self.assertFalse(found["office"])
		self.assertEqual((), found["types"])

	def test_an_unknown_doctype_resolves_rather_than_raising(self):
		found = resolve_stage("Job Card Label", "Printing")
		self.assertEqual((), found["types"])

	def test_numbering_resolves_to_the_collator(self):
		# NOTE: the master describes Collator 01 (numbers) and 02 (does not),
		# but only one "Collator" exists in the machine master, so this cannot
		# yet be narrowed. See spec 8.1.
		self.assertEqual(("Collation",), resolve_stage(CP, "Numbering")["types"])


if __name__ == "__main__":
	unittest.main()
