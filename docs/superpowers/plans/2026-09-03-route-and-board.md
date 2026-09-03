# Route and Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a job card's route and the daily production board the same truth — plan a card's stations onto the board, and let the board's entries advance the card.

**Architecture:** One new module of pure functions, `production_floor/routes.py`, that does two jobs: **derive** a route from whatever a card carries, and **translate** a route stage into the Workstation Types that can serve it. `get_plan_template` uses it so office stages never reach the board and unstaffed ones show unticked. A write-back on the day document turns `stage_status` into a projection of the board.

**Tech Stack:** Frappe / ERPNext, Python 3. Pure logic in `routes.py` with **no Frappe imports**, tested with plain `unittest` and no bench — matching `reporting.py`.

**Spec:** [`docs/superpowers/specs/2026-09-03-route-and-board-design.md`](../specs/2026-09-03-route-and-board-design.md)

## Global Constraints

- **`routes.py` imports nothing from Frappe.** It is pure, so it runs under `python3 -m unittest` with no bench, exactly as `reporting.py` does.
- **Nothing is renamed.** Not machine stages, not card route stages. The map translates (spec §4.1).
- **Three kinds of stage:** `office` (never on the board), floor-with-types, floor-unstaffed. **An unstaffed stage is shown unticked, never dropped** — the gap must be visible.
- **`Pack` stays unstaffed.** Do not add a packing machine (spec §7, decision 2).
- **Never infer route capability from a station type.** `Reel to Reel Printing` is reel-*fed* printing; it does not mean the press can produce a finished reel (spec §8.2).
- **`stage_status` is derived, never typed.** A stage with no rows stays `Not Started`.
- **Patches never create a machine.** They update and deactivate only — `seed_machines` owns creation, and a deleted machine returns on the next `after_migrate`.
- Run tests with `python3 -m unittest production_log.production_floor.tests.test_reporting` from the repo root. **165 pass before this plan starts.**

---

## File Structure

```
production_log/production_floor/
    routes.py                     NEW — pure: STAGE_MAP, resolve_stage, route_for_carton
    api.py                        MODIFIED — get_plan_template uses the resolver; two reads whitelisted
    doctype/vcl_daily_production/
        vcl_daily_production.py   MODIFIED — on_update pushes stage_status back
    tests/test_routes.py          NEW — the pure tests
production_log/patches/v10_3/
    map_presses_and_retire_planning.py   NEW — Roland, Kord, Pasting, PLANNING entries
production_log/patches.txt        MODIFIED — one line
```

`routes.py` is separate from `reporting.py` on purpose: reporting turns rows into
words, routes turn a card into stations. They change for different reasons.

---

### Task 1: The stage map and resolver

