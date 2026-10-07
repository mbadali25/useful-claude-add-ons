# L-0689 promote-gate matches a fragment of a declared deploy command and leaves a false in-flight marker          status: spec   risk: med
Written 2026-10-04 against origin/main `baf193aa` (crew 1.0.325). No earlier spec and no plan.md.

## Intent
`promote-gate.sh` and `promote-gate.ps1` treat a command as a declared deploy only when the command contains the declared `deploy` text. The reverse test (the command is a fragment of the declared text) is removed at all four sites, so `git rev-parse HEAD`, `HEAD`, `development` or `gh workflow run` no longer match a declared `gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)`, no `.crew/.deploy-in-flight` marker is written for them, and the Stop gate stops reporting "DEPLOY NOT RECORDED" for a deploy that never ran. The declared command run verbatim, with extra arguments after it, or wrapped (`cd <dir> && <declared>`) is gated exactly as today.

In `promote-gate.ps1` the working-map site also stops reading the declared text as a wildcard pattern: both of its sites use one literal, case-insensitive containment test.

## Exclusions
- No tokenizer and no "leading command plus environment argument" rule (direction.md, option 2). The workflow-dispatch reader is T-0062 / L-0664; the `github` entry is L-0648.
- `verify-gate.sh` / `verify-gate.ps1`: both are in `HARNESS` (`scripts/check-tooling-pr.py`). The Stop-time message and how the marker is read do not change.
- When or whether the marker is written for a matched command (it is written before the deploy runs, so a deploy that fails to start also leaves one). Not this ticket.
- Cleaning up a marker an older version already left behind. The docs say how to tell a false one; nothing deletes it.
- The `requires` / `rollback` / `requireHuman` checks, the tree resolution (T-0505), the first-row `passed()` (L-0665).
- `plugin/crew/tests/sabotage*.py` and every other `HARNESS` path. New mutations go in `promote_tree_mutations.py`, which is not harness; wiring them into `sabotage.py` is a separate tooling-only PR with no feature work in it.
- No rewrite of any consumer's `.crew/verify.json`.

