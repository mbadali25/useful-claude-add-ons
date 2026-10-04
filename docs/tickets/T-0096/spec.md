# T-0096 a shell config resolver, and the guard-class shell readers outside the harness inherit the main checkout's repo config          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket; there was no direction.md, spec.md or plan.md before today. Written against origin/main `155fe6d8` (crew 1.0.322) with the owner unavailable, so every choice below is the recommended default from direction.md and its four open questions are repeated under Unknowns.

- **Narrowed to slice 0 of three.** The INDEX title says "the 9 shell and PowerShell config readers". At origin/main the unrouted readers are in 19 files plus `review_gate.py` (direction.md lists every site). Six of those files and `review_gate.py` are review/gate harness paths, which must land alone. This spec covers the resolver and the guard-class readers outside the harness. The rest is in `children/1` (session hooks) and `children/2` (harness readers, a tooling PR).
- **No plan.md exists.** Nothing to reconcile.

## Intent
In a linked git worktree with no crew config of its own, the shell and PowerShell hooks read the main checkout's `.crew/config.json`, by the same rules as `crew_common.repo_config_dir`: the worktree's own files win whole, the two are never merged, and when git cannot name the main checkout the source is `unknown` and nothing is inherited. This slice adds the resolver in both flavours and routes the readers outside the review/gate harness that decide whether a guard acts: the incident stand-down read in `_common.sh` and `promote-gate.ps1`, the cloud guard's no-python fallback in both flavours, and `auto-clear.ps1`'s repo veto. In the cloud guard's fallback, `unknown` counts as armed, so a lane no longer passes commands unjudged because its own config file is absent.

Risk is `high`: the change moves what guards read in every lane worktree, and it can loosen (an inherited `cloudGuard: off`) as well as tighten.

