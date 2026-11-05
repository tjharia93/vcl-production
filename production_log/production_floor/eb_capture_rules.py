"""Exercise-book capture v3: the stock rules, no Frappe.

Held still by tests/test_eb_capture_rules.py. The page (exercise-book-production/
dev-page-v3/page.js, function planEntry) mirrors these rules for its Preview; the
server (eb_capture.post_entry) re-runs them against live stock before it posts.

Decided by Tanuj, 04/11/2026:
- Covers, folds and inserts count in SETS with the same up-count (A4 2-up, A5 3-up,
  read from the item name). 1 cover sheet + 1 fold set = 1 insert set. Only
  packing counts books.
- Covers: Material Receipt of COV-x into Stores - VCL, spoiled sheets recorded only.
- Folds: Material Receipt of FLD-x fold sets into Stores - VCL, rejects recorded only.
- Inserts: Repack, NO BOM (P11). Out COV-x x sets and FLD-x x sets, in INS-x x sets.
  Blocked when either is short (negative stock is off), unless the fold check is
  held off (until the first fold count); the hold is logged on the entry.
- Packing: Manufacture into Finished Goods - VCL. Books = full cartons x books per
  carton + loose. Out INS-x = ceil((books + rejects) / ups) sets and the empty
  cartons. Books left over in the last set become rejects. Spot-weigh 1 in 20.

Tanuj, 05/11/2026: every entry carries a production date and shift. The date is
today or up to BACKDATE_DAYS back, never ahead; the shifts are PPC's (Day / Night).
"""

import datetime
import math
import re

STORES = "Stores - VCL"
FG = "Finished Goods - VCL"
COMPANY = "Vimit Converters Limited"
MARKER = "Capture v3"

STATIONS = ("covers", "folds", "inserts", "packing")

ENTRY_TYPE = {
	"covers": "Material Receipt",
	"folds": "Material Receipt",
	"inserts": "Repack",
	"packing": "Manufacture",
}

BRAND_CODE = {"Prince": "PNC", "Swara": "SWR"}
BOOK_PREFIX = {"Prince": ("PNCEB", "BP"), "Swara": ("SWREB", "NP")}

# P12 is open (Tanuj): one common carton per size + brand, the PC proposal of 04/11/2026.
# Change it here (and in page.js CARTONS) when Tanuj decides.
CARTONS = {
	"A4|Prince": "PNC-EMPTY-CARTON-A4-EXBK-COMMON-425 x 305 x 260",
	"A4|Swara": "SWR- COMMON CARTON 280 MM",
	"A5|Prince": "PNCSWR-EMPTY-CARTON-A5-PLAINF-DPL",
	"A5|Swara": "PNCSWR-EMPTY-CARTON-A5-PLAINF-DPL",
}

SHIFTS = ("Day Shift", "Night Shift")  # same as PPC Daily Plan / Production Actual
BACKDATE_DAYS = 7
# Posting time for a back-dated entry (today's entries post at the current time).
SHIFT_POSTING_TIME = {"Day Shift": "17:00:00", "Night Shift": "23:00:00"}

SAMPLE_EVERY = 20  # spot-weigh 1 carton in 20
SAMPLE_SPREAD_PCT = 5.0

_GROUP = re.compile(r"^(Prince|Swara)\|(A4|A5)\|(\d+)\|([A-Z0-9]+)$")
_UPS = re.compile(r"(\d+)\s*up\s*$", re.I)


class CaptureError(ValueError):
	pass


def parse_group(key):
	m = _GROUP.match(str(key or "").strip())
	if not m:
		raise CaptureError(f"'{key}' is not a group (Brand|Size|Pages|Ruling).")
	brand, size, pages, ruling = m.groups()
	return {"brand": brand, "size": size, "pages": int(pages), "ruling": ruling, "key": key}


def ups_from_name(item_name, size=None):
	"""The up-count printed in the item name ('... - 3 up'); the size is the fallback."""
	m = _UPS.search(str(item_name or ""))
	if m:
		return int(m.group(1))
	if size:
		return 2 if size == "A4" else 3
	return None


def codes(group, cover="CB"):
	g = parse_group(group) if isinstance(group, str) else group
	tail = f"{BRAND_CODE[g['brand']]}-{g['size']}-{g['pages']:03d}PG-{g['ruling']}"
	prefix, paper = BOOK_PREFIX[g["brand"]]
	return {
		"cov": "COV-" + tail,
		"fld": "FLD-" + tail,
		"ins": "INS-" + tail,
		"book": f"{prefix}-{g['size']}-{g['pages']}PGS-{cover}-{paper}-{g['ruling']}",
		"carton": CARTONS.get(f"{g['size']}|{g['brand']}"),
	}


