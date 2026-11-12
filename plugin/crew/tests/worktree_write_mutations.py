"""L-0946 mutations, in `sabotage.py`'s tuple shape: a repo-layer write from a
linked worktree lands in the file reads use (the main checkout's), says so, and
refuses when git cannot tell. `test_worktree_config_write.py` is the suite.

UNWIRED, as `preproduction_mutations.py` is: `sabotage*.py` is in the review
harness (`HARNESS` in `scripts/check-tooling-pr.py`), and a harness change lands
alone, so the one-line registration in `sabotage.py` is a harness-only
follow-up. Until then run this family on its own with `sabotage.py`'s own
machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, worktree_write_mutations as m; \
        sabotage.MUTATIONS = m.WORKTREE_WRITE_MUTATIONS; raise SystemExit(sabotage.main())"

Every entry is platform-neutral: none is declared host-specific. Each names the
case that has to go red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
CONFIG = os.path.join(_S, "crew_config.py")
MENU = os.path.join(_S, "crew_config_menu.py")
_W = "tests/test_worktree_config_write.py::"

WORKTREE_WRITE_MUTATIONS = (
    ("a worktree repo write targets its own path again", CONFIG,
     '    main_root = detail if source == crew_common.SOURCE_MAIN else ""\n'
     '    return os.path.join(crew_dir, "config.json"), main_root\n',
     '    return repo_config_path(root), ""\n',
     _W + "test_worktree_set_writes_the_main_checkouts_file_and_says_so"),
    ("could-not-tell falls back to the worktree's own path", CONFIG,
     "    if source == crew_common.SOURCE_UNKNOWN:\n        raise RepoTargetUnknown(\n",
     "    if False:\n        raise RepoTargetUnknown(\n",
     _W + "test_worktree_could_not_tell_refuses_and_creates_nothing"),
    ("the write label stops naming the main checkout", CONFIG,
     '    if not main_root:\n        return ""\n',
     '    if True:\n        return ""\n',
     _W + "test_worktree_set_writes_the_main_checkouts_file_and_says_so"),
    ("--set prints the worktree's own path over the file it wrote", CONFIG,
     '    print(f"{verb}: " + (target + repo_target_note(main_root) if repo\n',
     '    print(f"{verb}: " + (repo_config_path(root) + repo_target_note(main_root) if repo\n',
     _W + "test_worktree_set_writes_the_main_checkouts_file_and_says_so"),
    ("write_repo_config resolves its own path without a target", CONFIG,
     "    real_path = repo_write_target(root)[0] if target is None else target\n",
     "    real_path = repo_config_path(root) if target is None else target\n",
     _W + "test_worktree_write_backs_up_the_main_file_first"),
    ("rebuild looks for the worktree's own .crew/", CONFIG,
     "    crew_dir = os.path.dirname(repo_write_target(root)[0])\n",
     '    crew_dir = os.path.join(root, ".crew")\n',
     _W + "test_worktree_rebuild_dry_run_names_the_main_file"),
    ("--backups lets could-not-tell escape as a traceback", CONFIG,
     "    except RepoTargetUnknown as exc:\n        print(str(exc), file=sys.stderr)\n",
     "    except ZeroDivisionError as exc:\n        print(str(exc), file=sys.stderr)\n",
     _W + "test_could_not_tell_refuses_every_repo_writer"),
    ("the menu Save stops naming the main checkout", MENU,
     '            notes["repo"] = crew_config.repo_target_note(main_root)\n',
     '            notes["repo"] = ""\n',
     _W + "test_worktree_menu_save_writes_the_main_file"),
)
