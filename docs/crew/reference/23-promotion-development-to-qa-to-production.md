<!-- Moved verbatim from plugin/crew/README.md (23. Promotion: development to qa to production) by L-0726; the README keeps an index entry. -->

## 23. Promotion: development to qa to production

A merge is not a deploy, a deploy is not a working application, and a green pipeline says only that the pipeline is green. Section 8 gates a *working tree*; this gates a *running environment*.

```
/crew:promote qa
/crew:promote production --dry-run
/crew:promote --status
```

### Five gates, in order, stopping at the first failure

| # | Gate | Answers |
|---|---|---|
| 1 | Pre-deploy | Is the source environment green, and is this the artifact it proved? |
| 2 | Deploy | Did the deployment mechanism report success? |
| 3 | Smoke | Does the deployed thing respond at all, in this environment? |
| 4 | Regression | Does everything that worked yesterday still work? |
| 5 | Verify | Are the environment's own signals clean — error logs, alarms, queues? |

Gate 2 is the weakest evidence in the list and the one most often mistaken for the whole set. A successful deploy proves bytes moved. Gates 3 to 5 are what prove the application works.

Smoke and regression are deliberately separate. Smoke passing tells you the deploy landed; it says nothing about the module three directories over that just broke. A promotion that only smoke-tests has skipped the gate that catches regressions, which is the gate that catches the expensive ones.

### Declared, not remembered

The sequence lives in the `environments` block of `.crew/verify.json`, beside the path rules:

```json
"environments": {
  "qa": {
    "requires":     ["development"],
    "deploy":       ["./scripts/deploy.sh qa"],
    "smoke":        ["./_verify/smoke.sh --env qa"],
    "regression":   ["./_verify/run-all.sh --env qa", "npx playwright test --grep @flow"],
    "verify":       ["./_verify/check-logs.sh qa --since 10m"],
    "soakMinutes":  10,
    "rollback":       "none",
    "rollbackReason": "qa is rebuilt from the latest development deploy; there is nothing to roll back to",
    "promotesTo":   "production"
  },
  "production": {
    "requires":     ["qa"],
    "deploy":       ["./scripts/deploy.sh prod"],
    "smoke":        ["./_verify/smoke.sh --env prod"],
    "regression":   ["./_verify/run-all.sh --env prod --read-only"],
    "verify":       ["./_verify/check-logs.sh prod --since 15m", "./_verify/check-alarms.sh prod"],
    "soakMinutes":  15,
    "rollback":     "docs/runbooks/rollback.md",
    "requireHuman": true
  }
}
```

`/crew:init` Phase 8 builds this by asking, per environment, what actually deploys it and what actually proves it worked. It fills in only what exists. A block with `deploy` and `smoke` and nothing else is honest; one with five aspirational commands nobody has run is worse than an empty file, because it reads as coverage.

**A GitHub Actions deploy** (first slice only) is described by a `github` entry in the environment: the workflow filename, a branch-name `ref` (checked as a name only: a bare tag name is not detected), fixed `inputs`, and optionally `shaInput`, `correlationInput`, `deployJob`, `watchMinutes` and `identifySeconds`. `deploy` must list each entry's canonical prefix (`gh workflow run <workflow> --ref <ref> -f k=v ...`). `python3 hooks/scripts/crew_ghdeploy.py check --root . --env <name>` validates the entry, refuses any value outside `[A-Za-z0-9._/@:+-]` by name, refuses a map either promote gate refuses, and prints the literal dispatch for HEAD with `gated-as:` - every environment the gates apply to it (the union rule of L-1503: a command matching several environments carries all their requirements); it writes nothing and runs no `gh`. `crew_ghdeploy.py prepare` (L-0644) runs before the dispatch: it refuses (exit 2, nothing written) on an entry problem, an unmapped workflow, a class T-0009's classifier cannot name or that does not match the environment's, an unreadable actor, a sha not on the remote, a branch tip that is not HEAD (no `shaInput`) or an unreadable run list; otherwise it snapshots the actor's existing runs into `.crew/.ghdeploy/<env>-<N>.json` and prints the dispatch, which the session runs as its own Bash call. It never dispatches. `crew_ghdeploy.py identify` (L-0645) then names the one new run (not in the snapshot, `workflow_dispatch`, on the ref, created no earlier than `t0` minus 30 seconds, and titled with the correlation id when one was sent), polling for up to `identifySeconds`; two candidates, none, or anything unreadable is could-not-tell (exit 3) and names no run. `crew_ghdeploy.py watch` (L-0646) follows that run in slices of at most 570 seconds (exit 75: call again) and answers pass (exit 0), fail (1) or unknown (3) from `gh run view` - the conclusion, the `deployJob` job and, with no `shaInput`, the head sha - never from the watch's exit code; it never cancels a run. `crew_ghdeploy.py record` (L-0647) writes the outcome into `.work/PROMOTIONS.md`: a detail line with no pipe and, on anything but pass, the previous good sha, a cleaned failed-step log excerpt and a `not-run` row that never satisfies `requires`. `/crew:promote` gate 2 runs the five steps for a `github` environment (prepare, dispatch, identify, watch, record); the sequence and its exit codes are in `skills/crew-verification/github-deploy.md`. The key table is in the crew-verification skill, section 4.

