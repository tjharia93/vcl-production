"""Unit tests for the Label half of the CPS rules.

Plain ``unittest``, no bench, no site, no database — ``cps_rules`` imports
nothing from Frappe. The Frappe-bound half (row locks, throws, rollups, the
legacy flag being re-derived on a real document) lives in ``order_derived.py``
and ``job_card_label.py`` and needs a bench; what is testable without one is the
decision itself, which is here. ``test_label_schema.py`` covers the half that
needs a site.

Three things in this file are regression tests rather than new coverage, and
they are the reason it is worth reading:

* **Computer Paper and Carton must not have moved.** The Label work widened the
  material-field set, the frozen snapshot and the version gate, and the one
  outcome that would make it a bad change is any of those behaving differently
  for a product type that was already in production.
* **Version 2 must still be readable.** An order frozen under the Carton release
  has to raise a job card under this one.
* **The 20 legacy order references must still save.** Those rows are the whole
  difficulty of this release, and the rules that let them through are the rules
  that must not let a forged card through with them.
"""

import unittest

from production_log.job_card_tracking import cps_rules

# Exactly what snapshot version 1 wrote, in its original order. Frozen here as a
# literal rather than imported, so a change to the module is a failing test
# rather than a test that changes with it.
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

# The Label block on Customer Product Specification, as the DocType declares it.
LABEL_CPS_FIELDS = (
	"dies",
	"label_length",
	"label_width",
	"cylinder_teeth",
	"plate_up",
	"plate_round",
	"packing_up",
	"material_type",
	"packing_pieces",
	"gap_between",
	"side_trim",
)

# Every fieldname Job Card Label carries after this release, as a literal. The
# site-dependent half of this assertion — that the DocType really does declare
# these — is in ``test_label_schema.py``; here it makes ``unmapped_jc_targets``
# answerable without a bench.
JC_LABEL_FIELDS = frozenset(
	{
		"amended_from",
		"naming_series",
		"order_date",
		"due_date",
		"customer",
		"lpo_number",
		"customer_product_spec",
		"specification_name",
		"job_size",
		"plate_status",
		"plate_code",
		"quantity_ordered",
		"sales_order",
		"sales_order_item",
		"item_code",
		"legacy_order_reference",
		"rate",
		"price_source",
		"so_qty",
		"spec_snapshot_at",
		"spec_snapshot",
		"ink_type",
		"uses_c",
		"uses_m",
		"uses_y",
		"uses_k",
		"number_of_colours",
		"spot_colours",
		"colour_notes",
		"dies",
		"label_length",
		"label_width",
		"material_type",
		"cylinder_teeth",
		"plate_up",
		"plate_round",
		"packing_up",
		"packing_pieces",
		"gap_between",
		"side_trim",
		"numbering_required",
		"numbering_prefix",
		"numbering_start",
		"numbering_end",
		"numbering_format",
		"standard_packing",
		"weight_per_carton",
		"sales_rep",
		"management_approver",
		"status",
		"job_status",
		"machine",
		"production_remarks",
	}
)


def has_field(fieldname):
	return fieldname in JC_LABEL_FIELDS


def label_spec(**overrides):
	"""A submitted, linked, fully specified Label specification.

	The four ``Data``-typed numerics are written as the strings the
	specification actually stores, because that is the shape the comparison has
	to survive — all 192 live records hold numbers in them and none holds a
	number as a number.
	"""
	values = {
		"name": "LBL-SPEC-00031",
		"modified": "2026-07-01 09:15:00",
		"product_type": "Label",
		"specification_name": "Greenspoon Honey 250g Front",
		"customer": "CUST-0099",
		"job_size": "70x100",
		"linked_item": "LBL-PPW-70X100",
		"numbering_required": 0,
		"standard_packing": "1000 per roll",
		"standard_weight_per_carton": 4.25,
		"ink_type": "Process UV",
		"uses_c": 1,
		"uses_m": 1,
		"uses_y": 1,
		"uses_k": 1,
		"number_of_colours": 5,
		"colour_notes": "One spot plus process",
		"dies": "DIE-00114",
		"label_length": 70.0,
		"label_width": 100.0,
		"material_type": "PP White",
		"cylinder_teeth": "96",
		"plate_up": "4",
		"plate_round": "2",
		"packing_up": "8",
		"packing_pieces": 1000,
		"gap_between": 3.0,
		"side_trim": 2.5,
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


def label_snapshot(spot_colours=None, **overrides):
	snapshot = cps_rules.build_spec_snapshot(
		label_spec(), [], spot_colours or [], "2026-07-02 10:00:00"
	)
	snapshot.update(overrides)
	return snapshot


def label_card(**overrides):
	"""A Job Card Label faithfully populated from :func:`label_snapshot`.

	Numbers where the card declares numbers, so this fixture also exercises the
	``Data``-frozen-against-``Float``-stored comparison that the four tooling
	fields depend on.
	"""
	values = {
		"specification_name": "Greenspoon Honey 250g Front",
		"job_size": "70x100",
		"numbering_required": 0,
		"standard_packing": "1000 per roll",
		"weight_per_carton": 4.25,
		"ink_type": "Process UV",
		"uses_c": 1,
		"uses_m": 1,
		"uses_y": 1,
		"uses_k": 1,
		"number_of_colours": 5,
		"colour_notes": "One spot plus process",
		"dies": "DIE-00114",
		"label_length": 70.0,
		"label_width": 100.0,
		"material_type": "PP White",
		"cylinder_teeth": 96.0,
		"plate_up": 4,
		"plate_round": 2,
		"packing_up": 8,
		"packing_pieces": 1000,
		"gap_between": 3.0,
		"side_trim": 2.5,
	}
	values.update(overrides)
	return values


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
	"pantone_code": "877 C",
	"pantone_name": "Silver",
	"hex_preview": "#8A8D8F",
	"cmyk_c": 0,
	"cmyk_m": 0,
	"cmyk_y": 0,
	"cmyk_k": 45,
	"notes": None,
}


