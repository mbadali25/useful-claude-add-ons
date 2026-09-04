---
description: Independent QA review of the current diff (Codex, Copilot, or Claude - first that probes clean)
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

**A rule may name any installed subagent, not only crew's eleven.** Resolve a
bare name as crew's own role first (`security` → `crew:security`), then as any
other installed agent of that name; a namespaced name (`voltagent:security-auditor`)
is taken literally. This is how a path match pulls in a domain specialist —
`powershell-security-hardening` on `**/*.ps1`, `security-auditor` on `iam/**` —
from evidence rather than from someone remembering.

**An agent a matched rule named but that is not installed here is a GAP, and you
report it in step 3 alongside the ones you skipped.** Never drop it silently.
`.crew/verify.json` is committed and travels between machines, so a rule naming
an agent that exists on the author's box and not on this one would otherwise
review strictly less while producing output indistinguishable from a full pass.
That is the same class of failure as a QA provider that authenticates and then
returns nothing, and it gets the same treatment: say it out loud.

**Step 1 — pick the reviewer.** Read `.crew/config.json` -> `qa` **and** `dev`.

**First, disqualify the author's own family.** `dev.provider` says who wrote the
code. Whichever family that is, strike it from the candidate list before choosing —
a family reviewing its own output agrees with itself, and that is the exact failure
this command exists to catch.

| `dev.provider` | Struck from QA |
|---|---|
| `claude` (default) | `claude` — the `qa-reviewer` fallback |
| `codex` | `codex` |
| `copilot` | whichever family `dev.copilot.model` names — `gemini-*` strikes nothing here, `claude-*` strikes the fallback, `gpt-*` strikes Codex |

Apply this at review time, from the config as it currently reads. Do not rely on
`qa.order` having been edited to match; the two keys are set at different times by
different people, and the ordering is a preference while this is a rule.

If striking the author's family leaves **no** candidate, fall back to step 2c and
say **in the verdict itself** that this review is same-family and does not count as
independent. Do not refuse to review: a repo with neither Codex nor Copilot still
benefits from the weaker pass, and `README.md`, `agents/pm.md` and `crew-pm` all
document `qa-reviewer` as the fallback — a step 1 that stopped instead would
contradict all three.

What is forbidden is letting a same-family review be *recorded* as an independent
one. Announce it, and never write it to `.crew/metrics.md` as though a different
family had looked.

Then, if `qa.provider` names a provider (`codex`, `copilot`, `claude`), use that one
and **hard-fail if its probe fails** — a pinned provider that cannot run is an error,
not a cue to fall back. If `qa.provider` is `auto`, walk `qa.order` and take the
first surviving provider that passes its probe:

| Provider | Probe | Runs |
|---|---|---|
| `codex` | `command -v codex` | step 2a |
| `copilot` | `command -v copilot` **and** `qa.copilot.model` is set | step 2b |
| `claude` | always passes | step 2c |

Announce which reviewer ran **and every provider you skipped, with the reason**. A
skipped provider is the single most dangerous silent failure here: a QA gate that
quietly finds nothing looks exactly like a clean diff.

**Why `copilot` needs a model set to be eligible at all.** Copilot CLI defaults to
`claude-sonnet-4.6` — the author's own family. An unpinned Copilot is therefore a
*same-family* reviewer wearing the costume of an independent one, which is strictly
worse than step 2c, since 2c at least announces its own weakness. Skip it and say
`copilot skipped: qa.copilot.model not set`. If the configured model string starts
with `claude-`, run it but say plainly that this review is same-family and does not
count as independent.

**Step 2 — set up the run.** Extract the config values into the shell first, so the
provider blocks below are literally runnable rather than prose about themselves:

