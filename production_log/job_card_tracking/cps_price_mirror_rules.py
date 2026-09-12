"""Pure decision rules for mirroring approved CPS prices into the price list.

Like :mod:`cps_rules`, this module imports nothing from Frappe. Every function
takes plain data and returns plain data, so the rules are unit testable without
a bench. The Frappe-bound caller is :mod:`cps_price_mirror`.

The decision recorded on 2026-09-12 (Tanuj): a printed job's price is typed and
approved on the specification; the price list is kept in step by a script. The
CPS is the authority and Item Price is derived.

Why this is not a straight copy
-------------------------------
Item Price is unique on item + price list + customer + UOM + date range — one
row per combination, enforced by ERPNext. That is fine when an Item is a
product. It is false when an Item is a *construction*: ``3PLY PRINTED CARTON``
carries six active specifications across five customers (a five-litre carton, a
rat-and-mice-killer carton, a cosmetics carton, an air-filter carton). The Item
describes how the board is built; the product is the spec.

So NOVEL MANUFACTURING CO LTD holds two live specs on that one Item at two
different rates, and no single Item Price row can be true for both. The rule
below mirrors where the candidate specs agree and refuses where they disagree —
refusing on ambiguity alone would also refuse NATIONAL PRINTING PRESS, whose two
specs sit at the same rate and mirror perfectly safely.
"""

from collections import namedtuple
from datetime import date

from production_log.job_card_tracking import cps_rules

# The price list the mirror writes to. Standard Selling with ``customer`` set on
# the row, which is how every customer-specific price in the system already
# works and how ERPNext's own price resolution finds one.
PRICE_LIST = "Standard Selling"

# Domestic VAT. Every rate VCL agrees is struck at 16%; if that ever stops being
# true this constant is the place it has to be dealt with, not a silent drift.
VAT_RATE = 0.16

# A specification that agreed the rate, for a key that more than one spec feeds.
MirrorKey = namedtuple("MirrorKey", ("customer", "item_code", "uom"))

# ``cps`` is the spec that supplied the rate; ``agreeing`` is every spec that
# resolves to this key, the supplier included. Stored so the price list row can
# name its source and the note can name the rest.
# ``gross`` is the original figure when the winning spec's rate was VAT-inclusive
# and had to be converted, otherwise None — so the price-list note can say a
# conversion happened rather than leaving an unexplained number.
MirrorTarget = namedtuple("MirrorTarget", ("key", "rate", "cps", "agreeing", "gross"))

# ``rates`` is [(cps, rate), ...] for every spec on the key, so the refusal can
# say precisely what the price list is unable to express.
MirrorRefusal = namedtuple("MirrorRefusal", ("key", "rates"))

MirrorPlan = namedtuple("MirrorPlan", ("targets", "refusals", "unmappable"))

# What to do with one target once the live Item Price row is known.
ACTION_INSERT = "insert"
ACTION_SUPERSEDE = "supersede"
ACTION_UNCHANGED = "unchanged"
ACTION_SKIP_UNOWNED = "skip_unowned"

WriteDecision = namedtuple("WriteDecision", ("action", "rate", "supersedes"))


def to_ex_vat(rate, vat_inclusive):
	"""Convert a CPS rate to the ex-VAT basis the price list is on.

	CPS Price labels its rate "Rate (net, ex-VAT)" and all but one live row obeys
	that. The exception is deliberate and documented on the specification:
	BAHATI VENTURES' coffee cup sleeve is agreed at 1.70 per piece INCLUSIVE, and
	the Sales Order is raised at 1.70 with VAT "included in print rate" so 50,000
	pieces bill exactly 85,000. Entering the ex-VAT 1.4655 instead was tried on
	2026-08-31 and failed — it rounded to 1.47 on submit and billed 73,500.

	So the gross rate has to stay on the specification, and the conversion has to
	happen here. Item Price is ex-VAT; copying a gross rate into it would publish
	that customer's price 16% high.
	"""
	if rate is None:
		return None
	if not vat_inclusive:
		return cps_rules.round_rate(rate)
	return cps_rules.round_rate(float(rate) / (1.0 + VAT_RATE))


def _sort_key(spec):
	"""Newest effective date wins, then the spec name, so runs are repeatable.

	Two specs agreeing on a rate still have to yield ONE row, and which of them
	the row names must not depend on dict ordering — otherwise a re-run rewrites
	the same price with a different source and the audit trail churns.
	"""
	return (cps_rules.to_date(spec.get("valid_from")) or date.min, spec.get("cps") or "")


