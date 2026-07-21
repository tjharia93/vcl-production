"""Pure shaping rules for the CPS migration/readiness report.

Like :mod:`cps_rules`, this module imports nothing from Frappe. It takes plain
data — specification dicts, link decisions from ``cps_rules.resolve_item_link``,
sets of "has an approved price" names — and returns plain dicts of scalars that
a CSV writer, a Compass table or a bench console can all consume unchanged.

The Frappe-bound half (reading documents, gating on roles, querying Sales Order
history) lives in :mod:`cps_migration_report`. Splitting it this way is what
makes the report's judgement — what counts as a blocker, when enforcement is
safe — testable without a bench, a site or a database.

Nothing here decides to *change* anything. ``proposed_item`` is a proposal for a
human to act on, never an instruction, and there is deliberately no function in
either half of this report that writes a link.
"""

import csv
import io

from production_log.job_card_tracking import cps_rules

# --- Issue codes ------------------------------------------------------------
#
# Kebab-case and stable: these end up in a CSV column that someone will filter
# on in a spreadsheet, so they are an interface, not a log message.

ISSUE_UNLINKED = "unlinked"
ISSUE_MISSING_CUSTOMER = "missing-customer"
ISSUE_MISSING_PRICE = "missing-price"
ISSUE_INACTIVE = "inactive"
ISSUE_CANCELLED = "cancelled"
ISSUE_DRAFT = "draft"
ISSUE_DUPLICATE = "duplicate-customer-item"

# Issues that must be cleared before Sales Order enforcement can go strict.
#
# Inactive, cancelled and draft specifications are deliberately absent: they
# already cannot be ordered against (``so_spec_control._load_and_validate_spec``
# throws on each), so they are migration hygiene rather than a gate. Blocking on
# them would mean an old discontinued spec kept enforcement off forever.
BLOCKING_ISSUES = frozenset(
	(ISSUE_UNLINKED, ISSUE_MISSING_CUSTOMER, ISSUE_MISSING_PRICE, ISSUE_DUPLICATE)
)

ALL_ISSUES = (
	ISSUE_UNLINKED,
	ISSUE_MISSING_CUSTOMER,
	ISSUE_MISSING_PRICE,
	ISSUE_INACTIVE,
	ISSUE_CANCELLED,
	ISSUE_DRAFT,
	ISSUE_DUPLICATE,
)

# Issue counters are prefixed in the summary because ``unlinked`` is both an
# issue code and a headline count, and one flat namespace let them increment the
# same key — a bug the summary tests caught before the report ever ran.
ISSUE_COUNT_PREFIX = "issue_"

DOCSTATUS_LABELS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

STATUS_ACTIVE = "Active"

# Column order for the CSV export. Explicit rather than derived from a dict, so
# a new field cannot silently reorder someone's saved spreadsheet filters.
REPORT_COLUMNS = (
	"name",
	"product_type",
	"specification_name",
	"customer",
	"customer_exists",
	"status",
	"docstatus",
	"docstatus_label",
	"is_enforceable",
	"linked_item",
	"is_linked",
	"has_approved_price",
	"current_rate",
	"current_uom",
	"match",
	"proposed_item",
	"proposed_confidence",
	"candidate_count",
	"top_candidates",
	"top_candidate_reasons",
	"issues",
	"is_blocking",
)

OPEN_SO_LINE_COLUMNS = (
	"sales_order",
	"transaction_date",
	"customer",
	"status",
	"idx",
	"item_code",
	"item_name",
	"qty",
	"rate",
	"issue",
)


def _get(row, key):
	"""Read a key from a dict or an attribute from a Frappe document."""
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def docstatus_label(docstatus):
	"""Human label for a docstatus, without guessing at unknown values."""
	try:
		return DOCSTATUS_LABELS[int(docstatus or 0)]
	except (TypeError, ValueError, KeyError):
		return "Unknown"