# ---------------------------------------------------------------------------
# Material fields
# ---------------------------------------------------------------------------


class TestLabelMaterialSpecFields(unittest.TestCase):
	def test_the_label_geometry_tooling_and_substrate_are_all_watched(self):
		watched = set(cps_rules.material_spec_fields("Label"))

		for fieldname in (
			"label_length",
			"label_width",
			"gap_between",
			"side_trim",
			"dies",
			"cylinder_teeth",
			"plate_up",
			"plate_round",
			"packing_up",
			"material_type",
		):
			self.assertIn(fieldname, watched)

	def test_packing_pieces_is_not_material(self):
		# It says how many labels go in a pack, which is the same kind of
		# statement as standard_packing - and standard_packing has never been
		# material for any product type.
		self.assertNotIn("packing_pieces", set(cps_rules.material_spec_fields("Label")))
		self.assertNotIn("standard_packing", set(cps_rules.material_spec_fields("Label")))

	def test_label_does_not_watch_other_product_types_fields(self):
		watched = set(cps_rules.material_spec_fields("Label"))

		self.assertNotIn("pay_slip_size", watched)
		self.assertNotIn("number_of_parts", watched)
		self.assertNotIn("ctn_length_mm", watched)
		self.assertNotIn("product_type_carton", watched)

	def test_computer_paper_and_carton_are_unchanged_by_the_label_release(self):
		self.assertEqual(
			set(cps_rules.material_spec_fields("Computer Paper")),
			set(cps_rules.SHARED_MATERIAL_SPEC_FIELDS)
			| set(cps_rules.COMPUTER_PAPER_MATERIAL_SPEC_FIELDS),
		)
		self.assertEqual(
			set(cps_rules.material_spec_fields("Carton")),
			set(cps_rules.SHARED_MATERIAL_SPEC_FIELDS)
			| set(cps_rules.CARTON_MATERIAL_SPEC_FIELDS),
		)

	def test_the_shared_set_is_still_watched_for_label(self):
		watched = set(cps_rules.material_spec_fields("Label"))

		for fieldname in cps_rules.SHARED_MATERIAL_SPEC_FIELDS:
			self.assertIn(fieldname, watched)

	def test_no_duplicates(self):
		watched = cps_rules.material_spec_fields("Label")

		self.assertEqual(len(watched), len(set(watched)))


class TestLabelMaterialSpecChanges(unittest.TestCase):
	def test_a_relabelled_die_is_material(self):
		self.assertEqual(
			cps_rules.material_spec_changes(label_spec(), label_spec(dies="DIE-00115")),
			["dies"],
		)

	def test_a_resized_label_is_material(self):
		self.assertEqual(
			cps_rules.material_spec_changes(label_spec(), label_spec(label_width=105.0)),
			["label_width"],
		)

	def test_a_substrate_change_is_material(self):
		self.assertEqual(
			cps_rules.material_spec_changes(label_spec(), label_spec(material_type="Thermal")),
			["material_type"],
		)

	def test_a_tooling_change_is_material(self):
		self.assertEqual(
			sorted(
				cps_rules.material_spec_changes(
					label_spec(), label_spec(plate_up="6", cylinder_teeth="120")
				)
			),
			["cylinder_teeth", "plate_up"],
		)

	def test_a_packing_note_is_not_material(self):
		self.assertEqual(
			cps_rules.material_spec_changes(
				label_spec(), label_spec(standard_packing="500 per roll", packing_pieces=500)
			),
			[],
		)

	def test_retyping_a_label_as_a_carton_compares_both_sets(self):
		# The union of both versions' product types is watched, so the fields a
		# record is abandoning are compared before they stop counting.
		changed = cps_rules.material_spec_changes(
			label_spec(), label_spec(product_type="Carton", ctn_length_mm=400)
		)

		self.assertIn("product_type", changed)
		self.assertIn("ctn_length_mm", changed)


class TestLabelItemLinkRequirement(unittest.TestCase):
	def test_an_untouched_legacy_label_spec_is_grandfathered(self):
		# 185 of the 192 live Label specifications carry no Item link. None of
		# them may become a blocked save on the day this lands.
		before = label_spec(linked_item=None)
		after = label_spec(linked_item=None, colour_notes="tidied")

		self.assertFalse(cps_rules.item_link_required(before, after))

	def test_a_material_edit_forces_the_link(self):
		before = label_spec(linked_item=None)

		self.assertTrue(
			cps_rules.item_link_required(before, label_spec(linked_item=None, side_trim=3.0))
		)

	def test_a_new_label_spec_must_be_linked(self):
		self.assertTrue(cps_rules.item_link_required(None, label_spec(linked_item=None)))


# ---------------------------------------------------------------------------
# Snapshot shape and version
# ---------------------------------------------------------------------------


