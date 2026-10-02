"""The L-0574 mutations: `review_checks.py` and `review_run.py`'s pre-review
gate. Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find,
replace, test) -- and appended to it there. Run `sabotage.py`, not this file.

Each is a way the pre-review checks could read an unknown as a pass, let a
new finding through, or spend a round they promised not to.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = os.path.join(CREW, "hooks", "scripts", "review_checks.py")
RUN = os.path.join(CREW, "hooks", "scripts", "review_run.py")
_C = "tests/test_review_checks.py::"
_R = "tests/test_review_run_prereview.py::"

PREREVIEW_MUTATIONS = (
    ("a check that could not run reports pass", CHECKS,
     "        result.update(status=COULD_NOT, detail=_detail(exc))\n",
     "        result.update(status=PASS, detail=_detail(exc))\n",
     _C + "test_could_not_check_cases"),
    ("the base count is ignored, every finding is new", CHECKS,
     '        added = n - counts["base"][key]\n',
     "        added = n\n",
     _C + "test_existing_finding_moved_is_not_new"),
    ("a parse abort is not treated as unchecked", CHECKS,
     "    if aborted:\n",
     "    if False:\n",
     _C + "test_parse_abort_either_side"),
    ("shellcheck's error exit is accepted as a run", CHECKS,
     '    _expect(proc, (0, 1), "shellcheck")\n',
     '    _expect(proc, (0, 1, 4), "shellcheck")\n',
     _C + "test_could_not_check_cases"),
    ("the linter config is dropped from the checked trees", CHECKS,
     "            with_base = _materialise(root, selected, _config_blobs(root, manifest), tmp)\n",
     "            with_base = _materialise(root, selected, {}, tmp)\n",
     _C + "test_path_dependent_config_applies"),
    ("a missing record reads as None", CHECKS,
     '        return {"result": NOT_RECORDED, "reason": f"no {RESULT_FILE} in the scratch directory"}\n',
     "        return None\n",
     _C + "test_a_missing_or_torn_record_is_not_recorded_never_none"),
    ("--allow-unverified overrides a new finding", RUN,
     "    if verdict == review_checks.COULD_NOT and args.allow_unverified:\n",
     "    if args.allow_unverified:\n",
     _R + "test_new_finding_is_not_overridable"),
    ("the pre-review refusal is dropped and a round is reserved", RUN,
     "        refused = prereview_gate(args)\n",
     "        prereview_gate(args)\n        refused = None\n",
     _R + "test_new_finding_refuses_before_reserve"),
    ("an expired or stood-down incident stands the checks down", RUN,
     '    if incident["active"]:\n        crew_incident.log_skip(args.root, "prereview-checks"',
     '    if incident["present"]:\n        crew_incident.log_skip(args.root, "prereview-checks"',
     _R + "test_only_an_active_incident_stands_down"),
)
