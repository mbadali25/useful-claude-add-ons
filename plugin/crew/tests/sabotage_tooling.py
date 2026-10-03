"""The T-0087 tooling-reliability mutations, appended to `sabotage.py`'s
MUTATIONS: everything that can grant review budget (the refund) or hide a
break at a review-format seam (the golden replay, the contracts, the canary).
Kept apart only because `sabotage.py` sits at `.pylintrc`'s max-module-lines;
the runner, its restore guarantees and its reporting are all `sabotage.py`'s.
Run that file, not this one.
"""
import os
import shutil

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
REVIEW_VERDICT = os.path.join(SCRIPTS, "review_verdict.py")
REVIEW_LEDGER = os.path.join(SCRIPTS, "review_ledger.py")
REVIEW_RUN = os.path.join(SCRIPTS, "review_run.py")
REVIEW_PATCH = os.path.join(SCRIPTS, "review_patch.py")
CREW_STATUS = os.path.join(SCRIPTS, "crew_status.py")
CREW_AUTOPILOT = os.path.join(SCRIPTS, "crew_autopilot.py")
VERIFY_RECORD = os.path.join(SCRIPTS, "verify_record.py")
GOLDEN_BUILD = os.path.join(CREW, "tests", "golden_build.py")
FORMATS_TEST = os.path.join(CREW, "tests", "test_external_tool_formats.py")
GOLDEN_TEST = os.path.join(CREW, "tests", "test_review_golden.py")
GOLDEN_ATTRIBUTES = os.path.join(CREW, "tests", "golden", ".gitattributes")
REPO = os.path.dirname(os.path.dirname(CREW))
CHECKER = os.path.join(REPO, "scripts", "check-tooling-pr.py")
VERIFY_JSON = os.path.join(REPO, ".crew", "verify.json")

