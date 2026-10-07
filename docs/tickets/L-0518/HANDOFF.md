# Cloud handoff: L-0518

**T-0085 round-4 follow-up (feature half): proposals trusts the round's recorded verdict, SHA-256 stamps, plan-time `sets --touch`, four NITs**

Handed to a cloud session on 2026-10-05 by owner instruction (orchestrated spec run). Do not pick up locally.

- **Role:** follow-up of T-0085 (#269), owner "Accept, follow-up" on review round 4 (2026-09-30). Feature half of two.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0518-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0518/direction.md`, `docs/tickets/L-0518/spec.md`, `docs/tickets/L-0518/HANDOFF.md`
- **Size:** about 45 production lines in `crew_standards.py`, about 120 test lines, doc lines.
- **Harness:** no for this PR. Two findings (F2 in `review_run.py`, N4 in `review_run.py`) and every sabotage entry are
  harness paths; they are specified in the spec's "Tooling half" for a separate tooling-only ticket.
- **Risk:** medium (`proposals` refuses more; the stamp regex is read by the review gate in every repo).

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0085 | merged (#269) | The code the findings are in. |
| L-0519 | spec (sibling hand-off) | Edits other lines of `crew-standards/SKILL.md`. Whichever lands second merges main. |
| L-0532..L-0538 | not landed | Edit `crew-standards/SKILL.md:18-22`. Same rule. |
| Tooling half | not minted | F2, N4, `commands/review.md:531`, sabotage entries. Lands after this PR. |

## Read before writing code

- Every finding was re-found at `a555ff37`; the table in direction.md has the current lines. The round-4 line numbers
  (`:715`, `:422`, `:86`, `:72`, `:51`, `:100`, `:292`, `:391`, `:488`) are stale.
- F1 reads the review ledger (`review_ledger.status`); it does not edit `review_ledger.py` or `review_run.py`. The five
  existing `proposals` tests need a ledger fixture first.
- F3's test needs `git init --object-format=sha256`; skip only with the reason printed when git cannot make one.
- F4 adds `--touch` to `sets`; plain `sets` keeps refusing without a scope base (an existing test pins that).
- Do not edit `commands/review.md`, `review_*.py` or `sabotage*.py` here: `check-tooling-pr.py` would refuse the mix.
- No plan.md is published. Write the plan first.

## Open questions for the owner (recommended option taken)

- Split into a feature PR (this) and a tooling-only PR (F2, N4, sabotage), per the standing tooling-PR rule.
- F1's source of truth is the ledger row for `--round N`; `out.txt`'s own parse stays as a second check.
- F3 accepts exactly 40 or 64 hex.
- N1 edits a released CHANGELOG line to name the rule instead of a number, since the number was never true on main.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline,
doc updates for `plugin/crew` changes, BUDGETS.md, guides rebuilt), run `python3 scripts/check-marketplace.py` after the
commit, ask the coordinator to mint the tooling-half ticket from the spec's "Tooling half" section, and remove
`docs/tickets/L-0518/` in the final PR unless the owner wants it kept.