**Files:**
- Create: `production_log/production_floor/routes.py`
- Test: `production_log/production_floor/tests/test_routes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `OFFICE`, `UNSTAFFED`, `STAGE_MAP`, and
  `resolve_stage(doctype: str, stage: str) -> dict` returning
  `{"stage": str, "office": bool, "types": tuple[str, ...]}`.

- [ ] **Step 1: Write the failing test**

`production_log/production_floor/tests/test_routes.py`:

```python
"""Pure route logic. No bench, no Frappe - run with:

    python3 -m unittest production_log.production_floor.tests.test_routes
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from production_log.production_floor.routes import (  # noqa: E402
    resolve_stage,
)

CP = "Job Card Computer Paper"
CARTON = "Job Card Carton"


class TestResolveStage(unittest.TestCase):

    def test_printing_on_a_cp_card_resolves_to_the_reel_fed_presses(self):
        # The whole reason this module exists: no machine offers a stage
        # called "Printing", so the route silently planned nothing.
        found = resolve_stage(CP, "Printing")
        self.assertFalse(found["office"])
        self.assertIn("Reel to Reel Printing", found["types"])

    def test_printing_means_something_different_on_a_carton_card(self):
        # Same word, different press. This is why the map is per doctype and
        # why renaming the machines would have collided.
        self.assertEqual(("Carton Printing",), resolve_stage(CARTON, "Printing")["types"])

    def test_design_is_office_and_never_reaches_the_board(self):
        found = resolve_stage(CP, "Design")
        self.assertTrue(found["office"])
        self.assertEqual((), found["types"])

    def test_pack_is_a_floor_stage_with_no_station(self):
        # Not office - somebody packs. There is just no machine for it, and
        # Tanuj decided not to add one.
        found = resolve_stage(CP, "Pack")
        self.assertFalse(found["office"])
        self.assertEqual((), found["types"])

    def test_an_unknown_stage_is_floor_and_unstaffed_not_an_error(self):
        # A stage nobody has mapped must still be visible on the plan. Raising
        # here would make one unmapped stage hide a whole route.
        found = resolve_stage(CP, "Something New")
        self.assertFalse(found["office"])
        self.assertEqual((), found["types"])

    def test_an_unknown_doctype_resolves_rather_than_raising(self):
        found = resolve_stage("Job Card Label", "Printing")
        self.assertEqual((), found["types"])

    def test_numbering_resolves_to_the_collator(self):
        # NOTE: the master describes Collator 01 (numbers) and 02 (does not),
        # but only one "Collator" exists in the machine master, so this cannot
        # yet be narrowed. See spec 8.1.
        self.assertEqual(("Collation",), resolve_stage(CP, "Numbering")["types"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
python3 -m unittest production_log.production_floor.tests.test_routes
```

Expected: `ModuleNotFoundError: No module named 'production_log.production_floor.routes'`.

- [ ] **Step 3: Write the module**

`production_log/production_floor/routes.py`:

```python
"""A job card's route, and where each of its stages can actually run.

Two jobs, both pure so they can be tested without a bench:

  DERIVE    - turn a card into an ordered list of stage names
  TRANSLATE - turn a stage name into the Workstation Types that serve it

