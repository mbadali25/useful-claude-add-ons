"""Structural and sabotage tests for crew 1.0's lifecycle commands and the
three vendored skills backing them (T4).

    python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py -q

Two kinds of check. The structural ones are what
`_test/validate-prompts.py` already covers for every command and skill --
frontmatter parses, ≤120 lines -- re-asserted here scoped to the new files so
this suite is a complete regression signal for T4 on its own. The sabotage
ones prove the text-presence checks are not vacuous: each mutates a
scratch COPY of the real file (never the tracked one), confirms the check
goes red on the mutation, and diffs the scratch against the tracked file to
prove the tracked file itself was never touched.
"""
import os
import re
import shutil
import tempfile

import pytest
import yaml

import context  # noqa: F401  pylint: disable=unused-import

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMANDS = os.path.join(CREW, "commands")
SKILLS = os.path.join(CREW, "skills")
MAX_LINES = 120

NEW_COMMANDS = ("brainstorm.md", "spec.md", "plan.md", "implement.md",
                "done.md", "fix.md", "approve.md", "autopilot.md")
NEW_SKILLS = ("crew-brainstorm", "crew-plan", "crew-execute", "crew-standards")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _frontmatter(text, path):
    assert text.startswith("---\n"), f"{path}: no frontmatter"
    end = text.index("\n---", 4)
    return yaml.safe_load(text[4:end])


def _line_count(text):
    # Trailing newline is not a 121st line; a file ending without one still
    # counts its last line. Matches how `wc -l` and this repo's other budget
    # checks (validate-prompts.py) read a file.
    return len(text.splitlines())


@pytest.mark.parametrize("name", NEW_COMMANDS)
def test_command_frontmatter_and_budget(name):
    path = os.path.join(COMMANDS, name)
    text = _read(path)
    fm = _frontmatter(text, path)
    assert isinstance(fm, dict), f"{name}: frontmatter did not parse to a mapping"
    assert fm.get("description"), f"{name}: no description"
    assert fm.get("allowed-tools"), f"{name}: no allowed-tools"
    lines = _line_count(text)
    assert lines <= MAX_LINES, f"{name}: {lines} lines, budget {MAX_LINES}"


@pytest.mark.parametrize("name", NEW_SKILLS)
def test_skill_frontmatter_and_budget(name):
    path = os.path.join(SKILLS, name, "SKILL.md")
    text = _read(path)
    fm = _frontmatter(text, path)
    assert fm.get("name") == name, f"{path}: frontmatter name != directory name"
    assert fm.get("description"), f"{name}: no description"
    lines = _line_count(text)
    assert lines <= MAX_LINES, f"{name}: {lines} lines, budget {MAX_LINES}"


# Each command names the T3 contract scripts with the exact CLI the brief
# gives: `crew_ticket.py validate|status --ticket <id>`, approval as the
# user-typed `/crew:approve <id>` (never the CLI, since crew 0.20.25),
# `completion_audit.py --check --ticket <id>`, and the review receipt check
# that already exists in review.md (`--ticket "$TICKET" --check-receipt`).
EXPECTED_CLI = {
    "plan.md": ("`/crew:approve $1`",),
    "implement.md": ("crew_ticket.py validate --ticket $1",
                      "scope_base.py --root . --record $1"),
    "done.md": ('review_ledger.py --ticket "$1" --check-receipt',
                'completion_audit.py --check --ticket "$1"',
                'crew_metrics.py record --ticket "$1"'),
    "fix.md": ("`/crew:approve <id>`",),
    "approve.md": ("Never run `crew_ticket.py approve` yourself",),
    "autopilot.md": ("crew_autopilot.py settings --root .",
                     "crew_autopilot.py resume --root .",
                     "crew_autopilot.py next --root .",
                     "crew_autopilot.py route --root .",
                     "crew_autopilot.py status --root ."),
}


@pytest.mark.parametrize("name,snippets", EXPECTED_CLI.items())
def test_command_names_exact_cli(name, snippets):
    text = _read(os.path.join(COMMANDS, name))
    for snippet in snippets:
        assert snippet in text, f"{name}: missing exact CLI {snippet!r}"


# T-0018: autopilot.md holds the router and `status` in 100 of the 120, so
# T-0010's approval branch, T-0012's `goal`, T-0019's `assign` and T-0020's
# `focus` have about 5 lines each. T-0010 took 10: its approve exception and
# the questions.md shape round 2 asked for (owner decision, 2026-09-27), which
# leaves T-0012, T-0019 and T-0020 10 lines between them. Past this, detail
# moves into crew_autopilot.py output (or a backing skill, which is the
# owner's call).
AUTOPILOT_MAX_LINES = 110


