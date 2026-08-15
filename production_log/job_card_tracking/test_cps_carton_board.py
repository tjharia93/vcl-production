"""Unit tests for the Carton board-plan arithmetic.

Plain ``unittest``, no bench, no site, no database - ``cps_carton_board`` imports
nothing from Frappe, which is the whole reason it exists as its own module.

The regression fixtures are the four REAL specifications created after the Board
Plan fields went live on 2026-07-23, read off production. They are the only
records whose stored board plan was written by the live client script, so they
are the only evidence of what it actually computes - and this module has to agree
with it exactly or a revised old specification would not read the same as a new
one.

	CPT-SPEC-00064   355 x 265 x 240   flap 135   510 x 1270   530 x 1290   256.39 g
	CTN-SPEC-00023   405 x 405 x 170   flap 205   580 x 1650   600 x 1670   375.75 g
	CTN-SPEC-00024   320 x 320 x 192   flap 163   518 x 1310   538 x 1330   268.33 g

All three are 3-ply 125/125/125 = 375 GSM, 2 Flap RSC, Stitched.

CTN-SPEC-00022 is deliberately NOT a fixture for the stored figures. It was
created at 14:58 on 2026-07-23, hours before the stitch flap was reduced from
40 mm to 30 mm, so its stored ``board_length_planned_mm`` of 1560 is 10 mm wider
than today's standard produces. It is asserted here as the stale record it is, so
that nobody "fixes" this module to match it.
"""

import unittest

from production_log.job_card_tracking import cps_carton_board as b


def spec(**overrides):
	"""A Carton specification as a plain dict, 3-ply 125 GSM throughout."""
	base = {
		"product_type": b.CARTON,
		"product_type_carton": "2 Flap RSC",
		"ply": "3",
		"joint_type": "Stitched",
		"ctn_length_mm": 355,
		"ctn_width_mm": 265,
		"ctn_height_mm": 240,
		"ctn_flap_mm": 0,
		"board_width_planned_mm": 0,
		"board_length_planned_mm": 0,
		"board_width_actual_mm": 0,
		"board_length_actual_mm": 0,
		"approximate_weight_grams": 0,
		"1_ply_top_layer_gsm": 125,
		"2_ply_fluting_gsm": 125,
		"3_ply_bottom_gsm": 125,
		"4_ply_fluting_gsm": 0,
		"5_ply_fluting_gsm": 0,
	}
	base.update(overrides)
	return base


class AutoFlap(unittest.TestCase):
	def test_is_half_the_width_plus_five_rounded_up(self):
		self.assertEqual(b.auto_flap(265), 135)  # 270 / 2
		self.assertEqual(b.auto_flap(405), 205)  # 410 / 2
		self.assertEqual(b.auto_flap(320), 163)  # 325 / 2 -> 162.5 -> 163
		self.assertEqual(b.auto_flap(280), 143)  # 285 / 2 -> 142.5 -> 143

	def test_an_odd_sum_rounds_up_not_to_nearest(self):
		# 101 + 5 = 106, exactly halvable, so no rounding happens at all.
		self.assertEqual(b.auto_flap(101), 53)
		# 100 + 5 = 105 -> 52.5 -> 53, the same answer from the other side.
		self.assertEqual(b.auto_flap(100), 53)

	def test_no_width_means_no_flap(self):
		self.assertEqual(b.auto_flap(0), 0)
		self.assertEqual(b.auto_flap(None), 0)
		self.assertEqual(b.auto_flap("junk"), 0)


class TotalGsm(unittest.TestCase):
	def test_three_ply_sums_the_first_three(self):
		self.assertEqual(b.total_gsm(spec()), 375)

	def test_two_ply_ignores_the_third_even_when_it_is_set(self):
		# A stale ply-3 value left behind by an earlier edit must not be counted.
		self.assertEqual(b.total_gsm(spec(ply="2", **{"3_ply_bottom_gsm": 125})), 250)

	def test_five_ply_sums_all_five(self):
		self.assertEqual(
			b.total_gsm(
				spec(ply="5", **{"4_ply_fluting_gsm": 110, "5_ply_fluting_gsm": 110})
			),
			595,
		)


