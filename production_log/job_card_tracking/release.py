"""The job-card release gate, Frappe-bound half (Stream A §7c-§7e; Codex r4/r5).

Every check is a pure function in :mod:`release_rules`; this module assembles
the context from the card, its Sales Order line, the specification, the BOUND
revision payload, the BOUND price row and the BOUND artwork version, runs the
checks, and writes the result. "On hold" means one thing: the card cannot be
printed until it is Released.

Gate mode (``Selling Settings.custom_cps_gate_mode``, ships **Off**):
  Off      - nothing here runs; no card is ever held by the gate.
  Observe  - every card is evaluated and the result recorded (release_state,
             checks, fingerprint, bindings) but job_status is never touched and
             Print is never refused. The §9 observation fortnight.
  Enforce  - hold on insert, clear only the gate's own hold on release, refuse
             print of a held / stale / manually held card.

Locking (Codex r5 item 4): the card row, the Sales Order header and line, the
sibling cards on that line, the specification, its price rows and its artwork
versions are locked ``FOR UPDATE`` BEFORE anything is read; the documents are
then reloaded under those locks. A version set (row counts + max modified) is
compared before and after as a belt; on a difference the evaluation re-runs
once and otherwise the card stays held.

Bound semantics (items 5, 7): checks read ``card.spec_revision``,
``card.release_price_row`` and ``card.release_artwork_version``; a first
evaluation binds (the SO line's selected row, the current artwork version) and
after that only :func:`refresh_binding` changes them. An authorised override
survives re-evaluation for its exact fingerprint; only an input change
invalidates it.

Persistence (item 8): ``prepare_render`` commits the evaluation before it
decides whether to refuse, so a refused render still leaves the held result
on the card. ``withdraw_and_reissue`` is the explicit path out of
``print_superseded``.
"""

import json

import frappe
from frappe import _

from production_log.job_card_tracking import (
	cps_lifecycle_rules,
	cps_pricing,
	release_rules,
	so_spec_control,
)

CPS = "Customer Product Specification"
ARTWORK_VERSION = "CPS Artwork Version"
LOG_TITLE = "vcl_release"

REBIND_ROLES = cps_lifecycle_rules.MANAGER_ROLES | {"CPS Approver"}
WITHDRAW_ROLES = frozenset({"Production Manager", "VCL Management Team", "System Manager"})


def card_doctypes():
	return tuple(so_spec_control.JOB_CARD_DOCTYPES.values())


def has_release_fields(doctype):
	return bool(frappe.get_meta(doctype).get_field("release_state"))


def gate_mode():
	return so_spec_control.gate_mode()


def gate_off():
	return gate_mode() == so_spec_control.GATE_OFF


def enforcing():
	return gate_mode() == so_spec_control.GATE_ENFORCE


def _assert_card_doctype(doctype):
	if doctype not in card_doctypes():
		frappe.throw(_("{0} is not a job card the release gate knows.").format(doctype))


def _parse(text):
	try:
		value = json.loads(text or "")
	except (TypeError, ValueError):
		return None
	return value if isinstance(value, dict) else None


def _parse_list(text):
	try:
		value = json.loads(text or "")
	except (TypeError, ValueError):
		return []
	return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Locks and versions (item 4)
# ---------------------------------------------------------------------------


def _lock_rows(table, where, params):
	"""``SELECT name, modified ... FOR UPDATE``; returns the rows (locked for the transaction)."""
	return frappe.db.sql(
		"SELECT name, modified FROM `tab{0}` WHERE {1} FOR UPDATE".format(table, where), params, as_dict=True,
	)


def _version_of(rows):
	"""(count, max modified, hash of names) - a deletion changes the count and the names."""
	names = sorted(r.name for r in rows)
	modified = max((str(r.modified) for r in rows), default=None)
	return (len(rows), modified, "|".join(names))


