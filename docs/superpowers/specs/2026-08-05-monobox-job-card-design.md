# Monobox Job Card & Production Tracking — Design

**Date:** 2026-08-05
**Status:** Design agreed, pending implementation plan
**Author:** Claude (with Tanuj)

## Problem

VCL makes custom-printed monoboxes with a window. No job card is raised for them and no
production tracking exists. They are the only product line running off-system:

- `Customer Product Specification.product_type` offers Computer Paper, Carton, Label,
  Exercise Books, ETR — no Monobox.
- `job_card_tracking` has four job card doctypes (Carton, Computer Paper, ETR, Label) —
  no Monobox.
- Job Card Carton cannot absorb it: its stage list is corrugated-specific (Corrugated →
  Pasting → Creasing/Slitting → Printing → Slotting → Stitching → Bundling) and its spec
  fields (flute type, ply count, liner materials) are meaningless for a monobox.

Consequence: no route is recorded, no waste or yield is captured, output cannot be tied to
an order, and film consumption is estimated rather than known.

## Decision summary

| # | Decision | Choice |
|---|---|---|
| 1 | Where monobox sits | Its own product line — new CPS type, new job card doctype, new traveller |
| 2 | In-house stages | All four groups run in-house, selected per job |
| 3 | Who decides the route | The CPS; the job card inherits and may override |
| 4 | Data capture | Paper traveller + a close-out block keyed back into ERPNext |
| 5 | Window specification | Explicit geometry on the CPS, backed by a new die register |
| 6 | Board description | Grade and GSM free text for iteration one, tightened later |
| 7 | Dimensions | L × W × H in mm; flat blank typed in, not derived |
| 8 | Close-out scope | Output vs order, board consumed, film consumed, time & labour per stage |
| 9 | Sales Order link | Optional and encouraged, not enforced |
| 10 | Die register | New `Monobox Die` doctype, planning geometry + physical asset |
| 11 | Board issue unit | Sheets |
| 12 | Film issue unit | Kg |

## Scope

Five artefacts, all inside the existing `production_log` app, `job_card_tracking` module.

| Artefact | Type | Detail |
|---|---|---|
| CPS extension | Change | `product_type` gains **Monobox**, naming series `MBX-SPEC-.#####`, Monobox-only field section |
| `Monobox Die` | New doctype | `MBX-DIE-.#####` — die register, planning geometry + asset tracking |
| `Job Card Monobox` | New doctype | `JC-MBX-.YYYY.-.####.`, submittable, mirrors Job Card Carton |
| `Monobox Stage Summary` | New child doctype | One row per applicable stage on the job card close-out |
| `Monobox Job Traveller` | New print format | App-managed: in-repo HTML + `print_format.json` fixture + `hooks.py` filter |

Explicitly **out of scope** for iteration one:

- Digital/QR floor capture. Paper first; the form must settle on the floor before capture
  is built on top of it.
- Any change to the existing `Dies` doctype. It remains the flexo label register.
- A derived blank/window layout drawing. The blank size is typed in, so a drawing would be
  decorative rather than load-bearing.
- Board grade/GSM as constrained Selects. Deliberately free text until we see what is
  actually typed.

## Route model

Six stage blocks:

1. Board Prep & Printing
2. Coating
3. Die-cutting & Stripping
4. Window Patching
5. Folding & Gluing
6. Bundling & Packing

The CPS carries an applies-flag per stage. The job card inherits the flags and leaves them
editable, so a genuine one-off (skip lamination on a rush job) does not require a CPS
revision — which under VCL convention would be a revise-in-place, not an amend.

The traveller prints applicable stages normally and prints non-applicable stages **struck
through**, never omitted. The floor must be able to see that a stage was consciously
excluded rather than forgotten. This matches how Printing is struck through on a plain
carton job.

## Component 1 — CPS Monobox extension

`product_type` gains `Monobox`; `naming_series` gains `MBX-SPEC-.#####`. All new fields sit
in a Monobox section gated on `product_type == "Monobox"`, following the existing
depends-on pattern used by the Carton, Label and ETR sections.

**Board**

