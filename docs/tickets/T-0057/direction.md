# T-0057 direction          status: ready   risk: med

## Ask
Owner (the owner, 2026-09-26): "If this isn't already, I need all these commands to be contextual
as well, so that I can activate these commands based on what I'm saying."
"These commands" means the autopilot command set shown to the owner the same day: `status`, `assign`,
`goal`, `--goal` resume, `focus`, `wave`, `split`, `sleep`/`wake`, and `/crew:approve`.

## What exists
- T-0023 (approved, building in wave 3) routes plain text for the lifecycle commands only:
  `brainstorm`, `spec`, `plan`, `implement`, `review`, `done`, `status` and "continue". It matches
  the whole prompt against `crew_route.PHRASES` in the UserPromptSubmit hook and injects one line
  naming the command. It never runs or blocks anything. Outcomes are `route`, `ask` or `none`, and
  "go ahead"/"yes"/"sure" are never routed. It is off unless `route.enabled` is exactly `true`,
  which is now set in the global config (2026-09-26).
- No autopilot subcommand is in its table, and approval is excluded (T-0024 owns the plain-text
  approval form).
- T-0025 adds `/crew:help` and nudges, not routing.

## Options
1. **Extend T-0023's phrase table and resolver to the autopilot commands (recommended).** Same
   mechanism, same three outcomes, one table, so there is still exactly one matcher. New rows:
   - "what's autopilot doing" / "autopilot status" -> `status`;
   - "take care of <work>" / "handle <work>" -> `assign`;
   - "work toward <goal>" / "make it so <goal>" -> `goal`;
   - "pick the goal back up" -> `--goal <slug>`, resolved from running goal files (T-0056);
   - "focus on T-0012" -> `focus`;
   - "run T-0020 and T-0022 in parallel" -> `wave`;
   - "split this ticket" / "this is too big" -> `split`;
   - "I'm heading to bed" / "going to sleep" -> `sleep`, and "I'm back" / "morning" -> `wake`.

   Free-text commands (`assign`, `goal`) route through the router's `--first` form (T-0019), so the
   user's words never reach a shell line. Each row ships with the ticket that builds its command.
   A row whose command has not landed routes to `ask`, saying "arrives with T-00xx".
2. **A model-invoked skill that describes the commands and lets Claude decide.** More forgiving
   phrasing, but it is a second, non-deterministic matcher, the thing T-0023 rejected. It costs
   context every session and cannot be tested for false positives.
3. **Make each command's description richer and rely on Claude's own command selection.** No code,
   but nothing is pinned, and a slip on `goal` or `sleep` changes how autonomous the session is.

## Recommendation
Option 1. It keeps one deterministic, testable matcher. The suite gets must-route and must-not-route
cases per row; the must-not cases are the dangerous ones. "go to sleep mode later" must not route,
and neither may quoted text or a question about sleep mode. `sleep` and `goal` also echo one line
saying what changed and how to undo it ("sleep on until 07:00 - say 'I'm back' to wake").

## Open questions (recommendation applies)
- Approval by plain text stays with T-0024 ("approve T-0018" with a confirm step). This ticket adds
  no approval row.
- Should `sleep` by phrase need the schedule to be configured? Recommendation: no. Without a
  schedule it runs until "I'm back" or the next morning summary edge (07:00 default).

## Depends on
T-0023 (the table and hook). Each row depends on its command's ticket: T-0018, T-0019, T-0012,
T-0056, T-0020, T-0029, T-0052 and its split children, and T-0053.

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; every choice below is the recommended option, and each is repeated under "Open questions for the owner".

**Still true**
- The problem is real. `crew_route.PHRASES` (plugin/crew/hooks/scripts/crew_route.py:82-94) holds the eight lifecycle rows only. No row names `/crew:autopilot`. `git log origin/main --grep=T-0057` is empty and the last change to `crew_route.py` is T-0088's resolver change.
- Option 1 (extend the one table) is still the right mechanism. T-0023 is merged, the matcher is whole-prompt and deterministic, and approval is still excluded (T-0024 merged and owns it).

**What changed since 2026-09-26**
- Only two autopilot subcommands run on main: `status` and `run` (`crew_autopilot.AVAILABLE`, plugin/crew/hooks/scripts/crew_autopilot.py:225). `assign`, `goal` and `focus` are reserved names that stop with "arrives with T-0019 / T-0012 / T-0020" (`:224-226`, `:1318-1320`). `--goal` stops the same way (`:1311-1313`). `wave`, `split`, `sleep` and `wake` are not names the router knows at all (`:1317`).
- So the router already answers "has this command landed?". The table does not need its own copy of that fact: `crew_route.decide` asks `crew_autopilot.route` and a row goes live on the day its command's ticket adds the name to `AVAILABLE`, with no edit to `crew_route.py`.
- An `ask` for a command that has not landed must not derail the prompt. "handle the merge conflict" is a normal instruction today. The existing ask line ends "ask the user which ticket before running anything", which is wrong here. The not-landed line says the command is not available yet and tells Claude to answer the prompt as written.
- `plugin/crew/tests/sabotage*.py` is review/gate harness (scripts/check-tooling-pr.py:79). `crew_route.py` is not. The mutations for the new rows cannot ride in the feature PR, so they are their own tooling-only PRs.
- `/crew:split` exists on main as the Jira split command (plugin/crew/commands/split.md). The `split` row routes to `/crew:autopilot split` (T-0058), not to it.

**Recommended option (taken)**
Option 1, cut into four PRs:
1. T-0057 (this ticket): the availability gate, the not-landed ask line, and rows for the names the router knows: `autopilot-status` (live now), `assign`, `goal`, `goal-resume`, `focus` (each asks "arrives with" until its ticket lands).
2. L-0661: sabotage mutations for slice 1 (tooling-only PR).
3. L-0662: rows for `wave`, `split`, `sleep`, `wake`. They produce no line at all until the router knows the name.
4. L-0663: sabotage mutations for L-0662 (tooling-only PR).

Phrase decisions that differ from the 2026-09-26 list, and why:
- `focus on <id>` needs an explicit id. "focus on this" is ordinary conversation.
- `take care of it`, `handle this` and the like (a bare pronoun as the work) never route.
- Bare "this is too big" is not a row; "this ticket is too big" and "<id> is too big" are (L-0662).
- The two status questions may end in `?`. Status is read-only. No other row accepts a question.
- "pick the goal back up" never picks a slug. Until goal files exist on main (T-0012, T-0056) there is nothing to resolve from, so it asks. The resolver ships with T-0056.

## Open questions for the owner
Each has a default already applied in spec.md.
1. Free-text rows before their command lands: a soft ask line (default, as the direction says) or no line at all until T-0019 / T-0012 land? The soft line appears on every short "handle ..." or "take care of ..." prompt while `route.enabled` is true.
2. Should `assign` and `goal` phrases need the word "autopilot" ("have autopilot handle ...")? Default: no, the approved phrases stand.
3. The 80-character prompt cap (`MAX_PROMPT_CHARS`) limits how much work a phrase can describe. Default: keep 80; longer work is typed as `/crew:autopilot assign ...`.
4. Bare "this is too big" as a `split` phrase. Default: not a row.
5. "morning" and "I'm back" as `wake` phrases (L-0662). Default: keep, as approved; they produce nothing until T-0053 lands.
6. `sleep` by phrase without a configured schedule: unchanged from 2026-09-26 (default: allowed; T-0053 decides the behaviour).
