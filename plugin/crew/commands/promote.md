---
description: Promote a build to the next environment, with the full post-deploy proof
argument-hint: <development | qa | production> [--dry-run | --status] [--merge-gate <github | bitbucket> [--merge-gate-branch NAME]]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Promote to: $ARGUMENTS

Follow the `crew-verification` skill, section 4. Read the `environments` block in `.crew/verify.json`. If there is none, stop and say so - build it first with `/crew:verify`, do not improvise a deploy sequence. Why each rule below exists, and what is and is not enforced: `docs/crew/promote.md` (repo only).

## `--status`

Print the last five rows of `.work/PROMOTIONS.md` and the current sha of each environment. Then stop. Say plainly whether the environments are running the same artifact.

## `--dry-run`

Print the exact sequence you would run, in order, with the commands resolved from config (a `github` environment: `crew_ghdeploy.py check`'s output). Run nothing.

## The sequence

Run these in order. **Stop at the first failure** and report which gate failed with the error text verbatim.

**Gate 1 - pre-deploy.**
- Every environment in `requires` has, as its NEWEST `.work/PROMOTIONS.md` row for the sha you are about to deploy, an all-pass row. A later failure revokes it. The row must carry the full 40-character sha: a short row never counts.
- An accepted review covers this exact tree: a ticket's receipt standing on its latest round, whose reviewed head has the same tree as the sha you are deploying. A merge commit that differs from the reviewed head does not count. Only `requireReview: false` plus a `reviewReason` on the environment waives it; `requireHuman` does not.
- The tree the deploy runs from is clean, is at the sha you are about to deploy, and that sha is pushed. That is the tree `promote-gate` judges: the Bash call's working directory, moved by a leading `cd <dir> &&` and named by any `git -C <dir>`. To deploy from a clean worktree while the main checkout is dirty, run the declared command there.
- `rollback` is set: a runbook that exists with a `last verified` date inside 90 days, or the literal `"none"` plus a `rollbackReason`. An absent key is a stop, not a pass. Production without a verified runbook has no override.
- If `requireHuman` is set, show me the sha, the diff summary, and the last production promotion, then wait for me to say go. Do not proceed on silence.
- **An approved change request**, if `change.requireForProduction` is true: see `## The change request`. **The shipped default is `false`, and at `false` this step does not exist** - ask for nothing, report nothing.
- **The merge gate**, if this repo has one: see `## The merge gate`. It runs ONLY when I ask for it on the command line with `--merge-gate <github|bitbucket>`; without that flag that section does not exist.
- **The source tree is reconciled against what the target is running.** List the deployed artifact, hash it against the same paths in the source tree, and classify **every** difference as exactly one of: *roll-forward* (the source is newer and the change is intended), *on-box edit* (the target has something the source does not, which this deploy would clobber), or *unexplained*. Any on-box edit or unexplained difference is a stop - carry it into the branch, or get explicit agreement that it is being discarded. A difference is not roll-forward merely because the source is the branch you were told to deploy.

**When the gate blocks.** `promote-gate` refusing a deploy is gate 1 failing, not an obstacle. Quote its `PROMOTION BLOCKED` line verbatim, name the precondition, fix that precondition, and run the same command again. **Never hand the owner a deploy so it skips the hook** (T-0505): if the gate is wrong, report it as a crew bug. Hand a deploy to the owner only where one is genuinely needed (`requireHuman`, or an MFA or browser approval a session cannot perform), as a question with your recommendation first - never a list of commands to paste.

**Gate 2 - deploy.** Run the `deploy` commands. A non-zero exit is a stop. A `github` environment runs the five steps in the skill's `github-deploy.md`. Then assert on what actually happened, not on the wrapper:
- **Check the job, not the run.** A conditional deploy step (path filters, `if:` guards) reports a green *run* while deploying nothing. Read the deploy job's own status and say whether it executed or was skipped.
- **Check the artifact on the box, not the log.** Hash or line-count the deployed file and compare it against the source. A run that resolved the wrong ref is green and wrong; only reading what landed tells them apart.

Green means the workflow finished. It does not mean anything shipped.

**Gate 3 - smoke.** Run the `smoke` commands against the environment just deployed to. Echo the target URL or host first and confirm it matches the environment name.

**Gate 4 - regression.** Run the `regression` commands. Do not skip it because smoke was green.

**Gate 5 - verify.** Wait `soakMinutes`, then run the `verify` commands. Report the actual numbers - error count, alarm state, queue depth - not "looks clean".

## The change request

Runs inside gate 1, only for `production`. Read `change.requireForProduction` through `/crew:config`, not out of `.crew/config.json`. **`false` is the shipped default and means this section does not exist:** no `sdp_*` or Jira call, no read of `.work/changes/`, nothing to report. Everything below is what `true` means.

**A change in an APPROVED state, for THIS sha.** Not "a change exists": a change whose record names the sha you are about to deploy and whose state the backend currently reports as approved. A change without this sha is a different change and this is a stop.

**Read the state from the backend, every time** - never from the local cache, and never from this session's memory. A cached `approved` is a claim about the past. Route through `/crew:change status <id>`, which reads the backend.

**"Could not read the state" is a STOP, not a pass.** Desk down, MCP tools not connected, id resolves to nothing: report it as **not checked**, name what could not be read, and stop.

**Outside the window is a stop.** Before gate 2, compare the current time against the change's `Scheduled Start Time` and `Scheduled End Time`; refuse outside, and say the window, the current time and which side you are on.

Under `--dry-run`, print which change would be checked and run **nothing**.

## The merge gate

Runs inside gate 1, before anything deploys, and ONLY when I ask for it on the command line: `--merge-gate <github|bitbucket>`, with an optional `--merge-gate-branch NAME`. No config key switches it on; a `bitbucket.mergeGate` or `github.mergeGate` block left in a config file is inert. The branch is fixed at `null` unless `--merge-gate-branch` is given, and the Bitbucket preset is fixed at `"standard"` (`crew_state.MERGE_GATE_ENABLED`, `MERGE_GATE_BRANCH`, `BITBUCKET_MERGE_GATE_PRESET`).

**Route every invocation through `/crew:gate <disable|enable|status> <github|bitbucket>`.** Promote does not compose `merge_gate.sh` commands of its own.

**`guards.mergeGate` ships as `block`.** At `block`, report the gate's state as **not checked** and say which key refused - never as checked and fine.

**No `--merge-gate` flag means do nothing at all.** No `merge_gate.sh` subcommand, no `/crew:gate` call, no Bitbucket or GitHub API call, not even `export`. It does **not** mean "apply the disabled preset": `disable` deletes branch restrictions. Say nothing and move to gate 2.

Everything below is what `--merge-gate` means.

**The script belongs to another marketplace entry. Reference it, never reimplement it.** It is `skills/bitbucket/scripts/merge_gate.sh` or `skills/github/scripts/merge_gate.sh`. If the script for this repo's provider is not on this machine, this is a **stop**: say "`--merge-gate <provider>` was given and the `<provider>` skill is not installed, so the merge gate could not be checked", name the two fixes (install the skill, or drop the flag), and stop. Do not hand-roll a `branch-restrictions` or `branches/*/protection` API call.

**`branch`:** without `--merge-gate-branch` pass no `--branch` - the script resolves `.mainbranch.name`; with it, pass `--branch <value>` verbatim. Never substitute `main` yourself. `--branch` is ignored with `--from-export`.

**`preset` is wired to nothing:** `merge_gate.sh` has no `--preset` flag; a bare `enable` applies the hardcoded `PRESET` literal, so the preset (`"standard"`) is not selectable - say so whenever you show an `enable` command. GitHub's `enable` requires `--from-export` and rejects `--branch`.

**Nothing changes without a yes at that moment.** Config is intent, not consent. Before any invocation that changes the live repo, print the exact command with every flag resolved from the command line and wait. Do not proceed on silence.
- **`disable`** (destructive: it removes protections) takes `--dry-run`: run it, show the plan, then wait for the yes.
- **`enable`** has no `--dry-run`: the echoed command is the entire preview, so say so when you ask.

Under `--dry-run`, print the command; it runs **nothing**, `export` included (a real API call needing `repository:admin`). **Never `disable` and then a bare `enable`**: `disable` removes more kinds than `PRESET` creates (`restrict_merges` among them), so restore only with `enable --from-export <the file disable wrote>`, and name that path in the promotion row.

Relay the script's outcomes unflattened: **exit 3** scope undetermined, nothing was deleted (quote it, stop, pick no `--branch-type`); **exit 4** writes failed, the repo is **partially** changed (say which kinds landed); `not-available-on-this-plan` is its own outcome.

## After

Append one row to `.work/PROMOTIONS.md` with the real result of every gate, failures included, and the full 40-character sha (`git rev-parse HEAD` of the tree deployed). Then:

- **All gates green:** say which environment now runs which sha, and name the next promotion from this environment's `promotesTo` - e.g. `qa is now on a1b2c3d; next is /crew:promote production`. If absent, say this is the last environment in the chain.
- **Any gate failed:** say which gate, quote the error, and state the two options - roll back using the runbook, or fix forward. Do not pick for me on production. Do not resume mid-sequence; the whole sequence runs again from gate 1.

Then, for every result (a pass silent, a failure loud), send `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh deploy "<env> <sha> - <pass|FAILED at gate N>" --outcome <pass|fail>`.

Do not report a promotion complete on gate 2, accept a green pipeline as a deploy, rebuild between environments, or promote to production on a week-old qa pass: `.work/PROMOTIONS.md` is the evidence, not this session's memory.
