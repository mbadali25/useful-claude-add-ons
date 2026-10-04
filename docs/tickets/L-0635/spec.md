# L-0635: sabotage mutations for cross-session contracts and dependencies (tooling PR)          status: spec   risk: med
Split from T-0031. Written 2026-10-04 against origin/main 155fe6d8 (crew 1.0.322). This is a tooling PR under the rule in the repo CLAUDE.md ("A change to the review/gate harness lands alone").
## Intent
Every fail-closed branch added by T-0031, L-0633 and L-0634 has a mutation that removes it and a named test that goes red when it is removed. The mutations live in a new `plugin/crew/tests/sabotage_contract.py` and are registered in `plugin/crew/tests/sabotage.py`.
## Exclusions
- No production code and no prompt: nothing under `plugin/crew/hooks/`, `plugin/crew/commands/`, `plugin/crew/agents/`, `scripts/` or `skills/`. If a mutation shows a guard does not hold, the fix is a new feature ticket, not an edit here.
- No change to `sabotage_coord.py` or `sabotage_wave.py` (T-0030's and T-0029's own modules) beyond what registering a new module in `sabotage.py` needs.
- No new test of behaviour. Where a mutation finds no test that goes red, the missing test is reported as a finding for the owning slice. A test file may be touched here only to add that missing must-block case.
- No change to the mutation runner's own logic in `sabotage.py`; only the import and the `MUTATIONS +=` line.
## Evidence
At origin/main 155fe6d8, checked 2026-10-04:
- `scripts/check-tooling-pr.py:79` lists `plugin/crew/tests/sabotage*.py` in `HARNESS` (`:58-87`); the module docstring (`:6-14`) says tests, docs, version files, code map, graph and ticket records may ride along and production code may not.
- The registry: `plugin/crew/tests/sabotage.py:67-88` imports one tuple per area module (for example `:71` `from sabotage_scope import SCOPE_MUTATIONS`), `:205` `MUTATIONS = (`, `:3064` `MUTATIONS += (...)`.
- 22 area modules exist under `plugin/crew/tests/sabotage_*.py`; none is `sabotage_contract.py`, `sabotage_coord.py` or `sabotage_wave.py` on main.
- `plugin/crew/tests/test_sabotage_harness.py` exists and pins the runner.
- `.pylintrc:140` `max-module-lines=3400`; `sabotage.py` is over 3000 lines, which is why new mutations go in an area module.
- The repo CLAUDE.md, "Stop and ask": a guard that can block "needs a committed regression suite with must-block and must-allow cases, sabotage-tested".
## Unknowns
- **The exact source lines to mutate do not exist yet.** Each mutation is anchored on a line of the landed feature code. Resolved at plan, after the three feature PRs merge.
- **Whether the harness rule's own suite needs the new module listed.** `.crew/verify.json`'s harness rule lists `HARNESS`, `SEAM` and its suites, and a test keeps that list in step. Resolved at plan by running `python3 scripts/check-tooling-pr.py` and the tooling suite on the branch.
- **Running the sabotage suite is heavy.** It goes through the gate runner's heavy-run path on a host with enough memory, never as several copies at once.
## Dependencies
Must land first:
- T-0031 (ready) - `crew_contract.py` and its must-block tests.
- L-0633 - the dependency parser in `crew_wave.py`.
- L-0634 - `check_bindings` and the wave refusal.
- T-0030 and T-0029 (both in-progress) - through the three above.

Blocks: nothing. T-0032 does not wait for it.
## Touch
- `plugin/crew/tests/sabotage_contract.py`
- `plugin/crew/tests/sabotage.py` - the import and the registration line only
- `plugin/crew/tests/test_crew_contract.py` - only to add a must-block case a mutation shows is missing
- `plugin/crew/tests/test_crew_contract_verify.py` - same
- `plugin/crew/tests/test_crew_wave_coord_deps.py` - same
- `plugin/crew/README.md` - the sabotage count or list, if the README states one
- `plugin/crew/BUDGETS.md` - the crew-markdown-lines claim
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/verify.json` - list the new module where the harness rule requires it
- `.crew/codemap/verification-harness.md`
## Acceptance checks
- [ ] `sabotage_contract.py` exports `CONTRACT_MUTATIONS`, registered in `sabotage.py`. Each mutation names the test it must turn red. Contract record (T-0031): let `put` overwrite a `built-against` version; let `build-against` run without an approved ticket; skip the body-hash comparison in `build-against`; read a corrupt record as absent; add `--force-with-lease` to the push; let `put --new-version` run on a `draft` predecessor.
- [ ] Dependencies (L-0633): read a missing peer claim as closed; read a `working` claim as closed; read a `released` claim as closed; read a failed fetch as closed; take the first of two same-id claims instead of refusing; read a malformed cross dependency as no dependency.
- [ ] Hash refusal (L-0634): drop the record-hash comparison; drop the body-hash comparison; read a corrupt bindings file as no bindings; read a failed fetch as a pass; drop the wave's call to `check_bindings`.
- [ ] Every anchor is present exactly once in its target file: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_sabotage_harness.py -q` passes, with a test for the new module's anchors if the harness test does not already cover every registered module.
- [ ] Each mutation goes red when run through the runner, restricted to the new module's mutations (the runner's selection option is read from `sabotage.py` at plan time; it is run through the gate runner's heavy-run path). The count of red mutations equals the count registered; a mutation that stays green is a finding, not a pass.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 on the branch: the only changed paths are harness, tests, docs and version files. `python3 scripts/_test/tooling-pr.py` passes, as `.crew/verify.json`'s harness rule runs it (origin/main `.crew/verify.json:469-470`).
- [ ] Crew is one patch above origin/main in `plugin.json` and `marketplace.json`, with a CHANGELOG entry and the `plugin/PLUGINS.md` row; `python3 scripts/check-marketplace.py` passes after the commit. The PR body says `Docs:` and lists what changed, or `Docs: none - <why>`.
## Size
0 production lines. About 170 lines of mutations in `sabotage_contract.py` and 2 lines in `sabotage.py`.
## Open questions for the owner
1. One tooling PR after all three slices (taken), or one after each?
2. May this PR add a missing must-block test to the three feature test files, as Touch allows, or should every gap go back to its slice as a new ticket?

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
