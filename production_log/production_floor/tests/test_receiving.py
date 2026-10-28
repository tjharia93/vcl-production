"""Rules for weighing cartons into stores. Plain Python, no bench.

    python3 -m unittest production_log.production_floor.tests.test_receiving
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from production_log.production_floor.receiving import (  # noqa: E402
	COLOURS,
	FLAG_HEAVY,
	FLAG_LIGHT,
	FLAG_OK,
	FLAG_REJECT,
	FLAG_UNCHECKED,
	WeightError,
	flag_for,
	light_streak,
	match_standard,
	parse_weight,
	standard_name,
	stock_lines,
	tally,
	tolerance_kg,
	variance_kg,
)

STANDARDS = [
	{"name": "Yellow 2P", "colour": "Yellow", "parts": 2, "customer": None, "standard_kg": 3.95, "active": 1},
	{"name": "Purple 2P", "colour": "Purple", "parts": 2, "customer": None, "standard_kg": 4.80, "active": 1},
	{"name": "Green 2P - MAGUNAS", "colour": "Green", "parts": 2, "customer": "MAGUNAS", "standard_kg": 6.55, "active": 1},
	{"name": "Blue 4P old", "colour": "Blue", "parts": 4, "customer": None, "standard_kg": 5.00, "active": 0},
]


def row(colour, parts, weight, flag, item="ITEM", customer=None):
	return {"colour": colour, "parts": parts, "weight_kg": weight, "flag": flag, "item": item, "customer": customer}


class ToleranceAndFlags(unittest.TestCase):
	def test_two_percent_of_the_standard(self):
		self.assertEqual(tolerance_kg(3.95, 2), 0.079)
		self.assertEqual(tolerance_kg(6.00, 2), 0.12)
		self.assertEqual(tolerance_kg(0, 2), 0.0)
		# Blank tolerance means the default, not zero
		self.assertEqual(tolerance_kg(5.0, None), 0.1)

	def test_flags_against_the_standard(self):
		tol = tolerance_kg(3.95, 2)
		self.assertEqual(flag_for("Yellow", 3.95, tol, 3.95), FLAG_OK)
		self.assertEqual(flag_for("Yellow", 3.95, tol, 3.88), FLAG_OK)  # on the edge, inside
		self.assertEqual(flag_for("Yellow", 3.95, tol, 3.85), FLAG_LIGHT)
		self.assertEqual(flag_for("Yellow", 3.95, tol, 4.10), FLAG_HEAVY)

	def test_sheet_figures_from_october(self):
		# 2P Purple ran 4.60-4.65 against 4.80 on every carton on 15/10 - LIGHT
		tol = tolerance_kg(4.80, 2)
		self.assertEqual(flag_for("Purple", 4.80, tol, 4.62), FLAG_LIGHT)

	def test_no_standard_is_unchecked_not_ok(self):
		self.assertEqual(flag_for("Green", 0, 0, 5.1), FLAG_UNCHECKED)
		self.assertEqual(flag_for("Green", None, None, 5.1), FLAG_UNCHECKED)

	def test_red_is_a_rejection_whatever_it_weighs(self):
		self.assertEqual(flag_for("Red", 3.95, 0.079, 3.95), FLAG_REJECT)
		self.assertEqual(flag_for("Red", 0, 0, 1.0), FLAG_REJECT)

	def test_variance(self):
		self.assertEqual(variance_kg(4.80, 4.62), -0.18)
		self.assertEqual(variance_kg(0, 4.62), 0.0)


class Weights(unittest.TestCase):
	def test_accepts_numbers_and_commas(self):
		self.assertEqual(parse_weight("3.95"), 3.95)
		self.assertEqual(parse_weight("3,95"), 3.95)
		self.assertEqual(parse_weight(4), 4.0)

	def test_refuses_nonsense(self):
		for bad in ("", None, "abc", "0", "-1", "395"):
			with self.assertRaises(WeightError):
				parse_weight(bad)


class Standards(unittest.TestCase):
	def test_house_colour_ignores_customer(self):
		self.assertEqual(match_standard(STANDARDS, "Yellow", 2, "MAGUNAS")["name"], "Yellow 2P")

	def test_green_needs_its_own_customer(self):
		self.assertEqual(match_standard(STANDARDS, "Green", 2, "MAGUNAS")["name"], "Green 2P - MAGUNAS")
		self.assertIsNone(match_standard(STANDARDS, "Green", 2, "SOMEONE ELSE"))
		self.assertIsNone(match_standard(STANDARDS, "Green", 2, None))

	def test_inactive_and_missing(self):
		self.assertIsNone(match_standard(STANDARDS, "Blue", 4))
		self.assertIsNone(match_standard(STANDARDS, "Pink", 3))

	def test_names(self):
		self.assertEqual(standard_name("Yellow", 2), "Yellow 2P")
		self.assertEqual(standard_name("Green", 3, "FULL CHANNEL"), "Green 3P - FULL CHANNEL")

	def test_legend_has_six_colours(self):
		self.assertEqual(COLOURS, ("Yellow", "Purple", "Green", "Pink", "Blue", "Red"))


class Tallies(unittest.TestCase):
	def test_rejects_are_counted_but_not_received(self):
		rows = [
			row("Yellow", 2, 3.95, FLAG_OK),
			row("Yellow", 2, 3.80, FLAG_LIGHT),
			row("Red", 2, 3.50, FLAG_REJECT),
			row("Green", 2, 5.10, FLAG_UNCHECKED, customer="X"),
		]
		t = tally(rows)
		self.assertEqual((t["cartons"], t["ok"], t["light"], t["reject"], t["unchecked"]), (4, 1, 1, 1, 1))
		self.assertEqual(t["total_kg"], 16.35)
		self.assertEqual(t["received_cartons"], 3)
		self.assertEqual(t["received_kg"], 12.85)

	def test_empty(self):
		self.assertEqual(tally([])["cartons"], 0)


class RunLight(unittest.TestCase):
	def test_three_light_in_a_row_on_one_standard(self):
		rows = [row("Purple", 2, 4.62, FLAG_LIGHT) for _ in range(3)]
		self.assertEqual(light_streak(rows), "Purple 2P")

	def test_two_is_not_a_run(self):
		rows = [row("Purple", 2, 4.62, FLAG_LIGHT) for _ in range(2)]
		self.assertIsNone(light_streak(rows))

	def test_an_ok_carton_breaks_the_streak(self):
		rows = [row("Purple", 2, 4.62, FLAG_LIGHT), row("Purple", 2, 4.62, FLAG_LIGHT), row("Purple", 2, 4.80, FLAG_OK), row("Purple", 2, 4.62, FLAG_LIGHT)]
		self.assertIsNone(light_streak(rows))

	def test_rejects_and_unchecked_are_skipped_not_breaking(self):
		rows = [row("Purple", 2, 4.62, FLAG_LIGHT), row("Red", 2, 4.0, FLAG_REJECT), row("Purple", 2, 4.62, FLAG_LIGHT), row("Purple", 2, 4.62, FLAG_LIGHT)]
		self.assertEqual(light_streak(rows), "Purple 2P")

	def test_mixed_standards_are_not_one_run(self):
		rows = [row("Purple", 2, 4.62, FLAG_LIGHT), row("Yellow", 2, 3.80, FLAG_LIGHT), row("Purple", 2, 4.62, FLAG_LIGHT)]
		self.assertIsNone(light_streak(rows))


class StockLines(unittest.TestCase):
	def test_groups_by_item_and_leaves_red_out(self):
		rows = [
			row("Yellow", 2, 3.95, FLAG_OK, item="CP-2P"),
			row("Yellow", 2, 3.90, FLAG_LIGHT, item="CP-2P"),
			row("Purple", 3, 4.60, FLAG_OK, item="CP-3P"),
			row("Red", 2, 3.0, FLAG_REJECT, item="CP-2P"),
		]
		lines, skipped = stock_lines(rows)
		self.assertEqual(sorted((l["item"], l["qty"]) for l in lines), [("CP-2P", 2), ("CP-3P", 1)])
		self.assertEqual(skipped, [])
		self.assertEqual(next(l for l in lines if l["item"] == "CP-2P")["kg"], 7.85)

	def test_customer_pack_gets_its_own_line_on_the_house_item(self):
		rows = [
			row("Purple", 2, 4.80, FLAG_OK, item="CP-2P"),
			row("Green", 2, 6.55, FLAG_OK, item="CP-2P", customer="MAGUNAS"),
			row("Green", 2, 6.50, FLAG_OK, item="CP-2P", customer="MAGUNAS"),
		]
		lines, _ = stock_lines(rows)
		got = sorted((l["item"], l["customer"] or "", l["qty"]) for l in lines)
		self.assertEqual(got, [("CP-2P", "", 1), ("CP-2P", "MAGUNAS", 2)])

	def test_no_item_is_reported_not_dropped(self):
		rows = [row("Green", 2, 5.1, FLAG_UNCHECKED, item=None, customer="X")]
		lines, skipped = stock_lines(rows)
		self.assertEqual(lines, [])
		self.assertEqual(len(skipped), 1)


if __name__ == "__main__":
	unittest.main()
