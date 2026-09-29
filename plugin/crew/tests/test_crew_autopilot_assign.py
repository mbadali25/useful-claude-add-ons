"""T-0019: `/crew:autopilot assign` -- free-text work becomes one ticket.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_assign.py -q

`crew_ticket.assign` checks a staging file under `.work/autopilot/` (and that
autopilot is armed), then calls `mint` exactly once. The assigned ticket is
then approved under `autopilot.approval` like any other ticket (the owner's
2026-09-26 "Follow the policy"): the `origin:` line is provenance only, and
T-0010's `crew_autopilot.py approve` is the one route. Every repository is
built under tmp_path; nothing touches the real one or ~/.claude.
`sabotage_autopilot.py`'s ASSIGN_MUTATIONS prove these can fail.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

import context  # pylint: disable=unused-import
import crew_autopilot
import crew_ticket
import pytest
import review_ledger
from scope_fixtures import PLAN, SPEC, make_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_TICKET_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_ticket.py")
_COMMAND = os.path.join(_ROOT, "commands", "autopilot.md")
T = "T-0001"
POLICIES = ("human", "self", "risk")

STAGED = """title: add a dry-run flag
risk: {risk}

## Ask
add a --dry-run flag to crew_ticket.py mint, "quoted" and $literal

## Options
1. A flag on the CLI (recommended).
2. An environment variable.

## Recommendation
Option 1: one flag, one test.

