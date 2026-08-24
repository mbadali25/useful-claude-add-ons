"""Tests for the PM brief renderer."""
import io
import json

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import pm_brief

HEALTHY = {
    "isCrew": True, "schema": 2, "tier": 1,
    "roles": ["explorer", "qa-reviewer"], "tracker": "files",
    "pm": {"enabled": True, "mode": "adaptive", "quietLines": 8,
           "maxLines": 40, "authority": "report-only"},
    "health": {"tickets": 10, "findings": 8, "rate": 0.8,
               "verdict": "healthy"},
    "work": {"ticket": "T-0042", "handoffPending": False},
    "knowledge": {"subsystems": 6, "behind": [],
                  "graph": {"present": True, "current": True}},
    "triggers": [],
}


def test_non_crew_repo_renders_nothing():
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert pm_brief.render({"isCrew": False, "triggers": []}) == []


def test_disabled_pm_renders_nothing():
    state = dict(HEALTHY, pm=dict(HEALTHY["pm"], enabled=False))
    assert pm_brief.render(state) == []  # pylint: disable=use-implicit-booleaness-not-comparison


def test_quiet_brief_respects_quiet_lines():
    out = pm_brief.render(HEALTHY)
    assert 0 < len(out) <= HEALTHY["pm"]["quietLines"]


def test_quiet_brief_states_tier_roles_and_tracker():
    joined = "\n".join(pm_brief.render(HEALTHY))
    assert "tier 1" in joined
    assert "2 roles" in joined
    assert "files" in joined


def test_quiet_brief_states_the_health_number():
    joined = "\n".join(pm_brief.render(HEALTHY))
    assert "0.8" in joined
    assert "healthy" in joined


def test_quiet_brief_names_the_open_ticket():
    assert "T-0042" in "\n".join(pm_brief.render(HEALTHY))


def test_quiet_brief_contains_no_imperative_framing():
    # Hook stdout is injected as context. Framing it as instructions trips
    # prompt-injection defences and gets it surfaced to the user instead.
    joined = "\n".join(pm_brief.render(HEALTHY)).lower()
    for banned in ("you must", "system:", "instruction", "ignore previous"):
        assert banned not in joined


def test_main_exits_zero_on_garbage_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    assert pm_brief.main([]) == 0
    assert capsys.readouterr().out == ""


def test_main_exits_zero_on_empty_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert pm_brief.main([]) == 0


def test_main_uses_cwd_from_the_payload(tmp_path, monkeypatch, capsys):
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    payload = json.dumps({"source": "startup", "cwd": str(root)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert pm_brief.main([]) == 0
    assert "crew" in capsys.readouterr().out


def test_main_on_a_plain_directory_prints_nothing(tmp_path, monkeypatch, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    payload = json.dumps({"source": "startup", "cwd": str(plain)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert pm_brief.main([]) == 0
    assert capsys.readouterr().out == ""


def _run(root, session, monkeypatch, capsys):
    payload = json.dumps({"source": "startup", "cwd": str(root),
                          "session_id": session})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert pm_brief.main([]) == 0
    return capsys.readouterr().out


def test_second_call_in_one_session_prints_nothing(tmp_path, monkeypatch, capsys):
    """The double-fire case. Both the .sh and .ps1 wrapper call this module in
    the same session, because SessionStart has no matcher to pick one.
    """
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    assert "## crew" in _run(root, "sess-abc", monkeypatch, capsys)
    assert _run(root, "sess-abc", monkeypatch, capsys) == ""


def test_a_new_session_prints_again(tmp_path, monkeypatch, capsys):
    # A permanent marker would be worse than a double-print: the brief would
    # appear once per repo, ever.
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    assert "## crew" in _run(root, "sess-abc", monkeypatch, capsys)
    assert "## crew" in _run(root, "sess-xyz", monkeypatch, capsys)


def test_no_session_id_still_prints(tmp_path, monkeypatch, capsys):
    # Without an id there is nothing to scope a claim to. Printing twice is
    # bad; never printing is worse.
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    assert "## crew" in _run(root, None, monkeypatch, capsys)
