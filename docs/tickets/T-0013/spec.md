# T-0013 auto-resume types the resume command into its own session          status: spec   risk: high
## Intent
When `resume.auto` is on (T-0006: machine-only, repo veto) and T-0006's `crew_resume.decide` returns `run` on SessionStart `clear` or a manual `compact`, crew types the re-rendered resume command plus Enter into the terminal that owns this session. It uses auto-clear's existing typing path unchanged: tmux `send-keys` into the pane whose pid is an ancestor of the hook on Linux, and on native Windows SendWait with the focus and tab rechecks, only under an explicit `method: sendkeys`. It types once per handoff, only after the session's input is ready, and never on any refusal auto-clear already has. Nothing here changes a gate: typing starts the command, and the command's own gates decide. Default OFF.
## Exclusions
- Depends on T-0006 (`decide`, `record_run`, the `resume:` grammar, `resume.auto` resolution); does not change their rules.
- No new hook registration in `plugin/crew/hooks/hooks.json`: the context hook (already registered, `hooks.json:8-9`) starts auto-clear's resume mode.
- No new window-finding, focus or tab logic: reuse `crew_autocycle.resolve_method` (`plugin/crew/hooks/scripts/crew_autocycle.py:452`) and `auto-clear.ps1`'s checks as they are.
- `auto` never resolves to `sendkeys` on native Windows (owner rule, `auto-clear.ps1:508-517`); `wtype` stays refused; `notify` types nothing.
- No typing of anything but `decide`'s rendered prompt: no handoff text, no `## Next action` prose.
- No `startup` trigger, no `claude --resume` trigger, no auto-compact trigger (T-0006 decisions).
- No change to `/clear`-typing auto-clear behaviour: the existing Stop-hook path, its markers and its tests are untouched.
- No test may send a real keystroke or enumerate a real window.
## Evidence
- T-0006's spike (`.work/tickets/T-0006/spike.md`): SessionStart `initialUserMessage` does not start a turn interactively on Claude Code 2.1.282 (only `-p`), so typing is the only interactive route. `session_id` changes across `/clear` and is stable across `/compact`.
- auto-clear.sh, the Linux/tmux path: `.crew/` gate `plugin/crew/hooks/scripts/auto-clear.sh:80`; decisions from `crew_autocycle.py plan` `:103`; per-session one-shot marker `:111` claimed with noclobber only after every refusal `:155-164`; off is silent `:114`; `notify` types nothing `:171-178`; `CREW_AUTOCLEAR_INHIBIT` checked immediately before the sender is built `:183-186`; the detached sender sleeps `:191`, then `tmux send-keys -t <pane> -l <text>` and `Enter` `:195-196`; `setsid` detach with fd 3 closed `:226`.
- `crew_autocycle.py`: `settings` `:137` (machine opt-in rule `:175`), `in_scope` narrowing `:281`, `resolve_method` `:452` (tmux: `$TMUX_PANE`'s pid must be an ancestor of the hook `:493-507`; `auto` on `OS=Windows_NT` -> `notify`), `plan` `:526`.
- auto-clear.ps1, the Windows path: exits unless `OS=Windows_NT` `plugin/crew/hooks/scripts/auto-clear.ps1:69`; method switch `:508-517`; one-shot marker via `FileMode::CreateNew` `:543`, `:786`, `:822`; child `param()` `:829`; child sleeps `:961`, then the foreground-window check `:980`, the tab recheck `Get-CrewChildTabRecheck` `:954`/`:990`, SendKeys escaping `:1013`, `SendWait` `:1014-1015`; `CREW_AUTOCLEAR_INHIBIT` in the child `:1007`; detached child `Start-Process` `:1131`.
- The context hook: `crew_context.run` `plugin/crew/hooks/scripts/crew_context.py:830`, its per-event flavour claim `:843` (`claim` `:161`); SessionStart branch `:731-771`; CLI `main` `:1001`; the ps1 wrapper builds python's argv at `plugin/crew/hooks/scripts/crew-context.ps1:229`, the sh wrapper at `crew-context.sh:19`.
- No-keystroke test precedents: every auto-cycle test sets `CREW_AUTOCLEAR_INHIBIT`, points HOME at the fixture and stubs the window list via `CREW_AUTOCLEAR_WINDOW_STUB` (`plugin/crew/tests/test_auto_cycle.py:19-23`); structural source-order checks with no execution (`plugin/crew/tests/test_auto_clear_review_fixes.py:657`, and `test_sendkeys_structural_gate.py` from T-0002's cherry-pick `e9b88060, squashed into main as f2bb919b (T-0002)`).
- Existing default delay for typing after a turn: `context.autoClear.delaySeconds: 3` (`plugin/crew/hooks/scripts/crew_state.py:667`) - measured for the Stop path, not for SessionStart.
## Unknowns
- **Typing before the session is ready.** SessionStart runs while Claude Code is still redrawing after `/clear`, and keys that arrive early may be dropped or land in the wrong widget. Resolved in plan step 1 by measurement in a throwaway tmux session. Two mechanisms follow from it: a ready-probe on tmux (poll `tmux capture-pane` for an empty input line, then type) and a fixed delay where no probe exists (Windows SendWait). The measured default is `resume.typeDelaySeconds`, and the probe gives up at `resume.readyTimeoutSeconds`. Stated limit: a delay is a guess, not a proof. On Windows no probe can see the input line, so a key can still land early on a loaded machine. The foreground and tab rechecks run after the delay and cover the wrong window, but not an unready input box.
- **Which flavour types, when both run (Windows).** Each flavour's python runs `decide` independently of the context claim. A flavour whose method cannot send refuses without claiming. The per-handoff marker `<git-common-dir>/crew/resume-typed-<handoff sha256[:16]>` is created with `O_EXCL`/`CreateNew` only after every refusal, so exactly one sender types. This is the same "claim last" rule `auto-clear.sh:155-164` states.
- **Record before type.** `crew_resume.record_run` (T-0006) runs after the claim and before the sender is spawned. A failed record types nothing, so the loop guard can never be bypassed by a run it did not see.
- The ready-probe's empty-line glyph is Claude Code UI text and version-specific. Pinned in step 1 against 2.1.282. A probe that never matches types nothing and logs the reason, which is the refusing direction.
- The spike found crew hooks writing `.crew/config.json` and `.work/HANDOFF.md` into a repo that had no `.crew/`, so tests must not assume crew is silent there. Every test builds its own fixture repo with HOME redirected.
- Codex out until 2026-10-01: same-family review, accepted as risk and announced.
## Touch
- `plugin/crew/hooks/scripts/auto-clear.sh`
- `plugin/crew/hooks/scripts/auto-clear.ps1`
- `plugin/crew/hooks/scripts/crew_autocycle.py`
- `plugin/crew/hooks/scripts/crew_context.py`
- `plugin/crew/hooks/scripts/crew-context.sh`
- `plugin/crew/hooks/scripts/crew-context.ps1`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/templates/global.template.json`
- `plugin/crew/tests/test_resume_typing.py`
- `plugin/crew/tests/test_resume_typing_structure.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/sabotage_resume_typing.py`
- `plugin/crew/tests/sabotage.py`
- `.work/tickets/T-0013/ready-measure.md` - step 1's measurement, ignored and local-only
- `plugin/crew/CONFIG.md`
- `plugin/crew/README.md`
- `plugin/crew/skills/crew-context/SKILL.md`
- `docs/guides/crew/src/auto-cycle.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
- `TODO.md`
## Acceptance checks
- [ ] `.work/tickets/T-0013/ready-measure.md` records, for Claude Code 2.1.282 under tmux, the SessionStart-to-ready latency over at least 20 `/clear` runs and 10 `/compact` runs, the chosen `resume.typeDelaySeconds` default derived from it, the probe glyph, and the stated limit
- [ ] must-fire (`test_resume_typing.py`, sh; ps1 cases skip without pwsh): armed + `decide` `run` + tmux pane owned by an ancestor -> the dry-run plan says `send`, method tmux, text = the rendered prompt; ps1 with `method: sendkeys` and a stubbed matching window -> `send`
- [ ] must-not-fire, one test each, with the reason logged to `.crew/.autoclear.log`: `decide` returns `wait` or `off`; `resume.auto` off (silent, no log line); `$TMUX` unset; pane not an ancestor; `onlyRepos`/`onlySessions` excluding this repo/session; method `wtype`; method `auto` on Windows (-> notify, nothing typed); focus lost or tab mismatch at recheck (ps1, stubbed); input line not empty at probe; probe timeout; same handoff a second time (marker exists); `record_run` failure
- [ ] both flavours racing on one SessionStart type at most once (marker `O_EXCL`/`CreateNew`), and a flavour that refuses leaves the marker unclaimed (test)
- [ ] no keystroke from any test: every case sets `CREW_AUTOCLEAR_INHIBIT` and a stub window list, and HOME points at the fixture; a structural test asserts in each sender's SOURCE the order delay/probe -> recheck -> inhibit check -> send (after `test_auto_clear_review_fixes.py:657`)
- [ ] the existing auto-clear suites (`test_auto_clear*.py`, `test_auto_cycle.py`, `sabotage_autocycle.py`) pass unchanged
- [ ] `sabotage_resume_typing.py` registered at `sabotage.py:2927`: typing on `wait`, dropping the per-handoff marker, claiming the marker before the method check, skipping the probe, ignoring a `record_run` failure, typing the raw handoff line, and resolving `auto` to sendkeys on Windows each turn a named test red
- [ ] `resume.typeDelaySeconds` (measured default) and `resume.readyTimeoutSeconds` (default 15) are machine-global, declared in `default_global_config` and the global template; `test_crew_config.py` leaf counts re-measured
- [ ] `.crew/verify.json` maps `auto-clear.*`, `crew_autocycle.py` and the new tests to `python3 -m pytest plugin/crew/tests/test_resume_typing.py plugin/crew/tests/test_resume_typing_structure.py plugin/crew/tests/test_auto_cycle.py -q`; crew version 1.0.39 with a CHANGELOG entry; README, CONFIG.md, SKILL.md and `auto-cycle.md` describe the typing path, its refusals, the delay and its limit