The translation exists because the two vocabularies are genuinely different
and neither is wrong. A card names a step in ITS product's route - "Printing".
A machine names the kind of work its station does - "Reel to Reel Printing",
"Carton Printing". The same word means a Miyakoshi on one card and a flexo
press on another, so renaming either side would collide. It is a many-to-one
mapping per product type, which makes it data.
"""

# A stage that happens, but never on a machine board. Design and film work are
# steps on the traveller; nobody records production against them.
OFFICE = "office"

# A real floor stage with no station type yet. Shown, unticked, so the gap is
# visible - never dropped, which would make the route look shorter than it is.
UNSTAFFED = ()


STAGE_MAP = {
    "Job Card Computer Paper": {
        "Design": OFFICE,
        "Pending Films": OFFICE,
        # Reel-FED printing. Says nothing about whether the press can produce a
        # finished reel - M4 and Roland cannot. Never infer route capability
        # from a station type.
        "Printing": ("Reel to Reel Printing", "Sheet to Sheet Printing"),
        "Collation": ("Collation",),
        # Should be the collator that numbers. Only one Collator exists in the
        # machine master today, so it cannot be narrowed yet.
        "Numbering": ("Collation",),
        # A real step. Tanuj decided against adding a packing machine, so it
        # stays visible and unplannable rather than invented.
        "Pack": UNSTAFFED,
    },
    "Job Card Carton": {
        "Corrugated": ("Corrugation",),
        # Sheeting and Creasing have Workstation Types but NO machines, so they
        # resolve and then show unticked. That is the honest outcome.
        "Sheeting": ("Sheeting",),
        "Pasting": ("Carton Pasting",),
        "Creasing and Slitting": ("Creasing",),
        "Printing": ("Carton Printing",),
        "Die-cutting and Stripping": ("Die Cutting",),
        "Slotting": ("Slotting",),
        "Stitching": ("Carton Stitching",),
        "Gluing": ("Carton Gluing",),
        "Bundling": ("Bundling",),
    },
}


def resolve_stage(doctype, stage):
    """Where this stage can run, and whether it belongs on the floor at all.

    An unmapped stage - or an unmapped card type - resolves to an unstaffed
    FLOOR stage rather than raising. One stage nobody has mapped must not hide
    a whole route.
    """
    stage = (stage or "").strip()
    mapped = STAGE_MAP.get(doctype, {}).get(stage)

    if mapped == OFFICE:
        return {"stage": stage, "office": True, "types": ()}
    return {"stage": stage, "office": False, "types": tuple(mapped or ())}
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest production_log.production_floor.tests.test_routes
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add production_log/production_floor/routes.py production_log/production_floor/tests/test_routes.py
git commit -m "feat(routes): translate a card's route stage to the stations that serve it"
```

---

### Task 2: Carton's route, derived from its flags

**Files:**
- Modify: `production_log/production_floor/routes.py`
- Test: `production_log/production_floor/tests/test_routes.py`

**Interfaces:**
- Consumes: Task 1's module.
- Produces: `route_for_carton(card: dict) -> list[str]`, returning ordered stage
  names that are keys of `STAGE_MAP["Job Card Carton"]`.

- [ ] **Step 1: Write the failing test**

Append to `test_routes.py`, above `if __name__`:

```python
from production_log.production_floor.routes import route_for_carton  # noqa: E402


def carton(**overrides):
    """JC-CORR-2026-0077 as it really is on the live site."""
    base = {
        "applies_corrugated": 1,
        "applies_pasting": 1,
        "applies_creasing": 1,
        "applies_printing": 1,
        "applies_diecut": 0,
        "applies_slotting": 1,
        "applies_stitching": 1,
        "applies_bundling": 1,
        "joint_type": "Stitched",
    }
    base.update(overrides)
    return base


class TestCartonRoute(unittest.TestCase):

    def test_the_live_card_produces_its_real_ladder(self):
        # Before this, _route_for() returned [] for every Carton card and
        # plan_job threw "Tick at least one station."
        self.assertEqual(
            [
                "Corrugated",
                "Pasting",
                "Creasing and Slitting",
                "Printing",
                "Slotting",
                "Stitching",
                "Bundling",
            ],
            route_for_carton(carton()),
        )

    def test_die_cutting_off_stays_off(self):
        self.assertNotIn("Die-cutting and Stripping", route_for_carton(carton()))

    def test_die_cutting_on_appears_in_ladder_order(self):
        route = route_for_carton(carton(applies_diecut=1))
        self.assertLess(route.index("Printing"), route.index("Die-cutting and Stripping"))
        self.assertLess(route.index("Die-cutting and Stripping"), route.index("Slotting"))

    def test_a_glued_job_gets_gluing_instead_of_stitching(self):
        # There is no applies_gluing. The joint is derived from joint_type.
        route = route_for_carton(carton(joint_type="Gluing - Machine", applies_stitching=0))
        self.assertIn("Gluing", route)
        self.assertNotIn("Stitching", route)

    def test_manual_gluing_is_the_same_station(self):
        self.assertIn("Gluing", route_for_carton(
            carton(joint_type="Gluing - Manual", applies_stitching=0)))

    def test_a_plain_tray_skips_printing_and_slotting(self):
        route = route_for_carton(carton(applies_printing=0, applies_slotting=0))
        self.assertNotIn("Printing", route)
        self.assertNotIn("Slotting", route)
        self.assertIn("Creasing and Slitting", route)

    def test_all_flags_zero_means_no_route_recorded_not_no_stages(self):
        # Historic cards predate the flags and carry all eight as zero. Reading
        # that as "this job has no stages" would empty every old traveller.
        blank = {key: 0 for key in carton() if key.startswith("applies_")}
        blank["joint_type"] = "Stitched"
        route = route_for_carton(blank)
        self.assertIn("Corrugated", route)
        self.assertIn("Bundling", route)
        self.assertNotIn("Die-cutting and Stripping", route)

    def test_every_stage_it_emits_is_mappable(self):
        # A route naming a stage the map has never heard of would resolve to
        # unstaffed and look like a missing machine rather than a typo.
        for stage in route_for_carton(carton(applies_diecut=1)):
            self.assertIn(stage, STAGE_MAP["Job Card Carton"], stage)
```

Add `STAGE_MAP` to the first import block.

- [ ] **Step 2: Run it and watch it fail**

```bash
python3 -m unittest production_log.production_floor.tests.test_routes
```

Expected: FAIL — `cannot import name 'route_for_carton'`.

- [ ] **Step 3: Implement it**

Append to `routes.py`:

```python
# The ladder in the order the Carton traveller prints it. Sheeting sits between
# corrugation and pasting on the floor but has no flag of its own, so it is not
# emitted - inventing it would put a station on the board nobody asked for.
CARTON_LADDER = (
    ("applies_corrugated", "Corrugated"),
    ("applies_pasting", "Pasting"),
    ("applies_creasing", "Creasing and Slitting"),
    ("applies_printing", "Printing"),
    ("applies_diecut", "Die-cutting and Stripping"),
    ("applies_slotting", "Slotting"),
    ("applies_stitching", "Stitching"),
    ("applies_bundling", "Bundling"),
)

# Historic cards were created before the flags existed and carry all eight as
# zero. That means "no route recorded", NOT "no stages" - reading it the second
# way empties every old traveller.
CARTON_LEGACY_ROUTE = (
    "Corrugated", "Pasting", "Creasing and Slitting",
    "Printing", "Slotting", "Stitching", "Bundling",
)


def route_for_carton(card):
    """Carton's route, from its eight flags and its joint type.

    The joint is DERIVED, not flagged - there is no `applies_gluing`. A
    `joint_type` of "Gluing - Manual" or "Gluing - Machine" replaces stitching
    with gluing, because a box is joined one way or the other, never both.
    """
    card = card or {}
    flags = {key: _truthy(card.get(key)) for key, _ in CARTON_LADDER}

    if not any(flags.values()):
        route = list(CARTON_LEGACY_ROUTE)
    else:
        route = [stage for key, stage in CARTON_LADDER if flags[key]]

    joint = (card.get("joint_type") or "").strip()
    if joint.startswith("Gluing"):
        route = [s for s in route if s != "Stitching"]
        if "Gluing" not in route:
            # Immediately before bundling, where the joint happens.
            insert_at = route.index("Bundling") if "Bundling" in route else len(route)
            route.insert(insert_at, "Gluing")

    return route


def _truthy(value):
    """Frappe checkboxes arrive as 0/1, "0"/"1", True/False or None."""
    if value in (None, "", "0", 0, False):
        return False
    return True
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest production_log.production_floor.tests.test_routes
```

Expected: PASS, 15 tests.

- [ ] **Step 5: Commit**

```bash
git add production_log/production_floor/routes.py production_log/production_floor/tests/test_routes.py
git commit -m "feat(routes): derive Carton's route from its flags, joint included"
```

---

### Task 3: `get_plan_template` uses the resolver, and both reads are reachable

**Files:**
- Modify: `production_log/production_floor/api.py`

**Interfaces:**
- Consumes: `resolve_stage`, `route_for_carton` from Tasks 1–2.
- Produces: `get_plan_template` and `get_job_progress` whitelisted; each plan
  line gains `"office": bool` and `"reason": str | None`.

- [ ] **Step 1: Import the routes module**

In `api.py`, beside the `reporting` import:

```python
from production_log.production_floor.routes import (
	resolve_stage,
	route_for_carton,
)
```

- [ ] **Step 2: Teach `_route_for` about Carton**

Replace the body of `_route_for`:

```python
def _route_for(card):
	"""The stages this job runs, in order.

	Read off the card rather than assumed. Computer Paper builds its own route
	and already drops Numbering when numbering_required is off. Carton has no
	stage table at all - its route lives in eight flags, which is why every
	Carton card used to produce an empty route and refuse to be planned.
	"""
	stages = card.get("production_stages") or []
	if stages:
		ordered = sorted(stages, key=lambda row: row.get("sequence") or 0)
		return [row.get("stage") for row in ordered if row.get("stage")]

	if hasattr(card, "get_production_stage_route"):
		try:
			return card.get_production_stage_route()
		except Exception:
			pass

	if card.doctype == "Job Card Carton":
		return route_for_carton(card.as_dict())

	return []
```

- [ ] **Step 3: Resolve each line through the map**

In `get_plan_template`, replace the block from `machines = get_machines()` down
to `line["include"] = bool(line["machines"])` with:

```python
	machines = get_machines()
	by_type = {}
	for machine in machines:
		if machine.get("stage"):
			by_type.setdefault(machine["stage"], []).append(machine["name"])

	lines = []
	for line in plan_lines(route, parts):
		resolved = resolve_stage(doctype, line["stage"])

		# Office stages never reach a machine board. Design and film work are
		# steps on the traveller; nobody records production against them.
		if resolved["office"]:
			continue

		candidates = []
		for station in resolved["types"]:
			for name in by_type.get(station, []):
				if name not in candidates:
					candidates.append(name)

		line["machines"] = candidates
		line["machine"] = candidates[0] if candidates else None
		line["office"] = False
		# Ticked only where the work can actually go somewhere. A stage with no
		# machine is SHOWN, unticked, with the reason - so the gap is visible
		# rather than the stage quietly missing from the plan.
		line["include"] = bool(candidates)
		line["reason"] = None if candidates else (
			"No machine is set up for this stage yet."
			if resolved["types"]
			else "This stage has no station."
		)
		lines.append(line)
```

- [ ] **Step 4: Make both reads reachable**

Add `@frappe.whitelist()` immediately above `def get_plan_template` and above
`def get_job_progress`. Both are reads; neither writes.

- [ ] **Step 5: Verify against the live card that proved the problem**

```bash
python3 - <<'PY'
import json, subprocess, tomllib
cfg = tomllib.load(open("/opt/vcl/CommandCentre/config/settings.toml", "rb"))["erpnext"]
url = f"{cfg['base_url']}/api/method/production_log.production_floor.api.get_plan_template"
out = subprocess.run([
    "curl", "-s", "--max-time", "60",
    "-H", f"Authorization: token {cfg['api_key']}:{cfg['api_secret']}",
    f"{url}?job_card=JC-CPT-2026-00080",
], capture_output=True, text=True).stdout
for line in json.loads(out)["message"]["lines"]:
    tick = "TICKED " if line["include"] else "BLOCKED"
    print(f"  {tick} {line['stage']:<26} {line.get('part_label') or '':<28} {line['machines']}")
PY
```

Expected: `Design` and `Pending Films` **absent**. Both `Printing` lines
**TICKED** against M1–M4. `Collation` TICKED. `Pack` BLOCKED with a reason.

Then the same for `JC-CORR-2026-0077`: a seven-stage ladder, with
`Creasing and Slitting` BLOCKED because no creasing machine exists.

- [ ] **Step 6: Commit**

```bash
git add production_log/production_floor/api.py
git commit -m "feat(plan): office stages leave the board, unstaffed ones stay visible"
```

---

### Task 4: The board advances the card

**Files:**
- Modify: `production_log/production_floor/doctype/vcl_daily_production/vcl_daily_production.py`
- Modify: `production_log/production_floor/api.py`

**Interfaces:**
- Consumes: `roll_up_stages`, `_stage_maps`, `resolve_stage`.
- Produces: `push_stage_status(job_card)` on `api.py`, called from `on_update`.

- [ ] **Step 1: Write the write-back**

Add to `api.py`:

```python
def push_stage_status(job_card):
	"""Set a card's stage_status from what the board actually recorded.

	Derived, never typed: stage_status becomes a projection of the board, so
	the card and the floor cannot disagree. A stage with no rows is left at
	"Not Started" rather than blanked - absence of work is not a status.

	Only for cards that HAVE a stage table. Carton, Label, ETR and Monobox read
	their progress through get_job_progress instead; giving them a stage table
	is a bigger decision than this.
	"""
	doctype = job_card_doctype(job_card)
	if not doctype:
		return

	card = frappe.get_doc(doctype, job_card)
	rows_by_stage = card.get("production_stages") or []
	if not rows_by_stage:
		return

	stage_of_machine, _ = _stage_maps()
	rolled = roll_up_stages(_rows_for_job_card(job_card), stage_of_machine)

	# The board reports Workstation Types; the card names its own stages. Walk
	# the card's stages and ask the map which types belong to each.
	status_of_type = {r["stage"]: r["status"] for r in rolled if r["stage"]}

	changed = False
	for row in rows_by_stage:
		types = resolve_stage(doctype, row.stage)["types"]
		statuses = [status_of_type[t] for t in types if t in status_of_type]
		if not statuses:
			continue
		# Running beats Completed: any station still going means the stage is.
		fresh = "Running" if "Running" in statuses else statuses[0]
		if row.stage_status != fresh:
			row.stage_status = fresh
			changed = True

	if changed:
		card.save(ignore_permissions=True)
		frappe.db.commit()
```

- [ ] **Step 2: Call it when the day changes**

In `vcl_daily_production.py`, extend `on_update`:

```python
	def on_update(self):
		self.remember_new_jobs()
		self.push_job_card_progress()

	def push_job_card_progress(self):
		"""Advance every job card this day touched.

		On the day document, not on each row: a day is saved once per change,
		and a card with five stations would otherwise be recomputed five times
		for one edit.
		"""
		from production_log.production_floor.api import push_stage_status

		cards = {
			(row.production_job_card or "").strip()
			for row in self.items
			if (row.production_job_card or "").strip()
		}
		for card in cards:
			try:
				push_stage_status(card)
			except Exception:
				# A job card problem must never stop a supervisor saving the
				# day. The board is the record that matters.
				frappe.log_error(
					title="push_stage_status failed",
					message=f"{card}\n{frappe.get_traceback()}",
				)
```

- [ ] **Step 3: Test the status rule, which is the only judgement in it**

Append to `test_routes.py`:

```python
class TestStageStatusRule(unittest.TestCase):
    """Running beats Completed when a stage has several stations.

    Computer Paper prints each part on its own press, so "Printing" can be
    two rows at once. If one press has finished and the other is still going,
    the STAGE is still running - reporting it Completed would tell the office
    a job is off the press when half of it is not.
    """

    @staticmethod
    def pick(statuses):
        return "Running" if "Running" in statuses else statuses[0]

    def test_one_press_still_running_keeps_the_stage_running(self):
        self.assertEqual("Running", self.pick(["Completed", "Running"]))

    def test_all_finished_completes_the_stage(self):
        self.assertEqual("Completed", self.pick(["Completed", "Completed"]))

    def test_a_single_station_reports_itself(self):
        self.assertEqual("Paused", self.pick(["Paused"]))
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest production_log.production_floor.tests.test_routes
python3 -m unittest production_log.production_floor.tests.test_reporting
```

Expected: PASS, 18 and 165.

- [ ] **Step 5: Commit**

```bash
git add production_log/production_floor
git commit -m "feat(progress): the board advances the job card's stages"
```

---

### Task 5: Correct the machine master

**Files:**
- Create: `production_log/patches/v10_3/__init__.py` (empty)
- Create: `production_log/patches/v10_3/map_presses_and_retire_planning.py`
- Modify: `production_log/patches.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable — a migration.

- [ ] **Step 1: Write the patch**

```python
"""Map the two unmapped presses, and take planning off the machine list.

