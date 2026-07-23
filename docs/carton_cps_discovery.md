# Carton CPS → Sales Order → Job Card — Discovery

**Date:** 2026-07-23
**Branch:** `agent/carton-orders` (vcl-production and vcl-compass worktrees, both clean at start)
**Scope:** discovery only. No application source, live data, branch, commit or GitHub state was changed.
**Baseline merge:** `26d5a38` (PR #22), which brought in the Computer-Paper guided flow (`42fa91b` add Sales Order job card action, `0b26cd9` CPS Desk controls, `334ea95` CPS control of Sales Orders and Job Cards).

---

## 0. Evidence status — read this first

Everything below marked **[CODE]** is verified against the source in the two worktrees and is
citable to file and line.

Everything marked **[LIVE — NOT OBTAINED]** could not be verified this turn. **Live ERPNext
access was denied in this session.** All three routes were attempted and refused by the
permission layer:

| Route attempted | Result |
|---|---|
| `mcp__vcl-erpnext__sql_query` | denied — permission not granted |
| `mcp__vcl-erpnext__list_docs` | denied — permission not granted |
| `frappe_client.py` via `venv/bin/python` (Bash) | denied — command requires approval |
| `Write` a helper script to `/tmp` | denied — write permission not granted |

No credentials were printed or handled. This is the single blocker on the discovery brief; the
specific counts and readings still outstanding are listed in §11 as a runnable checklist.

### Update — 2026-07-23, implementation turn

The production-side implementation has now landed (see
[`carton_cps_migration_report.md`](./carton_cps_migration_report.md) for the full change list and
the deploy sequence). Two things changed about the evidence position:

**One live figure has been obtained**, by an audit run outside this session and supplied to it:

| Question | Answer | Consequence |
|---|---|---|
| `Job Card Carton.quantity_ordered` — how many rows, how many parse as numbers? | **35 rows, all 35 numeric** | §8.3, ranked the highest-risk single schema change in the project, is **de-risked**. The `Data → Float` conversion has no unparseable rows to resolve. `patches/v8_1/normalise_carton_quantity_ordered` runs pre-model-sync anyway and will write nothing. |

**Everything else in §11 remains [LIVE — NOT OBTAINED].** Live ERPNext access was again not
exercised this turn: the implementation brief was explicit that live data was not to be touched.
The §11 checklist is unchanged and still runnable, and the counts it produces are still what a
cutover date must be set against — in particular §8.1 (Carton orders with no snapshot) and §8.2
(unlinked Carton specifications), neither of which the code can answer.

**Decisions §9 have been resolved as follows** by the implementation, and are recorded here so the
report and the code do not disagree:

| §9 | Decision taken | Where |
|---|---|---|
| 1. Plate on Carton | Plate stays Computer-Paper-only. `repeat` (Old/New) is the Carton analogue and is the Carton-specific dialog input. Plate validation is per-kind, driven by the dialog's kind registry. | `public/js/sales_order_cps.js` |
| 2. `quantity_ordered` type | Converted to `Float`, precision 3, guarded by a pre-model-sync audit patch that refuses to migrate rather than coerce. | `job_card_carton.json`, `patches/v8_1/` |
| 3. Permission table | Answered deliberately: System Manager full; Sales Manager full (no delete); Sales User read/write/create only; Manufacturing Manager read/write/amend; Manufacturing User read. | `job_card_carton.json` |
| 4. `customer_name` vs `customer` | Kept, and driven from configuration — `JC_CUSTOMER_FIELD` on the controller and `customer_field` on `cps_rules.jc_line_mismatches`. No rename over live data. | `order_derived.py`, `cps_rules.py` |
| 5. Carton dimensions as material | **Yes.** Dimensions, ply, flute, style, joint, ID/OD and all ten board layers are material and force an Item link on a materially edited record. Notes are not. | `cps_rules.CARTON_MATERIAL_SPEC_FIELDS` |
| 6. Historic Carton order amendment | Not forced. Legacy Carton cards keep the live-specification check; only order-derived cards are proved against the frozen line. Cutover can be "new orders only". | `job_card_carton.py` |
| 7. Board-plan geometry | Recompute from frozen inputs. No derived geometry is snapshotted, so a formula fix still reaches an open job. | `CARTON_SNAPSHOT_SCALARS` |
| 8. Cutover sequencing | Unchanged and still open — one `custom_cps_control_enabled` flag governs both product types. Carton readiness is a precondition for flipping it. | — |

---

## 1. Carton Item Groups and Item counts

**[LIVE — NOT OBTAINED].** The Item Group tree, the `custom_requires_cps` /
`custom_cps_product_type` settings on each Carton group, per-Item
`custom_cps_control_mode` overrides, and active Item counts all live in ERPNext only. None of it
is in the repo.

What the code fixes about the shape of that answer **[CODE]**:

- Control is a **nested-set walk upward**. `so_spec_control.item_group_requires_cps`
  (`so_spec_control.py:81-103`) reads `lft/rgt` of the Item's group and returns the *nearest
  ancestor* with `custom_requires_cps` ticked, `order_by="lft desc"`. A single Carton parent group
  therefore covers its whole subtree without per-group configuration.
- A controlled group **must** name a product type — enforced server-side, not by
  `mandatory_depends_on` (`so_spec_control.py:188-201`).
- The Item's own answer **beats the tree in both directions** (`cps_rules.item_requires_cps`,
  `cps_rules.py:121-138`): `Require CPS` controls an Item outside any controlled group;
  `Exempt from CPS` releases an Item inside one; blank/`Inherit from Item Group` defers.
  This is the mechanism for a Carton pilot on a handful of Items without flipping a whole group.
