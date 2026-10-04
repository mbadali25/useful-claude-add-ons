"""T-0058: autopilot's size check after spec and after plan, and
`/crew:autopilot split`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_split.py -q

`next_phase` runs T-0052's `crew_split.triggers` once after the spec
validates and once after the plan validates. Nothing fired continues; a fired
trigger with no current `split.md` decision is `split-check` (autopilot looks,
not a stop); `not-too-big` continues; `slices` continues at spec and, at plan,
only when T-0059's `parse_slices` validates; `split` is `split-approval` (a
stop) until applied, then `closed`. A measure whose source is there but cannot
be read is `split-check-unknown` (a stop); a source this repo does not have at
all (no codemap, no review recorded) is named `unmeasured`, never read as "not
fired" and never a stop. `crew_autopilot.py split` prints, checks and applies
through `crew_split.apply(..., via="autopilot")` under `ticket_split_policy`.

Every repository is built under tmp_path; nothing touches the real one.
"""
import json
import os
import subprocess
import sys


import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_split
import crew_ticket
import crew_tracker
from scope_fixtures import SPEC, make_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_autopilot.py")
_COMMAND = os.path.join(_ROOT, "commands", "autopilot.md")


# --- fixtures ----------------------------------------------------------------

def _criteria(count):
    return [f"criterion number {n} holds" for n in range(1, count + 1)]


def _spec(ticket, count, risk="high"):
    body = SPEC.format(ticket=ticket, touch="- `src/**`").replace(
        "- [ ] tests pass\n", "".join(f"- [ ] {c}\n" for c in _criteria(count)))
    first, rest = body.split("\n", 1)
    return f"{first} title          status: spec   risk: {risk}\n{rest}"


def _plan(steps):
    return "# Plan\n\n" + "".join(f"### Step {n}: s{n}\nFiles: src/app.py\nTest: pytest\n"
                                  f"Risk: low\n\n" for n in range(1, steps + 1))


def _repo(tmp_path, approval="self", tracker="files", allow=True):
    root = make_repo(tmp_path, mode="off")
    (root / ".crew" / "config.json").write_text(json.dumps({
        "tracker": tracker, "scope": {"mode": "off", "allowCliApproval": allow},
        "autopilot": {"mode": "plan", "approval": approval}}), encoding="utf-8")
    return root


def _ticket(root, count=1, steps=None, risk="high"):
    """Mint the parent through the real tracker, give it a spec (and a plan),
    move it to `spec` and activate it. Returns its id."""
    ticket = crew_ticket.mint(str(root), "parent", status="ready", direction="go\n")["ticket"]
    folder = root / ".work" / "tickets" / ticket
    (folder / "spec.md").write_text(_spec(ticket, count, risk), encoding="utf-8", newline="\n")
    if steps is not None:
        (folder / "plan.md").write_text(_plan(steps), encoding="utf-8", newline="\n")
    assert crew_tracker.exit_code(crew_tracker.move(str(root), ticket, "spec")) == 0
    crew_ticket.activate(str(root), ticket)
    return ticket


def _decision(root, ticket, decision, answered, count=12):
    lines = [f"# {ticket} split          decision: {decision}", f"answered: {answered}", "",
             "## Evidence", "- acceptance-count: 12 checks", ""]
    if decision == "split":
        crit = _criteria(count)
        half = count // 2
        lines[4:5] = ["- acceptance-count: 12 checks",
                      "- separable-criteria: the two halves are verified apart"]
        lines += ["## Children", "### Child 1: first half", "risk: low", "subsystem: crew",
                  "Criteria:"] + [f"- {c}" for c in crit[:half]] + [
                  "Excludes:", "- the second half", "", "### Child 2: second half",
                  "risk: low", "subsystem: crew", "Criteria:"] + [
                  f"- {c}" for c in crit[half:]] + ["Excludes:", "- the first half", "",
                                                    "## Stays on parent", "- none", ""]
    path = root / ".work" / "tickets" / ticket / "split.md"
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def _next(root, ticket):
    return crew_autopilot.next_phase(str(root), ticket)


def _cli(root, *args):
    return subprocess.run([sys.executable, _SCRIPT, *args, "--root", str(root)],
                          capture_output=True, text=True, check=False)


# --- next_phase: the size check ----------------------------------------------

