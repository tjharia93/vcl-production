"""Unit tests for the Carton half of the CPS rules.

Plain ``unittest``, no bench, no site, no database — ``cps_rules`` imports
nothing from Frappe. The Frappe-bound half (row locks, throws, rollups) lives in
``order_derived.py`` and needs a bench; what is testable without one is the
decision itself, which is here.

Every Computer Paper assertion in this file is a *regression* test. The Carton
work widened three shared things — the material-field set, the frozen snapshot
and the mismatch comparison — and the one thing that must not have changed is
what any of them does to a Computer Paper record.
"""

import unittest

from production_log.job_card_tracking import cps_rules

# The exact material set that shipped before product types were distinguished.
# Frozen here as a literal rather than imported, so a change to the module is a
# failing test rather than a test that changes with it.
LEGACY_MATERIAL_FIELDS = (
	"product_type",
	"specification_name",
	"customer",
	"job_size",
	"pay_slip_size",
	"number_of_parts",
	"linked_item",
)

# Exactly what snapshot version 1 wrote, in its original order.
V1_SNAPSHOT_KEYS = (
	"product_type",
	"specification_name",
	"customer",
	"job_size",
	"pay_slip_size",
	"number_of_parts",
	"numbering_required",
	"standard_packing",
	"standard_weight_per_carton",
	"ink_type",
	"uses_c",
	"uses_m",
	"uses_y",
	"uses_k",
	"number_of_colours",
	"colour_notes",
)


def carton_spec(**overrides):
	"""A submitted, linked, fully specified Carton specification."""
	values = {
		"name": "CTN-SPEC-00007",
		"modified": "2026-07-01 09:15:00",
		"product_type": "Carton",
		"specification_name": "Mango Export Carton 5 Ply",
		"customer": "CUST-0042",
		"customer_name": "CUST-0042",
		"job_size": "400x300x250",
		"linked_item": "CTN-5PLY-MANGO",
		"numbering_required": 0,
		"standard_packing": "25 per bale",
		"standard_weight_per_carton": 18.5,
		"ink_type": "Process Offset",
		"uses_c": 1,
		"uses_m": 0,
		"uses_y": 0,
		"uses_k": 1,
		"number_of_colours": 2,
		"colour_notes": "Two colour flexo",
		"ply": "5",
		"flute_type": "C",
		"ctn_length_mm": 400,
		"ctn_width_mm": 300,
		"ctn_height_mm": 250,
		"printing_or_plain": "Printed",
		"joint_type": "Gluing - Machine",
		"product_type_carton": "3 Flap RSC",
		"idod": "ID",
		"special_instructions_carton": "Handle stacking mark",
		"1_ply_top_layer_gsm": 150,
		"1_ply_top_layer_material": "White Test Liner",
		"2_ply_fluting_gsm": 120,
		"2_ply_top_layer_material": "Test Liner",
		"3_ply_bottom_gsm": 150,
		"3_ply_top_layer_material": "Kraft",
		"4_ply_fluting_gsm": 120,
		"4_ply_top_layer_material": "Test Liner",
		"5_ply_fluting_gsm": 150,
		"5_ply_top_layer_material": "Kraft",
	}
	values.update(overrides)
	return values


def cp_spec(**overrides):
	values = {
		"name": "CPT-SPEC-00001",
		"modified": "2026-07-01 09:15:00",
		"product_type": "Computer Paper",
		"specification_name": "Computer Paper 3 Part A4",
		"customer": "CUST-0001",
		"job_size": "A4",
		"linked_item": "CPT-3PT-A4",
		"pay_slip_size": "241x279",
		"number_of_parts": 3,
		"numbering_required": 1,
		"standard_packing": "1000 per box",
		"standard_weight_per_carton": 12.0,
		"ink_type": "Process Offset",
		"uses_c": 0,
		"uses_m": 0,
		"uses_y": 0,
		"uses_k": 1,
		"number_of_colours": 1,
		"colour_notes": None,
	}
	values.update(overrides)
	return values


def carton_snapshot(**overrides):
	snapshot = cps_rules.build_spec_snapshot(carton_spec(), [], [], "2026-07-02 10:00:00")
	snapshot.update(overrides)
	return snapshot


def carton_card(**overrides):
	"""A Job Card Carton faithfully populated from :func:`carton_snapshot`."""
	values = {
		"specification_name": "Mango Export Carton 5 Ply",
		"job_size": "400x300x250",
		"numbering_required": 0,
		"packing": "25 per bale",
		"weight_per_carton": 18.5,
		"ink_type": "Process Offset",
		"uses_c": 1,
		"uses_m": 0,
		"uses_y": 0,
		"uses_k": 1,
		"number_of_colours": 2,
		"colour_notes": "Two colour flexo",
		"ply": "5",
		"flute_type": "C",
		"ctn_length_mm": 400,
		"ctn_width_mm": 300,
		"ctn_height_mm": 250,
		"printing_or_plain": "Printed",
		"joint_type": "Gluing - Machine",
		# The rename: the card's own product_type holds the carton *style*.
		"product_type": "3 Flap RSC",
		"idod": "ID",
		"special_instructions": "Handle stacking mark",
		"1_ply_top_layer_gsm": 150,
		"1_ply_top_layer_material": "White Test Liner",
		"2_ply_fluting_gsm": 120,
		"2_ply_top_layer_material": "Test Liner",
		"3_ply_bottom_gsm": 150,
		"3_ply_top_layer_material": "Kraft",
		"4_ply_fluting_gsm": 120,
		"4_ply_top_layer_material": "Test Liner",
		"5_ply_fluting_gsm": 150,
		"5_ply_top_layer_material": "Kraft",
	}
	values.update(overrides)
	return values


def fields(mismatches):
	return sorted(m.field for m in mismatches)


