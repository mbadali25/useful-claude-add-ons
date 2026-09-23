"""Dispatched roles run their gates in the foreground; a partial result is
resumed by id, never re-dispatched.

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


def _command(name):
    """Same normalisation, for a command file. The resume-by-id mechanism
    lives here rather than in agents/pm.md: the PM itself has no SendMessage,
    so the half of the rule that actually calls it has to live in the caller,
    checked with this helper."""
    return _norm((PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8"))


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
    whole rule exists to stop.

    qa-reviewer is deliberately excluded here and checked separately below:
    its output contract is defect lines or exactly CLEAN, nothing else, so it
    cannot append a quoted part to its verdict the way the other five roles
    quote parts into a free-form report. Codex found this on round 1 --
    asserting the same 'quoted' clause against qa-reviewer.md would have
    meant approving a violation of its own output contract."""
    free_form_roles = tuple(r for r in FOREGROUND_ROLES if r != "qa-reviewer")
    quotes = {
        "developer": "Up to five parts, quote each one's exit code and "
                     "pass/fail count on its own line",
        "pm": "each part run in the foreground and each part's output quoted",
        "python-pro": "Up to five parts, report each one's exit code on its "
                      "own line",
        "browser-tester": "each run in the foreground with its own output "
                          "quoted",
        "smoke-author": "quoting each part's result",
    }
    assert set(quotes) == set(free_form_roles), (
        "a role gained or lost the foreground rule without its split-"
        "reporting clause being checked here"
    )
    for name, clause in quotes.items():
        assert clause in _agent(name), (
            f"{name}.md dropped the requirement to quote each split part, so "
            "a part that never ran now reports the same as one that passed"
        )


def test_developer_quotes_stay_inside_its_own_word_budget():
    """Codex found this on round 2: developer.md's original 'quote each
    part's exit code and pass/fail count, one line per part' has no ceiling
    either -- split a suite into 100 parts and 100 one-line quotes still
    blows the 200-word 'What you return' contract two sections down, even
    though each individual line is short. Round 3 found the actual fix:
    cap the per-part lines and fall back to totals plus a written table
    beyond that cap."""
    body = _agent("developer")
    assert (
        "Up to five parts, quote each one's exit code and pass/fail count "
        "on its own line"
    ) in body, (
        "developer.md dropped the cap on how many parts get an individual "
        "quoted line, so enough split parts can still blow the 200-word "
        "return even with short one-line quotes"
    )
    assert (
        "Beyond five, the return carries totals instead — how many parts "
        "ran, how many passed, how many failed, and the worst exit code "
        "among them"
    ) in body, (
        "developer.md no longer says what replaces per-part quoting past "
        "the five-part cap, so a large split run has nowhere to go except "
        "back to quoting every part"
    )
    assert (
        "the full per-part table goes to a file under `.work/`, named in "
        "your report so the reviewer can open it"
    ) in body, (
        "developer.md drops the per-part detail entirely past five parts "
        "instead of writing it somewhere the reviewer can still reach"
    )


def test_python_pro_inherits_developer_word_budget_cap():
    """python-pro's own wording ('each part's exit code reported
    separately') looked safe because it never promised full output -- but
    Codex found the same conflict anyway: enough split parts and even
    bare exit-code lines blow the 200-word return python-pro inherits from
    developer's report shape. The fix mirrors developer's five-part cap
    rather than duplicating its own scheme."""
    body = _agent("python-pro")
    assert (
        "Up to five parts, report each one's exit code on its own line"
    ) in body, (
        "python-pro.md dropped the cap on per-part exit-code lines, so a "
        "large split run can still blow the 200-word return it inherits "
        "from crew:developer's report shape"
    )
    assert (
        "beyond five, report totals instead — how many parts, how many "
        "passed, how many failed, and the worst exit code"
    ) in body, (
        "python-pro.md no longer says what replaces per-part exit codes "
        "past the five-part cap"
    )