def whole(value, what):
	text = str(value if value is not None else "").replace(",", "").replace(" ", "").strip()
	if text == "":
		return 0
	try:
		n = float(text)
	except ValueError:
		raise CaptureError(f"'{value}' is not a number of {what}.")
	if n < 0 or n != int(n):
		raise CaptureError(f"The {what} has to be a whole number, 0 or more.")
	return int(n)


def samples_due(cartons):
	cartons = int(cartons or 0)
	return 0 if cartons <= 0 else max(1, math.ceil(cartons / SAMPLE_EVERY))


def plan(station, ups, stock, inputs, books_per_carton=None, carton_enabled=True, item=None):
	"""What one entry will do.

	stock: {'cov','fld','ins','fg','carton'} on hand (cover/fold/insert sets in Stores,
	books in Finished Goods, cartons in Stores). inputs: the counted numbers.
	item: the codes() dict. Returns {'ok','rows','msgs','type','extra'} where rows are
	(direction, key, item, warehouse, qty, before, unit) and qty is signed.
	"""
	if station not in STATIONS:
		raise CaptureError(f"Unknown station '{station}'.")
	item = item or {}
	ups = int(ups or 0)
	if ups <= 0:
		raise CaptureError("The up-count could not be read from the item name.")
	rows, msgs, ok, extra = [], [], True, {}

	def row(direction, key, code, wh, qty, before, unit):
		rows.append({"dir": direction, "key": key, "item": code, "warehouse": wh, "qty": qty, "before": before,
			"after": before + qty, "unit": unit})

	if station == "covers":
		good, spoiled = whole(inputs.get("good"), "good sheets"), whole(inputs.get("spoiled"), "spoiled sheets")
		if good <= 0:
			ok = False
			msgs.append(("info", "Enter the good printed sheets counted."))
		row("in", "cov", item.get("cov"), STORES, good, stock.get("cov", 0), "sheets")
		if spoiled:
			msgs.append(("info", f"{spoiled:,} spoiled sheets recorded for the run, not added to stock."))
		msgs.append(("info", f"{good:,} sheets = {good * ups:,} books ({ups}-up)."))
		extra = {"good": good, "spoiled": spoiled}

	elif station == "folds":
		good, rejects = whole(inputs.get("good"), "good fold sets"), whole(inputs.get("rejects"), "rejected fold sets")
		if good <= 0:
			ok = False
			msgs.append(("info", "Enter the good fold sets counted."))
		row("in", "fld", item.get("fld"), STORES, good, stock.get("fld", 0), "sets")
		if rejects:
			msgs.append(("info", f"{rejects:,} rejected fold sets recorded for the run, not added."))
		if inputs.get("opening"):
			msgs.append(("info", "Opening count: this is the fold stock found on the floor, not new production."))
		msgs.append(("info", f"{good:,} fold sets = {good * ups:,} books' inners."))
		extra = {"good": good, "rejects": rejects, "opening": bool(inputs.get("opening"))}

	elif station == "inserts":
		sets, hold = whole(inputs.get("sets"), "insert sets"), bool(inputs.get("hold_fold_check"))
		if sets <= 0:
			ok = False
			msgs.append(("info", "Enter the insert sets made."))
		row("out", "cov", item.get("cov"), STORES, -sets, stock.get("cov", 0), "sheets")
		if not hold:
			row("out", "fld", item.get("fld"), STORES, -sets, stock.get("fld", 0), "sets")
		row("in", "ins", item.get("ins"), STORES, sets, stock.get("ins", 0), "sets")
		if sets > stock.get("cov", 0):
			ok = False
			msgs.append(("bad", f"Not enough covers: {stock.get('cov', 0):,} sheets on hand, {sets:,} needed. Print more covers first."))
		if not hold and sets > stock.get("fld", 0):
			ok = False
			msgs.append(("bad", f"Not enough folds: {stock.get('fld', 0):,} fold sets on hand, {sets:,} needed. "
				"Post the fold count on the Folds station first, or hold off the fold check."))
		if hold:
			msgs.append(("info", "Fold check held off: folds are not taken out. Use only until the first fold count is posted; this is noted on the entry."))
		msgs.append(("info", f"{sets:,} insert sets = {sets * ups:,} books."))
		extra = {"sets": sets, "hold_fold_check": hold}

	elif station == "packing":
		cpc = int(books_per_carton or 0)
		if cpc <= 0:
			raise CaptureError("This book has no Carton conversion (books per carton), so it can't be packed yet.")
		cartons = whole(inputs.get("cartons"), "full cartons")
		loose = whole(inputs.get("loose"), "loose books")
		rejects = whole(inputs.get("rejects"), "rejected books")
		books = cartons * cpc + loose
		sets = math.ceil((books + rejects) / ups) if books + rejects else 0
		over = sets * ups - books - rejects
		if books <= 0:
			ok = False
			msgs.append(("info", "Enter the full cartons and any loose books."))
		row("out", "ins", item.get("ins"), STORES, -sets, stock.get("ins", 0), "sets")
		if cartons and carton_enabled:
			row("out", "carton", item.get("carton"), STORES, -cartons, stock.get("carton", 0), "cartons")
		row("in", "fg", item.get("book"), FG, books, stock.get("fg", 0), "books")
		if sets > stock.get("ins", 0):
			ok = False
			msgs.append(("bad", f"Not enough inserts: {stock.get('ins', 0):,} sets on hand, {sets:,} needed for {books + rejects:,} books."))
		if cartons and carton_enabled and cartons > stock.get("carton", 0):
			ok = False
			msgs.append(("bad", f"Not enough empty cartons for this book: {stock.get('carton', 0):,} on hand."))
		if cartons and not carton_enabled:
			msgs.append(("warn", "The carton item for this size is disabled in ERPNext, so empty cartons are NOT taken out on this entry. Enable it to count cartons used."))
		msgs.append(("info", f"{cartons:,} cartons x {cpc} + {loose:,} loose = {books:,} books."))
		if over > 0:
			msgs.append(("info", f"The last insert set has {over} book{'s' if over != 1 else ''} over: recorded as rejects, so rejects = {rejects + over}."))
		due = samples_due(cartons)
		if due:
			msgs.append(("info", f"Spot-weigh {due} carton{'s' if due != 1 else ''} (1 in {SAMPLE_EVERY}). Flag any more than {SAMPLE_SPREAD_PCT:g}% off."))
		extra = {"books": books, "sets": sets, "rejects": rejects + over, "cartons": cartons, "loose": loose, "samples_due": due}

	return {"ok": ok, "rows": rows, "msgs": msgs, "type": ENTRY_TYPE[station], "extra": extra}


