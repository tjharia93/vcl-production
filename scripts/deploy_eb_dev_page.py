#!/usr/bin/env python3
"""Deploy an exercise-book dev Web Page from git, refusing to overwrite a live edit.

    py -3 scripts/deploy_eb_dev_page.py --page v3 --check     # diff live against the repo; writes nothing
    py -3 scripts/deploy_eb_dev_page.py --page v3 --create    # first deploy: create the Web Page (refuses if it exists)
    py -3 scripts/deploy_eb_dev_page.py --page v3             # deploy: refuses if live changed since the last stamp
    py -3 scripts/deploy_eb_dev_page.py --page v3 --pull      # adopt a reviewed live edit into the repo

Source of truth: exercise-book-production/dev-page-<page>/{index.html,page.js,page.css}
plus deploy-stamp.json ({name, modified, sha256_js, sha256_html, sha256_css, deployed_at, git_commit}).
Credentials: env FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET (never written anywhere).
Rule for every session: no REST edits of these Web Pages outside this script.
Standard library only, so it runs on the Windows PC as well as on Linux.
"""

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = {
	"v3": {
		"dir": ROOT / "exercise-book-production" / "dev-page-v3",
		"name": "exercise-book-production-v3-preview",  # Frappe names Web Pages from the title; the route is the URL
		"route": "exercise-book-production-v3-dev",
		"title": "Exercise Book Production v3 (preview)",
	},
}
FIELDS = {"index.html": "main_section_html", "page.js": "javascript", "page.css": "css"}


def env(k):
	v = os.environ.get(k)
	if not v and os.name == "nt":
		try:
			v = subprocess.check_output(["powershell", "-NoProfile", "-c", f"[Environment]::GetEnvironmentVariable('{k}','User')"], text=True).strip()
		except Exception:
			v = None
	if not v:
		sys.exit(f"Missing {k} in the environment.")
	return v


BASE = None
AUTH = None


def call(method, data=None, get=False):
	url = f"{BASE}/api/method/{method}"
	headers = {"Authorization": AUTH, "Accept": "application/json"}
	if get:
		url += "?" + urllib.parse.urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in (data or {}).items()})
		req = urllib.request.Request(url, headers=headers)
	else:
		headers["Content-Type"] = "application/json"
		req = urllib.request.Request(url, data=json.dumps(data or {}).encode(), headers=headers, method="POST")
	try:
		with urllib.request.urlopen(req, timeout=60) as r:
			return json.loads(r.read().decode()).get("message")
	except urllib.error.HTTPError as e:
		body = e.read().decode(errors="replace")
		if e.code == 404 or "DoesNotExistError" in body:
			return None
		sys.exit(f"{method}: HTTP {e.code}: {body[:400]}")


def sha(text):
	return hashlib.sha256((text or "").encode()).hexdigest()


def repo_files(cfg):
	out = {}
	for fname, field in FIELDS.items():
		p = cfg["dir"] / fname
		out[field] = p.read_text(encoding="utf-8") if p.exists() else ""
	return out


def live_doc(cfg):
	return call("frappe.client.get", {"doctype": "Web Page", "name": cfg["name"]}, get=True)


def stamp_path(cfg):
	return cfg["dir"] / "deploy-stamp.json"


def read_stamp(cfg):
	p = stamp_path(cfg)
	return json.loads(p.read_text()) if p.exists() else None


def write_stamp(cfg, doc):
	try:
		commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
	except Exception:
		commit = ""
	stamp = {"name": doc["name"], "modified": doc["modified"], "sha256_js": sha(doc.get("javascript")),
		"sha256_html": sha(doc.get("main_section_html")), "sha256_css": sha(doc.get("css")),
		"deployed_at": dt.datetime.now().isoformat(timespec="seconds"), "git_commit": commit}
	stamp_path(cfg).write_text(json.dumps(stamp, indent=1) + "\n")
	return stamp


def drifted(stamp, doc):
	return (doc["modified"] != stamp["modified"] or sha(doc.get("javascript")) != stamp["sha256_js"]
		or sha(doc.get("main_section_html")) != stamp["sha256_html"] or sha(doc.get("css")) != stamp.get("sha256_css", sha("")))


