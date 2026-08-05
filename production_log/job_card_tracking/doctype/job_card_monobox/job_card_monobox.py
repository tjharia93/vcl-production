import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

MONOBOX_PRODUCT_TYPE = "Monobox"

# Scalar values copied from the specification onto the card, so the card is
# self-contained at print time and a later spec revision cannot silently
# restate what the floor already ran. (spec_fieldname, jc_fieldname)
SNAPSHOT_FIELDS = (
	("specification_name",        "specification_name"),
	("mbx_board_grade",           "board_grade"),
	("mbx_board_gsm",             "board_gsm"),
	("mbx_print_side",            "print_side"),
	("mbx_sheet_size",            "sheet_size"),
	("mbx_sheet_length",          "sheet_length"),
	("mbx_sheet_width",           "sheet_width"),
	("mbx_length",                "mbx_length"),
	("mbx_width",                 "mbx_width"),
	("mbx_height",                "mbx_height"),
	("mbx_tuck_flap",             "tuck_flap"),
	("mbx_glue_flap",             "glue_flap"),
	("mbx_dust_flap",             "dust_flap"),
	("mbx_blank_length",          "blank_length"),
	("mbx_blank_width",           "blank_width"),
	("mbx_ups_per_sheet",         "ups_per_sheet"),
	("mbx_cutting_die",           "cutting_die"),
	("mbx_die_notes",             "die_notes"),
	("mbx_window_width",          "window_width"),
	("mbx_window_height",         "window_height"),
	("mbx_window_panel",          "window_panel"),
	("mbx_window_offset_bottom",  "window_offset_bottom"),
	("mbx_window_offset_left",    "window_offset_left"),
	("mbx_film_material",         "film_material"),
	("mbx_film_micron",           "film_micron"),
	("mbx_film_patch_width",      "film_patch_width"),
	("mbx_film_patch_height",     "film_patch_height"),
	("mbx_coating_type",          "coating_type"),
	("printing_or_plain",         "printing_or_plain"),
	("ink_type",                  "ink_type"),
	("colour_notes",              "colour_notes"),
)

# Checks snapshot separately: a falsy value is meaningful for them, whereas for
# the fields above an empty spec value must not blank a card the planner has
# already filled in by hand.
SNAPSHOT_CHECKS = (
	("has_window",                "has_window"),
	("uses_c",                    "uses_c"),
	("uses_m",                    "uses_m"),
	("uses_y",                    "uses_y"),
	("uses_k",                    "uses_k"),
)

# The route. Inherited on first link only — see populate_route.
ROUTE_FIELDS = (
	("mbx_applies_printing",      "applies_printing"),
	("mbx_applies_coating",       "applies_coating"),
	("mbx_applies_diecut",        "applies_diecut"),
	("mbx_applies_window_patch",  "applies_window_patch"),
	("mbx_applies_gluing",        "applies_gluing"),
	("mbx_applies_bundling",      "applies_bundling"),
)

SPOT_COLOUR_FIELDS = (
	"pantone_code", "pantone_name", "hex_preview",
	"cmyk_c", "cmyk_m", "cmyk_y", "cmyk_k", "notes",
)


