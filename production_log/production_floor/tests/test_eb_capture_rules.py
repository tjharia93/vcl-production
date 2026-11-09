import datetime
import unittest

from production_log.production_floor import eb_capture_rules as r

A5 = "Prince|A5|120|SL"
A4 = "Swara|A4|96|SL"


class TestCodes(unittest.TestCase):
	def test_codes_twin(self):
		c = r.codes(A5)
		self.assertEqual(c["cov"], "COV-PNC-A5-120PG-SL")
		self.assertEqual(c["fld"], "FLD-PNC-A5-120PG-SL")
		self.assertEqual(c["ins"], "INS-PNC-A5-120PG-SL")
		self.assertEqual(c["book"], "PNCEB-A5-120PGS-CB-BP-SL")
		self.assertEqual(c["carton"], "PNCSWR-EMPTY-CARTON-A5-PLAINF-DPL")
		self.assertEqual(r.codes(A4)["book"], "SWREB-A4-96PGS-CB-NP-SL")
		self.assertEqual(r.codes("Prince|A4|48|SL")["cov"], "COV-PNC-A4-048PG-SL")

	def test_bad_group(self):
		with self.assertRaises(r.CaptureError):
			r.parse_group("Unknown|A4|96|SL")

	def test_hi5_codes_and_no_empty_carton(self):
		c = r.codes("Hi5|A4|120|SL")
		self.assertEqual(c["cov"], "COV-HI5-A4-120PG-SL")
		self.assertEqual(c["fld"], "FLD-HI5-A4-120PG-SL")
		self.assertEqual(c["ins"], "INS-HI5-A4-120PG-SL")
		self.assertEqual(c["book"], "Hi5-A4-120PGS-CB-BP-SL")
		self.assertIsNone(c["carton"])

	def test_hi5_packing_deducts_only_inserts(self):
		p = r.plan("packing", 2, {"ins": 1000, "fg": 0, "carton": 0}, {"cartons": 2},
			books_per_carton=102, carton_enabled=False, item=r.codes("Hi5|A4|120|SL"))
		self.assertTrue(p["ok"])
		self.assertEqual([(row["key"], row["qty"]) for row in p["rows"]], [("ins", -102), ("fg", 204)])
		self.assertTrue(any("Hi5 packing does not deduct" in message for level, message in p["msgs"]))

	def test_ups(self):
		self.assertEqual(r.ups_from_name("Prince Cover - A5 - 120 Pages - Single Line - 3 up"), 3)
		self.assertEqual(r.ups_from_name("no count", "A4"), 2)


class TestMachines(unittest.TestCase):
	ROWS = [
		{"name": "Miller", "asset": "PRINTING MACHINE 05", "eb_stations": "Covers", "display_order": 20},
		{"name": "Solna", "asset": "ACC-ASS-2024-00010", "eb_stations": "covers\nFolds", "display_order": 10},
		{"name": "M1", "asset": "", "eb_stations": None, "display_order": 10},
		{"name": "Kord", "asset": "", "eb_stations": "Covers", "display_order": 0},
	]

	def test_grouped_by_station_in_display_order_with_zero_last(self):
		got = r.machines_by_station(self.ROWS)
		self.assertEqual([m["name"] for m in got["covers"]], ["Solna", "Miller", "Kord"])
		self.assertEqual([m["name"] for m in got["folds"]], ["Solna"])
		self.assertNotIn("inserts", got)

	def test_adding_a_machine_is_only_a_new_row(self):
		rows = self.ROWS + [{"name": "New Press", "asset": "X", "eb_stations": "Covers", "display_order": 30}]
		self.assertIn("New Press", [m["name"] for m in r.machines_by_station(rows)["covers"]])

	def test_a_station_with_machines_needs_one(self):
		by = r.machines_by_station(self.ROWS)
		with self.assertRaises(r.CaptureError):
			r.check_machine("covers", "", by)

	def test_the_machine_must_serve_the_station(self):
		by = r.machines_by_station(self.ROWS)
		self.assertEqual(r.check_machine("covers", "Solna", by)["asset"], "ACC-ASS-2024-00010")
		with self.assertRaises(r.CaptureError):
			r.check_machine("folds", "Miller", by)
		with self.assertRaises(r.CaptureError):
			r.check_machine("covers", "M1", by)

	def test_a_station_without_machines_posts_without_one(self):
		self.assertIsNone(r.check_machine("packing", "", r.machines_by_station(self.ROWS)))
		with self.assertRaises(r.CaptureError):
			r.check_machine("packing", "Solna", r.machines_by_station(self.ROWS))

	def test_a_typo_in_stations_is_reported(self):
		self.assertEqual(r.unknown_stations("Covers\nCover\n\nfolds"), ["Cover"])

	def test_remarks_carry_machine_and_asset_and_keep_the_audit_line_first(self):
		text = r.remarks("covers", "Swara|A4|120|SL", "EBR-1", {"machine": "Solna", "asset": "ACC-ASS-2024-00010"})
		self.assertTrue(text.startswith("Capture v3 · run EBR-1"))
		self.assertIn("Machine Solna (asset ACC-ASS-2024-00010)", text)


