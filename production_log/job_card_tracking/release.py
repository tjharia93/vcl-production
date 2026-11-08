"""The job-card release gate, Frappe-bound half (Stream A §7c-§7e).

Every check is a pure function in :mod:`release_rules`; this module assembles
the context from the card, its Sales Order line, the specification, the BOUND
revision payload, the BOUND price row and the artwork state, runs the checks,
and writes the result. "On hold" means one thing: the card cannot be printed
until it is Released.

Release is automatic when every required check passes (A); a person only
overrides a failure (B). Manual PPC holds and ``customer_hold`` are independent
and never cleared here (Codex r4 point 2). The row the checks validate is the
row Release binds (point 3). The SO line and the specification are read under
``FOR UPDATE`` and the spec / price-row ``modified`` stamps are compared before
and after; on contention the evaluation re-runs once and otherwise the card
stays held (point 4).

Entry points:
  evaluate(doctype, name)            server-side; on insert, from doc_events, from prepare_render
  override(doctype, name, reason)    whitelisted; VCL Management Team only
  request_override(doctype, name, reason)  whitelisted; reps
  prepare_render(doctype, name)      whitelisted POST; re-evaluates, persists, stamps render_issued_*
  before_print_guard(card)           called by the controllers' before_print; writes nothing
  release_status(job_card)           whitelisted read for the Order desk, board and list (Stream B)
"""

import json

import frappe
from frappe import _

from production_log.job_card_tracking import (
	cps_lifecycle,
	cps_lifecycle_rules,
	cps_pricing,
	release_rules,
	so_spec_control,
)

CPS = "Customer Product Specification"
ARTWORK_VERSION = "CPS Artwork Version"
LOG_TITLE = "vcl_release"


def card_doctypes():
	return tuple(so_spec_control.JOB_CARD_DOCTYPES.values())


def has_release_fields(doctype):
	return bool(frappe.get_meta(doctype).get_field("release_state"))


def _assert_card_doctype(doctype):
	if doctype not in card_doctypes():
		frappe.throw(_("{0} is not a job card the release gate knows.").format(doctype))


def _parse(text):
	try:
		value = json.loads(text or "")
	except (TypeError, ValueError):
		return None
	return value if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def _lock_line(line_name, lock=True):
	meta = frappe.get_meta("Sales Order Item")
	columns = ["name", "parent", "qty", "rate", "uom", "conversion_factor", "item_code"]
	for extra in ("custom_cps", "custom_cps_price_row", "custom_price_override_reason"):
		if meta.get_field(extra):
			columns.append(extra)
	rows = frappe.db.sql(
		"SELECT {0} FROM `tabSales Order Item` WHERE name = %(name)s{1}".format(
			", ".join("`{0}`".format(c) for c in columns), " FOR UPDATE" if lock else ""
		),
		{"name": line_name},
		as_dict=True,
	)
	return rows[0] if rows else None


def _spec_versions(spec_name, lock=True):
	"""``modified`` of the spec and the max ``modified`` of its price rows."""
	spec = frappe.db.sql(
		"SELECT modified FROM `tabCustomer Product Specification` WHERE name = %(n)s{0}".format(" FOR UPDATE" if lock else ""),
		{"n": spec_name},
	)
	rows = frappe.db.sql(
		"SELECT MAX(modified) FROM `tabCPS Price` WHERE parent = %(n)s AND parenttype = 'Customer Product Specification'",
		{"n": spec_name},
	)
	return (str(spec[0][0]) if spec else None, str(rows[0][0]) if rows and rows[0][0] else None)


def _other_cards_qty(card):
	rows = frappe.get_all(
		card.doctype,
		filters={"sales_order_item": card.sales_order_item, "docstatus": ["in", [0, 1]], "name": ["!=", card.name]},
		pluck="quantity_ordered",
	)
	return sum(float(q or 0) for q in rows)