class TestLabelSnapshotShape(unittest.TestCase):
	def test_the_version_is_three_and_one_and_two_are_still_readable(self):
		self.assertEqual(cps_rules.SNAPSHOT_VERSION, 3)
		self.assertEqual(cps_rules.SUPPORTED_SNAPSHOT_VERSIONS, (1, 2, 3))

	def test_only_label_freezes_at_version_three(self):
		# The write version is per product type, and this is the whole reason
		# why: the reader on the other side of the repository boundary deploys
		# on its own schedule, so a version number it has never seen must only
		# ever appear on a line that genuinely needs one. Versions 2 and 3 are
		# byte-identical for Computer Paper and Carton, so stamping either of
		# them 3 would buy nothing and cost every line submitted before that
		# reader ships.
		self.assertEqual(cps_rules.snapshot_write_version("Label"), 3)
		self.assertEqual(cps_rules.snapshot_write_version("Carton"), 2)
		self.assertEqual(cps_rules.snapshot_write_version("Computer Paper"), 2)

	def test_an_unknown_product_type_freezes_at_the_base_version(self):
		self.assertEqual(cps_rules.snapshot_write_version("Exercise Books"), 2)
		self.assertEqual(cps_rules.snapshot_write_version(None), 2)

	def test_a_label_line_submitted_today_freezes_at_version_three(self):
		self.assertEqual(label_snapshot()["_snapshot_version"], 3)

	def test_a_carton_or_computer_paper_line_is_unmoved_by_this_release(self):
		# The deployment-order regression. If either of these ever reads 3, a
		# Compass release that supports only 1 and 2 refuses lines it used to
		# accept, for a payload change that does not exist.
		carton = cps_rules.build_spec_snapshot(
			{"product_type": "Carton", "specification_name": "RSC 300x200x150"},
			[],
			[],
			"2026-07-20 09:00:00",
		)
		computer_paper = cps_rules.build_spec_snapshot(
			{"product_type": "Computer Paper", "specification_name": "9.5 x 11 2pt"},
			[],
			[],
			"2026-07-20 09:00:00",
		)

		self.assertEqual(carton["_snapshot_version"], 2)
		self.assertEqual(computer_paper["_snapshot_version"], 2)

	def test_the_written_version_is_always_one_this_code_can_read(self):
		for product_type in ("Computer Paper", "Carton", "Label", "Exercise Books", None):
			with self.subTest(product_type=product_type):
				self.assertIn(
					cps_rules.snapshot_write_version(product_type),
					cps_rules.SUPPORTED_SNAPSHOT_VERSIONS,
				)

	def test_what_a_type_writes_is_never_older_than_what_it_requires(self):
		# The reason the write version is derived from the floor rather than
		# tabulated beside it. Two tables could disagree; this cannot — but the
		# invariant is asserted anyway, because it is the one that would let an
		# order freeze a snapshot its own job card then refuses.
		for product_type in ("Computer Paper", "Carton", "Label"):
			with self.subTest(product_type=product_type):
				written = {"_snapshot_version": cps_rules.snapshot_write_version(product_type)}

				self.assertTrue(
					cps_rules.snapshot_describes_product_type(written, product_type)
				)

	def test_a_label_snapshot_freezes_the_version_one_keys_plus_the_label_block(self):
		snapshot = label_snapshot()
		scalars = {
			k
			for k in snapshot
			if not k.startswith("_") and k not in ("colour_of_parts", "spot_colours")
		}

		self.assertEqual(scalars, set(V1_SNAPSHOT_KEYS) | set(LABEL_CPS_FIELDS))

	def test_every_snapshot_still_carries_every_version_one_key(self):
		# The compatibility floor. A consumer that indexes rather than .get()s
		# must not break on a Label snapshot.
		snapshot = label_snapshot()

		for key in V1_SNAPSHOT_KEYS:
			self.assertIn(key, snapshot)

	def test_the_label_block_is_frozen_verbatim(self):
		snapshot = label_snapshot()

		self.assertEqual(snapshot["dies"], "DIE-00114")
		self.assertEqual(snapshot["label_length"], 70.0)
		self.assertEqual(snapshot["label_width"], 100.0)
		self.assertEqual(snapshot["material_type"], "PP White")
		# Recorded as the specification stores them, not coerced. A snapshot
		# must survive the field being retyped later.
		self.assertEqual(snapshot["cylinder_teeth"], "96")
		self.assertEqual(snapshot["plate_up"], "4")
		self.assertEqual(snapshot["plate_round"], "2")
		self.assertEqual(snapshot["packing_up"], "8")
		self.assertEqual(snapshot["packing_pieces"], 1000)
		self.assertEqual(snapshot["gap_between"], 3.0)
		self.assertEqual(snapshot["side_trim"], 2.5)

	def test_the_die_is_frozen_by_name_and_never_dereferenced(self):
		# The Dies record's own geometry is live master data that can be
		# corrected after an order is sold. Freezing the name records the
		# instruction; freezing the geometry from the specification's own fields
		# records what was agreed.
		snapshot = label_snapshot()

		self.assertEqual(snapshot["dies"], "DIE-00114")
		self.assertNotIn("die_length", snapshot)
		self.assertNotIn("die_width", snapshot)
		self.assertNotIn("dies_doc", snapshot)

	def test_provenance_is_recorded(self):
		snapshot = label_snapshot()

		self.assertEqual(snapshot["_snapshot_version"], 3)
		self.assertEqual(snapshot["_cps"], "LBL-SPEC-00031")
		self.assertEqual(snapshot["_cps_modified"], "2026-07-01 09:15:00")
		self.assertEqual(snapshot["_taken_at"], "2026-07-02 10:00:00")

	def test_both_tables_are_always_present(self):
		snapshot = label_snapshot()

		self.assertEqual(snapshot["colour_of_parts"], [])
		self.assertEqual(snapshot["spot_colours"], [])

	def test_spot_colours_are_carried(self):
		snapshot = label_snapshot(spot_colours=[dict(SPOT_A)])

		self.assertEqual(len(snapshot["spot_colours"]), 1)
		self.assertEqual(snapshot["spot_colours"][0]["pantone_code"], "185 C")
		self.assertEqual(snapshot["spot_colours"][0]["cmyk_m"], 91)

	def test_computer_paper_still_freezes_exactly_the_version_one_keys(self):
		# The regression that matters most: adding Label must not have widened
		# what a Computer Paper order captures.
		snapshot = cps_rules.build_spec_snapshot(cp_spec(), [], [], "2026-07-02 10:00:00")
		scalars = {
			k
			for k in snapshot
			if not k.startswith("_") and k not in ("colour_of_parts", "spot_colours")
		}

		self.assertEqual(scalars, set(V1_SNAPSHOT_KEYS))

	def test_an_unknown_product_type_still_gets_the_version_one_set_only(self):
		self.assertEqual(
			cps_rules.snapshot_scalar_fields("Exercise Books"), cps_rules.SNAPSHOT_V1_SCALARS
		)


