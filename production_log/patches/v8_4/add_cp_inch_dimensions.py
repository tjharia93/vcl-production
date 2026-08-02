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

Editable after submission
-------------------------

The whole Weight section becomes ``allow_on_submit``. It has to: the weights
landed in April, so every specification submitted before then carries zeros, and
`CPT-SPEC-00025` (SUBARU KENYA) is a live example — 4 parts, 400 to a carton, and
a hand-typed ``standard_weight_per_carton`` of 6 kg with nothing behind it. The
house rule is that a submitted specification is **revised in place, never
cancelled and amended**, because its job cards hold their own snapshot of it and
cancelling costs a job card. So the only way to complete one of these is to let
the section be written after submission.

That is safe here in a way it would not be for, say, the parts grid, because
:meth:`before_update_after_submit` calls ``apply_computer_paper_weights`` — the
derived results are recomputed server-side on an update-after-submit exactly as
they are on a save, so no route can post a weight that does not follow from the
inputs. The four derived fields are made writable for the same reason: the
controller itself writes them on that path, and ``validate_update_after_submit``
would otherwise refuse the document's own recomputation.

What it does not do is reach an order already placed.
``Sales Order Item.custom_spec_snapshot`` is frozen at submit, so completing a
weight here lands on future orders only.

The backfill
------------

Every Computer Paper specification that carries a millimetre size gets the
matching inch entry, so the record can be *edited* in the unit it was ordered in
rather than showing an empty inch field above a converted value nobody can
change. The conversion is exact at three decimals in both directions
(241 mm → 9.488 in → 241.0 mm), so no stored millimetre and therefore no stored
weight changes — this is additive, not a correction.

Written with ``frappe.db.set_value(..., update_modified=False)`` deliberately, on
both drafts and submitted records. The inch fields *are* ``allow_on_submit``, so
an ORM save could reach the submitted ones — this is not about being allowed to:

* ``modified`` must not move. ``Sales Order Item.custom_spec_snapshot`` records
  the spec's ``modified`` as ``_cps_modified`` to say which revision it froze, so
  bumping it here would make every live order's snapshot read as stale against a
  specification that did not actually change; and
* this is a restatement of a size the record already carries, not a revision of
  it. Nothing about the specification differs afterwards, so it is not something
  ``cps_revise`` should be asked to version or a reader should be asked to
  explain.

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
	allow_weight_on_submit()
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
				"allow_on_submit": 1,
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
				"allow_on_submit": 1,
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
				"allow_on_submit": 1,
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
				"allow_on_submit": 1,
				"insert_after": w.WIDTH_FIELD,
				"depends_on": _CP_ONLY,
				"description": _CONVERTED,
			},
		],
	}


# The rest of the Weight section. Owned by v8_3.add_cp_weight_fields, so they are
# flipped by name here rather than redefined - a second copy of a field definition
# is a second thing to keep in step, and this patch only has an opinion about one
# property of them.
_ALSO_EDITABLE_AFTER_SUBMIT = (
	w.SETS_PER_CARTON_FIELD,
	w.TARE_FIELD,
	w.ALLOWANCE_FIELD,
	# The derived four. The controller writes these on update_after_submit, so
	# without this the document's own recomputation is what gets refused.
	w.TOTAL_GSM_FIELD,
	w.PER_SET_FIELD,
	w.NET_FIELD,
	w.GROSS_FIELD,
)


def allow_weight_on_submit():
	"""Let the Weight section be completed on an already-submitted specification."""
	for fieldname in _ALSO_EDITABLE_AFTER_SUBMIT:
		name = "Customer Product Specification-{0}".format(fieldname)
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "allow_on_submit", 1)


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