def is_enforceable(spec):
	"""Whether this specification could actually be used on a Sales Order.

	Only submitted + Active specifications can be ordered against, so only those
	can hold enforcement back. A draft or discontinued spec with no Item is a
	tidy-up, not a blocker.
	"""
	return int(_get(spec, "docstatus") or 0) == 1 and _get(spec, "status") == STATUS_ACTIVE


def duplicate_customer_item_keys(specs):
	"""``(customer, linked_item)`` pairs held by more than one enforceable spec.

	Two Active submitted specifications naming the same Customer *and* the same
	Item are indistinguishable at order time: whichever the rep picks changes the
	price, and neither is wrong. That has to be resolved by a human before
	enforcement, so it is a blocker rather than a warning.
	"""
	seen = {}
	for spec in specs or []:
		linked = (_get(spec, cps_rules.ITEM_LINK_FIELD) or "").strip()
		customer = (_get(spec, "customer") or "").strip()
		if not linked or not customer or not is_enforceable(spec):
			continue
		seen.setdefault((customer, linked), []).append(_get(spec, "name"))

	return {key: sorted(names) for key, names in seen.items() if len(names) > 1}


def detect_spec_issues(spec, decision, has_approved_price, customer_exists, duplicate_keys=None):
	"""Every problem this specification carries, as stable issue codes.

	``decision`` is a :class:`cps_rules.ItemLinkDecision`. An unlinked spec is
	only reported as ``unlinked`` — the decision's own ``match`` carries whether
	a candidate was found, and duplicating that here would let the two disagree.
	"""
	issues = []

	if decision is not None and decision.match != cps_rules.MATCH_ALREADY_LINKED:
		issues.append(ISSUE_UNLINKED)

	if not (_get(spec, "customer") or "").strip() or not customer_exists:
		issues.append(ISSUE_MISSING_CUSTOMER)

	if not has_approved_price:
		issues.append(ISSUE_MISSING_PRICE)

	docstatus = int(_get(spec, "docstatus") or 0)
	if docstatus == 2:
		issues.append(ISSUE_CANCELLED)
	elif docstatus == 0:
		issues.append(ISSUE_DRAFT)

	if docstatus != 2 and _get(spec, "status") != STATUS_ACTIVE:
		issues.append(ISSUE_INACTIVE)

	linked = (_get(spec, cps_rules.ITEM_LINK_FIELD) or "").strip()
	customer = (_get(spec, "customer") or "").strip()
	if (customer, linked) in (duplicate_keys or {}):
		issues.append(ISSUE_DUPLICATE)

	return issues


def blocking_issues(spec, issues):
	"""The subset of ``issues`` that actually holds enforcement back.

	A non-enforceable specification blocks nothing, however broken it is.
	"""
	if not is_enforceable(spec):
		return []
	return [issue for issue in issues if issue in BLOCKING_ISSUES]


def format_candidates(candidates, limit=3):
	"""Render ranked candidates as two CSV-safe strings.

	One cell for the ranking and one for the reasoning, because a reviewer wants
	to scan the codes and only then read why. Nested structures are deliberately
	flattened here rather than in the caller: a report that is CSV-friendly in
	one code path and not in another is neither.
	"""
	shortlist = list(candidates or [])[:limit]
	if not shortlist:
		return "", ""

	ranked = "; ".join(
		"{0} ({1})".format(c.item_code, c.confidence) for c in shortlist
	)
	reasons = " || ".join(
		"{0}: {1}".format(c.item_code, " / ".join(c.reasons or [])) for c in shortlist
	)
	return ranked, reasons