def lock_and_version(doctype, name):
	"""Lock everything the checks read, in a fixed order, and return the version set.

	Order (Codex r6 defect 4): shared parents first - Sales Order header, then
	the line - then EVERY card on that line including this one, by name, then
	the specification, its price rows, its artwork versions. The same function
	is the only lock path, so no two evaluations can take the locks in
	different orders. A card with no line locks only itself.
	"""
	versions = {}
	head = frappe.db.get_value(doctype, name, ["sales_order", "sales_order_item", "customer_product_spec"], as_dict=True)
	if not head:
		versions["card"] = _version_of([])
		return versions

	if head.sales_order:
		versions["order"] = _version_of(_lock_rows("Sales Order", "name = %(n)s", {"n": head.sales_order}))
	if head.sales_order_item:
		versions["line"] = _version_of(_lock_rows("Sales Order Item", "name = %(n)s", {"n": head.sales_order_item}))
		siblings = frappe.db.sql(
			"SELECT name, modified FROM `tab{0}` WHERE sales_order_item = %(l)s AND docstatus < 2 ORDER BY name FOR UPDATE".format(doctype),
			{"l": head.sales_order_item}, as_dict=True,
		)
		versions["siblings"] = _version_of(siblings)
		if not any(r.name == name for r in siblings):
			versions["card"] = _version_of(_lock_rows(doctype, "name = %(n)s", {"n": name}))
	else:
		versions["card"] = _version_of(_lock_rows(doctype, "name = %(n)s", {"n": name}))
	spec_name = head.customer_product_spec
	if not spec_name and head.sales_order_item and frappe.get_meta("Sales Order Item").get_field("custom_cps"):
		spec_name = frappe.db.get_value("Sales Order Item", head.sales_order_item, "custom_cps")
	if spec_name:
		versions["spec"] = _version_of(_lock_rows(CPS, "name = %(n)s", {"n": spec_name}))
		versions["prices"] = _version_of(_lock_rows(
			"CPS Price", "parent = %(n)s AND parenttype = 'Customer Product Specification'", {"n": spec_name},
		))
		if frappe.db.exists("DocType", ARTWORK_VERSION):
			versions["artwork"] = _version_of(_lock_rows(ARTWORK_VERSION, "spec = %(n)s", {"n": spec_name}))
	return versions


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def _read_line(line_name):
	meta = frappe.get_meta("Sales Order Item")
	columns = ["name", "parent", "qty", "rate", "uom", "conversion_factor", "item_code"]
	for extra in ("custom_cps", "custom_cps_price_row", "custom_price_override_reason"):
		if meta.get_field(extra):
			columns.append(extra)
	return frappe.db.get_value("Sales Order Item", line_name, columns, as_dict=True)


def _other_cards_qty(card):
	rows = frappe.get_all(
		card.doctype,
		filters={"sales_order_item": card.sales_order_item, "docstatus": ["in", [0, 1]], "name": ["!=", card.name]},
		pluck="quantity_ordered",
	)
	return sum(float(q or 0) for q in rows)


def _artwork_state(spec_name, bound_version=None):
	"""The artwork version BOUND to the card decides (artwork_rules.artwork_for_card)."""
	from production_log.job_card_tracking import cps_artwork

	state = cps_artwork.artwork_for_card(spec_name, bound_version)
	return {
		"state": state.state, "version": state.version, "versions_exist": state.versions_exist,
		"superseded": state.superseded, "note": state.note,
	}


def _bound_revision(card, spec):
	"""The card's own binding and nothing else (Codex r7).

	``spec_revision`` is stamped once, at creation, from the specification's
	revision at that moment (``stamp_creation_binding``); the migration binds
	legacy cards whose snapshot verifies. A card with neither stays Held with
	"binding unverified" until a manager rebinds it explicitly.
	"""
	for fieldname in ("spec_revision", "release_spec_revision"):
		value = card.get(fieldname) if card.meta.get_field(fieldname) else None
		if value:
			return int(value)
	return 0


