<!-- Moved verbatim from plugin/crew/README.md (16. Context handoff) by L-0726; the README keeps an index entry. -->

## 16. Context handoff

**First, a correction worth having up front:** Claude Code cannot clear its own
session, and a script launched by a hook cannot either — hooks run as child
processes, and a child cannot reset its parent's conversation.

You don't need it to. The lifecycle already covers the cycle:

| Moment | Hook | What happens |
|---|---|---|
| Nearing the limit | `Stop` | Estimates usage, asks for a handoff before the turn ends |
| Auto-compaction imminent | `PreCompact` | Snapshots the transcript, writes a skeleton handoff |
| After `/clear`, `/compact`, resume | `SessionStart` | Prints the handoff — stdout is injected as context, byte-exact LF on every OS |

So: crew tells you it's time, you type `/clear`, and the next session opens
already holding the note. The one manual step is the `/clear` — which is the
step that should stay manual.

### The threshold is a measurement

No hook input reports token count, but the JSONL transcript that hooks receive
as `transcript_path` carries `message.usage` on every assistant turn, and the
last one is the real prompt size. Both `context-watch` flavours read that. The
window comes from the model id (Claude 5 family 1M, Haiku and the 4.x
generation 200k) and is corrected upward by the session's own peak usage, so a
`[1m]` variant that recorded its base id still gets the right budget. Subagent
transcripts live in separate files and are never counted. `budgetTokens` stays
`null` unless you have a reason to pin it - a stale `200000` from an older
`/crew:init` is the one thing that still makes the gate fire early.

It fires **once per session**, gated by a marker file that `SessionStart`
clears. Without that gate, a `Stop` hook returning exit 2 fires every turn and
traps the session in a loop. The marker is claimed atomically (`noclobber` in
bash, `FileMode::CreateNew` in PowerShell) because on Windows with Git Bash
installed both flavours really do run on the same `Stop`, and a
test-then-create lets both through.

### The default is 0.4 (1.2.40), one key for both

`context.warnAt` defaults to `0.4` (it was `0.5` from 0.19.52 to 1.2.39, `0.8` before). It is the single
threshold for the handoff warning, auto wrap-up and auto-clear: `autoWrapUp` and `autoClear` change what
happens when it fires, not when. A 1M window therefore warns at 400k.

Only the unset default moved. A `warnAt` you set in `~/.claude/crew/config.json` or `.crew/config.json`
keeps its value, and there is no auto-migration. A repo created while the default was `0.5` carries a literal
`"warnAt": 0.5` copied from the template, so it stays at 50% until you edit that line (or delete it to take
the new default).

### Two rules, and the later one wins

`warnAt` alone was tuned when every window was 200k, where 0.8 leaves 40k — about
enough to finish a thought and write the note. The same 0.8 on a 1M window
leaves **200,000 tokens** unused and still asks you to wrap up: a whole 200k
session's worth of room thrown away. That is the "it ends a bit earlier than it
should" complaint, and a percentage cannot fix it, because the right amount of
headroom is an absolute number, not a fraction.

So the threshold is the **later** of:

| Rule | Threshold | Wins on |
|---|---|---|
| percentage | `warnAt × budget` | small windows — 0.8 of 200k = 160k, leaving 40k |
| headroom | `budget − reserveTokens` | large windows — 1M − 100k = 900k, i.e. 90% |

Taking the later of the two means `reserveTokens` can only ever push the
warning **later**, never earlier. A 200k repo behaves exactly as it did; a 1M
session gets the extra 100k it was being denied. Set
`context.reserveTokens: 0` for the old pure-percentage behaviour, and note that
`warnAt: 0` still means "fire immediately" — the floor does not outrank the
one explicit override.

The warning names which rule fired, with absolute numbers on both, so a
threshold that behaves oddly is visible rather than mysterious.

### Pointers, not narrative

```
/crew:handoff
```

The note is built from `git status`, the diff, the ticket, and the last gate
result — plus the two things only the session knows: the next action in one
concrete sentence, and the dead ends already tried.

A session at 85% context is the *least* reliable narrator of what it just did —
that's exactly when detail has been compacted away. The diff is more trustworthy
than the recollection of it. A good handoff says "look here," not "here's what
happened." Under 40 lines; if it's longer, the session was doing too many things
at once, and that's the real finding.

Anything uncertain goes under **Verify first** rather than being asserted as done.

### Auto-wrap-up (on by default since 0.19.52)

`context.autoWrapUp` changes what the `Stop` hook says at `warnAt`, not
whether it fires. On (the default), it instructs the session to reach a
stopping point — finish or safely abandon the change in flight, write the
handoff, update the ticket — before telling you it's ready. Off, it just asks
you to write the handoff.

With `context.autoClear.wrapUp` armed (machine file only, and only where
auto-clear is armed), the warning becomes the one wrap-up procedure — finish
the step, commit only if its `Test:` passes, run `/crew:handoff --wrap-up`,
end the turn — and auto-clear waits until the handoff's `head:` is HEAD, its
`branch:` matches, no tracked file is modified and its `resume:` line parses
(or is `resume: none`). A refusal is shown to you and fed back to the session
once. Crew checks the commit, not the test (CONFIG.md §14).

