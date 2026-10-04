"""T-0037: one ticket status vocabulary, owned by `crew_tracker.py`.

`needs-owner`, `cancelled` and `superseded` are rows in crew_tracker's table.
Every other reader keeps its own list -- crew_state's closed words (the
session brief, `resolve_active`, approval precheck), autopilot's INDEX and
header lists, the Obsidian lane table copied into `obsidian-sync.md` and the
README -- so each list is held to crew_tracker's here, and a word added in one
place and forgotten in another fails by name instead of reopening a ticket.
"""
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_state
import crew_ticket
import crew_tracker

_ROOT = context._ROOT  # pylint: disable=protected-access
CLOSED = crew_tracker.CLOSED_STATUSES
OWNER = crew_tracker.OWNER_STATUSES


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _table_words(text, heading):
    """Every backticked word in the first cell of each row of the table under `heading`."""
    section = text.split(heading, 1)[1]
    rows = []
    for line in section.splitlines()[1:]:
        if line.startswith("#"):
            break
        if line.startswith("|") and not line.startswith("|---"):
            rows.append(line.split("|")[1])
    return set(re.findall(r"`([a-z-]+)`", " ".join(rows)))


def test_closed_words_are_closed_in_every_reader():
    assert {word: (word in crew_state._TABLE_DONE_WORDS,  # pylint: disable=protected-access
                   word in crew_autopilot.INDEX_DONE, word in crew_autopilot.HEADER_CLOSED)
            for word in CLOSED} == {word: (True, True, True) for word in CLOSED}


@pytest.mark.parametrize("word", CLOSED)
def test_closed_words_close_a_prose_line(word):
    """`_DONE_RE` is the prose half of the same reader; a word only in the table set misses `- cancelled: T-1`."""
    assert (bool(crew_state._DONE_RE.search(f"- {word}: T-1")),  # pylint: disable=protected-access
            bool(crew_state._DONE_RE.search(f"- {word.title()}: T-1"))) == (True, True)  # pylint: disable=protected-access


def test_new_words_share_nothing_with_status_values():
    """A closed or owner word in STATUS_VALUES would make that header edit KEEP an approval."""
    assert set(CLOSED + OWNER) & set(crew_ticket.STATUS_VALUES) == set()


def test_owner_word_is_open_everywhere():
    readers = (crew_state._TABLE_DONE_WORDS, crew_autopilot.INDEX_DONE,  # pylint: disable=protected-access
               crew_autopilot.HEADER_CLOSED, crew_autopilot.DIRECTION_APPROVED)
    assert ([word for word in OWNER if any(word in reader for reader in readers)],
            OWNER, crew_autopilot.WAITING.get(crew_autopilot.NEEDS_OWNER)) == ([], ("needs-owner",), "owner")


def test_every_closed_header_word_is_a_tracker_closed_word_or_done():
    assert set(crew_autopilot.HEADER_CLOSED) == set(CLOSED) | {"done"}


def test_obsidian_sync_table_lists_every_lane_status():
    words = _table_words(_read("commands", "obsidian-sync.md"), "| INDEX status |")

    assert sorted(set(crew_tracker.LANE_FOR_STATUS) - words) == []


def test_readme_ticket_statuses_table_lists_every_tracker_status():
    words = _table_words(_read("README.md"), "### Ticket statuses")

    assert sorted(set(crew_tracker.LANE_FOR_STATUS) - words) == []