def _artwork_state(spec_name):
	if not frappe.db.exists("DocType", ARTWORK_VERSION):
		return {"state": None, "version": None}
	rows = frappe.get_all(
		ARTWORK_VERSION,
		filters={"spec": spec_name, "superseded": 0},
		fields=["name", "version", "approval_state"],
		order_by="creation desc",
		limit_page_length=1,
	)
	if not rows:
		return {"state": None, "version": None}
	return {"state": rows[0].approval_state, "version": rows[0].name}


def _bound_revision(card, spec):
	for fieldname in ("spec_revision", "release_spec_revision"):
		value = card.get(fieldname) if card.meta.get_field(fieldname) else None
		if value:
			return int(value)
	return int(spec.get("vcl_revision") or 0)


def _bound_payload(spec, revision):
	payload = cps_lifecycle_rules.payload_for_revision(spec.get("vcl_revision_log"), revision)
	if payload is None:
		current = cps_lifecycle_rules.parse_payload(spec.get("vcl_revision_payload"))
		if current and int(current.get("_revision") or 0) == int(revision):
			payload = current
	return payload


def build_context(card, lock=True):
	"""Everything the eleven checks read, plus the versions seen while reading."""
	order = frappe.db.get_value(
		"Sales Order", card.sales_order,
		["name", "docstatus", "status", "customer", "transaction_date", "currency", "owner"],
		as_dict=True,
	) if card.get("sales_order") else None
	line = _lock_line(card.sales_order_item, lock) if card.get("sales_order_item") else None

	spec_name = card.get("customer_product_spec") or (line or {}).get("custom_cps")
	spec = frappe.get_doc(CPS, spec_name).as_dict() if spec_name and frappe.db.exists(CPS, spec_name) else None
	versions = _spec_versions(spec_name, lock) if spec_name else (None, None)

	bound_revision = _bound_revision(card, spec) if spec else 0
	bound_payload = _bound_payload(spec, bound_revision) if spec else None

	price_row = None
	if spec:
		bound_row_name = card.get("release_price_row") if card.meta.get_field("release_price_row") else None
		row_name = (line or {}).get("custom_cps_price_row") or bound_row_name
		if row_name:
			price_row = cps_pricing.get_price_row(spec["name"], row_name)
		if price_row is None and order:
			price_row = cps_pricing.get_eligible_price(spec["name"], order.transaction_date, order.currency)

	ctx = {
		"order": order,
		"line": line,
		"other_cards_qty": _other_cards_qty(card) if line else 0.0,
		"card": {
			"name": card.name,
			"quantity_ordered": card.get("quantity_ordered"),
			"customer_product_spec": card.get("customer_product_spec"),
			"item_code": card.get("item_code") or (line or {}).get("item_code"),
			"spec_snapshot": _parse(card.get("spec_snapshot")),
			"customer_hold": card.get("customer_hold") or 0,
			"artwork_approved": card.get("artwork_approved") or 0,
			"job_status": card.get("job_status"),
			"hold_reason": card.get("hold_reason"),
			"release_state": card.get("release_state"),
			"print_superseded": card.get("print_superseded") or 0,
		},
		"spec": spec,
		"bound_revision": bound_revision,
		"bound_payload": bound_payload,
		"item_control": so_spec_control.resolve_item_control(card.get("item_code") or (line or {}).get("item_code")),
		"price_row": price_row,
		"allowance": so_spec_control.rounding_allowance_settings(),
		"artwork": _artwork_state(spec_name) if spec_name else {"state": None, "version": None},
		"stored_fingerprint": _parse(card.get("release_fingerprint")) if card.meta.get_field("release_fingerprint") else None,
	}
	return ctx, versions


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


def is_gated(card):
	"""Only an order-derived card with the release fields is gated."""
	return bool(card.get("sales_order_item")) and has_release_fields(card.doctype)


