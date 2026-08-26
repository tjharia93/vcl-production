# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class VCLProductionMachine(Document):
	def before_save(self):
		self.machine_name = (self.machine_name or "").strip()
