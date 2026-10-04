"""The T-0087 tooling-reliability mutations, appended to `sabotage.py`'s
MUTATIONS: everything that can grant review budget (the refund) or hide a
break at a review-format seam (the golden replay, the contracts, the canary).
Kept apart only because `sabotage.py` sits at `.pylintrc`'s max-module-lines;
the runner, its restore guarantees and its reporting are all `sabotage.py`'s.
Run that file, not this one.
"""
import os
import shutil
import sys

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
        "            if r_state == review_gate.VERIFIED:\n",
        "            if False:  # pylint: disable=using-constant-test\n",
        ("tests/test_review_prompt.py::"
         "test_a_ci_receipt_the_gate_accepts_is_what_the_reviewer_is_told"),
    ),
    (
        # Review r1 BLOCK: without the local question first, a local pass on
        # a dirty tree reaches accepted_state and is printed as a CI receipt.
        "review_prompt: a local pass on a dirty tree is labelled a CI receipt",
        os.path.join(SCRIPTS, "review_prompt.py"),
        "        local, local_why = _ask(review_gate.gate_state, root)\n",
        "        local, local_why = review_gate.UNVERIFIED, \"\"\n",
        ("tests/test_review_prompt.py::"
         "test_a_local_pass_on_a_dirty_tree_is_never_called_a_ci_receipt"),
    ),
    (
        # Review r2: accepted_state re-asks gate_state, so a local pass that
        # lands mid-build comes back VERIFIED and is printed as a receipt.
        "review_prompt: the receipt is asked through accepted_state (a race)",
        os.path.join(SCRIPTS, "review_prompt.py"),
        "            r_state, r_reason = _ask(_receipt, root)\n",
        "            r_state, r_reason = _ask(review_gate.accepted_state, root)\n",
        ("tests/test_review_prompt.py::"
         "test_a_local_pass_that_lands_mid_build_is_never_a_ci_receipt"),
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

# The gate exports CLAUDE_PLUGIN_ROOT to its rule commands when unset.
TOOLING_MUTATIONS += (
    (
        # Unexported, a rule's child process (python3 under `/crew:verify
        # --all`) never sees it: the rule fails there and passes at Stop.
        "the gate does not export CLAUDE_PLUGIN_ROOT to its rule commands",
        GATE_SH,
        "  export CLAUDE_PLUGIN_ROOT\n",
        "  :\n",
        "tests/test_verify_gate_plugin_root.py::test_an_unset_plugin_root_is_the_gates_own",
    ),
    (
        # Replacing the hook's own value swaps a native Windows path for the
        # bash form.
        "the gate replaces a CLAUDE_PLUGIN_ROOT its caller set",
        GATE_SH,
        'if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -n "$GATE_PLUGIN_ROOT" ]; then\n',
        'if [ -n "$GATE_PLUGIN_ROOT" ]; then\n',
        "tests/test_verify_gate_plugin_root.py::test_a_plugin_root_the_caller_set_is_kept",
    ),
    (
        # An empty value kept as empty: a rule's `$CLAUDE_PLUGIN_ROOT/...`
        # becomes `/hooks/...`.
        "the gate keeps an empty CLAUDE_PLUGIN_ROOT",
        GATE_SH,
        'if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -n "$GATE_PLUGIN_ROOT" ]; then\n',
        'if [ "${CLAUDE_PLUGIN_ROOT+set}" != set ] && [ -n "$GATE_PLUGIN_ROOT" ]; then\n',
        "tests/test_verify_gate_plugin_root.py::test_an_unset_plugin_root_is_the_gates_own",
    ),
    (
        # Resolved after the gate cd's into the project, a relative script
        # path no longer names the plugin (the old code exported `/`; this
        # mutation exports the project dir).
        "the gate resolves its plugin root after leaving the caller's directory",
        GATE_SH,
        '  CLAUDE_PLUGIN_ROOT="$GATE_PLUGIN_ROOT"\n',
        '  CLAUDE_PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null; pwd)"\n',
        ("tests/test_verify_gate_plugin_root.py::"
         "test_a_gate_started_by_a_relative_path_still_finds_its_root"),
    ),
)
# The .ps1 cases run only on native Windows (verify-gate.ps1 exits early
# elsewhere), so its mutation would survive anywhere else.
if sys.platform.startswith("win") and shutil.which("pwsh"):
    TOOLING_MUTATIONS += (
        (
            "the PowerShell gate does not set CLAUDE_PLUGIN_ROOT for its rule commands",
            GATE_PS1,
            "  $env:CLAUDE_PLUGIN_ROOT = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path\n",
            "  $null = 0\n",
            "tests/test_verify_gate_plugin_root.py::test_an_unset_plugin_root_is_the_gates_own",
        ),
    )

# `verify-gate --ci`: the gate as a pull request's CI job. One mutation per
# behaviour; each must turn its named case in test_verify_gate_ci_mode.py red.
_CI = "tests/test_verify_gate_ci_mode.py::"
TOOLING_MUTATIONS += (
    (
        # A `network` rule runs on a CI runner that cannot reach its target.
        "--ci: the reach filter is not applied",
        GATE_SH,
        "REACH_FILTER = STOP_MODE or CI_MODE\n",
        "REACH_FILTER = STOP_MODE\n",
        _CI + "test_a_network_rule_is_excluded_named_and_does_not_fail[sh]",
    ),
    (
        # `always`/`default` skip the reach scan under --ci: the fallback
        # reintroduces what the rule-level filter excluded.
        "--ci: an `always` command is not reach-filtered",
        GATE_SH,
        "        continue\n"
        "    _cls = _classify_run_reach([c]) if REACH_FILTER else None\n"
        "    if _cls is not None:\n"
        "        fallback_notices.append(\"`always` command",
        "        continue\n"
        "    _cls = _classify_run_reach([c]) if STOP_MODE else None\n"
        "    if _cls is not None:\n"
        "        fallback_notices.append(\"`always` command",
        _CI + "test_an_always_command_is_reach_filtered_too[sh]",
    ),
    (
        # rc 77 reported and passed: the PR goes green on a check it never ran.
        "--ci: a command exiting 77 does not fail the run",
        GATE_SH,
        '    echo "verify-gate --ci: $SKIP_N command(s) exited 77 (SKIP) - a skip is not a pass in CI" >&2\n'
        "    FAILED=1\n",
        '    echo "verify-gate --ci: $SKIP_N command(s) exited 77 (SKIP) - a skip is not a pass in CI" >&2\n',
        _CI + "test_a_skip_is_not_a_pass_in_ci[sh]",
    ),
    (
        # A --ci pass falls through to the marker block and records a tree
        # whose reach-excluded rules never ran as verified.
        "--ci: a pass advances the verified marker",
        GATE_SH,
        ("    echo \"verify-gate --ci: passed; the verified baseline (.crew/.verify-verified-at) and "
         "the fingerprint were NOT advanced - --ci never writes them, by design\" >&2\n  fi\n  exit 0\n"),
        ("    echo \"verify-gate --ci: passed; the verified baseline (.crew/.verify-verified-at) and "
         "the fingerprint were NOT advanced - --ci never writes them, by design\" >&2\n  fi\n"),
        _CI + "test_a_passing_map_exits_0_and_records_nothing[sh]",
    ),
    (
        # Stop's clean-tree exclusion leaks into --ci, so the one place such
        # a rule can run never runs it.
        "--ci: a requiresCleanTree rule is excluded",
        GATE_SH,
        '                    if STOP_MODE and r.get("requiresCleanTree") is True:\n',
        '                    if r.get("requiresCleanTree") is True:\n',
        _CI + "test_a_requires_clean_tree_rule_runs[sh]",
    ),
    (
        # --ci diffs against a base like Stop: a committed file is invisible.
        "--ci: the scope narrows to the changed files",
        GATE_SH,
        'if [ "${1:-}" = "--all" ] || [ "$CI_MODE" -eq 1 ]; then\n',
        'if [ "${1:-}" = "--all" ]; then\n',
        _CI + "test_a_rule_on_a_file_the_branch_never_changed_still_runs[sh]",
    ),
    (
        # --all --ci silently picks one reading of the pair.
        "--ci: --all together with --ci is accepted",
        GATE_SH,
        'if [ "$CI_MODE" -eq 1 ] && [ "$CI_ALL_SEEN" -eq 1 ]; then\n',
        "if false; then\n",
        _CI + "test_all_and_ci_together_is_a_usage_error[sh-all-ci]",
    ),
    (
        # A disabled gate exits 0 under --ci too: a green job that checked nothing.
        "--ci: a disabled gate passes",
        GATE_SH,
        ('echo "verify-gate --ci: verifyGate is false in .crew/config.json - the gate is off, '
         'so nothing was checked. Turn it on or remove the CI job." >&2\n    exit 2\n'),
        "exit 0\n",
        _CI + "test_a_disabled_gate_fails_in_ci_rather_than_passing_unchecked[sh]",
    ),
    (
        # No map and no smoke exits 0 under --ci: nothing checked, reported green.
        "--ci: nothing to verify passes",
        GATE_SH,
        ('echo "verify-gate --ci: no .crew/verify.json and no _verify/smoke.sh - nothing to '
         'verify, so nothing was checked" >&2\n      exit 2\n'),
        "exit 0\n",
        _CI + "test_no_map_and_no_smoke_fails_in_ci[sh]",
    ),
)
# Round 2 (review r1): every --ci path that would end having checked nothing
# exits 2, the Stop-only stand-downs are skipped, the scope is tracked files,
# and arguments are checked strictly.
TOOLING_MUTATIONS += (
    (
        "--ci: zero commands to run passes (every rule reach-excluded)",
        GATE_SH,
        ('    echo "verify-gate --ci: zero commands to run - ${CI_NOTHING:-the matcher selected none} '
         '- nothing was checked" >&2\n    exit 2\n'),
        ('    echo "verify-gate --ci: zero commands to run - ${CI_NOTHING:-the matcher selected none} '
         '- nothing was checked" >&2\n'),
        _CI + "test_every_matched_rule_reach_excluded_fails[sh]",
    ),
    (
        "--ci: zero commands to run passes (no rule matched)",
        GATE_SH,
        ('    echo "verify-gate --ci: zero commands to run - ${CI_NOTHING:-the matcher selected none} '
         '- nothing was checked" >&2\n    exit 2\n'),
        ('    echo "verify-gate --ci: zero commands to run - ${CI_NOTHING:-the matcher selected none} '
         '- nothing was checked" >&2\n'),
        _CI + "test_no_rule_matching_anything_fails[sh]",
    ),
    (
        "--ci: no tracked files passes",
        GATE_SH,
        ('    echo "verify-gate --ci: no tracked files found in $PWD (not a git work tree, git failed '
         '- e.g. refused a dubious-ownership checkout - or nothing is tracked) - nothing was '
         'checked" >&2\n    exit 2\n'),
        "    :\n",
        _CI + "test_no_tracked_files_fails[sh]",
    ),
    (
        "--ci: a project dir that cannot be entered passes",
        GATE_SH,
        ('  [ "$CI_MODE" -eq 1 ] && { echo "verify-gate --ci: cannot cd into ${CLAUDE_PROJECT_DIR:-.} '
         '- nothing was checked" >&2; exit 2; }\n'),
        "",
        _CI + "test_a_project_dir_that_cannot_be_entered_fails[sh]",
    ),
    (
        "--ci: a Stop fingerprint skips the run",
        GATE_SH,
        '[ -f "$FP_DIR/verify_fingerprint.py" ] && [ -z "$BUDGET_FLAG" ]; then\n',
        '[ -f "$FP_DIR/verify_fingerprint.py" ] && [ "$BUDGET_FLAG" != "--all" ]; then\n',
        _CI + "test_a_stop_fingerprint_never_skips_a_ci_run[sh]",
    ),
    (
        "--ci: an unknown argument is ignored",
        GATE_SH,
        ('      echo "verify-gate: unknown argument \'$CI_ARG\' - the gate accepts --all, --ci, or '
         '--price as the first argument. Nothing was verified." >&2\n      exit 2 ;;\n'),
        "      : ;;\n",
        _CI + "test_an_unknown_argument_is_a_usage_error[sh--ci]",
    ),
    (
        "--ci: --price --ci prices a file named --ci",
        GATE_SH,
        ('      --ci) echo "verify-gate: --price and --ci cannot be combined (--price times the map '
         'and writes it; --ci is a gate run). Pass one of them. Nothing was verified." >&2\n'
         '            exit 2 ;;\n'),
        "",
        _CI + "test_ci_and_price_together_is_a_usage_error[sh-price-ci]",
    ),
    (
        "--ci: untracked files are in scope",
        GATE_SH,
        '{ [ "$CI_MODE" -eq 1 ] || git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null; })\n',
        '{ git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null; })\n',
        _CI + "test_an_untracked_unmapped_file_is_not_in_scope[sh]",
    ),
    (
        "--ci: a stop_hook_active payload ends the run",
        GATE_SH,
        'if [ "$CI_MODE" -eq 0 ] && [ ! -t 0 ]; then\n',
        "if [ ! -t 0 ]; then\n",
        _CI + "test_a_stop_hook_active_payload_does_not_end_a_ci_run[sh]",
    ),
    (
        "--ci: an incident stands the run down",
        GATE_SH,
        'if [ "$CI_MODE" -eq 1 ]; then\n  if [ -f .crew/incident.json ]; then\n',
        "if false; then\n  if [ -f .crew/incident.json ]; then\n",
        _CI + "test_an_incident_does_not_stand_a_ci_run_down[sh]",
    ),
    (
        "--ci: a lock back-off passes",
        GATE_SH,
        '    echo "verify-gate --ci: $1 - this run checked nothing" >&2\n    exit 2\n',
        '    echo "verify-gate --ci: $1 - this run checked nothing" >&2\n',
        _CI + "test_a_held_lock_fails_rather_than_backing_off_green[sh]",
    ),
)
# Their PowerShell twins. The .ps1 cases run wherever pwsh exists (the suite
# sets OS=Windows_NT past the flavour guard), so these are appended there.
if shutil.which("pwsh"):
    TOOLING_MUTATIONS += (
        (
            "--ci (ps1): the reach filter is not applied",
            GATE_PS1,
            "$reachFilter = $stopMode -or $Ci\n",
            "$reachFilter = $stopMode\n",
            _CI + "test_a_network_rule_is_excluded_named_and_does_not_fail[ps1]",
        ),
        (
            "--ci (ps1): a command exiting 77 does not fail the run",
            GATE_PS1,
            '    [Console]::Error.WriteLine("verify-gate --ci: $skipCount command(s) exited 77 (SKIP) - '
            'a skip is not a pass in CI")\n    $failed = $true\n',
            '    [Console]::Error.WriteLine("verify-gate --ci: $skipCount command(s) exited 77 (SKIP) - '
            'a skip is not a pass in CI")\n',
            _CI + "test_a_skip_is_not_a_pass_in_ci[ps1]",
        ),
        (
            "--ci (ps1): a pass advances the verified marker",
            GATE_PS1,
            "never writes them, by design\")\n  }\n  exit 0\n",
            "never writes them, by design\")\n  }\n",
            _CI + "test_a_passing_map_exits_0_and_records_nothing[ps1]",
        ),
        (
            "--ci (ps1): a requiresCleanTree rule is excluded",
            GATE_PS1,
            "            if ($stopMode -and $r.requiresCleanTree -eq $true) {\n",
            "            if ($r.requiresCleanTree -eq $true) {\n",
            _CI + "test_a_requires_clean_tree_rule_runs[ps1]",
        ),
        (
            "--ci (ps1): the scope narrows to the changed files",
            GATE_PS1,
            "if ($All -or $Ci) {\n  # -All does not diff",
            "if ($All) {\n  # -All does not diff",
            _CI + "test_a_rule_on_a_file_the_branch_never_changed_still_runs[ps1]",
        ),
        (
            "--ci (ps1): a disabled gate passes",
            GATE_PS1,
            ('      [Console]::Error.WriteLine("verify-gate --ci: verifyGate is false in .crew/config.json '
             '- the gate is off, so nothing was checked. Turn it on or remove the CI job.")\n      exit 2\n'),
            ('      [Console]::Error.WriteLine("verify-gate --ci: verifyGate is false in .crew/config.json '
             '- the gate is off, so nothing was checked. Turn it on or remove the CI job.")\n'),
            _CI + "test_a_disabled_gate_fails_in_ci_rather_than_passing_unchecked[ps1]",
        ),
        (
            "--ci (ps1): nothing to verify passes",
            GATE_PS1,
            ('    [Console]::Error.WriteLine("verify-gate --ci: no .crew/verify.json and no '
             '_verify/smoke.sh - nothing to verify, so nothing was checked")\n    exit 2\n'),
            ('    [Console]::Error.WriteLine("verify-gate --ci: no .crew/verify.json and no '
             '_verify/smoke.sh - nothing to verify, so nothing was checked")\n'),
            _CI + "test_no_map_and_no_smoke_fails_in_ci[ps1]",
        ),
        (
            "--ci (ps1): zero commands to run passes",
            GATE_PS1,
            ('    [Console]::Error.WriteLine("verify-gate --ci: zero commands to run - $ciNothing - '
             'nothing was checked")\n    exit 2\n'),
            ('    [Console]::Error.WriteLine("verify-gate --ci: zero commands to run - $ciNothing - '
             'nothing was checked")\n'),
            _CI + "test_every_matched_rule_reach_excluded_fails[ps1]",
        ),
        (
            "--ci (ps1): no tracked files passes",
            GATE_PS1,
            ('or nothing is tracked) - nothing was checked")\n    exit 2\n'),
            ('or nothing is tracked) - nothing was checked")\n'),
            _CI + "test_no_tracked_files_fails[ps1]",
        ),
        (
            "--ci (ps1): a project dir that cannot be entered passes",
            GATE_PS1,
            "  try { Set-Location $root -ErrorAction Stop }\n",
            "  try { Set-Location $root }\n",
            _CI + "test_a_project_dir_that_cannot_be_entered_fails[ps1]",
        ),
        (
            "--ci (ps1): a Stop fingerprint skips the run",
            GATE_PS1,
            "if (-not $All -and -not $Ci) {\n  try {\n    $fpPy = Resolve-CrewPython\n",
            "if (-not $All) {\n  try {\n    $fpPy = Resolve-CrewPython\n",
            _CI + "test_a_stop_fingerprint_never_skips_a_ci_run[ps1]",
        ),
        (
            "--ci (ps1): untracked files are in scope",
            GATE_PS1,
            "  if (-not $Ci) {\n    $changed += ($null | git -c core.quotePath=false ls-files --others",
            "  if ($true) {\n    $changed += ($null | git -c core.quotePath=false ls-files --others",
            _CI + "test_an_untracked_unmapped_file_is_not_in_scope[ps1]",
        ),
        (
            "--ci (ps1): a stop_hook_active payload ends the run",
            GATE_PS1,
            "if (-not $Ci -and [Console]::IsInputRedirected) {\n",
            "if ([Console]::IsInputRedirected) {\n",
            _CI + "test_a_stop_hook_active_payload_does_not_end_a_ci_run[ps1]",
        ),
        (
            "--ci (ps1): an incident stands the run down",
            GATE_PS1,
            "if ($Ci) {\n  if (Test-Path .crew/incident.json) {\n",
            "if ($false) {\n  if (Test-Path .crew/incident.json) {\n",
            _CI + "test_an_incident_does_not_stand_a_ci_run_down[ps1]",
        ),
        (
            "--ci (ps1): a lock back-off passes",
            GATE_PS1,
            '    [Console]::Error.WriteLine("verify-gate --ci: $Why - this run checked nothing")\n    exit 2\n',
            '    [Console]::Error.WriteLine("verify-gate --ci: $Why - this run checked nothing")\n',
            _CI + "test_a_held_lock_fails_rather_than_backing_off_green[ps1]",
        ),
        (
            "--ci (ps1): an unknown argument is ignored",
            GATE_PS1,
            "if ($args.Count -gt 0 -or ($PSBoundParameters.ContainsKey('PriceTarget') -and -not $Price)) {\n",
            "if ($false) {\n",
            _CI + "test_an_unknown_argument_is_a_usage_error[ps1---ci=1]",
        ),
        (
            "--ci (ps1): -Ci -Price is accepted",
            GATE_PS1,
            "if ($Price -and $Ci) {\n",
            "if ($false) {\n",
            _CI + "test_ci_and_price_together_is_a_usage_error[ps1-ci-price]",
        ),
        (
            # Off Windows the flavour guard's silent exit 0 is reached first.
            "--ci (ps1): -Ci off Windows stands down green",
            GATE_PS1,
            "  [ValidateScript({ if ($env:OS -ne 'Windows_NT') { throw ",
            "  [ValidateScript({ if ($false) { throw ",
            _CI + "test_the_ps1_with_ci_off_windows_fails_instead_of_standing_down",
        ),
        (
            "--ci (ps1): a blank command counts as a check",
            GATE_PS1,
            "          if ($Ci -and [string]::IsNullOrWhiteSpace([string]$c)) { continue }\n",
            "",
            _CI + "test_a_map_of_blank_commands_checks_nothing_and_fails[ps1-empty]",
        ),
    )
TOOLING_MUTATIONS += (
    (
        # A blank rule command runs and "passes" under --ci.
        "--ci: a blank command counts as a check",
        GATE_SH,
        "                if CI_MODE and not str(c).strip():\n                    continue\n",
        "",
        _CI + "test_a_map_of_blank_commands_checks_nothing_and_fails[sh-spaces]",
    ),
    (
        # The deploy-in-flight record check blocks a CI run and deletes the marker.
        "--ci: the deploy-in-flight check runs under --ci",
        GATE_SH,
        'if [ "$CI_MODE" -eq 0 ] && [ -f .crew/.deploy-in-flight ]; then\n',
        "if [ -f .crew/.deploy-in-flight ]; then\n",
        _CI + "test_a_deploy_marker_is_left_alone_and_does_not_block[sh]",
    ),
)

# T-0080: the per-entry bound `sabotage.py` runs every entry under. Mutating
# `sabotage_bound.py` cannot weaken the run doing the mutating: that run
# imported it before the first entry, and only the child pytest reads the
# mutated file.
BOUND = os.path.join(CREW, "tests", "sabotage_bound.py")
_BOUND = "tests/test_sabotage_bound.py::"
TOOLING_MUTATIONS += (
    (
        "sabotage bound: the memory cap is never applied",
        BOUND,
        '    if cap:\n        kwargs["preexec_fn"]',
        '    if False:\n        kwargs["preexec_fn"]',
        _BOUND + "test_a_child_over_the_memory_cap_fails_instead_of_growing",
    ),
    (
        "sabotage bound: a timeout stops only the leader",
        BOUND,
        "        os.killpg(pid, sig)\n",
        "        os.kill(pid, sig)\n",
        _BOUND + "test_a_timeout_stops_the_whole_group_and_returns_124",
    ),
    (
        "sabotage bound: an unreadable limit reads as the default",
        BOUND,
        '    if not re.fullmatch(r"[0-9]+", raw) or int(raw) < minimum:\n',
        '    if not re.fullmatch(r"[0-9]+", raw) or int(raw) < minimum:\n        return default\n',
        _BOUND + "test_an_unreadable_limit_refuses_and_never_means_no_cap[CREW_SABOTAGE_MEM_MB-abc]",
    ),
    (
        "sabotage bound: a timed-out entry counts as RED",
        BOUND,
        "    if code == REAL_TEST_FAILURE:\n",
        "    if code in (REAL_TEST_FAILURE, TIMED_OUT):\n",
        "tests/test_sabotage_harness.py::test_main_reports_a_timed_out_entry_as_unproven_and_fails",
    ),
    (
        "sabotage bound: the harness dying leaves its child running",
        BOUND,
        '        if os.name == "posix":\n            _signal_group(proc.pid, signal.SIGKILL)\n'
        "        elif proc.poll() is None:\n            _stop(proc)\n",
        "        pass\n",
        _BOUND + "test_the_harness_dying_stops_a_running_child",
    ),
    (
        "sabotage bound: a same-group child outlives a normal exit",
        BOUND,
        '        if os.name == "posix":\n            _signal_group(proc.pid, signal.SIGKILL)\n'
        "        elif proc.poll() is None:\n            _stop(proc)\n",
        "        pass\n",
        _BOUND + "test_a_same_group_child_left_behind_is_stopped_after_a_normal_exit",
    ),
    (
        "sabotage bound: a pre-4.7 kernel reads as enforced",
        BOUND,
        "    if (int(found.group(1)), int(found.group(2))) < (4, 7):\n",
        "    if False:\n",
        _BOUND + "test_the_cap_is_absent_below_linux_4_7[4.6.7-False]",
    ),
)

# T-0082: a rule passes only on a completion record. Each mutation names the
# test that must catch it; the .ps1 ones run wherever pwsh exists.
_DONE = "tests/test_verify_gate_rule_completion.py::"
TOOLING_MUTATIONS += (
    (
        "(a) sh: pass on the wrapper status alone (record not read)",
        GATE_SH,
        '    RULE_REC=$(head -c 8 "$RULE_DONE_FILE" 2>/dev/null; printf x)\n',
        "    RULE_REC=\"$RULE_WRAP_RC\"$'\\n'x\n",
        _DONE + "test_a_rule_killed_mid_run_could_not_tell[sh]",
    ),
    (
        "(b) sh: pass on the record alone (wrapper status not read)",
        GATE_SH,
        '    if [ "$RULE_WRAP_RC" -ne 0 ]; then\n',
        "    if false; then\n",
        _DONE + "test_no_completion_record_could_not_tell[wrapper-killed-sh]",
    ),
    (
        "(c) sh: a missing record reads as 0",
        GATE_SH,
        '      *) RULE_REC="" ;;\n',
        "      *) RULE_REC=0 ;;\n",
        _DONE + "test_no_completion_record_could_not_tell[record-vanished-sh]",
    ),
    (
        "sh: a record above 255 is read as a status",
        GATE_SH,
        '    [ -n "$RULE_REC" ] && [ "$RULE_REC" -gt 255 ] && RULE_REC=""\n',
        "",
        _DONE + "test_unreadable_record_could_not_tell[256-sh]",
    ),
    (
        "(d) sh: a status above 128 reads as a plain failure",
        GATE_SH,
        '    elif [ "$RULE_REC" -gt 128 ]; then\n',
        "    elif false; then\n",
        _DONE + "test_a_rule_killed_mid_run_could_not_tell[sh]",
    ),
    (
        "(e) sh: unknown is logged as pass",
        GATE_SH,
        '    CMD_STATUS="unknown"\n',
        '    CMD_STATUS="pass"\n',
        _DONE + "test_unknown_status_is_never_recorded_clean[sh]",
    ),
    (
        "(f) sh: the trap's in-flight lines removed",
        GATE_SH,
        '  [ -n "${RULE_IN_FLIGHT:-}" ] || return 0\n',
        "  return 0\n",
        _DONE + "test_a_signalled_gate_names_the_command_in_flight",
    ),
    (
        "sh: the in-flight command is never cleared",
        GATE_SH,
        '    RULE_WRAP_RC=$?\n    RULE_IN_FLIGHT=""\n',
        "    RULE_WRAP_RC=$?\n",
        _DONE + "test_a_signalled_gate_with_no_rule_in_flight_names_nothing",
    ),
    (
        "sh: the record sits beside other files, not in a private dir",
        GATE_SH,
        '  [ -n "$RULE_DONE_DIR" ] && RULE_DONE_FILE="$RULE_DONE_DIR/rc"\n',
        '  [ -n "$RULE_DONE_DIR" ] && RULE_DONE_FILE="$RULE_DONE_DIR.rc"\n',
        _DONE + "test_the_record_lives_in_a_private_directory[sh]",
    ),
    (
        "sh: the record directory survives a signalled gate",
        GATE_SH,
        '  [ -n "${RULE_DONE_DIR:-}" ] && rm -rf -- "$RULE_DONE_DIR"\n',
        "  :\n",
        _DONE + "test_a_signalled_gate_leaves_no_record_file",
    ),
    (
        "sh: a record with a leading zero is read",
        GATE_SH,
        "      0$'\\n'|[1-9]$'\\n'|[1-9][0-9]$'\\n'|[1-9][0-9][0-9]$'\\n') RULE_REC=${RULE_REC%$'\\n'} ;;\n",
        "      [0-9]$'\\n'|[0-9][0-9]$'\\n'|[0-9][0-9][0-9]$'\\n') RULE_REC=${RULE_REC%$'\\n'} ;;\n",
        _DONE + "test_unreadable_record_could_not_tell[leading-zero-sh]",
    ),
    (
        "sh: 255 is called a signal",
        GATE_SH,
        '    elif [ "$RULE_REC" -gt 192 ]; then\n',
        "    elif false; then\n",
        _DONE + "test_a_255_record_is_not_called_a_signal[sh]",
    ),
    (
        "sh: a signalled gate leaves the rule's temp files",
        GATE_SH,
        "_crew_gate_register_cleanup _crew_gate_rule_files_cleanup\n",
        "",
        _DONE + "test_a_signalled_gate_leaves_no_record_file",
    ),
)
if shutil.which("pwsh"):
    TOOLING_MUTATIONS += (
        (
            "(g) ps1: $rc not reset per rule",
            GATE_PS1,
            "  $rc = $null\n  $ruleRec = $null\n",
            "  $ruleRec = $null\n",
            _DONE + "test_ps1_launch_failure_does_not_inherit_the_previous_status",
        ),
        (
            "(h) ps1: a missing record takes the wrapper's status",
            GATE_PS1,
            '      $ruleWhy = "no completion record"\n',
            "      $ruleRec = $rc\n",
            _DONE + "test_no_completion_record_could_not_tell[record-vanished-ps1]",
        ),
        (
            "(i) ps1: unknown does not set $failed",
            GATE_PS1,
            "    $failed = $true\n    $unknownCount++\n",
            "    $unknownCount++\n",
            _DONE + "test_unknown_never_advances_the_marker[ps1]",
        ),
        (
            "ps1: a status above 128 reads as a plain failure",
            GATE_PS1,
            "    } elseif ($ruleRec -gt 128) {\n",
            "    } elseif ($false) {\n",
            _DONE + "test_a_rule_killed_mid_run_could_not_tell[ps1]",
        ),
        (
            "ps1: the .crew/ fallbacks are relative to the process directory",
            GATE_PS1,
            '    $crewDir = Join-Path $root ".crew"\n',
            '    $crewDir = ".crew"\n',
            _DONE + "test_ps1_fallback_record_from_a_subdirectory_passes",
        ),
        (
            "ps1: the record directory is left world-readable",
            GATE_PS1,
            "          [System.IO.File]::SetUnixFileMode($candidate, "
            "[System.IO.UnixFileMode]'UserRead, UserWrite, UserExecute')\n",
            "",
            _DONE + "test_the_record_lives_in_a_private_directory[ps1]",
        ),
        (
            "ps1: a record with a leading zero is read",
            GATE_PS1,
            "'\\A(0|[1-9][0-9]{0,2})\\n\\z'",
            "'\\A[0-9]{1,3}\\n\\z'",
            _DONE + "test_unreadable_record_could_not_tell[leading-zero-ps1]",
        ),
        (
            "ps1: 255 is called a signal",
            GATE_PS1,
            "    } elseif ($ruleRec -gt 192) {\n",
            "    } elseif ($false) {\n",
            _DONE + "test_a_255_record_is_not_called_a_signal[ps1]",
        ),
        (
            "ps1: pass on the record alone (wrapper status not read)",
            GATE_PS1,
            "    } elseif ($rc -ne 0) {\n      $ruleWhy = \"the rule's runner",
            "    } elseif ($false) {\n      $ruleWhy = \"the rule's runner",
            _DONE + "test_no_completion_record_could_not_tell[wrapper-killed-ps1]",
        ),
        (
            "ps1: a record above 255 is read as a status",
            GATE_PS1,
            " -and [int]$recText.Trim() -le 255)",
            ")",
            _DONE + "test_unreadable_record_could_not_tell[256-ps1]",
        ),
        (
            "ps1: unknown is logged as pass",
            GATE_PS1,
            '    $cmdStatus = "unknown"\n',
            '    $cmdStatus = "pass"\n',
            _DONE + "test_unknown_status_is_never_recorded_clean[ps1]",
        ),
    )