TOOLING_MUTATIONS = (
    (
        # (a) A bundle/webtest reason no longer outranks "not delivered": a
        # round whose tree moved under the reviewer is refunded as the tool's.
        "a tree reason no longer outranks a tool failure",
        REVIEW_VERDICT,
        "    if tree:\n        return TREE\n",
        "    if False:\n        return TREE\n",
        "tests/test_review_refund.py::test_tree_changed_round_is_not_refunded",
    ),
    (
        # (b) Every INCOMPLETE is the tool's: a reviewer that broke the
        # contract gets its round back.
        "every INCOMPLETE is classed a tool failure",
        REVIEW_VERDICT,
        "    return REVIEWER if delivered else TOOL\n",
        "    return TOOL\n",
        "tests/test_review_refund.py::test_contract_broken_round_is_not_refunded",
    ),
    (
        # (c) No limit: a tool that always fails loops forever on refunds.
        "refunds are unlimited",
        REVIEW_LEDGER,
        '            row["refunded"] = _refunded(data) < REFUND_LIMIT\n',
        '            row["refunded"] = True\n',
        "tests/test_review_refund.py::test_refund_limit_is_two_per_plan",
    ),
    (
        # (d) The refund is recorded but the budget still counts the round.
        "reserve charges refunded rounds against the budget",
        REVIEW_LEDGER,
        "        if _charged(data) >= BUDGET:\n",
        "        if _spent(data) >= BUDGET:\n",
        "tests/test_review_refund.py::test_refunded_rounds_do_not_exhaust_the_budget",
    ),
    (
        # (e) What status and autopilot are told disagrees with the budget.
        "rounds_left ignores refunds",
        REVIEW_LEDGER,
        '            "rounds_left": max(0, BUDGET - _charged(data)), "rounds": rounds,\n',
        '            "rounds_left": max(0, BUDGET - _spent(data)), "rounds": rounds,\n',
        "tests/test_review_refund.py::test_turn_failed_round_is_refunded",
    ),
    (
        # (f) The pre-T-0079 rule: a full-path READ line covers nothing, and
        # every honest real review that echoed the listed path is INCOMPLETE.
        "READ lines are compared by bare name only again",
        REVIEW_VERDICT,
        "    token, listed = _norm(token), _norm(listed)\n",
        "    token, listed = _norm(token), posixpath.basename(_norm(listed))\n",
        "tests/test_review_golden.py::test_golden_outputs_replay_to_their_recorded_verdicts",
    ),
    (
        # (g) splitlines() cuts an event at a raw U+2028 (T-0072 round 4).
        # T-0079's entry mutates the same line against a unit test; this one
        # proves the real stream in the golden corpus catches it too.
        "the Codex stream is split with splitlines again",
        REVIEW_VERDICT,
        '    for line in (jsonl or "").split("\\n"):\n',
        '    for line in (jsonl or "").splitlines():\n',
        "tests/test_review_golden.py::test_golden_codex_stream_yields_its_out_txt",
    ),
    (
        # (h) The producer stops writing a key a consumer reads.
        "the manifest loses patch_bytes",
        REVIEW_PATCH,
        '        "patch_bytes": len(patch),\n',
        "",
        ("tests/test_review_contracts.py::"
         "test_manifest_consumers_read_only_keys_the_producer_writes"),
    ),
    (
        # (i) Status counts every row against a hard-coded 2 again, so a
        # refunded round reads as spent.
        "status counts every row against a hard-coded 2 again",
        CREW_STATUS,
        "        used = f\"{summary['rounds_spent']}/{summary['budget']} rounds used\"\n",
        "        used = f\"{summary['rounds_used']}/2 rounds used\"\n",
        "tests/test_status.py::test_status_review_line_shows_budget_and_refunds",
    ),
    (
        # (j) Autopilot stops on a refunded round as on any INCOMPLETE.
        "autopilot stops on a refunded round like any INCOMPLETE",
        CREW_AUTOPILOT,
        '    if latest.get("refunded") is True and not ok:\n',
        "    if False:\n",
        "tests/test_crew_autopilot.py::test_next_refunded_incomplete_goes_to_review",
    ),
    (
        # (k) A record whose rules are not an object reads as "nothing owed".
        "a corrupt gate record reads as ok",
        VERIFY_RECORD,
        '    if not isinstance(data.get("rules"), dict):\n        return "corrupt", {}\n',
        '    if not isinstance(data.get("rules"), dict):\n        return "ok", {}\n',
        "tests/test_review_contracts.py::test_gate_record_consumers_share_one_reader",
    ),
    (
        # (l) The pre-T-0079 line: the parser is handed bare part names while
        # the reviewer echoes full paths. T-0079's (e) mutates the same line
        # against a unit test; this proves the end-to-end canary catches it.
        "review_run passes bare part names to the parser again",
        REVIEW_RUN,
        '    parts = [p.get("path") or p["name"] for p in manifest.get("parts") or []]\n',
        '    parts = [p["name"] for p in manifest.get("parts") or []]\n',
        ("tests/test_review_canary.py::"
         "test_canary_full_path_reads_and_golden_findings_are_findings"),
    ),
    (
        # (m) review.json stops carrying the class the ledger refunded on.
        "review_run stops recording the failure class",
        REVIEW_RUN,
        '    review["failure_class"] = failure\n',
        '    review["failure_class"] = None\n',
        "tests/test_review_canary.py::test_canary_turn_failed_is_a_refunded_tool_failure",
    ),
    (
        # (n) Round-1 FIX: a refunded round reruns review even straight after
        # /crew:review; the no-progress stop swallowed it.
        "autopilot reads a refunded rerun as no progress",
        CREW_AUTOPILOT,
        '    if last_command and result["command"] == last_command and not rerun:\n',
        '    if last_command and result["command"] == last_command:\n',
        "tests/test_crew_autopilot.py::test_next_refunded_rerun_after_review_is_not_no_progress",
    ),
    (
        # (o) The private marker leaks into `next`'s answer (and its --json).
        "the refunded-rerun marker is left in the answer",
        CREW_AUTOPILOT,
        '    rerun = result.pop("refunded_rerun", False)\n',
        '    rerun = result.get("refunded_rerun", False)\n',
        "tests/test_crew_autopilot.py::test_next_refunded_rerun_after_review_is_not_no_progress",
    ),
    (
        # (p) Round-1 NIT: a `successors` that is not a list of objects
        # crashes /crew:status instead of reading UNKNOWN.
        "malformed successors load as ok",
        REVIEW_LEDGER,
        "    if not isinstance(successors, list) or not all(isinstance(s, dict) for s in successors):\n",
        "    if False:\n",
        "tests/test_status.py::test_status_review_line_for_malformed_successors_is_unknown",
    ),
    (
        # (q) Round-1 NIT: the summary line prints the round over the budget.
        "the summary line prints round N/BUDGET again",
        REVIEW_RUN,
        "    print(f\"review: {result['verdict']} round {number}, {budget} \"\n",
        "    print(f\"review: {result['verdict']} round {number}/{review_ledger.BUDGET} \"\n",
        "tests/test_review_refund.py::test_summary_line_after_refunds_is_never_over_budget",
    ),
    (
        # (r) Round-1 NIT: a path placeholder with no left boundary rewrites
        # prose (`symlink/root race` -> `symlink<HOME> race`).
        "redaction loses its left boundary",
        GOLDEN_BUILD,
        '_START = r"(?:(?<![A-Za-z0-9_.-])|(?<=\\\\[nrt]))"\n',
        '_START = ""\n',
        "tests/test_review_golden.py::test_redact_leaves_prose_that_only_contains_a_machine_string",
    ),
    (
        # (s) The host name is replaced inside longer words again.
        "the host name is replaced as a bare substring",
        GOLDEN_BUILD,
        '    return re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(host) + r"(?![A-Za-z0-9_-])")\n',
        '    return re.compile(re.escape(host) + r"(?![A-Za-z0-9_-])")\n',
        "tests/test_review_golden.py::test_redact_leaves_prose_that_only_contains_a_machine_string",
    ),
    (
        # (z) Successor plan (Windows, PR #260): a batch-shim reviewer is
        # handed the multi-line prompt inline again, which cmd.exe cuts.
        "a batch-shim reviewer gets the prompt inline",
        REVIEW_RUN,
        "    if len(text) <= INLINE_PROMPT_LIMIT and not through_batch_shim(exe):\n",
        "    if len(text) <= INLINE_PROMPT_LIMIT:\n",
        "tests/test_external_tool_formats.py::test_a_batch_shim_never_gets_the_prompt_inline",
    ),
    (
        # (aa) A WSL that listed no distribution is judged as a wrong
        # encoding again instead of skipping as "could not tell".
        "the WSL probe no longer skips when no distribution answered",
        FORMATS_TEST,
        '        if proc.returncode != 0 or not out.strip(b"\\x00\\r\\n "):\n',
        "        if False:\n",
        "tests/test_external_tool_formats.py::test_wsl_probe_skips_when_no_distribution_answers",
    ),
    (
        # (ab) The golden corpus is converted on an autocrlf checkout again.
        "the golden corpus loses its -text attribute",
        GOLDEN_ATTRIBUTES,
        "* -text\n",
        "* text\n",
        ("tests/test_review_golden.py::"
         "test_golden_corpus_is_checked_out_without_line_ending_conversion"),
    ),
    (
        # (ac) Round-4 FIX: the refund marks every phase, so a refresh that
        # left its artifact stale repeats forever instead of stopping.
        "a refunded round exempts a stale refresh from no-progress",
        CREW_AUTOPILOT,
        '        return dict(found, refunded_rerun=found["phase"] == "review")\n',
        "        return dict(found, refunded_rerun=True)\n",
        ("tests/test_crew_autopilot.py::"
         "test_next_refunded_round_with_a_refresh_still_stale_is_no_progress"),
    ),
    (
        # (ad) Round-5 BLOCK: `sk-proj-`/`sk-ant-` keys pass the leak check again.
        "the sk- leak pattern loses its hyphenated segments",
        GOLDEN_BUILD,
        '    ("sk- token", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),\n',
        '    ("sk- token", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20}")),\n',
        "tests/test_review_golden.py::test_leak_refuses_every_secret_shape",
    ),
    (
        # (ae) Round-5 BLOCK: an address right after a JSON escape passes again.
        "an address after a JSON escape is not an address again",
        GOLDEN_BUILD,
        'EMAIL = re.compile(r"(?:(?<![\\\\A-Za-z0-9._%+-])|(?<=\\\\[nrt])(?=[A-Za-z0-9])"\n',
        'EMAIL = re.compile(r"(?:(?<![\\\\A-Za-z0-9._%+-])|(?!x)x"\n',
        "tests/test_review_golden.py::test_redact_replaces_an_address_after_a_json_escape",
    ),
    (
        # (af) Round-5 FIX: a falsey non-list `successors` reads as "no successor".
        "a falsey successors collapses to no successor plan",
        REVIEW_LEDGER,
        '    successors = data.get("successors", [])\n',
        '    successors = data.get("successors") or []\n',
        "tests/test_review_ledger.py::test_a_wrong_typed_successors_path_reads_unknown",
    ),
    (
        # (ag) ... or a wrong-typed `after_round` reads as boundary 0.
        "a wrong-typed after_round reads as boundary 0",
        REVIEW_LEDGER,
        '    if successors:\n        after = successors[-1].get("after_round")\n',
        '    if False:\n        after = successors[-1].get("after_round")\n',
        "tests/test_review_ledger.py::test_a_wrong_typed_successors_path_reads_unknown",
    ),
    (
        # (ah) Round-6 FIX: the committed-corpus test skips the builder's leak
        # check again, so the host name is never looked for.
        "the corpus leak test stops calling golden_build.leak",
        GOLDEN_TEST,
        "        found = golden_build.leak(text)\n",
        "        found = None\n",
        "tests/test_review_golden.py::test_corpus_leak_check_refuses_a_planted_host_name",
    ),
    (
        # (ai) ... or the builder's leak check forgets the host name.
        "golden_build.leak no longer looks for the host name",
        GOLDEN_BUILD,
        '    if host and _host_word(host).search(text):\n        return "host name"\n',
        '    if False:\n        return "host name"\n',
        "tests/test_review_golden.py::test_corpus_leak_check_refuses_a_planted_host_name",
    ),
)

