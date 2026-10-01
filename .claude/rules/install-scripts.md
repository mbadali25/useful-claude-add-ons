---
paths:
  - "plugin/crew/**"
  - "scripts/**"
---
<!-- crew:generated source=.crew/codemap/install-scripts.md sha256=4a6fe32f440bc7b6 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# install-scripts
Code map anchor `7ecbdc7f`; if it is behind HEAD, re-check with `git diff --name-only 7ecbdc7f..HEAD -- <cited paths>`.
Covers: The install-prerequisites.{sh,ps1} matched pair: catalog parity, the pick_fit/Format-PickerLine no-bypass rule, idempotency branches, and hook-plugins-default-off on both sides.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 5ab63076 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines); re-anchored to 805b0a25 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place); re-anchored to 7ecbdc7f (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only)
## Landmines
- `README.md`'s install-URL pin is current at this anchor.
- The five-way crew count disagreement this note tracked for several anchors is fully resolved and re-confirmed independently correct, not merely re-synced.
- `mcp_launcher_resolves` is unchanged; `add_or_refresh_mcp_server` is a new and stricter sibling, not a replacement.
- Nothing may bypass `pick_fit` / `Format-PickerLine`.
- `Test-PickerSupported` still refuses strictly more cases than bash's `picker_supported`, re-read at this anchor (`scripts/install-prerequisites.ps1:1372-1385` vs `scripts/install-prerequisites.sh:1717-1726`): redirect...
- The skill preflights are still REPORT-ONLY, unchanged in every particular this note checks.
- `ensure_uv`'s chain and memoisation are unchanged.
- `json_query` is still the one silent-collapse path.
- The `repo-plugins` menu row still defaults to OFF; its five plugins are still pre-ticked.
- `claude-memories-vault` / `claude-memories-canvas` are gone from both catalogs, replacing a landmine this note no longer needs to track.
Full note: `.crew/codemap/install-scripts.md`.