| Field | Type | Notes |
|---|---|---|
| `board_grade` | Data | Free text for iteration one |
| `board_gsm` | Int | Free number for iteration one |
| `print_side` | Select | White side / Grey side |

Stocked board today is Chipboard (Duplex Board), reels and sheets, stock UOM Kg, at
180 / 220 / 230 / 290 GSM, sheet sizes 610×860 and 914×1220. No SBS, FBB or art card items
exist. Iteration two converts grade and GSM to Selects once real usage is visible.

**Dimensions — all mm**

`length`, `width`, `height`, `tuck_flap`, `glue_flap`, `dust_flap`, `blank_length`,
`blank_width`.

Blank dimensions are typed in, not derived. Where a die is linked, they default from the
die (see Component 2).

**Window**

| Field | Type | Notes |
|---|---|---|
| `has_window` | Check | Gates the whole window group and close-out block C |
| `window_width` / `window_height` | Int (mm) | |
| `window_panel` | Select | Front / Back / Top / Side / Other |
| `window_offset_bottom` / `window_offset_left` | Int (mm) | From the panel edges |
| `film_material` | Data | Free text for iteration one |
| `film_micron` | Float | |
| `film_patch_width` / `film_patch_height` | Int (mm) | |

**Die**

`cutting_die` — Link to `Monobox Die`. Not free text, and not a link to `Dies`.

**Print** — reuses existing CPS fields: `printing_or_plain`, `ink_type`, the CMYK colour
checks, `number_of_colours`, the `Spot Colour` child table, `colour_notes`.

**Coating** — `coating_type`: None / Gloss Lamination / Matt Lamination / UV Varnish /
Aqueous Varnish. Coating is used infrequently, so a short Select is adequate.

**Route flags** — `applies_printing`, `applies_coating`, `applies_diecut`,
`applies_window_patch`, `applies_gluing`, `applies_bundling`.

**Packing** — boxes per bundle, bundles per carton, packing notes.

## Component 2 — `Monobox Die`

New doctype, naming `MBX-DIE-.#####`. Serves two purposes: it fixes the geometry the job
must run to, and it tracks the physical tool.

**Planning geometry**

| Field | Type | Notes |
|---|---|---|
| `blank_length` / `blank_width` | Int (mm) | The flat blank the die cuts |
| `ups_per_sheet` | Int | Blanks per sheet |
| `sheet_size` | Select | 610×860 / 914×1220 / Other |
| `sheet_length` / `sheet_width` | Int (mm) | Populated when sheet size is Other |
| `has_window` | Check | |
| `window_width` / `window_height` | Int (mm) | Aperture |
| `window_offset_bottom` / `window_offset_left` | Int (mm) | |

The CPS links the die and defaults blank size, ups and sheet size from it, so those values
stop being retyped per job and cannot silently disagree with the tool.

**Asset**

`die_number`, `customer` (Link), `maker` / supplier, `date_made`, `cost`,
`storage_location`, `condition` (Active / Worn / Retired / Lost), `notes`.

The existing `Dies` doctype (`DIE-.#####`, with `across_ups` / `round_ups` / `teeth` and PP
materials) is a flexo label die register and is left entirely untouched.

## Component 3 — `Job Card Monobox`

Submittable, naming `JC-MBX-.YYYY.-.####.`, structured to mirror Job Card Carton so the
form is familiar to both the floor and the office.

**Header** — `date_created`, `due_date`, `status` (Draft / In Progress / Completed /
Cancelled), `customer_name` (Link Customer), `customer_product_spec` (Link CPS),
`specification_name`, `job_description`, `quantity_ordered`, `repeat` (Old / New).

**Sales Order** — `sales_order` Link, optional, with `so_qty` fetched. Every consumer of it
is `{% if %}`-guarded and degrades to a blank write-in box on the printed form. On the CP
traveller only 1 of 61 cards carried a Sales Order, which is exactly why its close-out
numbers cannot be tied to an order; the field is therefore prominent and encouraged, but
not enforced.

**Spec carry-down** — board, dimensions, window, film, die, colours, coating and the six
route flags copy from the CPS via `fetch_from` and remain editable on the card.

