# One submitted order per CPS pending price approval

Tanuj confirmed on 10 November 2026: **one submitted Sales Order per CPS until
its price is approved**. The counter belongs to the CPS, not a price row or a
same-document revision. This change is prepared for review; it is not deployed.

## Resulting behaviour

- A selected CPS must still be Submitted, Active, and match the customer, Item
  and product type. Draft CPS and Draft CPS Price are different states.
- An eligible Approved price takes precedence, with existing currency, effective
  date, UOM, rounding allowance and explained-variance checks.
- With no eligible Approved row, an eligible Draft row can price the CPS's first
  submitted SO. No price row, a Rejected row, a future row or another currency
  does not qualify. The row remains Draft; approval authority is unchanged.
- Draft SO saves do not consume the allowance. Several lines for one CPS on one
  order share it. Another SO, including an amendment after cancellation, needs
  an eligible Approved price. Replacing a price row or revising the same CPS
  does not reset it. A newly amended CPS is a new CPS identity.
- The first submitted SO is recorded even if it used an Approved price. Migration
  backfills prior Submitted/Cancelled SO references so existing used CPSs do not
  gain a fresh allowance. Cancellation does not clear the reference.
- Existing Job Card generation remains a separate action from a submitted SO,
  with frozen line snapshots and remaining-quantity checks. No automatic cards,
  quantity bypass, price approval, release approval or Selling Settings change
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

The submit snapshot adds `_draft_price_first_order` (SO ID and price-row ID) as
an internal audit marker. This does not turn the reference price into Approved.

## Validation and deployment acceptance

Plain unit tests cover first/second orders, repeated lines, draft saves,
Approved-price precedence, missing/future/Rejected/foreign-currency rows,
price-row replacement, stale versions, claim protection, deterministic row
selection, current scoped price reads, migration idempotence and the schema
deployment window. DB doubles do not establish MariaDB transaction isolation.

Before enabling this on the live site, deploy/migrate on a bench and verify:

1. A Submitted/Active CPS with a valid Draft price allows exactly one submitted
   SO. Its price remains Draft and the SO's actual price stays unchanged.
2. Submit two different SOs for that CPS in two DB connections concurrently:
   exactly one commits; the other requires price approval. Repeat with multiple
   CPSs in opposite line order to check locking.
3. Force a later submit-hook failure. SO status and CPS claim both roll back;
   a subsequent valid submission can use the allowance.
4. Save an already-open stale CPS form after the SO commits; the claim survives.
   REST/Data Import must not clear or forge it. Cancel and amend an SO: the
   cancelled order still counts. Changing a same-CPS price row does not reset it.
5. Approve the eligible price through the normal authorised workflow. A second
   SO can then submit. Effective dates/currency/UOM and variance checks remain.
6. Explicitly generate Draft Computer Paper Job Cards from the first SO, with
   ordinary quantity/plate inputs. They bind its frozen snapshots and reject
   excess quantities. Verify release behaviour in the configured gate mode;
   do not change the live mode as part of this patch.
7. Run migration twice on seeded historical orders. The earliest submitted or
   cancelled SO is backfilled once; existing claims and commercial data remain.

Do not use production business documents as disposable test records.
