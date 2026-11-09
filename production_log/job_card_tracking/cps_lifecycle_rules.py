"""Pure rules for the Customer Product Specification lifecycle (Stream A §1-§3).

No Frappe import. Everything here takes plain dicts (or anything ``_get`` can
read) and returns plain values, so the revision, approval and edit-tier rules
are unit testable without a bench. The Frappe-bound half lives in
:mod:`production_log.job_card_tracking.cps_lifecycle`.

Three questions are answered here:

1. **Does this save bump the revision?** A revision is the approval-relevant
   fields at one moment (``stream_a_definitions.md`` §1). Notes-only changes do
   not bump it; dimensions, board, parts, print, packing, numbering, die and
   artwork do.
2. **What is the immutable record of a revision?** ``build_revision_payload``
   - the JSON that ``vcl_revision_payload`` stores and the review screen and
   the job-card gate compare against.
3. **Who may change which field, and when?** ``FIELD_TIERS`` +
   ``unauthorised_changes`` (§2): rep-editable (R), manager-only (M), derived
   and server-written (D).
"""

import json
from collections import namedtuple

from production_log.job_card_tracking import cps_rules

# --- States -------------------------------------------------------------------

APPROVAL_AWAITING = "Awaiting approval"
APPROVAL_APPROVED = "Approved"
APPROVAL_STATES = (APPROVAL_AWAITING, APPROVAL_APPROVED)

STATUS_ACTIVE = "Active"
STATUS_INACTIVE = "Inactive"
STATUS_DISCONTINUED = "Discontinued"
STATUS_SUPERSEDED = "Superseded"
LIFECYCLE_STATUSES = (STATUS_ACTIVE, STATUS_INACTIVE, STATUS_DISCONTINUED, STATUS_SUPERSEDED)

# Statuses a card may be released against (§7 check 3). Submitted first-use
# counts because the live estate is Active from the day it is submitted.
ORDERABLE_STATUSES = (STATUS_ACTIVE,)

# Roles that may change ``status`` on a submitted specification and edit the
# M-tier fields. System Manager is included so an administrator can repair a
# record; everything they do is still recorded by track_changes.
MANAGER_ROLES = frozenset({"Sales Master Manager", "VCL Management Team", "System Manager"})
REP_ROLES = frozenset({"Sales Manager", "Sales User"})

# --- Field tiers (§2) ---------------------------------------------------------

TIER_REP = "R"
TIER_MANAGER = "M"
TIER_DERIVED = "D"

# Fields the server alone writes. A caller that is not server code may not
# change any of these, whatever role it holds.
SERVER_OWNED_FIELDS = frozenset({
	"vcl_approval_state",
	"vcl_approved_rev",
	"vcl_approved_by",
	"vcl_approved_on",
	"vcl_approval_rule",
	"vcl_approval_notes",
	"vcl_revision",
	"vcl_revision_payload",
	"vcl_revision_log",
	"vcl_revision_at",
	"vcl_revision_by",
	"vcl_first_release_on",
	# Set only by the IQ transfer / create-from-IQ code: it supplies the
	# benchmarks automatic price approval reads (Codex r6 defect 2).
	"vcl_source_iq",
})

# Derived by the controller on every save from the rep's inputs (colour count,
# board plan, label geometry from the die, weights, current rate). They are
# D-tier in the §2 matrix, but the controller overwrites whatever a caller sent
# before the authorisation check runs, so comparing them here would refuse
# every legitimate save. Read-only on the form; the controller is the control.
CONTROLLER_DERIVED_FIELDS = frozenset({
	"current_rate",
	"current_uom",
	"number_of_colours",
	"label_length",
	"label_width",
	"cylinder_teeth",
	"plate_up",
	"plate_round",
	"board_width_planned_mm",
	"board_length_planned_mm",
	"approximate_weight_grams",
	"finished_width_mm",
	"finished_length_mm",
	"cp_total_gsm",
	"paper_weight_per_set_g",
	"net_product_weight_per_carton_kg",
	"gross_packed_weight_per_carton_kg",
	"linked_bom",
})

