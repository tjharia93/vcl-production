#!/usr/bin/env python3
"""Deploy the in-repo Computer Paper Job Traveller v2 HTML to Frappe Cloud.

The Print Format record is the live default for `Job Card Computer Paper`, so the
repo file is the source of truth and this script is the only way it should change.

    python3 scripts/deploy_cp_traveller_v2.py --check    # diff live vs repo
    python3 scripts/deploy_cp_traveller_v2.py            # PUT repo -> live
    python3 scripts/deploy_cp_traveller_v2.py --pull     # live -> repo (rescue)
"""
import argparse
import difflib
import os
import pathlib
import sys

import requests
from dotenv import load_dotenv

FORMAT = "Computer Paper Job Traveller v2"
HTML = (
    pathlib.Path(__file__).resolve().parents[1]
    / "production_log/job_card_tracking/doctype/job_card_computer_paper"
    / "computer_paper_job_traveller_v2.html"
)
ENV = pathlib.Path.home() / "projects/vcl-erpnext-mcp/.env"


def session():
    load_dotenv(ENV)
    try:
        url = os.environ["ERPNEXT_URL"].rstrip("/")
        key, secret = os.environ["ERPNEXT_API_KEY"], os.environ["ERPNEXT_API_SECRET"]
    except KeyError as exc:
        sys.exit(f"missing {exc} in {ENV}")
    s = requests.Session()
    s.headers["Authorization"] = f"token {key}:{secret}"
    return s, f"{url}/api/resource/Print Format/{FORMAT}"


def live_html(s, endpoint):
    r = s.get(endpoint, timeout=60)
    r.raise_for_status()
    return r.json()["data"].get("html") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="diff only, do not write")
    ap.add_argument("--pull", action="store_true", help="overwrite repo from live")
    args = ap.parse_args()

    s, endpoint = session()
    live = live_html(s, endpoint)

    if args.pull:
        HTML.write_text(live)
        print(f"pulled {len(live)} chars -> {HTML}")
        return

    repo = HTML.read_text()
    if live == repo:
        print("live already matches repo — nothing to do")
        return

    diff = difflib.unified_diff(
        live.splitlines(), repo.splitlines(), "live", "repo", lineterm="", n=1
    )
    body = "\n".join(diff)
    print(body if args.check else f"{body.count(chr(10)) + 1} diff lines")
    if args.check:
        return

    r = s.put(endpoint, json={"html": repo}, timeout=60)
    r.raise_for_status()
    if live_html(s, endpoint) != repo:
        sys.exit("FAILED: live html does not match repo after PUT")
    print(f"deployed {len(repo)} chars to '{FORMAT}' — verified")


if __name__ == "__main__":
    main()
