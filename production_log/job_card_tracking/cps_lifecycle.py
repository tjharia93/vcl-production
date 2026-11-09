"""Frappe-bound half of the CPS lifecycle (Stream A §1-§3).

Every decision comes from :mod:`cps_lifecycle_rules`; this module only reads
the document, the caller's roles and the clock, and writes what the rules say.

Wired from ``CustomerProductSpecification.validate`` (draft saves),
``before_submit`` (revision 1) and ``before_update_after_submit`` (every
ordinary submitted-document save - Desk, REST, Data Import; ``validate`` does
not run there). Server code that is allowed to write the ``vcl_*`` fields
wraps its save in :func:`server_write`.
"""

import contextlib
import json

import frappe
from frappe import _

from production_log.job_card_tracking import cps_lifecycle_rules as rules

CPS = "Customer Product Specification"

# Selling Settings field naming the migration authority (§1 patch). The
# grandfather routine does nothing until Tanuj sets it, and re-runs on every
# migrate until no submitted spec is left unstamped - which is what keeps it
# out of the install-stamping trap (vcl-frappe-app runbook, trap 7).
MIGRATION_AUTHORITY_FIELD = "custom_cps_migration_authority"

# Tanuj (08/11/2026): the authority recorded on every grandfathered spec is
# Tanuj unless Selling Settings names someone else.
DEFAULT_MIGRATION_AUTHORITY = "tanuj.haria@vimit.com"


@contextlib.contextmanager
def server_write():
	"""Mark the current write as server code, allowed to touch D-tier fields."""
	previous = frappe.flags.cps_server_write
	frappe.flags.cps_server_write = True
	try:
		yield
	finally:
		frappe.flags.cps_server_write = previous


def is_server_write():
	return bool(frappe.flags.cps_server_write) or frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch


def has_lifecycle_fields(doc):
	return bool(doc.meta.get_field("vcl_revision"))


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def validate(doc):
	"""Draft saves: the §2 tiers with the identity rule relaxed; a new record arrives unstamped."""
	if not has_lifecycle_fields(doc):
		return
	if doc.is_new():
		sanitise_initial_values(doc)
		return
	_enforce_tiers(doc, submitted=False)


def sanitise_initial_values(doc):
	"""Codex r5 item 1: nothing server-owned may be pre-set by the caller on insert.

	Reset, not refused: a REST client or Data Import that copies a record
	wholesale should still create the specification, just not pre-approved.
	Server code (the IQ transfer, the migration) is exempt.
	"""
	if is_server_write():
		return
	forged = rules.forged_initial_values(doc)
	if not forged:
		return
	resets, rows = rules.initial_value_resets(doc)
	for fieldname, value in resets.items():
		if doc.meta.get_field(fieldname):
			doc.set(fieldname, value)
	price_meta = frappe.get_meta("CPS Price")
	for row, values in zip(doc.get("pricing") or [], rows):
		for fieldname, value in values.items():
			if price_meta.get_field(fieldname):
				row.set(fieldname, value)
	frappe.msgprint(
		_("Approval and revision values supplied on creation were discarded: {0}.").format(", ".join(forged)),
		indicator="orange",
	)


def record_revision_approval(doc, revision, user, now, rule=None):
	"""Keep the per-revision approval history in the revision log (Codex r5 item 5)."""
	doc.vcl_revision_log = json.dumps(
		rules.approve_revision_in_log(doc.get("vcl_revision_log"), revision, user, now, rule), default=str
	)


def before_submit(doc):
	"""Revision 1 exists from the moment the specification is real (§1)."""
	if not has_lifecycle_fields(doc):
		return
	# A draft may have been created by anyone; the submit is where revision 1
	# is born, so every approval stamp present now is discarded (item 1).
	if not is_server_write():
		for fieldname in ("vcl_approved_rev", "vcl_approved_by", "vcl_approved_on", "vcl_approval_rule", "vcl_approval_notes", "vcl_revision_log"):
			doc.set(fieldname, None)
	doc.vcl_revision = 1
	doc.vcl_approval_state = rules.APPROVAL_AWAITING
	_stamp_revision(doc)
	_run_technical_rule(doc)


