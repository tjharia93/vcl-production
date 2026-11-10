# Computer Paper submission before management packing

Requested by Tanuj, 10 November 2026: sales reps must be able to submit a
Computer Paper CPS before management supplies sets per carton. The CRM form
must hide packing inputs, default the empty outer carton tare to 0.3 kg, and
derive size, parts and print defaults from the selected Item.

This change removes only sets-per-carton and tare from the CP submission
prerequisites. Finished dimensions and valid paper GSM remain required.
Derived carton weights remain unknown while packing is incomplete. Existing
submitted specs are not rewritten. The tare Custom Field fixture defaults
new documents to 0.3; it does not backfill stored zeroes.

Submitting still uses native document permissions and creates revision 1 in
Awaiting approval. It does not approve technical construction, artwork or
price. Gate settings, release checks and permissions are unchanged. Missing
packing remains release warning 7 under the existing policy; a mandatory
dispatch packing check is a separate, unfinished work item.

## Rollout

1. Review and merge this branch, then deploy `production_log` from main on
   Frappe Cloud. Run migrate to apply the fixture default. Pushing does not
   deploy the app.
2. On a permitted test customer, submit a complete CP draft with dimensions,
   paper/colours and numbering but no sets per carton. Verify the normal
   revision/approval transition, unknown carton weight, and packing warning.
   Also verify that missing dimensions or GSM still refuse submission.
3. Only after the deployed behavior is verified, enable `cpSubmitReady` in
   `~/projects/vcl_crm_v2/screens/sales_deal.js` and its helper source, build,
   regression-test, and surgically update the nine CRM Web Pages. This exposes
   the prepared native Submit CPS / Create and submit actions. They remain
   disabled in source (and hidden in the live UI) until then.

The CRM Item selector, automatic defaults, grouped dimensions, hidden packing
and empty error area, human CPS names and CPS-derived quotation descriptions
ship independently through Web Page updates. `Quotation Item.vcl_opportunity_item`
retains source-line identity after a CPS changes item/description. The field
is managed by the CRM's idempotent `setup_fields.py`. The live tare default
was updated through Customize Form metadata and is mirrored by this fixture.

Validation: plain unit tests cover CP submit/weight rules, revision lifecycle,
approval, snapshots, release checks and fixture integrity. The Frappe-dependent
`test_cps_control` requires a bench and is not a local unit-test check. Live
submission has not been exercised as part of this change; no customer CPS or
quotation was submitted/cancelled for testing.
