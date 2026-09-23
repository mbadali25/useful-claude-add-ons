"""crew 1.0, lane T9: the metrics harness. Every case runs against a
throwaway repo under tmp_path; nothing here touches the real `.crew/metrics.jsonl`
or `~/.claude`."""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_metrics as cm
import review_ledger
from scope_fixtures import approve_as_user, make_repo, make_ticket


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _ledger_result(root, ticket, provider="codex", verdict="CLEAN"):
    ok, number, _ = review_ledger.reserve(str(root), ticket, provider)
    assert ok
    review_ledger.record(str(root), ticket, number,
                         {"provider": provider, "model": None, "verdict": verdict,
                          "counts": {"BLOCK": 0, "FIX": 0, "NIT": 0},
                          "bundle_sha256": "a" * 64, "base": "deadbeef",
                          "head": "cafef00d", "model_family": "test"})


def _write_guard_log(root, rows):
    path = os.path.join(str(root), ".crew", "guard.log")
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write("\t".join(str(c) for c in row) + "\n")


def _write_context_log(root, records):
    import crew_context  # pylint: disable=import-outside-toplevel
    path = crew_context.log_path(str(root))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


def _transcript(tmp_path, events):
    path = tmp_path / "transcript.jsonl"
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    return str(path)


# --------------------------------------------------------------------------
# record: all sources present

def test_record_with_every_source_present(repo, tmp_path):
    make_ticket(repo, "T-1", touch=("src/**",))
    approve_as_user(repo, "T-1")  # session "sess-1", via user-prompt
    _ledger_result(repo, "T-1")
    _write_guard_log(repo, [
        (1000, "scope", "block", "block", "T-1", "other/x.py", "outside touch"),
        (1001, "scope", "block", "report", "T-1", "other/y.py", "outside touch (report)"),
        (1002, "scope", "block", "block", "T-2", "other/z.py", "different ticket"),
    ])
    _write_context_log(repo, [
        {"session": "sess-1", "chars": 100, "event": "UserPromptSubmit"},
        {"session": "sess-1", "chars": 50, "event": "PostToolUse"},
        {"session": "sess-other", "chars": 999, "event": "UserPromptSubmit"},
    ])
    transcript = _transcript(tmp_path, [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "isSidechain": False},
        {"type": "assistant", "timestamp": "2026-01-01T00:00:10Z", "isSidechain": False,
         "message": {"usage": {"input_tokens": 100, "output_tokens": 20}}},
        {"type": "user", "timestamp": "2026-01-01T00:00:40Z", "isSidechain": False},
    ])

    row = cm.record(str(repo), "T-1", transcript=transcript)

    assert row["schema"] == "1.0"
    assert row["scopeBlocks"] == 1  # only the "block" row for T-1
    assert row["injectedChars"] == 150  # 100 + 50, session sess-1 only
    assert row["activeTime"] == 40.0  # 10 + 30, both under the idle cap
    assert row["tokens"] == 120
    assert len(row["reviewRounds"]) == 1
    assert row["reviewRounds"][0]["provider"] == "codex"
    assert row["reviewRounds"][0]["verdict"] == "CLEAN"
    assert row["unapprovedScopeChanges"] == 0
    assert any(p["phase"] == "specApproved" for p in row["phases"])
    assert any(p["phase"] == "reviewRound1Completed" for p in row["phases"])


# --------------------------------------------------------------------------
# record: each source missing -> UNKNOWN, never 0

