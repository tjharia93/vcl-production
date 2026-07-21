"""Read-only CPS → Item migration and enforcement-readiness report.

53 of the 56 live Computer Paper specifications have no ``linked_item``, and
strict Sales Order enforcement cannot be switched on until that is resolved.
This module answers, from live data, the two questions that decision needs:
*what is actually linked today*, and *what would break if the setting flipped*.

**This module never writes.** There is no auto-map endpoint, no ``dry_run=False``
and no ``frappe.db.set_value`` anywhere in it — not because writing is hard, but
because a mapping applied in bulk is indistinguishable from a mapping guessed in
bulk once it is in the database. Where ``cps_rules.resolve_item_link`` finds a
provably sole candidate, the row carries it as ``proposed_item`` for a human to
apply by hand.

There is no new DocType either. This is a whitelisted function returning plain
dicts, so it can be called from a bench console, from Compass, or exported to
CSV without a schema change to roll back.

Design references: §4.2 controlled items, §5.2 price eligibility, §7 Sales Order
validation, §15 step 10 (the enforcement flag this report gates).
"""

import frappe
from frappe import _

from production_log.job_card_tracking import cps_report_rules, cps_rules, so_spec_control

# Reading this report means reading every customer's agreed specification and
# which of them have no price — commercially sensitive across the whole book, so
# it is not scoped by CSRA and therefore must not be open to a Sales User.
READ_ROLES = ("System Manager", "Sales Master Manager")

# Bounds on the history scan. Both are reported in ``notes`` when they bite:
# a report that silently truncates reads as "nothing else to see".
SO_HISTORY_LIMIT = 2000
OPEN_SO_LIMIT = 2000

OPEN_SO_EXCLUDED_STATUS = ("Closed", "Completed")

CPS = "Customer Product Specification"


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def _require_read_access():
	"""Gate on role rather than on DocType permission.

	The report crosses Customer, Item and Sales Order as well as the
	specification itself, so a ``has_permission`` check on any one of them would
	understate what the caller is about to see.
	"""
	if not set(frappe.get_roles()) & set(READ_ROLES):
		frappe.throw(
			_("{0} role required to read the CPS migration report.").format(
				_(" or ").join(READ_ROLES)
			),
			frappe.PermissionError,
		)


def _has_field(doctype, fieldname):
	"""Whether a field has landed on this site (custom or otherwise)."""
	try:
		return bool(frappe.get_meta(doctype).get_field(fieldname))
	except Exception:
		return False


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


def _load_specs(product_type=None, customer=None):
	"""Every specification in scope, including drafts and cancelled ones.

	Cancelled and draft records are deliberately included: the report exists to
	describe the migration surface, and "3 of your unlinked specs are cancelled"
	is an answer, whereas silently filtering them makes the totals disagree with
	the list view.
	"""
	filters = {}
	if product_type:
		filters["product_type"] = product_type
	if customer:
		filters["customer"] = customer

	fields = [
		"name",
		"product_type",
		"specification_name",
		"customer",
		"status",
		"docstatus",
		"current_rate",
		"current_uom",
		"modified",
	]
	if _has_field(CPS, cps_rules.ITEM_LINK_FIELD):
		fields.append(cps_rules.ITEM_LINK_FIELD)

	return frappe.get_all(CPS, filters=filters, fields=fields, order_by="name asc")


def _load_candidate_items(notes):
	"""Controlled Items, each tagged with the product type that controls it.

	``Item.custom_requires_cps`` is the denormalised flag maintained by
	``so_spec_control.derive_item_control_flag``; the product type itself lives
	on the controlling Item Group, so it is resolved once per distinct group
	rather than once per Item.
	"""
	if not _has_field("Item", "custom_requires_cps"):
		notes.append(
			"Item.custom_requires_cps has not landed on this site, so no candidate "
			"Items could be scored. Run the v8_0 custom field patch first."
		)
		return []

	items = frappe.get_all(
		"Item",
		filters={"custom_requires_cps": 1, "disabled": 0},
		fields=["name as item_code", "item_name", "item_group"],
		order_by="name asc",
	)

	group_types = {}
	for item in items:
		group = item.get("item_group")
		if group not in group_types:
			controlling = so_spec_control.item_group_requires_cps(group)
			group_types[group] = controlling.get("custom_cps_product_type") if controlling else None
		item["cps_product_type"] = group_types[group]

	if not items:
		notes.append(
			"No Item is flagged custom_requires_cps, so every unlinked specification "
			"reports match 'none'. Tick Requires CPS on the controlling Item Group first."
		)
	return items


