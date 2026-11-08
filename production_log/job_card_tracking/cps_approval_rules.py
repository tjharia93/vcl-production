"""Pure resolution engine for ``CPS Approval Rule`` (Stream A §6).

No Frappe import. ``resolve`` takes the candidate rule rows as plain dicts and
a context (rate, benchmarks, customer, date) and returns one
:class:`Decision`; ``may_decide`` answers whether a caller holds the authority
a decision names. The Frappe-bound half - loading rules, reading benchmarks,
writing the stamps - is :mod:`production_log.job_card_tracking.cps_approval`.

Resolution (final, 08/11/2026): candidates = enabled, in date, matching
``product_type`` and ``stage``; customer-specific before generic; then
``priority`` ascending. Each test yields one outcome: **Auto-approve** - final;
**Route** - a pending approval for ``approver_user`` / ``approver_role``, with
``fallback`` if they reject or are absent; **Continue** - abstain, next
candidate. A missing benchmark = Continue. If no rule decides: the last
candidate's ``fallback``, else Management.
"""

from collections import namedtuple

from production_log.job_card_tracking import cps_rules

STAGE_TECHNICAL = "Technical"
STAGE_PRICE = "Price"
STAGES = (STAGE_TECHNICAL, STAGE_PRICE)

TEST_ALWAYS = "Always"
TEST_RATE_GE_BENCHMARK = "Rate ≥ benchmark"
TEST_RATE_GE_MARKUP = "Rate ≥ benchmark × (1 + markup %)"
TEST_MARGIN_GE = "Margin on price ≥ %"
TESTS = (TEST_ALWAYS, TEST_RATE_GE_BENCHMARK, TEST_RATE_GE_MARKUP, TEST_MARGIN_GE)

BENCHMARK_STANDARD_SELLING = "Standard Selling Item Price"
BENCHMARK_IQ_MANAGEMENT = "IQ management_price"
BENCHMARK_IQ_COST = "IQ cost_price"
BENCHMARK_NONE = "None"
BENCHMARKS = (BENCHMARK_STANDARD_SELLING, BENCHMARK_IQ_MANAGEMENT, BENCHMARK_IQ_COST, BENCHMARK_NONE)

OUTCOME_AUTO_APPROVE = "Auto-approve"
OUTCOME_ROUTE = "Route"
OUTCOME_CONTINUE = "Continue"
OUTCOME_MANAGEMENT = "Management"

WHEN_MET_OPTIONS = (OUTCOME_AUTO_APPROVE, OUTCOME_ROUTE, OUTCOME_CONTINUE)
WHEN_NOT_MET_OPTIONS = (OUTCOME_ROUTE, OUTCOME_CONTINUE, OUTCOME_MANAGEMENT)
FALLBACK_OPTIONS = (OUTCOME_MANAGEMENT, OUTCOME_AUTO_APPROVE)

DEFAULT_MANAGEMENT_ROLE = "VCL Management Team"
APPROVER_ROLE = "CPS Approver"
SYSTEM_USER = "Administrator"

Decision = namedtuple(
	"Decision",
	(
		"outcome",          # Auto-approve | Route | Management
		"rule",             # rule_name that decided, or None
		"rule_modified",    # its `modified`, for the Comment
		"approver_user",    # for Route
		"approver_role",    # for Route
		"management_role",  # who may decide when the outcome is Management
		"fallback",         # the deciding rule's fallback (Route only)
		"benchmark",        # which benchmark was read
		"benchmark_value",  # frozen onto the row as rule_benchmark
		"allow_self_approval",
		"trail",            # [(rule_name, outcome)] in evaluation order
	),
)


def _get(row, key):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def _num(value):
	if value in (None, ""):
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


# --- Margin and markup (§6 note) ---------------------------------------------


def margin_on_price_pct(rate, cost):
	"""(rate - cost) / rate x 100. None when the rate is zero or missing."""
	rate, cost = _num(rate), _num(cost)
	if not rate or cost is None:
		return None
	return (rate - cost) / rate * 100.0