def _bound_payload(spec, revision):
	payload = cps_lifecycle_rules.payload_for_revision(spec.get("vcl_revision_log"), revision)
	if payload is None:
		current = cps_lifecycle_rules.parse_payload(spec.get("vcl_revision_payload"))
		if current and int(current.get("_revision") or 0) == int(revision):
			payload = current
	return payload


def _bound_price_row(card, line, spec, order):
	"""The card's bound row first (item 5); the SO line's selection binds a new card; else select."""
	bound_row_name = card.get("release_price_row") if card.meta.get_field("release_price_row") else None
	row_name = bound_row_name or (line or {}).get("custom_cps_price_row")
	row = cps_pricing.get_price_row(spec["name"], row_name) if row_name else None
	if row is None and not bound_row_name and order:
		row = cps_pricing.get_eligible_price(spec["name"], order.transaction_date, order.currency)
	return row


def build_context(card):
	"""Everything the eleven checks read. Call after :func:`lock_and_version`."""
	order = frappe.db.get_value(
		"Sales Order", card.sales_order,
		["name", "docstatus", "status", "customer", "transaction_date", "currency", "owner"],
		as_dict=True,
	) if card.get("sales_order") else None
	line = _read_line(card.sales_order_item) if card.get("sales_order_item") else None

	spec_name = card.get("customer_product_spec") or (line or {}).get("custom_cps")
	spec = frappe.get_doc(CPS, spec_name).as_dict() if spec_name and frappe.db.exists(CPS, spec_name) else None

	bound_revision = _bound_revision(card, spec) if spec else 0
	bound_payload = _bound_payload(spec, bound_revision) if spec else None
	price_row = _bound_price_row(card, line, spec, order) if spec else None
	bound_artwork = card.get("release_artwork_version") if card.meta.get_field("release_artwork_version") else None

	return {
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
		"artwork": _artwork_state(spec_name, bound_artwork) if spec_name else {
			"state": None, "version": None, "versions_exist": False, "superseded": False, "note": ""},
		"stored_fingerprint": _parse(card.get("release_fingerprint")) if card.meta.get_field("release_fingerprint") else None,
	}


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


def is_gated(card):
	"""Only an order-derived card with the release fields, and only when the gate is on."""
	return bool(card.get("sales_order_item")) and has_release_fields(card.doctype) and not gate_off()


def evaluate(doctype, name, trigger="manual"):
	"""Lock, read, run the checks, persist. Returns the summary dict or None (gate Off / not gated)."""
	_assert_card_doctype(doctype)
	if frappe.flags.in_release_evaluate or gate_off():
		return None
	if not has_release_fields(doctype):
		return None

	frappe.flags.in_release_evaluate = True
	try:
		before = lock_and_version(doctype, name)
		card = frappe.get_doc(doctype, name)  # reloaded under the locks
		if not is_gated(card) or card.docstatus == 2:
			return None
		ctx = build_context(card)
		results, fingerprint = release_rules.evaluate(ctx)
		after = lock_and_version(doctype, name)
		contention = after != before
		if contention:
			card = frappe.get_doc(doctype, name)
			ctx = build_context(card)
			results, fingerprint = release_rules.evaluate(ctx)
			contention = lock_and_version(doctype, name) != after
		return _apply(card, ctx, results, fingerprint, trigger, contention)
	finally:
		frappe.flags.in_release_evaluate = False


def _hold_values(card, reason, summary, now):
	return {
		"job_status": "On Hold",
		"hold_reason": reason,
		"hold_remarks": summary,
		"hold_previous_status": card.get("job_status"),
		"hold_by": release_rules.SYSTEM_USER,
		"hold_on": now,
	}


