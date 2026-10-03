# T-0013 step 1 spike: when an interactive session accepts typed keys after SessionStart

Run 2026-09-25, Claude Code **2.1.282**, Linux, tmux 3.6, `--model claude-haiku-4-5-20251001`, 160x45 pane.
Raw evidence (ephemeral) is in the session scratchpad `spike-t0013/logs/`: hooklog.jsonl, results.jsonl, and frames-<tag>.jsonl (capture-pane -e every 100 ms for 6 s after each SessionStart).
Scripts are beside them: hook_ss.py, sender.py, frames.py and driver.py.

## Result

**Readiness is not what fails. Paste detection is.** In every condition, the keys sent at D=0 (about 20-70 ms after the SessionStart hook ran) were taken, provided the text and the Enter arrived in separate reads.
The only failure seen does not depend on D. When the text is longer than about 60 characters and it arrives in the **same read** as the Enter, Claude Code handles the burst as a paste. The Enter becomes a newline in the input box, and nothing is submitted.
auto-clear.sh sends `send-keys -l <text>` and then `send-keys Enter` back to back (`auto-clear.sh:195-196`). Under CPU load those two calls can coalesce into one read. That happened in 3 of 8 long-text runs, all of them `/compact`.

- Earliest reliable D, worst case: **0 s**. Nothing was lost, garbled or typed into a redraw at any D from 0 to 5 s once text and Enter were separated.
- Worst observed "first ready frame" after the hook: **0.134 s** (clear), **0.133 s** (compact). Once ready, no frame went back to not-ready before the send: 0 flips in 1088 pre-send frames.
- `resume.typeDelaySeconds` by the plan's rule, ceil(2 x t_ready_max) with a floor of 2: ceil(0.27) = 1, so the floor applies and the value is **2**.
- New requirement for step 3, which the plan does not have: in the tmux sender, put **at least 0.3 s** between `send-keys -l <text>` and `send-keys Enter`. 0.5 s is suggested for margin. Then re-probe: if the input line still holds the text, log "typed but not submitted" and stop.

## Isolation

- `HOME` was a scratch directory. Its `.claude/` held only `.credentials.json` (the `claudeAiOauth` entry, copied), a minimal `.claude.json` (onboarding done, the scratch repo trusted) and a `settings.json` with no plugins and no hooks.
- The environment was built with `env -i` (HOME, PATH, TERM, LANG, SHELL, USER only). None of the parent's `CLAUDE_CODE_*` variables, the messaging socket among them, reached the child. The tmux server was private (`-L spike-t0013-575eb00f`).
- The only hooks were the scratch repo's project hooks. Afterwards the scratch repo had no `.crew/` and no `.work/`. Every UserPromptSubmit was a probe or the driver's own `say hi` filler. No cross-session message arrived.
- Not fully empty: at startup Claude Code synced the org's plugins into the scratch home (`plugins/synced/...`, `skills/synced/...`) and cloned the official marketplace. None of them was enabled. The only hook among them is `render`'s PostToolUse on Edit|Write, which cannot fire here. Claude Code also rewrote the scratch `settings.json`: it dropped `crossSessionInbound` and added `env.DISABLE_AUTOUPDATER`.
- The scratch home, including the copied credentials, and the scratch repo were deleted afterwards. The tmux server was killed and its socket removed. No claude, driver or load process remains.

## Method

- A SessionStart hook (matchers `clear`, `compact`, and `startup` for the log only) appends `{t, source, session_id, pane}` and spawns two detached processes (`start_new_session`, fds closed), then returns in about 1 ms.
  - A sender sleeps D and then runs `tmux send-keys -t $TMUX_PANE -l '/spike-ping <tag>'` followed by `send-keys Enter`, as two separate calls, the way auto-clear.sh does it.
  - A frame recorder runs `capture-pane -p -e` every 100 ms for 6 s.
- A UserPromptSubmit hook logs the raw prompt with its timestamp. That entry is the SPIKE-OK record.
  - `ok` means exactly one prompt, byte-equal to the text sent.
  - `lost` means no prompt. In every lost run, the screen showed the text still in the input box with a trailing newline.
  - No run came out `garbled`.
