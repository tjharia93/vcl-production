"""Unit tests for the Computer Paper weight arithmetic.

Plain ``unittest``, no bench, no site, no database - ``cps_cp_weight`` imports
nothing from Frappe, which is the whole reason it exists as its own module.

The worked example used throughout is a real 3-part A4-ish delivery note:

	241 mm x 279 mm finished, so 0.067239 m2 per set
	3 plies of 55 + 50 + 55 GSM, so 160 GSM per set
	substrate = 0.067239 * 160 = 10.75824 g per set
	500 sets per carton
	1.2 kg empty carton

	Plain:   net = 10.75824 * 500 / 1000 = 5.37912 kg ; gross = 6.57912 kg
	Printed at 4%: per set = 10.75824 * 1.04 = 11.1885696 g
	               net = 5.59428... kg ; gross = 6.79428... kg
"""

import unittest

from production_log.job_card_tracking import cps_cp_weight as w


def spec(**overrides):
	"""A Computer Paper specification as a plain dict, with a complete weight set."""
	base = {
		"product_type": w.COMPUTER_PAPER,
		"print_type": w.PRINT_TYPE_PLAIN,
		"finished_width_mm": 241,
		"finished_length_mm": 279,
		"sets_per_carton": 500,
		"packing_carton_tare_kg": 1.2,
		"print_weight_allowance_pct": None,
		"colour_of_parts": [
			{"part_number": 1, "paper_type": "CB", "gsm": 55, "colour": "White"},
			{"part_number": 2, "paper_type": "CFB", "gsm": 50, "colour": "Pink"},
			{"part_number": 3, "paper_type": "CF", "gsm": 55, "colour": "Blue"},
		],
	}
	base.update(overrides)
	return base


class TestTotalGsm(unittest.TestCase):
	def test_sums_every_ply(self):
		self.assertEqual(w.total_gsm(spec()["colour_of_parts"]), 160)

	def test_single_part(self):
		self.assertEqual(w.total_gsm([{"gsm": 60}]), 60)

	def test_missing_and_blank_gsm_contribute_nothing(self):
		self.assertEqual(w.total_gsm([{"gsm": 55}, {"gsm": None}, {"gsm": ""}]), 55)

	def test_no_rows_is_zero(self):
		self.assertEqual(w.total_gsm([]), 0)
		self.assertEqual(w.total_gsm(None), 0)


class TestArea(unittest.TestCase):
	def test_mm_to_m2(self):
		self.assertAlmostEqual(w.area_m2(241, 279), 0.067239)

	def test_missing_or_nonpositive_is_none(self):
		for width, length in ((None, 279), (241, None), (0, 279), (241, 0), (-1, 279)):
			self.assertIsNone(w.area_m2(width, length), (width, length))


class TestSubstrate(unittest.TestCase):
	def test_area_times_gsm(self):
		self.assertAlmostEqual(w.substrate_g_per_set(241, 279, 160), 10.75824)

	def test_no_gsm_is_none(self):
		self.assertIsNone(w.substrate_g_per_set(241, 279, 0))
		self.assertIsNone(w.substrate_g_per_set(241, 279, None))


class TestAllowanceMultiplier(unittest.TestCase):
	def test_plain_is_always_one(self):
		# Even a stale allowance on a Plain record is ignored - plain paper has no ink.
		self.assertEqual(w.allowance_multiplier(w.PRINT_TYPE_PLAIN, 4), 1.0)

	def test_printed_with_no_allowance_is_one(self):
		self.assertEqual(w.allowance_multiplier(w.PRINT_TYPE_PRINTED, None), 1.0)
		self.assertEqual(w.allowance_multiplier(w.PRINT_TYPE_PRINTED, 0), 1.0)

	def test_printed_with_allowance(self):
		self.assertAlmostEqual(w.allowance_multiplier(w.PRINT_TYPE_PRINTED, 4), 1.04)

	def test_unknown_type_carries_no_allowance(self):
		self.assertEqual(w.allowance_multiplier("Litho", 4), 1.0)


class TestPerSet(unittest.TestCase):
	def test_plain_is_the_substrate(self):
		self.assertAlmostEqual(
			w.paper_weight_per_set_g(241, 279, 160, w.PRINT_TYPE_PLAIN, None), 10.75824
		)

	def test_printed_applies_the_allowance(self):
		self.assertAlmostEqual(
			w.paper_weight_per_set_g(241, 279, 160, w.PRINT_TYPE_PRINTED, 4), 11.1885696
		)

	def test_printed_without_an_allowance_equals_plain(self):
		self.assertAlmostEqual(
			w.paper_weight_per_set_g(241, 279, 160, w.PRINT_TYPE_PRINTED, None), 10.75824
		)


