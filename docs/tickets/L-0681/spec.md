# L-0681: the verify gate, scope and completion wrappers and review gate inherit the main checkout's repo config in a linked worktree          status: spec   risk: high
Split from T-0096 on 2026-10-04 (slice 2 of 2 further slices). Written against origin/main `155fe6d8` (crew 1.0.322). Needs T-0096 merged first. **Tooling PR: lands alone, no feature work** (project CLAUDE.md owner rule 2026-09-28).

## Intent
In a linked git worktree with no crew config of its own, the verify gate (both flavours), `review_gate.py`, `verify_fingerprint.py` and the no-python fallbacks of the scope guard and completion audit wrappers read the main checkout's `.crew/config.json`, by the same rules as `crew_common.repo_config_dir`. The gate and the review gate move in one commit so they never disagree about a stand-down. With no python, a lane is "provably off" only when the resolved config is absent and git could tell; `unknown` blocks. After this slice no shell, PowerShell or Python reader of the repo config is outside a resolver, and the docs' "not yet covered" note is removed.

Risk is `high`: it changes when the gate runs and when two blocking guards block, in every lane.

## Exclusions
- **No file outside `HARNESS` and `ALONGSIDE`** (scripts/check-tooling-pr.py:58-118). In particular not `_common.sh`, `cloud-guard.*`, `promote-gate.*`, `auto-clear.*`, the session hooks, `crew_common.py`, `crew_status.py` or any command file other than those in `HARNESS`. No `Tooling-seam:` trailer is expected; if a `SEAM` file turns out to need an edit, stop and amend this spec first.
- `.crew/verify.json` is not inherited: a lane with no verification map still has no gate (`review_gate.py:123-125` stays).
- The gate's markers, lock, record and tree cache stay in the worktree's own `.crew/`.
- No change to what `scope_guard.py`, `completion_audit.py` or `crew_ticket.configured_mode` decide; they are already routed. Only the wrappers' no-python proof changes.
- No change to the incident file's location or format, to `verify_record.py`, `verify_price.py`, the review ledger, the reviewer prompt, `commands/review.md` or the golden corpus.
- `scope-guard.ps1`'s strict System.Text.Json proof of `scope.mode: off` is kept as it is; it is pointed at the resolved file, not rewritten.
- No bash resolver change: `crew_repo_config_dir` in `_common.sh` is used as T-0096 landed it.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04. Paths are under plugin/crew/hooks/scripts/ unless given in full.
- verify-gate.sh:160 `cd "${CLAUDE_PROJECT_DIR:-.}"`, :164-170 the `verifyGate` grep and the `--ci` exit 2. :988-998 the embedded python reads `.crew/config.json` (:993) for `verify.stopBudgetSeconds`, default 60.
- verify-gate.ps1:398-399 why the incident function is inline; :402-410 `Test-CrewIncidentActive`, config read at :405; :510-518 `verifyGate`; :1363-1366 the budget.
- review_gate.py:121-129 `_gate_state`: `verify.json` absent is NO_GATE (:123-125), then `config = _read(os.path.join(root, ".crew", "config.json"))` at :126 and `_STOOD_DOWN_RE`.
- verify_fingerprint.py:38 and :80: the own `.crew/config.json` is a fingerprint input because it carries the Stop budget.
- scope-guard.sh:26-30 and completion-audit.sh:24-28 `_scope_provably_off`: `${CLAUDE_PROJECT_DIR:-$PWD}/.crew/config.json`, absent means provably off. Callers scope-guard.sh:33 and :45. scope-guard.ps1:221 and completion-audit.ps1:220 `Test-ScopeProvablyOff`, path at :224 and :223.
- crew_ticket.py:658: `configured_mode` reads through `crew_common.repo_config_file` (routed), so the Python guard and its wrapper disagree in a lane today.
- plugin/crew/tests/test_review_gate.py:158-170 `test_a_lane_follows_its_own_gate_not_the_main_checkouts_stand_down`: main `{"verifyGate": false}`, lane gate red, asserts exit 2 and UNVERIFIED. Its comment: "When T-0096 lands, this test goes red: flip it and route both together."
- plugin/crew/tests/test_worktree_config.py:199-224 `ALLOWED`: `"verify_fingerprint.py": (1, ...)` and `"review_gate.py": (1, "mirrors verify-gate.sh's own-file stand-down read (T-0096)")`. :263 `test_no_module_reads_repo_config_outside_the_resolver`.
- plugin/crew/tests/test_completion_audit.py:603-618 `_sh_function`, `_ps_function` and `test_the_provably_off_readers_are_byte_for_byte_twins`.
- plugin/crew/tests/sabotage_limit_worktree.py:1-27: T-0088's mutation table, `(label, target, find, replace, test)`, appended to `sabotage.py`'s.
- scripts/check-tooling-pr.py:58-87 `HARNESS` lists every production file in Touch below; :99-118 `ALONGSIDE` lists every other path in Touch.
- .crew/verify.json:456-471: the harness rule runs `python3 scripts/check-tooling-pr.py`, `scripts/_test/tooling-pr.py`, and `test_review_golden.py`, `test_review_contracts.py`, `test_review_canary.py`.
- Docs: plugin/crew/README.md:1027-1029, plugin/crew/CONFIG.md:147-148, docs/guides/crew/src/troubleshooting.md:234-236.

