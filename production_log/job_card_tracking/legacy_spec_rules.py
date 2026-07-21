"""Pure verdict rules for the legacy ``vcl_spec`` / ``vcl_spec_rev`` audit.

Frappe-free, like :mod:`cps_rules` and :mod:`cps_report_rules`. The Frappe-bound
half — finding the fields, counting the rows — lives in
:mod:`legacy_spec_audit`.

Sales Order Item carried a "Product Spec" long before Customer Product
Specification existed. Two fields survive from it, ``vcl_spec`` and
``vcl_spec_rev``, and while they are still on the form a rep sees two things
that both look like the specification and has no way to tell which one the order
is actually held to (WBS-24).

**Nothing in either half of this audit deletes anything.** There is no
``execute()``, no ``drop=True`` and no ``frappe.delete_doc``. Retiring a field
that still has rows behind it destroys the only record of what a historical
order was for, and "the report said zero" is not the same as someone having
looked. So this produces a verdict and an ordered plan for a human to carry out,
and stops there.
"""

# The legacy fieldnames, in the order a reader meets them on the form.
LEGACY_FIELDNAMES = ("vcl_spec", "vcl_spec_rev")

# Fieldname -> what it was for, so the report explains itself to someone who
# never saw the app that created it.
LEGACY_FIELD_PURPOSE = {
	"vcl_spec": "Legacy Product Spec link, superseded by Sales Order Item.custom_cps.",
	"vcl_spec_rev": "Legacy Product Spec revision, superseded by the immutable specification snapshot.",
}

# Where a legacy field can live, and what it takes to retire each kind.
ORIGIN_CUSTOM_FIELD = "custom-field"
ORIGIN_STANDARD_FIELD = "standard-field"
ORIGIN_PROPERTY_SETTER = "property-setter"

RETIREMENT_BY_ORIGIN = {
	ORIGIN_CUSTOM_FIELD: "Delete the Custom Field, and remove it from any fixtures that recreate it on migrate.",
	ORIGIN_STANDARD_FIELD: "Owned by an installed app's DocType JSON. Remove it there and migrate, or uninstall the app; deleting the column by hand will be undone by the next migrate.",
	ORIGIN_PROPERTY_SETTER: "Delete the Property Setter. It only customises a field that is being retired anyway.",
}

# Verdicts, most severe first.
VERDICT_IN_USE = "in-use"
VERDICT_UNUSED = "unused"
VERDICT_UNKNOWN = "unknown"

REPORT_COLUMNS = (
	"doctype",
	"fieldname",
	"label",
	"fieldtype",
	"options",
	"origin",
	"purpose",
	"total_rows",
	"rows_with_value",
	"submitted_rows_with_value",
	"cancelled_rows_with_value",
	"draft_rows_with_value",
	"verdict",
	"is_blocking",
	"retirement_action",
)


def _get(row, key):
	"""Read a key from a dict or an attribute from a Frappe document."""
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def _count(value):
	"""A count, treating an uncountable value as unknown rather than as zero.

	The difference matters: a field whose host table could not be counted must
	not be reported as empty, because "empty" is the verdict that authorises
	deletion.
	"""
	if value is None:
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def field_verdict(rows_with_value):
	"""Whether one legacy field still holds data.

	``None`` — the count failed — is deliberately not folded into either answer.
	An unknown count blocks retirement exactly as a non-zero one does.
	"""
	count = _count(rows_with_value)
	if count is None:
		return VERDICT_UNKNOWN
	return VERDICT_UNUSED if count == 0 else VERDICT_IN_USE


def is_blocking(verdict):
	"""Whether this field stands between the site and a clean retirement."""
	return verdict != VERDICT_UNUSED


def build_field_row(
	doctype,
	fieldname,
	origin,
	label=None,
	fieldtype=None,
	options=None,
	total_rows=None,
	rows_with_value=None,
	submitted_rows_with_value=None,
	cancelled_rows_with_value=None,
	draft_rows_with_value=None,
):
	"""One flat, scalar-only row describing a legacy field and its usage."""
	verdict = field_verdict(rows_with_value)

	return {
		"doctype": doctype,
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"options": options,
		"origin": origin,
		"purpose": LEGACY_FIELD_PURPOSE.get(fieldname, "Legacy specification field."),
		"total_rows": _count(total_rows),
		"rows_with_value": _count(rows_with_value),
		"submitted_rows_with_value": _count(submitted_rows_with_value),
		"cancelled_rows_with_value": _count(cancelled_rows_with_value),
		"draft_rows_with_value": _count(draft_rows_with_value),
		"verdict": verdict,
		"is_blocking": is_blocking(verdict),
		"retirement_action": RETIREMENT_BY_ORIGIN.get(origin, "Review by hand."),
	}


