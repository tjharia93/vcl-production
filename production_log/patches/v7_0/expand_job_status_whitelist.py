"""S1 patch — placeholder marker for the whitelist expansion.

The actual code change is in production_log/job_card_tracking/utils.py
(set_job_status now accepts the full 8-value enum live on JC Computer Paper
since v6_0). This patch exists as an audit entry confirming the migration
ran, and verifies the whitelist matches reality post-deploy.

Per Sprint-0 audit finding (msg 267 §5): JC Computer Paper Property Setter
listed 8 status options (Open / Planned / In Production / Packing Pending /
Completed / Closed / On Hold / Cancelled) but utils.py whitelist only allowed
4. Code-side fix happened in utils.py; this patch is the audit record.
"""

import frappe


EXPECTED_STATUSES = {
	"Open",
	"Planned",
	"In Production",
	"Packing Pending",
	"Completed",
	"Closed",
	"On Hold",
	"Cancelled",
}


def execute():
	from production_log.job_card_tracking import utils

	current = set(getattr(utils, "ALLOWED_STATUSES", set()))
	if not EXPECTED_STATUSES.issubset(current):
		missing = EXPECTED_STATUSES - current
		frappe.log_error(
			title="v7_0 expand_job_status_whitelist — drift",
			message=(
				f"utils.ALLOWED_STATUSES missing values: {sorted(missing)}. "
				f"Edit production_log/job_card_tracking/utils.py to include them."
			),
		)
