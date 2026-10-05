"""T-0053: autopilot sleep mode, slice 1 -- a schedule overlays `approval`
and `questions`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q

`autopilot.sleep.schedule` (`HH:MM-HH:MM`, machine local time) names a
nightly window. Inside it, `autopilot.sleep.approval` and
`autopilot.sleep.questions` replace the day values of `autopilot.approval`
and `autopilot.questions`, re-resolved from the clock on every policy read.
Anything that cannot be told leaves the day values in force with a warning.
The clock is `crew_sleep.now`, monkeypatched in-process here: there is no
environment variable or flag that moves it. Every repository is built under
tmp_path; nothing touches the real one or ~/.claude.
"""
import datetime
import json
import os
import stat
import time

import context  # pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_sleep
import crew_sleep
import crew_ticket
import pytest
from scope_fixtures import PLAN, SPEC, make_repo

T = "T-1"
NIGHT = datetime.datetime(2026, 10, 4, 23, 0)
DAY = datetime.datetime(2026, 10, 4, 12, 0)
MISSING = object()


# --- fixtures ----------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _spec_text(risk):
    body = SPEC.format(ticket=T, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    return f"{first} title          status: spec   risk: {risk}\n{rest}"


def _repo(tmp_path, sleep=MISSING, approval="risk", questions="risk", allow=True,
          risk="high", armed=True):
    """One active ticket; `sleep` is written verbatim as `autopilot.sleep`."""
    root = make_repo(tmp_path, mode="off")
    block = {"mode": "plan" if armed else "off", "approval": approval,
             "questions": questions}
    if sleep is not MISSING:
        block["sleep"] = sleep
    config = {"scope": {"mode": "off", "allowCliApproval": allow}, "autopilot": block}
    _write(root / ".crew" / "config.json", json.dumps(config))
    folder = root / ".work" / "tickets" / T
    _write(folder / "direction.md", "go\n")
    _write(folder / "spec.md", _spec_text(risk))
    _write(folder / "plan.md", PLAN.format(files="src/app.py"))
    _write(root / ".work" / "INDEX.md", f"{T} | ready | {risk} | r | title\n")
    crew_ticket.activate(str(root), T)
    return root


def _night(schedule="22:00-07:00", approval="self", questions="self", **extra):
    return dict({"schedule": schedule, "approval": approval, "questions": questions}, **extra)


@pytest.fixture(name="clock")
def _clock(monkeypatch):
    """`clock(dt)` sets what `crew_sleep.now` returns; NIGHT by default."""
    when = {"now": NIGHT}
    monkeypatch.setattr(crew_sleep, "now", lambda: when["now"])

    def setter(value):
        when["now"] = value
    return setter


def _at(hour, minute):
    return datetime.datetime(2026, 10, 4, hour, minute)


def _receipt(root):
    receipt, state = crew_ticket.read_approval(str(root), T)
    return receipt if state == "ok" else None


# --- crew_sleep: the grammar, the window, the resolver ------------------------

@pytest.mark.parametrize("value,ok", [
    ("22:00-07:00", True), ("00:00-23:59", True), ("09:30-17:00", True),
    ("7:00-22:00", False), ("24:00-07:00", False), ("22:60-07:00", False),
    ("22:00-22:00", False), ("22:00 - 07:00", False), ("22:00-07:00 ", False),
    ("22:00", False), ("", False), (["22:00", "07:00"], False), (True, False),
    ("2200", False), ("٢٢:00-07:00", False), ("22:00-07:00\n", False),
])
def test_parse_schedule(value, ok):
    start, end, reason = crew_sleep.parse_schedule(value)

    assert ((start is not None, end is not None, reason == "") == (ok, ok, ok),
            bool(reason) != ok) == (True, True)


def test_parse_schedule_minutes():
    assert crew_sleep.parse_schedule("22:30-07:05") == (22 * 60 + 30, 7 * 60 + 5, "")


@pytest.mark.parametrize("schedule,hour,minute,inside", [
    ("22:00-07:00", 21, 59, False), ("22:00-07:00", 22, 0, True),
    ("22:00-07:00", 23, 59, True), ("22:00-07:00", 0, 0, True),
    ("22:00-07:00", 6, 59, True), ("22:00-07:00", 7, 0, False),
    ("09:00-17:00", 8, 59, False), ("09:00-17:00", 9, 0, True),
    ("09:00-17:00", 16, 59, True), ("09:00-17:00", 17, 0, False),
])
def test_in_window(schedule, hour, minute, inside):
    start, end, _ = crew_sleep.parse_schedule(schedule)

    assert crew_sleep.in_window(start, end, hour * 60 + minute) is inside


@pytest.mark.parametrize("block,now,state", [
    ({"schedule": None}, NIGHT, "off"),
    ({}, NIGHT, "off"),
    ({"schedule": "22:00-07:00"}, NIGHT, "asleep"),
    ({"schedule": "22:00-07:00"}, DAY, "awake"),
    ({"schedule": "22:00"}, NIGHT, "unknown"),
    ("22:00-07:00", NIGHT, "unknown"),
    (["22:00-07:00"], NIGHT, "unknown"),
    ({"schedule": "22:00-07:00"}, "23:00", "unknown"),
    ({"schedule": "22:00-07:00"}, None, "unknown"),
])
def test_resolve_states(block, now, state):
    got = crew_sleep.resolve(block, now, crew_autopilot.POLICIES)

    assert (got["state"], bool(got["warnings"])) == (state, state == "unknown")


def test_resolve_reads_a_bad_override_as_strictest_and_keeps_the_other():
    got = crew_sleep.resolve(_night(approval="always"), NIGHT, crew_autopilot.POLICIES)

    assert (got["overrides"], any("autopilot.sleep.approval" in w for w in got["warnings"])) == (
        {"approval": crew_sleep.STRICTEST, "questions": "self"}, True)


@pytest.mark.parametrize("key", ["reviewPolicy", "notifyHold"])  # L-0654 landed `deploy`
def test_resolve_names_a_key_this_version_does_not_have(key):
    got = crew_sleep.resolve(_night(**{key: "x"}), NIGHT, crew_autopilot.POLICIES)

    assert (got["state"], got["overrides"],
            [w for w in got["warnings"] if f"autopilot.sleep.{key}" in w
             and "not available in this crew version" in w] != []) == (
        "asleep", {"approval": "self", "questions": "self"}, True)


def test_crew_sleep_opens_nothing_for_writing():
    path = os.path.join(context._ROOT, "hooks", "scripts", "crew_sleep.py")  # pylint: disable=protected-access
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    assert [w for w in ('"w"', "'w'", '"a"', "'a'", "write", "os.replace", "unlink",
                        "os.environ", "getenv", "sys.argv", "import os") if w in text] == []


# --- must-allow ----------------------------------------------------------------

def test_asleep_self_approves_a_high_risk_plan(tmp_path, clock, capsys):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")

    got = crew_autopilot.approval_policy(str(root), T)
    code = crew_autopilot.main(["approve", "--root", str(root), "--ticket", T])
    out = capsys.readouterr().out.strip()

    suffix = " (asleep 22:00-07:00; day value risk)"
    assert (got["allow"], got["policy"], got["reason"].endswith(suffix), code, out,
            _receipt(root)["approved_by"]) == (
        True, "self", True, 0, f"self-approved {T} under approval=self, risk=high{suffix}",
        "autopilot:self")


def test_asleep_takes_the_recommendation(tmp_path, clock):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")

    got = crew_autopilot.question_policy(str(root), T)

    assert (got["action"], got["policy"],
            got["reason"].endswith(" (asleep 22:00-07:00; day value risk)")) == (
        "take", "self", True)


# --- must-block: each leaves the day value in force ----------------------------

def _day_values(root):
    conf = crew_autopilot.settings(str(root))
    return (crew_autopilot.approval_policy(str(root), T)["allow"],
            crew_autopilot.question_policy(str(root), T)["action"],
            conf["approval"], conf["questions"], conf["sleep"]["state"], conf["warnings"])


def test_outside_the_window_the_day_values_apply(tmp_path, clock):
    clock(DAY)
    got = _day_values(_repo(tmp_path, sleep=_night()))

    assert got == (False, "stop", "risk", "risk", "awake", [])


def test_a_null_schedule_is_off_without_a_warning(tmp_path, clock):
    clock(NIGHT)
    got = _day_values(_repo(tmp_path, sleep=_night(schedule=None)))

    assert got == (False, "stop", "risk", "risk", "off", [])


@pytest.mark.parametrize("schedule", ["22:00", "22:00-22:00", 2200, ["22:00", "07:00"]])
def test_a_malformed_schedule_is_unknown_and_warns(tmp_path, clock, schedule):
    clock(NIGHT)
    got = _day_values(_repo(tmp_path, sleep=_night(schedule=schedule)))

    assert (got[:5], any("autopilot.sleep.schedule" in w for w in got[5])) == (
        (False, "stop", "risk", "risk", "unknown"), True)


@pytest.mark.parametrize("value", ["Human", "always", True, ["self"], "Self", 1])
def test_a_bad_night_value_reads_strictest_while_asleep(tmp_path, clock, value):
    """Landing decision (owner-consistent with N7): a non-null night value
    that is not a policy is an override crew cannot read, so it counts as
    human, the strictest, instead of keeping the looser day value."""
    clock(NIGHT)
    got = _day_values(_repo(tmp_path, sleep=_night(approval=value)))

    assert (got[:5], any("autopilot.sleep.approval" in w and "counts as human" in w
                         for w in got[5])) == ((False, "take", "human", "self", "asleep"), True)


@pytest.mark.parametrize("value", ["Human", "always", True, 1])
def test_a_bad_night_value_reads_strictest_while_unknown(tmp_path, clock, value):
    clock(NIGHT)
    got = _day_values(_repo(tmp_path, approval="self", questions="self",
                            sleep=_night(schedule="22", approval=value, questions=None)))

    assert (got[:5], any("autopilot.sleep.approval" in w and "counts as human" in w
                         for w in got[5])) == ((False, "take", "human", "self", "unknown"), True)


def test_a_bad_night_value_is_ignored_while_awake(tmp_path, clock):
    """Must-allow: outside the window no night value applies, readable or not."""
    clock(DAY)
    got = _day_values(_repo(tmp_path, sleep=_night(approval="Human")))

    assert got[2:5] == ("risk", "risk", "awake")


@pytest.mark.parametrize("value", ["22:00-07:00", ["22:00-07:00"], 1, True])
def test_a_sleep_value_that_is_not_an_object_is_unknown(tmp_path, clock, value):
    """Review round 2 (N7, owner decision): both policies read human."""
    clock(NIGHT)
    got = _day_values(_repo(tmp_path, sleep=value))

    assert (got[:5], any("autopilot.sleep " in w for w in got[5])) == (
        (False, "stop", "human", "human", "unknown"), True)


@pytest.mark.parametrize("allow", [False, "true", 1, None])
def test_asleep_still_needs_allow_cli_approval_exactly_true(tmp_path, clock, allow):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), allow=allow)

    got = crew_autopilot.approval_policy(str(root), T)
    code, _text = crew_autopilot.approve(str(root), T)

    assert (got["allow"], got["policy"], code, _receipt(root)) == (False, "self", 2, None)


