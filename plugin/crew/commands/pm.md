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
Check the role is actually on the crew before doing anything else: read
`roles` from `crew_state.py`'s output and confirm the named role is in it. If
it is not, say so and stop — do not open `offboarding.md` for a role that was
never active. Running the procedure anyway would append a real `offboarded
<role>` line to `.crew/metrics.md` for coverage that never existed, and
`metrics.md` is what `/crew:scale` reads to decide whether the crew is
catching anything.

If it is on the crew, read
`${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/offboarding.md` and follow it exactly —
this is new capability with no shorter version to fall back to. Stop and ask
me yes/no before touching `.crew/config.json` or deleting anything. The
procedure ends with naming, out loud, the failure mode this removal leaves
uncovered — that sentence is the actual point, not optional polish.

**Anything else.**
An argument that is not empty, `onboard <role>`, or `offboard <role>` is
unrecognised. Do not fall through to the status form and do not stay silent
either — list the three supported forms and stop. A command that does
nothing on a typo is indistinguishable from one that did the work.

Never change a role or `tier` without my explicit yes, no matter how obvious
the recommendation looks.