class TestSnapshotVersionFloor(unittest.TestCase):
	def test_label_needs_version_three(self):
		self.assertEqual(cps_rules.min_snapshot_version("Label"), 3)
		self.assertEqual(cps_rules.min_snapshot_version("  Label  "), 3)

	def test_nothing_else_has_a_floor(self):
		for product_type in ("Computer Paper", "Carton", "Exercise Books", None, "", "   "):
			self.assertIsNone(cps_rules.min_snapshot_version(product_type))

	def test_a_version_two_label_line_cannot_support_a_label_card(self):
		# Readable, and still not enough: version 2 froze nothing about a label.
		snapshot = {"_snapshot_version": 2, "product_type": "Label"}

		self.assertTrue(cps_rules.snapshot_version_supported(snapshot))
		self.assertFalse(cps_rules.snapshot_describes_product_type(snapshot, "Label"))

	def test_a_version_three_label_line_does(self):
		self.assertTrue(cps_rules.snapshot_describes_product_type(label_snapshot(), "Label"))

	def test_an_unversioned_snapshot_does_not_satisfy_a_floor(self):
		self.assertFalse(cps_rules.snapshot_describes_product_type({}, "Label"))
		self.assertFalse(
			cps_rules.snapshot_describes_product_type({"_snapshot_version": "three"}, "Label")
		)

	def test_a_type_without_a_floor_accepts_anything_readable(self):
		for snapshot in ({}, {"_snapshot_version": 1}, {"_snapshot_version": 2}):
			self.assertTrue(cps_rules.snapshot_describes_product_type(snapshot, "Carton"))
			self.assertTrue(cps_rules.snapshot_describes_product_type(snapshot, None))

	def test_a_future_version_would_still_satisfy_the_floor_but_not_the_gate(self):
		# The two questions are independent and both have to be asked: version 4
		# is new enough to describe a Label and is not readable by this code.
		snapshot = {"_snapshot_version": 4}

		self.assertTrue(cps_rules.snapshot_describes_product_type(snapshot, "Label"))
		self.assertFalse(cps_rules.snapshot_version_supported(snapshot))


# ---------------------------------------------------------------------------
# Snapshot -> Job Card mapping
# ---------------------------------------------------------------------------


class TestLabelJobCardMap(unittest.TestCase):
	def test_every_frozen_label_field_is_either_mapped_or_excused(self):
		# The guarantee behind "the card is proved against everything the order
		# froze". An empty list is the only acceptable answer.
		self.assertEqual(
			cps_rules.unmapped_snapshot_keys("Label", cps_rules.LABEL_SNAPSHOT_JC_MAP), []
		)

	def test_every_mapped_target_exists_on_the_card(self):
		self.assertEqual(
			cps_rules.unmapped_jc_targets(cps_rules.LABEL_SNAPSHOT_JC_MAP, has_field), []
		)

	def test_every_mapped_table_target_exists_on_the_card(self):
		self.assertEqual(
			cps_rules.unmapped_jc_table_targets(cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP, has_field),
			[],
		)

	def test_standard_packing_maps_onto_itself(self):
		# Unlike Carton, which calls the same value `packing`. Renaming a field
		# on a live submittable DocType for symmetry is not worth the risk.
		mapping = dict((k, v) for k, v, _label in cps_rules.LABEL_SNAPSHOT_JC_MAP)

		self.assertEqual(mapping["standard_packing"], "standard_packing")

	def test_weight_per_carton_is_the_one_rename(self):
		mapping = dict((k, v) for k, v, _label in cps_rules.LABEL_SNAPSHOT_JC_MAP)
		renames = [k for k, v in mapping.items() if k != v]

		self.assertEqual(renames, ["standard_weight_per_carton"])
		self.assertEqual(mapping["standard_weight_per_carton"], "weight_per_carton")

	def test_the_die_maps_by_name_only(self):
		mapping = dict((k, v) for k, v, _label in cps_rules.LABEL_SNAPSHOT_JC_MAP)

		self.assertEqual(mapping["dies"], "dies")

	def test_no_snapshot_key_is_mapped_twice(self):
		keys = [k for k, _field, _label in cps_rules.LABEL_SNAPSHOT_JC_MAP]

		self.assertEqual(len(keys), len(set(keys)))

	def test_no_card_field_is_written_twice(self):
		fields = [f for _key, f, _label in cps_rules.LABEL_SNAPSHOT_JC_MAP]

		self.assertEqual(len(fields), len(set(fields)))

	def test_the_routing_key_is_never_copied_onto_the_card(self):
		fields = {f for _key, f, _label in cps_rules.LABEL_SNAPSHOT_JC_MAP}

		self.assertNotIn("product_type", fields)

	def test_every_entry_carries_a_readable_label(self):
		for _key, _field, label in cps_rules.LABEL_SNAPSHOT_JC_MAP:
			self.assertTrue(label and label.strip())

	def test_the_carton_map_is_untouched(self):
		self.assertEqual(
			cps_rules.unmapped_snapshot_keys("Carton", cps_rules.CARTON_SNAPSHOT_JC_MAP), []
		)


