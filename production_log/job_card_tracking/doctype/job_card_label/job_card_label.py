import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from production_log.job_card_tracking import cps_rules
from production_log.job_card_tracking.order_derived import OrderDerivedJobCard

QTY_PRECISION = 3

# The only product type this Job Card can run. Read from the frozen snapshot on
# the Sales Order line, never from the current specification.
LABEL_PRODUCT_TYPE = "Label"


class JobCardLabel(OrderDerivedJobCard, Document):
	JC_PRODUCT_TYPE = LABEL_PRODUCT_TYPE

	# This card calls its customer link ``customer``, like Computer Paper and
	# ETR. Carton is the outlier with ``customer_name``.
	JC_CUSTOMER_FIELD = "customer"

	# Every technical value on an order-derived card is proved against the
	# snapshot the order froze — the label's geometry, its tooling, its material
	# and its colour block. A card may name the right order, the right price and
	# the right customer and still be a label nobody sold.
	JC_SNAPSHOT_FIELD_MAP = cps_rules.LABEL_SNAPSHOT_JC_MAP

	# And the grid, on the same terms. On a label the Pantone frequently *is*
	# the product, and the table being ``read_only`` on the form stops a Desk
	# user and stops nothing else.
	JC_SNAPSHOT_TABLE_MAP = cps_rules.LABEL_SNAPSHOT_JC_TABLE_MAP

	QTY_PRECISION = QTY_PRECISION

	# Unlike Computer Paper and Carton, this card type reaches order control
	# with rows that already name a Sales Order — written by hand, years before
	# anything was frozen onto an order line. See ``cps_rules``' legacy
	# order-reference section, and ``stamp_legacy_label_order_references``.
	JC_LEGACY_ORDER_REFS = True

	def validate(self):
		# The legacy flag decides which of the two paths below this card takes,
		# so it is re-derived from evidence before anything reads it.
		self.sync_legacy_order_reference()

		# Provenance next: everything after this is allowed to assume that an
		# order-derived card really does come from the order it names.
		self.validate_sales_order()

		if not self.is_frozen_order_derived():
			self.validate_customer_product_spec()
			self.populate_specification_snapshot()

		self.validate_spec_fields()
		self.validate_quantity()
		self.validate_plate()
		self.validate_numbering()
		self.set_sales_rep_info()
		self.set_status()

	def on_update(self):
		"""Keep the Sales Order line rollup honest on every draft save.

		Fires on insert, on edit and on submit, so a draft that reserves
		quantity is counted from the moment it exists — which is what stops two
		people carding the same line twice in the same minute.

		Legacy references are rolled up too. Their quantity was genuinely
		consumed against that line, and a rollup that ignored it would invite
		the line to be carded a second time.
		"""
		self.update_sales_order_rollup()

	def on_submit(self):
		self.set_status()

	def on_cancel(self):
		self.set_status()
		self.update_sales_order_rollup()

	def on_trash(self):
		# on_trash fires before the row is gone, so this card must not count
		# itself towards the quantity it is about to stop reserving.
		self.update_sales_order_rollup(exclude_self=True)

	def validate_customer_product_spec(self):
		"""Validate the *current* specification — legacy and hand-built paths only.

		A frozen order-derived card is deliberately exempt, for the same reason
		Job Card Computer Paper and Job Card Carton are: its eligibility and its
		technical values were settled when the order was submitted and frozen
		onto the line. Re-deriving them from the specification as it stands
		today would mean a spec since deactivated, amended or re-priced
		retroactively blocks production on an order already sold.
		``validate_sales_order`` proves the card against the frozen line
		instead, field by field, which is a stronger check and not a weaker one.

		Everything else keeps the live check unchanged: the Desk form, the
		Compass hand-built screen, history, and the 20 legacy order references,
		which have no frozen line to be validated against and so have only the
		current specification as evidence.
		"""
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer}."
			)

		if spec.product_type != LABEL_PRODUCT_TYPE:
			frappe.throw(
				f"Specification {self.customer_product_spec} is not a Label specification "
				f"(found: {spec.product_type})."
			)

		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active (current status: {spec.status}). "
				"Please select an Active specification."
			)

	def populate_specification_snapshot(self):
		"""Copy the *live* specification onto the card.

		Never runs for a frozen order-derived card. That is the whole point of
		the split: on those cards these same values arrived from the order's
		frozen snapshot, and refreshing them here would silently replace what
		was sold with what the specification happens to say today — and would
		then fail ``validate_sales_order`` on the next save, which is a
		confusing way to discover it.

		``dies`` is copied as the Dies record's name and the Dies record is not
		read. The label's geometry comes from the specification's own fields,
		which is where the order freezes it from too.
		"""
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		self.specification_name = spec.specification_name
		self.job_size = spec.job_size
		self.dies = spec.dies
		self.label_length = spec.label_length
		self.label_width = spec.label_width
		self.cylinder_teeth = spec.cylinder_teeth
		self.plate_up = spec.plate_up
		self.plate_round = spec.plate_round
		self.packing_up = spec.packing_up
		self.material_type = spec.material_type
		self.packing_pieces = spec.packing_pieces
		self.gap_between = spec.gap_between
		self.side_trim = spec.side_trim
		self.numbering_required = spec.numbering_required
		self.standard_packing = spec.standard_packing
		self.weight_per_carton = spec.standard_weight_per_carton

		# Print colours block (shared with CP and Carton)
		for f in ("ink_type", "uses_c", "uses_m", "uses_y", "uses_k",
				  "number_of_colours", "colour_notes"):
			self.set(f, spec.get(f))

		self.spot_colours = []
		for sc in spec.get("spot_colours") or []:
			self.append("spot_colours", {
				"pantone_code": sc.pantone_code,
				"pantone_name": sc.pantone_name,
				"hex_preview":  sc.hex_preview,
				"cmyk_c":       sc.cmyk_c,
				"cmyk_m":       sc.cmyk_m,
				"cmyk_y":       sc.cmyk_y,
				"cmyk_k":       sc.cmyk_k,
				"notes":        sc.notes,
			})

	def validate_spec_fields(self):
		required_fields = {
			"label_length":  "Label Length",
			"label_width":   "Label Width",
			"material_type": "Material Type",
		}

		for fieldname, label in required_fields.items():
			if not self.get(fieldname):
				frappe.throw(f"{label} is required for Label Job Card.")

	def validate_quantity(self):
		"""A quantity, and one that does not over-card its Sales Order line.

		``quantity_ordered`` was an ``Int`` until this release, which made the
		three-decimal comparison every other quantity rule in the CPS work is
		stated in impossible to express on this card. It is a ``Float`` with
		precision 3 now; ``flt`` tolerates whatever a legacy row read back
		during the migration window holds, so the check behaves as it always
		did.
		"""
		if self.quantity_ordered in (None, ""):
			frappe.throw(_("Quantity Ordered must be greater than 0."))

		if flt(self.quantity_ordered) <= 0:
			frappe.throw(_("Quantity Ordered must be greater than 0."))

		self.validate_quantity_against_sales_order_line()

	def validate_plate(self):
		if not self.plate_status:
			frappe.throw("Plate Status is required. Please select New or Old.")

		if self.plate_status == "Old" and not self.plate_code:
			frappe.throw("Plate Code is required when Plate Status is 'Old'.")

		if self.plate_status == "New" and self.plate_code:
			frappe.throw("Plate Code must be empty when Plate Status is 'New'.")

	def validate_numbering(self):
		"""Numbering ranges, required only when the specification asks for one.

		On an order-derived card ``numbering_required`` arrives from the frozen
		snapshot and is proved against it, so this reads the order's answer and
		not today's. Not one of the 192 live Label specifications sets it, which
		is why the branch below is dormant in practice and enforced anyway —
		the first specification that does set it must not find the rule missing.
		"""
		if not self.numbering_required:
			return

		if not self.numbering_start:
			frappe.throw("Numbering Start is required when Numbering Required is checked.")

		if not self.numbering_end:
			frappe.throw("Numbering End is required when Numbering Required is checked.")

	def set_sales_rep_info(self):
		if self.sales_rep:
			return

		current_user = frappe.session.user
		user_roles = frappe.get_roles(current_user)

		if "Sales User" in user_roles or "Sales Manager" in user_roles:
			self.sales_rep = current_user

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			# On submit, default to In Progress unless user has already advanced to Completed.
			if self.status not in ("In Progress", "Completed"):
				self.status = "In Progress"
		elif self.docstatus == 2:
			self.status = "Cancelled"


@frappe.whitelist()
def get_label_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer and product type Label"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Label'
		AND status = 'Active'
		AND (name LIKE %(txt)s OR specification_name LIKE %(txt)s)
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
	""",
		{
			"customer": filters.get("customer"),
			"txt": "%%" + txt + "%%",
			"start": int(start),
			"page_len": int(page_len),
		},
	)
