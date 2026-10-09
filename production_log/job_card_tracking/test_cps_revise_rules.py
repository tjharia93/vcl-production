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
