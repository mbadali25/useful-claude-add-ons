"""R-72: every tracker kind's status map, the Jira target line, and `transition`.

    python3 -m pytest plugin/crew/tests/test_crew_tracker_maps.py -q

No invented status: a move or push to a status a kind's map lacks is refused.
`transition` (Jira only) answers from the issue's last seen status. Every repo
here is a throwaway under tmp_path. The in-test mutants at the end each patch
one guard out of the module in this process (never `crew_tracker.py`'s text,
so the sabotage anchors keep their counts) and assert the paired case goes red.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_tracker
from crew_fixtures import make_repo

SCRIPT = os.path.join(os.path.dirname(crew_tracker.__file__), "crew_tracker.py")
KEY = "ABC-12"
WORDS = crew_tracker.KNOWN_STATUSES
# The owner's workflow artifact, "JIRA STATUSES", in its order.
ARTIFACT = ("Backlog", "Brainstorm", "Spec", "Approve", "In Progress", "Development In Review",
            "Deployed to Development", "QA In Review", "Deployed to QA", "Production In Review",
            "Deployed to Prod", "Blocked or Parked", "Complete")
FORWARD = {"direction": "Brainstorm", "ready": "Spec", "spec": "Approve", "planned": "Approve",
           "in-progress": "In Progress", "review": "Development In Review", "done": "Complete",
           "needs-owner": "Blocked or Parked"}
REVERSE = {"Backlog": "direction", "Brainstorm": "direction", "Spec": "ready", "Approve": "spec",
           "In Progress": "in-progress", "Development In Review": "review",
           "Deployed to Development": "review", "QA In Review": "review", "Deployed to QA": "review",
           "Production In Review": "review", "Deployed to Prod": "review",
           "Blocked or Parked": "needs-owner", "Complete": "done"}


def _crew_json(root, tracker):
    (root / ".crew" / "crew.json").write_text(json.dumps({"schema": 1, "tracker": tracker}),
                                              encoding="utf-8")


def _repo(tmp_path, kind="jira"):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": kind})
    return root


def _cli(root, *args):
    return subprocess.run([sys.executable, SCRIPT, *args, "--root", str(root)],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


# --- the maps ---------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["files", "obsidian", "sdp"])
@pytest.mark.parametrize("word", WORDS)
def test_files_obsidian_and_sdp_map_each_word_to_itself(kind, word):
    assert crew_tracker.map_status(kind, word) == (word, None)


@pytest.mark.parametrize("word", sorted(FORWARD))
def test_jira_maps_each_open_word_to_its_workflow_name(word):
    native, why = crew_tracker.map_status("jira", word)

    assert (native, why, native in crew_tracker.JIRA_STATUSES) == (FORWARD[word], None, True)


@pytest.mark.parametrize("word", ["cancelled", "superseded"])
def test_jira_has_no_native_status_for_a_closed_word(word):
    native, why = crew_tracker.map_status("jira", word)

    assert (native, crew_tracker.native_status("jira", word)) == (None, None)
    assert why == f"no native status for {word}; the owner closes it by hand"


@pytest.mark.parametrize("kind", crew_tracker.KINDS)
@pytest.mark.parametrize("word,hint", [("approved", "; the crew word is spec"), ("Done", ""),
                                       ("merged", "; the crew word is done"), ("", "")])
def test_a_word_crew_does_not_know_is_refused_on_every_kind(kind, word, hint):
    assert crew_tracker.map_status(kind, word) == (None, f"{word} is not a crew status{hint}")


@pytest.mark.parametrize("name", ARTIFACT)
def test_each_jira_name_reads_as_its_crew_word(name):
    assert crew_tracker.jira_crew_word(name) == REVERSE[name]


@pytest.mark.parametrize("name", ["Done", "In Review", "", "complete", "in progress", " Complete"])
def test_a_jira_name_off_the_list_is_could_not_tell(name):
    """Matched verbatim: `complete` is not `Complete`."""
    assert crew_tracker.jira_crew_word(name) == crew_tracker.COULD_NOT_TELL


def test_jira_statuses_are_the_artifacts_thirteen_in_its_order():
    assert crew_tracker.JIRA_STATUSES == ARTIFACT
    assert len(set(crew_tracker.JIRA_STATUSES)) == 13
    assert sorted(crew_tracker.JIRA_TO_CREW) == sorted(ARTIFACT)
    assert crew_tracker.STATUS_MAP["jira"] == FORWARD


def test_only_jira_has_a_reverse_map():
    """Nothing maps a desk name to a crew word: sdp-sync resolves desk names itself."""
    reverse = [name for name in dir(crew_tracker) if name.endswith("_TO_CREW")]

    assert reverse == ["JIRA_TO_CREW"]
    assert crew_tracker.jira_crew_word("Open") == crew_tracker.COULD_NOT_TELL


def test_map_cli(tmp_path):
    root = _repo(tmp_path)

    ok, closed, unknown = (_cli(root, "map", "--to", "review"),
                           _cli(root, "map", "--to", "cancelled"),
                           _cli(root, "map", "--to", "approved", "--kind", "sdp"))

    assert (ok.returncode, ok.stdout) == (0, "jira: review -> Development In Review\n")
    assert (closed.returncode, closed.stdout) == (
        1, "jira: refused: no native status for cancelled; the owner closes it by hand\n")
    assert (unknown.returncode, unknown.stdout) == (
        1, "sdp: refused: approved is not a crew status; the crew word is spec\n")


# --- the Jira target line -----------------------------------------------------------

def test_jira_move_in_progress_prints_the_target_line(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "move", "--ticket", KEY, "--to", "in-progress")

    assert (done.returncode, done.stdout) == (
        3, f"jira: delegated: run /crew:jira-sync {KEY} --push --to in-progress\njira: target: In Progress\n")


def test_jira_move_done_prints_complete(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "move", "--ticket", KEY, "--to", "done")

    assert (done.returncode, done.stdout.splitlines()[1:]) == (3, ["jira: target: Complete"])


def test_line_of_a_delegated_result_is_still_one_line():
    """`_line`'s other readers (autopilot, crew_split, crew_ticket) see what they saw."""
    result = crew_tracker._push("jira", KEY, "in-progress")  # pylint: disable=protected-access

    assert (result["target"], result["command"], result["reason"]) == (
        "In Progress", f"/crew:jira-sync {KEY} --push --to in-progress",
        f"run /crew:jira-sync {KEY} --push --to in-progress")
    assert crew_tracker._line(result) == (  # pylint: disable=protected-access
        f"jira: delegated: run /crew:jira-sync {KEY} --push --to in-progress")