class TestMaterialSpecFields(unittest.TestCase):
	"""Which edits force an Item link, per product type."""

	def test_computer_paper_is_exactly_what_it_always_was(self):
		self.assertEqual(
			set(cps_rules.material_spec_fields("Computer Paper")),
			set(LEGACY_MATERIAL_FIELDS),
		)

	def test_the_legacy_constant_is_untouched(self):
		# Anything still importing MATERIAL_SPEC_FIELDS gets the same tuple.
		self.assertEqual(cps_rules.MATERIAL_SPEC_FIELDS, LEGACY_MATERIAL_FIELDS)

	def test_carton_watches_the_box(self):
		carton = set(cps_rules.material_spec_fields("Carton"))

		for fieldname in (
			"ctn_length_mm",
			"ctn_width_mm",
			"ctn_height_mm",
			"ply",
			"flute_type",
			"product_type_carton",
			"1_ply_top_layer_gsm",
			"5_ply_top_layer_material",
		):
			self.assertIn(fieldname, carton)

	def test_carton_does_not_watch_computer_paper_fields(self):
		carton = set(cps_rules.material_spec_fields("Carton"))

		self.assertNotIn("pay_slip_size", carton)
		self.assertNotIn("number_of_parts", carton)

	def test_shared_fields_are_watched_for_every_type(self):
		for product_type in ("Computer Paper", "Carton", "Label", None, "", "   "):
			watched = set(cps_rules.material_spec_fields(product_type))
			self.assertIn("customer", watched)
			self.assertIn("specification_name", watched)
			self.assertIn("job_size", watched)
			self.assertIn(cps_rules.ITEM_LINK_FIELD, watched)

	def test_an_unknown_type_gets_the_shared_set_only(self):
		# Inventing fields for a type this module does not know would compare
		# columns that do not exist.
		self.assertEqual(
			set(cps_rules.material_spec_fields("Exercise Books")),
			set(cps_rules.SHARED_MATERIAL_SPEC_FIELDS),
		)

	def test_no_duplicates_however_the_sets_overlap(self):
		for product_type in ("Computer Paper", "Carton", "Label"):
			watched = cps_rules.material_spec_fields(product_type)
			self.assertEqual(len(watched), len(set(watched)))


class TestMaterialSpecChanges(unittest.TestCase):
	def test_a_carton_resize_is_material(self):
		before = carton_spec()
		after = carton_spec(ctn_length_mm=420)

		self.assertEqual(cps_rules.material_spec_changes(before, after), ["ctn_length_mm"])

	def test_a_board_change_is_material(self):
		changed = cps_rules.material_spec_changes(
			carton_spec(), carton_spec(**{"3_ply_top_layer_material": "Test Liner"})
		)

		self.assertEqual(changed, ["3_ply_top_layer_material"])

	def test_the_carton_style_is_material(self):
		changed = cps_rules.material_spec_changes(
			carton_spec(), carton_spec(product_type_carton="Tray")
		)

		self.assertEqual(changed, ["product_type_carton"])

	def test_notes_are_not_material(self):
		# Deliberate, and the same rule Computer Paper has always had: notes,
		# status and pricing do not change what the specification *is*.
		self.assertEqual(
			cps_rules.material_spec_changes(
				carton_spec(), carton_spec(special_instructions_carton="Different note")
			),
			[],
		)

	def test_retyping_watches_both_sides(self):
		# Carton -> Computer Paper. The product type itself changed, and the
		# fields being abandoned still have to be compared before they stop
		# counting.
		before = carton_spec()
		after = carton_spec(product_type="Computer Paper", ctn_length_mm=999)
		changed = cps_rules.material_spec_changes(before, after)

		self.assertIn("product_type", changed)
		self.assertIn("ctn_length_mm", changed)

	def test_a_computer_paper_edit_is_unchanged(self):
		self.assertEqual(
			cps_rules.material_spec_changes(cp_spec(), cp_spec(number_of_parts=4)),
			["number_of_parts"],
		)

	def test_no_change_is_no_change(self):
		self.assertEqual(cps_rules.material_spec_changes(carton_spec(), carton_spec()), [])

	def test_missing_versions_compare_to_nothing(self):
		self.assertEqual(cps_rules.material_spec_changes(None, carton_spec()), [])
		self.assertEqual(cps_rules.material_spec_changes(carton_spec(), None), [])


class TestItemLinkRequired(unittest.TestCase):
	def test_a_new_specification_needs_a_link(self):
		self.assertTrue(cps_rules.item_link_required(None, carton_spec(linked_item=None)))

	def test_an_already_linked_specification_never_needs_one(self):
		self.assertFalse(cps_rules.item_link_required(None, carton_spec()))

	def test_resizing_an_unlinked_legacy_carton_forces_the_link(self):
		before = carton_spec(linked_item=None)
		after = carton_spec(linked_item=None, ctn_width_mm=310)

		self.assertTrue(cps_rules.item_link_required(before, after))

	def test_an_untouched_legacy_carton_is_grandfathered(self):
		before = carton_spec(linked_item=None)
		after = carton_spec(linked_item=None, internal_notes="tidied")

		self.assertFalse(cps_rules.item_link_required(before, after))

	def test_computer_paper_grandfathering_is_unchanged(self):
		before = cp_spec(linked_item=None)
		after = cp_spec(linked_item=None, colour_notes="tidied")

		self.assertFalse(cps_rules.item_link_required(before, after))
		self.assertTrue(
			cps_rules.item_link_required(before, cp_spec(linked_item=None, number_of_parts=4))
		)


