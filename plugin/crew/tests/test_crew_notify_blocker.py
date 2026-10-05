"""crew_notify.py's `blocker` event: who sends it, and when (T-0060).

Four reasons, each with its own subject: `Approval waiting` and `Lane stalled`
/ `Lane state unknown` from `run-stop` at `/crew:autopilot`'s report, `Review
out of rounds` from `run-stop` (and `rounds_check`, the call the review
ledger makes once its harness-only wiring lands), and `Stop gate refused`
from `stop_outcome` (the call the two Stop gates make once theirs lands).

The fake Telegram, the scratch configs and the repo fixture are
test_crew_notify.py's, so nothing here reaches a real chat.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_notify
import review_ledger
from test_crew_notify import (  # noqa: F401  pylint: disable=unused-import
    CHAT, TOKEN_ENV, _isolate, _repo, _state, _telegram, _text)

TICKET = "T-0042"
BLOCKER = {"provider": "telegram", "tokenEnv": TOKEN_ENV, "chatId": CHAT,
           "events": ["blocker", "deploy", "question"]}


def _blocker_repo(tmp_path):
    return _repo(tmp_path, notify=dict(BLOCKER))


def _subject(telegram, index=-1):
    return _text(telegram, index).split(" [")[0]


# --- the review ledger: out of rounds -------------------------------------------------------

def _review(verdict, block):
    return {"verdict": verdict, "counts": {"BLOCK": block, "FIX": 1, "NIT": 0},
            "bundle_sha256": "b" * 64, "base": "c" * 40, "head": "c" * 40,
            "model_family": "gpt", "provider": "codex", "model": None, "failure_class": None}


def _rounds(root, *results):
    for verdict, block in results:
        _, number, _ = review_ledger.reserve(str(root), TICKET, "codex")
        review_ledger.record(str(root), TICKET, number, _review(verdict, block))


def test_out_of_rounds_with_block_sends_blocker(tmp_path, telegram):
    root = _blocker_repo(tmp_path)
    _rounds(root, ("FINDINGS", 0), ("FINDINGS", 2))

    word = crew_notify.rounds_check(str(root), TICKET)

    line = _text(telegram)
    assert (word, _subject(telegram), "out of review rounds, 2 BLOCK open" in line,
            line.endswith(f"-> /crew:plan {TICKET}"),
            telegram.requests[0]["form"]["disable_notification"]) == (
                "sent", "Review out of rounds", True, True, "false")


def test_non_final_round_with_block_sends_nothing(tmp_path, telegram):
    root = _blocker_repo(tmp_path)
    _rounds(root, ("FINDINGS", 3))

    assert (crew_notify.rounds_check(str(root), TICKET), telegram.requests) == ("filtered", [])


@pytest.mark.parametrize("last", [("CLEAN", 0), ("FINDINGS", 0)], ids=["clean", "fix-only"])
def test_final_round_clean_or_fix_only_sends_nothing(tmp_path, telegram, last):
    root = _blocker_repo(tmp_path)
    _rounds(root, ("FINDINGS", 1), last)

    assert (crew_notify.rounds_check(str(root), TICKET), telegram.requests) == ("filtered", [])


def test_rounds_check_refunded_final_round_is_not_out_of_rounds(tmp_path, telegram):
    """A tool-failure round is refunded: it does not spend the budget."""
    root = _blocker_repo(tmp_path)
    _rounds(root, ("FINDINGS", 1))
    _, number, _ = review_ledger.reserve(str(root), TICKET, "codex")
    review_ledger.record(str(root), TICKET, number,
                         dict(_review("INCOMPLETE", 1), failure_class="tool"))

    assert (crew_notify.rounds_check(str(root), TICKET), telegram.requests) == ("filtered", [])


def test_rounds_check_never_raises_on_an_unreadable_ledger(tmp_path, telegram):
    root = _blocker_repo(tmp_path)
    path = pathlib.Path(review_ledger.ledger_path(str(root), TICKET))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert (crew_notify.rounds_check(str(root), TICKET), telegram.requests) == ("filtered", [])


# auto-replan-cap (T-0060 port review FIX): the cap turns a BLOCK-carrying
# accept-review stop into this one, and it is still the owner's.
@pytest.mark.parametrize("phase", ["accept-review", "replan", "auto-replan-cap"])
def test_run_stop_out_of_rounds_phases_send_rounds(tmp_path, telegram, phase):
    root = _blocker_repo(tmp_path)
    _rounds(root, ("FINDINGS", 1), ("FINDINGS", 1))

    word = crew_notify.run_stop(str(root), TICKET, phase, "round 2 is FINDINGS")

    assert (word, _subject(telegram)) == ("sent", "Review out of rounds")


def test_run_stop_accept_review_inside_budget_sends_nothing(tmp_path, telegram):
    root = _blocker_repo(tmp_path)
    _rounds(root, ("FINDINGS", 1))

    word = crew_notify.run_stop(str(root), TICKET, "accept-review", "round 1 is FINDINGS")

    assert (word, telegram.requests) == ("filtered", [])


# --- run-stop: approval waiting -------------------------------------------------------------

@pytest.mark.parametrize("reason", ["the plan has no approval receipt",
                                    "the approval receipt is stale: plan.md changed"])
def test_run_stop_approve_sends_blocker(tmp_path, telegram, reason):
    root = _blocker_repo(tmp_path)

    word = crew_notify.run_stop(str(root), TICKET, "approve", reason)

    line = _text(telegram)
    assert (word, _subject(telegram), "plan waiting on approval" in line,
            line.endswith(f"-> /crew:approve {TICKET}")) == (
                "sent", "Approval waiting", True, True)


def test_run_stop_approve_twice_in_a_run_sends_once(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    words = [crew_notify.run_stop(str(root), TICKET, "approve", "no receipt") for _ in range(2)]

    assert (words, len(telegram.requests)) == (["sent", "deduped"], 1)


# Every stop slug crew_autopilot.py's `next` prints that this ticket does not
# name (accept-review and replan ping only out of rounds, above).
_QUIET_PHASES = ("brainstorm", "spec", "plan", "open-questions", "implement", "review",
                 "refresh", "stale-after-review", "done", "handover-elsewhere", "invalid",
                 "max-phases", "no-progress", "unknown", "")


@pytest.mark.parametrize("phase", _QUIET_PHASES)
def test_run_stop_other_phases_send_nothing(tmp_path, telegram, phase):
    root = _blocker_repo(tmp_path)

    word = crew_notify.run_stop(str(root), TICKET, phase, "some reason")

    assert (word, telegram.requests) == ("filtered", [])


def test_run_stop_cli_prints_its_word_and_exits_0(tmp_path):
    root = _blocker_repo(tmp_path)
    script = pathlib.Path(crew_notify.__file__)
    env = dict(os.environ, HOME=str(tmp_path / "home"),
               CREW_NOTIFY_TELEGRAM_BASE="http://127.0.0.1:9")

    runs = [subprocess.run([sys.executable, str(script), "run-stop", "--root", str(root),
                            "--ticket", TICKET, "--phase", phase, "--reason", "r"],
                           capture_output=True, text=True, check=False, timeout=60, env=env)
            for phase in ("done", "approve")]

    assert [(run.returncode, run.stdout.strip() in ("filtered", "off", "missing-credentials")
             or run.stdout.strip().startswith("failed:")) for run in runs] == [(0, True)] * 2


# --- run-stop: lane died or stalled ---------------------------------------------------------

def _holds(monkeypatch, answer=None, error=None):
    """Stub crew_inflight.holds; returns the list of calls it saw."""
    import crew_inflight  # pylint: disable=import-outside-toplevel
    calls = []

    def fake(root, ticket, runner=None, session=None, wait=None):  # pylint: disable=unused-argument
        calls.append((ticket, runner))
        if error is not None:
            raise error
        return dict({"ticket": ticket, "runner": "", "since": "", "heartbeat_at": "",
                     "worktree": "", "why": "", "clear": ""}, **answer)

    monkeypatch.setattr(crew_inflight, "holds", fake)
    return calls


_CLEAR = ('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_inflight.py" clear --root . '
          f'--ticket {TICKET} --by <you> --reason "<why>"')


def test_lane_stale_sends_blocker(tmp_path, telegram, monkeypatch):
    root = _blocker_repo(tmp_path)
    calls = _holds(monkeypatch, {"state": "stale", "runner": "lane",
                                 "since": "2026-10-04T01:00:00+00:00", "clear": _CLEAR,
                                 "why": "holder pid 4242 is gone"})

    word = crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: stale - ...")

    line = _text(telegram)
    assert (word, calls, _subject(telegram),
            "lane stalled: lane since 2026-10-04T01:00:00+00:00" in line,
            line.endswith(f"-> {_CLEAR}")) == (
                "sent", [(TICKET, "autopilot")], "Lane stalled", True, True)


def test_lane_unknown_sends_lane_unknown(tmp_path, telegram, monkeypatch):
    root = _blocker_repo(tmp_path)
    _holds(monkeypatch, {"state": "unknown", "why": "heartbeat in the future by 130s"})

    word = crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: unknown")

    line = _text(telegram)
    assert (word, _subject(telegram), "lane state unknown: heartbeat in the future" in line,
            line.endswith("-> /crew:status")) == ("sent", "Lane state unknown", True, True)


@pytest.mark.parametrize("error", [ImportError("no crew_inflight"), RuntimeError("boom")],
                         ids=["import-error", "exception"])
def test_lane_import_error_sends_lane_unknown(tmp_path, telegram, monkeypatch, error):
    root = _blocker_repo(tmp_path)
    _holds(monkeypatch, error=error)

    word = crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: unknown")

    assert (word, _subject(telegram)) == ("sent", "Lane state unknown")


def test_lane_module_missing_sends_lane_unknown(tmp_path, telegram, monkeypatch):
    """crew_inflight cannot be imported at all: unknown, never quiet."""
    root = _blocker_repo(tmp_path)
    monkeypatch.setitem(sys.modules, "crew_inflight", None)

    word = crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: unknown")

    assert (word, _subject(telegram)) == ("sent", "Lane state unknown")


@pytest.mark.parametrize("state", ["live", "mine", "free", "elsewhere"])
def test_lane_live_mine_free_elsewhere_send_nothing(tmp_path, telegram, monkeypatch, state):
    """A live runner, or one driving the ticket from another checkout, is work
    in progress, not a blocker (T-0049's review: elsewhere sends nothing)."""
    root = _blocker_repo(tmp_path)
    _holds(monkeypatch, {"state": state, "runner": "lane", "since": "2026-10-04T01:00:00Z"})

    word = crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: live")

    assert (word, telegram.requests) == ("filtered", [])


def test_lane_same_stale_marker_sends_once_per_window(tmp_path, telegram, monkeypatch):
    root = _blocker_repo(tmp_path)
    _holds(monkeypatch, {"state": "stale", "runner": "autopilot",
                         "since": "2026-10-04T01:00:00+00:00", "clear": _CLEAR,
                         "why": "no heartbeat for 1900s (TTL 1800s)"})

    words = [crew_notify.run_stop(str(root), TICKET, "in-flight", f"in-flight: stale {n}")
             for n in range(3)]

    assert (words, len(telegram.requests)) == (["sent", "deduped", "deduped"], 1)


def test_lane_unknown_with_a_moving_duration_sends_once(tmp_path, telegram, monkeypatch):
    """The same unknown seen again a minute later is the same message."""
    root = _blocker_repo(tmp_path)
    words = []
    for skew in (130, 190):
        _holds(monkeypatch, {"state": "unknown", "why": f"heartbeat in the future by {skew}s"})
        words.append(crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: unknown"))

    assert (words, len(telegram.requests)) == (["sent", "deduped"], 1)


def test_run_stop_writes_nothing_under_inflight(tmp_path, telegram):
    """The real crew_inflight, no marker: `free`, nothing sent, nothing created."""
    root = _blocker_repo(tmp_path)
    import crew_inflight  # pylint: disable=import-outside-toplevel
    folder = crew_inflight.inflight_dir(str(root))

    word = crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: ?")

    assert (word, telegram.requests, os.path.exists(folder)) == ("filtered", [], False)


# --- the Stop gates: refused twice ----------------------------------------------------------

def _stop_payload(prompt="p-1", session="s-1", stamp=None):
    out = {"session_id": session, "hook_event_name": "Stop", "stop_hook_active": False,
           "transcript_path": "/nonexistent/t.jsonl", "cwd": "."}
    if prompt is not None:
        out["prompt_id"] = prompt
    if stamp is not None:
        out["extra"] = stamp
    return json.dumps(out).encode()


def test_first_refusal_sends_nothing(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    word = crew_notify.stop_outcome(str(root), "verify", True, _stop_payload("p-1"))

    assert (word, telegram.requests) == ("counted", [])


def test_second_refusal_sends_one_blocker(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    words = [crew_notify.stop_outcome(str(root), "verify", True, _stop_payload(prompt))
             for prompt in ("p-1", "p-2", "p-3")]

    line = _text(telegram)
    assert (words, len(telegram.requests), _subject(telegram),
            "verify gate refused twice" in line, line.endswith("-> /crew:status")) == (
                ["counted", "sent", "deduped"], 1, "Stop gate refused", True, True)


def test_a_long_refusal_streak_pings_once(tmp_path, telegram):
    """T-0060 port review FIX: the streak keeps its first refusal as its
    identity past the ten-id window, so refusal 12 is not a new episode."""
    root = _blocker_repo(tmp_path)

    words = [crew_notify.stop_outcome(str(root), "verify", True, _stop_payload(f"p-{n}"))
             for n in range(1, 15)]

    assert (words[:2], set(words[2:]), len(telegram.requests)) == (
        ["counted", "sent"], {"deduped"}, 1), words


def test_pass_between_refusals_resets(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    words = [crew_notify.stop_outcome(str(root), "audit", refused, _stop_payload(prompt))
             for refused, prompt in ((True, "p-1"), (False, "p-2"), (True, "p-3"))]

    assert (words, telegram.requests) == (["counted", "cleared", "counted"], [])


def test_twin_flavours_count_one_refusal(tmp_path, telegram):
    """Both Windows flavours run every Stop hook: one payload seen twice is
    one refusal, whatever bytes each shell added around it."""
    root = _blocker_repo(tmp_path)
    raw = _stop_payload("p-1")

    words = [crew_notify.stop_outcome(str(root), "verify", True, body)
             for body in (raw, b"\xef\xbb\xbf" + raw + b"\r\n")]

    assert (words, telegram.requests) == (["counted", "twin"], [])


def test_no_prompt_id_uses_payload_digest(tmp_path, telegram):
    root = _blocker_repo(tmp_path)
    first = _stop_payload(None, stamp=1)

    words = [crew_notify.stop_outcome(str(root), "verify", True, body)
             for body in (first, b"\xef\xbb\xbf" + first, _stop_payload(None, stamp=2))]

    assert (words, _subject(telegram)) == (["counted", "twin", "sent"], "Stop gate refused")


def test_refusals_count_per_gate_and_session(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    words = [crew_notify.stop_outcome(str(root), gate, True, _stop_payload(prompt, session))
             for gate, prompt, session in (("verify", "p-1", "s-1"), ("audit", "p-2", "s-1"),
                                           ("verify", "p-3", "s-2"))]

    assert (words, telegram.requests) == (["counted"] * 3, [])


def test_refusal_key_names_the_active_ticket(tmp_path, telegram):
    root = _blocker_repo(tmp_path)  # INDEX.md names T-0042 (crew_ticket.resolve_active)

    crew_notify.stop_outcome(str(root), "verify", True, _stop_payload("p-1"))
    stops = json.loads((_state(root) / "stops.json").read_text(encoding="utf-8"))

    assert list(stops) == [f"verify|s-1|{TICKET}"]


def test_stop_outcome_never_raises_on_garbage(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    words = [crew_notify.stop_outcome(str(root), "verify", True, body)
             for body in (b"", b"\x00garbage", b"[]")]

    # A payload that is not JSON still counts: the gate refused, whatever it read.
    assert words == ["counted", "sent", "deduped"]


def test_stop_unknown_gate_is_refused(tmp_path, telegram):
    root = _blocker_repo(tmp_path)

    assert crew_notify.stop_outcome(str(root), "smoke", True, _stop_payload()) == "failed:usage"


def test_stop_cli_reads_stdin_and_exits_0(tmp_path):
    root = _blocker_repo(tmp_path)
    script = pathlib.Path(crew_notify.__file__)
    env = dict(os.environ, HOME=str(tmp_path / "home"),
               CREW_NOTIFY_TELEGRAM_BASE="http://127.0.0.1:9")

    runs = [subprocess.run([sys.executable, str(script), "stop", "--root", str(root),
                            "--gate", "verify", flag], input=_stop_payload(prompt),
                           capture_output=True, check=False, timeout=60, env=env)
            for flag, prompt in (("--refused", "p-1"), ("--passed", "p-2"),
                                 ("--refused", "p-3"))]

    assert [(run.returncode, run.stdout.decode().strip()) for run in runs] == [
        (0, "counted"), (0, "cleared"), (0, "counted")]


# --- review round 1 (FIX 1): no local detail reaches the chat ------------------------------

@pytest.mark.parametrize("why,category", [
    ("marker unreadable: [Errno 13] Permission denied: '/home/alice/repo/.git/crew/inflight/T-0042"
     ".json'", "marker unreadable"),
    ("marker is not valid JSON: Expecting value: line 1 column 1 (char 0)", "marker unreadable"),
    ("lock /home/alice/repo/.git/crew/inflight/T-0042.json.lock held for over 5s; if no "
     "crew_inflight.py is running, a process died holding it", "lock held"),
    ("inflight directory: [Errno 5] Input/output error: '/home/alice/x'", "could not read state"),
    ("/home/alice/repo/.git/crew/inflight is not a directory", "could not read state"),
    ("git cannot name <git-common-dir>", "could not read state"),
    ("could not tell: OSError(13, 'Permission denied')", "could not read state"),
    ("heartbeat in the future by 130s", "heartbeat in the future"),
])
def test_lane_unknown_sends_a_category_never_a_path(tmp_path, telegram, monkeypatch, why,
                                                   category):
    root = _blocker_repo(tmp_path)
    _holds(monkeypatch, {"state": "unknown", "why": why})

    crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: unknown")

    line = _text(telegram)
    reason = line.split(f"{TICKET} (implement) ", 1)[1].split(" -> ")[0]
    assert (reason, "/home" in line, "alice" in line, "Errno" in line, "(" in reason) == (
        f"lane state unknown: {category} (detail: /crew:status)", False, False, False, True)


def test_lane_exception_text_never_reaches_the_chat(tmp_path, telegram, monkeypatch):
    root = _blocker_repo(tmp_path)
    _holds(monkeypatch, error=RuntimeError("/home/alice/secret-path exploded"))

    crew_notify.run_stop(str(root), TICKET, "in-flight", "in-flight: unknown")

    line = _text(telegram)
    assert ("alice" in line, "RuntimeError" in line,
            "lane state unknown: could not read state" in line) == (False, False, True)


# --- review round 1 (FIX 2): a new episode is not deduped as the old one -------------------

def _plan(root, text):
    path = root / ".work" / "tickets" / TICKET / "plan.md"
    path.write_text(text, encoding="utf-8")


def test_approval_same_plan_is_deduped_new_plan_sends(tmp_path, telegram):
    """approve -> replan -> approve again inside realertHours: the second plan
    is a new episode, so it pings; the same plan seen twice does not."""
    root = _blocker_repo(tmp_path)
    _plan(root, "# plan v1\n")
    words = [crew_notify.run_stop(str(root), TICKET, "approve", "no receipt") for _ in range(2)]
    _plan(root, "# plan v2 - the successor\n")
    words.append(crew_notify.run_stop(str(root), TICKET, "approve", "no receipt"))

    assert (words, len(telegram.requests), _text(telegram, 0) == _text(telegram, 1)) == (
        ["sent", "deduped", "sent"], 2, True)


def test_rounds_same_round_is_deduped_a_later_round_sends(tmp_path, telegram, monkeypatch):
    """A second out-of-rounds (a successor plan spent too) is a new episode."""
    root = _blocker_repo(tmp_path)
    states = []

    def status(_root, ticket):
        return states[-1] | {"ticket": ticket}

    monkeypatch.setattr(review_ledger, "status", status)
    words = []
    for number in (2, 2, 4):
        states.append({"rounds_spent": 2, "budget": 2, "successors": [],
                       "rounds": [{"round": number, "status": "completed",
                                   "counts": {"BLOCK": 1}}]})
        words.append(crew_notify.rounds_check(str(root), TICKET))

    assert (words, len(telegram.requests)) == (["sent", "deduped", "sent"], 2)


def test_gate_new_refusal_streak_after_a_pass_sends_again(tmp_path, telegram):
    root = _blocker_repo(tmp_path)
    steps = ((True, "p-1"), (True, "p-2"), (False, "p-3"), (True, "p-4"), (True, "p-5"))

    words = [crew_notify.stop_outcome(str(root), "verify", refused, _stop_payload(prompt))
             for refused, prompt in steps]

    assert (words, len(telegram.requests)) == (
        ["counted", "sent", "cleared", "counted", "sent"], 2)


# --- review round 1 (NITs) ---------------------------------------------------------------

@pytest.mark.parametrize("ticket", ["../etc", "T 1", "", "a/b"])
def test_run_stop_bad_ticket_sends_nothing(tmp_path, telegram, ticket):
    root = _blocker_repo(tmp_path)

    assert (crew_notify.run_stop(str(root), ticket, "approve", "r"), telegram.requests) == (
        "failed:usage", [])


def test_run_stop_logs_the_reason_to_stderr_only(tmp_path, telegram, capsys):
    root = _blocker_repo(tmp_path)

    crew_notify.run_stop(str(root), TICKET, "approve", "receipt stale: plan.md changed")

    assert ("receipt stale: plan.md changed" in capsys.readouterr().err,
            "receipt stale" in _text(telegram)) == (True, False)


def test_stops_json_prunes_old_keys(tmp_path, telegram, monkeypatch):
    root = _blocker_repo(tmp_path)
    crew_notify.stop_outcome(str(root), "verify", True, _stop_payload("p-1", session="old"))
    later = crew_notify.time.time() + crew_notify.PRUNE_SECONDS + 60
    monkeypatch.setattr(crew_notify.time, "time", lambda: later)

    crew_notify.stop_outcome(str(root), "verify", True, _stop_payload("p-2", session="new"))
    stops = json.loads((_state(root) / "stops.json").read_text(encoding="utf-8"))

    assert sorted(stops) == [f"verify|new|{TICKET}"]
