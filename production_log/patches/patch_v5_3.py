"""
Patch v5_3: Re-sync the `cp_planning_board` Page doc from disk + clear
cache.

Observed on vimitconverters.frappe.cloud after the
`claude/2026-04-23-merge-planner-etr` deploy: navigating to
/app/cp_planning_board resolves (no "Page not found"), but the main
section renders blank — `on_page_load` never fires. The Page row exists
in `tabPage` but the stored `script` / `content` / roles are out of
sync with the files Phase 7 shipped, so Frappe serves an empty shell.

This patch reloads the Page doc from the JSON on disk (picking up the
latest roles + standard=Yes flag so the disk-side JS gets re-attached
on every subsequent load) and clears the desk cache so bootinfo stops
serving the stale page descriptor. Idempotent on re-run.
"""

import frappe


def execute():
	frappe.reload_doc("production_log", "page", "cp_planning_board")
	frappe.clear_cache()
	frappe.db.commit()
