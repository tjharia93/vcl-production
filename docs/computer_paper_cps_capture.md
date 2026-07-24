# Computer Paper CPS capture — Numbering, colour, parts and artwork

Branch `agent/computer-paper-cps-ux`. Companion to `carton_cps_discovery.md` and
`label_cps_discovery.md`; everything those established about the shared
architecture is assumed here rather than restated.

This release exists because four things on a Computer Paper specification are
easy to skip and expensive to get wrong, and the live data shows all four being
skipped.

---

## 0. The live position this was written against

Read from the live site before any code was written:

| Fact | Value |
|---|---|
| Computer Paper CPS records | **59** |
| Submitted (`docstatus 1`) | 46 |
| Cancelled (`docstatus 2`) | 10 |
| Draft (`docstatus 0`) | 3 |
| `print_type = "Printed"` | 50 |
| `print_type = "Plain"` | 9 |
| Printed records with **no** CMYK tick and **no** spot row | **21** |
| Plain records that **do** carry ink data | **9** (all of them) |
| Records with a `linked_item` | 7 |

Two shapes therefore exist in production that the new rules would refuse if they
were applied retrospectively: *Printed with no ink*, and *Plain with ink*. Both
must keep saving for reasons that have nothing to do with colour, or this
release becomes a data-cleanup project nobody asked for.

---

## 1. What changed, and where

### vcl-production (the authority)

| File | What |
|---|---|
| `job_card_tracking/cps_cp_rules.py` | New. Frappe-free transition rules for Numbering, print colour, print side, parts and artwork. |
| `job_card_tracking/test_cps_cp_rules.py` | New. Unit tests for all of the above, including both legacy shapes. |
| `.../customer_product_specification.py` | `validate_computer_paper_capture()` and `before_submit()` wired in; `before_submit` also proves the stored artwork File via `validate_artwork_integrity()`. |
| `patches/v8_3/add_cps_numbering_artwork_fields.py` | New. Four additive Custom Fields. |
| `patches.txt` | The patch registered under `[post_model_sync]`. |
| `fixtures/custom_field.json` | The same four fields exported, so a site rebuilt from this app reproduces them. |

### vcl-compass (the screen)

