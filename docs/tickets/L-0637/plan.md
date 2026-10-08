# L-0637 plan            spec: docs/tickets/L-0637/spec.md

Written by the implementing session (rush g3d-bridge, 2026-10-05), on T-0029's ported
`crew_wave.py`, T-0030's `crew_coord.py`, and `crew_bridge.py` after T-0032 (#434) and L-0636 (#437).
Crew version: the group's placeholder, set in the group's last commit.

T-0029's lane marker, as landed: the lane file `.work/autopilot/<slug>/lanes/<id>.json` in the MAIN
checkout (`crew_wave.lane_path`, read with `crew_wave.read_lane`), whose `worktree` key `lane-init`
writes with the lane worktree's real path once it has checked the worktree is an isolated one under
`<main>/.claude/worktrees/`. That is a readable marker, so the spec's stop condition does not apply,
and the check is never "a linked worktree is a lane". The main checkout is the first entry of
`crew_wave.worktrees` (`git worktree list --porcelain`).

The lane prompt is `crew_wave.lane_prompt` in `plugin/crew/hooks/scripts/crew_wave.py`, not
`autopilot.md`; per the HANDOFF, Touch is amended (spec.md) to add `crew_wave.py` (not a HARNESS or
SEAM path). The prompt validator (`_test/validate-prompts.py`, not a HARNESS path either) therefore
reads the lane prompt's source file for the two tool names.

### Step 1: the hub refusal
Files: plugin/crew/hooks/scripts/crew_bridge.py, plugin/crew/tests/test_crew_bridge_hub.py
Test: python3 -m pytest plugin/crew/tests/test_crew_bridge_hub.py -q
Risk: med
- [ ] `lane_state(top)`: `main` (this is the main checkout), `lane` (a lane file names this
      worktree), `not-lane`, or `unknown` with a reason (worktrees cannot be listed, the autopilot
      directory or a set's lanes cannot be listed, a lane file is missing its JSON or corrupt)
- [ ] `ring` (with or without `--to`) checks it before any fetch or write: `lane` exit 1 with
      `refused - a lane does not message a peer; report the question to the main session`,
      `unknown` exit 3; `receive` and `pending` are not restricted
- [ ] tests: a fixture lane (real `crew_wave.start` + `lane_init`) refuses; a corrupt lane file is
      unknown; the main checkout and a non-lane linked worktree ring; `receive` works in a lane

### Step 2: the validator, the lane prompt, docs
Files: plugin/crew/hooks/scripts/_test/validate-prompts.py, plugin/crew/hooks/scripts/crew_wave.py,
plugin/crew/commands/autopilot.md, plugin/crew/README.md, .crew/verify.json, .crew/codemap/crew.md,
CHANGELOG.md, plugin/crew/BUDGETS.md
Test: python3 -m pytest plugin/crew/tests/test_crew_bridge_hub.py plugin/crew/tests/test_crew_wave.py plugin/crew/tests/test_verify_before_stating.py -q; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
- [ ] validator: an agent whose `tools:` grants `SendMessage` or `ListAgents` fails, and so does a
      lane prompt source naming either; `KNOWN_TOOLS` keeps both names
- [ ] lane prompt: one sentence, a question for another session goes back in the lane's report
      for the main session to file and ring; names neither tool
- [ ] autopilot.md section 8 states the hub rule, in place (120-line budget); README states the
      rule and its limit (a lane offered `SendMessage` by the harness can still call it)
