"""Stores receiving rules for exercise books.

Plain Python, no Frappe, held still by tests/test_receiving_books.py.

Exercise books are COUNTED, not weighed one by one (Tanuj, 03 Nov 2026): stores
picks the book, counts full cartons and loose books, and spot-weighs about 5% of
the cartons. Books per carton is the Item's "Carton" unit. There is no weight
standard yet, so the spot weights are checked against each other: a carton far
from the others in its sample is flagged, and the weights build the standard.
"""

import math
import re

from production_log.production_floor.receiving import WeightError, parse_weight

PRODUCT_TYPE = "Exercise books"
SAMPLE_PCT = 5.0
# A spot weight this far (%) from the middle of its sample is called out.
SAMPLE_SPREAD_PCT = 5.0
# Nobody packs this many books in one carton; past it is a typo.
MAX_BOOKS_PER_CARTON = 1000

SAMPLE_OK = "ok"
SAMPLE_OFF = "off"
SAMPLE_SHORT = "short"


class CountError(ValueError):
	pass


def parse_count(value, what, allow_zero=True):
	"""A whole, non-negative count. Loose input: spaces and thousands commas."""
	text = str(value if value is not None else "").replace(",", "").replace(" ", "").strip()
	if text == "":
		if allow_zero:
			return 0
		raise CountError(f"Enter the {what}.")
	try:
		n = float(text)
	except ValueError:
		raise CountError(f"'{value}' is not a number of {what}.")
	if n < 0 or n != int(n):
		raise CountError(f"The {what} has to be a whole number.")
	if not allow_zero and n == 0:
		raise CountError(f"The {what} has to be more than zero.")
	return int(n)


def parse_pack(value):
	pack = parse_count(value, "books per carton", allow_zero=False)
	if pack > MAX_BOOKS_PER_CARTON:
		raise CountError(f"{pack} books in one carton is not right. Check the number.")
	return pack


def book_total(cartons, books_per_carton, loose_books):
	return int(cartons or 0) * int(books_per_carton or 0) + int(loose_books or 0)


def samples_due(cartons, pct=SAMPLE_PCT):
	"""How many cartons to spot-weigh: about pct% of them, never fewer than one."""
	cartons = int(cartons or 0)
	if cartons <= 0:
		return 0
	return min(cartons, max(1, math.ceil(cartons * pct / 100.0 - 1e-9)))


def parse_samples(value):
	"""Spot weights as a list of kg. Accepts a list or text like '4.2, 4.3'."""
	if value is None:
		return []
	items = value if isinstance(value, (list, tuple)) else re.split(r"[;\n]|,(?=\s)|\s+", str(value))
	out = []
	for v in items:
		if str(v).strip() == "":
			continue
		out.append(parse_weight(v))
	return out


def format_samples(weights):
	# "; " not ", ": a decimal comma (4,2) must not split a weight in two.
	return "; ".join(f"{w:.3f}".rstrip("0").rstrip(".") for w in weights)


def _median(values):
	s = sorted(values)
	mid = len(s) // 2
	return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def sample_check(weights, due, spread_pct=SAMPLE_SPREAD_PCT):
	"""(flag, note) for one line's spot weights.

	short: fewer weighed than due. off: a weight more than spread_pct from the
	middle of the sample (needs two or more). ok otherwise - with one weight
	there is nothing to compare, which is still ok: it is recorded.
	"""
	weights = list(weights or [])
	if len(weights) < int(due or 0):
		left = int(due) - len(weights)
		return SAMPLE_SHORT, f"Weigh {left} more carton{'s' if left != 1 else ''}."
	if len(weights) >= 2:
		mid = _median(weights)
		off = [(i, w) for i, w in enumerate(weights, start=1) if mid and abs(w - mid) / mid * 100.0 > spread_pct + 1e-9]
		if off:
			parts = [f"#{i} {w:.2f} kg is {abs(w - mid) / mid * 100.0:.0f}% {'over' if w > mid else 'under'}" for i, w in off]
			return SAMPLE_OFF, "; ".join(parts) + f" the others ({mid:.2f} kg). Check the count in {'that carton' if len(off) == 1 else 'those cartons'}."
	return SAMPLE_OK, ""


_SIZE = re.compile(r"\b(A[0-6]|B[0-6]|Foolscap|Quarto)\b", re.I)
_PAGES = re.compile(r"\b(\d+)\s*(?:pages?|pgs?)\b", re.I)
_BRAND_PREFIX = re.compile(r"^(?:Brand\s+Exercise\s+Books?|School\s+Exercise)\s*[-:]?\s*", re.I)


def book_dims(code, name, group):
	"""Brand / size / pages for the picker, read from the code, name and item group.

	Same reading as the Exercise Book tracker on /production-dev. Anything not
	found is None, so the picker can put it under 'Other'.
	"""
	text = f"{code or ''} {name or ''}"
	text_spaced = re.sub(r"[-_]", " ", text)
	size = _SIZE.search(text_spaced)
	pages = _PAGES.search(text_spaced)
	brand = _BRAND_PREFIX.sub("", group or "").strip()
	if not brand or re.fullmatch(r"exercise\s*books?", brand, re.I):
		brand = None
	return {
		"brand": brand,
		"size": size.group(1).upper() if size else None,
		"pages": int(pages.group(1)) if pages else None,
	}


def book_stock_lines(rows):
	"""What the Stock Entry carries: one line per item, books (Nos) as qty."""
	by_item = {}
	for row in rows:
		item = row.get("item")
		books = int(row.get("books") or 0)
		if not item or books <= 0:
			continue
		line = by_item.setdefault(item, {"item": item, "qty": 0, "cartons": 0})
		line["qty"] += books
		line["cartons"] += int(row.get("cartons") or 0)
	return list(by_item.values())


def book_tally(rows):
	out = {"lines": 0, "cartons": 0, "loose": 0, "books": 0, "samples_due": 0, "samples": 0, "short": 0, "off": 0}
	for row in rows:
		out["lines"] += 1
		out["cartons"] += int(row.get("cartons") or 0)
		out["loose"] += int(row.get("loose_books") or 0)
		out["books"] += int(row.get("books") or 0)
		out["samples_due"] += int(row.get("samples_due") or 0)
		out["samples"] += len(parse_samples(row.get("sample_weights")))
		flag = row.get("sample_flag")
		if flag == SAMPLE_SHORT:
			out["short"] += 1
		elif flag == SAMPLE_OFF:
			out["off"] += 1
	return out


__all__ = [
	"PRODUCT_TYPE", "SAMPLE_PCT", "SAMPLE_SPREAD_PCT", "SAMPLE_OK", "SAMPLE_OFF", "SAMPLE_SHORT",
	"CountError", "WeightError", "parse_count", "parse_pack", "book_total", "samples_due", "parse_samples",
	"format_samples", "sample_check", "book_dims", "book_stock_lines", "book_tally",
]
