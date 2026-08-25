---
description: Declare an incident - stand the gates down, spin up parallel investigation lanes, and record what was skipped
argument-hint: "<what is broken> | status | extend [minutes] | end"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

An emergency lane is a **time-boxed, written-down** decision to stop gating so
the environment can be fixed, plus parallel lanes investigating it at once.

It is not a way to skip verification because verification is annoying. Every
gate that does not run is recorded, the lane expires on its own, and
`end` prints the bill.

## Which of these you were asked for

`$ARGUMENTS` decides. Do not run more than one.

| Argument | Do this |
|---|---|
| empty or `status` | **Status**, below. Never declare an incident from an empty argument — an incident nobody meant to declare is worse than none. |
| `end` / `close` / `resolve` | **Closing**, below. |
| `extend` / `extend 45` | Run `python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_incident.py" extend --ttl <minutes>` (omit `--ttl` for the configured default) and print the line it returns. |
| anything else | **Declaring**, below, with the argument as the summary. |

Every python call below is `python3`, `python` or `py` — whichever resolves.
The module is standard library only.

## Declaring

1. **Say what will and will not stand down, before doing it.** In one short
   block, so the human can stop you:
   - **Standing down:** the `verify` Stop gate (the changed-files checks do not
     run at all) and the `promote` PreToolUse gate (its preconditions are
     computed and recorded, not enforced).
   - **NOT standing down:** the command guard. Force pushes, `terraform
     destroy`, history rewrites, secret reads and production-CLI arguments are
     still blocked. An incident is when someone is tired enough to need that,
     and the guard stops mistakes that cannot be undone rather than mistakes
     that can be reviewed later.
2. Declare it:
   `python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_incident.py" declare --summary "<one line on what is actually broken>"`
   Add `--ttl <minutes>` only if the human named a window. The default is
   `emergency.ttlMinutes` (120), capped by `emergency.maxTtlMinutes` (480).
3. **Open the lanes.** Dispatch these in ONE message so they run at once. Each
   gets the symptom, the time it started, and what has already been ruled out —
   nothing else. A lane that has to ask what is broken is a lane that was
   briefed badly.

   | Lane | Agent | Question it answers |
   |---|---|---|
   | change | `crew:explorer` | What shipped or changed in the window before the symptom? Commits, deploys, config, feature flags, migrations, dependency bumps. |
   | blast radius | `crew:explorer` | What calls the failing path, and what else uses the same resource? Who else is already broken and does not know it yet. |
   | cause | `crew:analyst` | Given the symptom and the change list, the two or three most probable causes, each with the one cheap observation that would confirm or kill it. |
   | exposure | `crew:security` | Only when the symptom could be an incident of a different kind: auth, data exposure, injection, an unexpected 200. Skip it for a plain outage and say you skipped it. |
   | data | `crew:dba` | Only when a database is in the picture: locks, a long transaction, a migration mid-flight, replica lag, a table that grew. |

   Lanes are **read-only investigators**. They do not fix anything. If two
   plausible fixes need trying at once, that is a separate call with
   `isolation: worktree` per fix, so a half-applied fix cannot land on top of
   another one in the same tree.
4. While the lanes run, **do the cheapest observation yourself** — the log line,
   the health endpoint, the last deploy's sha. Do not wait idle on agents.
5. When the lanes report: one paragraph on the most probable cause, the
   observation that would settle it, and the smallest change that would restore
   service. Ask before applying anything that is not obviously reversible.

## Status

`python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_incident.py" status`

Print its line as-is, then, if an incident is open, read
`.crew/incident-skips.log` and say how many distinct gates are owed. The
session brief prints the same summary at every session start, so do not
paraphrase it differently here.

## Closing

Close as soon as the environment is stable — not when the follow-up work is
done, which is what the debt list is for.

1. `python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_incident.py" end`
   It writes `.work/INCIDENT-<id>.md`, archives the record under
   `.crew/incidents/`, and deletes the state file, which is what puts the gates
   back.
2. **Pay what can be paid now.** Run the checks that did not run — `/crew:verify`
   knows which ones the changed files need — and record the result. If a deploy
   went out ungated, add its row to `.work/PROMOTIONS.md` with the real result
   of each gate, failures included.
3. **Turn the rest into tickets**, one per item still owed, referencing the
   incident id. `/crew:ticket` for each. A debt list in a markdown file that
   nobody has a ticket for is a debt nobody will pay.
4. **Update the runbook**, per `crew-runbooks`. The runbook change is worth more
   than the postmortem: it is what makes the next occurrence boring.

## What it cannot do

- **Enforcement is session-local.** These are Claude Code hooks. An incident
  stands down the gates for sessions in this repository on this machine; it
  does nothing to CI, to another engineer's machine, or to a branch protection
  rule. If CI is what is blocking the fix, this is not the tool.
- **It cannot skip a gate retroactively.** A gate that already blocked a turn
  before the incident was declared stays blocked; declare first.
- **It expires whether or not anyone is watching.** That is the point. If the
  gates come back mid-incident, extend it — do not work around it.
- **`emergency.standDown: false`** in `.crew/config.json` means the gates never
  stand down here. The incident is still declared, recorded and briefed, and
  the lanes still run. Say so plainly rather than appearing to have relaxed
  something you did not.
