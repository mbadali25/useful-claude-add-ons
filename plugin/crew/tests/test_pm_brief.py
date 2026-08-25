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


def test_the_brief_prints_again_after_a_clear(tmp_path, monkeypatch, capsys):
    """SessionStart fires once per SOURCE, not once per session.

    Keying the claim on session_id alone made the brief print at startup and
    stay silent after every later /clear and /compact -- exactly when a fresh
    session most needs its state.
    """
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    seen = []
    for source in ("startup", "clear", "compact", "resume", "fork"):
        payload = json.dumps({"source": source, "cwd": str(root),
                              "session_id": "one-session"})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert pm_brief.main([]) == 0
        seen.append(bool(capsys.readouterr().out.strip()))
    assert all(seen), f"silent on: {seen}"


def test_the_same_source_twice_in_one_session_prints_once(tmp_path, monkeypatch,
                                                          capsys):
    # The double-fire case still has to hold: both wrappers fire one event.
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    payload = json.dumps({"source": "clear", "cwd": str(root),
                          "session_id": "one-session"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    pm_brief.main([])
    first = capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    pm_brief.main([])
    second = capsys.readouterr().out
    assert first.strip()
    assert second == ""


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


def _with(trigger, **over):
    state = dict(HEALTHY, triggers=[trigger])
    state.update(over)
    return state


def test_expanded_brief_names_the_finding_and_one_action():
    out = "\n".join(pm_brief.render(_with("upgradeNeeded", schema=1)))
    assert "/crew:upgrade" in out


def test_the_brief_is_pure_ascii(tmp_path):
    """A Windows console on an OEM codepage cannot encode what this module has
    no reason to emit.

    Measured: an em-dash under cp437 raises UnicodeEncodeError and the hook
    exits 1, which breaks every session opened in that repo. Rendering is
    checked here rather than at the print, so a non-ASCII string is caught the
    moment someone adds it.
    """
    state = dict(HEALTHY, schema=1,
                 triggers=list(pm_brief.crew_state.TRIGGERS))
    for line in pm_brief.render(state) + pm_brief.render(HEALTHY):
        line.encode("ascii")  # raises UnicodeEncodeError if it ever regresses

    for finding, action in pm_brief.FINDINGS.values():
        finding.encode("ascii")
        action.encode("ascii")


def test_each_trigger_has_a_finding_and_an_action():
    # A trigger with no entry would fire silently, which is worse than not
    # firing: the state says something is wrong and the brief says nothing.
    for name in pm_brief.crew_state.TRIGGERS:
        assert name in pm_brief.FINDINGS
        finding, action = pm_brief.FINDINGS[name]
        assert finding and action


def test_expanded_brief_states_report_only_authority():
    out = "\n".join(pm_brief.render(_with("upgradeNeeded", schema=1))).lower()
    assert "recommend" in out or "report" in out


def test_healthy_state_stays_quiet():
    out = pm_brief.render(HEALTHY)
    assert len(out) <= HEALTHY["pm"]["quietLines"]
    assert "/crew:upgrade" not in "\n".join(out)


def test_every_trigger_at_once_respects_max_lines():
    state = dict(HEALTHY, schema=1,
                 triggers=list(pm_brief.crew_state.TRIGGERS))
    out = pm_brief.render(state)
    assert len(out) <= HEALTHY["pm"]["maxLines"]


def test_truncation_never_orphans_a_finding_from_its_action():
    """A finding whose action was cut names a problem and says nothing about it.

    Every even cap used to do exactly that, because the cut fell between the
    two lines of one pair.
    """
    state = dict(HEALTHY, schema=1,
                 triggers=list(pm_brief.crew_state.TRIGGERS))
    # From 2, the floor max(2, ...) enforces. Below that the requested cap
    # is not the effective one, so comparing against it tests the harness.
    for cap in range(2, 24):
        out = pm_brief.render(dict(state, pm=dict(HEALTHY["pm"], maxLines=cap)))
        assert len(out) <= cap, f"cap {cap} exceeded: {len(out)}"
        findings = sum(1 for line in out if line.startswith("- "))
        actions = sum(1 for line in out if line.strip().startswith("->"))
        assert findings == actions, (
            f"cap {cap}: {findings} findings but {actions} actions"
        )


def test_the_truncation_notice_is_ascii():
    # The all-triggers case fits under the default cap, so the notice is never
    # rendered there and the ascii sweep never sees it.
    pm_brief._TRUNCATED.encode("ascii")  # pylint: disable=protected-access


def test_truncation_points_at_the_pm_command():
    state = dict(HEALTHY, schema=1,
                 triggers=list(pm_brief.crew_state.TRIGGERS),
                 pm=dict(HEALTHY["pm"], maxLines=7))
    out = pm_brief.render(state)
    assert len(out) <= 7
    assert "/crew:pm" in out[-1]


def test_truncation_keeps_the_highest_priority_finding():
    state = dict(HEALTHY, schema=1,
                 triggers=["upgradeNeeded", "ticketsTooLarge"],
                 pm=dict(HEALTHY["pm"], maxLines=7))
    out = "\n".join(pm_brief.render(state))
    assert "/crew:upgrade" in out


def test_quiet_mode_config_never_expands():
    state = dict(HEALTHY, schema=1, triggers=["upgradeNeeded"],
                 pm=dict(HEALTHY["pm"], mode="quiet"))
    assert "/crew:upgrade" not in "\n".join(pm_brief.render(state))


# -- context.autoResume ------------------------------------------------------
#
# Step 0 found initialUserMessage confirmed only in non-interactive (-p) mode;
# no PTY was available to drive an interactive session from this sandbox, and
# the CLI itself refuses non-tty stdio without --print semantics, which is
# consistent with (though not proof of) the -p-only reading. So the emitted
# field is additionalContext, not initialUserMessage -- see crew-context
# SKILL.md for the full record. additionalContext only ever changes shape
# (plain text -> one JSON object) when autoResume actually fires; the default
# path is untouched.

_BASE_CONFIG = {"schema": 2, "tier": 0, "roles": [], "tracker": "files"}


def test_auto_resume_false_by_default_changes_nothing(tmp_path, monkeypatch,
                                                       capsys):
    root = crew_fixtures.make_repo(tmp_path, config=_BASE_CONFIG, graph=True,
                                   handoff=True)
    out = _run(root, "sess-1", monkeypatch, capsys)
    assert "## crew" in out
    assert "additionalContext" not in out
    assert "hookSpecificOutput" not in out


def test_auto_resume_true_with_no_handoff_changes_nothing(tmp_path,
                                                          monkeypatch, capsys):
    config = dict(_BASE_CONFIG, context={"autoResume": True})
    root = crew_fixtures.make_repo(tmp_path, config=config, graph=True,
                                   handoff=False)
    out = _run(root, "sess-1", monkeypatch, capsys)
    assert "## crew" in out
    assert "additionalContext" not in out
    assert "hookSpecificOutput" not in out


def test_auto_resume_true_with_a_handoff_emits_additional_context(
    tmp_path, monkeypatch, capsys
):
    config = dict(_BASE_CONFIG, context={"autoResume": True})
    root = crew_fixtures.make_repo(tmp_path, config=config, graph=True,
                                   handoff=True)
    out = _run(root, "sess-1", monkeypatch, capsys)
    parsed = json.loads(out)  # the whole of stdout must be valid JSON
    payload = parsed["hookSpecificOutput"]
    assert payload["hookEventName"] == "SessionStart"
    assert "Something." in payload["additionalContext"]
    assert "## crew" in payload["additionalContext"]


def test_auto_resume_non_true_values_do_not_enable_it(tmp_path, monkeypatch,
                                                       capsys):
    # Gated on the value being exactly `true` -- "1" and 1 are not `true`.
    for value in ("true", 1):
        config = dict(_BASE_CONFIG, context={"autoResume": value})
        root = crew_fixtures.make_repo(
            tmp_path / f"case-{value}", config=config, graph=True,
            handoff=True,
        )
        out = _run(root, "sess-1", monkeypatch, capsys)
        assert "additionalContext" not in out


def test_auto_resume_handoff_with_non_ascii_stays_ascii_on_the_wire(
    tmp_path, monkeypatch, capsys
):
    # The handoff template in crew-context/SKILL.md documents an em-dash --
    # "file:line -- what is half-finished and why" -- so real handoff text
    # is not ASCII. The JSON path is safe only because json.dumps defaults
    # to ensure_ascii=True, escaping it to — rather than emitting the
    # raw byte; that default is load-bearing here and worth pinning, since
    # an em-dash took this hook out once already on the plain-text path.
    config = dict(_BASE_CONFIG, context={"autoResume": True})
    root = crew_fixtures.make_repo(tmp_path, config=config, graph=True)
    (root / ".work" / "HANDOFF.md").write_text(
        "# Handoff\n\n## Next action\n"
        "file.py:12 — finish the retry loop\n",
        encoding="utf-8",
    )
    out = _run(root, "sess-1", monkeypatch, capsys)
    out.encode("ascii")  # raises UnicodeEncodeError if ensure_ascii regresses
    parsed = json.loads(out)
    assert "—" in parsed["hookSpecificOutput"]["additionalContext"]


def test_auto_resume_second_call_in_one_session_prints_nothing(
    tmp_path, monkeypatch, capsys
):
    # The double-fire case (both .sh and .ps1 wrappers) still has to hold on
    # the JSON path -- the per-source claim gates emission before the
    # additionalContext branch is even reached.
    config = dict(_BASE_CONFIG, context={"autoResume": True})
    root = crew_fixtures.make_repo(tmp_path, config=config, graph=True,
                                   handoff=True)
    first = _run(root, "sess-abc", monkeypatch, capsys)
    assert "additionalContext" in first
    second = _run(root, "sess-abc", monkeypatch, capsys)
    assert second == ""
