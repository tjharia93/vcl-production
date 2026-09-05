"""The carry-forward must never leave two rows for one job on tomorrow's board.

Written 5 September 2026 after `VCL-PROD-2026-09-05` came up carrying
VPJ-2026-00015 (Sachi Stationery, ETR, 0.5 reels) twice — rows 1 and 12,
identical on machine, job card, job name and part label, differing only in that
one had been started. The guard required tomorrow's row to still be `Planned`,
so once an operator pressed Start, a further edit to today's carry figure
stopped matching and appended a second row.

It is not cosmetic. `stage_totals` sums `actual_quantity` per unit with no
de-duplication, so two rows for one job inflate the day's output, and
`roll_up_stages` carries that into the job card's completion against the order.

No bench required: the matching logic is exercised against a stand-in day
document, because that is where the defect lived.
"""
import sys
import types
import unittest

if "frappe" not in sys.modules:                       # pragma: no cover
    frappe = types.ModuleType("frappe")
    frappe.whitelist = lambda *a, **k: (lambda f: f)
    frappe.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a and a[0]))
    frappe._ = lambda s: s
    utils = types.ModuleType("frappe.utils")
    utils.flt = lambda v: float(v or 0)
    utils.cint = lambda v: int(v or 0)
    frappe.utils = utils
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils


class Row(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


class Day:
    """Stands in for a VCL Daily Production document."""

    def __init__(self, items, status="Open"):
        self.items = items
        self.status = status
        self.saves = 0

    def append(self, _field, values):
        # The doctype declares status default "Planned"; a stand-in that omits
        # it would make a freshly carried row unmatched on the next pass, which
        # is a bug in the test rather than in the code. Verified against
        # vcl_daily_production_item.json.
        self.items.append(Row(dict({"status": "Planned"}, **values)))

    def save(self):
        self.saves += 1


def carry(tomorrow, template):
    """The matching logic from `_carry_forward`, as it now stands.

    Kept in step with api.py by hand rather than imported, because importing it
    drags in the whole Frappe document layer for four lines of comparison.
    """
    for existing in tomorrow.items:
        same_job = (
            existing.machine == template["machine"]
            and (existing.production_job_card or "") == (template["production_job_card"] or "")
            and (existing.job_name or "") == (template["job_name"] or "")
            and (existing.part_label or "") == (template["part_label"] or "")
        )
        if same_job:
            if existing.status == "Planned":
                existing.planned_quantity = template["planned_quantity"]
                tomorrow.save()
            return {"created": 0}
    tomorrow.append("items", dict(template, remember_job=1))
    tomorrow.save()
    return {"created": 1}


SACHI = {
    "machine": "ETR", "production_job_card": None, "job_name": "Stationery",
    "part_label": None, "planned_quantity": 0.5,
}


class CarryForward(unittest.TestCase):

    def test_it_appends_when_the_job_is_not_there_yet(self):
        day = Day([])
        self.assertEqual(carry(day, SACHI)["created"], 1)
        self.assertEqual(len(day.items), 1)

    def test_a_second_carry_corrects_the_figure_and_adds_nothing(self):
        day = Day([])
        carry(day, SACHI)
        carry(day, dict(SACHI, planned_quantity=0.75))
        self.assertEqual(len(day.items), 1, "two rows for one job")
        self.assertEqual(day.items[0].planned_quantity, 0.75)

    def test_the_actual_defect_a_started_row_is_not_duplicated(self):
        """VCL-PROD-2026-09-05 rows 1 and 12. This is the regression."""
        started = Row(dict(SACHI, status="Running", start_time="2026-09-05 04:53:49"))
        day = Day([started])
        result = carry(day, dict(SACHI, planned_quantity=0.5))
        self.assertEqual(len(day.items), 1,
                         "a started row must not be duplicated by a later carry")
        self.assertEqual(result["created"], 0)

    def test_a_started_row_keeps_its_planned_figure(self):
        """The operator is working to a number. Do not move it under them."""
        started = Row(dict(SACHI, status="Running", planned_quantity=0.5))
        day = Day([started])
        carry(day, dict(SACHI, planned_quantity=99))
        self.assertEqual(day.items[0].planned_quantity, 0.5)
        self.assertEqual(day.saves, 0, "nothing changed, so nothing to save")

    def test_paused_and_carried_forward_are_also_matched(self):
        for status in ("Paused", "Carried Forward", "Completed"):
            with self.subTest(status=status):
                day = Day([Row(dict(SACHI, status=status))])
                carry(day, SACHI)
                self.assertEqual(len(day.items), 1, f"{status} row duplicated")

    def test_a_different_job_on_the_same_machine_still_appends(self):
        day = Day([Row(dict(SACHI, status="Running"))])
        carry(day, dict(SACHI, job_name="Something else"))
        self.assertEqual(len(day.items), 2)

    def test_a_different_part_of_the_same_job_still_appends(self):
        """Two parts of one Computer Paper job are two real machine runs."""
        day = Day([Row(dict(SACHI, status="Running", part_label="Part 1"))])
        carry(day, dict(SACHI, part_label="Part 2"))
        self.assertEqual(len(day.items), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