def test_autopilot_command_at_most_110_lines():
    lines = _line_count(_read(os.path.join(COMMANDS, "autopilot.md")))

    assert (lines <= AUTOPILOT_MAX_LINES, MAX_LINES - AUTOPILOT_MAX_LINES) == (True, 10), (
        f"autopilot.md: {lines} lines, budget {AUTOPILOT_MAX_LINES}")


IMPLEMENT_APPROVAL_TEXT = (
    "This command refuses to edit anything unless that call reports the plan\n"
    "approved."
)


def _implement_refuses_without_approval(text):
    return (IMPLEMENT_APPROVAL_TEXT in text
            and "crew_ticket.py validate --ticket $1" in text)


def test_implement_refuses_without_approval():
    text = _read(os.path.join(COMMANDS, "implement.md"))
    assert _implement_refuses_without_approval(text)


DONE_CHECKS = (
    'review_ledger.py --ticket "$1" --check-receipt',
    'crew_status.py --root .',
    'completion_audit.py --check --ticket "$1"',
)


def _done_has_all_checks(text):
    return all(check in text for check in DONE_CHECKS)


def test_done_requires_all_three_checks():
    text = _read(os.path.join(COMMANDS, "done.md"))
    assert _done_has_all_checks(text)


FIX_PHASES = ("## 1. Direction", "## 2. Spec", "## 3. Plan",
              "## 4. Implement, tests, docs", "## 5. Review", "## 6. Done")


def test_fix_has_every_lifecycle_phase():
    text = _read(os.path.join(COMMANDS, "fix.md"))
    for phase in FIX_PHASES:
        assert phase in text, f"fix.md: missing phase heading {phase!r}"


_PLAN_HEADER_STATUS = re.compile(r"plan\.md`?(?:'s)? header")


def test_plan_never_adds_status_to_plan_md():
    """T-0026: the approval digest normalises an existing status VALUE, never a
    token added where there was none, so a writer adding `status:` to plan.md
    after approval would stale the approval it just got."""
    flat = " ".join(_read(os.path.join(COMMANDS, "plan.md")).split())

    assert (_PLAN_HEADER_STATUS.search(flat) is None
            and "`spec.md`'s header to `status: planned`" in flat)


@pytest.mark.parametrize("name", ["implement.md", "done.md"])
def test_status_edits_say_they_keep_the_approval(name):
    flat = " ".join(_read(os.path.join(COMMANDS, name)).split())

    assert "keeps the approval" in flat


def _sabotage(path, target, checker, expected_before=True):
    """Copy `path` to a scratch file, remove `target` from the copy, and
    confirm `checker` flips from `expected_before` to its opposite. A text
    comparison against the tracked file proves the mutation landed only in
    the scratch copy and the tracked file was never touched.

    `shutil.copyfile`, not a spawned `cp`/`diff` -- neither exists on native
    Windows without Git Bash's `usr/bin` on PATH, and a bare `subprocess.run`
    on either raised `FileNotFoundError: [WinError 2]` there (Windows burn-in
    family D, `docs/review/06-windows-burn-in.md`@84f32325)."""
    with tempfile.TemporaryDirectory() as tmp:
        scratch = os.path.join(tmp, os.path.basename(path))
        shutil.copyfile(path, scratch)
        before_text = _read(scratch)
        assert target in before_text, f"sabotage target not found in {path}"
        assert checker(before_text) is expected_before
        after_text = before_text.replace(target, "", 1)
        assert after_text != before_text
        with open(scratch, "w", encoding="utf-8") as fh:
            fh.write(after_text)
        assert checker(after_text) is not expected_before, (
            f"{path}: check did not go red after removing {target!r} - "
            "the assertion is not exercising this text"
        )
        assert _read(path) != _read(scratch), (
            "sabotage produced no diff against the tracked file")
        tracked_now = _read(path)
        assert tracked_now == before_text, "tracked file was mutated by this test"


def test_sabotage_drop_the_approval_check_from_implement_goes_red():
    path = os.path.join(COMMANDS, "implement.md")
    _sabotage(path, IMPLEMENT_APPROVAL_TEXT, _implement_refuses_without_approval)