class TestLabelJobCardTableMap(unittest.TestCase):
	def test_only_the_spot_colour_grid_is_carried(self):
		self.assertEqual(
			[key for key, _f, _l, _rf in cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP], ["spot_colours"]
		)

	def test_a_label_has_no_parts_grid(self):
		fields = {f for _k, f, _l, _rf in cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP}

		self.assertNotIn("colour_of_parts", fields)

	def test_every_frozen_spot_colour_field_is_compared(self):
		row_fields = cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP[0][3]

		self.assertEqual(
			tuple(f for f, _label in row_fields), cps_rules.SNAPSHOT_SPOT_FIELDS
		)


# ---------------------------------------------------------------------------
# Proving a card against the snapshot
# ---------------------------------------------------------------------------


class TestLabelSnapshotMismatches(unittest.TestCase):
	def mismatches(self, card=None, snapshot=None):
		return cps_rules.jc_snapshot_mismatches(
			card if card is not None else label_card(),
			snapshot if snapshot is not None else label_snapshot(),
			cps_rules.LABEL_SNAPSHOT_JC_MAP,
		)

	def test_a_faithful_card_has_no_mismatches(self):
		self.assertEqual(self.mismatches(), [])

	def test_data_typed_tooling_compares_as_a_number(self):
		# The specification holds cylinder_teeth as "96" and the card as 96.0.
		# Every one of the 192 live records is numeric-compatible; this is what
		# makes that fact usable rather than merely true.
		self.assertEqual(self.mismatches(card=label_card(cylinder_teeth=96)), [])
		self.assertEqual(self.mismatches(card=label_card(cylinder_teeth=96.0)), [])
		self.assertEqual(self.mismatches(card=label_card(plate_up=4.0)), [])

	def test_a_different_tooling_number_is_a_mismatch(self):
		found = self.mismatches(card=label_card(plate_round=3))

		self.assertEqual([m.field for m in found], ["plate_round"])
		self.assertEqual(found[0].expected, "2")
		self.assertEqual(found[0].found, 3)

	def test_a_blank_tooling_value_matches_a_zero(self):
		# A cleared Data field and a zero on the card are the same absence.
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				label_card(packing_up=0),
				label_snapshot(packing_up=""),
				cps_rules.LABEL_SNAPSHOT_JC_MAP,
			),
			[],
		)

	def test_a_resized_label_is_caught(self):
		found = self.mismatches(card=label_card(label_width=105.0))

		self.assertEqual([m.field for m in found], ["label_width"])
		self.assertEqual(found[0].label, "Label Width (mm)")

	def test_a_substituted_material_is_caught(self):
		found = self.mismatches(card=label_card(material_type="Thermal"))

		self.assertEqual([m.field for m in found], ["material_type"])

	def test_a_swapped_die_is_caught(self):
		found = self.mismatches(card=label_card(dies="DIE-00115"))

		self.assertEqual([m.field for m in found], ["dies"])
		self.assertEqual(found[0].expected, "DIE-00114")

	def test_the_packing_note_is_proved_too(self):
		found = self.mismatches(card=label_card(standard_packing="500 per roll"))

		self.assertEqual([m.field for m in found], ["standard_packing"])

	def test_the_colour_block_is_proved(self):
		found = self.mismatches(card=label_card(uses_k=0, number_of_colours=4))

		self.assertEqual(sorted(m.field for m in found), ["number_of_colours", "uses_k"])

	def test_precision_matches_on_both_sides(self):
		# Both the specification and the card declare two decimal places on the
		# four Float geometry fields, so nothing is lost across the comparison.
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(
				label_card(side_trim=2.5, gap_between=3.0),
				label_snapshot(side_trim=2.50, gap_between=3.00),
				cps_rules.LABEL_SNAPSHOT_JC_MAP,
			),
			[],
		)

	def test_a_hand_built_card_with_no_snapshot_is_not_checked(self):
		self.assertEqual(
			cps_rules.jc_snapshot_mismatches(label_card(), None, cps_rules.LABEL_SNAPSHOT_JC_MAP),
			[],
		)

	def test_an_empty_map_checks_nothing(self):
		self.assertEqual(cps_rules.jc_snapshot_mismatches(label_card(), label_snapshot(), ()), [])

	def test_a_wholly_blank_card_disagrees_with_every_populated_field(self):
		# The forged-card case: nothing supplied, everything frozen.
		found = self.mismatches(card={})
		blank_safe = {"numbering_required", "uses_c", "uses_m", "uses_y", "uses_k"}
		reported = {m.field for m in found}

		self.assertIn("dies", reported)
		self.assertIn("label_length", reported)
		self.assertIn("material_type", reported)
		# numbering_required is 0 on this specification, so a blank card agrees
		# with it - which is correct, and is why the check above names fields
		# that actually hold something.
		self.assertNotIn("numbering_required", reported)
		self.assertTrue(reported - blank_safe)


