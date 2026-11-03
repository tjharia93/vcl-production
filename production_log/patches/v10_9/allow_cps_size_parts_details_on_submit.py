"""Let size, number of parts and the details be revised on a submitted specification.

``cps_revise.revise`` now takes ``size`` (finished inches, Job Size), a parts
list of a different length (Number of Parts follows it), a part's "Used for",
and ``details`` (name, item, numbering, printed side, colour notes, carton
special instructions, artwork link). Each field it writes must be
allow_on_submit, or the save is refused with "Not allowed to change X after
submission". For the parts table the child fields need the flag too:
``validate_update_after_submit`` checks every existing child row.

Print Type stays fixed: Plain and Printed are different products.

These are also set in the DocType JSON and the Custom Field fixture, which is
what a fresh site gets. This repairs a site whose copy differs, and records in
code what production relies on. The Desk form keeps them read-only on a
submitted spec (Client Script "CPS — Size and Build only via Revise"), so a
change always goes through Revise with a reason.

Idempotent; touches no specification and no ``modified`` stamp.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

FIELDS = {
	"Customer Product Specification": (
		"specification_name",
		"colour_notes",
		"special_instructions_carton",
		"number_of_parts",
		"colour_of_parts",
		"numbering_required",
		"numbering_confirmed",
		"print_side",
	),
	"Colour of Parts": ("part_number", "paper_type", "gsm", "colour", "purpose"),
}


def execute():
	for doctype, fieldnames in FIELDS.items():
		for fieldname in fieldnames:
			# Custom Fields carry the flag on the field itself, not a Property Setter.
			custom = "{0}-{1}".format(doctype, fieldname)
			if frappe.db.exists("Custom Field", custom):
				frappe.db.set_value("Custom Field", custom, "allow_on_submit", 1)
				continue
			make_property_setter(doctype, fieldname, "allow_on_submit", 1, "Check")
		frappe.clear_cache(doctype=doctype)
