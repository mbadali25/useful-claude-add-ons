# T-0017 direction
## Ask
Owner (Matthew Badali, 2026-09-25), verbatim: "add the ability to fix auto clear and in a way to allow auto clear to work even if its child process and autowrap up (depends on auto clear)". This ticket is the second half: auto wrap-up.

When context-watch's high-context warning fires, the session should:
1. stop taking new work;
2. finish the current step;
3. commit;
4. write `.work/HANDOFF.md` with a `resume:` line in T-0006's grammar;
5. trigger auto-clear;
6. be picked up by auto-resume.

It depends on T-0016 (auto-clear that is safe for child processes) and T-0006 (the `resume:` grammar and `crew_resume.parse_resume`). T-0013 does the typing after the clear. It is default OFF behind a config key. There must be one wrap-up path, not a second one beside T-0004's autopilot.

## What investigation found (origin/main c286f951)
- **Most of the loop already exists.**
  - On the first Stop over the threshold, context-watch writes a per-session wrap-up marker (`plugin/crew/hooks/scripts/context-watch.sh:536-537`) and exits 2 with a message (`:579-585`, ps1 `context-watch.ps1:399-405`).
  - The forced continuation's Stop (`stop_hook_active`) hands over to auto-clear (`context-watch.sh:162-167`, ps1 `:128-133`).
  - Auto-clear clears only on a handoff written after the request that is not the PreCompact skeleton and has at least `minHandoffLines` lines (`crew_autocycle.py:318-351`, ps1 `auto-clear.ps1:495-504`).
  - So "a check that HANDOFF.md is fresh before the clear is sent" is already there. What is missing is the commit, the `resume:` line, and any check that either happened.
- **`context.autoWrapUp` already exists.** It is a repo key, default `true` (`plugin/crew/hooks/scripts/crew_state.py:742`, `context-watch.sh:331`, `context-watch.ps1:159`). It only switches the message's wording ("Reach a stopping point now ... tell the user the session is ready to clear"). It cannot be the switch for this feature: it is already on everywhere, and a repo could arm it. SKILL.md even calls it "off by default" (`plugin/crew/skills/crew-context/SKILL.md:204-205`), which the code contradicts. This ticket corrects that line (plan step 5), because it documents both keys side by side.
- **A hook cannot make Claude do anything.** An exit-2 Stop hook sends text back to the model (`context-watch.sh:1-5`). The model decides what to do with it. The only enforcement point is the clear itself: auto-clear can refuse to clear unless the wrap-up's results are on disk.
- **verify-gate stands down on `stop_hook_active`** (`plugin/crew/hooks/scripts/verify-gate.sh:70`). So the forced-continuation turn, where the wrap-up commit happens, is not re-verified. Crew can check that a commit happened, not that the step's test passed.
- **`/crew:handoff`** is the single writer's procedure (`plugin/crew/commands/handoff.md:7-33`). T-0006 adds the `resume:`, `branch:` and `head:` lines to it (branch T-0006-resume, `plugin/crew/commands/handoff.md:17-20`). T-0004's autopilot plan (step 6) says: "on a context-watch handoff request: run `/crew:handoff`, with `resume: /crew:autopilot <ticket>` ... then stop".

## Options
1. **Escalate the Stop message, add one handoff mode, and gate the clear on checkable results (recommended).**
   - The new machine key `context.autoClear.wrapUp` (default null, meaning off) arms it.
   - When armed, context-watch's warning becomes the wrap-up procedure: a numbered, mechanical definition of "finish the current step", then `/crew:handoff --wrap-up`.
   - Auto-clear then also requires four things:
     - the handoff's `head:` equals HEAD, and its `branch:` equals the branch;
     - no tracked file is modified;
     - the `resume:` line parses via `crew_resume.parse_resume`, or is the explicit `resume: none`.
   - A wrap-up refusal is shown to the human (a `systemMessage`) and fed back to the model once, at the next Stop.
   - Autopilot's step 6 calls the same `/crew:handoff --wrap-up`.
2. **Have the hook commit.** A Stop hook would run `git commit` itself. Rejected: it would commit whatever is in the tree, finished or not, under a message nobody wrote. It would also be a hook that writes history unattended.
3. **Reuse `context.autoWrapUp`.** Rejected: it defaults to true, a repo can set it, and an unattended clear is machine consent (the `context.autoClear.enabled` rule, `crew_autocycle.py:175`).

## Recommendation
Option 1.

**"Finish the current step", mechanically:**
- With an active ticket (`crew_ticket.py active`), the step is the plan step in flight. It is finished when that step's `Test:` command passes now. Only then is it committed.
- With no active ticket, the step is the tracked diff in `git status`.
- A step that cannot pass now is not committed. The tree stays dirty, the handoff says why under **Verify first** with `resume: none`, and auto-clear refuses on the dirty tree. A human decides.
- Crew checks what is on disk (commit, `head:`, `resume:`, a clean tracked tree). It does not claim the test passed.

**One path.** `/crew:handoff --wrap-up` is the only wrap-up procedure. context-watch's message invokes it, and autopilot's context-watch step invokes it. T-0006's `handoff.md` already makes the resume line `/crew:autopilot <ticket>` when autopilot is driving.

**Boundaries.**
- T-0016 decides whether there is a terminal to clear. A headless child still commits and writes its handoff, and T-0016's notify names the parent restart.
- T-0006 decides whether the new session resumes (`resume.auto`), and T-0013 types it.
- With `resume.auto` off, the cleared session shows the handoff and waits for Enter.

## Open questions
- None blocking.
- Coordination: if T-0004 has not merged when this is implemented, T-0004's plan step 6 bullet should say `/crew:handoff --wrap-up`. The owner amends T-0004; this ticket does not edit another ticket.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
