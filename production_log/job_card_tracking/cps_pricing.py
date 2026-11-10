"""Approval, effective dating and current-rate derivation for CPS Price rows.

This is the app-code home of what would otherwise be a live Server Script. It
holds the Frappe-bound half only — every decision it makes comes from the pure
functions in :mod:`production_log.job_card_tracking.cps_rules`, so the rules
themselves are unit testable without a bench.

Design references: §5.1 schema, §5.2 eligibility, §5.3 approval, DN-2 (approval
gate approved), DN-3 (self-approval permitted, logged).
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_lifecycle, cps_price_rules, cps_rules

# Kept for the Desk toolbar's role check; authority itself is "the rule says so"
# (§6) - see ``cps_approval.authorise_price_decision``.
APPROVER_ROLE = "Sales Master Manager"


def validate_pricing(doc):
	"""Enforce the CPS Price table rules and refresh the derived current rate.

	Called from both ``validate`` and ``before_update_after_submit`` on the
	specification: a price row added to an already-submitted spec is the normal
	case, and only the second of those two hooks fires for it.
	"""
	rows = doc.get("pricing") or []
	if not rows and not doc.get("current_rate"):
		return

	validate_no_duplicate_effective_dates(doc, rows)
	fill_row_defaults(doc, rows)
	enforce_immutable_entered_fields(doc, rows)
	revoke_approval_on_edit(doc, rows)
	set_current_rate(doc, rows)


def fill_row_defaults(doc, rows):
	"""Currency KES and the frozen conversion factor on every row (§5).

	The factor is read from the Item's UOM table ONCE, when the row is first
	saved, and never again - a price row follows the factor it was approved
	with, not the current Item master.
	"""
	meta = frappe.get_meta("CPS Price")
	has_currency = bool(meta.get_field("currency"))
	has_factor = bool(meta.get_field("conversion_factor"))
	for row in rows:
		if has_currency and not (row.get("currency") or "").strip():
			row.currency = cps_price_rules.DEFAULT_CURRENCY
		if has_factor and not row.get("conversion_factor") and row.get("uom"):
			row.conversion_factor = item_conversion_factor(doc.get("linked_item"), row.uom)


def item_conversion_factor(item_code, uom):
	"""Row UOM -> stock UOM factor from the Item's UOM table; 1 for the stock UOM; None if unknown."""
	if not item_code or not uom:
		return None
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
	if stock_uom == uom:
		return 1.0
	factor = frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "parenttype": "Item", "uom": uom}, "conversion_factor")
	return float(factor) if factor else None


def enforce_immutable_entered_fields(doc, rows):
	"""``entered_*``, ``tax_rate``, ``tax_basis`` and ``rounding_method`` never change once set."""
	before = doc.get_doc_before_save()
	if not before or not frappe.get_meta("CPS Price").get_field("entered_gross"):
		return
	previous_rows = {row.name: row for row in (before.get("pricing") or [])}
	for row in rows:
		changed = cps_price_rules.immutable_fields_changed(previous_rows.get(row.name), row)
		if changed:
			frappe.throw(
				_("Price row effective {0}: {1} cannot change once set. Add a new row instead.").format(
					frappe.utils.formatdate(row.valid_from), ", ".join(changed)
				),
				title=_("Price Row Immutable"),
			)


def validate_no_duplicate_effective_dates(doc, rows):
	"""Two live rows may not share an effective date (design §5.2).

	Otherwise eligibility resolution would pick arbitrarily between them.
	Rejected rows are excluded, so a rejected row can be superseded by a
	corrected one carrying the same date.
	"""
	duplicates = cps_rules.find_duplicate_valid_from(rows)
	if not duplicates:
		return

	frappe.throw(
		_("Two price rows share the effective date {0}. Supersede a price by adding a row with a later Effective From, or reject the row being replaced.").format(
			frappe.utils.formatdate(duplicates[0])
		),
		title=_("Duplicate Effective Date"),
	)


def revoke_approval_on_edit(doc, rows):
	"""Editing rate, UOM, currency, conversion factor or effective date returns an Approved row to Draft.

	Without this, approval is a one-time rubber stamp on a mutable number
	(design §5.3).
	"""
	before = doc.get_doc_before_save()
	if not before:
		return

	previous_rows = {row.name: row for row in (before.get("pricing") or [])}
	for row in rows:
		previous = previous_rows.get(row.name)
		if not cps_rules.price_approval_reset_required(previous, row):
			continue

		row.approval_status = cps_rules.APPROVAL_DRAFT
		row.approved_by = None
		row.approved_on = None
		if frappe.get_meta("CPS Price").get_field("approved_via"):
			row.approved_via = None
			row.approval_rule = None
			row.rule_benchmark = None
		frappe.msgprint(
			_("Price row effective {0} was changed and needs approval again.").format(
				frappe.utils.formatdate(row.valid_from)
			),
			indicator="orange",
			alert=True,
		)


