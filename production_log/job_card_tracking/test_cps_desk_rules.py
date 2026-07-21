"""Unit tests for the Desk CPS preview and Item → specification list shaping.

Plain ``unittest``: no bench, no site, no database.

The property that matters most here is that the preview cannot be kinder than
the submit. Sales Order validation throws on the reasons in ``cps_rules``; the
preview reports the same reasons in the same order, and grades as a warning only
what validation itself lets a draft through with. A preview that cleared a line
the submit refuses would be worse than no preview at all — it would move the
failure to the moment the order is being committed.
"""

import unittest

from production_log.job_card_tracking import cps_desk_rules as desk
from production_log.job_card_tracking import cps_rules


def spec(**kw):
	base = {
		"name": "CPT-SPEC-00001",
		"customer": "ACME Ltd",
		"product_type": "Computer Paper",
		"specification_name": "Delivery Note 3 Part A4",
		"linked_item": "CP-DN-3PT-A4",
		"job_size": "A4",
		"pay_slip_size": None,
		"number_of_parts": 3,
		"number_of_colours": 2,
		"ink_type": "Process Offset",
		"numbering_required": 1,
		"standard_packing": "500 sets per carton",
		"standard_weight_per_carton": 12.5,
		"docstatus": 1,
		"status": "Active",
	}
	base.update(kw)
	return base


def price(**kw):
	base = {
		"name": "abc123",
		"valid_from": "2026-01-01",
		"rate": 5.172413793,
		"uom": "Set",
		"approval_status": cps_rules.APPROVAL_APPROVED,
	}
	base.update(kw)
	return base


# A sentinel, because None is a meaningful specification here: it is the
# "record not found" case, and defaulting it away would hide that test.
_DEFAULT = object()


def preview(spec_doc=_DEFAULT, **kw):
	kw.setdefault("item_code", "CP-DN-3PT-A4")
	kw.setdefault("customer", "ACME Ltd")
	kw.setdefault("price", price())
	return desk.build_line_preview(spec() if spec_doc is _DEFAULT else spec_doc, **kw)


class TestSeverity(unittest.TestCase):
	def test_no_reason_is_ok(self):
		self.assertEqual(desk.block_severity(None), desk.SEVERITY_OK)

	def test_a_missing_price_is_only_a_warning(self):
		# Design §7 V7 is draft-permissive: an order can be captured while its
		# price is still with the approver. Reporting it as a hard block would
		# tell a rep that a normal working state is a dead end.
		block = cps_rules.price_block_reason(None, "CPT-SPEC-00001", "21-07-2026")
		self.assertEqual(desk.block_severity(block), desk.SEVERITY_WARNING)

	def test_every_other_reason_blocks(self):
		for block in (
			cps_rules.spec_block_reason(None, "I", "C"),
			cps_rules.spec_block_reason(spec(customer="Other"), "CP-DN-3PT-A4", "ACME Ltd"),
			cps_rules.spec_block_reason(spec(docstatus=0), "CP-DN-3PT-A4", "ACME Ltd"),
			cps_rules.spec_block_reason(spec(status="Inactive"), "CP-DN-3PT-A4", "ACME Ltd"),
		):
			self.assertEqual(desk.block_severity(block), desk.SEVERITY_BLOCK, block.code)


class TestDisplayFields(unittest.TestCase):
	def test_every_field_is_always_present(self):
		# The client applies the dict verbatim, so a partial dict would leave the
		# previous specification's job size sitting under the new one's name.
		self.assertEqual(
			set(desk.build_display_fields(spec(), price())), set(desk.PREVIEW_DISPLAY_FIELDS)
		)
		self.assertEqual(set(desk.empty_display_fields()), set(desk.PREVIEW_DISPLAY_FIELDS))

	def test_the_blank_shape_matches_the_filled_one(self):
		self.assertEqual(
			set(desk.build_display_fields(None, None)), set(desk.empty_display_fields())
		)

	def test_commercial_and_technical_values_are_carried_across(self):
		fields = desk.build_display_fields(spec(), price())
		self.assertEqual(fields["custom_cps_rate"], 5.172413793)
		self.assertEqual(fields["custom_cps_uom"], "Set")
		self.assertEqual(fields["custom_cps_valid_from"], "2026-01-01")
		self.assertEqual(fields["custom_cps_price_row"], "abc123")
		self.assertEqual(fields["custom_spec_name"], "Delivery Note 3 Part A4")
		self.assertEqual(fields["custom_job_size"], "A4")
		self.assertEqual(fields["custom_number_of_parts"], 3)

	def test_a_specification_with_no_price_still_shows_its_technical_values(self):
		fields = desk.build_display_fields(spec(), None)
		self.assertIsNone(fields["custom_cps_rate"])
		self.assertEqual(fields["custom_spec_name"], "Delivery Note 3 Part A4")

	def test_the_rate_keeps_all_nine_decimal_places(self):
		# Anything less silently rounds 5.172413793, which then fails the
		# exact-match test at submit forever (design §5.1, §9.1).
		self.assertEqual(
			desk.build_display_fields(spec(), price(rate="5.172413793"))["custom_cps_rate"],
			5.172413793,
		)


