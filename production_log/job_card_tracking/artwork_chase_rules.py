"""Which specifications are still not saying where their artwork is.

Frappe-free, on the same terms as :mod:`cps_cp_rules`: every function takes
plain data and returns plain data, so the whole ruleset can be unit tested
without a bench, a site or a database. The Frappe-bound caller is
``production_log.api.artwork_chase``.

This exists because the artwork rule stopped being a gate. Until 2026-08-07 a
Printed Computer Paper specification could not be submitted without an attached
file; that was removed, because thirty-nine of the forty-three submitted
Printed specifications had nothing in the field and a rule the work routes
around is a delay rather than a control. Asking weekly is what replaced it.

Three things decide the list, and each of them is a judgement rather than an
implementation detail:

**The cutoff.** Artwork was first asked for by patch ``v8_3`` on 2026-07-23.
Before that date nobody was ever asked, and the numbers say so plainly — every
one of the thirty-eight specifications submitted between March and June carries
no file, and four of the five submitted after the rule landed do. Chasing the
earlier ones is chasing a question that was never put, which trains people to
ignore the email. They are excluded by date, not by pretending they are fine.

**Cancelled specifications are not chased.** A cancelled record is not going to
production and its artwork is nobody's outstanding work.

**Drafts are not chased either.** A draft is still being written; the artwork
arriving after the sizes and the colours is the normal order of things and was
the original reason the rule was a submit rule rather than a save rule. What is
worth an email is a *submitted* specification — one that production can pick up
— with nothing recorded about what it is plated from.
"""

# The release that first asked for artwork at all. Specifications created
# before this were never asked, so they are not chased. Moving this date is the
# one knob on the whole report: widen it to include the historical backlog,
# narrow it to start from a clean slate.
ARTWORK_CHASE_FROM = "2026-07-23"

# Only Computer Paper carries the artwork fields today. Widening the report to
# another product line means that line has somewhere to record artwork first,
# which is a separate decision with its own discovery.
COMPUTER_PAPER = "Computer Paper"
PRINT_TYPE_PRINTED = "Printed"

# Submitted only. See the module docstring — 0 is still being written and 2 is
# not going to production.
DOCSTATUS_SUBMITTED = 1


def _text(value):
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def _checked(value):
	return bool(value) and str(value).strip() not in ("0", "false", "False")


def artwork_state(row):
	"""What this specification says about its artwork.

	``"file"`` an attached file, ``"tracker"`` a Design and Artwork Tracker job,
	``"deferred"`` somebody has said the design is still being drawn, ``None``
	nothing has been said at all.

	Deliberately the same vocabulary as ``cps_cp_rules.artwork_evidence`` so the
	form, the submit path and this report cannot drift into three accounts of
	one thing. It is re-implemented rather than imported because this module
	reads report rows — dicts straight off a query — and that one takes a
	document; keeping them apart is what lets both stay Frappe-free.
	"""
	if _text(row.get("artwork")):
		return "file"
	if _text(row.get("artwork_tracker")):
		return "tracker"
	if _checked(row.get("artwork_not_ready")):
		return "deferred"
	return None


def is_outstanding(row, cutoff=ARTWORK_CHASE_FROM):
	"""Whether this row belongs on the chase.

	Note that ``"deferred"`` is NOT outstanding. Somebody has answered the
	question — the answer is "not yet" — and emailing them about it every Friday
	is how a useful report becomes one nobody opens. It shows in the summary
	count instead, so a specification cannot be deferred and then forgotten.
	"""
	if row.get("product_type") != COMPUTER_PAPER:
		return False
	if _text(row.get("print_type")) != PRINT_TYPE_PRINTED:
		return False
	if int(row.get("docstatus") or 0) != DOCSTATUS_SUBMITTED:
		return False
	if (row.get("creation") or "")[:10] < cutoff:
		return False
	return artwork_state(row) is None


def select_outstanding(rows, cutoff=ARTWORK_CHASE_FROM):
	"""The chase list, oldest first.

	Oldest first because age is the whole argument the email is making: a
	specification that has been in production for six weeks with nothing said
	about its artwork is a different problem from one submitted on Thursday.
	"""
	outstanding = [r for r in rows if is_outstanding(r, cutoff)]
	return sorted(outstanding, key=lambda r: (r.get("creation") or "", r.get("name") or ""))


def summarise(rows, cutoff=ARTWORK_CHASE_FROM):
	"""Counts for the whole in-scope population, not just the chase list.

	The bare chase list cannot tell "nothing outstanding" from "the report is
	broken", which is the failure mode of every silent weekly email. Reporting
	what was looked at alongside what was found makes an empty week legible.
	"""
	in_scope = [
		r for r in rows
		if r.get("product_type") == COMPUTER_PAPER
		and _text(r.get("print_type")) == PRINT_TYPE_PRINTED
		and int(r.get("docstatus") or 0) == DOCSTATUS_SUBMITTED
		and (r.get("creation") or "")[:10] >= cutoff
	]
	counts = {"in_scope": len(in_scope), "file": 0, "tracker": 0, "deferred": 0, "outstanding": 0}
	for row in in_scope:
		counts[artwork_state(row) or "outstanding"] += 1
	return counts


def age_in_days(row, today):
	"""Days since the specification was created. ``today`` is passed in, never
	read from the clock, so the report is reproducible and testable."""
	from datetime import date

	created = (row.get("creation") or "")[:10]
	if not created:
		return 0
	y, m, d = (int(part) for part in created.split("-"))
	return (today - date(y, m, d)).days
