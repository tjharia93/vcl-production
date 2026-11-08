"""Pure price semantics for CPS Price rows (Stream A §5).

No Frappe import. The rounding allowance, UOM normalisation, deterministic row
selection, the gross/net helper, the immutability of the ``entered_*`` fields
and the IQ -> CPS mapping all live here so they are unit testable; the
Frappe-bound callers are ``so_spec_control`` (Sales Order lines),
``cps_pricing`` (row validation and approval), ``iq_price_transfer`` and
``release`` (checks 9-10).
"""

from collections import namedtuple

from production_log.job_card_tracking import cps_rules

# --- Allowance (final, approved by Tanuj 08/11/2026) --------------------------

ALLOWANCE_DEFAULT_KES = 1.0
ALLOWANCE_DEFAULT_PCT = 1.0

# Selling Settings fields. They replace custom_cps_price_tolerance_pct and
# custom_cps_price_floor_pct, both 0 on the live site and deleted by the patch.
ALLOWANCE_FIELD = "custom_cps_rounding_allowance"
ALLOWANCE_PCT_FIELD = "custom_cps_rounding_allowance_pct"

DEFAULT_CURRENCY = cps_rules.DEFAULT_CURRENCY

# --- Tax basis ---------------------------------------------------------------

TAX_BASIS_NET = "Net"
TAX_BASIS_GROSS_VAT = "Gross entered — VAT 16%"
TAX_BASIS_GROSS_EXEMPT = "Gross entered — exempt"
TAX_BASES = (TAX_BASIS_NET, TAX_BASIS_GROSS_VAT, TAX_BASIS_GROSS_EXEMPT)
VAT_RATE_PCT = 16.0

# IQ carries a two-option basis (Net / Gross) and the row records which 16%
# variant that meant.
IQ_TAX_BASIS_NET = "Net"
IQ_TAX_BASIS_GROSS = "Gross"

# Fields frozen once set on a row (Codex r3 §3).
IMMUTABLE_ENTERED_FIELDS = ("entered_gross", "entered_uom", "tax_rate", "tax_basis", "rounding_method")

# Row sources added by §5.
SOURCE_INTERNAL_QUOTATION = "Internal Quotation"
SOURCE_MANAGEMENT_REPRICE = "Management reprice"
SOURCE_LPO = "LPO"

APPROVED_VIA_RULE = "Rule auto"
APPROVED_VIA_IQ = "IQ transfer"
APPROVED_VIA_APPROVER = "Approver"
APPROVED_VIA_MANAGEMENT = "Management"


def _get(row, key):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def _num(value):
	if value in (None, ""):
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def row_currency(row):
	"""A row with no currency is KES - every row written before §5 is."""
	return (_get(row, "currency") or "").strip() or DEFAULT_CURRENCY


# --- Gross / net --------------------------------------------------------------


def tax_rate_for_basis(tax_basis):
	"""The VAT percentage a tax basis implies; Net and exempt are 0."""
	return VAT_RATE_PCT if tax_basis == TAX_BASIS_GROSS_VAT else 0.0


def net_from_gross(entered_gross, tax_rate_pct):
	"""``rate = entered_gross / (1 + tax)`` at 9 dp. A 0% rate is the identity."""
	gross = _num(entered_gross)
	if gross is None:
		return None
	rate = _num(tax_rate_pct) or 0.0
	return cps_rules.round_rate(gross / (1.0 + rate / 100.0))


def gross_entry_values(entered_gross, tax_basis):
	"""What the "enter incl. VAT" helper writes: rate, entered_gross, tax_rate, tax_basis."""
	if tax_basis not in TAX_BASES:
		raise ValueError("Unknown tax basis {0!r}".format(tax_basis))
	tax_rate = tax_rate_for_basis(tax_basis)
	return {
		"rate": net_from_gross(entered_gross, tax_rate),
		"entered_gross": cps_rules.round_rate(entered_gross),
		"tax_rate": tax_rate,
		"tax_basis": tax_basis,
	}


def immutable_fields_changed(before, after):
	"""``entered_*``, ``tax_rate``, ``tax_basis`` and ``rounding_method`` never change once set."""
	if before is None:
		return []
	changed = []
	for fieldname in IMMUTABLE_ENTERED_FIELDS:
		old = _get(before, fieldname)
		if old in (None, "", 0):
			continue
		new = _get(after, fieldname)
		if fieldname in ("entered_gross", "tax_rate"):
			if cps_rules.round_rate(old) != cps_rules.round_rate(new):
				changed.append(fieldname)
		elif (str(old).strip() if old is not None else None) != (str(new).strip() if new is not None else None):
			changed.append(fieldname)
	return changed