def test_qa_reviewer_verifies_every_split_part_without_polluting_its_verdict():
    """qa-reviewer's output contract is strict: defect lines, or exactly
    CLEAN, nothing else. The shared 'quote each part' instruction the other
    five roles carry would violate that contract if copied verbatim -- a
    clean split run would have to append its parts' output after CLEAN.
    qa-reviewer's version says the opposite about WHERE the quoting goes:
    into the reasoning that reaches a verdict, never into the verdict."""
    body = _agent("qa-reviewer")
    assert (
        "Quoting belongs to the reasoning that gets you to a verdict, not "
        "the verdict itself"
    ) in body, (
        "qa-reviewer.md no longer distinguishes verifying a split run from "
        "reporting it, so the split-parts rule now conflicts with the "
        "defect-lines-or-CLEAN output contract -- this is the FIX Codex "
        "found on round 1"
    )
    assert "read every part's real output before you decide" in body, (
        "qa-reviewer.md dropped the requirement to actually read each split "
        "part's output before reaching a verdict"
    )
    assert (
        "what you output still ends at defect lines or exactly `CLEAN` — "
        "nothing from a split run gets appended after it"
    ) in body, (
        "qa-reviewer.md no longer protects its own output contract from the "
        "split-parts rule, so a clean split run could add text after CLEAN"
    )


def test_qa_reviewer_never_narrates_outside_its_strict_output_contract():
    """Codex found this on round 3: three separate instructions in this file
    told qa-reviewer to SAY something in its own return -- which model
    reviewed, whether the routing guard was skipped, what it could not
    verify -- and all three directly contradict 'output one line per
    defect, nothing else' / 'if you find nothing, output exactly: CLEAN'.
    The fix doesn't drop the underlying concerns, it moves the reporting
    responsibility to whoever dispatches qa-reviewer, which already has the
    information (the routing decision) or a place to record it
    (.crew/metrics.md's own <reviewer> column, written by /crew:review)."""
    body = _agent("qa-reviewer")
    assert (
        "your own return has no room to say so — it stays defect lines or "
        "exactly `CLEAN` either way, so this is not something you report"
    ) in body, (
        "qa-reviewer.md still implies the direct-dispatch disclosure "
        "belongs in its own output, contradicting the strict output "
        "contract lower in the file"
    )
    assert (
        "Which model is reviewing, and which of the three routes put it "
        "there — the pin, the family refusal, or the fallback — is not "
        "something your own return states"
    ) in body, (
        "qa-reviewer.md no longer says the model/route disclosure is out "
        "of scope for its return -- this is the exact contradiction Codex "
        "found on round 3, since the output contract leaves no room for it"
    )
    assert (
        "the `<reviewer>` column it writes to `.crew/metrics.md` on every "
        "run"
    ) in body, (
        "qa-reviewer.md dropped where the model/route information actually "
        "belongs, so the disclosure it can no longer make in its own "
        "output has nowhere documented to go instead"
    )
    assert (
        "none of it belongs in your output, which is always defect lines "
        "or exactly `CLEAN` and never anything else"
    ) in body, (
        "qa-reviewer.md no longer states the unifying rule that reconciles "
        "all three narration conflicts Codex found on round 3"
    )
    assert (
        "the fix for that risk is reading the diff as hard on a clean pass "
        "as a dirty one, not writing a caveat your own contract has no "
        "room for"
    ) in body, (
        "qa-reviewer.md dropped the reframe of the 'three clean reviews in "
        "a row' concern -- it still needs addressing, just not by writing "
        "text the strict output contract forbids"
    )


