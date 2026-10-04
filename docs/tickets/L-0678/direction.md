# L-0678 direction: `crew_memory.py migrate` and `restore` - convert existing native memories, previewed and opt-in, and undo it          status: direction   risk: med
Split from T-0084. Filed as L-0678.
## Ask
The parent direction says: "Migration of existing native memories is opt-in and previewed." After T-0084's first slice (format, resolver) and L-0677 (`save`), a host still has its older memories as full text. This child converts a whole memory directory in one previewed run, and gives the way back: a pointer turned into full text again, for a host that is leaving the vault or has lost it.
Checked against origin/main `155fe6d8` (crew 1.0.322) on 2026-10-04. The owner was not available; defaults are the recommended options and the questions are in the parent's direction.md, "Open questions for the owner".
## Options
1. **Recommended, taken: `migrate --memory-dir` as a loop over L-0677's `save`, dry run by default, plus `restore --file`.** One row per file in the preview; `--apply` converts only the rows the preview showed as convertible; a failure on one file never stops or undoes the others and never leaves a dangling pointer, because each file goes through `save`'s note-first order.
2. Migration only, no `restore`. Smaller, but then a pointer is a one-way door and a host without the vault has no supported way to get its text back. Rejected.
3. Migrate automatically at session start. Rewrites user files unasked; the direction says opt-in. Rejected.
## Recommendation
Option 1. Nothing runs unless the user asks for it, and the preview is the default.
## Approval
Status `direction`. Owner go for the hand-off: 2026-10-04.
