"""Unit tests for CPS Artwork Version rules. Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import artwork_rules as rules


def v(**kw):
	base = {"name": "CTN-SPEC-00001-ART-1", "spec": "CTN-SPEC-00001", "version": 1, "file": "/private/files/a.pdf",
	        "uploaded_by": "rep@vimit.com", "uploaded_on": "2026-11-01 09:00:00", "spec_revision": 1,
	        "approval_state": "Pending", "superseded": 0, "superseded_by": None}
	base.update(kw)
	return base


class TestVersions(unittest.TestCase):
	def test_next_version_counts_up(self):
		self.assertEqual(rules.next_version([]), 1)
		self.assertEqual(rules.next_version([v(version=1), v(version=3)]), 4)

	def test_insert_values_are_pending_and_bound_to_the_revision(self):
		values = rules.insert_values("CTN-SPEC-00001", 2, "/private/files/b.pdf", "rep", "now", [v()])
		self.assertEqual(values["version"], 2)
		self.assertEqual(values["approval_state"], rules.STATE_PENDING)
		self.assertEqual(values["spec_revision"], 2)
		with self.assertRaises(ValueError):
			rules.insert_values("S", 1, "", "rep", "now", [])

	def test_file_and_identity_are_immutable(self):
		self.assertEqual(rules.immutable_changes(v(), v(file="/private/files/other.pdf")), ["file"])
		self.assertEqual(rules.immutable_changes(v(), v(notes="x")), [])
		self.assertEqual(rules.immutable_changes(None, v()), [])

	def test_server_fields(self):
		self.assertEqual(rules.server_field_changes(v(), v(approval_state="Customer-approved")), ["approval_state"])


class TestMarking(unittest.TestCase):
	MGR = ["Sales Master Manager"]

	def test_rep_cannot_mark(self):
		self.assertIn("manager", rules.mark_refusal(v(), "Customer-approved", ["Sales Manager"]))

	def test_manager_approves(self):
		self.assertIsNone(rules.mark_refusal(v(), "Customer-approved", self.MGR))
		values = rules.mark_values("Customer-approved", "m", "now")
		self.assertEqual(values["approval_state"], "Customer-approved")

	def test_not_applicable_needs_reason(self):
		self.assertIn("reason", rules.mark_refusal(v(), "Not applicable", self.MGR))
		self.assertIsNone(rules.mark_refusal(v(), "Not applicable", self.MGR, reason="plain job"))
		self.assertEqual(rules.mark_values("Not applicable", "m", "now", "plain job")["na_reason"], "plain job")

	def test_superseded_or_same_state_refused(self):
		self.assertIn("superseded", rules.mark_refusal(v(superseded=1), "Customer-approved", self.MGR))
		self.assertIn("already", rules.mark_refusal(v(approval_state="Customer-approved"), "Customer-approved", self.MGR))
		self.assertIn("state", rules.mark_refusal(v(), "Pending", self.MGR))


class TestArtworkForCard(unittest.TestCase):
	def test_no_versions_falls_back_and_says_so(self):
		state = rules.artwork_for_card([])
		self.assertFalse(state.versions_exist)
		self.assertIn("artwork tracker", state.note)

	def test_bound_version_decides(self):
		versions = [v(approval_state="Customer-approved"), v(name="X-2", version=2, approval_state="Pending")]
		state = rules.artwork_for_card(versions, "CTN-SPEC-00001-ART-1")
		self.assertEqual(state.state, "Customer-approved")
		self.assertFalse(state.superseded)

	def test_bound_version_superseded_is_reported(self):
		versions = [v(approval_state="Customer-approved", superseded=1, superseded_by="X-2"),
		            v(name="X-2", version=2)]
		state = rules.artwork_for_card(versions, "CTN-SPEC-00001-ART-1")
		self.assertTrue(state.superseded)
		self.assertIn("superseded by X-2", state.note)

	def test_unbound_card_reads_the_current_version(self):
		versions = [v(superseded=1, superseded_by="X-2", approval_state="Customer-approved"), v(name="X-2", version=2)]
		state = rules.artwork_for_card(versions)
		self.assertEqual(state.version, "X-2")
		self.assertEqual(state.state, "Pending")

	def test_supersede_values(self):
		self.assertEqual(rules.supersede_values("X-2"), {"superseded": 1, "superseded_by": "X-2"})
		self.assertEqual(rules.current_version([v(superseded=1)]), None)


class TestChangeRequest(unittest.TestCase):
	def cards(self):
		return [{"doctype": "Job Card Carton", "name": "JC-CORR-2026-0001", "job_status": "Open", "render_issued_on": None},
		        {"doctype": "Job Card Carton", "name": "JC-CORR-2026-0002", "job_status": "In Production", "render_issued_on": "2026-11-01"}]

	def test_build_lists_open_cards_undecided(self):
		cr = rules.build_change_request(self.cards(), "X-1")
		self.assertEqual(len(cr), 2)
		self.assertEqual(len(rules.undecided(cr)), 2)
		self.assertEqual(cr[1]["bound_version"], "X-1")

	def test_record_decision(self):
		cr = rules.build_change_request(self.cards(), "X-1")
		out = rules.record_decision(cr, "JC-CORR-2026-0002", "Rework", "pm", "now", "replate")
		self.assertEqual(out[1]["decision"], "Rework")
		self.assertIsNone(out[0]["decision"])
		self.assertEqual(len(rules.undecided(out)), 1)
		self.assertIsNone(cr[1]["decision"])  # input untouched
		with self.assertRaises(ValueError):
			rules.record_decision(cr, "JC-X", "Hold", "pm", "now")

	def test_decision_refusal(self):
		entry = {"card": "JC-1"}
		self.assertIn("decision must", rules.decision_refusal("Stop", ["Production Manager"], entry))
		self.assertIn("Production Manager", rules.decision_refusal("Hold", ["Sales User"], entry))
		self.assertIn("not on", rules.decision_refusal("Hold", ["Production Manager"], None))
		self.assertIsNone(rules.decision_refusal("Hold", ["Production Manager"], entry))


if __name__ == "__main__":
	unittest.main()