```bash
CFG=.crew/config.json
# .get() at EVERY level. A config written before these keys existed has no
# qa.codex / qa.copilot block, and indexing it directly is a KeyError that kills
# the review before it starts. Absent means "pass no flag", never "crash".
q() { python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print((d.get("qa") or {}).get(sys.argv[2],{}).get(sys.argv[3]) or "")' "$CFG" "$1" "$2"; }
QA_MODEL=$(q codex model)
QA_EFFORT=$(q codex reasoningEffort)
QA_COPILOT_MODEL=$(q copilot model)

BASE=$(git merge-base HEAD "$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|origin/||' || echo main)")
git diff "$BASE"...HEAD > "$SCRATCH/diff.txt"

# Write the prompt HERE, before any provider block reads it. All three reviewers
# get byte-identical instructions, so a defect count that differs between them is
# a fact about the model and not about how you worded it. Unquoted heredoc marker
# so $SCRATCH becomes the real path - a reviewer handed the literal string
# "$SCRATCH/diff.txt" opens nothing and reports CLEAN on a file it never read.
cat > "$SCRATCH/prompt.txt" <<EOF
Review $SCRATCH/diff.txt as a hostile QA engineer.
Output one line per defect: SEVERITY|file:line|what breaks|how to reproduce.
SEVERITY is BLOCK, FIX, or NIT. Check: unintended behavior changes, unhandled
error paths, boundary and empty-collection cases, concurrency, and anything the
change makes reachable that was not before. Output nothing but those lines.
If no defects, output exactly: CLEAN
EOF
```

**Step 2a — Codex.** Empty means "pass no flag", so an unconfigured repo invokes
exactly the command it always did.

```bash
codex exec --skip-git-repo-check \
  ${QA_MODEL:+--model "$QA_MODEL"} \
  ${QA_EFFORT:+-c model_reasoning_effort="$QA_EFFORT"} \
  "$(cat "$SCRATCH/prompt.txt")" > "$SCRATCH/out.txt" 2>&1
```

`reasoningEffort` accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`.
A wrong value is safe to get wrong: Codex rejects it with an HTTP 400 naming the
supported set, rather than silently ignoring it and returning a shallow review.

**Step 2b — Copilot.** Same prompt, different family. Denying `write` and `shell` is
not optional: a reviewer that can edit the code under review can "fix" a defect
instead of reporting it, and you would never see the finding. Copilot's permission
patterns are `kind(argument)` with the argument optional — a bare kind matches all
of it. File reads need no grant; path access already defaults to the working
directory and its subdirectories, which is where `$SCRATCH` lives.

```bash
copilot -p "$(cat "$SCRATCH/prompt.txt")" \
  --model "$QA_COPILOT_MODEL" \
  --deny-tool write --deny-tool shell \
  -s > "$SCRATCH/out.txt" 2>&1
```

If this exits non-zero with `Access denied by policy settings`, Copilot CLI is
disabled by org or enterprise policy — report that exact cause. It is the dangerous
failure: auth succeeds, the call returns nothing, and an empty findings file is
indistinguishable from a clean diff. Never record a CLEAN verdict from a run that
exited non-zero.

**Step 2c — Claude fallback.** Invoke the `crew:qa-reviewer` subagent. It reviews
in its own context so it has not seen your reasoning for writing the code.
Write its output to `$SCRATCH/out.txt` in the same format.

The fallback is genuinely weaker than a different family: the same model family
reviewing itself finds fewer defects. Tell me when it is what ran, so I review
harder myself.

**The shared prompt is written in step 2**, before any provider block runs, because
2a and 2b both `cat` it. Do not re-word it per provider: identical instructions are
what make a differing defect count a fact about the model rather than about the
prompt.

Read ONLY `$SCRATCH/out.txt`. Never load the diff back into your context.

**Step 2d — re-run the failing control, do not read about it.** If the diff
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
7. Name every specialist from step 0 that ran, every one that a matched rule
   asked for but you skipped, and every one that a matched rule named but that
   **is not installed on this machine**. A review that quietly dropped the `dba`
   pass on a migration reads exactly like one that had nothing to find, and a
   rule naming an agent this box does not have fails the same way while looking
   even more normal — there is nothing to skip, so nothing feels skipped.

   Record the not-installed ones in `.crew/metrics.md` too. `/crew:scale` reads
   that file, and "this rule has asked for `security-auditor` eleven times and
   never got it" is exactly the evidence that should drive either installing it
   or deleting the rule.

That metrics line is not bookkeeping. `/crew:scale` reads it to decide whether
this setup is actually catching anything.