def plan_mirror(priced_specs, unmappable=0):
	"""Work out what the price list should say, and where it cannot say anything.

	``priced_specs`` is an iterable of dicts, one per Active specification that
	carries both a ``linked_item`` and an approved price in effect on the run
	date::

		{"cps", "customer", "item_code", "uom", "rate", "valid_from", "vat_inclusive"}

	``rate`` is taken on the specification's own basis and converted to ex-VAT
	here, because the price list has only one basis and the specification does
	not.

	``unmappable`` starts at the count the caller already knows about — specs
	with an approved price but no ``linked_item``, which have nowhere in the
	price list to go — and grows by any spec here that is missing part of its
	key. It is reported rather than dropped, because that count IS the data job.

	Returns a :class:`MirrorPlan`. Nothing here reads or writes anything — the
	plan is the dry run, and the dry run is the acceptance test.
	"""
	buckets = {}
	for spec in priced_specs or []:
		customer = spec.get("customer")
		item_code = spec.get("item_code")
		uom = spec.get("uom")
		gross = spec.get("rate") if spec.get("vat_inclusive") else None
		rate = to_ex_vat(spec.get("rate"), spec.get("vat_inclusive"))
		# A spec missing any part of the key, or carrying no rate, cannot be
		# placed in the price list at all. Silently dropping it would overstate
		# coverage, so it is counted as unmappable rather than ignored.
		if not (customer and item_code and uom) or rate is None:
			unmappable += 1
			continue
		buckets.setdefault(MirrorKey(customer, item_code, uom), []).append(
			dict(spec, rate=rate, gross=gross)
		)

	targets, refusals = [], []
	for key, specs in buckets.items():
		distinct = {s["rate"] for s in specs}
		if len(distinct) > 1:
			refusals.append(
				MirrorRefusal(
					key,
					sorted(((s.get("cps"), s["rate"]) for s in specs), key=lambda r: r[0] or ""),
				)
			)
			continue
		winner = sorted(specs, key=_sort_key, reverse=True)[0]
		targets.append(
			MirrorTarget(
				key,
				winner["rate"],
				winner.get("cps"),
				sorted(s.get("cps") for s in specs if s.get("cps")),
				winner.get("gross"),
			)
		)

	targets.sort(key=lambda t: (t.key.customer, t.key.item_code, t.key.uom))
	refusals.sort(key=lambda r: (r.key.customer, r.key.item_code, r.key.uom))
	return MirrorPlan(targets, refusals, unmappable)


def decide_write(target_rate, existing):
	"""Decide what to do with one target given the live Item Price row.

	``existing`` is the customer-scoped row in effect today, or ``None``::

		{"name", "price_list_rate", "cps"}

	``cps`` is the mirror's ownership mark. **A row without one was made by a
	person and is never touched** — not the twelve customer prices that predate
	this, and not the three set from invoices on 2026-09-11. The mirror owning
	only its own rows is the difference between a script and a liability.
	"""
	target_rate = cps_rules.round_rate(target_rate)
	if existing is None:
		return WriteDecision(ACTION_INSERT, target_rate, None)
	if not existing.get("cps"):
		return WriteDecision(ACTION_SKIP_UNOWNED, target_rate, existing.get("name"))
	if cps_rules.round_rate(existing.get("price_list_rate")) == target_rate:
		return WriteDecision(ACTION_UNCHANGED, target_rate, existing.get("name"))
	return WriteDecision(ACTION_SUPERSEDE, target_rate, existing.get("name"))


def plan_withdrawals(owned_rows, live_keys):
	"""Owned price-list rows whose specification no longer offers a price.

	Editing an approved rate returns the row to Draft (``revoke_approval_on_edit``)
	and a rejection does the same. Either way the price stops being one VCL has
	agreed, and a withdrawn price left standing in the price list is worse than
	one that never arrived — somebody will quote it.

	``owned_rows`` carry ``{"name", "customer", "item_code", "uom"}`` and only
	ever include rows the mirror owns; ``live_keys`` is the set of
	:class:`MirrorKey` the current plan still writes.
	"""
	live = set(live_keys or ())
	out = []
	for row in owned_rows or []:
		key = MirrorKey(row.get("customer"), row.get("item_code"), row.get("uom"))
		if key not in live:
			out.append(row)
	return sorted(out, key=lambda r: (r.get("customer") or "", r.get("item_code") or ""))


def refusal_digest(refusals):
	"""A stable one-line-per-refusal fingerprint, for 'has this changed?'.

	The daily sweep mails only when the refusal set moves. A mail that says
	"still Novel" every morning trains the reader to ignore the one that says
	something new.
	"""
	lines = []
	for r in sorted(refusals or [], key=lambda r: (r.key.customer, r.key.item_code, r.key.uom)):
		rates = " / ".join(f"{cps}={rate}" for cps, rate in r.rates)
		lines.append(f"{r.key.customer}|{r.key.item_code}|{r.key.uom}|{rates}")
	return "\n".join(lines)