class TestLabelTableMismatches(unittest.TestCase):
	def mismatches(self, card_rows, snapshot_rows):
		return cps_rules.jc_table_mismatches(
			{"spot_colours": card_rows},
			label_snapshot(spot_colours=snapshot_rows),
			cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP,
		)

	def test_matching_rows_agree(self):
		self.assertEqual(self.mismatches([dict(SPOT_A)], [dict(SPOT_A)]), [])

	def test_a_missing_row_is_reported_as_a_count(self):
		found = self.mismatches([dict(SPOT_A)], [dict(SPOT_A), dict(SPOT_B)])

		self.assertEqual(len(found), 1)
		self.assertEqual(found[0].label, "Spot Colour Rows")
		self.assertEqual((found[0].found, found[0].expected), (1, 2))

	def test_an_extra_row_is_reported_as_a_count(self):
		found = self.mismatches([dict(SPOT_A), dict(SPOT_B)], [dict(SPOT_A)])

		self.assertEqual((found[0].found, found[0].expected), (2, 1))

	def test_a_substituted_pantone_is_caught(self):
		swapped = dict(SPOT_A, pantone_code="186 C")
		found = self.mismatches([swapped], [dict(SPOT_A)])

		self.assertEqual(len(found), 1)
		self.assertEqual(found[0].field, "spot_colours[1].pantone_code")
		self.assertEqual(found[0].expected, "185 C")

	def test_print_order_is_part_of_the_value(self):
		# Two spot colours swapped between rows one and two is a different plate
		# sequence, not the same set of colours.
		found = self.mismatches([dict(SPOT_B), dict(SPOT_A)], [dict(SPOT_A), dict(SPOT_B)])

		self.assertTrue(found)

	def test_card_rows_are_ordered_by_idx_not_by_arrival(self):
		rows = [dict(SPOT_B, idx=2), dict(SPOT_A, idx=1)]

		self.assertEqual(self.mismatches(rows, [dict(SPOT_A), dict(SPOT_B)]), [])

	def test_an_empty_grid_on_both_sides_agrees(self):
		self.assertEqual(self.mismatches([], []), [])

	def test_a_grid_invented_on_the_card_is_caught(self):
		found = self.mismatches([dict(SPOT_A)], [])

		self.assertEqual((found[0].found, found[0].expected), (1, 0))


class TestLabelLineMismatches(unittest.TestCase):
	"""The identity, price and quantity half, with Label's own customer field."""

	def order(self, **overrides):
		values = {
			"name": "SO-2026-00042",
			"customer": "CUST-0099",
			"transaction_date": "2026-07-02",
			"po_no": "LPO-8891",
		}
		values.update(overrides)
		return values

	def line(self, **overrides):
		values = {
			"name": "abc123",
			"item_code": "LBL-PPW-70X100",
			"qty": 50000,
			"rate": 1.234567891,
			"custom_cps": "LBL-SPEC-00031",
			"custom_price_source": cps_rules.SOURCE_CPS_PRICE,
			"custom_spec_snapshot": '{"_snapshot_version": 3}',
			"custom_spec_snapshot_at": "2026-07-02 10:00:00",
		}
		values.update(overrides)
		return values

	def card(self, **overrides):
		values = {
			"customer": "CUST-0099",
			"item_code": "LBL-PPW-70X100",
			"customer_product_spec": "LBL-SPEC-00031",
			"price_source": cps_rules.SOURCE_CPS_PRICE,
			"spec_snapshot": '{"_snapshot_version": 3}',
			"spec_snapshot_at": "2026-07-02 10:00:00",
			"order_date": "2026-07-02",
			"lpo_number": "LPO-8891",
			"rate": 1.234567891,
			"so_qty": 50000,
		}
		values.update(overrides)
		return values

	def mismatches(self, card=None, order=None, line=None):
		return cps_rules.jc_line_mismatches(
			card if card is not None else self.card(),
			order if order is not None else self.order(),
			line if line is not None else self.line(),
			3,
			"customer",
		)

	def test_a_faithful_card_has_no_mismatches(self):
		self.assertEqual(self.mismatches(), [])

	def test_the_customer_is_checked_against_the_order(self):
		found = self.mismatches(card=self.card(customer="CUST-0001"))

		self.assertEqual([m.field for m in found], ["customer"])

	def test_somebody_elses_lpo_is_caught(self):
		found = self.mismatches(card=self.card(lpo_number="LPO-0001"))

		self.assertEqual([m.field for m in found], ["lpo_number"])

	def test_a_backdated_order_date_is_caught(self):
		found = self.mismatches(card=self.card(order_date="2026-07-01"))

		self.assertEqual([m.field for m in found], ["order_date"])

	def test_the_date_compares_by_calendar_day_however_serialised(self):
		self.assertEqual(self.mismatches(card=self.card(order_date="2026-07-02 00:00:00")), [])

	def test_a_discounted_rate_is_caught_at_nine_decimal_places(self):
		found = self.mismatches(card=self.card(rate=1.23456789))

		self.assertEqual([m.field for m in found], ["rate"])

	def test_a_rewritten_snapshot_is_caught(self):
		found = self.mismatches(card=self.card(spec_snapshot='{"_snapshot_version": 3, "x": 1}'))

		self.assertEqual([m.field for m in found], ["spec_snapshot"])

	def test_the_line_quantity_is_carried_not_the_card_quantity(self):
		found = self.mismatches(card=self.card(so_qty=40000))

		self.assertEqual([m.field for m in found], ["so_qty"])