def markup_on_cost_pct(rate, cost):
	"""(rate - cost) / cost x 100. None when the cost is zero or missing."""
	rate, cost = _num(rate), _num(cost)
	if rate is None or not cost:
		return None
	return (rate - cost) / cost * 100.0


# --- Benchmark normalisation (Codex r5 item 10) --------------------------------


def normalise_benchmark(value, from_currency, to_currency, from_factor, to_factor, gross=False, vat_pct=16.0):
	"""Bring a benchmark to the row's currency and UOM, net of VAT; None if it cannot be.

	``from_factor`` / ``to_factor`` are "UOM -> stock UOM" factors. No currency
	conversion is attempted: a different currency is not comparable (None).
	"""
	amount = _num(value)
	if amount is None:
		return None
	if ((from_currency or "").strip() or "KES") != ((to_currency or "").strip() or "KES"):
		return None
	from_factor, to_factor = _num(from_factor), _num(to_factor)
	if from_factor is None and to_factor is None:
		pass
	elif not from_factor or not to_factor:
		return None
	else:
		amount = amount / from_factor * to_factor
	if gross:
		amount = amount / (1.0 + (vat_pct or 0.0) / 100.0)
	return round(amount, 9)


# --- Candidates ---------------------------------------------------------------


def _in_date(rule, on_date):
	on_date = cps_rules.to_date(on_date)
	valid_from = cps_rules.to_date(_get(rule, "valid_from"))
	valid_to = cps_rules.to_date(_get(rule, "valid_to"))
	if on_date is None:
		return valid_from is None and valid_to is None or True
	if valid_from and on_date < valid_from:
		return False
	if valid_to and on_date > valid_to:
		return False
	return True


def candidate_rules(rules, product_type, stage, customer=None, on_date=None):
	"""Enabled, in date, matching type and stage; customer-specific first, then priority."""
	wanted_type = cps_rules.normalise_product_type(product_type)
	out = []
	for rule in rules or []:
		if not int(_get(rule, "enabled") or 0):
			continue
		if _get(rule, "stage") != stage:
			continue
		if cps_rules.normalise_product_type(_get(rule, "product_type")) != wanted_type:
			continue
		rule_customer = (_get(rule, "customer") or "").strip() or None
		if rule_customer and rule_customer != (customer or "").strip():
			continue
		if not _in_date(rule, on_date):
			continue
		out.append(rule)
	return sorted(
		out,
		key=lambda r: (
			0 if (_get(r, "customer") or "").strip() else 1,
			int(_get(r, "priority") or 0),
			str(_get(r, "rule_name") or _get(r, "name") or ""),
		),
	)


# --- Tests --------------------------------------------------------------------


def evaluate_test(rule, rate, benchmark_value):
	"""True (met), False (not met) or None (cannot be evaluated -> Continue)."""
	test = _get(rule, "test") or TEST_ALWAYS
	if test == TEST_ALWAYS:
		return True

	rate = _num(rate)
	benchmark = _num(benchmark_value)
	if rate is None or benchmark is None:
		return None
	threshold = _num(_get(rule, "threshold_pct")) or 0.0

	if test == TEST_RATE_GE_BENCHMARK:
		return rate >= benchmark
	if test == TEST_RATE_GE_MARKUP:
		return rate >= benchmark * (1.0 + threshold / 100.0)
	if test == TEST_MARGIN_GE:
		margin = margin_on_price_pct(rate, benchmark)
		return None if margin is None else margin >= threshold
	return None


def rule_needs_benchmark(rule):
	return (_get(rule, "test") or TEST_ALWAYS) != TEST_ALWAYS and (_get(rule, "benchmark") or BENCHMARK_NONE) != BENCHMARK_NONE


# --- Resolution ---------------------------------------------------------------


