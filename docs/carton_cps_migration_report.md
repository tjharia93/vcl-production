# Carton CPS → Sales Order → Job Card — Migration Report

**Date:** 2026-07-23
**Branch:** `agent/carton-orders`
**Repository:** `vcl-production` only. `vcl-compass` was not touched — see §6, which is the one
thing that stops this being end-to-end.
**Baseline:** `26d5a38` (PR #22)
**Companion:** [`carton_cps_discovery.md`](./carton_cps_discovery.md) — the findings this
implements. Section references below are to that report.

---

## 1. What this delivers

Carton reaches the same standard as Computer Paper: a product-type-aware frozen snapshot,
order-derived job cards, provenance verified field by field against what the order froze, draft
reservations, over-card protection and Sales Order rollups under a row lock.

Two things are deliberately *stronger* than Computer Paper, and one is deliberately weaker:

- **Stronger:** every technical value on an order-derived Carton card is proved against the
  snapshot, not just its identity, price and quantity. Computer Paper checks the line-level fields
  only. Carton has no legacy of order-derived cards to grandfather, so the strict rule can be the
  first rule.
- **Stronger:** the snapshot→card mapping refuses to run against a DocType missing any of its
  targets, rather than skipping the write. Discovery §8.9 — a card quietly missing its packing,
  weight and box style looks complete on screen and is not.
- **Weaker, on purpose:** legacy Carton cards (Desk form, Compass hand-built screen, history) keep
  the live-specification check. There is nothing frozen to prove them against.

---

## 2. Verified live position

| Fact | Value | Source | Consequence |
|---|---|---|---|
| `Job Card Carton` rows with a `quantity_ordered` | **35** | live audit, supplied to this turn | Small enough that the type change is a non-event. |
| …of which parse as numeric | **35 (100%)** | live audit | Discovery §8.3 — "the highest-risk single schema change in the project" — is **closed**. Nothing needs correcting before the `Data → Float` conversion. |
| …of which will not parse | **0** | live audit | The pre-model-sync guard will not fire. |

Everything else remains **[LIVE — NOT OBTAINED]**. Live ERPNext was not read this turn by
instruction. The counts that still gate a cutover date, all runnable from discovery §11:

1. Carton Sales Order lines with no `custom_spec_snapshot` — every one needs an amendment before it
   can be carded (discovery §8.1). **Unquantified.**
2. Carton CPS records with no `linked_item` — every one blocks its Item outright (§8.2).
   **Unquantified.** The Computer Paper baseline was 53 of 56.
3. Carton `CPS Price` rows not `Approved` (§8.7), duplicate `valid_from` (§8.6), and line-UOM vs
   price-UOM mismatches (§8.4). **Unquantified.**
4. Current value of `Selling Settings.custom_cps_control_enabled`. Documented as off; **unverified.**

None of these are code problems and none is fixed by deploying this branch. They are the migration.

---

## 3. Files changed

### Rules — Frappe-free, unit tested

| File | Change |
|---|---|
| `production_log/job_card_tracking/cps_rules.py` | Completed the previous cycle's product-type-aware material-field work (`SHARED_MATERIAL_SPEC_FIELDS`, `CARTON_MATERIAL_SPEC_FIELDS`, `material_spec_fields`, `material_spec_changes`); simplified `item_link_required`'s loop-as-boolean. **New:** snapshot version 2 with `SNAPSHOT_V1_SCALARS` as a compatibility floor, `CARTON_SNAPSHOT_SCALARS`, `snapshot_scalar_fields`, `snapshot_version`, `snapshot_version_supported`; `CARTON_SNAPSHOT_JC_MAP` and `SNAPSHOT_KEYS_NOT_ON_JOB_CARD`; `unmapped_snapshot_keys`, `unmapped_jc_targets`, `jc_snapshot_mismatches`; `customer_field` parameter on `jc_line_mismatches`. |

### Controllers

| File | Change |
|---|---|
| `production_log/job_card_tracking/order_derived.py` | **New.** The ~200 lines of concurrency-sensitive logic lifted verbatim out of `job_card_computer_paper.py` — row lock, parent verification, carded quantity, over-card refusal, rollup — as `OrderDerivedJobCard`, plus the snapshot version gate and the mapping-target assertion. Discovery §6.6 recommended extracting rather than copying; a second copy would drift. |
| `…/doctype/job_card_computer_paper/job_card_computer_paper.py` | Now inherits the mixin. Methods deleted, not rewritten. `SO_LINE_BASE_FIELDS`, `SO_LINE_CONTROL_FIELDS` and `_describe_mismatch` are re-exported so existing importers are unaffected. Behaviour is identical except for one addition: a snapshot declaring an unsupported version is refused (every snapshot this app has ever written declares 1 or 2). |
| `…/doctype/job_card_carton/job_card_carton.py` | Rewritten on the mixin. `JC_CUSTOMER_FIELD = "customer_name"`, full `JC_SNAPSHOT_FIELD_MAP`, `on_update` / `on_cancel` / `on_trash` rollups, numeric quantity, and `validate_customer_product_spec` now exempts order-derived cards. |
| `production_log/job_card_tracking/so_spec_control.py` | `JOB_CARD_DOCTYPES` gains `"Carton": "Job Card Carton"`, so V14 cancel-blocking covers Carton. The loop now also skips a registered DocType whose `sales_order` field has not landed — otherwise cancelling *any* order on a half-deployed site would throw. |

### Schema

| File | Change |
|---|---|
| `…/doctype/job_card_carton/job_card_carton.json` | **`quantity_ordered`: `Data` → `Float`, precision 3**, `in_list_view`. Order-derived block added: `order_date`, `lpo_number`, `sales_order`, `sales_order_item`, `item_code`, `rate` (9 dp), `price_source`, `so_qty` (3 dp), `spec_snapshot_at`, `spec_snapshot` — all read-only, none `allow_on_submit`. Snapshot-mapping targets added: `job_size`, `numbering_required`, `packing`, `weight_per_carton`. Permissions rewritten (§4). `modified` bumped so migrate picks it up. **`customer_name` and the `JC-CORR-.YYYY.-.####.` series are untouched** — discovery §8.8. |
| `production_log/patches/v8_1/normalise_carton_quantity_ordered.py` | **New**, pre-model-sync. Audits every stored quantity; **throws and aborts the migrate** naming each offending row rather than coercing anything; rewrites survivors as bare decimal text so the `ALTER` has nothing to interpret. Idempotent. On the audited data it writes nothing. |
| `production_log/patches.txt` | `[pre_model_sync]` / `[post_model_sync]` sections introduced. Every pre-existing patch stays in `post_model_sync`, which is where it ran before. |

### Desk

| File | Change |
|---|---|
| `production_log/public/js/sales_order_cps.js` | The submitted-order **Create → Job Cards** dialog is now kind-driven from `JOB_CARD_KINDS`, offering Computer Paper *and* Carton lines in one pass. Kind comes from the frozen snapshot's `product_type`, never from the operator. Plate status/code appear and are mandatory only while a Computer Paper line is ticked; `repeat` (Old/New) only while a Carton line is ticked. Each selection is a separate call creating a separate Draft card, with kind-specific inputs only — a Carton call carries no plate keys at all. |

### Tests

| File | Change |
|---|---|
| `production_log/job_card_tracking/test_carton_cps_rules.py` | **New**, 60 cases. Material fields per type, `material_spec_changes` including the retype-union case, `item_link_required` grandfathering, snapshot shape and version gating, the mapping invariants, `jc_snapshot_mismatches`, and the `customer_field` indirection. Includes Computer Paper regression throughout — the legacy material tuple and the version-1 key set are frozen as literals, so a change to the module fails a test rather than moving with it. |
| `production_log/job_card_tracking/test_cps_rules.py` | `_snapshot_version` assertion follows `SNAPSHOT_VERSION`; a version-1-still-readable case added. |

---

## 4. Permissions — the answer to discovery §9.3

The shipped table was incoherent: Sales User could create but not write, and could submit and
cancel a production document, while System Manager could do neither. There was no Sales Manager row
and no Manufacturing User row.

| Role | read | write | create | delete | submit | cancel | amend |
|---|---|---|---|---|---|---|---|
| System Manager | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Sales Manager | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ |
| Sales User | ✅ | ✅ | ✅ | — | — | — | — |
| Manufacturing Manager | ✅ | ✅ | — | — | — | — | ✅ |
| Manufacturing User | ✅ | — | — | — | — | — | — |

Sales User can now raise and edit the draft the guided flow produces, and can no longer submit or
cancel a production document. System Manager can cancel, which is what stops a mistaken Carton card
stranding its Sales Order permanently under V14.

⚠ **DocType JSON permissions do not overwrite a live `Custom DocPerm`.** Discovery §11 flags that
the live rows may already differ. Verify them after migrate — this is an OAT step, not a patch,
because silently resetting a permission somebody deliberately customised is worse than leaving it.

---

## 5. The name collision, handled in exactly one place

On the specification, `product_type` is the **kind** (`Carton`) and `product_type_carton` is the
**style** (Tray / Die Cut / n-Flap RSC). On Job Card Carton the style field is called
`product_type`.

- The snapshot keeps CPS fieldnames **verbatim**. `product_type` stays the routing key that decides
  which DocType a line becomes.
- The rename `product_type_carton → product_type` exists **once**, in
  `cps_rules.CARTON_SNAPSHOT_JC_MAP`, and is applied only at the mapping/validation boundary.
- `cps_rules.SNAPSHOT_KEYS_NOT_ON_JOB_CARD` names `product_type` as never-copied, and
  `unmapped_snapshot_keys` turns "every frozen field is mapped or explicitly excused" into an
  assertion that must equal `[]`. A field added to the snapshot later and forgotten fails a test.

---

## 6. What is **not** done — the cross-app half

The order-derived insert lives in `vcl_compass`, which this brief put out of scope. Deploying this
branch alone gives you the schema, the rules and the Desk dialog; it does **not** give you a working
Carton create path. `vcl_compass` needs, and the two must deploy together:

1. `jobcards_core.JOB_CARD_KINDS` += `"Carton": ("Job Card Carton", "carton")`.
2. `jobcards_core.SNAPSHOT_SCALAR_MAP` → per-kind, with the Carton map taken from
   `cps_rules.CARTON_SNAPSHOT_JC_MAP` (import it; do not restate it).
3. `jobcards.py:260-280` must write the customer through `KINDS[kind]["customer_field"]` instead of
   hardcoding `"customer"`, or Carton cards insert blank.
4. `jobcards._job_card_lines` must drop `if kind != "computer_paper": continue`.
5. `jc_core.plate_block_reason` must become per-kind optional, and `job_card_create` must accept the
   `repeat` input the dialog now sends for Carton.
6. Preserve the reasoning in discovery §7: the order-derived path deliberately skips
   `_assert_manager`. Adding it for Carton would make raising a Carton card need a role that raising
   a Computer Paper card does not.

Until (5) lands, the dialog's Carton calls will be rejected by the Compass endpoint. That is the
correct failure — a rejected call, not a malformed card.

---

## 7. Deploy sequence

1. Merge and deploy **`vcl-production` and `vcl-compass` together**. Neither is useful alone.
2. `bench migrate`. The pre-model-sync patch runs first and either passes silently (expected: 35/35
   numeric) or aborts naming the rows to fix. **If it aborts, nothing has been changed** — fix the
   rows and re-run.
3. Confirm `Job Card Carton` gained its order-derived fields and that `quantity_ordered` is
   `decimal`. Spot-check three legacy cards: quantity intact, card opens, saves.
4. Verify the live `Custom DocPerm` rows for `Job Card Carton` against §4.
5. **Leave `Selling Settings.custom_cps_control_enabled` off.** Everything above is additive and
   changes no existing behaviour until that checkbox flips.
6. Before flipping it, obtain the four outstanding counts in §2 and clear discovery §8.1 and §8.2.
   Ticking a Carton Item Group first enqueues a background re-derivation (§8.5) — let it drain.

## 8. Rollback

Reverting the branch reverts the code and the DocType JSON, but **not** the `quantity_ordered`
column type — a Frappe migrate on the reverted JSON returns it to `varchar`, and the values are
numeric text either way, so no quantity is lost in either direction. The patch log entry for
`v8_1.normalise_carton_quantity_ordered` remains; it is idempotent and re-running is harmless.

Snapshots already written at version 2 stay readable by the reverted code **only if** the reverted
code's `SUPPORTED_SNAPSHOT_VERSIONS` still contains 2 — it does not. Cartons ordered after the
deploy could not be carded by the old code anyway, since Carton was not in `JOB_CARD_KINDS`. No
Computer Paper snapshot is affected: version 2 writes exactly the version-1 key set for Computer
Paper, so an old reader sees a snapshot it fully understands apart from the version number.

---

## 9. Verification status

The Frappe-free tests were **written but not executed in the session that produced this report** —
`python3` invocations were refused by that session's permission layer. Run before merge:

```bash
python3 -m unittest discover -s production_log/job_card_tracking -p "test_*.py" -t .
```

The Frappe-bound half — row locks, throws, rollups, the permission table, the patch — needs a bench
and is covered by `docs/testing/uat-plan.md` and `oat-plan.md`, both of which must gain a dated
entry for this change per the rule in `docs/testing/README.md`.