- `Item.custom_requires_cps` is **read-only and derived**, written by
  `derive_item_control_flag` on `Item.validate` and re-derived across a subtree by the background
  `rederive_items_for_group` on `Item Group.on_update` (`so_spec_control.py:106-263`).
  Editing a group re-applies each Item's explicit mode, so a group edit does not silently revoke
  exemptions.
- The expected product type resolves **Item override first, controlling group second**
  (`cps_rules.expected_product_type`, `cps_rules.py:154-178`). Without the Item half, `Require CPS`
  on an Item outside a controlled group yields *no* expected type and a Label spec would pass on a
  Carton Item.

Valid product types are defined once, in `cps_rules.CPS_PRODUCT_TYPES` (`cps_rules.py:91-97`):
`Computer Paper, Carton, Label, Exercise Books, ETR (Reel to Reel Printing)`. Item Group, Item and
CPS `product_type` all draw from this list.

---

## 2. Carton CPS records — status, docstatus, link, pricing readiness

**[LIVE — NOT OBTAINED]** for the counts. The docstring of `cps_migration_report.py` records the
Computer-Paper baseline as **53 of 56 live CP specifications unlinked** at the time it was written;
the equivalent Carton figure is unknown and is the single most important number to obtain.

The **exact conditions a Carton CPS must satisfy to be orderable** are fully specified in code
(`cps_rules.spec_block_reason`, `cps_rules.py:645-701`, mirrored throw-for-throw by
`so_spec_control._load_and_validate_spec`, `so_spec_control.py:344-390`), checked in this order:

1. `customer` equals the Sales Order customer.
2. `linked_item` equals the line's `item_code` **exactly** — `cps_rules.spec_serves_item`
   (`cps_rules.py:612-622`). *There is no fuzzy fallback and unlinked ≠ wildcard.*
3. `product_type` equals the Item's expected product type.
4. `docstatus == 1` (submitted).
5. `status == "Active"` (options: Active / Inactive / Discontinued).
6. An **Approved** `CPS Price` row effective on or before the order's `transaction_date`.

### `linked_item` is a Custom Field, not a DocField

`linked_item` is **absent** from `customer_product_specification.json` and is created by
`patches/v8_0/add_cps_control_custom_fields.py:110-120` (Link → Item, `search_index: 1`,
inserted after `customer`). Any query for it must survive its absence; `cps_desk.item_linked_specs`
and `cps_migration_report` both guard with `_has_field`.

It is required on **new or materially changed** specifications only
(`cps_rules.item_link_required`, `cps_rules.py:720-739`; enforced in
`customer_product_specification.py:38-44`). "Material" = any change to
`product_type, specification_name, customer, job_size, pay_slip_size, number_of_parts,
linked_item` (`MATERIAL_SPEC_FIELDS`, `cps_rules.py:61-69`).

> **Carton gap:** `MATERIAL_SPEC_FIELDS` contains `pay_slip_size` and `number_of_parts`, both
> Computer-Paper-only. **No Carton dimension** (`ctn_length_mm`, `ctn_width_mm`, `ctn_height_mm`,
> `ply`, `flute_type`, the five GSM/material layers) is treated as material. A live Carton spec's
> box size can therefore be changed today without the link being forced — and, worse, without any
> of the freezing consequences in §4.

### Pricing readiness, UOM and effective dates **[CODE]**

`CPS Price` child table (`cps_price.json`):

| field | type | notes |
|---|---|---|
| `valid_from` | Date | **required** |
| `rate` | Currency | **required**, precision **9** |
| `uom` | Link → UOM | **required** |
| `source` | Select | blank / Quotation / LPO / Manual / Historical |
| `source_ref` | Data | |
| `approval_status` | Select | Draft / Approved / Rejected, **read-only**, default Draft |
| `approved_by` / `approved_on` | Link User / Datetime | read-only |
| `approval_notes` | Small Text | |

- **Eligibility** = greatest `valid_from <= transaction_date` among `Approved` rows
  (`cps_rules.resolve_eligible_price`, `cps_rules.py:334-361`). Draft, Rejected and future-dated
  rows are invisible. `transaction_date` is used, **never `today()`**, so a backdated order and a
  re-submitted amendment reproduce the original rate.