def build_spec_row(spec, decision, has_approved_price, customer_exists=True, duplicate_keys=None):
	"""One flat, scalar-only row describing a specification's readiness.

	Every value is a string, number, bool or None — no lists, no nested dicts —
	so the same row serialises to CSV, to JSON for Compass, and prints legibly
	in a bench console without a second shaping pass.
	"""
	issues = detect_spec_issues(spec, decision, has_approved_price, customer_exists, duplicate_keys)
	blockers = blocking_issues(spec, issues)
	ranked, reasons = format_candidates(decision.candidates if decision else [])

	linked = (_get(spec, cps_rules.ITEM_LINK_FIELD) or "").strip() or None
	proposed = decision.auto_item if decision else None

	return {
		"name": _get(spec, "name"),
		"product_type": _get(spec, "product_type"),
		"specification_name": _get(spec, "specification_name"),
		"customer": _get(spec, "customer"),
		"customer_exists": bool(customer_exists),
		"status": _get(spec, "status"),
		"docstatus": int(_get(spec, "docstatus") or 0),
		"docstatus_label": docstatus_label(_get(spec, "docstatus")),
		"is_enforceable": is_enforceable(spec),
		"linked_item": linked,
		"is_linked": bool(linked),
		"has_approved_price": bool(has_approved_price),
		"current_rate": _get(spec, "current_rate"),
		"current_uom": _get(spec, "current_uom"),
		"match": decision.match if decision else None,
		# A proposal only. Nothing in this app consumes this field; it exists for
		# a human to read, decide and set the link themselves.
		"proposed_item": proposed,
		"proposed_confidence": (
			cps_rules.CONFIDENCE_HIGH if proposed else (
				decision.candidates[0].confidence if decision and decision.candidates else None
			)
		),
		"candidate_count": len(decision.candidates) if decision else 0,
		"top_candidates": ranked,
		"top_candidate_reasons": reasons,
		"issues": ",".join(issues),
		"is_blocking": bool(blockers),
	}


def summarise_report(rows, open_so_lines=None):
	"""Aggregate rows into counts and the single ``ready_to_enforce`` verdict.

	``ready_to_enforce`` is stricter than ``cps_rules.summarise_readiness``: that
	one answers "is every link resolved", which is necessary but not sufficient.
	An Active spec with a resolved link but no approved price still throws V7 on
	submit, and an open controlled order line with no specification would start
	failing the moment enforcement went strict. Both are counted here, because
	the point of the verdict is that flipping the setting breaks nothing.
	"""
	rows = list(rows or [])
	open_so_lines = list(open_so_lines or [])

	summary = {
		"total": len(rows),
		"linked": 0,
		"unlinked": 0,
		"enforceable": 0,
		"blocking": 0,
		"proposed_mappings": 0,
		cps_rules.MATCH_ALREADY_LINKED: 0,
		cps_rules.MATCH_EXACT_SOLE: 0,
		cps_rules.MATCH_AMBIGUOUS: 0,
		cps_rules.MATCH_NONE: 0,
	}
	for issue in ALL_ISSUES:
		summary[ISSUE_COUNT_PREFIX + issue] = 0

	for row in rows:
		if row.get("is_linked"):
			summary["linked"] += 1
		else:
			summary["unlinked"] += 1
		if row.get("is_enforceable"):
			summary["enforceable"] += 1
		if row.get("is_blocking"):
			summary["blocking"] += 1
		if row.get("proposed_item"):
			summary["proposed_mappings"] += 1
		if row.get("match") in summary:
			summary[row["match"]] += 1
		for issue in (row.get("issues") or "").split(","):
			key = ISSUE_COUNT_PREFIX + issue
			if key in summary:
				summary[key] += 1

	summary["open_so_lines_without_cps"] = len(open_so_lines)
	summary["ready_to_enforce"] = (
		summary["blocking"] == 0 and summary["open_so_lines_without_cps"] == 0
	)
	return summary


def to_csv(rows, columns=REPORT_COLUMNS):
	"""Serialise report rows to a CSV string.

	Written with :mod:`csv` rather than joined by hand because specification
	names contain commas, and a report that corrupts on the first comma is worse
	than no report.
	"""
	buffer = io.StringIO()
	writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
	writer.writeheader()
	for row in rows or []:
		writer.writerow({key: row.get(key) for key in columns})
	return buffer.getvalue()