# ---------------------------------------------------------------------------
# Legacy order references
# ---------------------------------------------------------------------------


class TestOrderReferenceDetection(unittest.TestCase):
	def test_either_half_counts_as_a_claim_on_an_order(self):
		self.assertTrue(cps_rules.has_order_reference("SO-2026-00042", None))
		self.assertTrue(cps_rules.has_order_reference(None, "abc123"))
		self.assertTrue(cps_rules.has_order_reference("SO-2026-00042", "abc123"))

	def test_blank_and_whitespace_are_no_claim(self):
		self.assertFalse(cps_rules.has_order_reference(None, None))
		self.assertFalse(cps_rules.has_order_reference("", ""))
		self.assertFalse(cps_rules.has_order_reference("   ", "\t"))

	def test_a_snapshot_is_recognised_by_content_not_presence(self):
		self.assertTrue(cps_rules.has_frozen_snapshot('{"_snapshot_version": 3}'))
		self.assertFalse(cps_rules.has_frozen_snapshot(None))
		self.assertFalse(cps_rules.has_frozen_snapshot(""))
		self.assertFalse(cps_rules.has_frozen_snapshot("   \n "))


class TestOrderReferenceState(unittest.TestCase):
	def test_a_card_naming_no_order_is_none(self):
		self.assertEqual(
			cps_rules.order_reference_state(None, None), cps_rules.ORDER_REF_NONE
		)

	def test_a_card_naming_an_order_is_frozen_by_default(self):
		self.assertEqual(
			cps_rules.order_reference_state("SO-2026-00042", "abc123"),
			cps_rules.ORDER_REF_FROZEN,
		)

	def test_a_stamped_card_is_legacy(self):
		self.assertEqual(
			cps_rules.order_reference_state("SO-2026-00042", "abc123", legacy_flag=True),
			cps_rules.ORDER_REF_LEGACY,
		)

	def test_the_flag_means_nothing_without_an_order_reference(self):
		# Not a third kind of card. A card with no order and a stray flag is
		# simply a card with no order.
		self.assertEqual(
			cps_rules.order_reference_state(None, None, legacy_flag=True),
			cps_rules.ORDER_REF_NONE,
		)

	def test_an_unstamped_card_with_no_snapshot_is_still_frozen(self):
		# This is the forgery case, and it is deliberately not a state of its
		# own: it is a frozen card missing its snapshot, and the frozen path is
		# what refuses it.
		self.assertEqual(
			cps_rules.order_reference_state("SO-2026-00042", "abc123", legacy_flag=False),
			cps_rules.ORDER_REF_FROZEN,
		)


class TestLegacyQualification(unittest.TestCase):
	"""What the migration stamps, and only what it stamps."""

	def test_the_twenty_live_shapes_qualify(self):
		self.assertTrue(
			cps_rules.legacy_order_reference_qualifies("SO-2026-00042", None, None)
		)
		self.assertTrue(
			cps_rules.legacy_order_reference_qualifies("SO-2026-00042", "abc123", "")
		)

	def test_a_card_with_no_order_does_not_qualify(self):
		self.assertFalse(cps_rules.legacy_order_reference_qualifies(None, None, None))

	def test_a_card_carrying_a_snapshot_does_not_qualify(self):
		self.assertFalse(
			cps_rules.legacy_order_reference_qualifies(
				"SO-2026-00042", "abc123", '{"_snapshot_version": 3}'
			)
		)


