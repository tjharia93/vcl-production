"""Unit tests for Item-level CPS control and the orderability reasons (WBS-27).

Plain ``unittest``: no bench, no site, no database. What is under test is the
precedence rule — when an Item's own answer beats the Item Group tree's, and in
which direction — plus the reasons the Desk preview and Sales Order validation
must agree on.

The Frappe-bound half (``so_spec_control.derive_item_control_flag``, which reads
the Item Group nested set and writes the derived flag) is not covered here.
"""

import unittest

from production_log.job_card_tracking import cps_rules


def group(name="Pre-Printed Computer Paper", product_type="Computer Paper"):
	"""A controlling Item Group, as ``item_group_requires_cps`` returns one."""
	return {"name": name, "custom_requires_cps": 1, "custom_cps_product_type": product_type}


def spec(**kw):
	base = {
		"name": "CPT-SPEC-00001",
		"customer": "ACME Ltd",
		"product_type": "Computer Paper",
		"specification_name": "Delivery Note 3 Part A4",
		"linked_item": "CP-DN-3PT-A4",
		"docstatus": 1,
		"status": "Active",
	}
	base.update(kw)
	return base


class TestNormaliseControlMode(unittest.TestCase):
	def test_the_three_configured_modes_survive(self):
		for mode in cps_rules.CONTROL_MODES:
			self.assertEqual(cps_rules.normalise_control_mode(mode), mode)

	def test_blank_and_none_mean_inherit(self):
		# An Item written before the field existed has no value for it, and
		# "unset" has to mean "behave exactly as before".
		for value in (None, "", "   "):
			self.assertEqual(
				cps_rules.normalise_control_mode(value), cps_rules.CONTROL_MODE_INHERIT
			)

	def test_an_unrecognised_value_falls_back_to_inherit(self):
		# A Select option renamed underneath stored data must not silently become
		# a control decision nobody configured.
		self.assertEqual(
			cps_rules.normalise_control_mode("Require CPS Please"),
			cps_rules.CONTROL_MODE_INHERIT,
		)

	def test_surrounding_whitespace_is_not_a_different_mode(self):
		self.assertEqual(
			cps_rules.normalise_control_mode("  Exempt from CPS  "),
			cps_rules.CONTROL_MODE_EXEMPT,
		)


class TestItemRequiresCPS(unittest.TestCase):
	"""The precedence rule: explicit beats inherited, in both directions."""

	def test_inherit_defers_to_a_controlling_group(self):
		self.assertTrue(cps_rules.item_requires_cps(cps_rules.CONTROL_MODE_INHERIT, group()))

	def test_inherit_defers_to_an_uncontrolled_tree(self):
		self.assertFalse(cps_rules.item_requires_cps(cps_rules.CONTROL_MODE_INHERIT, None))

	def test_blank_behaves_exactly_as_inherit(self):
		self.assertTrue(cps_rules.item_requires_cps(None, group()))
		self.assertFalse(cps_rules.item_requires_cps(None, None))

	def test_require_controls_an_item_whose_group_does_not(self):
		# The point of the override: pilot one Item without controlling the 46
		# others in its group.
		self.assertTrue(cps_rules.item_requires_cps(cps_rules.CONTROL_MODE_REQUIRE, None))

	def test_require_also_holds_inside_a_controlled_group(self):
		self.assertTrue(cps_rules.item_requires_cps(cps_rules.CONTROL_MODE_REQUIRE, group()))

	def test_exempt_releases_an_item_from_a_controlled_group(self):
		# The other half of the point: one sample Item inside a controlled family.
		self.assertFalse(cps_rules.item_requires_cps(cps_rules.CONTROL_MODE_EXEMPT, group()))

	def test_exempt_on_an_uncontrolled_item_changes_nothing(self):
		self.assertFalse(cps_rules.item_requires_cps(cps_rules.CONTROL_MODE_EXEMPT, None))


