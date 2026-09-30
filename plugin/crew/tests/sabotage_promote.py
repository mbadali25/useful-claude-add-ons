"""T-0505 promote-gate effective-tree mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart for the reason the other `sabotage_*.py` files give:
`sabotage.py` sits at `.pylintrc`'s max-module-lines. Run that file, not this
one.

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
_T = "tests/test_promote_gate_effective_tree.py::"

PROMOTE_TREE_MUTATIONS = (
    ("promote-gate.sh judges the project dir again, not the deploy's tree", SH,
     '    TREE=$TOP\n',
     '    TREE=$PROJECT_TOP\n',
     _T + "test_a_clean_root_does_not_launder_a_cd_into_a_dirty_worktree[sh]"),
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
     'if [ -n "$(git status --porcelain -- .crew/verify.json 2>/dev/null)" ]; then\n',
     'if false; then\n',
     _T + "test_uncommitted_edits_to_the_deploy_map_block[sh]"),
    ("promote-gate.sh ignores a cd after the start of the command", SH,
     '    midcd)\n      block ',
     '    midcd)\n      : ',
     _T + "test_a_cd_after_the_start_of_the_command_blocks[sh]"),
    ("promote-gate.ps1 judges the project dir again, not the deploy's tree", PS1,
     '  if (-not $tree) { $tree = $top }\n',
     '  if (-not $tree) { $tree = $projectTop }\n',
     _T + "test_a_clean_root_does_not_launder_a_cd_into_a_dirty_worktree[ps1]"),
    ("promote-gate.ps1 accepts a worktree of a different repository", PS1,
     'if ($treeCommon -ne $projectCommon) {\n',
     'if ($false) {\n',
     _T + "test_a_worktree_of_a_different_repository_blocks[ps1]"),
    ("promote-gate.ps1 lets a literal sha differ from the tree's HEAD", PS1,
     '  if ($resolved -and $resolved -ne $full) {\n',
     '  if ($false) {\n',
     _T + "test_a_literal_sha_that_is_not_the_trees_head_blocks[ps1]"),
)
