"""Frappe-bound half of CPS Artwork Version: mark, supersede, change request, release feed.

A new version supersedes the current one and raises a change request listing
every open job card still bound to the superseded version; the Production
Manager records continue / hold / rework per card. Unissued cards re-hold and
issued ones are flagged by the release gate's own re-evaluation, because the
bound version is now superseded (artwork_rules.artwork_for_card).
"""

import contextlib
import json

import frappe
from frappe import _

from production_log.job_card_tracking import artwork_rules as rules

ARTWORK_VERSION = "CPS Artwork Version"


@contextlib.contextmanager
def server_write():
	previous = frappe.flags.cps_artwork_server_write
	frappe.flags.cps_artwork_server_write = True
	try:
		yield
	finally:
		frappe.flags.cps_artwork_server_write = previous


def versions_for(spec_name):
	if not frappe.db.exists("DocType", ARTWORK_VERSION):
		return []
	return frappe.get_all(
		ARTWORK_VERSION,
		filters={"spec": spec_name},
		fields=["name", "version", "approval_state", "superseded", "superseded_by", "spec_revision"],
		order_by="version asc",
	)


def artwork_for_card(spec_name, bound_version_name=None):
	"""What release check 6 reads: the bound version's state, or the fallback note."""
	return rules.artwork_for_card(versions_for(spec_name), bound_version_name)


def open_cards_on_version(version_name, spec_name):
	"""Live job cards whose release binding names this artwork version."""
	from production_log.job_card_tracking import release

	out = []
	for doctype in release.card_doctypes():
		if not frappe.db.exists("DocType", doctype) or not frappe.get_meta(doctype).get_field("release_artwork_version"):
			continue
		filters = {
			"customer_product_spec": spec_name, "release_artwork_version": version_name, "docstatus": ["<", 2],
			"job_status": ["not in", ["Closed", "Cancelled", "Completed"]],
		}
		for row in frappe.get_all(doctype, filters=filters, fields=["name", "job_status", "render_issued_on"]):
			out.append(dict(row, doctype=doctype))
	return out


def supersede_previous(new_version, previous):
	"""Mark the previous current version superseded and open the change request on the new one."""
	if previous is None:
		return
	previous_name = previous.get("name") if isinstance(previous, dict) else previous.name
	frappe.db.set_value(ARTWORK_VERSION, previous_name, rules.supersede_values(new_version.name), update_modified=False)
	cards = open_cards_on_version(previous_name, new_version.spec)
	change_request = rules.build_change_request(cards, previous_name)
	frappe.db.set_value(ARTWORK_VERSION, new_version.name, "change_request", json.dumps(change_request, default=str), update_modified=False)
	new_version.add_comment(
		"Comment",
		_("Supersedes version {0}. {1} open job card(s) bound to it need a continue / hold / rework decision.").format(
			previous.get("version") if isinstance(previous, dict) else previous.version, len(cards)
		),
	)


def reevaluate(spec_name):
	from production_log.job_card_tracking import release

	try:
		release.reevaluate_for_spec(spec_name, trigger="artwork")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "cps_artwork.reevaluate {0}".format(spec_name))


@frappe.whitelist(methods=["POST"])
def mark(version, state, reason=None, evidence=None):
	"""Manager marks a version Customer-approved or Not applicable (with a reason)."""
	doc = frappe.get_doc(ARTWORK_VERSION, version)
	if not frappe.has_permission(ARTWORK_VERSION, "write", doc):
		frappe.throw(_("Not permitted to mark {0}.").format(version), frappe.PermissionError)
	refusal = rules.mark_refusal(doc, state, frappe.get_roles(), reason)
	if refusal:
		frappe.throw(_("Cannot mark artwork: {0}.").format(refusal), frappe.PermissionError if "manager" in refusal else frappe.ValidationError)
	values = rules.mark_values(state, frappe.session.user, frappe.utils.now(), reason)
	if evidence:
		values["customer_approval_evidence"] = evidence
	for fieldname, value in values.items():
		doc.set(fieldname, value)
	with server_write():
		doc.save()
	doc.add_comment("Comment", _("Marked {0} by {1}{2}").format(state, frappe.session.user, ": " + reason if reason else ""))
	reevaluate(doc.spec)
	return {"version": doc.name, "approval_state": doc.approval_state}


@frappe.whitelist(methods=["POST"])
def record_decision(version, card, decision, notes=None):
	"""Production Manager records continue / hold / rework for an open card on the change request."""
	doc = frappe.get_doc(ARTWORK_VERSION, version)
	# The Production Manager holds READ on artwork versions (the record is the
	# rep's and the manager's); the decision is authorised by the dedicated role
	# (decision_refusal) plus write permission on the card it changes, and the
	# write to change_request below is a narrowly scoped server db.set_value.
	if not frappe.has_permission(ARTWORK_VERSION, "read", doc):
		frappe.throw(_("Not permitted to read {0}.").format(version), frappe.PermissionError)
	change_request = json.loads(doc.change_request or "[]")
	entry = next((e for e in change_request if e.get("card") == card), None)
	refusal = rules.decision_refusal(decision, frappe.get_roles(), entry)
	if refusal:
		frappe.throw(_("Cannot record decision: {0}.").format(refusal), frappe.PermissionError)
	# Codex r6 defect 5: document permission on the target card, not role alone.
	if entry.get("doctype") and not frappe.has_permission(entry["doctype"], "write", card):
		frappe.throw(_("Not permitted to change job card {0}.").format(card), frappe.PermissionError)
	updated = rules.record_decision(change_request, card, decision, frappe.session.user, frappe.utils.now(), notes)
	frappe.db.set_value(ARTWORK_VERSION, version, "change_request", json.dumps(updated, default=str), update_modified=False)
	doc.add_comment("Comment", _("{0}: {1} by {2}{3}").format(card, decision, frappe.session.user, " - " + notes if notes else ""))

	if decision == rules.DECISION_HOLD and entry.get("doctype"):
		# A Hold decision is a manual PPC hold on the card - independent of the gate.
		frappe.db.set_value(entry["doctype"], card, {
			"job_status": "On Hold", "hold_reason": "Other",
			"hold_remarks": _("Artwork superseded by {0}: hold decided by {1}").format(version, frappe.session.user),
			"hold_by": frappe.session.user, "hold_on": frappe.utils.now(),
		}, update_modified=False)
	return {"version": version, "undecided": len(rules.undecided(updated))}


@frappe.whitelist()
def change_request(version):
	doc = frappe.get_doc(ARTWORK_VERSION, version)
	if not frappe.has_permission(ARTWORK_VERSION, "read", doc):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	entries = json.loads(doc.change_request or "[]")
	return {"version": version, "entries": entries, "undecided": len(rules.undecided(entries))}
