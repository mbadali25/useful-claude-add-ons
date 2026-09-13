"""The ten-question gate, measured rather than described.

`crew_change` is the only mechanical part of `/crew:change`. Everything else
about the feature is prose an agent reads, so if this file is weak the whole
gate is prose too -- and a gate that is prose is the "I checked the answers"
claim CLAUDE.md's first lesson is about.

Four properties, and each is its own test function so a mutation that trips
one cannot claim coverage of another (`sabotage.py`'s header, on the vacuous
assertion it measured):

  * empty and whitespace-only boxes are UNANSWERED;
  * a placeholder is refused even though the box is not empty;
  * a fully answered request passes, with no finding at all;
  * `new` and `close` gate DIFFERENT questions, in both directions.
"""
import json
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_change
import pytest


def _answered(numbers):
    """A complete-looking answer for each of `numbers`.

    Deliberately real sentences rather than `"x"`: `"x"` is on PLACEHOLDERS,
    so a fixture built from it would make every "this passes" assertion below
    vacuously false and every "this refuses" assertion vacuously true.
    """
    return {n: f"A real answer to question {n}, with specifics in it."
            for n in numbers}


# ---- unanswered ------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "\t\n ", None, 0, [], {}])
def test_an_empty_or_unreadable_box_is_unanswered(value):
    """Whitespace-only is the case a `if not value` check would pass: the
    string is truthy. The non-strings are the fail-closed half -- a value the
    gate cannot read is UNANSWERED, never "probably fine"."""
    finding = crew_change.check_answer(1, value)

    assert finding is not None, value
    assert finding["kind"] == crew_change.UNANSWERED
    assert finding["number"] == 1
    assert finding["question"] == dict(crew_change.QUESTIONS)[1]


def test_a_missing_key_is_unanswered_not_a_crash():
    """The common shape: the operator answered eight of nine and the ninth key
    is simply absent from the mapping."""
    findings = crew_change.validate_new(_answered(range(1, 9)))

    assert [f["number"] for f in findings] == [9]
    assert findings[0]["kind"] == crew_change.UNANSWERED


# ---- placeholders ----------------------------------------------------------


@pytest.mark.parametrize("value", [
    "TBD", "tbd", " TBD. ", "**TBD**", "N/A", "n/a", "NA",
    "see above", "See Above", "Same as above", "none", "None",
    "?", "unknown", "pending", "TODO",
])
def test_a_placeholder_is_refused_and_named_as_one(value):
    """The box is not empty, so an emptiness check passes it. Case, surrounding
    punctuation and markdown emphasis are all normalised away, because
    `**TBD**` and `TBD.` are the same non-answer typed by someone being tidy."""
    finding = crew_change.check_answer(8, value)

    assert finding is not None, value
    assert finding["kind"] == crew_change.PLACEHOLDER
    # The refusal quotes what was TYPED, not the normalised form -- somebody
    # who wrote `**TBD**` has to recognise their own box.
    assert finding["given"] == value


def test_every_placeholder_entry_can_actually_be_matched():
    """A dead entry in a safety list reads as coverage it does not have.

    `normalise_answer` runs BEFORE the set is consulted, so an entry that does
    not survive normalisation can never be compared against anything. Three
    were in exactly that state -- `-`, `--` and `...`, all stripped to the
    empty string by `_TRIM` -- and they were invisible because the other arm
    still refused them, as UNANSWERED. Asserting the KIND is what exposed it;
    this asserts the property directly so the fourth one cannot arrive
    silently."""
    for entry in sorted(crew_change.PLACEHOLDERS):
        assert crew_change.normalise_answer(entry) == entry, entry
        finding = crew_change.check_answer(1, entry)
        assert finding is not None, entry
        assert finding["kind"] == crew_change.PLACEHOLDER, entry


def test_no_is_a_real_answer_and_is_not_a_placeholder():
    """Question 9 is "has there been a notification sent to those affected?",
    and `no` answers it completely. A gate that refused `no` would be refusing
    the truth, which is why `no` is deliberately absent from PLACEHOLDERS.

    Its own test rather than a line inside another: this is the assertion most
    likely to be broken by somebody "improving" the placeholder list."""
    assert crew_change.check_answer(9, "No") is None
    assert crew_change.check_answer(9, "No, not yet.") is None


