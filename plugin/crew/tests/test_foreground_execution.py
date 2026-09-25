"""Dispatched roles run their gates in the foreground.

Three subagents ended a turn waiting on something that would never wake them --
`crew-pm` at ~00:30, `dev-pm-contract` at 01:01, `dev-stophook-finish` at 02:07:
three agents, two roles, one behaviour. A subagent that has given its final
response is not resumed when a background task completes later. That is a
harness property (`code.claude.com/docs/en/sub-agents`), not a defect to wait
out, so the only place it can be fixed is the role prose that tells each agent
how to run a long command.

crew 1.0 deleted every writing role this file used to cover (developer, pm,
python-pro, browser-tester, smoke-author) and qa-reviewer's successor carries a
shorter contract, so what remains is the one role of the four that runs
anything itself: `reviewer`, which runs a check's mutation before accepting it.

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


# Every dispatched role that runs a gate, a suite or a mutation itself. In
# crew 1.0 that is `reviewer` alone: explorer, security and researcher run
# nothing that could be backgrounded.
FOREGROUND_ROLES = ("reviewer",)


def test_every_role_that_runs_a_mutation_runs_it_in_the_foreground():
    for name in FOREGROUND_ROLES:
        body = _agent(name)
        assert "Run the mutation yourself when you can, in the foreground" in body, (
            f"{name}.md no longer says to run its own mutation in the "
            "foreground; a subagent that has answered is not resumed when a "
            "background task completes, so the result would land nowhere"
        )
        assert "when you cannot, say so and BLOCK rather than accept a transcript" in body, (
            f"{name}.md dropped what to do when it cannot run the mutation, "
            "so a check with no demonstrated failing control passes review"
        )
