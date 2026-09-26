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
VERIFY = os.path.join(os.path.dirname(os.path.dirname(CREW)), ".crew", "verify.json")
_P = "tests/test_kimi_probe.py::"
_R = "tests/test_review_run_kimi.py::"
_D = "tests/test_kimi_docs.py::"
_HEAD_CHECK = "    if not head:\n        return None\n"
_STATUS_CHECK = "    if status is None or staged is None:\n        return None\n"
_SNAPSHOT_CALLS = (
    '    scope = ["--", ".", ":(exclude).work"]\n'
    '    status = _git_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all",\n'
    '                               "--ignored=traditional", *scope], env)\n'
    '    staged = _git_bytes(root, ["diff", "--cached", "--binary", *scope], env)\n')
_GIT_CALL = (
    "    try:\n"
    '        done = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True,\n'
    "                              stdin=subprocess.DEVNULL, timeout=SNAPSHOT_GIT_TIMEOUT,\n"
    "                              check=False)\n"
    "    except (OSError, subprocess.SubprocessError):\n"
    "        return None\n")

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
     "    if not _credential_present(config, alias, home):",
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
     '    snapshot = {":HEAD": head, ":index"',
     '    snapshot = {":index"',
     _R + "test_tree_fingerprint_sees_a_committed_edit"),
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
     '    snapshot = {":HEAD": head, ":index": hashlib.sha256(staged).hexdigest()}',
     '    snapshot = {":HEAD": head}',
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
     "                 if graph and not p.startswith(\":\") and _under(p, graph)]",
     "                 if False]",
     _R + "test_run_kimi_graph_rebuild_during_the_review_is_not_the_reviewers"),
    ("review_run: the graph exemption swallows every path",
     RUN,
     "                 if graph and not p.startswith(\":\") and _under(p, graph)]",
     "                 if graph]",
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
     "        if changed:\n            return f\"{KIMI_PROBE_CHANGED}",
     "        if False:\n            return f\"{KIMI_PROBE_CHANGED}",
     _R + "test_run_kimi_probe_that_writes_the_tree_spends_no_round"),
    ("review_run: the before-fingerprint is taken after the probe again",
     RUN,
     "                refusal = _probe_kimi(args, before)\n"
     "                if refusal:\n"
     "                    sys.stderr.write(",
     "                refusal = _probe_kimi(args, None)\n"
     "                before = tree_fingerprint(args.root)\n"
     "                if refusal:\n"
     "                    sys.stderr.write(",
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
    ("review_run: a round granted after a stale status launches unprobed",
     RUN,
     "            refusal = _probe_kimi(args, before)\n            if refusal:\n"
     "                return finish(",
     "            refusal = None\n            args.kimi_exe = args.launched_model = 'x'\n"
     "            if refusal:\n                return finish(",
     _R + "test_run_kimi_probes_after_the_reservation_when_the_status_was_stale"),
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
)
