# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today

from production_log.production_floor.reporting import normalise_key


class VCLProductionJob(Document):
	def before_save(self):
		self.customer_name = (self.customer_name or "").strip()
		self.job_name = (self.job_name or "").strip()
		self.full_label = build_label(self.customer_name, self.job_name)
		self.normalised_key = normalise_key(self.customer_name, self.job_name)

	def mark_used(self, on_date=None):
		"""Called when the job is used on a production day."""
		on_date = on_date or today()
		if self.last_used_date == on_date:
			return
		self.db_set("last_used_date", on_date, update_modified=False)
		self.db_set("times_used", (self.times_used or 0) + 1, update_modified=False)


def build_label(customer_name, job_name):
	customer = (customer_name or "").strip()
	job = (job_name or "").strip()
	if customer and job:
		return "{0} — {1}".format(customer, job)
	return customer or job


def find_job(customer_name, job_name):
	"""Return the name of the remembered job for this pair, if there is one."""
	return frappe.db.get_value(
		"VCL Production Job",
		{"normalised_key": normalise_key(customer_name, job_name)},
		"name",
	)


def remember_job(customer_name, job_name, department=None, uom=None, on_date=None, is_demo=0,
		job_card=None):
	"""Create or refresh a remembered job for this customer + job pair.

	Idempotent by design: the floor types the same names dozens of times a
	week and must never end up with dozens of masters. An existing job is
	reactivated rather than duplicated, and its department / unit are only
	filled in where they were previously blank - a manual correction on the
	master is not overwritten by whatever was typed on a busy Tuesday.
	"""
	customer_name = (customer_name or "").strip()
	job_name = (job_name or "").strip()
	if not (customer_name and job_name):
		return None

	job_card = (job_card or "").strip()

	existing = find_job(customer_name, job_name)
	if existing:
		doc = frappe.get_doc("VCL Production Job", existing)
		changed = False
		if job_card and not doc.production_job_card:
			# Only fills a blank, like department and unit above: a job first
			# typed by hand and later picked from a card gains the reference,
			# but a correction made on the master is never overwritten.
			doc.production_job_card = job_card
			doc.source = "Job Card"
			changed = True
		if not doc.active:
			doc.active = 1
			changed = True
		if department and not doc.department:
			doc.department = department
			changed = True
		if uom and not doc.default_uom:
			doc.default_uom = uom
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
		doc.mark_used(on_date)
		return doc.name

	doc = frappe.get_doc({
		"doctype": "VCL Production Job",
		"customer_name": customer_name,
		"job_name": job_name,
		"department": department,
		"default_uom": uom,
		"active": 1,
		"source": "Job Card" if job_card else "Manual",
		"production_job_card": job_card or None,
		"is_demo": 1 if is_demo else 0,
	})
	doc.insert(ignore_permissions=True)
	doc.mark_used(on_date)
	return doc.name
