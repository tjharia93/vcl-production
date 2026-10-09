"""Revise a SUBMITTED Customer Product Specification in place.

Never cancels, never amends. The spec keeps its name, job cards already raised
keep their own snapshot of the old values, and Frappe's Version log records the
diff field by field.

Why in place, and not amend
---------------------------

A Job Card copies the colours it needs off the specification at selection time
into its own child table. It is a snapshot, not a live fetch, so changing the
spec never rewrites an already-raised card - which makes amending pointless, and
expensive: ``check_no_back_links_exist`` refuses to cancel a document a submitted
one links to, so the spec will not cancel until its job card is cancelled first.
CPT-SPEC-00049 was amended once and its job card JC-CPT-2026-00045 is cancelled
to this day. That is the cost, and it is why this exists.

Why this is Python and no longer a Server Script
-------------------------------------------------

This began life as the Server Script ``cps_revise``, which could only revise the
Computer Paper ``colour_of_parts`` table. Extending it to Carton meant giving it
the board-plan geometry, and a Server Script runs under ``safe_exec`` where
imports are forbidden - so the formula would have had to be **inlined**, making a
fourth copy of arithmetic that had already drifted between its existing three
(see :mod:`cps_carton_board`). Moving here lets both product types import their
rules from the one module that owns them.

The Server Script is removed by the patch that installs this, in the same
migrate, so there is never a moment where two things answer to the same name.

What this must validate itself
-------------------------------

On an update-after-submit Frappe does **not** run ``validate()``, and neither
``Before Save`` server scripts nor the controller's own checks fire. Everything
this writes is therefore validated here, in this module, or it is unguarded.
That is the single most important thing to know before adding a field to it.
"""

import json

import frappe

from production_log.job_card_tracking import cps_carton_board as board
from production_log.job_card_tracking import cps_cp_rules
from production_log.job_card_tracking import cps_revise_rules as rules

COMPUTER_PAPER = "Computer Paper"
CARTON = "Carton"

# Why each reason is refused, in the operator's words.
_NOT_APPLICABLE = {
	board.SFK: "SFK is an un-glued web - there is no blank to plan.",
	board.DIE_CUT: "Die Cut blanks vary per job, so there is no formula to derive.",
	board.NO_STYLE: "This specification has no carton style, so the blank cannot be derived.",
	board.INCOMPLETE_DIMENSIONS: (
		"This specification is missing a length, width or height, so the blank "
		"cannot be derived. Correct the dimensions first."
	),
}


def _rows(payload):
	"""Parse a JSON payload from the dialog, tolerating an already-parsed value."""
	if not payload:
		return None
	return json.loads(payload) if isinstance(payload, str) else payload


@frappe.whitelist()
def revise(spec, reason, parts=None, carton=None, ink=None, packing=None, price=None):
	"""Apply a reasoned, versioned revision to a submitted specification.

	Returns ``{"ok": True, "spec": <name>, "changes": [<human summary>, ...]}``.

	A revision with a reason and no field changes is allowed and recorded as a
	note - saying in the record why nothing needed to change is worth having. A
	revision that *supplies* values which turn out to be identical is refused,
	because that is a no-op the operator believed was a change.
	"""
	reason = (reason or "").strip()
	if not spec:
		frappe.throw("spec is required.")
	if not reason:
		frappe.throw("A reason for the revision is required.")

	doc = frappe.get_doc("Customer Product Specification", spec)

	if doc.docstatus == 0:
		frappe.throw("This specification is still a Draft - edit it directly, no revision needed.")
	if doc.docstatus == 2:
		frappe.throw("This specification is cancelled and cannot be revised.")

	changes = []
	supplied = False

	parts_in = _rows(parts)
	if parts_in:
		supplied = True
		changes.extend(_apply_parts(doc, parts_in))

	carton_in = _rows(carton)
	if carton_in is not None:
		supplied = True
		changes.extend(_apply_carton(doc, carton_in))

	ink_in = _rows(ink)
	if ink_in is not None:
		supplied = True
		changes.extend(_apply_ink(doc, ink_in))

	packing_in = _rows(packing)
	if packing_in is not None:
		supplied = True
		changes.extend(_apply_packing(doc, packing_in))

	price_in = _rows(price)
	if price_in:
		supplied = True
		changes.extend(_apply_price(doc, price_in))

	if supplied and not changes:
		frappe.throw("Nothing changed - revision not recorded.")

	_stamp(doc, reason, changes)
	doc.save()

	return {"ok": True, "spec": doc.name, "changes": changes}


