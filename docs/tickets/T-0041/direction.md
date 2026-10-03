# T-0041 direction - crew verifies before it states, and says "not verified" instead of assuming

Status: direction APPROVED by the owner 2026-09-26 ("Guidance + mechanical checks": the rule in always-loaded guidance and agent prompts, plus validate-prompts "Not verified" enforcement, review-parser integrity, and a reviewer "claim without evidence" FIX category; not installed into consumer repos).

## Ask (owner, Matthew Badali, 2026-09-26, verbatim)
"also another ticket is to please verify information and don't assume if you don't already have that"

## Evidence from this session (2026-09-25/26) - each an assumption that was later corrected
- The coordinator said crew's four agents "set no model at all"; they all pin one (`model:` at line 15-24 of
  each agent file). It had read only the first 12 lines.
- A planner proposed moving `explorer` to Sonnet, reversing the owner's recorded 2026-09-24 decision
  (CHANGELOG 1.0.9) it had not looked up.
- The coordinator attributed 68 missing vault `.claude/` files to "another session" risk before checking that
  `.claude/` is outside Obsidian Sync (vault CLAUDE.md) - the files had never been on that host.
- A review round was recorded INCOMPLETE because an agent re-typed the reviewer's output instead of copying the
  bytes (T-0030 round 1).
- An independent review recommended a "tracked `.work/coord/`" on the premise that `.work/` is shared through
  git; `.work/` is ignored and per-worktree (`git check-ignore -v`).
These match CLAUDE.md's standing lessons ("unknown collapsing into the safe-looking value", "attach the ref
and the layer to every measurement", "run the states; do not reason about them").

## Recommendation (to be confirmed)
1. **A verification rule in crew's always-loaded guidance** (crew-best-practices / the agent prompts): a claim
   about code, config, history or state is either verified in this session (with `path:line`, the command and
   its output, or the ref it was measured at) or labelled `not verified` / `inferred` - never stated plainly.
   "Could not tell" is its own answer. Prior decisions are looked up (CHANGELOG, decisions, ticket directions)
   before proposing to change a thing.
2. **Copy, don't retype:** tools that hand one agent's output to another (review out.txt, fixtures, quoted
   errors) move bytes by file copy, never by re-typing.
3. **Checked, not just written:** a reviewer rubric line "claims without evidence" becomes a FIX category in
   crew's review prompt; `/crew:done`'s report must list what was not verified; subagent report templates
   require a "Not verified" section (most already do - make it universal and enforced by validate-prompts).
4. **Owner-facing:** when crew does not have a fact it asks or measures instead of filling the gap, and says
   which it did.

## Open questions
- How much of this can be mechanical? Candidates: validate-prompts asserting every dispatching command's
  report template has "Not verified"; the review parser rejecting byte-mangled out.txt (see the U+2028
  follow-up); a lint for unanchored numeric claims in codemaps (the existing claim markers). The rest is
  guidance and review.
- Scope: crew's own prompts and agents only, or also a CLAUDE.md rule crew installs into repos it sets up?

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
