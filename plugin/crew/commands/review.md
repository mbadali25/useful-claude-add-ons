---
description: Independent QA review of the current diff (Codex if available, Claude if not)
allowed-tools: Bash, Read, Agent
---

Run independent review of the working diff.

**Step 1 — pick the reviewer.** Read `.crew/config.json` -> `qa.provider`.

- `"codex"` or `"auto"`: check `command -v codex`. If found, use Codex (step 2a).
- If not found, or provider is `"claude"`: use the fallback (step 2b).
- Say which reviewer ran. Never silently downgrade.

**Step 2a — Codex.**
```
git diff $(git merge-base HEAD "$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||' || echo main)")...HEAD > .work/review-diff.txt
codex exec --skip-git-repo-check "Review .work/review-diff.txt as a hostile QA engineer.
Output one line per defect: SEVERITY|file:line|what breaks|how to reproduce.
SEVERITY is BLOCK, FIX, or NIT. Check: unintended behavior changes, unhandled
error paths, boundary and empty-collection cases, concurrency, and anything the
change makes reachable that was not before. Output nothing but those lines.
If no defects, output exactly: CLEAN" > .work/review-out.txt 2>&1
```
Read ONLY `.work/review-out.txt`. Never load the diff back into your context.

**Step 2b — Claude fallback.** Invoke the `crew:qa-reviewer` subagent. It reviews
in its own context so it has not seen your reasoning for writing the code.
Write its output to `.work/review-out.txt` in the same format.

The fallback is genuinely weaker than Codex: same model family reviewing itself
finds fewer defects. Tell me when it is what ran, so I review harder myself.

**Step 3 — act.**
1. Report every BLOCK and FIX line verbatim. Do not soften or argue before showing me.
2. Fix all BLOCK items. Rerun `./scripts/smoke.sh`. Rerun this review once.
3. If you disagree with a finding, say so explicitly and let me decide.
4. If `notify.provider` is not `none`, send one line:
   `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh review "<n> BLOCK, <n> FIX (<reviewer>)"`
   Counts only. Never the findings themselves — those stay in the repo.
5. Append the result to `.crew/metrics.md`: `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`

That metrics line is not bookkeeping. `/crew:scale` reads it to decide whether
this setup is actually catching anything.
