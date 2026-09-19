"""Dispatched roles run their gates in the foreground, and the PM resumes by id.

Three subagents ended a turn waiting on something that would never wake them --
`crew-pm` at ~00:30, `dev-pm-contract` at 01:01, `dev-stophook-finish` at 02:07:
three agents, two roles, one behaviour. A subagent that has given its final
response is not resumed when a background task completes later. That is a
harness property (`code.claude.com/docs/en/sub-agents`), not a defect to wait
out, so the only place it can be fixed is the role prose that tells each agent
how to run a long command.

Like test_scope_discipline.py, these assert PROMPT TEXT. A subagent prompt is
not executable and there is nothing to run; the only mechanical regression is
the instruction going missing, which is the state every one of these files was
in before crew 0.19.89.

The assertions name whole sentences rather than tokens on purpose. `foreground`
and `background` each appear several times in these files now, so a test that
asserted the bare token would stay green while the load-bearing sentence was
deleted -- that exact miss happened twice on the night this was written, on
four separate assertions.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]


def _norm(text):
    """Collapse runs of whitespace so an assertion survives a rewrap.

    Copied deliberately from test_scope_discipline.py rather than imported:
    these files are hand-wrapped prose, a phrase that sits on one line today
    straddles two after any edit, and a test that fails on a rewrap is one
    people repair by deleting the assertion.
    """
    return re.sub(r"\s+", " ", text)


def _agent(name):
    return _norm((PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8"))


# Every dispatched role that runs a gate, a suite or a mutation itself.
# `analyst`, `dba` and `legacy-modernizer` were considered and left out: none
# of them runs a suite in its own turn -- dba proposes the check that
# `smoke-author` then writes and runs.
FOREGROUND_ROLES = (
    "developer",
    "pm",
    "python-pro",
    "browser-tester",
    "smoke-author",
    "qa-reviewer",
)


def test_every_long_running_role_forbids_ending_a_turn_on_a_background_task():
    """The shared half of the rule, asserted as a sentence in each file.

    The wording differs per file because the voices differ; the clause that
    does the work is the same everywhere, and this is it."""
    for name in FOREGROUND_ROLES:
        body = _agent(name)
        assert "never end a turn waiting on a background task" in body.lower(), (
            f"{name}.md no longer forbids ending a turn on a background task, "
            "which is the behaviour that stalled three agents in one night"
        )


def test_every_long_running_role_carries_the_positive_instruction_too():
    """The prohibition alone is not the rule.

    Both of these sentences were deleted during sabotage and the suite stayed
    GREEN, because the 'never end a turn waiting' clause was carrying the whole
    check on its own. A file can lose the instruction that says what to DO and
    keep only the one that says what not to, which reads as a caveat on the
    surrounding paragraph rather than an instruction of its own."""
    positives = {
        "developer": "Run every gate and every suite in the foreground",
        "pm": "Every dispatch, gate and command you run goes in the "
              "foreground, and you read its result before the turn closes.",
        "python-pro": "Every one of those runs in the foreground.",
        "browser-tester": "Run it in the foreground and wait for it.",
        "smoke-author": "Run the mapped command in the foreground",
        "qa-reviewer": "Run it in the foreground.",
    }
    assert set(positives) == set(FOREGROUND_ROLES), (
        "a role gained or lost the foreground rule without its positive "
        "instruction being checked here"
    )
    for name, clause in positives.items():
        assert clause in _agent(name), (
            f"{name}.md kept the prohibition and lost the instruction, so the "
            "role is told what not to do and not what to do instead"
        )


def test_every_long_running_role_says_why_waiting_does_not_work():
    """A rule with no stated mechanism is the first thing a later edit drops,
    and this one reads as arbitrary caution until you know the harness will
    not resume a subagent that has already answered."""
    reasons = {
        "developer": "a subagent that has answered is not resumed by a "
                     "background task completing later",
        "pm": "A subagent that has given its final response is not woken when "
              "something completes later",
        "python-pro": "you have already given your final answer by the time "
                      "the run exits, nothing reopens the turn to read it",
        "browser-tester": "once you have given your final response nothing "
                          "wakes you",
        "smoke-author": "A subagent that has given its final response is not "
                        "woken by a run that finishes afterwards",
        "qa-reviewer": "your final response closes the turn and nothing wakes "
                       "you when the run exits",
    }
    assert set(reasons) == set(FOREGROUND_ROLES), (
        "a role gained or lost the foreground rule without its reason being "
        "checked here"
    )
    for name, reason in reasons.items():
        assert reason in _agent(name), (
            f"{name}.md states the foreground rule without saying why the "
            "harness makes waiting useless, so the rule now reads as a "
            "preference"
        )


def test_every_long_running_role_says_split_rather_than_background():
    """The rule is unfollowable without this half. A suite that exceeds the
    tool timeout has to go somewhere, and 'do not background it' with no
    alternative is read as permission to background it."""
    splits = {
        "developer": "If a command will not fit inside the tool timeout, "
                     "split it — do not background it.",
        "pm": "When a command is too long for the tool timeout, split it — do "
              "not background it.",
        "python-pro": "A `pytest` invocation that outlives the tool timeout "
                      "gets split rather than backgrounded",
        "browser-tester": "A spec run too long for the tool timeout gets split "
                          "instead",
        "smoke-author": "When a command will not fit inside the tool timeout, "
                        "split it into parts you run one after another",
        "qa-reviewer": "A suite too long for the tool timeout gets split into "
                       "parts run one after another",
    }
    assert set(splits) == set(FOREGROUND_ROLES), (
        "a role gained or lost the foreground rule without its split clause "
        "being checked here"
    )
    for name, clause in splits.items():
        assert clause in _agent(name), (
            f"{name}.md no longer tells the role what to do with a command "
            "that exceeds the tool timeout, so the only remaining option is "
            "the one the rule forbids"
        )


def test_split_parts_must_be_reported_individually():
    """Splitting without quoting each part buys nothing: an unreported part is
    indistinguishable from a part that was never run, which is the failure the
    whole rule exists to stop."""
    quotes = {
        "developer": "each part in the foreground, with each part's result "
                     "quoted in your report",
        "pm": "each part run in the foreground and each part's output quoted",
        "python-pro": "with each part's exit code reported separately",
        "browser-tester": "each run in the foreground with its own output "
                          "quoted",
        "smoke-author": "quoting each part's result",
        "qa-reviewer": "each part's output quoted",
    }
    for name, clause in quotes.items():
        assert clause in _agent(name), (
            f"{name}.md dropped the requirement to quote each split part, so "
            "a part that never ran now reports the same as one that passed"
        )


def test_pm_resumes_a_partial_result_by_id_rather_than_re_dispatching():
    """Re-dispatch is the expensive wrong answer: it opens an empty context
    that re-derives what the first pass already knew, and it spends one of the
    pass's finite dispatch slots to get back to where it started."""
    body = _agent("pm")
    assert "Resume a partial result by id; never re-dispatch it." in body, (
        "pm.md no longer tells the PM to resume a half-finished role, so the "
        "only documented move is a re-dispatch into an empty context"
    )
    assert "reach it with `SendMessage` addressed to that agent's id or name" in body, (
        "pm.md names the rule without naming the mechanism that carries it out"
    )
    assert ("spends one of your `pm.maxDispatches` slots to arrive back where "
            "you already were") in body, (
        "pm.md dropped the cost of re-dispatching -- a dispatch slot -- which "
        "is the half that makes this a budget rule and not a style note. "
        "Asserting the bare `pm.maxDispatches` token does NOT catch this: the "
        "token appears again in the maxDispatches cap above, so sabotage "
        "deleting this clause came back GREEN"
    )


def test_pm_resume_rule_does_not_contradict_the_no_name_dispatch_rule():
    """pm.md already forbids passing a `name` to the Agent tool: the runtime
    enforces a flat roster and a teammate spawning a teammate fails outright.
    A resume-by-id rule sitting beside that reads as a reversal unless it says
    which `name` it means, and a reader resolving the contradiction the wrong
    way gets "Teammates cannot spawn other teammates" at dispatch time."""
    body = _agent("pm")
    assert "never pass a `name` to the Agent tool" in body, (
        "the dispatch rule this one is reconciled against has moved or gone; "
        "re-check that the resume clause below still makes sense without it"
    )
    assert "This is not the `name` the rule above forbids" in body, (
        "pm.md carries both rules with nothing distinguishing them, so the "
        "resume clause now reads as permission to name a dispatch"
    )
