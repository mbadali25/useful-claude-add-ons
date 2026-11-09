"""crew 1.3.19 worktree-root mutations, in `sabotage.py`'s tuple shape.

Each puts back one way `crew_worktrees.py` could place a worktree somewhere it
must not, delete work it must not, or replace a refusal with a guess, and names
the must-refuse case in `test_crew_worktrees.py` that has to go red.

NOT wired into `sabotage.py`'s MUTATIONS: `sabotage*.py` is review harness
(`scripts/check-tooling-pr.py` `HARNESS`), so wiring this family in lands with a
harness change of its own. Until then run it alone, with sabotage.py's own
machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, worktrees_mutations as m; \
        sabotage.MUTATIONS = m.WORKTREES_MUTATIONS; raise SystemExit(sabotage.main())"
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT = os.path.join(CREW, "hooks", "scripts", "crew_worktrees.py")
CW = os.path.join(CREW, "hooks", "scripts", "crew_wave.py")
_T = "tests/test_crew_worktrees.py::"

WORKTREES_MUTATIONS = (
    ("worktrees: an unusable setting falls back to the default", WT,
     '    if raw is not None and (not isinstance(raw, str) or not raw.strip()):\n',
     '    if False:\n',
     _T + "test_an_unusable_setting_is_refused_and_never_replaced_by_the_default"),
    ("worktrees: a relative root is accepted", WT,
     "    if not os.path.isabs(base):\n",
     "    if False:\n",
     _T + "test_an_unusable_setting_is_refused_and_never_replaced_by_the_default"),
    ("worktrees: a root inside the repo is accepted", WT,
     "    if _inside(base, main):\n",
     "    if False:\n",
     _T + "test_a_root_inside_the_repo_is_refused"),
    ("worktrees: remove needs no --yes", WT,
     "    if not yes:\n",
     "    if False:\n",
     _T + "test_remove_needs_the_owners_yes"),
    ("worktrees: remove forces", WT,
     '    code, _, err = _git(main, "worktree", "remove", target["path"])\n    if code != 0:\n        return False, f"git worktree remove failed',
     '    code, _, err = _git(main, "worktree", "remove", "--force", target["path"])\n    if code != 0:\n        return False, f"git worktree remove failed',
     _T + "test_remove_never_forces"),
    ("worktrees: a could-not-tell dirty probe counts as clean", WT,
     '    if row["dirty"] is not False:\n',
     '    if row["dirty"] is True:\n',
     _T + "test_a_probe_that_fails_is_could_not_tell_and_not_removable"),
    ("worktrees: commits no remote has do not keep a worktree", WT,
     '    if row["unpushed"] != 0:\n',
     '    if False:\n',
     _T + "test_commits_no_remote_has_are_never_removable"),
    ("worktrees: an unknown merge state counts as merged", WT,
     '    if row["merged"] is not True:\n',
     '    if row["merged"] is False:\n',
     _T + "test_a_missing_default_branch_is_could_not_tell_not_merged"),
    ("worktrees: a young worktree is removable", WT,
     '    if row["age_days"] is None or row["age_days"] < days:\n',
     '    if False:\n',
     _T + "test_a_young_worktree_is_kept_until_it_is_old_enough"),
    ("worktrees: a locked worktree is removable", WT,
     "    if row[\"locked\"]:\n        problems.append(\"locked\")\n",
     "    if False:\n        problems.append(\"locked\")\n",
     _T + "test_a_locked_worktree_is_kept"),
    ("worktrees: remove may delete the checkout it runs in", WT,
     '    if here and _norm(here) == _norm(target["path"]):\n',
     '    if False:\n',
     _T + "test_remove_refuses_the_main_checkout_a_stranger_and_the_current_one"),
    ("worktrees: the hook accepts any name", WT,
     '    if not NAME_RE.match(name) or name.endswith(".") or ".." in name:\n',
     '    if False:\n',
     _T + "test_hook_create_refuses_a_name_that_is_not_a_plain_name"),
    ("worktrees: the hook builds in a directory it did not create", WT,
     "    if os.path.exists(dest):\n        return False, f\"refused: {dest} exists",
     "    if False:\n        return False, f\"refused: {dest} exists",
     _T + "test_hook_create_reuses_its_own_worktree_and_refuses_a_stranger_directory"),
    ("worktrees: the hook removes the main checkout", WT,
     "    target = next((r for r in found[1:] if _norm(r[\"path\"]) == _norm(path)), None)\n    if target is None:\n        return False, f\"refused: {path} is not a linked worktree\"",
     "    target = next((r for r in found if _norm(r[\"path\"]) == _norm(path)), None)\n    if target is None:\n        return False, f\"refused: {path} is not a linked worktree\"",
     _T + "test_hook_remove_refuses_the_main_checkout_and_a_path_that_is_not_a_worktree"),
    ("worktrees: the hook forces its removal", WT,
     '    code, _, err = _git(main, "worktree", "remove", target["path"])\n    if code != 0:\n        return False, f"left in place',
     '    code, _, err = _git(main, "worktree", "remove", "--force", target["path"])\n    if code != 0:\n        return False, f"left in place',
     _T + "test_hook_remove_leaves_uncommitted_work_and_unmerged_commits_in_place"),
    ("worktrees: the hook prints more than the path on stdout", WT,
     "        if ok:\n            print(message)\n            return 0\n        print(message, file=sys.stderr)",
     "        if ok:\n            print(\"created\" + message)\n            return 0\n        print(message, file=sys.stderr)",
     _T + "test_the_hook_cli_prints_only_the_path_on_stdout_and_exits_1_on_refusal"),
    ("worktrees: the wave admits any directory", CW,
     "        if not (standard and os.path.normcase(os.path.realpath(top)).startswith(",
     "        if False and not (standard and os.path.normcase(os.path.realpath(top)).startswith(",
     _T + "test_lane_init_admits_a_worktree_under_the_standard_root_and_still_refuses_a_sibling"),
)
