"""L-0733 mutations: the undeclared-reach wall and the marker it pinned. Same
tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find, replace,
test) -- and appended to it there. Run `sabotage.py`, not this file; to run
only these:

    python3 -c "import sabotage, sabotage_reach_notice as m; \\
        sabotage.MUTATIONS = m.REACH_NOTICE_MUTATIONS; raise SystemExit(sabotage.main())"

Each one puts back a piece of what TheSelectSource saw on crew 1.2.1: a
`rules[N] wrapper or inline shell` line per rule per Stop (both flavours), a
`NOT VERIFIED ON THIS TREE - rules[N]` line per record entry, the full notice
on every Stop instead of once per map, an edited undeclared rule holding the
marker, and a blocking orphan whose only named exit runs network/host rules.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
SH = os.path.join(SCRIPTS, "verify-gate.sh")
PS1 = os.path.join(SCRIPTS, "verify-gate.ps1")
RECORD = os.path.join(SCRIPTS, "verify_record.py")
_T = "tests/test_verify_gate_reach_notice.py::"

REACH_NOTICE_MUTATIONS = (
    ("L-0733 a: the sh matcher names every undeclared rule on every Stop", SH,
     "        if STOP_MODE and _kind in _UNDECLARED_KINDS:\n",
     "        if False and STOP_MODE and _kind in _UNDECLARED_KINDS:\n",
     _T + "test_later_stops_say_it_in_one_line[sh]"),
    ("L-0733 b: the ps1 matcher names every undeclared rule on every Stop", PS1,
     "    if ($stopMode -and ($undeclaredKinds -contains $stopExcluded[$ri].kind)) {\n",
     "    if ($false -and $stopMode -and ($undeclaredKinds -contains $stopExcluded[$ri].kind)) {\n",
     _T + "test_later_stops_say_it_in_one_line[ps1]"),
    ("L-0733 c: the record prints a line per undeclared entry again", RECORD,
     '    return isinstance(info, dict) and info.get("status") in UNDECLARED_REACH_KINDS\n',
     "    return False\n",
     _T + "test_later_stops_say_it_in_one_line[sh]"),
    ("L-0733 d: the full notice is shown on every Stop, not once per map", RECORD,
     "                if fh.read(128).strip() == digest:\n",
     "                if fh.read(128).strip() == digest and False:\n",
     _T + "test_later_stops_say_it_in_one_line[sh]"),
    ("L-0733 e: an edited undeclared rule holds the marker again", RECORD,
     "                if not _undeclared(info):\n                    orphaned += 1\n",
     "                orphaned += 1\n",
     _T + "test_an_edited_undeclared_rule_does_not_pin_the_marker[sh]"),
    ("L-0733 f: a blocking orphan names only /crew:verify --all", RECORD,
     '              f"{os.path.abspath(__file__)} forget-orphans (from the repo root)")\n',
     '              f"{os.path.abspath(__file__)} (from the repo root)")\n',
     _T + "test_a_blocking_orphan_names_forget_orphans[sh]"),
)
