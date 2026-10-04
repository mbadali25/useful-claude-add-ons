# L-0665: promote-gate reads the newest PROMOTIONS.md row for an environment and sha, not the first          status: spec   risk: high
Split from T-0062. Written 2026-10-04 against origin/main `155fe6d8`.

## Intent
In `promote-gate.sh` and `promote-gate.ps1`, the `requires` check for an upstream environment and sha is decided by the LAST row of `.work/PROMOTIONS.md` matching that environment and sha: all three of smoke, regression and verify `pass` admits, anything else blocks. A later pass clears an earlier failure; a later failure revokes an earlier pass. No matching row still blocks. The block message for a revoked pass says the newest row is not all-pass, so the reader is not sent looking for a missing row.

## Exclusions
- The row format, the 7-character sha prefix match, and how `/crew:promote` writes rows.
- `verify-gate.sh` / `.ps1` (`HARNESS`): they only test that a row exists (`plugin/crew/hooks/scripts/verify-gate.sh:208`), which this does not change.
- Ordering by the `when` column. File order is the order; rows are appended.
- Everything in T-0062 and L-0664.

## Evidence
At origin/main `155fe6d8`.
- Bash: `plugin/crew/hooks/scripts/promote-gate.sh:397-407`; `:405-406` returns inside the loop on the first match.
- PowerShell: `plugin/crew/hooks/scripts/promote-gate.ps1:428-438`; `:434-435` the same.
- Rows are appended: `plugin/crew/commands/promote.md:292`.
- Recorded as a follow-up: `.work/followups.md:40`.
- Fixture that writes rows (all-pass only today): `plugin/crew/tests/test_promote_gate_effective_tree.py:131-137`.

## Unknowns
- U1 A hand-edited file with rows out of time order. ACCEPTED: file order decides; documented.
- U2 Version: next free crew patch at implement time.

## Open questions for the owner
1. Newest row decides (taken, recommended), or any all-pass row admits?

## Size
About 15 changed production lines across two files. No new parser or guard.

## Touch
- `plugin/crew/hooks/scripts/promote-gate.sh`
- `plugin/crew/hooks/scripts/promote-gate.ps1`
- `plugin/crew/tests/test_promote_gate_rows.py` - new, both flavours
- `plugin/crew/tests/promote_tree_mutations.py` - two entries
- `plugin/crew/commands/promote.md` - one sentence at the requires line
- `plugin/crew/.budget-allowance.json` - only if it does not fit
- `plugin/crew/README.md` - "newest row"
- `plugin/crew/skills/crew-verification/SKILL.md` - "newest row"
- `plugin/PLUGINS.md` - "newest row"
- `INSTALLATION.md` - "newest row"
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/**` - src/troubleshooting.md plus rebuilt HTML, DOCX, PDF
- `.crew/verify.json` - only if test_promote*.py does not already cover the new file (it does at :130)
- `.crew/codemap/**`
- `.claude/rules/**`
- `docs/diagrams/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `TODO.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Acceptance checks
Run: `python3 -m pytest plugin/crew/tests/test_promote_gate_rows.py -q` (one parametrised table over row sequences and both flavours).
- [ ] Must-allow: upstream rows `fail` then `pass` for this sha: exit 0.
- [ ] Must-block: `pass` then `fail`: exit 2, stderr says the newest row is not all-pass.
- [ ] Must-block: no row; a row for another sha only; newest row with one of the three cells not `pass`.
- [ ] Must-allow: a single all-pass row (unchanged); `PASS` in capitals (unchanged).
- [ ] Must-block: a newer all-pass row for a DIFFERENT environment does not clear this environment's failing row.
- [ ] `ps1` cases skip without PowerShell 7, never fail.
- [ ] Mutations RED: each flavour put back to returning on the first match turns `fail then pass` and `pass then fail` red. Run: `cd plugin/crew/tests && python3 -c "import sabotage, promote_tree_mutations as m; sabotage.MUTATIONS = m.PROMOTE_TREE_MUTATIONS; raise SystemExit(sabotage.main())"`
- [ ] Existing promote suites pass unedited: `python3 -m pytest plugin/crew/tests/test_promote_gate_effective_tree.py plugin/crew/tests/test_promote_gate_fails_closed.py plugin/crew/tests/test_gates_powershell.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; `python3 scripts/check-marketplace.py` passes after the commit; crew suite, pylint, ruff with no new findings.

## Dependencies
- T-0505 - merged. Nothing else must land first.
- L-0564 (direction), T-0062 and L-0664 touch the same two scripts; second to land merges main.
Blocks: nothing. T-0045 (direction) hit this in planning.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