- The driver waits until the pane is idle, arms the D, types `/clear` or `/compact` + Enter, disarms on SessionStart, and scores the run.
- `sentinel` mode follows the plan's variant: `echo-<tag>` with no Enter, checked in the input line 2 s later, then cleared.

## Table: D x source x condition

Latency is the worst submit time measured from the SessionStart hook (UserPromptSubmit time minus hook time).

| cond | source | D (s) | text / send | ok/n | worst latency (s) |
|---|---|---|---|---|---|
| A | clear | 0 | short, split | 3/3 | 0.081 |
| A | clear | 0.25 | short, split | 3/3 | 0.321 |
| A | clear | 0.5 | short, split | 3/3 | 0.577 |
| A | clear | 1 | short, split | 3/3 | 1.074 |
| A | clear | 2 | short, split | 3/3 | 2.098 |
| A | clear | 3 | short, split | 3/3 | 3.093 |
| A | clear | 5 | short, split | 3/3 | 5.074 |
| A | compact | 0 | short, split | 4/4 | 0.069 |
| A | compact | 0.25 | short, split | 3/3 | 0.315 |
| A | compact | 0.5 | short, split | 3/3 | 0.576 |
| A | compact | 1 | short, split | 3/3 | 1.073 |
| A | compact | 2 | short, split | 3/3 | 2.067 |
| A | compact | 3 | short, split | 3/3 | 3.083 |
| A | compact | 5 | short, split | 3/3 | 5.057 |
| A | clear / compact | 0, 0.25 | sentinel, no Enter | 6/6, 6/6 | - |
| B | clear | 0 / 1 / 2 | short, split | 3/3 each | 3.065 |
| B | compact | 0 / 1 / 2 | short, split | 3/3 each | 3.044 |
| B | clear / compact | 0 | sentinel | 3/3, 3/3 | - |
| C | clear / compact | 0 | 215 chars, split | 3/3, 3/3 | 0.102 |
| C | clear / compact | 0 | 215 chars, split + 0.3 s gap | 3/3, 3/3 | 0.389 |
| D | clear / compact | 0 | short, split | 5/5, 5/5 | 0.539 |
| D | clear | 0 | 215 chars, split | 4/4 | 0.653 |
| **D** | **compact** | **0** | **215 chars, split** | **1/4** | - |
| D | clear / compact | 0 | 215 chars, split + 0.3 s gap | 4/4, 4/4 | 0.787 |
| E | clear / compact | 0 | short (about 34 chars), one burst | 1/1, 1/1 | 0.081 |
| E | clear | 1 | 40 / 60 chars, one burst | 1/1, 2/2 | 1.079 |
| E | clear | 1 | 65 / 70 / 75 / 80 / 100 / 120 / 150 chars, one burst | 0/1, 0/2, 0/1, 0/1, 0/1, 0/1, 0/1 | - |
| E | clear / compact | 0 and 1 | 215 chars, one burst | 0/2, 0/2 | - |
| F | clear / compact | 0 | short, split | 3/3, 3/3 | 0.304 |
| F | clear | 0.5 | sentinel | 1/1 | - |

Conditions:

- **A**: base sweep, no load.
- **B**: a sibling SessionStart hook that sleeps 3 s. This models crew's context hook or another plugin's hook.
- **C**: 215-character text, no load.
- **D**: 24 busy loops on 20 cores, load average 25-40.
- **E**: text and Enter in **one** tmux command (`send-keys -l T \; send-keys Enter`), which forces a single read.
- **F**: a `statusLine` configured.

"split" means two separate `tmux send-keys` calls with no sleep between them. Two runs are excluded because I restarted the server mid-trial: `compact-D0-t2-long-load` and `clear-D0-t3-long-gap-load`.

Totals, including the excluded runs: 77 `/clear` and 66 `/compact` SessionStarts. That meets the plan's 20 / 10. Short text had 0 failures. All 16 failures are the paste case: long text arriving in one read with its Enter.

## What the session does between SessionStart and ready

