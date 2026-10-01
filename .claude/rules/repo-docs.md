---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/repo-docs.md sha256=af1af1924b7ccdf9 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# repo-docs
Code map anchor `a1d6f3e6`; if it is behind HEAD, re-check with `git diff --name-only a1d6f3e6..HEAD -- <cited paths>`.
Covers: docs/ and CHANGELOG.md. Records that docs/adr/ holds four ADRs while accepted decisions under docs/review/ were never promoted to it, and that TODO.md's render.sh entry is still open though the cygpath -w fix is in source.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); re-anchored to 89ebda03 (L-0558 merges main 52489039); L-0513 re-anchored fe524012 -> 4eacfacf -> 3437cbdd -> e41bc6fd -> 4a48f594 -> de32cb87 -> f23b01b4 (the gate runner scripts/gate-runner.py and its review fixes; repository tooling, no plugin version; per-step notes in this map's provenance), then merged with main 52489039 (T-0040, crew 1.0.98) and re-anchored to 71038cb9, then merged with main 05a679bf (L-0558, crew 1.0.102) and re-anchored to 0d159692; re-anchored to a1d6f3e6 (T-0501 merges main 05a679bf, cacf7ff0 and ddcbf90d, crew 1.0.109)
## Landmines
- `INSTALLATION.md`'s "Eight MCP servers" section describes a menu row that no longer exists, and this is new at this anchor — not carried forward from a previous pass.
- `README.md`'s install-URL pin is current at this anchor.
- `docs/runbooks/rollback.md`'s only change in this range is a path-rename fix, and it is correct.
- `docs/HANDOFF.md` — unchanged file, closed by the per-path check.
- `docs/runbooks/INDEX.md` still does not exist.
- `/crew:handoff` still does not write `docs/HANDOFF.md`; unrelated to it.
- `docs/adr/` still exists and holds four ADRs, the fourth T-0085's.
- `docs/review/`'s existence is itself a mild instance of the same gap `docs/adr/` used to be.
- The diagram anchor-freshness mechanism is unchanged in logic, only in line numbers, confirmed by direct re-read rather than assumed.
- `TODO.md`'s `render.sh` entry is still open, still un-CLOSED, re-located rather than assumed at its old line.
- `crew-docs/SKILL.md`'s CHANGELOG rule is unchanged; its surrounding prose lost every reference to retired roles.
- `.crew/verify.json` changed substantively in this range, not merely in wording — corrected from what would otherwise be assumed by analogy to a previous pass's finding about a different range.
Full note: `.crew/codemap/repo-docs.md`.
