"""The order-derived Job Card behaviours, shared by every kind of card.

Extracted from ``job_card_computer_paper.py`` unchanged. Everything here is
concurrency-sensitive — a row lock, a reservation, a rollup recomputed from a
locked read — and the discovery report's recommendation was explicit: lift it
into one module rather than copy it, because ~200 lines of locking logic in two
files is two behaviours within a release or two.

A card opts in by inheriting :class:`OrderDerivedJobCard` before ``Document``
and stating four things about itself:

``JC_PRODUCT_TYPE``
    The snapshot ``product_type`` this DocType is allowed to run. A line
    ordered as anything else is refused rather than carded.

``JC_CUSTOMER_FIELD``
    What this card calls its customer link. Computer Paper says ``customer``
    and Carton says ``customer_name``; renaming a field on a live submittable
    DocType is a data migration plus every JS, print format and report
    reference, for cosmetics.

``JC_SNAPSHOT_FIELD_MAP``
    ``(snapshot key, card field, label)`` triples proving the card's technical
    values against the frozen snapshot. Empty means "not checked": Computer
    Paper's behaviour is exactly what it was, and this module does not
    retroactively tighten a card type that is already in production.

``JC_SNAPSHOT_TABLE_MAP``
    ``(snapshot key, card table field, row label, row fields)`` quadruples
    doing the same for the card's child tables. Separate from the scalar map
    because the shapes differ and because the two are not the same guarantee:
    the scalars say what the box is, the tables say what it is printed in.
    Empty means "not checked", on the same terms as above.

``QTY_PRECISION``
    Decimal places quantities are compared at. Three everywhere.

``JC_LEGACY_ORDER_REFS``
    Whether this card type has rows that named a Sales Order *before* order
    control existed. Off for Computer Paper and Carton, whose order references
    only ever came from this path; on for Label, which reaches this release with
    20 hand-written ones. See :meth:`OrderDerivedJobCard.order_reference_state`
    and ``cps_rules``' legacy-order-reference section for why the distinction is
    recorded rather than inferred.

Nothing in here is gated on ``Selling Settings.custom_cps_control_enabled``.
Turning order control off later must not turn a forged job card into a valid
one.
"""

import frappe
from frappe import _
from frappe.utils import flt

from production_log.job_card_tracking import cps_rules

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


