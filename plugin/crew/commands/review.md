---
description: Independent QA review of the current diff (Codex, Copilot, or Claude - first that probes clean)
argument-hint: "[ticket id]"
allowed-tools: Bash, Read, Agent
---

Run independent review of the working diff — called after tests and docs, last, so the reviewer reads the finished change, not a draft a later edit moves out from under it.

**Step 0a - claim a scratch directory.** A fixed `.work/review-*.txt` path
collides: two concurrent reviews - a second ticket, or a second session on the
same branch - clobber each other's diff and output mid-run. Claim one that is
scoped to both:

```bash
# `mkdir -p` first: `mktemp -d` creates the LEAF, never the parents, so without
# this it fails with "No such file or directory" on any checkout where
# `.work/review/` does not already exist - which is every fresh one.
mkdir -p .work/review
SCRATCH=$(mktemp -d ".work/review/$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr -c 'A-Za-z0-9._-' '-')-XXXXXX")
echo "SCRATCH=$SCRATCH"
TICKET="${1:-$(awk -F'|' 'NF>1{gsub(/^[ \t]+|[ \t]+$/,"",$2);if($2~/^(open|in-progress|in progress|review)$/){c++;t=$1}} END{if(c==1)print t}' .work/INDEX.md 2>/dev/null | tr -d ' ')}"  # no $1: exactly one active row, else empty - stop and ask, never guess
[ -n "$TICKET" ] || { echo "no ticket id and no single active ticket - stop and ask" >&2; exit 1; }
```

**Review runs after tests and docs**, and has **two rounds per ticket in
total** (`review_ledger.py`, in `<git-common-dir>/crew/review/<id>.json`,
shared by every worktree). A round is reserved before the reviewer launches,
so a crashed one still counts; a third is refused and the ticket becomes
`NEEDS_REPLAN`. Round 2's FINDINGS can still be accepted until then. No flag,
variable or config key raises or resets it.

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
rather than a gate-time one.

**Three outcomes here, and you must say which one happened. They are not
interchangeable.**

| What you found | Say | Then |
|---|---|---|
| `.crew/verify.json` does not exist | `no verification map - run /crew:init; no specialist review was selected` | step 1 |
| it exists, no rule matched a changed file | `verification map read; no rule matched, so no specialist is required` | step 1 |
| it exists, a rule matched | name each agent and why | dispatch them |

**The first row is the one that used to disappear.** `.crew/*` is ignored, and
`!.crew/verify.json` is one of three named un-ignores, so in a repo that has
adopted that list the map travels — but a repo that has not, or one where
`/crew:init` has never run, still has **no map at all**. An absent map selects
nobody, which is indistinguishable from "this diff needs no specialist" unless
you distinguish it.
Never let "I could not look" be reported as "I looked and found nothing": that
is this repo's recurring bug, an unknown collapsing into the safe-looking value,
sitting in the review path itself.

**A rule may name any installed subagent, not only crew's own roles.** Resolve a
bare name as crew's own role first (`security` → `crew:security`), then as any
other installed agent of that name; a namespaced name (`voltagent:security-auditor`)
is taken literally. This is how a path match pulls in a domain specialist —
`powershell-security-hardening` on `**/*.ps1`, `security-auditor` on `iam/**` —
from evidence rather than from someone remembering.

**An agent a matched rule named but that is not installed here is a GAP, and you
report it in step 3 alongside the ones you skipped.** Never drop it silently.
The map was written against whatever was installed on the box that ran
`/crew:verify` — a rule can name an agent that exists there and not here, and the
review then covers strictly less while producing output indistinguishable from a
full pass. Tracking the map makes this MORE likely, not less: a committed map
reaches machines whose agent roster nobody checked. That is the same class of failure as a QA
provider that authenticates and then returns nothing, and it gets the same
treatment: say it out loud.

(The reason here has been wrong in both directions — "the map travels" when it
was ignored, then "it is ignored" after 2026-09-14 un-ignored it. The
conclusion survived both: name what you could not look at. Cite the gitignore
**stanza**, never a line number; line citations here moved when negations did.)