def test_an_unreadable_config_reads_unknown_and_never_reads_sleep(tmp_path, clock,
                                                                 monkeypatch):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night())
    _write(root / ".crew" / "config.json", "{not json")

    def boom(*_args):
        raise AssertionError("sleep was read")
    monkeypatch.setattr(crew_sleep, "resolve", boom)
    conf = crew_autopilot.settings(str(root))

    assert (conf["approval"], conf["questions"], conf["sleep"]["state"],
            crew_autopilot.approval_policy(str(root), T)["allow"],
            crew_autopilot.question_policy(str(root), T)["action"]) == (
        "unknown", "unknown", "unknown", False, "stop")


def test_a_raising_resolve_is_unknown_with_day_values(tmp_path, clock, monkeypatch):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night())

    def boom(*_args):
        raise RuntimeError("clock")
    monkeypatch.setattr(crew_sleep, "resolve", boom)
    got = _day_values(root)

    assert (got[:5], any("autopilot.sleep" in w and "RuntimeError" in w for w in got[5])) == (
        (False, "stop", "risk", "risk", "unknown"), True)


def test_a_raising_clock_is_unknown_with_day_values(tmp_path, monkeypatch):
    def boom():
        raise OSError("no clock")
    monkeypatch.setattr(crew_sleep, "now", boom)
    got = _day_values(_repo(tmp_path, sleep=_night()))

    assert (got[:5], any("autopilot.sleep" in w for w in got[5])) == (
        (False, "stop", "risk", "risk", "unknown"), True)


@pytest.mark.parametrize("key", ["reviewPolicy"])  # L-0654 landed `deploy`
def test_an_unknown_sleep_key_has_no_other_effect(tmp_path, clock, key):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(approval=None, questions=None, **{key: "self"}))

    got = _day_values(root)

    assert (got[:5], [w for w in got[5] if "not available in this crew version" in w
                      and f"autopilot.sleep.{key}" in w] != [],
            crew_autopilot.settings(str(root))["deploy"]) == (
        (False, "stop", "risk", "risk", "asleep"), True, "none")


# --- re-resolved per decision ---------------------------------------------------

def test_a_run_that_crosses_the_window_end_returns_to_day_values(tmp_path, clock):
    root = _repo(tmp_path, sleep=_night())

    clock(_at(6, 59))
    first = crew_autopilot.approval_policy(str(root), T)
    clock(_at(7, 0))
    second = crew_autopilot.approval_policy(str(root), T)

    assert ((first["allow"], first["policy"]), (second["allow"], second["policy"])) == (
        (True, "self"), (False, "risk"))


def test_receipt_written_asleep_stops_standing_after_the_window(tmp_path, clock):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")
    code, _text = crew_autopilot.approve(str(root), T)
    night = crew_ticket.accepted(str(root), T)

    clock(_at(7, 0))
    morning = crew_ticket.accepted(str(root), T)

    assert (code, night["status"], morning["status"],
            "autopilot.approval" in morning["why"]) == (0, "approved", "unaccepted", True)


QUESTIONS = """# T-1 questions

## Q1: Which database?
Research: crew:explorer found src/db.py uses sqlite3; crew:researcher: none needed.

### Option A (recommended): keep sqlite
Cost: no concurrent writers.

### Option B: postgres
Cost: a server to run and a migration.

taken: Option A by autopilot (self)
"""


def test_taken_line_written_asleep_is_invalid_by_day(tmp_path, clock):
    root = _repo(tmp_path, sleep=_night(), risk="high")
    _write(root / ".work" / "tickets" / T / "questions.md", QUESTIONS)

    clock(NIGHT)
    night = crew_autopilot.questions_check(str(root), T)
    clock(DAY)
    day = crew_autopilot.questions_check(str(root), T)

    assert ((night["valid"], night["action"]), (day["valid"], day["action"])) == (
        (True, "take"), (False, "stop"))


# --- other policies and directions ----------------------------------------------

# L-0654: with no `sleep.deploy`, sleep leaves `none` and `nonprod` alone; a day
# `all` is the one value sleep changes (test_sleep_deploy_matrix).
@pytest.mark.parametrize("deploy", ["none", "nonprod"])
def test_deploy_allowed_ignores_sleep(tmp_path, clock, deploy):
    root = _repo(tmp_path, sleep=_night())
    config = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    config["autopilot"]["deploy"] = deploy
    _write(root / ".crew" / "config.json", json.dumps(config))

    answers = []
    for when in (NIGHT, DAY):
        clock(when)
        for env, cls in (("staging", "nonProd"), ("live", "prod")):
            answers.append(crew_autopilot.deploy_allowed(str(root), env, cls))

    assert answers[:2] == answers[2:]


