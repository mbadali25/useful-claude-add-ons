---
description: Promote a build to the next environment, with the full post-deploy proof
argument-hint: <development | qa | production> [--dry-run | --status]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Promote to: $ARGUMENTS

Follow the `crew-verification` skill, section 4. Read the `environments` block in
`.crew/verify.json`. If there is no such block, stop and say so - build it first
with `/crew:verify`, do not improvise a deploy sequence.

## `--status`

Print the last five rows of `.work/PROMOTIONS.md` and the current sha of each
environment. Then stop. Say plainly whether the environments are running the
same artifact.

## `--dry-run`

Print the exact sequence you would run, in order, with the commands resolved
from config. Run nothing. This is the safe way to check a new `environments`
block before trusting it.

## The sequence

Run these in order. **Stop at the first failure** and report which gate failed
with the error text verbatim.

**Gate 1 - pre-deploy.**
- Every environment in `requires` has a `pass` row in `.work/PROMOTIONS.md` for
  the sha you are about to deploy. Not "a pass row" - a pass row *for this sha*.
- The working tree is clean and the sha is pushed.
- `rollback` must be set: either a runbook that exists with a `last verified`
  date inside 90 days, or the literal `"none"` plus a `rollbackReason`. An
  absent key is a stop, not a pass - the fix is to add one of the two, in
  `.crew/verify.json`. Production without a verified runbook has no override.
- If `requireHuman` is set, show me the sha, the diff summary, and what the last
  production promotion was, then wait for me to say go. Do not proceed on
  silence.
- **The merge gate**, if this repo has one, on Bitbucket or on GitHub. See
  `## The merge gate` below - it runs here, before gate 2. When both
  `bitbucket.mergeGate.enabled` and `github.mergeGate.enabled` are `false`,
  which is the shipped default for both, that section does not exist and there
  is nothing to do or to report.
- **The source tree is reconciled against what the target is actually
  running.** A branch that was never reconciled will roll the environment
  backwards: an on-box hotfix, a config value changed during an incident, a
  file edited in place - all of it silently reverted by a deploy that reports
  success. List the deployed artifact, hash it against the same paths in the
  source tree, and classify **every** difference as exactly one of:
  *roll-forward* (the source is newer and the change is intended), *on-box
  edit* (the target has something the source does not, which this deploy would
  clobber or delete), or *unexplained*. Any on-box edit or unexplained
  difference is a stop - carry it into the branch, or say explicitly that it is
  being discarded and get that agreed. Do not call a difference roll-forward
  because the source is the branch you were told to deploy.

**Gate 2 - deploy.** Run the `deploy` commands. A non-zero exit is a stop.

Then assert on what actually happened, not on the wrapper:

- **Check the job, not the run.** A pipeline whose deploy step is conditional
  (path filters, `if:` guards, a changed-files check) reports a green *run*
  while having deployed nothing. Read the status of the deploy job itself and
  say whether it executed or was skipped.
- **Check the artifact on the box, not the log.** Hash or line-count the
  deployed file and compare it against the source. A run that resolved the
  wrong ref, or fetched tooling from a different ref than the code, is green
  and wrong; the only thing that distinguishes it is reading what landed.

Green means the workflow finished. It does not mean anything shipped.

**Gate 3 - smoke.** Run the `smoke` commands against the environment just
deployed to. A smoke suite that passes against the wrong environment is the most
convincing wrong answer available, so echo the target URL or host first and
confirm it matches the environment name.

**Gate 4 - regression.** Run the `regression` commands. This is the slow one and
it is the one that catches what smoke cannot. Do not skip it because smoke was
green - that is the whole reason it is a separate gate.

**Gate 5 - verify.** Wait `soakMinutes`, then run the `verify` commands. Report
the actual numbers - error count, alarm state, queue depth - not "looks clean".
A deploy that moved bytes successfully and broke the application looks identical
to a good one until this gate runs.

## The merge gate

This step runs inside gate 1, before anything deploys. Two providers, one
shape: Bitbucket reads `bitbucket.mergeGate.enabled`, `.branch` and `.preset`,
GitHub reads `github.mergeGate.enabled` and `.branch` (there is no `preset` -
see below). Both are documented in `plugin/crew/CONFIG.md` §8. Read them
through `/crew:config` rather than out of `.crew/config.json`, because a
machine-global file can set any of them and the repo file would not show it.

**Route every invocation through `/crew:gate <disable|enable|status>
<github|bitbucket>`.** Promote does not compose `merge_gate.sh` commands of its
own. That command owns the workflow - it reads `guards.mergeGate` before
anything else, it stops when the provider's skill is missing, and it knows the
two scripts' argument surfaces are not interchangeable. Promote deciding for
itself would be a second implementation of a sequence whose whole risk is the
order of its steps.

