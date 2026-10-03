# T-0017 auto wrap-up before auto-clear          status: spec   risk: high
## Intent
Wrap-up is armed when `context.autoClear.wrapUp` is exactly `true` in `~/.claude/crew/config.json`:
- a repo `false` vetoes it, and a repo `true` alone arms nothing;
- it acts only where `context.autoClear.enabled` is armed and in scope.

When it is armed, context-watch's high-context warning becomes a **wrap-up procedure**. It is a mechanical definition of "finish the current step", then commit, then `/crew:handoff --wrap-up`, then end the turn. Auto-clear clears only when the procedure's results are on disk. Those results are the existing checks plus four new ones:
- the handoff's `head:` equals HEAD;
- its `branch:` equals the checked-out branch;
- no tracked file is modified;
- its `resume:` line parses under T-0006's grammar, or is the explicit `resume: none`.

A refusal is shown to the human as a `systemMessage`. It is also fed back to the model once, at the session's next Stop.

After the clear, T-0006 decides whether to resume and T-0013 types the command. Neither is changed here.

`/crew:handoff --wrap-up` is the one wrap-up path: context-watch's message invokes it, and so does `/crew:autopilot`'s context-watch step.

Default OFF. With `wrapUp` unarmed, every output is byte-identical to today's.
## Exclusions
- No hook commits, stages, stashes or reverts anything. The model commits, and crew only checks the result.
- No claim that the step's test passed. verify-gate stands down on the forced-continuation turn (`plugin/crew/hooks/scripts/verify-gate.sh:70`), and this ticket does not change that.
- No change to the `resume:` grammar, `decide`, `record_run` or the typing path (T-0006, T-0013). No change to target identification (T-0016).
- No second wrap-up procedure. `/crew:autopilot` (T-0004) calls `/crew:handoff --wrap-up` and does not carry its own.
- No revival of `context.autoResume`.
- No change to `context.autoWrapUp`'s meaning (message wording, repo key, default `true`). When `wrapUp` is armed, the wrap-up message supersedes both of today's messages. When it is not, `autoWrapUp` behaves exactly as now.
- No new hook registration. context-watch is already on `Stop` in both flavours (`plugin/crew/hooks/hooks.json:60-61`).
- `stop_hook_active` still never blocks (`plugin/crew/hooks/scripts/context-watch.sh:44-45`, `:162-167`). The sent marker is still claimed last (`plugin/crew/hooks/scripts/auto-clear.sh:155-164`). `CREW_AUTOCLEAR_INHIBIT` is untouched.
- No test sends a keystroke, runs a real `git commit` outside a fixture repo, or reads the developer's real config.
- No call-shaped SendKeys text.
## Evidence
- **Warning and marker.**
  - The first over-threshold Stop writes `.crew/.handoff-requested-<session>` carrying `requested_at` and `trusted` (`context-watch.sh:536-537`), then exits 2 with the `autoWrapUp` message (`:579-585`) or the detailed one (`:587-603`).
  - ps1 twin: marker branch `plugin/crew/hooks/scripts/context-watch.ps1:128-133`, `autoWrapUp` read `:159`, message `:399-405`.
  - A later Stop with the marker still present re-runs auto-clear without blocking (`context-watch.sh:513-527`).
  - The forced continuation hands over to `cw_run_auto_clear` (`:103-133`). That function forwards auto-clear's stdout so a `systemMessage` reaches the user (`:105-111`, `:126-129`).
- **Existing freshness gate.** `verify_handoff`: the marker is this session's and trusted; the handoff is written after `requested_at`, is not the skeleton, and has at least `minHandoffLines` lines (`plugin/crew/hooks/scripts/crew_autocycle.py:318-351`). It is called from `plan` before `resolve_method` (`:546-551`). ps1 twin: `plugin/crew/hooks/scripts/auto-clear.ps1:495-504`.
- **Settings.**
  - `crew_autocycle.settings` reads `context.autoClear` from both layers, with the machine opt-in rule at `:175`. Recognised keys are listed at `:72-82`.
  - ps1 reads the machine block natively (`auto-clear.ps1:139-147`).
  - `AUTOCLEAR_DEFAULTS` is at `plugin/crew/hooks/scripts/crew_state.py:654-695` and flows into the global layer at `plugin/crew/hooks/scripts/crew_config.py:488-492`.
  - `context.autoWrapUp: True` is at `crew_state.py:742`, and context-watch's own read defaults it to true (`context-watch.sh:331`).
