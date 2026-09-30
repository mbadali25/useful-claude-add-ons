"""T-0505 promote-gate effective-tree mutations, in `sabotage.py`'s tuple shape.

NOT yet wired into `sabotage.py`: `scripts/check-tooling-pr.py` (owner rule,
T-0087) makes `plugin/crew/tests/sabotage*.py` harness, and a harness change
may not ride in a feature PR. So this file lives beside the tests, and a
follow-up tooling PR appends `PROMOTE_TREE_MUTATIONS` to `sabotage.py`'s
MUTATIONS. Until then run them with sabotage.py's own machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, promote_tree_mutations as m; \
        sabotage.MUTATIONS = m.PROMOTE_TREE_MUTATIONS; raise SystemExit(sabotage.main())"

Each puts back one way the gate judged the wrong tree, or one neighbour the
fix opened, and names the must-block or must-allow case that has to go red.
The `.ps1` ones target the pwsh-flavour cases, which run wherever PowerShell 7
resolves (see test_promote_gate_effective_tree.py's docstring).
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(CREW, "hooks", "scripts")
SH = os.path.join(_SCRIPTS, "promote-gate.sh")
PS1 = os.path.join(_SCRIPTS, "promote-gate.ps1")
TREE = os.path.join(_SCRIPTS, "_promote_tree.py")
_T = "tests/test_promote_gate_effective_tree.py::"

PROMOTE_TREE_MUTATIONS = (
    # Retargeted after review r1: the dirty-worktree case is now also caught by
    # the check on the tree the deploy RUNS in, which masks this mutation.
    ("promote-gate.sh judges the project dir again, not the deploy's tree", SH,
     '    TREE=$TOP\n',
     '    TREE=$PROJECT_TOP\n',
     _T + "test_a_pass_row_for_the_main_sha_does_not_admit_the_worktree_sha[sh]"),
    ("promote-gate.sh: a dirty main checkout blocks a clean worktree again", SH,
     '    TREE=$TOP\n',
     '    TREE=$PROJECT_TOP\n',
     _T + "test_a_clean_worktree_deploys_while_the_main_checkout_is_dirty[sh]"),
    ("promote-gate.sh accepts a worktree of a different repository", SH,
     'if [ "$TREE_COMMON" != "$PROJECT_COMMON" ]; then\n',
     'if false; then\n',
     _T + "test_a_worktree_of_a_different_repository_blocks[sh]"),
    ("promote-gate.sh lets a literal sha differ from the tree's HEAD", SH,
     '  if [ -n "$RESOLVED" ] && [ "$RESOLVED" != "$FULL" ]; then\n',
     '  if false; then\n',
     _T + "test_a_literal_sha_that_is_not_the_trees_head_blocks[sh]"),
    ("promote-gate.sh lets an uncommitted deploy-map edit become policy", SH,
     'if [ -n "$MAP_DIRTY" ]; then\n',
     'if false; then\n',
     _T + "test_uncommitted_edits_to_the_deploy_map_block[sh]"),
    ("promote-gate.sh ignores a cd after the start of the command", SH,
     '    midcd)\n      block ',
     '    midcd)\n      : ',
     _T + "test_a_cd_after_the_start_of_the_command_blocks[sh]"),
    ("promote-gate.ps1 judges the project dir again, not the deploy's tree", PS1,
     '  if (-not $tree) { $tree = $top }\n',
     '  if (-not $tree) { $tree = $projectTop }\n',
     _T + "test_a_pass_row_for_the_main_sha_does_not_admit_the_worktree_sha[ps1]"),
    ("promote-gate.ps1 accepts a worktree of a different repository", PS1,
     'if ($treeCommon -ne $projectCommon) {\n',
     'if ($false) {\n',
     _T + "test_a_worktree_of_a_different_repository_blocks[ps1]"),
    ("promote-gate.ps1 lets a literal sha differ from the tree's HEAD", PS1,
     '  if ($resolved -and $resolved -ne $full) {\n',
     '  if ($false) {\n',
     _T + "test_a_literal_sha_that_is_not_the_trees_head_blocks[ps1]"),
    ("promote-gate.ps1 ignores a cd after the start of the command", PS1,
     'if ($mid.Success) {\n',
     'if ($false) {\n',
     _T + "test_a_cd_after_the_start_of_the_command_blocks[ps1]"),
    ("_promote_tree.py stops refusing env -C / make -C", TREE,
     '    for m in _TOOLDIR.finditer(command):\n',
     '    for m in _TOOLDIR.finditer(""):\n',
     _T + "test_a_tool_that_changes_directory_is_could_not_tell[sh-env -C {wt} deploy-dev]"),
    ("_promote_tree.py reads a quoted `bash -c 'cd x'` as no directory change", TREE,
     """(?:^|(?<=[\\s;&|(){}'"`]))(?:cd|pushd|popd|chdir)""",
     """(?:^|(?<=[\\s;&|(){}]))(?:cd|pushd|popd|chdir)""",
     _T + "test_a_cd_in_any_other_form_is_could_not_tell[sh-bash -c 'cd {wt} && deploy-qa']"),
    # T-0505 review round 1 (Codex): one mutation per fixed finding.
    ("promote-gate.sh trusts git status for the map again (skip-worktree hides an edit)", SH,
     '  elif [ "$WORK_MAP" != "$HEAD_MAP" ]; then\n',
     '  elif false; then\n',
     _T + "test_skip_worktree_does_not_hide_an_uncommitted_map_edit[sh]"),
    ("promote-gate.sh stops matching a dirty map against the committed one", SH,
     '    if hit:\n        print(hit); sys.exit(0)\n',
     '    if False:\n        print(hit); sys.exit(0)\n',
     _T + "test_an_uncommitted_rename_of_the_deploy_command_still_blocks[sh]"),
    ("promote-gate.sh reads an uncommitted map deletion as the opt-out", SH,
     '  [ -z "$HEAD_MAP" ] && exit 0\n  MAP_DIRTY="deleted',
     '  exit 0\n  MAP_DIRTY="deleted',
     _T + "test_an_uncommitted_deletion_of_the_map_is_not_an_opt_out[sh]"),
    ("promote-gate.sh lets git -C launder the dirty tree the deploy runs in", SH,
     '[ "$RUN_TOP" != "$TREE" ] && clean_or_block "$RUN_TOP"\n',
     'true\n',
     _T + "test_git_dash_C_does_not_launder_the_dirty_tree_the_deploy_runs_in[sh]"),
    ("promote-gate.sh reads a failed git status as clean", SH,
     '    || block "could not read git status in',
     '    || : "could not read git status in',
     _T + "test_an_unreadable_status_is_not_clean[sh]"),
    ("promote-gate.sh ignores skip-worktree entries in the deployed tree", SH,
     "grep -q '^[a-zS]'",
     "grep -q '^NEVER'",
     _T + "test_skip_worktree_in_the_deployed_tree_blocks[sh]"),
    ("_promote_tree.py reads git -C inside quoted text again", TREE,
     '        if not live[m.start()]:\n',
     '        if False:\n',
     _T + "test_git_forms_outside_the_allowlist_are_could_not_tell"
     "[sh-deploy-dev --note \"x git -C {wt} rev-parse HEAD\"]"),
    ("_promote_tree.py accepts any git global option", TREE,
     '        if expands or text not in _GIT_FLAGS:\n',
     '        if expands:\n',
     _T + "test_git_forms_outside_the_allowlist_are_could_not_tell"
     "[sh-deploy-dev --ref $(git --bare -C {wt} rev-parse HEAD)]"),
    ("_promote_tree.py loses --no-pager from the allowlist", TREE,
     '_GIT_FLAGS = {"--no-pager", ',
     '_GIT_FLAGS = {',
     _T + "test_git_global_options_before_dash_C_still_name_the_tree[sh]"),
    ("promote-gate.ps1 trusts git status for the map again", PS1,
     '  elseif ($workMap -ne $headMap) {',
     '  elseif ($false) {',
     _T + "test_skip_worktree_does_not_hide_an_uncommitted_map_edit[ps1]"),
    ("promote-gate.ps1 lets git -C launder the dirty tree the deploy runs in", PS1,
     'if ($runTop -ne $tree) { Assert-Clean $runTop }\n',
     '\n',
     _T + "test_git_dash_C_does_not_launder_the_dirty_tree_the_deploy_runs_in[ps1]"),
    ("promote-gate.ps1 reads git -C inside quoted text again", PS1,
     '  if (-not $live[$m.Index]) {',
     '  if ($false) {',
     _T + "test_git_forms_outside_the_allowlist_are_could_not_tell"
     "[ps1-deploy-dev --note \"x git -C {wt} rev-parse HEAD\"]"),
    ("promote-gate.ps1 reads a failed git status as clean", PS1,
     '  if ($LASTEXITCODE -ne 0) { Stop-Promotion "could not read git status',
     '  if ($false) { Stop-Promotion "could not read git status',
     _T + "test_an_unreadable_status_is_not_clean[ps1]"),
    ("promote-gate.ps1's leading cd chain is case-sensitive again", PS1,
     "'\\s*(?:&&|;)'), 'IgnoreCase')",
     "'\\s*(?:&&|;)'), 'None')",
     _T + "test_powershell_directory_changes_are_case_insensitive"),
    ("_promote_tree.py lets a git -C outside a substitution name the sha", TREE,
     '            out.append(("Crun" if kind == "C" and not sub[m.start()] else kind, text))\n',
     '            out.append((kind, text))\n',
     _T + "test_git_dash_C_outside_a_substitution_does_not_name_the_sha[sh]"),
    ("promote-gate.ps1 lets a git -C outside a substitution name the sha", PS1,
     '  if ($inSub[$m.Index]) { $trees.Add($dir) } else { $runDirs.Add($dir) }\n',
     '  $trees.Add($dir)\n',
     _T + "test_git_dash_C_outside_a_substitution_does_not_name_the_sha[ps1]"),
)
