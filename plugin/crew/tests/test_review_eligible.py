"""`review_run.eligible`, the provider filter `/crew:review --prepare` prints as ELIGIBLE.

`qa.order` defaults to codex, kimi, copilot, claude, but review_run.py may have
no runner for a provider the report calls eligible. Before L-0527 an eligible
kimi reached `review_run.py --provider kimi`, argparse exited 2, and that read
as "not on PATH, walk to the next" - so kimi was skipped by accident and nobody
was told. The filter keeps review_run.PROVIDERS and names what it skipped.
(Until L-0726 this ran review.md's `$ELIGIBLE` snippet in bash.)
"""
import context  # noqa: F401  pylint: disable=unused-import
import review_run


def _eligible(fall_through):
    said = []
    out = review_run.eligible({"qaFallThrough": fall_through}, said.append)
    return " ".join(out), "".join(said)


def test_an_eligible_provider_without_a_runner_is_skipped_out_loud():
    """Every QA provider has a runner since L-0527 (kimi), so a stand-in name
    plays the provider the report calls eligible and nothing can launch."""
    out, err = _eligible([
        {"provider": "future", "eligible": True}, {"provider": "codex", "eligible": False},
        {"provider": "kimi", "eligible": True}, {"provider": "copilot", "eligible": True},
        {"provider": "claude", "eligible": True}])

    assert out == "kimi copilot claude"
    assert "future is eligible but has no review runner - skipped" in err


def test_every_runnable_provider_keeps_its_order():
    out, err = _eligible([
        {"provider": "codex", "eligible": True}, {"provider": "copilot", "eligible": True},
        {"provider": "claude", "eligible": True}])

    assert out == "codex copilot claude"
    assert err == ""


def test_the_filter_keeps_exactly_the_runner_providers():
    """Drift guard: every provider in review_run.PROVIDERS passes the filter."""
    rows = [{"provider": p, "eligible": True} for p in review_run.PROVIDERS]

    out, err = _eligible(rows)

    assert out.split() == list(review_run.PROVIDERS) and err == ""


def test_an_absent_or_empty_report_is_an_empty_list_not_an_error():
    assert review_run.eligible({}) == [] and review_run.eligible({"qaFallThrough": None}) == []
