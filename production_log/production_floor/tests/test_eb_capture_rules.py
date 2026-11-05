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
			r.parse_group("Hi5|A4|96|SL")

	def test_ups(self):
		self.assertEqual(r.ups_from_name("Prince Cover - A5 - 120 Pages - Single Line - 3 up"), 3)
		self.assertEqual(r.ups_from_name("no count", "A4"), 2)


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


if __name__ == "__main__":
	unittest.main()