class TestPlan(unittest.TestCase):
	def stock(self, **k):
		s = {"cov": 0, "fld": 0, "ins": 0, "fg": 0, "carton": 0}
		s.update(k)
		return s

	def test_covers(self):
		p = r.plan("covers", 3, self.stock(cov=100), {"good": "1,000", "spoiled": 12}, item=r.codes(A5))
		self.assertTrue(p["ok"])
		self.assertEqual(p["type"], "Material Receipt")
		self.assertEqual([(x["dir"], x["item"], x["qty"], x["after"]) for x in p["rows"]], [("in", "COV-PNC-A5-120PG-SL", 1000, 1100)])
		self.assertIn("3,000 books", p["msgs"][-1][1])

	def test_inserts_block_on_folds(self):
		p = r.plan("inserts", 3, self.stock(cov=500, fld=10), {"sets": 100}, item=r.codes(A5))
		self.assertFalse(p["ok"])
		self.assertTrue(any("Not enough folds" in m[1] for m in p["msgs"]))
		held = r.plan("inserts", 3, self.stock(cov=500, fld=10), {"sets": 100, "hold_fold_check": 1}, item=r.codes(A5))
		self.assertTrue(held["ok"])
		self.assertEqual([x["key"] for x in held["rows"]], ["cov", "ins"])

	def test_inserts_full(self):
		p = r.plan("inserts", 2, self.stock(cov=500, fld=500, ins=7), {"sets": 100}, item=r.codes(A4))
		self.assertTrue(p["ok"])
		self.assertEqual([(x["key"], x["qty"]) for x in p["rows"]], [("cov", -100), ("fld", -100), ("ins", 100)])

	def test_packing(self):
		# 2 cartons x 186 + 5 loose = 377 books, 1 reject -> 378/3 = 126 sets, 0 over
		p = r.plan("packing", 3, self.stock(ins=200, carton=10, fg=0), {"cartons": 2, "loose": 5, "rejects": 1},
			books_per_carton=186, item=r.codes(A5))
		self.assertTrue(p["ok"])
		self.assertEqual(p["type"], "Manufacture")
		self.assertEqual([(x["key"], x["qty"]) for x in p["rows"]], [("ins", -126), ("carton", -2), ("fg", 377)])
		self.assertEqual(p["extra"]["rejects"], 1)
		self.assertEqual(p["extra"]["samples_due"], 1)

	def test_packing_leftover_becomes_reject(self):
		p = r.plan("packing", 2, self.stock(ins=100, carton=5), {"cartons": 0, "loose": 3}, books_per_carton=120, item=r.codes(A4))
		self.assertEqual(p["extra"]["sets"], 2)
		self.assertEqual(p["extra"]["rejects"], 1)

	def test_packing_disabled_carton_not_taken(self):
		p = r.plan("packing", 3, self.stock(ins=300, carton=0), {"cartons": 1}, books_per_carton=186,
			carton_enabled=False, item=r.codes(A5))
		self.assertTrue(p["ok"])
		self.assertNotIn("carton", [x["key"] for x in p["rows"]])

	def test_packing_needs_pack_size(self):
		with self.assertRaises(r.CaptureError):
			r.plan("packing", 3, self.stock(), {"cartons": 1}, books_per_carton=0, item=r.codes(A5))

	def test_bad_count(self):
		with self.assertRaises(r.CaptureError):
			r.plan("covers", 3, self.stock(), {"good": "1.5"}, item=r.codes(A5))

	def test_remarks(self):
		t = r.remarks("inserts", A5, "EBR-0001", {"hold_fold_check": True}, user="tanuj@vimit.com", at="2026-11-05 08:00")
		self.assertTrue(t.startswith("Capture v3 · run EBR-0001 · confirmed twice by tanuj@vimit.com at 2026-11-05 08:00"))
		self.assertIn("FOLD CHECK HELD OFF", t)

	def test_remarks_date_and_shift(self):
		import datetime
		t = r.remarks("covers", A5, "EBR-0002", {}, user="u", at="x", date=datetime.date(2026, 11, 4), shift="Night Shift")
		self.assertTrue(t.startswith("Capture v3 · run EBR-0002 · confirmed twice by u at x · Production 04-11-2026 Night Shift"))

	def test_check_when(self):
		import datetime
		today = datetime.date(2026, 11, 5)
		self.assertEqual(r.check_when("2026-11-05", "Day Shift", today), (today, "Day Shift"))
		self.assertEqual(r.check_when("2026-10-29", "Night Shift", today)[0], datetime.date(2026, 10, 29))  # 7 days back
		for bad in [("2026-11-06", "Day Shift"), ("2026-10-28", "Day Shift"), ("", "Day Shift"), ("05-11-2026", "Day Shift"),
				("2026-11-05", "Evening Shift"), ("2026-11-05", "")]:
			with self.assertRaises(r.CaptureError):
				r.check_when(bad[0], bad[1], today)

	def test_posting_time(self):
		import datetime
		today = datetime.date(2026, 11, 5)
		self.assertEqual(r.posting_time(today, "Night Shift", today, "09:12:00"), "09:12:00")
		self.assertEqual(r.posting_time(datetime.date(2026, 11, 4), "Day Shift", today, "09:12:00"), "17:00:00")
		self.assertEqual(r.posting_time(datetime.date(2026, 11, 4), "Night Shift", today, "09:12:00"), "23:00:00")


