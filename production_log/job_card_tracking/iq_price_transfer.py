"""IQ -> CPS price transfer (§5), on the Internal Quotation workflow transition.

Trigger: the IQ ``status`` reaches Approved (``Issue`` by a Sales User with
``approval_status`` OK, or ``Approve`` by a Sales Master Manager) and a CPS
names it in ``vcl_source_iq`` - or "Create spec from this quote" runs later and
calls :func:`transfer` then. Precondition: confirmed ``vcl_uom``,
``vcl_currency`` and ``vcl_tax_basis`` on the IQ; nothing is inferred. An IQ
without them transfers nothing and says so in its own comments.

Idempotent on ``source`` = Internal Quotation + ``source_ref`` = IQ name.
Revocation: IQ Cancelled => the row is Rejected with a note, never deleted.
A later IQ amendment that reaches Approved adds a new row.

Wired as ``doc_events`` on ``Internal Quotation`` (a site-defined doctype, so
the hooks fire only where it exists) and callable from the CPS side.
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_lifecycle, cps_price_rules, cps_pricing, cps_rules

CPS = "Customer Product Specification"
IQ = "Internal Quotation"


def _status_changed_to(doc, status):
	before = doc.get_doc_before_save()
	return doc.get("status") == status and (before is None or before.get("status") != status)


def on_iq_update(doc, method=None):
	"""``on_update`` / ``on_update_after_submit`` on the IQ."""
	if _status_changed_to(doc, cps_price_rules.IQ_APPROVED_STATUS):
		for cps in specs_for_iq(doc.name):
			_safe_transfer(doc, cps)
	elif _status_changed_to(doc, "Cancelled"):
		revoke(doc)


def on_iq_cancel(doc, method=None):
	revoke(doc)


def specs_for_iq(iq_name):
	"""Specs linked to this IQ: ``vcl_source_iq``, or a submitted SO line whose quotation came from it."""
	if not frappe.get_meta(CPS).get_field("vcl_source_iq"):
		return []
	return frappe.get_all(CPS, filters={"vcl_source_iq": iq_name, "docstatus": ["<", 2]}, pluck="name")


def _safe_transfer(iq, cps):
	try:
		transfer(iq, cps)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "iq_price_transfer {0} -> {1}".format(iq.name, cps))


def approval_actor_and_time(iq):
	"""``IQ.approved_by`` else the user on the Issue/Approve transition, and when."""
	actor = iq.get("approved_by")
	when = None
	rows = frappe.get_all(
		"Version",
		filters={"ref_doctype": IQ, "docname": iq.name},
		fields=["owner", "creation", "data"],
		order_by="creation desc",
		limit_page_length=20,
	)
	for row in rows:
		if '"status"' in (row.data or "") and cps_price_rules.IQ_APPROVED_STATUS in (row.data or ""):
			when = row.creation
			actor = actor or row.owner
			break
	return actor or frappe.session.user, when or frappe.utils.now()


def transfer(iq, cps):
	"""Write the Approved row onto ``cps`` from an Approved IQ. Idempotent."""
	if isinstance(iq, str):
		iq = frappe.get_doc(IQ, iq)
	spec = frappe.get_doc(CPS, cps)

	if iq.get("status") != cps_price_rules.IQ_APPROVED_STATUS:
		return {"transferred": False, "reason": "IQ not Approved"}

	# Codex r5 item 2: the caller must be able to read the IQ, and the IQ must
	# be for this customer (or their lead), this kind of product, and linked.
	if not frappe.has_permission(IQ, "read", iq.name):
		frappe.throw(_("Not permitted to read {0}.").format(iq.name), frappe.PermissionError)
	customer_lead = frappe.db.get_value("Customer", spec.customer, "lead_name") if spec.customer else None
	relationship = cps_price_rules.iq_relationship_errors(iq, spec, customer_lead)
	if relationship:
		spec.add_comment("Comment", _("Price not transferred from {0}: {1}.").format(iq.name, "; ".join(relationship)))
		return {"transferred": False, "reason": "; ".join(relationship)}
	if not (spec.get("vcl_source_iq") or "").strip() and spec.meta.get_field("vcl_source_iq"):
		# First transfer binds the IQ to the spec; server-written.
		spec.vcl_source_iq = iq.name

	errors = cps_price_rules.iq_transfer_errors(iq)
	if errors:
		iq.add_comment("Comment", _("Price not transferred to {0}: {1}.").format(spec.name, "; ".join(errors)))
		return {"transferred": False, "reason": "; ".join(errors)}

	if cps_price_rules.find_transferred_row(spec.get("pricing") or [], iq.name):
		return {"transferred": False, "reason": "already transferred"}

	actor, when = approval_actor_and_time(iq)
	factor = cps_pricing.item_conversion_factor(spec.get("linked_item"), iq.get("vcl_uom"))
	values = cps_price_rules.price_row_from_iq(iq, factor, when, actor)

	meta = frappe.get_meta("CPS Price")
	values = {k: v for k, v in values.items() if meta.get_field(k)}
	# A row already live on the same effective date is superseded by this one
	# only if it is Draft; an Approved one with the same date is a duplicate
	# the rules refuse, so move this row to the next day and say so.
	duplicates = cps_rules.find_duplicate_valid_from((spec.get("pricing") or []) + [values])
	if duplicates:
		values["valid_from"] = frappe.utils.add_days(values["valid_from"], 1)
		values["approval_notes"] = (values.get("approval_notes") or "") + "; effective date moved one day to avoid a duplicate"

	spec.append("pricing", values)
	cps_pricing.set_current_rate(spec, spec.get("pricing") or [])
	with cps_lifecycle.server_write():
		spec.save()
	spec.add_comment("Comment", _("Price {0} per {1} transferred from Internal Quotation {2} (approved by {3}).").format(
		values.get("rate"), values.get("uom"), iq.name, actor
	))

	from production_log.job_card_tracking import cps_price_mirror, release
	cps_price_mirror.mirror_after_approval(spec.name)
	release.reevaluate_for_spec(spec.name)
	return {"transferred": True, "cps": spec.name, "rate": values.get("rate")}


def revoke(iq):
	"""IQ cancelled: every row it produced is Rejected with a note."""
	for cps in specs_for_iq(iq.name):
		spec = frappe.get_doc(CPS, cps)
		row = cps_price_rules.find_transferred_row(spec.get("pricing") or [], iq.name)
		if not row or row.approval_status == cps_rules.APPROVAL_REJECTED:
			continue
		for fieldname, value in cps_price_rules.iq_revocation_values(iq.name).items():
			row.set(fieldname, value)
		cps_pricing.set_current_rate(spec, spec.get("pricing") or [])
		with cps_lifecycle.server_write():
			spec.save()
		spec.add_comment("Comment", _("Price row from Internal Quotation {0} withdrawn: the IQ was cancelled.").format(iq.name))
		from production_log.job_card_tracking import release
		release.reevaluate_for_spec(spec.name)


@frappe.whitelist()
def transfer_from_iq(cps, iq):
	"""Deal-page / "Create spec from this quote" entry point."""
	if not frappe.has_permission(CPS, "write", cps):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return transfer(iq, cps)
