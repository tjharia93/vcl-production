# Transitional artefacts

Things that exist as **records in the live database** rather than as code, because
they had to work before the next Frappe Cloud deploy. Each one is superseded by
app code in the same migrate that retires it.

Nothing in this directory is imported. It sits outside the `production_log`
package deliberately — `cps_revise.server_script.py` is a Server Script body, not
a module, and executing it on import would blow up on `frappe.form_dict`.

It is here because a Server Script lives only in the database, and the database is
exactly where things go to be forgotten: 17 CPS Custom Fields once existed nowhere
but the site, and rebuilding from this app would not have reproduced them.

| File | Live record | Superseded by | Retired by |
|---|---|---|---|
| `cps_revise.server_script.py` | Server Script `CPS Revise (in-place, versioned)` | `production_log.job_card_tracking.cps_revise.revise` | patch `v9_7` |

## cps_revise.server_script.py

Pushed live 2026-08-15 so the Revise button could fill in the Board Plan of the 26
carton specifications submitted before those fields existed, without waiting on a
deploy.

Its carton geometry is **inlined** — `safe_exec` forbids imports, which is the
whole reason the logic moved into `cps_carton_board.py` for the app version. While
both exist they must agree; the app copy is the one with the 31 unit tests, and
this one was checked against it on 12 cases plus three live records
(`CPT-SPEC-00064`, `CTN-SPEC-00023`, `CTN-SPEC-00024` all recomputed to exactly
their stored values) before it went live.

The live Client Script `CPS — Revise Customer Spec Button` calls this by its
Server Script name, `cps_revise`. The committed fixture in
`production_log/fixtures/client_script.json` calls the dotted app method instead —
identical behaviour either side of the deploy. **Do not `bench export-fixtures`
against the live site before deploying**, or the transitional Client Script will
overwrite the committed one and the button will call a Server Script that `v9_7`
has just deleted.