# --- Allowance ----------------------------------------------------------------


def rounding_allowance(approved_rate, allowance_kes=ALLOWANCE_DEFAULT_KES, allowance_pct=ALLOWANCE_DEFAULT_PCT):
	"""``min(KES allowance, |approved| x pct)``. A zero approved rate allows nothing."""
	rate = abs(_num(approved_rate) or 0.0)
	if rate == 0.0:
		return 0.0
	kes = _num(allowance_kes)
	pct = _num(allowance_pct)
	kes = ALLOWANCE_DEFAULT_KES if kes is None else max(kes, 0.0)
	pct = ALLOWANCE_DEFAULT_PCT if pct is None else max(pct, 0.0)
	return min(kes, rate * pct / 100.0)


def normalised_line_rate(line_rate, line_conversion_factor, row_conversion_factor):
	"""The line's net rate expressed per the price row's UOM.

	Both factors are "row UOM -> stock UOM" as ERPNext stores them. The line's
	is the one stored on the Sales Order line; the row's is the one frozen at
	approval. Neither is read from the current Item master. Returns None when a
	factor is missing or zero - the caller treats that as a block (V8).
	"""
	rate = _num(line_rate)
	line_cf = _num(line_conversion_factor)
	row_cf = _num(row_conversion_factor)
	if rate is None or not line_cf or not row_cf:
		return None
	return cps_rules.round_rate(rate / line_cf * row_cf)


PriceCheck = namedtuple(
	"PriceCheck",
	("ok", "code", "normalised_rate", "approved_rate", "allowance", "variance"),
)

PRICE_OK = "ok"
PRICE_NO_ROW = "no-approved-row"
PRICE_CURRENCY = "currency-mismatch"
PRICE_UOM_UNCONVERTIBLE = "uom-unconvertible"
PRICE_OUTSIDE_ALLOWANCE = "outside-allowance"
PRICE_ZERO_NOT_EXACT = "zero-rate-not-exact"


def check_line_rate(line_rate, line_conversion_factor, line_currency, row,
                    allowance_kes=ALLOWANCE_DEFAULT_KES, allowance_pct=ALLOWANCE_DEFAULT_PCT):
	"""§5 / §7 check 10 in one call.

	Compares the normalised line rate with the row's net ``rate`` inside the
	allowance. Same UOM is the common case: when the row carries no frozen
	conversion factor and the line's UOM equals the row's, the factors cancel
	and the rates compare directly.
	"""
	if row is None or _get(row, "rate") in (None, ""):
		return PriceCheck(False, PRICE_NO_ROW, None, None, None, None)

	approved = cps_rules.round_rate(_get(row, "rate"))
	if ((line_currency or "").strip() or DEFAULT_CURRENCY) != row_currency(row):
		return PriceCheck(False, PRICE_CURRENCY, None, approved, None, None)

	row_cf = _num(_get(row, "conversion_factor"))
	line_cf = _num(line_conversion_factor)
	if not row_cf:
		# A row written before §5 froze no factor: it is priced per its own UOM
		# and the caller has already required the line to be in that UOM (V8).
		normalised = cps_rules.round_rate(line_rate) if _num(line_rate) is not None else None
	else:
		normalised = normalised_line_rate(line_rate, line_cf, row_cf)
	if normalised is None:
		return PriceCheck(False, PRICE_UOM_UNCONVERTIBLE, None, approved, None, None)

	allowance = rounding_allowance(approved, allowance_kes, allowance_pct)
	variance = cps_rules.round_rate(normalised - approved)
	if approved == 0.0:
		ok = normalised == 0.0
		return PriceCheck(ok, PRICE_OK if ok else PRICE_ZERO_NOT_EXACT, normalised, approved, 0.0, variance)

	ok = abs(variance) <= allowance + 1e-9
	return PriceCheck(ok, PRICE_OK if ok else PRICE_OUTSIDE_ALLOWANCE, normalised, approved, allowance, variance)


# --- Deterministic row selection (§5, Codex r3 §3) ----------------------------