def _apply(card, ctx, results, fingerprint, trigger, contention):
	now = frappe.utils.now()
	enforce = enforcing()
	prior_state = card.get("release_state") or release_rules.STATE_HELD
	was_released = prior_state in (release_rules.STATE_RELEASED, release_rules.STATE_RELEASED_OVERRIDE)
	stale = release_rules.is_stale(ctx.get("stored_fingerprint"), fingerprint)
	checks_pass = release_rules.all_required_pass(results) and not contention
	# Item 7: an authorised override stands for the exact inputs it was given.
	override_stands = prior_state == release_rules.STATE_RELEASED_OVERRIDE and not stale and not contention
	passed = checks_pass or override_stands

	values = {
		"release_checks": json.dumps(release_rules.results_payload(results), default=str),
		"release_fingerprint": json.dumps(fingerprint, default=str),
	}
	# The revision binding is never stamped here (creation or migration only);
	# the first evaluation binds price row and artwork, then only refresh_binding.
	if not card.get("release_price_row") and (ctx.get("price_row") or {}).get("name"):
		values["release_price_row"] = ctx["price_row"]["name"]
	if not card.get("release_artwork_version") and (ctx.get("artwork") or {}).get("version"):
		values["release_artwork_version"] = ctx["artwork"]["version"]
	values["release_spec_revision"] = ctx.get("bound_revision")

	spec_updates = {}
	if passed:
		values["release_state"] = release_rules.STATE_RELEASED_OVERRIDE if override_stands and not checks_pass else release_rules.STATE_RELEASED
		if not (was_released and card.get("released_on") and not stale):
			values["released_on"] = now
			values["released_by"] = release_rules.SYSTEM_USER
		if checks_pass:
			values["release_override_reason"] = None if not override_stands else card.get("release_override_reason")
		# Clear ONLY the gate's own hold. A PPC or customer hold stays (Codex r4 point 2).
		if enforce and card.get("job_status") == "On Hold" and (card.get("hold_reason") or "") in release_rules.RELEASE_HOLD_REASONS:
			values["job_status"] = (card.get("hold_previous_status") or "").strip() or "Open"
			values["hold_cleared_by"] = release_rules.SYSTEM_USER
			values["hold_cleared_on"] = now
		spec = ctx.get("spec") or {}
		if enforce and spec and not spec.get("vcl_first_release_on") and frappe.get_meta(CPS).get_field("vcl_first_release_on"):
			spec_updates["vcl_first_release_on"] = now
			if spec.get("status") != cps_lifecycle_rules.STATUS_ACTIVE:
				spec_updates["status"] = cps_lifecycle_rules.STATUS_ACTIVE
	else:
		summary = release_rules.summary(results)
		if was_released:
			values["release_state"] = release_rules.STATE_REHELD
			if card.get("render_issued_on"):
				values["print_superseded"] = 1  # issued: not pulled back silently (§7d)
			elif enforce and card.get("job_status") != "On Hold":
				values.update(_hold_values(card, release_rules.HOLD_REASON_SPEC_CHANGED, summary, now))
		else:
			values["release_state"] = release_rules.STATE_HELD
			if enforce and card.get("job_status") not in ("On Hold", "Closed", "Cancelled", "Completed"):
				values.update(_hold_values(card, release_rules.HOLD_REASON_AWAITING, summary, now))
			elif (card.get("hold_reason") or "") in release_rules.RELEASE_HOLD_REASONS:
				values["hold_remarks"] = summary

	values = {k: v for k, v in values.items() if card.meta.get_field(k)}
	frappe.db.set_value(card.doctype, card.name, values, update_modified=False)
	if spec_updates:
		frappe.db.set_value(CPS, ctx["spec"]["name"], spec_updates, update_modified=False)

	summary = release_rules.summary(results)
	if override_stands and not checks_pass:
		summary = "Released (override) - override stands for unchanged inputs"
	if contention:
		summary = "Held — specification or price changed during evaluation; re-run"
	state_changed = values.get("release_state") != prior_state
	if state_changed or trigger == "insert":
		card.add_comment("Comment", _("Release gate ({0}, {1}): {2}").format(trigger, gate_mode(), summary))
	if state_changed or contention or trigger in ("insert", "override-check"):
		# Not every successful re-evaluation: only a transition or a problem.
		frappe.log_error(
			title=LOG_TITLE,
			message=json.dumps({
				"card": card.name, "doctype": card.doctype, "trigger": trigger, "mode": gate_mode(),
				"state": values.get("release_state"), "prior_state": prior_state, "stale": stale,
				"contention": contention, "failing": release_rules.failing_numbers(results),
				"warnings": [w.number for w in release_rules.warnings(results)],
				"bound_revision": ctx.get("bound_revision"), "price_row": (ctx.get("price_row") or {}).get("name"),
				"artwork_version": (ctx.get("artwork") or {}).get("version"),
			}, default=str, indent=1),
		)
	return {
		"card": card.name,
		"mode": gate_mode(),
		"release_state": values.get("release_state"),
		"summary": summary,
		"failing": release_rules.failing_numbers(results),
		"warnings": [w.number for w in release_rules.warnings(results)],
		"stale": stale,
		"contention": contention,
		"bound_revision": ctx.get("bound_revision"),
		"price_row": (ctx.get("price_row") or {}).get("name"),
		"artwork_version": (ctx.get("artwork") or {}).get("version"),
		"checks": release_rules.results_payload(results),
	}