class TestItemControlSource(unittest.TestCase):
	def test_each_outcome_reports_a_distinct_code(self):
		codes = {
			cps_rules.item_control_source(mode, controlling).code
			for mode, controlling in (
				(cps_rules.CONTROL_MODE_REQUIRE, None),
				(cps_rules.CONTROL_MODE_EXEMPT, group()),
				(cps_rules.CONTROL_MODE_INHERIT, group()),
				(cps_rules.CONTROL_MODE_INHERIT, None),
			)
		}
		self.assertEqual(len(codes), 4)

	def test_an_exemption_names_the_group_it_overrides(self):
		# Without the group name the user cannot tell what the exemption is even
		# for, and cannot find the setting that would undo it.
		source = cps_rules.item_control_source(cps_rules.CONTROL_MODE_EXEMPT, group("Carton Blanks"))
		self.assertEqual(source.code, cps_rules.SOURCE_EXPLICIT_EXEMPT)
		self.assertIn("Carton Blanks", source.template.format(*source.args))

	def test_an_exemption_with_no_controlling_group_names_none(self):
		source = cps_rules.item_control_source(cps_rules.CONTROL_MODE_EXEMPT, None)
		self.assertEqual(source.args, ())
		self.assertEqual(source.template.format(), "Exempted explicitly on this Item.")

	def test_inheritance_names_the_group_it_came_from(self):
		source = cps_rules.item_control_source(None, group("Pre-Printed"))
		self.assertEqual(source.code, cps_rules.SOURCE_INHERITED)
		self.assertIn("Pre-Printed", cps_rules.item_control_source_text(None, group("Pre-Printed")))

	def test_the_template_is_left_untranslated_for_the_caller(self):
		# The rules stay Frappe-free, so the caller does _(template).format(*args)
		# rather than being handed a finished sentence that no catalogue matches.
		source = cps_rules.item_control_source(cps_rules.CONTROL_MODE_INHERIT, group("X"))
		self.assertIn("{0}", source.template)
		self.assertEqual(source.args, ("X",))

	def test_source_text_agrees_with_the_template_and_arguments(self):
		for mode in (None,) + cps_rules.CONTROL_MODES:
			for controlling in (None, group()):
				source = cps_rules.item_control_source(mode, controlling)
				self.assertEqual(
					cps_rules.item_control_source_text(mode, controlling),
					source.template.format(*source.args),
				)


class TestItemConfigError(unittest.TestCase):
	"""Require CPS on an Item must say which kind of specification it means."""

	def test_require_without_a_product_type_is_refused(self):
		# The gap this closes: without an expected type, a Label specification
		# passes on a Computer Paper Item because nothing says otherwise.
		error = cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, None)
		self.assertEqual(error.code, cps_rules.CONFIG_PRODUCT_TYPE_REQUIRED)

	def test_require_with_a_blank_product_type_is_refused(self):
		for value in ("", "   "):
			error = cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, value)
			self.assertEqual(error.code, cps_rules.CONFIG_PRODUCT_TYPE_REQUIRED)

	def test_require_with_a_valid_product_type_is_accepted(self):
		for product_type in cps_rules.CPS_PRODUCT_TYPES:
			self.assertIsNone(
				cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, product_type)
			)

	def test_a_product_type_outside_the_list_is_refused(self):
		error = cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, "Computer paper")
		self.assertEqual(error.code, cps_rules.CONFIG_PRODUCT_TYPE_UNKNOWN)
		self.assertIn("Computer paper", error.template.format(*error.args))

	def test_an_unknown_type_is_reported_before_a_missing_one(self):
		# Both are wrong at once only when the value is garbage; naming the
		# garbage is more useful than calling it absent.
		error = cps_rules.item_config_error(cps_rules.CONTROL_MODE_INHERIT, "Labels")
		self.assertEqual(error.code, cps_rules.CONFIG_PRODUCT_TYPE_UNKNOWN)

	def test_inherit_and_exempt_need_no_product_type(self):
		# Inherit takes the group's answer and Exempt has no lines to check, so
		# neither is an incomplete configuration.
		for mode in (None, cps_rules.CONTROL_MODE_INHERIT, cps_rules.CONTROL_MODE_EXEMPT):
			self.assertIsNone(cps_rules.item_config_error(mode, None))

	def test_the_message_lists_the_types_that_would_be_accepted(self):
		error = cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, None)
		message = error.template.format(*error.args)
		for product_type in cps_rules.CPS_PRODUCT_TYPES:
			self.assertIn(product_type, message)

	def test_every_template_placeholder_has_an_argument(self):
		for error in (
			cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, None),
			cps_rules.item_config_error(cps_rules.CONTROL_MODE_REQUIRE, "Nonsense"),
		):
			self.assertTrue(error.template.format(*error.args))


