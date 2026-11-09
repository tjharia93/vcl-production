# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from production_log.production_floor import eb_capture_rules


class VCLProductionMachine(Document):
	def before_save(self):
		self.machine_name = (self.machine_name or "").strip()

	def validate(self):
		bad = eb_capture_rules.unknown_stations(self.eb_stations)
		if bad:
			frappe.throw("Exercise Book Stations can only list Covers, Folds, Inserts or Packing, one per line. Not: " + ", ".join(bad))
