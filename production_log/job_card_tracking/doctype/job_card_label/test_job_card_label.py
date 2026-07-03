import frappe
from frappe.tests.utils import FrappeTestCase


JOB_STATUS_OPTIONS = [
	"Open",
	"Planned",
	"In Production",
	"Packing Pending",
	"Completed",
	"Closed",
	"On Hold",
	"Cancelled",
]


class TestJobCardLabel(FrappeTestCase):
	def test_job_card_metadata_has_machine_and_standard_job_status(self):
		for doctype in (
			"Job Card Carton",
			"Job Card Computer Paper",
			"Job Card Label",
			"Job Card ETR",
		):
			meta = frappe.get_meta(doctype)

			machine = meta.get_field("machine")
			self.assertIsNotNone(machine, doctype)
			self.assertEqual(machine.fieldtype, "Link")
			self.assertEqual(machine.options, "Workstation")
			self.assertFalse(machine.reqd)

			job_status = meta.get_field("job_status")
			self.assertIsNotNone(job_status, doctype)
			self.assertEqual(job_status.fieldtype, "Select")
			self.assertEqual(job_status.options.splitlines(), JOB_STATUS_OPTIONS)