## Evidence
All read at origin/main `baf193aa` with `git show origin/main:<path>`. Nothing was run.
- Working-map match, both directions: `plugin/crew/hooks/scripts/promote-gate.sh:213`, `if d and (d in cmd or cmd in d):`. The comment at `:211-212` says "Substring both ways ... Deliberately generous - a missed match means no gate."
- Committed-map match, same test: `plugin/crew/hooks/scripts/promote-gate.sh:140`, inside `matches()` (`:130-142`), used at `:169` when the working map is dirty.
- A match with every other check passing writes the marker: `plugin/crew/hooks/scripts/promote-gate.sh:510-511`, `printf '%s %s\n' "$ENVNAME" "$SHA" > .crew/.deploy-in-flight`. `SHA` is the judged tree's HEAD (`:351`).
- A bare `git rev-parse HEAD` reaches that line without a block on a clean worktree: no match exits at `:230`; a matched command with a bare `git` makes the tree the run directory (`:312-314`).
- The Stop gate's demand: `plugin/crew/hooks/scripts/verify-gate.sh:206-211`, "DEPLOY NOT RECORDED: $DENV was deployed at $DSHA and .work/PROMOTIONS.md has no row for it."
- Same family, already fixed: `plugin/crew/hooks/scripts/promote-gate.sh:199-204` (a string `deploy` iterated by character; `echo done` wrote a marker), pinned by `plugin/crew/tests/test_promote_gate_unreadable_map.py:241-257` (sh) and `:289-294` (ps1).
- PowerShell twin, committed map: `plugin/crew/hooks/scripts/promote-gate.ps1:90`, `if ($cmd.Contains($dep) -or $dep.Contains($cmd))` (case-sensitive, literal).
- PowerShell twin, working map: `plugin/crew/hooks/scripts/promote-gate.ps1:134`, `if ($dep -and ($cmd -like "*$dep*" -or $dep -like "*$cmd*"))` (case-insensitive, and `-like` reads `[`, `]`, `*`, `?` in the declared text as wildcards). Marker write: `:507`.
- Existing suites run the declared command verbatim, never a fragment of it: `plugin/crew/tests/test_promote_gate_fails_closed.py:35`, `:57`; `plugin/crew/tests/test_promote_gate_unreadable_map.py:47`, `:102`, `:111`; `plugin/crew/tests/test_gates_powershell.py:42`, `:126`; `plugin/crew/hooks/scripts/_test/run-tests.sh:475-478`, `:509-688`; fixture and runner to reuse: `plugin/crew/tests/test_promote_gate_effective_tree.py:47` (`FLAVOURS`), `:82` (`Repo`), `:149` (`run_gate`).
- Mutations file and how it is run: `plugin/crew/tests/promote_tree_mutations.py:1-15` (not wired into `sabotage.py`).
- The verify rule already covers both scripts and `test_promote*.py`: `.crew/verify.json:122-135`. The `.ps1` static check: `.crew/verify.json:249-251`.
- `HARNESS` (`scripts/check-tooling-pr.py:58-87`) lists `verify-gate.*` and `plugin/crew/tests/sabotage*.py`; it does not list `promote-gate.sh`, `promote-gate.ps1`, `_promote_tree.py`, `test_promote*.py`, `promote_tree_mutations.py` or `_test/run-tests.sh`. This is a feature PR.
- Docs that state the match rule, all as "a command matching a declared deploy entry", none stating the direction: `plugin/crew/README.md:2558-2559`, `:2850`; `plugin/crew/commands/promote.md:312`; `plugin/crew/skills/crew-verification/SKILL.md:399`, `:408-409`; `plugin/crew/skills/crew-setup/phases.md:439`; `plugin/PLUGINS.md:33`, `:290`; `INSTALLATION.md:271`; `docs/guides/crew/src/troubleshooting.md:312`.
- Reported, not reproduced: two false markers on 2026-10-04 in lane worktrees of another repository, each naming the worktree's HEAD, with no deploy run for either sha.

## Unknowns
- U1 The trigger is inferred. The reporter did not pipe a payload into the hook. RESOLVED BY the first acceptance check, run on the unfixed script before any edit. If it does not reproduce (exit 0 with no marker), stop: the cause is elsewhere, this spec's Intent does not hold, and the finding goes back to the owner.
- U2 Whether any real map relies on the reverse test (a declared `cd infra && ./deploy.sh prod` run as `./deploy.sh prod`, or the declared command run with fewer trailing arguments). Could not tell from this repository. ACCEPTED as risk and stated as a breaking change in CHANGELOG and the docs: such a command is no longer matched, and the fix is to declare the shortest text every real run contains.
- U3 The `-like` wildcard reading at `promote-gate.ps1:134`: a declared deploy holding `[` and `]` (for example `-f 'inputs[environment]=x'`) may fail to match its own verbatim command, which would be a missed gate. NOT MEASURED. An acceptance check pins it; the literal test in Intent fixes it either way.
- U4 Case. Bash stays case-sensitive (unchanged). PowerShell: DECIDED case-insensitive at both sites (the working-map site already is; the committed-map site becomes so, which can only add matches).
- U5 Version: next free crew patch past origin/main at implement time, in both version files.

## Open questions for the owner
1. Reverse test dropped outright (taken, recommended), or replaced by a token rule that still matches a shortened command?
2. The `-like` to literal change in `promote-gate.ps1` rides here because it is the same line (taken, recommended), or is split into its own ticket?
3. A marker left by the old rule: documented only (taken, recommended), or should the gate clear a marker whose sha has no deploy evidence? The second touches `verify-gate.*`, which is harness and would be a separate tooling-only PR.

## Size
About 25 production lines: two one-line conditions and their comments in `promote-gate.sh`, two conditions folded into one small helper in `promote-gate.ps1`. Well under 300, so no split. Tests about 150 lines.

