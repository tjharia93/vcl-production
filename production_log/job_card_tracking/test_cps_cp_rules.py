"""Unit tests for the Computer Paper specification capture rules.

Plain ``unittest``, no bench, no site, no database — ``cps_cp_rules`` imports
nothing from Frappe, which is the whole reason it exists as its own module.

The live estate these rules have to survive, from the discovery run:

	59 Computer Paper specifications: 46 submitted, 10 cancelled, 3 draft
	50 Printed, 9 Plain
	21 of the Printed records record no CMYK and no spot ink at all
	all 9 Plain records DO carry ink data
	only 7 carry a linked_item

So the two shapes that must keep saving for unrelated reasons are "Printed with
no ink" and "Plain with ink", and there is a test for each.
"""

import unittest

from production_log.job_card_tracking import cps_cp_rules as r


def spec(**overrides):
	"""A Computer Paper specification as a plain dict."""
	base = {
		"name": "CPT-SPEC-00042",
		"product_type": r.COMPUTER_PAPER,
		"specification_name": "3 Part Delivery Note A4",
		"customer": "GREENSPOON LIMITED",
		"job_size": "241 x 279",
		"print_type": r.PRINT_TYPE_PRINTED,
		"print_side": "Front Only",
		"numbering_required": 0,
		"numbering_confirmed": 0,
		"uses_c": 0,
		"uses_m": 0,
		"uses_y": 0,
		"uses_k": 1,
		"spot_colours": [],
		"number_of_parts": 3,
		"colour_of_parts": [],
		"artwork": "/private/files/greenspoon-dn.pdf",
	}
	base.update(overrides)
	return base


def spot(code="PANTONE 485 C", **overrides):
	row = {
		"pantone_code": code,
		"pantone_name": "Red 485",
		"hex_preview": "#DA291C",
		"cmyk_c": 0,
		"cmyk_m": 95,
		"cmyk_y": 100,
		"cmyk_k": 0,
		"notes": "",
	}
	row.update(overrides)
	return row


def part(number, paper_type, gsm, colour="White", purpose=""):
	return {
		"part_number": number,
		"paper_type": paper_type,
		"gsm": gsm,
		"colour": colour,
		"purpose": purpose,
	}


# ---------------------------------------------------------------------------
# Reading stored values
# ---------------------------------------------------------------------------


class TestChecked(unittest.TestCase):
	def test_every_shape_frappe_can_hand_back(self):
		for value in (1, "1", True, 2, "yes"):
			self.assertTrue(r._checked(value), value)
		for value in (0, "0", "", None, False, "false", "False", "No"):
			self.assertFalse(r._checked(value), value)

	def test_string_zero_is_not_ticked(self):
		# The bug this function exists for: a JSON payload sends "0" and plain
		# truthiness reads it as ticked.
		self.assertFalse(r._checked("0"))


class TestIsComputerPaper(unittest.TestCase):
	def test_only_computer_paper(self):
		self.assertTrue(r.is_computer_paper(spec()))
		self.assertFalse(r.is_computer_paper(spec(product_type="Carton")))
		self.assertFalse(r.is_computer_paper(spec(product_type=None)))

	def test_whitespace_is_trimmed(self):
		self.assertTrue(r.is_computer_paper(spec(product_type="  Computer Paper  ")))


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------


class TestNumbering(unittest.TestCase):
	def test_new_record_must_confirm(self):
		reason = r.numbering_block_reason(None, spec(numbering_confirmed=0))
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_NUMBERING_UNCONFIRMED)

	def test_new_record_confirmed_no_passes(self):
		# The whole point: an explicit No is a complete answer.
		self.assertIsNone(
			r.numbering_block_reason(
				None, spec(numbering_required=0, numbering_confirmed=1)
			)
		)

	def test_new_record_confirmed_yes_passes(self):
		self.assertIsNone(
			r.numbering_block_reason(
				None, spec(numbering_required=1, numbering_confirmed=1)
			)
		)

	def test_legacy_record_saving_for_another_reason_is_untouched(self):
		before = spec(numbering_required=0, numbering_confirmed=0)
		after = spec(numbering_required=0, numbering_confirmed=0, job_size="241 x 305")
		self.assertIsNone(r.numbering_block_reason(before, after))

	def test_changing_the_answer_needs_confirmation(self):
		before = spec(numbering_required=0, numbering_confirmed=0)
		after = spec(numbering_required=1, numbering_confirmed=0)
		reason = r.numbering_block_reason(before, after)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_NUMBERING_UNCONFIRMED)
		self.assertIn("No", r.reason_text(reason))
		self.assertIn("Yes", r.reason_text(reason))

	def test_changing_the_answer_with_confirmation_passes(self):
		before = spec(numbering_required=0, numbering_confirmed=0)
		after = spec(numbering_required=1, numbering_confirmed=1)
		self.assertIsNone(r.numbering_block_reason(before, after))

	def test_confirmation_cannot_be_withdrawn(self):
		before = spec(numbering_required=1, numbering_confirmed=1)
		after = spec(numbering_required=1, numbering_confirmed=0)
		reason = r.numbering_block_reason(before, after)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_NUMBERING_UNCONFIRMABLE)

	def test_none_becoming_zero_is_not_a_change(self):
		# A column written for the first time is not somebody re-answering.
		before = spec(numbering_required=None, numbering_confirmed=0)
		after = spec(numbering_required=0, numbering_confirmed=0)
		self.assertFalse(r.numbering_changed(before, after))
		self.assertIsNone(r.numbering_block_reason(before, after))

	def test_other_product_types_are_not_asked(self):
		self.assertIsNone(
			r.numbering_block_reason(None, spec(product_type="Carton", numbering_confirmed=0))
		)

	def test_range_notice_names_the_job_card(self):
		self.assertIn("Job Card", r.NUMBERING_RANGE_NOTICE)


