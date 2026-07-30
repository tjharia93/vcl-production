"""The finished size of a Computer Paper set, entered in inches.

Computer paper is specified, quoted, ordered and talked about in **inches** —
"9.5 x 8", "9.5 x 11", "14.5 x 11". Every LPO says inches; every ``job_size`` on
every existing specification says inches. The weight calculation, though, works
in millimetres, because :func:`cps_cp_weight.area_m2` is mm² → m². Until now the
Weight section asked for the millimetres, so the one number a person actually had
was the one number the form would not accept, and somebody multiplied by 25.4 in
their head on the way in.

So this patch turns the pair around:

``finished_width_in`` / ``finished_length_in`` (new, editable)
    The entry. Inches, to three decimals.

``finished_width_mm`` / ``finished_length_mm`` (existing, now **read-only**)
    Derived on every save from the inches above (``× 25.4``,
    :func:`cps_cp_weight.derived_dimensions`) and relabelled *Converted*. Still
    the only thing the weight is computed from, so nothing downstream moves.

Why the millimetre fields are kept rather than repurposed
---------------------------------------------------------

Repurposing them — relabelling the same two columns as inches — would have been
one property change and no new fields, and it would have been wrong: the
specifications submitted since April store **real millimetres** in them, and
reading 241 as inches would compute a carton 25.4 times too heavy. The columns
keep their meaning; the entry moves.

The backfill
------------

Every Computer Paper specification that carries a millimetre size gets the
matching inch entry, so the record can be *edited* in the unit it was ordered in
rather than showing an empty inch field above a converted value nobody can
change. The conversion is exact at three decimals in both directions
(241 mm → 9.488 in → 241.0 mm), so no stored millimetre and therefore no stored
weight changes — this is additive, not a correction.

Written with ``frappe.db.set_value(..., update_modified=False)`` deliberately, on
both drafts and submitted records:

* the inch fields are not ``allow_on_submit``, so an ORM save cannot touch the
  submitted ones, and this is a derived value rather than a revision — it is not
  something ``cps_revise`` should be asked to version; and
* ``modified`` must not move. ``Sales Order Item.custom_spec_snapshot`` records
  the spec's ``modified`` as ``_cps_modified`` to say which revision it froze, so
  bumping it here would make every live order's snapshot read as stale against a
  specification that did not actually change.

Idempotent: ``create_custom_fields`` inserts what is absent and reconciles the
properties of what is present, and the backfill skips any record that already has
an inch entry.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_cp_weight as w

_CP_ONLY = "eval:doc.product_type=='{0}'".format(w.COMPUTER_PAPER)

_CONVERTED = (
	"Converted from the inch entry above (× 25.4). This is the figure the weight is "
	"calculated from."
)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache(doctype="Customer Product Specification")
	backfill_inches()


def get_custom_fields():
	return {
		"Customer Product Specification": [
			{
				"fieldname": w.WIDTH_IN_FIELD,
				"label": "Finished Width (in)",
				"fieldtype": "Float",
				"precision": str(w.INCH_PRECISION),
				"non_negative": 1,
				"insert_after": "cp_weight_section",
				"depends_on": _CP_ONLY,
				"description": (
					"The finished width of one set, in inches — the unit computer paper is "
					"ordered in. The millimetre value beside it is converted from this "
					"(× 25.4) and is what the weight is calculated from."
				),
			},
			{
				"fieldname": w.LENGTH_IN_FIELD,
				"label": "Finished Length (in)",
				"fieldtype": "Float",
				"precision": str(w.INCH_PRECISION),
				"non_negative": 1,
				"insert_after": w.WIDTH_IN_FIELD,
				"depends_on": _CP_ONLY,
				"description": (
					"The finished length of one set, in inches. Converted to millimetres "
					"(× 25.4) beside it."
				),
			},
			# The two existing millimetre fields, reconciled rather than created:
			# moved below the inch entry, made read-only, relabelled as converted, and
			# widened to three decimals so a two-decimal inch entry is not rounded on
			# the way in (9.53 in = 242.062 mm).
			{
				"fieldname": w.WIDTH_FIELD,
				"label": "Converted Width (mm)",
				"fieldtype": "Float",
				"precision": str(w.MM_PRECISION),
				"non_negative": 1,
				"read_only": 1,
				"insert_after": w.LENGTH_IN_FIELD,
				"depends_on": _CP_ONLY,
				"description": _CONVERTED,
			},
			{
				"fieldname": w.LENGTH_FIELD,
				"label": "Converted Length (mm)",
				"fieldtype": "Float",
				"precision": str(w.MM_PRECISION),
				"non_negative": 1,
				"read_only": 1,
				"insert_after": w.WIDTH_FIELD,
				"depends_on": _CP_ONLY,
				"description": _CONVERTED,
			},
		],
	}


def backfill_inches():
	"""Give every millimetre size the inch entry it was ordered in."""
	specs = frappe.get_all(
		"Customer Product Specification",
		filters={"product_type": w.COMPUTER_PAPER},
		fields=[
			"name",
			w.WIDTH_FIELD,
			w.LENGTH_FIELD,
			w.WIDTH_IN_FIELD,
			w.LENGTH_IN_FIELD,
		],
	)

	stamped = 0
	for spec in specs:
		values = {}
		for mm_field, inch_field in (
			(w.WIDTH_FIELD, w.WIDTH_IN_FIELD),
			(w.LENGTH_FIELD, w.LENGTH_IN_FIELD),
		):
			# Already answered in inches — leave it. A hand-entered inch value is the
			# person's number and a converted one would be the same number anyway.
			if spec.get(inch_field):
				continue
			inches = w.inches_from_mm(spec.get(mm_field))
			if inches is not None:
				values[inch_field] = inches
		if values:
			frappe.db.set_value(
				"Customer Product Specification",
				spec.name,
				values,
				update_modified=False,
			)
			stamped += 1

	frappe.db.commit()
	print(
		"add_cp_inch_dimensions: stamped inches on {0} of {1} Computer Paper "
		"specifications".format(stamped, len(specs))
	)
