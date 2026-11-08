"""Unit tests for the CPS lifecycle rules (Stream A §1-§3). Plain unittest, no bench."""

import json
import unittest

from production_log.job_card_tracking import cps_lifecycle_rules as rules


def carton(**kw):
	base = {
		"name": "CTN-SPEC-00001",
		"product_type": "Carton",
		"customer": "ACME Ltd",
		"specification_name": "Shipper",
		"status": "Active",
		"docstatus": 1,
		"ply": "3",
		"flute_type": "B",
		"ctn_length_mm": 400,
		"ctn_width_mm": 300,
		"ctn_height_mm": 200,
		"joint_type": "Gluing - Machine",
		"product_type_carton": "1 Flap RSC",
		"idod": "ID",
		"1_ply_top_layer_gsm": 150,
		"print_type": "Plain",
		"internal_notes": "",
		"vcl_revision": 1,
		"vcl_approved_rev": 1,
		"vcl_approval_state": "Approved",
		"colour_of_parts": [],
		"spot_colours": [],
		"pricing": [],
	}
	base.update(kw)
	return base


class TestRevisionFields(unittest.TestCase):
	def test_shared_print_and_packing_fields_apply_to_every_type(self):
		for product_type in ("Carton", "Computer Paper", "Label", "Monobox", None):
			fields = rules.revision_fields(product_type)
			self.assertIn("print_type", fields)
			self.assertIn("standard_packing", fields)

	def test_carton_dimensions_and_die_are_revision_fields(self):
		fields = rules.revision_fields("Carton")
		for f in ("ctn_length_mm", "ply", "1_ply_top_layer_gsm", "carton_cutting_die", "joint_type"):
			self.assertIn(f, fields)

	def test_notes_name_customer_and_price_are_not(self):
		fields = rules.revision_fields("Carton")
		for f in ("internal_notes", "specification_name", "customer", "pricing", "current_rate", "status"):
			self.assertNotIn(f, fields)

	def test_no_duplicates(self):
		for product_type in rules.PRODUCT_TYPE_REVISION_FIELDS:
			fields = rules.revision_fields(product_type)
			self.assertEqual(len(fields), len(set(fields)))


class TestRevisionBump(unittest.TestCase):
	def test_notes_only_change_does_not_bump(self):
		before, after = carton(), carton(internal_notes="call before delivery")
		self.assertFalse(rules.revision_bump_required(before, after, "Carton"))
		self.assertEqual(rules.revision_changes(before, after, "Carton"), [])

	def test_dimension_change_bumps(self):
		self.assertTrue(rules.revision_bump_required(carton(), carton(ctn_length_mm=410), "Carton"))

	def test_price_row_added_does_not_bump(self):
		after = carton(pricing=[{"valid_from": "2026-11-01", "rate": 12.5}])
		self.assertFalse(rules.revision_bump_required(carton(), after, "Carton"))

	def test_child_row_change_bumps(self):
		before = carton(spot_colours=[{"pantone_code": "185 C", "colour_name": "Red"}])
		after = carton(spot_colours=[{"pantone_code": "186 C", "colour_name": "Red"}])
		self.assertIn("spot_colours", rules.revision_changes(before, after, "Carton"))

	def test_numeric_text_equivalence_is_not_a_change(self):
		self.assertFalse(rules.revision_bump_required(carton(ctn_length_mm="400"), carton(ctn_length_mm=400.0), "Carton"))

	def test_blank_and_none_are_equal(self):
		self.assertFalse(rules.revision_bump_required(carton(ctn_flap_mm=None), carton(ctn_flap_mm=""), "Carton"))

	def test_no_before_means_no_bump(self):
		self.assertFalse(rules.revision_bump_required(None, carton(), "Carton"))

	def test_after_bump_resets_approval_but_keeps_approved_rev(self):
		values = rules.after_revision_bump(2)
		self.assertEqual(values["vcl_revision"], 3)
		self.assertEqual(values["vcl_approval_state"], rules.APPROVAL_AWAITING)
		self.assertNotIn("vcl_approved_rev", values)


