import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from production_log.job_card_tracking import cps_rules
from production_log.job_card_tracking.order_derived import OrderDerivedJobCard

QTY_PRECISION = 3

# The only product type this Job Card can run. Read from the frozen snapshot on
# the Sales Order line, never from the current specification.
CARTON_PRODUCT_TYPE = "Carton"


class JobCardCarton(OrderDerivedJobCard, Document):
	JC_PRODUCT_TYPE = CARTON_PRODUCT_TYPE

	# This card calls its customer link ``customer_name`` where Computer Paper,
	# Label and ETR all say ``customer``. Renaming it would be a data migration
	# over live rows plus every JS, print format and report reference, for
	# uniformity alone — so the asymmetry is carried as configuration instead
	# (discovery §9.4). Compass already carries the same indirection twice.
	JC_CUSTOMER_FIELD = "customer_name"

	# Unlike Computer Paper, every technical value on this card is proved
	# against the snapshot the order froze. There is no legacy of order-derived
	# Carton cards to grandfather, so the strict rule can be the first rule: a
	# card may name the right order, the right price and the right customer and
	# still be a box nobody sold.
	JC_SNAPSHOT_FIELD_MAP = cps_rules.CARTON_SNAPSHOT_JC_MAP

	# And the grid, on the same terms. The scalar map above proves what the box
	# is; this proves what it is printed in. A Carton card seeded from an order
	# has its Spot Colours written from the snapshot by the creation path, and
	# the table is ``read_only`` on the form — which stops a Desk user and stops
	# nothing else, so the rows are compared back against the snapshot here.
	JC_SNAPSHOT_TABLE_MAP = cps_rules.CARTON_SNAPSHOT_JC_TABLE_MAP

	QTY_PRECISION = 3

	def validate(self):
		# Provenance first: everything below is allowed to assume that an
		# order-derived card really does come from the order it names.
		self.validate_sales_order()
		self.validate_customer_product_spec()
		self.validate_dimensions()
		self.validate_quantity()
		self.set_status()

	def on_update(self):
		"""Keep the Sales Order line rollup honest on every draft save.

		Fires on insert, on edit and on submit, so a draft that reserves
		quantity is counted from the moment it exists — which is what stops two
		people carding the same line twice in the same minute.
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

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			if self.status not in ("In Progress", "Completed"):
				self.status = "In Progress"
		elif self.docstatus == 2:
			self.status = "Cancelled"

	def validate_customer_product_spec(self):
		"""Validate the *current* specification — legacy path only.

		An order-derived card is deliberately exempt, for the same reason Job
		Card Computer Paper is: its eligibility and its technical values were
		settled when the order was submitted and frozen onto the line.
		Re-deriving them from the specification as it stands today would mean a
		spec since deactivated, amended or re-priced retroactively blocks
		production on an order already sold. ``validate_sales_order`` proves
		the card against the frozen line instead, field by field, which is a
		stronger check and not a weaker one.

		Cards with no Sales Order are the three existing creation paths — the
		Desk form, the Compass hand-built screen, and history. They keep the
		live check: there is nothing frozen to validate them against, so the
		current specification is the only evidence available.
		"""
		if self.is_order_derived():
			return

		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer_name:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer_name}."
			)

		if spec.product_type != CARTON_PRODUCT_TYPE:
			frappe.throw(
				f"Specification {self.customer_product_spec} is not a Carton specification "
				f"(found: {spec.product_type})."
			)

		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active (current status: {spec.status}). "
				"Please select an Active specification."
			)

	def validate_dimensions(self):
		if not self.ctn_length_mm or self.ctn_length_mm <= 0:
			frappe.throw(_("Carton Length (mm) must be greater than 0."))

		if not self.ctn_width_mm or self.ctn_width_mm <= 0:
			frappe.throw(_("Carton Width (mm) must be greater than 0."))

		if self.ply != "SFK":
			if not self.ctn_height_mm or self.ctn_height_mm <= 0:
				frappe.throw(
					_("Carton Height (mm) must be greater than 0 unless Ply is SFK.")
				)

	def validate_quantity(self):
		"""A quantity, and one that does not over-card its Sales Order line.

		``quantity_ordered`` was a ``Data`` field parsed with ``int()`` until
		this release, which made every quantity rule in the CPS work — carded,
		remaining, rollup, three-decimal comparison — impossible to state. It
		is a ``Float`` now; ``flt`` still tolerates a string, so a legacy row
		read back before the column is rewritten behaves as it always did.
		"""
		if self.quantity_ordered in (None, ""):
			frappe.throw(_("Quantity Ordered is required."))

		if flt(self.quantity_ordered) <= 0:
			frappe.throw(_("Quantity Ordered must be greater than 0."))

		self.validate_quantity_against_sales_order_line()


@frappe.whitelist()
def get_carton_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer and product type Carton"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Carton'
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
