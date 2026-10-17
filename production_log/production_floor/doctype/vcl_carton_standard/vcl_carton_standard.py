# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from production_log.production_floor.receiving import (
	REJECT_COLOURS,
	needs_customer,
	standard_name,
	tolerance_kg,
)


class VCLCartonStandard(Document):
	def autoname(self):
		self.name = standard_name(self.colour, self.parts, self.customer if needs_customer(self.colour) else None)

	def validate(self):
		if self.colour in REJECT_COLOURS:
			frappe.throw(_("Red is a rejection. It has no standard weight - leave it out of the standards."))
		if needs_customer(self.colour):
			if not self.customer:
				frappe.throw(_("A Green carton is a customer pack. Which customer?"))
		else:
			# A house colour is the same for everyone; a customer here would
			# only split one standard into two that drift apart.
			self.customer = None
		if int(self.parts or 0) < 1:
			frappe.throw(_("How many parts?"))
		if float(self.standard_kg or 0) <= 0:
			frappe.throw(_("The standard weight has to be more than zero."))
		if self.tolerance_pct in (None, ""):
			self.tolerance_pct = 2
		self.tolerance_kg = tolerance_kg(self.standard_kg, self.tolerance_pct)
		self.title = standard_name(self.colour, self.parts, self.customer)
		self.guard_duplicate()

	def guard_duplicate(self):
		expected = standard_name(self.colour, self.parts, self.customer)
		if not self.is_new() and self.name != expected:
			frappe.throw(
				_("Colour, parts and customer name the standard ({0}). Make a new one rather than changing these.").format(expected)
			)
		other = frappe.db.get_value(
			"VCL Carton Standard",
			{"colour": self.colour, "parts": self.parts, "customer": self.customer or "", "name": ("!=", self.name or "")},
		)
		if other:
			frappe.throw(_("{0} already exists.").format(other))

	def as_rule(self):
		return {
			"name": self.name,
			"colour": self.colour,
			"parts": int(self.parts),
			"customer": self.customer or None,
			"item": self.item,
			"sheets_per_pack": self.sheets_per_pack,
			"standard_kg": float(self.standard_kg),
			"tolerance_pct": float(self.tolerance_pct or 2),
			"tolerance_kg": float(self.tolerance_kg or 0),
			"active": int(self.active),
		}
