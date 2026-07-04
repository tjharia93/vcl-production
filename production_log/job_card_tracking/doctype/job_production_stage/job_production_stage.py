# Copyright (c) 2026, Vimit Converters Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class JobProductionStage(Document):
	def validate(self):
		self.validate_machine_asset_category()

	def validate_machine_asset_category(self):
		if not self.machine_asset:
			return

		asset_category = frappe.db.get_value("Asset", self.machine_asset, "asset_category")
		if asset_category != "Plant & Machinery":
			frappe.throw(
				_("Machine Asset must be in Asset Category 'Plant & Machinery'."),
				title=_("Invalid Machine Asset"),
			)
