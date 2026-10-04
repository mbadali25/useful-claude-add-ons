"""T-0010: `/crew:autopilot`'s approval and questions policies.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_policy.py -q

`autopilot.approval` and `autopilot.questions` (human|self|risk, default
`risk`) decide what autopilot does at the plan-approval phase and at an open
question. `approval_policy` never allows unless `scope.allowCliApproval` is
exactly true; `risk` allows only a spec header that says `risk: low`; an
unknown risk reads as high, and a value that is not a policy reads as
`human`. Review FINDINGS are never accepted by autopilot at any setting.
Every repository is built under tmp_path; nothing touches the real one or
~/.claude. `sabotage_autopilot.py`'s POLICY_MUTATIONS prove these can fail.
"""
import json
import os
import subprocess
import sys

import context  # pylint: disable=unused-import
import crew_autopilot
import crew_ticket
import pytest
import review_ledger
from scope_fixtures import PLAN, SPEC, approve_as_user, make_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_autopilot.py")
_COMMAND = os.path.join(_ROOT, "commands", "autopilot.md")
T = "T-1"
POLICIES = ("human", "self", "risk")
RISKS = ("low", "med", "high", None)


# --- fixtures ----------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _header(risk):
    return "status: spec" + (f"   risk: {risk}" if risk else "")


def _spec_text(header):
    body = SPEC.format(ticket=T, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    return f"{first} title          {header}\n{rest}"


def _repo(tmp_path, approval="risk", questions="risk", allow=True, risk="low",
          armed=True, header=None):
    """A repo with one valid, active ticket and the given policy config.
    `allow` is written verbatim as `scope.allowCliApproval` (MISSING omits it)."""
    root = make_repo(tmp_path, mode="off")
    scope = {"mode": "off"}
    if allow is not MISSING:
        scope["allowCliApproval"] = allow
    block = {"mode": "plan" if armed else "off"}
    for key, value in (("approval", approval), ("questions", questions)):
        if value is not MISSING:
            block[key] = value
    _write(root / ".crew" / "config.json", json.dumps({"scope": scope, "autopilot": block}))
    folder = root / ".work" / "tickets" / T
    _write(folder / "direction.md", "go\n")
    _write(folder / "spec.md", _spec_text(header if header is not None else _header(risk)))
    _write(folder / "plan.md", PLAN.format(files="src/app.py"))
    _write(root / ".work" / "INDEX.md", f"{T} | ready | low | r | title\n")
    crew_ticket.activate(str(root), T)
    return root


MISSING = object()


def _cli(root, *args):
    return subprocess.run([sys.executable, _SCRIPT] + list(args) + ["--root", str(root)],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def _receipt(root):
    receipt, state = crew_ticket.read_approval(str(root), T)
    return receipt if state == "ok" else None


def _ledger(root, rounds, state, receipt=None):
    path = review_ledger.ledger_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, json.dumps({"ticket": T, "budget": 2, "rounds": rounds, "refused": [],
                             "state": state, "receipt": receipt}))


# --- step 1: approval_policy ---------------------------------------------------

@pytest.mark.parametrize("risk", RISKS)
def test_approval_human_never_allows(tmp_path, risk):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, approval="human", risk=risk)), T)

    assert (got["allow"], got["policy"]) == (False, "human")


@pytest.mark.parametrize("risk", RISKS)
def test_approval_self_allows_any_risk(tmp_path, risk):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, approval="self", risk=risk)), T)

    assert (got["allow"], got["policy"]) == (True, "self")


@pytest.mark.parametrize("risk,allow", [("low", True), ("med", False), ("high", False),
                                        ("LOW", True), ("Med", False)])
def test_approval_risk_allows_only_low(tmp_path, risk, allow):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, approval="risk", risk=risk)), T)

    assert (got["allow"], got["risk"], got["known"]) == (allow, risk.lower(), True)


@pytest.mark.parametrize("header", ["status: spec", "status: spec   risk: lo",
                                    "status: spec   risk: LOW!", "status: spec   risk:"])
def test_approval_risk_unknown_denies(tmp_path, header):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, header=header)), T)

    assert (got["allow"], got["risk"], got["known"]) == (False, "high", False)


@pytest.mark.parametrize("header", [
    "status: spec   risk: high   risk: low",
    "cut risk: low paths   status: spec   risk: high"])
def test_approval_header_naming_risk_twice_is_unknown(tmp_path, header):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, approval="risk", header=header)),
                                         T)

    assert (got["allow"], got["known"]) == (False, False)


