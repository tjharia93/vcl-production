"""Pure rules for ``CPS Artwork Version`` (Stream A §1/§7, Codex r3 §6; Tanuj 08/11/2026).

Artwork is kept as immutable versions. The rep uploads a version; a manager
marks it Customer-approved or Not applicable (with a reason). A new file never
replaces an approved one in place: it is a new version, Pending, and the
previous version is superseded. Release check 6 reads the version BOUND to the
card; it falls back to ``artwork_tracker`` only when the spec has no versions
at all, and says so.

No Frappe import. The Frappe-bound half is :mod:`cps_artwork`.
"""

from collections import namedtuple

STATE_PENDING = "Pending"
STATE_CUSTOMER_APPROVED = "Customer-approved"
STATE_NOT_APPLICABLE = "Not applicable"
STATES = (STATE_PENDING, STATE_CUSTOMER_APPROVED, STATE_NOT_APPLICABLE)
OK_STATES = (STATE_CUSTOMER_APPROVED, STATE_NOT_APPLICABLE)

DECISION_CONTINUE = "Continue"
DECISION_HOLD = "Hold"
DECISION_REWORK = "Rework"
DECISIONS = (DECISION_CONTINUE, DECISION_HOLD, DECISION_REWORK)

# Who may mark a version approved / N/A, or record a change-request decision.
MANAGER_ROLES = frozenset({"Sales Master Manager", "VCL Management Team", "System Manager"})
PRODUCTION_MANAGER_ROLES = frozenset({"Production Manager", "VCL Management Team", "System Manager"})

# Fields frozen from insert: the version IS the file.
IMMUTABLE_FIELDS = ("spec", "version", "file", "uploaded_by", "uploaded_on", "spec_revision")
# Fields only the server writes.
SERVER_FIELDS = ("approval_state", "approved_by", "approved_on", "superseded", "superseded_by", "change_request")


def _get(row, key):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def next_version(existing_versions):
	"""1 + the highest version number already on the spec."""
	highest = 0
	for v in existing_versions or []:
		try:
			highest = max(highest, int(_get(v, "version") or 0))
		except (TypeError, ValueError):
			continue
	return highest + 1


def insert_values(spec, spec_revision, file_url, user, now, existing_versions):
	"""What a new version carries: Pending, next number, bound to the spec's current revision."""
	if not file_url:
		raise ValueError("a file is required")
	return {
		"spec": spec,
		"version": next_version(existing_versions),
		"file": file_url,
		"uploaded_by": user,
		"uploaded_on": now,
		"spec_revision": int(spec_revision or 0),
		"approval_state": STATE_PENDING,
		"superseded": 0,
	}


def immutable_changes(before, after):
	"""Fields changed after insert that may never change."""
	if before is None:
		return []
	return [f for f in IMMUTABLE_FIELDS if (_get(before, f) or "") != (_get(after, f) or "")]


def server_field_changes(before, after):
	if before is None:
		return []
	return [f for f in SERVER_FIELDS if (_get(before, f) or "") != (_get(after, f) or "")]


def mark_refusal(version, state, roles, reason=None):
	"""Why a version cannot be marked ``state`` by a caller with ``roles``, or None."""
	if state not in OK_STATES:
		return "state must be {0} or {1}".format(*OK_STATES)
	if not set(roles or ()) & MANAGER_ROLES:
		return "a manager marks artwork approved or not applicable"
	if int(_get(version, "superseded") or 0):
		return "this version is superseded; mark the current one"
	if _get(version, "approval_state") == state:
		return "already {0}".format(state)
	if state == STATE_NOT_APPLICABLE and not (reason or "").strip():
		return "a reason is required for Not applicable"
	return None


def mark_values(state, user, now, reason=None):
	values = {"approval_state": state, "approved_by": user, "approved_on": now}
	if state == STATE_NOT_APPLICABLE:
		values["na_reason"] = (reason or "").strip()
	return values


def supersede_values(new_version_name):
	"""The previous current version, once a new one is uploaded. Approval is kept as history."""
	return {"superseded": 1, "superseded_by": new_version_name}


def current_version(versions):
	"""The one live (not superseded) version, highest number wins."""
	live = [v for v in versions or [] if not int(_get(v, "superseded") or 0)]
	if not live:
		return None
	return max(live, key=lambda v: int(_get(v, "version") or 0))


ArtworkState = namedtuple("ArtworkState", ("state", "version", "versions_exist", "superseded", "note"))


def artwork_for_card(versions, bound_version_name=None):
	"""What release check 6 reads for a card.

	The version BOUND to the card decides. A bound version that has since been
	superseded is reported as such, so the card re-holds or shows "superseded".
	With no binding the current version is used. With no versions at all the
	caller falls back to the artwork tracker and the note says so.
	"""
	versions = list(versions or [])
	if not versions:
		return ArtworkState(None, None, False, False, "no artwork versions on the specification; artwork tracker used")
	bound = None
	if bound_version_name:
		bound = next((v for v in versions if _get(v, "name") == bound_version_name), None)
	if bound is not None:
		superseded = bool(int(_get(bound, "superseded") or 0))
		note = "bound artwork version {0} superseded by {1}".format(
			_get(bound, "version"), _get(bound, "superseded_by")) if superseded else ""
		return ArtworkState(_get(bound, "approval_state"), _get(bound, "name"), True, superseded, note)
	current = current_version(versions)
	if current is None:
		return ArtworkState(None, None, True, True, "every artwork version is superseded")
	return ArtworkState(_get(current, "approval_state"), _get(current, "name"), True, False, "")


# --- Change request (open cards on the superseded version) --------------------


def build_change_request(open_cards, superseded_version_name):
	"""One entry per open card still bound to the superseded version."""
	return [
		{
			"doctype": _get(c, "doctype"),
			"card": _get(c, "name"),
			"job_status": _get(c, "job_status"),
			"render_issued_on": str(_get(c, "render_issued_on") or ""),
			"bound_version": superseded_version_name,
			"decision": None,
			"decided_by": None,
			"decided_on": None,
			"notes": None,
		}
		for c in open_cards or []
	]


def decision_refusal(decision, roles, entry):
	if decision not in DECISIONS:
		return "decision must be one of {0}".format(", ".join(DECISIONS))
	if not set(roles or ()) & PRODUCTION_MANAGER_ROLES:
		return "the Production Manager records continue / hold / rework"
	if entry is None:
		return "card is not on this change request"
	return None


def record_decision(change_request, card, decision, user, now, notes=None):
	"""Return a new list with the card's entry decided. Raises ValueError if absent."""
	out = []
	found = False
	for entry in change_request or []:
		entry = dict(entry)
		if entry.get("card") == card:
			found = True
			entry.update({"decision": decision, "decided_by": user, "decided_on": str(now), "notes": (notes or "").strip() or None})
		out.append(entry)
	if not found:
		raise ValueError("card {0} is not on this change request".format(card))
	return out


def undecided(change_request):
	return [e for e in change_request or [] if not e.get("decision")]
