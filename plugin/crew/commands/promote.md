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
deploy job. Those are prose, and prose only holds if you run it. A hook fires before a command and after
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