def test_approval_risk_in_the_body_is_not_the_header(tmp_path):
    root = _repo(tmp_path, header="status: spec")
    spec = root / ".work" / "tickets" / T / "spec.md"
    _write(spec, spec.read_text(encoding="utf-8") + "\nrisk: low\n")

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], got["known"]) == (False, False)


@pytest.mark.parametrize("policy", ["self", "risk"])
@pytest.mark.parametrize("allow", [MISSING, False, "true", 1, None])
def test_approval_requires_allow_cli_approval(tmp_path, policy, allow):
    got = crew_autopilot.approval_policy(
        str(_repo(tmp_path, approval=policy, allow=allow)), T)

    assert (got["allow"], "scope.allowCliApproval" in got["reason"]) == (False, True)


def test_approval_without_a_config_file_denies(tmp_path):
    root = _repo(tmp_path, approval="self")
    (root / ".crew" / "config.json").unlink()

    got = crew_autopilot.approval_policy(str(root), T)

    assert got["allow"] is False


@pytest.mark.parametrize("value", ["Self", "auto", "yes", True, None, 1, ["self"]])
def test_approval_bad_value_reads_human(tmp_path, value):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, approval=value)), T)

    assert (got["allow"], got["policy"], repr(value) in " ".join(got["warnings"])) == (
        False, "human", True)


def test_approval_default_is_risk(tmp_path):
    got = crew_autopilot.approval_policy(str(_repo(tmp_path, approval=MISSING)), T)

    assert (got["policy"], got["allow"]) == ("risk", True)


def test_approval_refuses_when_the_review_ledger_is_unreadable(tmp_path):
    root = _repo(tmp_path, approval="self")
    path = review_ledger.ledger_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, "{not json")

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], "review ledger" in got["reason"]) == (False, True)


def _needs_replan_with_a_successor_plan(tmp_path, approval="self", risk="low"):
    """T-1 approved by the user, its review budget spent (NEEDS_REPLAN), then
    plan.md rewritten: the distinct successor plan that is the way out."""
    root = _repo(tmp_path, approval=approval, risk=risk)
    approve_as_user(root, T)
    _ledger(root, [], review_ledger.NEEDS_REPLAN)
    _write(root / ".work" / "tickets" / T / "plan.md",
           PLAN.format(files="src/app.py") + "\nA successor plan, after the budget ran out.\n")
    return root


@pytest.mark.parametrize("risk", RISKS)
def test_approval_self_allows_a_successor_plan_under_needs_replan(tmp_path, risk):
    root = _needs_replan_with_a_successor_plan(tmp_path, risk=risk)

    got = crew_autopilot.approval_policy(str(root), T)

    assert got["allow"] is True


def test_approval_risk_still_refuses_a_high_successor_plan_under_needs_replan(tmp_path):
    root = _needs_replan_with_a_successor_plan(tmp_path, approval="risk", risk="high")

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], "risk: high" in got["reason"]) == (False, True)


def test_autopilot_approve_of_a_successor_plan_continues_needs_replan(tmp_path):
    root = _needs_replan_with_a_successor_plan(tmp_path)

    done = _cli(root, "approve", "--ticket", T)

    assert (done.returncode, done.stdout.startswith(f"self-approved {T}"),
            review_ledger.status(str(root), T)["state"]) == (0, True, review_ledger.IN_REVIEW)


def test_autopilot_approve_of_the_same_plan_leaves_needs_replan(tmp_path):
    root = _repo(tmp_path, approval="self")
    approve_as_user(root, T)
    _ledger(root, [], review_ledger.NEEDS_REPLAN)

    done = _cli(root, "approve", "--ticket", T)

    assert (done.returncode, "NEEDS_REPLAN" in done.stdout,
            review_ledger.status(str(root), T)["state"]) == (3, True, review_ledger.NEEDS_REPLAN)


def test_approval_with_no_spec_denies_under_risk(tmp_path):
    root = _repo(tmp_path)
    (root / ".work" / "tickets" / T / "spec.md").unlink()

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], got["known"]) == (False, False)


def test_approval_policy_that_cannot_read_settings_denies(tmp_path, monkeypatch):
    root = _repo(tmp_path, approval="self")

    def boom(_root):
        raise OSError("disk")
    monkeypatch.setattr(crew_autopilot, "settings", boom)

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], got["policy"], "could not tell" in got["reason"]) == (
        False, "unknown", True)