**Step 1 — who wrote this diff, and how do we know?** Ask the thing that
recorded the dispatch, rather than re-deriving the answer from config:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --models
```

Its first line names the author family **and its source**, and you repeat that
source everywhere you name the family — never the family alone:

| First line says | What it means | You say |
|---|---|---|
| `author family: <f>  (recorded at dispatch)` | `.work/dispatch.json` holds the role, provider and model that actually ran, and the guard is judging what ran | `author: <f>, recorded dispatch <role>/<provider>/<model>` — the `last dev dispatch:` line printed right under it |
| `author family: <f>  (READ FROM CONFIG - no dispatch recorded...)` | nothing was recorded in this checkout, so the report read `dev` out of the config | `author: <f>, READ FROM CONFIG - no dispatch recorded, so this is what the NEXT run would use and not who wrote this diff` |
| `author family: <f or unknown>  (UNKNOWN - a dispatch on this branch has a family that cannot be determined, or something in .work/ would not parse...)` | either at least one dispatch's family cannot be determined -- an unpinned provider that hosts several families, so `family()` has nothing to answer with -- or a file in `.work/` exists and would not parse, so the store cannot say whether the dispatch that wrote this diff is among the ones it CAN read | `author: UNKNOWN - a dispatch on this branch has a family that cannot be determined, so no reviewer can be proven independent of it`. **This is not a pass.** Read the family line: if it names one, that family DID run and is struck, and the source is `unknown` because a second dispatch beside it could not be named; if it names none, nothing is struck and every candidate looks eligible. Either way the report sets `independentReviewer: false`. Say the review is not certified independent, and say that pinning `dev.<provider>.model` is what fixes it |

A recorded fact and a config-derived guess look identical once both are just the
word `claude`. The label is the only thing that separates them, so a review that
prints the family and swallows the source has withheld the half that says how
much to trust the bar it just applied.

**Step 1a — is that record about THIS diff?** Compute the diff's base here, in
step 1, and carry `$BASE` forward — step 2 reuses it rather than recomputing it,
for the same reason `$SCRATCH` is carried:

```bash
# The ticket's START, recorded by /crew:work step 1 (`scope_base.py --record`): <!-- deliberate -->
# the same range /crew:work's scope evidence covers, so the bundle -- and the <!-- deliberate -->
# receipt bound to its hash -- is this ticket's change, not everything on the
# branch since the trunk. With no record, or one this clone no longer holds,
# scope_base.py itself falls back to the merge-base with the default branch
# and says "(fallback)" on stderr; repeat that word in the verdict when it does.
BASE=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --base "$TICKET")
if [ -z "$BASE" ]; then
  # scope_base.py did not run at all (no python3). The stated fallback:
  # the merge-base. `... | sed ... || echo main` does NOT work: the || binds
  # to the whole pipeline and sed exits 0 even when symbolic-ref failed, so
  # the fallback never fires and merge-base is handed an empty string.
  # Branch on the ref itself.
  DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null) || DEFAULT_BRANCH=""
  DEFAULT_BRANCH=${DEFAULT_BRANCH#origin/}
  : "${DEFAULT_BRANCH:=main}"
  BASE=$(git merge-base HEAD "$DEFAULT_BRANCH")
  echo "review base: merge-base with $DEFAULT_BRANCH (fallback - scope_base.py did not run)"
fi

# The NEWEST of `.work/dispatch.json` and anything in `.work/dispatch.d/`.
# Since 0.16.7 each dispatch writes its own file in that directory and the
# shared `dispatch.json` slot is a best-effort convenience -- so a slot write
# that lost a race, or failed outright, would report this branch as having no
# record while the store holds several. Reading only the one file makes a
# recorded dispatch look absent, which fails OPEN: the review falls back to
# the config and clears whatever the config no longer names.
#
# A missing python3 must not take the review down with it, hence the `|| echo 0`.
REC_AT=$(python3 -c '
import os, sys
stamps = []
for path in (".work/dispatch.json", ".work/dispatch.d"):
    try:
        stamps.append(os.path.getmtime(path))
    except OSError:
        pass
    for name in (os.listdir(path) if os.path.isdir(path) else []):
        try:
            stamps.append(os.path.getmtime(os.path.join(path, name)))
        except OSError:
            pass
print(int(max(stamps)) if stamps else 0)
' 2>/dev/null || echo 0)
BASE_AT=$(git log -1 --format=%ct "$BASE" 2>/dev/null) || BASE_AT=0
: "${BASE_AT:=0}"
echo "record=$REC_AT base=$BASE_AT branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"

# Carry the verdict forward as a FLAG, not as a note to yourself. Step 2 passes
# it to crew_config.py so the resolved report strikes both families too; without
# it the report says `dispatch` with one family in it while the table below tells
# you to strike two, and the resolved data is what every later step reads.
STALE_FLAG=""
if [ "$REC_AT" -gt 0 ] && [ "$BASE_AT" -gt 0 ] && [ "$REC_AT" -lt "$BASE_AT" ]; then
  STALE_FLAG="--author-stale"
fi
```

| Reading | Means | Do |
|---|---|---|
| `REC_AT` is `0` | no record anywhere -- neither `.work/dispatch.json` nor `.work/dispatch.d/` -- or no `python3` | source is `config`; announce it in those words |
| `REC_AT >= BASE_AT` | the record is no older than the review base (the ticket's start, or the merge-base on fallback) | trust it |
| `REC_AT < BASE_AT` | **STALE** — the record predates every commit under review, so it cannot describe any of them | fail closed, below |

Compare against the **base**, never the tip. The normal sequence is implement,
record, commit, review, so the record is routinely older than `HEAD` and a
tip comparison would report STALE on every healthy review — which collapses the
guard into a permanent "no independent reviewer" and teaches everyone to ignore
it.

**A stale record is fail-closed, not discarded.** Strike **both** the family the
record names and the family the config names, and say you did both. Dropping the
stale record and trusting config is the one direction that can under-bar: if
codex wrote the commits and the config has since been changed to `claude`,
discarding the record clears codex to review its own work. Over-barring costs a
rung; under-barring costs the entire point of the guard. If striking both leaves
no candidate, that is the same state as striking one and leaving none — step 2c
runs and the verdict says same-family.

**This test proves stale, and never proves fresh. Say so.** The dispatch record
is one file per checkout with a single `dev` slot, and the record carries no
branch and no ticket — so a dispatch made on another branch overwrites it and
then reads as perfectly fresh here. Print the recorded `role`/`provider`/`model`
next to the current branch and the ticket under review, so a human can see a
mismatch this command cannot detect. **If the recorded role has nothing to do
with the work you are reviewing, treat it as stale and fail closed.**

**Step 1b — strike the author's family, then pick.** The report has already
applied the guard to its own `qa` rows and printed the `qa.order` fall-through;
apply the same strike to the provider you are about to run. When the source is
`config` rather than a record, the family comes from `dev.provider`:

| `dev.provider` | Struck from QA |
|---|---|
| `claude` (default) | `claude` — the `qa-reviewer` fallback | <!-- deliberate -->
| `codex` | `codex` |
| `copilot` | whichever family `dev.copilot.model` names — `gemini-*` strikes nothing here, `claude-*` strikes the fallback, `gpt-*` strikes Codex |

A family reviewing its own output agrees with itself, and that is the exact
failure this command exists to catch. Apply the strike at review time. Do not
rely on `qa.order` having been edited to match; the two keys are set at different
times by different people, and the ordering is a preference while this is a rule.

If striking the author's family leaves **no** candidate, fall back to step 2c and
say **in the verdict itself** that this review is same-family and does not count as
independent. Do not refuse to review: a repo with neither Codex nor Copilot still
benefits from the weaker pass, and `README.md`, `agents/pm.md` and `crew-pm` all
document `qa-reviewer` as the fallback — a step 1 that stopped instead would <!-- deliberate -->
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
# Resolve through crew_config, NEVER by re-reading .crew/config.json. That file
# is one layer of three, and it does not know about the `roles` table at all:
# reading it directly made both `qa.roles.review` and every value set in
# ~/.claude/crew/config.json invisible to the only command that actually runs a
# review, so /crew:model would report the pinned reviewer while /crew:review ran
# the block default. One resolver, or the report and the run describe different
# machines.
REPORT="$SCRATCH/models.json"
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py \
  --root . --models --json $STALE_FLAG > "$REPORT"

# What model would PROVIDER use for the `review` role? The role pin wins when it
# names that provider; otherwise the provider's own block does. Absent stays
# empty -- "pass no flag", never "crash" and never a literal "None" on the
# command line.
qm() { python3 -c '
import json, sys
report, want = json.load(open(sys.argv[1])), sys.argv[2]
field = sys.argv[3]
row = next((r for r in report.get("qa") or []
            if r.get("role") == "review"), {})
if row.get("provider") == want and row.get(field):
    print(row[field]); raise SystemExit
block = (report.get("qaProviders") or {}).get(want) or {}
print(block.get(field) or "")
' "$REPORT" "$1" "${2:-model}"; }

QA_MODEL=$(qm codex model)
QA_EFFORT=$(qm codex reasoningEffort)
QA_COPILOT_MODEL=$(qm copilot model)

# The author families to strike, from the same report -- never re-derived from
# dev.provider, which is a default a per-role pin may already have overridden.
# This is a SET: a stale or branchless record strikes the recorded family AND
# the configured one, because neither can be ruled out as the author.
AUTHORS=$(python3 -c 'import json,sys;print(" ".join(sorted(json.load(open(sys.argv[1])).get("authorFamilies") or [])))' "$REPORT")
AUTHOR_SOURCE=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("authorSource") or "")' "$REPORT")

# Which candidates survive that strike, and can actually run. The report has
# already applied the guard -- this is the list to pick from, in order, and an
# empty one is the "no independent reviewer" state, not an error.
ELIGIBLE=$(python3 -c '
import json, sys
report = json.load(open(sys.argv[1]))
print(" ".join(c["provider"] for c in report.get("qaFallThrough") or []
                if c.get("eligible")))' "$REPORT")
echo "authors=$AUTHORS source=$AUTHOR_SOURCE eligible=${ELIGIBLE:-<none>}"
```

**Use `$ELIGIBLE`, in that order, and say `$AUTHOR_SOURCE` out loud.** It is the
report's own answer to "who may review this", with the family guard already
applied and `qa.order` already walked. Re-deriving the choice from `qa.provider`
here would be a second implementation of the rule that can disagree with the one
`/crew:model` prints. An empty `$ELIGIBLE` is step 2c: run the `qa-reviewer` <!-- deliberate -->
fallback and say in the verdict that this review is same-family and does not
count as independent.

`source=stale` means the recorded dispatch could not be tied to this diff -- a
different branch, an unrecorded branch, or a record older than the review base --
so **both** the recorded and the configured family were struck. Report that as
the reason a rung was lost, rather than presenting the narrower candidate list
as though it were a preference.

```bash

# $BASE comes from step 1a. Reuse it; do not recompute it here. A second
# derivation can disagree with the first, and then the staleness verdict was
# about a different range than the diff the reviewer actually read.
#
# review_patch.py builds ONE bundle: committed range PLUS staged, unstaged and
# untracked changes, with renames, modes, binaries and submodules in the
# manifest, split into parts (never truncated) and hashed. `git diff
# "$BASE"...HEAD` alone gave a 0-byte patch on a dirty tree (found by Codex,
# `docs/review/03-codex-review.md`). The real index is never written.
MANIFEST="$SCRATCH/manifest.json"
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_patch.py \
  --root . --base "$BASE" --out "$SCRATCH/diff.txt" --manifest "$MANIFEST"
PATCH_STATUS=$?
if [ "$PATCH_STATUS" -eq 2 ]; then
  echo "nothing to review: HEAD matches $BASE and the tree is clean"
  exit 0
elif [ "$PATCH_STATUS" -ne 0 ]; then
  echo "review-patch failed (exit $PATCH_STATUS) -- see stderr above. This is a defect in building the review input, not an empty diff to wave through."
  exit "$PATCH_STATUS"
fi

# The ticket contract: bundle parts + READ acks, spec sections (Intent,
# Exclusions, Evidence, Unknowns, Acceptance checks), plan, test receipts.
# Anything absent is written as MISSING, never left out.
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_prompt.py --root . \
  --ticket "$TICKET" --manifest "$MANIFEST" --out "$SCRATCH/contract.txt"

# Gather this repo's own failure modes INTO the shared prompt, so every
# provider gets them -- wiring them into qa-reviewer.md alone reached only the <!-- deliberate -->
# fallback. Byte-identical instructions across providers is this file's
# invariant: never append for one provider.
# The changed-file list MUST be built here, before the loop greps it (an
# earlier draft grepped a changed.txt nothing wrote, and every review got an
# empty landmine section), and from $MANIFEST, not a second `git diff` that
# could disagree with what review_patch.py actually bundled.
python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
files = set()
for key in ("committed_files", "staged_files", "unstaged_files", "untracked_files"):
    files.update(m.get(key) or [])
sys.stdout.write("".join(f + "\n" for f in sorted(files)))
' "$MANIFEST" > "$SCRATCH/changed.txt"

: > "$SCRATCH/context.txt"
for note in .crew/codemap/*.md; do
  [ -e "$note" ] || continue
  case "$note" in */INDEX.md) continue ;; esac
  # Only notes whose cited paths intersect this diff. A reviewer handed every
  # landmine in the repo reads none of them. `-F` because a path is a literal,
  # not a pattern; an empty changed.txt matches nothing, which is correct.
  if [ -s "$SCRATCH/changed.txt" ] && grep -qFf "$SCRATCH/changed.txt" "$note"; then
    sed -n '/^## Landmines/,/^## /p' "$note" >> "$SCRATCH/context.txt"
    sed -n '/^## Written by \/ Read by/,/^## /p' "$note" >> "$SCRATCH/context.txt"
  fi
done
# KNOWN OVER-MATCH, stated rather than hidden: a widely-cited path
# (`README.md`) matches almost every note (measured: 7 of 10 notes, 333 lines,
# on a 13-file diff). Too much rather than too little, but not precision.
#
# So cap it, and make the cap ANNOUNCE itself. A prompt silently truncated
# mid-landmine is worse than one that says it was cut: the reviewer cannot
# tell a short landmine list from a truncated one.
if [ "$(wc -l < "$SCRATCH/context.txt")" -gt 200 ]; then
  head -200 "$SCRATCH/context.txt" > "$SCRATCH/context.trim" &&
  printf '
[TRUNCATED at 200 lines of %s. More landmines exist in .crew/codemap/ than fitted here.]
'     "$(wc -l < "$SCRATCH/context.txt")" >> "$SCRATCH/context.trim" &&
  mv "$SCRATCH/context.trim" "$SCRATCH/context.txt"
fi

# An empty context file is a real answer (no intersecting note, or no codemap)
# and must SAY so rather than silently producing a prompt that looks complete.
if [ ! -s "$SCRATCH/context.txt" ]; then
  printf 'No codemap note intersects this diff, so no repo-specific landmines were supplied.
' > "$SCRATCH/context.txt"
fi

# Write the prompt HERE, before any provider block reads it. All three reviewers
# get byte-identical instructions, so a defect count that differs between them is
# a fact about the model and not about how you worded it. Unquoted heredoc marker
# so $SCRATCH becomes the real path - a reviewer handed the literal string
# "$SCRATCH/diff.txt" opens nothing and reports CLEAN on a file it never read.
cat > "$SCRATCH/prompt.txt" <<EOF
Review the change in $SCRATCH/diff.txt, read as the parts listed below, as a
hostile QA engineer, against the ticket's spec and plan below.
Output one line per defect: SEVERITY|file:line|what breaks|how to reproduce.
SEVERITY is BLOCK, FIX, or NIT. Check: unintended behavior changes, unhandled
error paths, boundary and empty-collection cases, concurrency, anything the
change makes reachable that was not before, and every acceptance check.
Output nothing but the READ lines and those lines - no code fences, no prose.
If no defects, after the READ lines output exactly: CLEAN

$(cat "$SCRATCH/contract.txt")

This repository's own recorded failure modes follow. They come from its code
map, where each line was written because it already cost someone real time
here. Treat them as leads to check in the diff, not as findings to repeat: a
landmine this change does not touch is not a defect, and reporting it as one
trains the reader to skim your output.
$(cat "$SCRATCH/context.txt")
EOF
```

**Step 2a — Codex, 2b — Copilot.** `review_run.py` reserves the round, then
launches the reviewer with stdin closed (a real run hung on stdin), then
computes the verdict and writes `.work/tickets/$TICKET/review.json`. Codex runs
as `codex exec --json --sandbox read-only`, read from its event stream, so a
failed turn is INCOMPLETE even at exit 0. Copilot keeps `--deny-tool write
--deny-tool shell`: a reviewer that can edit the code can "fix" a defect instead
of reporting it. Empty model/effort pass no flag.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_run.py --root . --ticket "$TICKET" \
  --scratch "$SCRATCH" --provider codex --model "$QA_MODEL" --effort "$QA_EFFORT"
# or: --provider copilot --model "$QA_COPILOT_MODEL"
REVIEW_STATUS=$?   # 0 CLEAN, 1 FINDINGS, 3 INCOMPLETE, 4 NEEDS_REPLAN, 2 not run
```

`reasoningEffort` accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`;
Codex rejects a wrong one with an HTTP 400. Copilot exiting non-zero with `Access
denied by policy settings` is org or enterprise policy — report that exact
cause. Exit 2 means nothing launched (not on PATH) and no round was spent; walk
to the next eligible provider.

**Step 2c — Claude fallback.** Invoke the `crew:qa-reviewer` subagent with the
SAME bundle 2a and 2b just read: the exact `$SCRATCH/prompt.txt` content —
byte-identical instructions, per this file's own invariant — plus the concrete
paths `$SCRATCH/diff.txt` and `$SCRATCH/manifest.json`. Tell it to review that
patch only; it must not re-derive its own diff with `git diff` — that is the
same committed-range-only mistake `review_patch.py` exists to fix (found by
Codex, `docs/review/03-codex-review.md`), and a subagent computing its own
`git diff` fresh can miss the staged, unstaged and untracked content the
manifest already captured. It reviews in its own context so it has not seen
your reasoning for writing the code. Reserve the round BEFORE dispatching it,
then hand its output to the same verdict parser:

```bash
ROUND=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_run.py --root . --ticket "$TICKET" \
  --scratch "$SCRATCH" --provider claude --reserve-only | sed -n 's/^ROUND=//p')
