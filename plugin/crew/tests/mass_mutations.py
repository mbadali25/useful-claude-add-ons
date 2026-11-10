"""`guards.mass` mutations, in `sabotage.py`'s tuple shape (crew 1.3.28).

CLAUDE.md: a change that adds a hook that can block needs a committed
must-block / must-allow suite (`test_mass_guard.py`), sabotage-tested --
reintroduce each bug it should catch and confirm the suite goes red.

UNWIRED, as `preproduction_mutations.py` is: `sabotage*.py` is in the review
harness (`HARNESS` in `scripts/check-tooling-pr.py`), and a harness change lands
alone, so the one-line registration in `sabotage.py` is a harness-only
follow-up. Until then run this family on its own with `sabotage.py`'s machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, mass_mutations as m; \
        sabotage.MUTATIONS = m.MASS_MUTATIONS; raise SystemExit(sabotage.main())"

Each entry names the case that has to go red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
MASS = os.path.join(_S, "crew_mass.py")
GUARD = os.path.join(_S, "cloud_guard.py")
_T = "tests/test_mass_guard.py::"

MASS_MUTATIONS = (
    # --- the count and the limit
    ("mass: a count AT the limit passes", MASS,
     "    if touched is not None and touched < limit:\n        return None",
     "    if touched is not None and touched <= limit:\n        return None",
     _T + "test_rm_at_the_limit_stops_and_one_below_passes"),
    ("mass: could-not-tell collapses to not mass", MASS,
     "    if touched is not None and touched < limit:\n        return None",
     "    if touched is None or touched < limit:\n        return None",
     _T + "test_a_count_that_cannot_be_taken_stops"),
    ("mass: a glob is counted as one path", MASS,
     "return glob.glob(path, recursive=True) if _GLOB_RE.search(path) else [path]",
     "return [path]",
     _T + "test_a_glob_is_counted_after_expansion"),
    ("mass: rm without -r walks the directory", MASS,
     'if spec.kind == "rm" and spec.recursive:', 'if spec.kind == "rm":',
     _T + "test_a_directory_without_r_deletes_nothing"),
    ("mass: a variable in a path is counted as a path", MASS,
     "    if not isinstance(operand, str) or _DYNAMIC_RE.search(operand):",
     "    if not isinstance(operand, str):",
     _T + "test_a_count_that_cannot_be_taken_stops"),
    ("mass: a path after a cd is resolved against the old directory", MASS,
     "    if cd or not cwd:\n        return None, False",
     "    if not cwd:\n        return None, False",
     _T + "test_a_count_that_cannot_be_taken_stops"),
    ("mass: xargs-fed rm is counted from its visible words", MASS,
     'return [Spec(MASS_DELETE, "rm -r" if recursive else "rm", "rm", operands,\n'
     "                     recursive=recursive, unknown=fed)]",
     'return [Spec(MASS_DELETE, "rm -r" if recursive else "rm", "rm", operands,\n'
     "                     recursive=recursive, unknown=False)]",
     _T + "test_a_count_that_cannot_be_taken_stops"),
    # --- exemptions
    ("mass: node_modules counts", MASS, '"node_modules", ', "",
     _T + "test_a_regenerable_directory_never_counts"),
    ("mass: a worktree directory counts", MASS,
     "if part == WORKTREES and (relative or len(parts) - index - 1 <= 2):",
     "if False and (relative or len(parts) - index - 1 <= 2):",
     _T + "test_a_worktree_directory_is_exempt_by_path"),
    ("mass: a repo under a build/worktrees path is exempt wholesale", MASS,
     '        if rel not in (None, ".") and not rel.startswith(".."):',
     "        if False:",
     _T + "test_a_repo_that_lives_under_a_worktrees_or_build_path_is_still_guarded"),
    ("mass: the repo layer supplies the exempt globs", MASS,
     '"exempt": _exempt_globs(machine)}', '"exempt": _exempt_globs(repo)}',
     _T + "test_the_machine_exempt_globs_apply_and_the_repos_do_not"),
    ("mass: a copy into a regenerable directory counts", MASS,
     "    if _exempt_at(dest, cwd, globs):\n        return 0, 0",
     "    if False:\n        return 0, 0",
     _T + "test_copying_into_a_regenerable_directory_does_not_count"),
    ("mass: a generated file in a commit counts", MASS,
     "        if not names or exempt(names[-1], relative=True, globs=globs):",
     "        if not names:",
     _T + "test_commit_exempts_generated_files_by_the_machine_globs"),
    # --- create and change
    ("mass: touch counts a file that already exists", MASS,
     "total += 0 if os.path.lexists(match) else 1", "total += 1",
     _T + "test_touch_counts_new_files_only"),
    ("mass: cp over an existing file is a create", MASS,
     "                    if os.path.lexists(target):\n                        changed += 1\n"
     "                    else:\n                        new += 1",
     "                    if os.path.lexists(target):\n                        new += 1\n"
     "                    else:\n                        changed += 1",
     _T + "test_cp_over_existing_files_is_a_change"),
    ("mass: cp -n is judged as an overwrite", MASS,
     'if letters & {"n"} or "--no-clobber" in longs or len(operands) < 2:',
     "if len(operands) < 2:",
     _T + "test_cp_n_never_overwrites_and_a_single_file_is_one"),
    ("mass: sed without -i is judged", MASS,
     "    if not inplace:\n        return []", "    if False:\n        return []",
     _T + "test_sed_in_place_over_many_files"),
    # --- git
    ("mass: git commit counts the tree, not the index", MASS,
     'argv = ["diff", "--name-status", "-M"] + ([] if every else ["--cached"])',
     'argv = ["diff", "--name-status", "-M"] + []',
     _T + "test_commit_a_flag_counts_tracked_changes_not_staged_ones"),
    ("mass: an added file counts as a change", MASS,
     '(status == "A" and spec.rule == MASS_CREATE)',
     '(status == "A" and spec.rule == MASS_CHANGE)',
     _T + "test_commit_counts_staged_adds_deletes_and_changes"),
    ("mass: a deleted file is not counted", MASS,
     '(status == "D" and spec.rule == MASS_DELETE)',
     '(status == "X" and spec.rule == MASS_DELETE)',
     _T + "test_commit_counts_deletes"),
    ("mass: a push with no base is let through", MASS,
     "        if found is None:\n            return None",
     "        if found is None:\n            return []",
     _T + "test_push_without_a_base_it_can_find_is_unknown_and_stops"),
    ("mass: git clean -n is judged", MASS,
     'if "n" in letters or flags & {"--dry-run"} or not ("f" in letters or flags & {"--force"}):',
     'if not ("f" in letters or flags & {"--force"}):',
     _T + "test_git_clean_counts_what_it_would_remove"),
    ("mass: git rm --cached is judged", MASS,
     'if flags & {"--cached"} or "n" in letters or flags & {"--dry-run"}:',
     'if "n" in letters or flags & {"--dry-run"}:',
     _T + "test_git_rm_counts_tracked_files"),
    ("mass: git restore --staged is judged", MASS,
     'if "--staged" in flags and "--worktree" not in flags and "-W" not in flags:',
     'if False:',
     _T + "test_git_checkout_paths_and_restore"),
    ("mass: a plain git checkout is judged", MASS,
     '        if "--" not in rest and not (letters & {"f"} or flags & {"--force"}) \\\n'
     '                and "." not in rest:\n            return []',
     "        if False:\n            return []",
     _T + "test_git_checkout_paths_and_restore"),
    # --- terraform and sql
    ("mass: the terraform delete default is the general one", MASS,
     'DEFAULT_OVERRIDES = {"terraform": {"deleteCount": 3,',
     'DEFAULT_OVERRIDES = {"terraform": {"deleteCount": 10,',
     _T + "test_terraform_apply_of_a_plan_uses_the_terraform_limits"),
    ("mass: a replace counts only once", MASS,
     "    return sum(1 for change in changes if isinstance(change, dict) and want in\n"
     '               (change.get("change") or {}).get("actions", []))',
     "    return sum(1 for change in changes if isinstance(change, dict) and [want] ==\n"
     '               (change.get("change") or {}).get("actions", []))',
     _T + "test_terraform_apply_of_a_plan_uses_the_terraform_limits"),
    ("mass: an interactive terraform apply is judged", MASS,
     "    if sub == \"apply\" and not auto and not destroy:\n        return []",
     "    if False:\n        return []",
     _T + "test_terraform_without_a_plan_to_read_stops"),
    ("mass: WHERE 1=1 is a filter", MASS,
     "            if where and not _TRIVIAL_WHERE_RE.search(statement.strip()):",
     "            if where:",
     _T + "test_an_unfiltered_sql_delete_or_update_stops"),
    # --- settings
    ("mass: a switch that is not exactly true arms it", MASS,
     'layer.get("enabled") is True for layer', 'layer.get("enabled") for layer',
     _T + "test_a_switch_that_is_not_exactly_true_is_off"),
    ("mass: a boolean is a limit", MASS,
     "    if isinstance(value, bool) or not isinstance(value, int) or value < 1:",
     "    if not isinstance(value, int) or value < 1:",
     _T + "test_a_limit_that_is_not_a_positive_integer_reads_as_the_default"),
    ("mass: the repo layer can raise a limit", MASS,
     "out[category][key] = min(base, lower) if lower is not None else base",
     "out[category][key] = lower if lower is not None else base",
     _T + "test_the_repo_can_lower_a_limit_but_not_raise_the_machines"),
    ("mass: a resolver that raises is an opt-out", MASS,
     "is False for key in crew_humanonly.KEYS)\n    except Exception:  # noqa: BLE001  "
     "# pylint: disable=broad-except\n        return False",
     "is False for key in crew_humanonly.KEYS)\n    except Exception:  # noqa: BLE001  "
     "# pylint: disable=broad-except\n        return True",
     _T + "test_a_resolver_that_raises_is_no_opt_out"),
    # --- the approval
    ("mass: a cli-recorded approval is accepted", MASS,
     'or record.get("approved_via") != "user-prompt":', ":",
     _T + "test_a_forged_expired_or_future_approval_is_not_an_approval"),
    ("mass: an approval never expires by age", MASS,
     "return stamp <= now + 60 and now <= min(expires, stamp + MASS_APPROVAL_TTL)",
     "return stamp <= now + 60 and now <= expires",
     _T + "test_an_approval_older_than_the_ttl_is_not_an_approval"),
    ("mass: a future-dated approval is accepted", MASS,
     "return stamp <= now + 60 and now <=", "return True and now <=",
     _T + "test_a_forged_expired_or_future_approval_is_not_an_approval"),
    ("mass: an approval is not bound to the command", MASS,
     'raw = "\\0".join(("crew-mass/2", text, os.path.normcase(toplevel or "")))',
     'raw = "\\0".join(("crew-mass/2", "", os.path.normcase(toplevel or "")))',
     _T + "test_the_owners_typed_yes_lets_that_command_through_once_and_only_that_command"),
    ("mass: an unattended stop is an ask", MASS,
     "    if alone:\n        reason +=", "    if False:\n        reason +=",
     _T + "test_attended_is_an_ask_unattended_is_a_deny"),
    # --- the hook
    ("mass: an unarmed repo is judged", GUARD,
     "            if not mass_armed:\n                continue",
     "            if False:\n                continue",
     _T + "test_off_by_default_nothing_is_judged"),
    ("mass: a write to the approvals directory is allowed", GUARD,
     "    if mass_armed and crew_mass.tampers(command):",
     "    if False and crew_mass.tampers(command):",
     _T + "test_a_command_writing_the_approvals_directory_is_refused"),
)
