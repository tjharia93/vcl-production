"""Document-event handlers for Workstation Type."""

import frappe
from frappe import _


def validate_stage_position(doc, method=None):
	"""Block save if `custom_stage_position` is already used by another WT.

	The planner sorts stage columns by this number (low → high), so two
	WTs sharing one number would render in arbitrary order. Hard-block
	keeps ordering deterministic and forces the admin to renumber.
	A blank / zero value is treated as "not yet positioned" and skipped.
	"""
	pos = doc.get("custom_stage_position")
	if not pos:
		return

	conflict = frappe.db.get_value(
		"Workstation Type",
		{
			"custom_stage_position": pos,
			"name": ("!=", doc.name),
		},
		"name",
	)
	if conflict:
		frappe.throw(
			_(
				"Stage Position {0} is already used by Workstation Type "
				"'{1}'. Pick a different number or update '{1}' first."
			).format(pos, conflict)
		)