class TestApplyFields(unittest.TestCase):
	def test_the_approved_rate_and_uom_are_offered(self):
		self.assertEqual(
			desk.build_apply_fields(price()), {"rate": 5.172413793, "uom": "Set"}
		)

	def test_no_price_offers_nothing(self):
		# An empty dict rather than blanks: clobbering a typed rate with null
		# because the spec has no approved price destroys the rep's work.
		self.assertEqual(desk.build_apply_fields(None), {})
		self.assertEqual(desk.build_apply_fields(price(rate=None)), {})

	def test_a_zero_rate_is_still_a_rate(self):
		self.assertEqual(desk.build_apply_fields(price(rate=0))["rate"], 0.0)


class TestTechnicalPreview(unittest.TestCase):
	def test_unset_values_are_dropped(self):
		fieldnames = {row["fieldname"] for row in desk.build_technical_preview(spec())}
		self.assertIn("job_size", fieldnames)
		self.assertNotIn("pay_slip_size", fieldnames)

	def test_every_row_carries_a_label_for_the_reader(self):
		for row in desk.build_technical_preview(spec()):
			self.assertTrue(row["label"])
			self.assertNotEqual(row["label"], row["fieldname"])

	def test_an_absent_specification_previews_nothing(self):
		self.assertEqual(desk.build_technical_preview(None), [])

	def test_parts_are_reported_column_by_column(self):
		parts = desk.build_part_preview(
			[{"part_number": 1, "paper_type": "CB", "gsm": 55, "colour": "White", "purpose": "Original"}]
		)
		self.assertEqual(len(parts), 1)
		self.assertEqual(set(parts[0]), set(desk.PART_PREVIEW_FIELDS))
		self.assertEqual(parts[0]["paper_type"], "CB")

	def test_no_parts_serialise_as_an_empty_list(self):
		self.assertEqual(desk.build_part_preview(None), [])


class TestLinePreview(unittest.TestCase):
	def test_a_clean_line_previews_ok_and_offers_the_rate(self):
		result = preview(expected_product_type="Computer Paper")
		self.assertTrue(result["ok"])
		self.assertEqual(result["severity"], desk.SEVERITY_OK)
		self.assertIsNone(result["block"])
		self.assertEqual(result["apply"], {"rate": 5.172413793, "uom": "Set"})
		self.assertEqual(result["display"]["custom_spec_name"], "Delivery Note 3 Part A4")

	def test_a_blocked_line_clears_everything_it_touches(self):
		# A specification that must not be used at all: previewing its job size
		# would read as an invitation to keep it.
		result = preview(spec(customer="Beta Ltd"))
		self.assertFalse(result["ok"])
		self.assertEqual(result["severity"], desk.SEVERITY_BLOCK)
		self.assertEqual(result["block"]["code"], cps_rules.BLOCK_CUSTOMER)
		self.assertEqual(result["apply"], {})
		self.assertEqual(result["technical"], [])
		self.assertTrue(all(value is None for value in result["display"].values()))

	def test_a_missing_price_warns_but_keeps_the_specification_on_screen(self):
		result = preview(price=None, on_date_label="21-07-2026")
		self.assertFalse(result["ok"])
		self.assertEqual(result["severity"], desk.SEVERITY_WARNING)
		self.assertEqual(result["block"]["code"], cps_rules.BLOCK_NO_PRICE)
		# Nothing is put on the line — the rep's own rate stands — but the
		# specification they picked is still described.
		self.assertEqual(result["apply"], {})
		self.assertEqual(result["display"]["custom_spec_name"], "Delivery Note 3 Part A4")
		self.assertIsNone(result["display"]["custom_cps_rate"])
		self.assertTrue(result["technical"])

	def test_the_spec_reason_is_reported_before_the_price_reason(self):
		# A cancelled specification with no price is a cancelled specification.
		# Reporting the price first would send the user to add a price row to a
		# document that can never be ordered against.
		result = preview(spec(docstatus=2), price=None)
		self.assertEqual(result["block"]["code"], cps_rules.BLOCK_DOCSTATUS)

	def test_a_missing_specification_names_what_was_requested(self):
		result = preview(None, requested_name="CPT-SPEC-09999", price=None)
		self.assertEqual(result["block"]["code"], cps_rules.BLOCK_MISSING)
		self.assertEqual(result["block"]["args"], ["CPT-SPEC-09999"])

	def test_the_reason_survives_as_a_translatable_template(self):
		result = preview(spec(customer="Beta Ltd"))
		self.assertIn("{0}", result["block"]["template"])
		self.assertTrue(result["block"]["template"].format(*result["block"]["args"]))

	def test_the_wrong_kind_of_specification_is_previewed_as_blocked(self):
		result = preview(spec(product_type="Label"), expected_product_type="Computer Paper")
		self.assertEqual(result["block"]["code"], cps_rules.BLOCK_PRODUCT_TYPE)

	def test_the_payload_always_names_the_fields_it_drives(self):
		# The client clears exactly what the server says it fills, so the two
		# lists cannot drift apart.
		for result in (preview(), preview(spec(status="Inactive")), desk.blank_line_preview()):
			self.assertEqual(result["display_fields"], list(desk.PREVIEW_DISPLAY_FIELDS))
			self.assertEqual(set(result["display"]), set(desk.PREVIEW_DISPLAY_FIELDS))

	def test_the_blank_preview_is_inert(self):
		blank = desk.blank_line_preview()
		self.assertIsNone(blank["block"])
		self.assertEqual(blank["severity"], desk.SEVERITY_OK)
		self.assertFalse(blank["ok"])
		self.assertEqual(blank["apply"], {})
		self.assertTrue(all(value is None for value in blank["display"].values()))

	def test_parts_ride_along_when_the_specification_is_usable(self):
		result = preview(colour_of_parts=[{"part_number": 1, "paper_type": "CB"}])
		self.assertEqual(len(result["parts"]), 1)

	def test_parts_are_withheld_from_a_blocked_specification(self):
		result = preview(spec(status="Inactive"), colour_of_parts=[{"part_number": 1}])
		self.assertEqual(result["parts"], [])


