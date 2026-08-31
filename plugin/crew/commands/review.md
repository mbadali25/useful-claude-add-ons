---
description: Independent QA review of the current diff (Codex if available, Claude if not)
allowed-tools: Bash, Read, Agent
---

Run independent review of the working diff.

**Step 0a - claim a scratch directory.** A fixed `.work/review-*.txt` path
collides: two concurrent reviews - a second ticket, or a second session on the
same branch - clobber each other's diff and output mid-run. Claim one that is
scoped to both:

```bash
SCRATCH=$(mktemp -d ".work/review/$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr -c 'A-Za-z0-9._-' '-')-XXXXXX")
echo "SCRATCH=$SCRATCH"
```

`mktemp`'s branch-prefixed, randomly-suffixed directory is ticket-scoped (the
branch name) and session-scoped (no other process can be handed the same
path). Record the printed `SCRATCH` value and use that exact path everywhere
`$SCRATCH` appears below - do not recompute it partway through, or step 3 will
read a different review than the one that ran.

**Step 0b - which specialists does this diff require?** Read `.crew/verify.json`.
For every rule whose `paths` match a changed file, collect its `agents` list.
Those subagents review **in addition to** the general reviewer below, each in its
own context, and each gets only the files its rule matched - not the whole diff.

```bash
git diff --name-only HEAD; git ls-files --others --exclude-standard
```

A rule with `"agents": ["dba"]` on `sql/**` means a migration is never reviewed
by the generalist alone. This is the only thing that reads `agents`: the `Stop`
hook cannot spawn a subagent, so the key is deliberately a review-time concern
rather than a gate-time one. If no matched rule names an agent, skip to step 1.

**Step 1 — pick the reviewer.** Read `.crew/config.json` -> `qa.provider`.

- `"codex"` or `"auto"`: check `command -v codex`. If found, use Codex (step 2a).
- If not found, or provider is `"claude"`: use the fallback (step 2b).
- Say which reviewer ran. Never silently downgrade.

**Step 2a — Codex.**
```
git diff $(git merge-base HEAD "$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||' || echo main)")...HEAD > $SCRATCH/diff.txt
codex exec --skip-git-repo-check "Review $SCRATCH/diff.txt as a hostile QA engineer.
Output one line per defect: SEVERITY|file:line|what breaks|how to reproduce.
SEVERITY is BLOCK, FIX, or NIT. Check: unintended behavior changes, unhandled
error paths, boundary and empty-collection cases, concurrency, and anything the
change makes reachable that was not before. Output nothing but those lines.
If no defects, output exactly: CLEAN" > $SCRATCH/out.txt 2>&1
```
Read ONLY `$SCRATCH/out.txt`. Never load the diff back into your context.

**Step 2b — Claude fallback.** Invoke the `crew:qa-reviewer` subagent. It reviews
in its own context so it has not seen your reasoning for writing the code.
Write its output to `$SCRATCH/out.txt` in the same format.

The fallback is genuinely weaker than Codex: same model family reviewing itself
finds fewer defects. Tell me when it is what ran, so I review harder myself.

**Step 2c — re-run the failing control, do not read about it.** If the diff
adds or edits a test, guard, assertion or smoke step, the author is expected to
have broken it on purpose and shown it go red. A pasted RED transcript is a
claim about a mutation, not the mutation. Where the check is runnable here, run
it yourself: revert the guard's condition (or delete the line it asserts on),
run the check, confirm it fails with a message naming the thing under test,
then restore. Report which controls you re-ran and which you could only take on
the author's word. An unverified control is a BLOCK, not a NIT — a check that
has never been shown to fail is the defect class this crew loses the most time
to.

**Step 3 — act.**
1. Report every BLOCK and FIX line verbatim. Do not soften or argue before showing me.
2. Fix all BLOCK items. Rerun `./_verify/smoke.sh`. Rerun this review once.
3. If you disagree with a finding, say so explicitly and let me decide.
4. **Land the verdict as a review, not a comment.** If the change is on a
   GitHub PR, post the outcome with `gh pr review` so it exists as an artifact
   that tooling and branch protection can see:

   ```bash
   gh pr review <PR> --request-changes --body-file "$SCRATCH/out.txt"   # any BLOCK
   gh pr review <PR> --approve        --body "<reviewer>: CLEAN"        # no BLOCK
   ```

   A verdict posted as `gh pr comment` is invisible to every mechanism that
   could act on it: nothing distinguishes approved from blocked from
   never-reviewed without a human reading threads, and an unprotected branch
   cannot refuse a merge on the strength of a comment. Say which form you used.
   If the repo has no PR yet, say that instead of silently skipping the step.
5. If `notify.provider` is not `none`, send one line:
   `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh review "<n> BLOCK, <n> FIX (<reviewer>)"`
   Counts only. Never the findings themselves — those stay in the repo.
6. Append the result to `.crew/metrics.md`: `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`
7. Name every specialist from step 0 that ran, and every one that a matched rule
   asked for but you skipped. A review that quietly dropped the `dba` pass on a
   migration reads exactly like one that had nothing to find.

That metrics line is not bookkeeping. `/crew:scale` reads it to decide whether
this setup is actually catching anything.
