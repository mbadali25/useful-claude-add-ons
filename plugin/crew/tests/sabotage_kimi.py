"""Mutations for the Kimi Code provider (T-0028) -- kept in a module of its own,
same shape as sabotage_event_claim.py, a sibling of sabotage.py so that file
stays under `.pylintrc`'s max-module-lines.

One mutation per new guard branch: each reintroduces the bug the branch exists
to prevent, and sabotage.py confirms the named test goes red for real.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
PROBE = os.path.join(SCRIPTS, "kimi_probe.py")
RUN = os.path.join(SCRIPTS, "review_run.py")
VERDICT = os.path.join(SCRIPTS, "review_verdict.py")
STATE = os.path.join(SCRIPTS, "crew_state.py")
PROVIDERS_SH = os.path.join(CREW, "skills", "crew-setup", "scripts", "providers.sh")
REVIEW_MD = os.path.join(CREW, "commands", "review.md")
SKILL_MD = os.path.join(CREW, "skills", "crew-providers", "SKILL.md")
VERIFY = os.path.join(os.path.dirname(os.path.dirname(CREW)), ".crew", "verify.json")
_P = "tests/test_kimi_probe.py::"
_R = "tests/test_review_run_kimi.py::"
_D = "tests/test_kimi_docs.py::"
_W = "tests/test_worktree_config.py::"
# Successor 2026-09-30: the gate preflight ignores --allow-unverified.
_ALLOW = ("        if args.allow_unverified:\n"
          '            sys.stderr.write(f"review-run: gate {state}: {reason}. Reviewing anyway "\n')
_ALLOW_OFF = ("        if False:  # sabotage\n"
              '            sys.stderr.write(f"review-run: gate {state}: {reason}. Reviewing anyway "\n')
# Successor 2026-09-30: graph_out reads only the worktree's own .crew/ again.
_RESOLVED = ("    crew_dir, source, _detail = crew_common.repo_config_dir(top)\n"
             "    if source == crew_common.SOURCE_UNKNOWN:\n"
             "        return None\n"
             "    cfg = {}\n"
             "    for name in crew_common.CONFIG_NAMES:\n"
             "        path = os.path.join(crew_dir, name)\n")
_OWN_PATH = ("    cfg = {}\n"
             '    for name in ("crew.json", "config.json"):\n'
             '        path = os.path.join(top, ".crew", name)\n')
_HEAD_CHECK = ('    if not head:\n'
               '        unknown("HEAD could not be read (not a git repository?)")\n'
               '        return None\n')
_STATUS_CHECK = ('    if status is None or staged is None:\n'
                 '        unknown("git status or git ls-files failed or timed out")\n'
                 '        return None\n')
_SNAPSHOT_CALLS = (
    '    scope = ["--", "."] if _depth else ["--", ".", ":(exclude).work"]\n'
    '    status = _git_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all",\n'
    '                               "--no-renames",\n'
    '                               "--ignored=traditional", *scope], env)\n'
    '    staged = _git_bytes(root, ["ls-files", "--stage", "-z", *scope], env)\n')
_GIT_CALL = (
    "    try:\n"
    '        done = subprocess.run(["git", *GIT_OVERRIDES, *args], cwd=root, env=env,\n'
    "                              capture_output=True,\n"
    "                              stdin=subprocess.DEVNULL, timeout=SNAPSHOT_GIT_TIMEOUT,\n"
    "                              check=False)\n"
    "    except (OSError, subprocess.SubprocessError):\n"
    "        return None\n")
_OK_BRANCH = (
    "    if code == 0 and error is None and message is not None \\\n"
    "            and message.strip() == PROBE_MARKER:\n"
    '        return "ok", "answered PROBE_OK"\n')
_QUOTA_BRANCH = (
    '    if _QUOTA_MARKERS.search(blob) or _QUOTA_STATUS.search(stderr or "") \\\n'
    "            or '\"status_code\":429' in (stdout or \"\").replace(\" \", \"\"):\n"
    '        return "rate-limited", "the Kimi CLI answered with a quota or rate limit"\n')

# Round 4 FIX 3: the metadata keys and the separate `seen` set, reverted together to
# the `:HEAD`/`:index` keys that collided with tracked files of those names.
_KEYS = (
    '    snapshot = {HEAD_KEY: head, INDEX_KEY: hashlib.sha256(staged).hexdigest()}\n'
    '    listed = [(entry[:2].decode("ascii", "replace"), entry[3:])\n'
    '              for entry in status.split(b"\\0") if len(entry) >= 4]\n'
    '    listed += [("--", entry.split(b"\\t", 1)[1]) for entry in staged.split(b"\\0")\n'
    '               if b"\\t" in entry]\n'
    '    seen = set()\n'
    '    for code, raw in listed:\n'
    '        rel = os.fsdecode(raw).rstrip("/")\n'
    '        if rel in seen:\n'
    '            continue  # status listed it first, with its code\n'
    '        seen.add(rel)\n')
_KEYS_OLD = (
    '    snapshot = {":HEAD": head, ":index": hashlib.sha256(staged).hexdigest()}\n'
    '    listed = [(entry[:2].decode("ascii", "replace"), entry[3:])\n'
    '              for entry in status.split(b"\\0") if len(entry) >= 4]\n'
    '    listed += [("--", entry.split(b"\\t", 1)[1]) for entry in staged.split(b"\\0")\n'
    '               if b"\\t" in entry]\n'
    '    for code, raw in listed:\n'
    '        rel = os.fsdecode(raw).rstrip("/")\n'
    '        if rel in snapshot:\n'
    '            continue  # status listed it first, with its code\n')

KIMI_MUTATIONS = (
    # --- the probe: "could not tell" must never become `ok` ---------------
    ("kimi probe: unrecognised output collapses into ok",
     PROBE,
     '    return "unknown", (f"exit {code}, no {PROBE_MARKER}"',
     '    return "ok", (f"exit {code}, no {PROBE_MARKER}"',
     _P + "test_probe_unrecognised_output_is_unknown"),
    ("kimi probe: a timeout reads as ok",
     PROBE,
     '        return "unknown", f"the probe did not answer within {timeout}s"',
     '        return "ok", f"the probe did not answer within {timeout}s"',
     _P + "test_probe_timeout_is_unknown"),
    ("kimi probe: the quota classification is dropped",
     PROBE,
     '        return "rate-limited", "the Kimi CLI answered with a quota or rate limit"',
     '        pass',
     _P + "test_probe_quota_is_rate_limited"),
    ("kimi probe: the auth classification is dropped",
     PROBE,
     '        return "not-authenticated", "the Kimi CLI refused the credential - run `kimi login`"',
     '        pass',
     _P + "test_probe_401_is_not_authenticated"),
    ("kimi probe: a missing config.toml reads as ok",
     PROBE,
     '        return _result("not-authenticated", "no config.toml in the Kimi Code home - "',
     '        return _result("ok", "no config.toml in the Kimi Code home - "',
     _P + "test_probe_no_config_is_not_authenticated"),
    ("kimi probe: the stored-credential check is skipped",
     PROBE,
     "    if not present:",
     "    if False:",
     _P + "test_probe_no_credential_is_not_authenticated"),
    ("kimi probe: tomllib missing reads as ok",
     PROBE,
     '        return _result("unknown", "tomllib is unavailable (Python < 3.11), so "',
     '        return _result("ok", "tomllib is unavailable (Python < 3.11), so "',
     _P + "test_probe_without_tomllib_is_unknown"),
    ("kimi probe: an id no alias serves reads as ok",
     PROBE,
     '            return None, ("unknown", f"no alias in config.toml serves model id "',
     '            return None, ("ok", f"no alias in config.toml serves model id "',
     _P + "test_probe_id_with_no_kimi_alias_is_unknown"),
    ("kimi probe: an alias on a non-kimi provider is accepted",
     PROBE,
     '        if kind == "kimi":\n            return alias, None',
     '        if True:\n            return alias, None',
     _P + "test_probe_alias_on_non_kimi_provider_is_unknown"),
    ("kimi probe: launchable admits unknown",
     PROBE,
     '    return state == "ok"',
     '    return state in ("ok", "unknown")',
     _P + "test_only_ok_is_launchable"),
    ("kimi_env keeps the KIMI_MODEL_* overrides",
     PROBE,
     '           if k != "KIMI_CODE_INFINITE_RETRY" and not k.startswith("KIMI_MODEL_")}',
     '           if k != "KIMI_CODE_INFINITE_RETRY"}',
     _R + "test_run_kimi_argv_and_env"),
    ("kimi_env keeps the infinite-retry switch",
     PROBE,
     '           if k != "KIMI_CODE_INFINITE_RETRY" and not k.startswith("KIMI_MODEL_")}',
     '           if not k.startswith("KIMI_MODEL_")}',
     _P + "test_kimi_env_drops_retry_and_model_overrides"),
    ("kimi probe: stderr is echoed unredacted",
     PROBE,
     '    return _SECRETS.sub("[redacted]", text or "")',
     '    return text or ""',
     _P + "test_redact_masks_key_and_jwt_shapes"),
    # --- round 2 NIT kimi_probe.py:223: PROBE_OK before the quota markers ----
    ("kimi probe: the rate limit is checked before PROBE_OK again",
     PROBE,
     _OK_BRANCH + _QUOTA_BRANCH,
     _QUOTA_BRANCH + _OK_BRANCH,
     _P + "test_classify_a_retried_429_that_completed_is_ok"),
    ("kimi probe: PROBE_OK beside a failed turn reads ok",
     PROBE,
     "    if code == 0 and error is None and message is not None",
     "    if code == 0 and message is not None",
     _P + "test_classify_probe_ok_beside_a_failed_turn_is_not_ok"),
    # --- the family: fixed by provider, so `k3` never parses as `k` --------
    ("family(kimi, k3) falls through to the model string",
     STATE,
     '    if provider == "kimi":\n        return "kimi"\n',
     '',
     "tests/test_provider_table.py::test_family_kimi_is_provider_determined"),
    ("family(codex, k3) is the letter k again (round 1 NIT crew_state.py:1460)",
     STATE,
     '        if re.match(r"k\\d", bare):\n            return "kimi"\n',
     '',
     "tests/test_provider_table.py::test_family_of_a_bare_kimi_code_id_is_kimi_whoever_serves_it"),
    ("the bare-id rule swallows every k-name",
     STATE,
     '        if re.match(r"k\\d", bare):\n',
     '        if bare.startswith("k"):\n',
     "tests/test_provider_table.py::test_the_kimi_code_id_rule_leaves_its_neighbours_alone"),
    # --- review_run: probe before reserve, read-only controls --------------
    ("review_run: a failed kimi probe still launches and spends a round",
     RUN,
     '    if not kimi_probe.launchable(probed["state"]):',
     '    if False:',
     _R + "test_run_kimi_quota_spends_no_round"),
    ("review_run: a reviewer's tree change is not a reason",
     RUN,
     "        if changed:\n            extra.append(",
     "        if False:\n            extra.append(",
     _R + "test_run_kimi_tree_change_is_incomplete"),
    ("review_run: the tree fingerprint forgets HEAD",
     RUN,
     '    snapshot = {HEAD_KEY: head, INDEX_KEY',
     '    snapshot = {INDEX_KEY',
     _R + "test_tree_fingerprint_sees_a_move_of_head_alone"),
    ("review_run: an unfingerprintable tree reads as unchanged",
     RUN,
     "    if before is None or after is None:\n        extra.append(KIMI_TREE_UNKNOWN)\n    else:",
     "    if False:\n        pass\n    else:",
     _R + "test_run_kimi_unfingerprintable_tree_is_incomplete"),
    # The HEAD and status None exits go together: outside a repository each
    # one alone masks the other, so removing only one would stay green for a
    # reason unrelated to the branch it names.
    ("review_run: a failed git call still yields a fingerprint",
     RUN,
     _HEAD_CHECK + _SNAPSHOT_CALLS + _STATUS_CHECK,
     _SNAPSHOT_CALLS + "    status, staged = status or b'', staged or b''\n",
     _R + "test_tree_fingerprint_outside_a_repository_is_none"),
    # --- round 1 FIX review_run.py:179: untracked and ignored contents -------
    ("review_run: an untracked file's CONTENTS are not hashed",
     RUN,
     '        snapshot[rel] = f"{code} {digest}"',
     '        snapshot[rel] = code',
     _R + "test_tree_fingerprint_sees_untracked_and_ignored_contents"),
    ("review_run: ignored files are left out of the fingerprint",
     RUN,
     '                               "--ignored=traditional", *scope], env)',
     '                               *scope], env)',
     _R + "test_tree_fingerprint_sees_untracked_and_ignored_contents"),
    ("review_run: a staged-only change is not in the fingerprint",
     RUN,
     '    snapshot = {HEAD_KEY: head, INDEX_KEY: hashlib.sha256(staged).hexdigest()}',
     '    snapshot = {HEAD_KEY: head}',
     _R + "test_tree_fingerprint_sees_untracked_and_ignored_contents"),
    ("review_run: a git that cannot start or hangs raises instead of None",
     RUN,
     _GIT_CALL,
     '    done = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True,\n'
     "                          stdin=subprocess.DEVNULL, check=False)\n",
     _R + "test_tree_fingerprint_git_that_fails_to_run_is_none"),
    # --- round 1 FIX review_run.py:464: the background graph rebuild ---------
    ("review_run: a graph rebuild is blamed on the reviewer again",
     RUN,
     "        if graph and _under(path, graph):\n",
     "        if False:\n",
     _R + "test_run_kimi_graph_rebuild_during_the_review_is_not_the_reviewers"),
    ("review_run: the graph exemption swallows every path",
     RUN,
     "        if graph and _under(path, graph):\n",
     "        if graph:\n",
     _R + "test_run_kimi_a_write_beside_the_graph_is_still_incomplete"),
    ("review_run: the graph exemption matches by prefix, not by segment",
     RUN,
     "    return len(parts) > len(stem) and parts[:len(stem)] == stem",
     '    return rel.startswith(directory)',
     _R + "test_run_kimi_a_write_beside_the_graph_is_still_incomplete"),
    ("review_run: a configured graph.out is ignored",
     RUN,
     '    value = crew_common.dict_or_empty(crew_common.dict_or_empty(cfg).get("graph")).get("out")',
     '    value = None',
     _R + "test_run_kimi_honours_a_configured_graph_out"),
    # --- round 2 FIX review_run.py:301: graph.out resolved before the review --
    ("review_run: graph.out is resolved after the review again",
     RUN,
     "        changed, set_aside = reviewer_changes(before, after, args.graph_out)",
     "        changed, set_aside = reviewer_changes(before, after, graph_out(args.root))",
     _R + "test_run_kimi_a_reviewer_that_moves_graph_out_is_incomplete"),
    ("review_run: crew config under graph.out is set aside",
     RUN,
     '        if path in (HEAD_KEY, INDEX_KEY) or path in CREW_CONFIG_PATHS:',
     '        if path in (HEAD_KEY, INDEX_KEY):',
     _R + "test_run_kimi_a_crew_config_write_counts_even_under_graph_out"),
    # --- round 2 FIX review_run.py:623: no before fingerprint, nothing spent --
    ("review_run: an unfingerprintable tree still probes and reserves",
     RUN,
     "            if before is None:\n"
     '                sys.stderr.write("review-run: kimi: unknown - cannot fingerprint',
     "            if False:\n"
     '                sys.stderr.write("review-run: kimi: unknown - cannot fingerprint',
     _R + "test_run_kimi_unreadable_file_spends_no_probe_and_no_round"),
    ("review_run: the unreadable path is not named",
     RUN,
     '            unknown(f"{rel} exists and cannot be read")\n',
     "",
     _R + "test_run_kimi_unreadable_file_spends_no_probe_and_no_round"),
    # --- round 2 FIX :221 / round 3 FIX :127: what is set aside ---------------
    ("review_run: crew hook logs and IDE files are the reviewer's again",
     RUN,
     "        elif _ignored_throughout(before, after, path) and _not_a_check_input(path):",
     "        elif False:",
     _R + "test_run_kimi_crew_hook_logs_and_ide_files_are_not_the_reviewers"),
    ("review_run: every ignored path is set aside, .env included",
     RUN,
     "        elif _ignored_throughout(before, after, path) and _not_a_check_input(path):",
     "        elif _ignored_throughout(before, after, path):",
     _R + "test_run_kimi_a_cache_or_gate_input_write_still_counts"),
    ("review_run: a non-ignored IDE path is set aside",
     RUN,
     "        elif _ignored_throughout(before, after, path) and _not_a_check_input(path):",
     "        elif _not_a_check_input(path):",
     _R + "test_run_kimi_an_ide_path_that_is_not_ignored_still_counts"),
    ("review_run: a __pycache__ write is set aside again (round 3 NIT :360)",
     RUN,
     'IDE_DIRS = (".idea", ".vscode")',
     'IDE_DIRS = (".idea", ".vscode", "__pycache__")',
     _R + "test_run_kimi_a_cache_or_gate_input_write_still_counts"),
    ("review_run: the crew log tuple widens to the verify marker",
     RUN,
     'CREW_LOGS = (".crew/guard.log", ".crew/.autoclear.log")',
     'CREW_LOGS = (".crew/guard.log", ".crew/.autoclear.log", ".crew/.verify-verified-at")',
     _R + "test_set_aside_names_are_the_fixed_tuples"),
    ("review_run: a bare IDE directory name counts as under it",
     RUN,
     "    if any(part in IDE_DIRS for part in parts[:-1]):",
     "    if any(part in IDE_DIRS for part in parts):",
     _R + "test_set_aside_matches_by_whole_segment_and_whole_name"),
    ("review_run: a marker's session key may hold a path",
     RUN,
     '    return any(rel.startswith(marker + "-") and "/" not in rel[len(marker) + 1:]',
     '    return any(rel.startswith(marker + "-")',
     _R + "test_set_aside_matches_by_whole_segment_and_whole_name"),
    # --- round 3 BLOCK :317: "ignored THROUGHOUT" -----------------------------
    ("review_run: ignored at EITHER end is enough to set a path aside",
     RUN,
     '    return bool(states) and all(s.startswith("!! ") for s in states)',
     '    return bool(states) and any(s.startswith("!! ") for s in states)',
     _R + "test_a_set_aside_path_whose_ignore_state_flipped_still_counts"),
    ("review_run: only the AFTER state decides ignored-throughout",
     RUN,
     "    states = [s for s in (before.get(rel), after.get(rel)) if s is not None]",
     "    states = [s for s in (after.get(rel),) if s is not None]",
     _R + "test_a_set_aside_path_whose_ignore_state_flipped_still_counts"),
    # --- round 3 FIX :246: every tracked file hashed --------------------------
    ("review_run: tracked files are trusted to git status again",
     RUN,
     '    listed += [("--", entry.split(b"\\t", 1)[1]) for entry in staged.split(b"\\0")\n'
     '               if b"\\t" in entry]\n',
     "",
     _R + "test_tree_fingerprint_sees_an_edit_git_status_does_not_report"),
    ("review_run: git status reports renames as two fields again (round 3 NIT :250)",
     RUN,
     '                               "--no-renames",\n',
     "",
     _R + "test_tree_fingerprint_reads_a_worktree_rename_as_two_paths"),
    # --- round 3 FIX :194: a directory is never the constant `dir` ------------
    ("review_run: a nested repository is hashed as `dir` again",
     RUN,
     '    if digest != "dir":\n        return digest\n',
     "    return digest\n",
     _R + "test_tree_fingerprint_sees_an_edit_inside_a_nested_repository"),
    ("review_run: a directory with no .git is the constant `dir`",
     RUN,
     "        return _walk_digest(path, root)",
     "        return digest",
     _R + "test_tree_fingerprint_sees_a_write_into_an_uninitialised_submodule"),
    ("review_run: a .git that walks up to the parent is fingerprinted anyway",
     RUN,
     "    if depth >= NESTED_DEPTH or not top or \\\n",
     "    if depth >= NESTED_DEPTH or not top or False and \\\n",
     _R + "test_a_git_dir_that_is_not_its_own_repository_is_could_not_tell"),
    ("review_run: nesting has no depth cap",
     RUN,
     "    if depth >= NESTED_DEPTH or not top or \\\n",
     "    if not top or \\\n",
     _R + "test_tree_fingerprint_nested_deeper_than_the_cap_is_none"),
    ("review_run: a nested repository with no commit is could-not-tell",
     RUN,
     '        head = "unborn"  # a nested repository with no commit yet\n',
     "        pass\n",
     _R + "test_tree_fingerprint_of_a_nested_repository_with_no_commit"),
    # --- round 3 NIT :628: the probe's own fingerprint ------------------------
    ("review_run: a failed fingerprint after the probe reads as clean again",
     RUN,
     "    if mid is None:\n",
     "    if False:\n",
     _R + "test_run_kimi_unfingerprintable_tree_after_the_probe_spends_no_round"),
    # --- round 3 NIT :643: a process left running -----------------------------
    ("review_run: what the review left running is not stopped",
     RUN,
     "    killed, survivor_unknown = stop_survivors(started) if not timed_out else (False, None)",
     "    killed, survivor_unknown = False, None",
     _R + "test_run_kimi_a_process_left_running_cannot_write_after_the_check"),
    ("review_run: the probe runs without its own process group again",
     RUN,
     "    probed = kimi_probe.probe(args.model or None, runner=_probe_runner)",
     "    probed = kimi_probe.probe(args.model or None)",
     _R + "test_run_kimi_a_process_left_running_cannot_write_after_the_check"),
    ("review_run: a zombie reads as a live survivor",
     RUN,
     'fields[0] not in ("Z", "X"):',
     "True:",
     _R + "test_group_alive_ignores_a_zombie_and_sees_a_live_member"),
    ("review_run: a survivor that will not die reads as stopped",
     RUN,
     "            return True, KIMI_SURVIVOR_UNKNOWN\n",
     "            return True, None\n",
     _R + "test_stop_survivors_that_will_not_die_is_could_not_tell"),
    ("review_run: an unstoppable review survivor is not a reason",
     RUN,
     "    if survivor_unknown:\n        extra.append(survivor_unknown)\n",
     "    if False:\n        extra.append(survivor_unknown)\n",
     _R + "test_run_kimi_a_review_survivor_that_will_not_die_is_incomplete"),
    ("review_run: an unstoppable probe survivor still launches the review",
     RUN,
     "    if not timed_out and stop_survivors(started)[1]:",
     "    if False:",
     _R + "test_run_kimi_a_probe_survivor_that_will_not_die_spends_no_round"),
    # --- round 3 FIX .crew/verify.json:168 and the review.md NITs -------------
    ("verify.json: crew-setup SKILL.md reaches no rule that runs test_crew_config.py again",
     VERIFY,
     '                "plugin/crew/skills/crew-setup/SKILL.md",\n'
     '                "plugin/crew/tests/test_crew_config.py",\n',
     '                "plugin/crew/tests/test_crew_config.py",\n',
     _D + "test_every_kimi_file_reaches_a_rule_that_runs_its_tests"),
    ("review.md: Kimi is labelled 2d beside the failing-control Step 2d again",
     REVIEW_MD,
     "**Step 2a — Codex, 2b — Copilot, 2e — Kimi.**",
     "**Step 2a — Codex, 2b — Copilot, 2d — Kimi.**",
     _D + "test_review_kimi_step_label_names_one_step"),
    ("review.md: the Kimi prose says only graph.out is set aside again",
     REVIEW_MD,
     "`.crew/guard.log`, `.crew/.autoclear.log`",
     "`.crew/.autoclear.log`",
     _D + "test_review_kimi_paragraph_names_what_is_set_aside"),
    # --- round 1 FIX kimi_probe.py:219: the probe is read-only and watched ---
    ("kimi probe: launched without the read-only agent file again",
     PROBE,
     '        cmd = [exe, "-p", PROBE_PROMPT, "-m", alias, "--output-format", "stream-json",\n'
     "               *read_only_flags(workdir)]",
     '        cmd = [exe, "-p", PROBE_PROMPT, "-m", alias, "--output-format", "stream-json"]',
     _P + "test_probe_runs_with_the_review_read_only_controls_outside_the_cwd"),
    ("kimi probe: runs in the caller's directory again",
     PROBE,
     "(cmd, kimi_env(), timeout, workdir)",
     "(cmd, kimi_env(), timeout, None)",
     _P + "test_probe_runs_with_the_review_read_only_controls_outside_the_cwd"),
    ("review_run: a probe that wrote the tree still reserves a round",
     RUN,
     "        if changed:\n            return EXIT_PROBE_CHANGED, (",
     "        if False:\n            return EXIT_PROBE_CHANGED, (",
     _R + "test_run_kimi_probe_that_writes_the_tree_spends_no_round"),
    ("review_run: the before-fingerprint is taken after the probe again",
     RUN,
     "            refusal = _probe_kimi(args, before)\n"
     "            if refusal:\n"
     "                sys.stderr.write(",
     "            refusal = _probe_kimi(args, None)\n"
     "            before = tree_fingerprint(args.root)\n"
     "            if refusal:\n"
     "                sys.stderr.write(",
     _R + "test_run_kimi_probe_that_writes_the_tree_spends_no_round"),
    ("kimi agent file allows write tools",
     PROBE,
     '            "tools: [Read, Grep, Glob]\\n"',
     '            "tools: [Read, Grep, Glob, Write, Edit, Bash]\\n"',
     _R + "test_kimi_agent_file_is_read_only"),
    # --- round 1 NITs ------------------------------------------------------------
    ("review_run: a kimi stream error is not a reason",
     RUN,
     '        extra.append(f"kimi: {kimi_probe.redact(error)}")',
     '        pass',
     _R + "test_run_kimi_failed_turn_is_incomplete_at_exit_0"),
    ("review_run: a kimi stream error reaches review.json unredacted",
     RUN,
     '        extra.append(f"kimi: {kimi_probe.redact(error)}")',
     '        extra.append(f"kimi: {error}")',
     _R + "test_run_kimi_stream_error_is_redacted_in_the_reasons"),
    ("review_run: review.json forgets the alias it launched",
     RUN,
     '"model_launched": getattr(args, "launched_model", None) or args.model or None,',
     '"model_launched": args.model or None,',
     _R + "test_run_kimi_records_the_alias_it_launched"),
    ("review_run: a spent budget still costs a probe request",
     RUN,
     "            and status.get(\"rounds_left\", 0) > 0)",
     "            or True)",
     _R + "test_run_kimi_with_the_budget_spent_spends_no_probe_request"),
    # --- round 1 FIX test_kimi_docs.py:103 and the prose/map fixes ----------------
    ("providers.sh: the kimi probe runs on every call, the if left in place",
     PROVIDERS_SH,
     '  probe="$(dirname "$0")/../../../hooks/scripts/kimi_probe.py"\n',
     '  probe="$(dirname "$0")/../../../hooks/scripts/kimi_probe.py"\n'
     '  python3 "$probe" >/dev/null 2>&1\n',
     _D + "test_providers_sh_reports_kimi_and_probes_only_on_request"),
    ("review.md: step 1b has no kimi strike row again",
     REVIEW_MD,
     "| `kimi` | `kimi`, and any Copilot pin to a `kimi-*` model |\n",
     "",
     _D + "test_review_step_1b_strikes_kimi_for_a_kimi_author"),
    ("verify.json: crew_state.py's rule stops running test_provider_table.py",
     VERIFY,
     "test_verify_absent_and_diagram_kind.py plugin/crew/tests/test_provider_table.py -q",
     "test_verify_absent_and_diagram_kind.py -q",
     _D + "test_every_kimi_file_reaches_a_rule_that_runs_its_tests"),
    ("verify.json: the fake kimi and its fixture reach no Kimi suite again",
     VERIFY,
     '                "plugin/crew/tests/review_fixtures.py",\n'
     '                "plugin/crew/tests/fixtures/kimi-stream-2.1.1/*",\n',
     "",
     _D + "test_every_kimi_file_reaches_a_rule_that_runs_its_tests"),
    ("verify.json: model.md reaches no rule that runs test_kimi_docs.py again",
     VERIFY,
     '                "plugin/crew/commands/model.md",\n'
     '                "plugin/crew/skills/crew-providers/alternative-providers.md"],',
     '                "plugin/crew/skills/crew-providers/alternative-providers.md"],',
     _D + "test_every_file_this_module_reads_is_mapped_to_it"),
    # --- the stream parser ---------------------------------------------------
    ("kimi_final_message: no assistant text is not an error",
     VERDICT,
     "    if error is None and message is None:\n"
     '        error = "the Kimi event stream has no assistant message"',
     "    if False:\n"
     '        error = "the Kimi event stream has no assistant message"',
     "tests/test_review_verdict.py::test_kimi_final_message_with_no_assistant_text_is_an_error"),
    ("kimi_final_message: a meta line's string content is read as the answer",
     VERDICT,
     '        if event.get("role") == "assistant":',
     '        if event.get("role") in ("assistant", "meta"):',
     "tests/test_review_verdict.py::"
     "test_kimi_final_message_ignores_a_meta_line_carrying_string_content"),
    # --- review round 4 (T-0028): one entry per FIX branch -------------------
    ("review_run: graph.out may be .crew or lie under a .crew again (round 4 FIX 1)",
     RUN,
     '    if ".crew" in rel.split("/"):\n        return None\n',
     "",
     _R + "test_graph_out_that_could_hold_a_check_input_is_none"),
    ("review_run: a .crew graph.out sets a forged gate input aside (round 4 FIX 1)",
     RUN,
     '    if ".crew" in rel.split("/"):\n        return None\n',
     "",
     _R + "test_run_kimi_a_crew_graph_out_with_nothing_tracked_in_it_sets_nothing_aside"),
    ("review.md: exit 8 is not named, so it reads as not run (round 4 FIX 7)",
     REVIEW_MD,
     "Exit 8 means the Kimi probe changed the working tree; stop and report the named paths",
     "Exit 8 means the Kimi probe changed the working tree; report the named paths",
     _D + "test_review_md_names_the_probe_changed_exit_code"),
    ("review_run: graph.out may contain a .crew again (round 4 FIX 1)",
     RUN,
     '        if ".crew" in dirs:\n            return None\n',
     "        pass\n",
     _R + "test_graph_out_that_could_hold_a_check_input_is_none"),
    ("review_run: graph.out may hold a tracked check input again (round 4 FIX 1)",
     RUN,
     "    if tracked is None or any(os.fsdecode(name) not in",
     "    if tracked is None and any(os.fsdecode(name) not in",
     _R + "test_graph_out_that_could_hold_a_check_input_is_none"),
    ("review_run: a symlink is digested by its target string only (round 4 FIX 2)",
     RUN,
     "            return _link_digest(path, root, _depth)\n",
     '            return "link:" + os.readlink(path)\n',
     _R + "test_run_kimi_an_edit_through_a_tracked_symlink_is_incomplete"),
    ("review_run: a link to a directory outside the repo is walked (round 4 FIX 2)",
     RUN,
     "        if not root or not _inside(real, os.path.realpath(root)):\n            return None\n",
     "",
     _R + "test_tree_fingerprint_a_link_to_a_directory_outside_the_repo_is_could_not_tell"),
    ("review_run: the metadata keys are :HEAD and :index again (round 4 FIX 3)",
     RUN,
     _KEYS,
     _KEYS_OLD,
     _R + "test_run_kimi_files_named_like_the_metadata_keys_are_hashed"),
    ("review_run: a file's digest drops its mode bits (round 4 FIX 4)",
     RUN,
     '        return f"{digest.hexdigest()}:{stat.S_IMODE(opened):o}"',
     "        return digest.hexdigest()",
     _R + "test_run_kimi_a_chmod_under_filemode_false_is_incomplete"),
    ("review_run: a Kimi round is reserved when the status says none (round 4 FIX 5)",
     RUN,
     "            if not _round_available(args.root, args.ticket):\n",
     "            if False:\n",
     _R + "test_run_kimi_with_no_round_in_the_status_is_refused_before_reserve"),
    ("review_run: a kill refused with PermissionError reads as gone (round 4 FIX 6)",
     RUN,
     "        return False, KIMI_SURVIVOR_UNKNOWN\n",
     "        return False, None\n",
     _R + "test_stop_survivors_a_kill_refused_with_permission_error_is_could_not_tell"),
    ("review_run: a group we may not signal reads as empty (round 4 FIX 6)",
     RUN,
     "        return True  # round 4 of T-0028: a member we may not signal is alive\n",
     "        return False\n",
     _R + "test_group_alive_without_proc_reads_a_permission_error_as_alive"),
    ("review_run: a failing probe returns before the post-probe fingerprint (round 4 FIX 7)",
     RUN,
     "    problems = []\n    mid = tree_fingerprint(args.root, problems)\n",
     '    if not kimi_probe.launchable(probed["state"]):\n'
     "        return EXIT_USAGE, answer\n"
     "    problems = []\n    mid = tree_fingerprint(args.root, problems)\n",
     _R + "test_run_kimi_a_failing_probe_that_wrote_the_tree_exits_probe_changed"),
    ("review_run: a FIFO is opened to be hashed (round 4 FIX 8)",
     RUN,
     "        if not stat.S_ISREG(mode):\n"
     '            return f"special:{stat.S_IFMT(mode):o}"\n'
     "        fd = os.open(path, _READ_FLAGS)\n",
     "        fd = os.open(path, os.O_RDONLY)\n",
     _R + "test_tree_fingerprint_never_opens_a_fifo"),
    ("kimi probe: a non-string provider reaches providers.get (round 4 FIX 9)",
     PROBE,
     "        if not isinstance(ref, str):\n"
     "            # Round 4 of T-0028: an array or inline table reached\n"
     "            # `providers.get` and raised TypeError.\n"
     "            unnamed = True\n"
     "            continue\n",
     "",
     _P + "test_probe_a_provider_reference_that_is_not_a_name_is_unknown"),
    ("kimi probe: the credential check takes a non-string provider (round 4 FIX 9)",
     PROBE,
     '    ref = _table(_table(config.get("models")).get(alias)).get("provider")\n'
     "    if not isinstance(ref, str):\n        return None, PROVIDER_NOT_A_NAME\n",
     '    ref = _table(_table(config.get("models")).get(alias)).get("provider")\n',
     _P + "test_resolve_alias_and_the_credential_check_refuse_a_non_string_provider"),
    ("kimi probe: a relative exe is kept (round 4 FIX 10)",
     PROBE,
     "    exe = os.path.abspath(exe)\n",
     "",
     _P + "test_probe_through_a_relative_path_entry_launches_the_absolute_exe"),
    ("kimi_final_message: a non-string text part is joined (round 4 FIX 11)",
     VERDICT,
     "        if not all(isinstance(text, str) for text in texts):\n            return None\n",
     "",
     "tests/test_review_verdict.py::test_kimi_final_message_a_non_string_text_part_is_malformed"),
    ("kimi_final_message: splitlines() cuts an event again (the merge with main)",
     VERDICT,
     '    for line in (jsonl or "").split("\\n"):  # "\\n" only, as codex_final_message\n'
     "        line = line.strip()\n"
     "        if not line:\n"
     "            continue\n"
     "        try:\n"
     "            event = json.loads(line)\n"
     "        except ValueError:\n"
     "            event = None\n"
     "        if not isinstance(event, dict):\n"
     "            if error is None:\n"
     '                error = f"unparseable Kimi event line',
     '    for line in (jsonl or "").splitlines():\n'
     "        line = line.strip()\n"
     "        if not line:\n"
     "            continue\n"
     "        try:\n"
     "            event = json.loads(line)\n"
     "        except ValueError:\n"
     "            event = None\n"
     "        if not isinstance(event, dict):\n"
     "            if error is None:\n"
     '                error = f"unparseable Kimi event line',
     "tests/test_review_verdict.py::"
     "test_kimi_final_message_an_event_holding_a_unicode_line_break_parses_intact"),
    # --- successor 2026-09-30 (owner "Adapt, probe then preflight") ---------------
    ("review_run: main's gate preflight runs before the Kimi probe (successor (1))",
     RUN,
     '        if args.provider == "kimi":\n'
     "            # A Kimi round is never reserved unprobed",
     '        if args.provider == "kimi":\n'
     "            short = preflight(args)\n"
     "            if short is not None:\n"
     "                return short\n"
     "            # A Kimi round is never reserved unprobed",
     _R + "test_run_kimi_probes_before_the_gate_preflight"),
    ("review_run: preflight ignores --allow-unverified (successor (2), graph.out moved)",
     RUN, _ALLOW, _ALLOW_OFF,
     _R + "test_run_kimi_a_reviewer_that_moves_graph_out_is_incomplete"),
    ("review_run: preflight ignores --allow-unverified (successor (2), .crew graph.out)",
     RUN, _ALLOW, _ALLOW_OFF,
     _R + "test_run_kimi_a_crew_graph_out_sets_nothing_aside"),
    ("review_run: graph_out reads the lane's own .crew/ again (successor (3))",
     RUN, _RESOLVED, _OWN_PATH,
     _W + "test_graph_out_in_a_lane_reads_the_main_checkouts_config"),
    ("review_run: graph_out's own-path read is back, uncounted (successor (3)/(4))",
     RUN, _RESOLVED, _OWN_PATH,
     _W + "test_no_module_reads_repo_config_outside_the_resolver"),
    ("review_run: an unknown config source still sets graph.out aside (successor (3))",
     RUN,
     "    if source == crew_common.SOURCE_UNKNOWN:\n        return None\n    cfg = {}\n",
     "    cfg = {}\n",
     _W + "test_graph_out_is_none_when_git_could_not_tell_whose_config"),
    ("crew-providers SKILL.md names the pre-merge probe-changed exit 5 again",
     SKILL_MD,
     "answered, exits 8 with no round spent",
     "answered, exits 5 with no round spent",
     _D + "test_crew_providers_names_the_probe_changed_exit_code"),
    # --- review round 5 (T-0028): one entry per FIX -----------------------------
    ("review.md: a failed Kimi probe always skips, even when pinned (round 5 FIX 1)",
     REVIEW_MD,
     "skip it when `qa.provider` is `auto`; a pinned `kimi` hard-fails, as a pinned `codex` does.",
     "skip.",
     _D + "test_review_md_a_pinned_kimi_hard_fails_on_a_failed_probe"),
    ("kimi probe: an unreadable credentials directory is no credential (round 5 FIX 2)",
     PROBE,
     "    except OSError as exc:\n"
     '        return None, (f"the Kimi credentials directory could not be read "\n',
     "    except OSError as exc:  # sabotage\n"
     "        return False, None\n"
     '        return None, (f"the Kimi credentials directory could not be read "\n',
     _P + "test_probe_an_unreadable_credentials_directory_is_unknown"),
    ("kimi probe: any answer containing PROBE_OK is ok (round 5 FIX 3)",
     PROBE,
     "            and message.strip() == PROBE_MARKER:\n",
     "            and PROBE_MARKER in message:\n",
     _P + "test_classify_an_answer_that_only_contains_the_marker_is_not_ok"),
    ("kimi probe: a config.toml that is a directory reads as no config (round 5 FIX 4)",
     PROBE,
     "    if not stat.S_ISREG(mode):\n",
     "    if False:  # sabotage\n",
     _P + "test_probe_a_config_toml_that_is_a_directory_is_unknown"),
    ("kimi probe: a failed config.toml lookup reads as no config (round 5 FIX 4)",
     PROBE,
     "    except FileNotFoundError:\n"
     '        return _result("not-authenticated", "no config.toml in the Kimi Code home - "\n',
     "    except OSError:\n"
     '        return _result("not-authenticated", "no config.toml in the Kimi Code home - "\n',
     _P + "test_probe_a_config_toml_lookup_that_fails_is_unknown"),
    ("kimi probe: a failed scratch directory escapes as an exception (round 5 FIX 5)",
     PROBE,
     "    except OSError as exc:  # round 5 of T-0028: no scratch directory is `unknown`\n",
     "    except ArithmeticError as exc:  # sabotage\n",
     _P + "test_probe_that_cannot_create_its_scratch_directory_is_unknown"),
    ("review_run: invalid config JSON falls back to the graphify-out exemption (round 5 FIX 6)",
     RUN,
     "            return None  # round 5 of T-0028: invalid JSON sets nothing aside\n",
     "            cfg = {}\n",
     _R + "test_graph_out_with_a_config_that_does_not_parse_as_an_object_is_none"),
    ("review_run: an unreadable config falls back to the graphify-out exemption (round 5 FIX 6)",
     RUN,
     "                return None  # round 5 of T-0028: unreadable is could-not-tell\n",
     "                pass\n",
     _R + "test_graph_out_with_a_config_that_exists_but_cannot_be_read_is_none"),
    ("kimi_final_message: a non-object content member is skipped (round 5 FIX 7)",
     VERDICT,
     "        if not all(isinstance(p, dict) for p in content):\n            return None\n",
     "        content = [p for p in content if isinstance(p, dict)]\n",
     "tests/test_review_verdict.py::"
     "test_kimi_final_message_a_non_object_content_member_is_malformed"),
    ("kimi_final_message: a retry carrying an error object is terminal (round 5 FIX 8)",
     VERDICT,
     '    if event.get("type") == "turn.step.retrying":\n        return None\n',
     "",
     "tests/test_review_verdict.py::"
     "test_kimi_final_message_a_retry_carrying_an_error_object_is_not_a_failure"),
)