def test_move_json_carries_the_target(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "move", "--ticket", KEY, "--to", "in-progress", "--json")

    result = json.loads(done.stdout)["results"][0]
    assert (result["target"], result["command"], result["reason"]) == (
        "In Progress", f"/crew:jira-sync {KEY} --push --to in-progress",
        f"run /crew:jira-sync {KEY} --push --to in-progress")


@pytest.mark.parametrize("status", ["in-progress", "done"])
def test_sdp_move_is_byte_identical_one_line(tmp_path, status):
    root = _repo(tmp_path, "sdp")

    done = _cli(root, "move", "--ticket", "SDP-40219", "--to", status)

    assert (done.returncode, done.stdout) == (
        3, f"sdp: delegated: run /crew:sdp-sync SDP-40219 --push --to {status}\n")
    assert "target" not in crew_tracker._push("sdp", "SDP-40219", status)  # pylint: disable=protected-access


def test_jira_move_to_spec_still_pushes_nothing(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "move", "--ticket", KEY, "--to", "spec")

    assert (done.returncode, done.stdout) == (
        0, "tracker: jira syncs at boundaries only (in-progress, done); nothing to push\n")


# --- transition --------------------------------------------------------------------

TRANSITIONS = [
    ("in-progress", "Spec", False, "go: In Progress"),
    ("in-progress", "In Progress", False, "unchanged: already In Progress"),
    ("planned", "Approve", False, "unchanged: already Approve"),
    ("spec", "Approve", False, "unchanged: already Approve"),
    ("in-progress", "Complete", False, "refused: closed: Complete"),
    ("in-progress", "Complete", True, "go: In Progress"),
    ("done", "Weird Status", False, 'refused: could not tell "Weird Status"'),
    ("in-progress", "Development In Review", False,
     f"refused: backwards: {KEY} is review; moving it back to in-progress needs --reopen"),
    ("review", "QA In Review", False, 'refused: backwards: "QA In Review" is past "Development In Review"'),
    ("review", "Deployed to Prod", False,
     'refused: backwards: "Deployed to Prod" is past "Development In Review"'),
    ("review", "QA In Review", True, "go: Development In Review"),
    ("review", "Development In Review", False, "unchanged: already Development In Review"),
    ("direction", "Backlog", False, "go: Brainstorm"),
    ("done", "QA In Review", False, "go: Complete"),
    ("in-progress", "Blocked or Parked", False, "go: In Progress"),
    ("cancelled", "Spec", False, "refused: no native status for cancelled"),
]


def _answer(to, seen, reopen):
    return crew_tracker.transition_answer(KEY, to, seen, reopen)


@pytest.mark.parametrize("to,seen,reopen,expect", TRANSITIONS)
def test_transition_answers_from_the_last_seen_status(to, seen, reopen, expect):
    assert _answer(to, seen, reopen) == expect


def test_transition_planned_on_approve_is_unchanged():
    assert _answer("planned", "Approve", False) == "unchanged: already Approve"


def test_transition_review_on_qa_is_backwards():
    assert _answer("review", "QA In Review", False) == (
        'refused: backwards: "QA In Review" is past "Development In Review"')


def test_transition_complete_case_folded_is_could_not_tell():
    assert _answer("done", "complete", False) == 'refused: could not tell "complete"'


def test_transition_cancelled_is_refused():
    assert _answer("cancelled", "Spec", False) == "refused: no native status for cancelled"