- **Handoff fields.** `crew_state._HANDOFF_BRANCH_RE` / `_HANDOFF_HEAD_RE` (`crew_state.py:626-629`, `head:` is 7-40 hex). T-0006 (branch T-0006-resume, 165c714f):
  - `crew_resume.parse_resume` returns `ok: False, reason "resume: none"` for an explicit none (`plugin/crew/hooks/scripts/crew_resume.py:83-127`);
  - `handoff.md` step 5 writes `resume:`, `branch:` and `head:` (`plugin/crew/commands/handoff.md:17-20`);
  - `decide` requires `branch:`/`head:` to match the checkout at SessionStart. A handoff written before the wrap-up commit would therefore never resume, which is why head must match before the clear.
- **The procedure's writer.** `plugin/crew/commands/handoff.md:7-33` builds the note from `git status`, the ticket and the last verification. Its `--clear` argument only reminds the user (`:29-31`).
- **Active ticket.** `crew_ticket.py active` (`plugin/crew/hooks/scripts/crew_ticket.py:734-735`, `active_ticket` `:672`). A plan step's `Test:` line is the per-step check (`.work/tickets/T-0013/plan.md` shape, parsed by `crew_ticket.parse_plan`).
- **Autopilot.** T-0004's plan step 6 (`.work/tickets/T-0004/plan.md`): "on a context-watch handoff request: run `/crew:handoff`, with `resume: /crew:autopilot <ticket>` as the resume line (T-0006's grammar), then stop".
- **SKILL.md.** SKILL.md says `autoWrapUp` "is off by default" (`plugin/crew/skills/crew-context/SKILL.md:204-205`, example `:188`). CONFIG.md says `true` (`plugin/crew/CONFIG.md:763`), which matches the code.
- **Marker reset.** SessionStart removes this session's markers by name: `plugin/crew/hooks/scripts/handoff-read.sh:19` (7-day sweep `:23`) and `plugin/crew/hooks/scripts/handoff-read.ps1:195` (sweep `:201`). A new escalation marker has to be added to both, because `session_id` survives `/compact` (T-0006 spike).
- **Sabotage.** Registry at `plugin/crew/tests/sabotage.py:2927`. Existing auto-cycle mutations are in `plugin/crew/tests/sabotage_autocycle.py`.
## Unknowns
- **Getting the escalation to the model.**
  - The forced-continuation Stop must never block (layer 1). A wrap-up refusal found there cannot be fed back on that same turn.
  - It is shown to the human at once, as a `systemMessage` through `cw_run_auto_clear`'s stdout.
  - It is fed back to the model at the next Stop, through the marker branch `context-watch.sh:513-527`. That is one exit 2, claimed with a `noclobber` / `CreateNew` marker `.crew/.wrapup-escalated-<session>`. The next Stop always follows a human turn, so this adds no loop.
  - On Windows both flavours run on the same Stop, and the marker makes exactly one of them escalate.
