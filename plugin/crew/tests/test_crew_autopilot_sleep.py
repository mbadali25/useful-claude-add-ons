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

import context  # pylint: disable=unused-import
import crew_autopilot
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


@pytest.mark.parametrize("key", ["deploy", "reviewPolicy", "notifyHold"])
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


@pytest.mark.parametrize("key", ["deploy", "reviewPolicy"])
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

@pytest.mark.parametrize("deploy", ["none", "nonprod", "all"])
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
    (_night(), NIGHT, "sleep=asleep schedule=22:00-07:00 approval=self questions=self"),
    (_night(questions=None), DAY,
     "sleep=awake schedule=22:00-07:00 approval=self questions=-"),
    (_night(schedule=None), NIGHT, "sleep=off schedule=none approval=self questions=self"),
    (_night(schedule="22"), NIGHT,
     "sleep=unknown schedule=none approval=self questions=self applied=-"),
    (MISSING, NIGHT, "sleep=off schedule=none approval=- questions=-"),
])
def test_settings_cli_prints_the_sleep_line(tmp_path, clock, capsys, sleep, now, line):
    clock(now)
    root = _repo(tmp_path, sleep=sleep)

    crew_autopilot.main(["settings", "--root", str(root)])
    lines = capsys.readouterr().out.splitlines()
    crew_autopilot.main(["settings", "--root", str(root), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert (lines[2], data["day"], data["sleep"]["state"]) == (
        line, {"approval": "risk", "questions": "risk"}, line.split()[0][len("sleep="):])


def test_settings_cli_prints_unknown_for_an_unreadable_config(tmp_path, capsys):
    root = _repo(tmp_path, sleep=_night())
    _write(root / ".crew" / "config.json", "[")

    crew_autopilot.main(["settings", "--root", str(root)])

    assert capsys.readouterr().out.splitlines()[2] == (
        "sleep=unknown schedule=none approval=- questions=- applied=-")


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
