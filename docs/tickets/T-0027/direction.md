# T-0027 direction - T-0010 round-6 accepted findings follow-up

Status: seed.

## Ask
the owner, 2026-09-28 ~17:55 CDT, choice "T-0010 round 6" = accept with a follow-up. Ledger:
"round 6 FINDINGS accepted by the owner at 2026-09-28T22:14:25+00:00", receipt bundle 3e4832c4021a
(round 6, Claude reviewer, head 07032fc7, base 6387ab49; 0 BLOCK / 4 FIX / 3 NIT). T-0010 merged as
PR #261 (merge commit 8ab733d7, crew 1.0.61) with these findings open. This ticket holds them.

Number note: T-0027 was reserved on 2026-09-25 for T-0006 follow-ups and never created
(`.work/tickets/T-0037/direction.md:17`); it was the only free number below T-0110 on 2026-09-29.

## Findings (round 6, verbatim)

FIX|plugin/crew/hooks/scripts/crew_autopilot.py:1517|status still returns settings()' warnings, and those include the approval/questions policy warnings. That contradicts the requirement, and status's own docstring, that status reads no policy and stays identical under every policy setting. test_route_and_status_unaffected_by_approval_policy compares only the "waiting on" field, so it misses this.|Set autopilot.mode=plan and autopilot.approval=bogus, then run crew_autopilot.py status. Remove only the approval key and run it again. The first output has an extra "warning: autopilot.approval is 'bogus' ..." line.
FIX|plugin/PLUGINS.md:128|The catalog row still calls writing the receipt approve's "one write". That understates the documented three-write carve-out and revives the sole-receipt claim round 4 rejected.|Run an allowed first autopilot approval and watch both approval.json and scope-tickets.json change. Then approve a distinct successor plan under NEEDS_REPLAN and watch the review ledger change too.
FIX|docs/guides/crew/src/daily-workflow-scope.md:53|The opt-in recipe leaves out the required autopilot.mode=plan. It also says both settings it shows default off, but autopilot.approval defaults to risk. Following the guide does not turn on self-approval, and the guide misstates the safety default. The rebuilt HTML, DOCX and PDF carry the same text.|Set only scope.allowCliApproval=true and autopilot.approval=self as instructed, then run crew_autopilot.py settings. It reports mode=off, and crew_autopilot.py approve exits 2 with "autopilot.mode is not plan". With no approval key, settings reports approval=risk, not off.
FIX|plugin/crew/hooks/scripts/crew_ticket.py:752|The approve-time policy refusal for via=autopilot is only tested in test_crew_autopilot_policy.py (test_the_library_refuses_an_autopilot_receipt_the_policy_denies). The verify rules mapped to crew_ticket.py (rules 11 and 31 in .crew/verify.json) run test_approval_digest.py, test_approval_hook.py, test_approval_group.py and test_crew_ticket.py. None of those calls approve(via=autopilot) under a denying policy. An edit that drops this approval gate therefore passes the local verify gate.|Apply the POLICY_MUTATIONS entry "the library writes an autopilot receipt the policy refuses" (change `if refusal is not None:` to `if False:`). Then run the commands of every verify.json rule whose paths match plugin/crew/hooks/scripts/crew_ticket.py. All of them pass. Only rule 28's suite, which does not map crew_ticket.py, goes red.
NIT|plugin/crew/hooks/scripts/crew_autopilot.py:1109|When .crew/config.json is unreadable or the autopilot block is not an object, approve refuses with "autopilot.mode is not plan" and drops settings' could-not-tell warning. The operator is told to arm a mode that may already say plan, and is never told the real cause.|Write .crew/config.json as `{bad` (or set `"autopilot": ["x"]`) with allowCliApproval true, then run crew_autopilot.py approve --ticket T-1. It prints "refused: autopilot.mode is not plan ..." and does not say the config could not be read.
NIT|.crew/codemap/crew.md:690|This note numbers the verify rules one higher than verify.json's zero-indexed list, which verification-harness.md and repo-docs.md follow. It calls the policy rule 29, routing rule 31 and approval rule 32 ("the last"), but verify.json has 32 rules numbered 0-31, and those are rules 28, 30 and 31. The provenance lines "d7c7c75c re-prices rule 29" in every note name the wrong rule too: the re-priced rule is 28.|Run `python3 -c "import json;r=json.load(open('.crew/verify.json'))['rules'];print(len(r),r[28]['paths'][0],r[28]['seconds'])"`. It prints `32 plugin/crew/hooks/scripts/crew_autopilot.py 21`, so rule 28 is the one priced at 21 and there is no rule 32.
NIT|.crew/codemap/verification-harness.md:40|The section heading still reads "31 rules, up from 30", but the paragraph under it now says 32 rules and 339 lines.|Read .crew/codemap/verification-harness.md:40-43, or run len(json.load(open('.crew/verify.json'))['rules']), which gives 32.