def test_scope_blocks_unknown_when_guard_log_absent(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")

    row = cm.record(str(repo), "T-1")

    assert row["scopeBlocks"] == cm.UNKNOWN
    assert row["scopeBlocks"] != 0


def test_scope_blocks_is_a_real_zero_when_log_exists_but_names_no_block(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")
    _write_guard_log(repo, [(1, "scope", "report", "report", "T-1", "x", "would block")])

    row = cm.record(str(repo), "T-1")

    assert row["scopeBlocks"] == 0


def test_injected_chars_unknown_without_session_or_approval(repo):
    make_ticket(repo, "T-1")

    row = cm.record(str(repo), "T-1")

    assert row["injectedChars"] == cm.UNKNOWN


def test_active_time_and_tokens_unknown_without_transcript(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")

    row = cm.record(str(repo), "T-1")

    assert row["activeTime"] == cm.UNKNOWN
    assert row["tokens"] == cm.UNKNOWN


def test_cost_and_finding_disposition_are_always_unknown_from_record(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")

    row = cm.record(str(repo), "T-1")

    assert row["cost"] == cm.UNKNOWN
    assert row["findingsConfirmed"] == cm.UNKNOWN
    assert row["findingsRejected"] == cm.UNKNOWN
    assert row["findingsDuplicate"] == cm.UNKNOWN
    assert row["escapedDefects"] == cm.UNKNOWN


def test_review_rounds_is_empty_list_not_unknown_with_no_ledger(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")

    row = cm.record(str(repo), "T-1")

    assert row["reviewRounds"] == []


# --------------------------------------------------------------------------
# transcript active-time idle cap

def test_active_time_caps_each_gap_at_the_idle_threshold(tmp_path):
    transcript = _transcript(tmp_path, [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "user", "timestamp": "2026-01-01T00:10:00Z"},  # 600s gap, capped at 300
        {"type": "user", "timestamp": "2026-01-01T00:10:05Z"},  # 5s gap, not capped
    ])

    total = cm.active_time_seconds(transcript, idle_threshold=300)

    assert total == 305.0


def test_active_time_ignores_sidechain_events(tmp_path):
    transcript = _transcript(tmp_path, [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "isSidechain": False},
        {"type": "user", "timestamp": "2026-01-01T00:00:05Z", "isSidechain": True},
        {"type": "user", "timestamp": "2026-01-01T00:00:10Z", "isSidechain": False},
    ])

    total = cm.active_time_seconds(transcript, idle_threshold=300)

    assert total == 10.0


def test_active_time_unknown_with_fewer_than_two_timestamps(tmp_path):
    transcript = _transcript(tmp_path, [{"type": "user", "timestamp": "2026-01-01T00:00:00Z"}])

    assert cm.active_time_seconds(transcript) == cm.UNKNOWN


def test_tokens_unknown_when_no_assistant_usage(tmp_path):
    transcript = _transcript(tmp_path, [{"type": "user", "timestamp": "2026-01-01T00:00:00Z"}])

    assert cm.transcript_tokens(transcript) == cm.UNKNOWN


# --------------------------------------------------------------------------
# append-only

def test_record_is_append_only(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")
    cm.record(str(repo), "T-1")
    path = cm.metrics_path(str(repo))
    with open(path, "rb") as handle:
        before = handle.read()

    make_ticket(repo, "T-2", touch=("other/**",), files=["other/keep.py"])
    approve_as_user(repo, "T-2")
    cm.record(str(repo), "T-2")

    with open(path, "rb") as handle:
        after = handle.read()
    assert after[:len(before)] == before
    assert after != before


def test_escaped_appends_rather_than_editing_the_record_row(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")
    cm.record(str(repo), "T-1")
    path = cm.metrics_path(str(repo))
    with open(path, "rb") as handle:
        before = handle.read()

    cm.escaped(str(repo), "T-1", 2, note="found in prod")

    with open(path, "rb") as handle:
        after = handle.read()
    assert after.startswith(before)
    rows, _bad = cm.read_rows(str(repo))
    assert [r["kind"] for r in rows] == ["record", "escaped"]
    effective = cm.effective_ticket_metrics(rows)
    assert effective["T-1"]["escapedDefects"] == 2


# --------------------------------------------------------------------------
# baseline / compare

def _row(ticket, schema, **fields):
    row = {"schema": schema, "kind": "record", "ticket": ticket, "ticketId": ticket,
          "recordedAt": fields.pop("recordedAt", "2026-01-01T00:00:00Z")}
    row.update(fields)
    return row


def _write_rows(root, rows):
    path = cm.metrics_path(str(root))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_baseline_reports_unknown_counts_for_migrated_rows(repo):
    _write_rows(repo, [
        {"ticket": "T-old-1", "ticketId": "T-old-1", "activeTime": "UNKNOWN", "cost": "UNKNOWN"},
        {"ticket": "T-old-2", "ticketId": "T-old-2", "activeTime": "UNKNOWN", "cost": "UNKNOWN"},
    ])

    result = cm.baseline(str(repo))

    assert result["n"] == 2
    assert result["medianActiveTime"] is None
    assert result["activeTimeUnknown"] == 2


def test_baseline_computes_median_when_a_row_was_hand_reconstructed(repo):
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old-1", "ticketId": "T-old-1", "activeTime": 100,
         "cost": "UNKNOWN"},
        {"schema": "0.20", "ticket": "T-old-2", "ticketId": "T-old-2", "activeTime": 300,
         "cost": "UNKNOWN"},
    ])

    result = cm.baseline(str(repo))

    assert result["medianActiveTime"] == 200
    assert result["activeTimeKnown"] == 2


def test_compare_below_ten_tickets_is_insufficient_data(repo):
    # Every criterion would otherwise PASS cleanly (a >=30% active-time drop,
    # known review rounds, zero unapproved scope changes, zero escaped
    # defects against a known baseline) -- the ONLY thing standing between
    # this fixture and a false PASS is the floor. A test fixture where the
    # criteria themselves also read INSUFFICIENT DATA would pass even with
    # the floor check deleted, which is the failure this guards against.
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},
    ])
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN",
                reviewRounds=[{"round": 1, "verdict": "CLEAN"}],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(5)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["verdict"] == "INSUFFICIENT DATA"
    assert result["n"] == 5


def test_compare_passes_every_criterion_on_a_clean_fixture(repo):
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},
    ])
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["verdict"] == "PASS"
    assert result["criteria"]["30pctLowerActiveTimeOrCost"] == "PASS"
    assert result["criteria"]["reviewBudgetEnforcement100pct"] == "PASS"
    assert result["criteria"]["zeroUnapprovedScopeChanges"] == "PASS"


def test_compare_fails_when_active_time_did_not_drop_enough(repo):
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},
    ])
    rows = [_row(f"T-{i}", "1.0", activeTime=950, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["criteria"]["30pctLowerActiveTimeOrCost"] == "FAIL"
    assert result["verdict"] == "FAIL"


def test_compare_flags_unapproved_scope_changes(repo):
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},
    ])
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=1 if i == 0 else 0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["unapprovedScopeChanges"] == 1
    assert result["criteria"]["zeroUnapprovedScopeChanges"] == "FAIL"
