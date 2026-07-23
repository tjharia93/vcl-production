# Label CPS → Sales Order → Job Card — Migration Report

Branch `agent/label-orders`. Companion to `label_cps_discovery.md`, which holds
the verified live facts and the reasoning; this holds the change list, the
deploy sequence and the rollback.

**Ships dormant.** No control flag is flipped, no Item Group is configured, no
Item is set to `Require CPS`, and no CPS Price row is created. On the audited
site nothing observable changes on deploy except the Job Card Label form gaining
a Sales Order section that is empty on every existing card.

---

## 1. What this delivers

Job Card Label becomes an order-derived card on the shared
`OrderDerivedJobCard` architecture, on the same terms Job Card Carton did in
#23 — extended, never duplicated.

* A Label Sales Order line, once controlled and submitted, freezes a **version 3**
  snapshot carrying the label's geometry, tooling, substrate and colour block.
* A Job Card Label raised from that line is proved against it field by field —
  identity, customer, LPO, order date, rate, price source, line quantity, the
  full technical block, and the spot colour grid row for row.
* A frozen order-derived card **stops re-reading the live specification**. What
  was sold is what is made.
* Over-carding a line is refused; drafts reserve quantity; the Sales Order line
  rollup stays honest through save, submit, cancel and delete.
* A Sales Order with a live Label job card cannot be cancelled out from under it.
* **The 20 historical rows that already named a Sales Order keep working** and
  keep their links — without being mistaken for frozen cards, and without any
  new card being able to claim the same exemption.

---

## 2. Verified live position (2026-07-23)

| | |
|---|---|
| Label CPS records | 192 — 163 draft, 25 submitted, 4 cancelled |
| Missing `linked_item` | 185 |
| Missing `label_length` / `label_width` / `material_type` | 0 / 0 / 0 |
| `numbering_required = 1` | 0 |
| `cylinder_teeth`, `plate_up`, `plate_round`, `packing_up` | all numeric-compatible |
| CPS Price rows for a Label spec | 0 |
| Label specs with a `current_rate` | 0 |
| Label Item Group configured as controlled | none |
| Job Card Label rows | 56 — 31 submitted, 25 draft |
| Non-numeric `quantity_ordered` | 0 |
| Rows with `sales_order` | 20 |
| Rows with `sales_order_item` | 7 |
| Rows with a frozen snapshot | **0** |
| `Job Card Label-sales_order` | exists as a **Custom Field** (Link → Sales Order) |
| `Job Card Label-sales_order_item` | exists as a **Custom Field** (Link → Sales Order Item) |
| Either as a native DocField | no |

---

## 3. Files changed

### Rules — Frappe-free, unit tested

`production_log/job_card_tracking/cps_rules.py`

* `LABEL_DIMENSION_FIELDS`, `LABEL_TOOLING_FIELDS`, `LABEL_SUBSTRATE_FIELDS`,
  `LABEL_MATERIAL_SPEC_FIELDS`, registered in
  `PRODUCT_TYPE_MATERIAL_SPEC_FIELDS`.
* `LABEL_SNAPSHOT_SCALARS`, registered in `PRODUCT_TYPE_SNAPSHOT_SCALARS`.
* `SNAPSHOT_VERSION` 2 → **3** — now meaning "the newest version this code
  knows", not "the version every line is stamped with";
  `SUPPORTED_SNAPSHOT_VERSIONS` → `(1, 2, 3)`.
* `SNAPSHOT_BASE_WRITE_VERSION = 2` and `snapshot_write_version()` — the version
  a line is **stamped** with, per product type. Computer Paper and Carton keep
  writing **2**, exactly as before this release; only Label writes **3**.
  Derived from the floor below, not a second table. See §5a.
* `PRODUCT_TYPE_MIN_SNAPSHOT_VERSION`, `min_snapshot_version()`,
  `snapshot_describes_product_type()` — the per-type floor. Label only.
* `LABEL_SNAPSHOT_JC_MAP` (23 scalars) and `LABEL_SNAPSHOT_JC_TABLE_MAP`
  (the spot colour grid).
* The legacy order-reference section: `ORDER_REF_*`, `LEGACY_ORDER_REF_FIELD`,
  `has_order_reference()`, `has_frozen_snapshot()`, `order_reference_state()`,
  `legacy_order_reference_qualifies()`, `legacy_flag_earned()`,
  `legacy_order_reference_errors()`.

`production_log/job_card_tracking/order_derived.py`