class TestSnapshotShape(unittest.TestCase):
	def test_the_version_is_declared_and_supported(self):
		# 3 is the newest version this code knows. What matters to Carton is not
		# that number but that 2 is still readable: an order frozen under the
		# Carton release must still raise a Carton job card under this one.
		self.assertEqual(cps_rules.SNAPSHOT_VERSION, 3)
		self.assertIn(1, cps_rules.SUPPORTED_SNAPSHOT_VERSIONS)
		self.assertIn(2, cps_rules.SUPPORTED_SNAPSHOT_VERSIONS)
		self.assertIn(3, cps_rules.SUPPORTED_SNAPSHOT_VERSIONS)

	def test_a_carton_line_submitted_today_still_freezes_at_version_two(self):
		# The deployment-order guarantee. The Label release must not change one
		# byte of what a Carton line writes, because the reader on the other
		# side of the repository boundary may not have shipped version 3 yet and
		# treats an unknown version as unreadable.
		self.assertEqual(cps_rules.snapshot_write_version("Carton"), 2)
		self.assertEqual(carton_snapshot()["_snapshot_version"], 2)

	def test_a_computer_paper_line_submitted_today_still_freezes_at_version_two(self):
		self.assertEqual(cps_rules.snapshot_write_version("Computer Paper"), 2)
		snapshot = cps_rules.build_spec_snapshot(cp_spec(), [], [], "2026-07-02 10:00:00")

		self.assertEqual(snapshot["_snapshot_version"], 2)

	def test_a_carton_snapshot_written_now_is_readable_by_the_carton_release(self):
		# Stated as the round trip that actually matters: what this code writes
		# for a Carton is a version the *previous* release's whitelist accepted.
		self.assertIn(carton_snapshot()["_snapshot_version"], (1, 2))

	def test_carton_has_no_minimum_snapshot_version(self):
		# Carton has been fully frozen since version 2 and the version-3 bump
		# adds nothing to a Carton snapshot, so a version-2 Carton line must not
		# be retroactively refused.
		self.assertIsNone(cps_rules.min_snapshot_version("Carton"))
		self.assertTrue(
			cps_rules.snapshot_describes_product_type({"_snapshot_version": 2}, "Carton")
		)
		self.assertTrue(
			cps_rules.snapshot_describes_product_type({"_snapshot_version": 1}, "Computer Paper")
		)

	def test_computer_paper_freezes_exactly_the_version_one_keys(self):
		snapshot = cps_rules.build_spec_snapshot(cp_spec(), [], [], "2026-07-02 10:00:00")
		scalars = {
			k for k in snapshot if not k.startswith("_") and k not in ("colour_of_parts", "spot_colours")
		}

		self.assertEqual(scalars, set(V1_SNAPSHOT_KEYS))

	def test_every_snapshot_still_carries_every_version_one_key(self):
		# The compatibility floor. A reader that indexes rather than .get()s
		# must not break on a Carton snapshot.
		snapshot = carton_snapshot()

		for key in V1_SNAPSHOT_KEYS:
			self.assertIn(key, snapshot)

	def test_carton_freezes_the_box(self):
		snapshot = carton_snapshot()

		self.assertEqual(snapshot["ply"], "5")
		self.assertEqual(snapshot["flute_type"], "C")
		self.assertEqual(snapshot["ctn_length_mm"], 400)
		self.assertEqual(snapshot["ctn_width_mm"], 300)
		self.assertEqual(snapshot["ctn_height_mm"], 250)
		self.assertEqual(snapshot["idod"], "ID")
		self.assertEqual(snapshot["joint_type"], "Gluing - Machine")
		self.assertEqual(snapshot["1_ply_top_layer_gsm"], 150)
		self.assertEqual(snapshot["5_ply_top_layer_material"], "Kraft")
		self.assertEqual(snapshot["special_instructions_carton"], "Handle stacking mark")

	def test_the_routing_key_and_the_style_stay_separate(self):
		# The whole point. `product_type` routes the line to a Job Card type;
		# `product_type_carton` is the box style. Collapsing them would send
		# Carton lines to the wrong card.
		snapshot = carton_snapshot()

		self.assertEqual(snapshot["product_type"], "Carton")
		self.assertEqual(snapshot["product_type_carton"], "3 Flap RSC")
		self.assertEqual(cps_rules.snapshot_product_type(snapshot), "Carton")

	def test_carton_specific_keys_are_absent_from_a_computer_paper_snapshot(self):
		snapshot = cps_rules.build_spec_snapshot(cp_spec(), [], [], "2026-07-02 10:00:00")

		self.assertNotIn("product_type_carton", snapshot)
		self.assertNotIn("ctn_length_mm", snapshot)

	def test_an_unknown_type_freezes_the_version_one_set(self):
		spec = {"product_type": "Exercise Books", "specification_name": "EB 96pp"}
		snapshot = cps_rules.build_spec_snapshot(spec, [], [], "2026-07-02 10:00:00")
		scalars = {
			k for k in snapshot if not k.startswith("_") and k not in ("colour_of_parts", "spot_colours")
		}

		self.assertEqual(scalars, set(V1_SNAPSHOT_KEYS))

	def test_provenance_is_recorded(self):
		snapshot = carton_snapshot()

		self.assertEqual(snapshot["_snapshot_version"], 2)
		self.assertEqual(snapshot["_cps"], "CTN-SPEC-00007")
		self.assertEqual(snapshot["_cps_modified"], "2026-07-01 09:15:00")
		self.assertEqual(snapshot["_taken_at"], "2026-07-02 10:00:00")

	def test_both_tables_are_always_present(self):
		snapshot = carton_snapshot()

		self.assertEqual(snapshot["colour_of_parts"], [])
		self.assertEqual(snapshot["spot_colours"], [])

	def test_spot_colours_are_carried_for_carton_too(self):
		snapshot = cps_rules.build_spec_snapshot(
			carton_spec(),
			[],
			[{"pantone_code": "185 C", "pantone_name": "Red", "cmyk_k": 0}],
			"2026-07-02 10:00:00",
		)

		self.assertEqual(len(snapshot["spot_colours"]), 1)
		self.assertEqual(snapshot["spot_colours"][0]["pantone_code"], "185 C")
		self.assertIsNone(snapshot["spot_colours"][0]["hex_preview"])