def test_transition_cli_on_jira(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "transition", "--ticket", KEY, "--to", "in-progress", "--seen", "Spec")

    assert (done.returncode, done.stdout) == (0, "go: In Progress\n")


def _jira_only_message(kind):
    return crew_tracker.JIRA_ONLY.format(kind=kind)


def test_transition_on_sdp_is_usage_before_seen_is_read(tmp_path):
    """Must-allow: an SDP desk status such as Open never refuses an SDP push."""
    root = _repo(tmp_path, "sdp")

    code, line = crew_tracker.transition(str(root), "SDP-40219", "done", "Open")

    assert (code, line) == (2, _jira_only_message("sdp"))
    assert ("sdp-sync" in line, "sdp_list_metadata" in line, "refused" in line, "could not tell" in line) == (
        True, True, False, False)


def test_transition_cli_on_sdp_exits_two(tmp_path):
    root = _repo(tmp_path, "sdp")

    done = _cli(root, "transition", "--ticket", "SDP-40219", "--to", "in-progress", "--seen", "In Progress")

    assert (done.returncode, done.stdout) == (2, _jira_only_message("sdp") + "\n")


@pytest.mark.parametrize("kind", ["files", "obsidian"])
def test_transition_on_files_and_obsidian_is_jira_only(tmp_path, kind):
    root = _repo(tmp_path, kind)

    code, line = crew_tracker.transition(str(root), "T-0042", "in-progress", "in-progress")

    assert (code, "transition is for jira only" in line) == (2, True)


def test_transition_on_a_tracker_that_could_not_tell_answers_as_move(tmp_path):
    root = make_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text("{not json", encoding="utf-8")

    moved = _cli(root, "move", "--ticket", KEY, "--to", "in-progress")
    code, line = crew_tracker.transition(str(root), KEY, "in-progress", "Spec")

    assert (code, line + "\n") == (moved.returncode, moved.stdout)
    assert (code, "jira only" in line) == (1, False)


def test_transition_with_no_tracker_answers_as_move(tmp_path):
    root = make_repo(tmp_path)

    moved = _cli(root, "move", "--ticket", KEY, "--to", "in-progress")
    code, line = crew_tracker.transition(str(root), KEY, "in-progress", "Spec")

    assert (code, line + "\n") == (moved.returncode, moved.stdout)
    assert "jira only" not in line


def test_transition_refuses_an_archived_ticket(tmp_path):
    root = _repo(tmp_path)
    os.makedirs(root / ".work" / "tickets" / "Complete" / KEY)

    code, line = crew_tracker.transition(str(root), KEY, "in-progress", "Spec")

    assert (code, line) == (0, "refused: " + crew_tracker._archived(KEY))  # pylint: disable=protected-access


# --- in-test mutants (D15): each must turn its paired case red ------------------------

def _red(case, *args):
    with pytest.raises(AssertionError):
        case(*args)


def test_mutant_reverse_map_case_folds(monkeypatch):
    folded = {name.casefold(): word for name, word in crew_tracker.JIRA_TO_CREW.items()}
    monkeypatch.setattr(crew_tracker, "jira_crew_word",
                        lambda name: folded.get(name.casefold(), crew_tracker.COULD_NOT_TELL))

    _red(test_a_jira_name_off_the_list_is_could_not_tell, "complete")
    _red(test_transition_complete_case_folded_is_could_not_tell)


def test_mutant_cancelled_gains_a_jira_name(monkeypatch):
    monkeypatch.setitem(crew_tracker.STATUS_MAP["jira"], "cancelled", "Complete")

    _red(test_jira_has_no_native_status_for_a_closed_word, "cancelled")
    _red(test_transition_cancelled_is_refused)


def test_mutant_unchanged_compares_crew_words(monkeypatch):
    monkeypatch.setattr(crew_tracker, "_unchanged", lambda seen, seen_word, target, to: seen_word == to)

    _red(test_transition_planned_on_approve_is_unchanged)


def test_mutant_same_word_order_check_removed(monkeypatch):
    monkeypatch.setattr(crew_tracker, "_past_in_word", lambda *_: None)

    _red(test_transition_review_on_qa_is_backwards)


def test_mutant_jira_only_check_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_tracker, "_jira_only", lambda kind: None)

    _red(test_transition_on_sdp_is_usage_before_seen_is_read, tmp_path)


def test_mutant_folder_refusal_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_tracker, "_folder_refusal", lambda root, ticket: "")

    _red(test_transition_refuses_an_archived_ticket, tmp_path)


def test_mutant_target_moves_into_line(tmp_path, monkeypatch, capsys):
    real = crew_tracker._line  # pylint: disable=protected-access

    def with_target(result):
        text = real(result)
        return text + f"\n{result['backend']}: target: {result['target']}" if result.get("target") else text
    monkeypatch.setattr(crew_tracker, "_line", with_target)

    _red(test_line_of_a_delegated_result_is_still_one_line)
    import test_crew_autopilot_tracker  # pylint: disable=import-outside-toplevel
    _red(test_crew_autopilot_tracker.test_cli_tracker_on_jira_prints_no_target_line, tmp_path, capsys)