# --- step 1: question_policy ---------------------------------------------------

@pytest.mark.parametrize("risk", RISKS)
def test_questions_human_stops(tmp_path, risk):
    got = crew_autopilot.question_policy(str(_repo(tmp_path, questions="human", risk=risk)), T)

    assert (got["action"], got["policy"]) == ("stop", "human")


@pytest.mark.parametrize("risk", RISKS)
def test_questions_self_takes(tmp_path, risk):
    got = crew_autopilot.question_policy(str(_repo(tmp_path, questions="self", risk=risk)), T)

    assert (got["action"], got["policy"]) == ("take", "self")


@pytest.mark.parametrize("header,action", [
    ("status: spec   risk: low", "take"), ("status: spec   risk: med", "stop"),
    ("status: spec   risk: high", "stop"), ("status: spec", "stop"),
    ("status: spec   risk: lo", "stop")])
def test_questions_risk_takes_only_low(tmp_path, header, action):
    got = crew_autopilot.question_policy(str(_repo(tmp_path, questions="risk", header=header)),
                                         T)

    assert got["action"] == action


def test_questions_do_not_depend_on_allow_cli_approval(tmp_path):
    got = crew_autopilot.question_policy(
        str(_repo(tmp_path, questions="self", allow=False)), T)

    assert got["action"] == "take"


@pytest.mark.parametrize("value", ["Self", "take", True, None])
def test_questions_bad_value_reads_human(tmp_path, value):
    got = crew_autopilot.question_policy(str(_repo(tmp_path, questions=value, risk="low")), T)

    assert (got["action"], got["policy"], bool(got["warnings"])) == ("stop", "human", True)


def test_question_policy_that_cannot_read_settings_stops(tmp_path, monkeypatch):
    root = _repo(tmp_path, questions="self")

    def boom(_root):
        raise OSError("disk")
    monkeypatch.setattr(crew_autopilot, "settings", boom)

    got = crew_autopilot.question_policy(str(root), T)

    assert (got["action"], got["policy"]) == ("stop", "unknown")


def test_settings_report_both_policies(tmp_path):
    got = crew_autopilot.settings(str(_repo(tmp_path, approval="self", questions="human")))

    assert (got["approval"], got["questions"]) == ("self", "human")


# --- step 2: the autopilot receipt ---------------------------------------------

def test_autopilot_approve_writes_an_autopilot_receipt(tmp_path):
    root = _repo(tmp_path, approval="risk", risk="low")

    done = _cli(root, "approve", "--ticket", T)
    receipt = _receipt(root)

    assert (done.returncode, done.stdout.strip(), receipt["approved_via"],
            receipt["approved_by"], crew_ticket.accepted(str(root), T)["status"]) == (
        0, f"self-approved {T} under approval=risk, risk=low", "autopilot", "autopilot:risk",
        "approved")


@pytest.mark.parametrize("approval,risk", [("human", "low"), ("risk", "med"), ("risk", None)])
def test_autopilot_approve_refused_prints_reason(tmp_path, approval, risk):
    root = _repo(tmp_path, approval=approval, risk=risk)

    done = _cli(root, "approve", "--ticket", T)

    assert (done.returncode, done.stdout.startswith("refused:"),
            f"/crew:approve {T}" in done.stdout, _receipt(root)) == (2, True, True, None)


def test_autopilot_approve_refuses_unarmed(tmp_path):
    root = _repo(tmp_path, approval="self", armed=False)

    done = _cli(root, "approve", "--ticket", T)

    assert (done.returncode, "autopilot.mode" in done.stdout, _receipt(root)) == (
        2, True, None)


def test_autopilot_approve_refuses_without_allow_cli_approval(tmp_path):
    root = _repo(tmp_path, approval="self", allow=False)

    done = _cli(root, "approve", "--ticket", T)

    assert (done.returncode, _receipt(root)) == (2, None)


def test_the_library_refuses_an_autopilot_receipt_the_policy_denies(tmp_path):
    root = _repo(tmp_path, approval="human")

    with pytest.raises(crew_ticket.TicketError, match="autopilot.approval"):
        crew_ticket.approve(str(root), T, by="autopilot:human", via=crew_ticket.AUTOPILOT)

    assert _receipt(root) is None


def test_an_unknown_via_is_still_refused(tmp_path):
    root = _repo(tmp_path, approval="self")

    with pytest.raises(crew_ticket.TicketError, match="approved_via"):
        crew_ticket.approve(str(root), T, via="autopilot-ish")


