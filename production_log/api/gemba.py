"""S2 — EOD Gemba Report generator + Telegram push.

Runs at 17:00 EAT daily via the scheduled task wired in hooks.py.
Reads today's closed JCLs + their Job Traveller Run + Job Resource Consumption
rows, computes KPIs, renders the EOD Gemba PDF, posts to the configured
Telegram channel.

Per White Paper v4 §4.4 (Gemba input data-flow).

Telegram delivery (S2, 2026-05-20): the PDF is POSTed to an n8n webhook
which forwards it to Telegram. The bot token lives in n8n, never in Frappe.
Configuration — site_config.json keys (both optional, code defaults below):
  gemba_webhook_url — n8n webhook endpoint (defaults to GEMBA_WEBHOOK_URL)
  gemba_chat_id     — destination Telegram chat id (defaults to GEMBA_CHAT_ID)

Usage (manual):
  /api/method/production_log.api.gemba.generate_eod_report?date=2026-05-19
"""

from __future__ import annotations

import os
from datetime import date as date_cls, datetime

import frappe
from frappe import _


# Same JCL mapping as Release Plan
PRODUCT_LINE_JCL = {
	"Corrugation and Carton Department": "Job Card Carton",
	"Computer Paper":                    "Job Card Computer Paper",
	"ETR":                               "Job Card ETR",
	"Self Adhesive Label":               "Job Card Label",
}

OPEN_STATUSES   = ("Open", "Planned", "In Progress", "In Production", "Packing Pending", "On Hold")
CLOSED_STATUSES = ("Completed", "Closed")

# n8n webhook that forwards the EOD PDF to Telegram. The Telegram bot token
# is held by n8n — Frappe never stores it. Overridable via site_config
# key `gemba_webhook_url`.
GEMBA_WEBHOOK_URL = "https://vcl-intranet.tailb2b755.ts.net/webhook/gemba-telegram"

# Destination Telegram chat for the EOD report. Overridable per-site via
# site_config key `gemba_chat_id`.
GEMBA_CHAT_ID = "8566637123"


# ──────────────────────────────────────────────────────────────────────────
# public entry points
# ──────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def generate_eod_report(date=None, push_to_telegram=False):
	"""Generate the EOD Gemba PDF. Optionally push to Telegram.

	When called by the scheduler (17:00 EAT), the wrapper
	`scheduled_eod_run()` sets push_to_telegram=True.

	Returns:
		dict — {"pdf_filename": str, "report_date": "YYYY-MM-DD", "summary": {...}, "telegram_msg_id": int|None}
	"""
	target_date = _parse_date(date) if date else frappe.utils.today()

	per_line = []
	for product_line, jcl_doctype in PRODUCT_LINE_JCL.items():
		if not frappe.db.exists("DocType", jcl_doctype):
			continue
		per_line.append(_build_line_section(product_line, jcl_doctype, target_date))

	headline = _consolidate_headline(per_line)
	html = _render_gemba_html(target_date, headline, per_line)
	pdf_bytes = frappe.utils.pdf.get_pdf(html)

	pdf_filename = f"gemba-eod-{target_date}.pdf"
	telegram_msg_id = None
	if frappe.utils.cint(push_to_telegram):
		telegram_msg_id = _push_to_telegram(pdf_bytes, pdf_filename, headline, target_date)

	return {
		"pdf_filename":     pdf_filename,
		"report_date":      str(target_date),
		"summary":          headline,
		"telegram_msg_id":  telegram_msg_id,
	}


def scheduled_eod_run():
	"""Cron entry point — runs daily at 17:00 EAT via hooks.scheduler_events."""
	try:
		return generate_eod_report(push_to_telegram=True)
	except Exception:
		frappe.log_error(title="Gemba EOD cron — failure", message=frappe.get_traceback())
		raise


# ──────────────────────────────────────────────────────────────────────────
# per-line section build
# ──────────────────────────────────────────────────────────────────────────


def _build_line_section(product_line, jcl_doctype, target_date):
	closed_today = _query_closed_today(jcl_doctype, target_date)
	wip = _query_wip(jcl_doctype, target_date)
	backlog = _query_overdue_backlog(jcl_doctype, target_date)

	throughput = _throughput_by_station(jcl_doctype, target_date)
	bottleneck = _find_bottleneck(throughput)

	return {
		"product_line":  product_line,
		"closed_today":  closed_today,
		"wip":           wip,
		"backlog":       backlog,
		"throughput":    throughput,
		"bottleneck":    bottleneck,
		"jobs_closed":   len(closed_today),
		"jobs_wip":      len(wip),
		"jobs_backlog":  len(backlog),
		"otd_pct":       _on_time_delivery_pct(closed_today),
	}


def _safe_fields(jcl_doctype, candidates):
	"""Return only the candidate fields that actually exist on jcl_doctype's table.

	Different JCLs have slightly different field sets (e.g. JC ETR may not have
	customer_name as a denormalised column). Avoids "Unknown column" SQL errors.
	"""
	meta = frappe.get_meta(jcl_doctype)
	existing = {f.fieldname for f in meta.fields}
	# 'name' and 'modified' are always present on every doctype
	always = {"name", "modified", "creation", "owner", "modified_by", "docstatus", "idx"}
	return [f for f in candidates if f in existing or f in always]


