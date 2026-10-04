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
)
