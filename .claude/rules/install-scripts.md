---
paths:
  - "scripts/**"
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/install-scripts.md sha256=a05c7c9b04ebee0b -- do not hand-edit; regenerate with crew_instructions.py rules -->
# install-scripts
Code map anchor `2bb92f32`; if it is behind HEAD, re-check with `git diff --name-only 2bb92f32..HEAD -- <cited paths>`.
Covers: The install-prerequisites.{sh,ps1} matched pair: catalog parity, the pick_fit/Format-PickerLine no-bypass rule, idempotency branches, and hook-plugins-default-off on both sides.
## Landmines
- `README.md`'s install-URL pin is current at this anchor - and current is a state it leaves on the next script-touching merge.
- The five-way crew count disagreement this note tracked for several anchors is fully resolved and re-confirmed independently correct, not merely re-synced.
- `mcp_launcher_resolves` is unchanged; `add_or_refresh_mcp_server` is a new and stricter sibling, not a replacement.
- Nothing may bypass `pick_fit` / `Format-PickerLine`.
- `Test-PickerSupported` still refuses strictly more cases than bash's `picker_supported`, re-read at this anchor (`scripts/install-prerequisites.ps1:1371-1384` vs `scripts/install-prerequisites.sh:1715-1724`): redirect...
- The skill preflights are still REPORT-ONLY, unchanged in every particular this note checks.
- `ensure_uv`'s chain and memoisation are unchanged.
- `json_query` is still the one silent-collapse path.
- The `repo-plugins` menu row still defaults to OFF; its five plugins are still pre-ticked.
- `claude-memories-vault` / `claude-memories-canvas` are gone from both catalogs, replacing a landmine this note no longer needs to track.
Full note: `.crew/codemap/install-scripts.md`.