@pytest.mark.parametrize("missing", DONE_CHECKS)
def test_sabotage_drop_one_done_check_goes_red(missing):
    path = os.path.join(COMMANDS, "done.md")
    _sabotage(path, missing, _done_has_all_checks)


# T-0021: every lifecycle transition moves the tracker through crew_tracker.py,
# and every tracker command reads the kind through it rather than out of
# `.crew/config.json`. A transition with no call is a card that never moves.
_TRACKER = "crew_tracker.py"
TRACKER_CALLS = {
    "brainstorm.md": (f"{_TRACKER} create --root . --ticket",
                      f"{_TRACKER} move --root . --ticket <id> --to ready"),
    "spec.md": (f"{_TRACKER} move --root . --ticket $1 --to spec",),
    "plan.md": (f"{_TRACKER} move --root . --ticket $1 --to planned",),
    "implement.md": (f"{_TRACKER} move --root . --ticket $1 --to in-progress",
                     f"{_TRACKER} move --root . --ticket $1 --to review"),
    "done.md": (f'{_TRACKER} move --root . --ticket "$1" --to done',),
    "fix.md": (f"{_TRACKER} create --root . --ticket",
               f"{_TRACKER} move --root . --ticket <id> --to spec",
               f"{_TRACKER} move --root . --ticket <id> --to planned",
               f"{_TRACKER} move --root . --ticket <id> --to in-progress",
               f"{_TRACKER} move --root . --ticket <id> --to review"),
}
TRACKER_FAILURE_RULE = "tracker not updated: <reason>"
TRACKER_READERS = ("obsidian-sync.md", "jira-sync.md", "sdp-sync.md", "split.md", "change.md")
_CONFIG_TRACKER = re.compile(r"\.crew/config\.json`?\s*(?:->|→)\s*`?tracker")


@pytest.mark.parametrize("name,calls", TRACKER_CALLS.items())
def test_every_transition_calls_the_tracker(name, calls):
    text = _read(os.path.join(COMMANDS, name))

    missing = [call for call in calls if call not in text]

    assert (missing, TRACKER_FAILURE_RULE in text, "exit 3" in text) == ([], True, True)


def test_every_transition_status_maps_to_a_lane():
    import crew_tracker  # pylint: disable=import-outside-toplevel
    used = set()
    for name in TRACKER_CALLS:
        used |= set(re.findall(r"crew_tracker\.py move [^\n]*--to ([a-z-]+)",
                               _read(os.path.join(COMMANDS, name))))

    assert sorted(used - set(crew_tracker.LANE_FOR_STATUS)) == []


@pytest.mark.parametrize("name", TRACKER_READERS)
def test_no_tracker_precondition_reads_config_json(name):
    text = _read(os.path.join(COMMANDS, name))

    assert (_CONFIG_TRACKER.search(text), f"{_TRACKER} resolve" in text) == (None, True)


def test_obsidian_sync_fits_the_command_budget_without_an_allowance():
    text = _read(os.path.join(COMMANDS, "obsidian-sync.md"))
    allowance = _read(os.path.join(CREW, ".budget-allowance.json"))

    assert (_line_count(text) <= MAX_LINES, "obsidian-sync.md" in allowance) == (True, False)


def test_brainstorm_approval_does_not_hand_edit_the_index():
    text = _read(os.path.join(COMMANDS, "brainstorm.md"))

    assert "Update `.work/INDEX.md`'s status cell" not in text


def test_no_lifecycle_command_points_at_a_removed_command_for_tracker_writes():
    stale = ("the way `/crew:ticket` does", "`/crew:work`'s old step 13")

    found = [(name, s) for name in TRACKER_CALLS for s in stale
             if s in _read(os.path.join(COMMANDS, name))]

    assert found == []


_TRACKER_CALL = re.compile(r"(\S*)crew_tracker\.py (?:resolve|create|move|read)\b")
_PREFIX = "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/"


def test_every_tracker_call_in_commands_carries_the_prefix():
    """T-0021 review round 2: a bare `crew_tracker.py move` is "command not found"."""
    bare = []
    for name in sorted(os.listdir(COMMANDS)):
        if name.endswith(".md"):
            text = _read(os.path.join(COMMANDS, name))
            bare += [(name, found.group(0)) for found in _TRACKER_CALL.finditer(text)
                     if not found.group(1).endswith(_PREFIX)]

    assert bare == []