def evaluate(doctype, name, trigger="manual"):
	"""Run the checks and persist the result. Returns the summary dict or None."""
	_assert_card_doctype(doctype)
	if frappe.flags.in_release_evaluate:
		return None
	card = frappe.get_doc(doctype, name)
	if not is_gated(card) or card.docstatus == 2:
		return None

	frappe.flags.in_release_evaluate = True
	try:
		ctx, before = build_context(card)
		results, fingerprint = release_rules.evaluate(ctx)
		after = _spec_versions(ctx["spec"]["name"]) if ctx.get("spec") else (None, None)
		contention = False
		if after != before:
			# A concurrent CPS / price edit slipped between the reads (Codex r4
			# point 4): discard and run once more; if it moved again, stay held.
			ctx, before = build_context(card)
			results, fingerprint = release_rules.evaluate(ctx)
			after = _spec_versions(ctx["spec"]["name"]) if ctx.get("spec") else (None, None)
			contention = after != before
		return _apply(card, ctx, results, fingerprint, trigger, contention)
	finally:
		frappe.flags.in_release_evaluate = False


def _apply(card, ctx, results, fingerprint, trigger, contention):
	now = frappe.utils.now()
	prior_state = card.get("release_state") or release_rules.STATE_HELD
	was_released = prior_state in (release_rules.STATE_RELEASED, release_rules.STATE_RELEASED_OVERRIDE)
	stale = release_rules.is_stale(ctx.get("stored_fingerprint"), fingerprint)
	passed = release_rules.all_required_pass(results) and not contention

	values = {
		"release_checks": json.dumps(release_rules.results_payload(results), default=str),
		"release_fingerprint": json.dumps(fingerprint, default=str),
	}
	if card.meta.get_field("spec_revision") and not card.get("spec_revision") and ctx.get("bound_revision"):
		values["spec_revision"] = ctx["bound_revision"]

	spec_updates = {}
	if passed:
		values["release_state"] = release_rules.STATE_RELEASED
		if not (was_released and card.get("released_on") and not stale):
			values["released_on"] = now
			values["released_by"] = release_rules.SYSTEM_USER
		values["release_spec_revision"] = ctx.get("bound_revision")
		values["release_price_row"] = (ctx.get("price_row") or {}).get("name")
		values["release_artwork_version"] = (ctx.get("artwork") or {}).get("version")
		values["release_override_reason"] = None
		# Clear ONLY the gate's own hold. A PPC or customer hold stays.
		if card.get("job_status") == "On Hold" and (card.get("hold_reason") or "") in release_rules.RELEASE_HOLD_REASONS:
			values["job_status"] = (card.get("hold_previous_status") or "").strip() or "Open"
			values["hold_cleared_by"] = release_rules.SYSTEM_USER
			values["hold_cleared_on"] = now
		spec = ctx.get("spec") or {}
		if spec and not spec.get("vcl_first_release_on") and frappe.get_meta(CPS).get_field("vcl_first_release_on"):
			spec_updates["vcl_first_release_on"] = now
			if spec.get("status") != cps_lifecycle_rules.STATUS_ACTIVE:
				spec_updates["status"] = cps_lifecycle_rules.STATUS_ACTIVE
	else:
		if was_released:
			values["release_state"] = release_rules.STATE_REHELD
			if card.get("render_issued_on"):
				# Already issued: not pulled back silently (§7d).
				values["print_superseded"] = 1
			elif card.get("job_status") != "On Hold":
				values["job_status"] = "On Hold"
				values["hold_reason"] = release_rules.HOLD_REASON_SPEC_CHANGED
				values["hold_remarks"] = release_rules.summary(results)
				values["hold_previous_status"] = card.get("job_status")
				values["hold_by"] = release_rules.SYSTEM_USER
				values["hold_on"] = now
		else:
			values["release_state"] = release_rules.STATE_HELD
			if card.get("job_status") not in ("On Hold", "Closed", "Cancelled", "Completed"):
				values["job_status"] = "On Hold"
				values["hold_reason"] = release_rules.HOLD_REASON_AWAITING
				values["hold_remarks"] = release_rules.summary(results)
				values["hold_previous_status"] = card.get("job_status")
				values["hold_by"] = release_rules.SYSTEM_USER
				values["hold_on"] = now
			elif (card.get("hold_reason") or "") in release_rules.RELEASE_HOLD_REASONS:
				values["hold_remarks"] = release_rules.summary(results)

	values = {k: v for k, v in values.items() if card.meta.get_field(k)}
	frappe.db.set_value(card.doctype, card.name, values, update_modified=False)
	if spec_updates:
		frappe.db.set_value(CPS, ctx["spec"]["name"], spec_updates, update_modified=False)

	summary = release_rules.summary(results)
	if contention:
		summary = "Held — specification or price changed during evaluation; re-run"
	if values.get("release_state") != prior_state or trigger == "insert":
		card.add_comment("Comment", _("Release gate ({0}): {1}").format(trigger, summary))
	frappe.log_error(
		title=LOG_TITLE,
		message=json.dumps({
			"card": card.name, "doctype": card.doctype, "trigger": trigger, "state": values.get("release_state"),
			"prior_state": prior_state, "stale": stale, "contention": contention,
			"failing": release_rules.failing_numbers(results),
			"warnings": [w.number for w in release_rules.warnings(results)],
			"bound_revision": ctx.get("bound_revision"), "price_row": (ctx.get("price_row") or {}).get("name"),
		}, default=str, indent=1),
	)
	return {
		"card": card.name,
		"release_state": values.get("release_state"),
		"summary": summary,
		"failing": release_rules.failing_numbers(results),
		"warnings": [w.number for w in release_rules.warnings(results)],
		"stale": stale,
		"contention": contention,
		"bound_revision": ctx.get("bound_revision"),
		"price_row": (ctx.get("price_row") or {}).get("name"),
		"checks": release_rules.results_payload(results),
	}