def _decision(outcome, rule, benchmark_value, trail):
	return Decision(
		outcome,
		_get(rule, "rule_name") or _get(rule, "name") if rule is not None else None,
		str(_get(rule, "modified") or "") if rule is not None else None,
		_get(rule, "approver_user") or None if rule is not None else None,
		_get(rule, "approver_role") or None if rule is not None else None,
		(_get(rule, "management_role") or DEFAULT_MANAGEMENT_ROLE) if rule is not None else DEFAULT_MANAGEMENT_ROLE,
		(_get(rule, "fallback") or OUTCOME_MANAGEMENT) if rule is not None else OUTCOME_MANAGEMENT,
		_get(rule, "benchmark") if rule is not None else None,
		benchmark_value,
		bool(int(_get(rule, "allow_self_approval") or 0)) if rule is not None else False,
		tuple(trail),
	)


def resolve(rules, product_type, stage, rate=None, benchmarks=None, customer=None, on_date=None):
	"""Walk the candidates and return the one :class:`Decision`.

	``benchmarks`` maps a benchmark name to its value (None when absent). A
	rule whose benchmark is absent Continues. A Route whose rule names neither
	a user nor a role is an absent approver: its fallback applies at once.
	"""
	benchmarks = benchmarks or {}
	candidates = candidate_rules(rules, product_type, stage, customer, on_date)
	trail = []
	last = None

	for rule in candidates:
		last = rule
		benchmark_value = benchmarks.get(_get(rule, "benchmark")) if rule_needs_benchmark(rule) else None
		if rule_needs_benchmark(rule) and _num(benchmark_value) is None:
			trail.append((_get(rule, "rule_name"), OUTCOME_CONTINUE))
			continue

		met = evaluate_test(rule, rate, benchmark_value)
		if met is None:
			trail.append((_get(rule, "rule_name"), OUTCOME_CONTINUE))
			continue

		outcome = (_get(rule, "when_met") or OUTCOME_AUTO_APPROVE) if met else (_get(rule, "when_not_met") or OUTCOME_CONTINUE)
		if outcome == OUTCOME_CONTINUE:
			trail.append((_get(rule, "rule_name"), OUTCOME_CONTINUE))
			continue
		if outcome == OUTCOME_ROUTE and not (_get(rule, "approver_user") or _get(rule, "approver_role")):
			# Approver absent: the fallback applies immediately.
			outcome = _get(rule, "fallback") or OUTCOME_MANAGEMENT
		trail.append((_get(rule, "rule_name"), outcome))
		return _decision(outcome, rule, benchmark_value, trail)

	if last is not None:
		outcome = _get(last, "fallback") or OUTCOME_MANAGEMENT
		trail.append((_get(last, "rule_name"), "fallback -> " + outcome))
		return _decision(outcome, last, None, trail)

	trail.append((None, OUTCOME_MANAGEMENT))
	return _decision(OUTCOME_MANAGEMENT, None, None, trail)


# --- Authority ----------------------------------------------------------------


def may_decide(decision, user, roles, author=None):
	"""Whether ``user`` may approve or reject what ``decision`` routed.

	Caller = the rule's ``approver_user``, or holds ``approver_role`` or
	``management_role``. Management may always decide. Self-approval (the
	caller authored the row or revision) is refused unless the rule allows it.
	"""
	roles = set(roles or ())
	management = decision.management_role or DEFAULT_MANAGEMENT_ROLE
	allowed = management in roles
	if decision.outcome == OUTCOME_ROUTE:
		allowed = allowed or (decision.approver_user and user == decision.approver_user) or (
			decision.approver_role and decision.approver_role in roles
		)
	if not allowed:
		return False
	if author and user == author and not decision.allow_self_approval and management not in roles:
		return False
	return True


def comment_text(decision, routed_to=None):
	"""'Rule X v<modified>: auto / routed to Y / continued' (§6)."""
	if decision.rule is None:
		return "No approval rule matched: routed to {0}".format(decision.management_role)
	head = "Rule {0} v{1}: ".format(decision.rule, decision.rule_modified or "?")
	if decision.outcome == OUTCOME_AUTO_APPROVE:
		return head + "auto-approved"
	if decision.outcome == OUTCOME_ROUTE:
		return head + "routed to {0}".format(routed_to or decision.approver_user or decision.approver_role)
	return head + "routed to {0}".format(decision.management_role)


