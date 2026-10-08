# Cross-session messaging: the main session is the hub, lanes never ring a peer          status: spec   risk: med
Split from T-0032 (L-0637), 2026-10-04. Filed as L-0637.
## Intent
`crew_bridge.py ring` refuses with exit 1 and `refused - a lane does not message a peer; report the question to the main session` when it runs in a wave lane, using the lane marker T-0029 defines. When the marker cannot be read, it refuses as `unknown` (exit 3). `receive` is not restricted. The prompt validator fails if any file under `plugin/crew/agents/` grants `SendMessage` or `ListAgents`, or if the wave's lane prompt names either tool. The lane prompt gains one sentence: a question for another session is returned in the lane's report for the main session to file and ring.
## Exclusions
- No hook, and no change to `plugin/crew/hooks/hooks.json`.
- No change to `scope_guard.py`, `crew_ticket.py` or any other `HARNESS` path. No `sabotage*.py` file (L-0638).
- No restriction on the main session, and none on `receive` or `pending`.
- The tool-name allowlist in `validate-prompts.py` keeps both names (they are real tools); only granting them to an agent is refused.
## Evidence
Checked at origin/main 155fe6d8 unless a branch is named.
- `plugin/crew/hooks/scripts/_test/validate-prompts.py:106-112`: `KNOWN_TOOLS` lists `ListAgents` and `SendMessage` as valid names to grant.
- No file under `plugin/crew/agents/` grants either today (`git grep -n -E "SendMessage|ListAgents" origin/main -- plugin/crew/agents` is empty).
- The wave (`/crew:autopilot wave`, lane-init, lane-prompt) is T-0029, in-progress and not on origin/main: `plugin/crew/commands/autopilot.md:3` lists only `status|run|assign|goal|focus`. The lane marker and the lane-prompt file do not exist on main.
- `plugin/crew/hooks/scripts/crew_autopilot.py:745` already distinguishes "a lane worktree" for config reads (T-0088), through `crew_common.repo_config_file`. That is a linked-worktree test, not a wave-lane test: an owner may run a main session in a linked worktree, so it is not enough alone.
- T-0032's `crew_bridge.py` does not exist on origin/main.
## Unknowns
- **T-0029's lane marker.** Its name and location are whatever T-0029 lands. If T-0029 lands no readable marker, stop and return to the owner; do not fall back to "linked worktree means lane".
- **The lane-prompt file's path.** Named by T-0029. It is listed in Touch as `plugin/crew/commands/autopilot.md`; if T-0029 puts the lane prompt in another file, amend Touch before editing it.
- **A lane can still call `SendMessage` directly** if the harness offers the tool to it regardless of the prompt. This ticket does not prevent that; the README says so.
## Touch
- `plugin/crew/hooks/scripts/crew_bridge.py`
- `plugin/crew/hooks/scripts/_test/validate-prompts.py`
- `plugin/crew/hooks/scripts/crew_wave.py` - amended at plan (2026-10-05): T-0029 landed the lane prompt here (`lane_prompt`), not in `autopilot.md`
- `plugin/crew/tests/test_crew_bridge_hub.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `.crew/codemap/crew.md`
- `CHANGELOG.md`
## Acceptance checks
Tests in `plugin/crew/tests/test_crew_bridge_hub.py`: `python3 -m pytest plugin/crew/tests/test_crew_bridge_hub.py -q`.
- [ ] Must-block: `ring` in a fixture lane exits 1 with the refusal line and prints no doorbell; `ring` where the lane marker is unreadable or corrupt exits 3 with `unknown` (two tests).
- [ ] Must-allow: `ring` in a main checkout, and in a linked worktree that is not a wave lane, works as in T-0032. `receive` works in a lane (three tests).
- [ ] `python3 plugin/crew/hooks/scripts/_test/validate-prompts.py` fails on a fixture agent file whose `tools:` grants `SendMessage` or `ListAgents`, and passes on the repo as it is (tests run the validator on a throwaway copy).
- [ ] The lane prompt text states that a question for another session is returned to the main session, and names neither tool (test on the text).
- [ ] README states the hub rule and its limit. `.crew/verify.json` maps the new test file. Crew is bumped one patch above origin/main with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit and `python3 scripts/check-tooling-pr.py` exits 0.
## Dependencies
Must land first: T-0029 (in-progress; the lane marker and lane prompt), T-0030 (in-progress), T-0032 (ready; `crew_bridge.py`). Independent of L-0636, but both edit `crew_bridge.py` and `autopilot.md`, so land L-0636 first to avoid a conflict. Blocks: L-0638.
## Size
About 60 added production lines (`crew_bridge.py` about 35, the validator about 25). One guard. No harness path.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
