"""First-order approval request: whole CPS + proposed price, one authorised POST.

Email links only open a review page; scanners/GET requests cannot approve.
Normal CPS permissions and both existing approval rules remain authoritative.
Nothing here releases or prints a Job Card, or fills management packing.
"""

import hashlib
import html
import json
from urllib.parse import urlencode

import frappe
from frappe import _

from production_log.job_card_tracking import cps_approval, cps_approval_rules, cps_first_order_price
from production_log.job_card_tracking import cps_lifecycle_rules, cps_pricing, cps_rules

CPS = "Customer Product Specification"
METHOD = "production_log.job_card_tracking.cps_first_order_approval"
PACKING_ROLES = {"VCL Management Team", "System Manager"}


def _pending_line(order, cps, required=True):
	for line in order.get("items") or []:
		if line.get("custom_cps") != cps:
			continue
		try:
			marker = json.loads(line.get("custom_spec_snapshot") or "{}").get("_first_order_exception") or {}
		except (TypeError, ValueError):
			continue
		if marker.get("sales_order") == order.name and marker.get("price_row") == line.get("custom_cps_price_row"):
			return line
	if required:
		frappe.throw(_("This CPS is not bound to a first-use approval on this order."))
	return None


def _load(order_name, cps, lock=False):
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to review this approval."), frappe.PermissionError)
	if lock:
		# Same direction as Release: SO -> line -> CPS -> prices.
		frappe.db.sql("SELECT name FROM `tabSales Order` WHERE name=%s FOR UPDATE", (order_name,))
		frappe.db.sql("SELECT name FROM `tabSales Order Item` WHERE parent=%s ORDER BY name FOR UPDATE", (order_name,))
		versions = cps_first_order_price.lock_specs(frappe.db, [cps])
		frappe.db.sql("SELECT name FROM `tabCPS Price` WHERE parent=%s ORDER BY name FOR UPDATE", (cps,))
	order = frappe.get_doc("Sales Order", order_name)
	order.check_permission("read")
	if order.docstatus != 1:
		frappe.throw(_("The Sales Order must still be submitted."))
	line = _pending_line(order, cps)
	spec = frappe.get_doc(CPS, cps)
	spec.check_permission("read")
	spec.check_permission("write")
	if lock and (not versions.get(cps) or frappe.utils.get_datetime(versions[cps]["modified"]) != frappe.utils.get_datetime(spec.modified)):
		frappe.throw(_("The CPS changed. Reload the approval page."))
	if (spec.customer != order.customer or not cps_rules.spec_serves_item(spec, line.item_code)
	    or spec.docstatus not in (0, 1) or spec.status != "Active"
	    or spec.get(cps_first_order_price.CLAIM_FIELD) != order.name):
		frappe.throw(_("The CPS no longer matches this first submitted order."))
	row = next((r for r in spec.get("pricing") or [] if r.name == line.get("custom_cps_price_row")), None)
	if not row or row.approval_status not in (cps_rules.APPROVAL_DRAFT, cps_rules.APPROVAL_APPROVED):
		frappe.throw(_("The proposed price is missing or rejected. Review the CPS first."))
	return order, line, spec, row


def _authority(spec, row):
	if spec.docstatus == 0:
		spec.check_permission("submit")
	technical = cps_approval.resolve_technical(spec)
	if (spec.docstatus == 0 and not technical.allow_self_approval
	    and (technical.management_role or cps_approval_rules.DEFAULT_MANAGEMENT_ROLE) not in frappe.get_roles()):
		frappe.throw(_("Management must complete combined approval of this Draft CPS under its current self-approval rule."), frappe.PermissionError)
	cps_approval._refuse_without_authority(technical, spec.get("vcl_revision_by") or spec.owner)
	cps_approval.authorise_price_decision(spec, row)


