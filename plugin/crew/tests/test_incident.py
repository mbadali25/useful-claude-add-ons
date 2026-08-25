"""Tests for the emergency lane: crew_incident, and the state/brief it feeds.

The property that matters most here is not that an incident stands the gates
down - it is that it CANNOT stand them down forever. Every test that asserts
"active" has a sibling asserting the same state is inert once the clock passes
the expiry, because a forgotten incident is the realistic failure mode: nobody
forgets to declare one during an outage, and everybody forgets to close one
afterwards.

`now` is injected everywhere rather than slept through: a test that waits two
hours to prove an expiry is a test nobody runs.
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_incident
import crew_state
import pm_brief

T0 = 1_800_000_000          # a fixed "now", so every assertion is arithmetic
HOUR = 3600


def _repo(tmp_path, config=None):
    return crew_fixtures.make_repo(tmp_path, config=config or {"tier": 1}, git=False)


def _state(root, cfg=None, now=T0):
    return crew_incident.read_state(root, cfg or {}, now=now)


# --- Declaring ------------------------------------------------------------


def test_nothing_declared_reads_as_absent_not_active(tmp_path):
    state = _state(_repo(tmp_path))
    assert state == {
        "present": False, "active": False, "expired": False, "id": None,
        "summary": "", "skips": 0, "minutesLeft": 0, "standDown": True,
    }


def test_declare_writes_an_active_incident_with_a_default_ttl(tmp_path):
    root = _repo(tmp_path)
    state = crew_incident.declare(root, "prod 5xx after the 14:02 deploy", now=T0)
    assert state["active"] is True
    assert state["present"] is True
    assert state["expired"] is False
    assert state["minutesLeft"] == crew_incident.DEFAULT_TTL_MINUTES
    assert state["id"].startswith("INC-")
    on_disk = json.loads((root / ".crew" / "incident.json").read_text(encoding="utf-8"))
    assert on_disk["expiresAtEpoch"] == T0 + crew_incident.DEFAULT_TTL_MINUTES * 60
    # The gates read the epoch, never the ISO string. Both are written; only
    # one is parsed by anything.
    assert on_disk["expiresAt"].endswith("Z")


def test_declare_honours_a_configured_ttl(tmp_path):
    root = _repo(tmp_path)
    cfg = {"emergency": {"ttlMinutes": 30}}
    state = crew_incident.declare(root, "db failover", cfg=cfg, now=T0)
    assert state["minutesLeft"] == 30


def test_ttl_is_capped_by_max_ttl_minutes(tmp_path):
    root = _repo(tmp_path)
    cfg = {"emergency": {"ttlMinutes": 60, "maxTtlMinutes": 90}}
    state = crew_incident.declare(root, "cache stampede", cfg=cfg,
                                  ttl_minutes=10_000, now=T0)
    assert state["minutesLeft"] == 90


def test_redeclaring_extends_rather_than_forking_the_record(tmp_path):
    # Two records for one outage means two partial debt lists, and the second
    # silently orphans the first one's skips.
    root = _repo(tmp_path)
    first = crew_incident.declare(root, "prod 5xx", now=T0)
    crew_incident.log_skip(root, "verify", "pytest not run", now=T0 + 60)
    second = crew_incident.declare(root, "prod 5xx again", now=T0 + 600)
    assert second["id"] == first["id"]
    assert second["skips"] == 1, "the first declaration's skips must survive"


# --- Expiry: the safety property -----------------------------------------


def test_an_incident_is_inert_the_moment_the_clock_passes_its_expiry(tmp_path):
    root = _repo(tmp_path)
    crew_incident.declare(root, "prod 5xx", ttl_minutes=60, now=T0)
    just_before = _state(root, now=T0 + 60 * 60 - 1)
    at_expiry = _state(root, now=T0 + 60 * 60)
    assert just_before["active"] is True
    assert at_expiry["active"] is False
    assert at_expiry["expired"] is True
    assert at_expiry["present"] is True, "still on disk, still owed a close"


def test_extend_pushes_the_expiry_out_from_now_not_from_the_old_one(tmp_path):
    # Extending from the old expiry lets four extensions reach eight hours past
    # the point anyone was watching. The cap is on the remaining window.
    root = _repo(tmp_path)
    crew_incident.declare(root, "prod 5xx", ttl_minutes=60, now=T0)
    state = crew_incident.extend(root, ttl_minutes=60, now=T0 + 30 * 60)
    assert state["minutesLeft"] == 60
    on_disk = json.loads((root / ".crew" / "incident.json").read_text(encoding="utf-8"))
    assert on_disk["expiresAtEpoch"] == T0 + 30 * 60 + 60 * 60


def test_extend_with_nothing_open_does_nothing(tmp_path):
    root = _repo(tmp_path)
    state = crew_incident.extend(root, ttl_minutes=60, now=T0)
    assert state["present"] is False
    assert not (root / ".crew" / "incident.json").exists()


def test_a_malformed_state_file_is_not_an_active_incident(tmp_path):
    # Fail closed: an unparseable incident file must gate, not stand down.
    root = _repo(tmp_path)
    (root / ".crew" / "incident.json").write_text("{ not json", encoding="utf-8")
    assert _state(root)["active"] is False


def test_a_state_file_with_no_expiry_is_not_active(tmp_path):
    root = _repo(tmp_path)
    (root / ".crew" / "incident.json").write_text(
        json.dumps({"id": "INC-x", "summary": "no expiry"}), encoding="utf-8")
    state = _state(root)
    assert state["present"] is True
    assert state["active"] is False
    assert state["expired"] is True


# --- standDown: false -----------------------------------------------------


def test_stand_down_false_declares_a_real_incident_that_gates_anyway(tmp_path):
    # For a repo where skipping verification is not a decision anyone local
    # gets to make. The incident is still recorded and still briefed.
    root = _repo(tmp_path)
    cfg = {"emergency": {"standDown": False}}
    state = crew_incident.declare(root, "prod 5xx", cfg=cfg, now=T0)
    assert state["present"] is True
    assert state["active"] is False
    assert state["standDown"] is False
    assert "NOT standing down" in crew_incident.format_status(state)


# --- Skips and the closing report ----------------------------------------


def test_log_skip_records_one_row_per_gate_and_detail(tmp_path):
    # Not per turn. Stop fires every turn and on Windows both hook flavours run
    # on the same Stop, so counting occurrences would measure how long the
    # incident lasted rather than what is owed. The interleaved repeat is the
    # case a last-row-only check gets wrong: the gates log two different rows
    # per turn, so the same row is never immediately consecutive.
    root = _repo(tmp_path)
    crew_incident.declare(root, "prod 5xx", now=T0)
    crew_incident.log_skip(root, "verify", "detail A", now=T0 + 1)
    crew_incident.log_skip(root, "verify", "detail A", now=T0 + 2)
    assert _state(root)["skips"] == 1
    crew_incident.log_skip(root, "verify", "detail B", now=T0 + 3)
    crew_incident.log_skip(root, "verify", "detail A", now=T0 + 4)
    assert _state(root)["skips"] == 2, "an interleaved repeat is still a repeat"
    # Same detail, different gate, is a different debt.
    crew_incident.log_skip(root, "promote", "detail A", now=T0 + 5)
    assert _state(root)["skips"] == 3


def test_end_writes_the_report_archives_the_state_and_regates(tmp_path):
    root = _repo(tmp_path)
    declared = crew_incident.declare(root, "prod 5xx", now=T0)
    crew_incident.log_skip(root, "verify", "stop gate stood down", now=T0 + 60)
    crew_incident.log_skip(root, "promote", "prod at abc123: dirty tree",
                           now=T0 + 120)

    path, before = crew_incident.end(root, now=T0 + 300)

    assert before["id"] == declared["id"]
    assert before["skips"] == 2
    assert path == f".work/INCIDENT-{declared['id']}.md"
    text = (root / path).read_text(encoding="utf-8")
    assert declared["id"] in text
    assert "stop gate stood down" in text
    assert "dirty tree" in text
    assert "## Owed" in text
    # Re-gated: the gates read this file's existence, so its removal IS the
    # re-gating, and it must happen only after the archive is safely on disk.
    assert not (root / ".crew" / "incident.json").exists()
    assert (root / ".crew" / "incidents" / f"{declared['id']}.json").exists()
    assert not (root / ".crew" / "incident-skips.log").exists()
    assert _state(root)["active"] is False


def test_read_skips_dedupes_a_row_a_race_wrote_twice(tmp_path):
    # Both writers check before appending, but two hook flavours appending at
    # the same instant can both miss it. The count in a debt list is the number
    # of things owed, so deduping on read makes that true however the file was
    # written. Codex review finding.
    root = _repo(tmp_path)
    crew_incident.declare(root, "prod 5xx", now=T0)
    (root / ".crew" / "incident-skips.log").write_text(
        f"{T0}\tverify\tsame row\n{T0}\tverify\tsame row\n"
        f"{T0}\tpromote\tanother\n", encoding="utf-8")
    assert _state(root)["skips"] == 2
    assert "verify: 1 skipped" in crew_incident.report(root, now=T0 + 10)


def test_end_refuses_to_close_an_incident_that_changed_underneath_it(
        tmp_path, monkeypatch):
    # The state file is read more than once inside end(). If a new declaration
    # lands in between, archiving it under the OLD id and deleting it would
    # re-gate a repository somebody had just declared an incident for.
    root = _repo(tmp_path)
    crew_incident.declare(root, "the new one", now=T0)
    real = crew_incident.read_state

    def stale(*args, **kwargs):
        state = dict(real(*args, **kwargs))
        state["id"] = "INC-19700101-0000"      # a different, older incident
        return state

    monkeypatch.setattr(crew_incident, "read_state", stale)
    path, before = crew_incident.end(root, now=T0 + 60)

    assert path is None
    assert before["id"] == "INC-19700101-0000"
    # Nothing written, nothing removed: the open incident is still open.
    assert (root / ".crew" / "incident.json").exists()
    assert not list((root / ".work").glob("INCIDENT-*.md"))
    assert not (root / ".crew" / "incidents").exists()


def test_end_with_no_incident_is_a_no_op(tmp_path):
    root = _repo(tmp_path)
    path, before = crew_incident.end(root, now=T0)
    assert path is None
    assert before["present"] is False


def test_the_report_says_so_when_no_gate_was_actually_skipped(tmp_path):
    root = _repo(tmp_path)
    crew_incident.declare(root, "false alarm", now=T0)
    path, _ = crew_incident.end(root, now=T0 + 60)
    assert "None. The gates stood down but nothing tripped them." in (
        (root / path).read_text(encoding="utf-8"))


def test_report_lists_ten_details_then_says_how_many_more(tmp_path):
    root = _repo(tmp_path)
    crew_incident.declare(root, "prod 5xx", now=T0)
    for i in range(14):
        crew_incident.log_skip(root, "verify", f"check {i} not run", now=T0 + i)
    text = crew_incident.report(root, now=T0 + 100)
    assert "verify: 14 skipped" in text
    assert "and 4 more" in text


def test_a_second_incident_the_same_minute_does_not_overwrite_the_archive(tmp_path):
    root = _repo(tmp_path)
    first = crew_incident.declare(root, "one", now=T0)
    crew_incident.end(root, now=T0 + 10)
    second = crew_incident.declare(root, "two", now=T0 + 20)
    assert second["id"] != first["id"]
    crew_incident.end(root, now=T0 + 30)
    assert (root / ".crew" / "incidents" / f"{first['id']}.json").exists()
    assert (root / ".crew" / "incidents" / f"{second['id']}.json").exists()


def test_declaring_after_an_unclosed_expired_incident_does_not_inherit_its_skips(
        tmp_path):
    root = _repo(tmp_path)
    crew_incident.declare(root, "yesterday", ttl_minutes=1, now=T0)
    crew_incident.log_skip(root, "verify", "old debt", now=T0 + 10)
    # Expired, never closed. A new incident must not absorb the old skips --
    # that would misattribute the debt to the wrong outage.
    state = crew_incident.declare(root, "today", now=T0 + 10 * HOUR)
    assert state["skips"] == 0
    assert (root / ".crew" / "incident-skips.log.orphaned").exists()


# --- crew_state triggers and the session brief ---------------------------


def test_crew_state_reports_an_active_incident_as_the_first_trigger(tmp_path):
    root = _repo(tmp_path, config={"tier": 1, "schema": crew_state.SCHEMA_CURRENT})
    crew_incident.declare(root, "prod 5xx")
    state = crew_state.collect(str(root))
    assert state["incident"]["active"] is True
    assert state["triggers"][0] == "incidentActive"


def test_crew_state_reports_an_expired_incident_as_unclosed(tmp_path):
    root = _repo(tmp_path, config={"tier": 1, "schema": crew_state.SCHEMA_CURRENT})
    crew_incident.declare(root, "prod 5xx", ttl_minutes=1)
    # Rewrite the expiry into the past rather than waiting a minute.
    path = root / ".crew" / "incident.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["expiresAtEpoch"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")

    state = crew_state.collect(str(root))
    assert "incidentUnclosed" in state["triggers"]
    assert "incidentActive" not in state["triggers"]


@pytest.mark.parametrize("mode", ["adaptive", "quiet"])
def test_the_brief_names_the_incident_in_both_pm_modes(mode):
    # The findings section can be truncated away by the line cap; "the gates
    # are currently off" must not be the line that gets cut.
    state = {
        "isCrew": True,
        "pm": {"enabled": True, "mode": mode, "quietLines": 8, "maxLines": 40},
        "triggers": ["incidentActive"],
        "incident": {"present": True, "active": True, "expired": False,
                     "id": "INC-20260825-1342", "summary": "prod 5xx",
                     "skips": 3, "minutesLeft": 47, "standDown": True},
    }
    lines = pm_brief.render(state)
    assert lines[0].startswith("## incident - INC-20260825-1342 open, 47m left")
    if mode == "adaptive":
        joined = "\n".join(lines)
        assert "EMERGENCY LANE OPEN - INC-20260825-1342 (prod 5xx)" in joined
        assert "47m left, 3 gate(s) skipped" in joined
        assert "/crew:emergency end" in joined


def test_the_brief_survives_an_incident_with_no_usable_fields():
    # _fill must never raise: this renders from a SessionStart hook, and an
    # exception there breaks every session opened in the repository.
    state = {
        "isCrew": True,
        "pm": {"enabled": True, "mode": "adaptive", "quietLines": 8,
               "maxLines": 40},
        "triggers": ["incidentActive"],
        "incident": {"present": True, "active": True},
    }
    lines = pm_brief.render(state)
    assert any("EMERGENCY LANE OPEN" in line for line in lines)


def test_a_long_summary_is_trimmed_in_the_brief():
    state = {
        "isCrew": True,
        "pm": {"enabled": True, "mode": "adaptive", "quietLines": 8,
               "maxLines": 40},
        "triggers": ["incidentActive"],
        "incident": {"present": True, "active": True, "id": "INC-1",
                     "summary": "x" * 200, "skips": 0, "minutesLeft": 5,
                     "standDown": True},
    }
    joined = "\n".join(pm_brief.render(state))
    assert "x" * 57 + "..." in joined
    assert "x" * 61 not in joined
