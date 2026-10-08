"""commands/review.md's `$ELIGIBLE` snippet, run as written.

`qa.order` defaults to codex, kimi, copilot, claude, but review_run.py has no
kimi runner. Before this, an eligible kimi reached `review_run.py --provider
kimi`, argparse exited 2, and review.md reads exit 2 as "not on PATH, walk to
the next" - so kimi was skipped by accident and nobody was told. The snippet
now filters to review_run.PROVIDERS and names what it skipped.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import review_run

_BASH = crew_fixtures.resolve_bash()

_REVIEW_MD = os.path.join(context._ROOT, "commands", "review.md")  # pylint: disable=protected-access


def _snippet():
    with open(_REVIEW_MD, encoding="utf-8") as fh:
        text = fh.read()
    match = re.search(r"^ELIGIBLE=\$\(python3 -c '\n.*?' \"\$REPORT\"\)$", text, re.S | re.M)
    assert match, "review.md no longer computes $ELIGIBLE with the python one-liner"
    return match.group(0)


def _eligible(tmp_path, fall_through):
    """Run the snippet in a PROVEN bash (crew_fixtures.resolve_bash: on Windows a
    bare `bash` can be WSL's), with `python3` mapped to this interpreter: Git
    Bash ships without python3 (root CLAUDE.md, Landmines), and this test is
    about the snippet's filter, not about which python a shell resolves."""
    if _BASH is None:
        pytest.skip("needs a working bash")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"qaFallThrough": fall_through}), encoding="utf-8")
    py = '"' + sys.executable.replace("\\", "/") + '"'
    script = _snippet().replace("python3 -c", py + " -c", 1) + '\nprintf "%s" "$ELIGIBLE"\n'
    done = subprocess.run([_BASH, "-c", script], capture_output=True, text=True,
                          env=dict(os.environ, REPORT=str(report)), check=True, timeout=30)
    return done.stdout, done.stderr


def test_an_eligible_provider_without_a_runner_is_skipped_out_loud(tmp_path):
    """Every QA provider has a runner since L-0527 (kimi), so a stand-in name
    plays the provider the report calls eligible and nothing can launch."""
    out, err = _eligible(tmp_path, [
        {"provider": "future", "eligible": True}, {"provider": "codex", "eligible": False},
        {"provider": "kimi", "eligible": True}, {"provider": "copilot", "eligible": True},
        {"provider": "claude", "eligible": True}])

    assert out == "kimi copilot claude"
    assert "future is eligible but has no review runner - skipped" in err


def test_every_runnable_provider_keeps_its_order(tmp_path):
    out, err = _eligible(tmp_path, [
        {"provider": "codex", "eligible": True}, {"provider": "copilot", "eligible": True},
        {"provider": "claude", "eligible": True}])

    assert out == "codex copilot claude"
    assert err == ""


def test_the_snippet_names_exactly_the_runner_providers():
    """Drift guard: a provider added to review_run.PROVIDERS must reach the
    snippet's list, or it would be filtered out of every review."""
    lists = set(re.findall(r"\(\"codex\"(?:, \"\w+\")*\)", _snippet()))
    assert lists == {str(review_run.PROVIDERS).replace("'", '"')}, lists
    assert _snippet().count(str(review_run.PROVIDERS).replace("'", '"')) == 2