class LiveRegressionFixtures(unittest.TestCase):
	"""Agree exactly with what the live client script stored on real records."""

	def assert_plan(self, s, flap, blank, planned, weight):
		plan = b.board_plan(s)
		self.assertTrue(plan["ok"], plan["reason"])
		self.assertEqual(plan["flap"], flap)
		self.assertEqual((plan["blank_width"], plan["blank_length"]), blank)
		self.assertEqual((plan["planned_width"], plan["planned_length"]), planned)
		self.assertEqual(plan["weight_g"], weight)

	def test_cpt_spec_00064(self):
		self.assert_plan(spec(), 135, (510, 1270), (530, 1290), 256.39)

	def test_ctn_spec_00023(self):
		self.assert_plan(
			spec(ctn_length_mm=405, ctn_width_mm=405, ctn_height_mm=170),
			205,
			(580, 1650),
			(600, 1670),
			375.75,
		)

	def test_ctn_spec_00024(self):
		self.assert_plan(
			spec(ctn_length_mm=320, ctn_width_mm=320, ctn_height_mm=192),
			163,
			(518, 1310),
			(538, 1330),
			268.33,
		)

	def test_ctn_spec_00022_predates_the_30mm_tab_and_is_not_reproduced(self):
		# Stored live as 560 x 1560 under the old 40 mm stitch flap. Today's
		# standard gives 1550. If this ever starts passing at 1560, someone has
		# put the 40 mm tab back.
		plan = b.board_plan(spec(ctn_length_mm=435, ctn_width_mm=315, ctn_height_mm=220))
		self.assertEqual(plan["planned_width"], 560)
		self.assertEqual(plan["planned_length"], 1550)

	def test_ctn_spec_00005_the_record_this_was_built_for(self):
		# EAST WEST AFRICA LTD, CR 600 CARTON - 5LTIRE BY 6 JERRICANS.
		# Submitted 2026-04-29, months before the Board Plan fields existed.
		self.assert_plan(
			spec(ctn_length_mm=560, ctn_width_mm=280, ctn_height_mm=260),
			143,
			(546, 1710),
			(566, 1730),
			367.19,
		)


class Styles(unittest.TestCase):
	def test_tray_has_no_flap_and_no_joint_tab(self):
		plan = b.board_plan(spec(product_type_carton="Tray"))
		self.assertTrue(plan["ok"])
		self.assertEqual(plan["flap"], 0)
		self.assertEqual(plan["blank_width"], 265 + 2 * 240)
		self.assertEqual(plan["blank_length"], 355 + 2 * 240)

	def test_one_flap_rsc_has_a_single_flap_across_the_width(self):
		plan = b.board_plan(spec(product_type_carton="1 Flap RSC"))
		self.assertEqual(plan["blank_width"], 240 + 135)
		self.assertEqual(plan["blank_length"], 710 + 530 + b.TAB_WIDTH_MM)

	def test_three_flap_rsc_uses_the_rsc_formula(self):
		self.assertEqual(
			b.board_plan(spec(product_type_carton="3 Flap RSC"))["blank_width"],
			b.board_plan(spec(product_type_carton="2 Flap RSC"))["blank_width"],
		)


class NotApplicable(unittest.TestCase):
	def test_a_label_is_not_a_carton(self):
		self.assertEqual(b.board_plan(spec(product_type="Label"))["reason"], b.NOT_CARTON)

	def test_sfk_is_an_unglued_web_with_no_blank(self):
		self.assertEqual(b.board_plan(spec(ply=b.PLY_SFK))["reason"], b.SFK)

	def test_die_cut_shapes_have_no_formula(self):
		self.assertEqual(b.board_plan(spec(product_type_carton="Die Cut"))["reason"], b.DIE_CUT)

	def test_no_style_yet(self):
		self.assertEqual(b.board_plan(spec(product_type_carton=""))["reason"], b.NO_STYLE)

	def test_missing_height_on_a_flapped_style(self):
		self.assertEqual(
			b.board_plan(spec(ctn_height_mm=0))["reason"], b.INCOMPLETE_DIMENSIONS
		)

	def test_every_figure_is_zero_when_not_applicable(self):
		plan = b.board_plan(spec(product_type_carton="Die Cut"))
		self.assertFalse(plan["ok"])
		for key in ("blank_width", "planned_length", "weight_g", "total_gsm"):
			self.assertEqual(plan[key], 0)


