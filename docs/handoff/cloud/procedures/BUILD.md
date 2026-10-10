# Build procedure (useful-claude-add-ons, docs-only handoff PR -> implemented PR)

1. Read /home/user/useful-claude-add-ons/CLAUDE.md, Skill-Pipeline.md and Skill-Authoring-Standard.md (skim), and .claude/skills/steward/SKILL.md.
2. Worktree: `cd /home/user/useful-claude-add-ons && git fetch -q origin && git worktree add -f /home/user/pr-<N> origin/<BRANCH> -B <BRANCH>`. First `git merge --no-edit origin/main` (merge, never rebase) so you build on current main.
3. Read docs/tickets/<T>/direction.md, spec.md, plan.md in full. They are the contract. If the spec is ambiguous or conflicts with what main now does, choose the reading that keeps both, note it, and continue; only stop if a decision is genuinely the owner's (security posture, deleting/renaming a registered entry, new hook) - then report and stop.
4. Implement TEST-FIRST: for each behaviour, write the test, see it red, implement, see it green. For any check/guard, add must-block and must-allow cases and SABOTAGE them: reintroduce the bug, confirm the test goes red, restore. Follow CLAUDE.md landmines (CRLF, open(p,"w") truncation, python3 resolution, pwsh absolute path, branch on tool not OS, pick_fit).
5. Harness rule (CLAUDE.md, T-0087): do NOT edit any path in HARNESS in scripts/check-tooling-pr.py (e.g. sabotage.py entries, review prompts). Record those as "harness follow-ups" in your report instead. Run `python3 scripts/check-tooling-pr.py` - it must say no harness path changed.
6. Docs: update README/CONFIG/codemap (.crew/codemap/, DERIVED cites as path:line at HEAD), CHANGELOG entry, verify.json rule mapping the new code to its tests (with a measured `seconds` and a `why`), command line budgets (plugin/crew/.budget-allowance.json - don't exceed). Regenerate rules: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root .`. Delete docs/tickets/<T>/ in the final content commit (the spec ships as code + CHANGELOG) unless the plan says otherwise.
7. Version: LAST commit is version-only: crew (and any other touched plugin, one past main) set to <VERSION> everywhere stated (plugin.json, marketplace.json, plugin/PLUGINS.md claim line, CHANGELOG heading, arrival "since" text). Re-measure BUDGETS if check-marketplace asks.
8. Commits end with exactly one trailer `Claude-Session: https://claude.ai/code/session_016wQA2o38aSB65bpjaGpMVJ`; never Co-Authored-By.
9. Verify after committing: check-marketplace.py, rules --check, the verify.json rules mapped to every changed path (NOT the entire plugin/crew/tests suite unless your change is cross-cutting - container is shared), ruff + pylint on changed .py files (C0302 3400-line cap).
10. Push: `git push origin <BRANCH>` (fast-forward). Retry network errors 4x (2/4/8/16s).
11. Report (<30 lines): head sha, what was built vs the plan step by step (done/not done), tests added + counts, sabotage results, harness follow-ups, decisions you made on ambiguities, what you did not verify.

## Stacked builds (when a parameter DEPENDS_ON names another PR branch)
After `git merge origin/main`, also `git merge --no-edit origin/<DEPENDS_ON branch>` (merge, never rebase) so you build on the dependency's code. Say in the PR body: "Stacked on #<n> (<branch>): merge that first; this PR then merges main." Do not change the dependency's own files beyond what your ticket needs.

## Ticket IDs (owner rule 2026-10-04)
Every PR title must START with its ticket id(s) (e.g. `T-0057: ...`; a bundle lists every id: `H1 harness bundle: T-0098 + T-0109 + T-0101 ...`), and the PR body must name every ticket it closes on its own line (`Tickets: T-0098, T-0109, T-0101`). Every commit subject starts with the ticket id. The owner's tracker updates tickets from these.

## CI load
WITHDRAWN 2026-10-04: do NOT add [skip ci] to commits (the session's permission system treats it as a CI bypass). Push normally.

## Cloud ticket IDs (owner rule 2026-10-05)
New untracked cloud-session tickets are numbered C-0001, C-0002, ... (next free: see CLOUD-SESSION-TICKETS.md). L-1500 to L-1518 keep their IDs.
