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
Then the owner's 2026-10-08 additions: an edited rule's orphan kept instead of
superseded (g-j), an exit 2 with empty stdout (k-n), and owed lines that do not
name the record file (o).
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
    ("L-0733 g: an edited rule's orphan is kept, not superseded", RECORD,
     "            replaced_by = _replacements(info, current)\n",
     "            replaced_by = []\n",
     _T + "test_an_edited_rule_supersedes_its_orphan[sh]"),
    ("L-0733 h: a superseded chronic orphan holds the marker again", RECORD,
     "            replaced_by = _replacements(info, current)\n",
     "            replaced_by = [] if info.get('status') == 'chronic' else _replacements(info, current)\n",
     _T + "test_a_superseded_chronic_orphan_frees_the_marker[sh]"),
    ("L-0733 i: a peer on the same paths counts as the replacement", RECORD,
     "                  if current[k][1] == pk and k not in peers)\n",
     "                  if current[k][1] == pk)\n",
     _T + "test_a_removed_rule_beside_a_peer_is_not_superseded"),
    ("L-0733 j: a pre-L-0733 entry is superseded by any rule", RECORD,
     "    if not isinstance(pk, str) or not isinstance(peers, list):\n        return []\n",
     "    if not isinstance(pk, str) or not isinstance(peers, list):\n"
     "        return sorted((v[0], k) for k, v in current.items())\n",
     _T + "test_a_pre_l0733_orphan_is_kept"),
    ("L-0733 k: sh exits 2 with empty stdout (Claude Code downgrades it)", SH,
     '  echo "VERIFY GATE: BLOCKED (exit 2) - this Stop did not pass;',
     '  echo >&2 "VERIFY GATE: BLOCKED (exit 2) - this Stop did not pass;',
     _T + "test_a_no_such_file_failure_blocks_with_stdout[sh]"),
    ("L-0733 l: the gate's cleanup trap drops the stdout line (sh)", SH,
     "_crew_gate_run_cleanup; _crew_gate_exit_line \"$_crew_gate_exit_rc\"' EXIT\n",
     "_crew_gate_run_cleanup' EXIT\n",
     _T + "test_a_no_such_file_failure_blocks_with_stdout[sh]"),
    ("L-0733 m: an exit 2 before the cleanup trap leaves stdout empty (sh)", SH,
     "trap '_crew_gate_exit_line $?' EXIT\n",
     "trap '' EXIT\n",
     _T + "test_a_usage_error_writes_stdout_too[sh]"),
    ("L-0733 n: ps1 exits 2 with empty stdout (Claude Code downgrades it)", PS1,
     '  [Console]::Out.WriteLine("VERIFY GATE: BLOCKED (exit 2)',
     '  [Console]::Error.WriteLine("VERIFY GATE: BLOCKED (exit 2)',
     _T + "test_a_no_such_file_failure_blocks_with_stdout[ps1]"),
    ("L-0733 o: the owed lines do not say which record", RECORD,
     '    where = f" [record: {_record_abs()}]"\n',
     '    where = ""\n',
     _T + "test_owed_lines_name_the_absolute_record[sh]"),
)