def check_when(date, shift, today):
	"""Production date (YYYY-MM-DD or a date) and shift -> (date, shift). Raises CaptureError."""
	if isinstance(date, datetime.datetime):
		date = date.date()
	if not isinstance(date, datetime.date):
		try:
			date = datetime.date.fromisoformat(str(date or "").strip()[:10])
		except ValueError:
			raise CaptureError("Pick the production date.")
	if date > today:
		raise CaptureError("The production date can't be in the future.")
	if date < today - datetime.timedelta(days=BACKDATE_DAYS):
		raise CaptureError(f"The production date can only go back {BACKDATE_DAYS} days. Older entries: ask a Stock Manager.")
	shift = (shift or "").strip()
	if shift not in SHIFTS:
		raise CaptureError("Pick the shift (" + " or ".join(SHIFTS) + ").")
	return date, shift


def posting_time(date, shift, today, now_time):
	"""Today's entries post at the current time; back-dated ones at the shift's set time."""
	return now_time if date == today else SHIFT_POSTING_TIME[shift]


def remarks(station, group, run, extra, user_note="", user=None, at=None, date=None, shift=None):
	"""The entry's remarks. The first line is the audit line Tanuj asked for:
	"Capture v3 · run <run> · confirmed twice by <user> at <time>"; then the counts that are not stock rows."""
	audit = f"{MARKER} · run {run or '-'}"
	if user:
		audit += f" · confirmed twice by {user} at {at or ''}".rstrip()
	bits = [audit]
	if date or shift:
		d = date.strftime("%d-%m-%Y") if hasattr(date, "strftime") else (date or "")
		bits.append(f"Production {d} {shift or ''}".strip())
	bits += [f"Station {station}", f"Group {group}"]
	for k in ("spoiled", "rejects", "loose", "samples_due"):
		if extra.get(k):
			bits.append(f"{k.replace('_', ' ')} {extra[k]}")
	if extra.get("opening"):
		bits.append("opening fold count")
	if extra.get("hold_fold_check"):
		bits.append("FOLD CHECK HELD OFF (no fold count yet)")
	if extra.get("weights"):
		bits.append("spot weights " + extra["weights"])
	if user_note:
		bits.append(str(user_note)[:200])
	return " · ".join(bits)