- **No two non-Rejected rows may share a `valid_from`** (`find_duplicate_valid_from`,
  `cps_rules.py:364-385`; thrown by `cps_pricing.validate_no_duplicate_effective_dates`).
- **Editing `rate`, `uom` or `valid_from` on an Approved row resets it to Draft**
  (`PRICE_APPROVAL_RESET_FIELDS`, `cps_rules.py:31`; `cps_pricing.revoke_approval_on_edit`).
- **Approval requires the `Sales Master Manager` role**; self-approval is permitted and logged as a
  comment (`cps_pricing.approve_cps_price`, `cps_pricing.py:115-177`).
- **UOM must match the order line's UOM exactly** or submit throws
  (`so_spec_control._validate_price`, `so_spec_control.py:395-401`). This is a live migration risk
  for Carton: specs priced per `Nos` against lines ordered in `Box`/`Pcs` will block on submit.
- `current_rate` / `current_uom` on the spec are derived read-only mirrors of the row in effect
  **today** (`cps_pricing.set_current_rate`) — they are list-view convenience, not the order rate.
- Rate matching is **exact-match-only by default**: `tolerance_pct` and `floor_pct` both ship unset
  (DN-5). Any deviation in either direction needs an override reason **and** the
  `Sales Master Manager` role; a set floor cannot be overridden by anyone
  (`cps_rules.evaluate_price` / `is_below_floor`; `so_spec_control._validate_price`).

---

## 3. Job Card Carton — exact metadata as it stands

Source: `production_log/job_card_tracking/doctype/job_card_carton/job_card_carton.json` and
`.py` (103 lines), `.js` (~1090 lines).

- **Submittable**, `autoname: naming_series:`, single series
  **`JC-CORR-.YYYY.-.####.`** — note **four** digits and a trailing dot, where Computer Paper and
  Label use `JC-CPT-.YYYY.-.#####` / `JC-LBL-.YYYY.-.#####` (five digits, no trailing dot).
- Customer link field is **`customer_name`**, not `customer` (Computer Paper, Label and ETR all
  use `customer`). Compass already carries this asymmetry as data in two places —
  `jobcards.KINDS["carton"]["customer_field"] = "customer_name"` and
  `jobcards.TRACKED["carton"] = ("Job Card Carton", "customer_name")`.
- **`quantity_ordered` is `Data`, not Int or Float.** `JobCardCarton.validate_quantity`
  (`job_card_carton.py:64-74`) parses it with `int()` and throws on failure. Every quantity rule in
  the CPS work — remaining, carded, rollup, 3-dp comparison — is numeric.
- `customer_product_spec` is **`reqd = 0`** and is validated **against the live specification**
  (`job_card_carton.py:28-49`): customer match, `product_type == "Carton"`, `status == "Active"`.
  This is exactly the live-read path Computer Paper deliberately abandoned (see §5).
- Read-only, spec-derived fields already present: `specification_name`, `ink_type`,
  `uses_c/m/y/k`, `number_of_colours`, `spot_colours` (Table → Spot Colour), `colour_notes`.
- Carton-specific writable fields: `ply` (SFK/3/5), `flute_type` (B/C/E), `ctn_length_mm`,
  `ctn_width_mm`, `ctn_height_mm`, `ctn_flap_mm`, `1..5_ply_*_gsm`, `1..5_ply_top_layer_material`,
  `joint_type`, `idod`, **`product_type`** (Tray / Die Cut / 1|2|3 Flap RSC),
  `printing_or_plain`, `special_instructions`, `repeat` (Old/New).
- Board-plan/derived: `board_width_planned_mm`, `board_length_planned_mm`,
  `approximate_weight_grams` (read-only, computed client-side), `board_*_actual_mm`,
  `max_reel_width` (default 1500), `knife_gap_mm`, `trim_allowance_width_mm` /
  `trim_allowance_length_mm` (default 10), plus HTML board-plan and UPS-forecast panels.
- Status fields: `status` (Draft/In Progress/Completed/Cancelled, read-only, `allow_on_submit`),
  `job_status` (Open…Cancelled, read-only, `allow_on_submit`), `machine` → Workstation,
  `date_created`, `due_date`.

### Fields Job Card Carton does **not** have (all present on Job Card Computer Paper)

`sales_order`, `sales_order_item`, `item_code`, `rate`, `price_source`, `so_qty`,
`spec_snapshot`, `spec_snapshot_at`, `order_date`, `lpo_number`, `plate_status`, `plate_code`,
`sales_rep`, `sales_rep_approval_date`, `production_stages`.

### Permissions (as declared in the DocType JSON)

| Role | read | write | create | delete | submit | cancel | amend |
|---|---|---|---|---|---|---|---|
| System Manager | 1 | 1 | 1 | 1 | 1 | **0** | **0** |
| Manufacturing Manager | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| Sales User | 1 | **0** | **1** | 0 | **1** | **1** | 0 |

Compare Job Card Computer Paper:

| Role | read | write | create | delete | submit | cancel | amend |
|---|---|---|---|---|---|---|---|
| System Manager | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Sales Manager | 1 | 1 | 1 | 0 | 1 | 1 | 1 |
| Sales User | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| Manufacturing Manager | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| Manufacturing User | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

**The Carton permission set is incoherent and blocks the flow as designed.** Sales User can
*create* but not *write* — Frappe's insert path needs `create`, but the guided flow's draft-then-
review-then-submit shape needs `write`; Sales User can *submit and cancel* a production document
while a *System Manager cannot cancel or amend one at all*. `so_spec_control.on_cancel` (V14)
refuses to cancel a Sales Order while its job cards are submitted — with no cancel permission for
System Manager, a mistaken Carton card would strand its order permanently. There is also no
`Sales Manager` row and no `Manufacturing User` row.

### Fixtures

`hooks.py:135-149` exports `Custom Field` for `Job Card Carton` (among others) as a fixture, and
`Print Format` "Carton Job Card". Any Carton field added as a *Custom Field* rather than a DocField
will travel via that fixture; fields added to the JSON travel by git + migrate. Pick one and be
consistent — mixing them is how a field exists on one site and not another.

---

## 4. What a Sales Order freezes, and what a Carton CPS must add

### Sales Order Item custom fields today

From `patches/v8_0/add_cps_control_custom_fields.py:125-295`, all created as Custom Fields because
Frappe Cloud rejects DocField writes on core DocTypes (403):

**Inputs (2):** `custom_cps` (Link → CPS; re-asserted with `in_list_view` by the iteration-two
patch) and `custom_price_override_reason` (Small Text).

**Server-written, read-only, no `allow_on_submit` (12):** `custom_cps_rate` (Currency, precision 9),
`custom_cps_uom`, `custom_cps_valid_from`, `custom_cps_price_row`, `custom_price_source`,
`custom_price_variance_pct`, `custom_price_approved_by`, `custom_spec_name`, `custom_job_size`,
`custom_number_of_parts`, `custom_number_of_colours`, `custom_spec_snapshot_at`,
`custom_spec_snapshot` (Long Text).

**Rollups, the only two with `allow_on_submit` + `no_copy`:** `custom_jc_qty` (Float, 3 dp,
"includes draft Job Cards") and `custom_jc_status` (Not Started / Partial / Fully Carded).

Snapshot fields are **outputs of validation, never inputs** (V12): `_clear_snapshot` wipes all 13
on every draft save and `_stamp_snapshot` rewrites them server-side inside the submit pass
(`so_spec_control.py:435-481`). Whatever a REST or Data Import caller posts is discarded.

### The snapshot payload is Computer-Paper-shaped — the central Carton finding

`cps_rules.build_spec_snapshot` (`cps_rules.py:846-898`) freezes exactly:

- **Scalars:** `product_type, specification_name, customer, job_size, pay_slip_size,
  number_of_parts, numbering_required, standard_packing, standard_weight_per_carton, ink_type,
  uses_c, uses_m, uses_y, uses_k, number_of_colours, colour_notes`
- **Tables:** `colour_of_parts` (`part_number, paper_type, gsm, colour, purpose`),
  `spot_colours` (`pantone_code, pantone_name, hex_preview, cmyk_*, notes`)
- **Provenance:** `_snapshot_version: 1`, `_cps`, `_cps_modified`, `_taken_at`

`pay_slip_size`, `number_of_parts` and `colour_of_parts` are Computer-Paper-only. **Not one Carton
field is frozen.** A Carton order submitted today captures the customer, the name, the job size,
the colour block and nothing about the box.

**Carton CPS fields that must be added to the frozen set** (from
`customer_product_specification.json`, all `depends_on: doc.product_type=='Carton'`):

`ply`, `flute_type`, `ctn_length_mm`, `ctn_width_mm`, `ctn_height_mm`, `printing_or_plain`,
`joint_type`, **`product_type_carton`**, `idod`, `special_instructions_carton`,
`1_ply_top_layer_gsm`, `1_ply_top_layer_material`, `2_ply_fluting_gsm`, `2_ply_top_layer_material`,
`3_ply_bottom_gsm`, `3_ply_top_layer_material`, `4_ply_fluting_gsm`, `4_ply_top_layer_material`,
`5_ply_fluting_gsm`, `5_ply_top_layer_material` — plus the shared `numbering_required`,
`standard_packing`, `standard_weight_per_carton` already in the set.

> ⚠ **Name collision, high consequence.** On the CPS, `product_type` is the *specification kind*
> ("Carton"); the carton **style** is `product_type_carton`. On Job Card Carton the style field is
> named `product_type`. `cps_rules.snapshot_product_type()` reads `snapshot["product_type"]` and
> `Job Card Computer Paper._validate_frozen_line` routes the card on it. Mapping
> `product_type_carton → product_type` naively into the snapshot would overwrite the routing key
> and send Carton lines to the wrong card type. The snapshot must keep CPS fieldnames verbatim (as
> its docstring states) and the rename must happen in the *snapshot → Job Card* mapping only.

