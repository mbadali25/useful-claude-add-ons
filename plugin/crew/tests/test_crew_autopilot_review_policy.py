"""T-0067: `autopilot.reviewPolicy` and the single-ticket `fix` phase.

Must-allow: a non-final FINDINGS round under `fix-and-rereview` names `fix`,
and a complete fix (fixes.md quotes every BLOCK and FIX line, and the bundle
changed) goes toward the next round. Must-block: every could-not-tell or
refusal returns the existing `accept-review` stop, and `stop` keeps today's
reason byte for byte. Every case builds a throwaway repo under tmp_path.
"""

import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_fix
import review_patch
from review_fixtures import git
from test_crew_autopilot import (_COMMAND, _SCRIPT, _approved, _documents_ok,  # noqa: F401  pylint: disable=unused-import
                                 _ledger, _next, _refresh, _round, _write)

T = "T-1"
FINDINGS = ["FIX|src/app.py|1|x is wrong|set x to 2", "NIT|src/app.py|1|naming|rename x"]
BLOCKS = ["BLOCK|src/app.py|1|x breaks|guard x"]
CMD = f"fix-findings {T} round 1"


def _config(root, policy=None, raw=None):
    block = {} if policy is None else {"reviewPolicy": policy}
    text = raw if raw is not None else json.dumps({"scope": {"mode": "off"}, "autopilot": block})
    _write(root / ".crew" / "config.json", text)


def _head(root):
    return git(root, "rev-parse", "HEAD").strip()


def _findings_round(root, findings=tuple(FINDINGS), policy="fix-and-rereview", rounds=None, **row):
    """An approved ticket whose round 1 is FINDINGS on the current tree."""
    _config(root, policy)
    base = _head(root)
    _write(root / "src" / "app.py", "x = 1\ny = 1\n")  # the reviewed work
    git(root, "commit", "-q", "-am", "work")
    found = dict(_round(1, "FINDINGS"), base=base, findings=list(findings) if findings is not None else None,
                 bundle_sha256=review_patch.compute(str(root), base)[0]["bundle_sha256"])
    lines = found["findings"] if isinstance(found["findings"], list) else []
    found["counts"] = {sev: sum(1 for f in lines if isinstance(f, str) and f.startswith(sev + "|"))
                       for sev in ("BLOCK", "FIX", "NIT")}
    found.update(row)
    for key in [k for k, v in row.items() if v is None]:
        del found[key]
    return _ledger(root, rounds or [found], state="REVIEWED")


def _change(root):
    """A commit that changes a bundled file."""
    _write(root / "src" / "app.py", "x = 2\ny = 1\n")
    git(root, "add", "src/app.py")
    git(root, "commit", "-q", "-m", "fix x")


def _fixes(root, text):
    _write(root / ".work" / "tickets" / T / "fixes.md", text)


def _today(policy, tmp_path):
    root = _approved(tmp_path / str(policy))
    _findings_round(root, policy=policy)
    return _next(root)


# --- the setting ---------------------------------------------------------------

def test_settings_review_policy_defaults_to_stop(tmp_path):
    root = _approved(tmp_path)
    _config(root)
    done = subprocess.run([sys.executable, _SCRIPT, "settings", "--root", str(root)],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)

    assert (crew_autopilot.settings(str(root))["reviewPolicy"], "reviewPolicy=stop" in done.stdout) == (
        "stop", True), done.stdout


@pytest.mark.parametrize("value", ["Fix-And-Rereview", "fix", True, 1, ""])
def test_settings_review_policy_invalid_value_warns_and_reads_stop(tmp_path, value):
    root = _approved(tmp_path)
    _config(root, value)

    got = crew_autopilot.settings(str(root))

    assert (got["reviewPolicy"], any(f"autopilot.reviewPolicy is {value!r}" in w
                                     for w in got["warnings"])) == ("stop", True)


@pytest.mark.parametrize("raw", ["{not json", json.dumps({"autopilot": ["fix-and-rereview"]})])
def test_settings_unreadable_config_reads_review_policy_unknown(tmp_path, raw):
    root = _approved(tmp_path)
    _config(root, raw=raw)

    assert crew_autopilot.settings(str(root))["reviewPolicy"] == "unknown"


# --- must-allow ------------------------------------------------------------------

def test_next_round1_findings_names_the_fix_phase(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root)
    done = subprocess.run([sys.executable, _SCRIPT, "next", "--root", str(root), "--ticket", T],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)

    assert done.stdout.startswith(f"phase=fix stop=0 command={CMD}"), done.stdout


