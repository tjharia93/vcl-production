"""Frappe-bound half of CPS approval (§6): rules, benchmarks, stamps, authority.

Every decision comes from :mod:`cps_approval_rules`. This module loads the
enabled rules, reads the benchmarks a rule needs (Standard Selling Item Price,
the linked Internal Quotation's management or cost price), writes the stamps
on the specification or the price row, and refuses a caller without authority.

Technical and price stay separate decisions even on one screen.
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_approval_rules as rules
from production_log.job_card_tracking import cps_lifecycle, cps_lifecycle_rules, cps_price_rules, cps_rules

CPS = "Customer Product Specification"
RULE = "CPS Approval Rule"

STANDARD_SELLING = "Standard Selling"


# ---------------------------------------------------------------------------
# Rules and benchmarks
# ---------------------------------------------------------------------------


def load_rules():
	"""Every enabled rule, as plain dicts, or [] before the doctype has landed."""
	if not frappe.db.exists("DocType", RULE):
		return []
	return frappe.get_all(
		RULE,
		filters={"enabled": 1},
		fields=[
			"name", "rule_name", "product_type", "stage", "customer", "priority", "test",
			"benchmark", "threshold_pct", "when_met", "when_not_met", "approver_user",
			"approver_role", "fallback", "management_role", "allow_self_approval",
			"valid_from", "valid_to", "enabled", "modified",
		],
	)


def benchmarks_for(spec, row=None):
	"""The benchmark values a price rule may ask for, None when absent."""
	values = {}
	item = spec.get("linked_item")
	if item:
		price = frappe.db.get_value(
			"Item Price",
			{"item_code": item, "price_list": STANDARD_SELLING, "selling": 1},
			"price_list_rate",
			order_by="valid_from desc",
		)
		values[rules.BENCHMARK_STANDARD_SELLING] = float(price) if price not in (None, "") else None
	iq_name = spec.get("vcl_source_iq")
	if not iq_name and row is not None and row.get("source") == cps_price_rules.SOURCE_INTERNAL_QUOTATION:
		iq_name = row.get("source_ref")
	if iq_name and frappe.db.exists("DocType", "Internal Quotation"):
		iq = frappe.db.get_value("Internal Quotation", iq_name, ["management_price", "cost_price"], as_dict=True)
		if iq:
			values[rules.BENCHMARK_IQ_MANAGEMENT] = float(iq.management_price) if iq.management_price not in (None, "") else None
			values[rules.BENCHMARK_IQ_COST] = float(iq.cost_price) if iq.cost_price not in (None, "") else None
	return values


def resolve_technical(spec):
	return rules.resolve(
		load_rules(), spec.get("product_type"), rules.STAGE_TECHNICAL,
		customer=spec.get("customer"), on_date=frappe.utils.today(),
	)


def resolve_price(spec, row):
	return rules.resolve(
		load_rules(), spec.get("product_type"), rules.STAGE_PRICE,
		rate=row.get("rate"), benchmarks=benchmarks_for(spec, row),
		customer=spec.get("customer"), on_date=row.get("valid_from") or frappe.utils.today(),
	)


def _log_decision(doc, decision, routed_to=None):
	doc.add_comment("Comment", rules.comment_text(decision, routed_to))


def _refuse_without_authority(decision, author):
	if not rules.may_decide(decision, frappe.session.user, frappe.get_roles(), author=author):
		who = decision.approver_user or decision.approver_role or decision.management_role
		frappe.throw(
			_("{0} decides this ({1}); self-approval is {2}.").format(
				who, decision.rule or _("no rule"),
				_("allowed") if decision.allow_self_approval else _("not allowed"),
			),
			frappe.PermissionError,
		)


# ---------------------------------------------------------------------------
# Technical approval (§1 transition, §6)
# ---------------------------------------------------------------------------


def evaluate_technical(doc):
	"""Run the technical rule on submit or revision; auto-approve stamps the exact revision.

	Called from the lifecycle hooks on a document about to be saved: writes on
	``doc`` only, no save of its own.
	"""
	if not cps_lifecycle.has_lifecycle_fields(doc) or int(doc.get("vcl_revision") or 0) < 1:
		return None
	decision = resolve_technical(doc)
	if decision.outcome == rules.OUTCOME_AUTO_APPROVE:
		values = cps_lifecycle_rules.technical_approval_values(
			doc.vcl_revision, rules.SYSTEM_USER, frappe.utils.now(), rule=decision.rule,
			notes=rules.comment_text(decision),
		)
		for fieldname, value in values.items():
			doc.set(fieldname, value)
	else:
		doc.vcl_approval_notes = rules.comment_text(decision)
	frappe.flags.cps_technical_decision = decision
	return decision


@frappe.whitelist()
def approve_technical(cps, decision, notes=None):
	"""Approve or reject the specification's current revision (§1).

	Authority: the CPS Approver named by the matching rule, or management.
	Stamps ``vcl_approved_rev`` = the exact revision evaluated.
	"""
	if decision not in ("approve", "reject"):
		frappe.throw(_("Unknown decision {0}. Use 'approve' or 'reject'.").format(decision))

	doc = frappe.get_doc(CPS, cps)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted specification can be technically approved."))
	if not cps_lifecycle.has_lifecycle_fields(doc):
		frappe.throw(_("Lifecycle fields have not landed on this site yet."))

	routed = resolve_technical(doc)
	_refuse_without_authority(routed, author=doc.get("vcl_revision_by") or doc.owner)

	if decision == "approve":
		if cps_lifecycle_rules.is_technically_approved(doc):
			frappe.throw(_("Revision {0} is already approved.").format(doc.vcl_revision))
		values = cps_lifecycle_rules.technical_approval_values(
			doc.vcl_revision, frappe.session.user, frappe.utils.now(), rule=routed.rule, notes=notes,
		)
	else:
		if not (notes or "").strip():
			frappe.throw(_("A reason is required to reject a revision."))
		values = cps_lifecycle_rules.technical_rejection_values(notes)

	for fieldname, value in values.items():
		doc.set(fieldname, value)
	with cps_lifecycle.server_write():
		doc.save()
	doc.add_comment(
		"Comment",
		_("Revision {0} {1} by {2}{3}").format(
			doc.vcl_revision, _("approved") if decision == "approve" else _("rejected"),
			frappe.session.user, ": " + notes if notes else "",
		),
	)
	_log_decision(doc, routed)

	from production_log.job_card_tracking import release
	release.reevaluate_for_spec(doc.name)

	return {
		"cps": doc.name,
		"revision": doc.vcl_revision,
		"vcl_approval_state": doc.vcl_approval_state,
		"vcl_approved_rev": doc.vcl_approved_rev,
	}


# ---------------------------------------------------------------------------
# Price approval (§5, §6)
# ---------------------------------------------------------------------------


def evaluate_price_row(doc, row):
	"""Apply the price rule to a Draft row on ``doc`` (no save).

	Auto-approve stamps the row approved by Administrator with the rule and
	the frozen benchmark; Route / Management leave it Draft with the decision
	in ``approval_notes`` so the approver knows why it is theirs.
	"""
	decision = resolve_price(doc, row)
	row.approval_rule = decision.rule
	row.rule_benchmark = cps_rules.round_rate(decision.benchmark_value) if decision.benchmark_value is not None else None
	if decision.outcome == rules.OUTCOME_AUTO_APPROVE:
		row.approval_status = cps_rules.APPROVAL_APPROVED
		row.approved_by = rules.SYSTEM_USER
		row.approved_on = frappe.utils.now()
		row.approved_via = cps_price_rules.APPROVED_VIA_RULE
		row.approval_notes = rules.comment_text(decision)
	else:
		row.approval_notes = rules.comment_text(decision)
	return decision


def authorise_price_decision(doc, row):
	"""Refuse ``approve_cps_price`` unless the rule says the caller decides."""
	decision = resolve_price(doc, row)
	_refuse_without_authority(decision, author=row.owner)
	return decision


def approved_via_for(decision):
	roles = set(frappe.get_roles())
	if (decision.management_role or rules.DEFAULT_MANAGEMENT_ROLE) in roles:
		return cps_price_rules.APPROVED_VIA_MANAGEMENT
	return cps_price_rules.APPROVED_VIA_APPROVER
