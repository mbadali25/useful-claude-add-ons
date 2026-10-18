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


@pytest.fixture(autouse=True)
def _claude_home(tmp_path, monkeypatch):
    """`record` scans Claude Code transcripts under CLAUDE_CONFIG_DIR; no case may
    read the real ~/.claude."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))


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

    assert row["schema"] == "1.1"
    assert row["scopeBlocks"] == 1  # only the "block" row for T-1
    assert row["injectedChars"] == 150  # 100 + 50, session sess-1 only
    assert row["activeTime"] == 40.0  # 10 + 30, both under the idle cap
    assert row["tokens"] == {"input": 100, "output": 20, "cacheRead": 0, "cacheCreation": 0,
                             "total": 120}
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


def test_transcript_tokens_fields_sums_only_those(tmp_path):
    """L-0541: the goal cap counts input + output; the default stays all four."""
    usage = {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 40,
             "cache_creation_input_tokens": 300}
    transcript = _transcript(tmp_path, [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:00Z", "message": {"usage": usage}},
        {"type": "assistant", "timestamp": "2026-01-01T00:00:01Z",
         "message": {"usage": {"cache_read_input_tokens": 5000}}}])

    assert (cm.transcript_tokens(transcript),
            cm.transcript_tokens(transcript, fields=("input_tokens", "output_tokens"))) == (
        5343, 3)


# --------------------------------------------------------------------------
# L-0728: each assistant message counted once

def _asst(second, mid=None, uuid=None, model="claude-opus-5-5", cwd=None, side=False, **usage):
    message = {"model": model, "usage": usage}
    if mid:
        message["id"] = mid
    record = {"type": "assistant", "timestamp": f"2026-01-01T00:00:{second:02d}Z",
              "message": message}
    if uuid:
        record["uuid"] = uuid
    if cwd:
        record["cwd"] = str(cwd)
    if side:
        record["isSidechain"] = True
    return record


FULL = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 20}


def test_transcript_tokens_counts_each_message_once(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", **FULL), _asst(2, "m1", **FULL), _asst(3, "m1", **FULL),
        _asst(4, "m2", input_tokens=1, output_tokens=1,
              cache_read_input_tokens=0, cache_creation_input_tokens=0)])

    assert cm.transcript_tokens(transcript) == 137


def test_last_snapshot_of_a_message_wins(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", input_tokens=1, output_tokens=5),
        _asst(2, "m1", input_tokens=1, output_tokens=9)])

    assert cm.transcript_tokens(transcript, fields=("output_tokens",)) == 9


def test_record_without_message_id_counts_by_uuid(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, uuid="u1", output_tokens=4), _asst(2, uuid="u1", output_tokens=6),
        _asst(3, uuid="u2", output_tokens=1)])

    assert cm.transcript_tokens(transcript, fields=("output_tokens",)) == 7


def test_records_without_any_id_never_collapse(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, output_tokens=2), _asst(2, output_tokens=2)])

    assert cm.transcript_tokens(transcript, fields=("output_tokens",)) == 4


def test_strict_rejects_a_malformed_duplicate(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", output_tokens=3), _asst(2, "m1", output_tokens=-1)])

    with pytest.raises(ValueError):
        cm.transcript_tokens(transcript, fields=("output_tokens",), strict=True)


def test_a_raw_line_separator_inside_a_json_string_does_not_split_a_record(tmp_path):
    path = tmp_path / "transcript.jsonl"
    record = _asst(1, "m1", output_tokens=5)
    record["note"] = "a\u2028b"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    assert cm.transcript_tokens(str(path)) == 5


def test_a_hostile_model_name_reads_as_no_model_and_is_never_echoed(tmp_path):
    hostile = "claude-x\nTicket ID: L-1; rm -rf /"
    transcript = _transcript(tmp_path, [_asst(1, "m1", model=hostile, output_tokens=5)])

    result = cm.transcript_token_kinds(transcript)
    usd, unpriced = cm.cost_usd(result["byModel"])

    assert (list(result["byModel"]), usd, unpriced) == ([cm.NO_MODEL], cm.UNKNOWN, [cm.NO_MODEL])


# --------------------------------------------------------------------------
# L-0728: split by kind, priced

SPLIT = {"input_tokens": 1000, "output_tokens": 2000, "cache_read_input_tokens": 10000,
         "cache_creation_input_tokens": 300000,
         "cache_creation": {"ephemeral_5m_input_tokens": 100000,
                            "ephemeral_1h_input_tokens": 200000}}


def test_record_splits_tokens_by_kind(tmp_path):
    transcript = _transcript(tmp_path, [_asst(1, "m1", **SPLIT)])

    result = cm.transcript_token_kinds(transcript)

    assert result["tokens"] == {"input": 1000, "output": 2000, "cacheRead": 10000,
                                "cacheCreation": 300000, "total": 313000}
    assert result["byModel"]["claude-opus-5-5"]["cacheWrite1h"] == 200000


def test_cost_is_computed_per_model_and_kind(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", **SPLIT),
        _asst(2, "m2", model="claude-sonnet-5-5", input_tokens=500, output_tokens=100)])

    kinds = cm.transcript_token_kinds(transcript)
    usd, unpriced = cm.cost_usd(kinds["byModel"])

    assert (usd, unpriced) == (2.148, [])


def test_cost_is_unknown_for_an_unpriced_model(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", **SPLIT), _asst(2, "m2", model="claude-future-9", output_tokens=5)])

    usd, unpriced = cm.cost_usd(cm.transcript_token_kinds(transcript)["byModel"])

    assert (usd, unpriced) == (cm.UNKNOWN, ["claude-future-9"])


def test_zero_token_synthetic_message_needs_no_price(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", **SPLIT),
        _asst(2, "m2", model="<synthetic>", input_tokens=0, output_tokens=0,
              cache_read_input_tokens=0, cache_creation_input_tokens=0)])

    usd, unpriced = cm.cost_usd(cm.transcript_token_kinds(transcript)["byModel"])

    assert (usd, unpriced) == (2.146, [])


def test_haiku_5_5_over_a_100k_prompt_is_priced_at_the_long_tier(tmp_path):
    transcript = _transcript(tmp_path, [
        _asst(1, "m1", model="claude-haiku-5-5", input_tokens=100_000, output_tokens=1_000_000),
        _asst(2, "m2", model="claude-haiku-5-5", input_tokens=100_001, output_tokens=1_000_000)])

    usd, unpriced = cm.cost_usd(cm.transcript_token_kinds(transcript)["byModel"])

    assert (usd, unpriced) == (round((100_000 * 0.10 + 1_000_000 * 0.50
                                      + 100_001 * 0.50 + 1_000_000 * 2.50) / 1_000_000, 6), [])


def test_cache_creation_without_breakdown_counts_as_five_minute(tmp_path):
    transcript = _transcript(tmp_path, [_asst(1, "m1", cache_creation_input_tokens=1000)])

    kinds = cm.transcript_token_kinds(transcript)["byModel"]["claude-opus-5-5"]

    assert (kinds["cacheWrite5m"], kinds["cacheWrite1h"]) == (1000, 0)


# --------------------------------------------------------------------------
# L-0728: attribution

def _slug_dir(path):
    base = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects",
                        cm.project_slug(os.path.realpath(str(path))))
    os.makedirs(base, exist_ok=True)
    return base


def _write_lines(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


def _session(project, name, records, sub=None):
    """Write `<name>.jsonl`, or the subagent file `<name>/subagents/<sub>`."""
    base = _slug_dir(project)
    path = os.path.join(base, name + ".jsonl") if sub is None else os.path.join(
        base, name, "subagents", sub)
    _write_lines(path, records)
    return path


def _user(second, text, cwd=None, side=False):
    rec = {"type": "user", "timestamp": f"2026-01-01T00:00:{second:02d}Z",
           "message": {"role": "user", "content": text}}
    if cwd:
        rec["cwd"] = str(cwd)
    if side:
        rec["isSidechain"] = True
    return rec


def _worktree(repo, tmp_path, branch):
    from scope_fixtures import git  # pylint: disable=import-outside-toplevel
    target = tmp_path / ("wt-" + branch)
    git(repo, "worktree", "add", "-q", "-b", branch, str(target))
    return target


def _total(used):
    return None if used["tokens"] is None else used["tokens"]["total"]


def test_attribution_by_ticket_id_line(repo):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9\nplease go"),
                          _asst(2, "m1", cwd=repo, output_tokens=7)])
    _session(repo, "s2", [_user(1, "Ticket ID: L-8"), _asst(2, "m2", cwd=repo, output_tokens=100)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (_total(used), used["files"], used["mainSessions"]) == (7, 1, 1)


@pytest.mark.parametrize("text,expected", [
    ("/crew:implement L-9", 7), ("/crew:implement L-90", None), ("run /crew:done L-9.", 7),
    ("<command-name>/crew:plan</command-name><command-args>L-9</command-args>", 7)])
def test_attribution_by_crew_command(repo, text, expected):
    _session(repo, "s1", [_user(1, text), _asst(2, "m1", cwd=repo, output_tokens=7)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert _total(used) == expected


def test_attribution_ignores_tool_results_and_meta_records(repo):
    quoted = {"type": "user", "timestamp": "2026-01-01T00:00:01Z",
              "message": {"role": "user", "content": [
                  {"type": "tool_result", "tool_use_id": "t", "content": "Ticket ID: L-9"}]}}
    meta = _user(2, "Ticket ID: L-9")
    meta["isMeta"] = True
    _session(repo, "s1", [quoted, meta, _asst(3, "m1", cwd=repo, output_tokens=7)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert used["files"] == 0


def test_attribution_ignores_main_checkout_branch(repo):
    record = _asst(1, "m1", cwd=repo, output_tokens=7)
    record["gitBranch"] = "L-9-feature"
    _session(repo, "s1", [record])

    used = cm.attributed_usage(str(repo), "L-9")

    assert used["files"] == 0


def test_attribution_by_linked_worktree(repo, tmp_path):
    tree = _worktree(repo, tmp_path, "L-9-feature")
    _session(tree, "s1", [_asst(1, "m1", cwd=tree / "src", output_tokens=7)])
    _session(tree, "s2", [_asst(1, "m2", cwd=tree, output_tokens=5),
                          _asst(2, "m3", cwd=repo, output_tokens=5)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (_total(used), used["files"]) == (7, 1)


def test_worktree_and_stamp_disagree_is_conflicting(repo, tmp_path):
    tree = _worktree(repo, tmp_path, "L-9-feature")
    _session(tree, "s1", [_user(1, "Ticket ID: L-8", cwd=tree),
                          _asst(2, "m1", cwd=tree, output_tokens=7)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["conflicting"], used["tokens"]) == (0, 1, None)


def test_message_in_two_files_counts_once(repo):
    shared = _asst(2, "m1", cwd=repo, output_tokens=7)
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"), shared])
    _session(repo, "s2", [_user(1, "Ticket ID: L-9"), shared])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (_total(used), used["files"]) == (7, 2)


def test_message_seen_under_two_owners_counts_for_neither(repo):
    shared = _asst(2, "m1", cwd=repo, output_tokens=7)
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"), shared])
    _session(repo, "s2", [_user(1, "Ticket ID: L-8"), shared])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["tokens"], used["conflictingMessages"]) == (None, 1)


def test_child_with_own_id_follows_its_own(repo):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"), _asst(2, "m1", cwd=repo, output_tokens=1)])
    _session(repo, "s1", [_user(1, "Ticket ID: L-8", side=True),
                          _asst(2, "m2", cwd=repo, side=True, output_tokens=10)],
             sub="agent-a.jsonl")

    used = cm.attributed_usage(str(repo), "L-9")

    assert (_total(used), used["subagents"]) == (1, 0)


def test_child_without_id_inherits_parent(repo):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"), _asst(2, "m1", cwd=repo, output_tokens=1)])
    _session(repo, "s1", [_user(1, "do a thing", side=True),
                          _asst(2, "m2", cwd=repo, side=True, output_tokens=10)],
             sub="agent-a.jsonl")

    used = cm.attributed_usage(str(repo), "L-9")

    assert (_total(used), used["subagents"], used["mainSessions"]) == (11, 1, 1)


def test_subagent_sidechain_records_are_counted(repo):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9")])
    path = _session(repo, "s1", [_asst(2, "m2", cwd=repo, side=True, output_tokens=10)],
                    sub="agent-a.jsonl")

    used = cm.attributed_usage(str(repo), "L-9")

    assert _total(used) == 10
    assert cm.transcript_tokens(path) == cm.UNKNOWN
    assert cm.active_time_seconds(path) == cm.UNKNOWN


def test_workflow_subagent_files_are_scanned(repo):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9")])
    _session(repo, "s1", [_asst(2, "m2", cwd=repo, side=True, output_tokens=10)],
             sub=os.path.join("workflows", "wf_abc", "agent-w.jsonl"))

    used = cm.attributed_usage(str(repo), "L-9")

    assert (_total(used), used["subagents"]) == (10, 1)


def test_a_file_with_a_malformed_line_is_unreadable_and_attributed_to_nobody(repo):
    path = _session(repo, "s1", [_user(1, "Ticket ID: L-9"),
                                 _asst(2, "m1", cwd=repo, output_tokens=7)])
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("{not json Ticket ID: L-8\n")

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["unreadable"], used["tokens"]) == (0, 1, None)


@pytest.mark.parametrize("bad", [-1, "9", True, 1.5])
def test_an_invalid_usage_count_is_never_read_as_zero(repo, bad):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"),
                          _asst(2, "m1", cwd=repo, output_tokens=bad)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["unreadable"], used["tokens"]) == (0, 1, None)


def test_transcript_tokens_is_unknown_for_an_invalid_count_unless_strict(tmp_path):
    transcript = _transcript(tmp_path, [_asst(1, "m1", output_tokens="x", input_tokens=2)])

    assert cm.transcript_tokens(transcript) == cm.UNKNOWN
    assert cm.transcript_token_kinds(transcript) == cm.UNKNOWN
    with pytest.raises(ValueError):
        cm.transcript_tokens(transcript, fields=("output_tokens",), strict=True)


def test_a_record_without_cwd_gives_no_worktree_evidence(repo, tmp_path):
    tree = _worktree(repo, tmp_path, "L-9-feature")
    nowhere = _asst(2, "m2", output_tokens=5)
    _session(tree, "s1", [_asst(1, "m1", cwd=tree, output_tokens=7), nowhere])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["tokens"]) == (0, None)


def test_a_valid_json_line_of_the_wrong_shape_makes_the_file_unreadable(repo):
    path = _session(repo, "s1", [_user(1, "Ticket ID: L-9"),
                                 _asst(3, "m1", cwd=repo, output_tokens=7)])
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("[]\n")

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["unreadable"], used["tokens"]) == (0, 1, None)


def test_an_inconsistent_cache_creation_split_is_invalid_not_reallocated(tmp_path):
    transcript = _transcript(tmp_path, [_asst(1, "m1", cache_creation_input_tokens=1000,
                                              cache_creation={"ephemeral_5m_input_tokens": 100,
                                                              "ephemeral_1h_input_tokens": 200})])

    assert cm.transcript_token_kinds(transcript) == cm.UNKNOWN


def test_a_record_of_another_type_outside_the_worktree_gives_no_worktree_evidence(repo, tmp_path):
    tree = _worktree(repo, tmp_path, "L-9-feature")
    elsewhere = {"type": "progress", "timestamp": "2026-01-01T00:00:03Z", "cwd": str(repo)}
    _session(tree, "s1", [_asst(1, "m1", cwd=tree, output_tokens=7), elsewhere])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["tokens"]) == (0, None)


def test_a_directory_that_cannot_be_listed_is_counted_unreadable(repo, monkeypatch):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"), _asst(2, "m1", cwd=repo, output_tokens=7)])
    real = os.listdir

    def refuse(path):
        if "projects" in str(path):
            raise PermissionError(13, "denied", str(path))
        return real(path)

    monkeypatch.setattr(cm.os, "listdir", refuse)

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["unreadable"], used["tokens"]) == (0, 1, None)


def test_session_switching_tickets_is_unattributed_and_counted_conflicting(repo):
    _session(repo, "s1", [_user(1, "Ticket ID: L-9"), _user(2, "/crew:implement L-8"),
                          _asst(3, "m1", cwd=repo, output_tokens=7)])

    used = cm.attributed_usage(str(repo), "L-9")

    assert (used["files"], used["conflicting"], used["tokens"]) == (0, 1, None)


def test_no_attributed_transcript_is_unknown_not_zero(repo):
    make_ticket(repo, "T-1")
    _session(repo, "s1", [_asst(1, "m1", cwd=repo, output_tokens=7)])

    row = cm.record(str(repo), "T-1")

    assert (row["tokens"], row["cost"], row["tokensBasis"]) == (
        cm.UNKNOWN, cm.UNKNOWN, "attributed lower bound")
    assert row["tokensAttribution"]["files"] == 0


def test_record_row_carries_the_measurement_group(repo):
    make_ticket(repo, "T-1")
    _session(repo, "s1", [_user(1, "Ticket ID: T-1"), _asst(2, "m1", cwd=repo, **SPLIT)])

    row = cm.record(str(repo), "T-1")

    assert row["tokens"]["total"] == 313000
    assert row["cost"] == 2.146
    assert row["tokensAttribution"] == {"files": 1, "mainSessions": 1, "subagents": 0,
                                        "conflicting": 0, "conflictingMessages": 0,
                                        "unreadable": 0}
    assert (row["pricesAsOf"], row["source"]["cost"]) == (
        cm.PRICES_AS_OF, "computed from PRICES (list price)")
    assert row["pricesSource"] == cm.PRICES_SOURCE


# --------------------------------------------------------------------------
# L-0728: fold and compare with schema 1.1 rows

def _group(tokens, cost, basis="attributed lower bound"):
    return {"tokens": tokens, "cost": cost, "tokensBasis": basis,
            "tokensAttribution": {"files": 1}, "pricesAsOf": "d", "pricesSource": "s",
            "source": {"tokens": "scan", "cost": "computed"}}


def test_mixed_schema_rows_fold():
    rows = [{"ticket": "T-a", "ticketId": "T-a", "activeTime": 5, "cost": "UNKNOWN"},
            _row("T-b", "1.0", tokens=120, cost="UNKNOWN"),
            _row("T-c", "1.1", **_group({"total": 9}, 0.5))]

    effective = cm.effective_ticket_metrics(rows)

    assert (effective["T-a"]["activeTime"], effective["T-b"]["tokens"],
            effective["T-c"]["cost"], effective["T-c"]["sourceCost"]) == (5, 120, 0.5, "computed")


def test_later_unpriced_measurement_replaces_earlier_cost():
    rows = [_row("T-1", "1.1", **_group({"total": 9}, 0.5)),
            _row("T-1", "1.1", **_group({"total": 20}, cm.UNKNOWN))]

    effective = cm.effective_ticket_metrics(rows)["T-1"]

    assert (effective["tokens"], effective["cost"]) == ({"total": 20}, cm.UNKNOWN)


def test_later_unknown_attempt_invalidates_group():
    rows = [_row("T-1", "1.1", **_group({"total": 9}, 0.5)),
            _row("T-1", "1.1", **_group(cm.UNKNOWN, cm.UNKNOWN, "not measured (--no-scan)"))]

    effective = cm.effective_ticket_metrics(rows)["T-1"]

    assert (effective["tokens"], effective["cost"]) == (cm.UNKNOWN, cm.UNKNOWN)


def test_escaped_row_keeps_group():
    rows = [_row("T-1", "1.1", **_group({"total": 9}, 0.5)),
            {"schema": "1.0", "kind": "escaped", "ticket": "T-1", "ticketId": "T-1",
             "escapedDefects": 2}]

    effective = cm.effective_ticket_metrics(rows)["T-1"]

    assert (effective["tokens"], effective["cost"], effective["escapedDefects"]) == (
        {"total": 9}, 0.5, 2)


def test_compare_selects_schema_1_1_by_count_and_date(repo):
    _write_rows(repo, [_row("T-2", "1.0", recordedAt="2026-01-01T00:00:00Z", activeTime=1),
                       _row("T-1", "1.1", recordedAt="2026-03-01T00:00:00Z", activeTime=1)])

    by_count = cm.compare(str(repo), "1")
    by_date = cm.compare(str(repo), "2026-02-01")

    assert (by_count["tickets"], by_date["tickets"]) == (["T-1"], ["T-1"])


# --------------------------------------------------------------------------
# L-0728: record CLI

def test_no_scan_reads_no_transcript(repo):
    make_ticket(repo, "T-1")
    _session(repo, "s1", [_user(1, "Ticket ID: T-1"), _asst(2, "m1", cwd=repo, output_tokens=7)])

    row = cm.record(str(repo), "T-1", scan=False)

    assert (row["tokens"], row["source"]["tokens"]) == (cm.UNKNOWN, "--no-scan")


def test_transcript_flag_disables_scan(repo, tmp_path):
    make_ticket(repo, "T-1")
    _session(repo, "s1", [_user(1, "Ticket ID: T-1"), _asst(2, "m1", cwd=repo, output_tokens=700)])
    transcript = _transcript(tmp_path, [_asst(1, "m1", output_tokens=3),
                                        _asst(2, "m1", output_tokens=4)])

    row = cm.record(str(repo), "T-1", transcript=transcript)

    assert row["tokens"]["total"] == 4
    assert row["tokensAttribution"]["files"] == 1


def test_transcript_and_no_scan_is_a_usage_error(repo, capsys):
    make_ticket(repo, "T-1")

    with pytest.raises(SystemExit) as raised:
        cm.main(["record", "--root", str(repo), "--ticket", "T-1", "--transcript", "x.jsonl",
                 "--no-scan"])

    assert raised.value.code == 2
    assert "--no-scan" in capsys.readouterr().err


def test_cost_flag_overrides_table(repo):
    make_ticket(repo, "T-1")
    _session(repo, "s1", [_user(1, "Ticket ID: T-1"), _asst(2, "m1", cwd=repo, **SPLIT)])

    row = cm.record(str(repo), "T-1", cost=1.5)

    assert (row["cost"], row["source"]["cost"]) == (1.5, "--cost")


def test_schema_flag_still_overrides(repo):
    make_ticket(repo, "T-1")

    row = cm.record(str(repo), "T-1", schema="0.20")

    assert row["schema"] == "0.20"


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


@pytest.mark.parametrize("name", ["Complete", "complete", "COMPLETE"])
def test_complete_is_reserved_not_a_ticket_id(name):
    """L-0509: the archive folder's name is never a ticket id."""
    with pytest.raises(cm.MetricsError, match="reserved"):
        cm.check_ticket(name)


@pytest.mark.parametrize("ticket", ["L-0509", "W-0001", "T-0001", "SDP-12"])
def test_ids_beyond_t_are_accepted(ticket):
    assert cm.check_ticket(ticket) == ticket