### Snapshot → Job Card Carton field mapping gaps

Against `jobcards_core.SNAPSHOT_SCALAR_MAP` / `SNAPSHOT_TABLE_MAP` (`jobcards_core.py:38-58`),
checked against the Job Card Carton field list:

| snapshot key | CP job-card target | exists on Job Card Carton? |
|---|---|---|
| `specification_name` | `specification_name` | ✅ |
| `ink_type`, `uses_c/m/y/k`, `number_of_colours`, `colour_notes` | same | ✅ |
| `spot_colours` (table) | `spot_colours` | ✅ |
| `job_size` | `job_size` | ❌ |
| `pay_slip_size`, `number_of_parts`, `colour_of_parts` | same | ❌ (correctly — CP-only) |
| `numbering_required` | `numbering_required` | ❌ |
| `standard_packing` → `packing` | `packing` | ❌ |
| `standard_weight_per_carton` → `weight_per_carton` | `weight_per_carton` | ❌ |

The mapping loop guards every write with `jc.meta.has_field(...)` (`jobcards.py:281-286`), so these
**fail silently** rather than throwing. A Carton card raised through the current code would come out
missing its packing, weight, numbering flag and job size with no error at all.

---

## 5. Current Carton Job Card creation paths

Three paths exist today; **none is order-derived.**

1. **Desk form** — `job_card_carton.js`. `set_query` on `customer_product_spec` calls
   `get_carton_customer_product_spec_query` (`job_card_carton.py:77-103`), which filters
   `customer = <customer>, product_type = 'Carton', status = 'Active'` **from the live spec table**,
   then `frappe.call` (lines 64, 89) pulls spec values onto the card. `validate` re-reads the live
   spec. All board-plan geometry, ply rules, SFK rules, flap autofill, weight and the UPS forecast
   are computed **client-side** in the same file (~1090 lines) — none of it is server-verified.
2. **Compass "create job card" screen** — `frontend/src/dashboards/JobCardCreate.tsx` →
   `jobcards.job_card_create(kind="carton", data={...})` (`jobcards.py:132-174`). Manager-only
   (`_assert_manager`), required fields are only `customer_name, ctn_length_mm, ctn_width_mm`,
   no spec and no order.
3. **Compass tracker** — `jobcards.TRACKED` reads and `jobcards.review` / `submit_doc` act on
   existing cards. Read/act only.

Compass **tracks** four kinds but can **create** three, and `jobcards_core.JOB_CARD_KINDS`
(`jobcards_core.py:19`) — the registry that resolves an order-derived card — contains exactly
one entry: `{"Computer Paper": ("Job Card Computer Paper", "computer_paper")}`.
`so_spec_control.JOB_CARD_DOCTYPES` (`so_spec_control.py:33`) likewise. Both are explicitly
labelled "one registry entry each in Phase 3".

---

## 6. The Computer Paper guided flow — what generalising actually means

The flow is four cooperating pieces:

| Piece | Location | Role |
|---|---|---|
| `sales_order_cps.js` | `production_log/public/js/` (456 lines) | Desk: filtered spec query, per-line preview, **Create → Computer Paper Job Card** button on submitted orders, and the resets |
| `cps_desk.cps_line_preview` | `production_log/job_card_tracking/cps_desk.py:47-86` | read-only preview, shares `cps_rules` with submit so the two cannot disagree |
| `jobcards.job_card_create` / `_job_card_from_sales_order` | `vcl_compass/api/jobcards.py:132-302` | the actual insert, cross-app |
| `jobcards_core` | `vcl_compass/api/jobcards_core.py` | Frappe-free rules: kind resolution, blocks, qty, plate, due date, snapshot mapping |

Note the cross-app coupling: the button in **production_log** calls
`vcl_compass.api.jobcards.job_card_create` (`sales_order_cps.js:20`). Any Carton generalisation
touches both repos and both must deploy together.

Properties worth preserving verbatim when generalising:

- **Kind is resolved from the snapshotted product type, never from the payload and never from the
  live CPS** (`jobcards.py:233-239`).
- **Nothing identifying, pricing or specifying comes from the caller.** Only four operator inputs:
  qty, plate status, plate code, due-date override (`jobcards.py:200-204`).
- **Exact child-parent membership**: the line is found by scanning `so.items`, not by
  `get_doc("Sales Order Item", name)` (`jobcards.py:217-220`); the server-side controller repeats
  this under a row lock with `verify_parent=True` (`job_card_computer_paper.py:324-364`).
- **Batch is atomic by not committing** — a throw on selection 3 rolls back 1 and 2; no try/except
  swallowing (`jobcards.py:305-361`).
- **Order-derived cards are exempt from live-spec validation** and are instead proved field-by-field
  against the frozen line by `cps_rules.jc_line_mismatches`
  (`cps_rules.py:562-609`; called from `job_card_computer_paper.py:220-275`). This check is
  **deliberately not gated** on `custom_cps_control_enabled` — turning control off later must not
  turn a forged card into a valid one.