# ... dispatch crew:qa-reviewer; write its output to $SCRATCH/out.txt ...
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_run.py --root . --ticket "$TICKET" \
  --scratch "$SCRATCH" --provider claude --round "$ROUND" \
  --output "$SCRATCH/out.txt" --exit-code 0
```

An empty `ROUND` is a refusal (budget spent): do not dispatch.

The fallback is genuinely weaker than a different family: the same model family
reviewing itself finds fewer defects. Tell me when it is what ran, so I review
harder myself.

**The shared prompt is written in step 2**, before any provider runs. Do not
re-word it per provider: identical instructions are what make a differing
defect count a fact about the model rather than about the prompt.

Read ONLY `$SCRATCH/out.txt` and the `review:` lines. Never load the diff back
into your context. **The verdict is the script's, not yours**: CLEAN only for
exactly `CLEAN` at exit 0 with every part acknowledged; any BLOCK/FIX/NIT is
FINDINGS; a non-zero exit, empty or unparseable output, a skipped part or a
timeout is INCOMPLETE — never report INCOMPLETE as clean.

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
1. Report every BLOCK and FIX line verbatim. Do not soften or argue before
   showing me. State the review range and file list **from `$MANIFEST`**, not
   by re-deriving it: base, head, branch, whether the tree was dirty, and
   which category (committed / staged / unstaged / untracked) each changed
   file fell into is the one record of what was actually reviewed.
2. Fix all BLOCK items. Rerun `./_verify/smoke.sh`. Rerun this review once —
   round 2 is the last. A refusal (exit 4, `NEEDS_REPLAN`) is terminal in this
   release: stop, say so, and replan the ticket; there is no third round.
3. If you disagree with a finding, say so explicitly and let me decide. If I
   accept FINDINGS as they stand, record it — the receipt names who and when:
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_ledger.py --ticket "$TICKET" --accept --by "<who>"`.
   Only the most recent round can be accepted, once, including round 2, and not
   once the ticket is `NEEDS_REPLAN` (a refused third reservation, or
   `review_ledger.py --ticket "$TICKET" --reject --by "<who>"`). A CLEAN round writes its receipt itself. `review_ledger.py --ticket "$TICKET"
   --check-receipt` rebuilds the bundle and fails if anything changed since.
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
   (counts from `review.json`; an INCOMPLETE round is recorded as INCOMPLETE, not as 0/0)
7. Name every specialist from step 0 that ran, every one that a matched rule
   asked for but you skipped, and every one that a matched rule named but that
   **is not installed on this machine**. A review that quietly dropped the `dba`
   pass on a migration reads exactly like one that had nothing to find, and a
   rule naming an agent this box does not have fails the same way while looking
   even more normal — there is nothing to skip, so nothing feels skipped.

   Record the not-installed ones in `.crew/metrics.md` too. `/crew:scale` reads <!-- deliberate -->
   that file, and "this rule has asked for `security-auditor` eleven times and
   never got it" is exactly the evidence that should drive either installing it
   or deleting the rule.
8. Name the author family **and its source** in the same breath as the reviewer:
   `recorded dispatch <role>/<provider>/<model>`, `READ FROM CONFIG - no
   dispatch recorded`, or `STALE RECORD - both families struck`. Which family
   was barred is only checkable by a reader who knows whether the bar rests on a
   fact or on a guess, and that is the whole difference this record exists to
   make visible.

That metrics line is not bookkeeping. `/crew:scale` reads it to decide whether <!-- deliberate -->
this setup is actually catching anything.