# ---------------------------------------------------------------------------
# Print colour
# ---------------------------------------------------------------------------


class TestInkCounting(unittest.TestCase):
	def test_counts_ticks_and_rows(self):
		doc = spec(uses_c=1, uses_k=1, spot_colours=[spot(), spot("PANTONE 300 C")])
		self.assertEqual(r.cmyk_ticked(doc), ["uses_c", "uses_k"])
		self.assertEqual(r.ink_count(doc), 4)
		self.assertTrue(r.has_ink(doc))

	def test_no_ink_at_all(self):
		doc = spec(uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[])
		self.assertEqual(r.ink_count(doc), 0)
		self.assertFalse(r.has_ink(doc))

	def test_spot_only_counts_as_ink(self):
		doc = spec(uses_k=0, spot_colours=[spot()])
		self.assertTrue(r.has_ink(doc))


class TestColourTrigger(unittest.TestCase):
	def test_new_records_always_apply(self):
		self.assertTrue(r.colour_rules_apply(None, spec()))

	def test_unrelated_edit_does_not_apply(self):
		before = spec()
		after = spec(job_size="241 x 305", internal_notes="chased customer")
		self.assertFalse(r.colour_rules_apply(before, after))

	def test_colour_notes_alone_does_not_apply(self):
		# Deliberate: the nine live Plain records carrying legacy ink must be
		# able to have their notes corrected.
		before = spec(print_type=r.PRINT_TYPE_PLAIN, colour_notes="old")
		after = spec(print_type=r.PRINT_TYPE_PLAIN, colour_notes="corrected typo")
		self.assertFalse(r.colour_touched(before, after))

	def test_ink_type_alone_does_not_apply(self):
		before = spec(print_type=r.PRINT_TYPE_PLAIN, ink_type="Process Offset")
		after = spec(print_type=r.PRINT_TYPE_PLAIN, ink_type="Process UV")
		self.assertFalse(r.colour_touched(before, after))

	def test_ticking_an_ink_applies(self):
		self.assertTrue(r.colour_touched(spec(uses_c=0), spec(uses_c=1)))

	def test_changing_print_type_applies(self):
		self.assertTrue(
			r.colour_touched(
				spec(print_type=r.PRINT_TYPE_PLAIN), spec(print_type=r.PRINT_TYPE_PRINTED)
			)
		)

	def test_editing_a_spot_row_applies(self):
		before = spec(spot_colours=[spot()])
		after = spec(spot_colours=[spot(cmyk_m=90)])
		self.assertTrue(r.spot_rows_changed(before, after))
		self.assertTrue(r.colour_touched(before, after))

	def test_reordering_spot_rows_applies(self):
		a, b = spot("PANTONE 485 C"), spot("PANTONE 300 C")
		self.assertTrue(r.spot_rows_changed(spec(spot_colours=[a, b]), spec(spot_colours=[b, a])))

	def test_identical_spot_rows_do_not_apply(self):
		self.assertFalse(
			r.spot_rows_changed(spec(spot_colours=[spot()]), spec(spot_colours=[spot()]))
		)


class TestColourBlock(unittest.TestCase):
	def test_new_printed_with_no_ink_is_refused(self):
		doc = spec(print_type=r.PRINT_TYPE_PRINTED, uses_k=0, spot_colours=[])
		reason = r.colour_block_reason(None, doc)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PRINTED_NO_INK)
		# The message has to say the parts table is not a substitute — that
		# confusion is the reason the two blocks are being separated at all.
		self.assertIn("Colour of Parts", r.reason_text(reason))

	def test_new_printed_with_one_tick_passes(self):
		self.assertIsNone(r.colour_block_reason(None, spec(uses_k=1)))

	def test_new_printed_with_only_a_spot_passes(self):
		self.assertIsNone(
			r.colour_block_reason(None, spec(uses_k=0, spot_colours=[spot()]))
		)

	def test_new_plain_with_ink_is_refused(self):
		doc = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1)
		reason = r.colour_block_reason(None, doc)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PLAIN_HAS_INK)

	def test_new_plain_with_no_ink_passes(self):
		doc = spec(
			print_type=r.PRINT_TYPE_PLAIN, print_side="N/A",
			uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[],
		)
		self.assertIsNone(r.colour_block_reason(None, doc))

	def test_new_record_must_say_which_kind_of_job_it_is(self):
		reason = r.colour_block_reason(None, spec(print_type=None))
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PRINT_TYPE_MISSING)

	def test_unrecognised_print_type_is_named_not_assumed(self):
		reason = r.colour_block_reason(None, spec(print_type="Litho"))
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PRINT_TYPE_UNKNOWN)
		self.assertIn("Litho", r.reason_text(reason))

	# --- the two legacy shapes, which must keep saving ---------------------

	def test_legacy_printed_with_no_ink_saves_unrelated_edits(self):
		# 21 of the 50 live Printed records are this shape.
		before = spec(print_type=r.PRINT_TYPE_PRINTED, uses_k=0, spot_colours=[])
		after = spec(
			print_type=r.PRINT_TYPE_PRINTED, uses_k=0, spot_colours=[],
			standard_packing="500 sets / carton",
		)
		self.assertIsNone(r.colour_block_reason(before, after))

	def test_legacy_plain_with_ink_saves_unrelated_edits(self):
		# All 9 live Plain records are this shape.
		before = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1)
		after = spec(
			print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1,
			internal_notes="customer confirmed pack size",
		)
		self.assertIsNone(r.colour_block_reason(before, after))

	def test_legacy_plain_with_ink_is_refused_once_colour_is_touched(self):
		before = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1)
		after = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1, uses_c=1)
		reason = r.colour_block_reason(before, after)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PLAIN_HAS_INK)

	def test_legacy_printed_with_no_ink_is_refused_once_retyped_as_plain(self):
		# Retyping is itself touching the colour, so the record has to be made
		# consistent on the way through.
		before = spec(print_type=r.PRINT_TYPE_PRINTED, uses_k=1)
		after = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1)
		reason = r.colour_block_reason(before, after)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PLAIN_HAS_INK)

	def test_cleaning_a_legacy_plain_record_up_passes(self):
		before = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="N/A", uses_k=1)
		after = spec(
			print_type=r.PRINT_TYPE_PLAIN, print_side="N/A",
			uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[],
		)
		self.assertIsNone(r.colour_block_reason(before, after))

	def test_other_product_types_are_not_asked(self):
		doc = spec(product_type="Carton", print_type=r.PRINT_TYPE_PRINTED, uses_k=0, spot_colours=[])
		self.assertIsNone(r.colour_block_reason(None, doc))


