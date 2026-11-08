"""CPS Approval Rule - who approves a specification's technical content and its price (§6).

Resolution lives in :mod:`production_log.job_card_tracking.cps_approval_rules`
(pure) and :mod:`production_log.job_card_tracking.cps_approval` (Frappe). This
controller only keeps a row internally consistent.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from production_log.job_card_tracking import cps_approval_rules as rules


class CPSApprovalRule(Document):
	def validate(self):
		if self.test != rules.TEST_ALWAYS and (self.benchmark or rules.BENCHMARK_NONE) == rules.BENCHMARK_NONE:
			frappe.throw(_("A rule testing the rate needs a benchmark."), title=_("CPS Approval Rule"))
		if self.test in (rules.TEST_RATE_GE_MARKUP, rules.TEST_MARGIN_GE) and not self.threshold_pct:
			frappe.throw(_("This test needs a threshold percentage."), title=_("CPS Approval Rule"))
		if self.when_met == rules.OUTCOME_ROUTE or self.when_not_met == rules.OUTCOME_ROUTE:
			if not (self.approver_user or self.approver_role):
				frappe.msgprint(
					_("Route with no approver: the fallback ({0}) will apply at once.").format(self.fallback),
					indicator="orange",
				)
		if not self.management_role:
			self.management_role = rules.DEFAULT_MANAGEMENT_ROLE
		if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
			frappe.throw(_("Valid To is before Valid From."), title=_("CPS Approval Rule"))
