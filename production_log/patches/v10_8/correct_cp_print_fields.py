"""Correct Plain/N/A print fields on existing Computer Paper job cards (D5, TRK-00350).

38 of 86 live cards were raised Plain/N/A from a Printed specification, before
D4 fixed the path for new cards. This sets print_type, print_side and
printed_weight from the specification where the card is Plain and the spec is
Printed, and fills a blank print_side where a Printed card has none. It leaves a
Comment on each card it changes. Cancelled cards and cards with no spec are not
touched. The rules are in production_log.job_card_tracking.cp_print_correction.

Idempotent: the plan is recomputed from the live data each run, and a corrected
card no longer matches, so a re-run changes nothing.
"""

from production_log.job_card_tracking.cp_print_correction import apply, gather, plan_corrections


def execute():
	cards, specs = gather()
	changes, cancelled = plan_corrections(cards, specs)
	n = apply(changes)
	print(f"correct_cp_print_fields: {n} card(s) corrected; {len(cancelled)} cancelled card(s) left alone")