**Production** — `machine` (Link Workstation), `job_status` (Open / Planned / In Production
/ Packing Pending / Completed / Closed / On Hold / Cancelled).

## Component 4 — Close-out capture

Four blocks on the job card, keyed in from the returned paper traveller. This is what
answers the original complaint.

**A · Output vs order**

Ordered (auto from the Sales Order where present, else typed), boxes produced, boxes
delivered, boxes invoiced, and the computed difference. Same shape as the CP traveller's
page-2 close-out.

**B · Board consumed vs planned**

Planned sheets, sheets issued, sheets used, sheets returned to store, waste sheets, and
computed yield %. **Sheets only** — stock UOM is Kg but the floor counts sheets, and the
conversion is not written down anywhere. Weight is derivable later from GSM × blank area if
it is ever needed.

**C · Window film**

Film type, issued kg, used kg, returned kg, computed consumption. **Kg**, matching how film
is issued. The whole block is hidden when `has_window` is off.

**D · Time & labour per stage**

Child table `Monobox Stage Summary`, one row per applicable stage: stage, machine, total
hours, operator names, output, waste. Summary level only — the per-run detail stays on
paper in iteration one.

## Component 5 — `Monobox Job Traveller` print format

Four pages, A4 portrait.

1. **Front sheet** — commercial & order block, product spec, window spec, a route strip
   showing which stages this job runs, and enlarged hand-fill boxes for actual output.
2. **Material Release** — board and film issue/return, signed.
3. **Stage blocks** — the six blocks. Each captures Start / Finish / Operator / Output /
   Waste. Non-applicable stages print struck through.
4. **Close-out + QC critical checkpoints** — mirrors the A-to-D layout above so keying in
   is a straight transcription rather than an interpretation.

**Build constraints**, all learned the hard way on the Carton and CP travellers:

- 6-digit hex only. 8-digit `#RRGGBBAA` renders in Chrome and silently vanishes in
  wkhtmltopdf, taking every fill with it. Pre-blend against white.
- Named `@page` rules do nothing in wkhtmltopdf. Landscape pages are not achievable that
  way.
- Pagination must be deterministic Jinja against a measured mm budget, not CSS
  page-breaks, which are unreliable in wkhtmltopdf.
- Page numbers must be computed from a namespace counter, never hardcoded, because page
  count is data-dependent (route flags change how many stage blocks print).
- Watch for the trailing blank sheet and for the signature strip orphaning when anything is
  added to the front sheet.
- `table-layout: fixed` on any row holding SVGs.

**Verification** — render real PDFs and check page count *and* per-page ink (rasterise and
count dark pixels). A page can be present and blank. A pagination regression check
comparable to `check_cp_traveller_pagination.py` must pass before the format is called
done, covering the route-flag combinations that change page count.

## Deployment

Follows the `vcl-frappe-app` contract: doctypes and the print format live in the app, the
print format is exported to `fixtures/print_format.json` with a `hooks.py` filter, and a
patch handles the CPS `product_type` / `naming_series` option additions.

Note the known trap: installing an app stamps its patches as run without running them, so
any patch that must touch data outside the app needs verifying after migrate, not assuming.

UAT and OAT run as a new numbered round in the same turn as the push.

## Risks and open items

| Risk | Mitigation |
|---|---|
| Board grade/GSM free text drifts into unusable variants | Reviewed at iteration two and converted to Selects from observed values |
| Sales Order left blank, repeating the CP problem | Field is prominent; close-out block A degrades to typed ordered-qty rather than breaking |
| Route flags produce a page count the pagination model did not anticipate | Regression check must cover the flag combinations, not just one happy path |
| Floor does not in fact count board in sheets | Confirm with the shop before build; block B is sheets-only and would come back empty otherwise |

## Iteration two (not now)

- Board grade and GSM as constrained Selects.
- Film material as a Select or Item link.
- Derived blank size and ups from dimensions, with a printed blank/window layout drawing.
- Digital capture — QR-driven per-stage entry feeding a runs child table, replacing the
  keyed-in summary.
