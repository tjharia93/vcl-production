"""Stores receiving rules for computer paper cartons.

Plain Python, no Frappe: these are the rules the floor will argue about
(what counts as light, when a run is drifting, what posts to stock), so they
live where a unit test can hold them still.

    python3 -m unittest discover -s production_log/production_floor/tests

The colours are the carton label colours on the floor legend (photo,
2026-10-17). They are pack TYPES: normal vs payslip is carried by the colour,
Green is a customer pack whose standard is per customer, Red is a rejection
and is counted but never received into stock.
"""

COLOURS = ("Yellow", "Purple", "Green", "Pink", "Blue", "Red")

COLOUR_MEANING = {
	"Yellow": "C Pack - normal size",
	"Purple": "Normal / standard pack - 9.5 x 11",
	"Green": "Customised per customer",
	"Pink": "C Pack - payslip",
	"Blue": "Payslip standard pack",
	"Red": "Rejection",
}

CUSTOMER_COLOURS = ("Green",)
REJECT_COLOURS = ("Red",)

FLAG_OK = "ok"
FLAG_LIGHT = "light"
FLAG_HEAVY = "heavy"
FLAG_UNCHECKED = "unchecked"
FLAG_REJECT = "reject"
FLAGS = (FLAG_OK, FLAG_LIGHT, FLAG_HEAVY, FLAG_UNCHECKED, FLAG_REJECT)

DEFAULT_TOLERANCE_PCT = 2.0
# After this many light cartons in a row the screen says the RUN is light, not
# the carton - the scale, the packer or the standard needs looking at.
RUN_LIGHT_STREAK = 3
# A carton of computer paper is a few kilos. Anything past this is a typo.
MAX_CARTON_KG = 50.0


class WeightError(ValueError):
	pass


def parse_weight(value):
	"""A carton weight in kg: a positive number, sane for a carton."""
	if value is None or str(value).strip() == "":
		raise WeightError("Enter the weight.")
	try:
		weight = float(str(value).strip().replace(",", "."))
	except ValueError:
		raise WeightError(f"'{value}' is not a weight.")
	if weight <= 0:
		raise WeightError("The weight has to be more than zero.")
	if weight > MAX_CARTON_KG:
		raise WeightError(f"{weight:g} kg is not one carton. Check the scale.")
	return round(weight, 3)


def tolerance_kg(standard_kg, tolerance_pct=DEFAULT_TOLERANCE_PCT):
	standard_kg = float(standard_kg or 0)
	if standard_kg <= 0:
		return 0.0
	pct = float(tolerance_pct if tolerance_pct not in (None, "") else DEFAULT_TOLERANCE_PCT)
	return round(standard_kg * pct / 100.0, 3)


def flag_for(colour, standard_kg, tol_kg, weight_kg):
	"""ok / light / heavy against the standard; unchecked when there is no
	standard; reject for a Red carton whatever it weighs."""
	if colour in REJECT_COLOURS:
		return FLAG_REJECT
	standard_kg = float(standard_kg or 0)
	if standard_kg <= 0:
		return FLAG_UNCHECKED
	weight_kg = float(weight_kg or 0)
	tol_kg = float(tol_kg or 0)
	if weight_kg < standard_kg - tol_kg - 1e-9:
		return FLAG_LIGHT
	if weight_kg > standard_kg + tol_kg + 1e-9:
		return FLAG_HEAVY
	return FLAG_OK


def variance_kg(standard_kg, weight_kg):
	if not standard_kg:
		return 0.0
	return round(float(weight_kg or 0) - float(standard_kg), 3)


def needs_customer(colour):
	return colour in CUSTOMER_COLOURS


def standard_name(colour, parts, customer=None):
	name = f"{colour} {int(parts)}P"
	if customer:
		name += f" - {customer}"
	return name


def match_standard(standards, colour, parts, customer=None):
	"""The active standard for this carton, or None.

	`standards` is a list of dicts with colour, parts, customer, active.
	A Green carton matches only its own customer's standard; a house colour
	ignores the customer entirely.
	"""
	parts = int(parts)
	want_customer = customer if needs_customer(colour) else None
	for std in standards:
		if not std.get("active", 1):
			continue
		if std.get("colour") != colour or int(std.get("parts") or 0) != parts:
			continue
		if (std.get("customer") or None) != (want_customer or None):
			continue
		return std
	return None


def tally(rows):
	"""Counts and kilos for a receipt. Rejects are counted and weighed but
	are not part of what goes to stock."""
	out = {
		"cartons": 0,
		"ok": 0,
		"light": 0,
		"heavy": 0,
		"unchecked": 0,
		"reject": 0,
		"total_kg": 0.0,
		"received_cartons": 0,
		"received_kg": 0.0,
	}
	for row in rows:
		flag = row.get("flag") or FLAG_UNCHECKED
		weight = float(row.get("weight_kg") or 0)
		out["cartons"] += 1
		out[flag] = out.get(flag, 0) + 1
		out["total_kg"] += weight
		if flag != FLAG_REJECT:
			out["received_cartons"] += 1
			out["received_kg"] += weight
	out["total_kg"] = round(out["total_kg"], 3)
	out["received_kg"] = round(out["received_kg"], 3)
	return out


def light_streak(rows, streak=RUN_LIGHT_STREAK):
	"""The standard the run has drifted light on, or None.

	Looks at the last `streak` cartons that were actually checked against a
	standard (rejects and unchecked cartons are skipped, they say nothing).
	All of them light, all on the same standard, means the run - not one
	carton - is light.
	"""
	checked = [r for r in rows if (r.get("flag") in (FLAG_OK, FLAG_LIGHT, FLAG_HEAVY))]
	if len(checked) < streak:
		return None
	last = checked[-streak:]
	keys = {(r.get("colour"), int(r.get("parts") or 0), r.get("customer") or None) for r in last}
	if len(keys) != 1:
		return None
	if all(r.get("flag") == FLAG_LIGHT for r in last):
		return standard_name(*list(keys)[0])
	return None


def stock_lines(rows):
	"""What the Stock Entry carries: one line per item and customer, cartons as qty.

	A customer pack (Green) posts to the house item for now, on its own line
	so the customer name is written on the receipt. Returns (lines, skipped). Red cartons are skipped by design. A carton
	whose standard names no ERPNext item cannot be posted and is reported
	back rather than silently dropped.
	"""
	by_item = {}
	skipped = []
	for row in rows:
		if (row.get("flag") or "") == FLAG_REJECT:
			continue
		item = row.get("item")
		if not item:
			skipped.append(row)
			continue
		customer = row.get("customer") or None
		line = by_item.setdefault((item, customer), {"item": item, "customer": customer, "qty": 0, "kg": 0.0})
		line["qty"] += 1
		line["kg"] = round(line["kg"] + float(row.get("weight_kg") or 0), 3)
	return list(by_item.values()), skipped


def describe_flag(flag, variance=None):
	if flag == FLAG_OK:
		return "OK"
	if flag == FLAG_LIGHT:
		return f"LIGHT {variance:+.2f} kg" if variance is not None else "LIGHT"
	if flag == FLAG_HEAVY:
		return f"HEAVY {variance:+.2f} kg" if variance is not None else "HEAVY"
	if flag == FLAG_REJECT:
		return "Rejection"
	return "No standard - unchecked"
