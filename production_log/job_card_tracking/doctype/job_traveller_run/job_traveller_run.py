# Copyright (c) 2026, Vimit Converters Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class JobTravellerRun(Document):
	"""Child doctype representing one continuous production burst at a station.

	Multi-day jobs have multiple Job Traveller Run rows per station
	(RUN 1, RUN 2, etc. — see Carton Traveller v4 spec).

	Stamped by the station operator at point-of-work. Feeds the EOD Gemba
	throughput-by-station calc and the close-out summary on the parent JCL.
	"""

	def validate(self):
		self._validate_qty_bounds()
		self._validate_close_required_fields()
		self._validate_run_number_positive()
		self._validate_skipped_state()

	# ---- internal helpers ----

	def _validate_qty_bounds(self):
		"""Waste cannot exceed input qty (both must be set for the check)."""
		if (
			self.qty_in is not None
			and self.qty_waste is not None
			and self.qty_waste > self.qty_in
		):
			frappe.throw(
				_("Run #{0} at {1}: Qty Waste ({2}) cannot exceed Qty In ({3}).").format(
					self.run_number or "?",
					self.station or _("station"),
					self.qty_waste,
					self.qty_in,
				)
			)

	def _validate_close_required_fields(self):
		"""If the operator marks the run Closed (or stamps Date Out),
		Qty Good and Time Out must be present."""
		closing = self.status == "Closed" or self.date_out
		if not closing:
			return

		missing = []
		if not self.date_out:
			missing.append(_("Date Out"))
		if not self.time_out:
			missing.append(_("Time Out"))
		if self.qty_good is None:
			missing.append(_("Qty Good"))

		if missing:
			frappe.throw(
				_("Run #{0} at {1}: required to close — {2}").format(
					self.run_number or "?",
					self.station or _("station"),
					", ".join(missing),
				)
			)

	def _validate_run_number_positive(self):
		if self.run_number is not None and self.run_number < 1:
			frappe.throw(_("Run # must be 1 or greater."))

	def _validate_skipped_state(self):
		"""A 'Skipped' run means the station doesn't apply for this job
		(e.g. a plain carton skips Printing). Qty fields must be empty;
		operator initials still required for accountability."""
		if self.status != "Skipped":
			return

		if any(v is not None and v != 0 for v in (self.qty_in, self.qty_good, self.qty_waste)):
			frappe.throw(
				_("Skipped runs cannot carry Qty In/Good/Waste — clear them or change Status."),
			)
		if not self.operator:
			frappe.throw(_("Skipped runs require an Operator initial."))