# Manager-only on a submitted specification. ``customer`` is M until the first
# order and never after it; that extra rule is applied in ``unauthorised_changes``.
MANAGER_FIELDS = frozenset({
	"customer",
	"linked_item",
	"status",
	"vcl_superseded_by",
})

# Identity fields that never change after submit - a different product type is
# a new specification, not an amendment.
IMMUTABLE_AFTER_SUBMIT = frozenset({"product_type", "naming_series"})

# CPS Price child-row fields the server alone writes.
PRICE_ROW_SERVER_FIELDS = frozenset({
	"approval_status",
	"approved_by",
	"approved_on",
	"approved_via",
	"approval_rule",
	"rule_benchmark",
})


def field_tier(fieldname):
	"""R, M or D for a specification field (§2)."""
	if fieldname in SERVER_OWNED_FIELDS or fieldname in CONTROLLER_DERIVED_FIELDS:
		return TIER_DERIVED
	if fieldname in MANAGER_FIELDS:
		return TIER_MANAGER
	return TIER_REP


FIELD_TIERS = {
	**{f: TIER_DERIVED for f in SERVER_OWNED_FIELDS | CONTROLLER_DERIVED_FIELDS},
	**{f: TIER_MANAGER for f in MANAGER_FIELDS},
}

# --- Revision identity (§1) ---------------------------------------------------

# Per product type: the fields whose change makes a new revision. These are the
# fields the approver actually approves; a name, a note or a price row is not.
_CARTON_REVISION_FIELDS = (
	cps_rules.CARTON_DIMENSION_FIELDS
	+ tuple(f for f in cps_rules.CARTON_STYLE_FIELDS if f != "printing_or_plain")
	+ cps_rules.CARTON_MATERIAL_LAYER_FIELDS
	+ ("ctn_flap_mm", "carton_cutting_die")
)
_COMPUTER_PAPER_REVISION_FIELDS = (
	"job_size",
	"pay_slip_size",
	"number_of_parts",
	"numbering_answer",
	"numbering_required",
	"finished_width_in",
	"finished_length_in",
)
_LABEL_REVISION_FIELDS = (
	cps_rules.LABEL_DIMENSION_FIELDS
	+ ("dies", "material_type", "plate_up", "plate_round", "cylinder_teeth")
)
_MONOBOX_REVISION_FIELDS = (
	"mbx_board_grade", "mbx_board_gsm", "mbx_print_side", "mbx_sheet_size",
	"mbx_length", "mbx_width", "mbx_height", "mbx_tuck_flap", "mbx_glue_flap",
	"mbx_dust_flap", "mbx_cutting_die", "has_window", "mbx_window_width",
	"mbx_window_height", "mbx_coating_type",
)
_ETR_REVISION_FIELDS = (
	"etr_substrate", "etr_gsm", "etr_core_id", "etr_jumbo_width", "etr_output_type",
	"etr_finished_width", "etr_finished_diameter", "etr_finished_reel_length",
	"etr_print_type",
)

# Shared across every type: print definition, packing and artwork.
SHARED_REVISION_FIELDS = (
	"print_type",
	"print_side",
	"ink_type",
	"uses_c",
	"uses_m",
	"uses_y",
	"uses_k",
	"number_of_colours",
	"standard_packing",
	"standard_weight_per_carton",
	"packing_pieces",
	"packing_up",
	"sets_per_carton",
	# packing_carton_tare_kg is deliberately NOT a revision field: the tare is a
	# CR21 packing fact kept out of anything sales roles can read (the payload
	# itself sits at permlevel 1, but the job-card snapshot compare must not
	# demand it either).
	"artwork_tracker",
	"artwork",
)

PRODUCT_TYPE_REVISION_FIELDS = {
	"Carton": _CARTON_REVISION_FIELDS,
	"Computer Paper": _COMPUTER_PAPER_REVISION_FIELDS,
	"Label": _LABEL_REVISION_FIELDS,
	"Monobox": _MONOBOX_REVISION_FIELDS,
	"ETR (Reel to Reel Printing)": _ETR_REVISION_FIELDS,
}

# Child tables that are part of the revision, with the row fields that count.
REVISION_TABLES = {
	"colour_of_parts": ("part_number", "paper_type", "gsm", "colour", "purpose"),
	"spot_colours": cps_rules.SNAPSHOT_SPOT_FIELDS,
}