# ---------------------------------------------------------------------------
# Hooks: insert, spec, artwork, order
# ---------------------------------------------------------------------------


def stamp_creation_binding(card):
	"""On a NEW gated card: blank hold / release state, then bind the spec's current revision and hold (Enforce).

	Called from the controllers' ``validate`` while ``is_new()``. The hold is
	written here, in the insert itself, so an Enforce-mode card is On Hold from
	its first moment; the evaluation that may clear it runs after commit.
	"""
	if not is_gated(card):
		return
	spec_name = card.get("customer_product_spec")
	if spec_name and card.meta.get_field("spec_revision") and frappe.get_meta(CPS).get_field("vcl_revision"):
		card.spec_revision = int(frappe.db.get_value(CPS, spec_name, "vcl_revision") or 0) or None
	card.release_state = release_rules.STATE_HELD
	if enforcing() and card.get("job_status") not in ("On Hold", "Closed", "Cancelled", "Completed") and card.meta.get_field("hold_reason"):
		card.hold_previous_status = card.get("job_status")
		card.job_status = "On Hold"
		card.hold_reason = release_rules.HOLD_REASON_AWAITING
		card.hold_remarks = "Awaiting release evaluation"
		card.hold_by = release_rules.SYSTEM_USER
		card.hold_on = frappe.utils.now()


def on_card_insert(card):
	"""Controllers' ``after_insert``: evaluate after the insert commits (§7a).

	Enqueued, not run inline (Codex r7 item 3): the insert transaction already
	holds the new card's row and would take the parents afterwards - the
	opposite of ``lock_and_version``'s order.
	"""
	if not is_gated(card):
		return
	_reevaluate_async([(card.doctype, card.name)], trigger="insert")


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


DEADLOCK_RETRIES = 3


def _is_deadlock(exc):
	if isinstance(exc, getattr(frappe, "QueryDeadlockError", ())):
		return True
	args = getattr(exc, "args", ())
	return bool(args) and args[0] in (1213, 1205)


def reevaluate_cards(cards, trigger="spec"):
	"""Background job: evaluate each card, retrying transient deadlocks / lock waits."""
	if gate_off():
		return
	for doctype, name in cards:
		for attempt in range(1, DEADLOCK_RETRIES + 1):
			try:
				evaluate(doctype, name, trigger=trigger)
				frappe.db.commit()
				break
			except Exception as exc:
				frappe.db.rollback()
				if _is_deadlock(exc) and attempt < DEADLOCK_RETRIES:
					continue
				frappe.log_error(frappe.get_traceback(), "release.reevaluate {0} {1} (attempt {2})".format(doctype, name, attempt))
				break


