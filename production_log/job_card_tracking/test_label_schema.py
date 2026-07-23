"""Site-dependent checks on the Job Card Label order-derived schema.

Everything here needs a bench, because everything here is a question about the
DocType as the site has actually assembled it — which is not the same question
as "what does the JSON say". A Custom Field, a Property Setter or a half-applied
migration all change the answer, and each of those is exactly the failure this
release had to be designed around.

Run with ``bench --site <site> run-tests --module
production_log.job_card_tracking.test_label_schema``.

The Frappe-free half lives in ``test_label_cps_rules.py`` and covers the
decisions. These four are the ones that cannot be decided without a database:

1. Every field the frozen specification maps onto exists on the card. The
   mapping loop guards writes with ``meta.has_field``, so a missing target
   produces a card with quiet holes rather than an error.
2. ``quantity_ordered`` really is a three-decimal number after the migration.
3. No Custom Field shadows a DocField — the condition that made
   ``retire_label_order_custom_fields`` necessary must not exist afterwards.
4. The controller and the registry agree with each other and with the DocType.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from production_log.job_card_tracking import cps_rules, so_spec_control
from production_log.job_card_tracking.doctype.job_card_label.job_card_label import JobCardLabel
from production_log.job_card_tracking.order_derived import OrderDerivedJobCard
from production_log.job_card_tracking.test_label_cps_rules import JC_LABEL_FIELDS

DOCTYPE = "Job Card Label"


class TestJobCardLabelSchema(FrappeTestCase):
	@property
	def meta(self):
		return frappe.get_meta(DOCTYPE)

	def field(self, fieldname):
		df = self.meta.get_field(fieldname)
		self.assertIsNotNone(df, "{0} has no field {1}".format(DOCTYPE, fieldname))
		return df

	def docfields(self):
		"""Fields the *app* declares, excluding Custom Fields.

		``meta.fields`` is the assembled list and includes every Custom Field on
		the site — Job Card Label carries a Production Tracking block from the
		v2_0 patch, among others. Reading the DocField table instead is what
		makes "does a Custom Field shadow a DocField" a question with a
		meaningful answer rather than a tautology.
		"""
		return {
			row.fieldname: row
			for row in frappe.get_all(
				"DocField",
				filters={"parent": DOCTYPE, "parenttype": "DocType"},
				fields=["fieldname", "fieldtype"],
			)
			if row.fieldname
		}

	# -- the mapping ------------------------------------------------------

	def test_every_mapped_snapshot_target_exists(self):
		missing = cps_rules.unmapped_jc_targets(
			cps_rules.LABEL_SNAPSHOT_JC_MAP, lambda f: bool(self.meta.get_field(f))
		)

		self.assertEqual(missing, [])

	def test_every_mapped_table_target_exists(self):
		missing = cps_rules.unmapped_jc_table_targets(
			cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP, lambda f: bool(self.meta.get_field(f))
		)

		self.assertEqual(missing, [])

	def test_the_spot_colour_grid_holds_the_rows_the_snapshot_freezes(self):
		df = self.field("spot_colours")

		self.assertEqual(df.fieldtype, "Table")
		self.assertEqual(df.options, "Spot Colour")

		row_meta = frappe.get_meta("Spot Colour")
		for fieldname in cps_rules.SNAPSHOT_SPOT_FIELDS:
			self.assertIsNotNone(
				row_meta.get_field(fieldname), "Spot Colour has no field {0}".format(fieldname)
			)

	def test_the_field_inventory_has_not_drifted_from_the_frappe_free_tests(self):
		"""The literal in ``test_label_cps_rules`` must describe the real card.

		That literal is what makes ``unmapped_jc_targets`` answerable without a
		bench. A field added to the DocType and not to the literal makes the
		unit tests weaker without making them fail, which is the worst of both.
		"""
		declared = {
			fieldname
			for fieldname, df in self.docfields().items()
			if df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML", "Button")
		}

		self.assertEqual(declared - JC_LABEL_FIELDS, set())
		self.assertEqual(JC_LABEL_FIELDS - declared, set())

	# -- the order-derived block ------------------------------------------

	def test_the_order_reference_fields_exist_and_are_read_only(self):
		for fieldname in ("sales_order", "sales_order_item", "item_code", "rate",
						  "price_source", "so_qty", "spec_snapshot", "spec_snapshot_at",
						  cps_rules.LEGACY_ORDER_REF_FIELD):
			df = self.field(fieldname)
			self.assertTrue(
				df.read_only, "{0} must be read_only on the form".format(fieldname)
			)

	def test_the_sales_order_link_points_at_a_sales_order(self):
		df = self.field("sales_order")

		self.assertEqual(df.fieldtype, "Link")
		self.assertEqual(df.options, "Sales Order")

	def test_the_sales_order_line_is_data_not_a_link(self):
		"""Same shape as Job Card Carton, and for the same reason.

		The line is proved by ``_lock_sales_order_line``, which reads the row
		under a lock and checks its ``parent``/``parenttype``/``parentfield``.
		A Link to a child DocType would add a second, weaker check and would
		make the 7 historical values a link-validation risk on every save.
		"""
		df = self.field("sales_order_item")

		self.assertEqual(df.fieldtype, "Data")

	def test_the_legacy_flag_is_never_copied_onto_a_new_document(self):
		df = self.field(cps_rules.LEGACY_ORDER_REF_FIELD)

		self.assertEqual(df.fieldtype, "Check")
		self.assertTrue(df.no_copy)
		self.assertTrue(df.read_only)

	def test_the_snapshot_carries_no_allow_on_submit(self):
		# A snapshot that could be edited after submit is not a snapshot.
		for fieldname in ("spec_snapshot", "spec_snapshot_at", "sales_order",
						  "sales_order_item", "rate", "so_qty",
						  cps_rules.LEGACY_ORDER_REF_FIELD):
			self.assertFalse(
				self.field(fieldname).allow_on_submit,
				"{0} must not be editable after submit".format(fieldname),
			)

	def test_the_order_header_values_lock_when_an_order_is_named(self):
		for fieldname in ("order_date", "lpo_number", "customer"):
			self.assertEqual(
				self.field(fieldname).read_only_depends_on,
				"eval:doc.sales_order",
				"{0} must lock on an order-derived card".format(fieldname),
			)

	# -- the quantity -----------------------------------------------------

	def test_quantity_ordered_is_a_three_decimal_number(self):
		df = self.field("quantity_ordered")

		self.assertEqual(df.fieldtype, "Float")
		self.assertEqual(str(df.precision), "3")

	def test_every_stored_quantity_reads_back_as_a_number(self):
		"""The live half of ``audit_label_quantity_ordered``.

		The patch proved the column converted; this proves it stayed converted,
		on whatever rows the site holds today.
		"""
		for name, qty in frappe.get_all(
			DOCTYPE, fields=["name", "quantity_ordered"], as_list=True
		):
			self.assertIsNotNone(
				frappe.utils.flt(qty), "{0} has an unreadable quantity".format(name)
			)

	# -- metadata hygiene --------------------------------------------------

	def test_no_custom_field_shadows_a_docfield(self):
		"""The condition ``retire_label_order_custom_fields`` exists to remove.

		Two entries for one column in the assembled meta is what makes a DocType
		sync fail, and it is how ``sales_order`` and ``sales_order_item`` reached
		this release owned by nobody.
		"""
		custom = set(frappe.get_all("Custom Field", filters={"dt": DOCTYPE}, pluck="fieldname"))

		self.assertEqual(sorted(set(self.docfields()) & custom), [])

	def test_no_historical_order_reference_was_lost(self):
		"""Whatever links the site holds, it holds them attached to real fields.

		Deliberately not a fixed count. The audited site had 20 and 7 at the time
		the migration was written; asserting those numbers here would fail on
		every site that has since raised a job card, which is not a defect.
		"""
		columns = frappe.db.get_table_columns(DOCTYPE)

		for fieldname in ("sales_order", "sales_order_item", cps_rules.LEGACY_ORDER_REF_FIELD):
			self.assertIn(fieldname, columns)

	def test_every_stamped_legacy_row_still_has_the_shape_it_was_stamped_for(self):
		rows = frappe.get_all(
			DOCTYPE,
			filters={cps_rules.LEGACY_ORDER_REF_FIELD: 1},
			fields=["name", "sales_order", "sales_order_item", "spec_snapshot"],
		)

		for row in rows:
			self.assertTrue(
				cps_rules.legacy_order_reference_qualifies(
					row.sales_order, row.sales_order_item, row.spec_snapshot
				),
				"{0} is stamped legacy but no longer has a legacy shape".format(row.name),
			)

	def test_no_row_has_a_legacy_shape_without_the_stamp(self):
		"""The inverse, and the one that would break saves if it failed.

		A row naming an order with no snapshot and no stamp is refused on its
		next save, because it is indistinguishable from a forgery. After the
		migration there must be none.
		"""
		rows = frappe.get_all(
			DOCTYPE,
			fields=["name", "sales_order", "sales_order_item", "spec_snapshot",
					cps_rules.LEGACY_ORDER_REF_FIELD],
		)
		unstamped = [
			row.name
			for row in rows
			if cps_rules.legacy_order_reference_qualifies(
				row.sales_order, row.sales_order_item, row.spec_snapshot
			)
			and not row.get(cps_rules.LEGACY_ORDER_REF_FIELD)
		]

		self.assertEqual(unstamped, [])


class TestJobCardLabelController(FrappeTestCase):
	def test_the_controller_uses_the_shared_order_derived_behaviour(self):
		# Never a copy of it. Two hundred lines of locking logic in three files
		# is three behaviours within a release or two.
		self.assertTrue(issubclass(JobCardLabel, OrderDerivedJobCard))

	def test_it_declares_the_label_maps_and_nothing_borrowed(self):
		self.assertEqual(JobCardLabel.JC_PRODUCT_TYPE, "Label")
		self.assertEqual(JobCardLabel.JC_CUSTOMER_FIELD, "customer")
		self.assertIs(JobCardLabel.JC_SNAPSHOT_FIELD_MAP, cps_rules.LABEL_SNAPSHOT_JC_MAP)
		self.assertIs(JobCardLabel.JC_SNAPSHOT_TABLE_MAP, cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP)
		self.assertEqual(JobCardLabel.QTY_PRECISION, 3)

	def test_only_label_opts_into_legacy_order_references(self):
		from production_log.job_card_tracking.doctype.job_card_carton.job_card_carton import (
			JobCardCarton,
		)
		from production_log.job_card_tracking.doctype.job_card_computer_paper.job_card_computer_paper import (
			JobCardComputerPaper,
		)

		self.assertTrue(JobCardLabel.JC_LEGACY_ORDER_REFS)
		self.assertFalse(JobCardCarton.JC_LEGACY_ORDER_REFS)
		self.assertFalse(JobCardComputerPaper.JC_LEGACY_ORDER_REFS)

	def test_label_is_registered_for_sales_order_cancellation(self):
		self.assertEqual(so_spec_control.JOB_CARD_DOCTYPES["Label"], DOCTYPE)
		self.assertTrue(frappe.db.exists("DocType", DOCTYPE))

	def test_every_registered_card_type_can_be_filtered_on_its_order(self):
		# ``so_spec_control.on_cancel`` filters each registered DocType on
		# ``sales_order``. A registry entry for a card type without the column
		# would throw on every cancel of every order.
		for doctype in so_spec_control.JOB_CARD_DOCTYPES.values():
			if not frappe.db.exists("DocType", doctype):
				continue
			self.assertIsNotNone(
				frappe.get_meta(doctype).get_field("sales_order"),
				"{0} is registered but has no sales_order field".format(doctype),
			)