def revision_fields(product_type=None):
	"""Scalar fields whose change bumps ``vcl_revision`` for this product type."""
	extra = PRODUCT_TYPE_REVISION_FIELDS.get(cps_rules.normalise_product_type(product_type) or "", ())
	seen = []
	for f in extra + SHARED_REVISION_FIELDS:
		if f not in seen:
			seen.append(f)
	return tuple(seen)


def _get(row, key):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def _norm(value):
	"""Compare values as the user sees them: '' == None, 5 == 5.0 == '5'."""
	if value in (None, ""):
		return None
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, (int, float)):
		return round(float(value), 6)
	text = str(value).strip()
	if text == "":
		return None
	try:
		return round(float(text), 6)
	except ValueError:
		return text


def _rows(doc, table, fields):
	out = []
	for row in _get(doc, table) or []:
		out.append({f: _norm(_get(row, f)) for f in fields})
	return out


def revision_changes(before, after, product_type=None):
	"""Fieldnames (and table names) whose value differs between two states.

	Only the revision-relevant set is compared, so a note or a price row never
	appears here. Child tables are compared as ordered lists of their counted
	fields: a reordered grid with identical rows is not a change.
	"""
	changed = []
	for fieldname in revision_fields(product_type):
		if _norm(_get(before, fieldname)) != _norm(_get(after, fieldname)):
			changed.append(fieldname)
	for table, fields in REVISION_TABLES.items():
		if _rows(before, table, fields) != _rows(after, table, fields):
			changed.append(table)
	return changed


def revision_bump_required(before, after, product_type=None):
	"""True when saving ``after`` over ``before`` creates a new revision."""
	if before is None:
		return False
	return bool(revision_changes(before, after, product_type))


def build_revision_payload(spec, revision, at, by, artwork_version=None):
	"""The immutable record of one revision (§1, §3).

	Keys are CPS fieldnames verbatim, as in ``build_spec_snapshot``, so the
	review screen can compare the approved payload, the current record and the
	card's snapshot with one loop. Values are stored as recorded, not
	normalised: the record must survive a Select option being renamed later.
	"""
	product_type = _get(spec, "product_type")
	payload = {
		"_revision": int(revision or 0),
		"_cps": _get(spec, "name"),
		"_product_type": product_type,
		"_at": str(at or ""),
		"_by": by,
		"_artwork_version": artwork_version,
	}
	for fieldname in revision_fields(product_type):
		payload[fieldname] = _get(spec, fieldname)
	for table, fields in REVISION_TABLES.items():
		payload[table] = [
			{f: _get(row, f) for f in fields} for row in (_get(spec, table) or [])
		]
	return payload


def payload_mismatches(payload, current, product_type=None):
	"""Fields where ``current`` disagrees with a stored revision payload.

	The approved-vs-current half of the §3 three-way compare. Returns a list
	of ``(fieldname, payload_value, current_value)``.
	"""
	if not isinstance(payload, dict):
		return []
	out = []
	for fieldname in revision_fields(product_type or payload.get("_product_type")):
		if fieldname not in payload:
			continue
		if _norm(payload.get(fieldname)) != _norm(_get(current, fieldname)):
			out.append((fieldname, payload.get(fieldname), _get(current, fieldname)))
	for table, fields in REVISION_TABLES.items():
		if table not in payload:
			continue
		stored = [{f: _norm(r.get(f)) for f in fields} for r in payload.get(table) or []]
		if stored != _rows(current, table, fields):
			out.append((table, payload.get(table), [dict(r) for r in _rows(current, table, fields)]))
	return out


def parse_payload(text):
	"""JSON text -> dict, or None. Never raises: a bad payload is reported, not thrown."""
	if isinstance(text, dict):
		return text
	if not text:
		return None
	try:
		value = json.loads(text)
	except (TypeError, ValueError):
		return None
	return value if isinstance(value, dict) else None


def parse_revision_log(text):
	"""JSON text -> list of payloads, oldest first. Tolerates a missing log."""
	if isinstance(text, list):
		return text
	if not text:
		return []
	try:
		value = json.loads(text)
	except (TypeError, ValueError):
		return []
	return value if isinstance(value, list) else []


