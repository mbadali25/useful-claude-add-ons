"""T-0074: autopilot rejects an out-of-rounds BLOCK review and replans, capped.

    python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py -q

`autopilot.maxAutoReplans` (default 0, off) is the switch and the cap in one.
With it at 1 or more, armed, and `approval_policy` allowing the successor
plan, a final review round that is FINDINGS with a BLOCK is rejected by
`crew_autopilot.py auto-reject` under the fixed name `AUTO_REJECT_BY`, and
`next` names `/crew:plan` for a successor plan instead of stopping. Anything
else -- including a value it cannot read -- is today's stop. Autopilot never
accepts a BLOCK at any setting. Every repository is built under tmp_path;
nothing touches the real one or ~/.claude.
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
T = "T-1"
BLOCK_LINE = "BLOCK|src/app.py:3|the guard reads the wrong field"
FIX_LINE = "FIX|src/app.py:9|name the refusal"
NIT_LINE = "NIT|src/app.py:1|typo"
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


def _repo(tmp_path, replans=2, approval="self", allow=True, risk="low", armed=True):
    """One valid, active, user-approved ticket. `replans` is written verbatim as
    `autopilot.maxAutoReplans` (MISSING omits it)."""
    root = make_repo(tmp_path, mode="off")
    block = {"mode": "plan" if armed else "off", "approval": approval}
    if replans is not MISSING:
        block["maxAutoReplans"] = replans
    _write(root / ".crew" / "config.json",
           json.dumps({"scope": {"mode": "off", "allowCliApproval": allow},
                       "autopilot": block}))
    folder = root / ".work" / "tickets" / T
    _write(folder / "direction.md", "go\n")
    _write(folder / "spec.md", _spec_text(risk))
    _write(folder / "plan.md", PLAN.format(files="src/app.py"))
    _write(root / ".work" / "INDEX.md", f"{T} | ready | low | r | title\n")
    crew_ticket.activate(str(root), T)
    approve_as_user(root, T)
    return root


def _row(number, **over):
    row = {"round": number, "status": "completed", "provider": "codex", "model": None,
           "verdict": "FINDINGS", "bundle_sha256": "a" * 64, "base": "HEAD",
           "model_family": "gpt", "counts": {"BLOCK": 1, "FIX": 1, "NIT": 1},
           "findings": [BLOCK_LINE, FIX_LINE, NIT_LINE], "refunded": False,
           "ignored_lines": 0}
    for key, value in over.items():
        if value is MISSING:
            row.pop(key, None)
        else:
            row[key] = value
    return row


def _successor(letter, after, by="Owner"):
    return {"plan_sha256": letter * 64, "approved_at": "2026-10-01T00:00:00Z",
            "approved_by": by, "at": "2026-10-01T00:00:00Z", "after_round": after}


def _ledger(root, rounds=None, state="REVIEWED", successors=None, rejected=None, raw=None):
    """The ledger, written directly. Default: two completed rounds, the last a
    codex FINDINGS round with one BLOCK, so no round is left."""
    path = review_ledger.ledger_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"ticket": T, "budget": 2, "refused": [], "state": state, "receipt": None,
            "rounds": rounds if rounds is not None else [_row(1), _row(2)]}
    if successors is not None:
        data["successors"] = successors
    if rejected is not None:
        data["rejected"] = rejected
    _write(path, raw if raw is not None else json.dumps(data))
    return path


def _bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _cli(root, *args):
    return subprocess.run([sys.executable, _SCRIPT] + list(args) + ["--root", str(root)],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def _next(root):
    return crew_autopilot.next_phase(str(root), T)


# --- step 1: the setting -------------------------------------------------------

def test_setting_defaults_to_zero(tmp_path):
    got = crew_autopilot.settings(str(_repo(tmp_path, replans=MISSING)))

    assert (got["maxAutoReplans"], [w for w in got["warnings"] if "maxAutoReplans" in w]) == (
        0, [])


@pytest.mark.parametrize("value", [True, "2", 2.5, -1, None])
def test_setting_garbage_reads_zero_with_warning(tmp_path, value):
    got = crew_autopilot.settings(str(_repo(tmp_path, replans=value)))

    assert (got["maxAutoReplans"], [w for w in got["warnings"] if "maxAutoReplans" in w]) == (
        0, [f"autopilot.maxAutoReplans is {value!r}, not a non-negative integer; using 0 "
            "(off: a BLOCK round stops for the owner)"])


def test_setting_reads_a_positive_integer(tmp_path):
    assert crew_autopilot.settings(str(_repo(tmp_path, replans=3)))["maxAutoReplans"] == 3


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_unreadable_config_reads_zero(tmp_path, text):
    root = _repo(tmp_path)
    _write(root / ".crew" / "config.json", text)

    got = crew_autopilot.settings(str(root))

    assert (got["maxAutoReplans"], got["armed"]) == (0, False)


def test_settings_cli_first_line_names_the_key(tmp_path, capsys):
    root = _repo(tmp_path, replans=2)
    capsys.readouterr()

    code = crew_autopilot.main(["settings", "--root", str(root)])
    lines = capsys.readouterr().out.splitlines()

    # The first line, beside maxPhases: the second line is a sabotage anchor
    # (sabotage_autopilot.py "the settings text drops the policies").
    assert (code, lines[:2]) == (0, ["mode=plan maxPhases=12 deploy=none maxAutoReplans=2",
                                     "approval=self questions=risk"])


def test_settings_cli_json_carries_the_key(tmp_path, capsys):
    root = _repo(tmp_path, replans=1)
    capsys.readouterr()

    crew_autopilot.main(["settings", "--root", str(root), "--json"])

    assert json.loads(capsys.readouterr().out)["maxAutoReplans"] == 1


# --- step 2: the policy ----------------------------------------------------------

def test_policy_allows_an_out_of_rounds_block_round(tmp_path):
    root = _repo(tmp_path)
    _ledger(root)

    got = crew_autopilot.auto_replan_policy(str(root), T)

    assert (got["allow"], got["used"], got["cap"], got["round"], got["blocks"],
            got["fixes"]) == (True, 0, 2, 2, [BLOCK_LINE], [FIX_LINE])


def test_policy_allows_a_kimi_round_under_risk_low(tmp_path):
    root = _repo(tmp_path, approval="risk", risk="low")
    _ledger(root, rounds=[_row(1), _row(2, provider="kimi", model_family="kimi")])

    assert crew_autopilot.auto_replan_policy(str(root), T)["allow"] is True


def _set_state(state):
    def change(root):
        _ledger(root, state=state)
    return change


def _set_rows(**over):
    def change(root):
        _ledger(root, rounds=[_row(1), _row(2, **over)])
    return change


def _corrupt(root):
    _ledger(root, raw="{not json")


def _one_round_left(root):
    _ledger(root, rounds=[_row(1)])


def _cap_reached(root):
    _ledger(root, rounds=[_row(n) for n in range(1, 7)],
            successors=[_successor("b", 2), _successor("c", 4, by="autopilot:self")])


def _reserved(root):
    _ledger(root, rounds=[_row(1), {"round": 2, "status": "reserved", "provider": "codex",
                                    "model": None}], state="IN_REVIEW")


# (id, repo kwargs, ledger change, a word the refusal holds)
REFUSALS = [
    ("not-armed", {"armed": False}, None, "autopilot.mode"),
    ("key-zero", {"replans": 0}, None, "maxAutoReplans is 0"),
    ("approval-human", {"approval": "human"}, None, "could not be self-approved"),
    ("no-cli-approval", {"allow": False}, None, "could not be self-approved"),
    ("risk-high", {"approval": "risk", "risk": "high"}, None, "could not be self-approved"),
    ("in-review", {}, _set_state("IN_REVIEW"), "not REVIEWED"),
    ("accepted", {}, _set_state("ACCEPTED"), "not REVIEWED"),
    ("needs-replan", {}, _set_state("NEEDS_REPLAN"), "not REVIEWED"),
    ("corrupt", {}, _corrupt, "unreadable"),
    ("reserved", {}, _reserved, "not REVIEWED"),
    ("incomplete", {}, _set_rows(verdict="INCOMPLETE"), "not FINDINGS"),
    ("zero-block", {}, _set_rows(counts={"BLOCK": 0, "FIX": 1, "NIT": 1},
                                 findings=[FIX_LINE, NIT_LINE]), "no BLOCK"),
    ("block-bool", {}, _set_rows(counts={"BLOCK": True, "FIX": 1, "NIT": 1}), "could not tell"),
    ("block-str", {}, _set_rows(counts={"BLOCK": "1", "FIX": 1, "NIT": 1}), "could not tell"),
    ("counts-missing", {}, _set_rows(counts=MISSING), "could not tell"),
    ("findings-missing", {}, _set_rows(findings=MISSING), "could not tell"),
    ("findings-short", {}, _set_rows(counts={"BLOCK": 2, "FIX": 1, "NIT": 1}), "could not tell"),
    ("findings-broken", {}, _set_rows(findings=[BLOCK_LINE + "\nFIX|x"]), "could not tell"),
    ("round-left", {}, _one_round_left, "round(s) left"),
    ("provider-claude", {}, _set_rows(provider="claude"), "same family"),
    ("provider-copilot", {}, _set_rows(provider="copilot"), "unknown provider"),
    ("family-missing", {}, _set_rows(model_family=MISSING), "could not tell"),
    ("family-claude", {}, _set_rows(model_family="claude"), "same family"),
    ("cap-reached", {}, _cap_reached, "maxAutoReplans (2) reached"),
]


@pytest.mark.parametrize("kwargs,change,word", [r[1:] for r in REFUSALS],
                         ids=[r[0] for r in REFUSALS])
def test_auto_reject_refusals_write_nothing(tmp_path, kwargs, change, word):
    root = _repo(tmp_path, **kwargs)
    path = _ledger(root)
    if change is not None:
        change(root)
    before = _bytes(path)

    done = _cli(root, "auto-reject", "--ticket", T)

    assert (done.returncode, done.stdout.startswith("refused: "), word in done.stdout,
            _bytes(path) == before) == (2, True, True, True), done.stdout


def test_policy_that_raises_could_not_tell(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _ledger(root)

    def boom(*_args, **_kwargs):
        raise OSError("disk gone")
    monkeypatch.setattr(review_ledger, "load", boom)

    got = crew_autopilot.auto_replan_policy(str(root), T)

    assert (got["allow"], "could not tell" in got["reason"], "disk gone" in got["reason"]) == (
        False, True, True)


FAMILY_TABLE = [("codex", "gpt"), ("kimi", "kimi"), ("codex", "claude"), ("codex", " Claude "),
                ("claude", "claude"), ("claude", "gpt"), ("copilot", "gpt"), ("", "gpt"),
                (None, "gpt"), ("codex", ""), ("codex", None), ("kimi", "   ")]


@pytest.mark.parametrize("provider,family", FAMILY_TABLE)
def test_family_rule_matches_review_ledger(tmp_path, provider, family):
    """The policy's family verdict equals the ledger's auto-accept family
    verdict on a 0-BLOCK copy of the same row: the two cannot drift."""
    root = _repo(tmp_path)
    row = _row(2, provider=provider, model_family=family)
    _ledger(root, rounds=[_row(1), row])
    clean = dict(row, counts={"BLOCK": 0, "FIX": 1, "NIT": 1}, findings=[FIX_LINE, NIT_LINE],
                 webtest_open=0)

    ours = crew_autopilot.auto_replan_policy(str(root), T)
    theirs = review_ledger.auto_accept_refusal(
        {"state": "REVIEWED", "rounds": [_row(1), clean]}, T)

    assert ours["allow"] is (theirs is None)


# --- step 3: the writer -----------------------------------------------------------

def test_auto_reject_moves_ledger_and_names_the_policy(tmp_path):
    root = _repo(tmp_path)
    path = _ledger(root)

    done = _cli(root, "auto-reject", "--ticket", T)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    assert (done.returncode, done.stdout.splitlines(), data["state"], data["rejected"]["by"],
            data["rejected"]["round"]) == (
        0, [f"auto-rejected {T}: round 2, 1 BLOCK / 1 FIX, replan 1 of 2", BLOCK_LINE,
            FIX_LINE], "NEEDS_REPLAN", crew_autopilot.AUTO_REJECT_BY, 2)


def test_auto_reject_name_is_a_constant_no_flag_sets():
    assert (crew_autopilot.AUTO_REJECT_BY,
            "--by" in crew_autopilot.auto_reject.__code__.co_varnames) == (
        "autopilot (policy: autopilot.maxAutoReplans)", False)


def test_auto_reject_ledger_error_is_a_refusal(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _ledger(root)

    def refuse(*_args):
        raise review_ledger.LedgerError("T-1 is ACCEPTED; --reject does not change that state")
    monkeypatch.setattr(review_ledger, "reject", refuse)
    capsys.readouterr()

    code = crew_autopilot.main(["auto-reject", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out) == (
        2, "refused: T-1 is ACCEPTED; --reject does not change that state\n")


def test_auto_reject_crash_is_a_refusal(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _ledger(root)

    def boom(*_args):
        raise RuntimeError("boom")
    monkeypatch.setattr(crew_autopilot, "auto_reject", boom)
    capsys.readouterr()

    code = crew_autopilot.main(["auto-reject", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out.startswith("refused: ")) == (1, True)


def test_autopilot_still_never_accepts_a_block(tmp_path):
    with open(_SCRIPT, encoding="utf-8") as handle:
        source = handle.read()

    assert ("review_ledger.accept(" in source, "review_ledger.auto_accept(" in source) == (
        False, False)


# --- step 4: routing in next ------------------------------------------------------

AUTO_COMMAND = (f"python3 -B ${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/crew_autopilot.py "
                f"auto-reject --root . --ticket {T}")


# `_review_phase`'s reason on main before T-0074, verbatim.
TODAYS_ACCEPT_REVIEW = (
    "round 2 is FINDINGS; review_ledger.py --auto-accept refuses it (round 2 has 1 BLOCK "
    "finding(s); a BLOCK is never auto-accepted): the owner accepts with review_ledger.py "
    "--accept --by <owner>, or fixes then /crew:review")


def test_default_zero_changes_nothing(tmp_path):
    off = _repo(tmp_path / "off", replans=MISSING)
    _ledger(off)
    on = _repo(tmp_path / "on", replans=2, approval="human")
    _ledger(on)

    got, refused = _next(off), _next(on)

    assert (got["phase"], got["stop"], got["command"]) == ("accept-review", True, "")
    assert got["reason"] == refused["reason"] == TODAYS_ACCEPT_REVIEW


def test_next_names_auto_reject_when_policy_allows(tmp_path):
    root = _repo(tmp_path)
    _ledger(root)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"],
            got["command"].endswith(f"crew_autopilot.py auto-reject --root . --ticket {T}")) == (
        "auto-replan", False, AUTO_COMMAND, True)


def test_status_reads_no_auto_replan_policy(tmp_path):
    root = _repo(tmp_path)
    _ledger(root)

    got = crew_autopilot.next_phase(str(root), T, policy=False)

    assert (got["phase"], got["stop"]) == ("accept-review", True)


def test_a_round_left_keeps_todays_answer(tmp_path):
    root = _repo(tmp_path)
    _ledger(root, rounds=[_row(1)])

    got = _next(root)

    assert (got["phase"], got["stop"], "or fixes then /crew:review" in got["reason"]) == (
        "accept-review", True, True)


def test_cap_reached_stops_and_lists_successors(tmp_path):
    root = _repo(tmp_path)
    _cap_reached(root)

    got = _next(root)

    assert (got["phase"], got["stop"], got["reason"].startswith(
        "autopilot.maxAutoReplans (2) reached"), "b" * 12 in got["reason"],
            "c" * 12 in got["reason"], "after round 4" in got["reason"],
            "autopilot:self" in got["reason"]) == (
        "accept-review", True, True, True, True, True, True)


def _rejected(root, by=None, number=2, **ledger):
    return _ledger(root, state="NEEDS_REPLAN",
                   rejected={"by": by or crew_autopilot.AUTO_REJECT_BY, "at": "2026-10-04T00:00:00Z", "round": number},
                   **ledger)


def test_replan_after_auto_reject_is_not_a_stop(tmp_path):
    root = _repo(tmp_path)
    _rejected(root)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("replan", False, f"/crew:plan {T}")


# `_review_phase`'s NEEDS_REPLAN reason on main before T-0074, verbatim.
TODAYS_REPLAN = (f"{T} is NEEDS_REPLAN: the review budget is spent; a different plan "
                 "continues it once approved (the approve phase and autopilot.approval "
                 "decide by whom)")


def _todays_replan(tmp_path):
    root = _repo(tmp_path / "today", replans=MISSING)
    _rejected(root, by="Owner")
    got = _next(root)
    assert got["reason"] == TODAYS_REPLAN
    return got


def test_replan_after_owner_reject_still_stops(tmp_path):
    root = _repo(tmp_path)
    _rejected(root, by="Owner")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("replan", True, f"/crew:plan {T}")
    assert got["reason"] == _todays_replan(tmp_path)["reason"]


def test_replan_stops_when_rejected_round_is_not_latest(tmp_path):
    root = _repo(tmp_path)
    _rejected(root, number=1)

    assert (_next(root)["stop"], _next(root)["reason"]) == (True,
                                                              _todays_replan(tmp_path)["reason"])


@pytest.mark.parametrize("kwargs", [{"armed": False}, {"replans": 0}, {"approval": "human"},
                                    {"approval": "risk", "risk": "high"}])
def test_replan_after_auto_reject_stops_when_the_policy_no_longer_allows(tmp_path, kwargs):
    root = _repo(tmp_path, **kwargs)
    _rejected(root)

    assert _next(root)["stop"] is True


def test_replan_after_auto_reject_stops_at_the_cap(tmp_path):
    root = _repo(tmp_path, replans=1)
    _rejected(root, number=4, rounds=[_row(n) for n in range(1, 5)],
              successors=[_successor("b", 2)])

    assert _next(root)["stop"] is True


def test_full_cycle_reject_plan_approve_opens_fresh_rounds(tmp_path):
    root = _repo(tmp_path)
    _ledger(root)

    rejected = _cli(root, "auto-reject", "--ticket", T)
    replan = _next(root)
    _write(root / ".work" / "tickets" / T / "plan.md",
           PLAN.format(files="src/app.py") + "\nSuccessor: quotes " + BLOCK_LINE + "\n")
    approve = _next(root)
    approved = _cli(root, "approve", "--ticket", T)
    after = _next(root)

    assert (rejected.returncode, replan["phase"], replan["stop"], approve["phase"],
            approved.returncode, review_ledger.status(str(root), T)["state"],
            after["phase"], after["stop"]) == (
        0, "replan", False, "approve", 0, review_ledger.IN_REVIEW, "implement", False)


# --- stops and status --------------------------------------------------------------

def test_stops_list_the_cap_stop_and_reword_review_acceptance():
    got = crew_autopilot.stops()
    human = {row["id"]: row["text"] for row in got["human"]}

    assert ("auto-replan-cap" in [row["id"] for row in got["fixed"]],
            "never accepted by autopilot" in human["review-acceptance"],
            "autopilot.maxAutoReplans" in human["review-acceptance"]) == (True, True, True)


def test_status_maps_the_auto_replan_phase():
    assert crew_autopilot.WAITING.get("auto-replan") not in (None, crew_autopilot.UNKNOWN)


def test_command_names_the_auto_replan_procedure():
    with open(os.path.join(_ROOT, "commands", "autopilot.md"), encoding="utf-8") as handle:
        flat = " ".join(handle.read().split())

    assert ("`auto-replan`: run its `auto-reject` line, report every line verbatim" in flat,
            "quote every BLOCK and FIX line of the rejected round verbatim" in flat,
            "neighbouring-case check" in flat, "`maxAutoReplans` (0: off)" in flat,
            "`auto-rejected`" in flat, "every successor plan" in flat) == (
        True, True, True, True, True, True)
