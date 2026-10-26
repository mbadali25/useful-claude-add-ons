# /crew:promote - rationale

Repo-only background for `plugin/crew/commands/promote.md`, moved out of the command so the installed plugin
carries only the rules the model follows. The sections are the command's original text, verbatim.
The command keeps a short form of each rule; where the two differ in length, this file is the longer statement.

## The change request

This step runs inside gate 1, before anything deploys. Two providers, one
shape: Bitbucket and GitHub. It runs only when it is asked for on the command
line: `--merge-gate <github|bitbucket>`, with an optional
`--merge-gate-branch NAME`. No config key switches it on. The settings that once
did (`bitbucket.mergeGate.*`, `github.mergeGate.*`) were removed by L-0725, and a
block left in a config file is inert. The branch is fixed at `null` unless
`--merge-gate-branch` is given, and the Bitbucket preset is fixed at
`"standard"` (`crew_state.MERGE_GATE_ENABLED`, `MERGE_GATE_BRANCH`,
`BITBUCKET_MERGE_GATE_PRESET`). See `docs/crew/config-rationale.md`, "Removed
keys and migration".

**Route every invocation through `/crew:gate <disable|enable|status>
<github|bitbucket>`.** Promote does not compose `merge_gate.sh` commands of its
own. That command owns the workflow - it reads `guards.overrides.mergeGate`
before anything else, it stops when the provider's skill is missing, and it
knows the two scripts' argument surfaces are not interchangeable. Promote
deciding for itself would be a second implementation of a sequence whose whole
risk is the order of its steps.

**`guards.overrides.mergeGate` decides whether any of this may happen at all,
and it ships as `block`.** The `--merge-gate` flag says this run wants the gate
handled; the guard says whether crew may touch it. When it is `block`, report the
gate's state as **not checked** and say which guard refused - never as checked
and fine. That collapse is the bug this repo keeps rediscovering.

**No `--merge-gate` flag means do nothing at all.** No `merge_gate.sh`
subcommand, no `/crew:gate` invocation, no Bitbucket or GitHub API call, not even
`export`. It does **not** mean "apply the disabled preset":
`disable` deletes branch restrictions, and that is the opposite action against
a live repo from the one an absent flag expresses. A repo that
never asked crew for a gate keeps whatever restrictions its owner made by hand.
There is nothing to report in this case - say nothing and move to gate 2.

Everything below is what `--merge-gate` means.

**The script belongs to another marketplace entry. Reference it, never
reimplement it.** The gate is `skills/bitbucket/scripts/merge_gate.sh` from the
`bitbucket` skill, or `skills/github/scripts/merge_gate.sh` from the `github`
skill, and crew bundles neither. If the script for the provider this repo uses
is not on this machine, this is a **stop** - the same shape as an absent
`rollback` key, not a warning to walk past. Say "`--merge-gate <provider>` was
given and the `<provider>` skill is not installed, so the merge gate could
not be checked", name the two fixes (install the skill, or drop the flag), and
stop. Do not hand-roll a `branch-restrictions` or a
`branches/*/protection` API call, and do not let "could not check" become
"checked, and fine".

**`branch` binds to one flag, and `null` means ask:**

| Branch (fixed at `null`) | What promote passes |
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
the Bitbucket preset constant changes nothing today whatever it holds. Whenever
you show an `enable` command, say that in the same breath - otherwise the
`"standard"` reads as a choice that was honoured. The preset is a fixed constant
rather than a key bound to that literal.

### Nothing changes without a yes at that moment

**Asking for the gate is intent. It is not consent.** `--merge-gate` authorises
promote to look; it authorises no write. Before any invocation that changes the
live repo, print the exact command - script path, subcommand, workspace,
repository and every flag resolved from the command line - and wait. Do not proceed on silence. This is
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


## What is enforced, and what is not

Be precise about this, because the difference decides how much the sequence above
can be trusted.