class TestSnapshotVersionGate(unittest.TestCase):
	def test_reads_the_declared_version(self):
		self.assertEqual(cps_rules.snapshot_version({"_snapshot_version": 1}), 1)
		self.assertEqual(cps_rules.snapshot_version({"_snapshot_version": "2"}), 2)

	def test_an_undeclared_version_is_none_not_one(self):
		self.assertIsNone(cps_rules.snapshot_version({}))
		self.assertIsNone(cps_rules.snapshot_version({"_snapshot_version": "two"}))
		self.assertIsNone(cps_rules.snapshot_version(None))

	def test_version_one_orders_are_still_cardable(self):
		self.assertTrue(cps_rules.snapshot_version_supported({"_snapshot_version": 1}))
		self.assertTrue(cps_rules.snapshot_version_supported({"_snapshot_version": 2}))

	def test_a_future_version_is_refused(self):
		self.assertFalse(cps_rules.snapshot_version_supported({"_snapshot_version": 4}))
		self.assertFalse(cps_rules.snapshot_version_supported({}))


class TestCartonJobCardMap(unittest.TestCase):
	def test_every_frozen_carton_field_is_either_mapped_or_excused(self):
		# The guarantee behind "the card is proved against everything the order
		# froze". This is the assertion that makes it structural.
		self.assertEqual(
			cps_rules.unmapped_snapshot_keys("Carton", cps_rules.CARTON_SNAPSHOT_JC_MAP),
			[],
		)

	def test_the_routing_key_is_never_written_onto_a_card(self):
		mapped_keys = {k for k, _f, _l in cps_rules.CARTON_SNAPSHOT_JC_MAP}

		self.assertNotIn("product_type", mapped_keys)
		self.assertIn("product_type", cps_rules.SNAPSHOT_KEYS_NOT_ON_JOB_CARD)

	def test_the_style_is_renamed_exactly_once(self):
		targets = {k: f for k, f, _l in cps_rules.CARTON_SNAPSHOT_JC_MAP}

		self.assertEqual(targets["product_type_carton"], "product_type")

	def test_the_shared_packing_fields_are_renamed(self):
		targets = {k: f for k, f, _l in cps_rules.CARTON_SNAPSHOT_JC_MAP}

		self.assertEqual(targets["standard_packing"], "packing")
		self.assertEqual(targets["standard_weight_per_carton"], "weight_per_carton")

	def test_no_two_snapshot_keys_write_the_same_card_field(self):
		card_fields = [f for _k, f, _l in cps_rules.CARTON_SNAPSHOT_JC_MAP]

		self.assertEqual(len(card_fields), len(set(card_fields)))

	def test_every_entry_carries_a_label(self):
		for _key, _field, label in cps_rules.CARTON_SNAPSHOT_JC_MAP:
			self.assertTrue(label)

	def test_a_missing_target_is_reported_not_skipped(self):
		present = {f for _k, f, _l in cps_rules.CARTON_SNAPSHOT_JC_MAP} - {"packing", "idod"}
		missing = cps_rules.unmapped_jc_targets(
			cps_rules.CARTON_SNAPSHOT_JC_MAP, lambda f: f in present
		)

		self.assertEqual(sorted(missing), ["idod", "packing"])

	def test_a_complete_doctype_reports_nothing_missing(self):
		self.assertEqual(
			cps_rules.unmapped_jc_targets(cps_rules.CARTON_SNAPSHOT_JC_MAP, lambda f: True),
			[],
		)


class TestCartonSnapshotMismatches(unittest.TestCase):
	def test_a_faithful_card_has_no_mismatches(self):
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				carton_card(), carton_snapshot(), cps_rules.CARTON_SNAPSHOT_JC_MAP
			),
			[],
		)

	def test_works_on_objects_as_well_as_dicts(self):
		class Doc:
			def __init__(self, values):
				self.__dict__.update(values)

		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				Doc(carton_card()), carton_snapshot(), cps_rules.CARTON_SNAPSHOT_JC_MAP
			),
			[],
		)

	def test_a_resized_box_is_refused(self):
		found = cps_rules.jc_snapshot_mismatches(
			carton_card(ctn_length_mm=420), carton_snapshot(), cps_rules.CARTON_SNAPSHOT_JC_MAP
		)

		self.assertEqual(fields(found), ["ctn_length_mm"])
		self.assertEqual(found[0].found, 420)
		self.assertEqual(found[0].expected, 400)
		self.assertEqual(found[0].label, "Carton Length (mm)")

	def test_a_changed_board_is_refused(self):
		found = cps_rules.jc_snapshot_mismatches(
			carton_card(**{"1_ply_top_layer_material": "Kraft"}),
			carton_snapshot(),
			cps_rules.CARTON_SNAPSHOT_JC_MAP,
		)

		self.assertEqual(fields(found), ["1_ply_top_layer_material"])

	def test_the_style_is_compared_against_the_carton_style_not_the_routing_key(self):
		# A card whose product_type says "Carton" has copied the wrong key.
		found = cps_rules.jc_snapshot_mismatches(
			carton_card(product_type="Carton"),
			carton_snapshot(),
			cps_rules.CARTON_SNAPSHOT_JC_MAP,
		)

		self.assertEqual(fields(found), ["product_type"])
		self.assertEqual(found[0].expected, "3 Flap RSC")

	def test_numbers_compare_as_numbers(self):
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				carton_card(ctn_length_mm=400.0, weight_per_carton="18.5"),
				carton_snapshot(),
				cps_rules.CARTON_SNAPSHOT_JC_MAP,
			),
			[],
		)

	def test_a_cleared_check_and_a_zero_are_the_same_answer(self):
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				carton_card(numbering_required=None),
				carton_snapshot(numbering_required=0),
				cps_rules.CARTON_SNAPSHOT_JC_MAP,
			),
			[],
		)

	def test_blank_and_absent_are_the_same_absence(self):
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				carton_card(colour_notes=""),
				carton_snapshot(colour_notes=None),
				cps_rules.CARTON_SNAPSHOT_JC_MAP,
			),
			[],
		)

	def test_a_blanked_value_is_still_a_mismatch(self):
		found = cps_rules.jc_snapshot_mismatches(
			carton_card(flute_type=None), carton_snapshot(), cps_rules.CARTON_SNAPSHOT_JC_MAP
		)

		self.assertEqual(fields(found), ["flute_type"])

	def test_an_empty_card_disagrees_on_everything_that_has_a_value(self):
		found = cps_rules.jc_snapshot_mismatches(
			{}, carton_snapshot(), cps_rules.CARTON_SNAPSHOT_JC_MAP
		)

		# uses_m / uses_y are 0 on the specification, so a blank card agrees
		# with them; everything else disagrees.
		self.assertNotIn("uses_m", fields(found))
		self.assertIn("ply", fields(found))
		self.assertIn("product_type", fields(found))
		self.assertIn("packing", fields(found))

	def test_every_mismatch_is_reported_not_just_the_first(self):
		found = cps_rules.jc_snapshot_mismatches(
			carton_card(ply="3", flute_type="B", idod="OD"),
			carton_snapshot(),
			cps_rules.CARTON_SNAPSHOT_JC_MAP,
		)

		self.assertEqual(fields(found), ["flute_type", "idod", "ply"])

	def test_an_empty_map_checks_nothing(self):
		# Computer Paper's setting: this check does not apply to that card.
		self.assertEqual(cps_rules.jc_snapshot_mismatches(carton_card(), carton_snapshot(), ()), [])

	def test_a_non_dict_snapshot_checks_nothing(self):
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				carton_card(), None, cps_rules.CARTON_SNAPSHOT_JC_MAP
			),
			[],
		)

	def test_fields_outside_the_map_are_left_to_production(self):
		# Flap, board plan, knife gap, machine: computed or set on the shop
		# floor, not sold. Nothing in the snapshot speaks to them.
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				carton_card(ctn_flap_mm=153, board_width_planned_mm=1480, knife_gap_mm=4),
				carton_snapshot(),
				cps_rules.CARTON_SNAPSHOT_JC_MAP,
			),
			[],
		)


