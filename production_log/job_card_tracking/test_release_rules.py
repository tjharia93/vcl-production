"""Unit tests for the eleven release checks (§7). Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import cps_lifecycle_rules, cps_rules, release_rules as rules


def spec(**kw):
	base = {
		"name": "CTN-SPEC-00001", "docstatus": 1, "status": "Active", "product_type": "Carton",
		"customer": "ACME Ltd", "linked_item": "3 PLY PRINTED CARTON",
		"vcl_revision": 1, "vcl_approved_rev": 1, "vcl_approval_state": "Approved",
		"product_type_carton": "1 Flap RSC", "ply": "3", "flute_type": "B",
		"ctn_length_mm": 400, "ctn_width_mm": 300, "ctn_height_mm": 200, "joint_type": "Gluing - Machine", "idod": "ID",
		"1_ply_top_layer_gsm": 150, "1_ply_top_layer_material": "Test Liner",
		"2_ply_fluting_gsm": 120, "2_ply_top_layer_material": "Test Liner",
		"3_ply_bottom_gsm": 150, "3_ply_top_layer_material": "Kraft",
		"print_type": "Printed", "number_of_colours": 2, "standard_packing": "20s", "standard_weight_per_carton": 12.5,
		"artwork_tracker": "DAT-0001", "artwork_not_ready": 0,
		"colour_of_parts": [], "spot_colours": [],
	}
	base.update(kw)
	return base


def ctx(**kw):
	s = kw.pop("spec", None) or spec()
	payload = cps_lifecycle_rules.build_revision_payload(s, s["vcl_revision"], "t", "u")
	base = {
		"order": {"docstatus": 1, "status": "To Deliver and Bill", "customer": "ACME Ltd", "transaction_date": "2026-11-01", "currency": "KES"},
		"line": {"name": "SOI-1", "custom_cps": "CTN-SPEC-00001", "qty": 1000, "rate": 42.0, "uom": "Nos", "conversion_factor": 1, "custom_cps_price_row": "row-1"},
		"other_cards_qty": 0,
		"card": {"quantity_ordered": 1000, "customer_product_spec": "CTN-SPEC-00001", "item_code": "3 PLY PRINTED CARTON",
		         "spec_snapshot": {"ctn_length_mm": 400, "ctn_width_mm": 300, "ply": "3"}, "customer_hold": 0, "artwork_approved": 0},
		"spec": s,
		"bound_revision": s["vcl_revision"],
		"bound_payload": payload,
		"item_control": cps_rules.ItemControl(True, "Carton", "inherited", "Packaging - Carton", "x"),
		"price_row": {"name": "row-1", "approval_status": "Approved", "valid_from": "2026-10-01", "rate": 42.0, "uom": "Nos", "currency": "KES", "conversion_factor": 1},
		"allowance": (1.0, 1.0),
		"artwork": {"state": None, "version": None},
		"stored_fingerprint": None,
	}
	base.update(kw)
	return base


def by_number(results):
	return {r.number: r for r in results}


class TestHappyPath(unittest.TestCase):
	def test_a_complete_carton_releases(self):
		results, fingerprint = rules.evaluate(ctx())
		self.assertEqual(len(results), 11)
		self.assertTrue(rules.all_required_pass(results), [r for r in results if not r.passed])
		self.assertEqual(rules.summary(results), rules.STATE_RELEASED)
		self.assertEqual(fingerprint["spec_revision"], 1)
		self.assertEqual(fingerprint["price_row"], "row-1")

	def test_first_evaluation_has_nothing_to_compare(self):
		results, _ = rules.evaluate(ctx(stored_fingerprint=None))
		self.assertTrue(by_number(results)[11].passed)


class TestCheck1(unittest.TestCase):
	def test_unsubmitted_closed_or_missing_line_fail_and_cannot_be_overridden(self):
		for c in (ctx(order={"docstatus": 0}), ctx(order=dict(ctx()["order"], status="Closed")), ctx(line=None)):
			results, _ = rules.evaluate(c)
			r = by_number(results)[1]
			self.assertFalse(r.passed)
			self.assertFalse(r.overridable)
			self.assertFalse(rules.can_override(results))

	def test_card_qty_above_remaining_fails(self):
		results, _ = rules.evaluate(ctx(other_cards_qty=400))
		self.assertFalse(by_number(results)[1].passed)
		results, _ = rules.evaluate(ctx(other_cards_qty=0))
		self.assertTrue(by_number(results)[1].passed)


class TestCheck2And3(unittest.TestCase):
	def test_wrong_spec_customer_item_or_type(self):
		c = ctx(); c["card"]["customer_product_spec"] = "CTN-SPEC-00002"
		self.assertFalse(by_number(rules.evaluate(c)[0])[2].passed)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(customer="Beta")))[0])[2].passed)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(linked_item="OTHER")))[0])[2].passed)
		c = ctx(item_control=cps_rules.ItemControl(True, "Label", "inherited", "g", "x"))
		self.assertFalse(by_number(rules.evaluate(c)[0])[2].passed)

	def test_only_active_submitted_specs_are_orderable(self):
		for status in ("Inactive", "Superseded", "Discontinued"):
			self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(status=status)))[0])[3].passed)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(docstatus=0)))[0])[3].passed)


class TestCheck4(unittest.TestCase):
	def test_missing_mandatory_field_fails(self):
		results, _ = rules.evaluate(ctx(spec=spec(ctn_height_mm=None)))
		r = by_number(results)[4]
		self.assertFalse(r.passed)
		self.assertIn("ctn_height_mm", r.message)

	def test_unused_plies_flap_and_spot_colours_never_block(self):
		s = spec(ply="3")  # 4th/5th ply blank, no flap, no spots
		self.assertTrue(by_number(rules.evaluate(ctx(spec=s))[0])[4].passed)

	def test_sfk_needs_no_flute(self):
		s = spec(ply="SFK", flute_type=None)
		c = ctx(spec=s); c["card"]["spec_snapshot"]["ply"] = "SFK"
		self.assertTrue(by_number(rules.evaluate(c)[0])[4].passed)

	def test_die_required_only_on_the_diecut_route(self):
		self.assertTrue(by_number(rules.evaluate(ctx(spec=spec(carton_applies_diecut=0)))[0])[4].passed)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(carton_applies_diecut=1)))[0])[4].passed)

	def test_snapshot_must_match_the_bound_revision(self):
		c = ctx(); c["card"]["spec_snapshot"] = {"ctn_length_mm": 410}
		r = by_number(rules.evaluate(c)[0])[4]
		self.assertFalse(r.passed)
		self.assertIn("ctn_length_mm", r.message)

	def test_card_bound_to_earlier_approved_revision_is_judged_against_it(self):
		# Codex r4 (1): spec moved to rev 2 (awaiting), card bound to approved rev 1.
		s = spec(vcl_revision=2, vcl_approved_rev=1, vcl_approval_state="Awaiting approval", ctn_length_mm=450)
		rev1 = cps_lifecycle_rules.build_revision_payload(spec(), 1, "t", "u")
		results, fp = rules.evaluate(ctx(spec=s, bound_revision=1, bound_payload=rev1))
		self.assertTrue(by_number(results)[4].passed)
		self.assertTrue(by_number(results)[8].passed)
		self.assertEqual(fp["spec_revision"], 1)
		self.assertEqual(fp["spec_current_revision"], 2)

	def test_computer_paper_needs_a_row_per_part(self):
		s = spec(product_type="Computer Paper", job_size="A4", number_of_parts=2, numbering_answer="No",
		         colour_of_parts=[{"part_number": 1, "paper_type": "Bond", "gsm": 60, "colour": "White", "purpose": ""}])
		c = ctx(spec=s, item_control=cps_rules.ItemControl(True, "Computer Paper", "inherited", "g", "x"))
		c["card"]["spec_snapshot"] = {}
		r = by_number(rules.evaluate(c)[0])[4]
		self.assertFalse(r.passed)
		self.assertIn("colour_of_parts", r.message)


class TestChecks5To7(unittest.TestCase):
	def test_print_type_and_colours(self):
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(print_type=None)))[0])[5].passed)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(number_of_colours=0)))[0])[5].passed)
		self.assertTrue(by_number(rules.evaluate(ctx(spec=spec(print_type="Plain", number_of_colours=0)))[0])[5].passed)

	def test_artwork_plain_passes_printed_needs_evidence(self):
		self.assertTrue(by_number(rules.evaluate(ctx(spec=spec(print_type="Plain", number_of_colours=0)))[0])[6].passed)
		bare = spec(artwork_tracker=None)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=bare))[0])[6].passed)
		self.assertTrue(by_number(rules.evaluate(ctx(spec=bare, artwork={"state": "Customer-approved", "version": "v1"}))[0])[6].passed)
		c = ctx(spec=bare); c["card"]["artwork_approved"] = 1
		self.assertTrue(by_number(rules.evaluate(c)[0])[6].passed)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=spec(artwork_not_ready=1)))[0])[6].passed)

	def test_packing_is_a_warning_not_a_block(self):
		results, _ = rules.evaluate(ctx(spec=spec(standard_packing=None)))
		r = by_number(results)[7]
		self.assertFalse(r.passed)
		self.assertFalse(r.required)
		self.assertTrue(rules.all_required_pass(results))
		self.assertEqual([w.number for w in rules.warnings(results)], [7])
		self.assertEqual(rules.summary(results), rules.STATE_RELEASED)


class TestChecks8To10(unittest.TestCase):
	def test_awaiting_approval_fails_8(self):
		s = spec(vcl_approval_state="Awaiting approval", vcl_approved_rev=0)
		self.assertFalse(by_number(rules.evaluate(ctx(spec=s))[0])[8].passed)

	def test_price_row_rules(self):
		self.assertFalse(by_number(rules.evaluate(ctx(price_row=None))[0])[9].passed)
		row = dict(ctx()["price_row"], approval_status="Draft")
		self.assertFalse(by_number(rules.evaluate(ctx(price_row=row))[0])[9].passed)
		row = dict(ctx()["price_row"], valid_from="2026-12-01")
		self.assertFalse(by_number(rules.evaluate(ctx(price_row=row))[0])[9].passed)
		row = dict(ctx()["price_row"], currency="USD")
		self.assertFalse(by_number(rules.evaluate(ctx(price_row=row))[0])[9].passed)
		row = dict(ctx()["price_row"], uom="Carton", conversion_factor=None)
		self.assertFalse(by_number(rules.evaluate(ctx(price_row=row))[0])[9].passed)

	def test_rate_within_allowance(self):
		c = ctx(); c["line"]["rate"] = 42.4
		self.assertTrue(by_number(rules.evaluate(c)[0])[10].passed)
		c["line"]["rate"] = 43.5
		r = by_number(rules.evaluate(c)[0])[10]
		self.assertFalse(r.passed)
		self.assertIn("allowance", r.message)

	def test_zero_approved_rate_exact(self):
		row = dict(ctx()["price_row"], rate=0)
		c = ctx(price_row=row); c["line"]["rate"] = 0
		self.assertTrue(by_number(rules.evaluate(c)[0])[10].passed)
		c["line"]["rate"] = 0.5
		self.assertFalse(by_number(rules.evaluate(c)[0])[10].passed)


class TestCheck11(unittest.TestCase):
	def test_unchanged_inputs_pass(self):
		_, fp = rules.evaluate(ctx())
		results, _ = rules.evaluate(ctx(stored_fingerprint=fp))
		self.assertTrue(by_number(results)[11].passed)
		self.assertFalse(rules.is_stale(fp, fp))

	def test_changed_rate_or_revision_is_stale(self):
		_, fp = rules.evaluate(ctx())
		c = ctx(stored_fingerprint=fp); c["line"]["rate"] = 50
		results, new_fp = rules.evaluate(c)
		self.assertFalse(by_number(results)[11].passed)
		self.assertIn("rate", rules.fingerprint_changes(fp, new_fp))
		s = spec(vcl_revision=2, vcl_approval_state="Awaiting approval")
		_, fp2 = rules.evaluate(ctx(spec=s, bound_revision=1))
		self.assertIn("spec_current_revision", rules.fingerprint_changes(fp, fp2))

	def test_customer_hold_is_required_and_non_overridable(self):
		c = ctx(); c["card"]["customer_hold"] = 1
		results, _ = rules.evaluate(c)
		r = by_number(results)[11]
		self.assertFalse(r.passed)
		self.assertFalse(r.overridable)
		self.assertFalse(rules.can_override(results))


class TestOverrideAndIssuance(unittest.TestCase):
	def failing_results(self):
		return rules.evaluate(ctx(price_row=None))[0]

	def test_override_needs_management_reason_and_not_owner(self):
		results = self.failing_results()
		self.assertIsNone(rules.override_refusal(results, ["VCL Management Team"], "tanuj", ["rep"], "LPO confirms"))
		self.assertIn("role", rules.override_refusal(results, ["Sales Master Manager"], "x", [], "r"))
		self.assertIn("owner", rules.override_refusal(results, ["VCL Management Team"], "rep", ["rep"], "r"))
		self.assertIn("reason", rules.override_refusal(results, ["VCL Management Team"], "t", [], " "))
		self.assertIn("nothing to override", rules.override_refusal(rules.evaluate(ctx())[0], ["VCL Management Team"], "t", [], "r"))
		self.assertIn("cannot be overridden", rules.override_refusal(rules.evaluate(ctx(line=None))[0], ["VCL Management Team"], "t", [], "r"))

	def test_failing_numbers_and_summary(self):
		results = self.failing_results()
		self.assertEqual(rules.failing_numbers(results), [9, 10])
		self.assertTrue(rules.summary(results).startswith("Held — check 9 failed"))

	def test_manual_hold_blocks_issuance_even_when_released(self):
		# Codex r4 (2).
		card = {"release_state": "Released", "job_status": "On Hold", "hold_reason": "Machine issue", "customer_hold": 0}
		self.assertIn("Machine issue", rules.issuance_block_reason(card, False))
		card = {"release_state": "Released", "job_status": "Open", "customer_hold": 1}
		self.assertEqual(rules.issuance_block_reason(card, False), "customer hold")
		card = {"release_state": "Released", "job_status": "On Hold", "hold_reason": "Awaiting release", "customer_hold": 0}
		self.assertIsNone(rules.issuance_block_reason(card, False))
		self.assertEqual(rules.issuance_block_reason(card, True), "inputs changed since release")
		self.assertIn("Held", rules.issuance_block_reason({"release_state": "Held"}, False))
		self.assertIn("superseded", rules.issuance_block_reason({"release_state": "Released", "print_superseded": 1}, False))

	def test_results_payload_is_json_shaped(self):
		import json
		json.dumps(rules.results_payload(self.failing_results()))


if __name__ == "__main__":
	unittest.main()