def approve_revision_in_log(log, revision, user, now, rule=None):
	"""Stamp the approval onto the revision's log entry: the per-revision approval HISTORY.

	Approving revision 3 must not un-approve revision 2 (Codex r5 item 5), so
	the ``vcl_approved_rev`` scalar is only the latest, and the log carries one
	stamp per approved revision. Returns a new list.
	"""
	out = []
	found = False
	for entry in parse_revision_log(log):
		entry = dict(entry or {})
		if int(entry.get("_revision") or 0) == int(revision or 0):
			if entry.get("_revoked_on"):
				# A fresh approval after a rejection: the revocation moves to history.
				entry.setdefault("_revocations", []).append({
					"by": entry.pop("_revoked_by", None), "on": entry.pop("_revoked_on", None),
					"notes": entry.pop("_revocation_notes", None),
				})
			entry.update({"_approved_by": user, "_approved_on": str(now), "_approval_rule": rule})
			found = True
		out.append(entry)
	if not found:
		out.append({"_revision": int(revision or 0), "_approved_by": user, "_approved_on": str(now), "_approval_rule": rule})
	return out


def revoke_revision_in_log(log, revision, user, now, notes=None):
	"""A rejection after an approval: the revision's stamp is revoked (Codex r6 defect 3).

	History is kept - ``_approved_on`` stays as the record of what was once
	granted - but ``_revoked_on`` makes ``approved_revisions`` drop it.
	"""
	out = []
	for entry in parse_revision_log(log):
		entry = dict(entry or {})
		if int(entry.get("_revision") or 0) == int(revision or 0):
			entry.update({"_revoked_by": user, "_revoked_on": str(now), "_revocation_notes": notes or ""})
		out.append(entry)
	return out


def approved_revisions(log):
	"""Revision numbers carrying a live approval stamp (approved, not since revoked)."""
	return sorted({
		int(e.get("_revision") or 0)
		for e in parse_revision_log(log)
		if isinstance(e, dict) and e.get("_approved_on") and not e.get("_revoked_on")
	})


def payload_for_revision(log, revision):
	"""The stored payload for one revision number, from the log, or None."""
	for payload in reversed(parse_revision_log(log)):
		if isinstance(payload, dict) and int(payload.get("_revision") or 0) == int(revision or 0):
			return payload
	return None


# --- Approval state transitions (§1) -----------------------------------------

ApprovalStamp = namedtuple("ApprovalStamp", ("state", "approved_rev", "notes"))


def after_revision_bump(current_revision):
	"""The approval fields after a material change: back to Awaiting approval.

	``vcl_approved_rev`` is preserved - it still says which revision *was*
	approved, which is what lets a repeat card stay bound to it (§7 check 4).
	"""
	return {
		"vcl_revision": int(current_revision or 0) + 1,
		"vcl_approval_state": APPROVAL_AWAITING,
	}


def technical_approval_values(revision, user, now, rule=None, notes=None):
	"""What ``approve_technical`` writes on approve, stamped to the exact revision."""
	return {
		"vcl_approval_state": APPROVAL_APPROVED,
		"vcl_approved_rev": int(revision or 0),
		"vcl_approved_by": user,
		"vcl_approved_on": now,
		"vcl_approval_rule": rule,
		"vcl_approval_notes": notes or "",
	}


def technical_rejection_values(notes):
	"""Rejection is not a state: stay Awaiting approval with the notes recorded."""
	return {
		"vcl_approval_state": APPROVAL_AWAITING,
		"vcl_approval_notes": notes or "",
	}


def is_technically_approved(spec):
	"""§7 check 8 for the spec's *current* revision."""
	return (
		_get(spec, "vcl_approval_state") == APPROVAL_APPROVED
		and int(_get(spec, "vcl_approved_rev") or 0) >= 1
		and int(_get(spec, "vcl_approved_rev") or 0) == int(_get(spec, "vcl_revision") or 0)
	)