class TestPayload(unittest.TestCase):
	def test_payload_carries_revision_fields_and_children(self):
		spec = carton(spot_colours=[{"pantone_code": "185 C", "colour_name": "Red", "extra": "ignored"}])
		payload = rules.build_revision_payload(spec, 1, "2026-11-08 10:00:00", "neema@vimit.com")
		self.assertEqual(payload["_revision"], 1)
		self.assertEqual(payload["ctn_length_mm"], 400)
		self.assertEqual(payload["spot_colours"][0]["pantone_code"], "185 C")
		self.assertNotIn("extra", payload["spot_colours"][0])
		self.assertNotIn("internal_notes", payload)
		json.dumps(payload)  # must be serialisable

	def test_payload_mismatches_name_the_field(self):
		payload = rules.build_revision_payload(carton(), 1, "t", "u")
		out = rules.payload_mismatches(payload, carton(ctn_width_mm=310))
		self.assertEqual([m[0] for m in out], ["ctn_width_mm"])
		self.assertEqual(rules.payload_mismatches(payload, carton()), [])

	def test_parse_payload_tolerates_junk(self):
		self.assertIsNone(rules.parse_payload("not json"))
		self.assertIsNone(rules.parse_payload(""))
		self.assertEqual(rules.parse_payload('{"a": 1}'), {"a": 1})

	def test_payload_for_revision_finds_the_right_entry(self):
		log = json.dumps([{"_revision": 1, "x": 1}, {"_revision": 2, "x": 2}])
		self.assertEqual(rules.payload_for_revision(log, 2)["x"], 2)
		self.assertIsNone(rules.payload_for_revision(log, 3))
		self.assertIsNone(rules.payload_for_revision("", 1))


class TestApproval(unittest.TestCase):
	def test_technical_approval_stamps_exact_revision(self):
		values = rules.technical_approval_values(3, "neema@vimit.com", "now", rule="CP technical")
		self.assertEqual(values["vcl_approved_rev"], 3)
		self.assertEqual(values["vcl_approval_state"], rules.APPROVAL_APPROVED)
		self.assertEqual(values["vcl_approval_rule"], "CP technical")

	def test_rejection_stays_awaiting(self):
		values = rules.technical_rejection_values("die not confirmed")
		self.assertEqual(values["vcl_approval_state"], rules.APPROVAL_AWAITING)
		self.assertEqual(values["vcl_approval_notes"], "die not confirmed")

	def test_is_technically_approved_requires_matching_revision(self):
		self.assertTrue(rules.is_technically_approved(carton()))
		self.assertFalse(rules.is_technically_approved(carton(vcl_revision=2)))
		self.assertFalse(rules.is_technically_approved(carton(vcl_approval_state="Awaiting approval")))
		self.assertFalse(rules.is_technically_approved(carton(vcl_revision=0, vcl_approved_rev=0)))

	def test_approval_history_keeps_earlier_revisions_approved(self):
		# Codex r5 (5): approving rev 3 must not un-approve rev 2.
		log = json.dumps([{"_revision": 1}, {"_revision": 2}, {"_revision": 3}])
		log = rules.approve_revision_in_log(log, 2, "neema", "2026-11-01 10:00:00", "CP technical")
		log = rules.approve_revision_in_log(log, 3, "neema", "2026-11-05 10:00:00", "CP technical")
		self.assertEqual(rules.approved_revisions(log), [2, 3])
		spec = carton(vcl_revision=3, vcl_approved_rev=3, vcl_approval_state="Approved", vcl_revision_log=json.dumps(log))
		self.assertTrue(rules.revision_is_approved(spec, 2))
		self.assertTrue(rules.revision_is_approved(spec, 3))
		self.assertFalse(rules.revision_is_approved(spec, 1))
		# A revision absent from the log is appended, so the history survives a missing payload.
		log = rules.approve_revision_in_log("", 1, "u", "now")
		self.assertEqual(rules.approved_revisions(log), [1])

	def test_rejection_revokes_that_revisions_approval(self):
		# Codex r6 (3): approve rev 2, then reject it - revision_is_approved must say no.
		log = rules.approve_revision_in_log("", 2, "neema", "t1", "CP technical")
		self.assertEqual(rules.approved_revisions(log), [2])
		log = rules.revoke_revision_in_log(log, 2, "neema", "t2", "die changed")
		self.assertEqual(rules.approved_revisions(log), [])
		spec = carton(vcl_revision=2, vcl_approved_rev=2, vcl_approval_state="Awaiting approval", vcl_revision_log=json.dumps(log))
		self.assertFalse(rules.revision_is_approved(spec, 2))
		# A fresh approval after the rejection stands again; the revocation is kept as history.
		log = rules.approve_revision_in_log(log, 2, "neema", "t3")
		self.assertEqual(rules.approved_revisions(log), [2])
		self.assertEqual(len(log[0]["_revocations"]), 1)
		self.assertNotIn("_revoked_on", log[0])

	def test_vcl_source_iq_is_server_owned(self):
		out = rules.unauthorised_changes(carton(), carton(vcl_source_iq="IQ-2026-00001"), ("Sales Master Manager",))
		self.assertEqual([u.fieldname for u in out], ["vcl_source_iq"])
		self.assertEqual(rules.unauthorised_changes(carton(), carton(vcl_source_iq="IQ-2026-00001"), (), is_server=True), [])

	def test_bound_earlier_revision_stays_approved(self):
		# Codex r4 (1): the card is judged against the revision bound to it.
		spec = carton(vcl_revision=3, vcl_approved_rev=2, vcl_approval_state="Awaiting approval")
		self.assertTrue(rules.revision_is_approved(spec, 2))
		self.assertFalse(rules.revision_is_approved(spec, 3))
		self.assertFalse(rules.revision_is_approved(spec, None))