# L-0572: declared subset coverage under `verify-gate --all`. Each mutation
# makes the gate credit a subset it must run, or makes the record treat a
# credit as a measurement. The .ps1 ones need pwsh to run their test, so
# they are appended only where it exists (a skipped test reads as green).
GATE_SH = os.path.join(SCRIPTS, "verify-gate.sh")
GATE_PS1 = os.path.join(SCRIPTS, "verify-gate.ps1")
_COVER = "tests/test_verify_gate_subset_cover.py::"
TOOLING_MUTATIONS += (
    (
        "sh: a superset that failed still credits its subsets",
        GATE_SH,
        '    [ "${STATUS_AT[$((10#$p))]:-}" = "pass" ] || return 1\n',
        "    :\n",
        _COVER + "test_superset_not_passing_runs_subset[1-sh]",
    ),
    (
        "sh: Stop mode plans coverage too",
        GATE_SH,
        'if budget is None and _vr is not None and hasattr(_vr, "cover_plan"):\n',
        'if _vr is not None and hasattr(_vr, "cover_plan"):\n',
        _COVER + "test_stop_mode_never_credits[sh]",
    ),
    (
        "sh: a tree that moved after the superset still credits",
        GATE_SH,
        '    if [ -n "$COVER_SNAP0" ] && [ "$COVER_SNAP0" = "$COVER_SNAP1" ]; then\n',
        "    if true; then\n",
        _COVER + "test_tree_changed_after_superset_runs_subset[sh]",
    ),
    (
        "planner: a command also named by `always` is credited",
        VERIFY_RECORD,
        '            if any(c.split("\\x1c", 1)[0] in pinned or not owners[c] <= candidates\n',
        "            if any(not owners[c] <= candidates\n",
        _COVER + "test_command_also_in_always_runs[sh]",
    ),
    (
        "planner: PYTEST_ADDOPTS no longer declines credit",
        VERIFY_RECORD,
        '    if environ.get("PYTEST_ADDOPTS", "") != "":\n',
        "    if False:\n",
        _COVER + "test_pytest_addopts_runs_subset[-m slow-sh]",
    ),
    (
        "planner: a subset under another env is credited",
        VERIFY_RECORD,
        "            elif _rule_env(rule) != _rule_env(sup):\n",
        "            elif False:\n",
        _COVER + "test_invalid_declaration_runs_subset_and_says_why[env mismatch-sh]",
    ),
    (
        "snapshot: mode bits and symlink targets dropped from the snapshot",
        VERIFY_RECORD,
        '    snap = verify_fingerprint.fingerprint(root, paths) + "-" + meta\n',
        "    snap = verify_fingerprint.fingerprint(root, paths)\n",
        _COVER + "test_tree_metadata_change_after_superset_runs_subset[chmod +x a.py-sh]",
    ),
    (
        "cover-plan: a non-string command is coerced instead of refused",
        VERIFY_RECORD,
        "    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):\n",
        "    if not isinstance(value, list):\n",
        _COVER + "test_cover_plan_cli_refuses_malformed_input",
    ),
    (
        "record: a credited command's 0s is cached as the rule's cost",
        VERIFY_RECORD,
        '        if all(s == "pass" for s in statuses):\n',
        '        if True:\n',
        _COVER + "test_record_covered_is_clean_and_never_cached",
    ),
    (
        "record: a rule with a declared price is never measured again",
        VERIFY_RECORD,
        '        if all(s == "pass" for s in statuses):\n',
        '        if rule.get("unknown") and all(s == "pass" for s in statuses):\n',
        "tests/test_verify_gate_stop_budget.py::test_a_declared_rule_that_passes_is_measured",
    ),
    (
        "record: the tree-pass cache is read for any tree",
        VERIFY_RECORD,
        '    if not isinstance(data, dict) or data.get("snapshot") != snapshot:\n',
        '    if not isinstance(data, dict):\n',
        "tests/test_verify_gate_tree_cache.py::test_any_edit_anywhere_runs_it_again",
    ),
    (
        "record: a failing command is saved to the tree-pass cache",
        VERIFY_RECORD,
        '                if isinstance(e, dict) and e.get("status") == "pass" and isinstance(e.get("cmd"), str))\n',
        '                if isinstance(e, dict) and isinstance(e.get("cmd"), str))\n',
        "tests/test_verify_gate_tree_cache.py::test_a_failure_is_never_cached",
    ),
    (
        "record: CREW_VERIFY_FRESH=1 no longer refuses the tree-pass cache",
        VERIFY_RECORD,
        '    if not snapshot or os.environ.get("CREW_VERIFY_FRESH") == "1":\n',
        '    if not snapshot:\n',
        "tests/test_verify_gate_tree_cache.py::test_the_cache_can_always_be_refused",
    ),
    (
        # docs/review/08 defect 1: the prompt reads the local marker only, so
        # a round the gate reserved on a CI receipt is told MISSING.
        "review_prompt: a CI receipt the gate accepted is not shown to the reviewer",
        os.path.join(SCRIPTS, "review_prompt.py"),
        "        if state == review_gate.VERIFIED:\n",
        "        if False:  # pylint: disable=using-constant-test\n",
        ("tests/test_review_prompt.py::"
         "test_a_ci_receipt_the_gate_accepts_is_what_the_reviewer_is_told"),
    ),
    (
        # docs/review/08 defect 2: the recurring-findings block has no caller.
        "review_prompt: the recurring-findings block never reaches the reviewer",
        os.path.join(SCRIPTS, "review_prompt.py"),
        "                  recurring_findings.review_block(root, manifest),\n",
        "",
        "tests/test_review_prompt.py::test_the_recurring_findings_block_reaches_the_reviewer",
    ),
    (
        "review_gate: a receipt that is not VERIFIED still upgrades the gate",
        os.path.join(SCRIPTS, "review_gate.py"),
        "    if r_state == VERIFIED:\n",
        "    if r_state != NO_GATE:\n",
        "tests/test_review_gate_receipt.py::test_any_other_receipt_answer_leaves_the_local_verdict",
    ),
    (
        "review_gate: a receipt is consulted for a tree already VERIFIED or with no gate",
        os.path.join(SCRIPTS, "review_gate.py"),
        "    if state not in (UNVERIFIED, UNKNOWN):\n        return state, reason\n",
        "",
        "tests/test_review_gate_receipt.py::test_a_verdict_that_needs_no_upgrade_never_asks_for_a_receipt",
    ),
)
if shutil.which("pwsh"):
    TOOLING_MUTATIONS += (
        (
            "ps1: a superset that failed still credits its subsets",
            GATE_PS1,
            ' -or $statusAt[$pi] -ne "pass") {\n',
            ") {\n",
            _COVER + "test_superset_not_passing_runs_subset[1-ps1]",
        ),
        (
            "ps1: Stop mode plans coverage too",
            GATE_PS1,
            "if ($All -and $matchPy -and (Test-Path $verifyRecordScript)) {\n",
            "if ($matchPy -and (Test-Path $verifyRecordScript)) {\n",
            _COVER + "test_stop_mode_never_credits[ps1]",
        ),
    )

