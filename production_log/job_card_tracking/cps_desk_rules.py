"""Pure shaping for the ERPNext Desk CPS helpers (WBS-25, WBS-26, WBS-28).

Frappe-free, like :mod:`cps_rules` and :mod:`cps_report_rules`. It takes plain
specification and price dicts and returns plain dicts, so the Desk preview and
the Item → specification list can be unit tested without a bench.

Two things this module deliberately does *not* do:

* It never decides that a line is acceptable. The preview reports what Sales
  Order validation would say using the very same reason functions in
  :mod:`cps_rules`, so a rep can never be shown a green preview on a line the
  submit then refuses.
* It never produces a value that survives a save. The commercial and technical
  values it returns land in ``read_only`` Sales Order Item fields that
  ``so_spec_control._clear_snapshot`` wipes on every draft save and
  ``_stamp_snapshot`` rewrites server-side on submit. The preview is what the
  rep sees while typing; the snapshot is what the order is held to.

Design references: §5.2 price eligibility, §7 V2-V7, §8.2 snapshot payload.
"""

from production_log.job_card_tracking import cps_rules

_get = cps_rules._get


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

SEVERITY_OK = "ok"
SEVERITY_WARNING = "warning"
SEVERITY_BLOCK = "block"

# Reasons that Sales Order validation only warns about while the order is a
# draft (design §7 V7). The preview grades them the same way, or it would tell a
# rep that a line is dead when saving it is in fact how you park an order whose
# price is still with the approver.
PREVIEW_WARNING_CODES = frozenset((cps_rules.BLOCK_NO_PRICE,))


def block_severity(block):
	"""How hard a :class:`cps_rules.SpecBlock` bites, or ``ok`` for None."""
	if block is None:
		return SEVERITY_OK
	return SEVERITY_WARNING if block.code in PREVIEW_WARNING_CODES else SEVERITY_BLOCK


# ---------------------------------------------------------------------------
# The Sales Order Item fields the preview drives
# ---------------------------------------------------------------------------

# Display-only. Every one of these is a ``read_only`` Custom Field that the
# server owns: listed in ``so_spec_control.SNAPSHOT_FIELDS``, cleared on draft
# save and rewritten on submit. The client fills them so the rep can see what
# they have selected without leaving the row.
PREVIEW_DISPLAY_FIELDS = (
	"custom_cps_rate",
	"custom_cps_uom",
	"custom_cps_valid_from",
	"custom_cps_price_row",
	"custom_spec_name",
	"custom_job_size",
	"custom_number_of_parts",
	"custom_number_of_colours",
)

# Genuine line inputs, not display. These are the rep's own fields and are only
# ever written when the specification and its price are both clean — clobbering
# a typed rate with a blank because the spec is cancelled would destroy work.
PREVIEW_APPLY_FIELDS = ("rate", "uom")


def build_display_fields(spec, price):
	"""The read-only Sales Order Item values implied by a spec and its price.

	Every key in :data:`PREVIEW_DISPLAY_FIELDS` is always present, valued None
	when unknown, so a caller can apply the dict verbatim and have that double as
	the clear. A partial dict would leave the previous specification's job size
	sitting under the new one's name.
	"""
	return {
		"custom_cps_rate": cps_rules.round_rate(_get(price, "rate")) if price else None,
		"custom_cps_uom": _get(price, "uom") if price else None,
		"custom_cps_valid_from": _get(price, "valid_from") if price else None,
		"custom_cps_price_row": _get(price, "name") if price else None,
		"custom_spec_name": _get(spec, "specification_name") if spec else None,
		"custom_job_size": _get(spec, "job_size") if spec else None,
		"custom_number_of_parts": _get(spec, "number_of_parts") if spec else None,
		"custom_number_of_colours": _get(spec, "number_of_colours") if spec else None,
	}


def empty_display_fields():
	"""The same shape as :func:`build_display_fields`, entirely blank."""
	return {fieldname: None for fieldname in PREVIEW_DISPLAY_FIELDS}