class JobCardMonobox(Document):
	"""A custom-printed monobox job.

	Monobox is not a Carton: the Carton card's stages are corrugated
	(corrugating, slotting, stitching) and its spec fields (flute, ply, liners)
	describe a different product. This card carries the monobox route instead —
	board prep and printing, coating, die-cutting, window patching, folding and
	gluing, bundling — with the stages that apply chosen per job.

	Capture is paper-first. The traveller is filled on the floor and its
	close-out is keyed back in here; there is no per-run child table yet. That
	is deliberate — the form has to settle on the floor before digital capture
	is built on top of it.
	"""

	def validate(self):
		self.validate_customer_product_spec()
		self.populate_specification_snapshot()
		self.populate_route()
		self.validate_dimensions()
		self.validate_quantity()
		self.validate_route()
		self.fetch_sales_order_qty()
		self.calculate_closeout()
		self.set_status()

	def on_submit(self):
		self.set_status()

	def on_cancel(self):
		self.set_status()

	# ── Validation ────────────────────────────────────────────────────────────

	def validate_customer_product_spec(self):
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		if spec.customer != self.customer:
			frappe.throw(
				_("Specification {0} does not belong to customer {1}.").format(
					self.customer_product_spec, self.customer
				)
			)

		if spec.product_type != MONOBOX_PRODUCT_TYPE:
			frappe.throw(
				_("Specification {0} is not a Monobox specification (found: {1}).").format(
					self.customer_product_spec, spec.product_type
				)
			)

		if spec.status != "Active":
			frappe.throw(
				_(
					"Specification {0} is not Active (current status: {1}). "
					"Please select an Active specification."
				).format(self.customer_product_spec, spec.status)
			)

	def validate_dimensions(self):
		for fieldname, label in (
			("mbx_length", _("Length (mm)")),
			("mbx_width", _("Width (mm)")),
			("mbx_height", _("Height (mm)")),
		):
			if not self.get(fieldname) or self.get(fieldname) <= 0:
				frappe.throw(_("{0} must be greater than zero.").format(label))

	def validate_quantity(self):
		if self.quantity_ordered in (None, ""):
			frappe.throw(_("Quantity Ordered is required."))

		if flt(self.quantity_ordered) <= 0:
			frappe.throw(_("Quantity Ordered must be greater than zero."))

	def validate_route(self):
		"""A job has to run through something, and a window has to be patched.

		The second rule is the one worth having: a windowed box whose route
		skips patching is a box with a hole in it, and nothing else in the
		system would notice.
		"""
		if not any(self.get(jc_field) for _spec_field, jc_field in ROUTE_FIELDS):
			frappe.throw(
				_("Select at least one production stage in the Production Route.")
			)

		if self.has_window and not self.applies_window_patch:
			frappe.throw(
				_(
					"This job has a window but Window Patching is not in the route. "
					"Either tick Window Patching or clear Has Window."
				)
			)

	# ── Snapshot from the specification ───────────────────────────────────────

	def populate_specification_snapshot(self):
		if not self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)

		for spec_field, jc_field in SNAPSHOT_FIELDS:
			value = getattr(spec, spec_field, None)
			if value is not None and value != "":
				setattr(self, jc_field, value)

		for spec_field, jc_field in SNAPSHOT_CHECKS:
			setattr(self, jc_field, 1 if getattr(spec, spec_field, 0) else 0)

		self.spot_colours = []
		for src in (spec.spot_colours or []):
			row = self.append("spot_colours", {})
			for fieldname in SPOT_COLOUR_FIELDS:
				setattr(row, fieldname, getattr(src, fieldname, None))

		self.recalculate_number_of_colours()

	def populate_route(self):
		"""Inherit the route from the specification, once.

		Only on the first link. After that the card owns its route, because the
		whole point of holding the flags here is that a one-off — skip the
		lamination on a rush job — must not require revising a specification
		every other job is running against.
		"""
		if not self.customer_product_spec:
			return

		before = None if self.is_new() else self.get_doc_before_save()
		if before is not None and before.customer_product_spec == self.customer_product_spec:
			return

		spec = frappe.get_doc("Customer Product Specification", self.customer_product_spec)
		for spec_field, jc_field in ROUTE_FIELDS:
			setattr(self, jc_field, 1 if getattr(spec, spec_field, 0) else 0)

	def recalculate_number_of_colours(self):
		if self.printing_or_plain == "Plain":
			self.number_of_colours = 0
			return

		ticks = sum(
			1 for fieldname in ("uses_c", "uses_m", "uses_y", "uses_k")
			if self.get(fieldname)
		)
		self.number_of_colours = ticks + len(self.spot_colours or [])

	# ── Order ─────────────────────────────────────────────────────────────────

	def fetch_sales_order_qty(self):
		"""Read the ordered quantity off the Sales Order rather than recomputing it.

		Optional link by design — most monobox work arrives as an LPO against a
		verbal order — so everything downstream degrades to the typed
		``quantity_ordered`` when it is absent.
		"""
		if not self.sales_order:
			self.so_qty = 0
			return

		self.so_qty = flt(frappe.db.get_value("Sales Order", self.sales_order, "total_qty"))

	# ── Close-out ─────────────────────────────────────────────────────────────

	def calculate_closeout(self):
		"""Derive only what is genuinely derivable; leave the rest as entered.

		Waste is a residual, not an independent measurement — deriving it is
		what makes an unbalanced material account visible instead of letting
		someone write a figure that squares the books.
		"""
		self.output_difference = flt(self.boxes_produced) - flt(self.quantity_ordered)

		self.waste_sheets = (
			flt(self.sheets_issued) - flt(self.sheets_used) - flt(self.sheets_returned)
		)

		consumed = flt(self.sheets_issued) - flt(self.sheets_returned)
		self.board_yield_pct = (flt(self.sheets_used) / consumed * 100.0) if consumed else 0.0

		self.film_consumed_kg = flt(self.film_issued_kg) - flt(self.film_returned_kg)

		self.total_stage_hours = sum(
			flt(row.total_hours) for row in (self.stage_summary or [])
		)

	# ── Status ────────────────────────────────────────────────────────────────

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			if self.status not in ("In Progress", "Completed"):
				self.status = "In Progress"
		elif self.docstatus == 2:
			self.status = "Cancelled"


@frappe.whitelist()
def get_monobox_customer_product_spec_query(
	doctype, txt, searchfield, start, page_len, filters
):
	"""Link-field query: Active Monobox specifications for this customer."""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters.get("customer"):
		return []

	return frappe.db.sql(
		"""
		SELECT name, specification_name, customer
		FROM `tabCustomer Product Specification`
		WHERE customer = %(customer)s
		AND product_type = 'Monobox'
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