class TestPrintSide(unittest.TestCase):
	def test_plain_with_a_printed_side_is_refused_on_a_new_record(self):
		doc = spec(
			print_type=r.PRINT_TYPE_PLAIN, print_side="Front Only",
			uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[],
		)
		reason = r.print_side_block_reason(None, doc)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PRINT_SIDE_ON_PLAIN)

	def test_plain_with_na_or_blank_passes(self):
		for side in ("N/A", "", None):
			doc = spec(
				print_type=r.PRINT_TYPE_PLAIN, print_side=side,
				uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[],
			)
			self.assertIsNone(r.print_side_block_reason(None, doc), side)

	def test_printed_keeps_its_side(self):
		self.assertIsNone(r.print_side_block_reason(None, spec(print_side="Front and Back")))

	def test_legacy_plain_with_a_stale_side_saves_unrelated_edits(self):
		before = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="Front Only", uses_k=0,
		              spot_colours=[])
		after = spec(print_type=r.PRINT_TYPE_PLAIN, print_side="Front Only", uses_k=0,
		             spot_colours=[], job_size="241 x 305")
		self.assertIsNone(r.print_side_block_reason(before, after))


class TestItemPrintTypeMismatch(unittest.TestCase):
	def test_plain_print_type_on_a_pre_printed_item_is_refused_on_a_new_record(self):
		doc = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item="Computer Paper Pre-Printed-9.5 x 8-2 Part",
		           uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[])
		reason = r.item_print_type_mismatch_reason(None, doc, r.ITEM_GROUP_PRE_PRINTED)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_ITEM_PRINT_TYPE_MISMATCH)

	def test_printed_print_type_on_a_plain_item_is_refused(self):
		doc = spec(print_type=r.PRINT_TYPE_PRINTED, linked_item="Computer Paper Plain")
		reason = r.item_print_type_mismatch_reason(None, doc, r.ITEM_GROUP_PLAIN)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_ITEM_PRINT_TYPE_MISMATCH)

	def test_matching_item_and_print_type_passes(self):
		doc = spec(print_type=r.PRINT_TYPE_PRINTED, linked_item="Computer Paper Pre-Printed-9.5 x 8-2 Part")
		self.assertIsNone(r.item_print_type_mismatch_reason(None, doc, r.ITEM_GROUP_PRE_PRINTED))

	def test_no_item_group_is_silent(self):
		# Nothing linked, or the caller has not looked it up - either way this
		# rule has no opinion rather than a spurious refusal.
		doc = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item=None,
		           uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[])
		self.assertIsNone(r.item_print_type_mismatch_reason(None, doc, None))

	def test_computer_paper_other_is_silent(self):
		# A third group that says nothing about which print type the job is.
		doc = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item="Computer Paper Other-Foo",
		           uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[])
		self.assertIsNone(r.item_print_type_mismatch_reason(None, doc, "Computer Paper Other"))

	def test_legacy_mismatch_saves_for_an_unrelated_edit(self):
		# Neither Print Type nor the Item link moved, so an old mismatch stays
		# untouched by a save about something else - CPT-SPEC-00053's own shape
		# before it was corrected.
		before = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item="Computer Paper Pre-Printed-9.5x11x5.5-2 Part",
		              job_size="241 x 279")
		after = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item="Computer Paper Pre-Printed-9.5x11x5.5-2 Part",
		             job_size="9.5 x 11")
		self.assertIsNone(r.item_print_type_mismatch_reason(before, after, r.ITEM_GROUP_PRE_PRINTED))

	def test_changing_print_type_under_an_unchanged_mismatched_item_is_caught(self):
		# The Item was already "Computer Paper Plain"; moving Print Type onto
		# Printed is the deliberate act that creates the mismatch, so it must be
		# caught even though the Item itself did not change this save.
		before = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item="Computer Paper Plain")
		after = spec(print_type=r.PRINT_TYPE_PRINTED, linked_item="Computer Paper Plain")
		reason = r.item_print_type_mismatch_reason(before, after, r.ITEM_GROUP_PLAIN)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_ITEM_PRINT_TYPE_MISMATCH)

	def test_swapping_the_item_under_an_unchanged_print_type_is_caught(self):
		before = spec(print_type=r.PRINT_TYPE_PRINTED, linked_item="Computer Paper Pre-Printed-9.5 x 8-2 Part")
		after = spec(print_type=r.PRINT_TYPE_PRINTED, linked_item="Computer Paper Plain")
		reason = r.item_print_type_mismatch_reason(before, after, r.ITEM_GROUP_PLAIN)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_ITEM_PRINT_TYPE_MISMATCH)


