"""`plugin/crew/workflows/wave.js` run under node against a stub of the workflow runtime
(`workflow_stub.mjs`): the lane fan-out, its concurrency bound, and the rule that a lost,
rejected or malformed lane result is `unknown` and never `clean` (L-0727 A1, A1c).

node is required: a missing node is a failure here, never a skip."""
import json
import os
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(os.path.dirname(HERE), "workflows", "wave.js")
STUB = os.path.join(HERE, "workflow_stub.mjs")


def _run(tmp_path, scenario):
    node = shutil.which("node")
    assert node, "node is required to run the workflow tests (it is not on PATH)"
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    ran = subprocess.run([node, STUB, WORKFLOW, str(path)], capture_output=True, text=True,
                         encoding="utf-8", check=False, stdin=subprocess.DEVNULL, timeout=60)
    assert ran.returncode == 0, ran.stderr
    return json.loads(ran.stdout.strip().splitlines()[-1])


def _start(*tickets, max_lanes=2, stop=False, reason="", prompts=None):
    return {"match": "start", "result": {
        "stop": stop, "stopReason": reason, "maxLanes": max_lanes,
        "lanes": [{"ticket": t, "prompt": (prompts or {}).get(t, f"Ticket ID: {t}\nlane brief for {t}")}
                  for t in tickets]}}


def _lane(ticket, state="clean", reason="done"):
    return {"match": f"lane {ticket}", "result": {"ticket": ticket, "state": state, "reason": reason}}


def _collect(*rows):
    return {"match": "collect", "result": {"lanes": [
        {"ticket": t, "state": s, "reason": ""} for t, s in rows], "problems": []}}


def _states(out):
    return {lane["ticket"]: lane["state"] for lane in out["result"]["lanes"]}


def test_workflow_meta_is_a_pure_literal_named_wave():
    with open(WORKFLOW, encoding="utf-8") as handle:
        source = handle.read()

    head = source.split("\n\n", 1)[0]

    assert (head.startswith("export const meta = {"), "name: 'wave'" in head,
            "`" not in head, "${" not in head) == (True, True, True, True)


def test_wave_without_a_set_arg_returns_an_error_and_runs_nothing(tmp_path):
    out = _run(tmp_path, {"args": {}, "agents": []})

    assert (sorted(out["result"]), out["calls"]) == (["error"], [])


def test_zero_launches_start_no_lane_and_still_collect(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [_start(), _collect()]})

    assert ([c["label"] for c in out["calls"]], out["result"]["lanes"]) == (
        ["start s", "collect s"], [])


def test_a_stop_launches_nothing_and_names_the_cause(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("T-1", stop=True, reason="scope-not-enforcing")]})

    assert (len(out["calls"]), "scope-not-enforcing" in out["result"]["error"]) == (1, True)


def test_three_launches_with_max_lanes_two_peak_at_two_in_worktrees(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "delayMs": 30, "agents": [
        _start("L-0001", "L-0002", "L-0003", max_lanes=2),
        _lane("L-0001"), _lane("L-0002"), _lane("L-0003"),
        _collect(("L-0001", "clean"), ("L-0002", "clean"), ("L-0003", "clean"))]})

    lanes = [c for c in out["calls"] if c["label"].startswith("lane ")]
    assert (out["peak"], len(lanes), all(c["options"].get("isolation") == "worktree" for c in lanes),
            _states(out)) == (2, 3, True, {"L-0001": "clean", "L-0002": "clean", "L-0003": "clean"})


def test_each_lane_agent_gets_its_brief_verbatim_with_one_ticket_id_line(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0101", "L-0102"), _lane("L-0101"), _lane("L-0102"),
        _collect(("L-0101", "clean"), ("L-0102", "clean"))]})

    prompts = {c["label"]: c["prompt"] for c in out["calls"] if c["label"].startswith("lane ")}
    assert {label: [line for line in text.splitlines() if re.fullmatch(r"Ticket ID: [A-Z]+-\d{4}", line)]
            for label, text in prompts.items()} == {
        "lane L-0101": ["Ticket ID: L-0101"], "lane L-0102": ["Ticket ID: L-0102"]}
    assert prompts["lane L-0101"] == "Ticket ID: L-0101\nlane brief for L-0101"


def test_a_rejected_lane_agent_is_unknown_even_when_collect_says_clean(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001", "L-0002"), {"match": "lane L-0001", "reject": "boom"}, _lane("L-0002"),
        _collect(("L-0001", "clean"), ("L-0002", "clean"))]})

    assert _states(out) == {"L-0001": "unknown", "L-0002": "clean"}