- **Over-carding is a hard throw for every role**, drafts reserve quantity, and the SO-line rollup
  is recomputed under a row lock on `on_update` / `on_cancel` / `on_trash`
  (`job_card_computer_paper.py:66-89, 277-420`).

### The safe generalisation shape

Everything product-specific in the flow is already a registry entry or a map. The safe route is to
**widen the data, not fork the code**:

1. `jobcards_core.JOB_CARD_KINDS` += `"Carton": ("Job Card Carton", "carton")`.
2. `so_spec_control.JOB_CARD_DOCTYPES` += `"Carton": "Job Card Carton"` (so V14 cancel-blocking
   covers Carton).
3. `cps_rules.build_spec_snapshot` → make `scalar_fields` product-type-aware (a per-type tuple keyed
   off `spec.product_type`, unioned with the shared set), keeping CPS fieldnames verbatim.
4. `jobcards_core.SNAPSHOT_SCALAR_MAP` → per-kind maps; add the Carton map including the
   `product_type_carton → product_type` rename.
5. Job Card Carton needs the order-derived field block: `sales_order`, `sales_order_item`,
   `item_code`, `rate`, `price_source`, `so_qty`, `spec_snapshot`, `spec_snapshot_at`,
   `order_date`, `lpo_number` — all `read_only`, none `allow_on_submit`.
6. `JobCardCarton` needs the Computer-Paper controller behaviours lifted wholesale:
   `validate_sales_order`, `_load_sales_order`, `_validate_frozen_line`, `_lock_sales_order_line`,
   `_carded_qty`, `update_sales_order_rollup`, `is_order_derived`, and the `on_update` /
   `on_cancel` / `on_trash` hooks. **Recommendation: extract these into a shared mixin or module
   rather than copy them** — they are ~200 lines of concurrency-sensitive logic and a second copy
   will drift.
7. `job_card_carton.py:28-49` must become `is_order_derived()`-aware in the same way
   `job_card_computer_paper.py:110-148` is: legacy cards keep the live check, order-derived cards
   are proved against the frozen line instead.
8. `sales_order_cps.js` — the button label and `_job_card_lines`' hard
   `if kind != "computer_paper": continue` (`jobcards.py:387`) both need to become kind-driven.
9. `jobcards.KINDS["carton"]` already exists with `customer_field: "customer_name"` — the
   order-derived insert at `jobcards.py:260-280` hardcodes `"customer": so.customer` and must use
   `KINDS[kind]["customer_field"]`, or Carton cards will insert with a blank customer.
10. Plate status/code are **required inputs in the CP dialog and on the CP card**; Job Card Carton
    has no plate fields at all. `jc_core.plate_block_reason` must become optional per kind, or
    Carton must gain the fields. **Decision needed — see §9.**

---

## 7. Permissions and workflows

- **No Workflow documents** are referenced anywhere in the app; state is carried by `docstatus`
  plus the `status` / `job_status` Select fields, with transitions in controller `set_status()` and
  the `_carton_set_job_status` buttons in `job_card_carton.js:1050-1080`.
- **Roles in play:** `Sales Master Manager` (CPS price approval **and** price-override submit —
  `cps_pricing.py:17`, `so_spec_control.py:20`), `Sales Manager`, `Sales User`,
  `Manufacturing Manager`, `Manufacturing User`, `System Manager`.
- **Migration report access** is gated on role, not DocType permission — `System Manager` or
  `Sales Master Manager` only, because it exposes every customer's agreed rate across the whole
  book (`cps_migration_report.py:32-62`).
- **Compass scope:** `_assert_manager()` refuses a CSRA-scoped rep for the *hand-built* create
  paths, but the **order-derived** paths deliberately skip it and rely instead on read permission
  on the order + CSRA customer scope + a normal (non-`ignore_permissions`) insert
  (`jobcards.py:206-211, 328-332`). Preserve that reasoning for Carton; adding `_assert_manager` to
  the Carton order-derived path would make raising a Carton card need a role that raising a CP card
  does not.
- **Job Card Carton's own permission table is the outstanding problem** — see §3.

---

## 8. Data migration risks

Ranked by likelihood × consequence.

1. **No Carton snapshot exists on any historic order.** Every Carton line submitted before the
   snapshot lands has an empty `custom_spec_snapshot`, and both
   `jc_core.line_block_reason` and `_validate_frozen_line` refuse to card such a line — the
   remedy in both messages is "amend the Sales Order". For a live Carton book that is a large,
   manual, order-by-order amendment exercise. **Quantify before committing to a cutover date.**
2. **Unlinked Carton CPS records block everything.** `spec_serves_item` has no fallback; every
   Carton spec needs an exact `linked_item` before enforcement. `cps_rules.resolve_item_link`
   auto-maps **only** when exactly one Item reaches high confidence and nothing else is even a
   medium contender (`cps_rules.py:791-820`); `cps_migration_report` deliberately **never writes**
   — proposals are applied by hand. Budget human time proportional to the unlinked count.