class TestCustomerFieldIndirection(unittest.TestCase):
	"""Job Card Carton calls its customer link ``customer_name``."""

	ORDER = {"name": "SAL-ORD-0009", "docstatus": 1, "customer": "CUST-0042"}
	LINE = {
		"name": "SOI-0009",
		"item_code": "CTN-5PLY-MANGO",
		"qty": 2000.0,
		"rate": 41.5,
		"custom_cps": "CTN-SPEC-00007",
		"custom_price_source": cps_rules.SOURCE_CPS_PRICE,
		"custom_spec_snapshot": "{}",
		"custom_spec_snapshot_at": "2026-07-02 10:00:00",
	}

	def base_card(self, **overrides):
		values = {
			"customer_name": "CUST-0042",
			"item_code": "CTN-5PLY-MANGO",
			"customer_product_spec": "CTN-SPEC-00007",
			"rate": 41.5,
			"price_source": cps_rules.SOURCE_CPS_PRICE,
			"so_qty": 2000.0,
			"spec_snapshot": "{}",
			"spec_snapshot_at": "2026-07-02 10:00:00",
		}
		values.update(overrides)
		return values

	def test_a_carton_card_passes_on_its_own_customer_field(self):
		self.assertEqual(
			cps_rules.jc_line_mismatches(
				self.base_card(), self.ORDER, self.LINE, 3, "customer_name"
			),
			[],
		)

	def test_the_wrong_customer_is_reported_against_the_field_the_card_has(self):
		found = cps_rules.jc_line_mismatches(
			self.base_card(customer_name="CUST-9999"), self.ORDER, self.LINE, 3, "customer_name"
		)

		self.assertEqual(fields(found), ["customer_name"])
		self.assertEqual(found[0].expected, "CUST-0042")

	def test_the_default_is_still_computer_papers_field(self):
		# Regression: every existing caller passes no customer_field.
		found = cps_rules.jc_line_mismatches(
			{"customer": "CUST-0042"}, self.ORDER, self.LINE
		)

		self.assertNotIn("customer", fields(found))

	def test_a_carton_card_read_under_the_default_looks_wrong(self):
		# Which is exactly why the field is configuration and not a guess.
		found = cps_rules.jc_line_mismatches(self.base_card(), self.ORDER, self.LINE)

		self.assertIn("customer", fields(found))


SPOT_A = {
	"pantone_code": "185 C",
	"pantone_name": "Bright Red",
	"hex_preview": "#E4002B",
	"cmyk_c": 0,
	"cmyk_m": 91,
	"cmyk_y": 76,
	"cmyk_k": 0,
	"notes": "Brand red",
}

SPOT_B = {
	"pantone_code": "2945 C",
	"pantone_name": "Corporate Blue",
	"hex_preview": "#005EB8",
	"cmyk_c": 100,
	"cmyk_m": 56,
	"cmyk_y": 0,
	"cmyk_k": 21,
	"notes": None,
}


def spot_snapshot(*rows):
	"""A Carton snapshot whose frozen spot colours are exactly ``rows``."""
	return carton_snapshot(spot_colours=[dict(row) for row in rows])


def card_rows(*rows):
	"""Card-side grid rows, numbered as a child table always is."""
	return [dict(row, idx=position) for position, row in enumerate(rows, start=1)]


def table_mismatches(card_spot_rows, snapshot):
	return cps_rules.jc_table_mismatches(
		{"spot_colours": card_spot_rows}, snapshot, cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP
	)


