# L-0681 plan

Written by the implementing session (H1 harness lane, 2026-10-05) against the lane head, which has
merged origin/main `a555ff37`: T-0096 (`crew_repo_config_dir`, `CREW_CFG_DIR`, `CREW_CFG_SOURCE`,
`Get-CrewRepoConfigDir`) and L-0680 are both on main, so the spec's dependency holds.

## Steps

1. `verify-gate.sh`: resolve once after the `cd` (`crew_repo_config_dir .`), export
   `CREW_REPO_CONFIG`, read `verifyGate` from it; the embedded python reads
   `verify.stopBudgetSeconds` from `$CREW_REPO_CONFIG` (an unset variable is the default budget).
2. `review_gate.py` in the same commit: `_gate_state` reads
   `crew_common.repo_config_file(root, "config.json")`. Flip
   `test_a_lane_follows_its_own_gate_not_the_main_checkouts_stand_down` into
   `test_a_lane_inherits_the_main_checkouts_stand_down` (sh and ps1, plus `--ci` exit 2), and add
   the must-block own-config and git-cannot-tell cases.
3. `verify_fingerprint.py`: hash the resolved config under the label `repo-config` (no own-path
   join left, so its `ALLOWED` entry goes; one re-run after the upgrade, never a stale pass).
4. `verify-gate.ps1`: copy `Get-CrewRepoConfigDir` verbatim; `$repoConfig` (from `$root`) for
   `verifyGate` and the budget; the inline incident check reads the resolved `standDown`.
5. `scope-guard.sh` / `completion-audit.sh`: `_scope_provably_off` resolves first; `unknown` is
   never proof; the two copies stay byte-identical. Same in both `.ps1` `Test-ScopeProvablyOff`
   (with the resolver copied in), strict System.Text.Json proof unchanged.
6. Tests in `test_worktree_config_shell.py`: the stop budget, the fingerprint, the ps1 incident,
   the four wrappers (must-block main config, must-block unknown, must-allow none, ps1 strict off),
   `PS_COPIES` gains the three new resolver copies, and
   `test_no_hook_script_names_the_own_config_path` over every `.sh` and `.ps1`.
7. `sabotage_limit_worktree.py`: `L0681_MUTATIONS` (resolver, cloud guard, wrappers, the gate pair
   split, the ps1 gate, the fingerprint), appended to `LIMIT_WORKTREE_MUTATIONS`; `sabotage.py`
   is not edited (module-line limit).
8. Docs: README (the not-yet-covered note and the behaviour change), CONFIG.md, troubleshooting
   source and its rebuilt outputs, `.crew/verify.json`'s shell worktree-config rule paths,
   CHANGELOG. Version: the lane placeholder in its last commit.