def test_no_trigger_goes_straight_to_plan(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1)

    got = _next(root, ticket)

    assert (got["phase"], got["stop"]) == ("plan", False), got


def test_acceptance_trigger_after_spec_names_split_check(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], got["command"]) == (
        "split-check", False, f"/crew:autopilot split {ticket}"), got
    assert "acceptance-count" in got["reason"] and "after spec" in got["reason"]


def test_plan_steps_trigger_after_plan_names_split_check(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1, steps=9)

    got = _next(root, ticket)

    assert (got["phase"], got["stop"]) == ("split-check", False), got
    assert "plan-steps" in got["reason"] and "after plan" in got["reason"]


def test_eight_plan_steps_fire_nothing(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1, steps=8)

    assert _next(root, ticket)["phase"] == "approve"


def test_not_too_big_continues(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "not-too-big", "acceptance-count")

    got = _next(root, ticket)

    assert (got["phase"], got["stop"]) == ("plan", False), got


def test_new_trigger_after_plan_restales_spec_decision(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=9)
    _decision(root, ticket, "not-too-big", "acceptance-count")

    got = _next(root, ticket)

    assert (got["phase"], "plan-steps" in got["reason"]) == ("split-check", True), got


def test_decision_answering_every_trigger_continues_after_plan(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=9)
    _decision(root, ticket, "not-too-big", "acceptance-count, plan-steps")

    assert _next(root, ticket)["phase"] == "approve"


def test_decision_failing_the_rulebook_is_not_current(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    path = _decision(root, ticket, "not-too-big", "acceptance-count")
    path.write_text(path.read_text(encoding="utf-8").replace("acceptance-count: 12",
                                                             "vibes: 12"), encoding="utf-8")

    got = _next(root, ticket)

    assert (got["phase"], "vibes" in got["reason"]) == ("split-check", True), got


def test_unknown_measure_stops(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1)
    (root / ".crew" / "codemap").mkdir()  # there, but no subsystem can be read

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "subsystems" in got["reason"]) == (
        "split-check-unknown", True, True), got


def test_plain_bullet_acceptance_stops_unknown(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1)
    spec = root / ".work" / "tickets" / ticket / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("- [ ] ", "- "), encoding="utf-8")

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "acceptance-count" in got["reason"],
            "`- [ ]`" in got["reason"]) == ("split-check-unknown", True, True, True), got


def test_unreadable_metrics_stops(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1)
    (root / ".crew" / "metrics.md").mkdir()  # there, and not a readable file

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "findings-rate" in got["reason"]) == (
        "split-check-unknown", True, True), got


def test_unreadable_metrics_file_is_not_absent(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / ".crew" / "metrics.md").write_text("date | ticket\n", encoding="utf-8")
    real = open

    def denied(path, *args, **kwargs):
        if str(path).endswith("metrics.md"):
            raise PermissionError(13, "Permission denied")
        return real(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", denied)

    assert "findings-rate" not in crew_split.absent_sources(str(root))


def test_absent_sources_are_named_never_quiet(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)

    got = _next(root, ticket)
    absent = crew_split.absent_sources(str(root))

    assert sorted(absent) == ["findings-rate", "subsystems", "tickets-too-large"], absent
    assert "unmeasured: subsystems" in got["reason"], got


def test_header_only_metrics_is_no_review_yet(tmp_path):
    root = _repo(tmp_path)
    (root / ".crew" / "metrics.md").write_text("date | ticket | reviewer | BLOCK | FIX\n",
                                               encoding="utf-8")

    assert "findings-rate" in crew_split.absent_sources(str(root))


def test_metrics_with_a_review_is_measured(tmp_path):
    root = _repo(tmp_path)
    (root / ".crew" / "metrics.md").write_text(
        "date | ticket | reviewer | BLOCK | FIX\n2026-01-01 | T-9 | codex | 0 | 1\n",
        encoding="utf-8")

    assert "findings-rate" not in crew_split.absent_sources(str(root))


def test_slices_continues_at_spec(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "slices", "acceptance-count")

    assert _next(root, ticket)["phase"] == "plan"


def test_slices_without_parse_slices_stops_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=1)
    _decision(root, ticket, "slices", "acceptance-count")
    monkeypatch.delattr(crew_split, "parse_slices", raising=False)

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "T-0059" in got["reason"]) == (
        "split-check-unknown", True, True), got