def set_current_rate(doc, rows):
	"""Derive the list-view rate from the row in effect today (design §5.2).

	Same eligibility rule as a Sales Order line, with ``today()`` in place of
	the order's ``transaction_date``. Filtering on Approved matters here too, or
	the list view advertises prices nobody has approved.
	"""
	eligible = cps_rules.resolve_eligible_price(rows, frappe.utils.today())
	doc.current_rate = cps_rules.round_rate(eligible.rate) if eligible else None
	doc.current_uom = eligible.uom if eligible else None


def _row_fields():
	fields = ["name", "valid_from", "rate", "uom", "approval_status", "approved_on", "source", "source_ref"]
	meta = frappe.get_meta("CPS Price")
	for extra in ("currency", "conversion_factor"):
		if meta.get_field(extra):
			fields.append(extra)
	return fields


def approved_rows(cps):
	return frappe.get_all(
		"CPS Price",
		filters={
			"parent": cps,
			"parenttype": "Customer Product Specification",
			"parentfield": "pricing",
			"approval_status": cps_rules.APPROVAL_APPROVED,
		},
		fields=_row_fields(),
		order_by="valid_from asc",
	)


def get_eligible_price(cps, on_date, currency=None):
	"""Return the eligible CPS Price row for a specification on a given date.

	``on_date`` is the Sales Order ``transaction_date``, never ``today()``.
	Selection is :func:`cps_price_rules.select_price_row` - Approved, same
	currency, greatest ``valid_from`` <= date, then latest ``approved_on`` -
	so every caller (SO submit, Release, the Desk preview) binds the same row.
	"""
	return cps_price_rules.select_price_row(approved_rows(cps), currency, on_date)


def get_order_price_candidates(cps, on_date, currency=None, lock=False):
	"""Separate Approved/Draft candidates; only SO's first-order path uses Draft.

	Submit calls this after locking the parent CPS. A current locking read of
	prices avoids an earlier repeatable-read snapshot masking a new approval.
	The existing Approved-only selector used by Release/mirrors is unchanged.
	"""
	fields = _row_fields()  # Server-owned allowlist, never caller input.
	if lock:
		columns = ", ".join("`" + field + "`" for field in fields)
		rows = frappe.db.sql(
			"SELECT " + columns + " FROM `tabCPS Price` "
			"WHERE parent = %s AND parenttype = %s AND parentfield = %s "
			"ORDER BY name FOR UPDATE",
			(cps, "Customer Product Specification", "pricing"), as_dict=True,
		)
	else:
		rows = frappe.get_all(
			"CPS Price", filters={"parent": cps, "parenttype": "Customer Product Specification",
			                      "parentfield": "pricing"}, fields=fields,
		)
	return (
		cps_price_rules.select_price_row(rows, currency, on_date),
		cps_price_rules.select_draft_price_row(rows, currency, on_date),
	)


def get_price_row(cps, row_name):
	"""One row by name, in the shape ``check_line_rate`` reads, or None."""
	rows = frappe.get_all(
		"CPS Price",
		filters={"name": row_name, "parent": cps, "parenttype": "Customer Product Specification"},
		fields=_row_fields(),
		limit_page_length=1,
	)
	return rows[0] if rows else None


@frappe.whitelist(methods=["POST"])
def approve_cps_price(cps, row, action="approve", notes=None):
	"""Approve or reject a CPS Price row (design §5.3, §10.5; §6 authority).

	Who may call this is "the rule says so": the matching ``CPS Approval
	Rule``'s approver, or its management role. Self-approval is refused unless
	the rule ticks ``allow_self_approval`` (§6 replaces DN-3). On a site where
	the rule doctype has not landed the old Sales Master Manager check applies.
	"""
	from production_log.job_card_tracking import cps_approval

	if action not in ("approve", "reject"):
		frappe.throw(_("Unknown action {0}. Use 'approve' or 'reject'.").format(action))

	doc = frappe.get_doc("Customer Product Specification", cps)
	target = next((r for r in (doc.get("pricing") or []) if r.name == row), None)
	if not target:
		frappe.throw(_("Price row {0} not found on {1}.").format(row, cps))

	decision = None
	if frappe.db.exists("DocType", cps_approval.RULE):
		decision = cps_approval.authorise_price_decision(doc, target)
	elif APPROVER_ROLE not in frappe.get_roles():
		frappe.throw(
			_("{0} role required to approve a price.").format(APPROVER_ROLE),
			frappe.PermissionError,
		)

	new_status = (
		cps_rules.APPROVAL_APPROVED if action == "approve" else cps_rules.APPROVAL_REJECTED
	)
	if target.approval_status == new_status:
		frappe.throw(_("Row is already {0}.").format(new_status))

	target.approval_status = new_status
	target.approved_by = frappe.session.user
	target.approved_on = frappe.utils.now()
	if notes:
		target.approval_notes = notes
	if decision is not None and frappe.get_meta("CPS Price").get_field("approved_via"):
		target.approved_via = cps_approval.approved_via_for(decision)
		target.approval_rule = decision.rule
		if decision.benchmark_value is not None:
			target.rule_benchmark = cps_rules.round_rate(decision.benchmark_value)

	set_current_rate(doc, doc.get("pricing") or [])
	with cps_lifecycle.server_write():
		doc.save()

	_log_approval(doc, target, action)
	if decision is not None:
		doc.add_comment("Comment", cps_approval.rules.comment_text(decision, routed_to=frappe.session.user))

	# Cards bound to this spec re-evaluate (checks 9-10) - §7c doc_events.
	from production_log.job_card_tracking import release
	release.reevaluate_for_spec(doc.name)

	# The price list follows the specification (decision 2026-09-12). Wrapped so
	# a mirror fault can never fail an approval that has already happened; the
	# nightly sweep picks up anything dropped here.
	from production_log.job_card_tracking import cps_price_mirror

	cps_price_mirror.mirror_after_approval(doc.name)

	return {
		"cps": doc.name,
		"row": target.name,
		"approval_status": target.approval_status,
		"approved_by": target.approved_by,
		"approved_on": target.approved_on,
		"current_rate": doc.current_rate,
		"current_uom": doc.current_uom,
	}