def _reevaluate_async(cards, trigger):
	"""Enqueue after the current transaction commits (Codex r7 item 3).

	A save hook holds the spec (or artwork) row and would then lock the order
	- the reverse of ``lock_and_version``. Running after commit, in its own
	job, keeps one lock order on every path. Inert when the gate is Off.
	"""
	if not cards or frappe.flags.in_release_evaluate or gate_off():
		return
	if frappe.flags.in_test or frappe.flags.in_migrate:
		reevaluate_cards(cards, trigger)
		return
	frappe.enqueue(
		"production_log.job_card_tracking.release.reevaluate_cards",
		queue="short",
		enqueue_after_commit=True,
		cards=list(cards),
		trigger=trigger,
	)


def _reevaluate(cards, trigger):
	_reevaluate_async(cards, trigger)


def reevaluate_for_spec(spec_name, trigger="spec"):
	"""Re-evaluate (after commit) every live card whose fingerprint names this specification."""
	_reevaluate(cards_for_spec(spec_name), trigger)


def on_spec_change(doc, method=None):
	"""``Customer Product Specification.on_update_after_submit`` / ``on_cancel``."""
	reevaluate_for_spec(doc.name, trigger="spec")


def on_artwork_change(doc, method=None):
	"""``CPS Artwork Version.on_update``."""
	reevaluate_for_spec(doc.spec, trigger="artwork")


def on_sales_order_change(doc, method=None):
	"""``Sales Order.on_update_after_submit`` / ``on_cancel`` (amend, close, cancel)."""
	_reevaluate(cards_for_order(doc.name), trigger="order")


# ---------------------------------------------------------------------------
# Override, request, rebind, render, withdraw, status
# ---------------------------------------------------------------------------


def _owners(card):
	owners = [card.owner]
	if card.get("sales_order"):
		owners.append(frappe.db.get_value("Sales Order", card.sales_order, "owner"))
	return owners


def _results_from(result):
	return [
		release_rules.CheckResult(c["n"], c["name"], c["passed"], c["required"], c["overridable"], c["message"])
		for c in (result or {}).get("checks", [])
	]


@frappe.whitelist(methods=["POST"])
def override(doctype, name, reason=None):
	"""Release a failing card by hand (B): VCL Management Team, not the owner, reason mandatory."""
	_assert_card_doctype(doctype)
	card = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "write", card):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	if not is_gated(card):
		frappe.throw(_("This card is not under the release gate."))
	result = evaluate(doctype, name, trigger="override-check") or {}
	results = _results_from(result)
	refusal = release_rules.override_refusal(results, frappe.get_roles(), frappe.session.user, _owners(card), reason)
	if refusal:
		frappe.throw(_("Override refused: {0}.").format(refusal), frappe.PermissionError)

	card.reload()
	now = frappe.utils.now()
	failing = ", ".join(str(n) for n in result.get("failing", []))
	values = {
		"release_state": release_rules.STATE_RELEASED_OVERRIDE,
		"released_by": frappe.session.user,
		"released_on": now,
		"release_override_reason": "{0} (checks {1} overridden)".format(reason.strip(), failing),
	}
	if enforcing() and card.get("job_status") == "On Hold" and (card.get("hold_reason") or "") in release_rules.RELEASE_HOLD_REASONS:
		values["job_status"] = (card.get("hold_previous_status") or "").strip() or "Open"
		values["hold_cleared_by"] = frappe.session.user
		values["hold_cleared_on"] = now
	frappe.db.set_value(doctype, name, values, update_modified=False)
	card.add_comment("Comment", _("Released by override ({0}): checks {1} failed. Reason: {2}").format(
		frappe.session.user, failing, reason.strip()))
	frappe.log_error(title=LOG_TITLE, message=json.dumps({
		"card": name, "override": True, "user": frappe.session.user, "failing": result.get("failing"), "reason": reason,
		"fingerprint": result.get("checks") and _parse(frappe.db.get_value(doctype, name, "release_fingerprint")),
	}, default=str))
	return release_status(name, doctype)


@frappe.whitelist(methods=["POST"])
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