def test_slices_with_parse_slices_problems_goes_back_to_plan(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=1)
    _decision(root, ticket, "slices", "acceptance-count")
    monkeypatch.setattr(crew_split, "parse_slices", lambda text: ([], ["no ## PR slices"]),
                        raising=False)

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "no ## PR slices" in got["reason"]) == (
        "plan", True, True), got


def test_slices_with_valid_parse_slices_continues(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=1)
    _decision(root, ticket, "slices", "acceptance-count")
    monkeypatch.setattr(crew_split, "parse_slices", lambda text: (["a", "b"], []),
                        raising=False)

    assert _next(root, ticket)["phase"] == "approve"


def test_split_decision_stops_at_split_approval(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], got["command"]) == (
        "split-approval", True, f"/crew:split {ticket}"), got
    assert "split --apply" in got["reason"], got


def test_split_approval_with_a_policy_crash_stops_never_raises(tmp_path, monkeypatch):
    """NIT 2: an error inside the split rule reaches next as a could-not-tell
    refusal at split-approval, never a crash."""
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")

    def boom(*_a, **_k):
        raise KeyError("approval")

    monkeypatch.setattr(crew_autopilot, "_split_rule", boom)

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "could not tell" in got["reason"]) == (
        "split-approval", True, True), got


def test_split_approval_under_human_names_the_owner(tmp_path):
    root = _repo(tmp_path, approval="human")
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")

    got = _next(root, ticket)

    assert (got["phase"], "autopilot.approval is human" in got["reason"]) == (
        "split-approval", True), got


def test_split_approval_in_status_names_no_policy(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")

    got = crew_autopilot.next_phase(str(root), ticket, policy=False)

    assert (got["phase"], "autopilot.approval" in got["reason"]) == ("split-approval", False)


def test_superseded_parent_is_closed(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")
    crew_split.apply(str(root), ticket, "autopilot")

    got = _next(root, ticket)

    assert (got["phase"], got["stop"], "split-into" in got["reason"]) == ("closed", True, True)


def test_split_phases_have_a_waiting_party():
    assert (crew_autopilot.WAITING.get("split-check"),
            crew_autopilot.WAITING.get("split-approval"),
            crew_autopilot.WAITING.get("split-check-unknown")) == ("autopilot", "owner", "owner")


def test_split_stops_are_listed():
    slugs = {slug for slug, _text in crew_autopilot.FIXED_STOPS}
    assert {"split-approval", "split-check-unknown"} <= slugs


# --- the split subcommand ----------------------------------------------------

def test_split_subcommand_bare_prints_measures(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)

    run = _cli(root, "split", "--ticket", ticket)

    assert run.returncode == 0, run.stdout + run.stderr
    assert "acceptance=12" in run.stdout and "triggers: acceptance-count" in run.stdout
    assert "unmeasured: subsystems" in run.stdout and "policy: allow" in run.stdout


def test_split_subcommand_check_and_apply(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")

    check = _cli(root, "split", "--ticket", ticket, "--check")
    applied = _cli(root, "split", "--ticket", ticket, "--apply")

    assert (check.returncode, "ok decision=split" in check.stdout) == (0, True), check.stdout
    assert applied.returncode == 0, applied.stdout + applied.stderr
    kids = [line.split("=", 1)[1] for line in applied.stdout.splitlines()
            if line.startswith("child=")]
    assert len(kids) == 2 and f"parent={ticket} status=superseded" in applied.stdout
    assert all(os.path.isfile(root / ".work" / "tickets" / kid / "direction.md") for kid in kids)


def test_split_subcommand_apply_under_human_names_crew_split(tmp_path):
    root = _repo(tmp_path, approval="human")
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")

    run = _cli(root, "split", "--ticket", ticket, "--apply")

    assert run.returncode != 0, run.stdout
    assert run.stdout.rstrip().splitlines()[-1] == f"owner: the human types /crew:split {ticket}"
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()


def test_split_subcommand_apply_in_jira_always_stops(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")
    config = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    config["tracker"] = "jira"
    (root / ".crew" / "config.json").write_text(json.dumps(config), encoding="utf-8")

    run = _cli(root, "split", "--ticket", ticket, "--apply")

    assert (run.returncode != 0, "/crew:split <KEY>" in run.stdout) == (True, True), run.stdout


def test_split_apply_refuses_a_decision_missing_a_fired_trigger(tmp_path):
    """NIT 3: --apply holds split.md to the same answered: rule as --check and
    the gate: a decision taken before a trigger fired is not applied."""
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=9)
    _decision(root, ticket, "split", "acceptance-count")

    run = _cli(root, "split", "--ticket", ticket, "--apply")

    assert run.returncode == 1, run.stdout
    assert "answered: does not name plan-steps" in run.stdout, run.stdout
    assert run.stdout.rstrip().splitlines()[-1] == f"owner: the human types /crew:split {ticket}"
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()


def test_split_check_and_apply_refuse_while_a_measure_is_unknown(tmp_path):
    """Re-review FIX: where next says split-check-unknown, --check and --apply
    refuse too (the gate's wording), and nothing is minted or superseded."""
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)
    _decision(root, ticket, "split", "acceptance-count")
    (root / ".crew" / "metrics.md").mkdir()
    before = sorted(os.listdir(root / ".work" / "tickets"))

    gate = _next(root, ticket)
    check = _cli(root, "split", "--ticket", ticket, "--check")
    applied = _cli(root, "split", "--ticket", ticket, "--apply")

    assert gate["phase"] == "split-check-unknown", gate
    assert (check.returncode, "could not read findings-rate" in check.stdout) == (1, True), \
        check.stdout
    assert (applied.returncode, "could not read findings-rate" in applied.stdout) == (1, True), \
        applied.stdout
    assert applied.stdout.rstrip().splitlines()[-1] == (
        f"owner: the human types /crew:split {ticket}")
    assert sorted(os.listdir(root / ".work" / "tickets")) == before
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()


def test_split_check_uses_the_gate_stage_when_the_plan_fails_validate(tmp_path):
    """Re-review NIT: with a plan.md that fails validate, the gate runs only
    the spec-stage check, so --check does not hold the decision to plan-steps."""
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=9)
    plan = root / ".work" / "tickets" / ticket / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("src/app.py", "other/keep.py"),
                    encoding="utf-8")
    _decision(root, ticket, "not-too-big", "acceptance-count")

    gate = _next(root, ticket)
    check = _cli(root, "split", "--ticket", ticket, "--check")

    assert gate["phase"] == "plan", gate
    assert (check.returncode, check.stdout.strip()) == (0, "ok decision=not-too-big"), check.stdout


