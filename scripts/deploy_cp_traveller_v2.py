#!/usr/bin/env python3
"""Superseded by deploy_cp_job_card_prints.py (TRK-00342).

The v2 traveller is now the Production Copy. It calls Jinja methods that ship
with production_log, so it must not be deployed before the app migrate.
deploy_cp_job_card_prints.py checks for that; this wrapper keeps the old
command working and routes it there.

    python3 scripts/deploy_cp_traveller_v2.py [--check | --pull]
"""
import pathlib
import runpy
import sys

sys.argv = [sys.argv[0], "--format", "production", *sys.argv[1:]]
runpy.run_path(str(pathlib.Path(__file__).with_name("deploy_cp_job_card_prints.py")), run_name="__main__")