class TestSpotColourTableMap(unittest.TestCase):
	"""The map itself, before anything is compared with it."""

	def test_the_row_fields_are_exactly_what_the_snapshot_freezes(self):
		# The guarantee behind "the grid is proved against everything the order
		# froze". A field added to SNAPSHOT_SPOT_FIELDS and forgotten in the map
		# fails here rather than going unchecked forever.
		self.assertEqual(
			tuple(field for field, _label in cps_rules.SPOT_COLOUR_ROW_FIELDS),
			cps_rules.SNAPSHOT_SPOT_FIELDS,
		)

	def test_every_row_field_carries_a_label(self):
		for _field, label in cps_rules.SPOT_COLOUR_ROW_FIELDS:
			self.assertTrue(label)

	def test_carton_maps_the_grid_it_actually_has(self):
		# A box has no parts, so colour_of_parts is deliberately absent.
		self.assertEqual(
			[(key, field) for key, field, _l, _r in cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP],
			[("spot_colours", "spot_colours")],
		)

	def test_a_missing_grid_is_reported_not_skipped(self):
		self.assertEqual(
			cps_rules.unmapped_jc_table_targets(
				cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP, lambda f: False
			),
			["spot_colours"],
		)

	def test_a_complete_doctype_reports_nothing_missing(self):
		self.assertEqual(
			cps_rules.unmapped_jc_table_targets(
				cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP, lambda f: True
			),
			[],
		)


class TestSpotColourTableMismatches(unittest.TestCase):
	"""A Carton card is proved against the colours the order froze, row by row."""

	def test_a_faithful_grid_has_no_mismatches(self):
		self.assertEqual(
			table_mismatches(card_rows(SPOT_A, SPOT_B), spot_snapshot(SPOT_A, SPOT_B)), []
		)

	def test_no_colours_either_side_is_no_mismatch(self):
		self.assertEqual(table_mismatches([], spot_snapshot()), [])

	def test_an_added_colour_is_refused(self):
		found = table_mismatches(card_rows(SPOT_A, SPOT_B), spot_snapshot(SPOT_A))

		self.assertEqual(fields(found), ["spot_colours"])
		self.assertEqual(found[0].label, "Spot Colour Rows")
		self.assertEqual((found[0].found, found[0].expected), (2, 1))

	def test_a_dropped_colour_is_refused(self):
		found = table_mismatches(card_rows(SPOT_A), spot_snapshot(SPOT_A, SPOT_B))

		self.assertEqual((found[0].found, found[0].expected), (1, 2))

	def test_an_emptied_grid_is_refused(self):
		found = table_mismatches([], spot_snapshot(SPOT_A))

		self.assertEqual((found[0].found, found[0].expected), (0, 1))

	def test_a_count_difference_is_reported_alone(self):
		# Every row after an insertion is merely shifted; reporting each of them
		# would bury the one fact the reader can act on.
		found = table_mismatches(card_rows(SPOT_B, SPOT_A, SPOT_B), spot_snapshot(SPOT_A, SPOT_B))

		self.assertEqual(len(found), 1)
		self.assertEqual(found[0].field, "spot_colours")

	def test_a_retyped_pantone_is_refused(self):
		found = table_mismatches(
			card_rows(SPOT_A, dict(SPOT_B, pantone_code="2955 C")),
			spot_snapshot(SPOT_A, SPOT_B),
		)

		self.assertEqual(fields(found), ["spot_colours[2].pantone_code"])
		self.assertEqual(found[0].label, "Spot Colour row 2 Pantone Code")
		self.assertEqual(found[0].found, "2955 C")
		self.assertEqual(found[0].expected, "2945 C")

	def test_a_retuned_ink_mix_is_refused(self):
		found = table_mismatches(
			card_rows(dict(SPOT_A, cmyk_m=80)), spot_snapshot(SPOT_A)
		)

		self.assertEqual(fields(found), ["spot_colours[1].cmyk_m"])
		self.assertEqual(found[0].label, "Spot Colour row 1 CMYK M")

	def test_every_disagreeing_field_is_reported_not_just_the_first(self):
		found = table_mismatches(
			card_rows(dict(SPOT_A, pantone_code="X", notes="Y")), spot_snapshot(SPOT_A)
		)

		self.assertEqual(
			fields(found), ["spot_colours[1].notes", "spot_colours[1].pantone_code"]
		)

	def test_swapping_two_colours_over_is_refused(self):
		# The order is part of the value: two colours swapped is a different
		# print order and a different plate sequence, not the same grid.
		found = table_mismatches(card_rows(SPOT_B, SPOT_A), spot_snapshot(SPOT_A, SPOT_B))

		self.assertTrue(found)
		self.assertTrue(all(m.field.startswith("spot_colours[") for m in found))


class TestSpotColourRowOrdering(unittest.TestCase):
	"""Both sides are put in a stable order before anything is compared."""

	def test_rows_are_read_in_idx_order_not_payload_order(self):
		# A REST payload may list the grid in any order; idx is its real
		# position, and a card that states its rows out of order is still the
		# same card.
		shuffled = [dict(SPOT_B, idx=2), dict(SPOT_A, idx=1)]

		self.assertEqual(table_mismatches(shuffled, spot_snapshot(SPOT_A, SPOT_B)), [])

	def test_snapshot_rows_keep_the_order_they_were_frozen_in(self):
		# Snapshot rows are plain dicts with no idx at all — their position in
		# the list is their order, and it must not be reshuffled.
		self.assertEqual(
			table_mismatches(card_rows(SPOT_A, SPOT_B), spot_snapshot(SPOT_A, SPOT_B)), []
		)
		self.assertTrue(table_mismatches(card_rows(SPOT_A, SPOT_B), spot_snapshot(SPOT_B, SPOT_A)))

	def test_a_row_with_no_idx_keeps_its_arrival_position(self):
		self.assertEqual(
			table_mismatches([dict(SPOT_A), dict(SPOT_B)], spot_snapshot(SPOT_A, SPOT_B)), []
		)

	def test_idx_is_read_however_it_was_serialised(self):
		shuffled = [dict(SPOT_B, idx="2"), dict(SPOT_A, idx="1")]

		self.assertEqual(table_mismatches(shuffled, spot_snapshot(SPOT_A, SPOT_B)), [])