@frappe.whitelist(methods=["POST"])
def refresh_binding(doctype, name, spec_revision=None, price_row=None, artwork_version=None):
	"""Explicitly rebind a card to a different revision / price row / artwork version (item 5).

	The approver's recorded refresh, never a side effect of evaluation. Each
	target must exist on the card's specification; the card is re-evaluated
	against the new bindings and the result recorded.
	"""
	_assert_card_doctype(doctype)
	if not set(frappe.get_roles()) & REBIND_ROLES:
		frappe.throw(_("A manager or CPS Approver rebinds a card."), frappe.PermissionError)
	card = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "write", card):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	spec_name = card.get("customer_product_spec")
	spec = frappe.db.get_value(CPS, spec_name, ["vcl_revision", "vcl_revision_log"], as_dict=True) if spec_name else None
	if not spec:
		frappe.throw(_("Card {0} has no specification.").format(name))

	values, changes = {}, []
	if spec_revision not in (None, ""):
		revision = int(spec_revision)
		if revision < 1 or revision > int(spec.vcl_revision or 0) or (
			cps_lifecycle_rules.payload_for_revision(spec.vcl_revision_log, revision) is None and revision != int(spec.vcl_revision or 0)
		):
			frappe.throw(_("Revision {0} does not exist on {1}.").format(revision, spec_name))
		values["spec_revision"] = revision
		changes.append("revision {0} -> {1}".format(card.get("spec_revision"), revision))
	if price_row not in (None, ""):
		row = cps_pricing.get_price_row(spec_name, price_row)
		if not row:
			frappe.throw(_("Price row {0} is not on {1}.").format(price_row, spec_name))
		values["release_price_row"] = price_row
		changes.append("price row {0} -> {1}".format(card.get("release_price_row"), price_row))
	if artwork_version not in (None, ""):
		if not frappe.db.exists(ARTWORK_VERSION, {"name": artwork_version, "spec": spec_name}):
			frappe.throw(_("Artwork version {0} is not on {1}.").format(artwork_version, spec_name))
		values["release_artwork_version"] = artwork_version
		changes.append("artwork {0} -> {1}".format(card.get("release_artwork_version"), artwork_version))
	if not values:
		frappe.throw(_("Nothing to rebind."))

	frappe.db.set_value(doctype, name, values, update_modified=False)
	card.add_comment("Comment", _("Binding refreshed by {0}: {1}").format(frappe.session.user, "; ".join(changes)))
	evaluate(doctype, name, trigger="rebind")
	return release_status(name, doctype)


def issuance_block(card, require_issued=False):
	"""Why this card may not be rendered right now, or None. Writes nothing.

	Observe mode never blocks; the reason is still computed for the board.
	``require_issued`` is the print-time rule: a render needs its issuance stamp.
	"""
	if not is_gated(card):
		return None
	ctx = build_context(card)
	fingerprint = release_rules.build_fingerprint(ctx)
	stale = release_rules.is_stale(ctx.get("stored_fingerprint"), fingerprint)
	card_view = dict(ctx["card"], render_issued_on=card.get("render_issued_on"))
	block = release_rules.issuance_block_reason(card_view, stale, require_issued)
	if block and block.startswith("release state"):
		fails = [c for c in _parse_list(card.get("release_checks")) if not c.get("passed") and c.get("required")]
		if fails:
			block = "Held — check {0} failed: {1}".format(fails[0]["n"], fails[0]["message"] or fails[0]["name"])
	return block