* `JC_LEGACY_ORDER_REFS` class flag, default **False** — Computer Paper and
  Carton behave exactly as before.
* `order_reference_state()`, `is_frozen_order_derived()`,
  `is_legacy_order_reference()`, `sync_legacy_order_reference()`,
  `_stored_order_reference()`, `_amended_from_row()`.
* `validate_sales_order()` now gates on `is_frozen_order_derived()` instead of
  `is_order_derived()`. For a card type without the legacy flag these are the
  same predicate.
* `_validate_frozen_line()` adds the minimum-snapshot-version check, placed
  **after** the product-type check so a Carton snapshot offered to a Label card
  is refused for being a Carton rather than for being old.
* `validate_quantity_against_sales_order_line()` skips a recorded legacy
  reference. `_carded_qty` and `update_sales_order_rollup` still count it.

`production_log/job_card_tracking/so_spec_control.py`

* `JOB_CARD_DOCTYPES` gains `"Label": "Job Card Label"`. This is the
  cancellation-hook registration: `on_cancel` blocks cancelling a Sales Order
  that has a submitted card of any registered kind, and it filters on the
  `sales_order` column the same release adds.

### Controller

`production_log/job_card_tracking/doctype/job_card_label/job_card_label.py`

* `JobCardLabel(OrderDerivedJobCard, Document)`, declaring `JC_PRODUCT_TYPE`,
  `JC_CUSTOMER_FIELD = "customer"`, both Label maps, `QTY_PRECISION = 3` and
  `JC_LEGACY_ORDER_REFS = True`.
* `validate()` re-derives the legacy flag, proves provenance, and **skips the
  live specification re-read only for a genuinely frozen order-derived card**.
* `on_update` / `on_cancel` / `on_trash` maintain the Sales Order rollup.
* `validate_quantity()` uses `flt` and calls the over-carding check.
* `validate_plate()` and `validate_numbering()` unchanged in behaviour and now
  documented as running on every path.

### Schema

`production_log/job_card_tracking/doctype/job_card_label/job_card_label.json`

* New: `section_sales_order`, `sales_order` (Link, read-only, indexed),
  `sales_order_item` (Data, read-only, indexed), `item_code`,
  `legacy_order_reference` (Check, read-only, `no_copy`, indexed),
  `column_break_sales_order`, `rate` (Currency, 9 dp), `price_source`,
  `so_qty` (Float 3), `section_spec_snapshot`, `spec_snapshot_at`,
  `spec_snapshot`.
* Changed: `quantity_ordered` `Int` → `Float` precision 3.
* Conditional read-only on the Sales Order header values — `order_date`,
  `lpo_number` and `customer` all gain
  `read_only_depends_on: eval:doc.sales_order`.
* Permissions aligned with Job Card Carton (§5).

### Patches

| Patch | Section | Does |
|---|---|---|
| `v8_2.retire_label_order_custom_fields` | **pre**_model_sync | Deletes the two colliding Custom Fields and their Property Setters. Keeps every column and every value. Censuses row counts. |
| `v8_2.audit_label_quantity_ordered` | **pre**_model_sync | Censuses count / sum / range of `quantity_ordered` while it is still an `Int`. Refuses the migrate on any non-numeric value. Writes nothing. |
| `v8_2.stamp_legacy_label_order_references` | post_model_sync | Stamps `legacy_order_reference` on rows that exist, name an order and hold no snapshot. `update_modified=False`. |
| `v8_2.verify_label_order_migration` | post_model_sync | Reads both censuses back and stops the migrate if a value was lost, a quantity moved, a Custom Field still shadows a DocField, or a legacy-shaped row is unstamped. |

All four are idempotent and all four are no-ops on a site without the table.

### Tests

* `test_label_cps_rules.py` — new, Frappe-free. Material fields, snapshot shape
  and version floor, the full scalar and table mapping (including
  `unmapped_snapshot_keys == []` and `unmapped_jc_targets == []`), the
  `Data`-vs-numeric comparison, line mismatches under Label's `customer` field,
  and the complete legacy-order-reference matrix.
* `test_label_schema.py` — new, site-dependent (`FrappeTestCase`). Every mapped
  target exists on the real DocType, `quantity_ordered` is a three-decimal
  number, no Custom Field shadows a DocField, the field inventory has not
  drifted from the literal the unit tests rely on, every stamped row still has a
  legacy shape and no legacy-shaped row is unstamped, and the controller /
  registry agree with the DocType.