def _version(order, line, spec):
	return hashlib.sha256(json.dumps({
		"order": order.name, "status": order.docstatus,
		"line": line.as_dict(), "spec": spec.as_dict(),
	}, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _packing_allowed():
	return bool(PACKING_ROLES.intersection(frappe.get_roles()))


def _fields(doc, packing=False):
	"""Normal visible fields; level-one packing only for management."""
	out = []
	ignored = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Image", "Password"}
	for field in doc.meta.fields:
		level = int(field.permlevel or 0)
		if field.hidden or field.fieldtype in ignored or level > 1 or (level == 1 and not packing):
			continue
		value = doc.get(field.fieldname)
		if field.fieldtype in ("Table", "Table MultiSelect"):
			children = []
			for child in value or []:
				children.append(_fields(child, packing))
			value = children
		elif value is None or value == "":
			continue
		out.append({"label": field.label or field.fieldname, "type": field.fieldtype, "value": value})
	return out


@frappe.whitelist(methods=["GET"])
def review(sales_order, cps):
	order, line, spec, row = _load(sales_order, cps)
	_authority(spec, row)
	frozen = json.loads(line.get("custom_spec_snapshot") or "{}")
	current = cps_rules.build_spec_snapshot(spec, spec.get("colour_of_parts"), spec.get("spot_colours"), line.get("custom_spec_snapshot_at"))
	changes = [{"field": key, "ordered": frozen.get(key), "current": value}
	           for key, value in current.items() if not key.startswith("_") and frozen.get(key) != value]
	return {
		"sales_order": order.name, "cps": spec.name, "name": spec.specification_name,
		"customer": spec.customer, "version": _version(order, line, spec),
		"cps_status": "Draft" if spec.docstatus == 0 else "Submitted",
		"technical_status": spec.get("vcl_approval_state"),
		"price": {"name": row.name, "rate": row.rate, "uom": row.uom,
		          "currency": row.get("currency") or "KES", "status": row.approval_status,
		          "valid_from": row.valid_from},
		"order_rate": line.rate, "order_uom": line.uom, "order_currency": order.currency,
		"fields": _fields(spec, _packing_allowed()),
		"changes": changes,
		"packing_allowed": _packing_allowed() and spec.product_type == "Computer Paper",
		"sets_per_carton": spec.get("sets_per_carton") if _packing_allowed() else None,
		"carton_tare": spec.get("packing_carton_tare_kg") if _packing_allowed() else None,
	}


@frappe.whitelist(methods=["POST"])
def approve(sales_order, cps, version, sets_per_carton=None, carton_tare=None):
	order, line, spec, row = _load(sales_order, cps, lock=True)
	_authority(spec, row)  # Both rules checked BEFORE either approval is changed.
	if version != _version(order, line, spec):
		frappe.throw(_("The order, CPS or price changed. Reload and review before approving."))
	if sets_per_carton not in (None, "") or carton_tare not in (None, ""):
		if not _packing_allowed() or spec.product_type != "Computer Paper":
			frappe.throw(_("Only management may enter packing."), frappe.PermissionError)
		import math
		if sets_per_carton not in (None, ""):
			sets = float(sets_per_carton)
			if not math.isfinite(sets) or sets <= 0 or not sets.is_integer():
				frappe.throw(_("Sets per carton must be a positive whole number."))
			spec.sets_per_carton = int(sets)
		if carton_tare not in (None, ""):
			tare = float(carton_tare)
			if not math.isfinite(tare) or tare < 0:
				frappe.throw(_("Empty carton weight must be non-negative."))
			spec.packing_carton_tare_kg = tare
		spec.save()
	if spec.docstatus == 0:
		spec.submit()  # Normal submit/technical validation; not ignore_permissions.
	if not cps_lifecycle_rules.is_technically_approved(spec):
		cps_approval.approve_technical(spec.name, "approve", notes="First-order review: " + order.name)
	if row.approval_status != cps_rules.APPROVAL_APPROVED:
		cps_pricing.approve_cps_price(spec.name, row.name, notes="First-order review: " + order.name)
	return {"cps": spec.name, "sales_order": order.name, "approved": True}


def _recipients(spec, row):
	technical = cps_approval.resolve_technical(spec)
	pricing = cps_approval.resolve_price(spec, row)
	roles = set(filter(None, (technical.approver_role, technical.management_role,
	                         pricing.approver_role, pricing.management_role)))
	candidates = set(filter(None, (technical.approver_user, pricing.approver_user)))
	if roles:
		candidates.update(frappe.get_all("Has Role", filters={"role": ["in", sorted(roles)], "parenttype": "User"}, pluck="parent"))
	out = []
	for user in sorted(candidates - {"Guest", "Administrator"}):
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		user_roles = frappe.get_roles(user)
		if (spec.docstatus == 0 and not technical.allow_self_approval
		    and (technical.management_role or cps_approval_rules.DEFAULT_MANAGEMENT_ROLE) not in user_roles):
			continue
		if not all((
			cps_approval_rules.may_decide(technical, user, user_roles, spec.get("vcl_revision_by") or spec.owner),
			cps_approval_rules.may_decide(pricing, user, user_roles, row.owner),
			frappe.has_permission(CPS, "read", doc=spec, user=user),
			frappe.has_permission(CPS, "write", doc=spec, user=user),
			frappe.has_permission("Sales Order", "read", doc=spec.get(cps_first_order_price.CLAIM_FIELD), user=user),
		)):
			continue
		if spec.docstatus == 0 and not frappe.has_permission(CPS, "submit", doc=spec, user=user):
			continue
		email = frappe.db.get_value("User", user, "email")
		if email:
			out.append(email)
	return sorted(set(out))


def request_for_order(order):
	"""Queue one request per CPS at successful SO submit, in that transaction.

	No immediate SMTP call: rollback also removes the queued mail. Missing mail
	configuration must not silently undo a valid first order; it is reported.
	"""
	if order.docstatus != 1:
		return
	seen = set()
	for line in order.get("items") or []:
		cps = line.get("custom_cps")
		if not cps or cps in seen:
			continue
		seen.add(cps)
		pending = _pending_line(order, cps, required=False)
		if pending is None:
			continue
		spec = frappe.get_doc(CPS, cps)
		row = next((r for r in spec.get("pricing") or [] if r.name == pending.get("custom_cps_price_row")), None)
		if not row:
			continue
		subject = "Approve CPS {0} and price / {1}".format(cps, order.name)
		if frappe.db.exists("Email Queue", {"reference_doctype": "Sales Order", "reference_name": order.name, "subject": subject}):
			continue
		try:
			recipients = _recipients(spec, row)
			if not recipients:
				raise ValueError("No enabled recipient has both CPS and price approval authority")
			url = frappe.utils.get_url("/sales-crm-v2/approve-cps?" + urlencode({"sales_order": order.name, "cps": cps}))
			escape = html.escape
			frappe.sendmail(
				recipients=recipients, subject=subject, now=False,
				message=("<p>First order <b>{0}</b> uses <b>{1}</b> for {2}.</p>"
				         "<p>Proposed CPS price: {3} {4} per {5}, net/ex-VAT. Approval is pending.</p>"
				         "<p>Review the whole CPS and approve its specification and price together. "
				         "Management enters packing from the first production run; it is not filled automatically.</p>"
				         '<p><a href="{6}">Review and approve CPS + price</a></p>'
				         "<p>Sign-in is required. Opening this link does not approve or release production.</p>").format(
					escape(order.name), escape(spec.specification_name), escape(spec.customer),
					escape(row.get("currency") or "KES"), escape(str(row.rate)), escape(row.uom), escape(url, quote=True)),
				reference_doctype="Sales Order", reference_name=order.name,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "First-order CPS approval request: " + cps)
			frappe.msgprint(_("Order saved, but approval email for {0} could not be queued. Management must review its CPS and price.").format(cps), indicator="orange")