def test_a_lane_agent_returning_malformed_json_is_unknown(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001"), {"match": "lane L-0001", "raw": "not json at all"},
        _collect(("L-0001", "clean"))]})

    assert _states(out) == {"L-0001": "unknown"}


def test_a_lane_agent_reporting_a_state_outside_the_four_is_unknown(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001"), _lane("L-0001", state="done"), _collect(("L-0001", "clean"))]})

    assert _states(out) == {"L-0001": "unknown"}


def test_a_lane_agent_reporting_another_ticket_is_unknown(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001"), {"match": "lane L-0001", "result": {
            "ticket": "L-0002", "state": "clean", "reason": ""}}, _collect(("L-0001", "clean"))]})

    assert _states(out) == {"L-0001": "unknown"}


def test_collect_reporting_an_unknown_lane_is_returned_as_is(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001"), _lane("L-0001"), _collect(("L-0001", "unknown"))]})

    assert _states(out) == {"L-0001": "unknown"}


def test_collect_failing_or_malformed_makes_every_launched_lane_unknown(tmp_path):
    for bad in ({"match": "collect", "raw": "garbage"},
                {"match": "collect", "result": {"lanes": [{"ticket": "L-0001"}]}},
                {"match": "collect", "reject": "down"}):
        out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
            _start("L-0001", "L-0002"), _lane("L-0001"), _lane("L-0002"), bad]})

        assert (_states(out), out["result"]["error"]) == (
            {"L-0001": "unknown", "L-0002": "unknown"}, "collect unreadable"), bad


def test_a_launched_ticket_missing_from_collect_is_unknown(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001", "L-0002"), _lane("L-0001"), _lane("L-0002"), _collect(("L-0001", "clean"))]})

    assert _states(out) == {"L-0001": "clean", "L-0002": "unknown"}


def test_a_malformed_start_result_launches_nothing(tmp_path):
    for bad in ({"match": "start", "raw": "garbage"},
                {"match": "start", "reject": "down"},
                {"match": "start", "raw": {"stop": False, "stopReason": "", "lanes": []}},
                {"match": "start", "raw": {"stop": False, "stopReason": "", "maxLanes": 0, "lanes": []}},
                {"match": "start", "raw": {"stop": False, "stopReason": "", "maxLanes": 2,
                                           "lanes": [{"ticket": "L-0001"}]}}):
        out = _run(tmp_path, {"args": {"set": "s"}, "agents": [bad, _lane("L-0001")]})

        assert (sorted(out["result"]), [c["label"] for c in out["calls"]]) == (["error"], ["start s"]), bad


def test_an_empty_lane_prompt_launches_nothing(tmp_path):
    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001", "L-0002", prompts={"L-0002": "  "}), _lane("L-0001"), _lane("L-0002")]})

    assert (sorted(out["result"]), [c["label"] for c in out["calls"]]) == (["error"], ["start s"])


def test_collect_report_fields_beyond_lanes_are_kept(tmp_path):
    scenario = _collect(("L-0001", "clean"))
    scenario["result"]["land"] = [["L-0001", "1.2.57"]]

    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        _start("L-0001"), _lane("L-0001"), scenario]})

    assert out["result"]["land"] == [["L-0001", "1.2.57"]]


def test_a_pinned_lane_model_reaches_the_lane_agent_and_an_unpinned_lane_sets_none(tmp_path):
    start = _start("L-0001", "L-0002")
    start["result"]["lanes"][0]["model"] = "claude-sonnet-5-5"

    out = _run(tmp_path, {"args": {"set": "s"}, "agents": [
        start, _lane("L-0001"), _lane("L-0002"), _collect(("L-0001", "clean"), ("L-0002", "clean"))]})

    options = {c["label"]: c["options"] for c in out["calls"] if c["label"].startswith("lane ")}
    assert (options["lane L-0001"].get("model"), "model" in options["lane L-0002"]) == (
        "claude-sonnet-5-5", False)


@pytest.mark.parametrize("slug", ["Bad_Slug", "Has.Dot", "-lead", "", "x" * 65, "a b", 7, None])
def test_a_set_arg_outside_crew_waves_slug_grammar_is_rejected_before_any_agent_runs(tmp_path, slug):
    out = _run(tmp_path, {"args": {"set": slug}, "agents": []})

    assert (sorted(out["result"]), out["calls"]) == (["error"], [])


@pytest.mark.parametrize("slug", ["s", "my-wave", "a" * 64, "0day"])
def test_a_set_arg_inside_the_grammar_reaches_the_start_agent(tmp_path, slug):
    out = _run(tmp_path, {"args": {"set": slug}, "agents": [_start(), _collect()]})

    assert slug in out["calls"][0]["prompt"]