It blocks **once per threshold crossing per session**: keyed on the payload's
`session_id`, never on a `stop_hook_active` continuation, and re-armed only
when a measured reading drops back under the threshold (a compaction). It is
the one blocking `Stop` crew keeps besides the verify gate, as a documented
exception. The `/clear` that follows is yours to type unless this machine
opted in to auto-clear, below.

### Auto-clear (off by default, opt-in per machine)

The correction at the top of this section stands: a hook cannot clear the
conversation, because a hook is a child process and a child cannot reset its
parent. `context.autoClear` does not contradict that. It does something else —
it drives the **terminal**, typing `/clear` at the prompt the way you would.

Together with the wrap-up (above) and the resume (below) it is one cycle:
**wrap-up → handoff → clear → resume**. The full user guide is
`docs/guides/crew/src/auto-cycle.md`.

**It is a machine opt-in.** `enabled` is read from the machine-global
`~/.claude/crew/config.json`; a repo's `.crew/config.json` can switch it
*off* (`false`) but a repo `true` does not switch it on — the thing it drives is
this machine's keyboard, and templates written since 0.19.52 carried `true` in
every repo. The other keys layer normally, repo over machine.

```json
{ "context": { "autoClear": {
    "enabled": true,
    "method": "auto",
    "windowTitle": null,
    "command": "/clear",
    "delaySeconds": 3,
    "minHandoffLines": 5
} } }
```

| Method | How it finds the target | Confidence |
|---|---|---|
| `tmux` | `$TMUX_PANE`, and only when that pane's pid is this session's own process or an ancestor of it | **Exact.** No focus involved. Use this if you can. |
| `xdotool` | the one window owned by the nearest ancestor of this session's own process, hosting no other terminal; `windowTitle` narrows or, failing that, is a fallback that must match exactly one window (and refuses while another session is live) | Activates that window id, re-checks it is active, then types. |
| `notify` | no window — types nothing | Prints a `systemMessage` saying the handoff is written and verified and it is safe to run the configured command yourself. Never claims anything was cleared or compacted, because nothing was. `auto` resolves here on native Windows with no tmux pane. |
| `sendkeys` | the same rule, from this session's own process, through `EnumWindows` (renamed from the pre-1.0 `"windows"` literal); at send time that exact window handle must have foreground | **Opt-in only — `auto` never resolves here.** Windows Terminal hosts every tab in one window and nothing outside UI Automation can tell which tab is active, so a Windows-Terminal-owned target declines and falls back to `notify`, logged to `.crew/.autoclear.log`. Request it by name after reading what it does. |
| `wtype` | cannot identify a window | **Refused**, whatever `unsafeFocus` says. |

#### What has to be true before it types anything

1. This machine opted in, as above.
2. `context-watch` asked **this session** for a wrap-up. The marker is
   `.crew/.handoff-requested-<session_id>` — it used to be one file per repo,
   so two terminals shared it.
3. The context reading behind that request was a measurement: not an estimate
   from transcript size, not an unknown model window, not a reading from before
   a compaction. A marker that is empty or not the hook's JSON — the shape of
   the Windows low-context `/clear` — is unknown, and unknown never clears.
4. The handoff exists, is **newer** than the request, has at least
   `minHandoffLines` non-blank lines, and is not PreCompact's automatic skeleton.
5. This session is bound to its **own** process (T-0016): the nearest ancestor
   named by a Claude Code session record
   (`${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json`) with this session's
   id and that process's start time. A headless session — `claude -p`
   (entrypoint `sdk-cli`) or one with no controlling terminal — types
   nothing whatever the method: it gets one `notify-headless` message naming
   the handoff and its `resume:` line and saying the process that started it
   must start a new one. A session that cannot be identified, or whose
   entrypoint was never measured, types nothing either (`auto` falls back to
   plain `notify`). [CONFIG.md §14](../../../plugin/crew/CONFIG.md) has every rule.
6. The target window is identified uniquely (the table above), walking up
   from that process: through another Claude Code session, past a chain that
   could not be read, or into a window that hosts another terminal, it
   refuses. Zero or several candidates is a refusal, never a guess — this
   step does not apply to `notify`, which identifies no window because it
   types nothing.
7. Nothing has claimed this session's one attempt (`.crew/.autoclear-sent-<session_id>`).

Fail any of those and it writes a line to `.crew/.autoclear.log` saying which,
and does nothing. That log exists because a `Stop` hook's stderr is invisible
when it exits 0, so without it "nothing happened" is indistinguishable from
"the feature is broken".

#### When it runs

On the `Stop` that ends the forced continuation — the turn the wrap-up block
sent back to write the handoff. `context-watch` never blocks on
`stop_hook_active`, but it does hand that turn to auto-clear; before this it
exited first, so the clear waited for your next message.

#### The delay, and why it is not zero

The hook runs *while the turn is still ending*, so the prompt does not exist yet
and typing immediately types into nothing. The keystroke is handed to a detached
child that sleeps first. Three seconds is usually enough; raise it on a slow
machine. The parent exits 0 straight away so the turn is not held up.

#### A `/clear` is not undoable

With `minHandoffLines` set too low, or a handoff the session wrote badly, you
lose the context and keep a note that does not replace it. Watch the first few,
and read `.work/HANDOFF.md` before trusting the next session to resume from it.

#### Try it without risking anything

```bash
bash   ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-clear.sh --dry-run --force
pwsh -File ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-clear.ps1 -DryRun -Force
```

