"""crew_ticket_state.py (L-0639): derived `blocked` and `needs-replan`, gating
statuses, and the could-not-tell rule; next.md (L-0640). Must-block cases first,
then must-allow."""
import datetime
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


@pytest.mark.parametrize("value", ["someone", "[T-0002", "T-0002]", "[T-0002, later]"])
def test_a_depends_on_entry_that_is_not_a_ticket_id_is_a_spec_problem(tmp_path, value):
    """Group review round 4: a plain word or an unmatched bracket is a bad
    entry (the next.md ticket-id rule), not a dependency that cannot be read."""
    root = _repo(tmp_path)
    _spec(root, T, line2=f"depends-on: {value}")
    got = _view(root)
    assert (got["blocked"], got["depends_on"]) == (None, None)
    assert any("depends-on:" in p and "not a ticket id" in p for p in got["problems"])


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


def test_stateless_ledger_with_rounds_is_not_read_as_no_replan(tmp_path):
    """Round 6: `state: null` with a spent round summarises as EMPTY."""
    root = _repo(tmp_path)
    _spec(root, T)
    _ledger(root, T, json.dumps({"state": None, "rounds": [{"round": 1, "reserved": True}]}))
    got = _view(root)
    assert got["needs_replan"] is None
    assert any("no state but records review rounds" in p for p in got["problems"])


@pytest.mark.parametrize("line,word", [("- Cancelled: T-0002", "cancelled"),
                                       ("1. superseded: T-0002", "superseded"),
                                       ("* SUPERSEDED : T-0002 by T-0003", "superseded")])
def test_prose_closing_line_blocks_and_names_it(tmp_path, line, word):
    root = _repo(tmp_path, f"# Work\n\n{line}\n")
    _spec(root, T, line2="depends-on: T-0002")
    got = _view(root)
    assert (got["blocked"], got["dependencies"][0]["state"]) == (True, word)


@pytest.mark.parametrize("row, word", [("open", "Cancelled"), ("open", "Superseded"),
                                       ("done", "Cancelled"), ("done", "Superseded"),
                                       ("cancelled", "Superseded"), ("superseded", "Cancelled"),
                                       ("cancelled", "Done"), ("superseded", "Done")])
def test_a_row_and_a_prose_line_that_disagree_are_unknown(tmp_path, row, word):
    """Group review: a row any prose line contradicts is unknown -- a closing
    word in prose against an open or done row, and any other mark against a
    cancelled or superseded row (round 2)."""
    root = _repo(tmp_path, f"| T-0002 | {row} | low | r | t |\n\n- {word}: T-0002\n")
    state, reason = crew_ticket_state.dependency_state(str(root), "T-0002")
    assert (state, "cannot tell" in reason) == ("unknown", True)


@pytest.mark.parametrize("first, second", [("open", "done"), ("done", "open"),
                                           ("cancelled", "done"), ("hold", "superseded")])
def test_two_rows_that_disagree_are_unknown(tmp_path, first, second):
    """Group review round 3: one ticket's two INDEX rows with different
    status cells cannot tell, for a dependency and for the gate."""
    rows = f"| T-0002 | {first} | low | r | t |\n| T-0002 | {second} | low | r | t |\n"
    root = _repo(tmp_path, rows)
    state, reason = crew_ticket_state.dependency_state(str(root), "T-0002")
    assert (state, "cannot tell" in reason) == ("unknown", True)
    _spec(root, "T-0002")
    assert _view(root, "T-0002")["gate"] == "unknown"