def test_pm_does_not_resume_a_partial_result_itself():
    """The PM's own tools (its frontmatter `tools:` line) do not include
    SendMessage, so an instruction telling the PM to resume a role by id
    itself is unfollowable -- and it contradicts the dispatch rule above,
    which already says a dispatched role's address belongs to whoever invoked
    the PM, not to the PM. Codex found this on round 1: the PM was being told
    to do something it has no tool to do. The PM's only correct move is to
    return the partial result's id and say it can be resumed; the actual
    resume happens in commands/pm.md, checked separately below."""
    body = _agent("pm")
    assert (
        "A role that returns a PARTIAL result is not something you resume "
        "yourself."
    ) in body, (
        "pm.md no longer tells the PM it cannot resume a half-finished role "
        "itself, which is unfollowable anyway since the PM has no SendMessage"
    )
    assert (
        "you have no `SendMessage` in your own tool list, and the dispatch "
        "rule above already settled this from the other side"
    ) in body, (
        "pm.md dropped the reason the PM cannot resume a role itself, so the "
        "instruction reads as an arbitrary restriction rather than a tool "
        "limit reconciled against the dispatch rule above"
    )
    assert (
        "Return the partial result with the identifier the dispatch "
        "itself returned, and say plainly that it can be resumed by "
        "that id."
    ) in body, (
        "pm.md dropped the instruction to hand the partial result's id "
        "upward, so the caller has nothing to resume it with"
    )
    assert (
        'A role label such as "developer" is not that identifier and '
        "cannot resume anything with it"
    ) in body, (
        "pm.md no longer rules out a bare role label as the returned "
        "identifier -- this is the FIX Codex found on round 2: a report of "
        'PARTIAL with only the label "developer" gives the caller nothing '
        "commands/pm.md's SendMessage-by-id handoff can use"
    )
    assert (
        'if the dispatch returned no id at all, say plainly "not '
        'resumable: no id was returned" so the caller knows a fresh '
        "dispatch is the only option left, not a resume"
    ) in body, (
        "pm.md no longer covers the case where the dispatch returned no id "
        "at all -- an unknown collapsing into a wrong assumed value is the "
        "recurring failure shape this repo's CLAUDE.md warns about, and "
        "here it would silently tell the caller to resume something that "
        "cannot be resumed"
    )
    assert "Do not re-dispatch a resumable partial yourself" in body, (
        "pm.md no longer forbids the PM from re-dispatching a resumable "
        "partial result itself"
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
    assert "The id you are handing upward here is not the `name`" in body, (
        "pm.md carries both rules with nothing distinguishing them, so the "
        "resume clause now reads as permission to name a dispatch"
    )
    assert (
        "that one is passed to the Agent tool at dispatch time and makes "
        "the spawned role a teammate; this is the identifier the role came "
        "back with, and reporting it upward changes nothing about how the "
        "role was spawned"
    ) in body, (
        "pm.md asserts the two rules don't conflict without explaining WHY "
        "-- which id is which and where each comes from -- so the "
        "reconciliation is stated but not actually made. This is the FIX "
        "Codex found on round 1: the old assertion here only checked the "
        "lead-in sentence, so deleting the explanation that followed it "
        "left every test in this file green"
    )


def test_pm_write_scope_matches_the_write_guard_exactly():
    """Codex found this on round 3: pm.md stated its write scope TWICE, and
    the two statements disagreed. Higher up, 'Your own writes are
    `.crew/**`, `TODO.md`, ticket text under `.work/`, and
    `docs/diagrams/**`' matches the four prefixes
    `role_write_guard.py`'s `_PM_ALLOWED_PATTERNS` actually enforces. Lower
    down, a second sentence said only `.crew/` and `docs/diagrams/` --
    dropping TODO.md and .work/ entirely, which contradicts the rabbit-hole
    rule (a non-blocking finding with no tracker MUST go to TODO.md) and the
    ticket-writing table earlier in this same file. A role that followed
    the narrower sentence could not do what its own rabbit-hole rule
    requires."""
    body = _agent("pm")
    assert (
        "Your own writes are `.crew/**`, `TODO.md`, ticket text under "
        "`.work/`, and `docs/diagrams/**`"
    ) in body, (
        "pm.md dropped its first, correct statement of write scope -- the "
        "one that matches role_write_guard.py's four prefixes"
    )
    assert (
        "Everything you write is scoped to `.crew/**`, `TODO.md`, "
        "`.work/**` and `docs/diagrams/**`"
    ) in body, (
        "pm.md's second write-scope sentence no longer matches its first: "
        "this is the exact contradiction Codex found on round 3, where the "
        "second sentence dropped TODO.md and .work/, making the "
        "rabbit-hole rule's mandatory TODO.md write impossible under the "
        "scope this sentence states"
    )
    assert (
        "the same four prefixes the write-scope guard enforces "
        "mechanically, not a wider or narrower promise made only in prose"
    ) in body, (
        "pm.md's second write-scope sentence no longer ties itself back to "
        "the mechanically-enforced guard, so a future edit could drift the "
        "two apart again with nothing here to catch it"
    )


def test_pm_reaps_idle_roles_by_reporting_not_reengaging():
    """Codex found this on round 3: 'Reap what is idle' told the PM to
    're-engage a role that is still on the same subject' -- but the PM has
    no SendMessage, the same tool gap that made the resume-by-id rule need
    rewriting earlier in this file. 'Re-engage' is unfollowable for exactly
    the same reason 'resume it yourself' was. The fix is the same shape:
    report the role's existence and its id to the caller, never act on it
    directly."""
    body = _agent("pm")
    assert (
        "if a role is still on the same subject, report it as existing "
        "and hand its id to the caller rather than dispatching a "
        "duplicate"
    ) in body, (
        "pm.md no longer tells the PM to report an already-alive role to "
        "the caller instead of re-engaging it directly"
    )
    assert (
        "you have no `SendMessage` to re-engage it yourself, only the "
        "means to name it"
    ) in body, (
        "pm.md dropped the reason re-engaging is unfollowable -- the same "
        "tool gap (no SendMessage) that already forced the resume-by-id "
        "rule to move to commands/pm.md"
    )


def test_pm_command_resumes_a_partial_result_with_sendmessage():
    """The PM itself cannot resume a role -- it has no SendMessage. The
    mechanism that actually does the resuming lives one level up, in
    commands/pm.md, which DOES carry SendMessage in its allowed-tools.
    Without this half the PM's 'return the id upward' instruction goes
    nowhere: nothing downstream ever acts on it.

    Codex found two more gaps here on round 3: the resume instruction's own
    PRECONDITION ('a PM report says a role returned a PARTIAL result and
    names that role's id') was never asserted, only the SendMessage clause
    that follows it -- so deleting the precondition alone left every test
    green, since nothing then required a report to actually say PARTIAL
    before the caller acts. And nothing asserted that SendMessage is
    actually IN commands/pm.md's own allowed-tools frontmatter, as opposed
    to merely being named in prose -- removing it from the frontmatter left
    every test green too, verified independently."""
    body = _command("pm")
    assert (
        "If a PM report says a role returned a PARTIAL result and names "
        "that role's id, `SendMessage` that id directly"
    ) in body, (
        "commands/pm.md dropped the precondition for this resume "
        "instruction -- 'a PM report says PARTIAL and names the id' -- so "
        "the SendMessage clause below has nothing gating when it applies. "
        "This is the FIX Codex found on round 3: the old assertion here "
        "checked only the SendMessage clause, not this precondition"
    )
    assert (
        "A role's partial result carries an id — resume it yourself, "
        "don't send it back to the PM."
    ) in body, (
        "commands/pm.md no longer tells the caller to resume a role's "
        "partial result directly, so the PM's returned id has nothing "
        "reading it"
    )
    assert (
        "`SendMessage` that id directly rather than routing it back "
        "through the PM to redo"
    ) in body, (
        "commands/pm.md names the rule without naming the mechanism -- "
        "SendMessage -- that actually carries it out"
    )
    assert "it has no `SendMessage` in its own tool list" in body, (
        "commands/pm.md dropped the reason the PM cannot do this itself, so "
        "the split between 'PM returns the id' and 'caller resumes it' "
        "reads as arbitrary"
    )
    assert (
        "allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, "
        "SendMessage, AskUserQuestion"
    ) in body, (
        "commands/pm.md's frontmatter no longer actually grants "
        "SendMessage -- the prose above can still NAME the mechanism while "
        "the tool itself is unavailable, which is the FIX Codex found on "
        "round 3: the old assertions checked only prose, never the "
        "frontmatter that makes the prose followable"
    )


def test_pm_does_not_treat_an_idle_signal_as_proof_a_role_has_stopped():
    """The observer's half of the same rule. The actor's half (above) tells a
    dispatched role never to go idle while a gate is still running; this half
    tells the PM not to trust the harness's idle signal when a role is doing
    exactly that. Without it the PM has only one way to read 'idle': stopped
    -- which is what nearly restarted item 3 from disk over a live run whose
    eval results had been written three seconds earlier."""
    body = _agent("pm")
    assert (
        "An idle signal from a role running a gate or a suite is not "
        "evidence it stopped."
    ) in body, (
        "pm.md no longer states the observer's rule -- that an idle report "
        "is not proof a long-running role has stopped"
    )
    assert (
        "compare the worktree's newest file mtimes — excluding `.git` — "
        "against the shell clock"
    ) in body, (
        "pm.md dropped the mechanism for telling a live run from a stalled "
        "one, so 'idle' has no check left to weigh it against"
    )
    assert (
        "A recent write means the tree was active recently, not that "
        "anything is running there right now"
    ) in body, (
        "pm.md no longer distinguishes 'the tree was active recently' from "
        "'something is running right now' -- which is the honest strength "
        "Codex asked for on round 2: even a single matching write cannot "
        "establish current liveness, only recent activity"
    )
    assert (
        "the same trail is left by another role, by a process that "
        "already finished, or by the very role you are watching having "
        "already exited"
    ) in body, (
        "pm.md dropped the list of things besides a live role that can "
        "leave the same mtime trail. This is the FIX Codex found on round "
        "2: round 1's fix asserted only the sentence's lead-in, so deleting "
        "this clause on its own left every test in this file green"
    )
    assert (
        "Confirm which role by the files themselves — the paths its "
        "ticket touches"
    ) in body, (
        "pm.md dropped the ticket-path attribution mechanism itself, not "
        "just its lead-in. This is the other half of the FIX Codex found "
        "on round 2: round 1's assertion covered only 'Confirm which role "
        "by the files themselves' and stopped before naming HOW, so "
        "deleting '— the paths its ticket touches —' on its own also left "
        "every test in this file green"
    )
    assert (
        "The decision rule is a recent write means wait one cycle and "
        "re-check; no write across two consecutive cycles means report "
        "it, not restart it."
    ) in body, (
        "pm.md dropped the explicit two-reading decision rule, so 'wait, "
        "don't restart' has no stated threshold for when waiting ends"
    )
    assert (
        "You never classify a role as stopped on your own — a live "
        "read-only suite writes nothing at all and would satisfy "
        '"no write" while still running'
    ) in body, (
        "pm.md no longer says WHY two quiet cycles cannot be treated as "
        "confirmed-stopped -- this is the FIX Codex found on round 3: a "
        "live read-only suite writes nothing across any number of cycles "
        "and would be misclassified as stopped under the old wording"
    )
    assert (
        'say plainly "no writes across two cycles; not confirmed '
        'stopped" and hand the caller the role\'s id so it can confirm '
        "directly"
    ) in body, (
        "pm.md no longer says what the PM does after two quiet cycles -- "
        "escalate to the caller with the role's id -- so the only "
        "remaining move reads as silently giving up or restarting"
    )
    assert (
        "Never restart on a single reading, and never restart on two "
        "quiet cycles either — that call belongs to the caller, not to "
        "you"
    ) in body, (
        "pm.md dropped the rule that neither a single reading nor two "
        "quiet cycles is ever grounds for the PM itself to restart"
    )
    assert "Never restart a role from disk on an idle signal alone." in body, (
        "pm.md no longer forbids restarting on an idle signal alone, which "
        "is the exact move that nearly clobbered item 3's live run"
    )
    assert "the dirty files sitting there are that role's work" in body, (
        "pm.md dropped the reason a restart is destructive -- the uncommitted "
        "files an idle-looking role has on disk are its result, not debris"
    )
    assert (
        "Say so in your report and wait one cycle before deciding again — "
        "you cannot reach the role directly"
    ) in body, (
        "pm.md still tells the PM to reach the role directly after that "
        "action moved to commands/pm.md, which the PM cannot do -- it has "
        "no SendMessage"
    )