class TestLinkedSpecRows(unittest.TestCase):
	def test_an_original_is_labelled_as_one(self):
		self.assertEqual(desk.revision_label(spec(amended_from=None)), desk.REVISION_ORIGINAL)

	def test_an_amendment_names_its_predecessor(self):
		# Five near-identical rows are unreadable unless each says what it came
		# from.
		self.assertIn(
			"CPT-SPEC-00001",
			desk.revision_label(spec(amended_from="CPT-SPEC-00001")),
		)

	def test_only_submitted_and_active_specifications_are_orderable(self):
		self.assertTrue(desk.is_orderable(spec()))
		self.assertFalse(desk.is_orderable(spec(docstatus=0)))
		self.assertFalse(desk.is_orderable(spec(docstatus=2)))
		self.assertFalse(desk.is_orderable(spec(status="Discontinued")))

	def test_a_row_is_scalar_only(self):
		row = desk.build_linked_spec_row(spec(current_rate=5.17, current_uom="Set"))
		self.assertEqual(set(row), set(desk.LINKED_SPEC_COLUMNS))
		for value in row.values():
			self.assertNotIsInstance(value, (list, dict))

	def test_docstatus_is_given_a_label_a_person_can_read(self):
		self.assertEqual(desk.build_linked_spec_row(spec(docstatus=0))["docstatus_label"], "Draft")
		self.assertEqual(
			desk.build_linked_spec_row(spec(docstatus=2))["docstatus_label"], "Cancelled"
		)

	def test_orderable_rows_sort_above_history(self):
		# The question this list answers is nearly always "who can I sell this to
		# today", so the answer must not be interleaved with cancelled
		# amendments from three years ago.
		rows = [
			desk.build_linked_spec_row(spec(name="CPT-SPEC-9", customer="Zulu", docstatus=2)),
			desk.build_linked_spec_row(spec(name="CPT-SPEC-1", customer="Alpha")),
			desk.build_linked_spec_row(spec(name="CPT-SPEC-2", customer="Beta")),
		]
		ordered = [row["name"] for row in desk.sort_linked_spec_rows(rows)]
		self.assertEqual(ordered, ["CPT-SPEC-1", "CPT-SPEC-2", "CPT-SPEC-9"])

	def test_the_summary_counts_only_orderable_customers(self):
		rows = [
			desk.build_linked_spec_row(spec(name="A", customer="Alpha")),
			desk.build_linked_spec_row(spec(name="B", customer="Alpha")),
			desk.build_linked_spec_row(spec(name="C", customer="Beta", status="Inactive")),
		]
		summary = desk.summarise_linked_specs(rows)
		self.assertEqual(summary["total"], 3)
		self.assertEqual(summary["orderable"], 2)
		self.assertEqual(summary["customers"], 1)

	def test_an_item_with_no_specifications_summarises_cleanly(self):
		self.assertEqual(
			desk.summarise_linked_specs([]), {"total": 0, "orderable": 0, "customers": 0}
		)


if __name__ == "__main__":
	unittest.main()
