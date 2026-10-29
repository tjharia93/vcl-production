#!/usr/bin/env python3
"""Deploy the Computer Paper job card prints (TRK-00342 Option A) to Frappe Cloud.

Two print formats on `Job Card Computer Paper`, both sourced from this repo:

    Computer Paper Job Card - Sales Copy   computer_paper_job_card_sales_copy.html
    Computer Paper Job Traveller v2        computer_paper_job_traveller_v2.html  (Production Copy)

    python3 scripts/deploy_cp_job_card_prints.py --check            # diff live vs repo, write nothing
    python3 scripts/deploy_cp_job_card_prints.py                    # deploy both
    python3 scripts/deploy_cp_job_card_prints.py --format sales     # one only (sales|production)
    python3 scripts/deploy_cp_job_card_prints.py --pull --format production   # live -> repo (rescue)

ORDER: deploy and migrate production_log FIRST. Both formats call the Jinja
methods cp_csra_rep / cp_production_copy_allowed / cp_print_user from
production_log.job_card_tracking.cp_print. Before the migrate those methods do
not exist, every print of the card would throw, and the shop floor could not
print its traveller. So this script refuses to write unless the role
"Release to Production" exists on the site. That role is created by the same
migrate, so its presence proves the migrate ran.

This script does not change the doctype's default print format. That stays
"Computer Paper Job Traveller v2" for the floor. For a user with no production
or release role, the job card form (job_card_computer_paper.js) offers the
Sales Copy first, and v2 renders an access-denied page for them anyway.
"""
import argparse
import difflib
import os
import pathlib
import sys
import urllib.parse

import requests
from dotenv import load_dotenv

DOCTYPE = "Job Card Computer Paper"
JC_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "production_log/job_card_tracking/doctype/job_card_computer_paper"
)
FORMATS = {
    "sales": ("Computer Paper Job Card - Sales Copy", JC_DIR / "computer_paper_job_card_sales_copy.html"),
    "production": ("Computer Paper Job Traveller v2", JC_DIR / "computer_paper_job_traveller_v2.html"),
}
GATE_ROLE = "Release to Production"
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
    return s, url


def endpoint(base, name):
    return f"{base}/api/resource/Print Format/{urllib.parse.quote(name)}"


def live_html(s, base, name):
    r = s.get(endpoint(base, name), timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()["data"].get("html") or ""


def migrated(s, base):
    r = s.get(f"{base}/api/resource/Role/{urllib.parse.quote(GATE_ROLE)}", timeout=60)
    return r.status_code == 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="diff only, do not write")
    ap.add_argument("--pull", action="store_true", help="overwrite repo from live")
    ap.add_argument("--format", choices=["sales", "production", "both"], default="both")
    args = ap.parse_args()

    s, base = session()
    kinds = ["sales", "production"] if args.format == "both" else [args.format]

    if not (args.check or args.pull) and not migrated(s, base):
        sys.exit(
            f"REFUSED: role '{GATE_ROLE}' is not on the site, so production_log has not been "
            "migrated with cp_print.py. Deploy + migrate the app first; deploying these "
            "formats now would make every Computer Paper job card print throw."
        )

    for kind in kinds:
        name, path = FORMATS[kind]
        live = live_html(s, base, name)

        if args.pull:
            if live is None:
                print(f"{name}: not on the site, nothing to pull")
                continue
            path.write_text(live)
            print(f"pulled {len(live)} chars -> {path}")
            continue

        repo = path.read_text()
        if live == repo:
            print(f"{name}: live already matches repo")
            continue
        if live is None:
            print(f"{name}: NOT on the site; would create it ({len(repo)} chars)")
        else:
            diff = "\n".join(difflib.unified_diff(live.splitlines(), repo.splitlines(), "live", "repo", lineterm="", n=1))
            print(diff if args.check else f"{name}: {diff.count(chr(10)) + 1} diff lines")
        if args.check:
            continue

        if live is None:
            r = s.post(
                f"{base}/api/resource/Print Format",
                json={
                    "name": name,
                    "doc_type": DOCTYPE,
                    "module": "Job Card Tracking",
                    "standard": "No",
                    "custom_format": 1,
                    "print_format_type": "Jinja",
                    "html": repo,
                    "disabled": 0,
                },
                timeout=60,
            )
        else:
            r = s.put(endpoint(base, name), json={"html": repo}, timeout=60)
        r.raise_for_status()
        if live_html(s, base, name) != repo:
            sys.exit(f"FAILED: live html of '{name}' does not match repo after write")
        print(f"deployed {len(repo)} chars to '{name}' — verified")


if __name__ == "__main__":
    main()