class TestNetAndGross(unittest.TestCase):
	def test_net_is_paper_only(self):
		self.assertAlmostEqual(w.net_weight_per_carton_kg(10.75824, 500), 5.37912)

	def test_gross_adds_the_carton(self):
		self.assertAlmostEqual(w.gross_weight_per_carton_kg(5.37912, 1.2), 6.57912)

	def test_gross_is_exactly_net_plus_tare(self):
		# The property the whole "including the outer carton" line rests on.
		net = w.net_weight_per_carton_kg(10.75824, 500)
		self.assertAlmostEqual(w.gross_weight_per_carton_kg(net, 1.2) - net, 1.2)

	def test_a_zero_tare_gross_equals_net(self):
		self.assertAlmostEqual(w.gross_weight_per_carton_kg(5.37912, 0), 5.37912)

	def test_missing_inputs_are_none(self):
		self.assertIsNone(w.net_weight_per_carton_kg(None, 500))
		self.assertIsNone(w.net_weight_per_carton_kg(10.7, 0))
		self.assertIsNone(w.gross_weight_per_carton_kg(None, 1.2))
		self.assertIsNone(w.gross_weight_per_carton_kg(5.3, None))
		self.assertIsNone(w.gross_weight_per_carton_kg(5.3, -1))


class TestComputeWeights(unittest.TestCase):
	def test_plain_end_to_end(self):
		result = w.compute_weights(spec())
		self.assertEqual(result[w.TOTAL_GSM_FIELD], 160)
		self.assertEqual(result[w.PER_SET_FIELD], 10.76)
		self.assertEqual(result[w.NET_FIELD], 5.379)
		self.assertEqual(result[w.GROSS_FIELD], 6.579)

	def test_printed_end_to_end(self):
		result = w.compute_weights(
			spec(print_type=w.PRINT_TYPE_PRINTED, print_weight_allowance_pct=4)
		)
		self.assertEqual(result[w.PER_SET_FIELD], 11.19)
		self.assertEqual(result[w.NET_FIELD], 5.594)
		self.assertEqual(result[w.GROSS_FIELD], 6.794)

	def test_gross_is_heavier_than_net_by_the_tare(self):
		result = w.compute_weights(spec())
		self.assertAlmostEqual(
			result[w.GROSS_FIELD] - result[w.NET_FIELD], 1.2, places=2
		)

	def test_single_part_plain(self):
		result = w.compute_weights(
			spec(
				colour_of_parts=[{"part_number": 1, "paper_type": "60 GSM Bond", "gsm": 60}],
			)
		)
		self.assertEqual(result[w.TOTAL_GSM_FIELD], 60)
		# 0.067239 * 60 = 4.03434 g/set ; *500/1000 = 2.01717 kg ; +1.2 = 3.21717
		self.assertEqual(result[w.NET_FIELD], 2.017)
		self.assertEqual(result[w.GROSS_FIELD], 3.217)

	def test_incomplete_inputs_yield_none(self):
		result = w.compute_weights(spec(finished_width_mm=None))
		self.assertIsNone(result[w.PER_SET_FIELD])
		self.assertIsNone(result[w.NET_FIELD])
		self.assertIsNone(result[w.GROSS_FIELD])
		# The GSM is still known even when the dimensions are not.
		self.assertEqual(result[w.TOTAL_GSM_FIELD], 160)

	def test_no_parts_yields_no_gsm(self):
		result = w.compute_weights(spec(colour_of_parts=[]))
		self.assertIsNone(result[w.TOTAL_GSM_FIELD])
		self.assertIsNone(result[w.GROSS_FIELD])

	def test_string_inputs_are_accepted(self):
		# Frappe hands numbers back as strings off a JSON payload.
		result = w.compute_weights(
			spec(finished_width_mm="241", finished_length_mm="279", sets_per_carton="500",
			     packing_carton_tare_kg="1.2")
		)
		self.assertEqual(result[w.GROSS_FIELD], 6.579)


class TestStandardWeightValue(unittest.TestCase):
	def test_is_the_gross_at_precision_two(self):
		self.assertEqual(w.standard_weight_value(spec()), 6.58)

	def test_none_when_incomplete(self):
		self.assertIsNone(w.standard_weight_value(spec(sets_per_carton=None)))


