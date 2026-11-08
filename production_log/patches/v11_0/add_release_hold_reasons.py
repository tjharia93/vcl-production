"""Two hold reasons for the release gate on the three job cards (§7a).

``hold_reason`` is a Custom Field (v6_0 PPC block, in fixtures/custom_field.json
which is the source of truth and already carries both). This patch exists for
the window on a site where fixtures have not synced yet, and for
``after_install``. Idempotent: options are appended only when missing.
"""

import frappe

from production_log.job_card_tracking import release_rules

CARDS = ("Job Card Carton", "Job Card Computer Paper", "Job Card Label")


def execute():
	for doctype in CARDS:
		name = "{0}-hold_reason".format(doctype)
		if not frappe.db.exists("Custom Field", name):
			continue
		options = (frappe.db.get_value("Custom Field", name, "options") or "").split("\n")
		missing = [o for o in release_rules.RELEASE_HOLD_REASONS if o not in options]
		if not missing:
			continue
		frappe.db.set_value("Custom Field", name, "options", "\n".join(options + missing), update_modified=False)
		frappe.clear_cache(doctype=doctype)
		print("{0}: hold_reason gains {1}".format(doctype, ", ".join(missing)))
