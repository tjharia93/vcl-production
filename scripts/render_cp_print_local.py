#!/usr/bin/env python3
"""Render the Computer Paper job card prints from the REPO, against live data.

The live printview only ever renders what is deployed. This renders the repo
HTML (Sales Copy and Production Copy) with jinja2 against a real job card read
over REST, using the app's own Jinja methods from cp_print.py, so a change can
be seen and measured before it is deployed. READ-ONLY: it never writes to the
site.

    python3 scripts/render_cp_print_local.py JC-CPT-2026-00092 [more...]
        [--as-sales]        render as a user with no production role
        [--out DIR]         default scripts/measure/
        [--format sales|production|both]  default both

Output: <out>/<jc>.html (production, same name check_cp_traveller_pagination.py
reads from its cache) and <out>/<jc>.sales.html. Run the pagination check
afterwards WITHOUT --fresh, so it measures these files rather than live.

The page wrapper (frappe's printview shell and CSS) is taken from one live
printview fetch, so the measured box model matches what Frappe serves.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys
import types
import urllib.parse

import jinja2
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JC_DIR = ROOT / "production_log/job_card_tracking/doctype/job_card_computer_paper"
FORMATS = {
	"production": JC_DIR / "computer_paper_job_traveller_v2.html",
	"sales": JC_DIR / "computer_paper_job_card_sales_copy.html",
}

cfg = {}
for line in (pathlib.Path.home() / "projects/vcl-erpnext-mcp/.env").read_text().splitlines():
	if "=" in line and not line.strip().startswith("#"):
		k, v = line.split("=", 1)
		cfg[k.strip()] = v.strip().strip('"').strip("'")
BASE = cfg["ERPNEXT_URL"].rstrip("/")
S = requests.Session()
S.headers["Authorization"] = f"token {cfg['ERPNEXT_API_KEY']}:{cfg['ERPNEXT_API_SECRET']}"


def rest_get_all(doctype, filters=None, fields=None, order_by=None, limit_page_length=0, pluck=None, **_):
	if isinstance(filters, dict):
		filters = [[k] + (v if isinstance(v, list) else ["=", v]) for k, v in filters.items()]
	params = {"fields": json.dumps(fields or ["name"]), "filters": json.dumps(filters or []),
	          "limit_page_length": limit_page_length or 0}
	if order_by:
		params["order_by"] = order_by
	r = S.get(f"{BASE}/api/resource/{urllib.parse.quote(doctype)}", params=params, timeout=60)
	r.raise_for_status()
	rows = [_dict(x) for x in r.json()["data"]]
	return [x[pluck] for x in rows] if pluck else rows


class _dict(dict):
	__getattr__ = dict.get


def rest_get_value(doctype, name, field):
	if not name:
		return None
	r = S.get(f"{BASE}/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name)}", timeout=60)
	if r.status_code != 200:
		return None
	return r.json()["data"].get(field)


def getdate(v=None):
	if not v:
		return dt.date.today()
	if isinstance(v, dt.datetime):
		return v.date()
	if isinstance(v, dt.date):
		return v
	return dt.date.fromisoformat(str(v)[:10])


def formatdate(v, fmt=None):
	if not v:
		return ""
	d = getdate(v)
	if fmt == "dd-MMM-yy":
		return d.strftime("%d-%b-%y")
	return d.strftime("%d/%m/%Y")


PREVIEW_NAMES = {"Administrator": "Administrator"}


def make_frappe(user, roles):
	f = types.ModuleType("frappe")
	f.session = _dict(user=user)
	f.get_all = rest_get_all
	f.get_roles = lambda u=None: list(roles)
	f.db = types.SimpleNamespace(get_value=rest_get_value)
	utils = types.ModuleType("frappe.utils")
	utils.getdate = getdate
	utils.nowdate = lambda: dt.date.today().isoformat()
	utils.formatdate = formatdate
	utils.now_datetime = dt.datetime.now
	utils.get_fullname = lambda u: PREVIEW_NAMES.get(u) or rest_get_value("User", u, "full_name") or u
	f.get_fullname = utils.get_fullname
	f.utils = utils
	sys.modules["frappe"] = f
	sys.modules["frappe.utils"] = utils
	return f


def to_doc(d):
	out = _dict(d)
	for k, v in list(out.items()):
		if isinstance(v, list):
			out[k] = [_dict(r) for r in v]
	return out


def qr_placeholder(_name):
	svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='84' height='84'><rect width='84' height='84' "
	       "fill='#fff' stroke='#000'/><text x='42' y='46' font-size='10' text-anchor='middle'>QR</text></svg>")
	return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def wrapper(jc):
	"""Frappe's printview shell from one live fetch, split around the format body."""
	q = urllib.parse.urlencode({"doctype": "Job Card Computer Paper", "name": jc,
	                            "format": "Standard", "no_letterhead": "1", "_lang": "en"})
	html = S.get(f"{BASE}/printview?{q}", timeout=300).text
	# The "Print / Get PDF" banner is hidden by print CSS this file cannot load.
	b = html.find('<div class="action-banner print-hide">')
	if b != -1:
		html = html[:b] + html[html.index("</div>", b) + len("</div>"):]
	start = html.index('<div class="print-format">') + len('<div class="print-format">')
	end = html.index("<script", start)
	end = html.rindex("</div>", start, html.rindex("</div>", start, end))
	return html[:start], html[end:]


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("jobs", nargs="+")
	ap.add_argument("--as-sales", action="store_true")
	ap.add_argument("--out", default=str(ROOT / "scripts/measure"))
	ap.add_argument("--format", default="both", choices=["sales", "production", "both"])
	args = ap.parse_args()

	# Preview identities only; nothing is looked up for them on the site.
	if args.as_sales:
		user, roles = "sales.preview@vimit.com", ["Sales User", "All", "Guest"]
	else:
		user, roles = "release.preview@vimit.com", ["Release to Production", "All", "Guest"]
	PREVIEW_NAMES[user] = "Release Holder (preview)" if not args.as_sales else "Sales User (preview)"
	frappe = make_frappe(user, roles)
	from production_log.job_card_tracking import cp_print

	env = jinja2.Environment(extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])
	env.globals.update(frappe=frappe, cp_csra_rep=cp_print.cp_csra_rep,
	                   cp_production_copy_allowed=cp_print.cp_production_copy_allowed,
	                   cp_print_user=cp_print.cp_print_user, qr_for_job=qr_placeholder)
	out = pathlib.Path(args.out)
	out.mkdir(parents=True, exist_ok=True)
	kinds = ["sales", "production"] if args.format == "both" else [args.format]
	for jc in args.jobs:
		r = S.get(f"{BASE}/api/resource/Job Card Computer Paper/{jc}", timeout=60)
		r.raise_for_status()
		doc = to_doc(r.json()["data"])
		head, tail = wrapper(jc)
		for kind in kinds:
			body = env.from_string(FORMATS[kind].read_text()).render(doc=doc)
			suffix = ".sales" if kind == "sales" else ""
			who = ".as-sales" if args.as_sales else ""
			p = out / f"{jc}{suffix}{who}.html"
			p.write_text(head + body + tail)
			print(f"{jc} {kind:10s} -> {p}")


if __name__ == "__main__":
	main()
