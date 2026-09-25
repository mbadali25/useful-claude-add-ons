---
paths:
  - "scripts/**"
---
<!-- crew:generated source=.crew/codemap/install-scripts.md sha256=b11e390235867c3a -- do not hand-edit; regenerate with crew_instructions.py rules -->
# install-scripts
Code map anchor `5d1fc5fd`; if it is behind HEAD, re-check with `git diff --name-only 5d1fc5fd..HEAD -- <cited paths>`.
Covers: The install-prerequisites.{sh,ps1} matched pair: catalog parity (confirmed in sync), the pick_fit/Format-PickerLine no-bypass rule, idempotency branches, and hook-plugins-default-off on both sides.
## Landmines
- Matched pair, and confirmed in sync at this anchor - by mechanical diff, not by eye.
- The parity checker guards keys, not text - so agreeing descriptions can be jointly wrong.
- The README's install URLs are STALE again at this anchor — the previous pass's "now CURRENT" finding rotted within the same commit range that produced this pass.
- `claude mcp add` writes config and never invokes the command, so six rows reported success for servers that could not start.
- `ensure_uv` is a chain of rungs, it is memoised, and the two scripts' middle rungs are NOT the same.
- The skill preflights are REPORT-ONLY and must stay that way.
- Nothing may bypass `pick_fit` / `Format-PickerLine` - `scripts/install-prerequisites.sh:1715-1725` and `scripts/install-prerequisites.ps1:1325-1333`.
- Idempotent on both sides, and both sides re-checked.
- The `repo-plugins` menu row defaults to OFF; the five plugins inside it are pre-ticked.
- `json_query` resolves `jq` then `python3` and nothing else, with stderr discarded.
- The `pwsh`-not-on-PATH landmine does not live here.
Full note: `.crew/codemap/install-scripts.md`.