@frappe.whitelist(methods=["POST"])
def prepare_render(doctype, name):
	"""Step (i) of Print: re-evaluate, COMMIT, then decide; on Released stamp render_issued_on/by.

	The evaluation is committed before any refusal (Codex r5 item 8), so a
	refused render still leaves the held result on the card. In Observe mode
	the render is never refused; the result is recorded all the same.
	"""
	_assert_card_doctype(doctype)
	card = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "print", card):
		frappe.throw(_("Not permitted to print {0}.").format(name), frappe.PermissionError)
	if not is_gated(card):
		return {"ok": True, "gated": False, "mode": gate_mode()}

	# Evaluate, decide and stamp while the evaluation's locks are still held
	# (Codex r6: committing first would let another writer slip between the
	# decision and the stamp). The single commit below makes the evaluation
	# durable in both branches; the throw after it rolls nothing back.
	evaluate(doctype, name, trigger="render")
	card.reload()
	block = issuance_block(card)
	if block and enforcing():
		frappe.db.commit()
		frappe.throw(_("Cannot print {0}: {1}.").format(name, block), title=_("Job Card Held"))

	frappe.db.set_value(doctype, name, {
		"render_issued_on": frappe.utils.now(),
		"render_issued_by": frappe.session.user,
		"print_superseded": 0,
	}, update_modified=False)
	frappe.db.commit()
	status = release_status(name, doctype)
	status["observed_block"] = block if block else None
	return status


def before_print_guard(card):
	"""Step (ii): the controller's ``before_print``. Reads, recomputes the fingerprint, throws (Enforce). Writes nothing."""
	if not is_gated(card) or not enforcing():
		return
	block = issuance_block(card, require_issued=True)
	if block:
		frappe.throw(_("Cannot print {0}: {1}.").format(card.name, block), title=_("Job Card Held"))


@frappe.whitelist(methods=["POST"])
def withdraw_and_reissue(doctype, name, note=None):
	"""The Production Manager records the paper card withdrawn; the card re-evaluates and may be reissued.

	The explicit path out of ``print_superseded`` (item 8). Reissue itself is
	the next ``prepare_render``, which stamps a fresh render.
	"""
	_assert_card_doctype(doctype)
	if not set(frappe.get_roles()) & WITHDRAW_ROLES:
		frappe.throw(_("The Production Manager withdraws a superseded card."), frappe.PermissionError)
	card = frappe.get_doc(doctype, name)
	if not int(card.get("print_superseded") or 0):
		frappe.throw(_("{0} is not marked print-superseded.").format(name))
	frappe.db.set_value(doctype, name, {
		"print_superseded": 0, "render_issued_on": None, "render_issued_by": None,
		"printed_confirmed_on": None, "printed_confirmed_by": None,
	}, update_modified=False)
	card.add_comment("Comment", _("Superseded paper card withdrawn by {0}{1}").format(
		frappe.session.user, ": " + note.strip() if (note or "").strip() else ""))
	evaluate(doctype, name, trigger="withdraw")
	return release_status(name, doctype)


@frappe.whitelist(methods=["POST"])
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
	mode = gate_mode()
	if not is_gated(card):
		return {"job_card": job_card, "doctype": doctype, "gated": False, "mode": mode, "release_state": None,
		        "can_print": True, "block": None}
	checks = _parse_list(card.get("release_checks"))
	block = issuance_block(card)
	failing = [c for c in checks if not c.get("passed") and c.get("required")]
	return {
		"job_card": job_card,
		"doctype": doctype,
		"gated": True,
		"mode": mode,
		"release_state": card.get("release_state") or release_rules.STATE_HELD,
		"released_by": card.get("released_by"),
		"released_on": card.get("released_on"),
		"spec_revision": card.get("spec_revision"),
		"release_spec_revision": card.get("release_spec_revision"),
		"release_price_row": card.get("release_price_row"),
		"release_artwork_version": card.get("release_artwork_version"),
		"render_issued_on": card.get("render_issued_on"),
		"print_superseded": card.get("print_superseded"),
		"manual_hold": release_rules.manual_hold_active(card),
		"failing": [c["n"] for c in failing],
		"warnings": [c["n"] for c in checks if not c.get("passed") and not c.get("required")],
		"checks": checks,
		"block": block,
		# Observe mode records the block but never refuses the print.
		"can_print": block is None or mode != so_spec_control.GATE_ENFORCE,
		"can_override": release_rules.OVERRIDE_ROLE in frappe.get_roles() and bool(failing)
		and not [c for c in failing if not c.get("overridable")],
	}
