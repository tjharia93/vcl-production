"""The arithmetic behind the Job Card Label Run Log.

Imports nothing from Frappe, so it is tested under plain ``unittest``
(``test_label_run_rules.py``). ``JobCardLabel.set_run_log`` parses the
datetimes, calls these, and turns an out-of-order pair into a message.

The Run Log exists to cost short runs from what the press actually took rather
than the costing tool's assumed hour of setup, so a minute figure is only ever
written from two real timestamps. A missing stamp leaves the segment empty; it
is never guessed.
"""

# (minutes field, start stamp, end stamp) — in the order the press runs them.
SEGMENTS = (
	("setup_mins", "setup_start", "first_good_label"),
	("run_mins", "first_good_label", "run_end"),
	("washup_mins", "run_end", "washup_end"),
)

MINUTE_PRECISION = 1

# Parent rollup field -> child field it sums.
TOTALS = (
	("total_good_labels", "good_labels"),
	("total_setup_waste_m", "setup_waste_m"),
	("total_setup_mins", "setup_mins"),
	("total_run_mins", "run_mins"),
)


def run_minutes(stamps):
	"""Minutes for each segment of one run.

	``stamps`` maps each stamp fieldname to a ``datetime`` or ``None``.

	Returns ``(minutes, out_of_order)``: ``minutes`` maps each minutes field to
	a float, or ``None`` when either stamp is missing; ``out_of_order`` lists the
	``(start, end)`` stamp pairs whose end is earlier than their start. A
	segment that is out of order gets no minutes — a negative duration is never
	returned.
	"""
	minutes = {}
	out_of_order = []

	for minutes_field, start_field, end_field in SEGMENTS:
		start = stamps.get(start_field)
		end = stamps.get(end_field)

		if start is None or end is None:
			minutes[minutes_field] = None
			continue

		if end < start:
			minutes[minutes_field] = None
			out_of_order.append((start_field, end_field))
			continue

		minutes[minutes_field] = round((end - start).total_seconds() / 60, MINUTE_PRECISION)

	return minutes, out_of_order


def run_log_totals(rows):
	"""The card's rollups from its Run Log rows. Empty values count as zero."""
	totals = {}

	for total_field, row_field in TOTALS:
		totals[total_field] = sum((row.get(row_field) or 0) for row in rows)

	totals["total_good_labels"] = int(totals["total_good_labels"])

	for total_field in ("total_setup_waste_m", "total_setup_mins", "total_run_mins"):
		totals[total_field] = round(float(totals[total_field]), 3)

	return totals