**`guards.mergeGate` decides whether any of this may happen at all, and it
ships as `block`.** An `enabled: true` in `bitbucket.mergeGate` or
`github.mergeGate` says this repo HAS a gate; `guards.mergeGate` says whether
crew may touch it. When it is `block`, report the gate's state as
**not checked** and say which key refused - never as checked and fine. That
collapse is the bug this repo keeps rediscovering.

**`enabled: false` - the shipped default - means do nothing at all.** No
`merge_gate.sh` subcommand, no `/crew:gate` invocation, no Bitbucket or GitHub
API call, not even `export`. It does **not** mean "apply the disabled preset":
`disable` deletes branch restrictions, and that is the opposite action against
a live repo from the one a `false` in a config file expresses. A repo that
never asked crew for a gate keeps whatever restrictions its owner made by hand.
There is nothing to report in this case - say nothing and move to gate 2.

Everything below is what `enabled: true` means.

**The script belongs to another marketplace entry. Reference it, never
reimplement it.** The gate is `skills/bitbucket/scripts/merge_gate.sh` from the
`bitbucket` skill, or `skills/github/scripts/merge_gate.sh` from the `github`
skill, and crew bundles neither. If the script for the provider this repo uses
is not on this machine, this is a **stop** - the same shape as an absent
`rollback` key, not a warning to walk past. Say "`<provider>.mergeGate.enabled`
is true and the `<provider>` skill is not installed, so the merge gate could
not be checked", name the two fixes (install the skill, or set
`enabled: false`), and stop. Do not hand-roll a `branch-restrictions` or a
`branches/*/protection` API call, and do not let "could not check" become
"checked, and fine".

**`branch` binds to one flag, and `null` means ask:**

| `bitbucket.mergeGate.branch` | What promote passes |
|---|---|
| `null` (the default) | no `--branch` at all - the script resolves `.mainbranch.name` from the Bitbucket API (`skills/bitbucket/scripts/merge_gate.sh:198-202`) |
| a string, e.g. `"release/*"` | `--branch release/*`, verbatim |

If the API has no `.mainbranch.name` the script dies asking for `--branch`
(`skills/bitbucket/scripts/merge_gate.sh:202`). Relay that sentence and stop.
Never substitute `main` yourself: on a repo still on `master`, or a Gitflow
`develop`, a gate on `main` looks configured and watches a branch nobody merges
into.

One exception, which the script prints itself: `--branch` **is ignored** with
`--from-export` (`skills/bitbucket/scripts/merge_gate.sh:464`), because each
exported object carries its own scope. Do not report a restore as having been
scoped to the configured branch.

GitHub differs in two places `/crew:gate` documents in full and promote must
not paper over: its `export` is **branch-scoped** (classic protection is
per-branch in the URL), and its `enable` **requires** `--from-export` and
rejects `--branch` as a usage error. So a GitHub restore has no bare form at
all, and there is no GitHub `preset` for a config key to select.

**`preset` is wired to nothing, and promote must not pretend otherwise.**
`merge_gate.sh` has no `--preset` flag. The preset a bare `enable` applies is
one hardcoded JSON literal, `PRESET` at
`skills/bitbucket/scripts/merge_gate.sh:65`, and no flag selects it. So
`bitbucket.mergeGate.preset` changes nothing today whatever it holds. Whenever
you show an `enable` command, say that in the same breath - otherwise the
`"standard"` sitting in the config reads as a choice that was honoured.
`CONFIG.md` §8 records why the key is left unwired rather than bound to that
literal.

### Nothing changes without a yes at that moment

**Config is intent. It is not consent.** `enabled: true` authorises promote to
look; it authorises no write. Before any invocation that changes the live repo,
print the exact command - script path, subcommand, workspace, repository and
every flag resolved from config - and wait. Do not proceed on silence. This is
the standing rule and it does not move for a promotion that is otherwise green.

The two write subcommands do not preview the same way, and the difference is
the point:

- **`disable`** takes `--dry-run`
  (`skills/bitbucket/scripts/merge_gate.sh:317`). Run it, show the plan it
  prints, then wait for the yes. `disable` removes protections; it is the
  destructive direction.
- **`enable`** has **no `--dry-run`**. `cmd_enable` parses `--branch` and
  `--from-export` and rejects everything else
  (`skills/bitbucket/scripts/merge_gate.sh:430-439`). The echoed command is the
  entire preview, so say so when you ask - nobody should read that yes as
  confirming a dry run that never happened.

