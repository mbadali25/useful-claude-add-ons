"""The crew 1.0 T2 fix-round mutations for `crew_migrate.py`, `crew_status.py`
and the migrate crash test, appended to `sabotage.py`'s MUTATIONS. Kept apart
for the same reason as `sabotage_review.py`: `sabotage.py` sits at
`.pylintrc`'s max-module-lines. Run that file, not this one.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATE = os.path.join(CREW, "hooks", "scripts", "crew_migrate.py")
STATUS = os.path.join(CREW, "hooks", "scripts", "crew_status.py")
TEST_MIGRATE = os.path.join(CREW, "tests", "test_migrate.py")
AUTOCLEAR_SETUP = os.path.join(CREW, "hooks", "scripts", "crew_autoclear_setup.py")
_A = "tests/test_autoclear_setup.py::"

MIGRATE_FIX_MUTATIONS = (
    # Each was also run by hand against the tracked file, restored from a
    # scratch copy with `cp` and confirmed with `diff`.
    (
        # Containment gone: a symlinked ticket dir is written through.
        "migrate writes through a symlinked target directory",
        MIGRATE,
        "    parts = rel.replace(\"\\\\\", \"/\").split(\"/\")\n",
        "    return os.path.join(root, rel)\n",
        ("tests/test_migrate.py::"
         "test_symlinked_ticket_dir_is_a_conflict_and_nothing_is_written_through_it"),
    ),
    (
        # The plan no longer reports an existing staging name.
        "migrate plans over an existing .crew-migrate.tmp",
        MIGRATE,
        "        if os.path.lexists(path + TMP_SUFFIX):\n",
        "        if False:\n",
        ("tests/test_migrate.py::"
         "test_existing_staging_name_is_a_conflict_and_is_left_intact"),
    ),
    (
        # Staging truncates whatever holds the temp name, as before the fix.
        "migrate stages with a truncating open",
        MIGRATE,
        "                fd = os.open(path + TMP_SUFFIX,\n"
        "                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | "
        "getattr(os, \"O_BINARY\", 0))\n",
        "                fd = os.open(path + TMP_SUFFIX,\n"
        "                             os.O_WRONLY | os.O_CREAT | os.O_TRUNC | "
        "getattr(os, \"O_BINARY\", 0))\n",
        ("tests/test_migrate.py::"
         "test_staging_name_created_after_the_plan_is_never_truncated"),
    ),
    (
        # A stale plan replaces a target that appeared after it was built.
        "migrate apply no longer re-checks the planned pre-state",
        MIGRATE,
        "            _check_pre_state(root, item)\n",
        "",
        ("tests/test_migrate.py::"
         "test_target_created_after_the_plan_is_not_overwritten_and_apply_is_undone"),
    ),
    (
        # Rollback trusts manifest paths again, the pre-fix loop.
        "migrate rollback trusts the manifest's paths",
        MIGRATE,
        "    targets, dirs = _manifest_entries(root, manifest)\n",
        "    targets = [(t, os.path.join(root, t[\"path\"])) for t in manifest[\"targets\"]]\n"
        "    dirs = manifest.get(\"createdDirs\", [])\n",
        ("tests/test_migrate.py::"
         "test_rollback_refuses_a_manifest_path_outside_the_repo"),
    ),
    (
        # Same pre-fix loop, caught by the symlinked-dir case. (Dropping only
        # the per-target `contained` stays green: the created-directory
        # check refuses the symlinked dir too, so this restores both.)
        "migrate rollback removes through a symlinked dir",
        MIGRATE,
        "    targets, dirs = _manifest_entries(root, manifest)\n",
        "    targets = [(t, os.path.join(root, t[\"path\"])) for t in manifest[\"targets\"]]\n"
        "    dirs = manifest.get(\"createdDirs\", [])\n",
        ("tests/test_migrate.py::"
         "test_rollback_refuses_to_remove_through_a_symlinked_dir"),
    ),
    (
        # The crash test's pre-fix counter: backup writes count as targets.
        "the crash test counts backup replaces as target commits",
        TEST_MIGRATE,
        "        if src.endswith(crew_migrate.TMP_SUFFIX) and not dst.startswith(backups):\n",
        "        if src.endswith(crew_migrate.TMP_SUFFIX) and not dst.endswith(\"manifest.json\"):\n",
        "tests/test_migrate.py::test_crash_mid_apply_leaves_the_old_tree",
    ),
    (
        # The context script is left to find the session's project.
        "status --memory does not pass the requested root",
        STATUS,
        "                              env=dict(_GIT_ENV, CLAUDE_PROJECT_DIR=root))\n",
        "                              env=_GIT_ENV)\n",
        ("tests/test_status.py::"
         "test_memory_reports_the_requested_root_not_the_session_project"),
    ),
    (
        # A configured fsmonitor hook runs under `git status` again.
        "status lets git run core.fsmonitor",
        STATUS,
        "(\"git\", \"-c\", \"core.fsmonitor=false\") + args",
        "(\"git\",) + args",
        "tests/test_status.py::test_status_never_runs_a_configured_fsmonitor_hook",
    ),
    (
        # A corrupt crew.json hidden behind the legacy config.
        "status hides a corrupt crew.json behind config.json",
        STATUS,
        "    if crew is not None and not isinstance(crew, dict):\n",
        "    if False:\n",
        ("tests/test_status.py::"
         "test_corrupt_crew_json_is_reported_even_beside_a_valid_legacy_config"),
    ),
    (
        # INDEX rows split on a leading pipe again.
        "status drops INDEX rows with a leading pipe",
        STATUS,
        "        cells = [c.strip() for c in line.strip().strip(\"|\").split(\"|\")]\n",
        "        cells = [c.strip() for c in line.split(\"|\")]\n",
        "tests/test_status.py::test_index_rows_with_a_leading_pipe_are_reported_open",
    ),
    # C-0028: T-0106's apply-migrate --scan-root. Each is a way the scan could
    # read a repo it could not see into as "not opted in", or let --yes-widen
    # write a list that leaves an opted-in repo out (or an empty one).
    ("apply-migrate: --yes-widen writes past an unreadable scanned repo", AUTOCLEAR_SETUP,
     "    if unreadable:\n        return (\"refused --yes-widen: these repos could not be read",
     "    if False:\n        return (\"refused --yes-widen: these repos could not be read",
     _A + "test_yes_widen_refuses_when_a_candidate_could_not_be_read"),
    ("apply-migrate: --yes-widen writes an empty onlyRepos list", AUTOCLEAR_SETUP,
     '    if not widening["proposedOnlyRepos"]:\n',
     "    if False:\n",
     _A + "test_yes_widen_refuses_an_empty_proposal"),
    ("apply-migrate: the scan descends into a candidate repo", AUTOCLEAR_SETUP,
     "                    found.add(directory)\n                continue\n",
     "                    found.add(directory)\n",
     _A + "test_scan_skips_nested_hidden_vendored_and_symlinked_directories"),
    ("apply-migrate: an unreadable candidate reads as not opted in", AUTOCLEAR_SETUP,
     "                if reason:\n                    unreadable[directory] = reason\n",
     "                if False:\n                    unreadable[directory] = reason\n",
     _A + "test_unreadable_candidate_is_reported_not_treated_as_not_opted_in"),
    ("apply-migrate: an opted-in sibling masks an unreadable repo file", AUTOCLEAR_SETUP,
     '    return present, opted_in, "; ".join(problems)\n',
     '    return present, opted_in, "" if opted_in else "; ".join(problems)\n',
     _A + "test_an_unreadable_file_is_not_masked_by_an_opted_in_sibling"),
    ("apply-migrate: a .crew that cannot be statted reads as no crew here", AUTOCLEAR_SETUP,
     '        return True, False, f".crew could not be read: {exc}"\n',
     '        return False, False, ""\n',
     _A + "test_a_crew_directory_that_cannot_be_statted_is_unreadable"),
    ("apply-migrate: a .crew that cannot be listed reads as no crew here", AUTOCLEAR_SETUP,
     '        return True, False, f".crew could not be listed: {exc}"\n',
     '        return False, False, ""\n',
     _A + "test_a_crew_directory_that_cannot_be_listed_is_unreadable"),
    ("apply-migrate: the scan trusts listdir's spelling of the repo files", AUTOCLEAR_SETUP,
     "        if name not in names:\n            try:\n",
     "        if name not in names:\n            continue\n            try:\n",
     _A + "test_a_config_file_listed_in_another_case_is_still_scanned"),
    ("apply-migrate: a case-variant file that cannot be statted is skipped", AUTOCLEAR_SETUP,
     "            except OSError as exc:\n                present = True\n"
     '                problems.append(f".crew/{name}: {exc}")\n                continue\n',
     "            except OSError:\n                continue\n",
     _A + "test_a_case_variant_config_that_cannot_be_statted_is_unreadable"),
    ("apply-migrate: an entry whose type cannot be read is skipped", AUTOCLEAR_SETUP,
     '                unchecked[entry.path] = f"could not tell whether it is a directory: {exc}"\n',
     "                pass\n",
     _A + "test_an_entry_whose_type_cannot_be_read_is_unreadable"),
    ("apply-migrate: a symlinked .crew is followed", AUTOCLEAR_SETUP,
     "    if stat.S_ISLNK(mode):\n",
     "    if False:\n",
     _A + "test_a_symlinked_crew_directory_is_not_followed"),
    ("apply-migrate: the scan lists the current repo again", AUTOCLEAR_SETUP,
     "            if directory == current:\n                continue\n",
     "",
     _A + "test_scan_does_not_list_the_current_repo_twice"),
    # The walk bounds depth twice (`best`'s default and `level >= depth`), so
    # loosening either check alone leaves the other holding: start one lower.
    ("apply-migrate: the scan reads one level past --scan-depth", AUTOCLEAR_SETUP,
     "        stack = [(top, 0)]\n",
     "        stack = [(top, -1)]\n",
     _A + "test_scan_depth_limits_the_walk"),
    ("apply-migrate: a note no longer names its file", AUTOCLEAR_SETUP,
     '        file_notes = [f".crew/{name}: {note}" for note in\n',
     "        file_notes = [note for note in\n",
     _A + "test_apply_migrate_notes_name_their_file"),
)