### The promotion record

Every promotion appends a row to `.work/PROMOTIONS.md`, failures included:

```
| when (UTC) | env | sha | smoke | regression | verify | by |
|---|---|---|---|---|---|---|
| 2026-08-23T14:02Z | qa | a1b2c3d4e5f60718293a4b5c6d7e8f9012345678 | pass | pass | pass | mbadali |
```

The sha is written **in full** (40 characters). Since L-0703 `requires`
counts a row only when its sha cell is the deploying commit's full sha (case
ignored): a short row such as `a1b2c3d` never counts, even for the right
commit, and the block names it. A 7-character match admitted a PASS row for a
different commit that shares the prefix. Breaking change: re-record an old
short row (re-run the promotion, or rewrite the row with the full sha after
checking it).

`requires` reads this file. It is also the only honest answer to "is production running what qa signed off on" — compare the shas, not the branch names. A promotions log with no failures in it is a log nobody is writing to.

### What a hook enforces, and what it cannot

`promote-gate.sh` fires on `PreToolUse` and refuses any command that contains the declared text of a
`deploy` entry (L-0689: verbatim, with arguments after it, or wrapped; a fragment such as `git
rev-parse HEAD` is no deploy - a breaking change for a map whose real runs are SHORTER than the
declared text: declare the shortest text every real run contains. A "DEPLOY NOT RECORDED" for a sha
no deploy ran at, left by an older crew, is this bug) unless, for the sha at HEAD of **the tree the deploy
runs from** (the Bash call's `cwd`, moved by a leading `cd <dir> &&` and named
by any `git -C <dir>`; it must be a worktree of the same repository, and any
literal sha in the command must be its HEAD):

- every environment in `requires` has an **all-pass** row in `.work/PROMOTIONS.md`
- `rollback` is set: a runbook that exists and carries `last verified: YYYY-MM-DD` inside 90 days, or the literal `"none"` plus a `rollbackReason` - an absent key blocks the deploy
- `requireHuman` has an approval marker at `.crew/.approved-<env>-<sha>`
- that tree is clean - you cannot deploy a sha plus uncommitted changes
- **review evidence** (L-0703): an accepted review receipt covers the sha -
  a ticket's review ledger (`<git-common-dir>/crew/review/`) whose receipt
  stands on its latest round, whose reviewed head has **the same tree** as
  the commit being deployed, and which `review_ledger.check_receipt`, run in
  the deploying tree, confirms. `requireHuman` does not waive it: a human's
  yes is a deploy go/no-go, not a code review. The only opt-out is
  `"requireReview": false` plus a non-empty `reviewReason` string on the
  environment; any other `requireReview` value blocks. Breaking change: a map
  that deploys unreviewed builds (a development environment fed from feature
  branches, say) must opt out explicitly.

What the review evidence proves is narrow, on purpose. It proves the
deployed commit's tracked tree is byte-identical to a tree a reviewer was
shown under a receipt crew considers standing - not (a) that paths the review
bundle left out were reviewed (paths identical to merged main, and the
excluded `.work/`, `graphify-out/`, `.crew/metrics.md`), (b) that ignored
build output a deploy script ships was reviewed, or (c) who wrote the ledger:
it is local JSON, protected only by the scope guard's refusal to write under
`<git-common-dir>/crew/`, not authenticated. A merge commit whose tree differs
from the reviewed head (main moved, or a version bump landed after the review)
is NOT covered: deploy the reviewed head, or review the merged tree.

