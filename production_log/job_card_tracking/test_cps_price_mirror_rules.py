"""Frappe-free tests for the CPS -> price list mirror rules.

Run without a bench::

	python3 -m unittest production_log.job_card_tracking.test_cps_price_mirror_rules

The two live cases from the 2026-09-12 decision record are reproduced verbatim
below, because they are the two branches of the whole rule and they are real:
National Printing Press mirrors, Novel Manufacturing refuses.
"""

import unittest

from production_log.job_card_tracking import cps_price_mirror_rules as m

NPP = "NATIONAL PRINTING PRESS"
NOVEL = "NOVEL MANUFACTURING CO LTD"
CP_ITEM = "Computer Paper Pre-Printed-9.5x11x5.5-2 Part"
CTN_ITEM = "3PLY PRINTED CARTON"


def spec(cps, customer, item_code, uom, rate, valid_from="2026-08-31"):
	return {
		"cps": cps, "customer": customer, "item_code": item_code,
		"uom": uom, "rate": rate, "valid_from": valid_from,
	}


class TestPlanMirror(unittest.TestCase):
	def test_national_printing_press_mirrors(self):
		"""Two specs, one key, same rate — the price list can say this."""
		plan = m.plan_mirror([
			spec("CPT-SPEC-00072", NPP, CP_ITEM, "Carton", 4000, "2026-08-31"),
			spec("CPT-SPEC-00073", NPP, CP_ITEM, "Carton", 4000, "2026-08-31"),
		])
		self.assertEqual(plan.refusals, [])
		self.assertEqual(len(plan.targets), 1)
		t = plan.targets[0]
		self.assertEqual(t.key, m.MirrorKey(NPP, CP_ITEM, "Carton"))
		self.assertEqual(t.rate, 4000)
		# Both specs are named, so the row can say where the agreement came from.
		self.assertEqual(t.agreeing, ["CPT-SPEC-00072", "CPT-SPEC-00073"])

	def test_novel_manufacturing_refuses(self):
		"""Same key, two rates — no Item Price row can be true for both."""
		plan = m.plan_mirror([
			spec("CTN-SPEC-00026", NOVEL, CTN_ITEM, "Nos", 50.0),
			spec("CTN-SPEC-00027", NOVEL, CTN_ITEM, "Nos", 60.0),
		])
		self.assertEqual(plan.targets, [])
		self.assertEqual(len(plan.refusals), 1)
		r = plan.refusals[0]
		self.assertEqual(r.key, m.MirrorKey(NOVEL, CTN_ITEM, "Nos"))
		self.assertEqual(r.rates, [("CTN-SPEC-00026", 50.0), ("CTN-SPEC-00027", 60.0)])

	def test_one_customers_clash_does_not_block_another(self):
		"""A refusal is scoped to its key, never to the item or the run."""
		plan = m.plan_mirror([
			spec("CTN-SPEC-00026", NOVEL, CTN_ITEM, "Nos", 50.0),
			spec("CTN-SPEC-00027", NOVEL, CTN_ITEM, "Nos", 60.0),
			spec("CTN-SPEC-00019", "VAJAS MANUFACTURERS LTD", CTN_ITEM, "Nos", 134.0),
		])
		self.assertEqual(len(plan.refusals), 1)
		self.assertEqual(len(plan.targets), 1)
		self.assertEqual(plan.targets[0].key.customer, "VAJAS MANUFACTURERS LTD")

	def test_same_item_different_uom_is_a_different_key(self):
		"""UOM is part of the key because Item Price's uniqueness includes it."""
		plan = m.plan_mirror([
			spec("A", NPP, CP_ITEM, "Carton", 4000),
			spec("B", NPP, CP_ITEM, "Nos", 8.89),
		])
		self.assertEqual(plan.refusals, [])
		self.assertEqual(len(plan.targets), 2)

	def test_newest_effective_date_supplies_the_rate(self):
		"""Agreement still has to name ONE source, and it must be repeatable."""
		plan = m.plan_mirror([
			spec("CPT-SPEC-00072", NPP, CP_ITEM, "Carton", 4000, "2026-08-31"),
			spec("CPT-SPEC-00073", NPP, CP_ITEM, "Carton", 4000, "2026-09-03"),
		])
		self.assertEqual(plan.targets[0].cps, "CPT-SPEC-00073")

	def test_rates_agree_at_nine_dp(self):
		"""Rates round-trip at 9 dp; agreement is tested at that precision."""
		plan = m.plan_mirror([
			spec("A", NPP, CP_ITEM, "Nos", 5.172413793),
			spec("B", NPP, CP_ITEM, "Nos", 5.1724137930000001),
		])
		self.assertEqual(plan.refusals, [])

	def test_spec_missing_part_of_its_key_is_counted_not_dropped(self):
		plan = m.plan_mirror([
			spec("A", NPP, CP_ITEM, "Carton", 4000),
			spec("B", NPP, None, "Carton", 4000),      # no linked item
			spec("C", NPP, CP_ITEM, "Carton", None),   # no rate
		], unmappable=7)
		self.assertEqual(len(plan.targets), 1)
		self.assertEqual(plan.unmappable, 9)

	def test_empty_input_is_an_empty_plan(self):
		plan = m.plan_mirror([])
		self.assertEqual((plan.targets, plan.refusals, plan.unmappable), ([], [], 0))