class TestBackfill(unittest.TestCase):
	ITEM = r.codes(A4)
	STOCK = {"cov": 1000, "fld": 0, "ins": 100, "fg": 0, "carton": 50}

	def plan(self, stock=None, cartons=2, **kw):
		return r.backfill_plan(2, stock or self.STOCK, {"cartons": cartons}, books_per_carton=120, item=self.ITEM, **kw)

	def test_posts_only_the_missing_inserts(self):
		b = self.plan(cartons=2)  # 240 books = 120 inserts, 100 on hand
		self.assertEqual(b["need"], 20)
		self.assertEqual(b["inserts"]["extra"], {"sets": 20, "hold_fold_check": True})
		self.assertTrue(b["packing"]["ok"])
		self.assertEqual([x["after"] for x in b["packing"]["rows"] if x["key"] == "ins"], [0])

	def test_no_folds_are_taken_when_none_are_recorded(self):
		self.assertNotIn("fld", [x["key"] for x in self.plan()["inserts"]["rows"]])

	def test_folds_are_taken_when_they_cover_the_need(self):
		b = self.plan(dict(self.STOCK, fld=500))
		self.assertFalse(b["inserts"]["extra"]["hold_fold_check"])
		self.assertIn("fld", [x["key"] for x in b["inserts"]["rows"]])

	def test_part_fold_stock_is_refused(self):
		with self.assertRaisesRegex(r.CaptureError, "Not enough folds"):
			self.plan(dict(self.STOCK, fld=5))

	def test_short_covers_stay_blocked(self):
		with self.assertRaisesRegex(r.CaptureError, "Not enough covers"):
			self.plan(dict(self.STOCK, cov=10))

	def test_short_cartons_refuse_before_anything_posts(self):
		with self.assertRaisesRegex(r.CaptureError, "empty cartons"):
			self.plan(dict(self.STOCK, carton=1))

	def test_nothing_to_back_post(self):
		with self.assertRaisesRegex(r.CaptureError, "enough inserts"):
			self.plan(cartons=1)

	def test_no_count(self):
		with self.assertRaisesRegex(r.CaptureError, "Enter the full cartons"):
			self.plan(cartons=0)

	def test_closes_after_three_weeks(self):
		self.assertTrue(r.backfill_open(datetime.date(2026, 11, 26)))
		self.assertFalse(r.backfill_open(datetime.date(2026, 11, 27)))


if __name__ == "__main__":
	unittest.main()