**Enforced by `promote-gate.sh` (`PreToolUse`).** It fires on any command that contains the declared `deploy`
text (a fragment of it is no deploy) - and, on either tool, on a workflow dispatch of a declared deploy workflow in either spelling
(`gh workflow run` or `gh api .../dispatches`; inputs must fit one environment; a dispatch it cannot read is
could-not-tell and blocks; a `github` entry's `shaInput` must be given once, as that full sha) - and refuses it unless, for the sha at
HEAD **of the tree the deploy runs from**: every `requires` environment has an all-pass row in `.work/PROMOTIONS.md`;
the `rollback` runbook is verified inside 90 days; `requireHuman` has `.crew/.approved-<env>-<sha>`;
an accepted review receipt covers that tree (or `requireReview: false` with a
`reviewReason`); and that tree is clean. A row counts only with the full sha.
The review evidence proves the tracked tree deployed is one a reviewer was
shown under a standing receipt - not that paths the bundle left out or ignored
build output were reviewed, nor who wrote the ledger (local, unauthenticated).
With no python the gate blocks instead of standing down. These cannot be skipped by deciding to skip them.

The tree is the Bash call's `cwd`, moved by a leading `cd <dir> &&` chain and
named by git's global `-C <dir>` inside `$(...)` (a `git -C` whose output feeds
nothing may only name the tree the deploy runs in). It must be a worktree of the same
repository and every literal sha in the command must be its HEAD; the directory
the command itself runs in must be clean too, since that is where the deploy
process runs. A command that changes directory after it starts (a later `cd`,
`bash -c 'cd ...'`, `env -C`, `make -C`), names two trees, uses `--git-dir`,
or puts `git` in a form the gate cannot read with certainty (an unlisted global
option, quoted text) is refused rather than guessed at. Skip-worktree and
assume-unchanged entries, and a `git status` that fails, are refused too. `.crew/verify.json`, `.work/PROMOTIONS.md`, the approval
markers and `.crew/.deploy-in-flight` are read from the session's project
directory on purpose: they are gitignored per-checkout state, so a fresh
worktree has none of it and a throwaway one could hold a forged copy. For the
same reason an uncommitted change to the project's `.crew/verify.json` - an edit,
a deletion, an untracked map, compared with HEAD's copy rather than with
`git status` - blocks any command the working or the committed map declares.
What it cannot see: a deploy script that changes directory itself, and what a
workflow does with a branch-name ref (`ref=development`).

**Enforced by `verify-gate.sh` (`Stop`).** A deploy that wrote no
`.work/PROMOTIONS.md` row does not end the turn. A deploy nobody wrote down is a
deploy nobody can audit.

**NOT enforced - this is on you and on me.** That `smoke`, `regression` and
`verify` actually ran, that they ran against the environment just deployed to,
and that the soak was really waited out. The same goes for the two gate-1/gate-2
checks added above: the hook cannot reconcile the source tree against the live
artifact, and it cannot tell a green run from a green run that skipped its
deploy job. **The Bitbucket merge gate section is prose too** - no hook fires on
`merge_gate.sh` or on `/crew:gate`, nothing checks that a `--merge-gate` request was
honoured, and
`promote-gate.sh` does not read the merge-gate request at
all. `guards.overrides.mergeGate` is not prose - it is read by `/crew:gate` from
`crew_config.py --guard mergeGate`, and at `block` that command refuses. But
nothing forces promote to ROUTE through `/crew:gate`; that part is prose too.
**The change-request section is prose in exactly the same way, and by the same
measurement**: no hook fires on `/crew:change`, `promote-gate.sh` does not read
`change.requireForProduction`, and nothing checks that an approved change was
found or that the clock was inside the window. The config key is real and the
ratchet across the two layers is real - `change.requireForProduction` resolves
through `crew_config.resolve_ratcheted`, so a repo cannot turn the requirement
off - but what the requirement makes promote DO is this file, and this file
only holds if you run it.
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

## Reporting a deploy: three facts (L-0872)

A promotion is reported with the merged sha, the deployed sha read back from the target, and the
health-check result of gate 3; a missing fact makes it `unverified`. A green pipeline proves a
merge or a dispatch, not what the target runs, and a running target is not a healthy one, so each
link needs its own evidence. The wording follows the owner's rule (merged is not deployed, deployed
is not verified); gstack's land-and-deploy skill is prior art for the vocabulary (see `NOTICE.md`).
