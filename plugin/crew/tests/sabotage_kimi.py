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
_P = "tests/test_kimi_probe.py::"
_R = "tests/test_review_run_kimi.py::"
_HEAD_CHECK = "    if not head:\n        return None\n"
_FINGERPRINT_LOOP = (
    "    digest = hashlib.sha256(str(head).encode())\n"
    '    for args in (["status", "--porcelain=v1", "-z", "--untracked-files=all"],\n'
    '                 ["diff", "HEAD", "--binary"]):\n'
    '        done = subprocess.run(["git", *args, "--", ".", ":(exclude).work"], cwd=root,\n'
    "                              env=env, capture_output=True, stdin=subprocess.DEVNULL,\n"
    "                              check=False)\n")
_RC_CHECK = "        if done.returncode != 0:\n            return None\n"

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
    # --- review_run: probe before reserve, read-only controls --------------
    ("review_run: a failed kimi probe still launches and spends a round",
     RUN,
     '            if not kimi_probe.launchable(probed["state"]):',
     '            if False:',
     _R + "test_run_kimi_quota_spends_no_round"),
    ("review_run: the tree fingerprint compare is forced equal",
     RUN,
     "        elif after != before:",
     "        elif False:",
     _R + "test_run_kimi_tree_change_is_incomplete"),
    ("review_run: the tree fingerprint forgets HEAD",
     RUN,
     '    digest = hashlib.sha256(str(head).encode())',
     '    digest = hashlib.sha256()',
     _R + "test_tree_fingerprint_sees_a_committed_edit"),
    ("review_run: an unfingerprintable tree reads as unchanged",
     RUN,
     "        if before is None or after is None:\n            extra.append(KIMI_TREE_UNKNOWN)\n        elif",
     "        if",
     _R + "test_run_kimi_unfingerprintable_tree_is_incomplete"),
    # Both None exits go together: outside a repository each one alone
    # masks the other, so removing only one would stay green for a reason
    # unrelated to the branch it names.
    ("review_run: a failed git call still yields a fingerprint",
     RUN,
     _HEAD_CHECK + _FINGERPRINT_LOOP + _RC_CHECK,
     _FINGERPRINT_LOOP,
     _R + "test_tree_fingerprint_outside_a_repository_is_none"),
    ("review_run: the kimi agent file allows write tools",
     RUN,
     '                        "tools: [Read, Grep, Glob]\\n"',
     '                        "tools: [Read, Grep, Glob, Write, Edit, Bash]\\n"',
     _R + "test_kimi_agent_file_is_read_only"),
    ("review_run: a kimi stream error is not a reason",
     RUN,
     '            extra.append(f"kimi: {error}")',
     '            pass',
     _R + "test_run_kimi_failed_turn_is_incomplete_at_exit_0"),
    # --- the stream parser ---------------------------------------------------
    ("kimi_final_message: no assistant text is not an error",
     VERDICT,
     "    if error is None and message is None:\n"
     '        error = "the Kimi event stream has no assistant message"',
     "    if False:\n"
     '        error = "the Kimi event stream has no assistant message"',
     "tests/test_review_verdict.py::test_kimi_final_message_with_no_assistant_text_is_an_error"),
)