## Unknowns
- **Loosening by an inherited `verifyGate: false`** (direction question 1). Default taken; stated in README as a behaviour change.
- **`unknown` blocks without python** (question 2). Default taken.
- T-0096's landed names (`crew_repo_config_dir`, `CREW_CFG_DIR`, `CREW_CFG_SOURCE`, `Get-CrewRepoConfigDir`). Resolved by reading merged main before planning.
- **Whether `scope-guard.sh` and `completion-audit.sh` have sourced `_common.sh` before `_scope_provably_off` is defined and called.** Checked: scope-guard.sh:15 and completion-audit.sh:14 both source it before the function is defined. Nothing left to resolve.
- **The fingerprint changes for an inheriting lane.** `verify_fingerprint.py` will hash the main checkout's config, so the first gate run in each lane after the upgrade re-runs its commands once. Accepted as risk: it re-runs, it never credits a stale pass.
- `plugin/crew/tests/sabotage.py` is at the pylint module-line limit (3400). Mutations go in `sabotage_limit_worktree.py`, not in `sabotage.py`.
- Windows PowerShell 5.1 has no System.Text.Json (scope-guard.ps1:217-219): a present resolved config fails closed there, as the own one does today. Unchanged; accepted.

## Touch
- `plugin/crew/hooks/scripts/verify-gate.sh`
- `plugin/crew/hooks/scripts/verify-gate.ps1`
- `plugin/crew/hooks/scripts/review_gate.py`
- `plugin/crew/hooks/scripts/verify_fingerprint.py`
- `plugin/crew/hooks/scripts/scope-guard.sh`
- `plugin/crew/hooks/scripts/scope-guard.ps1`
- `plugin/crew/hooks/scripts/completion-audit.sh`
- `plugin/crew/hooks/scripts/completion-audit.ps1`
- `plugin/crew/tests/test_worktree_config_shell.py`
- `plugin/crew/tests/test_worktree_config.py` - the two ALLOWED entries go
- `plugin/crew/tests/test_review_gate.py` - the pinned lane test is flipped
- `plugin/crew/tests/test_completion_audit.py` - only if the twin assertion needs the new helper
- `plugin/crew/tests/sabotage_limit_worktree.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/crew-1.0-troubleshooting.html`
- `docs/guides/crew/crew-1.0-troubleshooting.docx`
- `docs/guides/crew/crew-1.0-troubleshooting.pdf`
- `.crew/verify.json` - add these scripts to the shell worktree-config rule
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `.crew/codemap/INDEX.md`
- `.claude/rules/**` - regenerated
- `docs/diagrams/data-flow-crew-config-no-python.mmd`
- `docs/diagrams/process-qa-gates.mmd`
- `docs/diagrams/index.html`
- `graphify-out/**` - by graphify update only

Estimated production lines added: about 125 (three PowerShell copies at about 28 each, bash edits about 25, Python about 10, PowerShell reader edits about 10). One PR.

