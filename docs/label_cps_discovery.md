# Label CPS → Sales Order → Job Card — Discovery

Branch `agent/label-orders`, cut from `main` after the Carton work merged (#23).
Companion to `carton_cps_discovery.md`; everything that report established about
the shared architecture is assumed here rather than restated.

---

## 0. Evidence status — read this first

Every number in §§1–5 was read from the live production site on **2026-07-23**
before any code was written. Nothing in this report is inferred from the DocType
JSON alone, because the JSON is not what the site runs — the site runs the JSON
plus whatever Custom Fields and Property Setters have accumulated on top of it,
and this release exists largely because of two of those.

Where a statement comes from reading the repository rather than the site it is
marked **[CODE]**.

The Label feature ships **dormant**. `Selling Settings.custom_cps_control_enabled`
stays off, no Label Item Group is configured as controlled, no Label Item is set
to `Require CPS`, and no CPS Price rows are created. §9 sets out the cutover.

---

## 1. Verified live position, 2026-07-23

### Customer Product Specification, `product_type = "Label"`

| Fact | Value |
|---|---|
| Total Label CPS records | **192** |
| Draft (`docstatus 0`) | 163 |
| Submitted (`docstatus 1`) | 25 |
| Cancelled (`docstatus 2`) | 4 |
| Missing `linked_item` | **185** |
| Missing `label_length` | 0 |
| Missing `label_width` | 0 |
| Missing `material_type` | 0 |
| `numbering_required = 1` | **0** |
| CPS Price rows against a Label spec | **0** |
| Label specs with a `current_rate` | **0** |

Four consequences follow, and each shaped a decision:

1. **185 unlinked records mean the Item link cannot be enforced retroactively.**
   The existing transition rule already handles this: a link is required for a
   new specification and for any *material* edit, so an untouched legacy record
   keeps saving. §2 defines what "material" means for a label.
2. **Every label's geometry and material is populated.** The three fields
   `Job Card Label.validate_spec_fields` insists on are present on all 192, so
   an order-derived card built from a frozen snapshot will satisfy that rule
   rather than trip over it.
3. **Nothing has a price.** With zero CPS Price rows there is not one Label line
   that could pass V7 today. That is what makes "dormant" honest rather than
   aspirational: even if the control flag were flipped by accident, no Label
   order could be submitted under control until somebody deliberately creates
   and approves a price.
4. **No specification asks for numbering.** `validate_numbering` is therefore
   dormant in practice. It is still enforced (§6) — the first specification that
   does set it must not find the rule missing.

### The four `Data`-typed numerics

`cylinder_teeth`, `plate_up`, `plate_round` and `packing_up` are `Data` on the
specification and numeric on Job Card Label (`Float`, `Int`, `Int`, `Int`). Every
populated value across all 192 records was checked and **all are
numeric-compatible** — each parses as a number with no unit, range or note
attached.

This is what makes the strict scalar mapping safe. `cps_rules._same_spec_value`
compares anything numeric-looking as a number, so `"96"` frozen against `96.0`
stored is the same value. Had one record held `"96 teeth"` the mapping would
have had to be loosened or the data corrected first; it did not.

### Job Card Label

| Fact | Value |
|---|---|
| Total rows | **56** |
| Submitted | 31 |
| Draft | 25 |
| Rows with a non-numeric `quantity_ordered` | 0 |
| Rows with `sales_order` populated | **20** |
| Rows with `sales_order_item` populated | **7** |
| Rows with a frozen snapshot | **0** |

### The two Custom Fields — the central Label finding

The live site carries:

* `Job Card Label-sales_order` — **Custom Field**, `Link` → `Sales Order`
* `Job Card Label-sales_order_item` — **Custom Field**, `Link` → `Sales Order Item`

Neither is a DocField. Neither is created by any patch in this repository
(`grep -rn sales_order production_log/patches/` returns only the v8_0 Sales Order
Item block) **[CODE]**, and no `custom_field.json` fixture exists — `hooks.py`
names `Job Card Label` in the `fixtures` filter but the repo holds only
`production_log/fixtures/print_format.json` **[CODE]**. They were made by hand.

That produces two separate problems, and conflating them is how this goes wrong:

* **A metadata collision.** Declaring `sales_order` as a DocField while a Custom
  Field of the same name exists puts two entries for one column into the
  assembled meta, and the DocType sync refuses it. This is a *migration*
  problem and is solved in §7.
* **A semantics collision.** Twenty rows already *use* those fields to mean
  something the new code will read as meaning something stronger. This is a
  *behaviour* problem and is solved in §5. It is by far the harder of the two.

---

## 2. What makes a Label specification materially changed

Carried into `cps_rules.PRODUCT_TYPE_MATERIAL_SPEC_FIELDS` as:

* **Geometry** — `label_length`, `label_width`, `gap_between`, `side_trim`
* **Tooling** — `dies`, `cylinder_teeth`, `plate_up`, `plate_round`, `packing_up`
* **Substrate** — `material_type`

`packing_pieces` is deliberately excluded. It says how many labels go in a pack,
which is the same kind of statement as `standard_packing` — and `standard_packing`
has never been material for any product type. It is still **frozen** into the
snapshot; freezing and materiality are different questions, and this is the one
field on which they diverge.

Editing any of the ten above on one of the 185 unlinked records forces an Item
link, which is the intended transition. Editing packing, notes, status or price
does not.

---

## 3. Dies — freeze the name, not the die

`Customer Product Specification.dies` is a `Link` to the `Dies` DocType, and
`Job Card Label.dies` is the same link. The snapshot freezes **the Dies record's
name and nothing else**. The Dies document is never read — not at snapshot time,
not at job card creation, not at comparison time.

The reasoning:

* The name is the shop-floor instruction. "Run die D-114" is what the operator
  needs and it is stable.
* A die's recorded dimensions are live master data. Dies get reground, corrected
  and re-measured. A snapshot that dereferenced the die would silently record
  today's measurement of a tool as though it were a term of the sale, and a
  correction to that master record would retroactively change what a customer
  had agreed to.
* The label's own geometry is already on the specification and is frozen from
  there. Reading it a second time from the die would give two sources for one
  number and no rule for which wins.

So the mapping is `("dies", "dies", "Dies")` and there is no second hop.

---

## 4. The frozen snapshot — version 3

Version 2 froze the Carton block. It froze **nothing** about a label: a Label
order captured the customer, the specification name, the job size, the packing
and the colour block, and not the die, the web, the material or the tooling.

Version 3 adds `LABEL_SNAPSHOT_SCALARS` — the eleven fields of the Label section
— on exactly the terms version 2 added Carton's: **additive only**. Every key
version 1 wrote is still written for every product type, so no consumer that
indexes rather than `.get()`s can break, including consumers in other
repositories that deploy on their own schedule.

A Carton or Computer Paper snapshot written at version 3 would be byte-identical
to one written at version 2 — which is why neither is ever written at 3. See
"Which lines actually get stamped 3" below.

### Why bump at all, given that

Because "readable" and "sufficient" are different questions and both have to be
asked. A version-2 Label snapshot is perfectly readable and everything in it is
true — it simply predates the label geometry. Without the bump, a Label card
raised from such a line would be refused with eleven separate mismatches saying
its die, its web and its material were each expected to be blank. With it, the
card is refused once, with the sentence that is actually true:

> Sales Order line X was frozen at snapshot version 2, which predates the full
> Label specification. Amend the order and re-submit it to freeze a current
> snapshot, then raise the Job Card again.

That is `cps_rules.PRODUCT_TYPE_MIN_SNAPSHOT_VERSION`, and Label is the only
entry in it. Computer Paper has been fully described since version 1 and Carton
since version 2, so neither gets a floor and neither is retroactively refused.

`SUPPORTED_SNAPSHOT_VERSIONS` becomes `(1, 2, 3)`. Old orders stay cardable;
nothing is rewritten.

### Which lines actually get stamped 3 — and why not all of them

Reading is one decision; **writing** is a separate one, and making them the same
decision is a deployment-order bug.

A snapshot's version number crosses a repository boundary. Compass reads these
lines, deploys on its own schedule, and — for exactly the forward-compatibility
reason above — treats a version it does not know as unreadable rather than as a
widening it can ignore. A single global write version therefore means that the
moment this app is deployed, every Computer Paper and Carton line submitted from
then on is stamped 3 and is refused by a Compass release that supports only 1
and 2. For a payload change that does not exist: versions 2 and 3 are identical
for both of those product types.

So the version written is per product type, and it is the oldest version that
still tells the whole truth about the record:

| Product type | Written at | Because |
|---|---|---|
| Computer Paper | **2** | Fully described since version 1; unchanged by this release |
| Carton | **2** | Fully described since version 2; unchanged by this release |
| Label | **3** | Version 3 is the first version that describes a label at all |
| Anything else | **2** | Only the version-1 scalars are frozen for it |

That is `cps_rules.snapshot_write_version()`, and it is **derived from
`PRODUCT_TYPE_MIN_SNAPSHOT_VERSION`** rather than tabulated beside it — floored
at `SNAPSHOT_BASE_WRITE_VERSION = 2`, the number this app was already writing.
There is one fact here, not two: the oldest version that describes a product
type in full is both what a job card demands and what an order freezes. Two
tables could drift apart, and the way they would fail is an order freezing a
snapshot that its own job card then refuses.

`SNAPSHOT_VERSION` stays 3 and keeps its meaning: the newest version this code
knows. It is no longer what every line is stamped with.

### Rollback cost, stated plainly

A site rolled back to the Carton release after this one has written a version-3
snapshot will refuse to card that line. Only **Label** lines are affected —
Computer Paper and Carton lines submitted under this release are stamped 2 and
card perfectly well on the previous one, which is the whole point of the
per-type write version. And since the Label feature ships dormant, the number of
version-3 snapshots in existence at rollback time is zero unless somebody has
deliberately completed the §9 cutover first.

---

## 5. The 20 legacy order references — the hard problem

Twenty Job Card Label rows name a Sales Order. Seven name a Sales Order line.
None carries a snapshot, because when they were written there was nothing to
freeze: the specification was read live at save time.

`OrderDerivedJobCard.is_order_derived()` asks "does this card name an order",
and for all twenty the answer is yes. Applied unchanged, the strict path would
demand a frozen snapshot from every one of them, and twenty historical — mostly
submitted — job cards would stop saving the day this deployed.

Three ways out were considered. Two are worse than the problem:

| Option | Why it was rejected |
|---|---|
| Clear the links | Destroys the only record of which order a job belonged to. The links are *correct*; they are just not what the new code means by the word. |
| Write a snapshot for them | Records a specification state that was never frozen and was never true. A snapshot is a record of what was known then; inventing one is inventing history. |
| **Record the difference** | Taken. |

### The mechanism

A third state, `legacy`, sitting alongside `none` and `frozen`. It is **recorded
in a column, never inferred from a shape**, and that distinction is the entire
security property.

`stamp_legacy_label_order_references` (post-model-sync, one-off) sets
`legacy_order_reference = 1` on exactly the rows that

1. exist at migration time,
2. name a Sales Order or a Sales Order line, and
3. hold no snapshot.

Nothing else about them changes — not the links, not the quantities, not
`modified`, not the docstatus.

From that moment the flag is an **output of validation and never an input**, on
exactly the same terms as the frozen snapshot itself (rule V12). Whatever an API
caller posts into it is discarded. `sync_legacy_order_reference` runs first in
`validate` and re-derives it:

* **Existing row** — the flag is whatever the database holds. It cannot be
  cleared, and the order links cannot be repointed or blanked while it is set.
  Attempting any of those is a throw naming what was attempted.
* **New row** — the flag is off, *unless* it is earned. The only evidence a new
  document can offer is being the amendment of a card that is itself stamped
  legacy, is cancelled, and names the same order and the same line. That is
  checked against the stored row rather than inherited, because `amended_from`
  is read-only on the form and therefore settable over REST like every other
  read-only field.

### What this buys

A card posted tomorrow with a Sales Order and no snapshot has the *same shape* as
the twenty and is refused, because it has no stamp and cannot earn one. Forged
and historical stop being the same document. Meanwhile a legacy card saving its
production remarks touches none of this and behaves exactly as it did in April.

### Quantity: exempt from the check, never from the count

A legacy card is exempt from the over-carding **check** — those cards were
written against orders nobody was measuring, and a rule invented today must not
refuse to save a job that was produced and invoiced months ago.

It is **not** exempt from the arithmetic. `_carded_qty` counts it like any other
card, and `update_sales_order_rollup` includes it. The quantity it consumed is a
fact, and the next card raised from that order is held to it. Exempting the
legacy rows from the count as well would let one line be carded twice.

---

## 6. Job Card Label — what the card validates

| Rule | Order-derived (frozen) | Legacy reference | No order |
|---|---|---|---|
| Proved field-by-field against the frozen line | **yes** | no | no |
| Live CPS re-read and re-copied on every save | **no** | yes | yes |
| Current CPS status/customer/type checked | no | yes | yes |
| `label_length` / `label_width` / `material_type` present | yes | yes | yes |
| Plate status and plate code coherent | yes | yes | yes |
| Numbering range required when `numbering_required` | yes | yes | yes |
| Over-carding refused | yes | no | n/a |
| Counted in the Sales Order rollup | yes | yes | n/a |

The live-refresh skip is the point of the whole exercise, and it applies to
**genuinely frozen order-derived cards only**. On those, the technical values
arrived from the order's frozen snapshot; refreshing them from the live
specification would silently replace what was sold with what the specification
happens to say today — and would then fail `validate_sales_order` on the next
save, which is a confusing way to discover it.

Legacy cards and hand-built cards keep the live check unchanged. They have
nothing frozen to be validated against, so the current specification is the only
evidence available.

Plate and numbering are validated on every path. Plate status is a production
input, not a specification value, so it is never frozen and never proved against
the order; numbering *is* frozen (`numbering_required` is a version-1 key) and is
proved, while the range fields the operator supplies are not.

---

## 7. The Custom Field migration

Solved in `retire_label_order_custom_fields`, **pre_model_sync** — the last
moment before the DocType is rewritten.

The Custom Field rows are deleted. **The columns are not.** Deleting Custom Field
metadata does not drop a column: the row goes from `tabCustom Field` and
`tabJob Card Label` keeps both columns and every value in them. Immediately
afterwards the model sync declares the same two columns from the DocType JSON,
and the historical links come back attached to fields the app now owns.

Type compatibility, checked before writing the patch:

| Field | Was (Custom Field) | Becomes (DocField) | Column |
|---|---|---|---|
| `sales_order` | `Link` → Sales Order | `Link` → Sales Order | `varchar(140)`, unchanged |
| `sales_order_item` | `Link` → Sales Order Item | `Data` | `varchar(140)`, unchanged |

`sales_order_item` becomes `Data`, matching Job Card Carton. The line is proved
by `_lock_sales_order_line`, which reads the row under a lock and verifies its
`parent`, `parenttype` and `parentfield`; a `Link` to a child DocType would add a
second, weaker check and would turn the 7 historical values into a
link-validation risk on every save.

Two supporting details:

* The delete is `frappe.db.delete` rather than `frappe.delete_doc`.
  `CustomField.on_trash` differs between Frappe versions and this patch must be
  exactly one thing — remove a metadata row — on every one of them.
* Property Setters on those fields are removed explicitly. Left behind they are
  orphans pointing at a field that is no longer custom, and Frappe would apply
  them to the new DocField.

The patch is written against a broader list than the two fields that actually
collide, so a site hand-patched differently from the audited one migrates rather
than fails.

### `quantity_ordered`: Int → Float(3)

`audit_label_quantity_ordered`, also pre_model_sync. `Int` → `Float` is a
widening conversion that MariaDB performs exactly, which is a claim — so the
claim is measured rather than asserted. The patch censuses the row count, the
exact sum and the range while the old column still exists, and refuses the
migrate if any value is not a number. It rewrites nothing: unlike the Carton
field, this column is already numeric, which is why it is an audit and not a
normalisation.

### Verification

`verify_label_order_migration`, post_model_sync, reads both censuses back and
stops the migrate if a figure moved. It asserts that no counted column lost a
value, that the quantity count/sum/range are identical to three decimal places,
that no Custom Field shadows a DocField on the far side, and that every row with
a legacy shape carries the stamp. All four patches are idempotent; re-running the
verification after the censuses are consumed falls back to the live-table checks.

---

## 8. Permissions

Job Card Label is aligned with Job Card Carton, which set the house standard for
an order-derived card in the immediately preceding release:

| Role | create | write | submit | cancel | amend | delete |
|---|---|---|---|---|---|---|
| System Manager | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Sales Manager | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Sales User | ✓ | ✓ | — | — | — | — |
| Manufacturing Manager | — | ✓ | — | — | ✓ | — |
| Manufacturing User | — | — | — | — | — | — |

**This widens Sales User from read-only to create + write** and gives
Manufacturing Manager `amend`. It is a real privilege change on a live DocType
with 56 rows.

**Decision: approved** (2026-07-23, Tanuj Haria). Both halves are approved
because guided order creation requires them, and the requirement is structural
rather than a convenience:

* **Sales User `create` + `write`.** The whole point of an order-derived card is
  that the person taking the order raises it from the order, in the guided flow,
  against a snapshot they cannot edit. A Sales User who can read a Label card and
  not create one cannot complete the flow at all — the card would have to be
  raised for them by someone who was not in the conversation with the customer.
  The permission is what makes the guided path usable; without it the flow has no
  user.
* **Manufacturing Manager `amend`.** A cancelled card has to be re-raised by
  production, not by sales, and amending is how that is done without inventing a
  second unlinked card for the same order line.

The alternative — leaving Label read-only for Sales User while Carton is not —
means the two order-derived cards behave differently for the same role doing the
same job, which is the definition of incoherent.

The widening is bounded by three things that are not being relaxed with it: the
snapshot fields on a card are proved against what the order froze, so a Sales
User who can create a card still cannot make it disagree with the order; the
order reference is immutable once set; and **nothing here grants Sales User
`submit`** — raising a card and committing one remain separate acts, held by
separate roles.

---

## 9. Dormant cutover — the explicit sequence

Nothing below is done by this branch. Each step is deliberate, reversible up to
step 5, and gated on the one before it.

1. **Deploy.** `bench migrate` runs the four patches. Job Card Label gains the
   order-derived block; the 20 legacy references are stamped. Behaviour for
   every existing user is unchanged, because no Label line can be
   specification-controlled yet.
2. ~~Sign off the permission change (§8) or revert that hunk before deploying.~~
   **Done** — approved 2026-07-23; see §8. The hunk ships as written.
3. **Link the Label specifications.** 185 records need `linked_item`. Until a
   specification names an Item it serves nothing, so no Label line can pass V4
   regardless of anything else.
4. **Create and approve CPS Price rows.** Zero exist. Until a Label
   specification has an approved price effective on the order date, V7 refuses
   every controlled Label line on submit.
5. **Configure control.** Either set a Label Item Group's `custom_requires_cps`
   with `custom_cps_product_type = "Label"`, or set individual Items to
   `Require CPS` with the same product type. This is the step that makes Label
   lines controlled.
6. **Tick `Selling Settings.custom_cps_control_enabled`.** One checkbox; every
   rule in `so_spec_control` becomes live for every product type at once. It is
   already live for Computer Paper and Carton or it is not — this switch is not
   per-type.
7. **The Compass creation path.** Job Cards are raised from a Sales Order by
   `vcl_compass.api.jobcards.job_cards_from_sales_order`, which lives in the
   other repository and is out of scope for this branch. Until it learns to
   build a Label card — including `plate_status`, which is a required production
   input the order cannot supply — the Desk dialog correctly reports
   *"No Job Card type raises Label lines yet."* for a Label line. The registry
   in `public/js/sales_order_cps.js` is deliberately **not** extended here:
   offering a button that calls an API which cannot serve it is worse than the
   honest dormant message.

Steps 3–6 are the ones that turn the feature on. Step 7 is the one that makes it
usable, and it is somebody else's deploy.

---

## 10. Assumptions made explicit

* The 20 rows with `sales_order` are historical references to real orders, not
  test data. Nothing in this release depends on that being true — a stamped
  legacy row pointing at a deleted order still saves, because the legacy path
  never reads the order — but it is the assumption behind preserving them.
* The four `Data`-typed numerics will stay numeric. If a specification is ever
  saved with `"96 teeth"` in `cylinder_teeth`, the snapshot will freeze that
  string faithfully and the card will report it as a mismatch against its
  numeric field. That is the correct failure and it is loud.
* `Job Card Label.customer` is the customer link, matching Computer Paper and
  ETR. Carton is the outlier with `customer_name`, and that asymmetry stays
  carried as configuration rather than migrated away.
