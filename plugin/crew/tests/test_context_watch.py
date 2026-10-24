"""Tests for the context-watch Stop hook: threshold detection, the
wrap-up instruction, and the three loop-safety layers.

context-watch has no Python module -- it is a Stop hook shipped as a bash
script invoked as a subprocess by Claude Code. These tests run it the same
way Claude Code does: JSON on stdin, exit code and stderr as the contract.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
# Forward slashes only: MSYS bash.exe re-parses its own argv and eats bare
# backslashes in a native Windows path passed straight through subprocess.
_SH = (_ROOT + "/hooks/scripts/context-watch.sh").replace("\\", "/")

_BASH = crew_fixtures.resolve_bash()
_HAS_BASH = _BASH is not None

FLAVORS = [f for f, have in (("sh", _HAS_BASH),) if have]

# Three tests (`by_flavor`) are the sample run by default: under the
# threshold, over it, and the stop_hook_active stand-down. Every other test (`by_flavor_matrix`) is `slow`:
# `pytest -m slow` or `--run-slow` (conftest.py).
by_flavor = pytest.mark.parametrize("flavor", FLAVORS)
by_flavor_matrix = pytest.mark.parametrize(
    "flavor", [pytest.param(f, marks=crew_fixtures.SLOW) for f in FLAVORS])

# A blob with no usage record and no model is read by size alone against the
# 200k default window, warnAt=0.8 -> the threshold sits at 160,000 estimated
# tokens. EST = bytes/4*0.75: 1,000,000 bytes clears it (EST=187,500); 100
# bytes stays well under it.
_OVER_BYTES = 1_000_000
_UNDER_BYTES = 100


def _marker(root):
    """The wrap-up marker for a payload with no session_id. Markers are keyed
    on the session since the auto-cycle fix; these payloads carry none, so
    the key is the documented fallback. test_auto_cycle.py owns the keying."""
    return root / ".crew" / ".handoff-requested-nosession"


def _fired(root):
    """The reading the hook recorded in its marker when it fired."""
    return json.loads(_marker(root).read_text(encoding="utf-8"))


def _run(flavor, root, transcript_path, stop_hook_active=False):
    payload = json.dumps({
        "transcript_path": str(transcript_path),
        "cwd": str(root),
        "stop_hook_active": stop_hook_active,
    })
    # A marker makes context-watch hand over to auto-clear, which reads the
    # machine-global config under HOME. Point HOME at the fixture so the
    # developer's real opt-in can never reach a test, and inhibit the
    # keystroke besides.
    env = dict(os.environ, HOME=str(root), USERPROFILE=str(root),
               CREW_AUTOCLEAR_INHIBIT="1")
    cmd = [_BASH, _SH]
    return subprocess.run(
        cmd, input=payload, cwd=str(root), env=env,
        capture_output=True, text=True, check=False,
    )


def _transcript(root, num_bytes):
    path = root / "transcript.jsonl"
    path.write_bytes(b"x" * num_bytes)
    return path


def _config(reserve=0):
    """`reserve` is 0, the headroom floor OFF, so the cases written against the
    pure-percentage threshold keep testing exactly that. (As of 0.19.52 that
    also happens to BE the shipped default, but the pin stays -- these cases
    depend on it, and a default that moves again must not silently rewrite
    what they measure.)

    `warnAt` is likewise pinned at 0.8 -- the arithmetic in these cases was
    written against it, not against the 0.4 that ships now."""
    return {"context": {"warnAt": 0.8, "reserveTokens": reserve}}


def _usage_record(model, total, sidechain=False):
    """One assistant turn as Claude Code writes it: message.usage carries the
    prompt size split across input / cache_read / cache_creation."""
    rec = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": model,
            "usage": {
                "input_tokens": total // 10,
                "cache_read_input_tokens": total - total // 10 - 1000,
                "cache_creation_input_tokens": 1000,
                "output_tokens": 50,
            },
        },
    }
    if sidechain:
        rec["isSidechain"] = True
    return json.dumps(rec)


def _usage_transcript(root, model, used, peak=None, sidechain_total=None,
                      subagent_total=None):
    """A transcript whose LAST usage record holds `used` tokens. `peak` adds an
    earlier, larger turn (a session that has already been deeper than it is
    now). `sidechain_total` adds an inline isSidechain record; `subagent_total`
    writes a separate <session>/subagents/agent-x.jsonl beside the transcript,
    which is where Claude Code keeps Agent-tool transcripts."""
    lines = ['{"type":"user","message":{"role":"user","content":"hi"}}']
    if peak is not None:
        lines.append(_usage_record(model, peak))
    if sidechain_total is not None:
        lines.append(_usage_record(model, sidechain_total, sidechain=True))
    lines.append(_usage_record(model, used))
    path = root / "session-1.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if subagent_total is not None:
        sub = root / "session-1" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-abc.jsonl").write_text(
            _usage_record(model, subagent_total) + "\n", encoding="utf-8")
    return path


def test_flavors_are_discoverable():
    # If neither interpreter is on PATH, the parametrized tests below
    # silently collect zero cases and the suite still reports green.
    assert FLAVORS, "bash is not on PATH; cannot test context-watch"


@by_flavor
def test_below_threshold_emits_nothing(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _UNDER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not _marker(root).exists()


@by_flavor
def test_above_threshold_emits_wrap_up_instruction(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "Reach a stopping point" in result.stderr
    assert "finish or safely abandon the change in flight" in result.stderr
    assert ".work/HANDOFF.md" in result.stderr
    assert "update the ticket" in result.stderr
    assert "ready to clear" in result.stderr
    assert "Do not start new work" in result.stderr
    assert _marker(root).exists()


@by_flavor_matrix
def test_auto_wrap_up_is_constant(flavor, tmp_path):
    cfg = _config()
    cfg["context"]["autoWrapUp"] = False
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "Reach a stopping point" in result.stderr


@by_flavor_matrix
def test_budget_tokens_is_constant(flavor, tmp_path):
    cfg = _config()
    cfg["context"]["budgetTokens"] = 100
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _transcript(root, 100_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not _marker(root).exists()


@by_flavor_matrix
def test_handoff_path_is_constant(flavor, tmp_path):
    cfg = _config()
    cfg["context"]["handoffPath"] = "notes/H.md"
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert ".work/HANDOFF.md" in result.stderr
    assert "notes/H.md" not in result.stderr


@by_flavor
def test_stop_hook_active_emits_nothing_even_above_threshold(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript, stop_hook_active=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not _marker(root).exists()


@by_flavor_matrix
def test_once_per_session_marker_still_gates_repeats(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    first = _run(flavor, root, transcript)
    assert first.returncode == 2, first.stderr
    second = _run(flavor, root, transcript)
    assert second.returncode == 0, second.stderr
    assert second.stderr.strip() == "", second.stderr


# --- Real usage records: the path a live session actually takes -----------
#
# Everything above feeds a byte blob with no usage record, which exercises only
# the file-size fallback. Both flavours looked identical on that path while the
# PowerShell one had never learned to read usage at all - it fired on turn one
# of every real Windows session. These cases feed what Claude Code writes.

CLAUDE5 = ["claude-opus-5", "claude-fable-5", "claude-sonnet-5"]


@by_flavor_matrix
@pytest.mark.parametrize("model", CLAUDE5)
def test_claude5_model_at_170k_does_not_fire(flavor, model, tmp_path):
    # 170k is 85% of 200k but 17% of the 1M window these models ship with.
    # The old table said 200k and only self-corrected past 190k, so the
    # 160k-190k band fired falsely on every Claude 5 session.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _usage_transcript(root, model, used=170_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not _marker(root).exists()


@by_flavor_matrix
def test_claude5_model_at_850k_fires_against_1m(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _usage_transcript(root, "claude-fable-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "roughly 85% of the context budget" in result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (850_000, 1_000_000)
    assert _fired(root)["source"] == "exact"  # this is a measurement, say so


@by_flavor_matrix
def test_claude5_model_at_960k_still_fires_against_1m(flavor, tmp_path):
    # A real Opus 5 session on this machine held 995,862 tokens. A self-correct
    # that trips at 95% of a *correct* 1M table entry would bump the budget to
    # the 2M tier and the gate would never fire; only a peak the window cannot
    # hold proves the table wrong.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=960_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "roughly 96% of the context budget" in result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (960_000, 1_000_000)


# --- The headroom floor (context.reserveTokens) ---------------------------
#
# warnAt was tuned when every window was 200k, where 0.8 leaves 40k. The same
# 0.8 on a 1M window leaves 200k free and still asks for a handoff, which is
# the "ends a bit earlier than it should" complaint. The threshold is now the
# LATER of warnAt * budget and budget - reserveTokens, so the floor can only
# ever delay the warning, never bring it forward.


@by_flavor_matrix
def test_reserve_floor_defers_the_warning_on_a_large_window(flavor, tmp_path):
    # 850k is 85% of 1M and would have fired on the percentage alone, with
    # 150,000 tokens still free - more than a whole 200k session's worth.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(reserve=100_000), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not _marker(root).exists()


@by_flavor_matrix
def test_reserve_floor_fires_once_the_headroom_is_gone(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(reserve=100_000), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=910_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "roughly 91% of the context budget" in result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (910_000, 1_000_000)


@by_flavor_matrix
def test_reserve_floor_leaves_a_200k_window_exactly_where_it_was(flavor, tmp_path):
    # 0.8 of 200k leaves 40k, which is under the 100k floor, so the percentage
    # is the later rule and wins. This is the no-regression case: every repo on
    # a 200k model must keep firing at 80%.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(reserve=100_000), git=False)
    transcript = _usage_transcript(root, "claude-haiku-4-5-20251001", used=160_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "roughly 80% of the context budget" in result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (160_000, 200_000)


@by_flavor_matrix
def test_reserve_floor_can_never_fire_earlier_than_warn_at(flavor, tmp_path):
    # A reserve larger than the whole window makes budget - reserve negative.
    # max() must keep the percentage, not fire on turn one.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(reserve=5_000_000), git=False)
    transcript = _usage_transcript(root, "claude-haiku-4-5-20251001", used=100_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor_matrix
def test_reserve_tokens_defaults_to_zero_when_the_key_is_absent(flavor, tmp_path):
    # CHANGED in 0.19.52, and the direction matters. The floor used to default
    # to 100k, which made the threshold `max(warnAt * budget, budget - 100k)`
    # -- so on a 1M window it fired at 900k NO MATTER what warnAt said, and
    # lowering warnAt alone would have changed nothing. The floor now defaults
    # to 0, so warnAt is the rule again and an aggressive setting actually
    # bites.
    #
    # Same fixture as before (1M window, 850k used). Under the old default
    # that was BELOW the 900k floor and stayed silent; under 0.5 with no floor
    # the threshold is 500k, so it must fire.
    cfg = _config()
    del cfg["context"]["reserveTokens"]
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert _marker(root).exists()


@by_flavor_matrix
def test_reserve_tokens_zero_restores_the_pure_percentage_threshold(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(reserve=0), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert _marker(root).exists()


@by_flavor_matrix
def test_warn_at_zero_still_beats_the_reserve_floor(flavor, tmp_path):
    # warnAt 0 is the documented "always fire" override. A floor that quietly
    # outranked it would make that a lie.
    cfg = _config(reserve=100_000)
    cfg["context"]["warnAt"] = 0
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=10_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (10_000, 1_000_000)


@by_flavor_matrix
def test_haiku_at_170k_fires_against_200k(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _usage_transcript(root, "claude-haiku-4-5-20251001", used=170_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (170_000, 200_000)


@by_flavor_matrix
def test_observed_peak_overrides_the_table_window(flavor, tmp_path):
    # The table says Haiku is 200k; the session has already held 300k, so 200k
    # is provably not the window.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _usage_transcript(
        root, "claude-haiku-4-5-20251001", used=250_000, peak=300_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor_matrix
def test_subagent_usage_is_not_counted(flavor, tmp_path):
    # Agent-tool transcripts live in <session>/subagents/*.jsonl and, in older
    # Claude Code builds, as isSidechain records inline. Neither is main-window
    # occupancy: the main window only ever sees the agent's returned summary.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _usage_transcript(
        root, "claude-fable-5", used=100_000,
        sidechain_total=950_000, subagent_total=950_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor_matrix
def test_sidechain_only_transcript_does_not_feed_the_size_fallback(flavor, tmp_path):
    # No main-thread usage record at all, only inline subagent records: the
    # size fallback must not count their bytes either. Codex review finding.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    path = root / "session-1.jsonl"
    path.write_text(
        "\n".join(_usage_record("claude-fable-5", 900_000, sidechain=True)
                  for _ in range(20)) + "\n", encoding="utf-8")
    result = _run(flavor, root, path)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor_matrix
def test_warn_at_zero_means_always_fire(flavor, tmp_path):
    # 0 is falsy in PowerShell; a truthiness test silently turned it into 0.8.
    cfg = _config()
    cfg["context"]["warnAt"] = 0
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _usage_transcript(root, "claude-fable-5", used=10_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (10_000, 1_000_000)


@by_flavor
def test_measured_warning_names_the_observed_tier(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(), git=False)
    # Haiku's table entry is 200k; a 451k peak forces the observed tier (500k).
    transcript = _usage_transcript(
        root, "claude-haiku-4-5-20251001", used=450_001, peak=451_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, (flavor, result.stderr)
    assert "roughly 90% of the context budget" in result.stderr
    assert (_fired(root)["used"], _fired(root)["budget"]) == (450_001, 500_000)