* `test_carton_cps_rules.py` — four assertions updated for the version bump
  (2 → 3, and "a future version" is now 4), plus a new regression test that
  Carton and Computer Paper have **no** minimum snapshot version and so are not
  retroactively refused.

---

## 4. Mapping — every target verified

23 scalars. `unmapped_snapshot_keys("Label", LABEL_SNAPSHOT_JC_MAP)` is asserted
empty, and every card field is asserted to exist both against a frozen literal
(unit test) and against the live meta (schema test).

| Snapshot key | Job Card Label field |
|---|---|
| `specification_name` | `specification_name` |
| `job_size` | `job_size` |
| `numbering_required` | `numbering_required` |
| `standard_packing` | **`standard_packing`** — identity, unlike Carton's `packing` |
| `standard_weight_per_carton` | `weight_per_carton` — the one rename |
| `ink_type`, `uses_c/m/y/k`, `number_of_colours`, `colour_notes` | identity |
| `dies` | `dies` — the Dies record's **name**, never dereferenced |
| `label_length`, `label_width` | identity (both sides `Float`, precision 2) |
| `material_type` | identity (CPS `Select` → card `Data`, compared as text) |
| `cylinder_teeth`, `plate_up`, `plate_round`, `packing_up` | identity (CPS `Data` → card numeric, compared as numbers) |
| `packing_pieces`, `gap_between`, `side_trim` | identity |

Excused, via `SNAPSHOT_KEYS_NOT_ON_JOB_CARD`: `product_type` (routing key,
checked not copied), `customer` (taken from the order), `pay_slip_size` and
`number_of_parts` (Computer Paper only).

Table map: `spot_colours` → `spot_colours`, all eight
`SNAPSHOT_SPOT_FIELDS` compared row for row, in order.

---

## 5. Permissions — **approved 2026-07-23**

Job Card Label is aligned with Job Card Carton:

| Role | Before | After |
|---|---|---|
| System Manager | full | full (unchanged) |
| Sales Manager | create, write, submit, cancel, amend | unchanged |
| **Sales User** | **read only** | **create + write**, no submit |
| **Manufacturing Manager** | write | write **+ amend** |
| Manufacturing User | read | read (unchanged) |

The Sales User widening is a real privilege change on a live DocType with 56
rows, and it was a business decision rather than a technical one.

**It is approved** (Tanuj Haria, 2026-07-23), on the ground that guided order
creation requires it. An order-derived card is raised by the person taking the
order, from the order, against a snapshot they cannot edit; a Sales User who can
read a Label card but not create one cannot complete that flow at all. The
Manufacturing Manager `amend` is approved on the same basis — a cancelled card
is re-raised by production, and amending is how that happens without a second
unlinked card against the same order line.

The widening is bounded: card fields are proved against the frozen snapshot, the
order reference is immutable once set, and **no `submit` is granted to Sales
User**. Raising a card and committing one stay separate acts held by separate
roles. Rationale in full: `label_cps_discovery.md` §8.

The hunk ships as written; nothing needs reverting before deploy.

---

## 5a. Snapshot write version is per product type

The version a snapshot is **stamped** with is not the newest version this code
knows. It is the oldest version that describes that product type in full:

| Product type | Stamped | Change from before this release |
|---|---|---|
| Computer Paper | 2 | none |
| Carton | 2 | none |
| Label | 3 | new — version 3 is the first that describes a label |
| Anything else | 2 | none |

This is a deployment-order requirement, not a preference. Compass reads these
snapshots, lives in another repository, deploys on its own schedule, and treats
an unrecognised version as unreadable — which is deliberate. A single global
write version would mean every Computer Paper and Carton line submitted after
this deploy is stamped 3 and refused by a Compass that supports only 1 and 2,
for a payload change that does not exist: versions 2 and 3 are byte-identical
for both types.

`snapshot_write_version()` derives the number from
`PRODUCT_TYPE_MIN_SNAPSHOT_VERSION`, floored at `SNAPSHOT_BASE_WRITE_VERSION`.
Deliberately derived rather than tabulated separately: "Label needs at least 3"
and "Label writes 3" are one fact, and two tables holding it could disagree —
the failure being an order that freezes a snapshot its own job card then
refuses. Readers are untouched: `SUPPORTED_SNAPSHOT_VERSIONS` is `(1, 2, 3)` and
Label's floor is 3.

---

## 6. What is **not** done