def _customer_item_history(customers, notes):
	"""Items each customer has actually been sold, from submitted Sales Orders.

	This is the strongest evidence the scorer has — an invoice beats a name
	resemblance — so it is worth a query per customer. Read through the ORM
	rather than raw SQL so row-level permissions and the child-table schema stay
	the framework's problem, and bounded per customer so one 20-year account
	cannot make the report time out.
	"""
	history = {}
	truncated = []

	for customer in sorted(c for c in customers if c):
		try:
			orders = frappe.get_all(
				"Sales Order",
				filters={"customer": customer, "docstatus": 1},
				pluck="name",
				order_by="transaction_date desc",
				limit_page_length=SO_HISTORY_LIMIT,
			)
			if len(orders) >= SO_HISTORY_LIMIT:
				truncated.append(customer)

			history[customer] = set(
				frappe.get_all(
					"Sales Order Item",
					filters={"parent": ["in", orders], "parenttype": "Sales Order"},
					pluck="item_code",
					distinct=True,
				)
			) if orders else set()
		except Exception as exc:
			# History is corroborating evidence, not the report's subject. If it
			# is unqueryable the candidates degrade to name matching, which is
			# weaker but still useful — losing the whole report would not be.
			history[customer] = set()
			notes.append(
				"Sales Order history unavailable for {0} ({1}); candidates for this "
				"customer are scored on name similarity only.".format(customer, exc)
			)

	if truncated:
		notes.append(
			"Sales Order history capped at the {0} most recent orders for: {1}. "
			"Older orders were not scanned.".format(SO_HISTORY_LIMIT, ", ".join(truncated))
		)
	return history


def _specs_with_approved_price(spec_names):
	"""Specifications holding an Approved price effective on or before today.

	Same eligibility rule as ``cps_rules.resolve_eligible_price`` reduced to a
	set membership test: a future-dated approved row is a scheduled increase, not
	a price you can order at today, so it does not clear ``missing-price``.
	"""
	if not spec_names:
		return set()

	return set(
		frappe.get_all(
			"CPS Price",
			filters={
				"parent": ["in", list(spec_names)],
				"parenttype": CPS,
				"parentfield": "pricing",
				"approval_status": cps_rules.APPROVAL_APPROVED,
				"valid_from": ["<=", frappe.utils.today()],
			},
			pluck="parent",
			distinct=True,
		)
	)


def _existing_customers(customers):
	"""The subset of referenced Customers that still exist.

	A specification pointing at a deleted or renamed Customer can never match a
	Sales Order, so it is a migration blocker rather than a cosmetic gap.
	"""
	wanted = [c for c in customers if c]
	if not wanted:
		return set()
	return set(frappe.get_all("Customer", filters={"name": ["in", wanted]}, pluck="name"))


def _open_so_lines_without_cps(product_type, notes):
	"""Submitted, still-open order lines on controlled Items carrying no CPS.

	These are what would have failed V1 had enforcement already been on. They
	cannot be fixed from the order screen once submitted, so they are counted
	against ``ready_to_enforce``: flipping the setting with any of these open
	means the next amendment to that order cannot be saved.
	"""
	if not (_has_field("Sales Order Item", "custom_cps") and _has_field("Item", "custom_requires_cps")):
		notes.append(
			"Sales Order Item.custom_cps or Item.custom_requires_cps is missing on this "
			"site, so open controlled order lines could not be checked."
		)
		return []

	orders = frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "status": ["not in", OPEN_SO_EXCLUDED_STATUS]},
		fields=["name", "customer", "transaction_date", "status"],
		order_by="transaction_date desc",
		limit_page_length=OPEN_SO_LIMIT,
	)
	if len(orders) >= OPEN_SO_LIMIT:
		notes.append(
			"Open Sales Order scan capped at the {0} most recent orders; older open "
			"orders were not checked.".format(OPEN_SO_LIMIT)
		)
	if not orders:
		return []

	by_name = {o["name"]: o for o in orders}
	lines = frappe.get_all(
		"Sales Order Item",
		# "not set" rather than an ``in`` list: an unset Link is NULL, and
		# ``IN ('', NULL)`` never matches NULL in SQL, so the ``in`` form would
		# quietly report zero missing specifications.
		filters={"parent": ["in", list(by_name)], "parenttype": "Sales Order", "custom_cps": ["is", "not set"]},
		fields=["parent", "idx", "item_code", "item_name", "qty", "rate"],
		order_by="parent asc, idx asc",
	)
	if not lines:
		return []

	controlled = _controlled_items_by_code({line["item_code"] for line in lines}, product_type)

	rows = []
	for line in lines:
		if line["item_code"] not in controlled:
			continue
		order = by_name[line["parent"]]
		rows.append(
			{
				"sales_order": line["parent"],
				"transaction_date": order.get("transaction_date"),
				"customer": order.get("customer"),
				"status": order.get("status"),
				"idx": line["idx"],
				"item_code": line["item_code"],
				"item_name": line.get("item_name"),
				"qty": line.get("qty"),
				"rate": line.get("rate"),
				"issue": "controlled-line-without-cps",
			}
		)
	return rows