class TestSpotColourValueNormalisation(unittest.TestCase):
	"""The same value written two ways is not a disagreement."""

	def test_numbers_compare_as_numbers(self):
		# An Int field read back out of JSON is a float, and 91 is not 91.0's
		# disagreement.
		self.assertEqual(
			table_mismatches(card_rows(dict(SPOT_A, cmyk_m=91.0)), spot_snapshot(SPOT_A)), []
		)

	def test_numeric_text_compares_as_a_number(self):
		self.assertEqual(
			table_mismatches(card_rows(dict(SPOT_A, cmyk_m="91")), spot_snapshot(SPOT_A)), []
		)

	def test_blank_and_absent_are_the_same_absence(self):
		# SPOT_B froze `notes` as None; a card carrying "" has not changed it.
		self.assertEqual(
			table_mismatches(card_rows(dict(SPOT_B, notes="")), spot_snapshot(SPOT_B)), []
		)

	def test_a_dropped_key_on_the_card_matches_a_blank_in_the_snapshot(self):
		row = {k: v for k, v in SPOT_B.items() if k != "notes"}

		self.assertEqual(table_mismatches(card_rows(row), spot_snapshot(SPOT_B)), [])

	def test_surrounding_whitespace_is_not_a_change(self):
		self.assertEqual(
			table_mismatches(
				card_rows(dict(SPOT_A, pantone_code="  185 C  ")), spot_snapshot(SPOT_A)
			),
			[],
		)

	def test_a_zero_and_a_cleared_value_are_the_same_answer(self):
		self.assertEqual(
			table_mismatches(card_rows(dict(SPOT_A, cmyk_c=None)), spot_snapshot(SPOT_A)), []
		)

	def test_a_blanked_pantone_is_still_a_mismatch(self):
		found = table_mismatches(card_rows(dict(SPOT_A, pantone_code="")), spot_snapshot(SPOT_A))

		self.assertEqual(fields(found), ["spot_colours[1].pantone_code"])

	def test_works_on_objects_as_well_as_dicts(self):
		class Row:
			def __init__(self, values):
				self.__dict__.update(values)

		class Card:
			def __init__(self, rows):
				self.spot_colours = rows

		self.assertEqual(
			cps_rules.jc_table_mismatches(
				Card([Row(dict(SPOT_A, idx=1))]),
				spot_snapshot(SPOT_A),
				cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP,
			),
			[],
		)


class TestSpotColourTableEdgeCases(unittest.TestCase):
	def test_an_empty_map_checks_nothing(self):
		# Computer Paper's map is empty, and its behaviour is exactly what it
		# was: a grid nobody declared is a grid nobody proves.
		self.assertEqual(cps_rules.jc_table_mismatches({"spot_colours": card_rows(SPOT_A)}, {}, ()), [])

	def test_a_non_dict_snapshot_checks_nothing(self):
		self.assertEqual(
			cps_rules.jc_table_mismatches(
				{"spot_colours": card_rows(SPOT_A)},
				"not a snapshot",
				cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP,
			),
			[],
		)

	def test_a_snapshot_with_no_grid_key_means_no_rows(self):
		# Snapshot v2 compatibility: an absent child table is a real value —
		# "no rows" — and a card claiming colours against it is refused.
		snapshot = carton_snapshot()
		snapshot.pop("spot_colours")

		self.assertEqual(table_mismatches([], snapshot), [])
		self.assertEqual(table_mismatches(card_rows(SPOT_A), snapshot)[0].expected, 0)

	def test_a_null_grid_on_the_card_is_no_rows(self):
		self.assertEqual(table_mismatches(None, spot_snapshot()), [])

	def test_a_version_one_carton_snapshot_still_reads(self):
		# v1 froze the colour tables but nothing about the box. Its grid is
		# still proved; the scalars it never carried are left alone by
		# jc_snapshot_mismatches, which is tested separately.
		v1 = {"_snapshot_version": 1, "product_type": "Carton", "spot_colours": [dict(SPOT_A)]}

		self.assertTrue(cps_rules.snapshot_version_supported(v1))
		self.assertEqual(table_mismatches(card_rows(SPOT_A), v1), [])
		self.assertEqual(fields(table_mismatches([], v1)), ["spot_colours"])


