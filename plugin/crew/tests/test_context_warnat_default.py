"""The shipped default for context.warnAt is 0.4 (L-0805, crew 1.2.40).

One key drives the handoff warning, auto wrap-up and auto-clear, so the
default is pinned at every site that states it: the state dict, the config
template, the Python note, and both hook flavours run with NO warnAt in the
config. A 1M window fires at 400k, not 500k.
"""
import json

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

import crew_context
import crew_state
import test_context_watch as watch

_MODEL = "claude-opus-5"


def _config_without_warn_at():
    cfg = watch._config()  # pylint: disable=protected-access
    del cfg["context"]["warnAt"]
    return cfg


def test_context_defaults_warn_at_is_forty_percent():
    assert crew_state.CONTEXT_DEFAULTS["warnAt"] == 0.4


def test_config_template_warn_at_is_forty_percent():
    path = watch._ROOT + "/templates/config.template.json"  # pylint: disable=protected-access
    with open(path, encoding="utf-8") as handle:
        template = json.load(handle)

    assert template["context"]["warnAt"] == 0.4


def _low_note(tmp_path, used, cfg_context):
    transcript = tmp_path / "t.jsonl"
    usage = {"message": {"model": _MODEL, "usage": {
        "input_tokens": 10, "cache_read_input_tokens": used, "cache_creation_input_tokens": 0}}}
    transcript.write_text(json.dumps(usage) + "\n", encoding="utf-8")
    state = {"epoch": "e1", "lowNoted": []}
    return crew_context.low_context_note(
        state, {"transcript_path": str(transcript)}, {"context": cfg_context})


def test_low_context_note_fires_at_forty_percent_of_a_1m_window(tmp_path):
    note = _low_note(tmp_path, 450_000, {"reserveTokens": 700_000})

    assert note is not None


def test_low_context_note_is_silent_below_forty_percent_of_a_1m_window(tmp_path):
    note = _low_note(tmp_path, 350_000, {"reserveTokens": 700_000})

    assert note is None


def test_budget_tokens_is_constant(tmp_path):
    note = _low_note(tmp_path, 50_000, {"reserveTokens": 700_000, "budgetTokens": 100_000})

    assert note is None


def test_low_context_note_out_of_range_warn_at_falls_back_to_forty_percent(tmp_path):
    note = _low_note(tmp_path, 450_000, {"reserveTokens": 700_000, "warnAt": 7})

    assert note is not None


def _flavour_run(flavor, tmp_path, used):
    root = crew_fixtures.make_repo(tmp_path, config=_config_without_warn_at(), git=False)
    transcript = watch._usage_transcript(root, _MODEL, used=used)  # pylint: disable=protected-access
    return watch._run(flavor, root, transcript)  # pylint: disable=protected-access


@watch.by_flavor_matrix
def test_hook_fires_at_forty_percent_when_warn_at_is_unset(flavor, tmp_path):
    result = _flavour_run(flavor, tmp_path, 450_000)

    assert result.returncode == 2, result.stderr
    assert "roughly 45% of the context budget" in result.stderr


@watch.by_flavor_matrix
def test_hook_is_silent_below_forty_percent_when_warn_at_is_unset(flavor, tmp_path):
    result = _flavour_run(flavor, tmp_path, 350_000)

    assert result.returncode == 0, result.stderr


@watch.by_flavor_matrix
def test_explicit_warn_at_is_kept_over_the_new_default(flavor, tmp_path):
    cfg = _config_without_warn_at()
    cfg["context"]["warnAt"] = 0.5
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    transcript = watch._usage_transcript(root, _MODEL, used=450_000)  # pylint: disable=protected-access

    result = watch._run(flavor, root, transcript)  # pylint: disable=protected-access

    assert result.returncode == 0, result.stderr
