# Auto wrap-up, auto-clear and auto-resume

This section is folded into the troubleshooting guide (`troubleshooting.md`), linked from it as
"Auto wrap-up, clear and resume". It covers the cycle that lets a long session finish itself
cleanly, clear, and pick up where it stopped.

## What the cycle does

1. **Wrap-up.** When the context window crosses its threshold, the `Stop` hook blocks once. It asks
   the session to finish or park the change in flight, write `.work/HANDOFF.md`, and update the
   ticket. This happens once for each threshold crossing in each session. It never happens on the
   forced continuation that follows a block. With `context.autoClear.wrapUp` armed (below), the
   block carries the wrap-up procedure instead, and the clear waits for its results.
2. **Clear, or notify.** After the handoff is written, auto-clear acts on it. What it does depends
   on `method` (below): `notify` (the default on native Windows) prints a message telling you the
   handoff is written and it is safe to run `/clear` (or `/compact`) yourself — it types nothing.
   `tmux`, `xdotool` and `sendkeys` actually type the configured command into the terminal that runs
   this session. Whichever method is in force, it acts only when all five of these hold:
   - this machine opted in;
   - the handoff was written by this session after the wrap-up request, is longer than a stub, and
     is not the automatic PreCompact skeleton;
   - the context reading that caused the wrap-up was a real measurement (see "When it will not
     clear");
   - this session is bound to its own Claude Code process, and that process has a terminal of its
     own (see "Which window gets the keystroke") — a headless session, such as a `claude -p` child,
     gets one message instead, naming its handoff and saying the process that started it must
     start a new one;
   - for a method that types (`tmux`/`xdotool`/`sendkeys`), the target window can be identified
     exactly, from that process — `notify` needs none of this, since it identifies no window.

   **Crew neither causes nor tunes Claude Code's own auto-compact.** That is a separate, built-in
   behaviour that fires whenever Claude Code itself decides to; this cycle only reacts to a handoff
   once one exists, and nothing here makes auto-compact happen sooner, later, or at all.
3. **Resume.** The new session starts with the handoff and its next action already in context,
   within the 3,000-character resume budget. Nothing starts working unprompted: crew does not use
   `initialUserMessage`, so you press Enter to continue. Claude Code 2.1.282 drops it in an
   interactive session anyway (spike, 2026-09-25): it is honoured by `claude -p` only.

   With **`resume.auto: true`** in the machine-global config, the handoff after `/clear` or a manual
   `/compact` also names the exact next command, read from the note's `resume:` line
   (`resume: /crew:done T-0001`): `Auto-resume: ready to run /crew:done T-0001.` — or
   `Auto-resume did not start: <reason>.` when a check refuses it. It does not start from the hook:
   you press Enter or type it, or crew types it where the terminal can be identified (below). The
   refusal reasons are: compact was not a manual /compact; no handoff note, or it was archived as
   stale, or is stale and could not be archived; the handoff is the automatic PreCompact skeleton;
   no resume line, `resume: none`, or a line the grammar refuses (a second line, trailing text, an
   unknown command, or an excluded one such as `/crew:approve`); the note's `branch:` or `head:`
   does not match the checkout; the ticket directory or goal file is missing; the command is not
   installed; `handoff-author.json` could not be read; no record of which session wrote this
   handoff; a later handoff write could not replace or remove `handoff-author.json` (`handoff-author.json.stuck`), or the file and its directory are both read-only so it can be neither replaced nor removed; the handoff changed since its author session wrote it; the handoff was written by
   another session; this session's process could not be identified (always on a host without
   `/proc`, such as native Windows or macOS); the record of past auto-resumes (`resume-state.json`)
   could not be read, or its directory cannot be searched; this handoff was already resumed; the
   progress fingerprint could not be computed; the same command with no progress since the last
   auto-resume; `internal error` (the decision itself failed, and the handoff is still injected).
   Never on a plain `startup`.

   **Crew types it where it can (T-0013).** The context hook runs its own flavour's `auto-clear`
   sender in resume mode. Consent is `resume.auto`; `context.autoClear` only describes the terminal.
   In tmux it waits `resume.typeDelaySeconds` (default 2), polls the pane for an idle, empty input
   line for up to `resume.readyTimeoutSeconds` (default 15), then sends the command and, half a
   second later, Enter. On native Windows it types only under an explicit `method: sendkeys`, after
   the delay, with the focus and tab rechecks; `auto` there types nothing. It types once per
   handoff (a marker under `<git-common-dir>/crew/`) and records the run first, so a run that could
   not be recorded is never typed. The context then says `Auto-resume: typing /crew:done T-0001 into
   this session in 2s (method tmux)`, or keeps the line above and adds `Auto-resume was not typed:
   <reason>.` Every refusal is in `.crew/.autoclear.log`: decide did not say run; no usable method,
   `$TMUX` unset or a pane that is not this session's; `wtype` or `xdotool`; already typed; the run
   could not be recorded; the input line is not empty; not ready in time; on Windows, focus lost or
   a tab not provable. The 2 s default comes from a measurement (input ready by 0.134 s after
   SessionStart on Claude Code 2.1.282); a delay is still a guess, and Windows has no probe.

   A note resumes only in the session that wrote it. Write it with the Write tool (as
   `/crew:handoff` does): the context hook then records which session and which Claude Code process
   wrote it. After `/compact` the session must match; after `/clear` the process must, so a `/clear`
   in another terminal on the same worktree waits. A note written by Bash or by hand waits.