def test_asleep_human_refuses(tmp_path, clock):
    clock(NIGHT)
    root = _repo(tmp_path, approval="self", sleep=_night(approval="human"), risk="low")

    code, text = crew_autopilot.approve(str(root), T)

    assert (code, "autopilot.approval is human" in text, "day value self" in text,
            _receipt(root)) == (2, True, True, None)


# --- reporting -------------------------------------------------------------------

@pytest.mark.parametrize("sleep,now,line", [
    (_night(), NIGHT, "sleep=asleep schedule=22:00-07:00 approval=self questions=self source=schedule"),
    (_night(questions=None), DAY,
     "sleep=awake schedule=22:00-07:00 approval=self questions=- source=schedule"),
    (_night(schedule=None), NIGHT, "sleep=off schedule=none approval=self questions=self source=schedule"),
    (_night(schedule="22"), NIGHT,
     "sleep=unknown schedule=none approval=self questions=self source=schedule applied=-"),
    (MISSING, NIGHT, "sleep=off schedule=none approval=- questions=- source=schedule"),
])
def test_settings_cli_prints_the_sleep_line(tmp_path, clock, capsys, sleep, now, line):
    clock(now)
    root = _repo(tmp_path, sleep=sleep)

    crew_autopilot.main(["settings", "--root", str(root)])
    lines = capsys.readouterr().out.splitlines()
    crew_autopilot.main(["settings", "--root", str(root), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert (lines[2], data["day"], data["sleep"]["state"]) == (
        line, {"approval": "risk", "questions": "risk", "deploy": "none"},  # L-0654: day.deploy
        line.split()[0][len("sleep="):])


def test_settings_cli_prints_unknown_for_an_unreadable_config(tmp_path, capsys):
    root = _repo(tmp_path, sleep=_night())
    _write(root / ".crew" / "config.json", "[")

    crew_autopilot.main(["settings", "--root", str(root)])

    assert capsys.readouterr().out.splitlines()[2] == (
        "sleep=unknown schedule=none approval=- questions=- source=schedule applied=-")


def test_a_schedule_set_keeps_approve_the_only_writer(tmp_path, clock, monkeypatch, capsys):
    """test_crew_autopilot_policy.py's only-writer test, with a window set."""
    import test_crew_autopilot_policy as policy  # pylint: disable=import-outside-toplevel
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night())
    before = policy._files(root)  # pylint: disable=protected-access

    for run in policy.READ_ONLY_RUNS:
        policy._main(root, *run)  # pylint: disable=protected-access
    capsys.readouterr()

    assert policy._files(root) == before  # pylint: disable=protected-access


# --- review round 1 -------------------------------------------------------------
# F1: when sleep cannot be told, a valid night override that is STRICTER than
# the day value still applies (human > risk > self); a looser one never does.

TIGHT = {"schedule": "22:00-7:00", "approval": "human", "questions": "human"}


def _bad_schedule(monkeypatch, root):  # pylint: disable=unused-argument
    return root


def _raising_resolve(monkeypatch, root):
    def boom(*_args):
        raise RuntimeError("resolver")
    monkeypatch.setattr(crew_sleep, "resolve", boom)
    return root


def _raising_clock(monkeypatch, root):
    def boom():
        raise OSError("no clock")
    monkeypatch.setattr(crew_sleep, "now", boom)
    return root


def _text_clock(monkeypatch, root):
    monkeypatch.setattr(crew_sleep, "now", lambda: "23:00")
    return root


@pytest.mark.parametrize("source", [_bad_schedule, _raising_resolve, _raising_clock,
                                    _text_clock])
def test_unknown_sleep_keeps_a_stricter_override(tmp_path, clock, monkeypatch, source):
    clock(NIGHT)
    sleep = dict(TIGHT, schedule="22:00-07:00") if source is not _bad_schedule else TIGHT
    root = source(monkeypatch, _repo(tmp_path, approval="self", questions="self",
                                     sleep=sleep, risk="low"))

    conf = crew_autopilot.settings(str(root))
    got = crew_autopilot.approval_policy(str(root), T)
    code, _text = crew_autopilot.approve(str(root), T)

    assert (conf["sleep"]["state"], conf["approval"], conf["questions"], got["allow"],
            crew_autopilot.question_policy(str(root), T)["action"], code,
            _receipt(root)) == ("unknown", "human", "human", False, "stop", 2, None)


@pytest.mark.parametrize("day,night,want", [
    ("self", "risk", "risk"), ("self", "human", "human"), ("risk", "human", "human"),
    ("risk", "self", "risk"), ("human", "self", "human"), ("human", "risk", "human"),
    ("risk", None, "risk"), ("self", "Human", "human"),
])
def test_unknown_sleep_takes_the_strictest_per_key(tmp_path, clock, day, night, want):
    clock(NIGHT)
    root = _repo(tmp_path, approval=day, questions="self",
                 sleep={"schedule": "22", "approval": night, "questions": None})

    conf = crew_autopilot.settings(str(root))

    assert (conf["approval"], conf["questions"], conf["day"]["approval"]) == (want, "self", day)


def test_unknown_sleep_from_a_non_object_block_has_no_override_to_read(tmp_path, clock):
    """The fourth unknown source: nothing under it can be read, so since
    review round 2 (N7) both keys read human, whatever the day values."""
    clock(NIGHT)
    root = _repo(tmp_path, approval="human", questions="self", sleep=["human"])

    conf = crew_autopilot.settings(str(root))

    assert (conf["sleep"]["state"], conf["approval"], conf["questions"]) == (
        "unknown", "human", "human")


def test_strictest_is_the_first_of_strictness():
    assert crew_sleep.STRICTEST == crew_autopilot.STRICTNESS[0]


# N1: the asleep note goes only on a key whose override applied.

def test_the_asleep_note_names_only_an_applied_override(tmp_path, clock):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(questions=None), risk="high")

    approval = crew_autopilot.approval_policy(str(root), T)
    questions = crew_autopilot.question_policy(str(root), T)

    assert ("(asleep 22:00-07:00; day value risk)" in approval["reason"],
            "asleep" in questions["reason"], questions["sleep"]) == (True, False, "")


# N2: approve's receipt, its line and crew_ticket.approve's re-check are one
# decision, even when the window ends between the reads.

def test_approve_uses_one_decision_across_the_window_edge(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, sleep=_night(), risk="high")
    when = {"now": NIGHT}
    monkeypatch.setattr(crew_sleep, "now", lambda: when["now"])
    original = crew_ticket.approve

    def approve_at_dawn(*args, **kwargs):
        when["now"] = _at(7, 0)
        return original(*args, **kwargs)
    monkeypatch.setattr(crew_ticket, "approve", approve_at_dawn)

    code = crew_autopilot.main(["approve", "--root", str(root), "--ticket", T])
    out = capsys.readouterr().out.strip()

    assert (code, out, _receipt(root)["approved_by"]) == (
        0, f"self-approved {T} under approval=self, risk=high"
           " (asleep 22:00-07:00; day value risk)", "autopilot:self")


def test_the_pinned_decision_does_not_outlive_approve(tmp_path, monkeypatch):
    root = _repo(tmp_path, sleep=_night(), risk="high")
    when = {"now": NIGHT}
    monkeypatch.setattr(crew_sleep, "now", lambda: when["now"])

    code, _text = crew_autopilot.approve(str(root), T)
    when["now"] = DAY

    assert (code, crew_autopilot.approval_policy(str(root), T)["allow"],
            crew_ticket.accepted(str(root), T)["status"]) == (0, False, "unaccepted")


# --- review round 2 -------------------------------------------------------------
# F2: an override value crew cannot render must not drop the other overrides,
# and an override that cannot be read counts as `human` under unknown.

def _deep_text(levels=985):
    """`["self"]` nested `levels` deep, as JSON text: json.dumps of the
    nested list itself would hit the recursion limit inside pytest."""
    return "[" * levels + '"self"' + "]" * levels