3. **`quantity_ordered` is `Data` on Job Card Carton.** Changing it to Int/Float is a schema change
   over live rows containing arbitrary strings ("5000 pcs", "10,000", ranges). Needs an audit patch
   *before* the type change, and a decision on rows that will not parse. This is the highest-risk
   single schema change in the project.
4. **UOM mismatch blocks submit** (`so_spec_control.py:395-401`). Carton specs priced per one UOM
   against lines ordered in another will throw on the first submit after the flag flips.
5. **`custom_requires_cps` re-derivation is a background job.** Ticking a Carton Item Group enqueues
   `rederive_items_for_group` on the `long` queue and commits directly. On a large Carton subtree
   there is a window where the flag is stale; do not flip
   `Selling Settings.custom_cps_control_enabled` until it has drained.
6. **Duplicate `valid_from` on existing Carton price rows** will throw on the *next save* of the
   spec, not at migration time — a latent failure that surfaces when someone edits an unrelated
   field. Sweep for duplicates before enforcement.
7. **Approval-status backfill.** `approval_status` defaults to `Draft` and is read-only; every
   historic Carton price row will be invisible to `resolve_eligible_price` until explicitly
   approved by a `Sales Master Manager`. Bulk approval is a deliberate management act, not a patch.
8. **The naming-series inconsistency** (`JC-CORR-.YYYY.-.####.`, 4 digits) — leave it alone.
   Changing a series on a live submittable doctype risks name collisions. Note it, do not fix it.
9. **Silent field-mapping failures.** The `jc.meta.has_field()` guard means a missing Carton target
   field produces a card with quiet holes rather than an error. Add an explicit
   assertion or a startup check that every mapped target exists.

---

## 9. Decisions needed

1. **Plate on Carton.** Job Card Carton has no `plate_status` / `plate_code`. Does a Carton job
   carry a plate concept (it has `printing_or_plain` and a `repeat` Old/New field, which may be the
   Carton analogue), or should plate validation become per-kind optional?
2. **`quantity_ordered` type change** — convert `Data` → Int/Float across live rows, or keep `Data`
   and coerce at every boundary? Recommend converting, but only after an audit of unparseable rows.
3. **Job Card Carton permission table** — what is the intended matrix? Current state (Sales User
   creates but cannot write, submits and cancels; System Manager cannot cancel or amend) is not
   workable with the CPS flow and needs a deliberate answer, not a copy of the CP table.
4. **`customer_name` vs `customer`** — rename the Carton field to `customer` for uniformity (a
   patch over live data plus every JS/print-format/report reference), or keep the asymmetry and
   drive it from `KINDS[kind]["customer_field"]`? Recommend the latter — the indirection already
   exists in two places in Compass.
5. **Carton dimensions in `MATERIAL_SPEC_FIELDS`** — should changing `ctn_length_mm` etc. force an
   Item link and be treated as material? Recommend yes, but it converts some currently-savable
   legacy Carton specs into blocked saves; confirm the appetite.
6. **Historic Carton order amendment** — is amending submitted Carton orders to freeze snapshots
   acceptable operationally, or should Carton go live "new orders only" with legacy cards raised on
   the existing non-order path during a transition?
7. **Board-plan geometry** — currently client-side only in `job_card_carton.js`. Should the
   snapshot freeze computed board dimensions, or should the card recompute from frozen CPS
   dimensions at creation? Recommend recompute-from-frozen-inputs; freezing derived geometry means
   a formula fix never reaches an open job.
8. **Cutover sequencing** — Carton and Computer Paper share one
   `Selling Settings.custom_cps_control_enabled` flag. Flipping it enforces both. Is a per-product-
   type enablement needed, or is Carton readiness a precondition for flipping at all?

---

## 10. Assumptions this report makes explicit

- That the Carton work is intended to reach the **same** standard as Computer Paper (frozen
  snapshot, order-derived cards, provenance verification, over-card protection) rather than a
  lighter link-only integration. Everything in §6 assumes this.
- That `Selling Settings.custom_cps_control_enabled` is still **off** in production. This is the
  documented ship state (`so_spec_control.py:9-11`) but **[LIVE — NOT OBTAINED]**; verify before
  any deployment planning, because the flag being already on changes the risk profile of every
  item in §8.

---

## 11. Outstanding live queries — runnable checklist

Run these once live read access is granted. All read-only.

**Status 2026-07-23:** query 7's second half is **answered** — 35 `Job Card Carton` rows, every
`quantity_ordered` numeric, zero unparseable. Queries 1–6, 8 and 9 are **still outstanding** and
still gate the cutover date.