class TestWeightFieldErrors(unittest.TestCase):
	def test_a_complete_set_has_no_errors(self):
		self.assertEqual(w.weight_field_errors(spec()), [])

	def test_absence_is_not_an_error(self):
		# A blank field is incomplete, not invalid - a draft may be blank.
		self.assertEqual(
			w.weight_field_errors(
				spec(finished_width_mm=None, finished_length_mm=None,
				     sets_per_carton=None, packing_carton_tare_kg=None)
			),
			[],
		)

	def test_negative_width(self):
		errors = w.weight_field_errors(spec(finished_width_mm=-5))
		self.assertEqual([e.code for e in errors], [w.BLOCK_WIDTH])

	def test_zero_is_absence_not_an_error(self):
		# A Frappe Float or Int column loads an untouched field as 0, not as None,
		# so a zero here cannot be told apart from "nobody typed it". Refusing it
		# refused every save of every record whose tare had never been entered.
		# Zero is incompleteness, and TestSubmitBlock is where it bites.
		for field in ("finished_width_mm", "finished_length_mm",
		              "sets_per_carton", "packing_carton_tare_kg",
		              "finished_width_in", "finished_length_in"):
			self.assertEqual(w.weight_field_errors(spec(**{field: 0})), [], field)

	def test_negative_tare(self):
		errors = w.weight_field_errors(spec(packing_carton_tare_kg=-1))
		self.assertIn(w.BLOCK_TARE, [e.code for e in errors])

	def test_negative_inches_are_refused(self):
		errors = w.weight_field_errors(spec(finished_width_in=-9.5, finished_length_in=-8))
		self.assertEqual({e.code for e in errors}, {w.BLOCK_WIDTH, w.BLOCK_LENGTH})

	def test_a_non_numeric_entry_is_refused(self):
		errors = w.weight_field_errors(spec(finished_width_in="nine and a half"))
		self.assertIn(w.BLOCK_WIDTH, [e.code for e in errors])

	def test_fractional_sets_are_refused(self):
		errors = w.weight_field_errors(spec(sets_per_carton=500.5))
		self.assertIn(w.BLOCK_SETS, [e.code for e in errors])

	def test_every_problem_is_reported_not_only_the_first(self):
		errors = w.weight_field_errors(
			spec(finished_width_mm=-1, finished_length_mm=-3, sets_per_carton=-2)
		)
		codes = {e.code for e in errors}
		self.assertEqual(codes, {w.BLOCK_WIDTH, w.BLOCK_LENGTH, w.BLOCK_SETS})

	def test_negative_allowance_is_refused(self):
		errors = w.weight_field_errors(
			spec(print_type=w.PRINT_TYPE_PRINTED, print_weight_allowance_pct=-4)
		)
		self.assertIn(w.BLOCK_ALLOWANCE, [e.code for e in errors])

	def test_allowance_on_a_plain_record_is_flagged(self):
		errors = w.weight_field_errors(spec(print_weight_allowance_pct=4))
		self.assertIn(w.BLOCK_ALLOWANCE_ON_PLAIN, [e.code for e in errors])

	def test_other_product_types_are_not_checked(self):
		self.assertEqual(w.weight_field_errors(spec(product_type="Carton", finished_width_mm=-5)), [])


class TestCompleteness(unittest.TestCase):
	def test_a_full_set_is_complete(self):
		self.assertTrue(w.weight_inputs_complete(spec()))

	def test_missing_any_dimension_is_incomplete(self):
		for field in w.WEIGHT_INPUT_FIELDS:
			self.assertFalse(w.weight_inputs_complete(spec(**{field: None})), field)

	def test_no_parts_is_incomplete(self):
		self.assertFalse(w.weight_inputs_complete(spec(colour_of_parts=[])))

	def test_inputs_present_detects_any_entry(self):
		self.assertFalse(
			w.weight_inputs_present(
				spec(finished_width_mm=None, finished_length_mm=None,
				     sets_per_carton=None, packing_carton_tare_kg=None)
			)
		)
		self.assertTrue(w.weight_inputs_present(spec(finished_width_mm=None,
		                                             finished_length_mm=None,
		                                             sets_per_carton=None)))


