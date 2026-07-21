"""Read-only audit of the legacy ``vcl_spec`` / ``vcl_spec_rev`` fields (WBS-24).

Sales Order Item carried a "Product Spec" before Customer Product Specification
existed. While those fields are still on the form a rep sees two things that
both look like the specification, and nothing tells them which one the order is
actually held to. Retiring them is the fix — but only once it is known that no
document still depends on them.

**This module never writes.** There is no delete path, no ``dry_run=False`` and
no ``frappe.delete_doc`` anywhere in it. Removing a field that still has rows
behind it destroys the only surviving record of what a historical order was
specified as, and that loss is not recoverable from the order itself. So the
audit reports what exists, what still holds data, and the ordered steps someone
would take — and stops.

The fields are not declared anywhere in this app, so they are *discovered* at
run time rather than assumed: they may be Custom Fields, they may be standard
DocFields belonging to an app that is still installed, and they may be on
DocTypes nobody remembers. Whatever is found is reported; nothing found is
reported as nothing found, which is itself the answer WBS-21 is waiting for.
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_report_rules, legacy_spec_rules

# Reading this crosses every DocType that ever held a legacy specification and
# counts rows on each, so it is gated the same way the migration report is.
READ_ROLES = ("System Manager", "Sales Master Manager")


def _require_read_access():
	if not set(frappe.get_roles()) & set(READ_ROLES):
		frappe.throw(
			_("{0} role required to read the legacy specification audit.").format(
				_(" or ").join(READ_ROLES)
			),
			frappe.PermissionError,
		)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _custom_field_sites(fieldnames):
	"""Legacy fields that exist as Custom Fields, with their host DocType."""
	return frappe.get_all(
		"Custom Field",
		filters={"fieldname": ["in", list(fieldnames)]},
		fields=["dt as doctype", "fieldname", "label", "fieldtype", "options"],
		order_by="dt asc, fieldname asc",
	)


def _standard_field_sites(fieldnames):
	"""Legacy fields baked into an installed app's DocType JSON.

	These cannot be deleted from the Desk — the next migrate would put them
	back — so the distinction from a Custom Field changes what retirement even
	means, and the report has to make it.
	"""
	return frappe.get_all(
		"DocField",
		filters={"fieldname": ["in", list(fieldnames)]},
		fields=["parent as doctype", "fieldname", "label", "fieldtype", "options"],
		order_by="parent asc, fieldname asc",
	)


def _property_setter_sites(fieldnames):
	"""Property Setters customising a legacy field, which retire with it."""
	return frappe.get_all(
		"Property Setter",
		filters={"field_name": ["in", list(fieldnames)]},
		fields=["doc_type as doctype", "field_name as fieldname", "property", "value"],
		order_by="doc_type asc, field_name asc",
	)


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


def _usage_counts(doctype, fieldname, notes):
	"""How many rows still carry a value, split by docstatus.

	Counted with ``["is", "set"]`` rather than ``!= ""``: an unset Link is NULL,
	and SQL comparisons against NULL are never true, so the naive form would
	report every legacy field as empty and authorise deleting all of them.
	"""
	counts = {
		"total_rows": None,
		"rows_with_value": None,
		"submitted_rows_with_value": None,
		"cancelled_rows_with_value": None,
		"draft_rows_with_value": None,
	}

	try:
		meta = frappe.get_meta(doctype)
	except Exception as exc:
		notes.append(
			_("{0} could not be loaded ({1}); its usage is reported as unknown.").format(
				doctype, exc
			)
		)
		return counts

	if not meta.get_field(fieldname):
		# Declared somewhere but not on the live meta — a stale Custom Field row
		# for a DocType that has since dropped it. Nothing to count.
		notes.append(
			_("{0}.{1} is declared but is not on the live schema; reporting zero usage.").format(
				doctype, fieldname
			)
		)
		return dict(counts, total_rows=0, rows_with_value=0)

	try:
		counts["total_rows"] = frappe.db.count(doctype)
		counts["rows_with_value"] = frappe.db.count(doctype, {fieldname: ["is", "set"]})

		# A child table has no docstatus of its own worth reading; its parent
		# carries the state, so splitting here would be a lie dressed as detail.
		if not meta.istable and meta.is_submittable:
			for label, docstatus in (
				("draft_rows_with_value", 0),
				("submitted_rows_with_value", 1),
				("cancelled_rows_with_value", 2),
			):
				counts[label] = frappe.db.count(
					doctype, {fieldname: ["is", "set"], "docstatus": docstatus}
				)
	except Exception as exc:
		notes.append(
			_("Could not count usage of {0}.{1} ({2}); it is reported as unknown and blocks retirement.").format(
				doctype, fieldname, exc
			)
		)

	return counts


def _parent_docstatus_counts(doctype, fieldname, notes):
	"""For a child table, how many rows hang off submitted parents.

	A legacy value on a draft line is a typo somebody can delete. The same value
	on a submitted line is part of a document that has been sent to a customer,
	and that is the number that decides whether retirement is safe.
	"""
	try:
		meta = frappe.get_meta(doctype)
		if not (meta.istable and meta.get_field(fieldname)):
			return {}

		rows = frappe.get_all(
			doctype,
			filters={fieldname: ["is", "set"]},
			fields=["parent", "parenttype"],
			limit_page_length=0,
		)
		if not rows:
			return {"submitted_rows_with_value": 0}

		by_parenttype = {}
		for row in rows:
			by_parenttype.setdefault(row.get("parenttype"), set()).add(row.get("parent"))

		submitted = 0
		for parenttype, parents in by_parenttype.items():
			if not parenttype or not frappe.db.exists("DocType", parenttype):
				continue
			submitted += frappe.db.count(
				parenttype, {"name": ["in", list(parents)], "docstatus": 1}
			)

		return {
			"submitted_rows_with_value": submitted,
			"parent_doctypes": sorted(p for p in by_parenttype if p),
		}
	except Exception as exc:
		notes.append(
			_("Could not resolve parent docstatus for {0}.{1} ({2}).").format(
				doctype, fieldname, exc
			)
		)
		return {}


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------


@frappe.whitelist()
def legacy_spec_audit(fieldnames=None):
	"""Where the legacy specification fields live and whether anything uses them.

	Returns ``fields``, ``property_setters``, ``summary``, ``retirement_plan``
	and ``notes``. Every value in every row is a scalar, so the same payload
	feeds CSV, a Desk dialog and a bench console unchanged.

	Deletes nothing. ``summary["safe_to_retire"]`` is a statement about the data,
	not an instruction, and ``retirement_plan`` is a list of sentences for a
	person to act on.
	"""
	_require_read_access()

	fieldnames = _resolve_fieldnames(fieldnames)
	notes = []

	sites = []
	seen = set()

	for site in _custom_field_sites(fieldnames):
		key = (site["doctype"], site["fieldname"])
		seen.add(key)
		sites.append((site, legacy_spec_rules.ORIGIN_CUSTOM_FIELD))

	for site in _standard_field_sites(fieldnames):
		key = (site["doctype"], site["fieldname"])
		if key in seen:
			# Both a DocField and a Custom Field of the same name is a broken
			# schema, not a second place to look; the Custom Field row already
			# covers it.
			continue
		seen.add(key)
		sites.append((site, legacy_spec_rules.ORIGIN_STANDARD_FIELD))

	rows = []
	for site, origin in sites:
		doctype, fieldname = site["doctype"], site["fieldname"]
		counts = _usage_counts(doctype, fieldname, notes)
		counts.update(
			{
				key: value
				for key, value in _parent_docstatus_counts(doctype, fieldname, notes).items()
				if key in counts
			}
		)
		rows.append(
			legacy_spec_rules.build_field_row(
				doctype,
				fieldname,
				origin,
				label=site.get("label"),
				fieldtype=site.get("fieldtype"),
				options=site.get("options"),
				**counts
			)
		)

	property_setters = _property_setter_sites(fieldnames)
	summary = legacy_spec_rules.summarise_audit(rows)

	if not rows:
		notes.append(
			_("Neither {0} was found on this site. Nothing is left to retire.").format(
				_(" nor ").join(fieldnames)
			)
		)
	if property_setters:
		notes.append(
			_("{0} Property Setter(s) customise a legacy field and retire with it.").format(
				len(property_setters)
			)
		)

	return {
		"generated_at": frappe.utils.now(),
		"generated_by": frappe.session.user,
		"fieldnames": list(fieldnames),
		"columns": list(legacy_spec_rules.REPORT_COLUMNS),
		"fields": rows,
		"property_setters": property_setters,
		"summary": summary,
		"retirement_plan": legacy_spec_rules.retirement_plan(rows, summary),
		"notes": notes,
	}


@frappe.whitelist()
def legacy_spec_audit_csv(fieldnames=None):
	"""The same audit as a CSV string, for pasting into the migration register.

	Returned as a string rather than written to a File, because writing a File is
	a mutation and this audit does not make any.
	"""
	report = legacy_spec_audit(fieldnames)
	return {
		"generated_at": report["generated_at"],
		"summary": report["summary"],
		"fields_csv": cps_report_rules.to_csv(
			report["fields"], legacy_spec_rules.REPORT_COLUMNS
		),
		"retirement_plan": report["retirement_plan"],
		"notes": report["notes"],
	}


def _resolve_fieldnames(fieldnames):
	"""Accept the default pair, a JSON list, or a comma-separated string."""
	if not fieldnames:
		return list(legacy_spec_rules.LEGACY_FIELDNAMES)

	if isinstance(fieldnames, str):
		fieldnames = frappe.parse_json(fieldnames) if fieldnames.strip().startswith("[") else fieldnames.split(",")

	cleaned = [str(name).strip() for name in fieldnames if str(name).strip()]
	return cleaned or list(legacy_spec_rules.LEGACY_FIELDNAMES)
