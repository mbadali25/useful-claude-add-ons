"""T-0011: `/crew:autopilot` ships a ticket after `/crew:done`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py -q

`crew_autopilot.ship_decision` is the pure rule that decides whether an
unattended merge happens: it merges only on every required check `pass` (or a
failing one named EXACTLY in `autopilot.knownFailures`), waits on pending,
stops on anything it could not read, and never merges a high- or
unknown-risk ticket whose completed review rounds are all same-family
(`claude`, or no `model_family` at all). Everything that runs `gh` or
`git push` is stubbed here; no test reaches a network or a real remote.
`sabotage_autopilot.py` mutates each refusing branch to prove these tests can
fail.
"""
import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot


def _check(name, state):
    return {"name": name, "state": state}


GREEN = [_check("build (3.12)", "pass"), _check("check", "pass")]


def _decide(policy="merge", risk="low", checks=None, families=("gpt",), known=()):
    return crew_autopilot.ship_decision(policy, risk, GREEN if checks is None else checks,
                                        list(families), list(known))


# --- step 1: the decision, pure ----------------------------------------------

def test_decision_pr_policy_never_merges():
    got = _decide(policy="pr", risk="low", families=("gpt",))

    assert got["action"] == "open-pr"


def test_decision_merge_all_green():
    got = _decide()

    assert got["action"] == "merge"


def test_decision_merge_waits_on_pending():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "pending")])

    assert (got["action"], "build (3.12)" in got["reason"]) == ("wait", True)


def test_decision_merge_stops_on_unknown_state():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "unknown")])

    assert (got["action"], "build (3.12)" in got["reason"]) == ("stop", True)


def test_decision_merge_stops_on_a_state_outside_the_known_set():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "neutral")])

    assert got["action"] == "stop"


def test_decision_merge_stops_on_unreadable_checks():
    got = crew_autopilot.ship_decision("merge", "low", None, ["gpt"], [])

    assert got["action"] == "stop"


def test_decision_no_required_check_reported_waits():
    got = _decide(checks=[])

    assert got["action"] == "wait"


def test_decision_skipped_required_check_stops():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "skipping")])

    assert got["action"] == "stop"


def test_decision_merge_stops_on_unlisted_failure():
    got = _decide(checks=[_check("check", "pass"), _check("shell", "fail")])

    assert (got["action"], "shell" in got["reason"]) == ("stop", True)


def test_decision_merge_allows_listed_known_failure():
    got = _decide(checks=[_check("check", "pass"),
                          _check("crew-shell-matrix (windows-latest)", "fail")],
                  known=("crew-shell-matrix (windows-latest)",))

    assert (got["action"], "crew-shell-matrix (windows-latest)" in got["reason"]) == (
        "merge", True)


def test_decision_known_failure_needs_exact_name():
    got = _decide(checks=[_check("check", "pass"),
                          _check("crew-shell-matrix (windows-latest)", "fail")],
                  known=("crew-shell-matrix",))

    assert got["action"] == "stop"


def test_decision_known_failure_is_not_a_prefix_of_the_list_entry():
    got = _decide(checks=[_check("check", "pass"), _check("shell", "fail")],
                  known=("shell (windows-latest)",))

    assert got["action"] == "stop"


def test_decision_high_risk_same_family_stops():
    got = _decide(risk="high", families=("claude", "claude"))

    assert (got["action"], "same-family" in got["reason"]) == ("stop", True)


def test_decision_missing_family_counts_as_same_family():
    got = _decide(risk="high", families=(None, ""))

    assert got["action"] == "stop"


def test_decision_no_completed_round_counts_as_same_family():
    got = _decide(risk="high", families=())

    assert got["action"] == "stop"


def test_decision_unknown_risk_counts_as_high():
    got = _decide(risk=None, families=("claude",))

    assert got["action"] == "stop"


def test_decision_family_spelling_does_not_escape_same_family():
    got = _decide(risk="high", families=("Claude ",))

    assert got["action"] == "stop"


def test_decision_high_risk_cross_family_merges():
    got = _decide(risk="high", families=("claude", "gpt"))

    assert got["action"] == "merge"


def test_decision_low_risk_same_family_merges():
    got = _decide(risk="low", families=("claude",))

    assert got["action"] == "merge"


def test_decision_same_family_stops_before_waiting_on_ci():
    got = _decide(risk="high", families=("claude",), checks=[_check("check", "pending")])

    assert got["action"] == "stop"
