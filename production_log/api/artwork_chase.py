"""Weekly chase on specifications not saying where their artwork is.

Runs Friday 16:00 EAT via ``hooks.scheduler_events``. The selection rules live
in :mod:`production_log.job_card_tracking.artwork_chase_rules`, which is
Frappe-free and unit tested; this module does the querying, the rendering and
the sending, and nothing else.

Why it exists: the artwork submit gate was removed on 2026-08-07 because the
live estate had been routing around it for months — thirty-nine of forty-three
submitted Printed specifications carried no file. Removing a control without
replacing it is how the artwork quietly stops being tracked at all, so the
refusal became a reminder. This is the reminder.

**Silent when there is nothing to chase.** A weekly email that arrives saying
"nothing outstanding" is one people filter, and a filtered email is not a
control either. The run is logged whether or not it sends, so a silent Friday
can be told from a broken scheduler by looking at the Scheduled Job Log.
"""

import frappe
from frappe.utils import getdate, nowdate

from production_log.job_card_tracking import artwork_chase_rules as rules

RECIPIENTS = ("vimitgraphics@vimit.com", "tanuj.haria@vimit.com")

SUBJECT = "Artwork outstanding — {0} Computer Paper specification(s)"

# Everything the report reads. Listed rather than fetched with "*" so a field
# renamed out from under this report fails loudly on the query instead of
# quietly reporting every specification as outstanding.
FIELDS = (
	"name",
	"specification_name",
	"customer",
	"product_type",
	"print_type",
	"docstatus",
	"creation",
	"artwork",
	"artwork_tracker",
	"artwork_not_ready",
)


def scheduled_weekly_run():
	"""Cron entry point — Friday 16:00 EAT via hooks.scheduler_events."""
	try:
		return run_chase(send=True)
	except Exception:
		frappe.log_error(
			title="Artwork chase — failure", message=frappe.get_traceback()
		)
		raise


def run_chase(send=False, cutoff=None, today=None):
	"""Build the chase, and send it if there is anything to say.

	Returns the outstanding rows and the summary counts either way, so the same
	call answers "what would it send" from the console without sending it.
	"""
	cutoff = cutoff or rules.ARTWORK_CHASE_FROM
	today = getdate(today or nowdate())

	rows = fetch_rows()
	outstanding = rules.select_outstanding(rows, cutoff)
	counts = rules.summarise(rows, cutoff)

	frappe.logger().info(
		"artwork chase: {0} outstanding of {1} in scope since {2}".format(
			len(outstanding), counts["in_scope"], cutoff
		)
	)

	if send and outstanding:
		frappe.sendmail(
			recipients=list(RECIPIENTS),
			subject=SUBJECT.format(len(outstanding)),
			message=render(outstanding, counts, cutoff, today),
			reference_doctype="Customer Product Specification",
			now=True,
		)

	return {"outstanding": outstanding, "counts": counts, "cutoff": cutoff}


def fetch_rows():
	"""Every Computer Paper specification the report could care about.

	Filtered to the product type in the query and to everything else in the
	rules, so the decisions all live in one testable place rather than half in
	SQL. The population is in the low hundreds; there is nothing to gain by
	pushing the rest of the conditions down.
	"""
	return frappe.get_all(
		"Customer Product Specification",
		filters={"product_type": rules.COMPUTER_PAPER},
		fields=list(FIELDS),
		limit_page_length=0,
	)


def render(outstanding, counts, cutoff, today):
	"""The email body.

	Plain and narrow on purpose — this is read on a phone as often as not, and
	the only thing it has to convey is which specifications need a file and how
	long they have been waiting.
	"""
	site = frappe.utils.get_url()
	head = (
		"<p>These Computer Paper specifications are submitted and printed, and "
		"nothing has been recorded about their artwork — no file, no Design &amp; "
		"Artwork Tracker job, and not marked as still being drawn.</p>"
	)

	body = [head, "<table cellpadding='6' cellspacing='0' border='0' "
	              "style='border-collapse:collapse;font-family:Calibri,sans-serif;font-size:14px'>"]
	body.append(
		"<tr style='background:#2B3990;color:#fff;text-align:left'>"
		"<th>Specification</th><th>Customer</th><th>Job</th>"
		"<th style='text-align:right'>Waiting</th></tr>"
	)
	for i, row in enumerate(outstanding):
		days = rules.age_in_days(row, today)
		shade = "#F4F5FA" if i % 2 else "#FFFFFF"
		body.append(
			"<tr style='background:{shade}'>"
			"<td><a href='{site}/app/customer-product-specification/{name}'>{name}</a></td>"
			"<td>{customer}</td><td>{job}</td>"
			"<td style='text-align:right'>{days} day{s}</td></tr>".format(
				shade=shade,
				site=site,
				name=frappe.utils.escape_html(row.get("name") or ""),
				customer=frappe.utils.escape_html(row.get("customer") or ""),
				job=frappe.utils.escape_html(row.get("specification_name") or ""),
				days=days,
				s="" if days == 1 else "s",
			)
		)
	body.append("</table>")

	# What was looked at, not only what was found. An email that reports a
	# number without its denominator cannot be sanity-checked by its reader.
	body.append(
		"<p style='color:#666;font-size:12px;font-family:Calibri,sans-serif'>"
		"Of {in_scope} submitted Printed specification(s) created since {cutoff}: "
		"{file} with a file, {tracker} linked to a tracker job, {deferred} marked "
		"as still being drawn, {outstanding} with nothing recorded.<br>"
		"Specifications created before {cutoff} are not chased — artwork was not "
		"asked for until then. Cancelled and draft specifications are not chased."
		"</p>".format(cutoff=cutoff, **counts)
	)
	return "".join(body)