class TestPaperTypeAttribute(unittest.TestCase):
	def test_the_three_coating_types_map_to_attribute_values(self):
		self.assertEqual(r.paper_type_attribute("CB"), "Coated Back")
		self.assertEqual(r.paper_type_attribute("CF"), "Coated Front")
		self.assertEqual(r.paper_type_attribute("CFB"), "Coated Front and Back")

	def test_bond_does_not_map(self):
		# Bond is deferred to v2: bought by Ream, and BOND 70 GSM carries no
		# attributes at all, so there is nothing for the resolver to match on.
		self.assertIsNone(r.paper_type_attribute("60 GSM Bond"))
		self.assertIsNone(r.paper_type_attribute("70 GSM Bond"))

	def test_unknown_and_blank_return_none_rather_than_guessing(self):
		for value in ("Litho", "", None, "cb"):
			self.assertIsNone(r.paper_type_attribute(value), value)


class TestReelWidthFor(unittest.TestCase):
	WIDTHS = [250, 625, 750]

	def test_the_9_5_inch_anchor(self):
		# 9.5in = 241.3mm, run on a 250mm reel: 8.7mm of trim.
		self.assertEqual(r.reel_width_for(241.3, self.WIDTHS), 250)

	def test_11_7_inch_finds_nothing_rather_than_matching_a_jumbo(self):
		# 297.18mm. 625 fits "wider than" but is 328mm too wide - it is a jumbo
		# nobody slits for this job. Deferred to v2; must refuse, not guess.
		self.assertIsNone(r.reel_width_for(297.18, self.WIDTHS))

	def test_narrowest_wins_when_several_fit(self):
		self.assertEqual(r.reel_width_for(241.3, [250, 260, 270]), 250)

	def test_exact_fit_is_accepted(self):
		self.assertEqual(r.reel_width_for(250, self.WIDTHS), 250)

	def test_tolerance_boundary(self):
		# Exactly 25mm over is in; a hair more is out.
		self.assertEqual(r.reel_width_for(225, [250]), 250)
		self.assertIsNone(r.reel_width_for(224.9, [250]))

	def test_no_widths_or_no_size_returns_none(self):
		self.assertIsNone(r.reel_width_for(241.3, []))
		self.assertIsNone(r.reel_width_for(0, self.WIDTHS))
		self.assertIsNone(r.reel_width_for(None, self.WIDTHS))


class TestPartQuantities(unittest.TestCase):
	def test_the_gilanis_anchor(self):
		# CPT-SPEC-00063: 5.39 g/set x 500 sets = 2,695 g, split 55/55.
		# Reproduces the 1.3475 kg lines built by hand on 2026-08-08.
		parts = [part(1, "CB", 55), part(2, "CF", 55)]
		qtys = r.part_quantities(5.39, 500, parts)
		self.assertEqual(qtys, [1.3475, 1.3475])
		self.assertAlmostEqual(sum(qtys), 2.695, places=4)

	def test_a_four_part_set_splits_by_gsm_not_evenly(self):
		# CPT-SPEC-00065: 55/50/50/55 = 210 total, 14.16 g/set x 500 sets.
		parts = [part(1, "CB", 55), part(2, "CFB", 50),
		         part(3, "CFB", 50), part(4, "CF", 55)]
		qtys = r.part_quantities(14.16, 500, parts)
		self.assertAlmostEqual(sum(qtys), 7.08, places=2)
		# The 50gsm plies draw less than the 55gsm ones.
		self.assertGreater(qtys[0], qtys[1])
		self.assertEqual(qtys[0], qtys[3])
		self.assertEqual(qtys[1], qtys[2])

	def test_incomplete_inputs_give_nothing_rather_than_zeros(self):
		parts = [part(1, "CB", 55), part(2, "CF", 55)]
		self.assertEqual(r.part_quantities(0, 500, parts), [])
		self.assertEqual(r.part_quantities(5.39, 0, parts), [])
		self.assertEqual(r.part_quantities(None, 500, parts), [])
		self.assertEqual(r.part_quantities(5.39, 500, []), [])

	def test_parts_with_no_gsm_give_nothing(self):
		# Dividing by a zero total would raise; refuse instead.
		self.assertEqual(r.part_quantities(5.39, 500, [part(1, "CB", 0)]), [])


