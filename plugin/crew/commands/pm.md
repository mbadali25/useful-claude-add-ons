---
description: Talk to the crew's manager - status, assign work, set its authority, onboarding, offboarding
argument-hint: [assign | authority [report-only|act] | onboard <role> | offboard <role>]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Talk to the crew's manager. Arguments: $ARGUMENTS

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py` first, in every
path below. This command reads crew state; it never re-derives it by hand.

Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/SKILL.md` before anything else — it
owns the field meanings and the authority rule this command must not loosen.

**No arguments — status.**
Report `triggers` first (already prioritized by the hook), then `health.rate`,
`work.ticket` / `work.handoffPending`, `knowledge.subsystems` / `knowledge.behind`,
`knowledge.graph.present` / `knowledge.graph.current`, `diagrams.total` /
`diagrams.behind` / `diagrams.missing`, and `roles` / `tier`.
`isCrew: false` means every other field is a default, not a finding — say that
instead of reporting zeros as facts.

Status reports. It does not dispatch — that is `assign`. A user who typed
`/crew:pm` to see where things stand has not asked for three agents to start
running.

If answering well means correlating the whole metrics history, auditing every
codemap anchor, or building the full evidence chain for a tier change — more
context than the answer is worth spending here — delegate to the `crew:pm`
subagent instead of doing it in this session. It returns a report under 200
words plus a recommendation.

**`assign`.**
Hand the whole picture to the `crew:pm` subagent and let it act: it reads
state, decides what the crew should do next, and dispatches the roles that do
it. Pass along anything the user has said about priorities in this session —
that ordering outranks the trigger order, and the subagent cannot see the
conversation you are in.

Typing `assign` **is** the explicit instruction, so it acts even where
`pm.authority` is `report-only`. Say so in one line when that applies ("acting
this once; config still says report-only"), so a user who wanted it permanent
knows there is a setting, and a user who did not is not surprised twice.

**`authority [report-only|act]`.**
With no value, report the current setting and what it means in one line each.

With a value, set `pm.authority` in `.crew/config.json` and confirm. This is
the one config write this command makes without a yes/no prompt — it is the
user typing the setting they want, not the PM deciding to widen its own
permissions, and refusing to honour a direct instruction would be its own kind
of wrong. Reject anything that is not one of the two values rather than writing
it: a config carrying `"acr"` silently behaves as `report-only` forever.

Say what changes. Moving to `act` means the PM will dispatch agents on its own
from the next session-start brief and the next state-change pulse; moving to
`report-only` means it stops and waits. Neither is reversible by accident, but
both should be visible.

Its dispatch table lives in `agents/pm.md`; do not restate a shorter version
here. Two rules from it that this command must not loosen: inputs before
outputs (`graphStale` and `knowledgeBehind` are fixed before anything that
derives from them), and removal or deletion still stops for an explicit yes.

Report what it did when it returns. If it dispatched nothing because nothing
was outstanding, say that in one sentence — do not go looking for work it
decided against.

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
An argument that is not empty, `assign`, `authority [value]`, `onboard
<role>`, or `offboard <role>` is unrecognised. Do not fall through to the
status form and do not stay silent either — list the five supported forms and
stop. A command that does nothing on a typo is indistinguishable from one that
did the work.

Never offboard a role, delete a codemap or a diagram, or rewrite
`.crew/metrics.md` without my explicit yes, no matter how obvious the
recommendation looks. Dispatching work and refreshing diagrams need no such
yes — but if I have said what I want prioritised, that ordering wins.