def revision_is_approved(spec, revision):
	"""Whether a *specific* revision carries technical approval.

	Codex r4 point 1 / r5 item 5: the card is evaluated against the revision
	bound to it. The revision log holds one approval stamp per approved
	revision (``approve_revision_in_log``), so approving revision 3 leaves a
	card bound to revision 2 approved. The ``vcl_approved_rev`` scalar is the
	latest approval and answers for sites whose log predates the history.
	"""
	if not revision:
		return False
	revision = int(revision)
	log = parse_revision_log(_get(spec, "vcl_revision_log"))
	if revision in approved_revisions(log):
		return True
	if any(int((e or {}).get("_revision") or 0) == revision and (e or {}).get("_revoked_on") for e in log):
		return False
	approved_rev = int(_get(spec, "vcl_approved_rev") or 0)
	if approved_rev != revision:
		return False
	if int(_get(spec, "vcl_revision") or 0) == approved_rev:
		return _get(spec, "vcl_approval_state") == APPROVAL_APPROVED
	return True


# --- Grandfathering (§1 patch, Codex r3 item 1) -------------------------------

def grandfather_values(status, authority, date_text):
	"""Values the migration writes on a submitted spec that predates the gate.

	Status preserved; revision and approved revision both 1 (both, or check 8
	fails on every grandfathered spec); authority and date recorded.
	"""
	return {
		"status": status,
		"vcl_revision": 1,
		"vcl_approved_rev": 1,
		"vcl_approval_state": APPROVAL_APPROVED,
		"vcl_approved_by": authority,
		"vcl_approval_notes": "Grandfathered by migration {0}".format(date_text),
	}


def needs_grandfathering(spec):
	"""A submitted spec with no revision yet is one the migration must stamp."""
	return int(_get(spec, "docstatus") or 0) == 1 and int(_get(spec, "vcl_revision") or 0) < 1


# --- Initial values on insert (Codex r5 item 1) ------------------------------


def forged_initial_values(doc):
	"""Server-owned values a NEW document arrived with. Nothing may be pre-stamped."""
	out = []
	for fieldname in sorted(SERVER_OWNED_FIELDS):
		if _norm(_get(doc, fieldname)) not in (None, 0):
			out.append(fieldname)
	for i, row in enumerate(_get(doc, "pricing") or []):
		if (_get(row, "approval_status") or cps_rules.APPROVAL_DRAFT) != cps_rules.APPROVAL_DRAFT:
			out.append("pricing[{0}].approval_status".format(i))
		for f in ("approved_by", "approved_on", "approved_via", "approval_rule", "rule_benchmark"):
			if _norm(_get(row, f)) is not None:
				out.append("pricing[{0}].{1}".format(i, f))
		if _get(row, "source") == IQ_SOURCE:
			out.append("pricing[{0}].source".format(i))
	return out


def initial_value_resets(doc):
	"""What to write on a new document a non-server caller pre-stamped: everything server-owned blank."""
	resets = {f: None for f in SERVER_OWNED_FIELDS}
	resets["vcl_revision"] = 0
	rows = []
	for row in _get(doc, "pricing") or []:
		rows.append({
			"approval_status": cps_rules.APPROVAL_DRAFT, "approved_by": None, "approved_on": None,
			"approved_via": None, "approval_rule": None, "rule_benchmark": None,
			"source": None if _get(row, "source") == IQ_SOURCE else _get(row, "source"),
			"source_ref": None if _get(row, "source") == IQ_SOURCE else _get(row, "source_ref"),
		})
	return resets, rows


# --- Shared authorisation check (§2) ------------------------------------------

# A price row whose source is the IQ transfer is written by server code only
# (Codex r5 item 2): its evidence drives automatic approval.
IQ_SOURCE = "Internal Quotation"


def _is_revocation(prev, row):
	"""Approved -> Draft with the stamps cleared: what revoke_approval_on_edit writes.

	Allowed from any caller, because it is the consequence of a rep editing the
	row's terms (Codex r5 item 9), not a grant of anything.
	"""
	if prev is None:
		return False
	return (
		_get(prev, "approval_status") == cps_rules.APPROVAL_APPROVED
		and _get(row, "approval_status") == cps_rules.APPROVAL_DRAFT
		and _norm(_get(row, "approved_by")) is None
		and _norm(_get(row, "approved_on")) is None
	)

Unauthorised = namedtuple("Unauthorised", ("fieldname", "tier", "reason"))