def before_update_after_submit(doc):
	"""Submitted saves: tiers, then the revision bump when a material field moved."""
	if not has_lifecycle_fields(doc):
		return
	_enforce_tiers(doc, submitted=True)

	before = doc.get_doc_before_save()
	if before is None:
		return

	if (before.get("status") or "") != (doc.get("status") or "") and not rules.status_change_allowed(
		frappe.get_roles(), is_server_write()
	):
		frappe.throw(
			_("Only a Sales Master Manager or VCL Management Team may change the status of a submitted specification."),
			title=_("Specification Status"),
		)

	if rules.revision_bump_required(before, doc, doc.get("product_type")):
		changed = rules.revision_changes(before, doc, doc.get("product_type"))
		values = rules.after_revision_bump(doc.get("vcl_revision"))
		for fieldname, value in values.items():
			doc.set(fieldname, value)
		_stamp_revision(doc)
		doc.add_comment(
			"Comment",
			_("Revision {0}: {1} changed; technical approval reset to Awaiting approval.").format(
				doc.vcl_revision, ", ".join(changed)
			),
		)
		_run_technical_rule(doc)
		frappe.flags.cps_revision_bumped = doc.name


def _run_technical_rule(doc):
	"""§6: a Carton auto-approves its own revision; the others wait for their approver."""
	from production_log.job_card_tracking import cps_approval

	try:
		cps_approval.evaluate_technical(doc)
	except Exception:
		# A rule fault must never stop a specification being saved; the
		# revision simply stays Awaiting approval.
		frappe.log_error(frappe.get_traceback(), "cps_approval.evaluate_technical {0}".format(doc.name))


def _enforce_tiers(doc, submitted):
	before = doc.get_doc_before_save()
	if before is None:
		return
	refused = rules.unauthorised_changes(
		before,
		doc,
		frappe.get_roles(),
		is_server=is_server_write(),
		first_order_placed=first_order_placed(doc.name) if submitted else False,
		submitted=submitted,
	)
	if refused:
		frappe.throw(
			_("You may not change: {0}.").format(rules.describe_unauthorised(refused)),
			title=_("Specification Edit Not Permitted"),
		)


def _stamp_revision(doc):
	now = frappe.utils.now()
	doc.vcl_revision_at = now
	doc.vcl_revision_by = frappe.session.user
	payload = rules.build_revision_payload(
		doc, doc.vcl_revision, now, frappe.session.user, artwork_version=doc.get("artwork_tracker")
	)
	doc.vcl_revision_payload = json.dumps(payload, default=str, indent=1)
	log = rules.parse_revision_log(doc.get("vcl_revision_log"))
	log = [p for p in log if int((p or {}).get("_revision") or 0) != int(doc.vcl_revision)]
	log.append(payload)
	doc.vcl_revision_log = json.dumps(log, default=str)


def first_order_placed(cps):
	"""Whether any submitted Sales Order line names this specification."""
	if not cps or not frappe.get_meta("Sales Order Item").get_field("custom_cps"):
		return False
	return bool(
		frappe.db.exists("Sales Order Item", {"custom_cps": cps, "docstatus": 1, "parenttype": "Sales Order"})
	)


# ---------------------------------------------------------------------------
# Grandfathering (§1 patch, Codex r3 item 1)
# ---------------------------------------------------------------------------


