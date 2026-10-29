# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

"""CP Standard Packing (CR8, TRK-00342): sets per carton, set once per item.

Packing is a property of the computer paper item, decided by management, not
retyped on every specification. Other code reads this doctype by these exact
names, so do not rename the doctype or its fields: ``item_code``,
``sets_per_carton``, ``notes``.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class CPStandardPacking(Document):
	def validate(self):
		if int(self.sets_per_carton or 0) < 1:
			frappe.throw(_("Sets per Carton must be at least 1."))