def test_next_round1_block_names_the_fix_phase(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root, findings=BLOCKS)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("fix", False, CMD), got


@pytest.mark.parametrize("state, phase, command", [
    ("stale", "refresh", "/crew:diagram refresh"), ("fresh", "review", f"/crew:review {T}")])
def test_next_after_the_fix_goes_toward_review(tmp_path, monkeypatch, state, phase, command):
    root = _approved(tmp_path)
    _findings_round(root)
    _change(root)
    _fixes(root, f"# fixes\n## Round 1\n{FINDINGS[0]}\nfixed: test_x - x is 2\n")
    _refresh(monkeypatch, state)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == (phase, False, command), got


def test_fixes_md_with_crlf_endings_counts(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _findings_round(root)
    _change(root)
    _fixes(root, f"## Round 1\r\n{FINDINGS[0]}\r\nfixed: t\r\n")
    _refresh(monkeypatch, "fresh")

    assert _next(root)["phase"] == "review"


def test_status_maps_the_fix_phase(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root)

    shown = crew_autopilot.status(str(root), T)

    assert (shown["phase"], shown["waiting"].startswith("autopilot - run")) == ("fix", True), shown


# --- must-block -------------------------------------------------------------------

def test_policy_stop_keeps_todays_reason(tmp_path):
    stop, missing = _today("stop", tmp_path), _today(None, tmp_path)

    assert (stop["phase"], stop["stop"], stop["reason"] == missing["reason"],
            "does not fix it" in stop["reason"], "could not be told" in stop["reason"]) == (
        "accept-review", True, True, False, False)


@pytest.mark.parametrize("policy", ["clean-only"])
def test_policy_clean_only_stops_as_today(tmp_path, policy):
    got, stop = _today(policy, tmp_path), _today("stop", tmp_path)

    assert (got["phase"], got["stop"], got["reason"] == stop["reason"]) == ("accept-review", True, True)


def test_policy_unknown_stops(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root)
    _config(root, raw="{not json")

    got = _next(root)

    assert (got["phase"], got["stop"], "could not be told" in got["reason"]) == (
        "accept-review", True, True), got


def _blocked(tmp_path, **kwargs):
    root = _approved(tmp_path)
    _findings_round(root, **kwargs)
    return _next(root)


def test_final_round_stops_under_fix_and_rereview(tmp_path):
    root = _approved(tmp_path)
    second = dict(_round(2, "FINDINGS"), findings=FINDINGS)
    _findings_round(root, rounds=[_round(1, "CLEAN"), second])

    got = _next(root)

    assert (got["phase"], got["stop"], "final round" in got["reason"]) == ("accept-review", True, True), got


@pytest.mark.parametrize("left", ["missing", True, "1"])
def test_rounds_left_that_is_not_an_int_stops(tmp_path, monkeypatch, left):
    root = _approved(tmp_path)
    _findings_round(root)
    real = crew_autopilot._ledger_status  # pylint: disable=protected-access

    def status(top, ticket):
        got = dict(real(top, ticket))
        if left == "missing":
            got.pop("rounds_left", None)
        else:
            got["rounds_left"] = left
        return got

    monkeypatch.setattr(crew_autopilot, "_ledger_status", status)
    got = _next(root)

    assert (got["phase"], got["stop"], "rounds_left" in got["reason"]) == ("accept-review", True, True), got


@pytest.mark.parametrize("row, words", [
    ({"findings": None}, "no list of finding lines"),
    ({"findings": ["FIX|a|1|b|c", 3]}, "no list of finding lines"),
    ({"findings": ["NIT|a|1|b|c"], "counts": {"BLOCK": 0, "FIX": 0, "NIT": 1}}, "no BLOCK or FIX line"),
    ({"counts": {"BLOCK": 1, "FIX": 1, "NIT": 1}}, "BLOCK count is 1 but it lists 0"),
    ({"counts": {"BLOCK": False, "FIX": 1, "NIT": 1}}, "BLOCK count is False"),
    ({"counts": None}, "counts are None"),
    ({"findings": ["FIX|a|1|b|c", "WARN|a|1|b|c"]}, "is not a BLOCK, FIX or NIT line"),
    ({"findings": ["FIX|a|1|b\nBLOCK|x"]}, "line break"),
    ({"base": None}, "no round number, base or bundle_sha256"),
    ({"bundle_sha256": None}, "no round number, base or bundle_sha256"),
])
def test_a_row_it_cannot_read_stops(tmp_path, row, words):
    got = _blocked(tmp_path, **row)

    assert (got["phase"], got["stop"], words in got["reason"]) == ("accept-review", True, True), got


def test_a_bundle_rebuild_that_raises_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _findings_round(root)

    def boom(*_args, **_kwargs):
        raise RuntimeError("git on fire")

    monkeypatch.setattr(review_patch, "compute", boom)
    got = _next(root)

    assert (got["phase"], got["stop"], "git on fire" in got["reason"]) == ("accept-review", True, True), got


def test_fixes_md_not_utf8_stops(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root)
    path = root / ".work" / "tickets" / T / "fixes.md"
    path.write_bytes(b"## Round 1\n\xff\xfe\n")

    got = _next(root)

    assert (got["phase"], got["stop"], "not UTF-8" in got["reason"]) == ("accept-review", True, True), got


def test_complete_fixes_md_with_an_unchanged_bundle_is_no_progress(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root)
    _fixes(root, f"## Round 1\n{FINDINGS[0]}\nfixed: t\n")
    first = _next(root)
    again = _next(root, last_command=CMD)

    assert ((first["phase"], first["stop"], "has not changed" in first["reason"]),
            (again["phase"], again["stop"], again["reason"].startswith("no progress"))) == (
        ("fix", False, True), ("fix", True, True)), (first, again)


@pytest.mark.parametrize("text", [
    "## Round 1\nunrelated\n",
    f"## Round 1\n- {FINDINGS[0]}\n",
    f"## Round 2\n{FINDINGS[0]}\n",
])
def test_changed_bundle_with_incomplete_fixes_md_stays_fix(tmp_path, text):
    root = _approved(tmp_path)
    _findings_round(root)
    _change(root)
    _fixes(root, text)

    got = _next(root)

    assert (got["phase"], got["stop"], "lacks 1 of 1" in got["reason"]) == ("fix", False, True), got


def test_a_line_carried_twice_is_owed_twice(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root, findings=[FINDINGS[0], FINDINGS[0]])
    _change(root)
    _fixes(root, f"## Round 1\n{FINDINGS[0]}\n")

    assert _next(root)["phase"] == "fix"


def test_next_incomplete_round_stops_under_fix_and_rereview(tmp_path):
    root = _approved(tmp_path)
    _findings_round(root, rounds=[dict(_round(1, "INCOMPLETE"), findings=FINDINGS)])

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("accept-review", True), got


def test_needs_replan_stops_under_fix_and_rereview(tmp_path):
    root = _approved(tmp_path)
    _config(root, "fix-and-rereview")
    _ledger(root, [dict(_round(1, "FINDINGS"), findings=FINDINGS), dict(_round(2, "FINDINGS"),
                                                                         findings=FINDINGS)],
            state="NEEDS_REPLAN")

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("replan", True), got


def test_reserved_round_stops_under_fix_and_rereview(tmp_path):
    root = _approved(tmp_path)
    _config(root, "fix-and-rereview")
    _ledger(root, [_round(1, status="reserved")])

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("review", True), got


# --- the command and the stop lists ---------------------------------------------

def test_stops_lists_fix_refused_under_procedure():
    assert "fix-refused" in [row["id"] for row in crew_autopilot.stops()["procedure"]]


def test_command_describes_the_fix_phase():
    with open(_COMMAND, encoding="utf-8") as handle:
        text = " ".join(handle.read().split())
    line = text[text.index("`phase=fix`"):]
    line = line[:line.index(" - `stop=1` with")]

    assert ([w for w in ("failing test first", "inside the spec's Touch", "verify gate", "commit",
                         "fixes.md", "## Round <n>", "verbatim", "`fixed:`", "outside Touch",
                         "disputes the spec or the plan", "disagree", "`fix-refused`")
             if w not in line], text.count("never fix and rerun inside the phase")) == ([], 1)


def test_fix_module_policies_match_the_wave():
    import crew_wave  # pylint: disable=import-outside-toplevel
    assert tuple(crew_wave.REVIEW_POLICIES) == crew_autopilot_fix.POLICIES


def test_fixes_path_is_in_the_ticket_folder(tmp_path):
    assert crew_autopilot_fix.fixes_path(str(tmp_path)) == os.path.join(str(tmp_path), "fixes.md")


def test_an_empty_rebuilt_bundle_stops(tmp_path):
    """T-0067 review r1 FIX: reverting the work leaves nothing to review; never `/crew:review`."""
    root = _approved(tmp_path)
    _findings_round(root)
    git(root, "revert", "--no-edit", "HEAD")
    _fixes(root, f"## Round 1\n{FINDINGS[0]}\n")

    got = _next(root)

    assert (got["phase"], got["stop"], "is empty" in got["reason"]) == ("accept-review", True, True), got
