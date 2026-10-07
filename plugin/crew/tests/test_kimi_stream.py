"""kimi_probe.final_message: the Kimi Code stream-json parser (T-0028).

Moved here from test_review_verdict.py when T-0028 was split: the parser lives
in kimi_probe.py (feature code), and the review harness imports it (L-0527).
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from kimi_probe import final_message

# The breaks str.splitlines() honours beyond "\n" that a JSON encoder with
# ensure_ascii=False leaves raw inside a string; the parser must split on "\n"
# only, or an event holding one is cut mid-JSON.
JSON_RAW_BREAKS = ("\u2028", "\u2029", "\u0085")
BREAK_IDS = {"\u2028": "U+2028", "\u2029": "U+2029", "\u0085": "U+0085"}


# --- Kimi Code stream-json (T-0028) -----------------------------------------
# Shapes from PromptJsonWriter in the Kimi Code 2.1.1 bundle, read as source
# text, and checked against `fixtures/kimi-stream-2.1.1/ok.jsonl`: the owner's
# one real `kimi -p` run, captured 2026-09-25 with its session id redacted.
_KIMI_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "fixtures", "kimi-stream-2.1.1")


def _kimi(*events):
    return "\n".join(json.dumps(e) for e in events)


def test_final_message_reads_the_last_assistant_text():
    stream = _kimi({"role": "meta", "type": "system.version", "version": "2.1.1"},
                   {"role": "assistant", "content": "draft"},
                   {"role": "assistant", "content": None,
                    "tool_calls": [{"type": "function", "id": "t", "function": {}}]},
                   {"role": "tool", "tool_call_id": "t", "content": "file body"},
                   {"role": "assistant", "content": "CLEAN"})

    assert final_message(stream) == ("CLEAN", None)


def test_final_message_with_no_assistant_text_is_an_error():
    stream = _kimi({"role": "meta", "type": "system.version", "version": "2.1.1"})

    assert final_message(stream)[1] is not None


def test_final_message_reports_a_failure_record():
    stream = _kimi({"role": "assistant", "content": "CLEAN"},
                   {"role": "meta", "type": "turn.failed",
                    "error": {"code": "provider.error", "message": "stream died"}})

    assert final_message(stream)[1] == "provider.error: stream died"


def test_final_message_unparseable_line_is_an_error():
    stream = _kimi({"role": "assistant", "content": "CLEAN"}) + "\nnot json"

    assert final_message(stream)[1] is not None


def test_final_message_a_retry_alone_is_not_a_failure():
    stream = _kimi({"role": "meta", "type": "turn.step.retrying", "status_code": 500,
                    "error_message": "transient"},
                   {"role": "assistant", "content": "CLEAN"})

    assert final_message(stream) == ("CLEAN", None)


def test_final_message_joins_list_content_text_parts():
    stream = _kimi({"role": "assistant",
                    "content": [{"type": "text", "text": "READ|a"},
                                {"type": "text", "text": "\nCLEAN"}]})

    assert final_message(stream) == ("READ|a\nCLEAN", None)


def test_final_message_ignores_a_meta_line_carrying_string_content():
    """The captured run ends on a `session.resume_hint` meta line whose
    `content` is a string. Only a `role: assistant` line is the answer."""
    stream = _kimi({"role": "assistant", "content": "CLEAN"},
                   {"role": "meta", "type": "session.resume_hint",
                    "session_id": "00000000-0000-0000-0000-fixture00001",
                    "content": "To resume this session: kimi -r x"})

    assert final_message(stream) == ("CLEAN", None)


def test_final_message_parses_the_captured_fixture():
    """The owner's real 2.1.1 run: system.version, the assistant text, then
    session.resume_hint -- see that directory's README."""
    with open(os.path.join(_KIMI_FIXTURES, "ok.jsonl"), encoding="utf-8") as fh:
        stream = fh.read()

    assert final_message(stream) == ("PROBE_OK", None)


# --- the merge with main: `final_message` splits on "\n" only ------------


@pytest.mark.parametrize("sep", JSON_RAW_BREAKS, ids=[BREAK_IDS[s] for s in JSON_RAW_BREAKS])
def test_final_message_an_event_holding_a_unicode_line_break_parses_intact(sep):
    """Main's T-0072 round-4 rule, reaching the Kimi parser at the merge: a raw
    U+2028 inside an event's JSON string must not cut the event in two."""
    message = f"BLOCK|a.py:1|one{sep}two|repro"
    stream = "\n".join(json.dumps(e, ensure_ascii=False) for e in (
        {"role": "meta", "type": "system.version", "version": "2.1.1"},
        {"role": "assistant", "content": message}))

    assert (sep in stream, final_message(stream)) == (True, (message, None))


def test_final_message_tolerates_crlf_line_ends():
    stream = "\r\n".join(json.dumps(e) for e in (
        {"role": "assistant", "content": "draft"},
        {"role": "assistant", "content": "CLEAN"}))

    assert final_message(stream) == ("CLEAN", None)


# --- review round 4 FIX review_verdict.py:170: a non-string text part ----------


@pytest.mark.parametrize("text", [1, None, ["x"], {"t": "x"}, True],
                         ids=["int", "null", "list", "dict", "bool"])
def test_final_message_a_non_string_text_part_is_malformed(text):
    stream = _kimi({"role": "assistant", "content": [{"type": "text", "text": text}]})

    message, error = final_message(stream)

    assert (message, error) == (None, "malformed content part")


def test_final_message_a_malformed_part_beside_a_good_one_is_still_malformed():
    stream = _kimi({"role": "assistant", "content": [{"type": "text", "text": "CLEAN"},
                                                     {"type": "text", "text": 1}]})

    assert final_message(stream)[1] == "malformed content part"


def test_final_message_string_text_parts_still_join():
    stream = _kimi({"role": "assistant", "content": [{"type": "text", "text": "CL"},
                                                     {"type": "text", "text": "EAN"}]})

    assert final_message(stream) == ("CLEAN", None)


def test_final_message_a_non_object_content_member_is_malformed():
    """Round 5 of T-0028: CLEAN beside an unparseable list member was accepted."""
    stream = _kimi({"role": "assistant", "content": [{"type": "text", "text": "CLEAN"}, 1]})

    assert final_message(stream)[1] == "malformed content part"


def test_final_message_a_non_text_part_object_is_still_skipped():
    stream = _kimi({"role": "assistant",
                    "content": [{"type": "think", "think": "..."},
                                {"type": "text", "text": "CLEAN"}]})

    assert final_message(stream) == ("CLEAN", None)


def test_final_message_a_retry_carrying_an_error_object_is_not_a_failure():
    """Round 5 of T-0028: a retrying event whose transient failure is an
    `error` object was read as terminal, so a working Kimi was skipped."""
    stream = _kimi({"role": "meta", "type": "turn.step.retrying",
                    "error": {"code": "429", "message": "transient"}},
                   {"role": "assistant", "content": "PROBE_OK"})

    assert final_message(stream) == ("PROBE_OK", None)
