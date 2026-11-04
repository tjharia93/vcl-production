# Exercise books: what is already settled

Taken on 04/11/2026 from the second-brain notes `exercise-book-naming-standard-2026-10`,
`exercise-book-orders-compass` and `exercise-books-no-stock-in-erpnext`.

## Item names (Tanuj decided this on 26/10/2026, and it went live the same day)
- Name: `<Brand or Paper> - <Size> - <Pages> Pages - <Ruling> - <Cover>`.
- Retail brands: Prince, Hi5 and Swara (the paper is not in the name).
- School books carry no brand. The paper is the name instead: Bank Paper (was Prince),
  Newsprint (was Swara), and Brilliant White Bank Paper (was Hi5, a different paper with its
  own prices, codes `SCH-WBP-EB-…`).
- Rulings: SL single line, SQ square line, GPH graph, PLN plain, MSC music, IRS Irish,
  HSL/HSQ, SQ13 (1/3 inch square line), FNB.
- Description = name + ` - <pieces> per carton`. The packing goes in the description only.
- A4 32-page books are not a product (30 items disabled).

## Packing and price
- Prices are per carton. The Carton UOM conversion = pieces per carton:
  200pg = 66, 120pg = 102, 96pg = 120, 80pg = 144, 64pg = 162, 48pg = 204.
- Standard Selling price per carton, ex-VAT = 2026 price list ÷ 1.16. Old price rows were
  end-dated 25/10/2026.
- Done: 392 chipboard items and 18 Hi5 school items.

## Stock
- Until 04/11/2026 no exercise-book item had a Stock Ledger Entry. Opening stock was then posted as
  `MAT-RECO-2026-00003` (3,566 ctn = 516,918 Nos, Finished Goods - VCL, zero valuation).
- Stock production with no customer uses customer `Stock`, with the brand in the job name
  (e.g. `Prince 4 Quire`). Prince is a brand, not a customer.

## Built so far (as recorded in the notes)
- Compass Exercise Book Orders, `/compass/exercise-books` (vcl_compass main 5709b0a,
  30/10/2026, TRK-00362). Merged, not deployed. The deploy needs a migrate (Sales Order fields
  `vcl_eb_stage`, `vcl_eb_stage_by`, `vcl_eb_stage_on`) and the site config
  `compass_exercise_books`. Stock goes to the earliest delivery date first.
- Print formats on Sales Order: "Prod Exercise Book" (SL/SQ side by side, A4/A5 size badges)
  and "Sales Order - Production".
- A quick-entry form for covers on production-dev (3-up/9-up and 2-up/4-up conversion),
  which submits straight to ERPNext. The PC session will fill in the details in
  `02-built-on-dev-pages.md`.
