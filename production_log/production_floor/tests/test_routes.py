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
	route_for_carton,
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


def carton(**overrides):
	"""JC-CORR-2026-0077 as it really is on the live site."""
	base = {
		"applies_corrugated": 1,
		"applies_pasting": 1,
		"applies_creasing": 1,
		"applies_printing": 1,
		"applies_diecut": 0,
		"applies_slotting": 1,
		"applies_stitching": 1,
		"applies_bundling": 1,
		"joint_type": "Stitched",
	}
	base.update(overrides)
	return base


class TestCartonRoute(unittest.TestCase):

	def test_the_live_card_produces_its_real_ladder(self):
		# Before this, _route_for() returned [] for every Carton card and
		# plan_job threw "Tick at least one station."
		self.assertEqual(
			[
				"Corrugated",
				"Pasting",
				"Creasing and Slitting",
				"Printing",
				"Slotting",
				"Stitching",
				"Bundling",
			],
			route_for_carton(carton()),
		)

	def test_die_cutting_off_stays_off(self):
		self.assertNotIn("Die-cutting and Stripping", route_for_carton(carton()))

	def test_die_cutting_on_appears_in_ladder_order(self):
		route = route_for_carton(carton(applies_diecut=1))
		self.assertLess(route.index("Printing"), route.index("Die-cutting and Stripping"))
		self.assertLess(route.index("Die-cutting and Stripping"), route.index("Slotting"))

	def test_a_glued_job_gets_gluing_instead_of_stitching(self):
		# There is no applies_gluing. The joint is derived from joint_type.
		route = route_for_carton(carton(joint_type="Gluing - Machine", applies_stitching=0))
		self.assertIn("Gluing", route)
		self.assertNotIn("Stitching", route)

	def test_manual_gluing_is_the_same_station(self):
		self.assertIn("Gluing", route_for_carton(
			carton(joint_type="Gluing - Manual", applies_stitching=0)))

	def test_a_plain_tray_skips_printing_and_slotting(self):
		route = route_for_carton(carton(applies_printing=0, applies_slotting=0))
		self.assertNotIn("Printing", route)
		self.assertNotIn("Slotting", route)
		self.assertIn("Creasing and Slitting", route)

	def test_all_flags_zero_means_no_route_recorded_not_no_stages(self):
		# Historic cards predate the flags and carry all eight as zero. Reading
		# that as "this job has no stages" would empty every old traveller.
		blank = {key: 0 for key in carton() if key.startswith("applies_")}
		blank["joint_type"] = "Stitched"
		route = route_for_carton(blank)
		self.assertIn("Corrugated", route)
		self.assertIn("Bundling", route)
		self.assertNotIn("Die-cutting and Stripping", route)

	def test_every_stage_it_emits_is_mappable(self):
		# A route naming a stage the map has never heard of would resolve to
		# unstaffed and look like a missing machine rather than a typo.
		for stage in route_for_carton(carton(applies_diecut=1)):
			self.assertIn(stage, STAGE_MAP["Job Card Carton"], stage)


class TestStageStatusRule(unittest.TestCase):
	"""Running beats Completed when a stage has several stations.

	Computer Paper prints each part on its own press, so "Printing" can be
	two rows at once. If one press has finished and the other is still going,
	the STAGE is still running - reporting it Completed would tell the office
	a job is off the press when half of it is not.
	"""

	@staticmethod
	def pick(statuses):
		return "Running" if "Running" in statuses else statuses[0]

	def test_one_press_still_running_keeps_the_stage_running(self):
		self.assertEqual("Running", self.pick(["Completed", "Running"]))

	def test_all_finished_completes_the_stage(self):
		self.assertEqual("Completed", self.pick(["Completed", "Completed"]))

	def test_a_single_station_reports_itself(self):
		self.assertEqual("Paused", self.pick(["Paused"]))


if __name__ == "__main__":
	unittest.main()