`--dry-run` prints the method, target, command and delay it *would* use and sends
nothing. `--force` skips the handoff and reading conditions so you can see the
plan without being deep into a session. Neither consumes the one attempt.

If you run Claude Code in a tmux pane inside WSL, prefer the `.sh` flavour: it
addresses a pane by id and never touches focus, which is strictly safer than
anything the Windows side can do.

### Resuming from the handoff

Since 1.0.0 the context hook (`crew-context.sh`, on by default through
`memory.inject`) opens the next `SessionStart` after `/clear`, `/compact` or a
resume already holding the last handoff, as `additionalContext` rather than
`initialUserMessage`. It does not make the session start working on its own:
a human still reads the note and gives the first turn — which is the one
moment where a subtly wrong handoff gets caught before more work is built on
top of it. `context.autoResume` is no longer read. Set `memory.inject: false`
and `handoff-read` prints the note instead.

#### Auto-resume (`resume.auto`, off by default)

`/crew:handoff` writes one machine-readable line into the note's header,
`resume: /crew:done T-0001` (or `resume: none`), and with `resume.auto: true`
in `~/.claude/crew/config.json` the context hook works out, on the
`SessionStart` after `/clear` or a manual `/compact`, whether that command may
be resumed. Only the machine file can switch it on; a `false` in
`.crew/crew.json` or `.crew/config.json` vetoes it, and a repo `true` does
nothing (`CONFIG.md` §14a). Never on `startup`.

**Nothing starts on its own yet.** Claude Code 2.1.282 drops a SessionStart
`initialUserMessage` in an interactive session (spike, 2026-09-25), so crew
never sends one. When the checks pass, the injected handoff carries
`Auto-resume: ready to run /crew:done T-0001.` and says it did not start from
the hook — press Enter or type it, unless crew types it (below). When
they do not, it carries `Auto-resume did not start: <reason>.` The reasons:
compact was not a manual /compact; no handoff note, or the handoff was
archived as stale (or is stale and could not be archived); the handoff is the
automatic PreCompact skeleton (it names no next action); no resume line,
`resume: none`, or a line the grammar refuses (two lines, trailing text, an
unknown or excluded command such as `/crew:approve`); the `branch:` or
`head:` line does not match the checkout; the ticket's `.work/tickets/<id>/`
(or the goal file) does not exist; the command is not installed;
`handoff-author.json` could not be read; no record of which session wrote
this handoff; a later handoff write could not replace or remove `handoff-author.json` (`handoff-author.json.stuck`), or the file and its directory are both read-only so it can be neither replaced nor removed; the handoff changed since its author session wrote it; the
handoff was written by another session; this session's process could not be
identified (always on a host without `/proc` — native Windows, macOS); the
record of past auto-resumes (`resume-state.json`) could not be read, or its
directory cannot be searched; this handoff was already resumed; the progress
fingerprint could not be computed; the same command with no progress since
the last auto-resume; or `internal error` (the decision itself failed — the
handoff is still injected).

**Typing it (T-0013).** Where the terminal can be driven, crew types the
command into its own session. On that SessionStart the context hook runs its
own flavour's `auto-clear` sender in resume mode, before its context claim.
Consent is `resume.auto`; `context.autoClear` only describes the terminal
(`method`, `windowTitle`, `onlyRepos`, `onlySessions`). The sender claims a
per-handoff marker (`<git-common-dir>/crew/resume-typed-<sha256[:16]>`) only
after every refusal, records the run with `crew_resume.py record` (a failed
record types nothing), and then a detached sender types. In tmux it waits
`resume.typeDelaySeconds` (2), polls the pane up to
`resume.readyTimeoutSeconds` (15) for an idle, empty input line, and sends
the text and, half a second later, Enter. On native Windows it types only
under an explicit `method: sendkeys`, after the delay, with the focus and
tab rechecks; `auto` there is `notify` and types nothing. The context says
`Auto-resume: typing /crew:done T-0001 into this session in 2s (method
tmux); ...`, or keeps the line above and adds `Auto-resume was not typed:
<reason>.` Refusals, each logged to `.crew/.autoclear.log` (off is silent):
`decide` did not say run; no usable method, `$TMUX` unset, or a pane that is
not an ancestor; `wtype` or `xdotool`; the other flavour's method; already
typed once (marker); the run could not be recorded; the input line is not
empty; the input line was not ready in time; on Windows, focus lost or a tab
not provable after the delay. The 2 s default comes from the T-0013 spike
(input ready by 0.134 s on Claude Code 2.1.282). A delay is a guess, not a
proof: Windows has no probe, so on a loaded machine a key can land before
the box is ready (`CONFIG.md` §14b).

A note resumes only in the session that wrote it (T-0042). When the note is
written with Write, Edit or MultiEdit on an armed machine, the context hook
records who wrote it in `<git-common-dir>/crew/handoff-author.json`: after
`/compact` the session id must match, and after `/clear` (which changes the
session id) the Claude Code process must. A note written by Bash, by hand,
or before the machine was armed has no such record, so it waits. The allowlist is `crew_resume.RESUME_COMMANDS`:
`/crew:spec`, `/crew:plan`, `/crew:implement`, `/crew:review`, `/crew:done`,
`/crew:autopilot` and `/crew:status`. No gate changes: the resumed command's
own approval, scope, verify and review gates still decide.

