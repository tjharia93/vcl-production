import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from production_log.job_card_tracking import cps_rules

QTY_PRECISION = 3

# The only product type this Job Card can run (DN-7). Read from the frozen
# snapshot, never from the current specification.
CP_PRODUCT_TYPE = "Computer Paper"

# Sales Order Item fields the order-derived path reads. Every one is a Custom
# Field that lands in a separate deploy step (design §15), so each is checked
# against the meta before it reaches the query.
SO_LINE_CONTROL_FIELDS = (
	"custom_cps",
	"custom_cps_rate",
	"custom_price_source",
	"custom_spec_snapshot",
	"custom_spec_snapshot_at",
)

# Fields on the row that identify it and bind it to its parent. `parent`,
# `parenttype` and `parentfield` are what make "this line belongs to that
# order" provable rather than assumed.
SO_LINE_BASE_FIELDS = (
	"name",
	"parent",
	"parenttype",
	"parentfield",
	"item_code",
	"qty",
	"rate",
)

CP_PRODUCTION_STAGE_STATUSES = {
	"Not Started",
	"Ready",
	"In Progress",
	"Done",
	"Blocked",
	"Skipped",
}


class JobCardComputerPaper(Document):
	def validate(self):
		# Provenance first: everything below is allowed to assume that an
		# order-derived card really does come from the order it names.
		self.validate_sales_order()
		self.validate_customer_product_spec()
		self.validate_spec_fields()
		self.validate_numbering()
		self.validate_plate()
		self.validate_quantity()
		self.validate_production_stage_assets()
		self.set_sales_rep_info()
		self.set_status()

	def after_insert(self):
		self.reseed_production_stages(save=True)

	def on_update(self):
		"""Keep the Sales Order line rollup honest on every draft save.

		§11.2 rule 4 enumerated insert/submit/cancel/trash, which left editing
		``quantity_ordered`` on an existing draft showing a stale
		``custom_jc_qty``. ``on_update`` covers that edit and also fires on
		insert and on submit, so the explicit calls that used to sit in
		``after_insert`` and ``on_submit`` are gone rather than duplicated —
		each would take the same row lock a second time for one write.

		It does not fire on cancel or trash, which keep their own calls.
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

	def validate_spec_fields(self):
		if self.customer_product_spec and not self.job_size:
			frappe.throw("Job Size is required. Please re-select the Customer Product Specification.")
		if self.customer_product_spec and not self.number_of_parts:
			frappe.throw("Number of Parts is required. Please re-select the Customer Product Specification.")

	def is_order_derived(self):
		"""Whether this card claims to come from a Sales Order line."""
		return bool(self.sales_order or self.sales_order_item)

	def validate_customer_product_spec(self):
		"""Validate the *current* specification — legacy path only.

		An order-derived card is deliberately exempt. Its eligibility and its
		technical values were settled when the order was submitted and frozen
		onto the line; re-deriving them from the specification as it stands
		today would mean a spec that has since been deactivated, amended or
		re-priced retroactively blocks production on an order already sold.
		``validate_sales_order`` proves that card against the frozen line
		instead, which is a stronger check, not a weaker one.

		Cards with no Sales Order predate this path and keep the live check
		during the transition — there is nothing frozen to validate them
		against, so the current specification is the only evidence available.
		"""
		if self.is_order_derived():
			return

		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer:
			frappe.throw(
				f"Specification {self.customer_product_spec} does not belong to customer {self.customer}."
			)

		if spec.product_type != "Computer Paper":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not a Computer Paper specification "
				f"(found: {spec.product_type})."
			)

		if spec.status != "Active":
			frappe.throw(
				f"Specification {self.customer_product_spec} is not Active (current status: {spec.status}). "
				"Please select an Active specification."
			)

	def validate_numbering(self):
		if not self.numbering_required:
			return

		if not self.numbering_start:
			frappe.throw("Numbering Start is required when Numbering Required is checked.")

		if not self.numbering_end:
			frappe.throw("Numbering End is required when Numbering Required is checked.")

	def validate_plate(self):
		if self.plate_status == "Old" and not self.plate_code:
			frappe.throw("Plate Code is required when Plate Status is 'Old'.")

		if self.plate_status == "New" and self.plate_code:
			frappe.throw("Plate Code must be empty when Plate Status is 'New'.")

	def validate_sales_order(self):
		"""Prove this card against the order line it claims to come from.

		The link is optional at the schema level because job cards predating
		this path exist and are not being invented a history. When it is set,
		every value the card carries from the order is verified server-side
		against the order's own row.

		The fields involved are ``read_only`` on the form, which stops a Desk
		user typing into them and stops nothing else — a REST POST or a Data
		Import sets read-only fields perfectly happily. Comparing them here is
		what makes them true, so this runs on every write path and is not
		gated on ``custom_cps_control_enabled``: turning order control off
		later must not turn a forged job card into a valid one.
		"""
		if not self.is_order_derived():
			return

		if not self.sales_order:
			frappe.throw(_("Sales Order is required when a Sales Order Line is set."))
		if not self.sales_order_item:
			frappe.throw(_("Sales Order Line is required when a Sales Order is linked."))

		order = self._load_sales_order()
		line = self._lock_sales_order_line(verify_parent=True)
		if not line:
			frappe.throw(
				_("Sales Order line {0} not found on {1}.").format(
					self.sales_order_item, self.sales_order
				)
			)

		self._validate_frozen_line(order, line)

	def _load_sales_order(self):
		"""Read the order and refuse anything but a submitted one."""
		order = frappe.db.get_value(
			"Sales Order", self.sales_order, ["name", "docstatus", "customer"], as_dict=True
		)
		if not order:
			frappe.throw(_("Sales Order {0} does not exist.").format(self.sales_order))

		if order.docstatus == 0:
			frappe.throw(
				_("Sales Order {0} must be submitted before raising a Job Card.").format(
					self.sales_order
				)
			)
		if order.docstatus == 2:
			frappe.throw(_("Sales Order {0} is cancelled.").format(self.sales_order))

		return order

	def _validate_frozen_line(self, order, line):
		"""V-JC1..3: the line must be controlled, frozen, and faithfully copied."""
		if not self._so_line_control_fields():
			# The CPS control fields have not landed on this site yet (design
			# §15 deploys schema and behaviour separately). Nothing is frozen
			# to compare against, so stay inert rather than throw on every save.
			return

		if not line.get("custom_cps"):
			frappe.throw(
				_("Sales Order line {0} carries no Customer Product Specification, so no Job Card can be raised from it.").format(
					self.sales_order_item
				),
				title=_("Line Not Specification-Controlled"),
			)

		raw_snapshot = (line.get("custom_spec_snapshot") or "").strip()
		if not raw_snapshot:
			frappe.throw(
				_("Sales Order line {0} has no frozen specification snapshot. It was submitted before specification control; amend the order to freeze one.").format(
					self.sales_order_item
				),
				title=_("No Specification Snapshot"),
			)

		# Product type comes from what the order froze. Reading it from the
		# current specification would let a spec retyped since the order
		# reroute a job to the wrong kind of card.
		try:
			snapshot = frappe.parse_json(raw_snapshot) or {}
		except (ValueError, TypeError):
			frappe.throw(
				_("The specification snapshot on Sales Order line {0} is not readable.").format(
					self.sales_order_item
				),
				title=_("Corrupt Specification Snapshot"),
			)

		product_type = cps_rules.snapshot_product_type(snapshot)
		if product_type != CP_PRODUCT_TYPE:
			frappe.throw(
				_("Sales Order line {0} was ordered as a {1} specification, not {2}.").format(
					self.sales_order_item, product_type or _("untyped"), CP_PRODUCT_TYPE
				),
				title=_("Wrong Job Card Type"),
			)

		mismatches = cps_rules.jc_line_mismatches(self, order, line, QTY_PRECISION)
		if mismatches:
			frappe.throw(
				_("This Job Card does not match Sales Order line {0}: {1}. Raise it from the order rather than entering these values by hand.").format(
					self.sales_order_item,
					"; ".join(_describe_mismatch(m) for m in mismatches),
				),
				title=_("Job Card Does Not Match The Order"),
			)

	def validate_quantity(self):
		if not self.quantity_ordered or self.quantity_ordered <= 0:
			frappe.throw("Quantity Ordered must be greater than 0.")

		self.validate_quantity_against_sales_order_line()

	def validate_quantity_against_sales_order_line(self):
		"""Job cards on a line may never exceed the line quantity (DN-6).

		Over-carding is a hard throw for every role - there is no bypass, no
		comment-based override and no Over-Carded status. Draft job cards count
		towards the total: a draft reserves quantity, or two people raise two
		full-quantity job cards in the same minute and neither validation fires.
		"""
		if not self.sales_order_item:
			return

		line = self._lock_sales_order_line()
		if not line:
			frappe.throw(_("Sales Order line {0} not found.").format(self.sales_order_item))

		carded = self._carded_qty(exclude_self=True)
		remaining = flt(
			cps_rules.remaining_qty(line.get("qty"), carded), QTY_PRECISION
		)

		if flt(self.quantity_ordered, QTY_PRECISION) > remaining:
			frappe.throw(
				_("Quantity {0} exceeds the {1} still remaining on Sales Order line {2} (ordered {3}, already on job cards {4}).").format(
					flt(self.quantity_ordered, QTY_PRECISION),
					remaining,
					self.sales_order_item,
					flt(line.get("qty"), QTY_PRECISION),
					flt(carded, QTY_PRECISION),
				),
				title=_("Over-Carding Not Permitted"),
			)

	def _so_line_control_fields(self):
		"""CPS control fields that actually exist on Sales Order Item.

		Schema and behaviour deploy in separate steps (design §15), so every
		read of these has to survive a site where they have not landed.
		"""
		meta = frappe.get_meta("Sales Order Item")
		return [f for f in SO_LINE_CONTROL_FIELDS if meta.get_field(f)]

	def _lock_sales_order_line(self, verify_parent=False):
		"""Read the parent line under a row lock.

		Two simultaneous job card submits against one line is a real race at
		VCL's volume; without the lock both would read the same remaining
		quantity and both would pass.

		``Sales Order Item`` names are globally unique, so a row always comes
		back for a valid name — but it need not be a row of *this* order, or
		even of a Sales Order at all. With ``verify_parent`` the row must prove
		it is an ``items`` row of ``self.sales_order``; a card pointed at
		someone else's line is refused rather than validated against it.
		"""
		columns = list(SO_LINE_BASE_FIELDS) + self._so_line_control_fields()
		rows = frappe.db.sql(
			"""
			SELECT {columns}
			FROM `tabSales Order Item`
			WHERE name = %(name)s
			FOR UPDATE
			""".format(columns=", ".join("`{0}`".format(c) for c in columns)),
			{"name": self.sales_order_item},
			as_dict=True,
		)
		line = rows[0] if rows else None
		if not line or not verify_parent:
			return line

		if (
			line.get("parenttype") != "Sales Order"
			or line.get("parentfield") != "items"
			or line.get("parent") != self.sales_order
		):
			frappe.throw(
				_("Sales Order line {0} does not belong to {1}.").format(
					self.sales_order_item, self.sales_order
				),
				title=_("Line Does Not Belong To This Order"),
			)

		return line

	def _carded_qty(self, exclude_self=False):
		"""Quantity already committed on this Sales Order line.

		Counts drafts and submitted cards; cancelled cards stop counting, which
		is what makes an amended job card behave without special handling.
		"""
		filters = {
			"sales_order_item": self.sales_order_item,
			"docstatus": ["in", [0, 1]],
		}
		if exclude_self and not self.is_new():
			filters["name"] = ["!=", self.name]

		rows = frappe.get_all(
			"Job Card Computer Paper", filters=filters, pluck="quantity_ordered"
		)
		return sum(flt(qty) for qty in rows)

	def update_sales_order_rollup(self, exclude_self=False):
		"""Refresh the Job Card rollup on the Sales Order line (design §11.1).

		Written with ``db.set_value`` rather than through the document, because
		the Sales Order is submitted by the time any job card exists. The two
		rollup fields are the only Sales Order Item fields carrying
		``allow_on_submit`` for exactly this reason.
		"""
		if not self.sales_order_item:
			return

		if not frappe.get_meta("Sales Order Item").get_field("custom_jc_qty"):
			return

		# Lock the parent line before recomputing (design §11.2 rule 6). The
		# insert path already holds this lock from validate, but on_cancel and
		# on_trash never run validate - without it, cancelling two cards on one
		# line at the same moment lets both read the same total and the later
		# write silently loses the earlier one.
		line = self._lock_sales_order_line()
		if not line:
			return

		so_qty = line.get("qty")
		if so_qty is None:
			return

		carded = self._carded_qty(exclude_self=exclude_self)
		frappe.db.set_value(
			"Sales Order Item",
			self.sales_order_item,
			{
				"custom_jc_qty": flt(carded, QTY_PRECISION),
				"custom_jc_status": cps_rules.derive_jc_status(carded, so_qty),
			},
			update_modified=False,
		)

	def set_sales_rep_info(self):
		if self.sales_rep:
			return

		current_user = frappe.session.user
		user_roles = frappe.get_roles(current_user)

		if "Sales User" in user_roles or "Sales Manager" in user_roles:
			self.sales_rep = current_user
			self.sales_rep_approval_date = frappe.utils.today()

	def get_production_stage_route(self):
		route = ["Design", "Pending Films", "Printing", "Collation"]
		if self.numbering_required:
			route.append("Numbering")
		route.append("Pack")
		return route

	def reseed_production_stages(self, save=False):
		"""Rebuild Computer Paper route rows without duplicating stages.

		Existing matching stage rows keep their status, machine, timing, quantity,
		and notes. Rows outside the current route are dropped from the rebuilt
		table, for example Numbering when numbering_required is cleared.
		"""
		existing_by_stage = {}
		for row in self.get("production_stages") or []:
			if row.stage and row.stage not in existing_by_stage:
				existing_by_stage[row.stage] = row

		self.set("production_stages", [])
		for sequence, stage in enumerate(self.get_production_stage_route(), start=1):
			existing = existing_by_stage.get(stage)
			row = self.append("production_stages", {})
			row.stage = stage
			row.stage_status = (existing.stage_status if existing else None) or "Not Started"
			row.machine_asset = existing.machine_asset if existing else None
			row.started_on = existing.started_on if existing else None
			row.completed_on = existing.completed_on if existing else None
			row.quantity = existing.quantity if existing else None
			row.notes = existing.notes if existing else None
			row.sequence = sequence

		if save:
			self.save()

		return self.get("production_stages")

	def validate_production_stage_assets(self):
		for row in self.get("production_stages") or []:
			if row.stage_status and row.stage_status not in CP_PRODUCTION_STAGE_STATUSES:
				frappe.throw(_("Invalid stage status: {0}").format(row.stage_status))
			if not row.machine_asset:
				continue

			asset_category = frappe.db.get_value("Asset", row.machine_asset, "asset_category")
			if asset_category != "Plant & Machinery":
				frappe.throw(
					_("Row {0}: Machine Asset must be in Asset Category 'Plant & Machinery'.").format(
						row.idx
					),
					title=_("Invalid Machine Asset"),
				)


def _describe_mismatch(mismatch):
	"""One readable clause per disagreeing field.

	Values are truncated: the specification snapshot is a page of JSON, and
	pasting two copies of it into an error message tells the reader nothing
	they can act on.
	"""

	def show(value):
		if value in (None, ""):
			return _("blank")
		text = str(value)
		return text if len(text) <= 60 else text[:57] + "..."

	return _("{0} is {1}, the order says {2}").format(
		mismatch.label, show(mismatch.found), show(mismatch.expected)
	)


@frappe.whitelist()
def get_customer_product_spec_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Customer Product Specification by customer and product type"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Computer Paper'
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


@frappe.whitelist()
def get_plant_machinery_asset_query(doctype, txt, searchfield, start, page_len, filters):
	return frappe.db.sql(
		"""
		SELECT name, asset_name, asset_category
		FROM `tabAsset`
		WHERE asset_category = 'Plant & Machinery'
		AND (name LIKE %(txt)s OR asset_name LIKE %(txt)s)
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"txt": "%%" + txt + "%%",
			"start": int(start),
			"page_len": int(page_len),
		},
	)


@frappe.whitelist()
def reseed_production_stages(name):
	doc = frappe.get_doc("Job Card Computer Paper", name)
	doc.check_permission("write")
	doc.reseed_production_stages(save=True)
	return doc.get("production_stages")
