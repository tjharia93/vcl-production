# Exercise book production

The working folder for exercise books: how they are made, what has been built for them, and
what we are still deciding. Add a new note here as each discussion happens.

Exercise books are not yet run through this app (no Job Card type, no CPS). They are sold
through Compass and made as stock production on the floor.

| File | What it holds | Status |
|---|---|---|
| `01-production-process.md` | The five steps and how each is recorded today | From the PC session, 04/11/2026 |
| `02-built-on-dev-pages.md` | Dev pages, backends and print formats built for exercise books | From the PC session, 04/11/2026 |
| `03-known-facts.md` | What is already settled: naming, packing, stock, orders | Taken from the second-brain notes, 04/11/2026 |
| `04-open-questions.md` | Decisions still open | Running list |

Copies kept elsewhere:
- second-brain: `brain_inbox/exercise-book-production-process.md` (on the Windows PC working copy only, not yet committed; see the chief of staff note)
- tanuj_chief_of_staff: `docs/exercise-book-production.md`

## Review page
`exercise-book-review.html` is the source of the tabbed review artifact:
https://claude.ai/artifact/DtTjNC15VeSb9cneqqK16o. To add a tab, add a link in the tab strip
and a `section.panel` with a matching `data-tab`, then republish.
