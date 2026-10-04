# L-0679 direction: sabotage entries for `crew_memory.py` (tooling-only PR)          status: direction   risk: low
Split from T-0084. Filed as L-0679.
## Ask
The parent direction ends: "sabotage for the dangling-pointer and absolute-path cases." The sabotage runner proves a test can fail: it applies a named mutation to production code and expects a named test to go red. Its files, `plugin/crew/tests/sabotage*.py`, are review/gate harness, and the repo rule (2026-09-28) is that a harness change lands alone with no feature work. So the mutations for the pointer resolver, the writer and the migration cannot ride in those feature PRs and are this separate, tooling-only ticket.
Checked against origin/main `155fe6d8` (crew 1.0.322) on 2026-10-04. The owner was not available; defaults are the recommended options and the questions are in the parent's direction.md, "Open questions for the owner".
## Options
1. **Recommended, taken: add a `MEMORY_MUTATIONS` tuple to the existing `plugin/crew/tests/sabotage_context.py` and fold it into `CONTEXT_MUTATIONS`.** That module already holds the `crew_recall.py` mutations and is already imported by `sabotage.py`, which is at the pylint module limit (3400 of 3400 lines) and cannot take a new import line.
2. A new `sabotage_memory.py`. Cleaner name, but needs a new import and a new term in `sabotage.py`'s `MUTATIONS +=` expression, so it needs lines freed in a file at its limit. Rejected unless L-0608 or another ticket has freed room by then.
3. No sabotage entries; rely on the must-refuse tests. The repo's lesson is that guard bugs shipped past review and were caught only by sabotage. Rejected.
## Recommendation
Option 1, one PR after L-0678 has merged, covering all three slices. If L-0678 is delayed, the entries for the first slice and L-0677 may land first and L-0678's follow in a second tooling PR.
## Approval
Status `direction`. Owner go for the hand-off: 2026-10-04.