def build_apply_fields(price):
	"""The rate and UOM to put on the line, or ``{}`` when there is no price.

	The rate is rounded to the same 9 dp the CPS Price row holds, because the
	exact-match test at submit compares them (design §9.1) and a rate the client
	rounded on the way in would fail it.
	"""
	if not price or _get(price, "rate") in (None, ""):
		return {}
	return {"rate": cps_rules.round_rate(_get(price, "rate")), "uom": _get(price, "uom")}


# ---------------------------------------------------------------------------
# Technical preview
# ---------------------------------------------------------------------------

# Read straight off the specification, in the order a printer reads a job. These
# are a subset of the scalars ``cps_rules.build_spec_snapshot`` freezes, so what
# the rep previews and what the order is held to cannot drift apart in wording.
TECHNICAL_PREVIEW_FIELDS = (
	("product_type", "Product Type"),
	("specification_name", "Specification Name"),
	("job_size", "Job Size"),
	("pay_slip_size", "Pay Slip Size"),
	("number_of_parts", "Number of Parts"),
	("number_of_colours", "Number of Colours"),
	("ink_type", "Ink Type"),
	("numbering_required", "Numbering Required"),
	("standard_packing", "Standard Packing"),
	("standard_weight_per_carton", "Standard Weight per Carton"),
)

PART_PREVIEW_FIELDS = ("part_number", "paper_type", "gsm", "colour", "purpose")


def build_technical_preview(spec):
	"""Label/value rows describing the specification, unset values omitted.

	Unset rows are dropped rather than shown empty: a Label specification has no
	pay slip size, and printing ten "—" rows to prove it buries the four values
	that matter under the six that never applied. Zero counts as unset here
	because every field in the list is a count, a size or a Check — for all of
	them zero and blank mean the same thing.
	"""
	rows = []
	for fieldname, label in TECHNICAL_PREVIEW_FIELDS:
		value = _get(spec, fieldname) if spec else None
		if value in (None, "", 0):
			continue
		rows.append({"fieldname": fieldname, "label": label, "value": value})
	return rows


def build_part_preview(colour_of_parts=None):
	"""One row per part, for the specifications that have parts."""
	return [
		{field: _get(row, field) for field in PART_PREVIEW_FIELDS}
		for row in colour_of_parts or []
	]


# ---------------------------------------------------------------------------
# The preview itself
# ---------------------------------------------------------------------------


def build_line_preview(
	spec,
	item_code,
	customer,
	price=None,
	expected_product_type=None,
	requested_name=None,
	on_date_label=None,
	colour_of_parts=None,
):
	"""What the Desk should show for one specification on one order line.

	The reasons come from :func:`cps_rules.spec_block_reason` and
	:func:`cps_rules.price_block_reason` — the same functions, in the same order,
	that ``so_spec_control`` throws on. The message survives as an untranslated
	template plus arguments so the Frappe-bound caller can translate it.

	``price`` is the already-resolved eligible row, because eligibility needs a
	database read and this module does not do those.
	"""
	block = cps_rules.spec_block_reason(
		spec, item_code, customer, expected_product_type, requested_name=requested_name
	)
	if block is None:
		block = cps_rules.price_block_reason(
			price, _get(spec, "name"), on_date_label
		)

	severity = block_severity(block)

	# A warning still describes a real specification, so its technical values are
	# worth showing; only the price half is missing. A hard block describes a
	# specification that must not be used at all, and previewing its job size
	# would read as an invitation to keep it.
	usable = severity in (SEVERITY_OK, SEVERITY_WARNING)

	return {
		"ok": severity == SEVERITY_OK,
		"severity": severity,
		"block": _block_payload(block),
		"display": build_display_fields(spec, price) if usable else empty_display_fields(),
		"apply": build_apply_fields(price) if severity == SEVERITY_OK else {},
		"technical": build_technical_preview(spec) if usable else [],
		"parts": build_part_preview(colour_of_parts) if usable else [],
		"display_fields": list(PREVIEW_DISPLAY_FIELDS),
	}


