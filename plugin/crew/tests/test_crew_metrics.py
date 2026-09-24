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


def _baseline_rows(active_time, n=cm.MIN_BASELINE_KNOWN, escaped=0):
    """`n` genuinely-known 0.20 legacy rows -- enough for `compare`'s
    per-criterion known-baseline thresholds to be satisfied honestly,
    rather than by the single-row inference bug this file used to rely on."""
    return [{"schema": "0.20", "ticket": f"T-old-{i}", "ticketId": f"T-old-{i}",
             "activeTime": active_time, "cost": "UNKNOWN", "escapedDefects": escaped}
            for i in range(n)]


def test_compare_below_ten_tickets_is_insufficient_data(repo):
    # A genuinely clean baseline (10 known legacy rows, all with known
    # escapedDefects) and a genuinely clean prospective cohort (known review
    # rounds, zero unapproved scope changes, zero escaped defects) -- every
    # criterion EXCEPT the median-based one has enough known data to PASS
    # honestly. The median-based criterion alone reads INSUFFICIENT DATA
    # because only 5 prospective tickets are known, below
    # MIN_COMPARE_TICKETS -- that is "the floor", now enforced per-criterion
    # rather than by a separate early return. A fixture where every
    # criterion reads INSUFFICIENT DATA would pass even with that per-
    # criterion floor deleted, which is the failure this guards against.
    _write_rows(repo, _baseline_rows(1000))
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN",
                reviewRounds=[{"round": 1, "verdict": "CLEAN"}],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(5)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["verdict"] == "INSUFFICIENT DATA"
    assert result["n"] == 5
    assert result["criteria"]["30pctLowerActiveTimeOrCost"] == "INSUFFICIENT DATA"
    assert result["criteria"]["reviewBudgetEnforcement100pct"] == "PASS"
    assert result["criteria"]["zeroUnapprovedScopeChanges"] == "PASS"
    assert result["criteria"]["noRiseInEscapedDefects"] == "PASS"


def test_compare_passes_every_criterion_on_a_clean_fixture(repo):
    _write_rows(repo, _baseline_rows(1000))
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["verdict"] == "PASS"
    assert result["criteria"]["30pctLowerActiveTimeOrCost"] == "PASS"
    assert result["criteria"]["reviewBudgetEnforcement100pct"] == "PASS"
    assert result["criteria"]["zeroUnapprovedScopeChanges"] == "PASS"
    assert result["criteria"]["noRiseInEscapedDefects"] == "PASS"


def test_compare_fails_when_active_time_did_not_drop_enough(repo):
    _write_rows(repo, _baseline_rows(1000))
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


# --------------------------------------------------------------------------
# fix round: every field and criterion carries UNKNOWN through

def test_append_row_repairs_a_missing_trailing_newline(repo):
    path = cm.metrics_path(str(repo))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"ticket": "T-1", "ticketId": "T-1", "kind": "record"}))  # no \n

    cm.append_row(str(repo), {"ticket": "T-2", "ticketId": "T-2", "kind": "record"})

    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["ticket"] == "T-1"
    assert json.loads(lines[1])["ticket"] == "T-2"


def test_scope_blocks_unknown_when_guard_log_has_a_truncated_row(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")
    path = os.path.join(str(repo), ".crew", "guard.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("1000\tscope\tblock\n")  # crashed mid-write, only 3 of 7 fields

    row = cm.record(str(repo), "T-1")

    assert row["scopeBlocks"] == cm.UNKNOWN


def test_injected_chars_unknown_when_a_matching_record_has_no_chars(repo):
    make_ticket(repo, "T-1")
    approve_as_user(repo, "T-1")  # session "sess-1", via user-prompt
    _write_context_log(repo, [{"session": "sess-1", "event": "UserPromptSubmit"}])

    row = cm.record(str(repo), "T-1")

    assert row["injectedChars"] == cm.UNKNOWN


def test_active_time_and_tokens_unknown_with_an_unparseable_transcript_line(tmp_path):
    path = tmp_path / "transcript.jsonl"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z"}) + "\n")
        handle.write("{not valid json\n")
        handle.write(json.dumps({"type": "assistant", "timestamp": "2026-01-01T00:00:10Z",
                                 "message": {"usage": {"input_tokens": 5}}}) + "\n")

    # Both readings would otherwise be measurable from the parseable lines
    # alone (a real gap, a real usage object) -- the corrupt line must still
    # make the whole result UNKNOWN rather than silently reporting a partial
    # figure from the surviving fragment.
    assert cm.active_time_seconds(str(path)) == cm.UNKNOWN
    assert cm.transcript_tokens(str(path)) == cm.UNKNOWN


def test_active_time_sorts_by_parsed_instant_not_raw_timestamp_text(tmp_path):
    # Two events 90 minutes apart in real UTC time, but their raw ISO strings
    # compare in the OPPOSITE order lexically (an explicit "+02:00" offset
    # sorts after a same-clock-time "Z" suffix even though it names an
    # earlier instant). Sorting the raw strings misorders them; the
    # resulting negative gap is then discarded, undercounting.
    transcript = _transcript(tmp_path, [
        {"type": "user", "timestamp": "2026-01-01T01:00:00+02:00"},  # UTC 2025-12-31T23:00:00
        {"type": "user", "timestamp": "2026-01-01T00:30:00Z"},        # UTC 2026-01-01T00:30:00
    ])

    total = cm.active_time_seconds(transcript, idle_threshold=100000)

    assert total == 5400.0


def test_parse_iso_never_raises_and_rejects_naive_or_non_string_timestamps():
    assert cm._parse_iso(12345) is None
    assert cm._parse_iso(None) is None
    assert cm._parse_iso("not-a-timestamp") is None
    assert cm._parse_iso("2026-01-01T00:00:00") is None  # naive, no offset -- unmixable


def test_active_time_rejects_a_non_positive_idle_threshold(tmp_path):
    transcript = _transcript(tmp_path, [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "user", "timestamp": "2026-01-01T00:00:10Z"},
    ])

    with pytest.raises(cm.MetricsError):
        cm.active_time_seconds(transcript, idle_threshold=0)
    with pytest.raises(cm.MetricsError):
        cm.active_time_seconds(transcript, idle_threshold=-5)


def test_tokens_unknown_when_usage_object_has_no_recognized_fields(tmp_path):
    transcript = _transcript(tmp_path, [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"usage": {"some_other_field": 5}}},
    ])

    assert cm.transcript_tokens(transcript) == cm.UNKNOWN