class TestSaveBlockOrdering(unittest.TestCase):
	def test_print_type_is_reported_before_numbering(self):
		# Neither ink rule means anything until the record says which kind of job
		# it is, so that question comes first.
		doc = spec(print_type=None, numbering_confirmed=0)
		reason = r.save_block_reason(None, doc)
		self.assertEqual(reason.code, r.BLOCK_PRINT_TYPE_MISSING)

	def test_numbering_is_reported_once_the_colours_are_sound(self):
		doc = spec(numbering_confirmed=0)
		reason = r.save_block_reason(None, doc)
		self.assertEqual(reason.code, r.BLOCK_NUMBERING_UNCONFIRMED)

	def test_a_complete_new_record_passes(self):
		doc = spec(numbering_confirmed=1, numbering_required=0)
		self.assertIsNone(r.save_block_reason(None, doc))

	def test_non_computer_paper_is_never_blocked(self):
		self.assertIsNone(r.save_block_reason(None, spec(product_type="Label", print_type=None)))

	def test_numbering_is_skipped_where_the_column_has_not_landed(self):
		# The window between a deploy and its migrate. Demanding a confirmation
		# with nowhere to record it would refuse every new record with an error
		# nobody could clear.
		doc = spec(numbering_confirmed=0)
		self.assertIsNotNone(r.save_block_reason(None, doc))
		self.assertIsNone(r.save_block_reason(None, doc, numbering_available=False))

	def test_the_colour_rules_still_bite_without_that_column(self):
		# They read only fields that already existed, so nothing about them is
		# conditional on the migration.
		doc = spec(numbering_confirmed=0, uses_k=0, spot_colours=[])
		reason = r.save_block_reason(None, doc, numbering_available=False)
		self.assertIsNotNone(reason)
		self.assertEqual(reason.code, r.BLOCK_PRINTED_NO_INK)

	def test_item_mismatch_is_reported_after_colour_but_before_numbering(self):
		# CPT-SPEC-00053's own shape: Plain with no ink (colour rules pass) but
		# linked to a Pre-Printed Item, and Numbering also unanswered. The Item
		# question is the one worth fixing first.
		doc = spec(print_type=r.PRINT_TYPE_PLAIN, linked_item="Computer Paper Pre-Printed-9.5x11x5.5-2 Part",
		           uses_c=0, uses_m=0, uses_y=0, uses_k=0, spot_colours=[], numbering_confirmed=0)
		reason = r.save_block_reason(None, doc, linked_item_group=r.ITEM_GROUP_PRE_PRINTED)
		self.assertEqual(reason.code, r.BLOCK_ITEM_PRINT_TYPE_MISMATCH)

	def test_no_linked_item_group_is_silent_by_default(self):
		# A caller that does not pass linked_item_group (every existing call
		# before this rule existed) gets exactly the old behaviour.
		doc = spec(numbering_confirmed=1, numbering_required=0, linked_item="Computer Paper Plain")
		self.assertIsNone(r.save_block_reason(None, doc))


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------


class TestPartPositions(unittest.TestCase):
	def test_single_part_offers_the_first_valid_option(self):
		self.assertEqual(r.part_positions(1), [("60 GSM Bond", 60)])

	def test_two_parts_are_cb_then_cf(self):
		self.assertEqual(r.part_positions(2), [("CB", 55), ("CF", 55)])

	def test_three_parts_insert_one_cfb(self):
		self.assertEqual(r.part_positions(3), [("CB", 55), ("CFB", 50), ("CF", 55)])

	def test_five_parts_insert_three_cfb(self):
		self.assertEqual(
			r.part_positions(5),
			[("CB", 55), ("CFB", 50), ("CFB", 50), ("CFB", 50), ("CF", 55)],
		)

	def test_zero_and_nonsense_produce_nothing(self):
		for value in (0, -1, None, "", "abc"):
			self.assertEqual(r.part_positions(value), [], value)

	def test_positions_agree_with_the_controllers_valid_options(self):
		# The controller's _validate_paper_type_and_gsm refuses anything else, so
		# a default that disagreed would be a form that cannot save its own
		# defaults.
		self.assertEqual(r.part_positions(1)[0], r.SINGLE_PART_OPTIONS[0])
		self.assertEqual(r.part_positions(4)[0], r.FIRST_PART)
		self.assertEqual(r.part_positions(4)[1], r.MIDDLE_PART)
		self.assertEqual(r.part_positions(4)[-1], r.LAST_PART)


class TestDefaultParts(unittest.TestCase):
	def test_rows_are_numbered_and_typed(self):
		rows = r.default_parts(3)
		self.assertEqual([row["part_number"] for row in rows], [1, 2, 3])
		self.assertEqual([row["paper_type"] for row in rows], ["CB", "CFB", "CF"])
		self.assertEqual([row["gsm"] for row in rows], [55, 50, 55])

	def test_every_row_gets_a_colour(self):
		for row in r.default_parts(4):
			self.assertTrue(row["colour"])

	def test_every_row_explains_itself(self):
		for row in r.default_parts(3):
			self.assertTrue(row["purpose"])

	def test_growing_a_set_keeps_the_colours_already_chosen(self):
		existing = [
			part(1, "CB", 55, colour="White"),
			part(2, "CFB", 50, colour="Customer Pink"),
			part(3, "CF", 55, colour="Customer Blue"),
		]
		rows = r.default_parts(4, existing)
		self.assertEqual(
			[row["colour"] for row in rows][:3], ["White", "Customer Pink", "Customer Blue"]
		)

	def test_growing_a_set_retypes_the_position_that_moved(self):
		# The third ply of a three-part set is CF; the third ply of a four-part
		# set is CFB. Carrying the paper type forward would be wrong.
		existing = [part(1, "CB", 55), part(2, "CFB", 50), part(3, "CF", 55)]
		rows = r.default_parts(4, existing)
		self.assertEqual(rows[2]["paper_type"], "CFB")
		self.assertEqual(rows[3]["paper_type"], "CF")

	def test_shrinking_a_set_drops_the_tail(self):
		existing = [part(i, "CB", 55, colour="C{0}".format(i)) for i in range(1, 6)]
		rows = r.default_parts(2, existing)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[-1]["paper_type"], "CF")


