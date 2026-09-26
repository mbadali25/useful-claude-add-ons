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
| Any session start, including plain `startup` | `SessionStart` | the context hook (`crew-context.sh`) injects branch/HEAD, code-map anchor state and a pointer to the handoff, so crew says something even on a fresh session, not only after a clear or compact |

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

The watcher fires **once per threshold crossing per session**. It writes
`.crew/.handoff-requested-<session_id>` (the payload's `session_id`, reduced to
`[A-Za-z0-9_-]`) and stays quiet afterwards; that session's next `SessionStart`
clears it, and so does a measured reading back under the threshold. Without
that gate a `Stop` hook returning exit 2 will fire on every turn and trap the
session in a loop. It never blocks on a `stop_hook_active` continuation, but
that continuation is the turn it hands to auto-clear.

The claim is taken atomically - `set -o noclobber` in bash, `FileMode::CreateNew`
in PowerShell - because on Windows with Git Bash installed **both** flavours
really do run on the same `Stop`, and a test-then-create lets both through and
prints the warning twice.

**The marker is per session.** It used to be one file per repository, so two
terminals in one repo shared it: the first to cross the threshold silenced the
other, and either one's `SessionStart` re-armed both. It is now keyed on the
payload's `session_id`, and `SessionStart` clears only its own session's marker
(other sessions' markers age out after seven days).

The marker also records the reading that caused it, and whether that reading
can be trusted. Auto-clear (opt-in per machine; see
`docs/guides/crew/src/auto-cycle.md`) never clears on an estimate, an unknown
window, a pre-compaction reading, or an empty marker.

## The handoff note

Write it to `.work/HANDOFF.md`. Keep it short, and prefer **pointers over
narrative**:

```
# Handoff
written: <iso timestamp>
ticket: T-0042
branch: feature/export-timeout
head: a1b2c3d
resume: /crew:<command> <ticket>

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

**The `resume:` line** is the one machine-readable line in the note. It names
the single next command, and `crew_resume.RESUME_COMMANDS`
(`plugin/crew/hooks/scripts/crew_resume.py`) is its only definition:
`/crew:spec`, `/crew:plan`, `/crew:implement`, `/crew:review` and `/crew:done`
each take one ticket id (`T-0042`); `/crew:autopilot` takes a ticket id,
`--goal <slug>` (lowercase letters, digits and `-`) or nothing; `/crew:status`
takes nothing. `resume: none` when no allowlisted command is next. Exactly one
`resume:` line, nothing after the argument: a second line, trailing text, an
unknown command, or an excluded one (`/crew:approve`, `/crew:brainstorm`,
`/crew:fix`, `/crew:emergency`, `/crew:gate`, `/crew:promote`,
`/crew:migrate`, `/crew:change`) is refused, never guessed at.

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
`memory.inject` on (the default since 1.0.0) and a handoff on disk, the context
hook (`crew_context.py`) injects the handoff text into `additionalContext` on
`clear`/`compact`/`resume`, and a pointer plus its extracted next action on
`startup` — the human presses Enter rather than typing. It does not start
working on its own. `context.autoResume` is no longer read.

`SessionStart` can also return `initialUserMessage`, meant to start the new
session working with no human turn. **It does not work interactively.**
Spike, 2026-09-25, Claude Code 2.1.282 (T-0006): `hookSpecificOutput.
initialUserMessage` with `hookEventName: "SessionStart"` is parsed and stored
for every source, but only the `claude -p` runner and the SDK's startup path
ever read it back; interactive `startup`, `/clear` and manual `/compact` start
no turn, with either placement. `claude -p`: it runs. Crew never emits it.

With `resume.auto: true` in `~/.claude/crew/config.json` (machine only; a repo
`false` in `.crew/crew.json` or `.crew/config.json` vetoes it, a repo `true`
does nothing), the injected handoff on `clear` or a manual `/compact` also
names the next command from the `resume:` line — `Auto-resume: ready to run
/crew:done T-0001.`, saying it did not start from the hook, so press Enter or
type it (T-0013 types it) — or says `Auto-resume did not start: <reason>.`
The reasons: compact was not a manual /compact; no handoff note, or it was
archived as stale, or is stale and could not be archived; no resume line, `resume: none`, or a refused line; the
`branch:`/`head:` line does not match the checkout; the ticket directory or
goal file is missing; the command is not installed; `resume-state.json` exists
and could not be read; this handoff was already
resumed; the progress fingerprint could not be computed; the same command
with no progress since the last auto-resume. Never on `startup`.

The injected note is framed as project information that the working tree
overrides, so a subtly wrong handoff is read against `git diff` before anyone
acts on it.

When `memory.inject` is on, `handoff-read` stops printing on
`clear`/`compact`/`resume`/`fork` so the context hook is the handoff's only
emitter — otherwise the same handoff would be injected twice. It still resets
its once-per-session markers either way. Set `memory.inject: false` and
`handoff-read` prints the note instead.

### Staleness and archiving

The old `handoffPending` finding only ever asked whether `HANDOFF.md`
exists — it fires the same way for a note written five minutes ago and one
written before a gate closed and two more commits landed on top of it. The
second case is a note describing a state that no longer exists, and injecting
it as though it were current is how a session ends up "resuming" work that a
different session already finished.

`handoff-read` and the context hook both judge the
note before printing or injecting it, on two signals — see
`crew_state.handoff_staleness` for the full reasoning:

- **Age.** The note's own `written:` line, compared against `staleHandoff.
  maxAgeHours`. Falls back to the file's mtime when `written:` is missing or
  unparseable, which is why the fallback is weaker: an edited file's mtime
  moves even when nobody updated the header to match.
- **Reality drift.** The note's `branch:` and `head:` lines, compared against
  the checkout right now. A `head:` this repository cannot find at all, or
  cannot reach from the current `HEAD`, means the note's account of history
  cannot be verified at all — the same "unknown resolves to stale" rule
  `crew-diagrams` and the codemap already apply to missing provenance. A
  `head:` that IS verifiable but is `staleHandoff.maxCommitsBehind` or more
  commits behind reports exactly how far the note has fallen behind. A
  `branch:` that no longer matches the checkout is flagged on its own, since
  a merge can leave the noted head a true ancestor of `HEAD` while the
  session has still moved off the branch the note describes.

A note either signal flags is **archived, never deleted** — moved to
`.crew/handoffs/HANDOFF-<timestamp>.md`, timestamped and never overwritten.
This is the automatic action crew's own "ask before deleting anything" rule
still allows: moving a file sideways into a dated archive is not deleting it,
and a stale note left visibly in that archive is recoverable in a way a
deleted one never is. Nothing here changes read_work's plain existence check
or the `handoffPending` finding it feeds — a note that is judged fresh is
left exactly where it was, which is what every session did before this
existed.

## Configuration

```json
"context": {
  "enabled": true,
  "warnAt": 0.8,
  "budgetTokens": null,
  "reserveTokens": 100000,
  "handoffPath": ".work/HANDOFF.md",
  "autoWrapUp": false,
  "keepTranscripts": 5,
  "staleHandoff": {
    "maxAgeHours": 72,
    "maxCommitsBehind": 3
  }
}
```

`staleHandoff` is generous by default on purpose: archiving a note someone is
still using is worse than leaving an honestly-stale one in place for one more
day. Tighten `maxCommitsBehind` for a repo where a handoff realistically
survives no more than a commit or two, or raise `maxAgeHours` for one where a
session reasonably picks a handoff back up after a quiet weekend.

`keepTranscripts` is honoured by `PreCompact`: that many `.jsonl` snapshots are
kept under `.crew/transcripts/` and older ones are deleted. `autoWrapUp` is
off by default. So is `autoClear`, which is
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

Delete `HANDOFF.md` yourself when the work it describes is finished, rather
than waiting on the staleness check above to catch it later. `/crew:done`
clears it on ticket completion for this reason, and that is still a real
delete — the work is done, the note has nothing left to record, and there is
nothing there worth archiving.

The staleness check under "Staleness and archiving" is the backstop for when
that manual step gets missed, not a replacement for it: it only fires on
`clear`/`compact`/`resume`/`fork`, and only once age or reality drift gives it
an actual reason to distrust the note, so a handoff can sit unread for a
while before it trips. Finishing the work and deleting the note yourself is
still faster and more certain than waiting for either.
