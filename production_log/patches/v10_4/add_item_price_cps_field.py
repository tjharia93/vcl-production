"""One Custom Field on Item Price: which specification supplied this rate.

Schema only. It does two jobs at once, which is why it is one field and not two:

1. It is the "store the detail in the price list as well as the CPS" half of the
   2026-09-12 decision — a price-list row can now say where its number came from.
2. It is the mirror's **ownership mark**. `cps_price_mirror` modifies a row only
   if this field is set, so the twelve customer prices that predate the mirror,
   and the three set from invoices on 2026-09-11, are never touched by it.

Item Price is a core ERPNext DocType, and core DocTypes cannot take DocField
writes on Frappe Cloud (403) — hence a Custom Field. Read-only because nothing
but the mirror should ever set it: a hand-typed value would hand a human row to
the script.

Also registered in ``install.py``: ``install_app()`` stamps every line of
patches.txt as completed WITHOUT running it, so a patch reaching outside the
app's own doctypes never executes on a fresh site and migrate never retries it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_custom_fields():
	return {
		"Item Price": [
			{
				"fieldname": "custom_cps",
				"label": "Customer Product Specification",
				"fieldtype": "Link",
				"options": "Customer Product Specification",
				"insert_after": "price_list_rate",
				"read_only": 1,
				"no_copy": 1,
				"description": (
					"Set by the CPS price mirror. A row without this was created by a "
					"person, and the mirror will never modify it."
				),
			}
		]
	}


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	frappe.clear_cache()