@pytest.mark.parametrize("deep_key", ["approval", "questions"])
def test_a_deeply_nested_override_drops_no_other_override(tmp_path, clock, deep_key):
    clock(NIGHT)
    other = "questions" if deep_key == "approval" else "approval"
    sleep = {"schedule": "22:00-7:00", deep_key: "DEEP", other: "human"}
    root = _repo(tmp_path, approval="self", questions="self", sleep=sleep, risk="low")
    path = root / ".crew" / "config.json"
    base = path.read_text(encoding="utf-8")
    # The reviewer's repro: the deepest value the config reader still decodes
    # at this stack depth, which an unbounded repr further down cannot render.
    # The depth that decodes varies with the stack (pytest, xdist), so it is
    # found, not fixed: step down from 999 until settings reads the file.
    conf = None
    for levels in range(999, 600, -1):
        _write(path, base.replace('"DEEP"', _deep_text(levels)))
        try:
            conf = crew_autopilot.settings(str(root))
        except RecursionError:
            continue
        break

    # The deep value itself is not a policy, so it counts as human whether or
    # not it can be rendered at this depth, and the OTHER key's tightening
    # stands.
    assert (conf["sleep"]["state"], conf[other], conf[deep_key] == "human",
            crew_autopilot.approval_policy(str(root), T)["allow"]) == (
        "unknown", "human", True, False)


def test_an_override_that_cannot_be_read_counts_as_human(tmp_path, clock, monkeypatch):
    clock(NIGHT)
    root = _repo(tmp_path, approval="self", questions="self",
                 sleep={"schedule": "22", "approval": "risk", "questions": "self"},
                 risk="low")
    real = crew_sleep._override  # pylint: disable=protected-access

    def flaky(block, key, policies):
        if key == "questions":
            raise RecursionError("cannot read")
        return real(block, key, policies)
    monkeypatch.setattr(crew_sleep, "_override", flaky)

    conf = crew_autopilot.settings(str(root))

    assert (conf["sleep"]["state"], conf["approval"], conf["questions"],
            any("autopilot.sleep.questions" in w for w in conf["warnings"])) == (
        "unknown", "risk", "human", True)


def test_a_rendering_that_raises_is_still_bounded():
    class Loud:  # pylint: disable=too-few-public-methods
        def __repr__(self):
            raise ValueError("no")
    text = crew_sleep.render(Loud())
    long = crew_sleep.render("x" * 5000)

    assert ("Loud" in text, len(long) < 200) == (True, True)


# N7 (owner decision, taken on the recommendation): a non-object
# autopilot.sleep reads `human` for both keys under unknown.

@pytest.mark.parametrize("value", ["22:00-07:00", ["self"], 1])
def test_a_non_object_sleep_reads_human_for_both_keys(tmp_path, clock, value):
    clock(NIGHT)
    root = _repo(tmp_path, approval="self", questions="self", sleep=value, risk="low")

    conf = crew_autopilot.settings(str(root))

    assert (conf["sleep"]["state"], conf["approval"], conf["questions"],
            crew_autopilot.approval_policy(str(root), T)["allow"]) == (
        "unknown", "human", "human", False)


# N6: an unknown warning does not claim the day values applied.

@pytest.mark.parametrize("sleep", [{"schedule": "22", "approval": "human"}, "x"])
def test_unknown_warnings_name_the_stricter_rule(tmp_path, clock, sleep):
    clock(NIGHT)
    root = _repo(tmp_path, approval="self", questions="self", sleep=sleep)

    warnings = [w for w in crew_autopilot.settings(str(root))["warnings"]
                if w.startswith("autopilot.sleep")]

    assert (warnings != [], any("the day values apply" in w for w in warnings),
            all("stricter" in w for w in warnings)) == (True, False, True)


# N8: approve's pinned decision is visible to its own thread only.

def test_the_pin_is_not_seen_by_another_thread(tmp_path, monkeypatch):
    import threading  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, sleep=_night(), risk="high")
    when = {"now": NIGHT}
    monkeypatch.setattr(crew_sleep, "now", lambda: when["now"])
    inside, release, seen = threading.Event(), threading.Event(), {}
    original = crew_ticket.approve

    def slow_approve(*args, **kwargs):
        inside.set()
        release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(crew_ticket, "approve", slow_approve)

    worker = threading.Thread(target=lambda: seen.update(
        code=crew_autopilot.approve(str(root), T)[0]))
    worker.start()
    inside.wait(10)
    when["now"] = DAY
    other = crew_autopilot.approval_policy(str(root), T)
    when["now"] = NIGHT
    release.set()
    worker.join(10)

    assert (other["allow"], other["policy"], seen.get("code")) == (False, "risk", 0)


# N9: the settings text line names the overrides applied under unknown.

@pytest.mark.parametrize("sleep,tail", [
    (TIGHT, "applied=approval,questions"),
    ({"schedule": "22", "approval": "self", "questions": "human"}, "applied=questions"),
    ({"schedule": "22", "approval": "self"}, "applied=-"),
])
def test_the_unknown_sleep_line_names_what_applied(tmp_path, clock, capsys, sleep, tail):
    clock(NIGHT)
    root = _repo(tmp_path, approval="risk", questions="risk", sleep=sleep)

    crew_autopilot.main(["settings", "--root", str(root)])
    line = capsys.readouterr().out.splitlines()[2]
    crew_autopilot.main(["settings", "--root", str(root), "--json"])
    applied = json.loads(capsys.readouterr().out)["sleep"]["applied"]

    assert (line.split()[0], line.split()[-1], line.split()[-1]) == (
        "sleep=unknown", tail, "applied=" + (",".join(applied) or "-"))


# --- L-0652: manual `sleep` and `wake` -------------------------------------------
# `crew_autopilot.py sleep` and `wake` write `<git-common-dir>/crew/autopilot-sleep.json`,
# which beats the schedule until its `until` (UTC-aware ISO). A file that
# cannot be trusted reads as `unknown` (per key the stricter of the day and the
# night value), never as a looser state. Owner decision 2026-10-04 (review B1):
# until L-1504, a manual `sleep` only TIGHTENS -- a night value applies only
# where it is stricter than the day value -- because the session can run it.

EVENING = _at(20, 0)
U = crew_sleep.to_utc
TIGHT_NIGHT = {"schedule": "22:00-07:00", "approval": "human", "questions": "human"}


def _manual_path(root):
    return os.path.join(crew_ticket.state_dir(str(root)), crew_sleep.MANUAL_FILE)


def _cmd(root, capsys, action, *rest):
    code = crew_autopilot.main([action, "--root", str(root)] + list(rest))
    return code, capsys.readouterr().out


def _allowed(root):
    return crew_autopilot.approval_policy(str(root), T)["allow"]


def _takes(root):
    return crew_autopilot.question_policy(str(root), T)["action"]


def _record(root):
    with open(_manual_path(root), encoding="utf-8") as handle:
        return json.load(handle)