def _controlled_items_by_code(item_codes, product_type):
	"""Which of ``item_codes`` are controlled, optionally by one product type."""
	if not item_codes:
		return set()

	items = frappe.get_all(
		"Item",
		filters={"name": ["in", list(item_codes)], "custom_requires_cps": 1},
		fields=["name", "item_group"],
	)
	if not product_type:
		return {i["name"] for i in items}

	group_types = {}
	controlled = set()
	for item in items:
		group = item["item_group"]
		if group not in group_types:
			controlling = so_spec_control.item_group_requires_cps(group)
			group_types[group] = controlling.get("custom_cps_product_type") if controlling else None
		if group_types[group] == product_type:
			controlled.add(item["name"])
	return controlled


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


@frappe.whitelist()
def cps_migration_report(product_type="Computer Paper", customer=None, include_candidates=1):
	"""Readiness of every in-scope specification, as plain dicts.

	Defaults to Computer Paper because that is the only product type Phase 2
	enforces (DN-7); pass ``product_type=None`` for the whole book.

	``include_candidates=0`` skips the scoring pass entirely — useful when you
	only want the counts and the data-quality issues, and do not want to pay for
	an Item scan and a Sales Order history query per customer.

	Returns a dict with ``summary``, ``specs``, ``open_so_lines_without_cps``,
	``duplicates`` and ``notes``. Every value in every row is a scalar, so the
	same payload feeds CSV, Compass and a console print without reshaping.
	"""
	_require_read_access()

	include_candidates = bool(int(include_candidates or 0))
	notes = []

	if not _has_field(CPS, cps_rules.ITEM_LINK_FIELD):
		notes.append(
			"Customer Product Specification.{0} does not exist on this site. Every "
			"specification reports as unlinked until the v8_0 patch has run.".format(
				cps_rules.ITEM_LINK_FIELD
			)
		)

	specs = _load_specs(product_type, customer)
	spec_names = [s["name"] for s in specs]
	customers = {s.get("customer") for s in specs}

	priced = _specs_with_approved_price(spec_names)
	existing_customers = _existing_customers(customers)
	duplicate_keys = cps_report_rules.duplicate_customer_item_keys(specs)

	items = _load_candidate_items(notes) if include_candidates else []
	history = _customer_item_history(customers, notes) if include_candidates else {}
	if not include_candidates:
		notes.append("include_candidates=0: candidate scoring and proposed mappings were skipped.")

	rows, decisions = [], []
	for spec in specs:
		decision = cps_rules.resolve_item_link(
			spec, items, history.get(spec.get("customer")) or set()
		)
		decisions.append(decision)
		rows.append(
			cps_report_rules.build_spec_row(
				spec,
				decision,
				has_approved_price=spec["name"] in priced,
				customer_exists=bool(spec.get("customer")) and spec["customer"] in existing_customers,
				duplicate_keys=duplicate_keys,
			)
		)

	open_lines = _open_so_lines_without_cps(product_type, notes)
	summary = cps_report_rules.summarise_report(rows, open_lines)

	# Stated separately from the verdict so a reader can see that enforcement is
	# blocked by prices rather than by links, which are different jobs.
	summary["link_readiness"] = (
		cps_rules.summarise_readiness(decisions) if include_candidates else None
	)

	if not so_spec_control.control_enabled():
		notes.append(
			"Selling Settings.{0} is currently off, so none of these rules are live "
			"yet.".format(so_spec_control.CONTROL_FLAG)
		)

	return {
		"generated_at": frappe.utils.now(),
		"generated_by": frappe.session.user,
		"product_type": product_type,
		"customer": customer,
		"columns": list(cps_report_rules.REPORT_COLUMNS),
		"summary": summary,
		"specs": rows,
		"duplicates": [
			{"customer": key[0], "linked_item": key[1], "specs": ", ".join(names)}
			for key, names in sorted(duplicate_keys.items())
		],
		"open_so_line_columns": list(cps_report_rules.OPEN_SO_LINE_COLUMNS),
		"open_so_lines_without_cps": open_lines,
		"notes": notes,
	}


@frappe.whitelist()
def cps_migration_report_csv(product_type="Computer Paper", customer=None, include_candidates=1):
	"""The same report as two CSV strings, for download or paste into a sheet.

	Returned as strings rather than written to a File, because writing a File is
	a mutation and this report does not make any.
	"""
	report = cps_migration_report(product_type, customer, include_candidates)

	return {
		"generated_at": report["generated_at"],
		"summary": report["summary"],
		"specs_csv": cps_report_rules.to_csv(report["specs"]),
		"open_so_lines_csv": cps_report_rules.to_csv(
			report["open_so_lines_without_cps"], cps_report_rules.OPEN_SO_LINE_COLUMNS
		),
		"notes": report["notes"],
	}