def test_implement_moves_to_review_before_it_runs_the_review():
    """T-0021 review round 2: the README's Review lane means `/crew:review` outstanding."""
    text = _read(os.path.join(COMMANDS, "implement.md"))

    move = text.find(f"{_TRACKER} move --root . --ticket $1 --to review")
    review = text.find("**Then, last, `/crew:review $1`**")

    assert (move != -1, review != -1, move < review) == (True, True, True)


TAKEN_RULE = "If a line says `id taken`, that id is not yours"


@pytest.mark.parametrize("name", ("brainstorm.md", "fix.md"))
def test_a_taken_id_is_never_written_under(name):
    """T-0021 review round 3: a refused mint carried on into writing the held
    ticket's files. The rule follows the create call and precedes every write
    under `.work/tickets/`."""
    text = " ".join(_read(os.path.join(COMMANDS, name)).split())

    create = text.find(f"{_TRACKER} create --root .")
    rule = text.find(TAKEN_RULE)
    folder = text.find("create `.work/tickets/")

    assert (create != -1, rule != -1, folder != -1, create < rule < folder,
            "write nothing under the taken one" in text) == (True, True, True, True, True)


STOP_RULE = "On any other failure, stop: show me its lines and write nothing under that id"


@pytest.mark.parametrize("name", ("brainstorm.md", "fix.md"))
def test_a_failed_create_stops_before_the_folder(name):
    """T-0021 review round 4: a create that failed for a reason other than
    `id taken` (the vault missing) carried on into the ticket folder of an id
    it never claimed. The stop rule sits between the create call and the first
    write under `.work/tickets/`."""
    text = " ".join(_read(os.path.join(COMMANDS, name)).split())

    create = text.find(f"{_TRACKER} create --root .")
    stop = text.find(STOP_RULE)
    folder = text.find("create `.work/tickets/")

    assert (create != -1, stop != -1, folder != -1, create < stop < folder) == (True, True, True, True)


# T-0085: the build-time standards reach the commands that apply them. Exact
# strings, matched on whitespace-normalised text, and one ordering control: the
# stamp sits before the review, so a self-check moved after `/crew:review $1`
# (a text mutation that keeps the words) still goes red. review.md's two
# refusal strings are in the exit-2 paragraph only T-0085 wrote; main's
# pre-T-0085 paragraph carries neither (review round 2 FIX 4).
_STANDARDS_STEPS = {
    "implement.md": ("crew_standards.py stamp --root . --ticket $1", "crew-standards"),
    "plan.md": ("Standards:",),
    "review.md": ('crew_standards.py proposals --root . --ticket "$TICKET"', "std:",
                  "`review-run: self-check: ...`",
                  "run the `crew_standards.py stamp` it names"),
    "fix.md": ("self-check",),
}


@pytest.mark.parametrize("name", sorted(_STANDARDS_STEPS))
def test_commands_name_the_standards_steps(name):
    text = " ".join(_read(os.path.join(COMMANDS, name)).split())

    missing = [s for s in _STANDARDS_STEPS[name] if s not in text]

    assert missing == [], f"{name} lacks {missing}"


def test_implement_stamps_the_self_check_before_the_review():
    lines = _read(os.path.join(COMMANDS, "implement.md")).splitlines()

    stamp = [i for i, line in enumerate(lines) if "crew_standards.py stamp" in line]
    review = [i for i, line in enumerate(lines) if "**Then, last, `/crew:review $1`**" in line]

    assert stamp and review and stamp[-1] < review[0], (stamp, review)


def test_plan_template_and_skill_carry_a_standards_line():
    template = _read(os.path.join(COMMANDS, "plan.md"))
    skill = _read(os.path.join(SKILLS, "crew-plan", "SKILL.md"))

    assert [("Standards:" in template.split("```")[1]),
            ("Standards:" in skill.split("```")[1])] == [True, True]


_TRAIN_LANDING = ("## Landing through the merge train", "crew_train.py\" status",
                  "armed: yes", 'crew_train.py" check-land --ticket "$1"',
                  "--match-head-commit", 'crew_train.py release --ticket "$1" --merged',
                  "crew_train.py catch-up", "Crew never merges")


def test_done_names_the_merge_train_landing():
    """L-0520: /crew:done names the land check, the printed merge and the
    release, and says crew never merges."""
    text = " ".join(_read(os.path.join(COMMANDS, "done.md")).split())

    missing = [s for s in _TRAIN_LANDING if s not in text]

    assert missing == [], f"done.md lacks {missing}"
