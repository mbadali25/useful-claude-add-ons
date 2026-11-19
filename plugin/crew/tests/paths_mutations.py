"""R-04 `crew_paths.py` mutations, in `sabotage.py`'s tuple shape.

Each row removes one check from the resolver or the deletion helper and names
ONE unparametrized node of `test_crew_paths.py` that runs, unskipped, on the
OS the row is applied on, and that must go red.

NOT wired into `sabotage.py`'s MUTATIONS: `sabotage*.py` is review harness
(`scripts/check-tooling-pr.py` `HARNESS`), and `sabotage_platform.PLATFORM_ONLY`
is keyed by MUTATIONS labels, so these rows are split here by OS instead. Run
alone, on Windows and on Linux:

    cd plugin/crew/tests && python3 -c "import sabotage, paths_mutations as m; \
        sabotage.MUTATIONS = m.PATHS_MUTATIONS; raise SystemExit(sabotage.main())"
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CP = os.path.join(CREW, "hooks", "scripts", "crew_paths.py")
_T = "tests/test_crew_paths.py::"

_COMMON = (
    ("paths: the ownership record is not checked", CP,
     "    problem = _record_problem(path, run_id, kind, nonce)\n",
     '    problem = ""\n',
     _T + "test_c5_record_missing_refused"),
    ("paths: the record's run_id is not compared", CP,
     '    if rec.get("run_id") != run_id:\n',
     "    if False:\n",
     _T + "test_c5_record_wrong_run_id_refused"),
    ("paths: a hard-linked record is accepted", CP,
     "    if lst.st_nlink != 1:\n",
     "    if False:\n",
     _T + "test_c5_record_hard_link_refused"),
    ("paths: the record's fstat is not matched to its lstat", CP,
     "        if not stat.S_ISREG(fst.st_mode) or (fst.st_dev, fst.st_ino) != (lst.st_dev, lst.st_ino):\n",
     "        if not stat.S_ISREG(fst.st_mode):\n",
     _T + "test_c5b_record_swapped_refused"),
    ("paths: containment accepts the folder's own parent as an allowed root", CP,
     "    for which, root in candidates:\n",
     '    for which, root in (("test_root", fl.dirname(p_raw)),) + candidates:\n',
     _T + "test_c4_planted_record_outside_roots_refused"),
    ("paths: the shape rule accepts a scratch <ticket> folder", CP,
     "        if len(rem) == 3 and _KEY_RE.match(rem[0]):\n",
     "        if len(rem) in (2, 3) and _KEY_RE.match(rem[0]):\n",
     _T + "test_c2_shared_parent_with_planted_record_refused"),
    ("paths: the realpath anchor is disabled", CP,
     ("    if os.path.normcase(os.path.realpath(path)) != "
      "os.path.normcase(os.path.join(os.path.realpath(root), *rem)):\n"),
     "    if False:\n",
     _T + "test_c6_anchor_isolated"),
    ("paths: the anchor compares the whole path unanchored", CP,
     ("    if os.path.normcase(os.path.realpath(path)) != "
      "os.path.normcase(os.path.join(os.path.realpath(root), *rem)):\n"),
     "    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.normpath(path)):\n",
     _T + "test_c6_linked_ancestor_allowed"),
    ("paths: the component lstat walk is disabled", CP,
     "        if stat.S_ISLNK(st.st_mode) or _attrs(st) & _REPARSE or not stat.S_ISDIR(st.st_mode):\n",
     "        if False:\n",
     _T + "test_c6_component_walk_isolated"),
    ("paths: the pre-scan ignores an st_dev change", CP,
     '                if _child_dev(st, entry, "scan") != root_dev:\n',
     "                if False:\n",
     _T + "test_c8a_prescan_st_dev_refused"),
    ("paths: the walk ignores an st_dev change", CP,
     '    if _child_dev(st, path, "walk") != root_dev:\n',
     "    if False:\n",
     _T + "test_c8a_walk_st_dev_stops"),
    ("paths: the mountinfo scan is skipped", CP,
     "    if _is_linux():\n",
     "    if False:\n",
     _T + "test_c8c_listed_mount_refused"),
    ("paths: an unreadable mountinfo reads as no mounts", CP,
     '            return f"could not tell whether a mount is inside: {exc}"\n',
     '            return ""\n',
     _T + "test_c8c_reader_raises_refused"),
    ("paths: the run folder's identity is not re-checked", CP,
     "        if _identity(cur) != _identity(st_path):\n",
     "        if False:\n",
     _T + "test_c9_root_replaced_by_dir_refused"),
    ("paths: /root is refused with everything under it", CP,
     ('_POSIX_EXACT = ("/root", "/home", "/tmp", "/var", "/opt", "/srv")\n'
      '_POSIX_UNDER = ("/bin",'),
     ('_POSIX_EXACT = ("/home", "/tmp", "/var", "/opt", "/srv")\n'
      '_POSIX_UNDER = ("/root", "/bin",'),
     _T + "test_a2_root_home_layout"),
    ("paths: the equal-or-under system list is empty", CP,
     ('_POSIX_UNDER = ("/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64", "/boot", "/dev", "/proc", '
      '"/sys", "/run", "/var/run")\n'),
     "_POSIX_UNDER = ()\n",
     _T + "test_c3_under_list_posix_flavour"),
    ("paths: the empty/relative/NUL guard is disabled", CP,
     '    if not isinstance(path, str) or not path.strip() or "\\0" in path or not fl.isabs(path):\n',
     "    if False:\n",
     _T + "test_c1_empty_string_is_not_cwd"),
    ("paths: the repo layer moves the worktree base", CP,
     "    cfg = crew_config.read_global_config(path)\n",
     '    cfg = crew_config.resolve_config(repo or ".")\n',
     _T + "test_r1_repo_worktrees_root_ignored"),
    ("paths: CREW_TEST_ROOT may contain the home, crew root or worktree base", CP,
     '        for name in ("home", "root", "wt"):\n',
     "        for name in ():\n",
     _T + "test_r4_test_root_ancestor_of_home_refused"),
    ("paths: CREW_TEST_ROOT may sit inside <root>/review", CP,
     '        if _inside(fl, t, norm(lay["review"])):\n',
     "        if False:\n",
     _T + "test_r4_test_root_inside_review_refused"),
    ("paths: CREW_TEST_ROOT may sit inside <root>/scratch outside tests", CP,
     '        if _inside(fl, t, norm(lay["scratch"])) and not _inside(fl, t, norm(lay["scratch_tests"])):\n',
     "        if False:\n",
     _T + "test_r4_test_root_inside_scratch_outside_tests_refused"),
)

_POSIX = (
    ("paths: the record is opened following links", CP,
     "            fd = os.open(rec, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK)\n",
     "            fd = os.open(rec, os.O_RDONLY | _O_NONBLOCK)\n",
     _T + "test_c5b_record_onofollow_isolated_posix"),
    ("paths: a symlink entry is descended into", CP,
     "        if stat.S_ISLNK(lst.st_mode):\n            os.unlink(name, dir_fd=dfd)\n",
     ("        if stat.S_ISLNK(lst.st_mode):\n"
      "            _walk_posix(os.open(name, os.O_RDONLY, dir_fd=dfd), entry, root_dev, done)\n"
      "            os.unlink(name, dir_fd=dfd)\n"),
     _T + "test_c7_symlink_dir_inside_removed_posix"),
    ("paths: a read-only dir is chmod-ed by path", CP,
     "        os.fchmod(dfd, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)\n",
     "        os.chmod(dpath, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)\n",
     _T + "test_c10_swap_before_attr_clear_refused"),
    ("paths: a read-only dir is not made writable", CP,
     "        os.fchmod(dfd, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)\n",
     "        pass\n",
     _T + "test_c10_readonly_tree_removed"),
)

_WINDOWS = (
    ("paths: a reparse-point record is accepted", CP,
     '    if _attrs(lst) & _REPARSE:\n        return None, f"record: {rec} is a reparse point"\n',
     '    if False:\n        return None, f"record: {rec} is a reparse point"\n',
     _T + "test_c5b_record_reparse_injected_windows"),
    ("paths: a junction entry is descended as a plain dir", CP,
     "        if attrs & _REPARSE:  # walk: a link entry is removed as a link, never descended\n",
     "        if False:  # walk: a link entry is removed as a link, never descended\n",
     _T + "test_c7_junction_inside_removed_windows"),
    ("paths: a volume-root junction target is not recognised", CP,
     '    return bool(_VOLUME_RE.match(target or ""))\n',
     "    return False\n",
     _T + "test_c8d_volume_target_injected_windows"),
    ("paths: READONLY is cleared by resolved path without the handle identity check", CP,
     ("        if _identity(fst) != _identity(st) or _attrs(fst) & _REPARSE:\n"
      "            return f\"{path} changed before its read-only flag was cleared\", False\n"
      "        if links > 1:\n"
      "            if _win_dispose(handle):\n"
      "                return \"\", True\n"
      "            return (f\"read-only file with {links} links: cannot delete without changing the shared file: \"\n"
      "                    f\"{path}\"), False\n"
      "        if not _win_set_attrs(handle, _attrs(fst)):\n"),
     ("        if False:\n"
      "            return f\"{path} changed before its read-only flag was cleared\", False\n"
      "        if links > 1:\n"
      "            if _win_dispose(handle):\n"
      "                return \"\", True\n"
      "            return (f\"read-only file with {links} links: cannot delete without changing the shared file: \"\n"
      "                    f\"{path}\"), False\n"
      "        if not ctypes.windll.kernel32.SetFileAttributesW(os.path.realpath(path), _settable(_attrs(st))):\n"),
     _T + "test_c10_swap_before_attr_clear_refused"),
    ("paths: the READONLY flag is never cleared", CP,
     ("        if not _win_set_attrs(handle, _attrs(fst)):\n"
      "            return f\"could not clear the read-only flag of {path}"),
     ("        if False:\n"
      "            return f\"could not clear the read-only flag of {path}"),
     _T + "test_c10_readonly_tree_removed"),
    ("paths: a hard-linked read-only file has its shared flag cleared", CP,
     "        if links > 1:\n",
     "        if False:\n",
     _T + "test_c10_hardlinked_readonly_file"),
)

PATHS_MUTATIONS = _COMMON + (_WINDOWS if os.name == "nt" else _POSIX)
