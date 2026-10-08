"""The L-0641 mutations: the fail-closed rules L-0639 and L-0640 added to
derived ticket state (`crew_ticket_state.py`, and the closed words in
`crew_state.py` and the INDEX reader in `crew_ticket.py` it leans on). Same
tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find, replace,
test) -- and appended to it there. Run `sabotage.py`, not this file.

Each one is a way a dependency that cannot be read, or that will never close
as done, reads as closed, or a next.md field that cannot be read reads as
"nothing asked" -- the unknown collapsing into the safe-looking value.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
TICKET_STATE = os.path.join(SCRIPTS, "crew_ticket_state.py")
STATE = os.path.join(SCRIPTS, "crew_state.py")
TICKET = os.path.join(SCRIPTS, "crew_ticket.py")
_T = "tests/test_ticket_state.py::"

TICKET_STATE_MUTATIONS = (
    ("ticket state: an unknown dependency (no row, no spec) reads closed", TICKET_STATE,
     '    if text is None:\n        return "unknown", (',
     '    if text is None:\n        return "closed", (',
     _T + "test_unknown_dependency_blocks"),
    ("ticket state: a cancelled or superseded dependency reads closed", TICKET_STATE,
     "    if found and cell in CLOSING_STATUSES:\n        return cell, ",
     "    if False:\n        return cell, ",
     _T + "test_cancelled_dependency_blocks_and_names_it"),
    ("ticket state: a dependency row with no status cell reads closed", TICKET,
     "                if not status:\n"
     '                    unknown = f"its row {line.strip()!r} has no status cell"\n',
     "                if not status:\n                    return True, None\n",
     _T + "test_dependency_row_without_a_status_cell_is_unknown"),
    ("ticket state: an unreadable review ledger reads as no replan", TICKET_STATE,
     'LEDGER_NOT_REPLAN = ("EMPTY", review_ledger.IN_REVIEW,',
     'LEDGER_NOT_REPLAN = ("EMPTY", review_ledger.UNKNOWN, review_ledger.IN_REVIEW,',
     _T + "test_unreadable_ledger_is_not_read_as_no_replan"),
    ("ticket state: `cancelled` dropped from the INDEX table's closed words", STATE,
     '    "done", "closed", "merged", "shipped", "complete", "completed", "cancelled", '
     '"superseded",\n',
     '    "done", "closed", "merged", "shipped", "complete", "completed", "superseded",\n',
     "tests/test_crew_state.py::test_cancelled_and_superseded_rows_are_closed"),
    ("ticket state: needs-owner with no next: reads as nothing asked", TICKET_STATE,
     '    if gate == "needs-owner" and fields["next"] is None:\n',
     "    if False:\n",
     _T + "test_needs_owner_without_next_says_cannot_tell"),
    ("ticket state: a bad revisit: date is dropped unreported (reads not due)", TICKET_STATE,
     "        except ValueError:\n"
     '            return None, f"next.md: revisit: {value!r} is not a YYYY-MM-DD date"\n',
     "        except ValueError:\n            return None, None\n",
     _T + "test_bad_revisit_date_is_listed"),
    ("ticket state: a bad waiting-on: value is accepted", TICKET_STATE,
     "        if _is_ticket_id(value):\n            return value, None\n"
     '        return None, (f"next.md: waiting-on:',
     "        if True:\n            return value, None\n"
     '        return None, (f"next.md: waiting-on:',
     _T + "test_bad_waiting_on_is_reported"),
)
