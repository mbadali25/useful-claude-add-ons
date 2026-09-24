# Auto wrap-up, auto-clear and auto-resume

This section is folded into the troubleshooting guide (`troubleshooting.md`), linked from it as
"Auto wrap-up, clear and resume". It covers the cycle that lets a long session finish itself
cleanly, clear, and pick up where it stopped.

## What the cycle does

1. **Wrap-up.** When the context window crosses its threshold, the `Stop` hook blocks once. It asks
   the session to finish or park the change in flight, write `.work/HANDOFF.md`, and update the
   ticket. This happens once for each threshold crossing in each session. It never happens on the
   forced continuation that follows a block.
2. **Clear.** After the handoff is written, auto-clear types `/clear` into the terminal that runs this
   session. It does this only when all four of these hold:
   - this machine opted in;
   - the handoff was written by this session after the wrap-up request, is longer than a stub, and
     is not the automatic PreCompact skeleton;
   - the context reading that caused the wrap-up was a real measurement (see "When it will not
     clear");
   - the target window can be identified exactly.
3. **Resume.** The new session starts with the handoff and its next action already in context,
   within the 3,000-character resume budget. Nothing starts working unprompted: crew does not use
   `initialUserMessage`, so you press Enter to continue.

## Turning it on and off

Wrap-up and resume are on by default. Auto-clear is **off** by default. You turn it on per machine,
in the machine-global config, because it drives this machine's keyboard:

| Where | Key | Value | Effect |
|---|---|---|---|
| `~/.claude/crew/config.json` (Windows: `%USERPROFILE%\.claude\crew\config.json`) | `context.autoClear.enabled` | `true` | turns auto-clear on for every crew repo on this machine |
| same | `context.autoClear.method` | `"auto"` (default), `"tmux"`, `"xdotool"`, `"windows"`, `"none"` | how the keystroke is delivered |
| same | `context.autoClear.windowTitle` | a substring of the terminal's title | fallback when the window cannot be found by process id |
| same | `context.autoClear.delaySeconds` | `3` | wait before typing, so the prompt exists |
| same | `context.autoClear.minHandoffLines` | `5` | a shorter handoff counts as a stub |
| `.crew/config.json` (the repo) | `context.autoClear.enabled` | `false` | switches auto-clear off in this repo. A repo can switch it off, but `true` here does not switch it on. |
| `.crew/config.json` | `context.autoWrapUp` | `false` | replaces the wrap-up instruction with a plain handoff request. It still blocks once. |
| `.crew/config.json` | `context.enabled` | `false` | turns off the whole context watcher, wrap-up included |
| `.crew/config.json` | `memory.inject` | `false` | `handoff-read` prints the handoff for you to read, without extracting the next action. `context.autoResume` is no longer read. |

`/crew:config` shows where each value comes from and walks you through the global file. To turn the
cycle off on a machine, set `context.autoClear.enabled` to `false` or delete the key.

## When it will not clear

Each refusal is logged with its reason to `.crew/.autoclear.log`. A Stop hook's stderr is not shown
to you, so check that log first.

| Log says | Meaning |
|---|---|
| `not trustworthy (estimated-from-transcript-size)` | no usage record was found, so the reading was an estimate |
| `not trustworthy (unknown-window)` | the model's context window is unknown and `context.budgetTokens` is not set |
| `not trustworthy (stale-reading-before-compaction)` | the last reading came from before a compaction |
| `the wrap-up marker is empty or not JSON` | the marker was not written by this version of the hook. Nothing clears on it. |
| `predates this session's wrap-up request` | the handoff on disk is older than the request, probably left by an earlier session |
| `automatic PreCompact skeleton` | only the compaction skeleton exists, not a real handoff |
| `N windows have a title containing ...` / `has N windows` | the window is ambiguous, so nothing is typed |
| `no window belongs to any ancestor of this hook` | the terminal's window could not be found by process id, and no `windowTitle` is set |
| `tmux pane %N could not be confirmed` | `$TMUX_PANE` is not the pane that runs this session |
| `method wtype ... is refused` | Wayland's `wtype` cannot target a window. Use tmux instead. |

Two sessions in one repository no longer interfere with each other. Wrap-up markers are
`.crew/.handoff-requested-<session_id>`, and a SessionStart clears only its own session's marker.

## Which window gets the keystroke

- **tmux (Linux, macOS, WSL):** the pane in `$TMUX_PANE`, and only when that pane's process is an
  ancestor of the hook. No title is needed. This is the most reliable method.
- **X11 (`xdotool`):** the one visible window owned by the nearest ancestor process of the hook. If
  that process owns more than one window, `windowTitle` has to narrow the choice to one. If no
  ancestor owns a window, exactly one window must match `windowTitle`. The keystroke goes to that
  window id after it is activated and confirmed active.
- **Windows (SendKeys):** chosen the same way, by owner process first and then by title. After the
  delay, `/clear` is sent only when that exact window handle has focus.

Windows Terminal runs every tab in one window. A process-id match cannot tell which tab is active,
so on Windows Terminal set `windowTitle` to something only this session's tab shows.