## Acceptance checks
Each test builds a throwaway repository and a `git worktree add` lane under `tmp_path`.
Command for the new tests: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_worktree_config_shell.py plugin/crew/tests/test_review_gate.py plugin/crew/tests/test_worktree_config.py -q` (heavy: through heavy-run).
- [ ] Gate and review gate agree, flipped. `test_a_lane_inherits_the_main_checkouts_stand_down` replaces the pinned test in `test_review_gate.py`: main `{"verifyGate": false}`, lane with a red `verify.json` rule and no config: `verify-gate.sh` exits 0 and `review_gate.gate_state` is NO_GATE. With `--ci`, exit 2. A PowerShell twin case asserts the same for `verify-gate.ps1`.
- [ ] Must-block. `test_a_lane_with_its_own_config_keeps_its_gate[sh|ps1]`: same main, the lane's own `config.json` is `{}`: the red rule blocks (exit 2) and the state is UNVERIFIED.
- [ ] Must-block. `test_gate_is_not_stood_down_when_git_cannot_tell[sh|ps1]`: `.git` a file naming a missing directory: the gate runs and blocks; `gate_state` is not NO_GATE by reason of a config.
- [ ] `test_stop_budget_is_inherited[sh|ps1]`: main `verify.stopBudgetSeconds: 0`, lane with one rule priced above 0: the rule is deferred exactly as it is in the main checkout.
- [ ] `test_fingerprint_follows_the_resolved_config`: changing the main checkout's `config.json` changes the lane's fingerprint; changing it when the lane has its own config does not.
- [ ] `test_verify_gate_ps1_incident_stand_down_false_is_inherited`: main `emergency.standDown: false`, lane with an unexpired incident: the PowerShell gate still gates.
- [ ] Must-block, no python. `test_scope_wrapper_without_python_blocks_in_a_lane_whose_main_checkout_has_a_config[scope-guard.sh|completion-audit.sh|scope-guard.ps1|completion-audit.ps1]`: red on origin/main (exit 0 today), exit 2 after.
- [ ] Must-block, no python. `test_scope_wrapper_without_python_blocks_when_git_cannot_tell[...]`, same four.
- [ ] Must-allow, no python. `test_scope_wrapper_without_python_allows_when_no_checkout_has_a_config[...]`: a lane whose main checkout has no config, and a plain repository with none: exit 0, as today. And, PowerShell 7 only, a lane whose main checkout is strictly `{"scope":{"mode":"off"}}`: allowed.
- [ ] `test_the_provably_off_readers_are_byte_for_byte_twins` still passes, and `test_powershell_resolver_copies_are_identical` covers the three new copies.
- [ ] `test_no_module_reads_repo_config_outside_the_resolver` passes with the `review_gate.py` and `verify_fingerprint.py` entries removed from `ALLOWED`. New `test_no_hook_script_names_the_own_config_path`: across every `.sh` and `.ps1` in `plugin/crew/hooks/scripts/`, executable lines naming `.crew/config.json` or `.crew/crew.json` outside the resolver match an explicit allowlist with counts (writers and message strings). If L-0680 has not landed, its eight scripts are in that allowlist with the reason L-0680.
- [ ] Sabotage. New rows in `sabotage_limit_worktree.py`, each red against a named test above: the bash resolver returns `own` for a `.git` file; the resolver prefers main over own; `unknown` reads as provably off; `unknown` reads as not armed in `_cloud_guard_armed`; `review_gate.py` routed while `verify-gate.sh` is not (the pair split). Command: `python3 plugin/crew/tests/sabotage.py` (heavy: through heavy-run; the cloud session runs it, not this host).
- [ ] Tooling PR alone: `python3 scripts/check-tooling-pr.py` exits 0, and the harness rule's suites pass: `python3 scripts/_test/tooling-pr.py` and `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_golden.py plugin/crew/tests/test_review_contracts.py plugin/crew/tests/test_review_canary.py -q`.
- [ ] Unchanged outside a lane: the `test_verify_gate_*.py`, `test_scope_guard.py`, `test_completion_audit.py` and `test_gates_powershell.py` suites pass, and `bash scripts/_test/check-powershell.sh` passes.
- [ ] Docs, in this PR: README.md, CONFIG.md and troubleshooting.md drop the "not yet covered" note (or leave only L-0680's hooks if it has not landed); README's **Behaviour change** paragraph gains the inherited `verifyGate: false` and the no-python wrapper rule; guide html, docx and pdf rebuilt with `python3 docs/guides/crew/src/build.py`; code map, rules and diagrams refreshed.
- [ ] Version: crew bumped once past origin/main in both version files, PLUGINS.md and CHANGELOG; commit, then `python3 scripts/check-marketplace.py` exits 0.

## Dependencies
- T-0096 (direction on 2026-10-04; spec written today): must be merged first, for `crew_repo_config_dir` in `_common.sh` and the PowerShell function to copy.
- T-0088 (merged): the Python resolver and the two pins this slice removes.
- T-0087 (merged): the tooling-PR rule and the harness rule's suites.
- Blocks nothing. Independent of L-0680; either order.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