class TestPartRowErrors(unittest.TestCase):
	def test_a_valid_three_part_set_has_no_errors(self):
		rows = r.default_parts(3)
		self.assertEqual(r.part_row_errors(3, rows), [])

	def test_every_default_set_up_to_the_maximum_saves(self):
		# A default the server would refuse is a form that cannot save its own
		# suggestion. Asserted across the whole range rather than at one count,
		# because the failure only appears where the colour list runs out.
		for count in range(1, r.MAX_DEFAULT_PARTS + 1):
			self.assertEqual(r.part_row_errors(count, r.default_parts(count)), [], count)

	def test_missing_count_is_reported_alone(self):
		errors = r.part_row_errors(0, [])
		self.assertEqual(len(errors), 1)
		self.assertEqual(errors[0].code, "parts-count-missing")

	def test_row_count_mismatch(self):
		errors = r.part_row_errors(3, r.default_parts(2))
		codes = [e.code for e in errors]
		self.assertIn("parts-count-mismatch", codes)

	def test_every_problem_is_reported_not_only_the_first(self):
		rows = [
			part(1, "CB", 55, colour=""),
			part(2, "CFB", 50, colour=""),
			part(3, "CF", 55, colour=""),
		]
		errors = r.part_row_errors(3, rows)
		self.assertEqual(sum(1 for e in errors if e.code == "parts-colour-missing"), 3)

	def test_missing_colour_says_it_is_paper_not_ink(self):
		errors = r.part_row_errors(1, [part(1, "60 GSM Bond", 60, colour="")])
		text = " ".join(r.reason_text(e) for e in errors)
		self.assertIn("pre-tinted paper", text)

	def test_out_of_sequence_part_numbers(self):
		rows = [part(1, "CB", 55), part(3, "CFB", 50), part(3, "CF", 55)]
		codes = [e.code for e in r.part_row_errors(3, rows)]
		self.assertIn("parts-out-of-sequence", codes)

	def test_wrong_paper_for_the_position(self):
		rows = [part(1, "CF", 55), part(2, "CFB", 50), part(3, "CF", 55)]
		errors = [e for e in r.part_row_errors(3, rows) if e.code == "parts-paper-invalid"]
		self.assertEqual(len(errors), 1)
		self.assertIn("first part", r.reason_text(errors[0]))

	def test_wrong_gsm_for_the_right_paper(self):
		rows = [part(1, "CB", 60), part(2, "CFB", 50), part(3, "CF", 55)]
		codes = [e.code for e in r.part_row_errors(3, rows)]
		self.assertIn("parts-paper-invalid", codes)

	def test_all_three_single_part_options_are_accepted(self):
		for paper_type, gsm in r.SINGLE_PART_OPTIONS:
			self.assertEqual(r.part_row_errors(1, [part(1, paper_type, gsm)]), [], paper_type)


# ---------------------------------------------------------------------------
# Artwork
# ---------------------------------------------------------------------------


class TestArtworkExtension(unittest.TestCase):
	def test_reads_the_extension_lowercased(self):
		self.assertEqual(r.artwork_extension("Design.PDF"), ".pdf")
		self.assertEqual(r.artwork_extension("/private/files/a/b/art.TIFF"), ".tiff")

	def test_ignores_query_and_fragment(self):
		self.assertEqual(r.artwork_extension("/private/files/x.pdf?v=2"), ".pdf")
		self.assertEqual(r.artwork_extension("/private/files/x.pdf#page=3"), ".pdf")

	def test_no_extension(self):
		self.assertEqual(r.artwork_extension("README"), "")
		self.assertEqual(r.artwork_extension(""), "")
		self.assertEqual(r.artwork_extension(None), "")

	def test_a_dotted_directory_is_not_an_extension(self):
		self.assertEqual(r.artwork_extension("/private/v1.2/artwork"), "")