def _plant(root, payload):
    """A state file written by hand: `payload` is text, or JSON-dumped."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    _write(_manual_path(root), text)


def _sleep_conf(root):
    return crew_autopilot.settings(str(root))


def _iso(when):
    return U(when).isoformat()


NEXT_MORNING = datetime.datetime(2026, 10, 5, 7, 0)
VALID = {"state": "asleep", "by": "x", "at": _iso(_at(11, 0)), "until": _iso(NEXT_MORNING)}


# Review B1: day human, night self, at noon. The session runs `sleep` itself;
# before the fix that was 19 hours of self-approval.
def test_b1_the_sessions_manual_sleep_never_loosens(tmp_path, clock, capsys):
    clock(DAY)
    root = _repo(tmp_path, sleep=_night(), approval="human", questions="human", risk="high")

    code, out = _cmd(root, capsys, "sleep", "--by", "owner")
    after_cli = (_allowed(root), _takes(root))
    _plant(root, dict(VALID, by="owner"))
    after_file = (_allowed(root), _takes(root))

    assert (code, "only tightens" in out, after_cli, after_file) == (
        2, True, (False, "stop"), (False, "stop"))


def test_manual_sleep_applies_only_the_stricter_night_value(tmp_path, clock, capsys):
    """Must-allow: night approval human is stricter than day self, so it
    applies; night questions self is looser than day human, so it does not."""
    clock(EVENING)
    root = _repo(tmp_path, sleep=_night(approval="human", questions="self"),
                 approval="self", questions="human", risk="high")
    before = _allowed(root)

    code, out = _cmd(root, capsys, "sleep")
    conf = _sleep_conf(root)

    assert (before, code, out, _allowed(root), _takes(root), conf["sleep"]["applied"]) == (
        True, 0, "asleep until 07:00 (set by cli; tightens approval); "
                 "/crew:autopilot wake undoes it\n", False, "stop", ["approval"])


def test_inside_the_window_a_manual_sleep_keeps_the_scheduled_night(tmp_path, clock, capsys):
    """The schedule already grants its night values inside the window; a
    manual sleep there takes nothing away."""
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(approval="self", questions="human"),
                 approval="risk", questions="risk", risk="high")

    code, _out = _cmd(root, capsys, "sleep")

    assert (code, _allowed(root), _takes(root)) == (0, True, "stop")


def test_manual_sleep_records_who_set_it_in_utc(tmp_path, clock, capsys):
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT)

    _cmd(root, capsys, "sleep", "--by", "owner")
    conf = _sleep_conf(root)
    record = _record(root)

    assert (record["by"], record["at"], record["until"], record["at"].endswith("+00:00"),
            conf["sleep"]["source"], conf["sleep"]["until"]) == (
        "owner", _iso(EVENING), _iso(NEXT_MORNING), True, "manual", _iso(NEXT_MORNING))


def test_manual_wake_inside_the_window(tmp_path, clock, capsys):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")
    asleep = _allowed(root)

    code, out = _cmd(root, capsys, "wake")
    awake_now = _allowed(root)
    clock(datetime.datetime(2026, 10, 5, 6, 59))
    awake_late = _allowed(root)
    clock(datetime.datetime(2026, 10, 5, 22, 30))
    next_night = _allowed(root)

    assert (asleep, code, out, awake_now, awake_late, next_night) == (
        True, 0, "awake; the schedule resumes at 07:00\n", False, False, True)


def test_manual_sleep_without_a_schedule_expires(tmp_path, clock, capsys):
    clock(DAY)
    root = _repo(tmp_path, sleep=_night(schedule=None, approval="human"), approval="self",
                 risk="high")

    code, _out = _cmd(root, capsys, "sleep")
    clock(datetime.datetime(2026, 10, 4, 23, 59))
    late = _allowed(root)
    clock(datetime.datetime(2026, 10, 5, 0, 1))
    after = _allowed(root)

    assert (code, _record(root)["until"], late, after) == (
        0, _iso(datetime.datetime(2026, 10, 5, 0, 0)), False, True)


def _without_allow(root):
    path = root / ".crew" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["scope"]["allowCliApproval"]
    _write(path, json.dumps(data))


@pytest.mark.parametrize("allow", [MISSING, False, "true", 1])
def test_sleep_refuses_unless_allow_cli_approval_is_exactly_true(tmp_path, clock, capsys,
                                                                   allow):
    import test_crew_autopilot_policy as policy  # pylint: disable=import-outside-toplevel
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT, allow=True if allow is MISSING else allow)
    if allow is MISSING:
        _without_allow(root)
    before = policy._files(root)  # pylint: disable=protected-access

    code, out = _cmd(root, capsys, "sleep")

    assert (code, out.startswith("refused: scope.allowCliApproval"),
            policy._files(root) == before) == (2, True, True)  # pylint: disable=protected-access


def _unarmed(tmp_path):
    return _repo(tmp_path, sleep=TIGHT_NIGHT, armed=False)


def _unreadable(tmp_path):
    root = _repo(tmp_path, sleep=TIGHT_NIGHT)
    _write(root / ".crew" / "config.json", "{not json")
    return root


def _no_override(tmp_path):
    return _repo(tmp_path, sleep={"schedule": "22:00-07:00"})


def _no_sleep_block(tmp_path):
    return _repo(tmp_path)


def _bad_window(tmp_path):
    return _repo(tmp_path, sleep=dict(TIGHT_NIGHT, schedule="22-07"))


def _only_looser(tmp_path):
    return _repo(tmp_path, sleep=_night(), approval="risk", questions="risk")


@pytest.mark.parametrize("build,why", [
    (_unarmed, "autopilot.mode is not plan"),
    (_unreadable, "could not be read"),
    (_no_override, "only tightens"),
    (_no_sleep_block, "only tightens"),
    (_bad_window, "autopilot.sleep.schedule"),
    (_only_looser, "only tightens"),
])
def test_sleep_refuses_and_writes_nothing(tmp_path, clock, capsys, build, why):
    import test_crew_autopilot_policy as policy  # pylint: disable=import-outside-toplevel
    clock(EVENING)
    root = build(tmp_path)
    before = policy._files(root)  # pylint: disable=protected-access

    code, out = _cmd(root, capsys, "sleep")

    assert (code, out.startswith("refused:"), why in out,
            policy._files(root) == before) == (2, True, True, True)  # pylint: disable=protected-access


@pytest.mark.parametrize("payload,state,reason", [
    ("not json", "unknown", "not JSON"),
    ([], "unknown", "not an object"),
    ({k: v for k, v in VALID.items() if k != "until"}, "unknown", "until"),
    (dict(VALID, state="on"), "unknown", "state"),
    (dict(VALID, until=_iso(_at(11, 30))), "awake", "expired"),
    (dict(VALID, until=_iso(datetime.datetime(2026, 10, 5, 12, 0))), "unknown", "24 hours"),
    (dict(VALID, until=_iso(datetime.datetime(2026, 10, 5, 11, 1))), "unknown", "24 hours"),
    (dict(VALID, at=_iso(_at(13, 0))), "unknown", "future"),
    (dict(VALID, at="yesterday"), "unknown", "at"),
    (dict(VALID, by=["x"]), "unknown", "by"),
    (dict(VALID, at="2026-10-04T11:00:00"), "unknown", "UTC"),
    (dict(VALID, until="2026-10-05T07:00:00"), "unknown", "UTC"),
])
def test_an_untrusted_state_file_is_ignored_with_a_warning(tmp_path, clock, payload, state,
                                                           reason):
    clock(DAY)
    root = _repo(tmp_path, sleep=_night(), risk="high")
    _plant(root, payload)

    conf = _sleep_conf(root)
    warned = [w for w in conf["warnings"] if crew_sleep.MANUAL_FILE in w and reason in w]

    assert (conf["sleep"]["state"], warned != [], _allowed(root)) == (state, True, False)


def _fifo(path):
    os.mkfifo(path)


def _directory(path):
    os.makedirs(path)


def _symlink(path):
    target = path + ".real"
    _write(target, json.dumps(VALID))
    os.symlink(target, path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs and symlinks")
@pytest.mark.parametrize("make", [_fifo, _directory, _symlink])
def test_a_state_file_that_is_not_a_regular_file_is_unknown(tmp_path, clock, make):
    """Review N3: never opened -- a FIFO would block the reader, a device
    could be read forever -- and never followed through a symlink."""
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")
    os.makedirs(os.path.dirname(_manual_path(root)), exist_ok=True)
    make(_manual_path(root))

    conf = _sleep_conf(root)

    assert (conf["sleep"]["state"], _allowed(root),
            [w for w in conf["warnings"] if "not a regular file" in w] != []) == (
        "unknown", False, True)


def test_a_valid_state_file_is_honoured_as_a_tightening(tmp_path, clock):
    """The must-allow neighbour of the untrusted shapes above."""
    clock(DAY)
    root = _repo(tmp_path, sleep=_night(approval="human"), approval="self", risk="high")
    before = _allowed(root)
    _plant(root, VALID)

    conf = _sleep_conf(root)

    assert (before, conf["sleep"]["state"], conf["sleep"]["source"], conf["warnings"],
            _allowed(root)) == (True, "asleep", "manual", [], False)


def test_an_untrusted_state_file_inside_the_window_never_loosens(tmp_path, clock):
    """Could-not-tell is per key the stricter value, not "no manual state":
    garbage planted at night does not leave the looser night value in force."""
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")
    without = _allowed(root)
    _plant(root, "{")

    assert (without, _allowed(root), _sleep_conf(root)["sleep"]["state"]) == (
        True, False, "unknown")


def test_a_manual_sleep_stops_counting_when_allow_cli_approval_is_turned_off(tmp_path, clock):
    """Read-time gate: a valid `asleep` file is honoured only while
    `scope.allowCliApproval` is exactly true."""
    clock(DAY)
    root = _repo(tmp_path, sleep=_night(), allow=False, risk="high")
    _plant(root, VALID)

    got = crew_autopilot.question_policy(str(root), T)
    conf = _sleep_conf(root)

    assert (got["action"], conf["sleep"]["state"],
            [w for w in conf["warnings"] if "scope.allowCliApproval" in w] != []) == (
        "stop", "unknown", True)


def test_a_manual_wake_never_loosens_a_stricter_night_value(tmp_path, clock, capsys):
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(questions="human"), questions="self", risk="high")

    code, _out = _cmd(root, capsys, "wake")
    got = crew_autopilot.question_policy(str(root), T)
    conf = _sleep_conf(root)

    assert (code, got["action"], conf["sleep"]["state"], conf["approval"]) == (
        0, "stop", "awake", "risk")


def test_wake_with_nothing_to_undo_says_already_awake(tmp_path, clock, capsys):
    import test_crew_autopilot_policy as policy  # pylint: disable=import-outside-toplevel
    clock(DAY)
    root = _repo(tmp_path, sleep=_night())
    before = policy._files(root)  # pylint: disable=protected-access

    code, out = _cmd(root, capsys, "wake")

    assert (code, out, policy._files(root) == before) == (  # pylint: disable=protected-access
        0, "already awake\n", True)


def test_wake_outside_the_window_removes_a_manual_sleep(tmp_path, clock, capsys):
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT, risk="low")
    _cmd(root, capsys, "sleep")
    asleep = _allowed(root)

    code, out = _cmd(root, capsys, "wake")

    assert (asleep, code, out, os.path.exists(_manual_path(root)), _allowed(root)) == (
        False, 0, "awake; the schedule resumes at 20:00\n", False, True)


def test_wake_never_refuses_for_policy(tmp_path, clock, capsys):
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT, risk="high")
    _cmd(root, capsys, "sleep")
    _write(root / ".crew" / "config.json", "{not json")

    code, _out = _cmd(root, capsys, "wake")

    assert (code, os.path.exists(_manual_path(root))) == (0, False)


@pytest.mark.parametrize("breaks", ["config", "schedule"])
def test_wake_says_when_the_schedule_cannot_be_told(tmp_path, clock, capsys, breaks):
    """Review N2: no "the schedule resumes at <now>" when it cannot be told."""
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT, risk="high")
    _cmd(root, capsys, "sleep")
    if breaks == "config":
        _write(root / ".crew" / "config.json", "{not json")
    else:
        config = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
        config["autopilot"]["sleep"]["schedule"] = "22-07"
        _write(root / ".crew" / "config.json", json.dumps(config))

    code, out = _cmd(root, capsys, "wake")

    assert (code, out.startswith("awake; whether the schedule is asleep cannot be told"),
            "resumes at" in out) == (0, True, False)


def test_manual_state_is_shared_by_worktrees(tmp_path, clock, capsys):
    import subprocess  # pylint: disable=import-outside-toplevel
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT, risk="high")
    lane = tmp_path / "lane"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "-q", str(lane), "-b", "lane"],
                   check=True, capture_output=True)

    code, _out = _cmd(root, capsys, "sleep")
    conf = crew_autopilot.settings(str(lane))

    assert (code, conf["sleep"]["state"], conf["sleep"]["source"],
            os.path.exists(lane / crew_sleep.MANUAL_FILE)) == (0, "asleep", "manual", False)


def test_the_sleep_line_names_a_manual_source(tmp_path, clock, capsys):
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT)
    _cmd(root, capsys, "sleep")

    crew_autopilot.main(["settings", "--root", str(root)])
    line = capsys.readouterr().out.splitlines()[2]

    assert line == ("sleep=asleep schedule=22:00-07:00 approval=human questions=human "
                    "source=manual until=07:00 applied=approval,questions")


def test_a_manual_sleep_note_names_its_end(tmp_path, clock, capsys):
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT, risk="high")
    _cmd(root, capsys, "sleep")

    got = crew_autopilot.approval_policy(str(root), T)

    assert "(asleep by hand until 07:00; day value risk)" in got["reason"]


@pytest.mark.parametrize("when,end,want", [
    (_at(20, 0), "07:00", "2026-10-05T07:00:00"),
    (_at(23, 0), "07:00", "2026-10-05T07:00:00"),
    (_at(6, 59), "07:00", "2026-10-04T07:00:00"),
    (_at(7, 0), "07:00", "2026-10-05T07:00:00"),
])
def test_next_edge(when, end, want):
    minute = int(end[:2]) * 60 + int(end[3:])

    assert crew_sleep.next_edge(minute, when).isoformat() == want


def test_read_manual_caps_at_24_hours():
    at = _at(7, 0)
    exact = dict(VALID, at=_iso(at), until=_iso(at + datetime.timedelta(hours=24)))
    over = dict(exact, until=_iso(at + datetime.timedelta(hours=24, minutes=1)))

    assert (crew_sleep.read_manual(("ok", exact), _at(8, 0))["kind"],
            crew_sleep.read_manual(("ok", over), _at(8, 0))["kind"]) == ("valid", "untrusted")


def test_a_state_directory_git_cannot_name_is_unknown(tmp_path, clock, monkeypatch):
    """Inside a checkout, a `<git-common-dir>` git cannot name is
    could-not-tell (the stricter value per key), never "no manual state"."""
    clock(NIGHT)
    root = _repo(tmp_path, sleep=_night(), risk="high")
    monkeypatch.setattr(crew_ticket, "state_dir", lambda _root: None)

    conf = _sleep_conf(root)

    assert (conf["sleep"]["state"], conf["approval"], _allowed(root)) == (
        "unknown", "risk", False)


# --- #427 review round 2: each read-safety layer of the state file (FIX-1) ------
# `_manual_found` / `_read_regular`: lstat must say regular (nothing else is
# ever opened), the open neither follows a final symlink (O_NOFOLLOW) nor
# blocks on a FIFO (O_NONBLOCK), fstat re-checks what was opened, and at most
# MANUAL_MAX_BYTES are read. Each test below goes red with one layer removed.

def _honouring(tmp_path):
    """A repo where a valid planted record reads `asleep` (a tightening)."""
    return _repo(tmp_path, sleep=_night(approval="human"), approval="self", risk="high")


def _opens(monkeypatch, path, before=None):
    """Wrap `os.open`: record the file type of every fd opened at `path`, and
    run `before()` once just ahead of the first open there (the swap between
    lstat and open)."""
    real, seen, armed = os.open, [], {"once": before}

    def fake(name, flags, *rest):
        if os.fspath(name) == path and armed["once"]:
            armed.pop("once")()
        handle = real(name, flags, *rest)
        if os.fspath(name) == path:
            seen.append(stat.S_IFMT(os.fstat(handle).st_mode))
        return handle
    monkeypatch.setattr(os, "open", fake)
    return seen


def test_an_oversized_state_file_is_unknown(tmp_path, clock):
    clock(DAY)
    root = _honouring(tmp_path)
    _plant(root, json.dumps(VALID) + " " * crew_autopilot_sleep.MANUAL_MAX_BYTES)

    conf = _sleep_conf(root)

    assert (conf["sleep"]["state"], _allowed(root)) == ("unknown", False)


def test_an_exactly_full_state_file_is_still_read(tmp_path, clock):
    """The cap's must-allow neighbour."""
    clock(DAY)
    root = _honouring(tmp_path)
    text = json.dumps(VALID)
    _plant(root, text + " " * (crew_autopilot_sleep.MANUAL_MAX_BYTES - len(text)))

    assert _sleep_conf(root)["sleep"]["state"] == "asleep"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs and symlinks")
