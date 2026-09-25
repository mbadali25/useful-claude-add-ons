"""The review verdict is computed, not read off the output by eye.

CLEAN is reachable only from exactly one CLEAN line, exit 0, no timeout, and a
READ line for every bundle part. Everything that went wrong is INCOMPLETE --
never CLEAN -- because an empty or failed reviewer output looks exactly like
"no findings" to anyone skimming it (`review_verdict.py`'s docstring).
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_verdict as rv

PARTS = ("part-001-of-002.patch", "part-002-of-002.patch")
ACKS = "READ|part-001-of-002.patch\nREAD|part-002-of-002.patch\n"


def test_parse_exact_clean_with_exit_zero_is_clean():
    result = rv.parse(ACKS + "CLEAN\n", 0, expected_parts=PARTS)

    assert result["verdict"] == rv.CLEAN


def test_parse_clean_without_parts_expected_is_clean():
    result = rv.parse("CLEAN", 0)

    assert result["verdict"] == rv.CLEAN


@pytest.mark.parametrize("exit_code", [1, 2, 127, -9, None])
def test_parse_clean_text_with_a_failed_exit_is_incomplete(exit_code):
    result = rv.parse(ACKS + "CLEAN\n", exit_code, expected_parts=PARTS)

    assert result["verdict"] == rv.INCOMPLETE


@pytest.mark.parametrize("text", ["", "   \n\n", "\n"])
def test_parse_empty_output_is_incomplete(text):
    result = rv.parse(text, 0)

    assert result["verdict"] == rv.INCOMPLETE


@pytest.mark.parametrize("text", [
    "Looks good to me!",
    "CLEAN.",
    "clean",
    "CLEAN\nbut also this",
    "BLOCK|no pipes after",
    "WARN|a.py:1|x|y",
])
def test_parse_garbage_is_incomplete(text):
    result = rv.parse(text, 0)

    assert result["verdict"] == rv.INCOMPLETE


def test_parse_timeout_is_incomplete_even_with_clean_text():
    result = rv.parse("CLEAN", 0, timed_out=True)

    assert result["verdict"] == rv.INCOMPLETE


def test_parse_missing_part_acknowledgement_is_incomplete():
    result = rv.parse("READ|part-001-of-002.patch\nCLEAN\n", 0, expected_parts=PARTS)

    assert (result["verdict"], result["parts_missing"]) == (
        rv.INCOMPLETE, ["part-002-of-002.patch"])


@pytest.mark.parametrize("line,severity", [
    ("BLOCK|a.py:3|breaks x|call y", "BLOCK"),
    ("FIX|b.py:9|leaks|run it", "FIX"),
    ("NIT|c.md:1|typo|read it", "NIT"),
])
def test_parse_any_finding_is_findings(line, severity):
    result = rv.parse(ACKS + line + "\n", 0, expected_parts=PARTS)

    assert (result["verdict"], result["counts"][severity]) == (rv.FINDINGS, 1)


def test_parse_clean_beside_a_finding_is_incomplete():
    result = rv.parse("CLEAN\nFIX|a.py:1|x|y\n", 0)

    assert result["verdict"] == rv.INCOMPLETE


@pytest.mark.parametrize("text", ["```\nCLEAN\n```\n", "```text\nCLEAN\n```\n"])
def test_parse_a_code_fence_is_incomplete(text):
    """Tolerating fences was fail-open: a fence is not part of the contract,
    and whatever it wrapped was never read as one."""
    result = rv.parse(text, 0)

    assert result["verdict"] == rv.INCOMPLETE


@pytest.mark.parametrize("line", [
    "FIX|a.py:1||",
    "FIX|a.py:1|breaks|",
    "FIX|a.py:1||repro",
    "FIX||breaks|repro",
    "BLOCK| |breaks|repro",
    "NIT|a.py:1|  |repro",
    "FIX|a.py:1|breaks",
])
def test_parse_a_finding_with_an_empty_or_missing_field_is_incomplete(line):
    result = rv.parse(line, 0)

    assert result["verdict"] == rv.INCOMPLETE


def test_parse_a_finding_whose_repro_contains_a_pipe_is_findings():
    result = rv.parse("FIX|a.py:1|breaks|run `a | b`", 0)

    assert result["verdict"] == rv.FINDINGS


def _stream(*events):
    return "\n".join(json.dumps(e) for e in events)


def test_codex_final_message_reads_the_last_agent_message_of_a_completed_turn():
    stream = _stream(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "draft"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "CLEAN"}},
        {"type": "turn.completed"})

    assert rv.codex_final_message(stream) == ("CLEAN", None)


def test_codex_final_message_reports_a_failed_turn():
    stream = _stream(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "CLEAN"}},
        {"type": "turn.failed", "error": {"message": "rate limited"}})

    assert rv.codex_final_message(stream)[1] == "rate limited"


def test_codex_final_message_without_a_completion_is_an_error():
    stream = _stream(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "CLEAN"}})

    assert rv.codex_final_message(stream)[1] is not None


def test_codex_final_message_reads_the_older_msg_shape():
    stream = _stream({"msg": {"type": "agent_message", "message": "CLEAN"}},
                     {"msg": {"type": "task_complete", "last_agent_message": "CLEAN"}})

    assert rv.codex_final_message(stream) == ("CLEAN", None)


@pytest.mark.parametrize("garbage", ["not json at all", '{"type": "item.comp', "[1, 2]",
                                     "warning: something"])
def test_codex_final_message_an_unparseable_event_line_is_an_error(garbage):
    """A garbled stream that still ends in a CLEAN message and a completed
    turn used to read as clean: unreadable lines were skipped."""
    stream = _stream(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "CLEAN"}}
    ) + "\n" + garbage + "\n" + _stream({"type": "turn.completed"})

    assert rv.codex_final_message(stream)[1] is not None
