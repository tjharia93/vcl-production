"""Let ink colours and packing be revised on a submitted specification.

The "Revise Customer Spec" button now takes print colours, packing and a new
price. Price already worked (``pricing`` is allow_on_submit); the others need
their fields open, or the revision is refused with "Not allowed to change X
after submission".

These ten fields are also set in the DocType JSON, which is what a fresh site
gets. Most already carry a Property Setter on the live site (made by hand), so
this repairs a rebuilt site and records in code what production relies on.
``number_of_colours`` is the one that matters most: it is read-only and derived,
and the revision has to be able to write the recomputed count.

Idempotent; touches no specification and no ``modified`` stamp.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

DOCTYPE = "Customer Product Specification"
FIELDS = (
	"uses_c",
	"uses_m",
	"uses_y",
	"uses_k",
	"number_of_colours",
	"spot_colours",
	"standard_packing",
	"standard_weight_per_carton",
	"packing_up",
	"packing_pieces",
)


def execute():
	for fieldname in FIELDS:
		# Custom Fields carry the flag on the field itself, not a Property Setter.
		custom = "{0}-{1}".format(DOCTYPE, fieldname)
		if frappe.db.exists("Custom Field", custom):
			frappe.db.set_value("Custom Field", custom, "allow_on_submit", 1)
			continue
		make_property_setter(DOCTYPE, fieldname, "allow_on_submit", 1, "Check")
	frappe.clear_cache(doctype=DOCTYPE)