class TestSubmitBlock(unittest.TestCase):
	def test_a_complete_record_submits(self):
		self.assertIsNone(w.weight_submit_block_reason(spec()))

	def test_missing_dimensions_block_submission(self):
		reason = w.weight_submit_block_reason(
			spec(finished_width_mm=None, sets_per_carton=None)
		)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, w.BLOCK_INCOMPLETE)
		text = w.reason_text(reason)
		self.assertIn("finished width", text)
		self.assertIn("sets per carton", text)

	def test_missing_gsm_is_reported_as_the_parts_grid(self):
		reason = w.weight_submit_block_reason(spec(colour_of_parts=[]))
		self.assertEqual(reason.code, w.BLOCK_GSM)

	def test_tare_is_required_to_submit(self):
		reason = w.weight_submit_block_reason(spec(packing_carton_tare_kg=None))
		self.assertEqual(reason.code, w.BLOCK_INCOMPLETE)
		self.assertIn("tare", w.reason_text(reason))

	def test_other_product_types_are_not_asked(self):
		self.assertIsNone(w.weight_submit_block_reason(spec(product_type="Label")))


class TestInchEntry(unittest.TestCase):
	"""Inches are the entry; millimetres are derived and are what is multiplied."""

	def test_the_sizes_the_floor_actually_orders(self):
		self.assertEqual(w.mm_from_inches(9.5), 241.3)
		self.assertEqual(w.mm_from_inches(8), 203.2)
		self.assertEqual(w.mm_from_inches(11), 279.4)
		self.assertEqual(w.mm_from_inches(14.5), 368.3)

	def test_a_string_entry_converts(self):
		self.assertEqual(w.mm_from_inches("9.5"), 241.3)

	def test_nothing_positive_is_no_size(self):
		for value in (None, "", 0, -9.5, "nine"):
			self.assertIsNone(w.mm_from_inches(value), value)
			self.assertIsNone(w.inches_from_mm(value), value)

	def test_the_round_trip_returns_what_was_typed(self):
		for inches in (8, 9.5, 11, 12, 14.5, 5.5):
			self.assertEqual(w.inches_from_mm(w.mm_from_inches(inches)), float(inches))

	def test_derived_dimensions_writes_only_what_was_entered(self):
		self.assertEqual(
			w.derived_dimensions({"finished_width_in": 9.5, "finished_length_in": 8}),
			{"finished_width_mm": 241.3, "finished_length_mm": 203.2},
		)
		self.assertEqual(
			w.derived_dimensions({"finished_width_in": 9.5}),
			{"finished_width_mm": 241.3},
		)

	def test_no_inches_never_blanks_a_stored_millimetre(self):
		# The legacy guarantee: a specification written in millimetres is not
		# emptied by the conversion of an inch field nobody filled in.
		self.assertEqual(w.derived_dimensions(spec()), {})

	def test_inches_win_over_a_stored_millimetre(self):
		self.assertEqual(
			w.effective_dimensions(spec(finished_width_in=9.5, finished_length_in=8)),
			(241.3, 203.2),
		)

	def test_millimetres_are_the_fallback(self):
		self.assertEqual(w.effective_dimensions(spec()), (241.0, 279.0))

	def test_neither_is_no_size(self):
		self.assertEqual(
			w.effective_dimensions(spec(finished_width_mm=None, finished_length_mm=None)),
			(None, None),
		)

	def test_a_weight_from_inches_alone(self):
		# The Gilani's 9.5 x 8 two-part: 55 CB + 55 CF = 110 GSM, 500 sets, 0.3 kg
		# carton. Computed from inches with no millimetres stored anywhere on the
		# record — which is the state a Compass preview is in before the save.
		got = w.compute_weights(
			{
				"product_type": w.COMPUTER_PAPER,
				"print_type": w.PRINT_TYPE_PRINTED,
				"finished_width_in": 9.5,
				"finished_length_in": 8,
				"sets_per_carton": 500,
				"packing_carton_tare_kg": 0.3,
				"colour_of_parts": [{"gsm": 55}, {"gsm": 55}],
			}
		)
		self.assertEqual(got[w.TOTAL_GSM_FIELD], 110.0)
		self.assertEqual(got[w.PER_SET_FIELD], 5.39)
		self.assertEqual(got[w.NET_FIELD], 2.697)
		self.assertEqual(got[w.GROSS_FIELD], 2.997)

	def test_inches_and_their_millimetres_weigh_the_same(self):
		from_inches = w.compute_weights(spec(
			finished_width_mm=None, finished_length_mm=None,
			finished_width_in=9.488, finished_length_in=10.984,
		))
		from_mm = w.compute_weights(spec(
			finished_width_mm=w.mm_from_inches(9.488),
			finished_length_mm=w.mm_from_inches(10.984),
		))
		self.assertEqual(from_inches, from_mm)