def show_diff(a, b, label):
	d = list(difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), f"live:{label}", f"repo:{label}", lineterm="", n=1))
	print("\n".join(d[:200]) + ("\n… (diff truncated)" if len(d) > 200 else ""))
	return bool(d)


def main():
	global BASE, AUTH
	ap = argparse.ArgumentParser()
	ap.add_argument("--page", default="v3", choices=sorted(PAGES))
	mode = ap.add_mutually_exclusive_group()
	mode.add_argument("--check", action="store_true")
	mode.add_argument("--create", action="store_true")
	mode.add_argument("--pull", action="store_true")
	args = ap.parse_args()
	cfg = PAGES[args.page]
	BASE = env("FRAPPE_URL").rstrip("/")
	AUTH = f"token {env('FRAPPE_API_KEY')}:{env('FRAPPE_API_SECRET')}"
	repo = repo_files(cfg)
	doc = live_doc(cfg)
	stamp = read_stamp(cfg)

	if args.check:
		if not doc:
			print(f"{cfg['name']} does not exist live. Deploy with --create.")
			return 1
		same = all((doc.get(f) or "") == repo[f] for f in FIELDS.values())
		print(f"live modified {doc['modified']}; stamp {stamp['modified'] if stamp else 'none'}")
		if stamp and drifted(stamp, doc):
			print("LIVE HAS DRIFTED from the last deploy. Review with the diff below, then --pull to adopt it.")
			for f in FIELDS.values():
				show_diff(doc.get(f), repo[f], f)
			return 2
		if same:
			print("Live matches the repo.")
			return 0
		for f in FIELDS.values():
			show_diff(doc.get(f), repo[f], f)
		print("Repo is ahead of live.")
		return 1

	if args.pull:
		if not doc:
			sys.exit("Nothing live to pull.")
		for fname, field in FIELDS.items():
			(cfg["dir"] / fname).write_text(doc.get(field) or "", encoding="utf-8")
		write_stamp(cfg, doc)
		print(f"Pulled live {cfg['name']} ({doc['modified']}) into {cfg['dir']}. Review and commit.")
		return 0

	if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "--", str(cfg["dir"])]).returncode != 0:
		sys.exit("The page folder has uncommitted changes. Commit first, so the stamp names the deployed commit.")

	if args.create:
		if doc:
			sys.exit(f"{cfg['name']} already exists live. Use a normal deploy.")
		new = {"doctype": "Web Page", "name": cfg["name"], "title": cfg["title"], "route": cfg["route"], "published": 1,
			"content_type": "HTML", **repo}
		created = call("frappe.client.insert", {"doc": new})
		got = call("frappe.client.get", {"doctype": "Web Page", "name": created["name"]}, get=True)
		if created["name"] != cfg["name"]:
			print(f"NOTE: Frappe named the page {created['name']}; set PAGES['{args.page}']['name'] to that.")
		write_stamp(cfg, got)
		print(f"Created {created['name']} at /{cfg['route']} ({got['modified']}). Commit deploy-stamp.json.")
		return 0

	if not doc:
		sys.exit(f"{cfg['name']} does not exist live. Use --create for the first deploy.")
	if not stamp:
		sys.exit("No deploy-stamp.json: run --pull (adopt live) or --check first.")
	if drifted(stamp, doc):
		print("REFUSED: the live page changed since the last deploy (someone edited it outside this script).")
		for f in FIELDS.values():
			show_diff(doc.get(f), repo[f], f)
		sys.exit("Review the change, then --pull to adopt it, or ask Tanuj.")
	upd = dict(doc)
	upd.update(repo)
	# frappe.client.save checks `modified` (check_if_latest), so a write that lands between our read and this save is refused too.
	call("frappe.client.save", {"doc": upd})
	got = live_doc(cfg)
	if any((got.get(f) or "") != repo[f] for f in FIELDS.values()):
		sys.exit("Deployed, but the live page does not match the repo on re-read. Check it.")
	write_stamp(cfg, got)
	print(f"Deployed {cfg['name']} ({got['modified']}). Commit deploy-stamp.json.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
