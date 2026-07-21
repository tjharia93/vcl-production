"""Read-only Desk endpoints for CPS-controlled order entry (WBS-25, 26, 28).

Two whitelisted functions, neither of which writes anything:

* :func:`cps_line_preview` — what a specification would price and produce on one
  Sales Order line, so a rep can see it before saving.
* :func:`item_linked_specs` — the specifications declared against one Item, so
  the Item form can navigate to them.

**The preview is advice, not a decision.** Everything it returns about the
commercial and technical shape of a line lands in ``read_only`` Sales Order Item
fields that ``so_spec_control`` owns: ``_clear_snapshot`` wipes them on every
draft save and ``_stamp_snapshot`` rewrites them server-side on submit, taking
its values from the specification rather than from anything the client sent
(V12). So a stale, forged or tampered preview cannot survive a save, and this
module needs no defences of its own beyond reading the right records.

The reasons it reports come from the same ``cps_rules`` functions that
``so_spec_control`` throws on, in the same order, so the preview and the submit
cannot disagree about which line is acceptable.
"""

import frappe
from frappe import _

from production_log.job_card_tracking import (
	cps_desk_rules,
	cps_pricing,
	cps_rules,
	so_spec_control,
)

CPS = "Customer Product Specification"

# Bound on the Item → specification list. An Item sold to every customer in the
# book could otherwise return hundreds of rows into a dialog; the cap is
# reported in ``notes`` when it bites, because a silently truncated list reads
# as a complete one.
LINKED_SPEC_LIMIT = 200


# ---------------------------------------------------------------------------
# Sales Order line preview (WBS-26)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def cps_line_preview(cps, item_code=None, customer=None, transaction_date=None):
	"""Preview one specification against one order line. Reads only.

	``transaction_date`` is the order date, never today: a backdated order prices
	at the rate that was agreed on the order date (design §5.2), and the preview
	has to show the rep the same rate the submit will insist on.

	Returns the payload shaped by :func:`cps_desk_rules.build_line_preview`, with
	``message`` translated. Missing or unreadable specifications come back as a
	blocked preview rather than as an exception — the client is asking a question
	about a value the user is still typing, and an error dialog per keystroke is
	not an answer.
	"""
	if not cps:
		return cps_desk_rules.blank_line_preview()

	transaction_date = transaction_date or frappe.utils.today()

	spec = _read_spec(cps)
	price = (
		cps_pricing.get_eligible_price(spec.name, transaction_date) if spec else None
	)

	preview = cps_desk_rules.build_line_preview(
		spec,
		item_code,
		customer,
		price=price,
		expected_product_type=so_spec_control.expected_product_type_for_item(item_code),
		requested_name=cps,
		on_date_label=frappe.utils.formatdate(transaction_date),
		colour_of_parts=(spec.get("colour_of_parts") if spec else None),
	)

	preview["cps"] = cps
	preview["transaction_date"] = transaction_date
	preview["message"] = _translate_block(preview["block"])
	preview["control_enabled"] = so_spec_control.control_enabled()
	return preview


def _read_spec(cps):
	"""The specification, or None when it is missing or not readable.

	Permission is checked against the document itself rather than against the
	DocType: a specification carries one customer's agreed shape and price, so
	"may read specifications in general" is the wrong question.
	"""
	if not frappe.db.exists(CPS, cps):
		return None

	if not frappe.has_permission(CPS, "read", doc=cps):
		frappe.throw(
			_("Not permitted to read specification {0}.").format(cps),
			frappe.PermissionError,
		)

	return frappe.get_doc(CPS, cps)


def _translate_block(block):
	"""Render a block payload as a translated sentence, or None.

	``cps_rules`` keeps its reasons as an untranslated template plus arguments so
	it can stay Frappe-free; translation is this layer's job.
	"""
	if not block:
		return None
	return _(block["template"]).format(*block["args"])