# ---------------------------------------------------------------------------
# Hooks: insert, spec, price, order
# ---------------------------------------------------------------------------


def on_card_insert(card):
	"""Controllers' ``after_insert``: hold, then evaluate at once (§7a)."""
	if not is_gated(card):
		return
	try:
		evaluate(card.doctype, card.name, trigger="insert")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "release.on_card_insert {0}".format(card.name))


def cards_for_spec(spec_name):
	out = []
	for doctype in card_doctypes():
		if not frappe.db.exists("DocType", doctype) or not has_release_fields(doctype):
			continue
		for name in frappe.get_all(
			doctype,
			filters={"customer_product_spec": spec_name, "docstatus": ["<", 2], "sales_order_item": ["is", "set"]},
			pluck="name",
		):
			out.append((doctype, name))
	return out


def cards_for_order(so_name):
	out = []
	for doctype in card_doctypes():
		if not frappe.db.exists("DocType", doctype) or not has_release_fields(doctype):
			continue
		for name in frappe.get_all(doctype, filters={"sales_order": so_name, "docstatus": ["<", 2]}, pluck="name"):
			out.append((doctype, name))
	return out


def _reevaluate(cards, trigger):
	if frappe.flags.in_release_evaluate:
		return
	for doctype, name in cards:
		try:
			evaluate(doctype, name, trigger=trigger)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "release.reevaluate {0} {1}".format(doctype, name))


def reevaluate_for_spec(spec_name, trigger="spec"):
	"""Re-evaluate every live card whose fingerprint names this specification."""
	_reevaluate(cards_for_spec(spec_name), trigger)


def on_spec_change(doc, method=None):
	"""``Customer Product Specification.on_update_after_submit``."""
	reevaluate_for_spec(doc.name, trigger="spec")


def on_sales_order_change(doc, method=None):
	"""``Sales Order.on_update_after_submit`` (amend, close, status)."""
	_reevaluate(cards_for_order(doc.name), trigger="order")


