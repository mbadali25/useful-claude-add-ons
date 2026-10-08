# L-0642 plan: the open-questions stop sees through code fences, and stops when it cannot tell

Written by the implementing session (rush g6a, 2026-10-05) on `rush/g6a-autopilot`, after T-0043.
Main's parser at `155fe6d8` is byte-identical to the one on this branch (`_BULLET` through
`return items`), so the floor copy is unambiguous.

One deviation from the spec's layout, for the coordinator's line budget: `crew_autopilot.py` sits
at pylint's 3,400-line cap, so the fence view lives in a new module,
`plugin/crew/hooks/scripts/crew_autopilot_fences.py` (`fence_view`, `names_open_questions`,
`open_items`). `crew_autopilot.py` keeps main's parser byte-for-byte as `_legacy_open_items`
(its two sabotage anchors stay unique) and `_open_items` becomes a thin call. The fence view is
main's parser run over the text with each tracked fence blanked, so a mutation of the legacy
parser still moves both halves.

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot.py`, `plugin/crew/tests/test_crew_autopilot_fences.py`
- `next`-level: the original finding (backticks and tildes), both round-2 repros.
- Parser-level: the seven could-not-tell cases, must-allow clean fences, no section means no
  stop, the unexplained-fence item, the floor corpus against a verbatim copy of main's parser.

### Step 2: the fence view
Files: `plugin/crew/hooks/scripts/crew_autopilot_fences.py`, `plugin/crew/hooks/scripts/crew_autopilot.py`

### Step 3: docs and verify
Files: `plugin/crew/README.md`, `.crew/verify.json`, `CHANGELOG.md`
- README's open-questions row states the floor, the column-0 rule and the could-not-tell stop.
- The autopilot verify rule gains the new module and test file, with re-measured seconds.
- Hand sabotage in a `git archive` scratch copy (seven mutations); the cost over the ticket files
  this clone holds.