def select_price_row(rows, currency, on_date):
	"""The one Approved row that prices an order dated ``on_date``.

	Approved, same currency, ``valid_from <= on_date``; greatest ``valid_from``,
	then latest ``approved_on``, then name - so two people reading the same
	spec on the same order always bind the same row, and a row approved today
	never resolves an older order by itself (``valid_from`` decides, not
	``approved_on``).
	"""
	on_date = cps_rules.to_date(on_date)
	if on_date is None:
		return None
	wanted = (currency or "").strip() or DEFAULT_CURRENCY

	best, best_key = None, None
	for row in rows or []:
		if _get(row, "approval_status") != cps_rules.APPROVAL_APPROVED:
			continue
		if row_currency(row) != wanted:
			continue
		valid_from = cps_rules.to_date(_get(row, "valid_from"))
		if valid_from is None or valid_from > on_date:
			continue
		key = (valid_from, str(_get(row, "approved_on") or ""), str(_get(row, "name") or ""))
		if best_key is None or key > best_key:
			best, best_key = row, key
	return best


# --- IQ -> CPS price transfer (§5) ----------------------------------------------

IQ_REQUIRED_FIELDS = ("vcl_uom", "vcl_currency", "vcl_tax_basis")
IQ_APPROVED_STATUS = "Approved"


def iq_transfer_errors(iq):
	"""Why an approved IQ cannot transfer: nothing is inferred from product type."""
	errors = []
	for fieldname in IQ_REQUIRED_FIELDS:
		if not (_get(iq, fieldname) or "").strip():
			errors.append("{0} not confirmed on the Internal Quotation".format(fieldname))
	basis = (_get(iq, "vcl_tax_basis") or "").strip()
	if basis and basis not in (IQ_TAX_BASIS_NET, IQ_TAX_BASIS_GROSS):
		errors.append("vcl_tax_basis must be Net or Gross, not {0!r}".format(basis))
	if _num(_get(iq, "customer_price")) is None:
		errors.append("customer_price is empty")
	return errors


def iq_transfer_ready(iq):
	"""Approved and every precondition met."""
	return _get(iq, "status") == IQ_APPROVED_STATUS and not iq_transfer_errors(iq)


def find_transferred_row(rows, iq_name):
	"""The row this IQ already produced, if any - the idempotency key."""
	for row in rows or []:
		if _get(row, "source") == SOURCE_INTERNAL_QUOTATION and _get(row, "source_ref") == iq_name:
			return row
	return None


def price_row_from_iq(iq, conversion_factor, approved_on, approved_by):
	"""The CPS Price row an Approved IQ produces (§5 mapping). Raises on a missing precondition."""
	errors = iq_transfer_errors(iq)
	if errors:
		raise ValueError("; ".join(errors))

	customer_price = _num(_get(iq, "customer_price"))
	basis = (_get(iq, "vcl_tax_basis") or "").strip()
	if basis == IQ_TAX_BASIS_GROSS:
		values = gross_entry_values(customer_price, TAX_BASIS_GROSS_VAT)
	else:
		values = {
			"rate": cps_rules.round_rate(customer_price),
			"entered_gross": None,
			"tax_rate": 0.0,
			"tax_basis": TAX_BASIS_NET,
		}

	return {
		"valid_from": cps_rules.to_date(approved_on),
		"rate": values["rate"],
		"entered_gross": values["entered_gross"],
		"entered_uom": (_get(iq, "vcl_uom") or "").strip(),
		"tax_rate": values["tax_rate"],
		"tax_basis": values["tax_basis"],
		"uom": (_get(iq, "vcl_uom") or "").strip(),
		"currency": (_get(iq, "vcl_currency") or "").strip() or DEFAULT_CURRENCY,
		"conversion_factor": _num(conversion_factor),
		"source": SOURCE_INTERNAL_QUOTATION,
		"source_ref": _get(iq, "name"),
		"approval_status": cps_rules.APPROVAL_APPROVED,
		"approved_by": approved_by,
		"approved_on": approved_on,
		"approved_via": APPROVED_VIA_IQ,
		"rule_benchmark": cps_rules.round_rate(_get(iq, "management_price")) if _num(_get(iq, "management_price")) is not None else None,
		"approval_notes": "IQ {0} {1}".format(_get(iq, "name"), _get(iq, "approval_status") or "").strip(),
	}


def iq_revocation_values(iq_name):
	"""IQ cancelled: the transferred row is Rejected with a note, never deleted."""
	return {
		"approval_status": cps_rules.APPROVAL_REJECTED,
		"approval_notes": "IQ {0} cancelled; price withdrawn".format(iq_name),
	}
