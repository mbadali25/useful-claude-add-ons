"""The U2 merge rule of crew_hook.merge, on synthetic child results (L-0727, A5).

Claude Code ran each registered hook on its own and combined their results; the
dispatcher runs several children in one process and must combine them the same
way. The rule (spec U2) is exercised here without running any hook:

  exit 2 from any child wins and carries each blocker's stderr, in order;
  PreToolUse permissionDecision: deny > ask > allow > absent, winners' reasons joined;
  decision "block" and continue false win, with their reasons;
  additionalContext and systemMessage are concatenated in registration order;
  plain stdout folds into additionalContext when another child emitted JSON;
  suppressOutput only when every child set it;
  stdout starting with `{` that does not parse is plain text, never dropped.
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook


def child(stdout="", stderr="", code=0):
    return {"exit": code, "stdout": stdout, "stderr": stderr}


def pre(decision=None, reason=None, context_text=None, **extra):
    out = {"hookEventName": "PreToolUse"}
    if decision:
        out["permissionDecision"] = decision
    if reason:
        out["permissionDecisionReason"] = reason
    if context_text:
        out["additionalContext"] = context_text
    return json.dumps({"hookSpecificOutput": out, **extra})


def merged_json(event, *children):
    result = crew_hook.merge(event, list(children))
    assert result["exit"] == 0
    return json.loads(result["stdout"])


def test_exit_2_from_any_child_wins_and_carries_every_blockers_stderr_in_order():
    children = [child(pre("allow")), child(stderr="first block", code=2), child(stderr="quiet"),
                child(stderr="second block", code=2)]

    result = crew_hook.merge("PreToolUse", children)

    assert result["exit"] == 2
    assert result["stderr"] == "first block\nsecond block\n"
    assert result["stdout"] == ""


@pytest.mark.parametrize("decisions,winner", [
    (("deny", "allow"), "deny"),
    (("allow", "deny"), "deny"),
    (("ask", "allow"), "ask"),
    (("allow", "ask", "deny"), "deny"),
    (("allow", "allow"), "allow"),
    (("ask", "ask"), "ask"),
])
def test_permission_decision_is_deny_over_ask_over_allow(decisions, winner):
    children = [child(pre(d, f"reason {i}")) for i, d in enumerate(decisions)]

    got = merged_json("PreToolUse", *children)

    assert got["hookSpecificOutput"]["permissionDecision"] == winner


def test_only_the_winning_children_reasons_are_joined():
    children = [child(pre("allow", "fine")), child(pre("deny", "cloud said no")),
                child(pre("deny", "env said no")), child(pre("deny", "cloud said no"))]

    got = merged_json("PreToolUse", *children)["hookSpecificOutput"]

    assert got["permissionDecisionReason"] == "cloud said no\nenv said no"


def test_a_child_with_no_decision_does_not_hide_a_deny():
    children = [child(), child(pre("deny", "no")), child("")]

    result = crew_hook.merge("PreToolUse", children)

    assert json.loads(result["stdout"])["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_single_childs_stdout_is_passed_through_byte_for_byte():
    text = '{"hookSpecificOutput": {"hookEventName": "SessionStart",  "additionalContext": "x"}}\n'

    result = crew_hook.merge("SessionStart", [child(), child(text), child("")])

    assert result == {"exit": 0, "stdout": text, "stderr": ""}


def test_two_additional_contexts_are_concatenated_in_registration_order():
    first = json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "one"}})
    second = json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "two"}})

    got = merged_json("SessionStart", child(first), child(second))

    assert got["hookSpecificOutput"] == {"hookEventName": "SessionStart", "additionalContext": "one\ntwo"}


def test_system_messages_are_concatenated_in_order():
    children = [child(json.dumps({"systemMessage": "a"})), child(json.dumps({"systemMessage": "b"}))]

    assert merged_json("Stop", *children)["systemMessage"] == "a\nb"


def test_plain_text_is_folded_into_additional_context_when_another_child_emitted_json():
    children = [child("handoff says hello\n"),
                child(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                          "additionalContext": "ctx"}}))]

    got = merged_json("SessionStart", *children)

    assert got["hookSpecificOutput"]["additionalContext"] == "ctx\nhandoff says hello"
    assert got["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_plain_text_only_is_passed_through_as_plain_text():
    children = [child("## platform - updated\n"), child("handoff\n")]

    result = crew_hook.merge("SessionStart", children)

    assert result["stdout"] == "## platform - updated\nhandoff\n"


def test_stdout_that_starts_with_a_brace_but_does_not_parse_is_plain_text_never_dropped():
    children = [child("{not json at all\n"),
                child(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                          "additionalContext": "ctx"}}))]

    got = merged_json("SessionStart", *children)

    assert "{not json at all" in got["hookSpecificOutput"]["additionalContext"]


def test_a_malformed_brace_child_alone_is_passed_through():
    result = crew_hook.merge("Stop", [child("{oops\n")])

    assert result["stdout"] == "{oops\n"


def test_decision_block_from_any_child_wins_with_its_reason():
    children = [child(json.dumps({"decision": "block", "reason": "unverified"})),
                child(json.dumps({"systemMessage": "note"}))]

    got = merged_json("Stop", *children)

    assert got["decision"] == "block" and got["reason"] == "unverified" and got["systemMessage"] == "note"


def test_continue_false_from_any_child_wins_and_keeps_its_stop_reason():
    children = [child(json.dumps({"systemMessage": "x"})),
                child(json.dumps({"continue": False, "stopReason": "context full"}))]

    got = merged_json("Stop", *children)

    assert got["continue"] is False and got["stopReason"] == "context full"


@pytest.mark.parametrize("flags,expected", [((True, True), True), ((True, False), None), ((False, False), None)])
def test_suppress_output_only_when_every_child_set_it(flags, expected):
    children = [child(json.dumps({"systemMessage": str(i), "suppressOutput": flag}))
                for i, flag in enumerate(flags)]

    got = merged_json("Stop", *children)

    assert got.get("suppressOutput") == expected


def test_a_silent_child_stops_suppress_output_from_applying():
    children = [child(json.dumps({"systemMessage": "a", "suppressOutput": True})),
                child(json.dumps({"systemMessage": "b", "suppressOutput": True})), child("")]

    assert merged_json("Stop", *children).get("suppressOutput") is True


def test_the_merge_only_ever_says_0_or_2_whatever_the_children_exited():
    codes = {crew_hook.merge("Stop", [child(code=code, stderr="x")])["exit"] for code in (1, 3, 127, 137, -9)}

    assert codes == {0}


def test_a_child_that_exited_oddly_keeps_its_stderr_and_does_not_hide_another_childs_output():
    result = crew_hook.merge("Stop", [child(code=1, stderr="oops"), child(pre("deny", "no"))])

    assert result["exit"] == 0 and result["stderr"] == "oops\n"
    assert json.loads(result["stdout"])["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stderr_of_a_non_blocking_child_is_kept():
    result = crew_hook.merge("Stop", [child(stderr="note one"), child(stderr="note two\n")])

    assert result["stderr"] == "note one\nnote two\n"


def test_an_unknown_top_level_key_is_kept_first_wins():
    children = [child(json.dumps({"custom": 1})), child(json.dumps({"custom": 2, "other": 3}))]

    got = merged_json("Stop", *children)

    assert got["custom"] == 1 and got["other"] == 3