# Outside the plugin: present only in the marketplace repo, never in an
# installed copy, so these are appended only when their targets exist.
_CHECKER_SUITE = ("tests/test_review_contracts.py::"
                  "test_tooling_alone_checker_passes_its_must_block_must_allow_suite")
_RULE_PATHS = ("tests/test_review_contracts.py::"
               "test_verify_rule_paths_cover_the_harness_its_seams_and_suites")
if os.path.isfile(CHECKER) and os.path.isfile(VERIFY_JSON):
    TOOLING_MUTATIONS += (
        (
            # (t) Round-1 FIX: an undeclared seam consumer rides along.
            "a seam consumer rides along undeclared",
            CHECKER,
            "    seams = [p for p in paths if p in declared and _matches(p, SEAM)]\n",
            "    seams = [p for p in paths if _matches(p, SEAM)]\n",
            _CHECKER_SUITE,
        ),
        (
            # (u) A Tooling-seam trailer admits a file outside SEAM.
            "a trailer admits any path",
            CHECKER,
            "    seams = [p for p in paths if p in declared and _matches(p, SEAM)]\n",
            "    seams = [p for p in paths if p in declared]\n",
            _CHECKER_SUITE,
        ),
        (
            # (v) Round-1 FIX: every prompt rides along again.
            "ALONGSIDE admits every command prompt again",
            CHECKER,
            '    "plugin/crew/docs/**",\n',
            '    "plugin/crew/docs/**",\n    "plugin/crew/commands/**",\n',
            _CHECKER_SUITE,
        ),
        (
            # (w) Round-1 NIT: a worktree rename (` R`) leaves its old path
            # in the stream, parsed as an entry of its own.
            "a worktree rename's source path is parsed as an entry",
            CHECKER,
            '        if set(entry[:2]) & {"R", "C"} and i < len(entries):\n',
            '        if entry[0] in ("R", "C") and i < len(entries):\n',
            _CHECKER_SUITE,
        ),
        (
            # (x) Round-1 FIX: the harness rule stops triggering on a suite it runs.
            "rule 36 stops triggering on test_status.py",
            VERIFY_JSON,
            '"plugin/crew/tests/test_status.py", "plugin/crew/docs/external-tool-formats.md"],',
            '"plugin/crew/docs/external-tool-formats.md"],',
            _RULE_PATHS,
        ),
        (
            # (y) ... or stops running the status suite at all.
            "rule 36 stops running test_status.py",
            VERIFY_JSON,
            ' plugin/crew/tests/test_status.py -q"]',
            ' -q"]',
            _RULE_PATHS,
        ),
    )

