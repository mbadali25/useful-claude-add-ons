"""The ten-question gate on a change request. Pure, and the whole feature.

The Change Management Request template `/crew:change` files against carries
its own rule, in capitals, above the questions:

    ALL THE BELOW QUESTIONS MUST BE ANSWERED. ANY PERTINENT MISSING
    INFORMATION WILL RESULT IN THE REQUEST BEING DENIED.

A command file can say that. It cannot enforce it -- nothing parses
`commands/change.md` at runtime, an agent reads it and acts, and "I checked
the answers" is exactly the shape of claim CLAUDE.md's first lesson is about:
an unknown collapsing into the safe-looking value. So the check lives here, in
a function with no I/O, and `commands/change.md` routes through it.

Two entry points, because `new` and `close` gate DIFFERENT questions and a
single boolean would get the asymmetry wrong silently:

  * `validate_new` gates questions 1-9 and deliberately does NOT require 10.
    Question 10 is "attach results of post-change validation", and at filing
    time the change has not happened. Requiring it at `new` would make the
    gate unsatisfiable; the natural repair is to write "N/A" into it, which
    teaches the operator that placeholders are how you get past this gate.
  * `validate_close` requires question 10 and nothing else. The other nine
    were gated when the request was filed, and re-gating them at close would
    refuse a legitimate close over an answer the backend already holds.

`PLACEHOLDERS` is defined ONCE, here. `commands/change.md` and
`skills/crew-change/SKILL.md` cite this module rather than restating the list:
a second copy is a list that drifts, and it would drift in the direction of
being shorter, which is the direction that lets a request through.
"""
import argparse
import json
import sys

# The ten questions, verbatim from the template, in the template's own order.
#
# Verbatim matters more than it looks. These are what a change board reads, and
# an answer is judged against the question as the board asked it -- so a
# paraphrase here would produce requests that answer a question nobody asked.
# `skills/crew-change/SKILL.md` carries the same ten for a human to read; this
# tuple is what the gate iterates, and the docs test asserts the two agree.
QUESTIONS = (
    (1, "What specifically is the change?"),
    (2, "Who will be implementing the change (added to Requestor Details "
        "also)?"),
    (3, "What is the scheduled time for the change - list downtime duration "
        "and day/time (added to Requestor Details also)?"),
    (4, "Who will this change affect? (how many are affected, what areas, or "
        "how many users)"),
    (5, "What is the worst-case scenario of impact to end users?"),
    (6, "What systems/applications are affected? (IP address, URL and/or "
        "hostname)"),
    (7, "List the system/applications/services impact, and whether each "
        "impacted system/application/service is hosted locally or in the "
        "cloud"),
    (8, "What is your rollback plan?"),
    (9, "Has there been a notification sent to those affected?"),
    (10, "Attach results of post-change validation"),
)

# Which questions each gate covers. Named rather than written as literals at
# the call sites so the asymmetry is stated once and can be asserted.
FILING_QUESTIONS = tuple(number for number, _ in QUESTIONS if number <= 9)
CLOSING_QUESTIONS = (10,)

# The template's header fields, in the template's order. `/crew:change new`
# collects these alongside the ten answers; they are NOT gated here, because
# a missing Priority is a field the desk itself rejects while a missing
# rollback plan is a change that gets approved and then cannot be undone.
TEMPLATE_FIELDS = (
    "Priority",
    "Impact",
    "Urgency",
    "Impact Details",
    "Requester name",
    "Implementor of Change",
    "Scheduled Start Time",
    "Scheduled End Time",
    "Subject",
    "Category",
    "Description",
)

# Answers that are typed in the box and say nothing.
#
# Every entry is a token that carries no information about ANY of the nine
# questions it is checked against, which is the bar for being on this list.
# Two judgement calls worth writing down rather than leaving to be
# rediscovered:
#
#   * `none` IS here, and it is the one that can refuse a technically true
#     answer -- "who will this change affect?" really can be nobody. The gate
#     then asks for a sentence ("no users are affected: the service has no
#     consumers yet"), which is what the change board needs anyway, and the
#     refusal names the question so the repair takes ten seconds. A bare
#     `none` on the ROLLBACK question is the case that decided it: it is
#     indistinguishable from an unanswered box and it is the single most
#     expensive thing to discover during an incident.
#   * `no` is NOT here, and must not be added. It is a complete and common
#     answer to question 9 ("has there been a notification sent"), and a gate
#     that refuses it would be refusing the truth.
#
# Matched against the WHOLE normalised answer, never as a substring: "none of
# the databases are affected" is a real answer that contains "none".
#
# **Every entry here must survive `normalise_answer`**, or it is an entry this
# set can never match -- dead weight that reads as coverage. `-`, `--` and
# `...` were in this set and were exactly that: `_TRIM` strips `.` and `-` from
# both ends, so all three normalise to the empty string and are refused as
# UNANSWERED before this set is ever consulted. Still refused, by the other
# arm, which is why the bug was invisible until a test asserted the KIND. They
# are gone rather than left, and `test_change_validator.py` asserts the
# property so a fourth one cannot arrive the same way.
PLACEHOLDERS = frozenset({
    "tbd",
    "tba",
    "todo",
    "to do",
    "to be determined",
    "to be confirmed",
    "n/a",
    "na",
    "not applicable",
    "none",
    "nil",
    "unknown",
    "see above",
    "as above",
    "same as above",
    "see below",
    "ditto",
    "pending",
    "?",
    "??",
    "x",
    "xxx",
    "placeholder",
    "fill in",
    "fill this in",
})

