import unittest

from production_log.production_floor.receiving_books import (
	SAMPLE_OFF, SAMPLE_OK, SAMPLE_SHORT, CountError, book_dims, book_stock_lines, book_total,
	format_samples, parse_count, parse_pack, parse_samples, sample_check, samples_due,
)


class TestBooks(unittest.TestCase):
	def test_samples_due_is_about_five_percent_never_below_one(self):
		self.assertEqual(samples_due(0), 0)
		self.assertEqual(samples_due(1), 1)
		self.assertEqual(samples_due(20), 1)
		self.assertEqual(samples_due(21), 2)
		self.assertEqual(samples_due(42), 3)

	def test_counts_accept_loose_input(self):
		self.assertEqual(parse_count(" 1,200 ", "cartons"), 1200)
		self.assertEqual(parse_count("", "loose books"), 0)
		with self.assertRaises(CountError):
			parse_count("2.5", "cartons")
		with self.assertRaises(CountError):
			parse_pack("0")

	def test_book_total(self):
		self.assertEqual(book_total(42, 100, 30), 4230)

	def test_samples_round_trip_keeps_decimal_commas(self):
		self.assertEqual(parse_samples("4,2; 4.3"), [4.2, 4.3])
		self.assertEqual(format_samples([4.2, 4.35]), "4.2; 4.35")

	def test_sample_check(self):
		self.assertEqual(sample_check([4.2], 2)[0], SAMPLE_SHORT)
		self.assertEqual(sample_check([4.2, 4.25, 4.22], 3)[0], SAMPLE_OK)
		flag, note = sample_check([4.2, 4.25, 4.9], 3)
		self.assertEqual(flag, SAMPLE_OFF)
		self.assertIn("#3", note)

	def test_book_dims(self):
		d = book_dims("Hi5-A4-120PGS-CB-BP-SL", "Hi5 Exercise Book - A4 - 120 Pages - Single Line - Chipboard", "Brand Exercise Book - Hi5")
		self.assertEqual(d, {"brand": "Hi5", "size": "A4", "pages": 120})

	def test_stock_lines_sum_books_per_item(self):
		lines = book_stock_lines([{"item": "A", "books": 100, "cartons": 1}, {"item": "A", "books": 50, "cartons": 0}, {"item": "B", "books": 0}])
		self.assertEqual(lines, [{"item": "A", "qty": 150, "cartons": 1}])


if __name__ == "__main__":
	unittest.main()
