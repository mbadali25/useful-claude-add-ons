# Cloud handoff: T-0030

**Cross-session claims and the git-backed coordination record `crew-coord/<channel>` (1 of 3; then T-0031, T-0032)**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **INDEX status:** in-progress (risk: high)
- **Branch:** `T-0030-coord` (existing local branch, first pushed 2026-10-05). Head before this commit `ec9a28a2`.
  (`T-0030-coord-pre-rebase-c0bd16e8` is a local backup only, not pushed.)
- **Implementation:** present. 35 own commits since merge base `2693d0fa` (2026-09-28); ~5,100 lines across 8 files,
  chiefly `plugin/crew/hooks/scripts/crew_coord.py`. Branch declares crew 1.0.71.
- **Review:** 7 rounds run. Round 7 (1 BLOCK, 2 FIX, 3 NITs) fixed test-first in `b3c7691f` (12 red before, in
  `round7-red-before-fix.txt`; 289 coord cases pass). Ledger shows **1 round left**: the next review is the last.
- **Last measured (2026-09-30, on this branch, under heavy-run):** crew pytest 6734 passed / 0 failed; coord sabotage
  101/101 RED; run-tests 122/0; validate-prompts 130/0; check-marketplace pass; pylint 10.00.
  **Not verified:** full `sabotage.py` (cut off by SIGTERM after 385 RED, not re-run). ruff-no-new exit 1
  (7 new: ISC004 x2, PT014, RUF100 x3, UP031) - fix at land.
- **Files here:** `docs/tickets/T-0030/` direction, spec, plan, the round-6 plan, spike, and the round 6/7 red-before-fix logs.

## Read before continuing

- **Far behind main:** ~3,000 commits behind origin/main. Merge origin/main first, re-run the suites above, re-bump crew
  above main's version, refresh the codemap and graph (`graphify update .`).
- Last review round: per the round-cap rule, a last round with edge-case-only findings means owner accepts + follow-up ticket.
- Fix the 7 ruff findings before landing (gate rule 15: no new findings vs merge-base).

## Downstream

Blocks T-0031 (#408) and T-0032 (#434).

## Before landing

Follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), land as a
merge commit, and remove `docs/tickets/T-0030/` in the final PR unless the owner wants it kept.
