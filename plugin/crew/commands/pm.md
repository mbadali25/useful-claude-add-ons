---
description: Talk to the crew's manager - status, onboarding, offboarding
allowed-tools: Read, Write, Edit, Bash, Agent
---

Talk to the crew's manager. Arguments: $ARGUMENTS

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py` first, in every
path below. This command reads crew state; it never re-derives it by hand.

Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/SKILL.md` before anything else — it
owns the field meanings and the authority rule this command must not loosen.

**No arguments — status.**
Report `triggers` first (already prioritized by the hook), then `health.rate`,
`work.ticket` / `work.handoffPending`, `knowledge.subsystems` / `knowledge.behind`,
`knowledge.graph.present` / `knowledge.graph.current`, and `roles` / `tier`.
`isCrew: false` means every other field is a default, not a finding — say that
instead of reporting zeros as facts.

If answering well means correlating the whole metrics history, auditing every
codemap anchor, or building the full evidence chain for a tier change — more
context than the answer is worth spending here — delegate to the `crew:pm`
subagent instead of doing it in this session. It returns a report under 200
words plus a recommendation.

**`onboard <role>`.**
Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/onboarding.md`'s "Onboarding a role"
section — do not improvise a shorter version. Name the specific defect class
the role closes, confirm `.crew/metrics.md` supports it, then stop and ask me
yes/no. Only on yes: add the role to `.crew/config.json` -> `roles` and
recompute `tier` from `crew-scaling`'s tier table.

**`offboard <role>`.**
Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/offboarding.md` and follow it
exactly — this is new capability with no shorter version to fall back to. Stop
and ask me yes/no before touching `.crew/config.json` or deleting anything.
The procedure ends with naming, out loud, the failure mode this removal
leaves uncovered — that sentence is the actual point, not optional polish.

Never change a role or `tier` without my explicit yes, no matter how obvious
the recommendation looks.