The review search is bounded: one 16s deadline for the whole gate, under the
20s hook timeout, after which it is killed and the deploy blocks as
could-not-tell. Without python the gate no longer stands down: with `jq` it
blocks any command that and a string in the map contain one another, and
without `jq` it blocks every command while a map exists.

Both flavours (`.sh` and `.ps1`) choose the environment by one rule, on the
working map and, when that is dirty, the committed map alike (L-1503):

- the command loses every CR and its trailing newlines; a command that is then
  empty or only whitespace deploys nothing and passes
- a declared command matches when the command contains it - a plain
  substring test, ignoring case (on Windows `./Deploy.ps1` and `./deploy.ps1`
  are one file). `*`, `?` and `[...]` are literal text, never wildcards. A
  fragment of a declared command (`git push` of `git push prod main`) is no
  deploy (L-0689)
- every key the gates read - `environments`, `deploy`, `requires`,
  `rollback`, `rollbackReason`, `requireHuman` - is read ignoring case
  (`"RequireHuman": true` requires a human); a map with a key repeated in one
  object - exactly, or differing only by case (`deploy` and `Deploy`) - is
  refused and the command blocks
- a `deploy` that is not a command or a list of commands - `null` included -
  or a `requireHuman` that is a list or an object refuses the map and the
  command blocks; `"deploy": []` and `[""]` declare nothing
- an environment name that is empty, holds a control character (a newline, a
  tab) or holds a comma refuses the map; `-`, `_` and `.` are fine
- the map must be strict JSON in both: a comment or a single-quoted or
  unquoted key refuses it. One difference is left: PowerShell reads a
  trailing comma that the bash flavour refuses
- if more than one environment matches, the strictest union of their
  requirements applies: every matched environment's `requires`, `rollback`
  and `requireHuman` must hold. They are named together - `staging,prod` - in
  the block message and in `.crew/.deploy-in-flight`, so the promotions row
  that clears the Stop check names `staging,prod` too. So `./deploy.sh
  --prod`, which contains both `./deploy.sh` and `./deploy.sh --prod`, needs
  every requirement of both environments.
  That combined row is not a row for `staging` or for `prod`: after such a
  deploy, an environment that `requires` one of them still needs an
  unambiguous deploy record for it first - deploy with a command that matches
  only that environment, and record that (L-1505 is to write one row per
  matched environment instead)
- if the comparison itself fails, the command blocks rather than skipping
  that environment

**A workflow dispatch of a declared deploy is that deploy, in either spelling
(T-0062, the Bash tool).** When a declared `deploy` is a GitHub workflow
dispatch, `promote-gate.sh` reads the command, whatever containment matched,
with T-0009's dispatch reader (`crew_dispatch.dispatch_read`, through
`_promote_dispatch.py`; no second parser). `gh workflow run deploy.yml -f
ref=<sha> -f environment=production` (inputs reordered) and `gh api -X POST
repos/<o>/<r>/actions/workflows/deploy.yml/dispatches -f ref=main -f
'inputs[environment]=production'` both reach the environment whose declared
dispatch names `deploy.yml` and whose declared literal inputs all appear with
the same value; extra inputs are allowed, and a declared input whose value is a
`$(...)` or backtick substitution is not compared. Workflow names compare as
file names, a leading `.github/workflows/` dropped. Blocked:

- a declared workflow whose inputs fit no environment, or more than one
- **could not tell**, naming why: a dispatch-shaped line the reader refuses (a
  variable, a substitution, double quotes, a pipe, `--json`, `--input`,
  `-F k=@file`, a nested shell, an alias of `gh`), a command input it cannot
  name, an input given two values, a workflow named by id or display name,
  and a declared dispatch the reader itself cannot read. The spelling that
  passes is plain literal words, as the declared deploy is written