def grandfather_submitted_specs(authority=None, dry_run=False):
	"""§1 migration: stamp unstamped submitted specs, then reconcile legacy card bindings.

	Two independent, idempotent passes (Codex r5 item 11): ``stamp_specs`` touches
	only specs with no revision; ``reconcile_card_bindings`` runs over every
	unbound legacy card whose spec IS stamped, every time, so a binding that
	did not verify yesterday is retried today. Writes with ``db.set_value`` so
	no validation re-runs on legacy records; ``modified`` moves on the spec so
	the stamp is visible, but no Version row is created by this path.
	"""
	if not frappe.get_meta(CPS).get_field("vcl_revision"):
		return {"skipped": "fields not landed"}

	if not authority and frappe.get_meta("Selling Settings").get_field(MIGRATION_AUTHORITY_FIELD):
		authority = frappe.db.get_single_value("Selling Settings", MIGRATION_AUTHORITY_FIELD)
	if not authority and frappe.db.exists("User", DEFAULT_MIGRATION_AUTHORITY):
		authority = DEFAULT_MIGRATION_AUTHORITY
	if not authority:
		return {"skipped": "no migration authority: set Selling Settings > CPS Migration Authority"}

	stamped = stamp_specs(authority, dry_run)
	bound, unbound = reconcile_card_bindings(dry_run)
	if (stamped or bound) and not dry_run:
		frappe.db.commit()
	return {"stamped": stamped, "cards_bound": bound, "cards_left_unbound": unbound, "authority": authority, "dry_run": dry_run}


def stamp_specs(authority, dry_run=False):
	"""Pass 1: revision 1 / approved revision 1 on every submitted spec with no revision."""
	date_text = frappe.utils.formatdate(frappe.utils.today(), "dd/mm/yyyy")
	now = frappe.utils.now()
	stamped = []
	# No "< 1" filter: a NULL revision (every row before the column existed) is
	# not < 1 in SQL. Read all submitted specs and let the rule decide.
	for row in frappe.get_all(CPS, filters={"docstatus": 1}, fields=["name", "vcl_revision"], limit_page_length=0):
		if int(row.vcl_revision or 0) >= 1:
			continue
		doc = frappe.get_doc(CPS, row.name)
		if not rules.needs_grandfathering(doc):
			continue
		values = rules.grandfather_values(doc.status, authority, date_text)
		values["vcl_approved_on"] = now
		values["vcl_revision_at"] = now
		values["vcl_revision_by"] = authority
		payload = rules.build_revision_payload(doc, 1, now, authority, artwork_version=doc.get("artwork_tracker"))
		values["vcl_revision_payload"] = json.dumps(payload, default=str, indent=1)
		values["vcl_revision_log"] = json.dumps(
			rules.approve_revision_in_log([payload], 1, authority, now, "grandfathered {0}".format(date_text)), default=str
		)
		if not dry_run:
			frappe.db.set_value(CPS, doc.name, values)
		stamped.append(doc.name)
	return stamped


def reconcile_card_bindings(dry_run=False):
	"""Pass 2: ``spec_revision`` = 1 on legacy cards whose snapshot verifies against revision 1.

	Repeatable: selects every unbound order-derived card whose spec is stamped.
	A card whose snapshot disagrees is left unbound and reported, never forced.
	"""
	from production_log.job_card_tracking import release_rules, so_spec_control

	bound, left = [], []
	payloads = {}
	for doctype in so_spec_control.JOB_CARD_DOCTYPES.values():
		meta = frappe.get_meta(doctype) if frappe.db.exists("DocType", doctype) else None
		if not meta or not meta.get_field("spec_revision") or not meta.get_field("customer_product_spec"):
			continue
		cards = frappe.get_all(
			doctype,
			filters={"docstatus": ["<", 2], "sales_order_item": ["is", "set"]},
			fields=["name", "customer_product_spec", "spec_snapshot", "spec_revision"],
			limit_page_length=0,
		)
		for card in cards:
			if int(card.spec_revision or 0) >= 1:
				continue
			spec_name = card.customer_product_spec
			if not spec_name:
				left.append("{0}:{1} (no spec)".format(doctype, card.name))
				continue
			if spec_name not in payloads:
				spec = frappe.db.get_value(CPS, spec_name, ["vcl_revision", "vcl_revision_log"], as_dict=True)
				payloads[spec_name] = (
					rules.payload_for_revision(spec.vcl_revision_log, 1) if spec and int(spec.vcl_revision or 0) >= 1 else None
				)
			payload = payloads[spec_name]
			if payload is None:
				left.append("{0}:{1} (spec not stamped)".format(doctype, card.name))
				continue
			snapshot = _parse(card.spec_snapshot)
			if snapshot and not release_rules.snapshot_mismatches(snapshot, payload):
				if not dry_run:
					frappe.db.set_value(doctype, card.name, "spec_revision", 1, update_modified=False)
				bound.append("{0}:{1}".format(doctype, card.name))
			else:
				left.append("{0}:{1}".format(doctype, card.name))
	return bound, left


