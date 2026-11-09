"""Correct the print type and side on existing Computer Paper job cards (D5, TRK-00350).

38 of 86 live cards (29/10/2026) were raised "Plain / N/A" from a specification
that says "Printed". D4 fixed new cards only. This module finds the existing
ones and plans the corrections.

``plan_corrections`` is pure (no frappe import at module level), so the dry run
can use the same rule over REST before the patch is ever applied.

Rules, per card with a linked specification:
  * type: card Plain (or blank) and spec Printed → set print_type, print_side
    and printed_weight from the spec. A zero spec weight keeps the card's own.
  * side: card Printed with side N/A (or blank) and the spec has a side → set
    print_side from the spec only.
  * anything else is left alone. That includes a card with no spec, a card
    whose spec is not Printed, and a card that already says Printed with a side
    (the one "Front and Back" against a "Front Only" spec is a case of this).
  * cancelled cards (docstatus 2) are reported and left alone.

Idempotent: after an apply, the plan is empty.
"""

PLAIN = "Plain"
PRINTED = "Printed"
UNSET = ("", "N/A", None)


def plan_corrections(cards, specs):
	"""Return ``(changes, skipped_cancelled)``.

	``cards``: iterable of mappings with name, docstatus, print_type, print_side,
	printed_weight, customer_product_spec.
	``specs``: mapping of spec name → mapping with print_type, print_side,
	printed_weight.
	"""
	changes, cancelled = [], []
	for c in cards:
		if (c.get("docstatus") or 0) == 2:
			cancelled.append(c.get("name"))
			continue
		spec_name = c.get("customer_product_spec")
		spec = specs.get(spec_name) if spec_name else None
		if not spec:
			continue
		card_type = c.get("print_type") or PLAIN
		card_side = c.get("print_side")
		spec_type = spec.get("print_type")
		spec_side = spec.get("print_side")

		if card_type == PLAIN and spec_type == PRINTED:
			changes.append({
				"name": c["name"],
				"kind": "type",
				"spec": spec_name,
				"from": {"print_type": card_type, "print_side": card_side, "printed_weight": c.get("printed_weight")},
				"to": {
					"print_type": PRINTED,
					"print_side": spec_side or "N/A",
					# A zero on the spec never wipes a weight the card already holds.
					"printed_weight": spec.get("printed_weight") or c.get("printed_weight") or 0,
				},
			})
		elif card_type == PRINTED and card_side in UNSET and spec_side not in UNSET:
			changes.append({
				"name": c["name"],
				"kind": "side",
				"spec": spec_name,
				"from": {"print_type": card_type, "print_side": card_side},
				"to": {"print_side": spec_side},
			})
	return changes, cancelled


def comment_text(change):
	"""The Comment left on a corrected card."""
	if change["kind"] == "type":
		was = change["from"]["print_type"] or PLAIN
		side = change["from"]["print_side"] or "N/A"
		return f"Print type corrected from {change['spec']} (was {was}/{side})"
	return f"Print side set from {change['spec']} (was {change['from']['print_side'] or 'N/A'})"


def describe(change):
	"""One line for the dry-run report."""
	f, t = change["from"], change["to"]
	before = f"{f.get('print_type') or ''}/{f.get('print_side') or ''}/{f.get('printed_weight', '')}".rstrip("/")
	after = "/".join(str(t[k]) for k in ("print_type", "print_side", "printed_weight") if k in t)
	return f"{change['name']:<20} {change['spec']:<14} {change['kind']:<5} {before:<22} -> {after}"


# --- Frappe side (imported by the patch only) -------------------------------

CARD = "Job Card Computer Paper"
SPEC = "Customer Product Specification"


def gather():
	"""Read the live cards and their specs. Read-only."""
	import frappe

	cards = frappe.get_all(
		CARD,
		fields=["name", "docstatus", "print_type", "print_side", "printed_weight", "customer_product_spec"],
		filters={"customer_product_spec": ["!=", ""]},
		limit_page_length=0,
	)
	names = sorted({c["customer_product_spec"] for c in cards})
	specs = {
		s["name"]: s
		for s in frappe.get_all(
			SPEC, fields=["name", "print_type", "print_side", "printed_weight"],
			filters={"name": ["in", names]} if names else {}, limit_page_length=0,
		)
	} if names else {}
	return cards, specs


def apply(changes):
	"""Write the planned corrections, and leave a Comment on each card. Idempotent."""
	import frappe

	for ch in changes:
		frappe.db.set_value(CARD, ch["name"], ch["to"], update_modified=False)
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": CARD,
			"reference_name": ch["name"],
			"content": comment_text(ch),
		}).insert(ignore_permissions=True)
	if changes:
		frappe.db.commit()
	return len(changes)
