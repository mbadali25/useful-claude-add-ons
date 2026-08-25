---
name: crew-context
description: Manage context exhaustion - warn near the limit, write handoff notes, and resume work after a clear or compact. Use when the user says set up handoff, context is filling up, wrap up the session, write a handoff note, resume where we left off, or asks how to clear the session without losing state.
---

# Context and handoff

## One correction first

Claude Code cannot clear its own session, and neither can a shell script a hook
launches — hooks run as child processes of the session, and a child cannot reset
its parent's conversation. Anything promising otherwise is guessing.

`context.autoClear` (experimental, off by default) does not contradict that. It
does not clear the conversation; it drives the **terminal**, typing `/clear` at
the prompt the way a human would. Different mechanism, different failure mode —
it depends on knowing which terminal, which is why `tmux` (exact, by pane id) is
the only method that needs no window title and the rest refuse without one. See
`hooks/scripts/auto-clear.sh` and the crew README's Auto-clear section.

You do not need it to. The lifecycle already provides the whole cycle:

| Moment | Hook | What crew does |
|---|---|---|
| Approaching the limit | `Stop` | Estimate usage; ask for a handoff note before the turn ends |
| Auto-compaction about to run | `PreCompact` | Snapshot the transcript, write a skeleton handoff if none exists |
| After `/clear`, `/compact`, or resume | `SessionStart` | Print the handoff — its stdout is injected as context |
| Any session start, including plain `startup` | `SessionStart` | `pm-brief` prints the PM's brief (triggers like `upgradeNeeded`, `handoffPending`, `graphStale`) so crew says something even on a fresh session, not only after a clear or compact |

So the flow is: crew tells you it is time, you type `/clear` or `/compact`, and
the next session opens already holding the handoff. The one manual step is the
`/clear` itself, which is the step that should stay manual anyway.

## Measuring usage

No hook input reports token count, but the JSONL transcript that hooks receive
as `transcript_path` does: every assistant turn carries `message.usage`, and
the last one is the real prompt size. `context-watch.sh` and its PowerShell
twin read that - see "How the reading is taken" below. `/context` should agree
with the watcher to within a turn; if it does not, the budget is wrong, not
the reading, and the warning prints both numbers so you can see which.

The watcher fires **once per session**. It writes `.crew/.handoff-requested` and
stays quiet afterwards; `SessionStart` clears the marker. Without that gate a
`Stop` hook returning exit 2 will fire on every turn and trap the session in a
loop.

The claim is taken atomically - `set -o noclobber` in bash, `FileMode::CreateNew`
in PowerShell - because on Windows with Git Bash installed **both** flavours
really do run on the same `Stop`, and a test-then-create lets both through and
prints the warning twice.

**The marker is per repository, not per session.** Two sessions open in the same
repo share it: the first to cross the threshold claims it and the second is not
warned, and either one's `SessionStart` clears it for both. That is pre-existing
behaviour and it is wrong, not deliberate - the fix is to key the marker on the
hook payload's `session_id`. Worth knowing before concluding the watcher is
broken in a two-terminal workflow.

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

`SessionStart` can return JSON with an `additionalContext` payload. With
`context.autoResume: true` and a handoff on disk, `pm_brief` folds the
handoff text plus its extracted next action into `additionalContext`, so the
new session opens already holding that context — the human presses Enter
rather than typing. It does not start working on its own.

`SessionStart` can also return `initialUserMessage`, which starts the new
session working with no human turn at all. It is confirmed working only for
non-interactive `claude -p` sessions (tested against Claude Code 2.1.243); no
PTY was available to prove it in an interactive session, so interactive
behavior is unproven. Crew does not use it. Reproduce the `-p` test before
relying on it interactively.

Off by default, and it should stay off unless you have a specific reason. It
removes the one moment where a human reads what the previous session claimed
before work continues on top of it. If a handoff is subtly wrong, auto-resume is
how that error compounds unattended.

Turn it on with `context.autoResume: true` only after you have watched a dozen
handoffs and trust their accuracy.

When it is on, `handoff-read` stands down on `clear`/`compact`/`resume`/`fork`
so `pm_brief` is the handoff's only emitter — otherwise the same handoff would
be injected twice.

## Configuration

```json
"context": {
  "enabled": true,
  "warnAt": 0.8,
  "budgetTokens": null,
  "reserveTokens": 100000,
  "handoffPath": ".work/HANDOFF.md",
  "autoWrapUp": false,
  "autoResume": false,
  "keepTranscripts": 5
}
```