class OrderDerivedJobCard:
	"""Provenance, over-card protection and Sales Order rollups."""

	JC_PRODUCT_TYPE = None
	JC_CUSTOMER_FIELD = "customer"
	JC_SNAPSHOT_FIELD_MAP = ()
	JC_SNAPSHOT_TABLE_MAP = ()
	QTY_PRECISION = 3
	JC_LEGACY_ORDER_REFS = False

	# -- provenance ---------------------------------------------------------

	def is_order_derived(self):
		"""Whether this card claims to come from a Sales Order line."""
		return bool(self.get("sales_order") or self.get("sales_order_item"))

	def order_reference_state(self):
		"""``none``, ``frozen`` or ``legacy`` for this card.

		Card types without :data:`JC_LEGACY_ORDER_REFS` can never be ``legacy``,
		so for Computer Paper and Carton this is exactly the two-state question
		``is_order_derived`` has always answered, under a longer name.
		"""
		return cps_rules.order_reference_state(
			self.get("sales_order"),
			self.get("sales_order_item"),
			self.is_legacy_order_reference(),
		)

	def is_frozen_order_derived(self):
		"""Whether this card must be proved against a frozen Sales Order line.

		The question every caller actually wants. A card in this state has its
		specification settled by the order and must not be refreshed from the
		live one; a card in any other state has nothing frozen to be refreshed
		*from* and keeps the behaviour it has always had.
		"""
		return self.order_reference_state() == cps_rules.ORDER_REF_FROZEN

	def is_legacy_order_reference(self):
		"""Whether this card's order reference predates order control.

		Reads the recorded flag and never infers it. A card type that does not
		declare :data:`JC_LEGACY_ORDER_REFS`, or a site where the field has not
		landed yet, answers False — which is the strict answer, and the right
		default for a question about whether to relax a check.
		"""
		if not self.JC_LEGACY_ORDER_REFS:
			return False
		if not self.meta.get_field(cps_rules.LEGACY_ORDER_REF_FIELD):
			return False
		return bool(self.get(cps_rules.LEGACY_ORDER_REF_FIELD))

	def sync_legacy_order_reference(self):
		"""Re-derive the legacy flag from evidence, discarding whatever was sent.

		Must run before :meth:`validate_sales_order`, because it decides which
		of the two paths that method takes.

		The flag is an output of validation and never an input, on the same
		terms as the frozen snapshot (V12). For an existing row it is whatever
		the database already holds — the migration stamped it, and nothing on a
		write path may move it. For a new row it is earned or it is off, and the
		only way to earn it is to be the amendment of a card that already has
		it (see :func:`cps_rules.legacy_flag_earned`).

		Inert on card types that do not declare :data:`JC_LEGACY_ORDER_REFS`,
		and on a site where the field has not landed yet.
		"""
		if not self.JC_LEGACY_ORDER_REFS:
			return
		if not self.meta.get_field(cps_rules.LEGACY_ORDER_REF_FIELD):
			return

		if self.is_new():
			earned = cps_rules.legacy_flag_earned(
				self.get("sales_order"),
				self.get("sales_order_item"),
				self.get("spec_snapshot"),
				self._amended_from_row(),
			)
			self.set(cps_rules.LEGACY_ORDER_REF_FIELD, 1 if earned else 0)
			return

		stored = self._stored_order_reference()
		if stored is None:
			# The row is not new but has no stored image — a rename, or a
			# document being replayed. Nothing has been proved, so nothing is
			# relaxed.
			self.set(cps_rules.LEGACY_ORDER_REF_FIELD, 0)
			return

		errors = cps_rules.legacy_order_reference_errors(stored, self)
		if errors:
			frappe.throw(
				"<br>".join(_(e.template).format(*e.args) for e in errors),
				title=_("Legacy Order Reference"),
			)

		self.set(
			cps_rules.LEGACY_ORDER_REF_FIELD,
			1 if stored.get(cps_rules.LEGACY_ORDER_REF_FIELD) else 0,
		)

	def _legacy_reference_columns(self):
		# A list, not a tuple: ``frappe.db.get_value`` branches on the argument
		# being a string and hands everything else to the query builder, and a
		# list is what every caller in the framework passes it.
		return [
			"name",
			"docstatus",
			"sales_order",
			"sales_order_item",
			"spec_snapshot",
			cps_rules.LEGACY_ORDER_REF_FIELD,
		]

	def _stored_order_reference(self):
		"""This card's order reference as the database currently holds it."""
		if self.is_new() or not self.name:
			return None
		return frappe.db.get_value(
			self.doctype, self.name, self._legacy_reference_columns(), as_dict=True
		)

	def _amended_from_row(self):
		"""The cancelled card this one amends, or None.

		``amended_from`` is ``read_only`` and therefore settable over REST like
		every other read-only field, which is precisely why the row it names is
		read and checked rather than believed.
		"""
		amended_from = (self.get("amended_from") or "").strip()
		if not amended_from:
			return None
		return frappe.db.get_value(
			self.doctype, amended_from, self._legacy_reference_columns(), as_dict=True
		)

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

		A recorded legacy reference is exempt, and only a recorded one. Those
		rows named an order before there was anything to freeze, so there is no
		frozen line to prove them against; ``sync_legacy_order_reference``
		is what makes "recorded" mean something a REST caller cannot claim.
		"""
		if not self.is_frozen_order_derived():
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
		"""Read the order and refuse anything but a submitted one.

		``transaction_date`` and ``po_no`` are read here and not only because
		they are cheap: they are what ``order_date`` and ``lpo_number`` on the
		card are proved against, and a column left out of this read would make
		every card look as though it disagreed with a blank order (see
		``cps_rules.jc_line_mismatches``). Both are standard Sales Order fields,
		so unlike the ``custom_`` line fields there is no deploy step to survive.
		"""
		order = frappe.db.get_value(
			"Sales Order",
			self.sales_order,
			["name", "docstatus", "customer", "transaction_date", "po_no"],
			as_dict=True,
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

		if not cps_rules.snapshot_version_supported(snapshot):
			frappe.throw(
				_("The specification snapshot on Sales Order line {0} was written at version {1}, which this site cannot read. Supported versions: {2}.").format(
					self.sales_order_item,
					cps_rules.snapshot_version(snapshot) or _("unstated"),
					", ".join(str(v) for v in cps_rules.SUPPORTED_SNAPSHOT_VERSIONS),
				),
				title=_("Unreadable Specification Snapshot"),
			)

		product_type = cps_rules.snapshot_product_type(snapshot)
		if product_type != self.JC_PRODUCT_TYPE:
			frappe.throw(
				_("Sales Order line {0} was ordered as a {1} specification, not {2}.").format(
					self.sales_order_item, product_type or _("untyped"), self.JC_PRODUCT_TYPE
				),
				title=_("Wrong Job Card Type"),
			)

		# Only now that the snapshot is known to be of this card's kind is it
		# worth asking whether it is new enough to describe that kind in full.
		# Asked before the type check, a Carton snapshot offered to a Label card
		# would be refused for being old when the truth is that it is a Carton.
		if not cps_rules.snapshot_describes_product_type(snapshot, self.JC_PRODUCT_TYPE):
			frappe.throw(
				_("Sales Order line {0} was frozen at snapshot version {1}, which predates the full {2} specification. Amend the order and re-submit it to freeze a current snapshot, then raise the Job Card again.").format(
					self.sales_order_item,
					cps_rules.snapshot_version(snapshot) or _("unstated"),
					self.JC_PRODUCT_TYPE,
				),
				title=_("Specification Snapshot Too Old"),
			)

		mismatches = cps_rules.jc_line_mismatches(
			self, order, line, self.QTY_PRECISION, self.JC_CUSTOMER_FIELD
		)

		if self.JC_SNAPSHOT_FIELD_MAP or self.JC_SNAPSHOT_TABLE_MAP:
			self._assert_mapped_targets_exist()

		if self.JC_SNAPSHOT_FIELD_MAP:
			mismatches += cps_rules.jc_snapshot_mismatches(
				self, snapshot, self.JC_SNAPSHOT_FIELD_MAP, self.QTY_PRECISION
			)

		# The card's child tables, on the same terms as its scalars. Run
		# separately rather than folded into the scalar map because the two are
		# different comparisons — one value against one value, versus one
		# ordered list against another — and because a card type may reasonably
		# prove one and not the other.
		if self.JC_SNAPSHOT_TABLE_MAP:
			mismatches += cps_rules.jc_table_mismatches(
				self, snapshot, self.JC_SNAPSHOT_TABLE_MAP, self.QTY_PRECISION
			)

		if mismatches:
			frappe.throw(
				_("This Job Card does not match Sales Order line {0}: {1}. Raise it from the order rather than entering these values by hand.").format(
					self.sales_order_item,
					"; ".join(describe_mismatch(m) for m in mismatches),
				),
				title=_("Job Card Does Not Match The Order"),
			)

	def _assert_mapped_targets_exist(self):
		"""Refuse to run a mapping whose targets are not all on this DocType.

		The Compass mapping loop guards every write with ``meta.has_field``, so
		a missing target produces a card with quiet holes rather than an error
		(discovery §8.9). Silence is the wrong answer here: a half-populated
		card is indistinguishable from a complete one on screen, and the first
		person to notice is whoever cuts the board.
		"""
		has_field = lambda f: bool(self.meta.get_field(f))  # noqa: E731
		missing = cps_rules.unmapped_jc_targets(self.JC_SNAPSHOT_FIELD_MAP, has_field)
		missing += cps_rules.unmapped_jc_table_targets(self.JC_SNAPSHOT_TABLE_MAP, has_field)
		if missing:
			frappe.throw(
				_("{0} is missing the fields the frozen specification maps onto: {1}. The DocType and the code are out of step — run bench migrate.").format(
					self.doctype, ", ".join(missing)
				),
				title=_("Specification Mapping Incomplete"),
			)

	# -- quantity, reservation and rollup -----------------------------------

	def validate_quantity_against_sales_order_line(self):
		"""Job cards on a line may never exceed the line quantity (DN-6).

		Over-carding is a hard throw for every role - there is no bypass, no
		comment-based override and no Over-Carded status. Draft job cards count
		towards the total: a draft reserves quantity, or two people raise two
		full-quantity job cards in the same minute and neither validation fires.

		A recorded legacy reference is exempt from the *check* and never from
		the *count*. Those cards were written against orders nobody was
		measuring, so a rule invented today could refuse to save a job that was
		produced and invoiced months ago — but the quantity they consumed is a
		fact, ``_carded_qty`` reads it, and the next card raised from the order
		is held to it. Exempting them from the arithmetic as well would let one
		line be carded twice.
		"""
		if not self.sales_order_item:
			return

		if self.order_reference_state() == cps_rules.ORDER_REF_LEGACY:
			return

		line = self._lock_sales_order_line()
		if not line:
			frappe.throw(_("Sales Order line {0} not found.").format(self.sales_order_item))

		carded = self._carded_qty(exclude_self=True)
		remaining = flt(
			cps_rules.remaining_qty(line.get("qty"), carded), self.QTY_PRECISION
		)

		if flt(self.quantity_ordered, self.QTY_PRECISION) > remaining:
			frappe.throw(
				_("Quantity {0} exceeds the {1} still remaining on Sales Order line {2} (ordered {3}, already on job cards {4}).").format(
					flt(self.quantity_ordered, self.QTY_PRECISION),
					remaining,
					self.sales_order_item,
					flt(line.get("qty"), self.QTY_PRECISION),
					flt(carded, self.QTY_PRECISION),
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

		Scoped to ``self.doctype``: one Sales Order line produces one kind of
		card, because the snapshot's product type decides which kind it is and
		a line has exactly one snapshot.
		"""
		filters = {
			"sales_order_item": self.sales_order_item,
			"docstatus": ["in", [0, 1]],
		}
		if exclude_self and not self.is_new():
			filters["name"] = ["!=", self.name]

		rows = frappe.get_all(self.doctype, filters=filters, pluck="quantity_ordered")
		return sum(flt(qty) for qty in rows)

	def update_sales_order_rollup(self, exclude_self=False):
		"""Refresh the Job Card rollup on the Sales Order line (design §11.1).

		Written with ``db.set_value`` rather than through the document, because
		the Sales Order is submitted by the time any job card exists. The two
		rollup fields are the only Sales Order Item fields carrying
		``allow_on_submit`` for exactly this reason.
		"""
		if not self.get("sales_order_item"):
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
				"custom_jc_qty": flt(carded, self.QTY_PRECISION),
				"custom_jc_status": cps_rules.derive_jc_status(carded, so_qty),
			},
			update_modified=False,
		)


def describe_mismatch(mismatch):
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
