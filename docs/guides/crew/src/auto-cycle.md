# Auto wrap-up, auto-clear and auto-resume

This section is folded into the troubleshooting guide (`troubleshooting.md`), linked from it as
"Auto wrap-up, clear and resume". It covers the cycle that lets a long session finish itself
cleanly, clear, and pick up where it stopped.

## What the cycle does

1. **Wrap-up.** When the context window crosses its threshold, the `Stop` hook blocks once. It asks
   the session to finish or park the change in flight, write `.work/HANDOFF.md`, and update the
   ticket. This happens once for each threshold crossing in each session. It never happens on the
   forced continuation that follows a block.
2. **Clear, or notify.** After the handoff is written, auto-clear acts on it. What it does depends
   on `method` (below): `notify` (the default on native Windows) prints a message telling you the
   handoff is written and it is safe to run `/clear` (or `/compact`) yourself — it types nothing.
   `tmux`, `xdotool` and `sendkeys` actually type the configured command into the terminal that runs
   this session. Whichever method is in force, it acts only when all four of these hold:
   - this machine opted in;
   - the handoff was written by this session after the wrap-up request, is longer than a stub, and
     is not the automatic PreCompact skeleton;
   - the context reading that caused the wrap-up was a real measurement (see "When it will not
     clear");
   - for a method that types (`tmux`/`xdotool`/`sendkeys`), the target window can be identified
     exactly — `notify` needs none of this, since it identifies no window.

   **Crew neither causes nor tunes Claude Code's own auto-compact.** That is a separate, built-in
   behaviour that fires whenever Claude Code itself decides to; this cycle only reacts to a handoff
   once one exists, and nothing here makes auto-compact happen sooner, later, or at all.
3. **Resume.** The new session starts with the handoff and its next action already in context,
   within the 3,000-character resume budget. Nothing starts working unprompted: crew does not use
   `initialUserMessage`, so you press Enter to continue.

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
| `.crew/config.json` | `context.autoWrapUp` | `false` | replaces the wrap-up instruction with a plain handoff request. It still blocks once. |
| `.crew/config.json` | `context.enabled` | `false` | turns off the whole context watcher, wrap-up included |
| `.crew/config.json` | `memory.inject` | `false` | `handoff-read` prints the handoff for you to read, without extracting the next action. `context.autoResume` is no longer read. |

`/crew:config` shows where each value comes from and walks you through the global file. To turn the
cycle off on a machine, set `context.autoClear.enabled` to `false` or delete the key.

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
| `tmux` | Types the command into the `$TMUX_PANE` that is an ancestor of the hook. No focus involved — the most reliable method. | Linux, macOS, WSL, Git Bash on Windows, when `$TMUX` names a pane and `tmux` is on PATH |
| `xdotool` | Types into the one X11 window owned by the nearest ancestor process (or matching `windowTitle`). | Linux with `xdotool` on PATH and `$DISPLAY` set |
| `notify` | Types nothing. Prints a message saying the handoff is written and verified and it is safe to run the command yourself. Never says anything was cleared or compacted — it does not know that, and it did not do it. | **native Windows**, whenever there is no tmux pane — this is the default there, not a fallback for something missing |
| `sendkeys` | `System.Windows.Forms.SendKeys` against the one window owned by an ancestor process (or matching `windowTitle`), confirmed still in the foreground right before typing. **`auto` never picks this** — typing into a window this hook found itself is a risk `auto` does not get to accept on your behalf. Set `method: "sendkeys"` explicitly to opt in. Even then, it declines and falls back to `notify` — logging why — when the target window is owned by Windows Terminal, because that host puts every tab in one window and nothing outside it can confirm which tab is active. | never (opt-in only) |
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
| `no window belongs to any ancestor of this hook` | the terminal's window could not be found by process id, and no `windowTitle` is set (`sendkeys`/`xdotool` only) |
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

- **tmux (Linux, macOS, WSL):** the pane in `$TMUX_PANE`, and only when that pane's process is an
  ancestor of the hook. No title is needed. This is the most reliable method.
- **X11 (`xdotool`):** the one visible window owned by the nearest ancestor process of the hook. If
  that process owns more than one window, `windowTitle` has to narrow the choice to one. If no
  ancestor owns a window, exactly one window must match `windowTitle`. The keystroke goes to that
  window id after it is activated and confirmed active.
- **Windows (`sendkeys`):** chosen the same way, by owner process first and then by title. Declines
  outright, before any of that matters, when the resolved window is owned by Windows Terminal — see
  the method table above. Otherwise, after the delay, the command is sent only when that exact
  window handle still has focus; if it does not, nothing is typed and the decline is logged.

Windows Terminal runs every tab in one window. A process-id match cannot tell which tab is active,
so on Windows Terminal set `windowTitle` to something only this session's tab shows.
