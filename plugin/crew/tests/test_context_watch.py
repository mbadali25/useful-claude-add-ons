"""Tests for the context-watch Stop hook: threshold detection, the
autoWrapUp instruction branch, and the three loop-safety layers.

context-watch has no Python module -- it is a Stop hook shipped as a matched
pair of scripts (bash + native PowerShell) invoked as a subprocess by Claude
Code. These tests run both flavours the same way Claude Code does: JSON on
stdin, exit code and stderr as the contract.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
# Forward slashes only: MSYS bash.exe re-parses its own argv and eats bare
# backslashes in a native Windows path passed straight through subprocess.
_SH = (_ROOT + "/hooks/scripts/context-watch.sh").replace("\\", "/")
_PS1 = _ROOT + "/hooks/scripts/context-watch.ps1"


def _resolve_bash():
    """Find a bash that works when spawned directly by python's subprocess.

    Git for Windows ships bash.exe in two places. usr/bin/bash.exe is the
    raw MSYS binary: launched from a non-MSYS parent (python.exe here,
    rather than another MSYS shell) it fails to resolve its own mount
    table and cannot open ANY path, including its own script argument --
    confirmed by running a trivial one-line script and getting "No such
    file or directory" back for a file that demonstrably exists. bin/
    bash.exe is a launcher shim that bootstraps the MSYS environment
    correctly first. Prefer the shim when this looks like a Git for
    Windows install and it is present.
    """
    found = shutil.which("bash")
    if not found:
        return None
    parts = pathlib.Path(found).parts
    lower = [p.lower() for p in parts]
    if "usr" in lower and "bin" in lower:
        root = pathlib.Path(*parts[:lower.index("usr")])
        shim = root / "bin" / "bash.exe"
        if shim.exists():
            return str(shim)
    return found


_BASH = _resolve_bash()
_HAS_BASH = _BASH is not None
_HAS_PWSH = shutil.which("pwsh") is not None

FLAVORS = [f for f, have in (("sh", _HAS_BASH), ("ps1", _HAS_PWSH)) if have]

by_flavor = pytest.mark.parametrize("flavor", FLAVORS)

# budgetTokens=100, warnAt=0.8 -> the threshold sits at 80 estimated tokens.
# EST = bytes/4*0.75, so EST=80 needs bytes ~= 427. 500 bytes clears it
# (EST=93.75, pct=0.9375); 100 bytes stays well under it (EST=18.75, pct=0.1875).
_OVER_BYTES = 500
_UNDER_BYTES = 100


def _run(flavor, root, transcript_path, stop_hook_active=False):
    payload = json.dumps({
        "transcript_path": str(transcript_path),
        "cwd": str(root),
        "stop_hook_active": stop_hook_active,
    })
    if flavor == "sh":
        cmd = [_BASH, _SH]
    else:
        cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", _PS1]
    return subprocess.run(
        cmd, input=payload, cwd=str(root),
        capture_output=True, text=True, check=False,
    )


def _transcript(root, num_bytes):
    path = root / "transcript.jsonl"
    path.write_bytes(b"x" * num_bytes)
    return path


def _config(auto_wrap_up=None, budget=100, reserve=0):
    """`reserve` defaults to 0 (headroom floor OFF) so the cases written
    against the pure-percentage threshold keep testing exactly that. The
    shipped default is 100k; the tests that own the floor set it explicitly."""
    cfg = {"warnAt": 0.8, "budgetTokens": budget, "handoffPath": ".work/HANDOFF.md",
           "reserveTokens": reserve}
    if auto_wrap_up is not None:
        cfg["autoWrapUp"] = auto_wrap_up
    return {"context": cfg}


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
    assert FLAVORS, "neither bash nor pwsh is on PATH; cannot test context-watch"


@by_flavor
def test_below_threshold_emits_nothing(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _UNDER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_above_threshold_auto_wrap_up_false_emits_existing_warning_only(
        flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=False), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "write the handoff note to" in result.stderr
    assert "Reach a stopping point" not in result.stderr
    assert (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_above_threshold_default_config_behaves_like_auto_wrap_up_false(
        flavor, tmp_path):
    # autoWrapUp is absent from the fixture's config entirely -- default false.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "write the handoff note to" in result.stderr
    assert "Reach a stopping point" not in result.stderr


@by_flavor
def test_above_threshold_auto_wrap_up_true_emits_wrap_up_instruction(
        flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=True), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "Reach a stopping point" in result.stderr
    assert "finish or safely abandon the change in flight" in result.stderr
    assert ".work/HANDOFF.md" in result.stderr
    assert "update the ticket" in result.stderr
    assert "ready to clear" in result.stderr
    assert "Do not start new work" in result.stderr
    assert (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_stop_hook_active_emits_nothing_even_above_threshold(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=True), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript, stop_hook_active=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_once_per_session_marker_still_gates_repeats(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=True), git=False)
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


@by_flavor
@pytest.mark.parametrize("model", CLAUDE5)
def test_claude5_model_at_170k_does_not_fire(flavor, model, tmp_path):
    # 170k is 85% of 200k but 17% of the 1M window these models ship with.
    # The old table said 200k and only self-corrected past 190k, so the
    # 160k-190k band fired falsely on every Claude 5 session.
    root = crew_fixtures.make_repo(tmp_path, config=_config(budget=None), git=False)
    transcript = _usage_transcript(root, model, used=170_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_claude5_model_at_850k_fires_against_1m(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(budget=None), git=False)
    transcript = _usage_transcript(root, "claude-fable-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "850,000 of 1,000,000 tokens (85%)" in result.stderr
    assert "auto:claude-fable-5" in result.stderr
    assert "estimate" not in result.stderr  # this is a measurement, say so


@by_flavor
def test_claude5_model_at_960k_still_fires_against_1m(flavor, tmp_path):
    # A real Opus 5 session on this machine held 995,862 tokens. A self-correct
    # that trips at 95% of a *correct* 1M table entry would bump the budget to
    # the 2M tier and the gate would never fire; only a peak the window cannot
    # hold proves the table wrong.
    root = crew_fixtures.make_repo(tmp_path, config=_config(budget=None), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=960_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "960,000 of 1,000,000 tokens (96%)" in result.stderr
    assert "Budget source: auto:claude-opus-5." in result.stderr


# --- The headroom floor (context.reserveTokens) ---------------------------
#
# warnAt was tuned when every window was 200k, where 0.8 leaves 40k. The same
# 0.8 on a 1M window leaves 200k free and still asks for a handoff, which is
# the "ends a bit earlier than it should" complaint. The threshold is now the
# LATER of warnAt * budget and budget - reserveTokens, so the floor can only
# ever delay the warning, never bring it forward.


@by_flavor
def test_reserve_floor_defers_the_warning_on_a_large_window(flavor, tmp_path):
    # 850k is 85% of 1M and would have fired on the percentage alone, with
    # 150,000 tokens still free - more than a whole 200k session's worth.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=None, reserve=100_000), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_reserve_floor_fires_once_the_headroom_is_gone(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=None, reserve=100_000), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=910_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "910,000 of 1,000,000 tokens (91%)" in result.stderr
    assert "Headroom left: 90,000 tokens" in result.stderr
    assert "Threshold: 900,000 tokens" in result.stderr
    assert "the later of warnAt 80%" in result.stderr


@by_flavor
def test_reserve_floor_leaves_a_200k_window_exactly_where_it_was(flavor, tmp_path):
    # 0.8 of 200k leaves 40k, which is under the 100k floor, so the percentage
    # is the later rule and wins. This is the no-regression case: every repo on
    # a 200k model must keep firing at 80%.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=200_000, reserve=100_000), git=False)
    transcript = _usage_transcript(root, "claude-haiku-4-5-20251001", used=160_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "160,000 of 200,000 tokens (80%)" in result.stderr
    assert "Threshold: 160,000 tokens" in result.stderr


@by_flavor
def test_reserve_floor_can_never_fire_earlier_than_warn_at(flavor, tmp_path):
    # A reserve larger than the whole window makes budget - reserve negative.
    # max() must keep the percentage, not fire on turn one.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=200_000, reserve=5_000_000), git=False)
    transcript = _usage_transcript(root, "claude-haiku-4-5-20251001", used=100_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor
def test_reserve_tokens_defaults_to_100k_when_the_key_is_absent(flavor, tmp_path):
    # The shipped default. An existing config that predates reserveTokens must
    # get the floor without being edited -- which is the whole point, since the
    # complaint came from repos whose config nobody is going to revisit.
    cfg = _config(budget=None)
    del cfg["context"]["reserveTokens"]
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor
def test_reserve_tokens_zero_restores_the_pure_percentage_threshold(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=None, reserve=0), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=850_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "context.reserveTokens is off" in result.stderr


@by_flavor
def test_warn_at_zero_still_beats_the_reserve_floor(flavor, tmp_path):
    # warnAt 0 is the documented "always fire" override. A floor that quietly
    # outranked it would make that a lie.
    cfg = _config(budget=None, reserve=100_000)
    cfg["context"]["warnAt"] = 0
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=10_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "10,000 of 1,000,000 tokens (1%)" in result.stderr


@by_flavor
def test_haiku_at_170k_fires_against_200k(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(budget=None), git=False)
    transcript = _usage_transcript(root, "claude-haiku-4-5-20251001", used=170_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "170,000 of 200,000 tokens (85%)" in result.stderr


@by_flavor
def test_observed_peak_overrides_smaller_configured_budget(flavor, tmp_path):
    # A stale `budgetTokens: 200000` pinned by an older /crew:init. The session
    # has already held 300k, so 200k is provably not the window.
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=200_000), git=False)
    transcript = _usage_transcript(
        root, "claude-opus-5", used=250_000, peak=300_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor
def test_configured_budget_still_wins_when_observed_fits_inside_it(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(budget=200_000), git=False)
    transcript = _usage_transcript(root, "claude-opus-5", used=170_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "170,000 of 200,000 tokens (85%)" in result.stderr
    assert "Budget source: configured." in result.stderr


@by_flavor
def test_subagent_usage_is_not_counted(flavor, tmp_path):
    # Agent-tool transcripts live in <session>/subagents/*.jsonl and, in older
    # Claude Code builds, as isSidechain records inline. Neither is main-window
    # occupancy: the main window only ever sees the agent's returned summary.
    root = crew_fixtures.make_repo(tmp_path, config=_config(budget=None), git=False)
    transcript = _usage_transcript(
        root, "claude-fable-5", used=100_000,
        sidechain_total=950_000, subagent_total=950_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor
def test_sidechain_only_transcript_does_not_feed_the_size_fallback(flavor, tmp_path):
    # No main-thread usage record at all, only inline subagent records: the
    # size fallback must not count their bytes either. Codex review finding.
    root = crew_fixtures.make_repo(tmp_path, config=_config(budget=100), git=False)
    path = root / "session-1.jsonl"
    path.write_text(
        "\n".join(_usage_record("claude-fable-5", 900_000, sidechain=True)
                  for _ in range(20)) + "\n", encoding="utf-8")
    result = _run(flavor, root, path)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


@by_flavor
def test_warn_at_zero_means_always_fire(flavor, tmp_path):
    # 0 is falsy in PowerShell; a truthiness test silently turned it into 0.8.
    cfg = _config(budget=None)
    cfg["context"]["warnAt"] = 0
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = _usage_transcript(root, "claude-fable-5", used=10_000)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "10,000 of 1,000,000 tokens (1%)" in result.stderr


def test_measured_warning_is_identical_across_flavors(tmp_path):
    # Full-stderr parity on the measured path, digits included: both flavours
    # truncate the percentage and format thousands the same way.
    if not (_HAS_BASH and _HAS_PWSH):
        pytest.skip("need both bash and pwsh on PATH to compare flavors")
    texts = {}
    for flavor in ("sh", "ps1"):
        root = crew_fixtures.make_repo(
            tmp_path / flavor, config=_config(budget=None), git=False)
        # Haiku's table entry is 200k; a 451k peak forces the +observed
        # branch (tier 500k), so the longest note in the script is compared.
        transcript = _usage_transcript(
            root, "claude-haiku-4-5-20251001", used=450_001, peak=451_000)
        result = _run(flavor, root, transcript)
        assert result.returncode == 2, (flavor, result.stderr)
        assert "450,001 of 500,000 tokens (90%)" in result.stderr
        assert "+observed" in result.stderr
        texts[flavor] = result.stderr.replace("\r\n", "\n").strip()
    assert texts["sh"] == texts["ps1"]


def test_headroom_floor_warning_is_identical_across_flavors(tmp_path):
    # The floor adds its own text to both scripts; the parity check above runs
    # with the floor off, so without this case the two could drift on exactly
    # the branch this feature owns.
    if not (_HAS_BASH and _HAS_PWSH):
        pytest.skip("need both bash and pwsh on PATH to compare flavors")
    texts = {}
    for flavor in ("sh", "ps1"):
        root = crew_fixtures.make_repo(
            tmp_path / flavor, config=_config(budget=None, reserve=100_000),
            git=False)
        transcript = _usage_transcript(root, "claude-opus-5", used=910_000)
        result = _run(flavor, root, transcript)
        assert result.returncode == 2, (flavor, result.stderr)
        texts[flavor] = result.stderr.replace("\r\n", "\n").strip()
    assert texts["sh"] == texts["ps1"]


def test_auto_wrap_up_instruction_is_identical_across_flavors(tmp_path):
    # "Both flavours must behave identically" is a real claim, not an
    # assumption -- substring checks in the tests above would not have
    # caught the two scripts drifting apart. Compare full stderr, not just
    # a few keywords, for the branch this task owns.
    if not (_HAS_BASH and _HAS_PWSH):
        pytest.skip("need both bash and pwsh on PATH to compare flavors")
    texts = {}
    for flavor in ("sh", "ps1"):
        root = crew_fixtures.make_repo(
            tmp_path / flavor, config=_config(auto_wrap_up=True), git=False)
        transcript = _transcript(root, _OVER_BYTES)
        result = _run(flavor, root, transcript)
        assert result.returncode == 2, (flavor, result.stderr)
        # Normalize line endings (PowerShell's WriteLine emits CRLF, bash's
        # heredoc emits LF) and the percentage digits: bash's estimate
        # truncates (python int()) where PowerShell's rounds ([int] cast),
        # a one-off pre-existing divergence in the shared math, not the
        # instruction text this task owns.
        text = result.stderr.replace("\r\n", "\n").strip()
        texts[flavor] = re.sub(r"\d+%", "N%", text)
    assert texts["sh"] == texts["ps1"]
