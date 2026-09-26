---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/repo-docs.md sha256=66163814881ce5da -- do not hand-edit; regenerate with crew_instructions.py rules -->
# repo-docs
Code map anchor `6f96e627`; if it is behind HEAD, re-check with `git diff --name-only 6f96e627..HEAD -- <cited paths>`.
Covers: docs/ and CHANGELOG.md. Records that docs/adr/ holds three ADRs while accepted decisions under docs/review/ were never promoted to it, and that TODO.md's render.sh entry is still open though the cygpath -w fix is in source.
## Landmines
- `INSTALLATION.md`'s "Eight MCP servers" section describes a menu row that no longer exists, and this is new at this anchor — not carried forward from a previous pass.
- `README.md`'s install-URL pin is stale again at this anchor, as its history said it would be.
- `docs/runbooks/rollback.md`'s only change in this range is a path-rename fix, and it is correct.
- `docs/HANDOFF.md` — unchanged file, closed by the per-path check.
- `docs/runbooks/INDEX.md` still does not exist.
- `/crew:handoff` still does not write `docs/HANDOFF.md`; unrelated to it.
- `docs/adr/` still exists, unchanged in count (three) since it was first found.
- `docs/review/`'s existence is itself a mild instance of the same gap `docs/adr/` used to be.
- The diagram anchor-freshness mechanism is unchanged in logic, only in line numbers, confirmed by direct re-read rather than assumed.
- `TODO.md`'s `render.sh` entry is still open, still un-CLOSED, re-located rather than assumed at its old line.
- `crew-docs/SKILL.md`'s CHANGELOG rule is unchanged; its surrounding prose lost every reference to retired roles.
- `.crew/verify.json` changed substantively in this range, not merely in wording — corrected from what would otherwise be assumed by analogy to a previous pass's finding about a different range.
Full note: `.crew/codemap/repo-docs.md`.
