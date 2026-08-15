"""Let a Carton specification's Board Plan be completed after submit.

The Board Plan landed on Customer Product Specification on 2026-07-23. Twenty-six
carton specifications had already been submitted by then, and every one of them
carries zeroes for all six board fields - not because anything is wrong with
them, but because the fields did not exist when they were signed off.

They could not be filled in afterwards. The fields are not ``allow_on_submit``,
and the board-plan client script only persists while ``docstatus == 0``, so a
submitted specification recomputes its plan for display on every form load and
stores none of it. The one route that should have worked - the "Revise Customer
Spec" button - only ever understood the Computer Paper ``colour_of_parts`` table,
so on a carton it fell through to its note-only branch and recorded, truthfully,
"note only (no field changes)". That is exactly what CTN-SPEC-00005 (EAST WEST
AFRICA LTD, CR 600) says against an attempt made on 2026-08-15.

This patch opens the route. It does **not** fill anything in: the values are a
production decision (the auto flap is a formula, not a measurement) and they are
made one specification at a time, with a reason, through the button.

Three things change together
----------------------------

1. The eight board and weight fields become ``allow_on_submit`` so the server can
   write them at all. Mirrored in ``fixtures/custom_field.json``, which is what a
   deploy actually applies - this is the belt to that braces, and repairs a site
   whose fixture sync predates the change.

2. The Server Script ``cps_revise`` is removed. It is superseded by
   ``production_log.job_card_tracking.cps_revise.revise``, which can import the
   board geometry instead of inlining a fourth copy of it - ``safe_exec`` forbids
   imports, which is the whole reason the logic had to leave the Server Script.
   Removed in the same migrate that ships the replacement so no window exists
   where two things answer to one name.

3. Nothing is backfilled, and ``modified`` is not touched on any specification.
   ``Sales Order Item.custom_spec_snapshot`` records the spec's ``modified`` as
   ``_cps_modified`` to say which revision it froze, so moving it here would make
   every live order's snapshot read as stale against a spec that did not change -
   the same reason v8_4 wrote its backfill with ``update_modified=False``.

Idempotent, and safe to run on a site where the fields are already open or the
Server Script is already gone.
"""

import frappe

# The two the operator states, the three the geometry derives, and the two
# weights that are weighed rather than calculated. All eight have to be writable
# for a revision to leave a carton specification reading like one created today.
BOARD_PLAN_FIELDS = (
	"ctn_flap_mm",
	"board_width_planned_mm",
	"board_length_planned_mm",
	"board_width_actual_mm",
	"board_length_actual_mm",
	"approximate_weight_grams",
	"printed_weight",
	"empty_carton_weight",
)

SUPERSEDED_SERVER_SCRIPT = "CPS Revise (in-place, versioned)"


def execute():
	allow_board_plan_on_submit()
	remove_superseded_server_script()
	frappe.clear_cache(doctype="Customer Product Specification")


def allow_board_plan_on_submit():
	"""Open the Board Plan and weight fields for update-after-submit."""
	for fieldname in BOARD_PLAN_FIELDS:
		name = "Customer Product Specification-{0}".format(fieldname)
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "allow_on_submit", 1)


def remove_superseded_server_script():
	"""Drop the Server Script the whitelisted method replaces.

	Deleted rather than disabled: a disabled Server Script is still a second
	definition of ``cps_revise`` for the next person to find and re-enable.
	"""
	if frappe.db.exists("Server Script", SUPERSEDED_SERVER_SCRIPT):
		frappe.delete_doc(
			"Server Script", SUPERSEDED_SERVER_SCRIPT, force=True, ignore_permissions=True
		)
