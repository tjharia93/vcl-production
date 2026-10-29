"""Who may see what on a Computer Paper job card print (TRK-00342, Option A).

One job card, two copies:

* **Sales Copy** (``Computer Paper Job Card - Sales Copy``): what was sold. It
  never carries packing, carton count or carton tare. Anyone who can read the
  card may print it.
* **Production Copy** (``Computer Paper Job Traveller v2``): the full traveller
  with packing and press detail. It is printed only by a holder of
  ``Release to Production`` (VCL Management and named delegates) or a
  production role. Anyone else gets an "access denied" page instead.

Frappe does not role-gate print formats, and a Jinja print format reads
``doc`` directly, so field permlevels do NOT hide a value it prints. The
check therefore lives inside the format, through the Jinja methods below
(registered in hooks.py).

The sales rep printed on either copy is the customer's rep in Customer Sales
Rep Assignment (CSRA) on the order date, never the user who raised the card.
It resolves the same way vcl_compass does (``api/order_notify._csra_reps``).

The pure functions take plain values so they are tested without a bench.
"""

RELEASE_ROLE = "Release to Production"
MANAGEMENT_ROLE = "VCL Management Team"

# Production roles live on the site (read 2026-10-29). Manufacturing
# Manager/User are the ERPNext roles that already hold the doctype; the rest
# are the production_log and Production Floor roles.
PRODUCTION_ROLES = (
	"Manufacturing Manager",
	"Manufacturing User",
	"Production Manager",
	"Production Supervisor",
	"Production User",
	"VCL Production Manager",
	"VCL Production User",
	"PPC Planner",
)

# May print the Production Copy and read the packing fields.
PRODUCTION_COPY_ROLES = ("System Manager", MANAGEMENT_ROLE, RELEASE_ROLE) + PRODUCTION_ROLES

# May also change the packing fields (permlevel 1 write).
PACKING_WRITE_ROLES = ("System Manager", MANAGEMENT_ROLE, RELEASE_ROLE, "Manufacturing Manager")

SALES_COPY_FORMAT = "Computer Paper Job Card - Sales Copy"
PRODUCTION_COPY_FORMAT = "Computer Paper Job Traveller v2"


def may_print_production_copy(user, roles):
	"""True when ``user`` holding ``roles`` may see the Production Copy."""
	if user == "Administrator":
		return True
	return bool(set(roles or ()) & set(PRODUCTION_COPY_ROLES))


def pick_csra_rep(rows, on_date):
	"""The CSRA sales representative in force on ``on_date``, or None.

	``rows`` are Active CSRA rows for one customer, each a mapping with
	``sales_representative``, ``effective_from`` and ``effective_to`` (date or
	ISO string, ``effective_to`` may be empty). The latest ``effective_from``
	not after ``on_date`` whose ``effective_to`` is empty or not before it wins.
	"""
	d = str(on_date)[:10]
	live = []
	for r in rows or ():
		frm = str(r.get("effective_from") or "0001-01-01")[:10]
		to = str(r.get("effective_to") or "9999-12-31")[:10]
		if frm <= d <= to and r.get("sales_representative"):
			live.append((frm, r["sales_representative"]))
	if not live:
		return None
	live.sort(key=lambda x: x[0], reverse=True)
	return live[0][1]


# --- Frappe-bound, registered as Jinja methods ------------------------------


def cp_csra_rep(customer, on_date=None):
	"""Display name of the customer's CSRA rep on ``on_date`` (default today).

	Empty string when CSRA names nobody; the format prints the gap in red so
	it is chased, rather than falling back to whoever raised the card.
	"""
	import frappe
	from frappe.utils import getdate, nowdate

	if not customer:
		return ""
	d = str(getdate(on_date or nowdate()))
	rows = frappe.get_all(
		"Customer Sales Rep Assignment",
		filters={"customer": customer, "status": "Active", "effective_from": ["<=", d]},
		fields=["sales_representative", "effective_from", "effective_to"],
		order_by="effective_from desc",
	)
	rep = pick_csra_rep(rows, d)
	if not rep:
		return ""
	return frappe.db.get_value("Sales Person", rep, "sales_person_name") or rep


def cp_production_copy_allowed():
	"""May the session user print the Production Copy?"""
	import frappe

	user = frappe.session.user
	return may_print_production_copy(user, frappe.get_roles(user))


def is_releaser(user, roles):
	"""May ``user`` release a card, i.e. stand as "Released by" on the print?

	Production roles may print the Production Copy (a reprint on the floor),
	but printing it does not make them the releaser.
	"""
	if user == "Administrator":
		return False
	return bool(set(roles or ()) & {RELEASE_ROLE, MANAGEMENT_ROLE})


def cp_print_user():
	"""Who is printing, for the Production Copy release block.

	``{"name", "date", "time", "is_releaser"}``. The block pre-fills "Released
	by" only when the printer holds Release to Production or VCL Management
	Team. A production user's reprint leaves it as a write-in.
	"""
	import frappe
	from frappe.utils import now_datetime

	user = frappe.session.user
	stamp = now_datetime()
	return {
		"name": frappe.utils.get_fullname(user) or user,
		"date": stamp.strftime("%d/%m/%Y"),
		"time": stamp.strftime("%H:%M"),
		"is_releaser": is_releaser(user, frappe.get_roles(user)),
	}