def _apply_parts(doc, rows):
	"""Change the Colour of Parts table of a Computer Paper specification."""
	if doc.product_type != COMPUTER_PAPER:
		frappe.throw("Colour of Parts applies to Computer Paper specifications only.")

	count = len(rows)
	if count != len(doc.colour_of_parts):
		frappe.throw(
			"Revise cannot add or remove parts - Number of Parts is fixed after "
			"submit. Create a new specification instead."
		)

	# validate() does NOT re-run on update-after-submit, so the paper type / GSM
	# rule is enforced here against the same positions the controller uses.
	expected = cps_cp_rules.part_positions(count)
	for index, row in enumerate(rows):
		paper_type = (row.get("paper_type") or "").strip()
		gsm = int(row.get("gsm") or 0)
		if not (row.get("colour") or "").strip():
			frappe.throw("Part {0} is missing a colour.".format(index + 1))

		if count == 1:
			allowed = list(cps_cp_rules.SINGLE_PART_OPTIONS)
		else:
			allowed = [expected[index]]

		if (paper_type, gsm) not in allowed:
			frappe.throw(
				"Part {0}: invalid paper type / GSM. Expected one of: {1}. Got: {2} ({3} GSM).".format(
					index + 1,
					", ".join("{0} ({1} GSM)".format(p, g) for p, g in allowed),
					paper_type,
					gsm,
				)
			)

	changes = []
	for index, row in enumerate(rows):
		target = doc.colour_of_parts[index]
		label = "Part {0}".format(target.part_number)
		for field, new in (
			("colour", (row.get("colour") or "").strip().upper()),
			("paper_type", (row.get("paper_type") or "").strip()),
			("gsm", int(row.get("gsm") or 0)),
		):
			old = target.get(field)
			if field == "colour":
				same = (old or "").strip().upper() == new
			elif field == "gsm":
				same = int(old or 0) == new
			else:
				same = (old or "") == new
			if not same:
				changes.append("{0} {1}: {2} -> {3}".format(label, field, old, new))
				target.set(field, new)
	return changes


def _apply_carton(doc, requested):
	"""Fill in the Board Plan of a Carton specification.

	Every derived figure is recomputed here from the specification's own
	dimensions rather than taken from ``requested``, so a caller cannot post a
	board plan that does not follow from the carton it describes. Only the flap
	and the two actual board sizes are the operator's to state.
	"""
	if doc.product_type != CARTON:
		frappe.throw("The Board Plan applies to Carton specifications only.")

	values, reason = board.revisable_changes(
		doc.as_dict(),
		requested,
		flap_override=requested.get("ctn_flap_mm"),
	)
	if reason:
		frappe.throw(_NOT_APPLICABLE.get(reason, "The board plan cannot be derived."))

	changes = []
	for field in sorted(values):
		old = doc.get(field)
		changes.append(
			"{0}: {1} -> {2}".format(
				doc.meta.get_label(field) or field, old or 0, values[field]
			)
		)
		doc.set(field, values[field])
	return changes