class TestExpectedProductType(unittest.TestCase):
	"""Item override first, controlling Item Group second."""

	def test_the_item_override_wins_over_the_group(self):
		self.assertEqual(
			cps_rules.expected_product_type(
				cps_rules.CONTROL_MODE_REQUIRE, "Label", group(product_type="Computer Paper")
			),
			"Label",
		)

	def test_the_group_answers_when_the_item_does_not(self):
		self.assertEqual(
			cps_rules.expected_product_type(cps_rules.CONTROL_MODE_INHERIT, None, group()),
			"Computer Paper",
		)

	def test_an_explicit_require_outside_a_controlled_group_still_expects_a_type(self):
		# The Codex gap: control turned on at the Item, no group to inherit a
		# type from. Without this the product-type check never runs.
		self.assertEqual(
			cps_rules.expected_product_type(cps_rules.CONTROL_MODE_REQUIRE, "Computer Paper", None),
			"Computer Paper",
		)

	def test_a_require_with_no_type_and_no_group_expects_nothing(self):
		# Unconfigurable through the form — validation refuses it — but a row
		# written before this landed must not crash the resolver.
		self.assertIsNone(
			cps_rules.expected_product_type(cps_rules.CONTROL_MODE_REQUIRE, None, None)
		)

	def test_an_exempt_item_expects_nothing_at_all(self):
		# It is not controlled, so there is no specification for it to need.
		self.assertIsNone(
			cps_rules.expected_product_type(cps_rules.CONTROL_MODE_EXEMPT, "Label", group())
		)

	def test_an_uncontrolled_item_expects_nothing(self):
		self.assertIsNone(cps_rules.expected_product_type(None, None, None))

	def test_surrounding_whitespace_is_not_a_different_type(self):
		self.assertEqual(
			cps_rules.expected_product_type(cps_rules.CONTROL_MODE_REQUIRE, "  Label  ", None),
			"Label",
		)

	def test_an_inherit_item_may_still_correct_its_groups_type(self):
		# One Label Item sitting in a Carton group is a real configuration, and
		# the Item is the more specific statement.
		self.assertEqual(
			cps_rules.expected_product_type(None, "Label", group(product_type="Carton")),
			"Label",
		)

	def test_a_label_spec_cannot_pass_on_an_explicitly_required_computer_paper_item(self):
		# End to end over the two functions Sales Order validation composes.
		expected = cps_rules.expected_product_type(
			cps_rules.CONTROL_MODE_REQUIRE, "Computer Paper", None
		)
		block = cps_rules.spec_block_reason(
			spec(product_type="Label"), "CP-DN-3PT-A4", "ACME Ltd", expected
		)
		self.assertEqual(block.code, cps_rules.BLOCK_PRODUCT_TYPE)


