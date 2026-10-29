#!/usr/bin/env python3
"""Superseded by deploy_cp_job_card_prints.py (TRK-00342). Kept so the old command still works.

    python3 scripts/deploy_cp_traveller_v2.py [--check | --pull]
"""
import pathlib
import runpy
import sys

runpy.run_path(str(pathlib.Path(__file__).with_name("deploy_cp_job_card_prints.py")), run_name="__main__")
