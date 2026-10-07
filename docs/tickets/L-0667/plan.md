# L-0667 plan - /crew:graph

Written by the implementing session (rush g3d, release/1.2.0 line, after T-0064 landed there).

1. `crew_refresh_check.py`: move the command choice into `graph_command(info)`, the anchored
   `    command = ("graphify update ." if info["reportTracked"]` line byte-identical and once;
   `_graph` wraps `_graph_entry` and sets `command` to `/crew:graph --refresh` and `runs` to the
   graphify line. Unknown resolved: no script executes the artifact's `command` as a shell line
   (`crew_autopilot._refresh_state` hands it to the session as a phase command; `implement.md`
   step 6 says to run the command named), so nothing else reads `runs`.
2. `crew_graph.py` (`status`, `refresh`), test-first in `test_crew_graph.py` with a stand-in
   graphify run; one POSIX case runs a fake graphify from PATH through `crew_shell.run`.
   `_read_graph` reads a failed `ls-files` as an untracked report, so the script asks git again
   and reads a failure as `pair=unknown`.
3. `commands/graph.md`; the count 36 -> 37 in every place the spec lists (both install scripts,
   same text, same place); README command table and refresh-check row, PLUGINS.md, the skill's
   Refresh section, autopilot.md's refresh list, the guide's refresh paragraph (rebuilt).
4. verify.json rule appended last; code map; CHANGELOG; BUDGETS.md re-measured; rules regenerated.
5. Not done here: the by-hand `/crew:graph --refresh` on this repo (graphify is not installed in
   this container); the sabotage entry for `runs` (none needed: the existing mutation's test now
   asserts `runs`).