A dispatch of a workflow file no declared deploy names, `--help`, a GET and
every command in a repo that declares no dispatch deploy pass untouched. The
committed map's dispatches are matched too while the map is dirty, and an
open incident turns each block into a skip row. A `requires` environment is judged by its NEWEST row for the sha in `.work/PROMOTIONS.md` (L-0665): a later failure revokes an earlier pass, a later pass clears an earlier failure. For an environment with a `github` entry
whose `shaInput` is set, both flavours also require that input once, as the
full lowercase HEAD of the judged tree (L-0648). The PowerShell tool is read the
same way (L-0664), python found by the shared `Resolve-CrewPython` probe; with
no python, a command naming `gh` with `workflow` or `dispatches` blocks when a
declared deploy names them too. Not seen: `curl`, a script file, `gh run
rerun`, a `gh alias` set by an earlier command, and symbolic refs (`--ref
<branch>`, `inputs[ref]=<branch>`), as T-0505 decided; a literal sha anywhere
in the command must still be the tree's HEAD.

So a clean worktree deploys while the main checkout is dirty, and a clean main
checkout cannot wave a dirty or wrong-sha worktree through. `.crew/verify.json`,
`.work/PROMOTIONS.md`, the approval markers and `.crew/.deploy-in-flight` are
read from the session's project directory on purpose - they are gitignored
per-checkout state that a fresh worktree lacks and a throwaway one could forge -
so an uncommitted change to the project's `.crew/verify.json` (edit, deletion,
untracked, or hidden by skip-worktree - compared with HEAD's copy) blocks too.
The directory the command runs in must also be clean. A command that changes
directory after it starts (`env -C` and `make -C` included), names two trees,
uses `--git-dir`, or puts `git` in a form the gate cannot read with certainty is
refused rather than guessed at (T-0505). When the gate blocks,
`/crew:promote` fixes the precondition it names; it never hands the owner the
command to run past the hook.

**Limitation: this enforcement lives in the session, not the repo.** All three
gates - `guard.sh`, `verify-gate.sh`, `promote-gate.sh` - are hooks that run
only inside a Claude Code session with the crew plugin active. A fresh
session that does not have the plugin installed - a teammate who skipped
setup, a different machine, any tool other than Claude Code - gets none of
these guarantees, even though `.crew/verify.json`, `.crew/STATUS.md`, and
this README are all still sitting in the repo looking fully configured.
Nothing here is durable across that boundary except the plugin being active.

`verify-gate.sh` then refuses to end a turn that deployed and recorded nothing.

What no hook can enforce: that `smoke`, `regression` and `verify` actually ran,
against the right environment, after the soak. A hook fires before a command and
after a turn; it cannot watch the middle. The row you append is a claim - which
is exactly why it must record failures too.

Two setup consequences. First, `.gitignore` must ignore `.crew/*` and `.work/`,
which is what keeps the approval marker out of the tree — an approval marker git
tracks dirties the tree, and the gate then blocks on the file the operator was
told to create. `.crew/.approved-*` is listed explicitly as documentation of
which file that is; measured with `git check-ignore`, deleting that line changes
nothing, because `.crew/*` already covers it and none of the negations re-admits
it. Its position relative to the un-ignore list is likewise not load-bearing.
(This paragraph previously said both were, and that the *gate* writes the marker.
The operator creates it; the file the gate writes is `.crew/.deploy-in-flight`.)
Write `.crew/*`, never `.crew/` — a trailing slash makes git refuse
to descend into the directory, and nothing can be re-included from a directory
git never entered, so `!.crew/codemap/`, `!.crew/endpoints.json` and
`!.crew/verify.json` all silently do nothing. Second, the rollback runbook needs
a literal `last verified: YYYY-MM-DD` line, because that is what the hook greps
for.

### Rules with no override

- **The sha must match across environments.** A rebuild between qa and production is a different artifact, and qa proved nothing about it.
- **`verify` runs after the soak.** Errors surface on the first real traffic, which arrives after the deploy finishes, not during it.
- **Every gated environment declares a rollback plan, or says why it does not need one.** A verified runbook inside 90 days, or `rollback: "none"` plus a `rollbackReason` - an absent key blocks the deploy. Production without a verified runbook is the one case with no override.
- **A failed gate is a stop.** Roll back or fix forward, then run the whole sequence again from gate 1. Never resume mid-sequence.

### Starting from nothing

Most legacy repos have a deploy script and no post-deploy proof at all. Build it in payoff order, not all at once: `smoke` for the environment you deploy to most; then `verify`, where even `grep -c ERROR` over the last ten minutes beats nothing because it turns "looks fine" into a number; then `regression` last, being the most expensive to build and the least useful until the first two are trustworthy.
