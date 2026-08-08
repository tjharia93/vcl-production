"""Patch v9_5: put ``All`` back in the Workstation Product Line options.

``patch_v5_5`` refreshed the product-line taxonomy — renamed ``Label`` to
``Self Adhesive Label``, added ``Trading`` and ``R2R`` — and in doing so
dropped ``All`` from the ``Workstation.custom_product_line`` Select. Its own
docstring records the intent and the gap in the same breath: "``All`` is kept
in the option list — admins requested manual control over migrating WTs from
``All`` to explicit per-PL rows". ``All`` was indeed kept for the Workstation
*Product Line Tag* child table, and dropped from the Workstation Select. The
manual re-tagging it assumed would follow never happened.

The result is nine live Workstations holding a value their own field no longer
permits, and Frappe validates a Select on save — so every one of them is
frozen. Not read-only: *unsaveable*, with an error naming the eight allowed
values and no hint that the stored one used to be legal. Setting an hour rate
on Collater 01 is what surfaced it; nine of twenty machines could not be
edited at all.

Frozen: Collater 01, Collater 02, Design Desk, Miyakoshi 4, Roland 01,
Ruling Machine 01, Sheeting Machine 01, Sheeting Machine 02, Slitter 01.

The field also carries ``default: "All"``, which the same change left pointing
at a value it had just removed — so a newly created Workstation would have
been born invalid too. Restoring the option repairs both without touching the
default.

``All`` goes at the TOP of the list, which is where the Workstation Product
Line Tag child table already keeps it (``patch_v5_5``) — the two lists agreeing
matters more than alphabetical order.

**This is the option list, not a re-tagging.** Deciding which specific product
line each of those nine machines serves is a business call, and several of them
genuinely serve more than one — which is the case ``All`` exists to express and
the reason the tag child table was built alongside it. This patch only makes
the stored values legal again; nothing is re-tagged and no machine's meaning
changes.

Also mirrored into ``fixtures/custom_field.json``. Workstation Custom Fields
are in the ``fixtures`` list in ``hooks.py``, so the fixture is what a deploy
actually applies — without that edit the next migrate would re-import the
narrowed options and re-freeze all nine. Live, fixture and patch were verified
to agree before this was committed.

Idempotent: rewrites the options only when ``All`` is absent.
"""

import frappe

FIELD = "Workstation-custom_product_line"

# `All` first, matching the Workstation Product Line Tag list.
OPTIONS = (
	"All\n"
	"Computer Paper\n"
	"ETR\n"
	"Self Adhesive Label\n"
	"General Stationery and Exercise Book\n"
	"Mono Boxes\n"
	"Corrugation and Carton Department\n"
	"Trading\n"
	"R2R"
)


def execute():
	if not frappe.db.exists("Custom Field", FIELD):
		return

	current = frappe.db.get_value("Custom Field", FIELD, "options") or ""
	if "All" in [line.strip() for line in current.split("\n")]:
		return

	frappe.db.set_value("Custom Field", FIELD, "options", OPTIONS)
	frappe.clear_cache(doctype="Workstation")
