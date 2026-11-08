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
	"""Draft saves: the §2 tiers with the identity rule relaxed."""
	if not has_lifecycle_fields(doc):
		return
	_enforce_tiers(doc, submitted=False)


def before_submit(doc):
	"""Revision 1 exists from the moment the specification is real (§1)."""
	if not has_lifecycle_fields(doc):
		return
	if int(doc.get("vcl_revision") or 0) < 1:
		doc.vcl_revision = 1
	doc.vcl_approval_state = rules.APPROVAL_AWAITING
	_stamp_revision(doc)


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
		frappe.flags.cps_revision_bumped = doc.name


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
	"""Stamp revision 1 / approved revision 1 on every submitted spec that has none.

	Idempotent: a stamped spec is never touched again. Run from
	``after_migrate`` and callable by a System Manager. Writes with
	``db.set_value`` so ``modified`` moves (Version records the migration) but
	no validation re-runs on legacy records that could not pass it today.
	"""
	if not frappe.get_meta(CPS).get_field("vcl_revision"):
		return {"skipped": "fields not landed"}

	if not authority and frappe.get_meta("Selling Settings").get_field(MIGRATION_AUTHORITY_FIELD):
		authority = frappe.db.get_single_value("Selling Settings", MIGRATION_AUTHORITY_FIELD)
	if not authority:
		return {"skipped": "no migration authority set on Selling Settings"}

	date_text = frappe.utils.formatdate(frappe.utils.today(), "dd/mm/yyyy")
	now = frappe.utils.now()
	stamped, unbound = [], []
	specs = frappe.get_all(
		CPS,
		filters={"docstatus": 1, "vcl_revision": ["<", 1]},
		fields=["name", "status"],
	)
	for row in specs:
		doc = frappe.get_doc(CPS, row.name)
		if not rules.needs_grandfathering(doc):
			continue
		values = rules.grandfather_values(doc.status, authority, date_text)
		values["vcl_approved_on"] = now
		values["vcl_revision_at"] = now
		values["vcl_revision_by"] = authority
		payload = rules.build_revision_payload(doc, 1, now, authority, artwork_version=doc.get("artwork_tracker"))
		values["vcl_revision_payload"] = json.dumps(payload, default=str, indent=1)
		values["vcl_revision_log"] = json.dumps([payload], default=str)
		if not dry_run:
			frappe.db.set_value(CPS, doc.name, values)
		stamped.append(doc.name)
		unbound.extend(_bind_legacy_cards(doc, payload, dry_run))

	if stamped and not dry_run:
		frappe.db.commit()
	return {"stamped": stamped, "cards_left_unbound": unbound, "authority": authority, "dry_run": dry_run}


def _bind_legacy_cards(spec, payload, dry_run):
	"""Backfill ``spec_revision`` = 1 on legacy cards whose snapshot verifies.

	A card whose ``spec_snapshot`` disagrees with the grandfathered payload is
	left unbound and reported, never forced.
	"""
	from production_log.job_card_tracking import so_spec_control

	left = []
	for doctype in so_spec_control.JOB_CARD_DOCTYPES.values():
		meta = frappe.get_meta(doctype) if frappe.db.exists("DocType", doctype) else None
		if not meta or not meta.get_field("spec_revision") or not meta.get_field("customer_product_spec"):
			continue
		cards = frappe.get_all(
			doctype,
			filters={"customer_product_spec": spec.name, "docstatus": ["<", 2], "spec_revision": ["<", 1]},
			fields=["name", "spec_snapshot"],
		)
		for card in cards:
			snapshot = _parse(card.spec_snapshot)
			if snapshot and not rules.payload_mismatches(payload, snapshot, spec.product_type):
				if not dry_run:
					frappe.db.set_value(doctype, card.name, "spec_revision", 1, update_modified=False)
			else:
				left.append("{0}:{1}".format(doctype, card.name))
	return left


def _parse(text):
	try:
		value = json.loads(text or "")
	except (TypeError, ValueError):
		return None
	return value if isinstance(value, dict) else None


@frappe.whitelist()
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
	if result.get("stamped"):
		print("CPS grandfather: stamped {0} specification(s); {1} legacy card(s) left unbound".format(
			len(result["stamped"]), len(result.get("cards_left_unbound") or [])
		))
