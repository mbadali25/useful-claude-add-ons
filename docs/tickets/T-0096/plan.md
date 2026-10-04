# T-0096 plan: the shell config resolver and the guard-class readers outside the harness

status: plan   written 2026-10-04 by the implementing session (owner unavailable)

Written from spec.md against origin/main `baf193aa` (crew 1.0.325), merged into
`T-0096-build`. Every anchor the spec cites was re-read there and still holds:
`_common.sh:341` (the stand-down grep), `cloud-guard.sh:35-45` (`_cloud_guard_armed`),
`cloud-guard.ps1:192-210` (`Test-CloudGuardArmed`, paths at :199-200),
`promote-gate.ps1:148-158` (`Test-CrewIncidentActive`, read at :151),
`auto-clear.ps1:146` (`$repoCfg`), `crew_common.py:92-177` (the Python resolver).
Dependencies T-0088 and T-0087 are on main.

## Decisions taken with the owner unavailable
The spec's recommended option for each open question, unchanged: `unknown` is armed in
the cloud guard's no-python fallback; the `.crew/` directory gates stay; three PRs;
an inherited relative `handoffPath` stays lane-relative (L-0680's concern, untouched
here); the `verify-gate.ps1` stand-down divergence is documented until L-0681;
`.crew/verify.json` is not inherited.

One reading the spec left open: PowerShell 5.1 has no symlink-resolving path call.
`Get-CrewRepoConfigDir` therefore returns `unknown` when any component of the git dir
or the common dir it is about to compare is a symlink or junction, so it can read
`unknown` where Python reads `main`/`own`, and never `main` where Python reads `own`.

## Steps (test-first: each test is written and seen red before its code)
1. `plugin/crew/tests/test_worktree_config_shell.py` (new): fixtures (a main checkout,
   a lane, a submodule, a bare repo's worktree, a `.git` file naming a missing dir, a
   lane path with a space), and the parity tests `test_bash_resolver_agrees_with_python`
   and `test_powershell_resolver_agrees_with_python` against
   `crew_common.repo_config_dir`. Red: neither function exists.
2. bash resolver in `_common.sh`: `crew_repo_config_dir [root]` setting `CREW_CFG_DIR`
   and `CREW_CFG_SOURCE` (`own`/`main`/`unknown`), and `crew_repo_config_file [name]`.
   Green on step 1's bash cases.
3. PowerShell resolver `Get-CrewRepoConfigDir` (returns `@{ Dir; Source }`), copied
   verbatim into `cloud-guard.ps1`, `promote-gate.ps1`, `auto-clear.ps1`;
   `test_powershell_resolver_copies_are_identical`. Green on step 1's pwsh cases.
4. Cloud guard fallback, both flavours: the must-block cases (main checkout's `block`
   inherited; `unknown` armed) and must-allow cases (lane's own `off`; no layer arms
   it, in a lane and in a plain repo). Then route `_cloud_guard_armed` /
   `Test-CloudGuardArmed` through the resolver; `unknown` returns armed.
5. Incident stand-down: `test_incident_stand_down_false_is_inherited[sh|promote-gate.ps1]`,
   then route `crew_incident_active` and promote-gate's `Test-CrewIncidentActive`.
   `.crew/incident.json` stays own.
6. `test_auto_clear_ps1_reads_the_inherited_repo_veto`, then route `$repoCfg`.
7. Hand sabotage (a)-(d) from the spec's Acceptance, each with its red test named in
   the PR body; restore and re-run green.
8. Docs: README "not yet covered" list, CONFIG.md "In a linked worktree",
   troubleshooting.md (and the built html/docx/pdf), CHANGELOG, code map, the two
   config diagrams, a `.crew/verify.json` rule with a measured `seconds`, regenerated
   `.claude/rules`. Each names the `verify-gate.ps1` stand-down divergence.
9. Delete `docs/tickets/T-0096/` in the last content commit.
10. Version-only last commit: crew to the coordinator's placeholder in every place
    stated.

## Not in this PR
No harness path (`verify-gate.*`, `scope-guard.*`, `completion-audit.*`,
`review_gate.py`, `tests/sabotage*.py`): L-0681. No session hook: L-0680. No change to
`crew_common.py`. The sabotage mutations are recorded for L-0681 to add.
