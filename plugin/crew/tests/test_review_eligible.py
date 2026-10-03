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

import context  # noqa: F401  pylint: disable=unused-import
import review_run

_REVIEW_MD = os.path.join(context._ROOT, "commands", "review.md")  # pylint: disable=protected-access


def _snippet():
    with open(_REVIEW_MD, encoding="utf-8") as fh:
        text = fh.read()
    match = re.search(r"^ELIGIBLE=\$\(python3 -c '\n.*?' \"\$REPORT\"\)$", text, re.S | re.M)
    assert match, "review.md no longer computes $ELIGIBLE with the python one-liner"
    return match.group(0)


def _eligible(tmp_path, fall_through):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"qaFallThrough": fall_through}), encoding="utf-8")
    script = _snippet() + '\nprintf "%s" "$ELIGIBLE"\n'
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=dict(os.environ, REPORT=str(report)), check=True, timeout=30)
    return done.stdout, done.stderr


def test_an_eligible_provider_without_a_runner_is_skipped_out_loud(tmp_path):
    out, err = _eligible(tmp_path, [
        {"provider": "kimi", "eligible": True}, {"provider": "codex", "eligible": False},
        {"provider": "copilot", "eligible": True}, {"provider": "claude", "eligible": True}])

    assert out == "copilot claude"
    assert "kimi is eligible but has no review runner - skipped" in err


def test_every_runnable_provider_keeps_its_order(tmp_path):
    out, err = _eligible(tmp_path, [
        {"provider": "codex", "eligible": True}, {"provider": "copilot", "eligible": True},
        {"provider": "claude", "eligible": True}])

    assert out == "codex copilot claude"
    assert err == ""


def test_the_snippet_names_exactly_the_runner_providers():
    """Drift guard: a provider added to review_run.PROVIDERS must reach the
    snippet's list, or it would be filtered out of every review."""
    lists = set(re.findall(r"\(\"codex\", \"copilot\", \"claude\"\)", _snippet()))
    assert lists == {str(review_run.PROVIDERS).replace("'", '"')}, lists
    assert _snippet().count(str(review_run.PROVIDERS).replace("'", '"')) == 2