- **Python on Windows.** The resume-line check needs `crew_resume.parse_resume`, which is python. context-watch.ps1 and auto-clear.ps1 resolve a python the way the context wrapper does (`crew-context.ps1`). With no usable python, wrap-up reads as unarmed in context-watch.ps1, so today's message is sent. auto-clear.ps1 refuses the clear with a logged reason. Both are the refusing direction. Stated, not hidden: armed wrap-up on Windows needs python.
- **`resume: none` still clears.** It is the model saying "the next step needs a human". Clearing then loses nothing, because the handoff is injected and nothing resumes. A missing, duplicated or unparseable line refuses, because that is "could not tell".
- **Untracked files do not block.** Untracked files count as not dirty (`git status --porcelain --untracked-files=no`), because `.work/` and scratch output are untracked by design. Only tracked modifications block.
- **Dependency on T-0006.** If T-0006 is not merged, `crew_resume` cannot be imported. An armed wrap-up then refuses every clear with "T-0006's crew_resume is not installed", and nothing silently skips the check. Precondition: T-0006 merged. T-0016 merged is also a precondition, because this ticket's tests build on its session-record fixture.
- **T-0004 order.** If `plugin/crew/commands/autopilot.md` exists at implement time, its context-watch bullet is changed to `/crew:handoff --wrap-up`. If it does not exist, the owner amends T-0004 step 6 instead. This ticket never edits another ticket's files.
- **Version.** The assigned version is 1.0.41. Recheck at implement time.
- **Review.** Codex is out until 2026-10-01, so this is a same-family review, accepted as risk and announced.
## Touch
- `plugin/crew/hooks/scripts/crew_autocycle.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/hooks/scripts/context-watch.sh`
- `plugin/crew/hooks/scripts/context-watch.ps1`
- `plugin/crew/hooks/scripts/auto-clear.sh`
- `plugin/crew/hooks/scripts/auto-clear.ps1`
- `plugin/crew/hooks/scripts/handoff-read.sh`
- `plugin/crew/hooks/scripts/handoff-read.ps1`
- `plugin/crew/templates/global.template.json`
- `plugin/crew/templates/config.template.json`
- `plugin/crew/commands/handoff.md`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_wrapup.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/sabotage_wrapup.py`
- `plugin/crew/tests/sabotage.py`
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
- [ ] Arming (`test_wrapup.py`): it is armed only with a machine `wrapUp: true`, an armed and in-scope `enabled`, and no repo `false`. A repo `true` alone, `null`, the string `"true"`, or `enabled` off each leave it unarmed. With it unarmed, context-watch's stderr, exit code and marker file are byte-identical to today's for both `autoWrapUp` values. The ps1 cases skip without pwsh and say so.
- [ ] Armed message: the first over-threshold Stop exits 2 with the wrap-up procedure. The procedure:
  - says to start no new step;
  - names the active ticket, or says there is none;
  - says to run the step's `Test:` command and commit only if it passes;
  - says to leave the tree and write `resume: none` if it cannot pass;
  - says to run `/crew:handoff --wrap-up`, then end the turn;
  - lists the four clear conditions.

  Both flavours print the same text (a parity test).
- [ ] must-fire: armed, a fresh handoff with `head:` equal to HEAD, a matching `branch:`, a valid `resume: /crew:done T-0001`, and a clean tracked tree -> the auto-clear dry-run plan says `send`. The same with `resume: none` -> `send`.
- [ ] must-not-fire, one test each, with the reason in `.crew/.autoclear.log` and in a `systemMessage`:
  - `head:` missing;
  - `head:` not HEAD, i.e. a handoff written before the commit;
  - `branch:` mismatch;
  - a tracked file modified;
  - `resume:` missing;
  - two `resume:` lines;
  - an excluded command (`/crew:approve T-0001`);
  - `crew_resume` not importable;
  - git failing;
  - ps1 with no python.

  An untracked file alone does not block.
- [ ] Escalation: after a wrap-up refusal, the next non-`stop_hook_active` Stop exits 2 once with the refusal reason. A second one does not. A `stop_hook_active` Stop never exits 2. On Windows both flavours racing escalate once (marker `noclobber` / `CreateNew`).
- [ ] One path:
  - `handoff.md` documents `--wrap-up`: check the tracked tree first; take `branch:` and `head:` after the commit; write `resume:` per T-0006, with `/crew:autopilot <ticket>` when autopilot drives; if the tree is dirty, write `resume: none` and a **Verify first** line listing the files; then stop without telling the user to `/clear`.
  - `test_wrapup.py` asserts context-watch's armed message names `/crew:handoff --wrap-up`.
  - If `autopilot.md` exists, `test_wrapup.py` asserts its context-watch step names `/crew:handoff --wrap-up` and carries no wrap-up procedure of its own.
- [ ] Existing suites pass unchanged: `test_context_watch*.py`, `test_auto_clear*.py`, `test_auto_cycle.py`, `test_autoclear_binding.py` (T-0016), and T-0006/T-0013's suites if landed.
- [ ] `sabotage_wrapup.py` is registered at `sabotage.py:2927`. Each mutation below turns a named test red:
  - arming on a repo `true`;
  - skipping the head match;
  - skipping the dirty-tree check;
  - counting untracked files as dirty;
  - accepting an unparseable resume line;
  - treating an import failure as pass;
  - escalating on `stop_hook_active`;
  - escalating twice.
- [ ] Config and docs:
  - `context.autoClear.wrapUp` (default `null`, effective off) is declared in `AUTOCLEAR_DEFAULTS` and both templates.
  - `test_crew_config.py` leaf counts are re-measured.
  - CONFIG.md §14, README, SKILL.md and `auto-cycle.md` describe the procedure, the four conditions, the stated limit (commit checked, test not), and the relation to `autoWrapUp`.
  - SKILL.md's "`autoWrapUp` is off by default" is corrected to the code's `true`.
- [ ] Release: `.crew/verify.json` maps `context-watch.*`, `auto-clear.*`, `crew_autocycle.py`, `handoff.md` and the new tests to `python3 -m pytest plugin/crew/tests/test_wrapup.py plugin/crew/tests/test_context_watch.py plugin/crew/tests/test_auto_cycle.py -q`. Crew is at 1.0.41 with a CHANGELOG entry. `python3 scripts/check-marketplace.py` passes.