## Open questions
{questions}
"""


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _config(root, approval="risk", questions="risk", allow=True, armed=True):
    _write(root / ".crew" / "config.json", json.dumps({
        "scope": {"mode": "off", "allowCliApproval": allow},
        "autopilot": {"mode": "plan" if armed else "off", "approval": approval,
                      "questions": questions},
        "tracker": "files"}))


def _repo(tmp_path, name="r", **config):
    root = make_repo(tmp_path, mode="off", name=name)
    _config(root, **config)
    return root


def _stage(root, text=None, name="assign-1.md", risk="low", questions="none"):
    path = root / ".work" / "autopilot" / name
    _write(path, text if text is not None else STAGED.format(risk=risk, questions=questions))
    return path


def _tickets(root):
    folder = root / ".work" / "tickets"
    return sorted(os.listdir(folder)) if folder.is_dir() else []


def _index(root):
    path = root / ".work" / "INDEX.md"
    return path.read_bytes() if path.exists() else None


def _state_files(root):
    """Every file under `<git-common-dir>/crew/`, as a digest map."""
    found = {}
    base = os.path.join(crew_ticket.common_dir(str(root)), "crew")
    for where, _dirs, names in os.walk(base):
        for name in names:
            with open(os.path.join(where, name), "rb") as handle:
                found[os.path.join(where, name)] = hashlib.sha256(handle.read()).hexdigest()
    return found


# --- step 2: the staging check, then mint once --------------------------------

def test_assign_refuses_when_not_armed(tmp_path):
    root = _repo(tmp_path, armed=False)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.assign(str(root), str(_stage(root)))

    assert (_tickets(root), _index(root), "autopilot" in str(err.value)) == ([], None, True)


def _drop(text, what):
    if what == "title":
        return re.sub(r"^title:.*\n", "", text, flags=re.MULTILINE)
    heading = {"ask": "Ask", "options": "Options", "recommendation": "Recommendation",
               "open questions": "Open questions"}[what]
    return re.sub(rf"^## {heading}\n(?:(?!## ).*\n)*", "", text, flags=re.MULTILINE)


@pytest.mark.parametrize("what", ["ask", "options", "recommendation", "open questions",
                                  "title"])
def test_assign_refuses_missing_section_and_mints_nothing(tmp_path, what):
    root = _repo(tmp_path)
    text = _drop(STAGED.format(risk="low", questions="none"), what)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.assign(str(root), str(_stage(root, text)))

    assert (_tickets(root), _index(root), what in str(err.value).lower()) == ([], None, True)


def test_assign_refuses_empty_ask(tmp_path):
    root = _repo(tmp_path)
    text = STAGED.format(risk="low", questions="none").replace(
        'add a --dry-run flag to crew_ticket.py mint, "quoted" and $literal\n', "\n")

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.assign(str(root), str(_stage(root, text)))

    assert (_tickets(root), _index(root), "ask" in str(err.value).lower()) == ([], None, True)


def _outside(root, tmp_path, where):
    if where == "/tmp/x.md":
        path = tmp_path / "x.md"
        _write(path, STAGED.format(risk="low", questions="none"))
        return str(path)
    if where == "ticket-folder":
        path = root / ".work" / "tickets" / "T-1" / "direction.md"
        _write(path, STAGED.format(risk="low", questions="none"))
        return str(path)
    if where == "dotdot":
        _write(root / ".work" / "x.md", STAGED.format(risk="low", questions="none"))
        os.makedirs(root / ".work" / "autopilot", exist_ok=True)
        return str(root / ".work" / "autopilot" / ".." / "x.md")
    target = tmp_path / "elsewhere.md"
    _write(target, STAGED.format(risk="low", questions="none"))
    link = root / ".work" / "autopilot" / "link.md"
    os.makedirs(link.parent, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")
    return str(link)


@pytest.mark.parametrize("where", ["/tmp/x.md", "ticket-folder", "dotdot", "symlink"])
def test_assign_refuses_direction_file_outside_staging(tmp_path, where):
    root = _repo(tmp_path)
    path = _outside(root, tmp_path, where)
    before = _tickets(root)

    with pytest.raises(crew_ticket.TicketError) as err:
        crew_ticket.assign(str(root), path)

    assert (_tickets(root), _index(root), ".work/autopilot" in str(err.value)) == (
        before, None, True)


def test_assign_unknown_risk_is_high(tmp_path):
    root = _repo(tmp_path)

    got = crew_ticket.assign(str(root), str(_stage(root, risk="extreme")))
    text = (root / ".work" / "tickets" / T / "direction.md").read_text(encoding="utf-8")

    assert (got["risk"], "risk: high\n" in text, got["warnings"]) == (
        "high", True, ["risk: 'extreme' is not low|med|high; written as high"])


def test_assign_mints_exactly_one(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    real, calls = crew_ticket.mint, []

    def counting(*args, **kwargs):
        calls.append(kwargs.get("status"))
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", counting)

    crew_ticket.assign(str(root), str(_stage(root)))

    assert (calls, _tickets(root), len(_index(root).decode("utf-8").splitlines())) == (
        ["ready"], [T], 1)


def test_assign_direction_carries_origin(tmp_path):
    root = _repo(tmp_path)
    staged = STAGED.format(risk="med", questions="none")

    crew_ticket.assign(str(root), str(_stage(root, staged)))
    lines = (root / ".work" / "tickets" / T / "direction.md").read_text(
        encoding="utf-8").splitlines()
    sections = staged[staged.index("## Ask"):]

    assert (lines[:5], "\n".join(lines[5:]) + "\n") == (
        [f"# {T} direction", crew_ticket.ORIGIN_ASSIGN, "title: add a dry-run flag",
         "risk: med", ""], sections)


def test_assign_never_writes_a_receipt(tmp_path):
    root = _repo(tmp_path, approval="self")
    before = _state_files(root)

    crew_ticket.assign(str(root), str(_stage(root)))

    assert (crew_ticket.status(str(root), T)["status"], _state_files(root) == before) == (
        "none", True)


def test_assign_then_next_phase_is_spec(tmp_path):
    root = _repo(tmp_path)

    got = crew_ticket.assign(str(root), str(_stage(root)))
    crew_ticket.activate(str(root), got["ticket"])
    step = crew_autopilot.next_phase(str(root), got["ticket"])

    assert (step["phase"], step["stop"]) == ("spec", False), step["reason"]


def test_assign_with_open_question_next_phase_is_open_questions(tmp_path):
    root = _repo(tmp_path)

    got = crew_ticket.assign(str(root), str(_stage(root, questions="- which flag name?")))
    crew_ticket.activate(str(root), got["ticket"])
    step = crew_autopilot.next_phase(str(root), got["ticket"])

    assert (step["phase"], step["stop"]) == ("open-questions", True), step["reason"]


def _cli(root, *args):
    return subprocess.run([sys.executable, _TICKET_SCRIPT, *args], capture_output=True,
                          text=True, check=False, cwd=str(root), stdin=subprocess.DEVNULL)


def test_assign_cli_prints_ticket_and_risk(tmp_path):
    root = _repo(tmp_path)
    _stage(root, risk="bogus")

    done = _cli(root, "assign", "--root", ".", "--direction-file",
                ".work/autopilot/assign-1.md")

    assert (done.returncode, done.stdout) == (
        0, (f"ticket={T} risk=high\nwarning: risk: 'bogus' is not low|med|high; "
            "written as high\n")), done.stderr


def test_assign_cli_refusal_mints_nothing(tmp_path):
    root = _repo(tmp_path, armed=False)
    _stage(root)

    done = _cli(root, "assign", "--root", ".", "--direction-file",
                ".work/autopilot/assign-1.md")

    assert (done.returncode, done.stdout.startswith("refused: "), _tickets(root)) == (
        1, True, [])


def test_assign_cli_takes_no_title():
    with pytest.raises(SystemExit):
        crew_ticket.main(["assign", "--root", ".", "--title", "x"])


# --- step 3: the approve phase is T-0010's, for an assigned ticket -------------

def _spec_text(ticket, risk):
    body = SPEC.format(ticket=ticket, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    header = "status: spec" + (f"   risk: {risk}" if risk else "")
    return f"{first} title          {header}\n{rest}"


def _assigned(tmp_path, name="r", risk="low", origin=True, **config):
    """An assigned ticket carried to the approve phase: spec and plan valid,
    no open question, the ticket active. `origin=False` strips the origin
    line, which is the only difference from a ticket brainstorm minted."""
    root = _repo(tmp_path, name=name, **config)
    got = crew_ticket.assign(str(root), str(_stage(root, risk=risk or "high")))
    folder = root / ".work" / "tickets" / got["ticket"]
    if not origin:
        path = folder / "direction.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            crew_ticket.ORIGIN_ASSIGN + "\n", ""), encoding="utf-8")
    _write(folder / "spec.md", _spec_text(got["ticket"], risk))
    _write(folder / "plan.md", PLAN.format(files="src/app.py"))
    crew_ticket.activate(str(root), got["ticket"])
    return root, got["ticket"]


def _approve(root, ticket, capsys):
    code = crew_autopilot.main(["approve", "--root", str(root), "--ticket", ticket])
    return code, capsys.readouterr().out


def _receipt(root, ticket):
    receipt, state = crew_ticket.read_approval(str(root), ticket)
    return receipt if state == "ok" else None


def test_assigned_ticket_reaches_approve(tmp_path):
    root, ticket = _assigned(tmp_path, approval="human")

    step = crew_autopilot.next_phase(str(root), ticket)

    assert (step["phase"], step["stop"]) == ("approve", True), step["reason"]


def test_assigned_ticket_self_approved_under_self(tmp_path, capsys):
    root, ticket = _assigned(tmp_path, approval="self", risk="high")

    code, out = _approve(root, ticket, capsys)

    assert (code, out.strip(), (_receipt(root, ticket) or {}).get("approved_via")) == (
        0, f"self-approved {ticket} under approval=self, risk=high", "autopilot")


def test_assigned_ticket_self_approved_under_risk_low(tmp_path, capsys):
    root, ticket = _assigned(tmp_path, approval="risk", risk="low")

    code, out = _approve(root, ticket, capsys)

    assert (code, out.strip(), (_receipt(root, ticket) or {}).get("approved_via")) == (
        0, f"self-approved {ticket} under approval=risk, risk=low", "autopilot")


def _refused(root, ticket, capsys):
    code, out = _approve(root, ticket, capsys)
    return (code != 0, _receipt(root, ticket), f"/crew:approve {ticket}" in out)


def test_assigned_ticket_refused_under_human(tmp_path, capsys):
    root, ticket = _assigned(tmp_path, approval="human", risk="low")

    assert _refused(root, ticket, capsys) == (True, None, True)


@pytest.mark.parametrize("risk", ["med", "high", None])
def test_assigned_ticket_refused_under_risk_not_low(tmp_path, capsys, risk):
    root, ticket = _assigned(tmp_path, approval="risk", risk=risk)

    assert _refused(root, ticket, capsys) == (True, None, True)


def test_assigned_ticket_refused_without_allow_cli_approval(tmp_path, capsys):
    root, ticket = _assigned(tmp_path, approval="self", allow=False)

    assert _refused(root, ticket, capsys) == (True, None, True)


def test_assigned_ticket_refused_when_unarmed(tmp_path, capsys):
    root, ticket = _assigned(tmp_path, approval="self")
    _config(root, approval="self", armed=False)

    assert _refused(root, ticket, capsys) == (True, None, True)


def test_assigned_ticket_refused_on_unreadable_ledger(tmp_path, capsys):
    root, ticket = _assigned(tmp_path, approval="self")
    path = review_ledger.ledger_path(str(root), ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, "{not json")

    assert _refused(root, ticket, capsys) == (True, None, True)


@pytest.mark.parametrize("policy", POLICIES)
def test_origin_line_changes_no_policy(tmp_path, policy):
    with_origin, ticket = _assigned(tmp_path, name="a", approval=policy, questions=policy)
    without, other = _assigned(tmp_path, name="b", approval=policy, questions=policy,
                               origin=False)

    assert ((ticket, crew_autopilot.approval_policy(str(with_origin), ticket),
             crew_autopilot.question_policy(str(with_origin), ticket)) ==
            (other, crew_autopilot.approval_policy(str(without), other),
             crew_autopilot.question_policy(str(without), other)))


def test_assigned_invalid_plan_never_reaches_approve(tmp_path):
    root, ticket = _assigned(tmp_path, approval="self")
    _write(root / ".work" / "tickets" / ticket / "plan.md", "# Plan\n\nno steps\n")

    step = crew_autopilot.next_phase(str(root), ticket)

    assert (step["phase"], step["stop"]) == ("plan", True), step["reason"]


def test_assigned_open_question_under_human_questions_stops(tmp_path):
    root, ticket = _assigned(tmp_path, approval="self", questions="human")
    path = root / ".work" / "tickets" / ticket / "direction.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "## Open questions\nnone\n", "## Open questions\n- which flag name?\n"),
        encoding="utf-8")

    step = crew_autopilot.next_phase(str(root), ticket)

    assert ((step["phase"], step["stop"]),
            crew_autopilot.question_policy(str(root), ticket)["action"]) == (
        ("open-questions", True), "stop")


def test_assign_is_not_a_crew_autopilot_subparser(tmp_path, capsys):
    root = _repo(tmp_path)
    _stage(root)

    code = crew_autopilot.main(["assign", "--root", str(root), "--direction-file",
                                ".work/autopilot/assign-1.md"])
    capsys.readouterr()

    assert (code, _tickets(root), _index(root)) == (2, [], None)


# --- step 4: the router and the command's assign lines --------------------------

def test_route_first_assign_is_available(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), "assign")

    assert (got["sub"], got["stop"], got["reason"]) == ("assign", False, "")


def test_route_args_assign_with_text_refuses(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), "assign fix the parser")

    assert (got["sub"], got["stop"], got["ticket"],
            "route --root . --first assign" in got["reason"]) == ("assign", True, "", True)


def test_route_args_assign_with_a_ticket_id_refuses_too(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), "assign T-0019")

    assert (got["stop"], got["ticket"]) == (True, "")


def test_route_args_run_assign_still_drives_a_ticket_folder_named_assign(tmp_path):
    root = make_repo(tmp_path, mode="off")
    (root / ".work" / "tickets" / "assign").mkdir(parents=True)

    got = crew_autopilot.route_args(str(root), "run assign")

    assert (got["sub"], got["stop"], got["ticket"]) == ("run", False, "assign")


def _command():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def test_assign_lines_at_most_4():
    lines = _command().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("`assign <text>`"))

    assert (lines[start - 1], len(lines) - (start - 1) <= 4, len(lines) <= 114) == (
        "", True, True)


def test_assign_section_never_puts_arguments_on_a_shell_line():
    lines = _command().splitlines()
    both = [line for line in lines if "$ARGUMENTS" in line and "assign" in line]
    shell = [line for line in lines if "crew_ticket.py assign" in line]

    assert (both, len(shell), all(
        "crew_ticket.py assign --root . --direction-file .work/autopilot/assign-<n>.md" in line
        for line in shell)) == ([], 1, True)


def test_assign_section_skips_the_route_shell_line():
    flat = " ".join(_command().split())

    assert ("If the first word is exactly `assign`, run `crew_autopilot.py route --root . "
            "--first assign` in place of this shell line" in flat,
            "`sub=assign`: the assign lines" in flat) == (True, True)


def test_assign_section_names_the_stop():
    flat = " ".join(_command().split())

    assert ("Anything else - `refused:`, no output, a traceback - print it and stop: nothing "
            "was minted" in flat, "`ticket=<id>`: announce `assigned <id>` and run sections "
            "2 to 5" in flat) == (True, True)


def test_assign_sabotage_is_registered_with_sabotage_py():
    import sabotage  # pylint: disable=import-outside-toplevel
    from sabotage_autopilot import ASSIGN_MUTATIONS  # pylint: disable=import-outside-toplevel

    missing = [m[0] for m in ASSIGN_MUTATIONS if m not in sabotage.MUTATIONS]

    assert (len(ASSIGN_MUTATIONS), missing) == (17, [])