def test_two_rows_that_agree_are_read(tmp_path):
    root = _repo(tmp_path, "| T-0002 | done | low | r | t |\n| t-0002 | Done | low | r | t |\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "closed"


@pytest.mark.parametrize("line, word", [("- [x] Cancelled: T-0002", "cancelled"),
                                        ("* [X] superseded: T-0002", "superseded"),
                                        ("~~Superseded: T-0002~~", "superseded"),
                                        ("- [x] ~~Cancelled: T-0002~~", "cancelled")])
def test_a_checked_or_struck_closing_word_keeps_its_word(tmp_path, line, word):
    """Group review round 3: `_DONE_RE` matches only the `[x]`/`~~` prefix,
    so the closing word after it must still be read."""
    root = _repo(tmp_path, f"# Work\n\n{line}\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == word


def test_two_checked_lines_with_different_words_are_unknown(tmp_path):
    root = _repo(tmp_path, "# Work\n\n- [x] Cancelled: T-0002\n- [x] Superseded: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "unknown"


def test_a_checked_done_line_closes(tmp_path):
    root = _repo(tmp_path, "# Work\n\n- [x] Done: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "closed"


def test_two_prose_lines_that_disagree_are_unknown(tmp_path):
    root = _repo(tmp_path, "# Work\n\n- Done: T-0002\n- Cancelled: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "unknown"


@pytest.mark.parametrize("word", ["cancelled", "superseded"])
def test_a_closing_row_and_prose_that_agree_name_the_word(tmp_path, word):
    root = _repo(tmp_path, f"| T-0002 | {word} | low | r | t |\n\n- {word.title()}: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == word


def test_a_done_row_and_a_done_prose_line_agree_and_close(tmp_path):
    root = _repo(tmp_path, "| T-0002 | done | low | r | t |\n\n- Done: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "closed"


def test_prose_done_line_closes(tmp_path):
    root = _repo(tmp_path, "# Work\n\n- Done: T-0002\n")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "closed"


def test_title_carrying_status_does_not_close_a_dependency(tmp_path):
    root = _repo(tmp_path)
    folder = root / ".work" / "tickets" / "T-0002"
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text("# T-0002 Explain status: done reporting          status: spec"
                                    "   risk: low\n## Intent\nx\n", encoding="utf-8")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "unknown"


@pytest.mark.parametrize("header", ["# T-0002 Explain status: done reporting",
                                    "# T-0002 Explain status: done reporting   risk: low",
                                    "# T-0002 x          status: done   status: spec"])
def test_title_status_without_a_status_field_is_unknown(tmp_path, header):
    """Round 5: a `status:` in the title is not the header's status field."""
    root = _repo(tmp_path)
    folder = root / ".work" / "tickets" / "T-0002"
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text(header + "\n## Intent\nx\n", encoding="utf-8")
    assert crew_ticket_state.dependency_state(str(root), "T-0002")[0] == "unknown"


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
    (root / ".work" / "tickets" / T / "next.md").write_text(
        "waiting-on: owner\nnext: answer Q1\nrevisit: 2026-10-01\n", encoding="utf-8")
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


# --- next.md (L-0640): must-block --------------------------------------------

TODAY = datetime.date(2026, 10, 5)


def _next(folder, text):
    (folder / "next.md").write_bytes(text.encode("utf-8") if isinstance(text, str) else text)


def _next_view(root, ticket=T):
    return crew_ticket_state.view(str(root), ticket, today=TODAY)


def test_needs_owner_without_next_says_cannot_tell(tmp_path):
    root = _repo(tmp_path, f"| {T} | needs-owner | low | r | t |\n")
    _next(_spec(root, T), "waiting-on: owner\n")
    got = _next_view(root)
    assert "needs-owner: cannot tell what is asked (no next: in next.md)" in got["problems"]


def test_needs_owner_without_next_md_says_cannot_tell(tmp_path):
    root = _repo(tmp_path, f"| {T} | needs-owner | low | r | t |\n")
    _spec(root, T)
    assert "needs-owner: cannot tell what is asked (no next: in next.md)" in \
        _next_view(root)["problems"]


def test_superseded_without_successor_is_reported(tmp_path):
    root = _repo(tmp_path, f"| {T} | superseded | low | r | t |\n")
    _next(_spec(root, T), "reason: replaced\n")
    got = _next_view(root)
    assert any(p.startswith("superseded: cannot tell what replaced it") for p in got["problems"])


@pytest.mark.parametrize("line", ["split-into: TBD", "superseded-by: later", "split-into: T-0002, ?",
                                  "split-into: T-0002]", "superseded-by: [T-0002",
                                  "split-into: [[T-0002]]"])
def test_superseded_with_a_spec_line_naming_no_ticket_is_reported(tmp_path, line):
    """Round 1: a successor line must name ticket ids to count."""
    root = _repo(tmp_path, f"| {T} | superseded | low | r | t |\n")
    _spec(root, T, header="status: superseded   risk: low", line2=line)
    assert crew_ticket_state.SUPERSEDED_NO_SUCCESSOR in _next_view(root)["problems"]


@pytest.mark.parametrize("line", [f"superseded-by: {T}", f"split-into: {T.lower()}",
                                  f"split-into: [{T}, T-0002]"])
def test_a_spec_successor_naming_the_ticket_itself_is_not_a_successor(tmp_path, line):
    """Group review round 5: a ticket cannot replace itself."""
    root = _repo(tmp_path, f"| {T} | superseded | low | r | t |\n")
    _spec(root, T, header="status: superseded   risk: low", line2=line)
    assert crew_ticket_state.SUPERSEDED_NO_SUCCESSOR in _next_view(root)["problems"]


def test_a_next_md_successor_naming_the_ticket_itself_is_a_problem(tmp_path):
    root = _repo(tmp_path, f"| {T} | superseded | low | r | t |\n")
    _next(_spec(root, T), f"superseded-by: {T}\n")
    got = _next_view(root)
    assert got["next"]["superseded-by"] is None
    assert any("superseded-by:" in p and "itself" in p for p in got["problems"])
    assert crew_ticket_state.SUPERSEDED_NO_SUCCESSOR in got["problems"]


def test_a_depends_on_naming_the_ticket_itself_is_a_problem(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T, line2=f"depends-on: T-0002, {T}")
    got = _view(root)
    assert (got["blocked"], got["depends_on"]) == (None, None)
    assert any("depends-on:" in p and "itself" in p for p in got["problems"])


def test_bad_waiting_on_is_reported(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), "waiting-on: someone\n")
    got = _next_view(root)
    assert got["next"]["waiting-on"] is None
    assert any("waiting-on" in p and "someone" in p for p in got["problems"])


@pytest.mark.parametrize("value", ["2026-13-01", "5 Oct 2026", "2026-10-5", "soon"])
def test_bad_revisit_date_is_listed(tmp_path, value):
    root = _repo(tmp_path, f"| {T} | hold | low | r | t |\n")
    _next(_spec(root, T), f"revisit: {value}\n")
    got = _next_view(root)
    assert (got["revisit_due"], got["next"]["revisit"]) == (None, None)
    assert any("revisit" in p and value in p for p in got["problems"])


def test_duplicate_key_is_reported(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), "next: answer Q1\nNext: answer Q2\n")
    got = _next_view(root)
    assert got["next"]["next"] is None
    assert any("next" in p and "more than once" in p for p in got["problems"])


def test_unreadable_next_md_is_reported(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), b"waiting-on: owner\nnext: \xff\xfe broken\n")
    got = _next_view(root)
    assert set(got["next"].values()) == {None}
    assert any("next.md" in p and "cannot tell" in p for p in got["problems"])


def test_next_md_symlink_out_of_the_folder_is_refused(tmp_path):
    root = _repo(tmp_path)
    folder = _spec(root, T)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("waiting-on: owner\nnext: from outside\n", encoding="utf-8")
    try:
        os.symlink(outside, folder / "next.md")
    except (OSError, NotImplementedError):
        pytest.skip("cannot create a symlink here")
    got = _next_view(root)
    assert set(got["next"].values()) == {None}
    assert any("next.md" in p and "outside" in p for p in got["problems"])


def test_line_that_is_not_key_value_is_reported(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), "waiting on the owner\n")
    assert any("not a `key: value` line" in p for p in _next_view(root)["problems"])


def test_empty_value_is_reported(tmp_path):
    root = _repo(tmp_path, f"| {T} | needs-owner | low | r | t |\n")
    _next(_spec(root, T), "next:\n")
    got = _next_view(root)
    assert got["next"]["next"] is None
    assert any("next.md: next: is empty" in p for p in got["problems"])


# --- next.md (L-0640): must-allow --------------------------------------------

def test_next_md_fields_are_read(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), "# a comment\n\nWaiting-On: owner\nnext: answer Q1 in spec.md\n"
                          "reason: waits on the vendor\nrevisit: 2026-11-01\n"
                          "superseded-by: T-0009\nowner-note: ignored\n")
    got = _next_view(root)
    assert got["next"] == {"waiting-on": "owner", "next": "answer Q1 in spec.md",
                           "reason": "waits on the vendor", "revisit": "2026-11-01",
                           "superseded-by": "T-0009"}
    assert (got["revisit_due"], got["problems"]) == (False, [])


def test_long_free_text_is_clipped_for_display(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), "next: " + "x" * 300 + "\n")
    assert len(_next_view(root)["next"]["next"]) == crew_ticket_state.NEXT_TEXT_MAX


def test_no_next_md_has_no_problems(tmp_path):
    root = _repo(tmp_path)
    _spec(root, T)
    got = _next_view(root)
    assert (got["problems"], got["revisit_due"], set(got["next"].values())) == ([], None, {None})


def test_hold_revisit_in_the_future_is_not_due(tmp_path):
    root = _repo(tmp_path, f"| {T} | hold | low | r | t |\n")
    _next(_spec(root, T), "reason: vendor fix\nrevisit: 2026-10-06\n")
    got = _next_view(root)
    assert (got["gate"], got["revisit_due"], got["problems"]) == ("hold", False, [])


@pytest.mark.parametrize("day", ["2026-10-05", "2026-01-31"])
def test_hold_revisit_today_is_due(tmp_path, day):
    root = _repo(tmp_path, f"| {T} | hold | low | r | t |\n")
    _next(_spec(root, T), f"revisit: {day}\n")
    assert _next_view(root)["revisit_due"] is True


def test_waiting_on_a_ticket_id(tmp_path):
    root = _repo(tmp_path)
    _next(_spec(root, T), "waiting-on: L-0641\n")
    got = _next_view(root)
    assert (got["next"]["waiting-on"], got["problems"]) == ("L-0641", [])


def test_needs_owner_with_next_has_no_problem(tmp_path):
    root = _repo(tmp_path, f"| {T} | needs-owner | low | r | t |\n")
    _next(_spec(root, T), "waiting-on: owner\nnext: pick option A or B\n")
    assert _next_view(root)["problems"] == []


@pytest.mark.parametrize("line", ["split-into: T-0002, T-0003", "superseded-by: T-0009",
                                  "split-into: [L-0640, L-0641]"])
def test_superseded_with_a_spec_successor_line_is_not_reported(tmp_path, line):
    """T-0037/T-0052's successor line under the spec header still names it."""
    root = _repo(tmp_path, f"| {T} | superseded | low | r | t |\n")
    _spec(root, T, header="status: superseded   risk: low", line2=line)
    assert _next_view(root)["problems"] == []
