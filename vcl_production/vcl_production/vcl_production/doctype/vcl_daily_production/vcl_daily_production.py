# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, today

from vcl_production.reporting import (
	QuantityError,
	build_report_text,
	build_whatsapp_text,
	exception_summary,
	parse_quantity,
	summarise,
)

MANAGER_ROLE = "VCL Production Manager"

# Snapshotted onto the row from the remembered job. Copied once, on the way
# in - the row is the record of what actually ran, so renaming the master
# later must not rewrite history.
SNAPSHOT_FIELDS = {
	"customer_name": "customer_name",
	"job_name": "job_name",
	"department": "department",
	"uom": "default_uom",
}


class VCLDailyProduction(Document):
	def validate(self):
		self.guard_closed()
		if not self.submitted_by:
			self.submitted_by = frappe.session.user
		for row in self.items:
			self.prepare_row(row)

	def guard_closed(self):
		"""A closed day is a published report; it does not quietly change."""
		if self.is_new():
			return
		was_closed = frappe.db.get_value("VCL Daily Production", self.name, "status") == "Closed"
		if was_closed and self.status == "Closed":
			frappe.throw(
				_("{0} is closed. Reopen the day before changing it.").format(self.name),
				title=_("Day Closed"),
			)

	def prepare_row(self, row):
		if row.production_job:
			self.snapshot_from_job(row)

		row.customer_name = (row.customer_name or "").strip()
		row.job_name = (row.job_name or "").strip()

		for fieldname, label in (("planned_quantity", _("Planned Quantity")), ("actual_quantity", _("Actual Quantity"))):
			try:
				setattr(row, fieldname, parse_quantity(row.get(fieldname), label))
			except QuantityError as exc:
				frappe.throw(str(exc), title=_("Row {0}").format(row.idx))

		self.stamp_times(row)

		# Deliberately a warning and not a throw. Mid-shift the floor should
		# be able to flag a pause in one tap and explain it a minute later;
		# the reason is enforced on the quick-update path and at closing.
		if row.status in ("Paused", "Carried Forward") and not (row.reason or "").strip():
			frappe.msgprint(
				_("Row {0} ({1}) is {2} with no reason. Add one before closing the day.").format(
					row.idx, row.machine or row.customer_name, row.status
				),
				indicator="orange",
				alert=True,
			)

	def snapshot_from_job(self, row):
		job = frappe.db.get_value(
			"VCL Production Job",
			row.production_job,
			list(SNAPSHOT_FIELDS.values()),
			as_dict=True,
		)
		if not job:
			return
		for target, source in SNAPSHOT_FIELDS.items():
			if not row.get(target) and job.get(source):
				setattr(row, target, job.get(source))

	def stamp_times(self, row):
		if row.status == "Running" and not row.start_time:
			row.start_time = now_datetime()
		if row.status == "Completed":
			if not row.start_time:
				row.start_time = now_datetime()
			if not row.completed_time:
				row.completed_time = now_datetime()
		if row.status in ("Planned", "Not Started"):
			row.completed_time = None

	def on_update(self):
		self.remember_new_jobs()

	def remember_new_jobs(self):
		"""Turn what was typed today into tomorrow's autocomplete.

		This is the whole point of the remembered-jobs master: nobody has to
		visit it. A row typed by hand becomes a reusable job as a side effect
		of saving the day.
		"""
		from vcl_production.vcl_production.doctype.vcl_production_job.vcl_production_job import (
			remember_job,
		)

		if not frappe.db.get_single_value("VCL Production Settings", "auto_remember_jobs"):
			return

		for row in self.items:
			if not (row.customer_name and row.job_name):
				continue
			if not row.remember_job:
				continue
			job_name = remember_job(
				row.customer_name,
				row.job_name,
				department=row.department,
				uom=row.uom,
				on_date=self.production_date,
				is_demo=self.is_demo,
			)
			if job_name and row.production_job != job_name:
				row.db_set("production_job", job_name, update_modified=False)

	# ------------------------------------------------------------------
	# day lifecycle
	# ------------------------------------------------------------------

	def as_report_dict(self):
		return {
			"name": self.name,
			"production_date": str(self.production_date),
			"status": self.status,
			"notes": self.notes,
			"items": [row.as_dict() for row in self.items],
		}

	def get_summary(self):
		return summarise([row.as_dict() for row in self.items])

	def get_exceptions(self):
		return exception_summary([row.as_dict() for row in self.items])

	def report_text(self, departments=None):
		return build_report_text(self.as_report_dict(), departments)

	def whatsapp_text(self, departments=None):
		return build_whatsapp_text(self.as_report_dict(), departments)

	def close_day(self, force=False):
		"""Close the day, refusing while critical information is missing."""
		if self.status == "Closed":
			frappe.throw(_("{0} is already closed.").format(self.name))

		require_manager()

		exceptions = self.get_exceptions()
		blocking = frappe.db.get_single_value("VCL Production Settings", "block_close_on_critical")
		if exceptions["critical"] and blocking and not force:
			frappe.throw(
				_("This day cannot be closed yet:") + "<br><br>" + "<br>".join(
					"• {0} — {1}".format(item["label"], item["message"])
					for item in exceptions["critical"]
				),
				title=_("Information Missing"),
			)

		self.status = "Closed"
		self.closed_by = frappe.session.user
		self.closed_at = now_datetime()
		self.save()
		return exceptions

	def reopen_day(self):
		require_manager()
		self.db_set("status", "Open")
		self.db_set("closed_by", None)
		self.db_set("closed_at", None)
		return self.name


def require_manager():
	if MANAGER_ROLE in frappe.get_roles() or "System Manager" in frappe.get_roles():
		return
	frappe.throw(
		_("Only a {0} can open or close a production day.").format(MANAGER_ROLE),
		frappe.PermissionError,
	)


def get_or_create_day(production_date=None, create=True):
	"""The day document for a date, created on first use.

	A supervisor should never have to think about 'creating today' - opening
	the screen is what creates it.
	"""
	production_date = production_date or today()
	name = frappe.db.get_value("VCL Daily Production", {"production_date": production_date}, "name")
	if name:
		return frappe.get_doc("VCL Daily Production", name)
	if not create:
		return None

	doc = frappe.get_doc({
		"doctype": "VCL Daily Production",
		"production_date": production_date,
		"status": "Open",
		"submitted_by": frappe.session.user,
	})
	doc.insert(ignore_permissions=True)
	return doc