- **/clear, fast hooks:** the first frame, taken 17-40 ms after the hook, already shows the idle, empty input. The prompt is submitted 50-100 ms after the hook.
- **/clear, slow sibling hook:** the UI goes idle **before** the SessionStart hooks finish.
  - A prompt typed at that point is accepted immediately and rendered as a user message with a `running SessionStart hooks… 1/2` spinner.
  - UserPromptSubmit fires only once the hooks are done, at about 3.03 s whatever D was.
  - Typing early is safe, and the prompt waits for the hooks.
- **/compact:** the SessionStart hooks run under `Running SessionStart hooks…` with `esc to interrupt` in the footer, and the input line looks empty the whole time.
  - This frame is empty but busy (108 such frames were seen).
  - A prompt typed now becomes a **queued message**, marked `Press up to edit queued messages` and `ctrl+x ctrl+s to send now`. It is submitted when the hooks end.
  - With fast hooks, the idle frame appears by 0.133 s.
- On compact, SessionStart fires about 11-18 s after PreCompact, once the summary is written.
- The session_id stayed the same across compact and changed on clear, which matches T-0006.

## Ready-line probe

The input line is the line that starts with `❯` and sits between two lines starting `───` (U+2500, SGR `38;5;244`).

- **Ready and empty:** the plain text of that line is exactly `❯` + U+00A0 (NBSP). With escapes, `capture-pane -e` gives `\x1b[39m❯ ` (978 of 979 ready frames).
- **Busy:** during the busy compact phase the glyph is grey, `\x1b[38;5;246m❯ \x1b[39m`.
- **Placeholder:** at startup the empty input shows a **dim placeholder**, for example `❯ Try "how does <filepath> work?"`, as `\x1b[2m…\x1b[0m` runs.
  - Plain `capture-pane -p` cannot tell a placeholder from typed text.
  - The probe must use `-e`, remove `\x1b[2m…\x1b[0m` runs, remove the other SGR codes, and then require the remainder to be `❯` plus whitespace.
  - No placeholder appeared after `/clear` or `/compact` in these runs. I did not check whether other states produce one.
- **Idle:** `esc to interrupt` must be absent from the pane. Without this check, the empty-looking busy frame during `/compact` passes the probe.
- **Do not use `? for shortcuts` as a marker.**
  - It disappears when a `statusLine` is configured (condition F): the footer becomes `⏸ manual mode on · ← for agents`.
  - It also disappears whenever the input is non-empty.
  - The user's real machine has a custom statusLine, so this marker would never match there.
- **Stability:** 0 ready-to-not-ready flips in 1088 pre-send frames across all conditions. The plain-text form `❯ ` was identical in every ready frame.

Recommended probe: the input line is `❯` + NBSP once dim runs and SGR codes are stripped, the lines above and below it are rule lines, and the pane has no `esc to interrupt`.

Note: requiring idle on `/compact` means waiting until every SessionStart hook in the batch has finished. `resume.readyTimeoutSeconds` (15) therefore has to exceed the slowest sibling SessionStart hook on the machine. I did not measure that on the real machine.

## Stated limits and what was NOT verified

- A delay is a guess, not a proof. The tmux probe sees the input line. Windows SendWait has no probe.
- I did **not** test whether SendWait's per-character input triggers the same paste handling of Enter on Windows. The same ~60-character limit may apply there. The Stop path's `/clear` is 6 characters, so it has never exercised this.
- The paste limit lies between 60 (passed) and 65 (failed) characters, measured once or twice per length at 160 columns. I did not pin the exact value. T-0006's grammar allows `/crew:autopilot <ticket> --goal "…"`, which can exceed it.
- Only one model (Haiku 4.5) and one pane size were tested. The real crew plugin was not installed, so the real context hook's latency was not measured; condition B stands in for it.
- The user's real statusLine and plugin set were not tested, only a stub statusLine.
- Load was synthetic (busy loops). Memory, IO and swap pressure were not tested.
- `drift-detection.sh` and the repo suites were not run. This was a measurement with no code change.
- The plan names this file `ready-measure.md`, and so does the spec's acceptance check. It was written as `spike.md` as instructed for this spike.