class TestSpecBlockReason(unittest.TestCase):
	"""Same reasons, same order, as ``so_spec_control._load_and_validate_spec``."""

	def test_a_clean_specification_is_not_blocked(self):
		self.assertIsNone(
			cps_rules.spec_block_reason(spec(), "CP-DN-3PT-A4", "ACME Ltd", "Computer Paper")
		)

	def test_a_missing_specification_names_what_was_asked_for(self):
		# Not the Item: the record is missing, and naming the Item would send the
		# reader to the wrong document.
		block = cps_rules.spec_block_reason(
			None, "CP-DN-3PT-A4", "ACME Ltd", requested_name="CPT-SPEC-09999"
		)
		self.assertEqual(block.code, cps_rules.BLOCK_MISSING)
		self.assertEqual(block.args, ("CPT-SPEC-09999",))

	def test_a_missing_specification_falls_back_to_the_item(self):
		block = cps_rules.spec_block_reason(None, "CP-DN-3PT-A4", "ACME Ltd")
		self.assertEqual(block.args, ("CP-DN-3PT-A4",))

	def test_another_customers_specification_is_refused(self):
		block = cps_rules.spec_block_reason(spec(), "CP-DN-3PT-A4", "Beta Ltd")
		self.assertEqual(block.code, cps_rules.BLOCK_CUSTOMER)

	def test_a_specification_for_another_item_is_refused(self):
		block = cps_rules.spec_block_reason(spec(), "CP-DN-4PT-A4", "ACME Ltd")
		self.assertEqual(block.code, cps_rules.BLOCK_ITEM)

	def test_an_unlinked_specification_serves_nothing(self):
		# A missing link is not a wildcard; treating it as one is how the wrong
		# customer's agreed rate reaches the wrong product.
		block = cps_rules.spec_block_reason(spec(linked_item=None), "CP-DN-3PT-A4", "ACME Ltd")
		self.assertEqual(block.code, cps_rules.BLOCK_ITEM)

	def test_the_wrong_kind_of_specification_is_refused(self):
		block = cps_rules.spec_block_reason(
			spec(product_type="Label"), "CP-DN-3PT-A4", "ACME Ltd", "Computer Paper"
		)
		self.assertEqual(block.code, cps_rules.BLOCK_PRODUCT_TYPE)

	def test_no_expected_product_type_means_no_product_type_check(self):
		self.assertIsNone(
			cps_rules.spec_block_reason(spec(product_type="Label"), "CP-DN-3PT-A4", "ACME Ltd")
		)

	def test_draft_and_cancelled_specifications_are_refused_distinctly(self):
		draft = cps_rules.spec_block_reason(spec(docstatus=0), "CP-DN-3PT-A4", "ACME Ltd")
		cancelled = cps_rules.spec_block_reason(spec(docstatus=2), "CP-DN-3PT-A4", "ACME Ltd")
		self.assertEqual(draft.code, cps_rules.BLOCK_DOCSTATUS)
		self.assertEqual(cancelled.code, cps_rules.BLOCK_DOCSTATUS)
		self.assertNotEqual(draft.args, cancelled.args)

	def test_an_inactive_specification_is_refused(self):
		block = cps_rules.spec_block_reason(spec(status="Discontinued"), "CP-DN-3PT-A4", "ACME Ltd")
		self.assertEqual(block.code, cps_rules.BLOCK_STATUS)

	def test_the_wrong_customer_is_reported_before_the_wrong_item(self):
		# Both paths must name the same reason when several are wrong at once, or
		# the preview clears a line the submit then refuses for a different one.
		block = cps_rules.spec_block_reason(
			spec(customer="Beta Ltd", linked_item="OTHER"), "CP-DN-3PT-A4", "ACME Ltd"
		)
		self.assertEqual(block.code, cps_rules.BLOCK_CUSTOMER)

	def test_every_template_placeholder_has_an_argument(self):
		for block in (
			cps_rules.spec_block_reason(None, "I", "C"),
			cps_rules.spec_block_reason(spec(customer="Other"), "I", "C"),
			cps_rules.spec_block_reason(spec(), "OTHER-ITEM", "ACME Ltd"),
			cps_rules.spec_block_reason(spec(product_type="Label"), "CP-DN-3PT-A4", "ACME Ltd", "Computer Paper"),
			cps_rules.spec_block_reason(spec(docstatus=0), "CP-DN-3PT-A4", "ACME Ltd"),
			cps_rules.spec_block_reason(spec(status="Inactive"), "CP-DN-3PT-A4", "ACME Ltd"),
		):
			# Raises IndexError if the template asks for more than it was given.
			self.assertTrue(block.template.format(*block.args))


class TestPriceBlockReason(unittest.TestCase):
	def test_an_approved_price_is_not_blocked(self):
		self.assertIsNone(
			cps_rules.price_block_reason({"rate": 5.172413793}, "CPT-SPEC-00001", "2026-07-21")
		)

	def test_no_eligible_row_is_reported(self):
		block = cps_rules.price_block_reason(None, "CPT-SPEC-00001", "21-07-2026")
		self.assertEqual(block.code, cps_rules.BLOCK_NO_PRICE)
		self.assertEqual(block.args, ("CPT-SPEC-00001", "21-07-2026"))

	def test_a_row_with_no_rate_is_the_same_problem(self):
		# From an order line, "no price at all" and "a price nobody approved" are
		# indistinguishable, so they report identically.
		block = cps_rules.price_block_reason({"rate": None}, "CPT-SPEC-00001", "21-07-2026")
		self.assertEqual(block.code, cps_rules.BLOCK_NO_PRICE)

	def test_a_zero_rate_is_a_price(self):
		# Zero is a rate someone approved — a free sample — not a missing one.
		self.assertIsNone(cps_rules.price_block_reason({"rate": 0}, "CPT-SPEC-00001", "21-07-2026"))


if __name__ == "__main__":
	unittest.main()