class TestSuggestDimensions(unittest.TestCase):
	def test_a_plain_two_number_size(self):
		self.assertIsNone(w.suggest_dimensions("241 x 279"))
		self.assertEqual(w.suggest_dimensions("241 x 279", "mm"), (241.0, 279.0))

	def test_various_separators_and_units(self):
		for text in ("241 x 279 mm", "241x279mm"):
			self.assertEqual(w.suggest_dimensions(text), (241.0, 279.0), text)

	def test_decimal_inches_style(self):
		self.assertEqual(w.suggest_dimensions("9.5 x 11", "in"), (241.3, 279.4))
		for text in ("9.5 x 11 in", "9.5 x 11 inches", '9.5 x 11"'):
			self.assertEqual(w.suggest_dimensions(text), (241.3, 279.4), text)

	def test_no_suggestion_for_ambiguous_or_unparseable_text(self):
		for text in ("A4", "continuous", "", None, "241 x 279 x 2", "241", "letter size"):
			self.assertIsNone(w.suggest_dimensions(text), text)

	def test_the_suggestion_is_never_read_by_the_calculation(self):
		# job_size is not an input to any weight function - the calculation reads
		# only the structured fields. A record with a job_size and no structured
		# dimensions computes no weight.
		doc = spec(job_size="241 x 279", finished_width_mm=None, finished_length_mm=None)
		self.assertIsNone(w.compute_weights(doc)[w.GROSS_FIELD])


class TestFrozenSnapshotMapping(unittest.TestCase):
	"""The gross weight rides the field the order already freezes.

	The whole reason the derived gross is *also* written into
	``standard_weight_per_carton`` is that that field is a version-1 snapshot
	scalar and already maps onto the Job Card as ``weight_per_carton``. So a Sales
	Order freezes the computed gross with no snapshot version bump and no mapping
	change, and a historical order keeps whatever it froze.
	"""

	def test_standard_weight_is_a_frozen_snapshot_scalar(self):
		from production_log.job_card_tracking import cps_rules

		self.assertIn(w.STANDARD_WEIGHT_FIELD, cps_rules.SNAPSHOT_V1_SCALARS)

	def test_a_snapshot_freezes_the_computed_gross(self):
		from production_log.job_card_tracking import cps_rules

		# The controller has already set standard_weight_per_carton to the gross;
		# the snapshot copies the field verbatim.
		record = spec()
		record[w.STANDARD_WEIGHT_FIELD] = w.standard_weight_value(record)  # 6.58
		record["name"] = "CPT-SPEC-00042"
		snapshot = cps_rules.build_spec_snapshot(record, record["colour_of_parts"], [], "2026-07-23")
		self.assertEqual(snapshot[w.STANDARD_WEIGHT_FIELD], 6.58)

	def test_a_historical_snapshot_retains_its_own_frozen_value(self):
		from production_log.job_card_tracking import cps_rules

		# A record whose stored weight predates the calculation freezes that stored
		# value, not a recomputed one - build_spec_snapshot copies, it never derives.
		record = spec()
		record[w.STANDARD_WEIGHT_FIELD] = 99.99
		record["name"] = "CPT-SPEC-00001"
		snapshot = cps_rules.build_spec_snapshot(record, record["colour_of_parts"], [], "2025-01-01")
		self.assertEqual(snapshot[w.STANDARD_WEIGHT_FIELD], 99.99)

	def test_the_new_weight_inputs_are_not_added_to_the_snapshot_contract(self):
		from production_log.job_card_tracking import cps_rules

		# Deliberate, matching the artwork follow-up: the structured inputs and the
		# extra derived fields are NOT frozen. Adding keys a cross-repository
		# consumer must act on is a contract change, and the gross is already
		# carried by standard_weight_per_carton. The snapshot version stays 2.
		record = spec()
		record["name"] = "CPT-SPEC-00042"
		snapshot = cps_rules.build_spec_snapshot(record, record["colour_of_parts"], [], "2026-07-23")
		for field in (w.WIDTH_FIELD, w.LENGTH_FIELD, w.SETS_PER_CARTON_FIELD,
		              w.TARE_FIELD, w.GROSS_FIELD, w.NET_FIELD):
			self.assertNotIn(field, snapshot, field)
		self.assertEqual(snapshot["_snapshot_version"], 2)


if __name__ == "__main__":
	unittest.main()