def _block_payload(block):
	"""A :class:`cps_rules.SpecBlock` as a JSON-safe dict, or None."""
	if block is None:
		return None
	return {"code": block.code, "template": block.template, "args": list(block.args)}


def blank_line_preview():
	"""The payload that clears a line: no specification selected at all.

	Returned rather than assembled in the client so there is exactly one
	definition of "clear this line", and it lives next to the one that fills it.
	"""
	return {
		"ok": False,
		"severity": SEVERITY_OK,
		"block": None,
		"display": empty_display_fields(),
		"apply": {},
		"technical": [],
		"parts": [],
		"display_fields": list(PREVIEW_DISPLAY_FIELDS),
	}


# ---------------------------------------------------------------------------
# Item -> linked specifications (WBS-28)
# ---------------------------------------------------------------------------

LINKED_SPEC_COLUMNS = (
	"name",
	"customer",
	"specification_name",
	"product_type",
	"status",
	"docstatus_label",
	"revision",
	"is_orderable",
	"current_rate",
	"current_uom",
)

REVISION_ORIGINAL = "Original"


def revision_label(spec):
	"""Which revision of a specification this record is.

	A CPS is submittable, so a change to a submitted one is an amendment: Frappe
	names it ``CPT-SPEC-00012-1`` and points ``amended_from`` at its predecessor.
	Naming the predecessor is what makes a list of five near-identical rows
	readable.
	"""
	amended_from = (_get(spec, "amended_from") or "").strip()
	return "Amended from {0}".format(amended_from) if amended_from else REVISION_ORIGINAL


def is_orderable(spec):
	"""Whether a Sales Order line could actually use this specification.

	Submitted and Active, the same pair ``cps_rules.spec_block_reason`` insists
	on. Everything else is history, and the point of showing it is so a user can
	see that the record they remember is no longer the live one.
	"""
	try:
		docstatus = int(_get(spec, "docstatus") or 0)
	except (TypeError, ValueError):
		return False
	return docstatus == 1 and _get(spec, "status") == "Active"


def build_linked_spec_row(spec):
	"""One flat, scalar-only row for the Item's specification list."""
	return {
		"name": _get(spec, "name"),
		"customer": _get(spec, "customer"),
		"specification_name": _get(spec, "specification_name"),
		"product_type": _get(spec, "product_type"),
		"status": _get(spec, "status"),
		"docstatus_label": _docstatus_label(_get(spec, "docstatus")),
		"revision": revision_label(spec),
		"is_orderable": is_orderable(spec),
		"current_rate": _get(spec, "current_rate"),
		"current_uom": _get(spec, "current_uom"),
	}


def _docstatus_label(docstatus):
	try:
		return {0: "Draft", 1: "Submitted", 2: "Cancelled"}[int(docstatus or 0)]
	except (TypeError, ValueError, KeyError):
		return "Unknown"


def sort_linked_spec_rows(rows):
	"""Orderable rows first, then by customer, then by specification.

	The question being asked of this list is nearly always "who can I sell this
	Item to today", so the answer has to be at the top rather than interleaved
	with cancelled amendments from three years ago.
	"""
	return sorted(
		rows or [],
		key=lambda row: (
			not row.get("is_orderable"),
			(row.get("customer") or "").lower(),
			(row.get("specification_name") or "").lower(),
			row.get("name") or "",
		),
	)


def summarise_linked_specs(rows):
	"""Counts for the button badge and the dialog header."""
	rows = list(rows or [])
	orderable = [row for row in rows if row.get("is_orderable")]
	return {
		"total": len(rows),
		"orderable": len(orderable),
		"customers": len({row.get("customer") for row in orderable if row.get("customer")}),
	}