# --- review FINDINGS are the owner's at every setting ----------------------------

@pytest.mark.parametrize("approval", POLICIES)
@pytest.mark.parametrize("questions", POLICIES)
def test_findings_are_never_self_accepted(tmp_path, approval, questions):
    root = _repo(tmp_path, approval=approval, questions=questions)
    approve_as_user(root, T)
    row = {"round": 1, "status": "completed", "provider": "claude", "model": None,
           "verdict": "FINDINGS", "bundle_sha256": "a" * 64, "base": "HEAD"}
    _ledger(root, [row], "REVIEWED")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"]) == ("accept-review", True)


def test_autopilot_has_no_route_to_review_acceptance():
    with open(_SCRIPT, encoding="utf-8") as handle:
        source = handle.read()

    assert ("review_ledger.accept(" in source, "accept_review" in source) == (False, False)


# --- next names the policy at the two human phases ------------------------------

def test_next_approve_phase_names_the_autopilot_route_when_the_policy_allows(tmp_path):
    root = _repo(tmp_path, approval="risk", risk="low")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], f"crew_autopilot.py approve --root . --ticket {T}"
            in got["reason"]) == ("approve", True, True)


def test_next_approve_phase_names_the_human_when_the_policy_refuses(tmp_path):
    root = _repo(tmp_path, approval="human")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], "crew_autopilot.py approve" in got["reason"],
            got["command"]) == ("approve", True, False, f"/crew:approve {T}")


@pytest.mark.parametrize("questions,action", [("self", "take"), ("human", "stop")])
def test_next_open_questions_names_the_question_policy(tmp_path, questions, action):
    root = _repo(tmp_path, questions=questions)
    _write(root / ".work" / "tickets" / T / "direction.md",
           "go\n\n## Open questions\n- which database?\n")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], f"action={action}" in got["reason"]) == (
        "open-questions", True, True)


# --- step 4: questions.md -------------------------------------------------------

GOOD_QUESTIONS = """# T-1 questions

## Q1: Which database?
Research: crew:explorer found src/db.py uses sqlite3; crew:researcher: none needed.

### Option A (recommended): keep sqlite
Nothing new to run.
Cost: no concurrent writers.

### Option B: postgres
Cost: a server to run and a migration.
"""


def _questions(root, text):
    _write(root / ".work" / "tickets" / T / "questions.md", text)


def _check(root):
    return crew_autopilot.questions_check(str(root), T)


def test_questions_file_shape_valid(tmp_path):
    root = _repo(tmp_path)
    _questions(root, GOOD_QUESTIONS)

    got = _check(root)

    assert (got["valid"], got["problems"], got["questions"]) == (True, [], 1)


def test_questions_file_recommendation_not_first_invalid(tmp_path):
    root = _repo(tmp_path)
    _questions(root, GOOD_QUESTIONS.replace("Option A (recommended)", "Option A").replace(
        "Option B:", "Option B (recommended):"))

    got = _check(root)

    assert (got["valid"], any("recommended" in p for p in got["problems"])) == (False, True)


def test_questions_file_one_option_invalid(tmp_path):
    root = _repo(tmp_path)
    _questions(root, GOOD_QUESTIONS.split("### Option B", maxsplit=1)[0])

    got = _check(root)

    assert (got["valid"], any("2-4" in p for p in got["problems"])) == (False, True)


def test_questions_file_five_options_invalid(tmp_path):
    root = _repo(tmp_path)
    extra = "".join(f"\n### Option {c}: more\nCost: some.\n" for c in "CDE")
    _questions(root, GOOD_QUESTIONS + extra)

    got = _check(root)

    assert (got["valid"], any("2-4" in p for p in got["problems"])) == (False, True)


def test_questions_file_option_without_cost_invalid(tmp_path):
    root = _repo(tmp_path)
    _questions(root, GOOD_QUESTIONS.replace("Cost: a server to run and a migration.\n", ""))

    got = _check(root)

    assert (got["valid"], any("Cost:" in p for p in got["problems"])) == (False, True)


def test_questions_file_without_research_invalid(tmp_path):
    root = _repo(tmp_path)
    _questions(root, "\n".join(line for line in GOOD_QUESTIONS.splitlines()
                               if not line.startswith("Research:")) + "\n")

    got = _check(root)

    assert (got["valid"], any("Research:" in p for p in got["problems"])) == (False, True)


