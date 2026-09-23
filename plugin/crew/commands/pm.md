---
description: Talk to the crew's manager - status, assign work, set its authority, onboarding, offboarding
argument-hint: "[assign | authority [report-only|act|autonomous] | onboard <role> | offboard <role>]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, SendMessage, AskUserQuestion
---

Talk to the crew's manager. Arguments: $ARGUMENTS

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py` first, in every
path below. This command reads crew state; it never re-derives it by hand.

Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/SKILL.md` before anything else — it
owns the field meanings and the authority rule this command must not loosen.

## The PM is always spawned unnamed. Resume by id when you can.

The `crew:pm` subagent is dispatched with **no `name`**, always. A `name`
makes a spawned agent an addressable teammate, and per
[agent teams](https://code.claude.com/docs/en/agent-teams.md) "teammates
cannot spawn their own teammates — only the lead can manage the team." The
PM's whole job is dispatching roles, so naming it is what disables it: a
named PM's own `Agent` calls fail with "Teammates cannot spawn other
teammates," and the crew stops mid-turn. Never `ListAgents` for a teammate
named `crew-pm` and never `SendMessage` to that name — there is no such
teammate to find.

Continuity ("same manager each time") now comes from two mechanisms instead:

1. **Resume by id, in this session.** After a PM spawn returns, record the
   agent id it was given. On a later `/crew:pm` invocation in the *same*
   session, `SendMessage` to that id (never a name) to resume the same plain
   subagent with its whole transcript — resuming a plain subagent by id is
   itself per the docs above, and the resume call must not pass `name`
   either. If no id is held, or the resume errors, do not retry it: spawn a
   fresh unnamed `crew:pm` and say so in one line.
2. **The PM journal and standing file, across sessions.** `.crew/pm-journal.md`
   is the dated record — what was dispatched, decided, deferred, and what's
   next — read as a bounded tail. `.crew/pm-standing.md` is the durable one:
   one line per still-live decision, veto, or onboard/offboard ruling, read in
   full every time so it can never fall out of view. The PM reads both and
   appends a journal entry every turn, plus a standing line whenever the turn
   produced a durable outcome; a fresh PM (this session, or a new one) picks
   the picture back up from there rather than from a transcript that no
   longer exists.

Never run two PM subagents concurrently in the same session. If you are
unsure whether the held id is still resumable, attempt the resume once; on
error, spawn fresh rather than guessing.

## A `**Decision needed:**` block is yours to render, not to relay

The PM cannot ask — `AskUserQuestion` is not in its tool list, on purpose. So it
ends a report that needs a decision with a `**Decision needed:**` block: the
question, two to four options with its recommendation first, and the research
behind it. **You render that with `AskUserQuestion`.**

- One `AskUserQuestion` call per decision; several decisions can be several
  questions in the same call.
- Keep the PM's recommendation as the first option and keep its `(Recommended)`
  marker. Reordering it hides the crew's own judgement, which is most of what
  the block is for.
- Carry each option's stated cost into its `description`. An option list with
  no downsides reads as a formality.
- **Do not add an "Other" option.** `AskUserQuestion` already offers free text;
  a hand-written one makes two.

Pasting the block through as prose is the failure here. The user then has to
type an answer to a question that was built to be picked, which is the whole
thing this is meant to avoid. If a report has a decision block, you ask it — you
do not summarise it and you do not answer it on their behalf.

**The answer is yours to journal too.** The block's answer arrives after the
PM's turn already ended, so nothing guarantees a later PM spawn ever learns
what was picked — resume-by-id may fail, or the next spawn may be fresh. When
`isCrew: true`, append the outcome yourself, the same way as onboard/offboard
below: `Write` a journal entry naming which option was chosen and the
one-line reason if you have it to `.work/pm-entry.md`, then `python3
${CLAUDE_PLUGIN_ROOT}/hooks/scripts/pm_journal.py --root . --append journal
--from .work/pm-entry.md` — plus, if the decision is durable (a veto, a
ruling that should hold), the same for `--append standing`.

## Relay what it did, never what it said it would do

The PM can fail by describing a dispatch instead of making it — a plan with
roles and an order, ending without a single Agent call. Passing that upward as
progress is how work that never started gets reported as running.

Before you relay a PM report under `act`, check it names results, not
intentions. Findings that came back, roles that returned, a diff that exists.
If the report is written in the future tense — "I'll send", "next is", "the plan
is to" — it did not dispatch. Send it back once, saying so plainly, rather than
relaying it. If the second attempt is also narration, tell me that instead of
trying a third time; something is wrong with the run and more retries will not
find it.

**A role's partial result carries an id — resume it yourself, don't send it
back to the PM.** The PM cannot reach a dispatched role again: it has no
`SendMessage` in its own tool list, and its own dispatch rule already forbids
treating a role as addressable from inside the PM for exactly that reason —
that address belongs to you, the caller, not to it. If a PM report says a role
returned a PARTIAL result and names that role's id, `SendMessage` that id
directly rather than routing it back through the PM to redo: the role resumes
with everything it already worked out, where a re-dispatch would open an
empty context and pay for that work twice.

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
context than the answer is worth spending here — put the question to `crew:pm`
instead of doing it in this session, resuming by id where you hold one. It
returns a report under 200 words plus a recommendation, and — resumed or via
the journal — it keeps the working it did, so the follow-up question costs a
message rather than another full analysis.

**`assign`.**
Reach the PM as described above — resume by id if you hold one, otherwise
spawn it fresh and unnamed — and let it act: it reads state, decides what the
crew should do next, and dispatches the roles that do it. Pass along anything
the user has said about priorities in this session — that ordering outranks the
trigger order, and the PM cannot see the conversation you are in.

Typing `assign` **is** the explicit instruction, so it acts even where
`pm.authority` is `report-only`. Say so in one line when that applies ("acting
this once; config still says report-only"), so a user who wanted it permanent
knows there is a setting, and a user who did not is not surprised twice.

**`authority [report-only|act|autonomous]`.**
With no value, report the current setting and what it means in one line each.

With a value, set `pm.authority` in `.crew/config.json` and confirm. This is
the one config write this command makes without a yes/no prompt — it is the
user typing the setting they want, not the PM deciding to widen its own
permissions, and refusing to honour a direct instruction would be its own kind
of wrong. Reject anything that is not one of the three values rather than writing
it: a config carrying `"acr"` silently behaves as `report-only` forever - an
unknown collapses to the LEAST permissive tier, never the most, and
`autonomous` is now one typo away from `act`.

Say what changes. Moving to `act` means the PM will dispatch agents on its own
from the next session-start brief and the next state-change pulse; moving to
`autonomous` additionally means it stops asking you to choose - where it would
emit a `**Decision needed:**` block it takes the option it would have
recommended and tells you which; moving to `report-only` means it stops and
waits. Name the direction, not just the value: widening is the change a user
cannot recover from by noticing, and narrowing must never be announced as a
widening or the warning becomes noise.

The stops hold at every tier, `autonomous` included, and they are enumerated in
`crew_state.AUTONOMOUS_STOPS` rather than here - offboarding a role, deleting a
codemap or diagram, rewriting `.crew/metrics.md`, and destroying git history or
tracked work. Read them from that tuple rather than restating them, so a stop
added there cannot be missing here.

Its dispatch table lives in `agents/pm.md`; do not restate a shorter version
here. Two rules from it that this command must not loosen: inputs before
outputs (`graphStale` and `knowledgeBehind` are fixed before anything that
derives from them), and removal or deletion still stops for an explicit yes.

Report what it did when it returns. If it dispatched nothing because nothing
was outstanding, say that in one sentence — do not go looking for work it
decided against. The PM reports after each returned dispatch, not only at the
end; if a status request goes unanswered for one full dispatch cycle, say so
to the user rather than waiting.

**`onboard <role>`.**
Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-pm/onboarding.md`'s "Onboarding a role"
section — do not improvise a shorter version. Name the specific defect class
the role closes, confirm `.crew/metrics.md` supports it, then stop and ask me
yes/no. Only on yes: add the role to `.crew/config.json` -> `roles` and
recompute `tier` from `crew-scaling`'s tier table.

This decision is yours, the caller's, not the PM's — it never reaches the PM
to journal on its own. So when `isCrew: true`, append the outcome yourself,
using the mechanism in `agents/pm.md`'s append-mechanism rule ("Reporting";
`Write` the entry to `.work/pm-entry.md`, then `pm_journal.py --append`;
never `Write`/`Edit` against `.crew/pm-standing.md` or `.crew/pm-journal.md`
directly, never a heredoc, `printf`, or `echo`): a standing line,
`onboarded <role> — <defect class>`, or `vetoed onboarding <role> —
<reason>` if I said no — this is a durable ruling, so it gets a standing
line. It also gets a one-line journal entry, the same as every turn does;
standing is in addition to the journal entry, never a replacement for it.

**Domain specialists take the same command and a different justification.**
The specialists are real roles with real agent definitions and no tier — no
amount of scaling ever grants one, because "this repo does SharePoint" is a
fact about a checkout rather than a defect class every repo can have.
`crew_state.SPECIALIST_ROLES` is the list, and onboarding.md's specialist table
is the readable copy of it; do not enumerate them here, because a list in two
places drifts and this one is not the one a test checks. For these, the
evidence is the repo's own stack rather than `.crew/metrics.md`: name the file
that proves it — the agent's own file says which one it expects — and say so
before asking. On yes, add it to `roles` and **leave `tier` alone** — there is no rung
to recompute, and a tier that moved would tell `/crew:scale` the crew had grown
when it has only specialised. See onboarding.md's "Domain specialists are
justified by the stack, not by metrics".

A role name crew does not ship at all is still not an error — a repo may
onboard one and write its own `agents/<role>.md` — but say plainly that no
agent definition backs it yet, because a name in `roles` with no file behind it
dispatches nothing and fails silently.

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

Same standing-file rule as onboarding: this is your decision to record, not
the PM's. When `isCrew: true`, append the outcome yourself, using the
mechanism in `agents/pm.md`'s append-mechanism rule ("Reporting"): a
standing line, `offboarded <role> — <failure mode left uncovered>`, or
`vetoed offboarding <role> — <reason>` if I said no — plus a one-line
journal entry, the same as every turn does; standing is in addition to the
journal entry, never a replacement for it.

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
