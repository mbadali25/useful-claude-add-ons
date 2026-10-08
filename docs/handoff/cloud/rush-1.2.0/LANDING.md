# Landing a rush group into release/1.2.0 (or main for H lanes)

You are the LANDER. One group at a time; the coordinator gives you: group, worktree, target branch,
and the crew version to set. Read `/home/user/useful-claude-add-ons/CLAUDE.md` and
`.claude/skills/steward/SKILL.md` first. `$S` = /tmp/claude-0/-home-user-useful-claude-add-ons/cf8010ca-0ad0-5d92-8922-7bbd28b697af/scratchpad

1. `cd <worktree>; git fetch origin; git status` (must be clean; if not, stop and report).
2. Merge the target: `git merge --no-ff origin/<target>`. Resolve conflicts by reading both sides:
   - Version files (`.claude-plugin/marketplace.json`, `plugin/*/.claude-plugin/plugin.json`,
     `plugin/PLUGINS.md` claim lines): take the TARGET's value for now (step 4 sets the new one).
   - `CHANGELOG.md`: keep BOTH sides' entries, newest landing on top.
   - `README.md` "What's new": regenerate with `python3 scripts/sync-updates.py` (never hand-merge).
   - `plugin/crew/BUDGETS.md` / line-count claims: re-measure with the repo's tool or the check's
     own message.
   - `.claude/rules/*`: regenerate (`python3 plugin/crew/hooks/scripts/crew_instructions.py rules`
     or whatever `check_instructions.py`'s message names). `graphify-out/`, code-map anchors,
     diagrams: take the target's side, never hand-edit `graphify-out/`.
   - Real code conflicts: resolve keeping BOTH behaviours; if both sides changed the same logic and
     you cannot keep both, stop and report it.
   Commit the merge.
3. Run the cheap gates: `python3 scripts/check-tooling-pr.py` (must say "no harness path changed"
   for release lanes), `python3 scripts/check_instructions.py`, `python3 scripts/sync-updates.py
   --check`, `python3 scripts/_test/self-claims.py`. Fix what they name.
4. LAST commit = version only: set crew (and any other plugin the group changed, by its own next
   patch above the target's) to the given version in EVERY place it is declared — marketplace.json,
   plugin.json, PLUGINS.md claim, and rename the group's CHANGELOG/README headings that name the
   placeholder version. `git grep -n '<placeholder>'` must return nothing. Commit, THEN run
   `python3 scripts/check-marketplace.py` (it compares commits). Must print "all checks passed".
5. Targeted tests for files the merge touched (wrap in `flock $S/heavy.lock`), then push.
6. Whole-group Codex review: `$S/codex-review.sh <worktree> origin/<target> GROUP-<group>-rN
   $S/group-review-extra-<group>.txt` (create the extra file from `$S/group-review-extra.txt`
   with the right version). Verify each BLOCK/FIX against the code; fix the real ones (version
   commit stays last: re-do it after fixes), push, re-review until CLEAN. Reject a wrong finding
   only with a stated reason.
7. Report: head sha, version set, conflicts and how resolved, gates, tests, review rounds and final
   verdict, anything not verified. Do NOT open or merge PRs; the coordinator does.

Commit trailer: `Claude-Session: https://claude.ai/code/session_01QLY3kk7DCXpucXGu3wSniW` only.
Push after every commit.
