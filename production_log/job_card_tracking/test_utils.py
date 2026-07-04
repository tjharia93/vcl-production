from unittest.mock import Mock, patch

from frappe.tests.utils import FrappeTestCase

from production_log.job_card_tracking import utils


class TestJobCardTrackingUtils(FrappeTestCase):
	def _row(self, **values):
		class Row(dict):
			def __getattr__(self, key):
				return self[key]

		return Row(values)

	def _submitted_job_card(self):
		doc = Mock()
		doc.docstatus = 1
		return doc

	def test_list_workstations_returns_active_rows_with_title_label(self):
		meta = Mock()
		meta.title_field = "workstation_name"
		meta.has_field.side_effect = lambda fieldname: fieldname in {
			"workstation_name",
			"disabled",
		}
		rows = [
			self._row(name="WS-01", workstation_name="Printing 01"),
			self._row(name="WS-02", workstation_name=None),
		]

		with (
			patch.object(utils.frappe, "get_meta", return_value=meta) as get_meta,
			patch.object(utils.frappe, "get_all", return_value=rows) as get_all,
		):
			result = utils.list_workstations()

		get_meta.assert_called_once_with("Workstation")
		get_all.assert_called_once_with(
			"Workstation",
			filters={"disabled": 0},
			fields=["name", "workstation_name"],
			order_by="name asc",
		)
		self.assertEqual(
			result,
			[
				{"name": "WS-01", "label": "Printing 01"},
				{"name": "WS-02", "label": "WS-02"},
			],
		)

	def test_list_workstations_handles_basic_workstation_meta(self):
		meta = Mock()
		meta.title_field = None
		meta.has_field.return_value = False
		rows = [self._row(name="WS-01")]

		with (
			patch.object(utils.frappe, "get_meta", return_value=meta),
			patch.object(utils.frappe, "get_all", return_value=rows) as get_all,
		):
			result = utils.list_workstations()

		get_all.assert_called_once_with(
			"Workstation",
			filters={},
			fields=["name"],
			order_by="name asc",
		)
		self.assertEqual(result, [{"name": "WS-01", "label": "WS-01"}])

	def test_set_machine_happy_path(self):
		doc = self._submitted_job_card()

		with (
			patch.object(utils.frappe.db, "exists", return_value=True) as exists,
			patch.object(utils.frappe, "get_doc", return_value=doc) as get_doc,
		):
			result = utils.set_machine("Job Card ETR", "JC-ETR-0001", "WS-PRINT-01")

		exists.assert_called_once_with("Workstation", "WS-PRINT-01")
		get_doc.assert_called_once_with("Job Card ETR", "JC-ETR-0001")
		doc.check_permission.assert_called_once_with("submit")
		doc.db_set.assert_called_once_with("machine", "WS-PRINT-01", update_modified=True)
		self.assertEqual(result, "WS-PRINT-01")

	def test_set_machine_rejects_invalid_doctype(self):
		with (
			patch.object(utils.frappe, "throw", side_effect=Exception("invalid doctype")) as throw,
			patch.object(utils.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(Exception):
				utils.set_machine("Sales Order", "SO-0001", "WS-PRINT-01")

		throw.assert_called_once()
		get_doc.assert_not_called()

	def test_set_machine_rejects_missing_workstation(self):
		with (
			patch.object(utils.frappe.db, "exists", return_value=False) as exists,
			patch.object(utils.frappe, "throw", side_effect=Exception("invalid machine")) as throw,
			patch.object(utils.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(Exception):
				utils.set_machine("Job Card Label", "JC-LBL-0001", "WS-MISSING")

		exists.assert_called_once_with("Workstation", "WS-MISSING")
		throw.assert_called_once()
		get_doc.assert_not_called()

	def test_set_machine_allows_clearing(self):
		doc = self._submitted_job_card()

		with (
			patch.object(utils.frappe.db, "exists") as exists,
			patch.object(utils.frappe, "get_doc", return_value=doc) as get_doc,
		):
			result = utils.set_machine("Job Card Carton", "JC-CORR-0001", "")

		exists.assert_not_called()
		get_doc.assert_called_once_with("Job Card Carton", "JC-CORR-0001")
		doc.check_permission.assert_called_once_with("submit")
		doc.db_set.assert_called_once_with("machine", None, update_modified=True)
		self.assertIsNone(result)

	def test_set_machine_rejects_draft_job_card(self):
		doc = Mock()
		doc.docstatus = 0

		with (
			patch.object(utils.frappe.db, "exists", return_value=True),
			patch.object(utils.frappe, "get_doc", return_value=doc),
			patch.object(utils.frappe, "throw", side_effect=Exception("draft")) as throw,
		):
			with self.assertRaises(Exception):
				utils.set_machine("Job Card ETR", "JC-ETR-0001", "WS-PRINT-01")

		throw.assert_called_once()
		doc.check_permission.assert_not_called()
		doc.db_set.assert_not_called()

	def test_set_machine_requires_submit_permission(self):
		doc = self._submitted_job_card()
		doc.check_permission.side_effect = Exception("permission denied")

		with (
			patch.object(utils.frappe.db, "exists", return_value=True),
			patch.object(utils.frappe, "get_doc", return_value=doc),
		):
			with self.assertRaises(Exception):
				utils.set_machine("Job Card ETR", "JC-ETR-0001", "WS-PRINT-01")

		doc.check_permission.assert_called_once_with("submit")
		doc.db_set.assert_not_called()
