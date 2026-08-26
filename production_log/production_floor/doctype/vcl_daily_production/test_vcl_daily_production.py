# Copyright (c) 2026, VCL and contributors
# For license information, please see license.txt

"""Bench tests for the day document.

	bench --site <site> run-tests --module \
		production_log.production_floor.doctype.vcl_daily_production.test_vcl_daily_production

The report wording and the exception rules are tested separately, without a
bench, in production_floor/tests/test_reporting.py. What is tested here is only the part that
genuinely needs a database: remembering jobs, snapshotting, and closing.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from production_log.production_floor.api import add_item, close_day, update_item
from production_log.production_floor.setup.seed import seed_machines
from production_log.production_floor.doctype.vcl_production_job.vcl_production_job import find_job


def cleanup(production_date):
	name = frappe.db.get_value("VCL Daily Production", {"production_date": production_date}, "name")
	if name:
		frappe.delete_doc("VCL Daily Production", name, force=True, ignore_permissions=True)


class TestVCLDailyProduction(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		seed_machines()
		frappe.db.commit()

	def setUp(self):
		# A date far enough out that it cannot collide with real production
		# on a site someone is also using by hand.
		self.date = add_days(today(), 400)
		cleanup(self.date)

	def tearDown(self):
		cleanup(self.date)

	def test_a_brand_new_job_can_be_typed_without_any_master(self):
		day = add_item(
			production_date=self.date,
			department="Computer",
			machine="M1",
			customer_name="Chandaria",
			job_name="Yellow Copy",
			planned_quantity="3",
			uom="reels",
		)
		self.assertEqual(len(day["items"]), 1)
		self.assertEqual(day["items"][0]["customer_name"], "Chandaria")
		self.assertEqual(day["items"][0]["planned_quantity"], 3)

	def test_typing_a_job_remembers_it_for_next_time(self):
		add_item(
			production_date=self.date,
			department="Computer",
			machine="M1",
			customer_name="Zeta Test Customer",
			job_name="Zeta Test Job",
			planned_quantity="1",
			uom="reels",
		)
		remembered = find_job("Zeta Test Customer", "Zeta Test Job")
		self.assertTrue(remembered)
		job = frappe.get_doc("VCL Production Job", remembered)
		self.assertEqual(job.department, "Computer")
		self.assertEqual(job.default_uom, "reels")
		self.assertEqual(job.last_used_date, frappe.utils.getdate(self.date))

	def test_the_same_job_typed_twice_does_not_duplicate_the_master(self):
		for machine, customer in (("M1", "E.W.A.L"), ("M2", "ewal")):
			add_item(
				production_date=self.date,
				department="Computer",
				machine=machine,
				customer_name=customer,
				job_name="Carton",
				planned_quantity="1",
				uom="cartons",
			)
		keys = frappe.get_all(
			"VCL Production Job",
			filters={"normalised_key": "ewal::carton"},
			pluck="name",
		)
		self.assertEqual(len(keys), 1)

	def test_picking_a_remembered_job_snapshots_it_onto_the_row(self):
		add_item(
			production_date=self.date,
			department="Offset",
			machine="Solna",
			customer_name="Prince",
			job_name="3 Quire",
			planned_quantity="2000",
			uom="pcs",
		)
		job = find_job("Prince", "3 Quire")
		cleanup(self.date)

		day = add_item(
			production_date=self.date,
			department="Offset",
			machine="Solna",
			customer_name="Prince",
			job_name="3 Quire",
			production_job=job,
			planned_quantity="2000",
			uom="pcs",
		)
		self.assertEqual(day["items"][0]["production_job"], job)
		self.assertEqual(day["items"][0]["customer_name"], "Prince")

		# Renaming the master must not rewrite what actually ran.
		doc = frappe.get_doc("VCL Production Job", job)
		doc.job_name = "3 Quire (renamed)"
		doc.save()
		fresh = frappe.get_doc("VCL Daily Production", {"production_date": self.date})
		self.assertEqual(fresh.items[0].job_name, "3 Quire")

	def test_arithmetic_in_a_quantity_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			add_item(
				production_date=self.date,
				department="Computer",
				machine="M1",
				customer_name="Chandaria",
				job_name="Yellow Copy",
				planned_quantity="41+6",
				uom="reels",
			)

	def test_carrying_forward_without_a_reason_is_refused(self):
		day = add_item(
			production_date=self.date,
			department="Carton",
			machine="Bundling",
			customer_name="E.W.A.L",
			job_name="Carton",
			planned_quantity="1000",
			uom="pcs",
		)
		row = day["items"][0]["name"]
		with self.assertRaises(frappe.ValidationError):
			update_item(
				production_date=self.date,
				row=row,
				status="Carried Forward",
				actual_quantity="47",
			)

		day = update_item(
			production_date=self.date,
			row=row,
			status="Carried Forward",
			actual_quantity="47",
			reason="Board ran out at 3pm",
		)
		self.assertEqual(day["items"][0]["status"], "Carried Forward")

	def test_a_day_will_not_close_while_something_critical_is_missing(self):
		day = add_item(
			production_date=self.date,
			department="Offset",
			machine="Solna",
			customer_name="Prince",
			job_name="1 Quire",
			planned_quantity="1500",
			uom="pcs",
		)
		row = day["items"][0]["name"]

		# Completed with no actual quantity is critical, so closing is refused.
		doc = frappe.get_doc("VCL Daily Production", day["name"])
		doc.items[0].status = "Completed"
		doc.save()
		with self.assertRaises(frappe.ValidationError):
			close_day(production_date=self.date)

		update_item(production_date=self.date, row=row, status="Completed", actual_quantity="1500")
		result = close_day(production_date=self.date)
		self.assertEqual(result["day"]["status"], "Closed")

	def test_a_closed_day_refuses_further_entry(self):
		add_item(
			production_date=self.date,
			department="Offset",
			machine="Miller",
			customer_name="Prince",
			job_name="2 Quire",
			planned_quantity="10",
			uom="pcs",
		)
		doc = frappe.get_doc("VCL Daily Production", {"production_date": self.date})
		doc.items[0].status = "Completed"
		doc.items[0].actual_quantity = 10
		doc.save()
		close_day(production_date=self.date)

		with self.assertRaises(frappe.ValidationError):
			add_item(
				production_date=self.date,
				department="Offset",
				machine="Miller",
				customer_name="Prince",
				job_name="4 Quire",
				planned_quantity="10",
				uom="pcs",
			)