## Exclusions
- **No harness path.** Not `verify-gate.sh`, `verify-gate.ps1`, `scope-guard.sh`, `scope-guard.ps1`, `completion-audit.sh`, `completion-audit.ps1`, `review_gate.py`, nor any `plugin/crew/tests/sabotage*.py` (all in `HARNESS`, scripts/check-tooling-pr.py:58-87). Those are L-0681. `test_a_lane_follows_its_own_gate_not_the_main_checkouts_stand_down` and the `review_gate.py` allowlist entry stay exactly as they are and stay green.
- **No session hook.** `notify`, `handoff-read`, `handoff-write` and `context-watch`, both flavours, are L-0680.
- No change to `crew_common.py` or any Python reader. The Python resolver is the reference; the shell ones are made to agree with it.
- No writer follows the resolver. Markers, logs, transcripts and `.crew/incident.json` stay in the worktree's own `.crew/`. Only reads of `config.json` (and `crew.json` where a reader already reads it) move.
- The `.crew/` **directory** gates are unchanged (`auto-clear.sh:87`, `auto-clear.ps1:101`).
- No merge of the two checkouts' configs, no copy of the main checkout's config into the lane, no new config key, no new hook, no `hooks.json` edit.
- The machine-global layer (`~/.claude/crew/config.json`) is read exactly as today.
- No inline `.crew/config.json` reads in `plugin/crew/commands/*.md` or `plugin/crew/skills/**` prose are rewritten; `skills/crew-setup/scripts/detect.sh` and `skills/crew-graph/scripts/crew_upgrade.py` are setup-time writers' helpers and are not touched.
- `verify-gate.ps1:402-410` keeps its own inline `Test-CrewIncidentActive` reading the own file until L-0681. Between this slice and L-0681, the bash gate (through `_common.sh`) and `crew_incident.py` read the inherited `emergency.standDown` while the PowerShell gate reads the own file. That is named in the docs this slice edits.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_common.py:92-93 `CONFIG_NAMES`, `SOURCE_OWN`/`SOURCE_MAIN`/`SOURCE_UNKNOWN`. :96-126 `repo_config_dir(root)`: own `.crew/` when it holds either config name (`os.path.lexists`); else `_main_checkout`; `unknown` returns the own directory. :129-150 `_main_checkout`: `.git` not a file means not a linked worktree, with no subprocess; `git rev-parse --git-dir --git-common-dir`, exactly two lines or `unknown`; both joined to `root` and real-pathed; equal paths (submodule) or a common directory not named `.git` (bare) means own. :175-177 `repo_config_file`.
- plugin/crew/hooks/scripts/_common.sh:339-341 `crew_incident_active` greps `"standDown": false` in `.crew/config.json` relative to the cwd. :59 `crew_py`, :141 `crew_py_strict`. No worktree resolver exists in the file.
- plugin/crew/hooks/scripts/crew_incident.py:433 reads the same key through `crew_common.repo_config_file` (routed).
- plugin/crew/hooks/scripts/promote-gate.ps1:144-147 says why the PowerShell twins are inline (a dot-sourced function is invisible to `scripts/check-powershell.ps1`'s static call check). :148-158 `Test-CrewIncidentActive`, config read at :151. `promote-gate.sh` has no config read of its own; it calls `crew_incident_active`.
- plugin/crew/hooks/scripts/cloud-guard.sh:35-45 `_cloud_guard_armed`: loops over `$root/.crew/config.json` and the machine-global file, `[ -f "$cfg" ] || continue`. Called at :49 and :64, only when python could not run or judge. plugin/crew/hooks/scripts/cloud-guard.ps1:192-210 `Test-CloudGuardArmed`, the twin, paths at :199-200.
- plugin/crew/hooks/scripts/cloud_guard.py:3169 `resolve_mode`, repo path through `repo_config_file` at :3178 (routed).
- plugin/crew/hooks/scripts/auto-clear.ps1:146 `$repoCfg = Read-CrewJsonFile ".crew/config.json"`. plugin/crew/hooks/scripts/auto-clear.sh has no config read; its decision comes from plugin/crew/hooks/scripts/crew_autocycle.py:154 (routed).
- plugin/crew/tests/test_worktree_config.py:39-46 `_lane(tmp_path, main_cfg)`, :182 `test_cloud_guard_reads_the_inherited_layer`. plugin/crew/tests/test_completion_audit.py:615-616 is the existing "two shell copies are identical" assertion to copy.
- Docs that state the gap: plugin/crew/README.md:1027-1029, plugin/crew/CONFIG.md:147-148, docs/guides/crew/src/troubleshooting.md:234-236 (and the built docs/guides/crew/crew-1.0-troubleshooting.html:387). CONFIG.md:114-135 is the resolution order to extend.
- .crew/verify.json:406-411 is the rule that runs `test_worktree_config.py` (its paths also name `review_run.py` and `review_limit.py`, so it is left alone); :147-156 the cloud-guard rule; :115 `bash scripts/_test/check-powershell.sh`.
- scripts/check-tooling-pr.py:58-87 `HARNESS`: `_common.sh`, `cloud-guard.*`, `promote-gate.*` and `auto-clear.*` are not in it, so this slice is a feature PR.
- Nothing on main does this: `git grep -n "repo_config" origin/main -- 'plugin/crew/hooks/scripts/*.sh' 'plugin/crew/hooks/scripts/*.ps1'` prints nothing.

## Design
- **bash, in `_common.sh`:** `crew_repo_config_dir [root]` sets `CREW_CFG_DIR` and `CREW_CFG_SOURCE` (`own`, `main` or `unknown`); `root` defaults to the cwd. No python. Steps as crew_common.py:96-150: own `.crew/` holds `config.json` or `crew.json` (`-e` or `-L`) gives `own`; `.git` not a regular file gives `own` with no git call; otherwise `git rev-parse --git-dir --git-common-dir` (no `--path-format`), exactly two lines or `unknown`; each resolved with `cd ... && pwd -P` from `root`, a failure is `unknown`; equal paths or a basename other than `.git` gives `own`; the parent's `.crew/` holding either file gives `main`; else `own`. On `unknown`, `CREW_CFG_DIR` is the own `.crew/`. `crew_repo_config_file [name]` prints `$CREW_CFG_DIR/<name>`.
- **PowerShell:** one function, `Get-CrewRepoConfigDir`, returning the directory and the source, copied verbatim into `cloud-guard.ps1`, `promote-gate.ps1` and `auto-clear.ps1`. Path comparison is case-insensitive on Windows only.
- **Readers.** `crew_incident_active` and `promote-gate.ps1`'s `Test-CrewIncidentActive` read `standDown` from the resolved file; `.crew/incident.json` stays own. `_cloud_guard_armed` / `Test-CloudGuardArmed` read the resolved repo file, and return armed when the source is `unknown`. `auto-clear.ps1` reads `$repoCfg` from the resolved file.

## Unknowns
- **`unknown` is armed in the cloud guard's no-python fallback** (direction.md question 1). Default taken. A lane with broken git and no python refuses Bash until one works. Owner may reverse; the test for it is one parametrised case.
- **Directory gates unchanged** (question 2). Default taken; accepted as risk for repos whose lanes have no `.crew/` directory.
- **Three PRs** (question 3). Default taken.
- **Symlinked `.git` paths on Windows PowerShell 5.1.** `pwd -P` and `os.path.realpath` resolve symlinks; 5.1 has no equivalent call. Resolved at plan time: the parity test below runs under `pwsh` on Linux and on the Windows CI leg; if 5.1 differs on a symlinked common directory it must read `unknown`, never `main`. Accepted as risk beyond that.
- **No git timeout in bash.** Python uses `GIT_TIMEOUT`; `timeout(1)` is not on every Git Bash. Accepted as risk: `git rev-parse` reads two files and does not touch the network.
- **Line numbers move.** Other lanes edit these hooks. Re-read every cited site on the build branch's base before planning.
- **Sabotage has to be by hand.** `plugin/crew/tests/sabotage*.py` are harness paths, so this feature PR cannot add mutations. The must-block cases are sabotage-tested by hand (Acceptance) and the mutations are added to `sabotage_limit_worktree.py` by L-0681.

## Touch
- `plugin/crew/hooks/scripts/_common.sh` - the resolver and the stand-down read
- `plugin/crew/hooks/scripts/cloud-guard.sh`
- `plugin/crew/hooks/scripts/cloud-guard.ps1`
- `plugin/crew/hooks/scripts/promote-gate.ps1`
- `plugin/crew/hooks/scripts/auto-clear.ps1`
- `plugin/crew/tests/test_worktree_config_shell.py` - new
- `plugin/crew/tests/test_cloud_guard.py` - only if an existing no-python case needs the resolver's fixture
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
- `.crew/verify.json` - one new rule mapping the five scripts and the new test file to the new test file, priced from a measured run
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `.crew/codemap/INDEX.md`
- `.claude/rules/**` - regenerated
- `docs/diagrams/data-flow-crew-config-read.mmd`
- `docs/diagrams/data-flow-crew-config-no-python.mmd`
- `docs/diagrams/index.html`
- `graphify-out/**` - by graphify update only

Estimated production lines added: about 140 (`_common.sh` 42, three PowerShell copies at about 28 each, reader edits about 15).

## Acceptance checks
Each test builds a throwaway repository and a `git worktree add` lane under `tmp_path`; none reads the real repository's config. bash cases are skipped with a stated reason where bash is absent, PowerShell cases where `pwsh` is absent.
- [ ] Parity, bash. `test_bash_resolver_agrees_with_python[<case>]` in `test_worktree_config_shell.py`: for each of main checkout; lane with no config; lane with own `config.json`; lane with own `crew.json` only; lane whose main checkout has no config; submodule; worktree of a bare repository; `.git` a file naming a missing directory (unknown); a lane with a space in its path, the pair `CREW_CFG_SOURCE`, real path of `CREW_CFG_DIR` equals `crew_common.repo_config_dir`'s source and directory. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_worktree_config_shell.py -q`.
- [ ] Parity, PowerShell. `test_powershell_resolver_agrees_with_python[<case>]`, same matrix, the function extracted from `cloud-guard.ps1`. Same command.
- [ ] `test_powershell_resolver_copies_are_identical`: the `Get-CrewRepoConfigDir` text in `cloud-guard.ps1`, `promote-gate.ps1` and `auto-clear.ps1` is byte-identical.
- [ ] Must-block. `test_cloud_guard_without_python_is_armed_by_the_main_checkouts_config[sh|ps1]`: main checkout `guards.cloudGuard: block`, lane with no config, PATH with no python: the hook refuses (the exit code the existing no-python armed case asserts). Red on origin/main.
- [ ] Must-block. `test_cloud_guard_without_python_is_armed_when_git_cannot_tell[sh|ps1]`: `.git` a file naming a missing directory, no python: refuses.
- [ ] Must-allow. `test_cloud_guard_without_python_follows_the_lanes_own_off[sh|ps1]`: main `block`, lane's own `cloudGuard: off`: allowed. And `test_cloud_guard_without_python_allows_when_no_layer_arms_it[sh|ps1]`: a lane whose main checkout has no config, and a plain main checkout with none: allowed, as today.
- [ ] `test_incident_stand_down_false_is_inherited[sh|promote-gate.ps1]`: main checkout `emergency.standDown: false`, lane with an unexpired `.crew/incident.json` and no config: `crew_incident_active` returns 1 and `promote-gate.ps1` does not stand down. With the lane's own config omitting the key: active.
- [ ] `test_auto_clear_ps1_reads_the_inherited_repo_veto`: machine-global `context.autoClear.enabled: true`, main checkout repo config `enabled: false`, lane with no config: `auto-clear.ps1` is off, the same decision `crew_autocycle.py` gives for `auto-clear.sh`.
- [ ] Unchanged outside a lane: the existing suites stay green. Commands: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_cloud_guard.py plugin/crew/tests/test_incident.py plugin/crew/tests/test_promote_gate_fails_closed.py plugin/crew/tests/test_auto_clear.py plugin/crew/tests/test_worktree_config.py plugin/crew/tests/test_review_gate.py -q` (heavy: run through heavy-run), and `bash scripts/_test/check-powershell.sh`.
- [ ] Hand sabotage, recorded in the PR body with the red test named for each: (a) make the bash resolver return `own` when `.git` is a file; (b) make `unknown` return not armed in `_cloud_guard_armed`; (c) make the resolver prefer the main checkout over an own file; (d) the same three in the PowerShell copy. Each turns at least one test above red; restore and re-run green (check the `.pyc` note in project memory does not apply: these are shell files).
- [ ] Feature PR, not tooling: `python3 scripts/check-tooling-pr.py` exits 0 and `git diff --name-only origin/main...HEAD` lists no `HARNESS` path.
- [ ] Docs, in this PR. README.md:1027-1029 and CONFIG.md:147-148: the "not yet covered" list drops `_common.sh`, `promote-gate.ps1`, `cloud-guard.ps1` and `auto-clear.ps1`, names the readers still own-file (the session hooks, the verify gate, the scope and completion wrappers, `review_gate.py`), and states the `verify-gate.ps1` stand-down divergence. CONFIG.md "In a linked worktree" names the shell resolver and the "unknown is armed" rule. troubleshooting.md:234-236 the same, with html, docx and pdf rebuilt by `python3 docs/guides/crew/src/build.py`. Code map, rules and the two config diagrams refreshed. `Docs:` line in the PR body lists them.
- [ ] Version. crew bumped once past origin/main in `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, PLUGINS.md and a CHANGELOG entry; commit, then `python3 scripts/check-marketplace.py` exits 0.

## Dependencies
- T-0088 (merged, crew 1.0.69): the Python resolver this mirrors and the `_lane` test helper.
- T-0087 (merged): the tooling-PR rule that forces the split.
- Blocks: L-0680 and L-0681, which both use the resolver added here.

## Split
- L-0680 (child 1 of T-0096, filed 2026-10-04): the session hooks (notify, handoff-read, handoff-write, context-watch) inherit the main checkout's repo config in a linked worktree
- L-0681 (child 2 of T-0096, filed 2026-10-04): the verify gate, the scope and completion wrappers and the review gate inherit the main checkout's repo config in a linked worktree (tooling PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