# Characters stripped from both ends before the answer is compared, so
# `**TBD**`, `"TBD"`, `TBD.` and `- TBD` are all the same non-answer. Stripped
# rather than removed globally: a hyphen inside `prod-db-01` is part of the
# answer.
_TRIM = " \t\r\n.,;:!*_`\"'()[]<>-"

# The failure kinds, as constants so a caller can branch on them without
# matching prose. `unanswered` is an empty or whitespace-only box;
# `placeholder` is a box with something in it that says nothing.
UNANSWERED = "unanswered"
PLACEHOLDER = "placeholder"


def normalise_answer(value):
    """`value` reduced to the form `PLACEHOLDERS` is compared against.

    Lower-cased, with runs of whitespace collapsed to one space and the
    decorative characters in `_TRIM` taken off both ends. A non-string (None, a
    number, a dict someone built wrong) normalises to the empty string, which
    reads as UNANSWERED -- the fail-closed direction, and the only safe answer
    for a value the gate cannot read.

    Pure and total: it raises for no input.
    """
    if not isinstance(value, str):
        return ""
    collapsed = " ".join(value.split())
    return collapsed.strip(_TRIM).lower().strip()


def check_answer(number, value):
    """One finding for question `number`, or None when it is answered.

    A finding is `{"number", "question", "kind", "given"}`. `given` is the
    answer EXACTLY as supplied, untouched, so the refusal can quote what was
    typed rather than the normalised form -- somebody who wrote `**TBD**`
    needs to see `**TBD**` to recognise their own box.
    """
    text = dict(QUESTIONS).get(number, "")
    cleaned = normalise_answer(value)
    if not cleaned:
        kind = UNANSWERED
    elif cleaned in PLACEHOLDERS:
        kind = PLACEHOLDER
    else:
        return None
    return {
        "number": number,
        "question": text,
        "kind": kind,
        "given": value if isinstance(value, str) else "",
    }


def _answer_for(answers, number):
    """`answers[number]`, accepting an int key or its string spelling.

    JSON objects have string keys, so a mapping that made a round trip through
    a file arrives keyed `"1"` while one built in Python is keyed `1`. Reading
    only one of the two would make the gate pass everything for exactly one of
    the two callers, which is the failure mode where a gate looks like it ran.
    """
    if not isinstance(answers, dict):
        return None
    if number in answers:
        return answers[number]
    return answers.get(str(number))


def validate(answers, numbers):
    """Findings for every question in `numbers`, in question order.

    An empty list means the gate passes. Never a bool: "refuses to file while
    any of 1-9 is unanswered or a placeholder, NAMING WHICH" is the
    requirement, and a bool cannot name anything.
    """
    out = []
    for number in numbers:
        finding = check_answer(number, _answer_for(answers, number))
        if finding is not None:
            out.append(finding)
    return out


def validate_new(answers):
    """The filing gate: questions 1-9. Question 10 is not required here.

    See this module's docstring for why requiring 10 at filing time would make
    the gate unsatisfiable and teach the operator to write placeholders.
    """
    return validate(answers, FILING_QUESTIONS)


def validate_close(answers):
    """The closing gate: question 10, the post-change validation results.

    Only 10. The other nine were gated at `new` and the backend holds them;
    re-gating them here would refuse a legitimate close over an answer nobody
    is being asked to retype.
    """
    return validate(answers, CLOSING_QUESTIONS)


def describe(findings, mode="new"):
    """The refusal, as lines. Empty when there is nothing to refuse.

    Names every failing question rather than the first, because an operator
    who fixes one and is refused again for the next learns to hate the gate
    rather than the template.
    """
    if not findings:
        return []
    what = ("change request" if mode == "new" else "close")
    lines = [
        f"REFUSED: this {what} is not complete. "
        f"{len(findings)} question(s) still need a real answer.",
        "The template's own rule: ALL THE BELOW QUESTIONS MUST BE ANSWERED. "
        "ANY PERTINENT",
        "MISSING INFORMATION WILL RESULT IN THE REQUEST BEING DENIED.",
        "",
    ]
    for finding in findings:
        lines.append(f"  {finding['number']}. {finding['question']}")
        if finding["kind"] == UNANSWERED:
            lines.append("     -> nothing was written here.")
        else:
            lines.append(
                f"     -> {finding['given'].strip()!r} says nothing. It is on "
                "crew_change.PLACEHOLDERS.")
    lines.append("")
    lines.append("Nothing was filed. Answer the questions above and run it "
                 "again.")
    return lines


def main(argv=None):
    """CLI. Exit 0 when the gate passes, 2 when it refuses, 2 on bad input.

    Exit 2 for a refusal AND for unreadable input, on purpose. The caller is a
    command file, and the two states it must never tell apart the wrong way
    round are "complete" and "I could not tell" -- so everything that is not a
    positively verified pass exits non-zero.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", default="-",
                        help="JSON file of {question number: answer}, or - "
                             "for stdin")
    parser.add_argument("--mode", choices=("new", "close"), default="new",
                        help="new gates questions 1-9; close gates 10")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.answers == "-":
            raw = sys.stdin.read()
        else:
            with open(args.answers, encoding="utf-8") as handle:
                raw = handle.read()
        answers = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"could not read the answers: {exc}", file=sys.stderr)
        return 2

    findings = (validate_new(answers) if args.mode == "new"
                else validate_close(answers))
    if args.json:
        print(json.dumps({"mode": args.mode, "refused": bool(findings),
                          "findings": findings}, indent=2))
    elif findings:
        print("\n".join(describe(findings, args.mode)), file=sys.stderr)
    else:
        gated = (FILING_QUESTIONS if args.mode == "new" else CLOSING_QUESTIONS)
        print(f"complete: {len(gated)} question(s) answered, none a "
              "placeholder")
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