## Touch
- `plugin/crew/hooks/scripts/promote-gate.sh` - the conditions at :140 and :213 and the comment at :211-212
- `plugin/crew/hooks/scripts/promote-gate.ps1` - the conditions at :90 and :134, one literal containment helper
- `plugin/crew/tests/test_promote_gate_match.py` - new, both flavours: reproduction, must-allow, must-block
- `plugin/crew/tests/promote_tree_mutations.py` - new entries
- `plugin/crew/hooks/scripts/_test/run-tests.sh` - only if a fragment case belongs in the shell suite too
- `plugin/crew/README.md` - the match rule and the breaking-change note
- `plugin/crew/CONFIG.md` - only if it states the match rule
- `plugin/crew/commands/promote.md` - the Enforced-by paragraph
- `plugin/crew/.budget-allowance.json` - only if promote.md does not fit its ceiling
- `plugin/crew/skills/crew-verification/SKILL.md` - the deploy row and the limitation paragraph
- `plugin/crew/skills/crew-setup/phases.md` - the sentence at :439
- `plugin/crew/BUDGETS.md` - counts
- `plugin/PLUGINS.md`
- `INSTALLATION.md`
- `docs/guides/crew/**` - src/troubleshooting.md gets a false DEPLOY NOT RECORDED entry, plus the rebuilt HTML, DOCX and PDF
- `.crew/verify.json` - only if the new test file is not already covered by the test_promote glob
- `.crew/codemap/**` - refreshed
- `.claude/rules/**` - refreshed
- `docs/diagrams/**` - refreshed
- `graphify-out/**` - refreshed
- `CHANGELOG.md`
- `TODO.md`
- `plugin/crew/.claude-plugin/plugin.json` - version
- `.claude-plugin/marketplace.json` - version