def _is_manager(roles):
	return bool(set(roles or ()) & MANAGER_ROLES)


def _price_rows_by_name(doc):
	return {(_get(r, "name") or "idx-{0}".format(i)): r for i, r in enumerate(_get(doc, "pricing") or [])}


def unauthorised_changes(before, after, roles, is_server=False, first_order_placed=False, submitted=True):
	"""Changed fields the caller is not allowed to change (§2).

	``before`` is the stored document (``get_doc_before_save``), ``after`` the
	one being written. ``roles`` are the caller's roles. ``is_server`` is True
	only when server code (approval, release, revise) is the writer, which is
	the only thing allowed to touch a D-tier field. ``first_order_placed`` makes
	``customer`` immutable even for a manager. ``submitted`` False relaxes the
	identity rule for a draft, where the rep may still correct the type.

	Child rows: the CPS Price approval fields are server-owned; everything else
	in the two revision tables is R. Returns a list of :class:`Unauthorised`.
	"""
	if before is None:
		return []
	roles = set(roles or ())
	manager = _is_manager(roles)
	out = []

	# Scalars: compare every field named in either document that has a tier.
	fieldnames = set()
	for doc in (before, after):
		if isinstance(doc, dict):
			fieldnames.update(doc.keys())
		else:
			fieldnames.update(k for k in getattr(doc, "__dict__", {}).keys())
	fieldnames = {f for f in fieldnames if not f.startswith("_")}

	for fieldname in sorted(fieldnames):
		if _norm(_get(before, fieldname)) == _norm(_get(after, fieldname)):
			continue
		if fieldname in SERVER_OWNED_FIELDS:
			if not is_server:
				out.append(Unauthorised(fieldname, TIER_DERIVED, "server-written"))
			continue
		if fieldname in IMMUTABLE_AFTER_SUBMIT and submitted:
			out.append(Unauthorised(fieldname, TIER_MANAGER, "identity - raise a new specification"))
			continue
		if fieldname == "customer":
			if submitted and first_order_placed:
				out.append(Unauthorised(fieldname, TIER_MANAGER, "customer is fixed once an order exists"))
			elif submitted and not manager and not is_server:
				out.append(Unauthorised(fieldname, TIER_MANAGER, "manager only after submit"))
			continue
		if fieldname in MANAGER_FIELDS and submitted and not manager and not is_server:
			out.append(Unauthorised(fieldname, TIER_MANAGER, "manager only"))

	# Price rows: a rep may add a Draft row; only the server approves one.
	if not is_server:
		before_rows = _price_rows_by_name(before)
		for key, row in _price_rows_by_name(after).items():
			prev = before_rows.get(key)
			revoked = _is_revocation(prev, row)
			for f in PRICE_ROW_SERVER_FIELDS:
				old = _norm(_get(prev, f)) if prev is not None else None
				new = _norm(_get(row, f))
				if prev is None and f == "approval_status" and new in (None, "draft", cps_rules.APPROVAL_DRAFT):
					continue
				if revoked and new is None:
					continue
				if revoked and f == "approval_status":
					continue
				if old != new:
					out.append(Unauthorised("pricing." + f, TIER_DERIVED, "server-written"))
			# The IQ transfer's identity is evidence for automatic approval.
			if _get(row, "source") == IQ_SOURCE and (prev is None or _get(prev, "source") != IQ_SOURCE):
				out.append(Unauthorised("pricing.source", TIER_DERIVED, "Internal Quotation rows are written by the transfer"))
			elif prev is not None and _get(prev, "source") == IQ_SOURCE and (
				_get(row, "source") != IQ_SOURCE or _norm(_get(row, "source_ref")) != _norm(_get(prev, "source_ref"))
			):
				out.append(Unauthorised("pricing.source_ref", TIER_DERIVED, "Internal Quotation rows are written by the transfer"))
	return out


def status_change_allowed(roles, is_server=False):
	"""Only a manager (or the system) moves a submitted spec between statuses."""
	return bool(is_server or _is_manager(roles))


def describe_unauthorised(items):
	"""One line per refused field, for the thrown message."""
	return "; ".join("{0} ({1}: {2})".format(i.fieldname, i.tier, i.reason) for i in items)
