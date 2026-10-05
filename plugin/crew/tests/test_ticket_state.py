"""crew_ticket_state.py (L-0639): derived `blocked` and `needs-replan`, gating
statuses, and the could-not-tell rule. Must-block cases first, then must-allow."""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_ticket
import crew_ticket_state
import crew_tracker
import review_ledger

T = "T-0001"


def _repo(tmp_path, index=""):
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(index, encoding="utf-8", newline="\n")
    return root


def _spec(root, ticket, header="status: spec   risk: low", line2=None):
    folder = root / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    body = f"# {ticket} title          {header}\n"
    if line2 is not None:
        body += line2 + "\n"
    body += "## Intent\nx\n"
    (folder / "spec.md").write_text(body, encoding="utf-8", newline="\n")
    return folder


def _ledger(root, ticket, text):
    path = review_ledger.ledger_path(str(root), ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _view(root, ticket=T):
    return crew_ticket_state.view(str(root), ticket)


# --- vocabulary --------------------------------------------------------------

def test_closing_statuses_are_the_tracker_closed_words():
    assert crew_ticket_state.CLOSING_STATUSES == crew_tracker.CLOSED_STATUSES


# --- must-block --------------------------------------------------------------

def test_open_dependency_blocks(tmp_path):
    root = _repo(tmp_path, "| T-0002 | in-progress | low | r | t |\n")
    _spec(root, T, line2="depends-on: [T-0002]")
    got = _view(root)
    assert (got["blocked"], got["dependencies"][0]["state"], "blocked" in got["derived"]) == \
        (True, "open", True)


def test_unknown_dependency_blocks(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T, line2="depends-on: T-0002")
    got = _view(root)
    dep = got["dependencies"][0]
    assert (got["blocked"], dep["state"], "cannot tell" in dep["reason"]) == (True, "unknown", True)


@pytest.mark.parametrize("word", ["cancelled", "superseded"])
def test_cancelled_dependency_blocks_and_names_it(tmp_path, word):
    root = _repo(tmp_path, f"| T-0002 | {word} | low | r | t |\n")
    _spec(root, T, line2="depends-on: T-0002")
    got = _view(root)
    dep = got["dependencies"][0]
    assert (got["blocked"], dep["state"], word in dep["reason"]) == (True, word, True)


def test_superseded_dependency_blocks_and_names_it(tmp_path):
    """By its spec header, with no INDEX row: still never `closed`."""
    root = _repo(tmp_path)
    _spec(root, "T-0002", header="status: superseded   risk: low")
    _spec(root, T, line2="depends-on: T-0002")
    got = _view(root)
    assert (got["blocked"], got["dependencies"][0]["state"]) == (True, "superseded")


def test_dependency_row_without_a_status_cell_is_unknown(tmp_path):
    root = _repo(tmp_path, "| T-0002 |\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "unknown"


@pytest.mark.parametrize("word", ["in-progress", "spec", "review"])
def test_open_spec_header_without_a_row_is_unknown(tmp_path, word):
    """No INDEX row: only a closed or closing header word answers; anything else cannot tell."""
    root = _repo(tmp_path)
    _spec(root, "T-0002", header=f"status: {word}   risk: low")
    state, reason = crew_ticket_state.dependency_state(str(root), "T-0002")
    assert (state, "cannot tell" in reason) == ("unknown", True)


def test_unreadable_index_makes_a_dependency_unknown(tmp_path):
    root = _repo(tmp_path)
    (root / ".work" / "INDEX.md").unlink()
    (root / ".work" / "INDEX.md").mkdir()
    state, reason = crew_ticket_state.dependency_state(str(root), "T-0002")
    assert (state, "cannot tell" in reason) == ("unknown", True)


def test_needs_replan_is_derived_from_the_ledger(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T)
    _ledger(root, T, json.dumps({"state": review_ledger.NEEDS_REPLAN, "rounds": []}))
    got = _view(root)
    assert (got["needs_replan"], "needs-replan" in got["derived"]) == (True, True)


def test_unreadable_ledger_is_not_read_as_no_replan(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T)
    _ledger(root, T, "{not json")
    got = _view(root)
    assert got["needs_replan"] is None
    assert any("needs-replan" in p and "cannot tell" in p for p in got["problems"])


@pytest.mark.parametrize("word", ["blocked", "needs-replan"])
def test_typed_derived_status_in_index_is_reported(tmp_path, word):
    root = _repo(tmp_path, f"| {T} | {word} | low | r | t |\n")
    _spec(root, T)
    got = _view(root)
    assert any(word in p and "not obeyed" in p for p in got["problems"])
    assert got["derived"] == []


def test_bad_depends_on_entry_is_unknown_not_unblocked(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T, line2="depends-on: T-0002, ../x")
    got = _view(root)
    assert got["blocked"] is None and got["depends_on"] is None
    assert any("not a ticket id" in p for p in got["problems"])


def test_unreadable_spec_is_unknown_not_unblocked(tmp_path):
    root = _repo(tmp_path)
    folder = root / ".work" / "tickets" / T
    (folder / "spec.md").mkdir(parents=True)
    got = _view(root)
    assert got["blocked"] is None


def test_open_row_and_a_closing_prose_line_disagree_and_are_unknown(tmp_path):
    root = _repo(tmp_path, "| T-0002 | open | low | r | t |\n\n- Done: T-0002\n")
    state, reason = crew_ticket_state.dependency_state(str(root), "T-0002")
    assert (state, "cannot tell" in reason) == ("unknown", True)


def test_unrecognised_ledger_state_is_not_read_as_no_replan(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T)
    _ledger(root, T, json.dumps({"state": "UNRECOGNIZED", "rounds": []}))
    got = _view(root)
    assert got["needs_replan"] is None
    assert any("UNRECOGNIZED" in p for p in got["problems"])


@pytest.mark.parametrize("line,word", [("- Cancelled: T-0002", "cancelled"),
                                       ("1. superseded: T-0002", "superseded"),
                                       ("* SUPERSEDED : T-0002 by T-0003", "superseded")])
def test_prose_closing_line_blocks_and_names_it(tmp_path, line, word):
    root = _repo(tmp_path, f"# Work\n\n{line}\n")
    _spec(root, T, line2="depends-on: T-0002")
    got = _view(root)
    assert (got["blocked"], got["dependencies"][0]["state"]) == (True, word)


def test_prose_done_line_closes(tmp_path):
    root = _repo(tmp_path, "# Work\n\n- Done: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "closed"


def test_missing_spec_is_unknown_not_unblocked(tmp_path):
    root = _repo(tmp_path)
    got = _view(root)
    assert (got["blocked"], got["depends_on"]) == (None, None)
    assert any("no spec.md" in p for p in got["problems"])


def test_unreadable_index_leaves_the_gate_unknown(tmp_path):
    root = _repo(tmp_path)
    (root / ".work" / "INDEX.md").unlink()
    (root / ".work" / "INDEX.md").mkdir()
    _spec(root, T, header="status: cancelled   risk: low")
    got = _view(root)
    assert (got["gate"], got["gate_source"]) == ("unknown", None)


# --- must-allow --------------------------------------------------------------

def test_all_dependencies_closed_is_not_blocked(tmp_path):
    root = _repo(tmp_path, "| T-0002 | done | low | r | t |\n| T-0003 | merged | low | r | t |\n")
    _spec(root, T, line2="depends-on: [T-0002, T-0003]")
    got = _view(root)
    assert (got["blocked"], [d["state"] for d in got["dependencies"]], got["derived"]) == \
        (False, ["closed", "closed"], [])


@pytest.mark.parametrize("word", ["done", "merged"])
def test_dependency_closed_by_its_spec_header_without_a_row(tmp_path, word):
    root = _repo(tmp_path)
    _spec(root, "T-0002", header=f"status: {word}   risk: low")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "closed"


def test_no_depends_on_is_not_blocked(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T)
    got = _view(root)
    assert (got["blocked"], got["depends_on"], got["needs_replan"], got["problems"]) == \
        (False, [], False, [])


def test_gate_reads_index_first_then_header(tmp_path):
    root = _repo(tmp_path, f"| {T} | hold | low | r | t |\n")
    _spec(root, T, header="status: cancelled   risk: low")
    assert (_view(root)["gate"], _view(root)["gate_source"]) == ("hold", "index")
    (root / ".work" / "INDEX.md").write_text(f"| {T} | in-progress | low | r | t |\n",
                                            encoding="utf-8")
    assert (_view(root)["gate"], _view(root)["gate_source"]) == ("cancelled", "header")
    _spec(root, T, header="status: spec   risk: low")
    assert _view(root)["gate"] is None


def test_depends_on_after_the_first_section_is_not_read(tmp_path):
    assert crew_ticket_state.parse_depends_on(
        "# T-1 x   status: spec\n## Intent\ndepends-on: T-2\n") == ([], None)


def test_view_is_read_only(tmp_path):
    root = _repo(tmp_path, "| T-0002 | open | low | r | t |\n")
    _spec(root, T, line2="depends-on: T-0002")
    _ledger(root, T, json.dumps({"state": review_ledger.NEEDS_REPLAN, "rounds": []}))
    walks = [str(root), os.path.join(crew_ticket.common_dir(str(root)), "crew")]

    def snapshot():
        found = {}
        for top in walks:
            for base, _dirs, files in os.walk(top):
                for name in files:
                    path = os.path.join(base, name)
                    found[path] = os.stat(path).st_mtime_ns
        return found

    before = snapshot()
    _view(root)
    assert snapshot() == before