A handoff written while `/crew:autopilot` drives a ticket carries
`resume: /crew:autopilot <id>`; typing `/crew:autopilot` with no argument in
the next session reads that line and recomputes the phase from disk (see
"Autopilot"). **While a goal runs (T-0056), every handoff names the goal
instead.** The goal file `.work/autopilot/<slug>.json` keeps a `run` block
(`state` `running`, `stopped` or `done`, the current `ticket`, a `reason`,
`at`), written through a temp file and `os.replace` by `crew_autopilot.py
goal-mark` and by `goal-run` itself. One function,
`crew_autopilot.py handoff-resume --root . [--ticket <id>]`, decides the line
for every writer: autopilot's low-context stop, `/crew:handoff`, and the
PreCompact skeleton (`handoff-write.sh`/`.ps1`, which adds the line after
`head:` only while exactly one goal runs). One running goal: `resume:
/crew:autopilot --goal <slug>`, even when a ticket is in hand. No running goal:
the ticket form, or `resume: none`. Two running goals, or a goal file it
cannot read: `resume: none` with `kind=unknown` and the reason — **could not
tell which goal runs, so it names none rather than dropping the goal for the
ticket**. A `stopped` or `done` goal never produces the goal line.

### Housekeeping

`/crew:done` deletes `HANDOFF.md` on ticket completion — do that yourself
whenever the work it describes is finished, rather than relying on the check
below to catch it. A stale handoff is worse than none: it gets injected into
every later session as though current, and that session can't tell it's
reading history.

As a backstop for when that manual step gets missed, `handoff-read` and the
context hook both judge the note before printing or
injecting it, on age (`written:` vs. `context.staleHandoff.maxAgeHours`) and
on whether its `head:`/`branch:` lines still describe the checkout (a `head:`
this repo cannot verify, or `staleHandoff.maxCommitsBehind` or more commits
landed on top of it). A note either signal flags is **archived, never
deleted** — moved to `.crew/handoffs/HANDOFF-<timestamp>.md`, so a wrong
judgment call is recoverable rather than silently gone. See
`crew-context/SKILL.md`'s "Staleness and archiving" for the full reasoning
and both thresholds' defaults.

`PreCompact` keeps the last five raw transcripts in `.crew/transcripts/`, which
setup gitignores — transcripts contain everything the session saw, including any
secret that reached it.

### Cross-session claims (`crew_coord.py`)

Since 1.1.6. When several sessions — same or different repositories, same or
different machines — work one backlog, each **claims** a ticket before working
it, so two sessions never hold the same one. The record is not in `.work/`
(ignored and per worktree) but on a git branch, `crew-coord/<channel>`, on a
shared remote. Its tree holds `claims/<repo>__<id>.json` per claim and an
append-only `log.jsonl`. You claim with the commands below: no crew command claims for you yet - neither a `/crew:autopilot` run nor a wave, which only run `status` first.

```
python3 hooks/scripts/crew_coord.py status  --channel <c> --remote origin
python3 hooks/scripts/crew_coord.py claim   --channel <c> --remote origin --ticket <id>
python3 hooks/scripts/crew_coord.py release --channel <c> --remote origin --ticket <id>
python3 hooks/scripts/crew_coord.py done    --channel <c> --remote origin --ticket <id>
python3 hooks/scripts/crew_coord.py recover --channel <c> --remote origin --ticket <id>
```

`--channel` and `--remote` default to `coord.channel` and `coord.remote`
(remote falling back to `origin`) in `.crew/config.json`.