def test_questions_file_missing_invalid(tmp_path):
    got = _check(_repo(tmp_path))

    assert (got["valid"], got["questions"]) == (False, 0)


def test_questions_file_taken_under_self_valid_and_reported(tmp_path):
    root = _repo(tmp_path, questions="self", risk="high")
    _questions(root, GOOD_QUESTIONS + "\ntaken: Option A by autopilot (self)\n")

    got = _check(root)

    assert (got["valid"], got["taken"]) == (True, ["Q1: Option A by autopilot (self)"])


@pytest.mark.parametrize("questions,risk", [("human", "low"), ("risk", "high"),
                                            ("risk", None)])
def test_questions_file_taken_while_the_policy_stops_invalid(tmp_path, questions, risk):
    root = _repo(tmp_path, questions=questions, risk=risk)
    _questions(root, GOOD_QUESTIONS + "\ntaken: Option A by autopilot (self)\n")

    got = _check(root)

    assert (got["valid"], got["action"],
            any("the questions policy says stop" in p for p in got["problems"])) == (
        False, "stop", True)


def test_questions_file_taken_non_recommended_invalid(tmp_path):
    root = _repo(tmp_path, questions="self")
    _questions(root, GOOD_QUESTIONS + "\ntaken: Option B by autopilot (self)\n")

    got = _check(root)

    assert (got["valid"], any("recommended" in p for p in got["problems"])) == (False, True)


SECOND_QUESTION = """
## Q2: Which port?
Research: crew:explorer found src/app.py binds 8080; crew:researcher: none needed.

### Option A (recommended): keep 8080
Cost: none.

### Option B: 443
Cost: root to bind it.
"""


@pytest.mark.parametrize("taken_under,questions,risk", [("risk", "self", "high"),
                                                        ("self", "risk", "low")])
def test_questions_file_taken_under_an_earlier_policy_that_took_stays_valid(
        tmp_path, taken_under, questions, risk):
    root = _repo(tmp_path, questions=questions, risk=risk)
    _questions(root, GOOD_QUESTIONS + f"\ntaken: Option A by autopilot ({taken_under})\n"
               + SECOND_QUESTION)

    got = _check(root)

    assert (got["valid"], got["questions"], got["action"]) == (True, 2, "take")


@pytest.mark.parametrize("taken_under", ["human", "yolo"])
def test_questions_file_taken_naming_a_policy_that_never_takes_invalid(tmp_path, taken_under):
    root = _repo(tmp_path, questions="self")
    _questions(root, GOOD_QUESTIONS + f"\ntaken: Option A by autopilot ({taken_under})\n")

    got = _check(root)

    assert (got["valid"], any("never takes" in p for p in got["problems"])) == (False, True)


def test_questions_check_cli_prints_action_first_then_taken(tmp_path):
    root = _repo(tmp_path, questions="self")
    _questions(root, GOOD_QUESTIONS + "\ntaken: Option A by autopilot (self)\n")

    done = _cli(root, "questions-check", "--ticket", T)
    lines = done.stdout.splitlines()

    assert (done.returncode, lines[0].startswith("valid=1 action=take policy=self"),
            "taken: Q1: Option A by autopilot (self)" in lines) == (0, True, True)


def test_questions_check_cli_invalid_exits_one_and_prints_the_shape(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "questions-check", "--ticket", T)

    assert (done.returncode, done.stdout.startswith("valid=0"),
            "(recommended)" in done.stdout) == (1, True, True)


# --- step 4: the command --------------------------------------------------------

def _command_text():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def test_command_routes_approval_through_policy():
    flat = " ".join(_command_text().split())

    assert ("crew_autopilot.py approve --root . --ticket <ticket>" in flat,
            "crew_autopilot.py questions-check --root . --ticket <ticket>" in flat,
            "crew_ticket.py approve" in flat, "`human` always stops" in flat) == (
        True, True, False, True)


def test_command_sends_a_stop_at_approve_or_open_questions_to_the_policy_first():
    flat = " ".join(_command_text().split())

    assert ("- `stop=1` with `phase=approve` or `phase=open-questions` - not yet a stop" in flat,
            "- any other `stop=1` - print the phase" in flat,
            "Anything but a `stop=0` line" in flat) == (True, True, False)


def test_command_reports_every_self_approval_and_answer_by_name():
    flat = " ".join(_command_text().split())

    assert ("self-approved" in flat, "taken:" in flat) == (True, True)


# --- step 5: sabotage anchors ----------------------------------------------------

