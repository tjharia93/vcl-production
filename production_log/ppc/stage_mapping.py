"""PPC Computer Paper — stage mapping and quantity math.

Locked operating truth (ppc_may26_v1):
  quantity_ordered  = cartons
  packing           = sets/forms per carton
  number_of_parts   = physical parts/sheets per set
  finished_sets_required   = quantity_ordered × packing
  physical_sheets_required = quantity_ordered × packing × number_of_parts
"""

import math
import frappe


STAGES = ("Printing by Part", "Collation + Numbering", "Packing")
PRINTING = "Printing by Part"
COLLATION_NUMBERING = "Collation + Numbering"
PACKING = "Packing"

POOL_STATUSES = ("Open", "Planned", "In Production", "Packing Pending", "On Hold")


def _to_float(v, default=0.0):
	try:
		return float(v) if v is not None else default
	except (TypeError, ValueError):
		return default


def _to_int(v, default=0):
	try:
		return int(v) if v is not None else default
	except (TypeError, ValueError):
		return default


def finished_sets_required(jc):
	return _to_float(jc.get("quantity_ordered")) * _to_float(jc.get("packing"))


def physical_sheets_required(jc):
	return finished_sets_required(jc) * _to_int(jc.get("number_of_parts") or 1)


def collated_sets_from_cartons(cartons, packing):
	return _to_float(cartons) * _to_float(packing)


def numbering_range_count(number_from, number_to):
	if number_from is None or number_to is None:
		return 0
	return _to_int(number_to) - _to_int(number_from) + 1


def customer_completion(jc):
	"""Fraction (0..1) of cartons ordered that have been packed as good."""
	ordered = _to_float(jc.get("quantity_ordered"))
	packed = _to_float(jc.get("packed_cartons"))
	if ordered <= 0:
		return 0.0
	return packed / ordered


def get_part_labels(jc):
	"""Return part labels for a JC, derived from CPS colour_of_parts.

	Falls back to ['Part 1', ..., 'Part N'] if the CPS rows aren't reachable.
	"""
	parts = _to_int(jc.get("number_of_parts") or 1)
	cps = jc.get("customer_product_spec")
	if cps:
		try:
			rows = frappe.get_all(
				"Colour of Parts",
				filters={"parent": cps, "parenttype": "Customer Product Specification"},
				fields=["part_label", "idx"],
				order_by="idx asc",
				limit=parts,
			)
			labels = [r.part_label or f"Part {r.idx}" for r in rows]
			if labels:
				return labels
		except Exception:
			pass
	return [f"Part {i+1}" for i in range(parts)]


def part_printed_quantities(jc_name):
	"""Sum good_quantity per part_label across all submitted Production Actuals."""
	rows = frappe.db.sql(
		"""
		SELECT pi.part_label, SUM(IFNULL(pi.good_quantity, 0)) AS qty
		FROM `tabPPC Production Actual Item` pi
		INNER JOIN `tabPPC Production Actual` pa ON pa.name = pi.parent
		WHERE pi.source_job_card = %(jc)s
		  AND pi.stage = 'Printing by Part'
		  AND pa.docstatus = 1
		GROUP BY pi.part_label
		""",
		{"jc": jc_name},
		as_dict=True,
	)
	return {r.part_label or "": _to_float(r.qty) for r in rows}


def printing_readiness(jc, jc_name):
	"""Return (ready_sets, required_sets, pct).

	ready_sets = min printed quantity across all required parts.
	"""
	required_sets = finished_sets_required(jc)
	parts = get_part_labels(jc)
	if not parts or required_sets <= 0:
		return 0.0, required_sets, 0.0
	totals = part_printed_quantities(jc_name)
	ready = min((totals.get(p, 0.0) for p in parts), default=0.0)
	pct = (ready / required_sets) if required_sets else 0.0
	return ready, required_sets, pct


def evaluate_completion_gates(jc, jc_name):
	"""Return (status, reason).

	status is one of: 'Completed', 'Packing Pending', None.
	None means no auto-transition (still in flight).
	"""
	ordered = _to_float(jc.get("quantity_ordered"))
	packed = _to_float(jc.get("packed_cartons"))
	loose = _to_float(jc.get("loose_balance_sets"))
	required_sets = finished_sets_required(jc)

	# All required parts printed enough?
	ready_sets, _, _ = printing_readiness(jc, jc_name)
	parts_ok = ready_sets >= required_sets

	# Collation completed enough?
	collated_sets = _to_float(jc.get("collated_quantity"))
	collation_ok = collated_sets >= required_sets

	# Numbering, only if required
	numbering_ok = True
	if jc.get("numbering_required"):
		numbered = _to_float(jc.get("numbered_quantity"))
		numbering_ok = numbered >= required_sets

	packed_ok = packed >= ordered

	if parts_ok and collation_ok and numbering_ok and packed_ok:
		return "Completed", "all gates passed"
	if not packed_ok and loose > 0:
		return "Packing Pending", "loose sets exist but packed cartons short"
	return None, ""
