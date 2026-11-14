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

	def _etr_card(self, job_status, status):
		values = {"job_status": job_status, "status": status}
		doc = Mock(spec=["docstatus", "get", "db_set", "check_permission", "add_comment"])
		doc.docstatus = 1
		doc.get.side_effect = values.get
		return doc

	def test_set_job_status_accepts_etr_and_keeps_status_in_step(self):
		doc = self._etr_card("Open", "In Progress")
		with patch.object(utils.frappe, "get_doc", return_value=doc):
			result = utils.set_job_status("Job Card ETR", "JC-ETR-0001", "Completed")

		self.assertEqual(result, "Completed")
		doc.check_permission.assert_called_once_with("submit")
		doc.db_set.assert_any_call("job_status", "Completed", update_modified=True)
		doc.db_set.assert_any_call("status", "Completed", update_modified=False)

	def test_set_job_status_reopens_a_completed_etr_card(self):
		doc = self._etr_card("Completed", "Completed")
		with patch.object(utils.frappe, "get_doc", return_value=doc):
			utils.set_job_status("Job Card ETR", "JC-ETR-0001", "In Production")

		doc.db_set.assert_any_call("status", "In Progress", update_modified=False)

	def test_set_job_status_leaves_etr_status_alone_when_already_right(self):
		doc = self._etr_card("Open", "Completed")
		with patch.object(utils.frappe, "get_doc", return_value=doc):
			utils.set_job_status("Job Card ETR", "JC-ETR-0001", "Closed")

		self.assertEqual([c.args[0] for c in doc.db_set.call_args_list], ["job_status"])

	def test_set_job_status_does_not_touch_status_on_other_cards(self):
		doc = self._etr_card("Open", "Open")
		with patch.object(utils.frappe, "get_doc", return_value=doc):
			utils.set_job_status("Job Card Label", "JC-LBL-0001", "Planned")

		self.assertEqual([c.args[0] for c in doc.db_set.call_args_list], ["job_status"])