`keepTranscripts` is honoured by `PreCompact`: that many `.jsonl` snapshots are
kept under `.crew/transcripts/` and older ones are deleted. `autoWrapUp` and
`autoResume` are both off by default - see above. So is `autoClear`, which is
experimental and presses a key on the user's behalf; its own block is
`context.autoClear` and it refuses rather than guessing whenever it cannot
identify what it would be typing into.

## How the reading is taken

The `Stop` watch reads the transcript's **last `message.usage` record** and adds
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. That is
the actual prompt size - the window occupancy, measured by the thing that filled
it, not inferred.

Both flavours used to estimate from transcript file size (`bytes / 4 * 0.75`).
That reads high, because the transcript is cumulative: it keeps every turn ever
written, including ones a compaction already discarded. Measured on real
sessions it read 158%, 195% and 664% of a 200k budget - it fired on turn one,
every session. The PowerShell flavour kept that heuristic for a release after
the bash one dropped it, so Windows sessions were cut short while Linux ones
were not; the test suite now feeds real usage records to both.

**Subagent turns are not counted.** Claude Code writes Agent-tool transcripts
to `<session>/subagents/*.jsonl`, which the watcher never opens; the main
window only ever sees the agent's returned summary, and that summary is
already inside the main transcript's usage figure. Older builds wrote subagent
turns inline flagged `isSidechain`; those are skipped too.

### The threshold is the later of two rules

```
percentage  warnAt * budget        what this always did
headroom    budget - reserveTokens never nag while this much is still free
fires at    max(the two)
```

`warnAt` was tuned when every window was 200k, where 0.8 leaves 40k - about
enough to finish a thought and write the note. The same 0.8 on a 1M window
leaves 200,000 tokens free and still asks for a handoff, which throws away a
fifth of the window and is the "it ends earlier than it should" complaint. A
percentage cannot fix that, because the right amount of headroom is an absolute
number.

Taking the **later** of the two rules is what makes this safe to default on:
the reserve can only ever push the warning later, never earlier. On a 200k
window the percentage still wins (40k < 100k) and nothing changes; on 1M the
floor wins and the gate moves from 80% to 90%.

Two edges worth knowing:

- `reserveTokens: 0` or `null` turns the floor off and restores the pure
  percentage.
- `warnAt: 0` still means "fire immediately". It is the documented override, and
  a floor that quietly outranked it would make that a lie - so the floor is
  skipped entirely when `warnAt <= 0`.

The warning prints which rule fired and both figures, so a threshold behaving
oddly is visible rather than mysterious.

### The budget works itself out

`budgetTokens` defaults to `null`, meaning "derive it". The transcript records
the model on every turn, so the window comes from a lookup: the Claude 5 family
(`claude-fable-5`, `claude-opus-5`, `claude-sonnet-5`) is 1M, Haiku 4.5 and the
4.x generation are 200k unless the id carries a `[1m]` suffix. Then the lookup
gets corrected by what this session has actually held: observed usage cannot
exceed the real window, so once a session has held *more* than the table claims,
the budget is raised to the smallest standard tier that fits. That is what
catches a `[1m]` variant that recorded its base id, and a model the table has
never heard of. Only a peak the window could not hold triggers it - an earlier
95% margin bumped a correct 1M entry to 2M once a session passed 950k, and the
gate then never fired.

The same correction applies to a pinned `budgetTokens`. An older `/crew:init`
wrote `200000` into every config, and that figure outlived the move to 1M
models: a session that has already held 300k tokens overrides the pin and says
so (`configured+observed`). It cannot help a session that is *under* the stale
pin, though - a Claude 5 session at 170k is 17% full and a `200000` pin makes
it 85% - so set the value to `null` if a config predates this.

The warning names its source (`auto:claude-opus-5`, `auto:...+observed`,
`configured`, `configured+observed`) and prints absolute token counts beside the
percentage, so a wrong budget is visible rather than just making the gate behave
oddly.

`PreCompact` keeps the last few raw transcripts under `.crew/transcripts/`.
Gitignore that directory — transcripts contain everything the session saw,
including any secret that reached it.

## Housekeeping

Delete `HANDOFF.md` when the work it describes is finished. A stale handoff is
worse than none: it gets injected into every subsequent session as though it
were current, and the next session has no way to know it is reading history.

`/crew:work` clears it on ticket completion for this reason.