# --- Seed rows (final, 08/11/2026) --------------------------------------------

SEED_RULES = (
	{
		"rule_name": "CP price — list",
		"product_type": "Computer Paper", "stage": STAGE_PRICE, "priority": 10,
		"test": TEST_RATE_GE_BENCHMARK, "benchmark": BENCHMARK_STANDARD_SELLING,
		"when_met": OUTCOME_AUTO_APPROVE, "when_not_met": OUTCOME_CONTINUE,
		"fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "CP price — Neema",
		"product_type": "Computer Paper", "stage": STAGE_PRICE, "priority": 20,
		"test": TEST_ALWAYS, "benchmark": BENCHMARK_NONE,
		"when_met": OUTCOME_ROUTE, "when_not_met": OUTCOME_CONTINUE,
		"approver_user": "neema@vimit.com", "fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "CP technical",
		"product_type": "Computer Paper", "stage": STAGE_TECHNICAL, "priority": 10,
		"test": TEST_ALWAYS, "benchmark": BENCHMARK_NONE,
		"when_met": OUTCOME_ROUTE, "when_not_met": OUTCOME_CONTINUE,
		"approver_user": "neema@vimit.com", "fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "Carton price",
		"product_type": "Carton", "stage": STAGE_PRICE, "priority": 10,
		"test": TEST_RATE_GE_MARKUP, "benchmark": BENCHMARK_IQ_MANAGEMENT, "threshold_pct": 30,
		"when_met": OUTCOME_AUTO_APPROVE, "when_not_met": OUTCOME_MANAGEMENT,
		"fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "Carton technical",
		"product_type": "Carton", "stage": STAGE_TECHNICAL, "priority": 10,
		"test": TEST_ALWAYS, "benchmark": BENCHMARK_NONE,
		"when_met": OUTCOME_AUTO_APPROVE, "when_not_met": OUTCOME_CONTINUE,
		"fallback": OUTCOME_AUTO_APPROVE,
	},
	{
		"rule_name": "Label price",
		"product_type": "Label", "stage": STAGE_PRICE, "priority": 10,
		"test": TEST_MARGIN_GE, "benchmark": BENCHMARK_IQ_COST, "threshold_pct": 30,
		"when_met": OUTCOME_AUTO_APPROVE, "when_not_met": OUTCOME_MANAGEMENT,
		"fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "Label technical",
		"product_type": "Label", "stage": STAGE_TECHNICAL, "priority": 10,
		"test": TEST_ALWAYS, "benchmark": BENCHMARK_NONE,
		"when_met": OUTCOME_ROUTE, "when_not_met": OUTCOME_CONTINUE,
		"approver_role": DEFAULT_MANAGEMENT_ROLE, "fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "Monobox technical",
		"product_type": "Monobox", "stage": STAGE_TECHNICAL, "priority": 10,
		"test": TEST_ALWAYS, "benchmark": BENCHMARK_NONE,
		"when_met": OUTCOME_ROUTE, "when_not_met": OUTCOME_CONTINUE,
		"approver_role": DEFAULT_MANAGEMENT_ROLE, "fallback": OUTCOME_MANAGEMENT,
	},
	{
		"rule_name": "ETR technical",
		"product_type": "ETR (Reel to Reel Printing)", "stage": STAGE_TECHNICAL, "priority": 10,
		"test": TEST_ALWAYS, "benchmark": BENCHMARK_NONE,
		"when_met": OUTCOME_ROUTE, "when_not_met": OUTCOME_CONTINUE,
		"approver_role": DEFAULT_MANAGEMENT_ROLE, "fallback": OUTCOME_MANAGEMENT,
	},
)


def seeded(rules=SEED_RULES):
	"""Seed rows as the doctype stores them: enabled, default management role."""
	out = []
	for rule in rules:
		row = {"enabled": 1, "management_role": DEFAULT_MANAGEMENT_ROLE, "allow_self_approval": 0}
		row.update(rule)
		out.append(row)
	return out
