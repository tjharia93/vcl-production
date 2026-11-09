# Exercise book production process

The five floor steps, as Tanuj set them out on 04/11/2026:

1. **Ruling** (inner papers)
2. **Covers**
3. **Folding** of the inner paper
4. **Inserts**
5. **Packing**

## How each step is recorded today
From the PC session (TMP-M034) on 04/11/2026: what is recorded, not yet confirmed on the floor.

| Step | ERPNext / dev page today |
|---|---|
| Ruling | Not modelled. The `Ruling` workstation type has Ruling Machine 01 and Ruling 02, with zero schedule lines. The handwritten daily log goes to n8n (Ruling Log Sync), then to a CSV and Slack. Floor log stations: R-01 to R-04. Paper: NP/BP. Output A1. |
| Covers | Counted in PRINTED SHEETS (1 Nos = 1 sheet), item `COV-<book code minus first 4 chars>`. The Cover Stock quick entry posts a submitted Material Receipt into `Stores - VCL`. Remove posts a Material Issue ("used in binding"). Standard imposition A5 = 3-up, A4 = 2-up, read from the item name with `/(\d+)\s*up$/`. A5 9-up and A4 4-up are defined in code but unused. Watch out: older code reads "covers" as single covers, so applying the up-count twice overstates capacity. |
| Folding | Not modelled. Collation workstations Collater 01/02 have no book work recorded. |
| Inserts | 1 cover sheet becomes 1 insert sheet. A submitted Repack in `Stores - VCL`: the COV item goes down and `INS-…` (Item Group Exercise Book Inserts) goes up by the same quantity. Book equivalents = sets × up-count. Collating, stitching, binding and trimming are not modelled. |
| Packing | Full cartons, loose books and rejects are saved to browser localStorage only. Nothing reaches ERPNext. |

Finished goods: the opening balance is Stock Reconciliation `MAT-RECO-2026-00003` (04/11 16:29). It has 29 rows, 3,566 cartons = 516,918 Nos in `Finished Goods - VCL`, at zero valuation (authorised by Tanuj). No ongoing receipt exists yet.

Demand: open submitted Sales Orders in cartons. Required = max(0, pending − physical finished cartons), across all warehouses, with no reservation.

Machines, owners and wastage: none are recorded for any step. The Production Floor Exercise Book department (vcl-production `71590c8`) has no machines. The 04/11 review (PC: `C:\Second_Brain\output\production-process-flow-review.md`) proposes printed/usable/spoilage per cover run and good/reject/rework per binding stage.

## Still to confirm on the floor
- Where stitching and trimming sit (inside Inserts?), and whether folding is done by machine or by hand.
- Where quantities are counted, and who owns each handover (Nadeem and Peter are candidates).
- Where the run reference travels.
- Which actions post stock, when inserts are consumed, and when finished stock is accepted.
- How rejects, loose books and reversals are handled.
