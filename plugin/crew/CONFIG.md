# crew configuration reference

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand:
`python3 scripts/check-marketplace.py` fails when this file is stale. The
reasoning behind the keys is in `docs/crew/config-rationale.md`.

107 keys: 69 settable in the machine-global file, 38 repo-only.

## The two layers

crew reads `~/.claude/crew/config.json` (the machine-global file: your
defaults for every repo on this machine) and `.crew/config.json` (the repo file:
facts about one checkout). The repo value wins over the machine value, which wins
over crew's built-in default, with these exceptions, each named in the Layer
column:

- A repo-only key in the machine file takes effect nowhere (pruned on read,
  refused on write).
- A ratcheted key resolves to the NARROWER of the two layers, so a cloned repo
  can tighten what your machine allows and never loosen it.
- A machine-arms key (`resume.auto`, `context.autoClear.enabled`,
  `context.autoClear.wrapUp`) is turned on only in the machine file; a repo can
  only veto it with `false`.
- A personal key (`crew_guards.PERSONAL_KEYS`) resolves per key to the stricter
  of the layers that set it; a layer that says nothing imposes nothing.
- A human-only opt-out key (`humanOnly.*`) has its own rules, below.
- A `null` in the repo file over a machine value inherits the machine value.
- In a linked git worktree with no config of its own, the main checkout's repo
  config is the one read.

## The human-only opt-out (`humanOnly`)

`humanOnly.approve` and `humanOnly.promoteMarker` are the owner's opt-out of
two human-only rules: `/crew:approve`, and the production promote marker
`.crew/.approved-<env>-<sha>`. `null` and `true` mean human-only. A `false`
takes effect only when all of these hold (`crew_humanonly.resolve`):

