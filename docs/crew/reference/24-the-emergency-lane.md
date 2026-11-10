<!-- Moved verbatim from plugin/crew/README.md (24. The emergency lane) by L-0726; the README keeps an index entry. -->

## 24. The emergency lane

Something is broken in an environment right now. The gates that normally earn
their keep — the `Stop` gate running the changed-files checks, the deploy gate
demanding an all-pass row for this sha — are, for the next twenty minutes,
standing between you and a fix. The honest options are to work around them
silently, or to make standing them down a decision with a record and a clock on
it.

```bash
/crew:emergency prod checkout returning 500 since the 14:02 deploy
/crew:emergency status
/crew:emergency extend 45
/crew:emergency end
```

### What stands down, and what does not

| | During an incident |
|---|---|
| `verify-gate` (`Stop`) | Does not run the checks at all. Records "stop gate stood down with N changed file(s) unverified". |
| `verify-gate`'s deploy-record check | Stands down. Records the deploy that has no `PROMOTIONS.md` row. |
| `promote-gate` (`PreToolUse`) | Still computes every precondition — they are file reads, not test suites — records each one that failed, then allows the deploy. |
| `guard` (`PreToolUse`) | **Unchanged. Still blocks.** |

The guard's exemption from all of this is the point rather than an oversight.
Standing down a check that tells you a change is wrong is a trade you can make
at 03:00; standing down the one that stops a change being *unrecoverable* — a
force push, a destructive Terraform verb, a history rewrite, a secret read into
the transcript — is not a trade, it is just removing the thing you most need
while tired. If the guard is genuinely in the way, run that one command by hand
outside the session.

### It expires on its own

The window is 120 minutes (fixed; `emergency.ttlMinutes` was removed), or the `--ttl` you name, capped by `emergency.maxTtlMinutes`. Past it, the gates gate
again: they compare an integer epoch, so nothing has to run and no file has to
be touched for normal service to resume. That matters because the realistic
failure here is not declaring an incident when you should not have — nobody does
that during an outage — it is **forgetting to close one afterwards**, and this
design makes that recoverable by default.

`extend` is capped by `emergency.maxTtlMinutes` (default 480) and measured from
now each time, so four extensions cannot compound into a permanently ungated
repository. Eight hours is one shift; past that, the environment is not in an
incident any more, it is in its new normal, and the checks should be back on.

Two honest limits on that clock. It is **wall time**: a machine whose clock is
moved backwards extends the window until real time catches up, which matters for
a badly-skewed VM and not much else - anyone who wants the gates off can set
`verifyGate: false` and not have to be clever about it. And the bash flavour's
stand-down needs a python (`python3`, `python`, or `py`) to parse the state file
strictly - the state has to be *valid JSON*, not merely contain a future epoch,
or `{ not json "expiresAtEpoch": 9999999999` would switch every gate off. With
no python at all it reports no incident and the gates keep gating, which is the
safe direction, but it does mean the lane does nothing on a python-less machine
where the `.sh` half is what runs.

### The debt list is the deliverable

Every skipped gate goes to `.crew/incident-skips.log`, one row per gate and
reason — not one per turn, because the same unrun check is one debt however many
times the gate declined to run it. `/crew:emergency end` turns that into
`.work/INCIDENT-<id>.md`: what did not run, what is owed, and what to verify
before trusting the list. The record is archived under `.crew/incidents/` and
the state file is deleted, which is what puts the gates back.

Then pay it: run the checks that did not run, add the missing `PROMOTIONS.md`
row, and open a ticket per remaining item. A debt list nobody has a ticket for
is a debt nobody pays.

While an incident is open — and after it expires unclosed — every session start
says so. `incidentActive` and `incidentUnclosed` are the two highest-priority PM
triggers, above `upgradeNeeded`, and the line sits in the brief's quiet lines so
no line cap can truncate it away. A session that does not know the gates are off
is a session about to merge unverified work believing it was checked.

### The lanes

Declaring also fans out **read-only** investigation lanes in parallel, each
briefed with the symptom and nothing else:

| Lane | Agent | Question |
|---|---|---|
| change | `explorer` | What shipped in the window before the symptom — commits, deploys, config, flags, migrations? |
| blast radius | `explorer` | What else calls the failing path or shares the resource, and is already broken without knowing? |
| cause | `explorer` | The two or three most probable causes, each with the cheapest observation that would kill it |
| exposure | `security` | Only when the symptom might be an incident of a different kind — auth, data exposure, an unexpected 200 |
| data | `explorer` | Only when a database is in the picture — locks, a long transaction, a migration mid-flight, replica lag |

They investigate; they do not fix. Two plausible fixes that both need trying get
a worktree each, so a half-applied one cannot land on top of the other.

### When this is the wrong tool

- **Enforcement is session-local.** An incident stands the hooks down for
  sessions in this repository on this machine. It does nothing to CI, to a
  colleague's machine, or to a branch protection rule. If CI is what blocks the
  fix, this will not help.
- **Some repositories should never do this.** `emergency.standDown: false`
  keeps every gate gating. The incident is still declared, recorded and briefed,
  and the lanes still run — you get the investigation and the paper trail
  without the exemption.
