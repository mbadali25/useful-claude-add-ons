"""The T-0087 tooling-reliability mutations, appended to `sabotage.py`'s
MUTATIONS: everything that can grant review budget (the refund) or hide a
break at a review-format seam (the golden replay, the contracts, the canary).
Kept apart only because `sabotage.py` sits at `.pylintrc`'s max-module-lines;
the runner, its restore guarantees and its reporting are all `sabotage.py`'s.
Run that file, not this one.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
REVIEW_VERDICT = os.path.join(SCRIPTS, "review_verdict.py")
REVIEW_LEDGER = os.path.join(SCRIPTS, "review_ledger.py")
REVIEW_RUN = os.path.join(SCRIPTS, "review_run.py")
REVIEW_PATCH = os.path.join(SCRIPTS, "review_patch.py")
CREW_STATUS = os.path.join(SCRIPTS, "crew_status.py")
CREW_AUTOPILOT = os.path.join(SCRIPTS, "crew_autopilot.py")
VERIFY_RECORD = os.path.join(SCRIPTS, "verify_record.py")

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
)