class TestVatBasis(unittest.TestCase):
	"""CPS Price is labelled "Rate (net, ex-VAT)" and one live row is not.

	BAHATI's coffee cup sleeve is agreed at 1.70 INCLUSIVE and the Sales Order is
	raised at 1.70 with VAT included in the print rate, because the ex-VAT 1.4655
	rounded to 1.47 on submit and billed 73,500 instead of 85,000. The gross rate
	has to stay on the spec; the price list still has to receive the net one.
	"""

	def test_a_net_rate_passes_through(self):
		self.assertEqual(m.to_ex_vat(4000, 0), 4000)

	def test_none_stays_none(self):
		self.assertIsNone(m.to_ex_vat(None, 1))

	def test_bahati_gross_converts_to_the_invoiced_net(self):
		self.assertAlmostEqual(m.to_ex_vat(1.70, 1), 1.4655, places=4)

	def test_conversion_survives_the_round_trip(self):
		self.assertAlmostEqual(m.to_ex_vat(1.70, 1) * 1.16, 1.70, places=9)

	def test_plan_converts_and_records_the_gross(self):
		plan = m.plan_mirror([
			dict(spec("CTN-SPEC-00025-1", "BAHATI VENTURES LTD",
			          "Coffee Cup Sleeve - E Flute Plain", "Nos", 1.70),
			     vat_inclusive=1),
		])
		t = plan.targets[0]
		self.assertAlmostEqual(t.rate, 1.4655, places=4)
		# The original is kept so the price-list note can explain the number.
		self.assertEqual(t.gross, 1.70)

	def test_an_unflagged_rate_records_no_gross(self):
		plan = m.plan_mirror([spec("A", NPP, CP_ITEM, "Carton", 4000)])
		self.assertIsNone(plan.targets[0].gross)

	def test_gross_and_net_specs_agreeing_after_conversion_do_not_refuse(self):
		"""One spec quoting 1.16 gross and another quoting the same net is ONE
		price, and the price list should carry it rather than refuse."""
		plan = m.plan_mirror([
			dict(spec("GROSS", NPP, CP_ITEM, "Nos", 4640.0), vat_inclusive=1),
			spec("NET", NPP, CP_ITEM, "Nos", 4000.0),
		])
		self.assertEqual(plan.refusals, [])
		self.assertEqual(plan.targets[0].rate, 4000)