def _parse(text):
	try:
		value = json.loads(text or "")
	except (TypeError, ValueError):
		return None
	return value if isinstance(value, dict) else None


@frappe.whitelist(methods=["POST"])
def run_grandfather(dry_run=1):
	"""System Manager entry point for the §1 migration. Dry run by default."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("System Manager role required."), frappe.PermissionError)
	return grandfather_submitted_specs(dry_run=bool(int(dry_run or 0)))


def after_migrate():
	"""Re-attempt the grandfather stamp on every migrate until nothing is left."""
	try:
		result = grandfather_submitted_specs()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "cps_lifecycle.after_migrate")
		return
	if result.get("stamped") or result.get("cards_bound"):
		print("CPS grandfather: stamped {0} specification(s); bound {1} card(s); {2} legacy card(s) left unbound".format(
			len(result.get("stamped") or []), len(result.get("cards_bound") or []), len(result.get("cards_left_unbound") or [])
		))


# ---------------------------------------------------------------------------
# "What changed" summary for the review panel (§3) - permlevel-0 read, no restricted values
# ---------------------------------------------------------------------------


@frappe.whitelist()
def revision_changes_summary(cps, since_revision=None):
	"""Field label, old -> new, who and when, per revision - without level-1 values.

	The payload and log sit at permlevel 1 (they carry CR21 packing figures), so
	a rep cannot read them; this read method needs only level-0 read on the
	specification and withholds the VALUE of any field whose permlevel the
	caller cannot read (the label and "changed" are still shown). Stream B's
	screen and the Desk panel read this, never the raw log.
	"""
	if not frappe.has_permission(CPS, "read", cps):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	meta = frappe.get_meta(CPS)
	spec = frappe.db.get_value(CPS, cps, ["vcl_revision", "vcl_approved_rev", "vcl_revision_log", "product_type"], as_dict=True)
	if not spec:
		frappe.throw(_("Specification {0} not found.").format(cps))

	readable_levels = set(frappe.permissions.get_permitted_permlevels(CPS)) if hasattr(frappe.permissions, "get_permitted_permlevels") else {0}
	log = rules.parse_revision_log(spec.vcl_revision_log)
	entries = sorted((e for e in log if isinstance(e, dict)), key=lambda e: int(e.get("_revision") or 0))
	since = int(since_revision or 0)
	out = []
	previous = None
	for entry in entries:
		revision = int(entry.get("_revision") or 0)
		changes = []
		if previous is not None:
			for fieldname in rules.revision_fields(spec.product_type):
				old, new = previous.get(fieldname), entry.get(fieldname)
				if rules._norm(old) == rules._norm(new):
					continue
				df = meta.get_field(fieldname)
				visible = df is None or int(df.permlevel or 0) in readable_levels
				changes.append({
					"fieldname": fieldname,
					"label": df.label if df else fieldname,
					"old": old if visible else None,
					"new": new if visible else None,
					"value_hidden": not visible,
				})
			for table in rules.REVISION_TABLES:
				if rules._rows(previous, table, rules.REVISION_TABLES[table]) != rules._rows(entry, table, rules.REVISION_TABLES[table]):
					df = meta.get_field(table)
					changes.append({"fieldname": table, "label": df.label if df else table, "old": None, "new": None, "value_hidden": False, "rows_changed": True})
		if revision >= since:
			out.append({
				"revision": revision,
				"at": entry.get("_at"),
				"by": entry.get("_by"),
				"approved_by": entry.get("_approved_by"),
				"approved_on": entry.get("_approved_on"),
				"revoked_on": entry.get("_revoked_on"),
				"approval_rule": entry.get("_approval_rule"),
				"is_current": revision == int(spec.vcl_revision or 0),
				"changes": changes,
			})
		previous = entry
	return {"cps": cps, "current_revision": spec.vcl_revision, "approved_revision": spec.vcl_approved_rev, "revisions": out}