# ---------------------------------------------------------------------------
# Item -> linked specifications (WBS-28)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def item_linked_specs(item_code, include_inactive=1):
	"""Specifications declared against one Item. Reads only.

	Drafts, cancelled records and inactive ones are included by default: the
	question this answers is "what exists for this Item", and hiding the
	cancelled amendment is how someone concludes the specification was never
	written.
	"""
	if not item_code:
		return {"item_code": None, "rows": [], "summary": cps_desk_rules.summarise_linked_specs([]), "notes": []}

	frappe.has_permission("Item", "read", doc=item_code, throw=True)
	frappe.has_permission(CPS, "read", throw=True)

	notes = []
	if not _has_field(CPS, cps_rules.ITEM_LINK_FIELD):
		notes.append(
			_("{0}.{1} does not exist on this site, so no specification can be linked to an Item yet.").format(
				CPS, cps_rules.ITEM_LINK_FIELD
			)
		)
		return {
			"item_code": item_code,
			"rows": [],
			"summary": cps_desk_rules.summarise_linked_specs([]),
			"notes": notes,
		}

	specs = frappe.get_all(
		CPS,
		filters={cps_rules.ITEM_LINK_FIELD: item_code},
		fields=[
			"name",
			"customer",
			"specification_name",
			"product_type",
			"status",
			"docstatus",
			"amended_from",
			"current_rate",
			"current_uom",
		],
		order_by="modified desc",
		limit_page_length=LINKED_SPEC_LIMIT,
	)
	if len(specs) >= LINKED_SPEC_LIMIT:
		notes.append(
			_("Showing the {0} most recently modified specifications only; older ones were not listed.").format(
				LINKED_SPEC_LIMIT
			)
		)

	rows = cps_desk_rules.sort_linked_spec_rows(
		[cps_desk_rules.build_linked_spec_row(spec) for spec in specs]
	)
	if not bool(int(include_inactive or 0)):
		rows = [row for row in rows if row["is_orderable"]]

	return {
		"item_code": item_code,
		"columns": list(cps_desk_rules.LINKED_SPEC_COLUMNS),
		"rows": rows,
		"summary": cps_desk_rules.summarise_linked_specs(rows),
		"notes": notes,
	}


@frappe.whitelist()
def item_control_explanation(item_code):
	"""Why one Item is (or is not) specification-controlled. Reads only.

	``Item.custom_requires_cps`` is read-only and derived (design §4.2), so
	without this the only way to find out why it holds the value it does is to
	read the source.
	"""
	frappe.has_permission("Item", "read", doc=item_code, throw=True)

	# Only the columns that have actually landed: the iteration-two patch may not
	# have run, and asking for a column that does not exist is a database error
	# rather than a blank.
	fields = ["item_group", "custom_requires_cps"]
	for fieldname in (cps_rules.CONTROL_MODE_FIELD, cps_rules.PRODUCT_TYPE_FIELD):
		if _has_field("Item", fieldname):
			fields.append(fieldname)

	item = frappe.db.get_value("Item", item_code, fields, as_dict=True)
	if not item:
		frappe.throw(_("Item {0} was not found.").format(item_code))

	controlling = so_spec_control.item_group_requires_cps(item.get("item_group"))
	mode = cps_rules.normalise_control_mode(item.get(cps_rules.CONTROL_MODE_FIELD))
	source = cps_rules.item_control_source(mode, controlling)

	return {
		"item_code": item_code,
		"control_mode": mode,
		"controlling_item_group": controlling.get("name") if controlling else None,
		# Resolved, not read off the group: an Item may name its own kind, and
		# reporting the group's here would explain a rejection the rep is not
		# getting and hide the one they are.
		"expected_product_type": cps_rules.expected_product_type(
			mode, item.get(cps_rules.PRODUCT_TYPE_FIELD), controlling
		),
		"requires_cps": cps_rules.item_requires_cps(mode, controlling),
		"stored_flag": bool(item.get("custom_requires_cps")),
		"source_code": source.code,
		"explanation": _(source.template).format(*source.args),
		"control_enabled": so_spec_control.control_enabled(),
	}


def _has_field(doctype, fieldname):
	"""Whether a field has landed on this site (custom or otherwise)."""
	try:
		return bool(frappe.get_meta(doctype).get_field(fieldname))
	except Exception:
		return False
