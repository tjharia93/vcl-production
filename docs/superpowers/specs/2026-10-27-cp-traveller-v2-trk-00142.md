# CP Job Traveller v2 — TRK-00142 print changes

**Date:** 2026-10-27 · **Print format:** `Computer Paper Job Traveller v2` (live default) · **Source:** Tanuj, 7 Oct 2026
(Notion "Session log — 7 Oct 2026", §4: "Job Traveller v2 print changes").

## The changes (all on page 1)
1. **Sales Rep = the customer's CSRA rep** on the order date (Customer Sales Rep Assignment, Active, in date).
   Falls back to the card's `sales_rep` user's full name when CSRA names nobody.
2. **"Created by" in the footer**: the card owner's full name and the creation date, under Authorizations.
3. **No underline on the rep sign line** (`.sig-line.no-rule`). Management keeps its rule.
4. **Larger font on page one**: tables and section headers at 9pt (were 8pt); sign captions 8pt.
5. **Packing printed divided by 10**: 400 shows as 40. A non-numeric packing prints as typed. Weight/Ctn and the
   Section 2 set maths (`_p = doc.packing`) are unchanged.

## Open
- **What is the 40 counted per** (bundle, pack or something else)? The cell keeps the label "Packing:" until Tanuj
  says. Asked 7 Oct, still open.

## Deliver
No schema change, no migrate. After merge: `python3 scripts/deploy_cp_traveller_v2.py --check`, then without
`--check`. Render PDFs for JC-CPT-2026-00044, 00046, 00047 and 00087 and read page 1. The larger font must not push
page 1 onto a second sheet; if it does, drop `.page-one` sizes to 8.5pt.
Rollback: `git checkout` the previous HTML and re-run the deploy script.
