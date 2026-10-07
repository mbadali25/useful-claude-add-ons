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
5. By hand, once (2026-10-07, graphify 0.9.79, in a throwaway clone of the branch so this
   repo's `graphify-out/` is untouched): `status` printed `graph=stale ... pair=agree
   ignore=covered command=graphify update .`; `refresh` exited 0 with `pair=agree` (31633 nodes /
   75277 links on both sides) and listed the two changed files; `status` then read `graph=fresh`.
   No sabotage entry is needed for `runs`: the existing mutation's test now asserts `runs`.