| File | What |
|---|---|
| `api/cps_core.py` | New. The payload allowlist (Compass's own authority) plus mirrors of the rules above. |
| `api/cps.py` | New. The narrow whitelisted API: options, search, list, get, save, preview, submit, artwork upload/remove. |
| `api/test_cps_core.py` | New. Allowlist and mirror tests. |
| `frontend/src/computerpaper/*` | New. `cpsForm.ts` (pure), `blocks.tsx` (one block per question), `cpsCss.ts`, `ComputerPaperSpec.tsx`. |
| `frontend/tests/cpsForm.test.ts` | New. |
| `App.tsx`, `shell/Sidebar.tsx` | Route `/computer-paper-spec` and its nav entry, both gated on the existing `cps` module. |
| `api/jobcards.py`, `dashboards/JobCardCreate.tsx` | The generic `/cps` screen now points Computer Paper users at the new one. |

`/specs` and the `VCL Product Spec` doctype are untouched.

**The specification library is customer-scoped in the screen, not just on the
server.** `ComputerPaperSpec` makes no `list_specs` call at all until a customer
is chosen: with none chosen the list is cleared and the fetch returns. The
server would happily return every Computer Paper specification the user may read
— for an unrestricted manager that is all of them, one customer's product range
legible to somebody who opened the screen to work on another's — so the boundary
is drawn where the customer is, before the request is made rather than after the
rows come back.

---

## 2. Numbering — why a second field

`numbering_required` is a `Check`. A Check has two states, so an unticked box has
always meant "No" and "nobody was asked" at the same time, and there is no way to
tell the 59 existing records apart retrospectively.

So the business field keeps its meaning exactly — production, the Job Card and
the frozen order snapshot all still read it, and nothing about what it means has
changed. Beside it sits an additive `numbering_confirmed` Check that records only
that a person actually gave the answer. Nothing downstream reads it, no snapshot
freezes it and no Job Card is shaped by it.

The rule is a transition rule:

* a **new** Computer Paper record must carry the confirmation;
* an **existing** one must carry it only when the answer is being *changed*;
* a confirmation, once given, cannot be withdrawn.

Everything else — the whole legacy estate saving for unrelated reasons — passes.

`numbering_confirmed` is hidden on the Desk layout. It is provenance, not an
input, and a Desk user who ticks it by hand without answering the question beside
it has recorded a confirmation that never happened. Compass sets it from the
explicit Yes/No control and cannot be talked into setting it any other way: it is
absent from `cps_core.WRITABLE_FIELDS`, and the payload carries a
`numbering_choice` of `"yes"` or `"no"` from which the server derives both flags.

`numbering_notes` is a Small Text shown when the answer is Yes. **Start and end
ranges are job-specific and are entered on the Job Card, not here** — said once,
in `cps_cp_rules.NUMBERING_RANGE_NOTICE`, and served to the Desk description, the
Compass hint and the API options from that one string.

---

## 3. Colour — two things that are not the same thing

"Print colours (ink)" and "Colour of parts (pre-tinted paper)" have been one
undifferentiated block on the form and have been filled in as if they were the
same question. They are now two panels with two headings and an explicit note in
each: a three-part white / pink / blue set printed in black is **one** colour, not
four.

The consistency rules:

* a **Printed** specification must record at least one CMYK process ink or one
  spot colour row;
* a **Plain** specification must not carry print inks at all;
* `number_of_colours` stays derived and read-only — ticked inks plus spot rows;
* a Plain specification's `print_side` must be `N/A` or blank.

All four are transition rules on the same trigger: they bind a new record always,
and an existing record only when somebody has deliberately moved `print_type` or
one of the four ink Checks, or edited the spot colour grid.

`colour_notes` and `ink_type` are deliberately **not** in the trigger set. Neither
states which inks the job runs — one is free text and the other is which ink
*system* is used — and including them would mean that correcting a typo in a note
on one of the nine Plain records carrying legacy ink data refuses the save. That
is precisely the failure this release is written to avoid.

Spot colour rows write the actual child-table fields: `pantone_code`,
`pantone_name`, `hex_preview`, `cmyk_c/m/y/k`, `notes`. A row with neither a
Pantone code nor a name is refused, because it counts as a plate in
`number_of_colours` and would price and plan a colour nobody will ever print.

---

## 4. Parts — defaults, not new restrictions

The controller has always enforced paper type and GSM per position, and nothing
here loosens or tightens it:

| Position | Accepted |
|---|---|
| single part | 60 GSM Bond (60), CB (55), 70 GSM Bond (70) |
| first of many | CB (55) |
| middle | CFB (50) |
| last | CF (55) |

What is added is the **defaults**: `part_positions` / `default_parts` generate
exactly one row per part in the CB / CFB… / CF sequence with those GSMs, a
conventional colour per position and a plain-language `purpose` per ply. Changing
the part count keeps the colours and purposes somebody already chose, position by
position, and re-types only the plies whose position actually moved — the third
ply of a three-part set is CF, and the third ply of a four-part set is CFB.

Row colour remains required. Grid problems are reported as a **list** rather than
one at a time, so a five-part set is corrected in one pass rather than five.

---

## 5. Artwork

Two new Custom Fields: `artwork` (Attach) and `artwork_notes` (Small Text). The
panel is always visible, whether or not the job needs artwork — hiding it for a
Plain job would leave an operator with no way to see that there is none, which is
the one question they need answered before the job runs.

* A **Printed** specification may be saved as a draft without artwork but cannot
  be **submitted** without it (`before_submit`).
* A **Plain** specification does not need artwork at all.

The security properties, and where each lives:

| Property | Where |
|---|---|
| Private uploads only | `cps.upload_artwork` sets `is_private: 1` unconditionally — no parameter, no branch. |
| Server-side permission check | `_load(name, "write")` → `doc.check_permission` + CSRA scope. |
| Document ownership binding | The File is created with `attached_to_doctype`/`attached_to_name`, then **re-read and re-proved** by `_binding_problem`. |
| Extension allowlist + size cap | `cps_core.artwork_upload_problem`, checked before any byte is stored. 25 MB. |
| Bounded read on the upload | `upload.stream.read(ARTWORK_MAX_BYTES + 1)`, not an unbounded `read()`: a request the cap will refuse anyway cannot allocate its whole self in the worker first. The extension is checked *before* the read, so a disallowed kind pulls no bytes at all. |
| Another document's File URL rejected | Structural: `artwork` is absent from `WRITABLE_FIELDS`, so no endpoint takes a URL at all. `_binding_problem` is the belt to that braces. |
| Remove deletes only a correctly bound orphan | `_delete_if_orphan` — right document, private, and nothing else referencing the URL. |

`frappe.handler.upload_file` is deliberately **not** used: it writes the target
field itself for anyone with write permission on the document, which would make
the allowlist, the cap and the private-only rule advisory rather than enforced.

No credentials and no public URLs are ever returned. The screen is handed the
private `/private/files/...` path, which Frappe re-checks permission on for every
request.

**The upload endpoint is only one of the routes to the `artwork` field.** It is an
Attach — a Data field holding a path — so Desk's own attach control, a REST
write, a Data Import and an amendment can all set it, and none of them has ever
been past the allowlist, the cap or the private-only rule. So the integrity
check is repeated at the one moment it matters for every route at once:
`CustomerProductSpecification.before_submit` → `validate_artwork_integrity()`
resolves the File row from the stored URL (`cps_cp_rules.artwork_file_error`) and
asks it every question again — exists, private, bound to *this* CPS, an allowed
kind, size `> 0` and `<= 25 MB`. A well-formed path that names no File, or
another document's File, is refused there even though the string itself is
valid: a URL is not evidence of anything. Because this is `before_submit`, it
fires once on the draft→submitted transition and never touches the records that
were already submitted before this release.

`.svg` was **removed** from the allowlist in all three copies of it
(`cps_cp_rules.ARTWORK_EXTENSIONS`, `cps_core.ARTWORK_EXTENSIONS`,
`cpsForm.ts`). An SVG is XML, not an image: a browser handed one from the site's
own origin parses its `<script>` and its external references, and artwork is
served back to signed-in staff on that origin. No VCL customer has ever sent
press artwork as one. The accepted kinds are PDF, AI, EPS, PNG, JPG/JPEG and
TIF/TIFF.

---

## 6. Deliberately NOT in this change — the snapshot contract

**Artwork is not added to the Sales Order specification snapshot, and therefore
not to any Job Card.**

`cps_rules.build_spec_snapshot` freezes a versioned payload onto
`Sales Order Item.custom_spec_snapshot` at submit. That payload is read across a
repository boundary — vcl-compass reads it, and deploys on its own schedule — and
its version number is part of the contract (see `SNAPSHOT_BASE_WRITE_VERSION` and
`snapshot_write_version`). Adding a key to it is a *widening*, which is safe, but
adding one that consumers are then expected to act on is a contract change, and
it needs its own discovery:

* what an artwork reference frozen at order time even means when the file behind
  it can be replaced, moved or deleted afterwards;
* whether the Job Card should carry the URL, a copy of the File, or nothing;
* whether `jc_snapshot_mismatches` should *prove* the card's artwork against the
  order's, as it proves every other technical value — and what a mismatch means
  when the only honest answer is "the artwork was revised";
* the version bump, and what a Compass release that predates it does with it.

None of that is answerable from this release's evidence, so it is a follow-up.
Until it lands, artwork lives on the specification and is read live from there.

---

## 7. Also deliberately not done

* **No retroactive block on legacy records.** Every rule above is a transition
  rule. The 21 inkless Printed records and the 9 inked Plain records keep saving
  for any reason that is not about their colour.
* **No backfill of `numbering_confirmed`.** Every existing record legitimately
  has it unset, because nobody confirmed anything on it. Writing 1 across the
  estate would destroy the one fact the field exists to record.
* **No pricing from Compass.** The screen reads the current rate and the number
  of approved price rows and writes neither. Creating or approving a CPS Price
  row remains a Desk action for an authorised pricing approver, and `pricing`,
  `current_rate` and `current_uom` are absent from the payload allowlist. (The
  screen's own copy says the same, role-neutral, thing: a new rate is approved
  "by an authorised pricing approver in Desk".)
* **No widening to other product types.** Numbering, colour, parts and artwork
  all mean something on a Carton and a Label too, but they mean *different*
  things — a box has no parts, a label's artwork is partly its die — and each is
  a separate decision with its own discovery. Every rule in `cps_cp_rules` is
  gated on `product_type == "Computer Paper"`.
* **Generic `/cps` kept for other types.** It now refuses Computer Paper with a
  message naming the screen that can do the job. In practice it has never been
  able to create one — the parts rule has refused it since before that endpoint
  existed — so what changes is the quality of the refusal, not the capability.

---

## 8. Cutover

Nothing here is gated behind a feature flag, and nothing needs one:

1. `bench migrate` runs `v8_3.add_cps_numbering_artwork_fields` and syncs the
   fixture. Four columns appear; no row changes.
2. From that moment, a **new** Computer Paper specification must answer Numbering
   and be colour-consistent, and a **Printed** one needs artwork to submit.
3. Existing records are unaffected until somebody deliberately changes the thing
   a rule is about.
4. The Compass screen appears under **Catalogue → Computer Paper Spec** for
   everyone who already holds the `cps` module.

---

## 9. Carton weight — two numbers, both calculated

A Computer Paper carton has two weights that get quoted, planned and shipped
against, and until this release both were the one free-text
`standard_weight_per_carton` box, which meant whichever a person meant when they
typed it:

* the **net product weight** of the paper in the carton, and
* the **gross packed weight** including the outer packing carton it ships in.

Both are derivable from things the specification already records, so they are
**derived server-side** rather than trusted from an input Desk or an API caller
can set to anything.

### The fields

| Field | Kind | Meaning |
|---|---|---|
| `finished_width_mm`, `finished_length_mm` | input, Float | The finished set, in mm. Their own fields — never parsed from `job_size`. |
| `sets_per_carton` | input, Int | Sets in one carton. |
| `packing_carton_tare_kg` | input, Float | The empty outer carton. The whole of gross − net. |
| `print_weight_allowance_pct` | input, Float, **Printed only** | Optional. A labelled *allowance* on the paper weight — not an ink weight. |
| `cp_total_gsm` | derived, read-only | Sum of every ply's GSM. |
| `paper_weight_per_set_g` | derived, read-only | One set as it ships (with the allowance, if Printed). |
| `net_product_weight_per_carton_kg` | derived, read-only | The paper only. |
| `gross_packed_weight_per_carton_kg` | derived, read-only | Net + carton tare. |

### The formula (`cps_cp_weight`, Frappe-free)

```
area_m2       = width_mm × length_mm / 1_000_000
total_gsm     = Σ gsm of every colour_of_parts row        # 3-part 55/50/55 = 160
substrate_g   = area_m2 × total_gsm                        # the Plain weight
per_set_g     = substrate_g × (1 + allowance_pct/100)      # Printed
              = substrate_g                                # Plain (allowance ignored)
net_kg        = per_set_g × sets_per_carton / 1000
gross_kg      = net_kg + packing_carton_tare_kg
```

Ink weight is **not** modelled as a fact. The printing allowance is labelled as
an allowance everywhere it appears, is Printed-only, and defaults to no uplift.

### Storage — the narrowest compatible carrier

The gross is **also** written into the existing `standard_weight_per_carton`.
That field is a version-1 snapshot scalar (`cps_rules.SNAPSHOT_V1_SCALARS`) that
already freezes onto every Sales Order line and already maps onto the Job Card as
`weight_per_carton` — in production's `*_SNAPSHOT_JC_MAP` and in Compass's
`jobcards_core.SNAPSHOT_SCALAR_MAP`. So the shipping weight reaches the order
snapshot and the shop floor with **no snapshot version bump and no mapping
change**. `gross_packed_weight_per_carton_kg` is the labelled, user-facing copy;
`standard_weight_per_carton` is the plumbing. They are set together, in one
place (`apply_computer_paper_weights`), and cannot drift.

The structured inputs and the extra derived fields are **not** added to the
snapshot — the same call made for artwork in §6. Adding a key a cross-repository
consumer must act on is a contract change; the gross is already carried, and a
Computer Paper snapshot stays version 2. `test_cps_cp_weight.TestFrozenSnapshotMapping`
asserts this and that a historical snapshot keeps its own frozen value.

### Legacy, drafts and submission

* **Save** recomputes the derived fields from whatever is present and mirrors the
  gross into `standard_weight_per_carton` *only when the inputs are complete*. A
  legacy record with no structured inputs computes no gross, so its hand-typed
  weight is left exactly where it is — the recompute never blanks a legacy value.
* A **present** input that is zero, negative or a fractional set count is refused
  on any save (it is impossible, not incomplete); a **blank** input is fine on a
  draft.
* **Submit** requires the complete inputs, on the same terms as artwork: the 46
  already-submitted records never re-run the check and are frozen; a record
  submitted now is going to production now and needs a real weight.

### The old manual boxes

`standard_weight_per_carton`'s manual input is **removed from the Compass
screen** — it is the derived gross now, shown read-only, so the "is this the
typed number or the calculated one?" confusion is gone.

Two **pre-existing** hand-created CPS fields overlap semantically and are left
**untouched by this release**: `printed_weight` (kg, "Auto: sets × sheet area ×
ΣGSM") and `empty_carton_weight` (g). They were captured into the fixture by
commit `c003cec` to close fixture drift, are wired to no code or print format,
use inconsistent units (g vs kg) and are not read-only — an abandoned manual
sketch of this calculation. Retiring or repurposing them touches the separate
board-plan work and their live data, so it is **a follow-up for explicit
sign-off**, not folded in here silently. Recommended follow-up: hide/relabel both
as legacy once confirmed, since the calculated fields supersede them.

### Cutover (weight)

`v8_3.add_cp_weight_fields` adds eleven additive Custom Fields (a section, a
column break, five inputs, four read-only results); no row changes. From migrate,
a new Computer Paper specification calculates its weights and needs the inputs to
submit; existing records are untouched until their inputs are entered.