# ---------------------------------------------------------------------------
# Override, request, render, status
# ---------------------------------------------------------------------------


def _owners(card):
	owners = [card.owner]
	if card.get("sales_order"):
		owners.append(frappe.db.get_value("Sales Order", card.sales_order, "owner"))
	return owners


@frappe.whitelist()
def override(doctype, name, reason=None):
	"""Release a failing card by hand (B): VCL Management Team, not the owner, reason mandatory."""
	_assert_card_doctype(doctype)
	card = frappe.get_doc(doctype, name)
	if not is_gated(card):
		frappe.throw(_("This card is not under the release gate."))
	result = evaluate(doctype, name, trigger="override-check") or {}
	results = [release_rules.CheckResult(c["n"], c["name"], c["passed"], c["required"], c["overridable"], c["message"]) for c in result.get("checks", [])]
	refusal = release_rules.override_refusal(results, frappe.get_roles(), frappe.session.user, _owners(card), reason)
	if refusal:
		frappe.throw(_("Override refused: {0}.").format(refusal), frappe.PermissionError)

	card.reload()
	now = frappe.utils.now()
	values = {
		"release_state": release_rules.STATE_RELEASED_OVERRIDE,
		"released_by": frappe.session.user,
		"released_on": now,
		"release_override_reason": "{0} (checks {1} overridden)".format(reason.strip(), ", ".join(str(n) for n in result.get("failing", []))),
		"release_spec_revision": result.get("bound_revision"),
		"release_price_row": result.get("price_row"),
	}
	if card.get("job_status") == "On Hold" and (card.get("hold_reason") or "") in release_rules.RELEASE_HOLD_REASONS:
		values["job_status"] = (card.get("hold_previous_status") or "").strip() or "Open"
		values["hold_cleared_by"] = frappe.session.user
		values["hold_cleared_on"] = now
	frappe.db.set_value(doctype, name, values, update_modified=False)
	card.add_comment("Comment", _("Released by override ({0}): checks {1} failed. Reason: {2}").format(
		frappe.session.user, ", ".join(str(n) for n in result.get("failing", [])), reason.strip()))
	frappe.log_error(title=LOG_TITLE, message=json.dumps({"card": name, "override": True, "user": frappe.session.user,
	                                                      "failing": result.get("failing"), "reason": reason}, default=str))
	return release_status(name, doctype)


@frappe.whitelist()
def request_override(doctype, name, reason=None):
	"""A rep asks management to override: records the request, changes no state."""
	_assert_card_doctype(doctype)
	if not (reason or "").strip():
		frappe.throw(_("A reason is required."))
	card = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "read", card):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	frappe.db.set_value(doctype, name, {
		"override_requested_by": frappe.session.user,
		"override_requested_on": frappe.utils.now(),
		"override_requested_reason": reason.strip(),
	}, update_modified=False)
	card.add_comment("Comment", _("Override requested by {0}: {1}").format(frappe.session.user, reason.strip()))
	_notify_management(card, reason)
	return {"ok": True}


def _notify_management(card, reason):
	users = frappe.get_all("Has Role", filters={"role": release_rules.OVERRIDE_ROLE, "parenttype": "User"}, pluck="parent")
	for user in set(users):
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.publish_realtime("msgprint", {"message": _("Release override requested on {0}: {1}").format(card.name, reason)}, user=user)


def issuance_block(card, ctx=None):
	"""Why this card may not be rendered right now, or None. Writes nothing."""
	if not is_gated(card):
		return None
	if ctx is None:
		ctx, _versions = build_context(card, lock=False)
	fingerprint = release_rules.build_fingerprint(ctx)
	stale = release_rules.is_stale(ctx.get("stored_fingerprint"), fingerprint)
	block = release_rules.issuance_block_reason(ctx["card"], stale)
	if block and block.startswith("release state"):
		checks = json.loads(card.get("release_checks") or "[]") if card.get("release_checks") else []
		fails = [c for c in checks if not c.get("passed") and c.get("required")]
		if fails:
			block = "Held — check {0} failed: {1}".format(fails[0]["n"], fails[0]["message"] or fails[0]["name"])
	return block