def _apply_ink(doc, requested):
	"""Change the print colours: process inks and the spot colour rows.

	``requested`` may carry any of ``uses_c/m/y/k`` and ``spot_colours`` (a list
	of ``{"pantone_code": ...}``); anything absent is left alone. The count is
	recomputed here because the controller's ``recalculate_number_of_colours``
	does not run on update-after-submit.
	"""
	if doc.product_type not in rules.INK_PRODUCT_TYPES:
		frappe.throw("{0} specifications do not carry print colours.".format(doc.product_type))

	changes = []
	for field in rules.PROCESS_INKS:
		if field not in requested:
			continue
		new = 1 if requested[field] else 0
		old = 1 if doc.get(field) else 0
		if new != old:
			changes.append("{0}: {1} -> {2}".format(
				doc.meta.get_label(field) or field, "on" if old else "off", "on" if new else "off"))
			doc.set(field, new)

	if "spot_colours" in requested:
		new_codes = [(r.get("pantone_code") or "").strip() for r in requested["spot_colours"] or []]
		if "" in new_codes:
			frappe.throw("Every spot colour row needs a Pantone colour.")
		old_codes = [r.pantone_code for r in doc.spot_colours]
		if sorted(new_codes) != sorted(old_codes):
			changes.append("Spot colours: {0} -> {1}".format(
				", ".join(old_codes) or "none", ", ".join(new_codes) or "none"))
			doc.set("spot_colours", [])
			for code in new_codes:
				doc.append("spot_colours", {"pantone_code": code})

	process = sum(1 for f in rules.PROCESS_INKS if doc.get(f))
	spots = len(doc.spot_colours)
	if changes:
		error = rules.ink_error(doc.print_type, process, spots)
		if error:
			frappe.throw(error)
	count = process + spots
	if doc.number_of_colours != count:
		doc.number_of_colours = count
		if changes:
			changes.append("Number of colours -> {0}".format(count))
	return changes


def _apply_packing(doc, requested):
	"""Change the packing fields that belong to this product type."""
	allowed = rules.packing_fields(doc.product_type)
	unknown = sorted(set(requested) - set(allowed))
	if unknown:
		frappe.throw("{0} cannot be revised on a {1} specification.".format(
			", ".join(unknown), doc.product_type))

	changes = []
	for field, kind in allowed.items():
		if field not in requested:
			continue
		new, error = rules.coerce_packing(field, kind, requested[field])
		if error:
			frappe.throw(error)
		old = doc.get(field)
		same = (str(old or "").strip() == str(new)) if kind == "text" else (float(old or 0) == float(new))
		if not same:
			changes.append("{0}: {1} -> {2}".format(doc.meta.get_label(field) or field, old or "empty", new))
			doc.set(field, new)
	return changes


def _apply_price(doc, row):
	"""Add a new price row. Never edits one, never approves one.

	A price change is a new row with a later Effective From, not an edit
	(design 6.2). The row lands as Draft: approval stays with a Sales Master
	Manager through ``approve_cps_price``, so revising a spec cannot be a way
	round it. Duplicate effective dates are refused by ``validate_pricing`` in
	``before_update_after_submit``.
	"""
	error = rules.price_row_error(row)
	if error:
		frappe.throw(error)
	doc.append("pricing", {
		"valid_from": row["valid_from"],
		"rate": float(row["rate"]),
		"uom": row["uom"],
		"vat_inclusive": 1 if row.get("vat_inclusive") else 0,
		"source": "Manual",
		"notes": (row.get("notes") or "").strip(),
		"approval_status": "Draft",
	})
	return ["New price {0} per {1}{2} from {3} (Draft - needs approval)".format(
		float(row["rate"]), row["uom"], ", VAT inclusive" if row.get("vat_inclusive") else "",
		row["valid_from"])]


def _stamp(doc, reason, changes):
	"""Append this revision to the human-readable Revision Notes trail."""
	summary = "; ".join(changes) if changes else "note only (no field changes)"
	entry = "[{0}] {1}\nReason: {2}\nChanged: {3}".format(
		frappe.utils.now()[:16], frappe.session.user, reason, summary
	)
	doc.revision_notes = ((doc.revision_notes or "") + "\n\n" + entry).strip()