class TestArtworkUpload(unittest.TestCase):
	def test_accepts_the_allowlist(self):
		for extension in r.ARTWORK_EXTENSIONS:
			self.assertIsNone(r.artwork_upload_error("art" + extension, 1024), extension)

	def test_refuses_anything_else(self):
		for name in ("payload.exe", "macro.docm", "archive.zip", "script.svgz", "noext"):
			reason = r.artwork_upload_error(name, 1024)
			self.assertIsNotNone(reason, name)
			self.assertEqual(reason.code, r.BLOCK_ARTWORK_EXTENSION)

	def test_svg_is_not_artwork(self):
		# XML that a same-origin browser will parse, not an image. Nobody has ever
		# sent press artwork as one, so it buys nothing that would pay for that.
		self.assertNotIn(".svg", r.ARTWORK_EXTENSIONS)
		for name in ("logo.svg", "LOGO.SVG", "/private/files/brand/mark.svg"):
			reason = r.artwork_upload_error(name, 1024)
			self.assertIsNotNone(reason, name)
			self.assertEqual(reason.code, r.BLOCK_ARTWORK_EXTENSION)

	def test_the_allowlist_is_exactly_what_was_agreed(self):
		self.assertEqual(
			r.ARTWORK_EXTENSIONS,
			(".pdf", ".ai", ".eps", ".png", ".jpg", ".jpeg", ".tif", ".tiff"),
		)

	def test_refuses_an_empty_file(self):
		reason = r.artwork_upload_error("art.pdf", 0)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_EMPTY)

	def test_refuses_an_oversized_file(self):
		reason = r.artwork_upload_error("art.pdf", r.ARTWORK_MAX_BYTES + 1)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_TOO_LARGE)
		self.assertIn("25", r.reason_text(reason))

	def test_accepts_exactly_the_cap(self):
		self.assertIsNone(r.artwork_upload_error("art.pdf", r.ARTWORK_MAX_BYTES))

	def test_extension_is_checked_before_size(self):
		# A 400 MB .exe should be refused for being an .exe.
		reason = r.artwork_upload_error("payload.exe", 400 * 1024 * 1024)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_EXTENSION)


def file_row(**overrides):
	row = {
		"name": "abc123",
		"file_name": "greenspoon-dn.pdf",
		"file_url": "/private/files/greenspoon-dn.pdf",
		"is_private": 1,
		"file_size": 240 * 1024,
		"attached_to_doctype": "Customer Product Specification",
		"attached_to_name": "CPT-SPEC-00042",
	}
	row.update(overrides)
	return row


class TestArtworkBinding(unittest.TestCase):
	DT = "Customer Product Specification"
	NAME = "CPT-SPEC-00042"

	def test_a_correctly_bound_private_file_passes(self):
		self.assertIsNone(r.artwork_binding_error(file_row(), self.DT, self.NAME))

	def test_a_missing_file_is_refused(self):
		reason = r.artwork_binding_error(None, self.DT, self.NAME)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)

	def test_a_public_file_is_refused(self):
		reason = r.artwork_binding_error(file_row(is_private=0), self.DT, self.NAME)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_NOT_PRIVATE)

	def test_another_documents_file_is_refused(self):
		# The rule that stops a caller reading any private file on the site by
		# guessing its path.
		reason = r.artwork_binding_error(
			file_row(attached_to_name="CPT-SPEC-00001"), self.DT, self.NAME
		)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)
		self.assertIn("CPT-SPEC-00001", r.reason_text(reason))

	def test_another_doctypes_file_is_refused(self):
		reason = r.artwork_binding_error(
			file_row(attached_to_doctype="Sales Invoice", attached_to_name="SINV-0001"),
			self.DT, self.NAME,
		)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)

	def test_an_unattached_file_is_refused(self):
		reason = r.artwork_binding_error(
			file_row(attached_to_doctype=None, attached_to_name=None), self.DT, self.NAME
		)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)


class TestArtworkFileError(unittest.TestCase):
	"""The submit-time check that makes Desk, REST and Data Import obey the rules.

	``artwork`` is an Attach — a Data field holding a path — so anything that can
	write the document can write that path. Only the Compass uploader has ever
	been past the allowlist and the cap; this is where every other route is asked
	the same questions, from the *stored* File row rather than from the field.
	"""

	DT = "Customer Product Specification"
	NAME = "CPT-SPEC-00042"

	def error(self, row):
		return r.artwork_file_error(row, self.DT, self.NAME)

	def test_a_correctly_bound_private_file_of_an_allowed_kind_passes(self):
		self.assertIsNone(self.error(file_row()))

	def test_a_url_that_names_no_file_is_refused(self):
		# A perfectly well-formed path that no File row backs. This is the case a
		# REST write or a Data Import produces, and the one the field's value
		# cannot possibly prove on its own.
		reason = self.error(None)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)

	def test_a_public_file_is_refused(self):
		reason = self.error(file_row(is_private=0))
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_NOT_PRIVATE)

	def test_another_documents_file_is_refused(self):
		reason = self.error(file_row(attached_to_name="CPT-SPEC-00001"))
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)
		self.assertIn("CPT-SPEC-00001", r.reason_text(reason))

	def test_another_doctypes_file_is_refused(self):
		reason = self.error(
			file_row(attached_to_doctype="Sales Invoice", attached_to_name="SINV-0001")
		)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)

	def test_a_disallowed_kind_is_refused_even_when_correctly_bound(self):
		# The Desk attach control will store this happily. Submit is where it stops.
		for name in ("payload.exe", "brand.svg", "notes.docx"):
			reason = self.error(file_row(file_name=name))
			self.assertIsNotNone(reason, name)
			self.assertEqual(reason.code, r.BLOCK_ARTWORK_EXTENSION, name)

	def test_an_empty_file_is_refused(self):
		reason = self.error(file_row(file_size=0))
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_EMPTY)

	def test_a_missing_size_is_treated_as_empty(self):
		reason = self.error(file_row(file_size=None))
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_EMPTY)

	def test_an_oversized_file_is_refused(self):
		reason = self.error(file_row(file_size=r.ARTWORK_MAX_BYTES + 1))
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_TOO_LARGE)

	def test_exactly_the_cap_passes(self):
		self.assertIsNone(self.error(file_row(file_size=r.ARTWORK_MAX_BYTES)))

	def test_the_extension_is_read_from_the_url_when_there_is_no_file_name(self):
		self.assertIsNone(self.error(file_row(file_name=None)))
		reason = self.error(file_row(file_name=None, file_url="/private/files/brand.svg"))
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_EXTENSION)

	def test_binding_is_reported_before_the_kind(self):
		# A public .exe belonging to another document has three things wrong with
		# it. The one worth saying first is whose file it is.
		reason = self.error(
			file_row(file_name="payload.exe", is_private=0, attached_to_name="CPT-SPEC-00001")
		)
		self.assertEqual(reason.code, r.BLOCK_ARTWORK_WRONG_DOC)