def test_select_prospective_selects_by_the_record_rows_timestamp_not_any_row(repo):
    _write_rows(repo, [_row("T-1", "1.0", recordedAt="2026-01-01T00:00:00Z", activeTime=600)])
    cm.escaped(str(repo), "T-1", 1, note="found later")
    rows, _bad = cm.read_rows(str(repo))
    escaped_row = [r for r in rows if r["kind"] == "escaped"][0]

    # `since` is the escaped row's own (much later) timestamp -- only the
    # T-1 `record` row's timestamp should decide selection, and it is well
    # before `since`, so T-1 must not be selected just because ITS escaped
    # correction happens to be recent.
    selected = cm._select_prospective(rows, escaped_row["recordedAt"])

    assert selected == {}


def test_compare_cannot_pass_with_an_unparseable_metrics_row(repo):
    _write_rows(repo, _baseline_rows(1000))
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)
    path = cm.metrics_path(str(repo))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("{not valid json\n")

    result = cm.compare(str(repo), "10")

    assert result["unparseableRows"] == 1
    assert result["verdict"] != "PASS"


def test_30pct_criterion_is_insufficient_with_only_one_known_value_each_side(repo):
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},
    ])
    rows = [_row("T-0", "1.0", activeTime=100, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0, escapedDefects=0)]
    rows += [_row(f"T-{i}", "1.0", activeTime="UNKNOWN", cost="UNKNOWN", reviewRounds=[],
                  unapprovedScopeChanges=0, escapedDefects=0) for i in range(1, 10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    # A single known value on each side shows a huge, fake-looking drop
    # ((100-1000)/1000 = -90%) -- the old code PASSed on exactly this.
    assert result["criteria"]["30pctLowerActiveTimeOrCost"] == "INSUFFICIENT DATA"


def test_review_budget_treats_a_missing_reviewrounds_field_as_unknown(repo):
    _write_rows(repo, _baseline_rows(1000))
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN",
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(10)]  # no reviewRounds
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["reviewBudgetEnforcementRate"] == 0.0
    assert result["criteria"]["reviewBudgetEnforcement100pct"] == "FAIL"


def test_scope_change_sum_excludes_non_integer_values_from_known_count(repo):
    _write_rows(repo, _baseline_rows(1000))
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges="not-a-number" if i == 0 else 0,
                escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["unapprovedScopeChanges"] == 0
    assert result["unapprovedScopeChangesUnknown"] == 1
    assert result["criteria"]["zeroUnapprovedScopeChanges"] == "INSUFFICIENT DATA"


def test_escaped_defects_criterion_requires_a_measured_baseline(repo):
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},  # baseline never carries an escapedDefects field
    ])
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["criteria"]["noRiseInEscapedDefects"] == "INSUFFICIENT DATA"


def test_escaped_defects_criterion_requires_every_prospective_value_known(repo):
    _write_rows(repo, _baseline_rows(1000))
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=0,
                escapedDefects="UNKNOWN" if i == 0 else 0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["escapedDefectsUnknown"] == 1
    assert result["criteria"]["noRiseInEscapedDefects"] == "INSUFFICIENT DATA"


def test_overall_verdict_fails_even_when_another_criterion_is_insufficient(repo):
    # Only 1 baseline row -> the median-based criterion reads INSUFFICIENT
    # DATA. That must not swallow the definite FAIL from unapproved scope
    # changes -- any FAIL wins the overall verdict.
    _write_rows(repo, [
        {"schema": "0.20", "ticket": "T-old", "ticketId": "T-old", "activeTime": 1000,
         "cost": "UNKNOWN"},
    ])
    rows = [_row(f"T-{i}", "1.0", activeTime=600, cost="UNKNOWN", reviewRounds=[],
                unapprovedScopeChanges=1 if i == 0 else 0, escapedDefects=0) for i in range(10)]
    _write_rows(repo, rows)

    result = cm.compare(str(repo), "10")

    assert result["criteria"]["30pctLowerActiveTimeOrCost"] == "INSUFFICIENT DATA"
    assert result["criteria"]["zeroUnapprovedScopeChanges"] == "FAIL"
    assert result["verdict"] == "FAIL"
