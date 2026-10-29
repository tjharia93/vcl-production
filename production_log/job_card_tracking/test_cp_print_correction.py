"""Unit tests for the D5 print-field correction plan (TRK-00350). Plain unittest, no bench."""

import unittest

from production_log.job_card_tracking import cp_print as p  # noqa: F401  (kept for parity with test_cp_print)


class CorrectionPlan(unittest.TestCase):
	from production_log.job_card_tracking import cp_print_correction as cc

	SPECS = {
		"S-PRINTED": {"print_type": "Printed", "print_side": "Front Only", "printed_weight": 0.3},
		"S-PLAIN": {"print_type": "Plain", "print_side": "N/A", "printed_weight": 0},
		"S-PRINTED-NOSIDE": {"print_type": "Printed", "print_side": "N/A", "printed_weight": 0},
	}

	def card(self, name, **kw):
		base = {"name": name, "docstatus": 1, "print_type": "Plain", "print_side": "N/A",
		        "printed_weight": 0, "customer_product_spec": "S-PRINTED"}
		base.update(kw)
		return base

	def test_plain_card_on_printed_spec_is_corrected_from_the_spec(self):
		changes, _ = self.cc.plan_corrections([self.card("JC-1")], self.SPECS)
		self.assertEqual(len(changes), 1)
		self.assertEqual(changes[0]["kind"], "type")
		self.assertEqual(changes[0]["to"], {"print_type": "Printed", "print_side": "Front Only", "printed_weight": 0.3})

	def test_zero_spec_weight_keeps_the_card_weight(self):
		changes, _ = self.cc.plan_corrections(
			[self.card("JC-1", printed_weight=4.31, customer_product_spec="S-PRINTED-NOSIDE")], self.SPECS)
		self.assertEqual(changes[0]["to"]["printed_weight"], 4.31)

	def test_printed_card_with_blank_side_gets_the_spec_side_only(self):
		changes, _ = self.cc.plan_corrections(
			[self.card("JC-1", print_type="Printed", print_side="N/A")], self.SPECS)
		self.assertEqual(changes[0]["kind"], "side")
		self.assertEqual(changes[0]["to"], {"print_side": "Front Only"})

	def test_printed_card_with_a_side_is_left_alone(self):
		changes, _ = self.cc.plan_corrections(
			[self.card("JC-1", print_type="Printed", print_side="Front and Back")], self.SPECS)
		self.assertEqual(changes, [])

	def test_card_with_no_spec_or_plain_spec_is_left_alone(self):
		changes, _ = self.cc.plan_corrections(
			[self.card("JC-1", customer_product_spec=None), self.card("JC-2", customer_product_spec="S-PLAIN")],
			self.SPECS)
		self.assertEqual(changes, [])

	def test_cancelled_cards_are_reported_not_changed(self):
		changes, cancelled = self.cc.plan_corrections([self.card("JC-1", docstatus=2)], self.SPECS)
		self.assertEqual(changes, [])
		self.assertEqual(cancelled, ["JC-1"])

	def test_second_pass_is_empty(self):
		first, _ = self.cc.plan_corrections([self.card("JC-1")], self.SPECS)
		after = self.card("JC-1", print_type="Printed", print_side="Front Only", printed_weight=0.3)
		second, _ = self.cc.plan_corrections([after], self.SPECS)
		self.assertEqual(second, [])
		self.assertEqual(len(first), 1)

	def test_comment_text_names_the_spec_and_the_old_value(self):
		changes, _ = self.cc.plan_corrections([self.card("JC-1")], self.SPECS)
		self.assertEqual(self.cc.comment_text(changes[0]), "Print type corrected from S-PRINTED (was Plain/N/A)")


if __name__ == "__main__":
	unittest.main()
