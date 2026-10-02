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
LISTED = ("/s/b/part-001-of-002.patch", "/s/b/part-002-of-002.patch")
# Every break str.splitlines() honours beyond "\n" and "\r". Codex prints the
# first three raw inside JSON strings, as json.dumps(ensure_ascii=False) does;
# it escapes the C0 controls, so those reach only the verdict text raw.
UNICODE_BREAKS = (" ", " ", "\u0085", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e")
JSON_RAW_BREAKS = (" ", " ", "\u0085")
BREAK_IDS = {" ": "U+2028", " ": "U+2029", "\u0085": "U+0085", "\x0b": "VT",
             "\x0c": "FF", "\x1c": "FS", "\x1d": "GS", "\x1e": "RS"}


def _acks(tokens):
    return "".join(f"READ|{token}\n" for token in tokens)


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


def test_parse_a_full_path_read_counts_for_its_listed_part():
    """The prompt lists every part by its full path; a reviewer that echoes
    that path back was scored INCOMPLETE until T-0079 (T-0009 round 4)."""
    result = rv.parse(_acks(LISTED) + "CLEAN\n", 0, expected_parts=LISTED)

    assert (result["verdict"], result["parts_missing"]) == (rv.CLEAN, [])


def test_parse_a_bare_name_read_counts_for_its_listed_part():
    result = rv.parse(_acks(PARTS) + "CLEAN\n", 0, expected_parts=LISTED)

    assert (result["verdict"], result["parts_missing"]) == (rv.CLEAN, [])


@pytest.mark.parametrize("listed,token", [
    ("C:\\s\\b\\part-001-of-001.patch", "C:/s/b/part-001-of-001.patch"),
    ("C:/s/b/part-001-of-001.patch", "C:\\s\\b\\part-001-of-001.patch"),
    ("/s/b/part-001-of-001.patch", "/s/b/x/../part-001-of-001.patch"),
    ("/s/b/part-001-of-001.patch", "./part-001-of-001.patch"),
])
def test_parse_a_differently_spelled_listed_path_counts(listed, token):
    result = rv.parse(f"READ|{token}\nCLEAN\n", 0, expected_parts=(listed,))

    assert (result["verdict"], result["parts_missing"]) == (rv.CLEAN, [])


def test_parse_a_read_of_a_path_outside_the_bundle_counts_for_nothing():
    result = rv.parse(_acks((LISTED[0], "/etc/passwd")) + "CLEAN\n", 0,
                      expected_parts=LISTED)

    assert (result["verdict"], result["parts_missing"]) == (rv.INCOMPLETE, [LISTED[1]])


def test_parse_a_same_basename_in_another_directory_counts_for_nothing():
    """A file name alone is not an identity: part-002 of some other bundle is
    not this bundle's part-002."""
    result = rv.parse(_acks((LISTED[0], "/tmp/other/part-002-of-002.patch")) + "CLEAN\n", 0,
                      expected_parts=LISTED)

    assert (result["verdict"], result["parts_missing"]) == (rv.INCOMPLETE, [LISTED[1]])


def test_parse_a_listed_path_with_a_space_counts():
    listed = ("/s/Some One/part-001-of-001.patch",)

    result = rv.parse(f"READ|{listed[0]}\nCLEAN\n", 0, expected_parts=listed)

    assert (result["verdict"], result["parts_missing"]) == (rv.CLEAN, [])


def test_parse_an_unlisted_read_beside_full_coverage_adds_no_reason():
    result = rv.parse(_acks(LISTED + ("/elsewhere/notes.txt",)) + "CLEAN\n", 0,
                      expected_parts=LISTED)

    assert (result["verdict"], result["reasons"]) == (rv.CLEAN, [])


def test_parse_an_empty_read_token_is_unparseable():
    result = rv.parse("READ|\nCLEAN\n", 0)

    assert result["verdict"] == rv.INCOMPLETE and any(
        "match no part of the contract" in reason for reason in result["reasons"])


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
    """A fence beside CLEAN is never recovered: CLEAN is exact (L-0576), so
    skipping fences here would let a wrapped CLEAN pass as one."""
    result = rv.parse(text, 0)

    assert result["verdict"] == rv.INCOMPLETE


FIX_LINE = "FIX|a.py:1|breaks|run it"
BLOCK_LINE = "BLOCK|b.py:2|breaks badly|call it"


@pytest.mark.parametrize("before,after", [
    ([], ["The sabotage entries need `--run-slow`; sabotage.py passes it, so they are fine."]),
    (["## Findings"], []),
    (["```"], ["```"]),
    (["```text"], ["```"]),
    (["```FIX"], ["```"]),
    (["~~~"], ["~~~"]),
    (["Two defects below."], ["", "Everything else reads correctly."]),
])
def test_parse_harmless_stray_lines_beside_findings_are_recovered(before, after):
    """T-0100 round 2: both parts READ, four well-formed findings, exit 0,
    and one trailing paragraph scored the round INCOMPLETE (L-0576)."""
    text = ACKS + "\n".join(before + [FIX_LINE, BLOCK_LINE] + after) + "\n"

    result = rv.parse(text, 0, expected_parts=PARTS)

    assert (result["verdict"], result["reasons"], result["ignored"], result["counts"]) == (
        rv.FINDINGS, [], [line for line in before + after if line],
        {"BLOCK": 1, "FIX": 1, "NIT": 0})


def test_parse_ignored_lines_are_kept_verbatim():
    """Review round 1 FIX: the ignored lines were stored stripped."""
    text = ACKS + f"{FIX_LINE}\n  Closing note, indented.  \r\n"

    result = rv.parse(text, 0, expected_parts=PARTS)

    assert (result["verdict"], result["ignored"]) == (
        rv.FINDINGS, ["  Closing note, indented.  "])


@pytest.mark.parametrize("stray", ["Looks fine.", "## Verdict", "```"])
def test_parse_clean_with_any_stray_line_is_incomplete(stray):
    result = rv.parse(ACKS + f"{stray}\nCLEAN\n", 0, expected_parts=PARTS)

    assert (result["verdict"], result["ignored"]) == (rv.INCOMPLETE, [])


@pytest.mark.parametrize("stray", [
    "- FIX|a.py:1|breaks|repro",
    "`BLOCK|a.py:1|breaks|repro`",
    "**FIX**|a.py:1|breaks|repro",
    "1. NIT|a.py:1|typo|read it",
    "fix|a.py:1|breaks|repro",
    "Block: a.py:1 breaks on empty input",
    "- **BLOCK** a.py:1 breaks on empty input",
    "**FIX:** a.py:1 leaks a handle",
    "> READ part-002-of-002.patch",
    "BLOCK a.py:1 breaks on empty input",
    "FIX|a.py:1|breaks",
    "READ part-001-of-002.patch",
    "read|part-001-of-002.patch",
    "Clean.",
    "| a.py:1 | breaks | repro |",
    "a.py:1 | breaks | repro | more",
    "INCOMPLETE: I did not read all 30 patch parts in full.",
    "Note: this review is incomplete; part 2 was skimmed.",
    "block a.py:1 deletes user data",
    "Fix the retry loop in a.py:1 before landing.",
    "I could not review part 2; its contents were truncated.",
    "Part 2 was not fully read.",
    "Skipped the generated files.",
    "I ran out of time before the last part.",
    "Only a partial pass over the tests.",
])
def test_parse_a_contract_like_stray_line_is_incomplete(stray):
    """A line that may be a finding, READ or verdict the parser failed to
    read is "could not tell", never ignorable prose (L-0576)."""
    result = rv.parse(ACKS + f"{FIX_LINE}\n{stray}\n", 0, expected_parts=PARTS)

    assert (result["verdict"], result["ignored"]) == (rv.INCOMPLETE, [])
    assert any("match no part of the contract" in r for r in result["reasons"]), result


@pytest.mark.parametrize("acks,exit_code,timed_out", [
    ("READ|part-001-of-002.patch\n", 0, False),
    (ACKS, 1, False),
    (ACKS, None, False),
    (ACKS, 0, True),
])
def test_parse_recovery_never_masks_another_reason(acks, exit_code, timed_out):
    result = rv.parse(acks + f"{FIX_LINE}\nSome prose.\n", exit_code, timed_out,
                      expected_parts=PARTS)

    assert (result["verdict"], result["ignored"]) == (rv.INCOMPLETE, [])
    assert any("match no part of the contract" in r for r in result["reasons"]), result


def test_parse_a_prior_reason_rules_recovery_out():
    """A reason found outside the text (a Codex stream error, a bundle part
    that changed) makes the round INCOMPLETE before recovery is considered."""
    result = rv.parse(ACKS + f"{FIX_LINE}\nSome prose.\n", 0, expected_parts=PARTS,
                      prior_reasons=["bundle part changed"])

    assert (result["verdict"], result["ignored"], result["reasons"][0]) == (
        rv.INCOMPLETE, [], "bundle part changed")
    assert any("match no part of the contract" in r for r in result["reasons"]), result


@pytest.mark.parametrize("text,verdict", [
    (ACKS + "CLEAN\n", rv.CLEAN),
    (ACKS + FIX_LINE + "\n", rv.FINDINGS),
    ("Only prose here.\n", rv.INCOMPLETE),
])
def test_parse_ignored_is_empty_when_nothing_was_ignored(text, verdict):
    result = rv.parse(text, 0, expected_parts=PARTS if text.startswith("READ") else ())

    assert (result["verdict"], result["ignored"]) == (verdict, [])


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


@pytest.mark.parametrize("sep", UNICODE_BREAKS, ids=[BREAK_IDS[s] for s in UNICODE_BREAKS])
def test_parse_a_verdict_line_holding_a_unicode_line_break_is_one_line(sep):
    """splitlines() cut this line in two and scored the halves unparseable;
    reviewer output is split on "\\n" only (T-0079 amendment)."""
    line = f"BLOCK|a.py:1|one{sep}two|repro"

    result = rv.parse(ACKS + line + "\n", 0, expected_parts=PARTS)

    assert (result["verdict"], result["findings"], result["reasons"]) == (rv.FINDINGS, [line], [])


def test_parse_crlf_line_ends_still_parse():
    result = rv.parse(ACKS.replace("\n", "\r\n") + "CLEAN\r\n", 0, expected_parts=PARTS)

    assert result["verdict"] == rv.CLEAN


def _stream(*events):
    return "\n".join(json.dumps(e) for e in events)


def _raw_stream(*events):
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


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


@pytest.mark.parametrize("sep", JSON_RAW_BREAKS, ids=[BREAK_IDS[s] for s in JSON_RAW_BREAKS])
def test_codex_final_message_an_event_holding_a_unicode_line_break_parses_intact(sep):
    """T-0072 round 4: a raw U+2028 inside an event's JSON string cut the
    event in two under splitlines(), and the round read INCOMPLETE."""
    message = f"BLOCK|a.py:1|one{sep}two|repro"
    stream = _raw_stream(
        {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
        {"type": "turn.completed"})

    assert (sep in stream, rv.codex_final_message(stream)) == (True, (message, None))


def test_codex_final_message_tolerates_crlf_line_ends():
    stream = "\r\n".join(json.dumps(e) for e in (
        {"type": "item.completed", "item": {"type": "agent_message", "text": "draft"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "CLEAN"}},
        {"type": "turn.completed"}))

    assert rv.codex_final_message(stream) == ("CLEAN", None)