def test_a_placeholder_word_inside_a_real_answer_is_not_a_placeholder():
    """Matched against the WHOLE normalised answer, never as a substring.
    "none of the databases are affected" is a real answer that contains
    "none"; a substring match would refuse it and teach the operator to fight
    the gate."""
    assert crew_change.check_answer(
        4, "None of the databases are affected; 12 internal users are.") is None
    assert crew_change.check_answer(
        6, "app-01.internal, and the TBD-2 staging host") is None


# ---- the passing case ------------------------------------------------------


def test_a_fully_answered_request_produces_no_findings():
    """The assertion that keeps every refusal above non-vacuous. Without it a
    validator that refused EVERYTHING would pass every other test here."""
    assert crew_change.validate_new(_answered(range(1, 10))) == []


def test_every_failing_question_is_named_not_just_the_first():
    """"Naming which" is the requirement. An operator who fixes one answer and
    is refused again for the next learns to hate the gate rather than the
    template."""
    answers = _answered(range(1, 10))
    answers[3] = ""
    answers[5] = "TBD"
    answers[8] = "   "

    findings = crew_change.validate_new(answers)

    assert [f["number"] for f in findings] == [3, 5, 8]
    assert [f["kind"] for f in findings] == [
        crew_change.UNANSWERED, crew_change.PLACEHOLDER,
        crew_change.UNANSWERED]
    said = "\n".join(crew_change.describe(findings))
    for number in (3, 5, 8):
        assert dict(crew_change.QUESTIONS)[number] in said, number


# ---- the asymmetry ---------------------------------------------------------


def test_new_gates_one_to_nine_and_does_not_require_ten():
    """At filing time the change has not happened, so question 10 cannot be
    answered. Requiring it would make the gate unsatisfiable, and the natural
    repair is to type "N/A" -- which teaches the operator that placeholders are
    how you get past this gate."""
    assert crew_change.FILING_QUESTIONS == tuple(range(1, 10))

    answers = _answered(range(1, 10))          # 10 absent entirely
    assert crew_change.validate_new(answers) == []

    answers[10] = "TBD"                        # and a placeholder in 10 is fine
    assert crew_change.validate_new(answers) == []


def test_close_requires_ten_and_gates_nothing_else():
    """The other direction. Re-gating 1-9 at close would refuse a legitimate
    close over answers the backend already holds and nobody is being asked to
    retype."""
    assert crew_change.CLOSING_QUESTIONS == (10,)

    assert crew_change.validate_close({}) != []
    assert crew_change.validate_close({10: "N/A"}) != []
    assert crew_change.validate_close(
        {10: "Smoke suite green, 0 errors in 30 minutes of logs."}) == []
    # Nothing else is consulted: an empty 1-9 does not block a close.
    assert crew_change.validate_close(
        {1: "", 10: "Smoke green; error rate flat."}) == []


def test_json_string_keys_are_read_as_well_as_int_keys():
    """A mapping that made a round trip through a JSON file arrives keyed "1",
    not 1. Reading only one spelling would make the gate pass EVERYTHING for
    exactly one of its two callers, which is the shape where a gate looks like
    it ran."""
    answers = {str(n): v for n, v in _answered(range(1, 10)).items()}

    assert crew_change.validate_new(answers) == []
    answers["4"] = "n/a"
    assert [f["number"] for f in crew_change.validate_new(answers)] == [4]


# ---- the CLI ---------------------------------------------------------------


def _run_cli(answers, mode):
    return subprocess.run(
        [sys.executable, crew_change.__file__, "--mode", mode,
         "--answers", "-"],
        input=json.dumps(answers), capture_output=True, text=True,
        check=False, timeout=120)


def test_the_cli_exits_zero_only_on_a_verified_pass():
    """The command file branches on the exit code, so the code is the
    contract."""
    ok = _run_cli(_answered(range(1, 10)), "new")
    assert ok.returncode == 0, ok.stderr

    refused = _run_cli({1: "TBD"}, "new")
    assert refused.returncode == 2
    assert "REFUSED" in refused.stderr
    assert "1." in refused.stderr


def test_unreadable_input_exits_non_zero_rather_than_passing():
    """"Could not tell" must never wear the label of "complete". This is the
    collapse this repo keeps rediscovering, and here what it would wave through
    is a change request filed with nothing in it."""
    proc = subprocess.run(
        [sys.executable, crew_change.__file__, "--mode", "new",
         "--answers", "-"],
        input="{not json", capture_output=True, text=True, check=False,
        timeout=120)

    assert proc.returncode == 2
    assert "could not read the answers" in proc.stderr