class FlapOverride(unittest.TestCase):
	def test_an_override_replaces_the_formula(self):
		plan = b.board_plan(spec(), flap_override=150)
		self.assertEqual(plan["flap"], 150)
		self.assertEqual(plan["blank_width"], 150 + 240 + 150)

	def test_zero_and_none_fall_back_to_the_formula(self):
		for override in (0, None, "", "junk"):
			self.assertEqual(b.board_plan(spec(), flap_override=override)["flap"], 135)


class RevisableChanges(unittest.TestCase):
	def test_an_empty_old_format_spec_gains_the_whole_plan(self):
		values, reason = b.revisable_changes(
			spec(ctn_length_mm=560, ctn_width_mm=280, ctn_height_mm=260), {}
		)
		self.assertEqual(reason, "")
		self.assertEqual(
			values,
			{
				"ctn_flap_mm": 143,
				"board_width_planned_mm": 566,
				"board_length_planned_mm": 1730,
				"board_width_actual_mm": 546,
				"board_length_actual_mm": 1710,
				"approximate_weight_grams": 367.19,
			},
		)

	def test_a_spec_already_carrying_the_plan_changes_nothing(self):
		already = spec(
			ctn_flap_mm=135,
			board_width_planned_mm=530,
			board_length_planned_mm=1290,
			board_width_actual_mm=510,
			board_length_actual_mm=1270,
			approximate_weight_grams=256.39,
		)
		values, reason = b.revisable_changes(already, {})
		self.assertEqual(reason, "")
		self.assertEqual(values, {})

	def test_a_supplied_actual_wins_over_the_blank(self):
		values, _ = b.revisable_changes(spec(), {"board_width_actual_mm": 755})
		self.assertEqual(values["board_width_actual_mm"], 755)
		# ...and the planned size is still the derived one, not the override.
		self.assertEqual(values["board_width_planned_mm"], 530)

	def test_derived_figures_cannot_be_posted_by_the_caller(self):
		# A caller that tries to dictate the weight is ignored; it is recomputed.
		values, _ = b.revisable_changes(spec(), {"approximate_weight_grams": 9999})
		self.assertEqual(values["approximate_weight_grams"], 256.39)

	def test_weights_are_only_carried_through_when_given(self):
		values, _ = b.revisable_changes(spec(), {})
		self.assertNotIn("printed_weight", values)
		self.assertNotIn("empty_carton_weight", values)

		values, _ = b.revisable_changes(spec(), {"printed_weight": 12.5})
		self.assertEqual(values["printed_weight"], 12.5)

	def test_a_flap_override_flows_into_every_derived_figure(self):
		values, _ = b.revisable_changes(spec(), {}, flap_override=150)
		self.assertEqual(values["ctn_flap_mm"], 150)
		self.assertEqual(values["board_width_actual_mm"], 540)
		self.assertEqual(values["board_width_planned_mm"], 560)

	def test_a_stored_manual_flap_survives_an_unrelated_revision(self):
		# CTN-SPEC-00022 carries a hand-set flap. Revising it to record a weight
		# must not quietly pull the flap back to the formula - and with it the
		# blank, the planned size and the weight.
		manual = spec(ctn_flap_mm=150, ctn_width_mm=265)
		values, _ = b.revisable_changes(manual, {"printed_weight": 4.0})
		self.assertNotIn("ctn_flap_mm", values)
		self.assertEqual(values["board_width_actual_mm"], 150 + 240 + 150)

	def test_an_explicit_flap_still_overrides_the_stored_one(self):
		values, _ = b.revisable_changes(spec(ctn_flap_mm=150), {}, flap_override=160)
		self.assertEqual(values["ctn_flap_mm"], 160)

	def test_a_die_cut_spec_yields_nothing_and_says_why(self):
		values, reason = b.revisable_changes(spec(product_type_carton="Die Cut"), {})
		self.assertEqual(values, {})
		self.assertEqual(reason, b.DIE_CUT)


if __name__ == "__main__":
	unittest.main()
