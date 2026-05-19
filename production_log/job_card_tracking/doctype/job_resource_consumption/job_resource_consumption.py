# Copyright (c) 2026, Vimit Converters Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class JobResourceConsumption(Document):
	"""Child doctype representing one resource consumption event on a JCL.

	One row per reel mounted, per ink batch drawn, per plate used, etc.
	8 default resource_type values matching v4 Carton Traveller spec.

	variance_pct is auto-computed from (actual_qty - planned_qty) / planned_qty.
	Drives the Yield & Variance close-out on the traveller and the
	per-job material variance flag in the EOD Gemba PDF.
	"""

	def validate(self):
		self._compute_variance_pct()
		self._validate_actual_present_for_closed_jobs()

	# ---- internal helpers ----

	def _compute_variance_pct(self):
		"""variance_pct = (actual - planned) / planned * 100.

		Positive = over-consumed. Negative = under-consumed.
		Left blank if either side is unset or planned is zero.
		"""
		planned = self.planned_qty
		actual = self.actual_qty

		if planned is None or actual is None or planned == 0:
			self.variance_pct = None
			return

		self.variance_pct = round((actual - planned) / planned * 100.0, 2)

	def _validate_actual_present_for_closed_jobs(self):
		"""Only block if the parent JCL is closed and actual_qty is still blank.
		For in-progress JCLs, partial / interim rows are fine.
		"""
		if not self.parent or not self.parenttype:
			return

		try:
			parent_status = frappe.db.get_value(self.parenttype, self.parent, "job_status")
		except Exception:
			# Parent might not exist yet on insert — let parent save sort it.
			return

		if parent_status in ("Closed", "Completed") and self.actual_qty is None:
			frappe.throw(
				_(
					"Resource row '{0}' ({1}) on closed/completed job: Actual quantity must be set."
				).format(self.identifier or "?", self.resource_type or _("resource")),
			)