def blocker_reason(row):
	"""One sentence explaining why a row blocks retirement, or None."""
	verdict = row.get("verdict")
	if verdict == VERDICT_UNUSED:
		return None

	if verdict == VERDICT_UNKNOWN:
		return "{0}.{1}: usage could not be counted, so it cannot be treated as empty.".format(
			row.get("doctype"), row.get("fieldname")
		)

	submitted = row.get("submitted_rows_with_value")
	if submitted:
		return "{0}.{1}: {2} row(s) still carry a value, {3} of them on submitted documents.".format(
			row.get("doctype"), row.get("fieldname"), row.get("rows_with_value"), submitted
		)

	return "{0}.{1}: {2} row(s) still carry a value.".format(
		row.get("doctype"), row.get("fieldname"), row.get("rows_with_value")
	)


def summarise_audit(rows):
	"""Counts and the single ``safe_to_retire`` verdict.

	``safe_to_retire`` describes the *data* only. It says every legacy field is
	empty, which is the precondition for retiring them — not that anyone has
	agreed to, nor that the fixtures and reports referring to them have been
	found. Those are steps in :func:`retirement_plan`, and they are somebody's
	job rather than this function's.
	"""
	rows = list(rows or [])
	blockers = [reason for reason in (blocker_reason(row) for row in rows) if reason]

	return {
		"fields_found": len(rows),
		"fields_in_use": sum(1 for row in rows if row.get("verdict") == VERDICT_IN_USE),
		"fields_unused": sum(1 for row in rows if row.get("verdict") == VERDICT_UNUSED),
		"fields_unknown": sum(1 for row in rows if row.get("verdict") == VERDICT_UNKNOWN),
		"rows_with_value": sum(row.get("rows_with_value") or 0 for row in rows),
		"submitted_rows_with_value": sum(
			row.get("submitted_rows_with_value") or 0 for row in rows
		),
		"doctypes_affected": len({row.get("doctype") for row in rows if row.get("doctype")}),
		"safe_to_retire": bool(rows) and not blockers,
		"nothing_to_retire": not rows,
		"blockers": blockers,
	}


def retirement_plan(rows, summary):
	"""The ordered steps a human would take, as plain sentences.

	Returned rather than performed. Every step is reversible up to the last one,
	which is why the last one is the deletion and why it is gated on a backup
	taken in the step before it.
	"""
	rows = list(rows or [])
	summary = summary or summarise_audit(rows)

	if summary.get("nothing_to_retire"):
		return [
			"Nothing to do: neither {0} appears on this site.".format(
				" nor ".join(LEGACY_FIELDNAMES)
			)
		]

	if not summary.get("safe_to_retire"):
		steps = [
			"Do not retire anything yet. Clear the blockers below first, keeping the data:",
		]
		steps += ["  - {0}".format(blocker) for blocker in summary.get("blockers") or []]
		steps.append(
			"For each blocking row, record the legacy value against the order it belongs to "
			"(or export it) before the field is removed. The value is the only record of what "
			"that order was specified as."
		)
		steps.append("Re-run this audit. It must report safe_to_retire before anything is deleted.")
		return steps

	steps = [
		"Every legacy field is empty. Retirement is a data-safe change, in this order:",
		"1. Take a site backup, database and files.",
		"2. Hide the fields first (set hidden on each) and leave them one full week. "
		"A field nobody misses while hidden is a field nobody needs.",
	]

	for index, row in enumerate(sorted(rows, key=lambda r: (r.get("doctype") or "", r.get("fieldname") or "")), start=3):
		steps.append(
			"{0}. {1}.{2} — {3}".format(
				index, row.get("doctype"), row.get("fieldname"), row.get("retirement_action")
			)
		)

	steps.append(
		"{0}. Re-run this audit and confirm it reports nothing_to_retire, then run a "
		"regression pass over existing Sales Orders: open one, amend one, and print one.".format(
			len(rows) + 3
		)
	)
	return steps