## Turning it on and off

Wrap-up and resume are on by default. Auto-clear is **off** by default. You turn it on per machine,
in the machine-global config, because it drives this machine's keyboard:

| Where | Key | Value | Effect |
|---|---|---|---|
| `~/.claude/crew/config.json` (Windows: `%USERPROFILE%\.claude\crew\config.json`) | `context.autoClear.enabled` | `true` | turns auto-clear on for every crew repo on this machine |
| same | `context.autoClear.method` | `"auto"` (default), `"tmux"`, `"xdotool"`, `"notify"`, `"sendkeys"`, `"none"` | how the cycle acts — see "Which method, and what it does" below |
| same | `context.autoClear.windowTitle` | a substring of the terminal's title | fallback when the window cannot be found by process id |
| same | `context.autoClear.delaySeconds` | `3` | wait before typing, so the prompt exists |
| same | `context.autoClear.minHandoffLines` | `5` | a shorter handoff counts as a stub |
| `.crew/config.json` (the repo) | `context.autoClear.enabled` | `false` | switches auto-clear off in this repo. A repo can switch it off, but `true` here does not switch it on. |
| `~/.claude/crew/config.json` | `resume.auto` | `true` | names the next command from the handoff's `resume:` line after `/clear` or a manual `/compact` (off by default) |
| `.crew/crew.json` or `.crew/config.json` (the repo) | `resume.auto` | `false` | vetoes auto-resume in this repo. `true` here does not switch it on. |
| `~/.claude/crew/config.json` | `context.autoClear.wrapUp` | `true` | turns the wrap-up into the wrap-up procedure and makes the clear wait for its results (off by default; acts only where `enabled` is armed). A repo `false` vetoes it; a repo `true` does nothing. |
| `.crew/config.json` | `context.autoWrapUp` | `false` | replaces the wrap-up instruction with a plain handoff request. It still blocks once. Armed `wrapUp` supersedes both wordings. |
| `.crew/config.json` | `context.enabled` | `false` | turns off the whole context watcher, wrap-up included |
| `.crew/config.json` | `memory.inject` | `false` | `handoff-read` prints the handoff for you to read, without extracting the next action. `context.autoResume` is no longer read. |

`/crew:config --show` shows where each value comes from. `/crew:config` with no argument (or
`/crew:config-setup`) opens a menu that sets either file from a list of values, with a dry run
before anything is written. To turn the cycle off on a machine, set `context.autoClear.enabled` to
`false` or delete the key. In a repo the menu offers only the veto (`false`) or `null` for
`context.autoClear.enabled` and `resume.auto`, and shows `onlyRepos`/`onlySessions` read-only,
because only the machine file can arm or narrow them.

### Armed wrap-up (`context.autoClear.wrapUp`)

A hook cannot make the session do anything; it can only refuse to clear. So with `wrapUp` armed the
threshold block sends one procedure — start no new step; run the step's `Test:` command (the
active ticket's plan step, or the checks for the tracked diff with no ticket); commit only if it
passes; if it cannot pass, leave the tree and write `resume: none` with the reason under **Verify
first**; run `/crew:handoff --wrap-up`; end the turn — and auto-clear acts only when, beside the
checks above:

- the handoff's `head:` is HEAD, so it was written after the commit;
- its `branch:` is the checked-out branch;
- no tracked file is modified (untracked files, and the handoff itself, do not count);
- its `resume:` line parses, or is `resume: none`.