def _log_approval(doc, row, action):
	"""Leave a visible audit trail, flagging self-approval explicitly (DN-3)."""
	self_approved = row.owner == frappe.session.user
	doc.add_comment(
		"Comment",
		_("Price row effective {0} at {1} was {2} by {3}.{4}").format(
			frappe.utils.formatdate(row.valid_from),
			row.rate,
			"approved" if action == "approve" else "rejected",
			frappe.session.user,
			_(" Self-approved by the row's author.") if self_approved else "",
		),
	)


@frappe.whitelist(methods=["POST"])
def add_price_row(cps, valid_from, uom, rate=None, entered_gross=None, tax_basis=None,
                  currency=None, source="Manual", source_ref=None, notes=None):
	"""Draft a dated price row and run the §6 price rule on it.

	The one write path behind the three §5 entry points - LPO at a different
	price (``source`` LPO, ``source_ref`` = po_no), Management reprice, and the
	Desk/Compass "enter incl. VAT" helper. Either ``rate`` (net) or
	``entered_gross`` + ``tax_basis`` is given; the gross path stores both and
	computes ``rate`` = gross / 1.16 at 9 dp. Rows are never edited: a change is
	a new row. Returns the row name and the rule's decision.
	"""
	from production_log.job_card_tracking import cps_approval

	doc = frappe.get_doc("Customer Product Specification", cps)
	if not frappe.has_permission("Customer Product Specification", "write", doc):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	if not uom:
		frappe.throw(_("UOM is required - nothing is inferred from the product type."))
	if source not in ("Quotation", cps_price_rules.SOURCE_LPO, "Manual", cps_price_rules.SOURCE_MANAGEMENT_REPRICE, "Historical"):
		# "Internal Quotation" is written by the transfer alone (Codex r5 item 2).
		frappe.throw(_("Source must be Quotation, LPO, Manual, Management reprice or Historical."))

	meta = frappe.get_meta("CPS Price")
	values = {
		"valid_from": valid_from,
		"uom": uom,
		"source": source,
		"source_ref": source_ref,
		"notes": notes,
		"approval_status": cps_rules.APPROVAL_DRAFT,
	}
	if meta.get_field("currency"):
		values["currency"] = (currency or "").strip() or cps_price_rules.DEFAULT_CURRENCY
	if entered_gross not in (None, ""):
		basis = tax_basis or cps_price_rules.TAX_BASIS_GROSS_VAT
		if basis not in cps_price_rules.TAX_BASES:
			frappe.throw(_("Tax basis must be one of {0}.").format(", ".join(cps_price_rules.TAX_BASES)))
		gross = cps_price_rules.gross_entry_values(float(entered_gross), basis)
		values.update(gross if meta.get_field("entered_gross") else {"rate": gross["rate"]})
		if meta.get_field("entered_uom"):
			values["entered_uom"] = uom
	elif rate not in (None, ""):
		values["rate"] = cps_rules.round_rate(rate)
		if meta.get_field("tax_basis"):
			values["tax_basis"] = tax_basis or cps_price_rules.TAX_BASIS_NET
			values["tax_rate"] = 0.0
	else:
		frappe.throw(_("Give a net rate or a gross entered amount."))

	if source == cps_price_rules.SOURCE_MANAGEMENT_REPRICE and "VCL Management Team" not in frappe.get_roles():
		frappe.throw(_("Only VCL Management Team may record a Management reprice."), frappe.PermissionError)

	row = doc.append("pricing", values)
	decision = None
	if frappe.db.exists("DocType", cps_approval.RULE):
		fill_row_defaults(doc, [row])
		decision = cps_approval.evaluate_price_row(doc, row)
	with cps_lifecycle.server_write():
		doc.save()

	if decision is not None:
		doc.add_comment("Comment", cps_approval.rules.comment_text(decision))
		from production_log.job_card_tracking import release
		release.reevaluate_for_spec(doc.name)

	return {
		"cps": doc.name,
		"row": row.name,
		"rate": row.rate,
		"approval_status": row.approval_status,
		"decision": decision.outcome if decision else None,
		"rule": decision.rule if decision else None,
	}