class TestDecideWrite(unittest.TestCase):
	def test_no_existing_row_inserts(self):
		d = m.decide_write(4000, None)
		self.assertEqual(d.action, m.ACTION_INSERT)
		self.assertIsNone(d.supersedes)

	def test_matching_owned_row_is_left_alone(self):
		d = m.decide_write(4000, {"name": "ip1", "price_list_rate": 4000, "cps": "CPT-SPEC-00072"})
		self.assertEqual(d.action, m.ACTION_UNCHANGED)

	def test_changed_owned_row_is_superseded_not_overwritten(self):
		d = m.decide_write(4200, {"name": "ip1", "price_list_rate": 4000, "cps": "CPT-SPEC-00072"})
		self.assertEqual(d.action, m.ACTION_SUPERSEDE)
		self.assertEqual(d.supersedes, "ip1")

	def test_a_hand_made_row_is_never_touched(self):
		"""The twelve rows that predate the mirror, and the three set from
		invoices on 2026-09-11, carry no CPS. They stay exactly as they are."""
		d = m.decide_write(4200, {"name": "ip1", "price_list_rate": 4000, "cps": None})
		self.assertEqual(d.action, m.ACTION_SKIP_UNOWNED)

	def test_ownership_is_checked_before_equality(self):
		"""An unowned row that happens to match is still reported as unowned,
		so the dry run never implies the mirror is managing it."""
		d = m.decide_write(4000, {"name": "ip1", "price_list_rate": 4000, "cps": ""})
		self.assertEqual(d.action, m.ACTION_SKIP_UNOWNED)


class TestWithdrawals(unittest.TestCase):
	def test_owned_row_with_no_live_price_is_withdrawn(self):
		rows = [{"name": "ip1", "customer": NPP, "item_code": CP_ITEM, "uom": "Carton"}]
		self.assertEqual(m.plan_withdrawals(rows, []), rows)

	def test_owned_row_still_priced_is_kept(self):
		rows = [{"name": "ip1", "customer": NPP, "item_code": CP_ITEM, "uom": "Carton"}]
		live = [m.MirrorKey(NPP, CP_ITEM, "Carton")]
		self.assertEqual(m.plan_withdrawals(rows, live), [])

	def test_a_refused_key_withdraws_a_previously_mirrored_row(self):
		"""If two specs diverge after one was mirrored, the stale row must go —
		leaving it standing is exactly the lie the refusal exists to prevent."""
		rows = [{"name": "ip1", "customer": NOVEL, "item_code": CTN_ITEM, "uom": "Nos"}]
		plan = m.plan_mirror([
			spec("CTN-SPEC-00026", NOVEL, CTN_ITEM, "Nos", 50.0),
			spec("CTN-SPEC-00027", NOVEL, CTN_ITEM, "Nos", 60.0),
		])
		self.assertEqual(m.plan_withdrawals(rows, [t.key for t in plan.targets]), rows)


class TestRefusalDigest(unittest.TestCase):
	def test_digest_is_stable_across_input_order(self):
		a = m.plan_mirror([
			spec("CTN-SPEC-00026", NOVEL, CTN_ITEM, "Nos", 50.0),
			spec("CTN-SPEC-00027", NOVEL, CTN_ITEM, "Nos", 60.0),
		])
		b = m.plan_mirror([
			spec("CTN-SPEC-00027", NOVEL, CTN_ITEM, "Nos", 60.0),
			spec("CTN-SPEC-00026", NOVEL, CTN_ITEM, "Nos", 50.0),
		])
		self.assertEqual(m.refusal_digest(a.refusals), m.refusal_digest(b.refusals))

	def test_digest_moves_when_a_rate_moves(self):
		a = m.plan_mirror([
			spec("X", NOVEL, CTN_ITEM, "Nos", 50.0),
			spec("Y", NOVEL, CTN_ITEM, "Nos", 60.0),
		])
		b = m.plan_mirror([
			spec("X", NOVEL, CTN_ITEM, "Nos", 50.0),
			spec("Y", NOVEL, CTN_ITEM, "Nos", 65.0),
		])
		self.assertNotEqual(m.refusal_digest(a.refusals), m.refusal_digest(b.refusals))

	def test_no_refusals_is_an_empty_digest(self):
		self.assertEqual(m.refusal_digest([]), "")


if __name__ == "__main__":
	unittest.main()