# The Stop gate's measured pricing and tree-pass cache.
# Kept here, not in sabotage.py, which sits at pylint's 3400-line module cap.
TOOLING_MUTATIONS += (
    (
        # min(declared, measured) turned into "measured wins": a stale cache
        # ABOVE the declared price makes a rule that fits chronic, and Stop
        # stops running it. The whole safety argument is the minimum.
        "a dearer cached measurement replaces a declared price",
        GATE_SH,
        "                            and 0 < cached < secs):\n",
        "                            and 0 < cached):\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_a_dearer_measurement_never_defers_a_declared_rule"),
    ),
    (
        # A JSON true is an int in python; without the bool test a cached
        # `true` prices a 90s rule at 1s.
        "a cached true prices a declared rule",
        GATE_SH,
        "                    if (isinstance(cached, int) and not isinstance(cached, bool)\n"
        "                            and 0 < cached < secs):\n",
        "                    if (isinstance(cached, int)\n"
        "                            and 0 < cached < secs):\n",
        ("tests/test_verify_gate_stop_budget.py::"
         "test_an_unusable_measurement_leaves_the_declared_price"),
    ),
    (
        # The tree-pass cache stops zeroing a fully-credited rule's price: it
        # is credited if it runs, but it still spends the budget, so the rule
        # it was deferring stays deferred on every Stop of an unchanged tree.
        "a rule that passed on this exact tree still spends the Stop budget",
        GATE_SH,
        "        rule_secs[_ri] = 0\n",
        "        pass\n",
        ("tests/test_verify_gate_tree_cache.py::"
         "test_an_acutely_deferred_stop_converges_on_an_unchanged_tree"),
    ),
    (
        # Passes saved although the tree moved while the rules ran: they then
        # describe no single tree, and the next run credits them anyway.
        "the tree-pass cache is saved after the tree moved during the run",
        GATE_SH,
        '  if [ -n "$TREE_PRE" ] && [ "$TREE_PRE" = "$TREE_POST" ]; then\n',
        '  if [ -n "$TREE_PRE" ]; then\n',
        ("tests/test_verify_gate_tree_cache.py::"
         "test_a_rule_that_edits_the_tree_leaves_no_cache"),
    ),
    (
        # Review r1: --all reads the cache and credits from it, so "run
        # everything" silently runs less.
        "--all credits from the tree-pass cache",
        GATE_SH,
        "if STOP_MODE and tree_snap and _vr is not None and hasattr(_vr, \"passes_load\"):\n",
        "if tree_snap and _vr is not None and hasattr(_vr, \"passes_load\"):\n",
        "tests/test_verify_gate_tree_cache.py::test_all_never_credits",
    ),
    (
        # Review r1: refs left out of the key, so a fetch that moves
        # origin/main keeps crediting a rule that diffs against it.
        "record: the tree-pass cache key ignores refs",
        VERIFY_RECORD,
        '        snap += "-" + refs\n',
        "        snap += \"\"\n",
        "tests/test_verify_gate_tree_cache.py::test_a_moved_ref_runs_it_again",
    ),
    (
        # Review r1: a tree that moved after a credit keeps the credit, and
        # the marker advances over a command never checked on the end tree.
        "a tree that moved after a tree-pass credit still verifies the run",
        GATE_SH,
        "      TREE_MOVED=1\n",
        "      TREE_MOVED=0\n",
        ("tests/test_verify_gate_tree_cache.py::"
         "test_a_tree_that_moves_after_a_credit_withdraws_it"),
    ),
    (
        # Review r2: the withdrawn credits' log lines reach the record sync,
        # so the rule reads as clean and its standing entry is popped.
        "a withdrawn tree-pass credit still reaches the record sync",
        GATE_SH,
        "      CMD_LOG=$(printf '%s\\n' \"$CMD_LOG\" | grep -v '\"tree\": true}$' || true)\n",
        "      :\n",
        ("tests/test_verify_gate_tree_cache.py::"
         "test_a_withdrawn_credit_never_clears_the_rule_s_record"),
    ),
    (
        # Review r2: refs that cannot be listed read as "no refs", a key
        # that then credits across a fetch.
        "record: refs that cannot be listed still give a stable snapshot",
        VERIFY_RECORD,
        "        if refs is None:\n            return None\n",
        "        refs = refs or \"\"\n",
        ("tests/test_verify_gate_tree_cache.py::"
         "test_refs_that_cannot_be_listed_mean_no_stable_snapshot"),
    ),
)
if shutil.which("pwsh"):
    TOOLING_MUTATIONS += (
        (
            # Its PowerShell twin.
            "the PowerShell gate lets a dearer measurement replace a declared price",
            GATE_PS1,
            "              if (($cached -is [int] -or $cached -is [long]) -and $cached -gt 0 -and\n"
            "                  $cached -lt [double]$r.seconds) {\n",
            "              if (($cached -is [int] -or $cached -is [long]) -and $cached -gt 0) {\n",
            ("tests/test_verify_gate_stop_budget.py::"
             "test_a_dearer_measurement_never_defers_a_declared_rule"),
        ),
        (
            # Its PowerShell twin.
            "the PowerShell gate charges a rule that passed on this exact tree",
            GATE_PS1,
            "    $ruleSecs[$ri] = [double]0\n",
            "    $null = $ri\n",
            ("tests/test_verify_gate_tree_cache.py::"
             "test_an_acutely_deferred_stop_converges_on_an_unchanged_tree"),
        ),
        (
            "the PowerShell gate saves the tree-pass cache after the tree moved",
            GATE_PS1,
            "    if ($treePre -and $treePre -eq $treePost) {\n",
            "    if ($treePre) {\n",
            ("tests/test_verify_gate_tree_cache.py::"
             "test_a_rule_that_edits_the_tree_leaves_no_cache"),
        ),
        (
            "the PowerShell gate credits from the tree-pass cache under -All",
            GATE_PS1,
            "    if ($treePre -and $stopMode) {\n",
            "    if ($treePre) {\n",
            "tests/test_verify_gate_tree_cache.py::test_all_never_credits",
        ),
        (
            "the PowerShell gate keeps a credit after the tree moved",
            GATE_PS1,
            "      if ($treeN -gt 0) {\n        $treeMoved = $true\n      }\n",
            "      if ($treeN -gt 0) {\n        $treeMoved = $false\n      }\n",
            ("tests/test_verify_gate_tree_cache.py::"
             "test_a_tree_that_moves_after_a_credit_withdraws_it"),
        ),
        (
            "the PowerShell gate keeps a withdrawn credit in the record sync",
            GATE_PS1,
            "  $cmdLog = [System.Collections.ArrayList]@(@($cmdLog) | Where-Object { -not $_.Contains('tree') })\n",
            "  $cmdLog = [System.Collections.ArrayList]@($cmdLog)\n",
            ("tests/test_verify_gate_tree_cache.py::"
             "test_a_withdrawn_credit_never_clears_the_rule_s_record"),
        ),
    )