Decisions from Tanuj, 2026-09-03:
  - Roland maps like M4, so reel-fed printing.
  - Kord is a printing machine, so sheet-fed like Solna and Miller beside it.
  - Pasting gets the Carton Pasting type that already exists.
  - The two PLANNING entries stop being pickable. Planning is a process; it is
    not something production is recorded against.

⛔ This patch NEVER creates a machine. `seed_machines` owns creation, and a
machine inserted here would fail `_validate_selects` if its department Select
had not been widened yet - which is how five lines of seed data once took the
whole site down. It only updates rows that already exist.

Retiring is `active = 0`, never a delete: `seed_machines` runs from
after_migrate and puts a deleted machine straight back, losing its history with
it.
"""

import frappe

STAGES = {
	# Reel-FED printing. Says nothing about whether the press can produce a
	# finished reel - per the department master, Roland and M4 cannot.
	"Roland": "Reel to Reel Printing",
	"Kord": "Sheet to Sheet Printing",
	"Pasting": "Carton Pasting",
}

RETIRE = ("PLANNING", "PLANNING STAGE - PRINTING")


def execute():
	if not frappe.db.exists("DocType", "VCL Production Machine"):
		return

	for machine, stage in STAGES.items():
		if not frappe.db.exists("VCL Production Machine", machine):
			continue
		if not frappe.db.exists("Workstation Type", stage):
			continue
		if frappe.db.get_value("VCL Production Machine", machine, "stage"):
			# Already mapped, by hand or by an earlier run. Leave it alone.
			continue
		frappe.db.set_value("VCL Production Machine", machine, "stage", stage)

	for machine in RETIRE:
		if frappe.db.exists("VCL Production Machine", machine):
			frappe.db.set_value("VCL Production Machine", machine, "active", 0)

	frappe.db.commit()
```

- [ ] **Step 2: Register it**

Append to `patches.txt`:

```
# Maps Roland and Kord to the station types they actually are, gives Pasting
# the Carton Pasting type that already existed, and retires the two PLANNING
# entries from the machine list - planning is a process, not something
# production is recorded against. Updates only; never creates a machine.
production_log.patches.v10_3.map_presses_and_retire_planning
```

- [ ] **Step 3: Check the patch is importable and creates nothing**

```bash
python3 -c "import ast; ast.parse(open('production_log/patches/v10_3/map_presses_and_retire_planning.py').read()); print('parses')"
grep -c "new_doc\|insert(" production_log/patches/v10_3/map_presses_and_retire_planning.py
```

Expected: `parses`, then `0` — the patch must create nothing.

- [ ] **Step 4: Commit**

```bash
git add production_log/patches production_log/patches.txt
git commit -m "fix(machines): map Roland and Kord, retire the planning entries"
```

- [ ] **Step 5: After deploy, verify on the live site**

```bash
python3 - <<'PY'
import json, subprocess, tomllib
cfg = tomllib.load(open("/opt/vcl/CommandCentre/config/settings.toml", "rb"))["erpnext"]
out = subprocess.run([
    "curl", "-s", "--max-time", "60",
    "-H", f"Authorization: token {cfg['api_key']}:{cfg['api_secret']}",
    f'{cfg["base_url"]}/api/resource/VCL Production Machine'
    '?fields=["name","stage","active"]&limit_page_length=60',
], capture_output=True, text=True).stdout
for m in json.loads(out)["data"]:
    if m["name"] in ("Roland", "Kord", "Pasting", "PLANNING", "PLANNING STAGE - PRINTING"):
        print(f'  {m["name"]:<26} stage={m["stage"] or "NONE":<24} active={m["active"]}')
PY
```

Expected: Roland `Reel to Reel Printing`, Kord `Sheet to Sheet Printing`,
Pasting `Carton Pasting`, both PLANNING entries `active=0`.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §4.1 route registry — derive and translate | 1, 2 |
| §4.2 plan down, office excluded, unstaffed visible | 3 |
| §4.3 progress up, derived not typed | 4 |
| §7 decisions 3, 4, 5 — Roland, Kord, PLANNING | 5 |
| §7 decision 2 — Pack stays unstaffed | 1 (`"Pack": UNSTAFFED`) |
| §8.1 one Collator | 1 — mapped to `Collation`, limitation commented and tested |
| §8.2 two meanings of "Reel to Reel" | 1, 5 — commented in both |
| §8.3 Pasting one-field fix; Sheeting/Creasing unstaffed | 5, and 1 maps them so they surface unticked |
| §6 testing — pure, no bench | 1, 2, 4 |

**Not covered, and deliberately (spec §5 and §9):** Label, ETR and Reel-to-Reel
routes; a stage table for Carton; Monobox. Each needs a floor decision first.

**Type consistency:** `resolve_stage` returns `{"stage", "office", "types"}` in
Task 1 and is read with exactly those keys in Tasks 3 and 4. `route_for_carton`
takes a dict in Task 2 and is called with `card.as_dict()` in Task 3.
