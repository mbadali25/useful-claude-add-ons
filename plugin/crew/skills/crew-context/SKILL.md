---
name: crew-context
description: Manage context exhaustion - warn near the limit, write handoff notes, and resume work after a clear or compact. Use when the user says set up handoff, context is filling up, wrap up the session, write a handoff note, resume where we left off, or asks how to clear the session without losing state.
---

# Context and handoff

## One correction first

Claude Code cannot clear its own session, and neither can a shell script a hook
launches — hooks run as child processes of the session, and a child cannot reset
its parent's conversation. Anything promising otherwise is guessing.

You do not need it to. The lifecycle already provides the whole cycle:

| Moment | Hook | What crew does |
|---|---|---|
| Approaching the limit | `Stop` | Estimate usage; ask for a handoff note before the turn ends |
| Auto-compaction about to run | `PreCompact` | Snapshot the transcript, write a skeleton handoff if none exists |
| After `/clear`, `/compact`, or resume | `SessionStart` | Print the handoff — its stdout is injected as context |

So the flow is: crew tells you it is time, you type `/clear` or `/compact`, and
the next session opens already holding the handoff. The one manual step is the
`/clear` itself, which is the step that should stay manual anyway.

## Estimating usage

There is no hook that reports token count. `context-watch.sh` estimates from the
size of the JSONL transcript, which hooks receive as `transcript_path`.

**This is a proxy, not a measurement.** Bytes are not tokens, the file carries
JSON scaffolding the model never sees, and compaction resets the relationship.
Calibrate once: run `/context` at some point, compare to what the watcher
estimates, and adjust `context.budgetTokens` until they roughly agree. Being
20% early is fine; being late defeats the purpose.

The watcher fires **once per session**. It writes `.crew/.handoff-requested` and
stays quiet afterwards; `SessionStart` clears the marker. Without that gate a
`Stop` hook returning exit 2 will fire on every turn and trap the session in a
loop.

## The handoff note

Write it to `.work/HANDOFF.md`. Keep it short, and prefer **pointers over
narrative**:

```
# Handoff
written: <iso timestamp>
ticket: T-0042
branch: feature/export-timeout
head: a1b2c3d

## Done
- <what is actually committed or in the working tree>

## In flight
- file:line — what is half-finished and why

## Next action
<one sentence. The single next thing, concrete enough to just do.>

## Do not
- <dead end already tried, so the next session does not repeat it>

## Verify first
- <anything asserted above that the next session should re-check>
```

**Why pointers rather than a summary.** A session at 85% of its context is the
least reliable narrator of what it just did — that is precisely when detail has
been compacted away and recollection drifts. The diff, the ticket, and the test
output are all more trustworthy than the memory of them. A good handoff says
"look here," not "here is what happened."

Under 40 lines. If it is longer, the session was doing too many things at once,
and that is the real finding.

## Resuming

`SessionStart` prints the note; Claude Code injects it. The injected text ends
with a reminder that the working tree is the source of truth, because a handoff
can be wrong in ways the diff cannot.

The note is phrased as project information, not as commands. Text framed as
out-of-band system instructions trips prompt-injection defences and gets
surfaced to the user rather than treated as context — the opposite of what you
want here.

### Auto-resume

`SessionStart` can in principle return JSON with an `initialUserMessage` to start
the new session working immediately, with no human turn.

**crew does not implement this.** `handoff-read.sh` prints the note as plain
context and stops. `context.autoResume` is accepted in config and read by
nothing; setting it to `true` changes no behaviour.

That is deliberate. Auto-resume removes the one moment where a human reads what
the previous session claimed before work continues on top of it, and if a handoff
is subtly wrong that is how the error compounds unattended. If you want it, it is
a change to `handoff-read.sh` and its `.ps1` twin - not a config flag that is
already wired.

## Configuration

```json
"context": {
  "enabled": true,
  "warnAt": 0.8,
  "budgetTokens": null,
  "handoffPath": ".work/HANDOFF.md",
  "keepTranscripts": 5
}
```

`keepTranscripts` is honoured by `PreCompact`: that many `.jsonl` snapshots are
kept under `.crew/transcripts/` and older ones are deleted. `autoResume` is
accepted and ignored - see above.

## How the reading is taken

The `Stop` watch reads the transcript's **last `message.usage` record** and adds
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. That is
the actual prompt size - the window occupancy, measured by the thing that filled
it, not inferred.

It used to estimate from transcript file size (`bytes / 4 * 0.75`). That reads
high, because the transcript is cumulative: it keeps every turn ever written,
including ones a compaction already discarded. On a real session it read 45%
high - 950k estimated against 654k actual - which on a 200k budget is the
difference between firing at 80% and firing on turn one, every turn.

### The budget works itself out

`budgetTokens` defaults to `null`, meaning "derive it". The transcript records
the model on every turn, so the window comes from a lookup - and then gets
corrected by what this session has actually held.

That correction is the part that matters. A 1M-context model reports its **base**
id: this session runs `claude-opus-5[1m]` and the transcript says
`claude-opus-5`. Read the id alone and you conclude 200k, then fire the gate on
turn one, every turn, forever. But observed usage cannot exceed the real window -
so once a session has held 668k tokens, the window is provably not 200k, and the
budget is raised to the smallest standard tier that fits.

The warning names its source (`auto:claude-opus-5+observed`, or `configured`) and
prints absolute token counts beside the percentage, so a wrong budget is visible
rather than just making the gate behave oddly.

`PreCompact` keeps the last few raw transcripts under `.crew/transcripts/`.
Gitignore that directory — transcripts contain everything the session saw,
including any secret that reached it.

## Housekeeping

Delete `HANDOFF.md` when the work it describes is finished. A stale handoff is
worse than none: it gets injected into every subsequent session as though it
were current, and the next session has no way to know it is reading history.

`/crew:work` clears it on ticket completion for this reason.