```sql
-- 1. Item Group tree + CPS control settings + Item counts
SELECT ig.name, ig.parent_item_group, ig.is_group, ig.lft, ig.rgt,
       ig.custom_requires_cps, ig.custom_cps_product_type,
       (SELECT COUNT(*) FROM `tabItem` i WHERE i.item_group = ig.name) AS items_total,
       (SELECT COUNT(*) FROM `tabItem` i WHERE i.item_group = ig.name AND i.disabled = 0) AS items_active
FROM `tabItem Group` ig ORDER BY ig.lft;

-- 2. Item-level overrides (Require / Exempt), and flag vs mode disagreement
SELECT item_group, custom_cps_control_mode, custom_cps_product_type,
       custom_requires_cps, COUNT(*) n
FROM `tabItem`
WHERE custom_cps_control_mode IN ('Require CPS','Exempt from CPS')
   OR custom_requires_cps = 1
GROUP BY 1,2,3,4;

-- 3. Carton CPS population: status / docstatus / link / customer
SELECT status, docstatus, COUNT(*) n,
       SUM(linked_item IS NULL OR linked_item = '') AS unlinked,
       COUNT(DISTINCT customer) AS customers
FROM `tabCustomer Product Specification`
WHERE product_type = 'Carton' GROUP BY 1,2;

-- 4. Carton pricing readiness: approved / draft / rejected / no rows at all, and UOMs in use
SELECT p.approval_status, p.uom, COUNT(*) n, MIN(p.valid_from), MAX(p.valid_from)
FROM `tabCPS Price` p JOIN `tabCustomer Product Specification` c ON c.name = p.parent
WHERE c.product_type = 'Carton' GROUP BY 1,2;

SELECT COUNT(*) FROM `tabCustomer Product Specification` c
WHERE c.product_type = 'Carton'
  AND NOT EXISTS (SELECT 1 FROM `tabCPS Price` p
                  WHERE p.parent = c.name AND p.approval_status = 'Approved');

-- 5. Duplicate effective dates that will throw on next save
SELECT p.parent, p.valid_from, COUNT(*) n FROM `tabCPS Price` p
JOIN `tabCustomer Product Specification` c ON c.name = p.parent
WHERE c.product_type = 'Carton' AND p.approval_status != 'Rejected'
GROUP BY 1,2 HAVING n > 1;

-- 6. Missing Carton spec data (what would block a snapshot)
SELECT SUM(ply IS NULL OR ply = '') no_ply, SUM(COALESCE(flute_type,'') = '') no_flute,
       SUM(COALESCE(ctn_length_mm,0) = 0) no_len, SUM(COALESCE(ctn_width_mm,0) = 0) no_wid,
       SUM(COALESCE(ctn_height_mm,0) = 0) no_hgt, SUM(COALESCE(product_type_carton,'') = '') no_style,
       SUM(COALESCE(1_ply_top_layer_gsm,0) = 0) no_gsm1, COUNT(*) total
FROM `tabCustomer Product Specification` WHERE product_type = 'Carton';

-- 7. Job Card Carton population + the quantity_ordered parse risk
SELECT docstatus, job_status, COUNT(*) n,
       SUM(quantity_ordered REGEXP '^[0-9]+$') AS parses_clean,
       SUM(customer_product_spec IS NULL OR customer_product_spec = '') AS no_spec
FROM `tabJob Card Carton` GROUP BY 1,2;

SELECT name, quantity_ordered FROM `tabJob Card Carton`
WHERE quantity_ordered NOT REGEXP '^[0-9]+$' LIMIT 100;

-- 8. Live Carton Sales Order exposure
SELECT so.docstatus, COUNT(DISTINCT so.name) orders, COUNT(*) lines,
       SUM(soi.custom_cps IS NOT NULL AND soi.custom_cps != '') AS with_cps,
       SUM(COALESCE(soi.custom_spec_snapshot,'') != '') AS with_snapshot
FROM `tabSales Order Item` soi JOIN `tabSales Order` so ON so.name = soi.parent
JOIN `tabItem` i ON i.name = soi.item_code
WHERE i.item_group IN (/* Carton groups from query 1 */) GROUP BY 1;

-- 9. UOM mismatch risk: line UOM vs approved CPS price UOM
SELECT soi.uom AS line_uom, p.uom AS price_uom, COUNT(*) n
FROM `tabSales Order Item` soi
JOIN `tabCustomer Product Specification` c ON c.name = soi.custom_cps
JOIN `tabCPS Price` p ON p.parent = c.name AND p.approval_status = 'Approved'
WHERE c.product_type = 'Carton' AND soi.uom != p.uom GROUP BY 1,2;
```

Non-SQL checks:

- `Selling Settings.custom_cps_control_enabled`, `custom_cps_price_tolerance_pct`,
  `custom_cps_price_floor_pct` — current values.
- Whether `patches.v8_0.add_cps_control_custom_fields` and
  `patches.v8_0.add_cps_iteration_two_fields` have both run on production (`tabPatch Log`).
- Live `Job Card Carton` permission rows (`tabCustom DocPerm`) — they may differ from the JSON.
- Live role membership for `Sales Master Manager`.
- Run `cps_migration_report(product_type="Carton")` — it already answers most of the above and is
  guaranteed read-only.