**The `<repo>` half of the key is derived, never typed:** it is the `origin`
remote's URL as git resolves it — `git remote get-url origin`, so
`url.<base>.insteadOf` applies and an alias names the repository it points
at — reduced to its host and every path segment, lowercased, with `.git` and any
user or token removed, and a port removed only when it is the scheme's default (ssh 22,
https 443, http 80, git 9418): `ssh://host:2222/team/repo` gives `host_3a2222.team.repo`,
so two repositories behind two ports of one host are two keys. Each of those parts is written so it can
be read back one way only — every byte outside `a-z`, `0-9` and `-` becomes
`_` and two hex digits, so `.` is `_2e` and `_` is `_5f` — and the parts are
joined with a dot (`https://github.com/Owner/Repo.git`,
`ssh://git@github.com/Owner/Repo.git` and `git@github.com:Owner/Repo.git` all
give `github_2ecom.owner.repo`; `https://gitlab.com/group/sub/repo.git` gives
`gitlab_2ecom.group.sub.repo`). So every worktree and clone of one repository
names a ticket alike, and two different repositories never do — not on
different hosts, not in different groups with the same last two names, and
not where a dot inside a name would otherwise read as a separator
(`team/a.b/repo` and `team/a/b.repo` are two keys). A network URL keeps that
lowercasing and `.git` stripping because a hosting service serves those
spellings as one repository; a local one does not. A local path, or the path
a `file://` URL names (percent-decoded as git decodes it, with an empty or
`localhost` host), gives `file_` and its segments **with their case and any
`.git` kept**, because on a case-sensitive filesystem `Repo.git` and
`repo.git` are two directories, and `repo` beside `repo.git` is two
repositories anywhere. A local segment may be any name the filesystem allows
(`.git`, a dot-directory, a space); only one that is not UTF-8 reads
`unknown`. The path keyed is the repository git itself opens for
it: a leading `~` or `~user` is expanded as git expands it, a relative path is
read against the worktree git runs in, then git's own
suffix order is applied (`<path>/.git`, `<path>`, `<path>.git/.git`,
`<path>.git` — `enter_repo` in git's `setup.c`, read at v2.53.0), a gitfile is
followed and a linked worktree's git directory is taken to its common one, and
the result is made real (`..` and symlinks resolved) and each component is
spelled as its directory lists it, so on a case-insensitive volume (macOS and
Windows defaults) the case on disk is keyed, not the case typed. So
`remote.git` from `/srv/work`, `/srv/work/remote.git/`, `/srv/work/remote`
when only `remote.git` exists, and `file:///srv/work/remote.git` are one key;
a non-bare `/srv/src` and its `/srv/src/.git` are one key; and a path that is
not a repository here is keyed as written. A component whose directory cannot
be listed, on a volume where its case does not matter, reads `unknown`,
because its spelling on disk cannot be told. Every Azure DevOps form of one repository gives
`dev_2eazure_2ecom.<org>.<project>.<repo>`: `https://dev.azure.com/<org>/<project>/_git/<repo>`,
`https://dev.azure.com/<org>/_git/<repo>` (a project's default repository,
whose name is the project's, so project = repo),
`<org>.visualstudio.com/[DefaultCollection/][<project>/]_git/<repo>` and
`ssh.dev.azure.com:v3/<org>/<project>/<repo>` — each name percent-decoded and
lowercased, then written like any other part, so `My%20Project` and
`My-Project` stay two projects. The markers `_git`, `v3` and
`DefaultCollection` are compared after that decoding too, so `%5Fgit` is
`_git`. An origin the key cannot be told
from reads `unknown` (exit 3) and nothing is written: an Azure DevOps URL that
fits none of those forms or whose names are not UTF-8, a network URL's host or
path segment that is not letters, digits, `.`, `_`, `-`, a local path segment
that is not UTF-8, a key over 128 characters, a URL with no
path, a network URL with no host once any user and port are dropped
(`https:///owner/repo`, `https://user@/owner/repo`, `https://:443/owner/repo`,
`ssh:///owner/repo` — never read as a local path), a `file://` URL naming
another host or not percent-encoded UTF-8, an empty `origin` URL, or a
`get-url` that fails. That includes an
on-premises Azure DevOps Server URL
(`https://server/tfs/<collection>/<project>/_git/<repo>`), whose `_git`
segment is outside the rule. It never falls back to a directory name, which
would give one ticket a second key. Only when git says `origin` has no URL at
all (`git config` exit 1) does it use the main worktree's directory name, and
it prints why; a `git config` or `git rev-parse --git-common-dir` probe that
fails is `unknown` too, never that fallback. `--ticket <repo>:<id>` is still accepted, but
the `<repo>` given must be that derived name (compared lowercased); any other
is refused, because a free-text repo gives one ticket several keys and so
several holders. **The `<id>` half is upper-cased** for the same reason:
tracker ids — Jira keys, SDP ids, the local `T-NNNN` — name one ticket
whatever case they are typed in, so `t-0030` and `T-0030` are one key, not
two holders.

- **Writes never force.** Every change is a new commit on the freshly fetched
  tip, built with git plumbing (no checkout, no working tree, index, `.work/`,
  `HEAD` or `FETCH_HEAD` touched; other files on the channel keep their mode)
  and sent with a plain `git push`. crew_coord.py will never force: no
  `--force`, `-f`, `--force-with-lease` or `+` refspec. The push goes to
  `crew-coord--push`, a remote defined only in the push's environment
  (`GIT_CONFIG_COUNT`, git 2.31+) with the real remote's url, pushurl, proxy
  and receivepack, and never its fetch or push refspecs or `mirror`: git
  writes no remote-tracking ref, no local ref moves, and
  no URL — or a token inside one — appears in the process's arguments. A
  remote with several push URLs reads `unknown`, and so does one whose push
  configuration cannot be read: each of those keys is read with
  `git config --get-all`, where exit 1 means the key is absent and any other
  failure is `unknown` with nothing pushed, never a missing pushurl that would
  send the claim to the fetch URL. It runs with `--no-verify`,
  so the repo's pre-push hook (husky, lefthook) never runs on a claim or a
  heartbeat. A rejected push
  re-fetches, re-applies the change — a peer's claim that landed in between is
  then seen and refused — and retries at most 3 times, then reports
  `unknown - could not push`. A fetch that fails reads `unknown`, never current,
  and a claim is refused rather than granted on it.
- **The TTL is 30 minutes** (`coord.ttlMinutes`; anything but a number above
  0 and at most 10080, 7 days — a string, `0`, `NaN`, `Infinity`, `1e308` — is
  a config error: every command exits 2 naming the key before any fetch or
  push, so nothing is written). `claim` starts a detached
  heartbeat that pushes `heartbeat_at` every 10 minutes while the session's
  `CLAUDE_PID` lives and exits once it is gone, is reused by another process
  (a different start time), or the claim is no longer `working` for it. One
  loop runs per claim and holder — the holder's session id, machine,
  worktree, pid and start time, every field that makes a holder: a second
  loop for the same holder finds the first's lock and exits, while a new
  holder's loop — after a release and a claim by another session, the same
  session and pid claiming from another worktree, or a recover — takes a lock
  of its own and does not wait for the old holder's loop, which exits on its
  next tick. Inside
  Claude Code's sandbox (bubblewrap `--unshare-pid`) the loop cannot see
  `CLAUDE_PID`, reads it gone and exits at once, so the claim reads
  `owner unknown` after the TTL; the claim recorded no PID namespace (below),
  so recovery never adopts it: a false alarm, never a false grant. Its log
  and locks live in a private per-user directory in the system
  temp directory (`crew-coord-<uid>`, mode 0700; refused if it is a symlink,
  another user's, or open to others), the log opened 0600 without following a
  symlink. A `working` claim whose heartbeat is older than the TTL reads
  `owner unknown (last heartbeat <age>)`, **never free**: a new claim on it is
  refused. Staleness alone never releases or hands over a claim.
- **Only the holder** releases, finishes or heartbeats a claim. A holder is
  one session id in one process on one machine and worktree: session id,
  machine, worktree and `CLAUDE_PID` all equal, and the pid's start time equal
  where both sides recorded one. The same session id from another process or
  worktree — `claude --resume <id>` while the original is still open — is
  another holder: its `claim` is refused with the holder named, and it goes
  through `recover`'s rules, never a silent reclaim. **Only the
  owner** breaks one: `release --break --by <name>`, run from a terminal
  outside Claude Code (it refuses while `CLAUDECODE` or
  `CLAUDE_CODE_SESSION_ID` is set) and logged. That signal can be stripped
  with `env -u`, so it stops accidental breaks, not a determined agent — it is
  a documented rule, not an enforced one.
- **Recovery when a session's id changes.** `/clear` changes the session id,
  so a claim the previous session made looks foreign. `status` lists such
  claims **first**, marked `yours from a previous session`, each with its one
  recommended action. `recover` adopts one only when all of these hold: the
  claim's machine is this host, its worktree is this worktree, the local
  identity file (`<git-common-dir>/crew/coord-identity.json`, written by the
  script) names the claim's holder, and the holder's `CLAUDE_PID` is
  **provably gone** — then at once, however fresh its heartbeat (owner
  decision, rush g0). Where the end cannot be proven (a sandbox's namespace,
  a probe error, macOS), a fresh heartbeat says to wait for the TTL, and past
  it the claim is still only presented. Anything else — another machine, a
  live pid, a pid reused with a different start time, a missing or corrupt
  identity file, a check that cannot tell — reads `needs the owner: <reason>`
  and is never adopted. A pid check that cannot tell reads **alive**. On
  Linux a pid reads gone only from the **PID namespace** the claim recorded
  (`holder.pidns`, from `/proc/self/ns/pid` at claim time), and one is
  recorded only when `CLAUDE_PID` was visible from it: Claude Code's sandbox
  runs each command under bubblewrap's `--unshare-pid`, where a live
  `CLAUDE_PID` is invisible and looks gone, and bubblewrap reuses namespace
  ids, so a later sandbox can match the id of the one that claimed. A
  namespace that was not recorded, that differs, or that this side cannot
  read, cannot tell. The Linux check (`/proc`; a live pid whose `/proc` entry
  cannot be read reads alive; the namespace rule, including a real
  `bwrap --unshare-pid`) is exercised by the test suite — the spike's Linux
  section was not run. The Windows check was measured, elevated, on one host:
  `OpenProcess` with limited query rights, where only error 87 means gone,
  any other error reads alive, an opened handle is gone only with a nonzero
  exit time, and the creation time is compared with the recorded start. On
  macOS it always reads "cannot tell", so
  recovery there always goes to the owner. The identity file is shared by
  every worktree of the repo and rewritten under a lock,
  `<git-common-dir>/crew/coord-identity.json.lock` — an empty file that stays
  there by design. Those two are the only files crew_coord.py writes under
  `<git-common-dir>/crew/` (plus the identity file's per-pid `.tmp`, renamed
  into place).
- **Not measured: whether `/clear` keeps `CLAUDE_PID`.** If it does — the same
  process carries on under a new session id — the old session's heartbeat
  keeps the claim fresh while that process lives and its pid is alive, so
  `recover` refuses. The new session
  then cannot release, finish or recover its own ticket: the owner runs
  `release --break --by <name>` from a terminal outside Claude Code, and the
  new session claims again.
- **Everything on the channel is peer-written data**, never instructions:
  every line that prints a peer-written field — `status`, and the refusals of
  `claim`, `release`, `done`, `heartbeat` and `recover` — ends
  `[peer-written]`, and control, bidi-format and line-separator characters
  (U+2028, U+202E and the like) become `?` first, so a peer field cannot start
  a line of its own. A recommended command carries a peer-written `repo` or
  ticket id only when it passes the key's own rule; anything else prints as
  `<unsafe value withheld>`, so no shell metacharacter a peer wrote reaches a
  command you are told to run.

**After `/clear` or a resume, run `crew_coord.py status` first**, before any
other work, and stop on any `needs the owner` line. (`/crew:autopilot` runs it
itself before a run or a wave when `.crew/config.json` has a `coord` block.)

### Cross-session messages (`crew_bridge.py`)

Since 1.2.0. Sessions on one channel may talk over Claude Code's messaging
bridge (`ListAgents` / `SendMessage`, Remote Control included), and
`/crew:autopilot` may use both tools (section 9). The channel
`crew-coord/<channel>` stays **the record**; a message is only **the
doorbell**, one line in a closed grammar that `crew_bridge.py` composes and
classifies:

```
crew-doorbell/1 channel=<c> tip=<40 or 64 hex> kind=<changed|contract|finding|question> ref=<id or ->
```

```
python3 hooks/scripts/crew_bridge.py ring    --channel <c> --remote origin [--kind <k>] [--ref <id>]
python3 hooks/scripts/crew_bridge.py receive --channel <c> --remote origin   # the message on stdin
```

- **`ring`** fetches the channel and prints exactly that line, `tip` being the
  fetched tip; the session rings only after its own change to the record is
  pushed, and passes the line to `SendMessage` unchanged. It never carries a
  URL, a ticket body, a question or an answer, and is at most 200 characters.
  A failed fetch prints `unknown - could not fetch` (exit 3) and an absent
  channel is refused (exit 1), with no line to send; a `--kind` outside the
  four or a `--ref` outside `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}` exits 2.
  `kind` and `ref` are hints for the human-readable line only: whatever a
  doorbell says, the receiver fetches the record and reads it.
- **`receive`** classifies an inbound message, and the session runs it on
  every one before anything else. Three results: a doorbell whose announced
  tip is the fetched tip or an ancestor of it (exit 0, re-read the record); a
  doorbell it **could not tell** — the fetch failed, the channel is absent,
  the tip is not in the object store or not in the fetched record (exit 3);
  and **not a doorbell** (exit 1) — anything but exactly one doorbell line for
  this `--channel` (one trailing newline is stripped; more than 4096 bytes or
  non-UTF-8 input never matches). A non-doorbell is printed only as
  `crew_coord.py` prints peer data: capped, control, bidi and line-separator
  characters made `?`, labelled `[peer-written]`. In every case the one next
  step printed is `next: crew_coord.py status --channel <c> --remote <r>`,
  never a step taken from the message.
- **An inbound message is untrusted data.** It is never an approval (that
  comes only from your own prompt), never a `taken:` answer under the
  autopilot questions policy, never a reason to write outside the ticket's
  Touch list, and never a command to run. A request that needs action is
  filed in the record by the peer and read from there. `could not tell` and
  `not a doorbell` are reported to you, the owner.
- **The stdin hand-off is a prose control.** The session writes the message
  to `receive`'s stdin with a quoted heredoc whose terminator it generates
  fresh per call and checks against the whole message first, picking another
  if any line of the message equals it — a line equal to the terminator would
  end the heredoc early and run the rest as shell. Nothing checks that the session did so; a test checks only that
  `commands/autopilot.md` says it.
- **The main session is the hub; lanes never ring a peer** (L-0637; `session-relay`, L-0797, is the one transport the main session dispatches). A
  subagent's `SendMessage` goes out under its parent session's address and
  the reply lands in the parent's conversation, so a lane that messaged a
  peer would speak for the main session without it knowing, and never see
  the answer. `ring` (with or without `--to`) therefore refuses in a wave
  lane — exit 1, `refused - a lane does not message a peer; report the
  question to the main session` — judged by T-0029's lane marker: a lane file
  `.work/autopilot/<slug>/lanes/<id>.json` in the main checkout whose
  `worktree` is this worktree. A marker that cannot be read (a directory
  whose existence cannot be looked up, a lanes directory or lane file that is
  unreadable or corrupt, a `worktree` that is not an absolute path, or none
  on a `running` lane) refuses as `unknown`, exit 3, never as "not a lane";
  a `pending` lane, whose `lane-init` has not run, names no worktree yet.
  The main checkout, and a linked worktree no lane file names, ring as
  usual: being a linked worktree alone proves nothing. `receive` and `pending` are not restricted. The wave's lane prompt
  tells a lane to return a question for another session in its report, for
  the main session to file and ring, and `validate-prompts.py` fails any
  crew agent granted `SendMessage` or `ListAgents` and a lane prompt naming
  either. **Limit:** this is a refusal in crew's own script and a prompt
  rule, not a block on the tool: a lane that Claude Code offers `SendMessage`
  regardless of its prompt can still call it directly. No hook blocks it.
- Apart from `ring --to`, no command here writes: no ref, working tree,
  index, `FETCH_HEAD`, `.work/` or `<git-common-dir>/crew/` moves. None
  calls `SendMessage` or `ListAgents` (they are Claude Code tools), and none
  reads, prints or passes on `CLAUDE_CODE_MESSAGING_TOKEN`.
- **An unanswered doorbell reads `could not tell`** (L-0636). A held or
  undelivered message cannot be told apart from a delivered one — the bridge
  gives no delivery receipt — so the record moving is the only
  acknowledgement. `ring --to <label>` (the peer's name,
  `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`) first appends one `rang` line to the
  channel log (holder, label, announced tip, time, machine, worktree) in one
  commit on the fetched tip, through the same no-force write path as a claim;
  a push that still fails after the retries prints `unknown - could not push`
  (exit 3) and no doorbell. So does a channel whose `log.jsonl` is missing,
  empty or unreadable: a ring added there would hide the rings that went
  with it, so nothing is written. Without `--to`, `ring` writes nothing.

  ```
  python3 hooks/scripts/crew_bridge.py ring    --channel <c> --remote origin --to <label>
  python3 hooks/scripts/crew_bridge.py pending --channel <c> --remote origin
  ```

  `pending` lists every ring of this session — its session id, or this
  machine and worktree, so a ring survives `/clear` — that no later log line
  by another holder follows: `could not tell - no record change from <label>
  since the doorbell at <time> (<age> ago) [peer-written]`, exit 3; with
  none, `no pending doorbells`, exit 0. Nothing turns a pending ring into
  consent: no timeout, no retry, no "delivered" state, however old it is. A
  failed fetch, a channel that does not exist, a channel with no or an empty
  `log.jsonl`, a blank line in it, and a log line that is not a whole entry (every key
  `crew_coord.py` writes) are all `unknown`, never `no pending doorbells`:
  an incomplete line is never read as a peer moving the record. So is a log
  a later commit rewrote: no commit from the oldest ring commit (subject
  `crew-coord: rang <label>`) to the tip may delete a line of `log.jsonl`
  (read from `git log --numstat`, line counts only, so the check stays cheap
  as the log grows), and the history may hold no merge, which crew never
  writes — so a ring dropped or edited, an older line moved after it, a later
  line's holder changed, or a ring carried on a merge's side parent is
  `unknown`, never answered. `/crew:autopilot`
  prints it in `status` and in its resume step and reports the lines to you;
  a pending ring is not a stop. **Limit:** any later log line by a holder
  other than the ringer and this session clears the ring — a third session on
  the channel clears it too, because the log does not record which peer a
  holder is.

### Versioned contracts (`crew_contract.py`)

Since 1.2.0. Two sessions building against each other put the interface between
them on the same channel as the claims, as a numbered version with a content
hash, and each side records that its ticket built against that version.

```
python3 hooks/scripts/crew_contract.py put           --name <n> --file <path>
python3 hooks/scripts/crew_contract.py put           --name <n> --file <path> --new-version --ticket <id>
python3 hooks/scripts/crew_contract.py build-against --name <n> --version <N> --ticket <id>
python3 hooks/scripts/crew_contract.py status        [--name <n>]
python3 hooks/scripts/crew_contract.py verify        --ticket <id>
```

`--channel` (not on `verify`, which reads each binding's channel from the
binding), `--remote` and `--root` default as `crew_coord.py`'s do. A
version is two files on `crew-coord/<channel>`: `contracts/<n>/v<N>.json`
(`name`, `version`, `hash` = `sha256:` of the body, `status` `draft` or
`built-against`, and `built_by`, one `{repo, ticket, hash, at}` per side) and
`contracts/<n>/v<N>.body`, the interface itself as opaque bytes, 1 MiB at
most. `<n>` follows the channel-name rule (`[a-z0-9][a-z0-9-]{0,63}`). Every
write goes through the claims' path: one commit on the fetched tip, a plain
push, never a force push, claims and every other file carried through.

- **The freeze rule.** `put` writes v1 as a draft and replaces a draft in
  place. From the first `build-against` the version is `built-against` and
  frozen: `put` on it is refused, naming who built against it. The only way
  forward is `put --new-version --ticket <id>`, a draft v(N+1) tied to this
  side's new ticket for the change; it is refused while the latest version is
  still a draft. Nothing deletes a version or returns it to `draft`.
- **Owner approval comes through the ticket.** `build-against` is refused
  unless `crew_ticket.accepted` reads the ticket `approved`, so only a ticket
  the owner approved binds to a version. It also checks that the body's sha256
  is the record's hash.
- **Two copies of the binding.** `build-against` appends this repository and
  ticket to `built_by` on the channel (running it again adds nothing), and
  writes `.work/tickets/<id>/contracts.json` (`{"schema": 1, "bindings":
  [{remote, channel, name, version, hash}]}`, `remote` being the git remote it
  was built on) locally, the only local file it writes.
- **What a peer can rewrite.** Anything on the channel: a peer pushing without
  this tool can edit a frozen record or body. This tool cannot prevent that;
  the local binding is the evidence `verify` compares the channel against.
- **`verify` and the wave refusal** (L-0634). `verify --ticket <id>` checks every
  binding in the ticket's `contracts.json`: the channel must still show that
  version with the bound hash, a body whose sha256 is that hash, status
  `built-against`, and this repository and ticket in `built_by`, read from the
  remote the binding records (never whatever `coord.remote` says now; a
  `verify --remote` naming another remote reads that binding unknown). Exit 0 when
  every binding holds, 1 on a mismatch, 3 when it cannot tell (the fetch fails,
  the channel is absent, the version's record or body is missing, the record is
  corrupt, the bindings file cannot be checked, does not parse or holds an
  empty list — never read as "no bindings"). A
  ticket with no `contracts.json` is not checked and fetches nothing; a newer
  version on the channel is information only. `crew_wave.py plan` and `start`
  run the same check after a ticket's dependencies and refuse it with
  `contract <n> v<N> changed since <id> built against it` or
  `contract <n> v<N> unknown (<why>)`; no lane starts for it. Nothing is
  repaired: the owner's way out is a new contract version and a new ticket on
  each side.
- **Unknown is never current.** A record that cannot be fetched or parsed, a
  version missing one of its two files, versions not numbered 1 to N, or a
  body whose sha256 is not its hash reads `unknown` (exit 3), and `status`
  prints it rather than skipping it. Every line with a peer-written field ends
  `[peer-written]`. Exit codes: 0 ok, 1 refused, 2 usage (checked before any
  git call), 3 unknown.