class TestOrderDateAndLpo(unittest.TestCase):
	"""``order_date`` and ``lpo_number`` are proved against the order header.

	Both are copied off the Sales Order by the creation path and were, until
	this release, the only values on an order-derived card that nothing checked.
	They are read-only on the form, which stops a Desk user and stops nothing
	else — a REST POST writes them perfectly happily.
	"""

	ORDER = {
		"name": "SAL-ORD-0009",
		"docstatus": 1,
		"customer": "CUST-0042",
		"transaction_date": "2026-07-02",
		"po_no": "LPO-88213",
	}
	LINE = {
		"name": "SOI-0009",
		"item_code": "CTN-5PLY-MANGO",
		"qty": 2000.0,
		"rate": 41.5,
		"custom_cps": "CTN-SPEC-00007",
		"custom_price_source": cps_rules.SOURCE_CPS_PRICE,
		"custom_spec_snapshot": "{}",
		"custom_spec_snapshot_at": "2026-07-02 10:00:00",
	}

	def card(self, **overrides):
		values = {
			"customer_name": "CUST-0042",
			"item_code": "CTN-5PLY-MANGO",
			"customer_product_spec": "CTN-SPEC-00007",
			"rate": 41.5,
			"price_source": cps_rules.SOURCE_CPS_PRICE,
			"so_qty": 2000.0,
			"spec_snapshot": "{}",
			"spec_snapshot_at": "2026-07-02 10:00:00",
			"order_date": "2026-07-02",
			"lpo_number": "LPO-88213",
		}
		values.update(overrides)
		return values

	def mismatches(self, order=None, **overrides):
		return cps_rules.jc_line_mismatches(
			self.card(**overrides), order or self.ORDER, self.LINE, 3, "customer_name"
		)

	def test_a_faithful_card_has_no_mismatches(self):
		self.assertEqual(self.mismatches(), [])

	def test_a_retyped_order_date_is_refused(self):
		found = self.mismatches(order_date="2026-06-02")

		self.assertEqual(fields(found), ["order_date"])
		self.assertEqual(found[0].label, "Order Date")
		self.assertEqual(found[0].expected, "2026-07-02")

	def test_a_blanked_order_date_is_refused(self):
		self.assertEqual(fields(self.mismatches(order_date=None)), ["order_date"])

	def test_somebody_elses_lpo_is_refused(self):
		found = self.mismatches(lpo_number="LPO-00001")

		self.assertEqual(fields(found), ["lpo_number"])
		self.assertEqual(found[0].label, "LPO Number")
		self.assertEqual(found[0].expected, "LPO-88213")

	def test_a_blanked_lpo_is_refused(self):
		self.assertEqual(fields(self.mismatches(lpo_number="")), ["lpo_number"])

	def test_an_order_with_no_lpo_expects_none_on_the_card(self):
		order = dict(self.ORDER, po_no=None)

		self.assertEqual(self.mismatches(order=order, lpo_number=None), [])
		self.assertEqual(self.mismatches(order=order, lpo_number=""), [])
		self.assertEqual(fields(self.mismatches(order=order, lpo_number="LPO-1")), ["lpo_number"])

	def test_the_lpo_is_compared_by_content_not_by_whitespace(self):
		self.assertEqual(self.mismatches(lpo_number="  LPO-88213 "), [])

	def test_a_date_object_and_its_string_are_the_same_day(self):
		from datetime import date

		order = dict(self.ORDER, transaction_date=date(2026, 7, 2))

		self.assertEqual(self.mismatches(order=order), [])
		self.assertEqual(self.mismatches(order=order, order_date=date(2026, 7, 2)), [])

	def test_a_datetime_serialisation_still_compares_by_day(self):
		self.assertEqual(self.mismatches(order_date="2026-07-02 00:00:00"), [])

	def test_computer_paper_is_held_to_the_same_two_fields(self):
		# The check lives on the shared line comparison, so it applies to every
		# order-derived card. Its Computer Paper *snapshot* behaviour is
		# untouched — that is JC_SNAPSHOT_FIELD_MAP, which stays empty.
		card = self.card(customer="CUST-0042", order_date="2026-01-01")
		card.pop("customer_name")

		self.assertEqual(fields(cps_rules.jc_line_mismatches(card, self.ORDER, self.LINE)), ["order_date"])

	def test_both_fields_are_reported_together(self):
		found = self.mismatches(order_date="2026-06-02", lpo_number="LPO-1")

		self.assertEqual(fields(found), ["lpo_number", "order_date"])


class TestJobCardCartonDocType(unittest.TestCase):
	"""The DocType and the maps, read off disk and compared.

	The Compass write loop guards every field with ``meta.has_field``, so a
	target the DocType does not have produces a card with quiet holes rather
	than an error. This is the assertion that keeps the two in step without a
	bench.
	"""

	@classmethod
	def setUpClass(cls):
		import json
		import os

		path = os.path.join(
			os.path.dirname(os.path.abspath(__file__)),
			"doctype", "job_card_carton", "job_card_carton.json",
		)
		with open(path) as handle:
			cls.doctype = json.load(handle)
		cls.by_name = {f["fieldname"]: f for f in cls.doctype["fields"]}

	def test_every_mapped_scalar_target_exists_on_the_card(self):
		self.assertEqual(
			cps_rules.unmapped_jc_targets(
				cps_rules.CARTON_SNAPSHOT_JC_MAP, lambda f: f in self.by_name
			),
			[],
		)

	def test_every_mapped_table_target_exists_on_the_card(self):
		self.assertEqual(
			cps_rules.unmapped_jc_table_targets(
				cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP, lambda f: f in self.by_name
			),
			[],
		)

	def test_the_spot_colour_grid_is_the_shared_child_doctype(self):
		self.assertEqual(self.by_name["spot_colours"]["fieldtype"], "Table")
		self.assertEqual(self.by_name["spot_colours"]["options"], "Spot Colour")

	def test_the_line_level_fields_the_comparison_needs_all_exist(self):
		for fieldname in (
			"sales_order", "sales_order_item", "item_code", "customer_name",
			"customer_product_spec", "price_source", "rate", "so_qty",
			"spec_snapshot", "spec_snapshot_at", "order_date", "lpo_number",
		):
			self.assertIn(fieldname, self.by_name)

	def test_order_derived_header_fields_are_read_only_on_the_form(self):
		for fieldname in ("order_date", "lpo_number"):
			self.assertEqual(
				self.by_name[fieldname].get("read_only_depends_on"),
				"eval:doc.sales_order",
				fieldname,
			)

	def test_they_stay_editable_on_a_card_with_no_order(self):
		# The three legacy creation paths — the Desk form, the Compass
		# hand-built screen, and history — have no Sales Order and genuinely
		# type these. A flat read_only would break all three, which is why the
		# lock is conditional and the *server* check is what makes it true.
		for fieldname in ("order_date", "lpo_number"):
			self.assertFalse(self.by_name[fieldname].get("read_only"), fieldname)

	def test_the_snapshot_the_card_is_proved_against_is_not_hand_editable(self):
		for fieldname in ("spec_snapshot", "spec_snapshot_at", "sales_order", "rate", "so_qty"):
			self.assertEqual(self.by_name[fieldname].get("read_only"), 1, fieldname)


if __name__ == "__main__":
	unittest.main()