class TestGrandfather(unittest.TestCase):
	def test_values_set_both_revisions_and_preserve_status(self):
		values = rules.grandfather_values("Inactive", "tanuj@vimit.com", "08/11/2026")
		self.assertEqual(values["status"], "Inactive")
		self.assertEqual(values["vcl_revision"], 1)
		self.assertEqual(values["vcl_approved_rev"], 1)
		self.assertEqual(values["vcl_approved_by"], "tanuj@vimit.com")
		self.assertIn("08/11/2026", values["vcl_approval_notes"])

	def test_needs_grandfathering_only_for_submitted_unstamped(self):
		self.assertTrue(rules.needs_grandfathering({"docstatus": 1, "vcl_revision": 0}))
		self.assertTrue(rules.needs_grandfathering({"docstatus": 1, "vcl_revision": None}))
		self.assertFalse(rules.needs_grandfathering({"docstatus": 1, "vcl_revision": 1}))
		self.assertFalse(rules.needs_grandfathering({"docstatus": 0, "vcl_revision": 0}))


class TestUnauthorisedChanges(unittest.TestCase):
	REP = ("Sales Manager", "Sales User")
	MGR = ("Sales Master Manager",)

	def test_rep_may_change_construction(self):
		self.assertEqual(rules.unauthorised_changes(carton(), carton(ctn_length_mm=410), self.REP), [])

	def test_rep_may_not_change_status_after_submit(self):
		out = rules.unauthorised_changes(carton(), carton(status="Discontinued"), self.REP)
		self.assertEqual([u.fieldname for u in out], ["status"])

	def test_manager_may_change_status(self):
		self.assertEqual(rules.unauthorised_changes(carton(), carton(status="Discontinued"), self.MGR), [])

	def test_nobody_but_server_writes_vcl_fields(self):
		out = rules.unauthorised_changes(carton(), carton(vcl_approval_state="Awaiting approval"), self.MGR)
		self.assertEqual(out[0].tier, rules.TIER_DERIVED)
		self.assertEqual(rules.unauthorised_changes(carton(), carton(vcl_approval_state="Awaiting approval"), self.MGR, is_server=True), [])

	def test_controller_derived_fields_are_not_refused(self):
		# The controller recomputes these from the rep's inputs on every save.
		self.assertEqual(rules.unauthorised_changes(carton(), carton(number_of_colours=4, current_rate=9.5), self.REP), [])
		self.assertEqual(rules.field_tier("number_of_colours"), rules.TIER_DERIVED)

	def test_customer_fixed_after_first_order_even_for_manager(self):
		out = rules.unauthorised_changes(carton(), carton(customer="Beta"), self.MGR, first_order_placed=True)
		self.assertEqual([u.fieldname for u in out], ["customer"])
		self.assertEqual(rules.unauthorised_changes(carton(), carton(customer="Beta"), self.MGR), [])

	def test_product_type_is_identity_after_submit(self):
		out = rules.unauthorised_changes(carton(), carton(product_type="Label"), self.MGR)
		self.assertEqual(out[0].fieldname, "product_type")
		self.assertEqual(rules.unauthorised_changes(carton(docstatus=0), carton(docstatus=0, product_type="Label"), self.REP, submitted=False), [])

	def test_rep_may_add_a_draft_price_row_but_not_approve_it(self):
		drafted = carton(pricing=[{"name": None, "rate": 10, "approval_status": "Draft"}])
		self.assertEqual(rules.unauthorised_changes(carton(), drafted, self.REP), [])
		approved = carton(pricing=[{"name": None, "rate": 10, "approval_status": "Approved"}])
		out = rules.unauthorised_changes(carton(), approved, self.REP)
		self.assertEqual([u.fieldname for u in out], ["pricing.approval_status"])

	def test_editing_an_existing_rows_approval_is_refused(self):
		before = carton(pricing=[{"name": "r1", "rate": 10, "approval_status": "Draft"}])
		after = carton(pricing=[{"name": "r1", "rate": 10, "approval_status": "Approved", "approved_by": "x"}])
		out = rules.unauthorised_changes(before, after, self.MGR)
		self.assertEqual(sorted(u.fieldname for u in out), ["pricing.approval_status", "pricing.approved_by"])

	def test_revocation_by_edit_is_allowed_for_a_rep(self):
		# Codex r5 (9): revoke_approval_on_edit writes Approved -> Draft with the
		# stamps cleared; that must not be refused as a server-owned change.
		before = carton(pricing=[{"name": "r1", "rate": 10, "approval_status": "Approved", "approved_by": "m", "approved_on": "t"}])
		after = carton(pricing=[{"name": "r1", "rate": 11, "approval_status": "Draft", "approved_by": None, "approved_on": None}])
		self.assertEqual(rules.unauthorised_changes(before, after, self.REP), [])
		# But Draft -> Approved, or keeping the stamps while changing terms, is refused.
		kept = carton(pricing=[{"name": "r1", "rate": 11, "approval_status": "Approved", "approved_by": "rep", "approved_on": "t"}])
		self.assertEqual([u.fieldname for u in rules.unauthorised_changes(before, kept, self.REP)], ["pricing.approved_by"])

	def test_iq_rows_are_server_only(self):
		# Codex r5 (2): a rep cannot label a row as the IQ transfer.
		row = {"name": None, "rate": 10, "approval_status": "Draft", "source": "Internal Quotation", "source_ref": "IQ-1"}
		out = rules.unauthorised_changes(carton(), carton(pricing=[row]), self.MGR)
		self.assertEqual([u.fieldname for u in out], ["pricing.source"])
		self.assertEqual(rules.unauthorised_changes(carton(), carton(pricing=[row]), self.MGR, is_server=True), [])
		before = carton(pricing=[{"name": "r1", "rate": 10, "approval_status": "Approved", "source": "Internal Quotation", "source_ref": "IQ-1"}])
		after = carton(pricing=[{"name": "r1", "rate": 10, "approval_status": "Approved", "source": "Internal Quotation", "source_ref": "IQ-2"}])
		self.assertEqual([u.fieldname for u in rules.unauthorised_changes(before, after, self.MGR)], ["pricing.source_ref"])

	def test_forged_initial_values_are_named_and_reset(self):
		# Codex r5 (1): a new CPS may not arrive pre-approved.
		doc = carton(vcl_approval_state="Approved", vcl_approved_rev=1, vcl_revision=1,
		             pricing=[{"rate": 10, "approval_status": "Approved", "approved_by": "x", "source": "Internal Quotation", "source_ref": "IQ-1"}])
		forged = rules.forged_initial_values(doc)
		for f in ("vcl_approval_state", "vcl_approved_rev", "vcl_revision", "pricing[0].approval_status", "pricing[0].approved_by", "pricing[0].source"):
			self.assertIn(f, forged)
		resets, rows = rules.initial_value_resets(doc)
		self.assertIsNone(resets["vcl_approval_state"])
		self.assertEqual(resets["vcl_revision"], 0)
		self.assertEqual(rows[0]["approval_status"], "Draft")
		self.assertIsNone(rows[0]["source"])
		clean = carton(vcl_revision=0, vcl_approved_rev=None, vcl_approval_state=None, pricing=[{"rate": 10, "approval_status": "Draft", "source": "LPO"}])
		self.assertEqual(rules.forged_initial_values(clean), [])

	def test_describe_lists_every_refusal(self):
		out = rules.unauthorised_changes(carton(), carton(status="Inactive", vcl_revision=5), self.REP)
		text = rules.describe_unauthorised(out)
		self.assertIn("status", text)
		self.assertIn("vcl_revision", text)

	def test_no_before_means_nothing_to_refuse(self):
		self.assertEqual(rules.unauthorised_changes(None, carton(), ()), [])

	def test_status_change_allowed(self):
		self.assertTrue(rules.status_change_allowed(self.MGR))
		self.assertFalse(rules.status_change_allowed(self.REP))
		self.assertTrue(rules.status_change_allowed(self.REP, is_server=True))


if __name__ == "__main__":
	unittest.main()