class TestArtworkNoLongerBlocksSubmit(unittest.TestCase):
	"""The submit gate is gone, and its absence is worth a test.

	Deleting a rule leaves nothing behind to fail, so without these the next
	reader has no way to tell "deliberately removed" from "never existed" — and
	the obvious repair for a Printed specification with no artwork would be to
	put the gate back.
	"""

	def test_the_rule_is_gone_from_the_module(self):
		self.assertFalse(hasattr(r, "artwork_submit_block_reason"))
		self.assertFalse(hasattr(r, "BLOCK_ARTWORK_MISSING"))

	def test_printed_still_declares_that_artwork_applies_to_it(self):
		# artwork_required is KEPT: it is what tells a report, a Job Card or the
		# weekly chase that this job is printed and therefore ought to have
		# artwork somewhere. It just no longer refuses anything.
		self.assertTrue(r.artwork_required(spec(artwork=None)))
		self.assertFalse(r.artwork_required(spec(print_type=r.PRINT_TYPE_PLAIN)))
		self.assertFalse(r.artwork_required(spec(product_type="Label")))

	def test_a_printed_spec_with_no_artwork_has_no_save_block(self):
		self.assertIsNone(
			r.save_block_reason(None, spec(name=None, artwork=None, numbering_confirmed=1))
		)


class TestArtworkEvidence(unittest.TestCase):
	"""Which claim a specification makes, not merely whether it makes one."""

	def test_file_wins_when_everything_is_set(self):
		self.assertEqual(
			r.artwork_evidence(
				spec(artwork_tracker="ADVANCE PLASTICS LTD - 00001", artwork_not_ready=1)
			),
			"file",
		)

	def test_tracker_beats_deferral(self):
		self.assertEqual(
			r.artwork_evidence(
				spec(artwork=None, artwork_tracker="ADVANCE PLASTICS LTD - 00001",
				     artwork_not_ready=1)
			),
			"tracker",
		)

	def test_deferred_when_that_is_all_there_is(self):
		self.assertEqual(
			r.artwork_evidence(spec(artwork=None, artwork_not_ready=1)), "deferred"
		)

	def test_none_when_nothing_is_claimed(self):
		self.assertIsNone(r.artwork_evidence(spec(artwork=None)))


class TestNumberingAnswer(unittest.TestCase):
	"""The Desk Select mapped onto the two stored fields."""

	def test_yes_sets_both(self):
		self.assertEqual(
			r.numbering_answer_fields("Yes"),
			{r.NUMBERING_FIELD: 1, r.NUMBERING_CONFIRMED_FIELD: 1},
		)

	def test_no_confirms_without_requiring(self):
		self.assertEqual(
			r.numbering_answer_fields("No"),
			{r.NUMBERING_FIELD: 0, r.NUMBERING_CONFIRMED_FIELD: 1},
		)

	def test_blank_writes_nothing(self):
		# The legacy estate's whole protection: a record nobody answered carries
		# no answer here, and 0/0 would withdraw a confirmation nobody touched.
		self.assertIsNone(r.numbering_answer_fields(""))
		self.assertIsNone(r.numbering_answer_fields(None))
		self.assertIsNone(r.numbering_answer_fields("   "))

	def test_unrecognised_value_writes_nothing(self):
		self.assertIsNone(r.numbering_answer_fields("Maybe"))

	def test_answering_clears_the_numbering_block(self):
		# The whole point of the field: a new Desk record that answers the
		# question must save, and one that does not must still be refused.
		answered = spec(name=None, **r.numbering_answer_fields("No"))
		self.assertIsNone(r.numbering_block_reason(None, answered))
		self.assertIsNotNone(r.numbering_block_reason(None, spec(name=None)))


class TestArtworkDeletable(unittest.TestCase):
	DT = "Customer Product Specification"
	NAME = "CPT-SPEC-00042"

	def test_a_bound_orphan_may_be_deleted(self):
		self.assertTrue(r.artwork_deletable(file_row(), self.DT, self.NAME, 0))

	def test_a_file_another_record_still_points_at_is_kept(self):
		self.assertFalse(r.artwork_deletable(file_row(), self.DT, self.NAME, 1))

	def test_another_documents_file_is_never_deleted(self):
		self.assertFalse(
			r.artwork_deletable(
				file_row(attached_to_name="CPT-SPEC-00001"), self.DT, self.NAME, 0
			)
		)

	def test_a_public_file_is_never_deleted_by_this_path(self):
		self.assertFalse(r.artwork_deletable(file_row(is_private=0), self.DT, self.NAME, 0))

	def test_a_missing_file_is_not_deletable(self):
		self.assertFalse(r.artwork_deletable(None, self.DT, self.NAME, 0))


if __name__ == "__main__":
	unittest.main()
