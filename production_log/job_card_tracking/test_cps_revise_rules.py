"""Unit tests for the CPS revise rules. Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import cps_revise_rules as r


class InkError(unittest.TestCase):
	def test_printed_without_ink_refused(self):
		self.assertIsNotNone(r.ink_error("Printed", 0, 0))

	def test_printed_one_process_ink_ok(self):
		self.assertIsNone(r.ink_error("Printed", 1, 0))

	def test_printed_spot_only_ok(self):
		self.assertIsNone(r.ink_error("Printed", 0, 1))

	def test_plain_with_ink_refused(self):
		self.assertIsNotNone(r.ink_error("Plain", 1, 0))
		self.assertIsNotNone(r.ink_error("Plain", 0, 2))

	def test_plain_without_ink_ok(self):
		self.assertIsNone(r.ink_error("Plain", 0, 0))


class Packing(unittest.TestCase):
	def test_fields_per_type(self):
		self.assertIn("sets_per_carton", r.packing_fields("Computer Paper"))
		self.assertIn("packing_pieces", r.packing_fields("Label"))
		self.assertNotIn("sets_per_carton", r.packing_fields("Carton"))

	def test_unknown_type_gets_standard_packing_only(self):
		self.assertEqual(list(r.packing_fields("Monobox")), ["standard_packing"])

	def test_returns_a_copy(self):
		r.packing_fields("Label")["x"] = "text"
		self.assertNotIn("x", r.packing_fields("Label"))

	def test_coerce_number(self):
		self.assertEqual(r.coerce_packing("f", "number", "400"), (400, None))
		self.assertEqual(r.coerce_packing("f", "number", 2.5), (2.5, None))

	def test_coerce_rejects_negative_and_junk(self):
		self.assertIsNotNone(r.coerce_packing("f", "number", -1)[1])
		self.assertIsNotNone(r.coerce_packing("f", "number", "abc")[1])
		self.assertIsNotNone(r.coerce_packing("f", "number", None)[1])

	def test_coerce_text_trims(self):
		self.assertEqual(r.coerce_packing("f", "text", "  400 "), ("400", None))


class PriceRow(unittest.TestCase):
	good = {"valid_from": "2026-10-09", "uom": "Nos", "rate": 12.5}

	def test_good(self):
		self.assertIsNone(r.price_row_error(self.good))

	def test_missing_parts(self):
		for key in ("valid_from", "uom", "rate"):
			row = dict(self.good)
			row.pop(key)
			self.assertIsNotNone(r.price_row_error(row), key)

	def test_zero_and_negative_rate(self):
		self.assertIsNotNone(r.price_row_error({**self.good, "rate": 0}))
		self.assertIsNotNone(r.price_row_error({**self.good, "rate": -3}))


if __name__ == "__main__":
	unittest.main()


def carton(**kw):
	base = {
		"ply": "3", "flute_type": "B", "ctn_length_mm": 425, "ctn_width_mm": 305,
		"ctn_height_mm": 295, "1_ply_top_layer_gsm": 125, "2_ply_fluting_gsm": 125,
		"3_ply_bottom_gsm": 125,
	}
	base.update(kw)
	return base


class CartonBuild(unittest.TestCase):
	def test_coerce_int(self):
		self.assertEqual(r.coerce_build("ctn_height_mm", "285"), (285, None))

	def test_coerce_rejects_fraction_and_negative(self):
		self.assertIsNotNone(r.coerce_build("ctn_height_mm", "28.5")[1])
		self.assertIsNotNone(r.coerce_build("ctn_height_mm", -1)[1])

	def test_coerce_select(self):
		self.assertEqual(r.coerce_build("flute_type", " C "), ("C", None))
		self.assertIsNotNone(r.coerce_build("flute_type", "A")[1])
		self.assertIsNotNone(r.coerce_build("flute_type", "")[1])
		self.assertEqual(r.coerce_build("joint_type", ""), ("", None))

	def test_coerce_unknown_field(self):
		self.assertIsNotNone(r.coerce_build("customer", "x")[1])

	def test_valid_build(self):
		self.assertIsNone(r.build_error(carton()))

	def test_zero_height_refused_unless_sfk(self):
		self.assertIsNotNone(r.build_error(carton(ctn_height_mm=0)))
		self.assertIsNone(r.build_error(carton(ply="SFK", ctn_height_mm=0)))

	def test_five_ply_needs_five_layers(self):
		self.assertIsNotNone(r.build_error(carton(ply="5")))
		self.assertIsNone(r.build_error(carton(ply="5", **{"4_ply_fluting_gsm": 125, "5_ply_fluting_gsm": 125})))

	def test_three_ply_ignores_unused_layers(self):
		self.assertIsNone(r.build_error(carton(**{"4_ply_fluting_gsm": 0})))

	def test_job_size(self):
		self.assertEqual(r.job_size_text(425, 305, 285, "3"), "425 X 305 X 285")
		self.assertEqual(r.job_size_text(270, 61, 0, "SFK"), "270 X 61")