@frappe.whitelist()
def prepare_render(doctype, name):
	"""Step (i) of Print: re-evaluate, persist, and on Released stamp render_issued_on/by.

	Its own transaction, so the GET that follows (the print itself) writes
	nothing. Refuses a held, stale or manually held card.
	"""
	_assert_card_doctype(doctype)
	card = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "print", card):
		frappe.throw(_("Not permitted to print {0}.").format(name), frappe.PermissionError)
	if not is_gated(card):
		return {"ok": True, "gated": False}

	evaluate(doctype, name, trigger="render")
	card.reload()
	block = issuance_block(card)
	if block:
		frappe.throw(_("Cannot print {0}: {1}.").format(name, block), title=_("Job Card Held"))

	frappe.db.set_value(doctype, name, {
		"render_issued_on": frappe.utils.now(),
		"render_issued_by": frappe.session.user,
		"print_superseded": 0,
	}, update_modified=False)
	frappe.db.commit()
	return release_status(name, doctype)


def before_print_guard(card):
	"""Step (ii): the controller's ``before_print``. Reads state, recomputes the fingerprint, throws. Writes nothing."""
	if not is_gated(card):
		return
	block = issuance_block(card)
	if block:
		frappe.throw(_("Cannot print {0}: {1}.").format(card.name, block), title=_("Job Card Held"))


@frappe.whitelist()
def confirm_printed(doctype, name):
	"""A person confirms the paper card reached the floor."""
	_assert_card_doctype(doctype)
	card = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "write", card):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	if not card.get("render_issued_on"):
		frappe.throw(_("No render has been issued for {0}.").format(name))
	frappe.db.set_value(doctype, name, {
		"printed_confirmed_on": frappe.utils.now(), "printed_confirmed_by": frappe.session.user,
	}, update_modified=False)
	return {"ok": True}


def _doctype_for(job_card):
	for doctype in card_doctypes():
		if frappe.db.exists(doctype, job_card):
			return doctype
	return None


@frappe.whitelist()
def release_status(job_card, doctype=None):
	"""Read-only state for the Order desk line, the board, the list and the Print button (Stream B)."""
	doctype = doctype or _doctype_for(job_card)
	if not doctype:
		frappe.throw(_("Job card {0} not found.").format(job_card))
	card = frappe.get_doc(doctype, job_card)
	if not frappe.has_permission(doctype, "read", card):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	if not is_gated(card):
		return {"job_card": job_card, "doctype": doctype, "gated": False, "release_state": None, "can_print": True, "block": None}
	checks = json.loads(card.get("release_checks") or "[]") if card.get("release_checks") else []
	block = issuance_block(card)
	return {
		"job_card": job_card,
		"doctype": doctype,
		"gated": True,
		"release_state": card.get("release_state") or release_rules.STATE_HELD,
		"released_by": card.get("released_by"),
		"released_on": card.get("released_on"),
		"release_spec_revision": card.get("release_spec_revision"),
		"release_price_row": card.get("release_price_row"),
		"render_issued_on": card.get("render_issued_on"),
		"print_superseded": card.get("print_superseded"),
		"manual_hold": release_rules.manual_hold_active(card),
		"failing": [c["n"] for c in checks if not c.get("passed") and c.get("required")],
		"warnings": [c["n"] for c in checks if not c.get("passed") and not c.get("required")],
		"checks": checks,
		"block": block,
		"can_print": block is None,
		"can_override": release_rules.OVERRIDE_ROLE in frappe.get_roles() and bool(
			[c for c in checks if not c.get("passed") and c.get("required")]
		) and not [c for c in checks if not c.get("passed") and c.get("required") and not c.get("overridable")],
	}