- it is in the machine file, or in a repo `.crew/config.json` that git does
  not track (a tracked or committed repo file can never opt out; "could not
  tell" counts as tracked);
- neither layer says `true` (a `true` anywhere vetoes, the stricter wins);
- it was written by a double confirmation: `crew_confirm_config.py propose`
  records the change and prints an id with two lines the agent relays to you
  word for word (the change, and the exact command; crew 1.3.70), and the
  owner types
  `/crew:confirm-config <change_id>` twice, in two prompts, within 15 minutes.
  `crew_config.py --set` and `/crew:config` refuse a `false` (and a repo
  `null` or removal, which drops a veto); a `false` written by hand reads as
  human-only.

**What is live (crew 1.3.33).** The prompt hook (`approval_hook.py`) now
records `/crew:confirm-config <change_id>` from a prompt you typed, so a
double confirmation can complete, and `humanOnly.approve: false` takes effect
through ONE decision point, `crew_ticket.cli_approval_allowed`: with an opt-out
in force a `cli`-recorded approval receipt counts as if `scope.allowCliApproval`
were `true`, for the scope guard, the Stop audit and every autopilot reader at
once. It does NOT let the session run `crew_ticket.py approve` (the scope guard
still refuses that text); the session's route is `crew_autopilot.py approve`,
which still needs `autopilot.approval` `self` or `risk` and `autopilot.mode`
`plan` or `backlog`. Anything unclear - the module missing, the resolver
raising or answering anything but exactly `humanOnly: false` - reads as
human-only.

**Finding the change id (crew 1.3.69).** Type `/crew:confirm-config` with no
id (or with an id that is wrong, expired or already used) and the hook refuses
it, records nothing, and lists the proposals in this machine's store
(`~/.claude/crew/confirm-config/`): each pending one's id, key, current value
-> `false`, layer and file, age, time left and confirmations so far, then up
to five from the last day that can no longer be confirmed. With none pending
it says so, and why one may be missing: none was made, it expired, it was
already applied, cancelled or refused, or it was proposed under another home
directory (WSL rather than Windows has its own store). The store is per
machine and home directory, not per repository, so a proposal made in one repo
or worktree is listed from any other. The listing never confirms: even with
exactly one pending proposal a bare `/crew:confirm-config` records nothing,
because "the only pending one" is a choice whoever ran `propose` makes, and the
id you type is what binds the change. A store crew cannot read is reported as
"could not tell", never as none pending.

**Still human-only (crew 1.3.33).** No hook reads `humanOnly.promoteMarker`:
the promote marker is human-only by instruction alone, and no hook checks who
created it. `crew_confirm_config.py resolve` shows what each key would
resolve to.

**Who can write the receipts.** The double confirmation is recorded only by
the prompt hook, from your own prompt. The scope guard (when `scope.mode` is
not `off`) refuses every Write/Edit under `~/.claude/crew/confirm-config/` and
every shell command that names that store beside a writing word. That is a
textual tripwire, not a sandbox: a session that sets out to forge a receipt
(`python -c`, an encoded command, a variable holding the path) still can, and
`scope.mode: off` has no tripwire at all. Treat `humanOnly` opt-outs as
meaningful only with `scope.mode` `block`.

**`/crew:approve-mass <id>` (crew 1.3.36).** Your yes to ONE blocked mass
operation, typed by you and recorded by the same prompt hook in
`<git-common-dir>/crew/mass-approvals/<id>.json`, good for 15 minutes. The
directory is under `<git-common-dir>/crew/`, which the scope guard refuses to
every Write/Edit and every shell command naming it, so the session cannot
write the file. The cloud guard (`cloud_guard.py`) prints the `<id>` with its
stop and reads the file; see "Mass operations".

## Mass operations (`guards.mass`, crew 1.3.36)

The rule for an autopilot that runs without a human: full automation, except a
mass delete, a mass create or a mass change, which wait for your yes. The stop
is armed by `guards.mass.enabled: true` (either layer) or by a double-confirmed
`humanOnly` opt-out, and by nothing else; it is off by default. It rides on
the cloud guard's hook, judges every shell command, and works even where
`guards.cloudGuard` is `off`.

| Limit | Default | Counts |
|---|---|---|
| `deleteCount` | 10 | files a command removes |
| `createCount` | 20 | files it adds |
| `changeCount` | 30 | files it rewrites |

A count AT the limit stops. The defaults were measured on this repo's own
history (104 days, 623 merged PRs: a PR adds a median 0 and p95 16 files,
changes a median 5 and p95 30, deletes none in all but 15).
`guards.mass.overrides.<files|git|terraform>.<limit>` replaces one limit for
one kind of command; with nothing set `terraform` is delete 3, create 10,
change 10 (inferred - the history held no terraform). The machine file sets
the limits and `guards.mass.exempt`; the repo file can lower a limit and turn
the stop on (`enabled` is on if either layer says so), so a cloned repo can
tighten the stop and never loosen yours. `guards.mass.exempt` (machine file
only) lists repo-relative globs of generated files that never count; node_modules,
`__pycache__`, `.venv`, caches, `build`, `dist`, `.work` and worktrees
(including `~/.claude/crew/worktrees/<repo>/<name>`) are always exempt.

What it sees: `rm`, `Remove-Item`, `git clean -f`, `git rm`, `find -delete`,
`rsync --delete` (delete); `cp`, `mv`, `rsync`, `Copy-Item`, `touch` (create
and change); `sed -i` and `git reset --hard` / `checkout -- <paths>` /
`restore` (change); `git commit`, `git push` and `gh pr create`, which count
the added, deleted and changed files of the commit or of the whole branch
against its base - so Write and Edit work is counted where it is about to be
shared; `terraform apply <plan>` (the plan's own changes), `destroy` and
`apply -auto-approve`; and an unfiltered SQL `DELETE` or `UPDATE`.

A count that cannot be taken - a variable in a path, a path after a `cd`,
`find -delete`, `xargs rm`, a failed `git`, an unfiltered SQL statement (no
command text says how many rows it hits) - is "could not tell", and could not
tell stops. It does NOT see a script (`bash cleanup.sh`, `python -c`,
`make clean`), an MCP server, the Write and Edit tools before they are
committed, `tar -x` or `unzip`, `git merge` or `pull`, or many small commands
each under a limit: a tripwire in front of native permissions, not a sandbox.

A stopped command prints an id. Attended, the stop is an `ask`; unattended
it is a `deny`. Type `/crew:approve-mass <id>` in the session, then re-run the
exact command. One id covers every limit that command trips.

## Git commands (`guards.git.allow`, crew 1.3.75)

The owner's switch that stops crew's command guards from blocking or asking on
git commands, destructive ones included. Off by default (`null`, or `"off"`).

| Value | What passes |
|---|---|
| `null` / `"off"` | nothing changes: every guard judges git as before |
| `"all"` | every git command |
| `["commit", "push", ...]` | a git command whose subcommand is listed; every other git command keeps today's checks |

A listed subcommand passes with every option it takes: listing `push` also lets
`git push --force` and `git push origin +main` through, because the force-push
rule is a finding on the `push` subcommand. To keep force pushes stopped, leave
`push` out of the list.

What it loosens, and nothing else: the cloud guard's `guards.forcePush` rule
(`git push --force`, `+ref`; not `xargs git`, whose appended arguments crew
cannot see); the mass stop's git counts (`git commit`, `git push`,
`git clean -f`, `git rm`, `git reset --hard`, `git checkout -f` / `-- <paths>`,
`git restore`); and the promote gate for a command line made ONLY of covered
git commands, so a commit message or heredoc that merely mentions a declared
deploy no longer trips it. Everything else on the same line is judged as
before (`git commit && rm -rf big/` still meets the mass stop for the `rm`). A
declared deploy that is itself a git command (`git push prod main`) stays
gated: that is a deploy, not a git block. `gh` is not git: `gh pr merge
--admin` (`guards.adminMerge`), `gh pr create`'s mass count, workflow
dispatches and `gh api` calls are untouched.

Who can turn it on: the machine file only, and only through the double
confirmation. `crew_confirm_config.py propose --layer machine --key
guards.git.allow --value '"all"'` (or `'["commit","push"]'`) records the change
and prints an id; you type `/crew:confirm-config <change_id>` twice, in two
prompts, within 15 minutes. A value counts only while the newest settled
receipt for that file is a whole double confirmation (two confirmations from
two distinct prompts you typed, inside the proposal's window, for that file)
of exactly that value, AND the machine file is still the file that
confirmation left: the same bytes, size, modification time and change time
(the metadata-change time: POSIX `ctime`, NTFS ChangeTime on Windows). crew's own
config writer (`crew_config.py --set`, `/crew:config`, a confirmed `humanOnly`
change) carries the receipt over when it changes another key. Any other change
to the machine file turns the switch off until you confirm it again: a hand
edit, an agent's Edit, a restore from backup, even setting `"off"` by hand and
then the same `"all"` back, or putting a copy of the confirmed file back with
`cp -p` (bytes and modification time restored; the change time still moves).
One gap, on Windows only: a copy made AND put back with a Windows file copy
(`Copy-Item`, Explorer, `shutil.copy2`) carries the change time over with the
bytes, so crew cannot tell it from the confirmed file. `crew_config.py --set` and `/crew:config` refuse
every value but `"off"` and null, and a crew write back to `"off"` revokes the
receipt. A repo file can never turn it on; a repo `"off"`, a malformed repo
value, or a repo `.crew/config.json` crew cannot read or parse (a link that
does not resolve, or a `.crew` that is a file, included) vetoes it.
Anything crew cannot read - a value outside the table, a store it cannot read,
a line it cannot split, a subcommand it cannot see - is off.

Never exempt, whatever the value: a git command that hands git config or a
command of its own - a global `-c` (an alias `!cmd`, `core.sshCommand`,
`core.pager`), `--config-env` or `--exec-path`, a `GIT_*` environment variable
set on the line, or an option or subcommand that runs a command it is given
(`rebase --exec`/`-x`, `submodule foreach`, `bisect run`, `push
--receive-pack`, `fetch`/`pull`/`clone`/`ls-remote --upload-pack`, `clone
-u`/`-c`/`--template`, `grep -O`, `difftool --extcmd`, `filter-branch`,
`instaweb`, `send-email --*-cmd`, `daemon --access-hook`), in any
abbreviation git accepts (`--exe`, `--receive=...`: git takes an unambiguous
prefix of a long option). Nor a git command crew cannot read whole: a word
built when it runs (`"$OPT"`, `${X:-...}`, `$env:X`, a backtick or `$(...)`
substitution, a PowerShell `@splat`) - so `git commit -m "$(git rev-parse
HEAD)"` is judged as before - or a git command `xargs` / `parallel` runs,
whose appended arguments come from input crew cannot see. In PowerShell a
single `&` (the background or call operator) makes the line unreadable for the
promote gate; `2>&1` and a quoted `&` do not. A git command aimed at another
repository (`git -C <dir>`) passes only when that repository's own file does
not veto it either; one whose repository crew cannot tell (`--git-dir`,
`--work-tree`, a `-C` built from a variable, or any `cd` on the line) is
judged as before.

What a receipt cannot prove: the store (`~/.claude/crew/confirm-config/`) is
plain files. It is protected from an agent's writes ONLY while `scope.mode` is
on: then the scope guard refuses a Write/Edit into it, and a shell command
naming it beside a writing word. With `scope.mode` off nothing stops an agent
writing a receipt, and even with it on a process that runs arbitrary code as
you can write a whole, well-formed record. And `"all"` does not stop what git
runs from its own persistent configuration: hooks (`.git/hooks/`,
`core.hooksPath`), aliases (`alias.*` set in a config file earlier), and
`core.sshCommand`, `core.pager`, `core.editor`, filters and the like all run
under `"all"` exactly as they would with crew absent. crew reads only the
command line, never git's config files or hooks.

`python3 hooks/scripts/crew_gitallow.py --root .` prints what is in force.
Each pass is logged to `.crew/guard.log` with the policy `gitAllow:<value>`.

## Guard profiles

`guards.profile` is one word for all twelve guards; `guards.overrides.<guard>`
replaces the profile's value for one guard. Each layer expands to a value per
guard, and the per-guard ratchet then takes the narrower layer. A malformed
profile or override reads as the guard's floor (`block`, or `none` for the
production guards), never as `off`. The per-guard keys of earlier versions
(`guards.<guard>`) are still READ as aliases for `guards.overrides.<guard>`
until `/crew:migrate` rewrites them, and are never written. For `envGuard` an
explicit `null` (`"guards": {"envGuard": null}`) is malformed and reads as `block`; only an
absent key is `off`. The other guards still read a legacy `null` as absent.

| Guard | `off` | `standard` | `strict` |
|---|---|---|---|
| `terraformApply` | `block` | `block` | `block` |
| `forcePush` | `block` | `block` | `block` |
| `adminMerge` | `block` | `ask` | `block` |
| `mergeGate` | `block` | `block` | `block` |
| `cloudDestructive` | `block` | `block` | `block` |
| `sqlDestructive` | `block` | `block` | `block` |
| `deployWorkflow` | `block` | `block` | `block` |
| `prodDatabase` | `none` | `none` | `none` |
| `prodServer` | `none` | `none` | `none` |
| `roleWrites` | `off` | `report` | `block` |
| `cloudGuard` | `off` | `block` | `block` |
| `envGuard` | `off` | `off` | `block` |

## Migrating and removed keys

`/crew:migrate` upgrades a repo file; `python3 plugin/crew/hooks/scripts/crew_migrate.py --global`
does the same for the machine file (preview, apply and rollback). It rewrites
`guards.*` into the profile with the fewest overrides and removes removed keys
that hold their default. A removed key holding another value stops the migration
until it is deleted or accepted with `--accept-dropped <key>`. 60 keys were
removed (ticket L-0725) and are now constants in `crew_state`
(`crew_dropped.DROPPED` lists each with its constant); a config still carrying
one is reported as having no effect (`crew_config.py --inert`, `/crew:status`, and the
SessionStart notice).

## Counts by family

| Family | Keys |
|---|---|
| `core` | 26 |
| `providers` | 18 |
| `guards` | 9 |
| `cloud` | 13 |
| `trackers` | 5 |
| `autopilot` | 15 |
| `context` | 11 |
| `notify` | 4 |
| `memory` | 2 |
| `platform` | 4 |

## `core` keys (26)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `schema` | repo | `8` | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | Config schema version; `/crew:migrate` upgrades an older one. |
| `verifyGate` | repo | `true` | not validated - read by `hooks/scripts/verify-gate.sh` (expects boolean) | Run the Stop verify gate. |
| `humanOnly.approve` | human-only opt-out | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | The owner's opt-out of `/crew:approve` being human-only. null or `true` keeps it human-only; `false` opts out only from the machine file or an untracked repo file, only after `/crew:confirm-config` twice, and a `true` in either layer vetoes. crew 1.3.27: with an opt-out in force a cli-recorded approval counts (`crew_ticket.cli_approval_allowed`). |
| `humanOnly.promoteMarker` | human-only opt-out | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | The same opt-out for the production promote marker `.crew/.approved-<env>-<sha>`, under the same rules. crew 1.3.9: no hook acts on it yet, and no hook today checks who created the marker. |
| `worktrees.root` | both | `null` | absolute path or null (coerced in `hooks/scripts/crew_worktrees.py`) | The base directory for this repo's git worktrees, OUTSIDE the repo: they go in `<root>/<repo>-<digest>/<name>`. null is `~/.claude/crew/worktrees`; `~` is expanded, a relative path or one inside the repo is refused (never replaced by the default). It places the worktrees crew places (`/crew:emergency`, `crew_worktrees.py path`) and, once the owner registers the opt-in `WorktreeCreate` hook, the ones Claude Code creates; without the hook Claude Code keeps using `.claude/worktrees/`. |
| `promote.deadlineSeconds` | both | `null` | number of seconds, or null (coerced in `hooks/scripts/_promote_gate.py`) | How many seconds the promote gate (`promote-gate.sh`) may run, counted from the moment its shell began, before it gives up and blocks (a hook that times out is not a block, so the gate stops itself first). null derives it from the guard's hook timeout less a 4 s margin: 16 s of the 20 s row. A number above the timeout less 2 s (18 s of 20) is clamped to that, so the setting can never let the gate outlive its hook; zero, a negative, a string or a boolean reads as null. The hook timeout is the guard's row in the dispatcher's table, not a setting. |
| `reaper.enabled` | both | `false` | boolean (coerced in `hooks/scripts/crew_reaper.py`) | Whether scheduled and session-start passes of the orphan reaper (`crew_reaper.py --scheduled`) do anything. false by default; a manual `crew_reaper.py` run always works and is a dry run unless given `--apply`. Read from the machine file only: a repo value is ignored, because the reaper ends processes on this machine. |
| `reaper.dryRun` | both | `true` | boolean (coerced in `hooks/scripts/crew_reaper.py`) | When true (the default) a scheduled or session-start pass only logs what it would end to `~/.claude/crew/reaper.log`; set false to let it end processes. Only a scheduled pass reads it; a manual run ends processes only with `--apply`. |
| `reaper.spinCpuPct` | both | `50` | percent of one core (coerced in `hooks/scripts/crew_reaper.py`) | An orphan is SPINNING when it used at least this percentage of one core over the reaper's short sample (5 s) and is older than `spinMinAgeMin`. A number above 0; anything else reads as 50. |
| `reaper.spinMinAgeMin` | both | `15` | number of minutes (coerced in `hooks/scripts/crew_reaper.py`) | Minutes an orphan must be running before the spinning rule (and the self-matching `until pgrep -f` watcher rule) may end it. A number above 0; anything else reads as 15. |
| `reaper.blockedMinAgeHours` | both | `2` | number of hours (coerced in `hooks/scripts/crew_reaper.py`) | Hours an orphan using under 1% of a core must be running before it counts as BLOCKED and may be ended. A number above 0; anything else reads as 2. |
| `reaper.protectedRegex` | both | `null` | regular expression, or null (coerced in `hooks/scripts/crew_reaper.py`) | A regular expression; a process whose image name or command line matches is never ended, it REPLACES the built-in list (claude, node, MCP servers, ai-connect, psmux/tmux, tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm, Defender, ssh). null keeps the built-in list; an invalid expression reads as null. |
| `reaper.intervalMin` | both | `10` | whole number of minutes (coerced in `hooks/scripts/crew_reaper.py`) | Minutes between runs of the scheduled task `crew_reaper.py --install-task` creates, and the least gap between two session-start passes. A whole number from 1; anything else reads as 10. The task is never installed by default. |
| `reaper.onSessionStart` | both | `false` | boolean (coerced in `hooks/scripts/crew_reaper.py`) | When true and `reaper.enabled` is true, the SessionStart context hook starts one detached reaper pass (at most one per `intervalMin`) and does not wait for it. false by default. |
| `emergency.standDown` | repo | `true` | not validated - read by `hooks/scripts/_common.sh` (expects boolean) | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.maxTtlMinutes` | repo | `480` | integer (coerced in `hooks/scripts/crew_incident.py`) | Longest incident lifetime; never below `ttlMinutes`. |
| `pm.authority` | both, widening warned | `"report-only"` | `report-only` \| `act` \| `autonomous` | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.maxDispatches` | both | `3` | integer (coerced in `hooks/scripts/crew_state.py`) | Roles the PM may dispatch in one pass. |
| `graph.out` | repo | `"graphify-out"` | not validated - read by `hooks/scripts/crew_state.py` (expects path) | Where the code graph is written. |
| `install.policy` | both, ratchet | `"manual"` | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | Whether crew may install a missing prerequisite. |
| `change.requireForProduction` | both, ratchet | `false` | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |
| `git.forbiddenTrailers` | both | `[]` | list of trailer tokens (letters, digits and `-`, no `:`) (checked in `hooks/scripts/crew_trailers.py`) | Commit trailer tokens the owner forbids, reported by `/crew:done`. The two layers combine by union, so a repo can add a token and never remove the machine owner's; a value that is not a list of tokens makes the list unknown, never empty (docs/crew/config-rationale.md). |
| `scope.mode` | repo | `"off"` | `off` \| `report` \| `block` \| `auto` | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | repo | `false` | `false` \| `true` (checked in `hooks/scripts/crew_ticket.py`) | Whether a CLI-written approval receipt counts; only exactly `true` allows it. `autopilot.approval: self` or `risk` needs it, and `autopilot.mode: plan` or `backlog`, to approve anything. A hand edit by the owner in the repo's `.crew/config.json` (`"scope": {"allowCliApproval": true}`); `crew_config.py --set` refuses it. |
| `tickets.baseBranch` | repo | `null` | branch name or null (checked in `hooks/scripts/scope_base.py`) | The branch ticket branches are cut from; null tries origin/HEAD's target, then origin/main, then main. A value that is not a branch name, or names no commit, makes the scope base could not tell. |
| `route.enabled` | both | `false` | `false` \| `true` (checked in `hooks/scripts/crew_route.py`) | Route plain-text prompts to `/crew:` commands; only the JSON value `true` arms it. |

## `providers` keys (18)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `qa.provider` | both | `"auto"` | `auto` \| `claude` \| `codex` \| `copilot` \| `kimi` | Who reviews: `auto` walks `qa.order`; a named provider is used as-is. |
| `qa.order` | both | `["codex", "kimi", "copilot", "claude"]` | list of: `claude` \| `codex` \| `copilot` \| `kimi` | The reviewers `auto` tries, in order. A list is one leaf, replaced wholesale. |
| `qa.fallback` | both | `"claude-sonnet-5"` | not validated - read by `commands/review.md` (expects model id) | Model a gone pin falls back to, on its family's provider (L-0712). |
| `qa.codex.model` | both | `null` | not validated - read by `commands/review.md` (expects string or null) | Codex model for review; null passes no flag. |
| `qa.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | both | `null` | not validated - read by `commands/review.md` (expects string or null) | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | both | `null` | not validated - read by `commands/review.md` (expects string or null) | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `qa.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a pin beats the provider block for that role. |
| `dev.provider` | both | `"claude"` | `claude` \| `codex` \| `copilot` \| `kimi` | Who implements. |
| `dev.fallback` | both | `"claude-sonnet-5"` | not validated - read by `skills/crew-providers/SKILL.md` (expects model id) | Model a gone dev pin falls back to, on its family's provider. |
| `dev.codex.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Codex model for implementation. |
| `dev.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | Codex reasoning effort for implementation. |
| `dev.copilot.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Copilot model for implementation. |
| `dev.kimi.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | Per-role dev pins, as `qa.roles`. |
| `secondOpinion.provider` | both | `"none"` | not validated - read by `commands/plan.md` (expects string) | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | both | `"cli"` | not validated - read by `skills/crew-providers/SKILL.md` (expects string) | How the second opinion is reached. |
| `secondOpinion.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Second-opinion model. |

## `guards` keys (9)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `guards.profile` | both, ratchet | `"off"` | `off` \| `standard` \| `strict` | One word for the twelve guards: `off` (today's defaults), `standard` or `strict`. Expands per layer; each guard's ratchet then runs on the expanded values. |
| `guards.overrides` | both, ratchet | `{}` | object of guard name to tier (checked in `hooks/scripts/crew_guards.py`) | `guards.overrides.<guard>`: one guard's tier, replacing the profile's value for it. Each entry is checked against that guard's own tiers; a bad one reads as the floor. |
| `guards.mass.enabled` | both | `false` | boolean (coerced in `hooks/scripts/crew_mass.py`) | Turns the mass delete / create / change stop on (it is also armed by a double-confirmed `humanOnly` opt-out). On if EITHER layer says exactly `true`; off by default. |
| `guards.mass.deleteCount` | both | `10` | integer (1 or more) (coerced in `hooks/scripts/crew_mass.py`) | Files a command may delete before it waits for `/crew:approve-mass`; a count at the limit stops. The machine file sets it; the repo file can only lower it; a value that is not a positive integer reads as the default. |
| `guards.mass.createCount` | both | `20` | integer (1 or more) (coerced in `hooks/scripts/crew_mass.py`) | Files a command may create before it waits for `/crew:approve-mass`; a count at the limit stops. The machine file sets it; the repo file can only lower it; a value that is not a positive integer reads as the default. |
| `guards.mass.changeCount` | both | `30` | integer (1 or more) (coerced in `hooks/scripts/crew_mass.py`) | Files a command may rewrite before it waits for `/crew:approve-mass`; a count at the limit stops. The machine file sets it; the repo file can only lower it; a value that is not a positive integer reads as the default. |
| `guards.mass.overrides` | both | `{}` | object of category to {deleteCount, createCount, changeCount} (checked in `hooks/scripts/crew_mass.py`) | `guards.mass.overrides.<files\|git\|terraform>.<deleteCount\|createCount\|changeCount>`: one limit for one kind of command. Unset, `terraform` is delete 3, create 10, change 10 (inferred, not measured); the others use the limits above. |
| `guards.mass.exempt` | both | `[]` | list of globs (coerced in `hooks/scripts/crew_mass.py`) | Repo-relative globs of generated files that never count toward a limit, read from the machine file only (a glob can only loosen the stop), on top of the built-in  regenerable directories (node_modules, __pycache__, .venv, caches, build, dist, .work, worktrees). |
| `guards.git.allow` | both | `null` | null, `"off"`, `"all"` or a list of git subcommand names (coerced in `hooks/scripts/crew_gitallow.py`) | The owner's switch that stops crew's command guards blocking or asking on git commands: `"all"` lets every git command past the force-push rule, the mass guard's git counts and the promote gate (a line of only git commands, unless a declared deploy is itself a git command); a list of subcommands (`["commit", "push"]`) lets only those through, with every option they take (listing `push` lets `push --force` through). null or `"off"` changes nothing. Machine file only, and only after `/crew:confirm-config` twice (`crew_confirm_config.py propose --key guards.git.allow --value ...`); a value written any other way, or any later change to the machine file outside crew's config writer, reads as off, and a repo `"off"` or unreadable repo file vetoes it. A git command carrying `-c`, a `GIT_*` variable or a command to run (`rebase --exec` or an abbreviation such as `--exe`, `submodule foreach`, ...), a word built when it runs (`"$OPT"`), or run by `xargs` is never exempt. |

## `cloud` keys (13)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `production.databases` | repo | `[]` | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | Globs naming production databases. |
| `production.hosts` | repo | `[]` | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | Globs naming production hosts. |
| `cloud.awsProfiles` | repo | `[]` | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | AWS profiles this repo may use. |
| `cloud.awsRegions` | repo | `[]` | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | AWS regions this repo may use. |
| `cloud.azureSubscriptions` | repo | `[]` | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | Azure subscriptions this repo may use. |
| `environments.nonProd` | repo | `[]` | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | Terraform targets that are not production and may run unattended. |
| `environments.prodUnattended` | both, ratchet | `false` | `false` \| `true` (ratchet: narrower layer wins; listed narrowest first) | Whether production terraform may run unattended; `true` only when both layers say so. |
| `environments.workflows` | repo | `{}` | not validated - read by `hooks/scripts/crew_config.py` (expects object of glob to string) | Deploy workflow globs, each mapped to its environment or `input:<name>`. |
| `environments.preProduction` | repo | `{}` | not validated - read by `hooks/scripts/crew_preprod.py` (expects object of exact name to {reason, targets}) | Environments labelled production that are not live yet: exact name -> `reason` (+ optional exact `targets`); judged non-production by the cloud guard, with an audit line. |
| `unattendedCloud.aws.readOnly.profile` | machine-only | `null` | profile name, or null (coerced in `hooks/scripts/crew_unattended.py`) | The AWS profile an unattended run exports credentials from (`aws configure export-credentials`); it must yield temporary credentials. Machine file only. |
| `unattendedCloud.aws.readOnly.identity` | machine-only | `null` | ARN prefix ending in `/`, or null (coerced in `hooks/scripts/crew_unattended.py`) | The assumed-role ARN prefix STS must report for that profile, ending in `/`; null refuses every launch. Machine file only. |
| `unattendedCloud.aws.readOnly.region` | machine-only | `null` | region, or null (coerced in `hooks/scripts/crew_unattended.py`) | The AWS region the unattended run gets; null is `us-east-1`. Machine file only. |
| `unattendedCloud.aws.nonProd` | machine-only | `{}` | None (checked in `hooks/scripts/crew_unattended.py`) | Environment name -> `{profile, identity, region}` for `launch --environment NAME`; usable only where the repo's `environments.nonProd` agrees. Machine file only. |

## `trackers` keys (5)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `tracker` | repo | `"files"` | `files` \| `obsidian` \| `jira` \| `sdp` | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `jira.project` | repo | `null` | not validated - read by `commands/jira-sync.md` (expects string or null) | Jira project key. No consumer found (docs/crew/config-rationale.md). |
| `jira.cloudId` | repo | `null` | not validated - read by `commands/jira-sync.md` (expects string or null) | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |
| `obsidian.vaultPath` | repo | `null` | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | repo | `null` | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | Board folder inside the vault (relative, no `..`). |

## `autopilot` keys (15)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `autopilot.mode` | both, stricter wins | `"off"` | `off` \| `plan` \| `backlog` (checked in `hooks/scripts/crew_autopilot.py`); personal: listed strictest first, the stricter wins | Only the exact strings `plan` (one ticket per run) and `backlog` (L-0541: a goal's tickets in dependency order, inside the caps) arm `/crew:autopilot`; anything else reads as off, with a warning. |
| `autopilot.maxPhases` | both, stricter wins | `12` | positive integer (checked in `hooks/scripts/crew_autopilot.py`); personal: the smaller wins | Phases one run may take; anything but a positive integer reads as 12, with a warning. |
| `autopilot.deploy` | both, stricter wins | `"none"` | `none` \| `nonprod` \| `all`; personal: listed strictest first, the stricter wins | Where a deploy may run without asking; anything else reads as `none`. |
| `autopilot.approval` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | Who approves a ticket under autopilot; anything else reads as `human`. `risk` and `self` also need `autopilot.mode: plan` (or `backlog`) and `scope.allowCliApproval: true` (a hand edit of the repo's `.crew/config.json`); a refused `approve` lists each unmet one, with its value as written, the file that holds it and, under `risk`, the spec risk that blocks. |
| `autopilot.questions` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | Who answers a ticket's open questions under autopilot; anything else reads as `human`. |
| `autopilot.maxAutoReplans` | repo | `0` | non-negative integer (checked in `hooks/scripts/crew_autopilot.py`) | Successor plans autopilot may start by rejecting an out-of-rounds BLOCK review itself; 0 is off, and anything but a non-negative integer reads as 0, and above 5 as 5, with a warning. |
| `autopilot.ship` | repo | `"merge"` | `pr` \| `merge` | After `/crew:done`: `pr` pushes and opens the PR; `merge` also merges it (a merge commit) once the required checks allow. Anything else reads as `pr`, with a warning. |
| `autopilot.sleep.schedule` | repo | `null` | HH:MM-HH:MM or null (checked in `hooks/scripts/crew_sleep.py`) | A nightly window, `HH:MM-HH:MM` in machine local time (may cross midnight); inside it the two sleep overrides apply. Anything else is could not tell: only a stricter override applies. |
| `autopilot.sleep.approval` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `hooks/scripts/crew_sleep.py`) | `autopilot.approval` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.questions` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `hooks/scripts/crew_sleep.py`) | `autopilot.questions` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.deploy` | repo | `null` | `null` \| `nonprod` \| `none` (checked in `hooks/scripts/crew_sleep.py`) | `autopilot.deploy` inside the sleep window (L-0654): null keeps the day value, `nonprod` or `none` replaces it; anything else, `all` included, is refused with a warning. Asleep, an effective `all` reads as `nonprod`: production never runs unattended asleep. |
| `autopilot.maxTicketsPerRun` | repo | `3` | positive integer (checked in `hooks/scripts/crew_autopilot_backlog.py`) | Tickets one goal run (one session) may start; the next one stops the run. Anything but a positive integer reads as 3, with a warning. |
| `autopilot.maxTokensPerSession` | repo | `2000000` | positive integer (checked in `hooks/scripts/crew_autopilot_backlog.py`) | Input plus output tokens one goal session may spend, each assistant message counted once, before the run stops; a transcript that cannot be read stops too. Anything but a positive integer reads as 2000000, with a warning. |
| `autopilot.maxLanes` | repo | `null` | positive integer or null (checked in `hooks/scripts/crew_wave.py`) | Lanes one `/crew:autopilot wave` runs at once; null is the resolved `pm.maxDispatches`, a larger value is capped to it and anything but a positive integer reads as it, each with a warning. |
| `autopilot.reviewPolicy` | repo | `"stop"` | `stop` \| `clean-only` \| `fix-and-rereview` | What autopilot does with a review verdict. A wave lane: `stop` ends at the first verdict, `clean-only` takes a CLEAN round on to the done checks, `fix-and-rereview` fixes within the ledger's rounds. A single-ticket run (T-0067): only `fix-and-rereview` acts, fixing a non-final FINDINGS round's BLOCK and FIX lines itself (the `fix` phase) and re-reviewing. Anything else reads as `stop`, with a warning; no setting accepts a review. |

## `context` keys (11)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `context.enabled` | repo | `true` | not validated - read by `hooks/scripts/context-watch.sh` (expects boolean) | Run the context watcher. |
| `context.warnAt` | repo | `0.4` | not validated - read by `hooks/scripts/context-watch.sh` (expects number) | Fraction of the budget at which the watcher warns, wraps up and auto-clears; default 0.4 since 1.2.40 (was 0.5), an explicit value is kept. |
| `context.reserveTokens` | repo | `0` | not validated - read by `hooks/scripts/context-watch.sh` (expects integer or null) | Tokens held back from the budget; `null` means off. |
| `context.autoClear.enabled` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.method` | both | `"auto"` | `auto` \| `none` \| `notify` \| `tmux` \| `xdotool` \| `wtype`; per OS: linux: auto, none, notify, tmux, xdotool, wtype; macos: auto, none, notify, tmux; windows: auto, none, notify; windows-bash: auto, none, notify, tmux | How `/clear` is typed. `auto` picks per platform; a method this OS lacks stands auto-clear down. |
| `context.autoClear.delaySeconds` | both | `3` | number (coerced in `hooks/scripts/crew_autocycle.py`) | Delay before typing; an unusable value warns and reads as 3. |
| `context.autoClear.minHandoffLines` | both | `5` | number (coerced in `hooks/scripts/crew_autocycle.py`) | Shortest handoff that may be cleared after; a non-number reads as 5. |
| `context.autoClear.onlyRepos` | machine-only | `null` | list of absolute repo paths, or null (coerced in `hooks/scripts/crew_autocycle.py`) | Narrowing only, machine file only: null narrows nothing, a list arms only those repos, `[]` or a non-list arms nothing. |
| `context.autoClear.onlySessions` | machine-only | `null` | list of session ids, or null (coerced in `hooks/scripts/crew_autocycle.py`) | As `onlyRepos`, for session ids; with both set, both must match. |
| `context.autoClear.wrapUp` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |
| `resume.auto` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_resume.py`) | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |

## `notify` keys (4)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `notify.provider` | both | `null` | telegram, teams, none or null; any other value sends nothing (coerced in `hooks/scripts/crew_notify.py`) | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.tokenEnv` | machine-only | `null` | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | Name of the environment variable holding the Telegram bot token; null may be filled from the notify skill's `bot_token_env`. Honoured from the machine file only. |
| `notify.chatId` | both | `null` | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |
| `notify.events` | both | `["blocker", "deploy", "question"]` | list of event names; an unknown name is dropped with a notice (coerced in `hooks/scripts/crew_notify.py`) | Events that notify: `deploy`, `question`, and `blocker` (T-0060's four blocker reasons). The pre-1.0 names `gate`, `waiting`, `phase`, `review` and `done` are mapped with a notice. A list is one leaf. |

## `memory` keys (2)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `memory.mode` | both | `"repo"` | not validated - read by `skills/crew-memory/SKILL.md` (expects string) | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | both | `null` | not validated - read by `hooks/scripts/crew_recall.py` (expects path or null) | The Obsidian vault used for memory. |

## `platform` keys (4)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `platform.os` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | Detected OS, stamped by platform-sync. |
| `platform.wsl` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects boolean or null) | Detected WSL, stamped by platform-sync. |
| `platform.shell` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | Windows host IP seen from WSL. |
