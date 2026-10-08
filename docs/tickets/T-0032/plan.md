# T-0032 plan            spec: docs/tickets/T-0032/spec.md

Written by the implementing session (rush g3d-bridge, 2026-10-05) on a base that carries T-0030
(`crew_coord.py`, ported in rush g0) and release/1.2.0. Crew version: the group's placeholder, set in
the group's last commit.

Anchors re-checked on this base: `crew_coord.Channel.fetch` still returns `(tip, state, why)` with
state `ok`, `absent` or `failed` and touches no ref (`ls-remote`, then `fetch --no-write-fetch-head
--refmap=`); `safe`, `peer`, `PEER`, `run_git`, `UsageError` and `EXIT_OK/REFUSED/USAGE/UNKNOWN`
(0/1/2/3) keep their names. The channel rule is `crew_coord._CHANNEL_RE` (private), so
`crew_bridge.py` states the same pattern and a test pins the two equal; nothing in `crew_coord.py`
changes.

### Step 1: the doorbell grammar and `ring` / `receive`
Files: plugin/crew/hooks/scripts/crew_bridge.py, plugin/crew/tests/test_crew_bridge.py
Test: python3 -m pytest plugin/crew/tests/test_crew_bridge.py -q
Risk: high - the classifier is the line between data and instruction
- [ ] `compose` builds `crew-doorbell/1 channel=<c> tip=<hex> kind=<k> ref=<r>`; a line over 200
      characters (a long channel and ref with a 64-hex tip) is a usage error, exit 2
- [ ] `parse` reads at most 4096 bytes, strict UTF-8, strips one trailing `\n`, and full-matches
      the whole input; anything else is `not a doorbell` with its reason
- [ ] `ring`: kind/ref checked first (exit 2), fetch failed -> `unknown - could not fetch` exit 3,
      absent -> refused exit 1, else the one line
- [ ] `receive`: not a doorbell (exit 1, message printed only through `safe` + `[peer-written]`)
      before any fetch; a channel other than `--channel` is not a doorbell; fetch failed, absent,
      announced tip not in the object store, or not an ancestor of the fetched tip -> `could not
      tell` exit 3; else exit 0. Every outcome ends with the one fixed `next: crew_coord.py status`
      line
- [ ] CLAUDE_CODE_MESSAGING_TOKEN popped from the environment before anything runs
- [ ] tests: one per acceptance bullet (grammar, must-block for both commands, isolation, secret)

### Step 2: the command text, docs, verify rule
Files: plugin/crew/commands/autopilot.md, plugin/crew/README.md, docs/guides/crew/src/troubleshooting.md
(+ rebuilt HTML/DOCX/PDF), .crew/verify.json, .crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: python3 -m pytest plugin/crew/tests/test_crew_bridge.py -q -k command; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
Risk: med
- [ ] `autopilot.md` section 8 "Cross-session messages"; `allowed-tools` adds `SendMessage, ListAgents`;
      stays at or under 120 lines
- [ ] README subsection after "Cross-session claims"; troubleshooting entry; guide rebuilt
- [ ] verify rule through `pytest_rule.py`

Note on the Touch list: the spec names `docs/guides/crew/crew-1.0-troubleshooting.*`; on this base
the built guide is `docs/guides/crew/crew-troubleshooting.{html,docx,pdf}` (renamed since the spec
was written), so those are the files rebuilt.