## Wanted
Each FIX fixed test-first, each with a named test that fails without it; NITs fixed or explicitly declined.
Line numbers are round 6's (at 07032fc7); the landing lint fixes in PR #261 kept them in place, but re-find
each by content on origin/main.

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

## Split 2026-09-30 (owner 2026-09-30 "Triage pass now")

Owner decision 2026-09-30 ~11:30: oldest tickets first, 1-2 deliverables per ticket, extras split into new tickets.

Kept in T-0027: the FIX at crew_autopilot.py:1517 (status returns policy warnings) and the NIT at crew_autopilot.py:1109 (approve drops the could-not-tell cause). Both are in crew_autopilot.py.

Moved:
- L-0542: FIX plugin/PLUGINS.md:128 and FIX docs/guides/crew/src/daily-workflow-scope.md:53 (doc text, plus the rebuilt guide outputs).
- L-0543: FIX crew_ticket.py:752 (no verify rule mapped to crew_ticket.py runs the policy refusal) and the two codemap NITs (crew.md:690, verification-harness.md:40).

## Direction check 2026-10-04

Checked against origin/main 155fe6d8 (crew 1.0.322 in `plugin/crew/.claude-plugin/plugin.json:3`).
All line numbers in the findings above are round 6's; the current ones are below.

Still true (both findings are live, nothing merged since T-0010 touched either site):
- FIX, status prints policy warnings. `status` (`plugin/crew/hooks/scripts/crew_autopilot.py:1523`)
  returns `"warnings": conf["warnings"]` at `:1547`, and `settings` puts `_policy_setting`'s
  per-key value warnings (`:995-1003`, appended at `:820-822`) in that list. `status_text` prints
  each as a `warning:` line (`:1581`). So `autopilot.approval: "bogus"` adds a line to `status`,
  against the docstring at `:1528-1530` ("It reads no approval or questions policy ... its lines
  are the same under every setting"). `test_route_and_status_unaffected_by_approval_policy`
  (`plugin/crew/tests/test_crew_autopilot_status.py:1121`) still compares only the `waiting on`
  field and only the three valid policy values.
- NIT, approve hides an unreadable config. `approve` (`:1129`) refuses at `:1139-1141` with
  "autopilot.mode is not plan" whenever `settings(top)["armed"]` is false. `settings` (`:759`)
  returns `armed: False` with a could-not-tell warning when `_unreadable_autopilot` (`:739`) names
  a cause (`:776-785`), and `approve` drops that warning.
- `git log origin/main -- plugin/crew/hooks/scripts/crew_autopilot.py` since T-0010's landing
  (08eeaa3e) shows T-0087, T-0088 and L-0510 work only; none changes `status`'s warnings or
  `approve`'s unarmed branch.

What changed since the seed:
- Crew moved from 1.0.61 to 1.0.322; the two sites moved from `:1517` / `:1109` to `:1547` /
  `:1139`.
- T-0087 landed the tooling-PR rule. `plugin/crew/tests/sabotage*.py` is in `HARNESS`
  (`scripts/check-tooling-pr.py`) and `crew_autopilot.py` is a `SEAM` file. A PR that edits
  `crew_autopilot.py` for a feature may therefore not edit `sabotage_autopilot.py`. Two existing
  mutations anchor on lines next to this change and must keep matching exactly once:
  `'    if not settings(top)["armed"]:\n'` (`plugin/crew/tests/sabotage_autopilot.py:753`) and the
  `status reads the policy` mutation that names
  `test_route_and_status_unaffected_by_approval_policy[self]` (`:866`).
- The split of 2026-09-30 stands: L-0542 (doc text) and L-0543 (verify mapping, codemap NITs) are
  still `direction`.

Options:
1. (Recommended) Fix both in `crew_autopilot.py` with pytest tests only, no sabotage edit.
   `settings` marks which of its warnings come from a policy value; `status` leaves those out and
   keeps every other warning, the could-not-tell one included. `approve` keeps its armed check
   line as it is and, inside it, names the could-not-tell cause when there is one. Cost: the two
   new behaviours have named red-first tests but no sabotage mutation of their own.
2. Same, plus new mutations in `sabotage_autopilot.py`. Cost: breaks the tooling-PR rule, so it
   needs a second, tooling-only PR. The behaviours are a report line and a refusal message, not a
   guard that blocks, so the repo rule that demands sabotage (a hook that can block) does not
   apply.
3. Decline the NIT and fix only the FIX. Cost: the operator is still told to arm a mode that may
   already say `plan`.

Taken: option 1. The owner was not available on 2026-10-04; see "Open questions for the owner" in
spec.md.

Sub-decision, also taken as recommended: under an unreadable `.crew/config.json` (or a non-object
`autopilot` block) `status` KEEPS the single could-not-tell warning. It explains why the mode line
reads off, it is the same line whatever the policy keys say (they cannot be read), and dropping it
would let an unknown read as a plain "off".
