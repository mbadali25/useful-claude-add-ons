# Cloud handoff: L-0525

**sabotage suite: 13 vacuous entries and 1 unproven keep the whole run from going green (tooling-only PR)**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** standalone. Filed from T-0086 round 1, BLOCK 2: the owner waived "the whole sabotage run is not green" for that ticket and filed this one.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; the implementing session writes the plan)
- **Branch:** `L-0525-build`, new from origin/main `a555ff37`. Docs only so far, no implementation yet.
- **Files here:** `docs/tickets/L-0525/direction.md`, `docs/tickets/L-0525/spec.md`
- **Size:** 0 production lines. About 70 lines across `sabotage_bound.py` and `sabotage.py`, up to 3 strengthened tests, and about 8 `test_sabotage_bound.py` cases.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a review/gate harness path (`scripts/check-tooling-pr.py:79`), so this lands alone as a tooling-only PR. Tests and docs may ride along. Production code may not.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0080 | merged (PR #399, crew 1.0.337) | The per-entry memory and time bound. It already fixed the direction's entry 15 (the cloud guard OOM). |
| T-0087 | merged | The rule that tooling PRs land alone. |

This ticket blocks nothing. It can start now.

## What was re-measured at `a555ff37`

- Entry 15 (azureProfile OOM): done by T-0080. Only confirm it in the full run.
- Entry 14 (`docs.theme`, exit 4): the target test was renamed, so pytest cannot find the node id. `test_upgrade_config_does_not_alias_the_shared_docs_block` already pins the value.
- Entries 4-12 and 13: their targets are `skipif` off Windows even with pwsh present. On Linux they are **unexercised**, not proven vacuous, but the runner reports a skip as `STILL GREEN -- TEST IS VACUOUS`.
- Entries 1-3 run on Linux and each needs a one-entry measurement (see spec Unknowns).

## Read before writing code

- Re-find every `path:line` by content. They were checked at `a555ff37`.
- `plugin/crew/tests/sabotage.py` is at 3381 of pylint's 3400-line cap, so put the new verdict logic and the Windows-only label set in `sabotage_bound.py`, not in `sabotage.py`.
- "Skipped" is its own value. An undeclared skip, or a pytest summary that cannot be read, fails the suite. Never let it read as a pass (CLAUDE.md, Lessons).
- If entry 1, 2 or 3 turns out to be a real production defect, record it on the entry and file a new ticket. The fix does not go in this PR.
- A harness change runs the harness rule's suites: the tooling checker, its suite, the golden replay, the seam contracts, and the canary review.
- Run the sabotage suite through heavy-run. It is the longest suite in the repo.

## Open questions for the owner (recommended option taken)

- A Linux run that skips declared Windows-only entries prints `PASS (N windows-only entries not run on this host)`, exit 0. Owner may require the Windows leg instead.
- Skip detection reads pytest's summary line, and an unreadable summary is "could not tell", which fails.
- Option 2 (making the Windows-only tests portable to Linux pwsh) was rejected as production work in a harness file.

## Before landing

Merge origin/main and take a crew version above main's from the coordinator. Follow the repo's CLAUDE.md: scope discipline, doc updates for `plugin/crew` changes (README sabotage section, `.crew/codemap/verification-harness.md`), and the tooling-PR rule. Attach the full sabotage log to the PR. Remove `docs/tickets/L-0525/` in the final PR unless the owner wants it kept.