## Acceptance checks
Fixture map for every case, committed in a throwaway repository with a clean tree: `development.deploy = "gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)"`, `rollback: "none"`, `rollbackReason: "fixture"`; `production.deploy` the same text with `environment=production`, `requires: ["development"]`.
Suite: `python3 -m pytest plugin/crew/tests/test_promote_gate_match.py -q` (rule `.crew/verify.json:122-135`).
- [ ] FIRST, before any edit, reproduce on origin/main's script: in the fixture repository run `printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git rev-parse HEAD"},"cwd":"'"$PWD"'"}' | CLAUDE_PROJECT_DIR="$PWD" bash <repo>/plugin/crew/hooks/scripts/promote-gate.sh; echo "exit=$?"; cat .crew/.deploy-in-flight`. Expected on the unfixed script: exit 0 and the file reads `development <short sha>`. Record the output verbatim in the PR. If no marker appears, stop (U1).
- [ ] The new test `test_a_fragment_of_a_declared_deploy_is_not_a_deploy` fails on origin/main's scripts and passes after the change, in both flavours: `python3 -m pytest plugin/crew/tests/test_promote_gate_match.py -q -k fragment`
- [ ] Must-allow, exit 0 and no `.crew/.deploy-in-flight`, both flavours: `git rev-parse HEAD`; `HEAD`; `development`; `echo development`; `gh workflow run`; `gh workflow run --help`; `gh workflow run deploy.yml`; `-f environment=development`. Command: the suite above, `-k must_allow`
- [ ] Must-allow with the working map dirty (an uncommitted edit that renames the deploy): `git rev-parse HEAD` still exits 0 with no marker, so the committed-map site (`:140`, `.ps1:90`) is covered too. Command: the suite above, `-k committed`
- [ ] Must-block: the production deploy text run verbatim with no development PASS row: exit 2, stderr names `production`. Command: the suite above, `-k must_block`
- [ ] Still gated: the development text verbatim; with ` --verbose` appended; and as `cd <worktree> && <declared>`: each exit 0 and the marker reads `development <sha>`. Command: the suite above, `-k still_gated`
- [ ] PowerShell literal match (U3): a map declaring `gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches -f 'inputs[environment]=production'` with an unmet `requires`, run verbatim on the `ps1` flavour: exit 2. And a declared `Deploy-App prod` run as `deploy-app prod`: exit 2. Command: the suite above, `-k literal`
- [ ] On a machine without PowerShell 7 the `ps1` cases skip and never fail: `python3 -m pytest plugin/crew/tests/test_promote_gate_match.py -q -rs`
- [ ] The existing suites pass with no edit to their assertions: `python3 -m pytest plugin/crew/tests/test_promote_gate_effective_tree.py plugin/crew/tests/test_promote_gate_fails_closed.py plugin/crew/tests/test_promote_gate_unreadable_map.py plugin/crew/tests/test_gates_powershell.py -q` and `bash plugin/crew/hooks/scripts/_test/run-tests.sh`
- [ ] Mutations, each RED on a named test in the new file: `or cmd in d` put back at `promote-gate.sh:213`; put back at `:140`; the reverse test put back at each `.ps1` site; `-like` put back at the `.ps1` working-map site. Command: `cd plugin/crew/tests && python3 -c "import sabotage, promote_tree_mutations as m; sabotage.MUTATIONS = m.PROMOTE_TREE_MUTATIONS; raise SystemExit(sabotage.main())"`
- [ ] No reverse test is left: `git grep -n -E "cmd in d|dep\.Contains\(\\\$cmd\)|dep -like" -- plugin/crew/hooks/scripts/promote-gate.sh plugin/crew/hooks/scripts/promote-gate.ps1` prints nothing.
- [ ] The harness is untouched: `git diff --name-only origin/main...HEAD -- plugin/crew/hooks/scripts/verify-gate.sh plugin/crew/hooks/scripts/verify-gate.ps1 "plugin/crew/tests/sabotage*.py"` prints nothing, and `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] The PowerShell static check passes: the `.crew/verify.json:249-251` rule (`scripts/check-powershell.ps1`).
- [ ] Docs state: a command is a deploy when it contains the declared text; a fragment is not; declare the shortest text every real run contains (breaking change, U2); a "DEPLOY NOT RECORDED" for a sha with no deploy run on an older crew is this bug. Command: `git grep -n -i "contains the declared" -- plugin/crew/README.md plugin/crew/commands/promote.md plugin/crew/skills/crew-verification/SKILL.md docs/guides/crew/src/troubleshooting.md` prints a line from each.
- [ ] Version bumped in both files and the gate is green after the commit: `python3 scripts/check-marketplace.py`; crew suite `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"` then `-m wallclock`; pylint and ruff with no new findings.

## Dependencies
Must land first: none. This ticket needs nothing that is not on origin/main `baf193aa`.
- T-0505 - merged (#296). The effective-tree gate; the code this edits.
Same files, no required order. Whichever lands second merges main and re-checks its anchors:
- T-0062 (draft PR #467) - edits the same two lines' surroundings in `promote-gate.sh` (it adds a helper call after "containment matched nothing") and says the containment match "stays first and unchanged". After this ticket, read that as "the containment match as L-0689 left it". T-0062 is blocked on T-0009; this ticket is not, so this one is expected to land first.
- L-0664 (draft PR #471) - the same for `promote-gate.ps1`, after T-0062.
- L-0665 (draft PR #473) - `passed()` in both flavours; different lines.
- L-0648 (draft PR #445) - reads the `github` entry after a match, both flavours; different lines, but its "longest substring of the command" rule runs only for a command this ticket's rule matched.
- T-0009 (PR #336, open) - does not touch `promote-gate.*` at `f08ae7fb`; it changes `.crew/verify.json`, which is in Touch here only conditionally.
Recommended order: L-0689, then the others in their own order (T-0009, T-0062, L-0664; L-0665 and L-0648 any time). Reason: T-0062's and L-0648's must-allow lists (`gh workflow run deploy.yml --help`, `echo done`, no marker) are easier to hold once fragments no longer match.
This ticket blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