@pytest.mark.parametrize("make", [_fifo, _directory, _symlink])
def test_lstat_keeps_anything_but_a_regular_file_from_being_opened(tmp_path, clock, monkeypatch,
                                                                    make):
    clock(DAY)
    root = _honouring(tmp_path)
    path = _manual_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    make(path)
    seen = _opens(monkeypatch, path)

    conf = _sleep_conf(root)

    assert (conf["sleep"]["state"], seen) == ("unknown", [])


def _swap_to(path, make):
    def swap():
        os.unlink(path)
        make(path)
    return swap


def _symlink_to_fifo(path):
    os.mkfifo(path + ".fifo")
    os.symlink(path + ".fifo", path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs and symlinks")
def test_o_nofollow_never_opens_what_a_swapped_in_symlink_names(tmp_path, clock, monkeypatch):
    """lstat saw a regular file; a symlink to a FIFO replaced it before the
    open. O_NOFOLLOW refuses the link, so the FIFO is never opened."""
    clock(DAY)
    root = _honouring(tmp_path)
    _plant(root, VALID)
    path = _manual_path(root)
    seen = _opens(monkeypatch, path, _swap_to(path, _symlink_to_fifo))

    conf = _sleep_conf(root)

    assert (conf["sleep"]["state"], seen) == ("unknown", [])


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs")
def test_o_nonblock_never_waits_on_a_swapped_in_fifo(tmp_path, clock, monkeypatch):
    """A FIFO with no writer, swapped in after lstat: the read returns at once."""
    import threading  # pylint: disable=import-outside-toplevel
    clock(DAY)
    root = _honouring(tmp_path)
    _plant(root, VALID)
    path = _manual_path(root)
    _opens(monkeypatch, path, _swap_to(path, os.mkfifo))
    got = {}
    worker = threading.Thread(target=lambda: got.update(conf=_sleep_conf(root)), daemon=True)

    worker.start()
    worker.join(10)
    stuck = worker.is_alive()
    if stuck:  # unblock the reader so the thread can end
        os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
        worker.join(10)

    assert (stuck, got.get("conf", {}).get("sleep", {}).get("state")) == (False, "unknown")


def _within(seconds, call, fifo):
    """`call()` on a thread; if it is still running after `seconds` (an
    O_NONBLOCK regression blocking on the FIFO), open a writer to free it and
    fail rather than hang the suite."""
    import threading  # pylint: disable=import-outside-toplevel
    got = {}
    worker = threading.Thread(target=lambda: got.update(value=call()), daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        worker.join(seconds)
        pytest.fail(f"reading the state file blocked for more than {seconds}s")
    return got["value"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs")
def test_fstat_refuses_a_swapped_in_fifo_that_holds_a_valid_record(tmp_path, clock,
                                                                    monkeypatch):
    """O_NOFOLLOW and O_NONBLOCK let a FIFO open; only fstat sees it is not a
    regular file. Its writer has already queued a valid record."""
    clock(DAY)
    root = _honouring(tmp_path)
    _plant(root, VALID)
    path = _manual_path(root)
    writers = []
    real_open = os.open

    def swap():
        os.unlink(path)
        os.mkfifo(path)
        writers.append(path)
    seen = _opens(monkeypatch, path, swap)
    real_read = os.read

    def feed(handle, size):
        if writers:
            writer = real_open(writers.pop(), os.O_WRONLY | os.O_NONBLOCK)
            os.write(writer, json.dumps(VALID).encode())
            os.close(writer)
        return real_read(handle, size)
    monkeypatch.setattr(os, "read", feed)
    conf = _within(10, lambda: _sleep_conf(root), path)

    assert (conf["sleep"]["state"], seen) == ("unknown", [stat.S_IFIFO])


def test_without_o_nofollow_lstat_still_refuses_a_symlink(tmp_path, clock, monkeypatch):
    """Windows has no O_NOFOLLOW: simulated by removing it, a symlink at the
    path is still refused by lstat before anything is opened."""
    if not hasattr(os, "symlink"):
        pytest.skip("no symlinks")
    clock(DAY)
    root = _honouring(tmp_path)
    path = _manual_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _symlink(path)
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    seen = _opens(monkeypatch, path)

    assert (_sleep_conf(root)["sleep"]["state"], seen) == ("unknown", [])


# --- #427 review round 2: DST (FIX-2, NIT 1) -----------------------------------

@pytest.fixture(name="new_york")
def _new_york(monkeypatch):
    if not hasattr(time, "tzset") or not os.path.exists("/usr/share/zoneinfo/America/New_York"):
        pytest.skip("needs time.tzset and the tz database")
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_sleep_on_a_fall_back_day_writes_a_record_it_trusts(tmp_path, clock, capsys, new_york):
    """03:30 on 2026-10-31, window 23:00-03:00: the next 03:00 is 24.5 real
    hours away across the fall-back; the record must still be trusted."""
    when = datetime.datetime(2026, 10, 31, 3, 30)
    clock(when)
    root = _repo(tmp_path, sleep=dict(TIGHT_NIGHT, schedule="23:00-03:00"))

    code, _out = _cmd(root, capsys, "sleep")

    assert (code, _record(root)["until"], _sleep_conf(root)["sleep"]["state"]) == (
        0, "2026-11-01T08:00:00+00:00", "asleep")


def test_sleep_on_a_spring_forward_day_ends_at_the_next_valid_instant(tmp_path, clock, capsys,
                                                                      new_york):
    """Window 22:00-02:30 the night 02:00 becomes 03:00: 02:30 does not exist,
    and the sleep ends at 03:30 EDT (07:30Z), never an hour early."""
    clock(datetime.datetime(2026, 3, 7, 23, 0))
    root = _repo(tmp_path, sleep=dict(TIGHT_NIGHT, schedule="22:00-02:30"))

    code, _out = _cmd(root, capsys, "sleep")

    assert (code, _record(root)["until"]) == (0, "2026-03-08T07:30:00+00:00")


def test_sleep_refuses_a_record_its_own_reader_would_not_trust(tmp_path, clock, capsys,
                                                               monkeypatch):
    import test_crew_autopilot_policy as policy  # pylint: disable=import-outside-toplevel
    clock(EVENING)
    root = _repo(tmp_path, sleep=TIGHT_NIGHT)
    monkeypatch.setattr(crew_sleep, "next_edge",
                        lambda _minute, when: when + datetime.timedelta(hours=30))
    before = policy._files(root)  # pylint: disable=protected-access

    code, out = _cmd(root, capsys, "sleep")

    assert (code, out.startswith("refused: the record sleep would write is not trusted"),
            policy._files(root) == before) == (2, True, True)  # pylint: disable=protected-access


def test_wake_writes_whole_seconds(tmp_path, clock, capsys):
    clock(datetime.datetime(2026, 10, 4, 23, 0, 12, 345678))
    root = _repo(tmp_path, sleep=_night())

    _cmd(root, capsys, "wake")

    assert [("." in _record(root)[key]) for key in ("at", "until")] == [False, False]


@pytest.fixture(name="troll")
def _troll(monkeypatch):
    if not hasattr(time, "tzset") or not os.path.exists("/usr/share/zoneinfo/Antarctica/Troll"):
        pytest.skip("needs time.tzset and the tz database")
    monkeypatch.setenv("TZ", "Antarctica/Troll")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_the_25_real_hour_backstop_holds_where_a_clock_change_is_two_hours(troll):
    """Antarctica/Troll falls back two hours (+02 to +00, 2026-10-25): 24
    wall-clock hours there are 26 real ones, past the 25-hour backstop."""
    at, until = datetime.datetime(2026, 10, 24, 12, 0), datetime.datetime(2026, 10, 25, 12, 0)
    record = dict(VALID, at=_iso(at), until=_iso(until))
    inside = dict(record, until=_iso(datetime.datetime(2026, 10, 25, 10, 0)))

    got = crew_sleep.read_manual(("ok", record), datetime.datetime(2026, 10, 24, 13, 0))
    kept = crew_sleep.read_manual(("ok", inside), datetime.datetime(2026, 10, 24, 13, 0))

    assert (got["kind"], "25 real" in got["warning"], kept["kind"]) == (
        "untrusted", True, "valid")


# --- L-0654: the sleep deploy override, nonprod only ---------------------------------

import crew_config  # noqa: E402  pylint: disable=wrong-import-position,wrong-import-order
import crew_state  # noqa: E402  pylint: disable=wrong-import-position,wrong-import-order


def _deploy_repo(tmp_path, monkeypatch, deploy="none", sleep=MISSING, prod=True):
    """A repo and machine layer armed for production (T-0072's rows), with
    `autopilot.deploy` = `deploy` and `autopilot.sleep` = `sleep`."""
    root = tmp_path / "repo"
    repo = {"autopilot": {"mode": "plan", "deploy": deploy},
            "guards": {"cloudGuard": "block"},
            "environments": {"nonProd": ["dev", "qa"], "prodUnattended": prod}}
    if sleep is not MISSING:
        repo["autopilot"]["sleep"] = sleep
    _write(root / ".crew" / "config.json", json.dumps(repo))
    machine = tmp_path / "machine" / "config.json"
    _write(machine, json.dumps({"guards": {"cloudGuard": "block"},
                                "environments": {"prodUnattended": prod}}))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(machine))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(machine))
    return str(root)


def _asks(root, cls, env=None):
    return crew_autopilot.deploy_allowed(root, env or ("qa" if cls == "nonProd" else "live"), cls)


def test_asleep_allows_nonprod(tmp_path, monkeypatch, clock):
    clock(NIGHT)
    root = _deploy_repo(tmp_path, monkeypatch, "none", {"schedule": "22:00-07:00",
                                                        "deploy": "nonprod"})

    got = _asks(root, "nonProd")

    assert (got["verdict"], got["deploy"], "asleep 22:00-07:00; day value none" in got["reason"]) == (
        "allow", "nonprod", True)


@pytest.mark.parametrize("when,schedule", [(DAY, "22:00-07:00"), (NIGHT, "25:00-07:00")],
                         ids=["awake", "unknown"])
def test_the_override_needs_the_sleep_state(tmp_path, monkeypatch, clock, when, schedule):
    clock(when)
    root = _deploy_repo(tmp_path, monkeypatch, "none", {"schedule": schedule, "deploy": "nonprod"})

    assert _asks(root, "nonProd")["verdict"] == "ask"


def test_asleep_production_never_allows(tmp_path, monkeypatch, clock):
    clock(NIGHT)
    root = _deploy_repo(tmp_path, monkeypatch, "all", {"schedule": "22:00-07:00"})

    got = _asks(root, "prod")
    nonprod = _asks(root, "nonProd")

    assert (got["verdict"], got["deploy"], "day value all" in got["reason"],
            nonprod["verdict"]) == ("ask", "nonprod", True, "allow")


@pytest.mark.parametrize("value", ["all", True, ["nonprod"], "NonProd", 1])
def test_a_refused_sleep_deploy_keeps_the_day_value(tmp_path, monkeypatch, clock, value):
    clock(DAY)
    root = _deploy_repo(tmp_path, monkeypatch, "none", {"schedule": "22:00-07:00",
                                                        "deploy": value})
    awake = crew_autopilot.settings(root)
    clock(NIGHT)
    asleep = crew_autopilot.settings(root)

    assert (asleep["deploy"], awake["deploy"],
            any("autopilot.sleep.deploy" in w and "never runs unattended asleep" in w
                for w in asleep["warnings"]),
            _asks(root, "prod")["verdict"], _asks(root, "nonProd")["verdict"]) == (
        "none", "none", True, "ask", "ask")


def test_asleep_with_an_incident_still_refuses(tmp_path, monkeypatch, clock):
    clock(NIGHT)
    root = _deploy_repo(tmp_path, monkeypatch, "none", {"schedule": "22:00-07:00",
                                                        "deploy": "nonprod"})
    _write(os.path.join(root, ".crew", "incident.json"), "{}")

    assert _asks(root, "nonProd")["verdict"] == "refuse"


def test_asleep_with_a_layer_that_cannot_be_told_asks(tmp_path, monkeypatch, clock):
    clock(NIGHT)
    root = _deploy_repo(tmp_path, monkeypatch, "none", {"schedule": "22:00-07:00",
                                                        "deploy": "nonprod"})
    _write(crew_config.GLOBAL_CONFIG_PATH, "{not json")

    assert _asks(root, "nonProd")["verdict"] == "ask"


def test_awake_production_is_unchanged(tmp_path, monkeypatch, clock):
    clock(DAY)
    root = _deploy_repo(tmp_path, monkeypatch, "all", {"schedule": "22:00-07:00",
                                                       "deploy": "nonprod"})

    got = _asks(root, "prod")

    assert (got["verdict"], got["deploy"], "asleep" in got["reason"]) == ("allow", "all", False)


# state x day value x override x class -> verdict, written out by hand.
_MATRIX = {
    # awake: the day value alone
    ("awake", "none", None): ("ask", "ask"), ("awake", "none", "nonprod"): ("ask", "ask"),
    ("awake", "nonprod", None): ("allow", "ask"), ("awake", "nonprod", "none"): ("allow", "ask"),
    ("awake", "all", None): ("allow", "allow"), ("awake", "all", "nonprod"): ("allow", "allow"),
    # asleep: the override, then `all` reads as `nonprod`
    ("asleep", "none", None): ("ask", "ask"), ("asleep", "none", "nonprod"): ("allow", "ask"),
    ("asleep", "nonprod", None): ("allow", "ask"), ("asleep", "nonprod", "none"): ("ask", "ask"),
    ("asleep", "all", None): ("allow", "ask"), ("asleep", "all", "nonprod"): ("allow", "ask"),
    ("asleep", "all", "none"): ("ask", "ask"),
    # unknown: neither rule, the day value stands (all included)
    ("unknown", "none", "nonprod"): ("ask", "ask"), ("unknown", "nonprod", "none"): ("allow", "ask"),
    ("unknown", "all", "nonprod"): ("allow", "allow"),
}


@pytest.mark.parametrize("state,day,override", sorted(_MATRIX, key=str))
def test_sleep_deploy_matrix(tmp_path, monkeypatch, clock, state, day, override):
    clock(DAY if state == "awake" else NIGHT)
    sleep = {"schedule": "25:00-07:00" if state == "unknown" else "22:00-07:00"}
    if override is not None:
        sleep["deploy"] = override
    root = _deploy_repo(tmp_path, monkeypatch, day, sleep)

    got = (_asks(root, "nonProd")["verdict"], _asks(root, "prod")["verdict"])

    assert got == _MATRIX[(state, day, override)]


def test_deploy_order_matches_crew_autopilot():
    assert crew_sleep.DEPLOY_ORDER == crew_autopilot.DEPLOY_VALUES


def test_a_manual_sleep_outside_the_window_never_loosens_deploy(tmp_path, monkeypatch, clock):
    clock(DAY)
    root = _deploy_repo(tmp_path, monkeypatch, "none", {"schedule": "22:00-07:00",
                                                        "deploy": "nonprod"})
    sleep = {"state": "asleep", "tightenOnly": True, "deploy": "nonprod", "applied": []}
    day = {}

    got = crew_sleep.deploy_overlay("none", sleep, day)
    tighter = crew_sleep.deploy_overlay("all", dict(sleep, deploy="none"), {})

    assert (got, day, tighter, _asks(root, "nonProd")["verdict"]) == (
        "none", {"deploy": "none"}, "none", "ask")
