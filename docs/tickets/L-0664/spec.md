# L-0664: promote-gate.ps1 treats a workflow dispatch of a declared deploy workflow as that deploy          status: spec   risk: high
Split from T-0062. Written 2026-10-04 against origin/main `155fe6d8`.

## Intent
`promote-gate.ps1` gets the same rule T-0062 gave `promote-gate.sh`: when containment matches no declared `deploy` and the map declares a workflow-dispatch deploy, the command is read by `_promote_dispatch.py` (T-0062) with `shell=powershell`, and the answer is used exactly as the Bash flavour uses it: an environment name gates the command as that environment's deploy; could-not-tell blocks; not-a-dispatch and an undeclared workflow pass untouched. The committed map is matched too when the working map is dirty. Python is resolved by the inline `Resolve-CrewPython`, byte-identical to the other crew `.ps1` copies. When no python resolves, a command naming `gh` with `workflow` or `dispatches` (case-insensitive) blocks if any declared `deploy` names them too; anything else behaves as today.

## Exclusions
- The reader, the helper's rules and `promote-gate.sh`: T-0062. No behaviour change there.
- The first-row bug: L-0665.
- Symbolic refs; other routes to a dispatch; L-0564's findings.
- No path in `HARNESS` (`scripts/check-tooling-pr.py`).

## Evidence
At origin/main `155fe6d8`.
- Containment only: `plugin/crew/hooks/scripts/promote-gate.ps1:87-93` (committed map), `:117-135` (working map).
- The script runs no python: `git grep -n "Resolve-CrewPython" origin/main -- plugin/crew/hooks/scripts/promote-gate.ps1` prints nothing.
- The resolver to copy: `plugin/crew/hooks/scripts/cloud-guard.ps1:22`; its copies are held identical by `plugin/crew/tests/test_ps1_python_probe.py`.
- Flavour guard and payload read: `promote-gate.ps1:14-22`.
- The suite runs a `ps1` flavour wherever PowerShell 7 resolves: `plugin/crew/tests/test_promote_gate_effective_tree.py:45-47`, `:149-166`.

## Unknowns
- U1 Whether `test_ps1_python_probe.py` discovers `.ps1` files by glob or by a list. If a list, `promote-gate.ps1` is added to it (in Touch).
- U2 The no-python rule. DECIDED: block as Intent states; an unknown does not become "not a deploy".
- U3 Windows-native proof. ACCEPTED: the pwsh cases run on Linux with PowerShell 7; a native Windows run is requested from the Windows lane before landing, as for T-0505.
- U4 Version: next free crew patch at implement time.

## Open questions for the owner
1. No python on the PowerShell side: block dispatch-looking commands (taken, recommended) or stand down as the Bash flavour does at `promote-gate.sh:79`?

## Size
About 100 added production lines in one file (about 60 are the resolver copy). No new parser.

## Touch
- `plugin/crew/hooks/scripts/promote-gate.ps1`
- `plugin/crew/tests/test_promote_gate_dispatch.py` - add the ps1 flavour to T-0062's cases
- `plugin/crew/tests/test_ps1_python_probe.py` - only if U1 needs it
- `plugin/crew/tests/test_gates_powershell.py` - only if a fixture's premise changes
- `plugin/crew/tests/promote_tree_mutations.py` - .ps1 entries
- `plugin/crew/commands/promote.md` - drop "PowerShell is containment-only"
- `plugin/crew/README.md` - drop "PowerShell is containment-only"
- `plugin/crew/CONFIG.md` - drop "PowerShell is containment-only"
- `plugin/crew/skills/crew-verification/SKILL.md` - drop "PowerShell is containment-only"
- `plugin/crew/BUDGETS.md`
- `plugin/PLUGINS.md`
- `INSTALLATION.md`
- `docs/guides/crew/**` - src/troubleshooting.md plus rebuilt HTML, DOCX, PDF
- `.crew/codemap/**`
- `.claude/rules/**`
- `docs/diagrams/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Acceptance checks
Run: `python3 -m pytest plugin/crew/tests/test_promote_gate_dispatch.py plugin/crew/tests/test_ps1_python_probe.py -q`
- [ ] Every must-block and must-allow case of T-0062's `test_promote_gate_dispatch.py` passes for the `ps1` flavour with the same exit code, written in PowerShell syntax where it differs.
- [ ] Must-block: with PATH holding no python, `gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches -f 'inputs[environment]=production'`: exit 2, stderr says python could not be found and that this is not a pass.
- [ ] Must-allow: with no python, `Write-Output done` and `gh pr list`: exit 0.
- [ ] On a machine without PowerShell 7 the `ps1` cases skip; they never fail.
- [ ] `Resolve-CrewPython` in `promote-gate.ps1` is byte-identical to the other copies (the probe test).
- [ ] Mutations RED on a named test: the helper call removed from the `.ps1`; could-not-tell read as no match; the no-python branch exiting 0. Run as in T-0062.
- [ ] `promote-gate.sh` is unchanged: `git diff origin/main --stat -- plugin/crew/hooks/scripts/promote-gate.sh` is empty.
- [ ] The PowerShell static check passes (the `.crew/verify.json` rule that runs `scripts/check-powershell.ps1`).
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; `python3 scripts/check-marketplace.py` passes after the commit; crew suite, pylint, ruff as in T-0062.

## Dependencies
- T-0062 - ready (spec), not built. Supplies `_promote_dispatch.py`. Hard blocker.
- T-0009 - in-progress (PR #336 open). Through T-0062.
- T-0505 - merged.
Blocks: nothing. T-0045 (direction) benefits.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
