# Cloud handoff: L-0519

**Reconcile crew-standards with crew-qa-standards: one source per kind of rule, RF derived from the standards**

Handed to a cloud session on 2026-10-05 by owner instruction (orchestrated spec run). Do not pick up locally.

- **Role:** standalone follow-up of T-0085 (owner 2026-09-30 land decision, "follow-up for crew-qa-standards overlap").
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0519-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0519/direction.md`, `docs/tickets/L-0519/spec.md`, `docs/tickets/L-0519/HANDOFF.md`
- **Size:** 0 production lines. About 35 lines of skill/reference Markdown, one new test (~25 lines), doc rows.
- **Harness:** no. `review_prompt.py`, `review_run.py`, `commands/review.md` and `sabotage*.py` are untouched.
- **Risk:** low.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0085 / T-0086 | merged (#269, #282) | crew-standards and its first stack set. |
| L-0575 / L-0592 / L-0601 | merged | recurring-findings.md and both of its printers. |
| L-0518 | spec (sibling hand-off) | Edits `crew-standards/SKILL.md:99-104`; different lines. Whichever lands second merges main. |
| L-0532..L-0538 | not landed | Edit `crew-standards/SKILL.md:18-22` and README `:795`. Same rule. |

This ticket blocks nothing.

## Read before writing code

- The split: crew-standards owns code-level rules and the self-check; crew-qa-standards owns harness, review-process,
  gate and environment rules; RF-01..07 is a derived probe index whose `seen:` ids must exist, and the standard wins
  on a conflict.
- Write the new test first and watch it fail on RF-07 (its `seen:` names no id today), then fix RF-07's `seen:`.
- Do not add, remove, rename or re-rank an RF section, and do not change `recurring_findings.py`: three existing tests
  pin the seven classes, their order and the 60-line cap.
- Read all 21 RF probes against the standards they cite and record "agrees" or the edit in the PR body.
- `plugin/PLUGINS.md` has no `crew-qa-standards` row today; add one beside `crew-standards`.
- No plan.md is published. Write the plan first.

## Open questions for the owner (recommended option taken)

- Keep both review-prompt blocks (no harness change) rather than folding RF into crew-standards (Option 2, deferred).
- RF-07 cites this repository's overlay `REPO-03`; the test accepts overlay ids from this repo. Moving marketplace-only
  RF sections to a per-repository file is a follow-up.
- Overlapping process rules (R10, H8, R12) get one reference line each; no rule text moves.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline,
every document that describes crew in the same PR, BUDGETS.md re-measure, guides rebuilt), run
`python3 scripts/check-marketplace.py` after the commit, and remove `docs/tickets/L-0519/` in the final PR unless the
owner wants it kept.