Anything crew cannot tell — git failing, no `crew_resume`, on native Windows no python — refuses.
A refusal is logged, shown to you as `crew wrap-up: not clearing - <reason>`, and handed back to
the session once, at its next ordinary Stop. Crew checks that the commit happened, not that the
test passed: the verify gate stands down on the turn the commit is made on.

The chain end to end: wrap-up (T-0017) → the target proven from this session's own process
(T-0016) → clear → `resume.auto` decides (T-0006) → the command is typed (T-0013).

### Arming one scratch repo while other sessions are live

`enabled: true` arms auto-clear in **every** Claude session on the machine, not just the one you
are testing. If other sessions are running, one of them can get `/clear` typed into its terminal
when its own handoff lands. To limit auto-clear to one repo or one session, add these keys to the
same machine file. They can only narrow what `enabled` turns on:

| Key | Value | Effect |
|---|---|---|
| `context.autoClear.onlyRepos` | list of absolute repo paths | auto-clear runs only in these repos |
| `context.autoClear.onlySessions` | list of session ids | auto-clear runs only in these sessions |

- A missing key or `null` does not narrow anything. An empty list `[]` turns auto-clear off
  everywhere. If a key holds anything other than a list, auto-clear is off everywhere too.
- When both keys are set, a session must match both.
- Paths are compared after symlinks are resolved. Backslashes and trailing separators do not
  matter. On Windows, case does not matter and `/c/repos/x` means `C:\repos\x`. A relative path such
  as `.` never matches.
- Session ids must match exactly, including case.
- These keys are read **only** from the machine file. If a repo's `.crew/config.json` sets them, they
  are ignored, so a repo cannot add itself. A repo's `enabled: false` still turns auto-clear off.
- In any other repo or session, auto-clear stays silent. It does not write a log line, just as it
  does when `enabled` is off.

To arm one scratch repo safely:

```json
{
  "context": {
    "autoClear": {
      "enabled": true,
      "onlyRepos": ["C:\\repos\\autoclear-scratch"]
    }
  }
}
```

On Linux, use a path such as `"/home/you/autoclear-scratch"`. When you are done testing, remove
`enabled` or set it to `false`. Also delete `onlyRepos`, so that a later `enabled: true` does not
arm only that repo without anyone noticing.

## Which method, and what it does

| Method | What it does | Where `auto` picks it |
|---|---|---|
| `tmux` | Types the command into the `$TMUX_PANE` whose process is this session's own process or an ancestor of it. No focus involved — the most reliable method. | Linux, macOS, WSL, Git Bash on Windows, when `$TMUX` names a pane and `tmux` is on PATH |
| `xdotool` | Types into the one X11 window owned by the nearest ancestor of this session's own process, when that window hosts no other terminal (or matching `windowTitle`). | Linux with `xdotool` on PATH and `$DISPLAY` set |
| `notify` | Types nothing. Prints a message saying the handoff is written and verified and it is safe to run the command yourself. Never says anything was cleared or compacted — it does not know that, and it did not do it. | **native Windows**, whenever there is no tmux pane — this is the default there, not a fallback for something missing |
| `sendkeys` | `System.Windows.Forms.SendKeys` against the one window owned by an ancestor of this session's own process (or matching `windowTitle`), confirmed still in the foreground right before typing. **`auto` never picks this** — typing into a window this hook found itself is a risk `auto` does not get to accept on your behalf. Set `method: "sendkeys"` explicitly to opt in. Even then, it declines and falls back to `notify` — logging why — when the target window is owned by Windows Terminal, because that host puts every tab in one window and nothing outside it can confirm which tab is active. | never (opt-in only) |
| `none` | Refused outright. | never |

## When it will not clear (or notify)

Each refusal is logged with its reason to `.crew/.autoclear.log`. A Stop hook's stderr is not shown
to you, so check that log first. A `notify` or `sendkeys` decline is logged the same way — "declined"
rather than "refusing", since the machine has opted in and something still happened (a message, or a
fallback), just not a keystroke.