def _query_closed_today(jcl_doctype, target_date):
	fields = _safe_fields(
		jcl_doctype,
		["name", "customer_name", "job_description", "quantity_ordered", "due_date", "modified"],
	)
	return frappe.db.get_all(
		jcl_doctype,
		filters={
			"docstatus": 1,
			"job_status": ("in", CLOSED_STATUSES),
			"modified": (">=", f"{target_date} 00:00:00"),
		},
		fields=fields,
		order_by="modified desc",
		limit=200,
	)


def _query_wip(jcl_doctype, target_date):
	fields = _safe_fields(
		jcl_doctype,
		["name", "customer_name", "due_date", "job_status"],
	)
	return frappe.db.get_all(
		jcl_doctype,
		filters={
			"docstatus": 1,
			"job_status": ("in", OPEN_STATUSES),
		},
		fields=fields,
		order_by="due_date asc",
		limit=200,
	)


def _query_overdue_backlog(jcl_doctype, target_date):
	fields = _safe_fields(
		jcl_doctype,
		["name", "customer_name", "due_date", "quantity_ordered"],
	)
	return frappe.db.get_all(
		jcl_doctype,
		filters={
			"docstatus": 1,
			"job_status": ("in", OPEN_STATUSES),
			"due_date":  ("<", target_date),
		},
		fields=fields,
		order_by="due_date asc",
		limit=50,
	)


def _throughput_by_station(jcl_doctype, target_date):
	"""Sum Qty Good per station across all closed Job Traveller Run rows today.

	Job Traveller Run is a child of the JCL; we walk via parent.parenttype.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			jtr.station       AS station,
			SUM(COALESCE(jtr.qty_good, 0))  AS total_good,
			SUM(COALESCE(jtr.qty_waste, 0)) AS total_waste,
			COUNT(*)                        AS run_count
		FROM `tabJob Traveller Run` jtr
		WHERE jtr.parenttype = %(jcl)s
		  AND jtr.date_in    = %(date)s
		GROUP BY jtr.station
		ORDER BY total_good DESC
		""",
		{"jcl": jcl_doctype, "date": target_date},
		as_dict=True,
	)
	# Compute waste %
	for r in rows:
		total_in = (r.total_good or 0) + (r.total_waste or 0)
		r["waste_pct"] = round(((r.total_waste or 0) / total_in * 100.0), 1) if total_in else 0.0
	return rows


def _find_bottleneck(throughput):
	if not throughput:
		return None
	max_good = max(r.total_good or 0 for r in throughput) or 1
	# Bottleneck = lowest throughput ratio
	worst = min(throughput, key=lambda r: (r.total_good or 0) / max_good)
	ratio = round((worst.total_good or 0) / max_good * 100.0, 1)
	return {"station": worst.station, "ratio_pct": ratio, "qty_good": worst.total_good}


def _on_time_delivery_pct(closed_today):
	if not closed_today:
		return None
	on_time = sum(
		1 for j in closed_today
		if j.due_date and frappe.utils.getdate(j.modified) <= frappe.utils.getdate(j.due_date)
	)
	return round(on_time / len(closed_today) * 100.0, 1)


# ──────────────────────────────────────────────────────────────────────────
# rendering + telegram
# ──────────────────────────────────────────────────────────────────────────


def _consolidate_headline(per_line):
	return {
		"total_closed":  sum(s["jobs_closed"]  for s in per_line),
		"total_wip":     sum(s["jobs_wip"]     for s in per_line),
		"total_backlog": sum(s["jobs_backlog"] for s in per_line),
		"lines":         [s["product_line"] for s in per_line],
	}


def _render_gemba_html(target_date, headline, per_line):
	template_path = os.path.join(
		frappe.get_app_path("production_log"),
		"templates",
		"includes",
		"eod_gemba.html",
	)
	with open(template_path) as f:
		template_src = f.read()

	return frappe.render_template(template_src, {
		"target_date": target_date,
		"headline":    headline,
		"per_line":    per_line,
	})


def _push_to_telegram(pdf_bytes, filename, headline, target_date):
	"""POST the EOD Gemba PDF to the n8n webhook, which forwards it to Telegram.

	The Telegram bot token is held by n8n — never by Frappe. Frappe sends
	only the PDF, a caption and the destination chat_id; none are secret.

	Config — site_config.json (both optional):
	  gemba_webhook_url — n8n endpoint (defaults to GEMBA_WEBHOOK_URL)
	  gemba_chat_id     — destination chat id (defaults to GEMBA_CHAT_ID)
	"""
	import base64
	import requests

	site = frappe.local.conf or {}
	webhook_url = site.get("gemba_webhook_url") or GEMBA_WEBHOOK_URL
	chat_id = site.get("gemba_chat_id") or GEMBA_CHAT_ID

	caption = (
		f"VCL EOD Gemba · {target_date}\n"
		f"Closed: {headline['total_closed']} · WIP: {headline['total_wip']} · "
		f"Backlog: {headline['total_backlog']}"
	)
	resp = requests.post(
		webhook_url,
		json={
			"pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
			"filename":   filename,
			"caption":    caption,
			"chat_id":    str(chat_id),
		},
		timeout=60,
	)
	resp.raise_for_status()
	result = resp.json()
	if not result.get("ok"):
		frappe.log_error(
			title="Gemba EOD — n8n webhook returned an error",
			message=frappe.as_json(result),
		)
		return None
	return result.get("message_id")


def _parse_date(value):
	if isinstance(value, (date_cls, datetime)):
		return value
	return frappe.utils.getdate(value)