* **The Compass creation path.** `vcl_compass.api.jobcards.job_cards_from_sales_order`
  lives in the other repository and is untouched, as instructed. Until it can
  build a Label card — including `plate_status`, a required production input the
  order cannot supply — a Label line in the Desk "Create Job Cards" dialog
  correctly reports *"No Job Card type raises Label lines yet."*
* **`public/js/sales_order_cps.js` is deliberately not extended.** Adding Label
  to `JOB_CARD_KINDS` would offer a button that calls an API which cannot serve
  it. The existing dormant message is the honest state.
* **No control data.** No Item Group flagged, no Item set to `Require CPS`, no
  CPS Price row, no `custom_cps_control_enabled`.
* **No Item links created.** 185 Label specifications still need one; that is
  data work, not code, and the transition rule grandfathers them until they are
  materially edited.

---

## 7. Deploy sequence

1. Review and merge the branch. The §5 permission change is approved and ships
   as written — nothing to confirm or revert.
2. `bench migrate`. Watch for four lines:
   * `retire_label_order_custom_fields: N Custom Field(s) retired ...`
   * `audit_label_quantity_ordered: 56 row(s) read, ... Nothing rewritten.`
   * `stamp_legacy_label_order_references: 56 row(s) read, 20 name an order, 0 carry a snapshot, 20 stamped legacy ...`
   * `verify_label_order_migration: 4 check(s) passed - ...`
   A failure in the fourth stops the migrate with the figures side by side.
   Nothing in this release drops a column, so the data is still there.
3. Spot-check on the site: open two of the 20 legacy cards, confirm the Sales
   Order section shows the original link and **Legacy Order Reference** ticked,
   and save one — it must save unchanged.
4. Confirm a Label card with no order still saves and still refreshes from its
   specification.
5. Stop. Steps 3–7 of `label_cps_discovery.md` §9 are the cutover and are
   separate, deliberate acts.

---

## 8. Rollback

* **Before any version-3 snapshot exists** (i.e. any time before cutover step 6):
  revert the branch and `bench migrate`. The Custom Fields do not come back, but
  the columns and every value in them are untouched, and the DocType reverts to
  declaring `quantity_ordered` as an `Int` over values that are all integers.
  The `legacy_order_reference` column is left populated and harmless.
* **After version-3 snapshots exist**: the previous release will refuse to raise
  job cards from **those Label lines**, because `snapshot_version_supported` is a
  whitelist. Roll forward, or amend the affected orders to re-freeze. Computer
  Paper and Carton lines submitted under this release are unaffected — they are
  stamped 2, exactly as before (§5a), so they still card on the previous release
  and on a Compass that has not yet shipped version 3. This is also why the
  cutover is gated: nothing in this deploy creates a version-3 snapshot at all.

---

## 9. Verification status

| | |
|---|---|
| Frappe-free unit tests written | yes — `test_label_cps_rules.py`, 106 tests across 15 classes |
| Site-dependent schema tests written | yes — `test_label_schema.py`, 21 tests |
| Existing Carton/CP tests updated for the write-version split | yes — 3 assertions changed, 9 new regression tests |
| Frappe-free suite **executed** | yes at the pre-review state — **473 passed**; the write-version follow-up has not been re-run, see below |
| Live site touched | no |
| `vcl-compass` touched | no |
| Committed / pushed / deployed | no |

**The write-version follow-up has not been executed.** The 473-test pass predates
it. Every attempt to invoke `python3` (`-m unittest`, `-m pytest`) in the session
that made these edits was refused by the tool permission layer, and that session
was non-interactive so the prompt could not be answered. The change was reviewed
statically instead: `snapshot_write_version()` is a two-term `max()` over
constants already asserted by the suite, and every assertion that previously read
`cps_rules.SNAPSHOT_VERSION` for a Computer Paper or Carton snapshot was located
by grep and changed to the literal `2`.

Re-run before merge:

```
python3 -m unittest production_log.job_card_tracking.test_label_cps_rules \
                   production_log.job_card_tracking.test_carton_cps_rules \
                   production_log.job_card_tracking.test_cps_rules \
                   production_log.job_card_tracking.test_cps_jobcard_rules \
                   production_log.job_card_tracking.test_cps_item_control \
                   production_log.job_card_tracking.test_cps_item_link \
                   production_log.job_card_tracking.test_cps_desk_rules \
                   production_log.job_card_tracking.test_cps_report_rules \
                   production_log.job_card_tracking.test_legacy_spec_rules

bench --site <site> run-tests --module production_log.job_card_tracking.test_label_schema
```

The second needs a site that has already migrated.
