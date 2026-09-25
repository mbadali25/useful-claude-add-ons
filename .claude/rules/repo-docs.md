---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/repo-docs.md sha256=df8136f7624d5d89 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# repo-docs
Code map anchor `5d1fc5fd`; if it is behind HEAD, re-check with `git diff --name-only 5d1fc5fd..HEAD -- <cited paths>`.
Covers: docs/ and CHANGELOG.md. Records that docs/adr/ does not exist despite two documents citing it, and that TODO.md's render.sh entry is stale — the cygpath -w fix is in source.
## Landmines
- The machine-read diagram header is line 1, and line 2 is also read, by code that exists but was previously missed.
- `/crew:handoff` does not write `docs/HANDOFF.md`.
- `TODO.md`'s `render.sh` entry is still at `TODO.md:1061` — re-located by grepping the heading at this anchor and found not to have moved, even though `TODO.md` is in this range's changed set; the edits landed elsewher...
- The regression test for that fix is no longer misdocumented — this landmine is resolved, not carried forward.
- `docs/runbooks/INDEX.md` does not exist — unchanged.
- A count written into a file under `docs/` changes that count.
Full note: `.crew/codemap/repo-docs.md`.
