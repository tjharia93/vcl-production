#!/usr/bin/env python3
"""Deploy the Computer Paper job card print (TRK-00342) to Frappe Cloud.

ONE print format, "Computer Paper Job Traveller v2", sourced from
computer_paper_job_traveller_v2.html. Page 1 is the Sales page for everyone.
Pages 2 onward are the Production pages, rendered only for release and
production roles (cp_print.cp_production_copy_allowed).

The earlier separate "Computer Paper Job Card - Sales Copy" is redundant. This
script DISABLES it on live (disabled=1, never deleted) and leaves it in place.

    python3 scripts/deploy_cp_job_card_prints.py --check            # diff live vs repo, write nothing
    python3 scripts/deploy_cp_job_card_prints.py                    # deploy v2, disable Sales Copy
    python3 scripts/deploy_cp_job_card_prints.py --pull             # live -> repo (rescue)

ORDER: deploy and migrate production_log FIRST. The format calls the Jinja
methods cp_csra_rep / cp_production_copy_allowed / cp_print_user / cp_print_side
from production_log.job_card_tracking.cp_print. Before the migrate those methods
do not exist and every print of the card would throw. The script refuses to
write until the role "Release to Production" exists, which proves the migrate ran.
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
FORMAT = ("Computer Paper Job Traveller v2", JC_DIR / "computer_paper_job_traveller_v2.html")
RETIRED_FORMAT = "Computer Paper Job Card - Sales Copy"
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


def retire(s, base):
    """Disable (never delete) the retired Sales Copy format if it is live and enabled."""
    r = s.get(endpoint(base, RETIRED_FORMAT), timeout=60)
    if r.status_code == 404:
        print(f"{RETIRED_FORMAT}: not on the site")
        return
    r.raise_for_status()
    if not r.json()["data"].get("disabled"):
        resp = s.put(endpoint(base, RETIRED_FORMAT), json={"disabled": 1}, timeout=60)
        resp.raise_for_status()
        print(f"{RETIRED_FORMAT}: disabled (kept, not deleted)")
    else:
        print(f"{RETIRED_FORMAT}: already disabled")


def migrated(s, base):
    r = s.get(f"{base}/api/resource/Role/{urllib.parse.quote(GATE_ROLE)}", timeout=60)
    return r.status_code == 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="diff only, do not write")
    ap.add_argument("--pull", action="store_true", help="overwrite repo from live")
    args = ap.parse_args()

    s, base = session()
    name, path = FORMAT

    if not (args.check or args.pull) and not migrated(s, base):
        sys.exit(
            f"REFUSED: role '{GATE_ROLE}' is not on the site, so production_log has not been "
            "migrated with cp_print.py. Deploy + migrate the app first."
        )

    live = live_html(s, base, name)

    if args.pull:
        if live is None:
            sys.exit(f"{name}: not on the site, nothing to pull")
        path.write_text(live)
        print(f"pulled {len(live)} chars -> {path}")
        return

    repo = path.read_text()
    if live == repo:
        print(f"{name}: live already matches repo")
    else:
        if live is None:
            print(f"{name}: NOT on the site; would create it ({len(repo)} chars)")
        else:
            diff = "\n".join(difflib.unified_diff(live.splitlines(), repo.splitlines(), "live", "repo", lineterm="", n=1))
            print(diff if args.check else f"{name}: {diff.count(chr(10)) + 1} diff lines")
        if not args.check:
            if live is None:
                r = s.post(
                    f"{base}/api/resource/Print Format",
                    json={"name": name, "doc_type": DOCTYPE, "module": "Job Card Tracking", "standard": "No",
                          "custom_format": 1, "print_format_type": "Jinja", "html": repo, "disabled": 0},
                    timeout=60,
                )
            else:
                r = s.put(endpoint(base, name), json={"html": repo}, timeout=60)
            r.raise_for_status()
            if live_html(s, base, name) != repo:
                sys.exit(f"FAILED: live html of '{name}' does not match repo after write")
            print(f"deployed {len(repo)} chars to '{name}' — verified")

    if args.check:
        r = s.get(endpoint(base, RETIRED_FORMAT), timeout=60)
        state = "not on the site" if r.status_code == 404 else ("disabled" if r.json()["data"].get("disabled") else "ENABLED")
        print(f"{RETIRED_FORMAT}: {state} (would be disabled on a deploy)")
    else:
        retire(s, base)


if __name__ == "__main__":
    main()