def test_split_check_refuses_a_decision_missing_a_fired_trigger(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12, steps=9)
    _decision(root, ticket, "not-too-big", "acceptance-count")

    run = _cli(root, "split", "--ticket", ticket, "--check")

    assert run.returncode == 1, run.stdout
    assert "answered: does not name plan-steps" in run.stdout


def test_split_subcommand_crash_is_a_refusal(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=12)

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(crew_split, "measure", boom)
    code = crew_autopilot.main(["split", "--root", str(root), "--ticket", ticket])

    assert (code, "refused:" in capsys.readouterr().out) == (1, True)


def test_route_lists_split_as_available(tmp_path):
    root = _repo(tmp_path)
    ticket = _ticket(root, count=1)

    got = crew_autopilot.route_args(str(root), f"split {ticket}")

    assert (got["sub"], got["stop"], got["ticket"], "split" in crew_autopilot.AVAILABLE) == (
        "split", False, ticket, True), got


# --- autopilot.md ------------------------------------------------------------

def _command_text():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def test_command_runs_the_split_check_through_the_rulebook():
    flat = " ".join(_command_text().split())
    assert all(word in flat for word in (
        "`split-check`", "`split-approval`", "`split-check-unknown`", "crew:explorer",
        "split.md", "crew_autopilot.py split --root . --ticket <ticket> --check",
        "crew_autopilot.py split --root . --ticket <ticket> --apply")), flat


def test_command_stops_split_approval_on_crew_split_for_the_human():
    flat = " ".join(_command_text().split())
    assert "the human types `/crew:split <ticket>`" in flat


def test_autopilot_never_runs_crew_split():
    lines = [line for line in _command_text().splitlines() if "/crew:split" in line]
    assert lines, "autopilot.md names /crew:split for the human"
    assert all("human" in line or "never" in line for line in lines), lines
    assert "Never run `/crew:split`" in " ".join(_command_text().split())


def test_command_says_jira_always_stops_for_the_owner():
    flat = " ".join(_command_text().split())
    assert "Jira" in flat and "always" in flat.split("Jira", 1)[1][:200]