| Log says | Meaning |
|---|---|
| `not trustworthy (estimated-from-transcript-size)` | no usage record was found, so the reading was an estimate |
| `not trustworthy (unknown-window)` | the model's context window is unknown and `context.budgetTokens` is not set |
| `not trustworthy (stale-reading-before-compaction)` | the last reading came from before a compaction |
| `the wrap-up marker is empty or not JSON` | the marker was not written by this version of the hook. Nothing clears on it. |
| `predates this session's wrap-up request` | the handoff on disk is older than the request, probably left by an earlier session |
| `automatic PreCompact skeleton` | only the compaction skeleton exists, not a real handoff |
| `N windows have a title containing ...` / `has N windows` | the window is ambiguous, so nothing is typed (`sendkeys`/`xdotool` only) |
| `no window belongs to any ancestor of this hook` / `... of this session's process` | the terminal's window could not be found by process id, and no `windowTitle` is set (`sendkeys`/`xdotool` only) |
| `sent - method notify-headless: crew: this session has no terminal of its own (...)` | a headless session (`claude -p`: entrypoint `sdk-cli`, or no controlling terminal): nothing was typed, and the message names the handoff and its `resume:` line. The process that started the session restarts it |
| `could not identify this session's process (...)` | no Claude Code session record names a process above the hook with this session's id and start time (or the record is unreadable, or names another session). Nothing is typed; `auto` falls back to `notify` |
| `could not tell whether this session has a terminal of its own (entrypoint '...' ...)` | the session record's entrypoint is not one measured to have a terminal (only `cli` is). Nothing is typed; `auto` falls back to `notify` |
| `passes through another Claude Code session (pid N)` | this session is a child of another session, and the pane or window above it is the parent's |
| `the window's owner (pid N) also hosts another terminal` / `another Claude Code session` | the terminal that owns the window also runs another tab or session, so the window is not provably this one's |
| `could not be listed` / `the parent of pid N could not be read` / `deeper than 16 processes` | the process tree could not be read far enough to prove anything |
| `found by its title alone, and another Claude Code session is live` / `has no owning process` | a `windowTitle` match (or a window with no process) cannot tell two sessions apart |
| `tmux pane %N could not be confirmed` | `$TMUX_PANE` is not the pane that runs this session |
| `method wtype ... is refused` | Wayland's `wtype` cannot target a window. Use tmux instead. |
| `sent - method notify` | the message was printed — this is the normal, successful outcome for `notify` |
| `declined sendkeys - cannot verify the active tab ...` | the target window is owned by Windows Terminal; `sendkeys` fell back to `notify` instead of guessing which tab is active |
| `declined sendkeys - the target window lost focus during the ...s delay` | the window had focus when identified, but not when the delay ended, so nothing was typed |

Two sessions in one repository no longer interfere with each other. Wrap-up markers are
`.crew/.handoff-requested-<session_id>`, and a SessionStart clears only its own session's marker.

## Which window gets the keystroke

Applies only to the methods that type — `tmux`, `xdotool`, `sendkeys`. `notify` identifies no window
and needs none of this.

First, the session is bound to its own process: the nearest ancestor of the hook named by a Claude
Code session record (`${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json`) carrying this session's
id and that process's start time. Only a session whose record says kind `interactive` and
entrypoint `cli`, with a controlling terminal (native Windows has none to read), is typed into.
Every rule below walks up from that process, not from the hook, and refuses when the walk passes
through another Claude Code session — a child started from a session's Bash tool inherits `$TMUX`,
and without this its parent's pane is the one that got `/clear`. CONFIG.md §14 has the full rules and
their limits (Windows' entrypoint is unmeasured; macOS cannot check the start time).

- **tmux (Linux, macOS, WSL):** the pane in `$TMUX_PANE`, and only when that pane's process is this
  session's own process or an ancestor of it. No title is needed. This is the most reliable method.
- **X11 (`xdotool`):** the one visible window owned by the nearest ancestor of the session's process,
  and only when no other terminal (another tab's tty, another session) runs under that window's
  owner. If
  that process owns more than one window, `windowTitle` has to narrow the choice to one. If no
  ancestor owns a window, exactly one window must match `windowTitle`, and no other session may be
  live, since a title cannot tell two apart. The keystroke goes to that
  window id after it is activated and confirmed active.
- **Windows (`sendkeys`):** chosen the same way, by owner process first and then by title. Declines
  outright, before any of that matters, when the resolved window is owned by Windows Terminal — see
  the method table above. Otherwise, after the delay, the command is sent only when that exact
  window handle still has focus; if it does not, nothing is typed and the decline is logged.

Windows Terminal runs every tab in one window. A process-id match cannot tell which tab is active,
so on Windows Terminal set `windowTitle` to something only this session's tab shows.
