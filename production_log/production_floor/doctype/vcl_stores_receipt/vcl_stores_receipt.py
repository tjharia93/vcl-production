# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from production_log.production_floor.receiving import (
	flag_for,
	tally,
	variance_kg,
)


class VCLStoresReceipt(Document):
	def validate(self):
		self.guard_received()
		if not self.started_at:
			self.started_at = now_datetime()
		for i, row in enumerate(self.cartons, start=1):
			row.seq = i
			self.prepare_row(row)
		self.apply_tally()
		self.title = f"{self.machine or self.weigher or 'Receipt'} {frappe.utils.formatdate(self.receipt_date, 'dd/mm/yyyy')}"

	def guard_received(self):
		"""Once received the cartons are in stock. The record does not quietly change.

		Reopen (which cancels the Stock Entry) is the one way back, and it sets
		this flag for the save it makes.
		"""
		if self.is_new() or self.flags.allow_received_edit:
			return
		was = frappe.db.get_value("VCL Stores Receipt", self.name, "status")
		if was == "Received" and self.status == "Received":
			before = self.get_doc_before_save()
			if before and self._carton_signature(before) != self._carton_signature(self):
				frappe.throw(
					_("{0} has been received into stock. Reopen it before changing the cartons.").format(self.name),
					title=_("Already Received"),
				)

	@staticmethod
	def _carton_signature(doc):
		return [(r.colour, int(r.parts or 0), r.customer or "", round(float(r.weight_kg or 0), 3)) for r in doc.cartons]

	def prepare_row(self, row):
		# The flag is always re-derived from what is on the row, so a desk
		# edit to the weight cannot leave a stale verdict behind.
		row.variance_kg = variance_kg(row.standard_kg, row.weight_kg)
		row.flag = flag_for(row.colour, row.standard_kg, row.tolerance_kg, row.weight_kg)
		if row.colour != "Green":
			row.customer = None

	def apply_tally(self):
		t = tally([r.as_dict() for r in self.cartons])
		self.carton_count = t["cartons"]
		self.ok_count = t["ok"]
		self.light_count = t["light"]
		self.heavy_count = t["heavy"]
		self.unchecked_count = t["unchecked"]
		self.reject_count = t["reject"]
		self.received_cartons = t["received_cartons"]
		self.total_kg = t["total_kg"]
		self.received_kg = t["received_kg"]

	def on_trash(self):
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			frappe.throw(
				_("{0} is in stock as {1}. Reopen the receipt (which cancels the entry) before deleting it.").format(
					self.name, self.stock_entry
				)
			)
