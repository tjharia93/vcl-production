# First-order Draft CPS, proposed price and combined approval

Tanuj clarified on 10 November 2026: **one submitted Sales Order per CPS even
when the CPS itself is Draft**. If pricing is empty, that SO supplies its net
rate as a Draft CPS Price. Approval email opens the whole specification, with
one authenticated action to approve the CPS and its price together. Management
enters packing manually from the first run. This supersedes the earlier
Draft-price-only interpretation. This change is not deployed yet.

## Resulting behaviour

- A selected CPS must be Active and match the customer, Item and product type.
  The first order may use a Draft CPS and Draft price. Draft order saves do not
  submit or approve the CPS, create prices, queue email, or consume the allowance.
- An eligible Approved price takes precedence, with existing currency, effective
  date, UOM, rounding allowance and explained-variance checks.
- When the price table is empty, the first SO submit proposes its actual rate,
  currency, UOM, conversion factor and date as a Draft row, source Sales Order.
  It does not approve the price or change the order rate. An existing Draft row
  can be used; existing Approved/Draft/Rejected/future/foreign-currency rows are
  never silently overwritten. Unusable existing prices require explicit review.
- Draft SO saves do not consume the allowance. Several lines for one CPS on one
  order share it. Another SO, including an amendment after cancellation, needs
  a Submitted, technically approved CPS and an eligible Approved price.
  Replacing a price row or revising the same CPS
  does not reset it. A newly amended CPS is a new CPS identity.
- The first submitted SO is recorded even if it used an Approved price. Migration
  backfills prior Submitted/Cancelled SO references so existing used CPSs do not
  gain a fresh allowance. Cancellation does not clear the reference.
- Existing Job Card generation remains a separate action from a submitted SO,
  with frozen line snapshots and remaining-quantity checks. No automatic cards,
  quantity bypass, automatic approval, release approval or Selling Settings change
  is introduced. When the release gate is Enforce, its Approved-price checks
  still apply; generating a Draft card does not grant release.
- The screen-only CRM CPS price memo is independent. Its data is not added to
  quotation/order fields, descriptions, snapshots or printouts. The SO's own
  rate is not overwritten by the reference price.

## Transaction and schema

`first_submitted_sales_order` is a hidden, read-only, no-copy, print-hidden CPS
Data field, written only by the server. CPS save/update-after-submit/cancel
restores its current stored value, protecting against stale or forged input.

SO validation locks unique CPS rows in sorted order and reads price rows with
current `FOR UPDATE` reads. It rejects a stale technical-spec version. It does
not lock another SO after taking a CPS lock, avoiding inversion of Release's
SO-to-CPS lock order. `on_submit` records the claim in the same transaction;
there is no intermediate commit. Failed submissions roll back with the SO.
Before migration adds the field, the existing Approved-only rule remains.

The submit snapshot adds `_first_order_exception` (SO, CPS document status and
price-row approval state). This does not turn the reference price into Approved.
The missing-price proposal and first-use claim share the SO transaction.

Approval requests are queued at SO submit, once per CPS/order, only to enabled
users authorised by both existing approval rules and document permissions.
Tanuj's enabled account and existing VCL Management Team role were verified.
Opening `/sales-crm-v2/approve-cps` or fetching review data cannot approve.
Approval is an authenticated, CSRF-checked POST, with server-side permission and
both rule checks, a current version check, normal CPS submission/validation,
technical approval and price approval in one transaction. A mail scanner/guest
cannot approve. Failed email routing is reported and logged, never treated as
approval. No real email was sent while testing.

The review shows the whole visible CPS, changes since the order snapshot and
proposed/actual order prices. Only management sees packing; optional sets per
carton/tare inputs use measured first-run values. Blank packing stays unknown,
and mandatory dispatch packing remains separate unfinished work. Approving a
Draft CPS creates revision 1; cards generated before that may require the
existing authorised Release binding refresh when gate enforcement is enabled.

## Validation and deployment acceptance

Plain unit tests cover first/second orders, repeated lines, draft saves,
Approved-price precedence, missing/future/Rejected/foreign-currency rows,
price-row replacement, stale versions, claim protection, deterministic row
selection, current scoped price reads, migration idempotence and the schema
deployment window. DB doubles do not establish MariaDB transaction isolation.

Before enabling this on the live site, deploy/migrate on a bench and verify:

1. A Draft/Active CPS with an empty price table allows a Draft SO save without
   mutation, then exactly one SO submission. It creates one Draft CPS Price from
   the SO's actual net rate and queues one request. CPS remains Draft; no packing
   or approval is invented. A second order needs CPS and price approval.
2. Submit two different SOs for that CPS in two DB connections concurrently:
   exactly one commits; the other requires price approval. Repeat with multiple
   CPSs in opposite line order to check locking.
3. Force a later submit-hook failure. SO status and CPS claim both roll back;
   a subsequent valid submission can use the allowance.
4. Save an already-open stale CPS form after the SO commits; the claim survives.
   REST/Data Import must not clear or forge it. Cancel and amend an SO: the
   cancelled order still counts. Changing a same-CPS price row does not reset it.
5. Open the email link signed in as Tanuj; review the whole CPS and any changes.
   One button submits/technically approves the CPS and approves the price. A
   second SO can then submit. Stale data, denied authority, cancelled order/CPS
   or a rejected price fails before approval. Force a price-approval failure and
   verify the preceding technical approval/submission also rolls back. Verify
   email configuration, recipient filtering, delivery and the login return URL.
6. Explicitly generate Draft Computer Paper Job Cards from the first SO, with
   ordinary quantity/plate inputs. They bind its frozen snapshots and reject
   excess quantities. Verify release behaviour in the configured gate mode;
   do not change the live mode as part of this patch.
7. Run migration twice on seeded historical orders. The earliest submitted or
   cancelled SO is backfilled once; existing claims and commercial data remain.

Do not use production business documents as disposable test records.

UI regression (mock requests only):
`node scripts/test_cps_first_order_approval_ui.cjs [playwright-module-path] [screenshot-directory]`.
Passes at 1440/390px: read-only GET, one approval POST, management packing,
stale/error handling, escaped data and no horizontal overflow. Shared-host
source upload was denied; the tests ran locally instead, without uploading code.