def test_every_policy_sabotage_anchor_is_present_exactly_once():
    from sabotage_autopilot import POLICY_MUTATIONS  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, _test in POLICY_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label


def test_policy_sabotage_is_registered_with_sabotage_py():
    import sabotage  # pylint: disable=import-outside-toplevel
    from sabotage_autopilot import POLICY_MUTATIONS  # pylint: disable=import-outside-toplevel

    assert [m[0] for m in POLICY_MUTATIONS if m not in sabotage.MUTATIONS] == []


# --- step 6: the approve exception to T-0018's read-only module ---------------

_REPO = os.path.dirname(os.path.dirname(_ROOT))


def _files(root):
    """{path: (size, sha256)} for every file in the worktree (not `.git`) and
    under `<git-common-dir>/crew/`."""
    import hashlib  # pylint: disable=import-outside-toplevel
    found = {}
    walks = [str(root), os.path.join(crew_ticket.common_dir(str(root)), "crew")]
    for base, dirs, names in (entry for top in walks for entry in os.walk(top)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                data = handle.read()
            found[path] = (len(data), hashlib.sha256(data).hexdigest())
    return found


READ_ONLY_RUNS = (("next", "--ticket", T), ("resume",), ("settings",), ("stops",),
                  ("route", "--args", f"status {T}"), ("status",),
                  ("questions-check", "--ticket", T),
                  ("deploy-allowed", "--env", "staging", "--class", "nonProd"))


def _main(root, action, *rest):
    argv = [action] + ([] if action == "stops" else ["--root", str(root)]) + list(rest)
    return crew_autopilot.main(argv)


# T-0074: `auto-reject` is the module's second writer; nothing else writes.
WRITERS = ("approve", "auto-reject")


def _usage_subcommands():
    usage = crew_autopilot.__doc__.split("\n\n")[1]
    return {line.split()[2] for line in usage.splitlines()
            if line.strip().startswith("python3 crew_autopilot.py ")}


def _out_of_rounds_block(root):
    """`autopilot.maxAutoReplans: 2` and a REVIEWED ledger whose final codex
    round is FINDINGS with one BLOCK: what `auto-reject` acts on."""
    config = root / ".crew" / "config.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["autopilot"]["maxAutoReplans"] = 2
    _write(config, json.dumps(data))
    rows = [{"round": n, "status": "completed", "provider": "codex", "model": None,
             "model_family": "gpt", "verdict": "FINDINGS", "bundle_sha256": "a" * 64,
             "base": "HEAD", "counts": {"BLOCK": 1, "FIX": 0, "NIT": 0},
             "findings": ["BLOCK|src/app.py:1|wrong"], "refunded": False} for n in (1, 2)]
    _ledger(root, rows, review_ledger.REVIEWED)


# The name is older than T-0074: two sabotage_autopilot.py entries (a harness
# file) target this node id, so it keeps the name until L-0671 renames it
# with them. What it pins is WRITERS, `approve` and `auto-reject`.
def test_approve_is_the_only_writing_subcommand(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root = _repo(tmp_path, approval="self", risk="low")
    _questions(root, GOOD_QUESTIONS)
    before = _files(root)

    for run in READ_ONLY_RUNS:
        _main(root, *run)
    after_reads = _files(root)
    code = _main(root, "approve", "--ticket", T)
    after = _files(root)
    _out_of_rounds_block(root)
    ledger = review_ledger.ledger_path(str(root), T)
    staged = _files(root)
    rejected = _main(root, "auto-reject", "--ticket", T)
    last = _files(root)
    capsys.readouterr()

    added = sorted(set(after) - set(before))
    # The receipt is what crew_ticket.approve writes for every route: the
    # approval and, on a ticket's first approval, the scope ramp's list.
    receipt = sorted([crew_ticket.approval_path(str(root), T),
                      os.path.join(crew_ticket.state_dir(str(root)), "scope-tickets.json")])
    changed = sorted(p for p in set(staged) | set(last) if staged.get(p) != last.get(p))
    assert (_usage_subcommands() - {run[0] for run in READ_ONLY_RUNS}, after_reads == before,
            code, added, {p: v for p, v in after.items() if p in before} == before,
            rejected, changed) == (
        set(WRITERS), True, 0, receipt, True, 0, [ledger])


def test_approve_refused_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root = _repo(tmp_path, approval="human", risk="low")
    before = _files(root)

    code = _main(root, "approve", "--ticket", T)
    capsys.readouterr()

    assert (code, _files(root) == before) == (2, True)


def test_command_states_the_approve_exception():
    flat = " ".join(_command_text().split())

    assert ("Nothing here approves" in flat,
            "only the human types `/crew:approve <ticket>`" in flat,
            "nothing approves except section 3's `approve`, under the approval policy" in flat,
            "`plan-approval` and `open-questions` are a person unless section 3's policy "
            "allows" in flat) == (False, False, True, True)


def test_module_docstring_states_the_approve_exception():
    doc = crew_autopilot.__doc__
    usage = doc.split("\n\n")[1]
    flat = " ".join(doc.split())

    assert ("never approves" in flat,
            "Read-only except `approve` and `auto-reject`, each only when its policy allows "
            "under the configured setting; it never accepts a review." in flat,
            "crew_autopilot.py approve --root . --ticket <id>" in usage,
            "crew_autopilot.py questions-check --root . --ticket <id>" in usage) == (
        False, True, True, True)


# Review round 3's BLOCK: every statement of the exception names what approve
# writes -- what crew_ticket.approve writes for every route -- never "only the
# approval receipt". Each file is where the exception is stated.
APPROVE_WRITES = ("`approval.json`", "`scope-tickets.json`", "on a ticket's first approval",
                  "NEEDS_REPLAN -> IN_REVIEW")
UNDERSTATED = ("writes only the approval receipt", "receipt and nothing else",
               "The one write this module makes")


def _exception_statements():
    def read(*parts):
        with open(os.path.join(*parts), encoding="utf-8") as handle:
            return handle.read()
    return {"crew_autopilot.py docstring": crew_autopilot.__doc__,
            "crew_autopilot.approve docstring": crew_autopilot.approve.__doc__,
            "commands/autopilot.md": _command_text(),
            "README.md": read(_ROOT, "README.md"),
            "CONFIG.md": read(_ROOT, "CONFIG.md"),
            "daily-workflow-scope.md": read(_REPO, "docs", "guides", "crew", "src",
                                            "daily-workflow-scope.md")}


def test_every_statement_of_the_exception_names_what_approve_writes():
    missing = {name: [w for w in APPROVE_WRITES if w not in " ".join(text.split())]
               for name, text in _exception_statements().items()}

    assert {name: gaps for name, gaps in missing.items() if gaps} == {}


def test_no_statement_of_the_exception_says_approve_writes_only_the_receipt():
    found = {name: [w for w in UNDERSTATED if w in " ".join(text.split())]
             for name, text in _exception_statements().items()}

    assert {name: hits for name, hits in found.items() if hits} == {}


def test_approve_of_a_successor_plan_writes_the_receipt_and_moves_the_ledger(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root = _needs_replan_with_a_successor_plan(tmp_path)
    ledger = review_ledger.ledger_path(str(root), T)
    before = _files(root)

    code = _main(root, "approve", "--ticket", T)
    after = _files(root)
    capsys.readouterr()

    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    assert (code, changed, review_ledger.status(str(root), T)["state"]) == (
        0, sorted([crew_ticket.approval_path(str(root), T), ledger]), review_ledger.IN_REVIEW)


def test_readme_phase_table_names_the_policy_route_at_approve():
    with open(os.path.join(_ROOT, "README.md"), encoding="utf-8") as handle:
        rows = [line for line in handle.read().splitlines()
                if line.startswith("| approval not accepted")]

    assert (len(rows), "`autopilot.approval`" in rows[0],
            "`crew_autopilot.py approve`" in rows[0], "`/crew:approve <id>`" in rows[0],
            "`scope.allowCliApproval: true`" in rows[0]) == (1, True, True, True, True)


def test_command_states_questions_file_shape():
    flat = " ".join(_command_text().split())
    required = ("`## Q<n>: <question>`", "`Research:`", "2-4 `### Option <id>`",
                f"`{crew_autopilot.RECOMMENDED}`", "`Cost:`",
                "`taken: Option <id> by autopilot (<policy>)`")

    assert [literal for literal in required if literal not in flat] == []


def test_verify_maps_autopilot_command_to_policy_suite():
    import fnmatch  # pylint: disable=import-outside-toplevel
    with open(os.path.join(_REPO, ".crew", "verify.json"), encoding="utf-8") as handle:
        rules = json.load(handle)["rules"]
    target = "plugin/crew/commands/autopilot.md"

    runs = [" ".join(rule.get("run") or []) for rule in rules
            if any(fnmatch.fnmatchcase(target, path) for path in rule.get("paths") or [])]

    assert any("test_crew_autopilot_policy.py" in run for run in runs), runs


# --- step 7: review round 4's three FIXes ---------------------------------------
# An unreadable `.crew/config.json`, or an `autopilot` value that is not an
# object, is could-not-tell: both policies read `unknown`, never the default
# `risk`. Absence is known and still reads the defaults.

def _raw_config(root, text):
    _write(root / ".crew" / "config.json", text)


@pytest.mark.parametrize("text", ["{bad", "[]"])
def test_settings_unreadable_config_reads_policies_unknown(tmp_path, text):
    root = _repo(tmp_path, approval="self", questions="self")
    _raw_config(root, text)

    got = crew_autopilot.settings(str(root))

    assert (got["approval"], got["questions"], got["mode"],
            any(".crew/config.json" in w and "could not" in w for w in got["warnings"])) == (
        "unknown", "unknown", "off", True)


@pytest.mark.parametrize("value", [["x"], "self", 1, True])
def test_settings_non_object_autopilot_reads_policies_unknown(tmp_path, value):
    root = _repo(tmp_path)
    _raw_config(root, json.dumps({"scope": {"allowCliApproval": True}, "autopilot": value}))

    got = crew_autopilot.settings(str(root))

    assert (got["approval"], got["questions"], got["mode"],
            any("not an object" in w and repr(value) in w for w in got["warnings"])) == (
        "unknown", "unknown", "off", True)


def test_question_policy_stops_when_config_unreadable(tmp_path):
    root = _repo(tmp_path, questions="self", risk="low")
    _raw_config(root, "{bad")

    got = crew_autopilot.question_policy(str(root), T)

    assert (got["action"], got["policy"], "could not tell" in got["reason"]) == (
        "stop", "unknown", True)


def test_question_policy_stops_when_autopilot_not_an_object(tmp_path):
    root = _repo(tmp_path, risk="low")
    _raw_config(root, json.dumps({"scope": {"allowCliApproval": True}, "autopilot": ["x"]}))

    got = crew_autopilot.question_policy(str(root), T)

    assert (got["action"], got["policy"], "could not tell" in got["reason"]) == (
        "stop", "unknown", True)


def test_approval_policy_refuses_when_autopilot_not_an_object(tmp_path):
    root = _repo(tmp_path, risk="low")
    _raw_config(root, json.dumps({"scope": {"allowCliApproval": True}, "autopilot": ["x"]}))

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], got["policy"], "could not tell" in got["reason"]) == (
        False, "unknown", True)


def test_approval_policy_refuses_an_unknown_policy_before_the_risk_branch(tmp_path,
                                                                          monkeypatch):
    root = _repo(tmp_path, risk="low")
    monkeypatch.setattr(crew_autopilot, "settings", lambda _root: {
        "mode": "off", "armed": False, "maxPhases": 12, "approval": "unknown",
        "questions": "unknown", "saw": None,
        "warnings": ["autopilot.approval could not be told (a test)"]})

    got = crew_autopilot.approval_policy(str(root), T)

    assert (got["allow"], got["policy"]) == (False, "unknown")


@pytest.mark.parametrize("config", [None, {"scope": {"allowCliApproval": True}},
                                    {"scope": {"allowCliApproval": True}, "autopilot": None}])
def test_settings_absent_config_or_block_reads_defaults(tmp_path, config):
    root = _repo(tmp_path)
    path = root / ".crew" / "config.json"
    if config is None:
        path.unlink()
    else:
        _raw_config(root, json.dumps(config))

    got = crew_autopilot.settings(str(root))

    assert (got["approval"], got["questions"], got["warnings"]) == ("risk", "risk", [])


@pytest.mark.parametrize("approval,questions", [("self", "human"), ("human", "self")])
def test_settings_cli_text_prints_both_policies(tmp_path, approval, questions):
    root = _repo(tmp_path, approval=approval, questions=questions)

    out = _cli(root, "settings").stdout

    assert out.splitlines()[1] == f"approval={approval} questions={questions}"


@pytest.mark.parametrize("approval,questions", [("self", "human"), ("human", "self")])
def test_settings_cli_json_prints_both_policies(tmp_path, approval, questions):
    root = _repo(tmp_path, approval=approval, questions=questions)

    got = json.loads(_cli(root, "settings", "--json").stdout)

    assert (got["approval"], got["questions"]) == (approval, questions)
