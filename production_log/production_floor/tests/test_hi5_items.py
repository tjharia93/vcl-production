import unittest
from production_log.production_floor.setup.hi5_items import planned_items


class TestHi5Setup(unittest.TestCase):
	def test_active_books_make_three_stages_without_cartons_or_transactions(self):
		docs = planned_items([{"name": "Hi5-A4-120PGS-CB-BP-SL", "disabled": 0}])
		self.assertEqual(len(docs), 3)
		self.assertTrue(all(d["doctype"] == "Item" and d["stock_uom"] == "Nos" for d in docs))
		self.assertTrue(all(d["item_name"].endswith("2 up") for d in docs))
		self.assertFalse(any("opening_stock" in d for d in docs))

	def test_disabled_variants_do_not_create_stage_items(self):
		self.assertEqual(planned_items([{"name": "Hi5-A4-32PGS-CB-BP-SL", "disabled": 1}]), [])

	def test_cover_variants_share_the_same_intermediates(self):
		docs = planned_items([{"name": "Hi5-A5-120PGS-CB-BP-SL"}, {"name": "Hi5-A5-120PGS-HC-BP-SL"}])
		self.assertEqual(len(docs), 3)
		self.assertTrue(all(d["item_name"].endswith("3 up") for d in docs))
