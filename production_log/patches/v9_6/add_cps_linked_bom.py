"""Patch v9_6: the ``linked_bom`` field on Customer Product Specification.

Records which BOM was generated from a specification. It is not a
convenience: several specifications share one ``linked_item`` with different
colour recipes — ``Computer Paper Pre-Printed-9.5 x 8-2 Part`` serves
Gilani's White/Yellow, Classic Ironmongers Yellow/White reversed and two
Mikeline White/Pink specs — so ``is_default`` on the BOM cannot say which
recipe belongs to which job, and searching by item would return somebody
else's.

``allow_on_submit`` because every specification this will ever run on is
already submitted; the same revise-in-place rule this doctype follows for its
weight and artwork fields.

Read-only on the form: it is written by the Create BOM button, and a hand-typed
value would point a job at the wrong recipe with no way to tell.

Also mirrored into ``fixtures/custom_field.json``. CPS Custom Fields are in the
``fixtures`` list in ``hooks.py``, so the fixture is what a deploy applies —
without it the next migrate would drop this field.

Idempotent: ``create_custom_fields`` inserts what is absent and reconciles what
is present.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_log.job_card_tracking import cps_cp_rules

_COMPUTER_PAPER_ONLY = "eval:doc.product_type=='{0}'".format(cps_cp_rules.COMPUTER_PAPER)


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache(doctype="Customer Product Specification")


def get_custom_fields():
	return {
		"Customer Product Specification": [
			{
				"fieldname": "linked_bom",
				"label": "Linked BOM",
				"fieldtype": "Link",
				"options": "BOM",
				"insert_after": "linked_item",
				"allow_on_submit": 1,
				"read_only": 1,
				"depends_on": _COMPUTER_PAPER_ONLY,
				"description": (
					"The BOM generated from this specification. Set by the Create BOM "
					"button; several specifications share one Item with different "
					"recipes, so this is what tells them apart."
				),
			},
		],
	}