class TestLegacyFlagEarned(unittest.TestCase):
	"""A new document may only be legacy as the amendment of one that is."""

	def amended_from(self, **overrides):
		values = {
			"name": "JC-LBL-2026-00007",
			"docstatus": 2,
			"sales_order": "SO-2026-00042",
			"sales_order_item": "abc123",
			"spec_snapshot": None,
			cps_rules.LEGACY_ORDER_REF_FIELD: 1,
		}
		values.update(overrides)
		return values

	def earned(self, amended_from=None, **card):
		values = {
			"sales_order": "SO-2026-00042",
			"sales_order_item": "abc123",
			"spec_snapshot": None,
		}
		values.update(card)
		return cps_rules.legacy_flag_earned(
			values["sales_order"],
			values["sales_order_item"],
			values["spec_snapshot"],
			amended_from,
		)

	def test_the_amendment_of_a_stamped_cancelled_card_earns_it(self):
		self.assertTrue(self.earned(self.amended_from()))

	def test_a_brand_new_card_cannot_earn_it(self):
		# The forgery this whole mechanism exists to refuse: same shape as the
		# twenty, no history behind it.
		self.assertFalse(self.earned(None))

	def test_amending_a_card_that_was_never_legacy_does_not_earn_it(self):
		self.assertFalse(
			self.earned(self.amended_from(**{cps_rules.LEGACY_ORDER_REF_FIELD: 0}))
		)

	def test_amending_a_card_that_is_not_cancelled_does_not_earn_it(self):
		for docstatus in (0, 1):
			self.assertFalse(self.earned(self.amended_from(docstatus=docstatus)))

	def test_an_amendment_may_not_repoint_the_order(self):
		self.assertFalse(
			self.earned(self.amended_from(), sales_order="SO-2026-00099")
		)

	def test_an_amendment_may_not_repoint_the_line(self):
		self.assertFalse(self.earned(self.amended_from(), sales_order_item="zzz999"))

	def test_an_amendment_may_not_drop_the_line_it_inherits(self):
		self.assertFalse(self.earned(self.amended_from(), sales_order_item=None))

	def test_a_card_carrying_a_snapshot_never_earns_it(self):
		self.assertFalse(
			self.earned(self.amended_from(), spec_snapshot='{"_snapshot_version": 3}')
		)

	def test_a_card_with_no_order_reference_never_earns_it(self):
		self.assertFalse(
			self.earned(self.amended_from(), sales_order=None, sales_order_item=None)
		)

	def test_blank_lines_compare_as_blank_on_both_sides(self):
		# A legacy card naming an order and no line amends into one naming an
		# order and no line.
		self.assertTrue(
			self.earned(
				self.amended_from(sales_order_item=None), sales_order_item=""
			)
		)


class TestLegacyOrderReferenceErrors(unittest.TestCase):
	def stored(self, **overrides):
		values = {
			"sales_order": "SO-2026-00042",
			"sales_order_item": "abc123",
			"spec_snapshot": None,
			cps_rules.LEGACY_ORDER_REF_FIELD: 1,
		}
		values.update(overrides)
		return values

	def current(self, **overrides):
		values = {
			"sales_order": "SO-2026-00042",
			"sales_order_item": "abc123",
			"spec_snapshot": None,
			cps_rules.LEGACY_ORDER_REF_FIELD: 1,
		}
		values.update(overrides)
		return values

	def codes(self, stored=None, current=None):
		return [
			e.code
			for e in cps_rules.legacy_order_reference_errors(
				stored if stored is not None else self.stored(),
				current if current is not None else self.current(),
			)
		]

	def test_an_ordinary_legacy_save_is_allowed(self):
		# Editing production remarks on a legacy card touches none of this. This
		# is the case the whole release exists to protect.
		self.assertEqual(self.codes(current=self.current()), [])

	def test_a_card_that_was_never_legacy_is_not_governed_by_these_rules(self):
		self.assertEqual(
			self.codes(stored=self.stored(**{cps_rules.LEGACY_ORDER_REF_FIELD: 0})), []
		)

	def test_no_stored_image_means_nothing_to_compare(self):
		self.assertEqual(cps_rules.legacy_order_reference_errors(None, self.current()), [])

	def test_the_flag_cannot_be_cleared(self):
		self.assertEqual(
			self.codes(current=self.current(**{cps_rules.LEGACY_ORDER_REF_FIELD: 0})),
			[cps_rules.LEGACY_FLAG_IMMUTABLE],
		)

	def test_the_order_cannot_be_repointed(self):
		self.assertEqual(
			self.codes(current=self.current(sales_order="SO-2026-00099")),
			[cps_rules.LEGACY_REF_IMMUTABLE],
		)

	def test_the_line_cannot_be_repointed(self):
		self.assertEqual(
			self.codes(current=self.current(sales_order_item="zzz999")),
			[cps_rules.LEGACY_REF_IMMUTABLE],
		)

	def test_the_links_cannot_be_cleared_either(self):
		# "Do not clear links" is enforced against the user as well as against
		# the migration.
		self.assertEqual(
			self.codes(current=self.current(sales_order=None, sales_order_item=None)),
			[cps_rules.LEGACY_REF_IMMUTABLE, cps_rules.LEGACY_REF_IMMUTABLE],
		)

	def test_a_snapshot_cannot_be_invented_on_a_legacy_card(self):
		self.assertEqual(
			self.codes(current=self.current(spec_snapshot='{"_snapshot_version": 3}')),
			[cps_rules.LEGACY_FLAG_NOT_EARNED],
		)

	def test_several_problems_are_all_reported(self):
		self.assertEqual(
			self.codes(
				current=self.current(
					sales_order="SO-2026-00099",
					spec_snapshot='{"_snapshot_version": 3}',
					**{cps_rules.LEGACY_ORDER_REF_FIELD: 0}
				)
			),
			[
				cps_rules.LEGACY_FLAG_IMMUTABLE,
				cps_rules.LEGACY_REF_IMMUTABLE,
				cps_rules.LEGACY_FLAG_NOT_EARNED,
			],
		)

	def test_every_message_formats_with_its_arguments(self):
		errors = cps_rules.legacy_order_reference_errors(
			self.stored(),
			self.current(
				sales_order="SO-2026-00099",
				spec_snapshot="{}",
				**{cps_rules.LEGACY_ORDER_REF_FIELD: 0}
			),
		)

		for error in errors:
			self.assertTrue(error.template.format(*error.args).strip())


if __name__ == "__main__":
	unittest.main()