Under promote's own `--dry-run`, this step prints the command it would run and
runs **nothing** - `export` included, which is a real API call and needs
`repository:admin` exactly as a write does.

**Never `disable` and then a bare `enable`.** `disable` removes more kinds than
`PRESET` creates - `restrict_merges` and `require_no_changes_requested` among
them (`skills/bitbucket/SKILL.md:123-126`) - so the pair silently drops whatever
those were. The only restore is `enable --from-export <the file disable wrote>`.
Keep that export and name its path in the promotion row.

### Relay the script's outcomes; do not re-summarise them

Three of its exits are not "failed", and flattening them loses the part the
reader needs (`skills/bitbucket/scripts/merge_gate.sh:30-35`):

- **exit 3 - scope undetermined, nothing was deleted.** Restrictions can be
  scoped by a `branch_type` from the branching model instead of a glob, and the
  script refuses to guess which types cover your branch. Quote it and stop. Do
  not pick a `--branch-type` on my behalf.
- **exit 4 - one or more writes failed.** The live repo is now **partially**
  changed. Say which kinds landed and which did not; "failed" on its own reads
  as "nothing happened", which is false.
- **`not-available-on-this-plan`** on the three Premium-only kinds is its own
  outcome - neither applied nor failed. Report it as itself.

## After

Append one row to `.work/PROMOTIONS.md` with the real result of every gate,
including failures. Then:

- **All gates green:** say which environment now runs which sha, and name the
  next promotion explicitly from this environment's `promotesTo` - e.g.
  `qa is now on a1b2c3d; next is /crew:promote production`. If `promotesTo` is
  absent, say this is the last environment in the chain.
- **Any gate failed:** say which gate, quote the error, and state the two
  options - roll back using the runbook, or fix forward. Do not pick for me on
  production. Do not resume mid-sequence afterwards; the whole sequence runs
  again from gate 1.

Then send `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh gate "<env> <sha> - <pass|FAILED at gate N>"`.

## What is enforced, and what is not

Be precise about this, because the difference decides how much the sequence above
can be trusted.

**Enforced by `promote-gate.sh` (`PreToolUse`).** It fires on any command matching
a declared `deploy` entry and refuses it unless, for the sha at HEAD: every
`requires` environment has an all-pass row in `.work/PROMOTIONS.md`; the
`rollback` runbook exists with `last verified` inside 90 days; `requireHuman` has
an approval marker at `.crew/.approved-<env>-<sha>`; and the tree is clean. These
cannot be skipped by deciding to skip them.

**Enforced by `verify-gate.sh` (`Stop`).** A deploy that wrote no
`.work/PROMOTIONS.md` row does not end the turn. A deploy nobody wrote down is a
deploy nobody can audit.

**NOT enforced - this is on you and on me.** That `smoke`, `regression` and
`verify` actually ran, that they ran against the environment just deployed to,
and that the soak was really waited out. The same goes for the two gate-1/gate-2
checks added above: the hook cannot reconcile the source tree against the live
artifact, and it cannot tell a green run from a green run that skipped its
deploy job. **The Bitbucket merge gate section is prose too** - no hook fires on
`merge_gate.sh` or on `/crew:gate`, nothing checks that an `enabled: true` was
honoured, and
`promote-gate.sh` does not read `bitbucket.mergeGate` or `github.mergeGate` at
all. `guards.mergeGate` is not prose - it is read by `/crew:gate` from
`crew_config.py --guard mergeGate`, and at `block` that command refuses. But
nothing forces promote to ROUTE through `/crew:gate`; that part is prose too.
Those are prose,
and prose only holds if you run it. A hook fires before a command and after
a turn; it cannot watch the middle. The row you append is a claim, and the only
thing that makes it worth anything is that it is written honestly - **including
the failures**. A promotions log with no failures in it is a log nobody is
writing to.

So: `.work/PROMOTIONS.md` is the evidence, not this session's memory of what
happened. And anything mechanisable belongs in a `.crew/verify.json` rule, where
the hook enforces it, rather than in this sequence where it has to be remembered.

## What not to do

- Do not report a promotion complete on the strength of gate 2. A successful
  deploy proves bytes moved and nothing else.
- Do not accept a green pipeline as proof of a deploy. Green, shipped and
  healthy are three separate claims and each needs its own evidence.
- Do not rebuild between environments. The artifact qa proved is the artifact
  production gets, or qa proved nothing.
- Do not deploy to production because qa passed a week ago. Re-check the sha.
