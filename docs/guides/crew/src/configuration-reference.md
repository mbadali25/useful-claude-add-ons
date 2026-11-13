# crew 1.0 - configuration reference

This document has two parts. The first is short and hand-written: how crew's two
config files combine, how to see what is in force, and the common setups. The
second is generated from the code and lists every key.

## How the two files combine

crew reads two JSON files:

- `~/.claude/crew/config.json` - the **machine-global** file. Your personal
  defaults for every repo on this machine: providers and models, notifications,
  auto-clear, the guards, how far autopilot may go.
- `.crew/config.json` - the **repo** file. Facts about one checkout: the
  tracker, the board, scope enforcement, production declarations.

The repo file wins over the machine file, which wins over crew's defaults. Four
exceptions, each named in the Layer column below:

- A **repo-only** key in the machine file takes effect nowhere. It is pruned on
  read and refused on write.
- A **ratcheted** key (`install.policy`, each guard `guards.profile` and
  `guards.overrides` expand to, `change.requireForProduction`,
  `environments.prodUnattended`) resolves to the narrower of the two values, so
  a cloned repo cannot widen what your machine allows.
- A **machine-armed** key (`resume.auto`, `context.autoClear.enabled`) can be
  turned on only in the machine file. A repo can only switch it off.
- A **personal** key (the five `autopilot.*` keys) resolves per key to the
  stricter of the layers that set it; a layer that says nothing imposes
  nothing. A machine value is your default for every repo, which a repo may
  narrow and never widen.

A `null` in the repo file over a machine value inherits the machine value. The
`/crew:init` template writes every key except the personal ones, so it does not
shadow your machine defaults for those; a repo `/crew:init` set up before that
still spells `autopilot.mode: "off"`, which holds a machine `plan` down until
you remove it (`--explain --all` names it as a `shadow:`).

## Seeing what is in force

- `/crew:config --show` prints every machine-settable key, its value and the
  layer it came from, and names any key that takes effect nowhere.
- `/crew:config` with no argument is a menu that writes either file through the
  validated path. It shows a dry run first, refuses unknown keys and
  out-of-range values, and marks a widening with `!`.
- From a shell:
  `python3 plugin/crew/hooks/scripts/crew_config.py --explain` is the same
  table, `--explain --all` adds every repo-only key and names each shadowing
  repo value, and `--models` is the per-role provider table.

## Backups and rebuilding a lost config

Every write a crew script makes to either file first copies the old bytes to
`~/.claude/crew/backups/` (the newest 20 per file kept) and is refused when
that copy fails; a hand edit is not backed up. `crew_config.py --backups`
lists the machine file's (add `--repo` for the repo file's) and
`--restore <stamp> --apply` puts one back. Your non-default values are kept in
`~/.claude/crew/profile.json` (and in your vault when `memory.vaultPath` is
set), so `--rebuild --repo` or `--rebuild --global` regenerates a lost or
corrupt file from the template plus that profile, as a dry run until
`--apply`.

## Common setups

- **Personal defaults once, for every repo.** Put providers, models,
  `notify.*`, the guards and the `autopilot.*` keys in
  `~/.claude/crew/config.json`. Leave repo files to repo facts.
- **Self-approval under autopilot.** Set `autopilot.mode: "plan"` and choose
  `autopilot.approval` (`human`, `self` or `risk`) in either file, and set
  `scope.allowCliApproval: true` in the repo file, which is the only file
  that key is read from. Review acceptance and production deploys still stop
  for you.
- **Notifications.** In the machine file, set `notify.provider` and the name
  of the environment variable holding the token in `notify.tokenEnv`. The
  secret stays in your environment, never in the file. `tokenEnv` is
  machine-only: a repo file's value is ignored with a notice.

The key list is `plugin/crew/CONFIG.md`, which ships with the plugin; the
reasoning behind the keys is in `docs/crew/config-rationale.md`.

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

## Git commands (`guards.git.allow`, crew 1.3.82)

The owner's switch that stops crew's command guards from blocking or asking on
git commands, destructive ones included. Off by default (`null`, or `"off"`).

| Value | What passes |
|---|---|
| `null` / `"off"` | nothing changes: every guard judges git as before |
| `"all"` | a line made only of plain git commands |
| `["commit", "push", ...]` | such a line whose every git command's subcommand is listed; every other line keeps today's checks |

A listed subcommand passes with every option it takes: listing `push` also lets
`git push --force` and `git push origin +main` through, because the force-push
rule is a finding on the `push` subcommand. To keep force pushes stopped, leave
`push` out of the list.

What it loosens, and nothing else: the cloud guard's `guards.forcePush` rule
(`git push --force`, `+ref`) and the promote gate, so a commit message or
heredoc that merely mentions a declared deploy no longer trips it. A declared
deploy that is itself a git command (`git push prod main`) stays gated: that
is a deploy, not a git block. `gh` is not git: `gh pr merge --admin`
(`guards.adminMerge`), workflow dispatches and `gh api` calls are untouched.

**The line is a fail-closed allowlist (crew 1.3.82).** A command line is
exempt only when EVERY command on it is exactly `git` - not a path
(`/usr/bin/git`, `./git`, `git.exe`), and with no other command on the line,
so a function, alias or `shopt` that redefines git, an assignment, `cd`,
`command git`, a subshell `( )` or group `{ }` all leave the line judged as
before - and every word of every git command is a plain literal, read by ONE
reader that both the cloud guard and the promote gate use:

- bash: unquoted letters, digits and `_ - . / : = + , @ % ^`, a `~` that is
  not at the start (`HEAD~3`), git's `@{...}` (`@{u}`, `HEAD@{1}`) with no `,`
  or `..` inside; whole `'...'` runs; `"..."` runs with no `$` or backtick; a
  backslash escaping one character; a heredoc whose delimiter is quoted, or
  whose body has no `$`, backtick or backslash. Commands joined only by `;`,
  `&&`, `||`, `|`, `&` or a newline. A redirection only AFTER the
  subcommand, and only `>` / `>>` (an optional digit descriptor) to a plain
  file name not starting with `-`, `N>&M` between digit descriptors
  (`2>&1`), or a heredoc / here-string (crew 1.3.82).
- PowerShell: unquoted letters, digits and `_ - . / : = + \ ^ % ~ @` (no
  leading `~`, `@` only inside a word); a whole `'...'` or `"..."`
  word (a double-quoted one holding no `$`); a here-string (`@"..."@` with no
  `$` or backtick); a backtick escaping a character that is not a letter or
  digit; an unquoted first word; a redirection after the subcommand
  (`2>&1`, `*>&1`, `> out`; only `n>&1` merges, PowerShell reserves `1>&2`).
  Statements joined only by `;`, `&&`, `||` or a newline, with a statement on
  both sides of every `&&` and `||`.

Anything else is "cannot tell", and cannot tell is never exempt: `$` in any
form (`"$OPT"`, `${X:-...}`, `$'\x2d...'`, `$"..."`, `$env:X`, `$(...)`), a
backtick substitution, a glob (`*`, `?`, `[`), a brace expansion, a leading
`~`, a PowerShell `(expr)`, `@(...)`, `@splat`, `{ }` or `[type]`, a pipe into
anything, a single `&`, `--%`, a `%NAME%`, a curly quote, a backtick
before a letter (`` `u{2d} `` is a `-`) or a newline inside a word, a
dangling `&&` / `||` (or an empty command after one), and every other
redirection: `<`, `<&`, `<>`, `>|`, `&>`, `>&-`, `>& file`, a `{var}>`
descriptor, one with no target, and any redirection between `git` and its
subcommand. Bash reads `>&-` as "close the descriptor" and hands the rest of
that word to git, so `git push >&---receive-pack=x origin main` runs git with
`--receive-pack=x`; and `git 2>&1 -c core.sshCommand=x push` hid its `-c`
from a reader that kept the `2` (crew 1.3.82, review round 5). Five review
rounds each found a new way to build a git word at run time; the allowlist
lists what is plain instead of what is dangerous, so a form nobody has
thought of yet is judged, not exempt. A differential test
(`tests/test_git_allow_differential.py`) runs every line of a generated
corpus that the allowlist accepts under real bash and PowerShell 7 with a
shim `git` that logs its argv, and fails when git is handed anything other
than the argv crew read.

Never exempt even when every word is plain: a git command that hands git
config or a command of its own - a global `-c` (an alias `!cmd`,
`core.sshCommand`, `core.pager`), `--config-env` or `--exec-path`; an option or
subcommand that runs a command it is given (`rebase --exec`/`-x`,
`submodule foreach`, `bisect run`, `push`/`send-pack --receive-pack`/`--exec`,
`fetch-pack --upload-pack`/`--exec`, `fetch`/`pull`/`clone`/`ls-remote
--upload-pack`, `clone -u`/`-c`/`--template`, `init --template`, `grep -O`,
`difftool --extcmd`, `filter-branch`, `instaweb`, `send-email --*-cmd`,
`daemon --access-hook`), in any abbreviation git accepts (`--exe`,
`--receive=...`); and a `git config` that is not plainly a read (`--get*`,
`-l`/`--list`, `get`, `list`, or one key alone, with only read options): a
write may set `alias.*` or a program-valued key (`core.sshCommand`,
`core.pager`, `core.editor`, `core.fsmonitor`, `core.hooksPath`,
`diff.external`, `credential.helper`, `sequence.editor`, `gpg.program`, ...)
that a later git command on the same line runs. A git command aimed at another
repository (`git -C <dir>`) passes only when that repository's own file does
not veto it either; one whose repository crew cannot tell (`--git-dir`,
`--work-tree`) is judged as before.

What stays exempt, for example: `git commit -m "fix: x"`, `git push
--force-with-lease origin topic`, `git push -f origin topic`, `git rebase -i
HEAD~3`, `git -C <path> status`, `git log --format=%H`, `git log @{u}..HEAD`,
`git add -A && git commit -m 'x' && git push origin topic`, `git config
user.name`, and `git commit -F - <<'EOF' ... EOF`. What no longer is: `git
commit -m "$(...)"` (a substitution), a line with anything but git on it
(`git push -f && rm x`, `FOO=1 git push`), `/usr/bin/git ...`, and `git config
<key> <value>`.

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
a line it cannot read whole - is off.

What a receipt cannot prove: the store (`~/.claude/crew/confirm-config/`) is
plain files. It is protected from an agent's writes ONLY while `scope.mode` is
on: then the scope guard refuses a Write/Edit into it, and a shell command
naming it beside a writing word. With `scope.mode` off nothing stops an agent
writing a receipt, and even with it on a process that runs arbitrary code as
you can write a whole, well-formed record. And `"all"` does not stop what git
runs from its own persistent configuration: hooks (`.git/hooks/`,
`core.hooksPath`), aliases (`alias.*` set in a config file earlier, by an
earlier command line), and `core.sshCommand`, `core.pager`, `core.editor`,
filters and the like all run under `"all"` exactly as they would with crew
absent. crew reads only the command line, never git's config files or hooks.

`python3 hooks/scripts/crew_gitallow.py --root .` prints what is in force.
Each pass is logged to `.crew/guard.log` with the policy `gitAllow:<value>`.

## Reference (generated)

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand:
`python3 scripts/check-marketplace.py` fails when this file is stale.

**101 keys**: 63 settable in the machine-global file, 38 repo-only.

Columns:

- **Layer**: which file may set the key.
- **Default**: what `default_config()` returns. Where the machine default differs, both are shown.
- **Values**: the values crew accepts, read from the same tuple the validator reads. "not validated" means crew checks nothing and names the file that reads the key.
- **Since**: the first crew version whose template declared the key. Keys in the first template (crew 0.11.0) read "0.11.0 or earlier".

### Layers

- **repo**: only `.crew/config.json` may set it; the global file's value is pruned on read and refused on write.
- **both**: either file may set it; the repo value wins over the machine one.
- **both, ratchet**: either file may set it, and the NARROWER of the two wins (`crew_guards.RATCHETED_KEYS`). A repo can tighten what the machine allows, never loosen it.
- **both, widening warned**: either file may set it and the repo wins, but a write that widens it is flagged (`crew_config._RATCHETED`).
- **both, stricter wins**: a personal key (`crew_guards.PERSONAL_KEYS`): either file may set it, and where both do the STRICTER value wins; a layer that is silent (absent or `null`) imposes nothing, so a machine value is your default for every repo and a repo may only narrow it.
- **machine-arms**: only the global file can turn it on (exactly `true`); a repo may only veto it with `false` (`crew_config.REPO_VETO_ONLY`).
- **machine-only**: read from the global file alone; a repo's own value is never consulted.
- **human-only opt-out**: a `humanOnly` key (`crew_humanonly`): `false` opts out only from the machine file or an untracked repo file, only after the owner types `/crew:confirm-config <change_id>` twice, and a `true` in either layer vetoes it. Not acted on by any hook yet (see the section below).

### Top-level keys

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `schema` | repo | `8` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.11.0 or earlier | Config schema version; `/crew:migrate` upgrades an older one. |
| `tracker` | repo | `"files"` | `files` \| `obsidian` \| `jira` \| `sdp` | 0.11.0 or earlier | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `verifyGate` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/verify-gate.sh` (expects boolean) | 0.11.0 or earlier | Run the Stop verify gate. |

### `qa`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `qa.provider` | both | `"auto"` | `auto` \| `claude` \| `codex` \| `copilot` \| `kimi` | 0.11.0 or earlier | Who reviews: `auto` walks `qa.order`; a named provider is used as-is. |
| `qa.order` | both | `["codex", "kimi", "copilot", "claude"]` | list of: `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | The reviewers `auto` tries, in order. A list is one leaf, replaced wholesale. |
| `qa.fallback` | both | `"claude-sonnet-5"` | not validated - read by `plugin/crew/commands/review.md` (expects model id) | 0.16.6 | Model a gone pin falls back to, on its family's provider (L-0712). |
| `qa.codex.model` | both | `null` | not validated - read by `plugin/crew/commands/review.md` (expects string or null) | 0.14.6 | Codex model for review; null passes no flag. |
| `qa.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `plugin/crew/commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | both | `null` | not validated - read by `plugin/crew/commands/review.md` (expects string or null) | 0.14.6 | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | both | `null` | not validated - read by `plugin/crew/commands/review.md` (expects string or null) | 1.0.39 | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `qa.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `plugin/crew/hooks/scripts/crew_config.py`) | 0.16.6 | Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a pin beats the provider block for that role. |

### `dev`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `dev.provider` | both | `"claude"` | `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | Who implements. |
| `dev.fallback` | both | `"claude-sonnet-5"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects model id) | 0.16.6 | Model a gone dev pin falls back to, on its family's provider. |
| `dev.codex.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Codex model for implementation. |
| `dev.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `plugin/crew/commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for implementation. |
| `dev.copilot.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Copilot model for implementation. |
| `dev.kimi.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 1.0.39 | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `plugin/crew/hooks/scripts/crew_config.py`) | 0.16.6 | Per-role dev pins, as `qa.roles`. |

### `secondOpinion`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `secondOpinion.provider` | both | `"none"` | not validated - read by `plugin/crew/commands/plan.md` (expects string) | 0.11.0 or earlier | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | both | `"cli"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string) | 0.11.0 or earlier | How the second opinion is reached. |
| `secondOpinion.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.11.0 or earlier | Second-opinion model. |

### `jira`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `jira.project` | repo | `null` | not validated - read by `plugin/crew/commands/jira-sync.md` (expects string or null) | 0.11.0 or earlier | Jira project key. No consumer found (docs/crew/config-rationale.md). |
| `jira.cloudId` | repo | `null` | not validated - read by `plugin/crew/commands/jira-sync.md` (expects string or null) | 0.19.10 | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |

### `obsidian`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `obsidian.vaultPath` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Board folder inside the vault (relative, no `..`). |

### `memory`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `memory.mode` | both | `"repo"` | not validated - read by `plugin/crew/skills/crew-memory/SKILL.md` (expects string) | 0.11.0 or earlier | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_recall.py` (expects path or null) | 0.11.0 or earlier | The Obsidian vault used for memory. |

### `context`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `context.enabled` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects boolean) | 0.11.0 or earlier | Run the context watcher. |
| `context.warnAt` | repo | `0.4` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects number) | 0.11.0 or earlier | Fraction of the budget at which the watcher warns, wraps up and auto-clears; default 0.4 since 1.2.40 (was 0.5), an explicit value is kept. |
| `context.reserveTokens` | repo | `0` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects integer or null) | 0.11.0 or earlier | Tokens held back from the budget; `null` means off. |
| `context.autoClear.enabled` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 0.19.10 | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.method` | both | `"auto"` | `auto` \| `none` \| `notify` \| `tmux` \| `xdotool` \| `wtype`; per OS: linux: auto, none, notify, tmux, xdotool, wtype; macos: auto, none, notify, tmux; windows: auto, none, notify; windows-bash: auto, none, notify, tmux | 0.19.10 | How `/clear` is typed. `auto` picks per platform; a method this OS lacks stands auto-clear down. |
| `context.autoClear.delaySeconds` | both | `3` | number (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 0.19.10 | Delay before typing; an unusable value warns and reads as 3. |
| `context.autoClear.minHandoffLines` | both | `5` | number (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 0.19.10 | Shortest handoff that may be cleared after; a non-number reads as 5. |
| `context.autoClear.onlyRepos` | machine-only | `null` | list of absolute repo paths, or null (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.25 | Narrowing only, machine file only: null narrows nothing, a list arms only those repos, `[]` or a non-list arms nothing. |
| `context.autoClear.onlySessions` | machine-only | `null` | list of session ids, or null (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.25 | As `onlyRepos`, for session ids; with both set, both must match. |
| `context.autoClear.wrapUp` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.334 | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |

### `resume`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `resume.auto` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_resume.py`) | 1.0.40 | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |

### `humanOnly`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `humanOnly.approve` | human-only opt-out | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_humanonly.py`) | 1.3.9 | The owner's opt-out of `/crew:approve` being human-only. null or `true` keeps it human-only; `false` opts out only from the machine file or an untracked repo file, only after `/crew:confirm-config` twice, and a `true` in either layer vetoes. crew 1.3.27: with an opt-out in force a cli-recorded approval counts (`crew_ticket.cli_approval_allowed`). |
| `humanOnly.promoteMarker` | human-only opt-out | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_humanonly.py`) | 1.3.9 | The same opt-out for the production promote marker `.crew/.approved-<env>-<sha>`, under the same rules. crew 1.3.9: no hook acts on it yet, and no hook today checks who created the marker. |

### `worktrees`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `worktrees.root` | both | `null` | absolute path or null (coerced in `plugin/crew/hooks/scripts/crew_worktrees.py`) | 1.3.19 | The base directory for this repo's git worktrees, OUTSIDE the repo: they go in `<root>/<repo>-<digest>/<name>`. null is `~/.claude/crew/worktrees`; `~` is expanded, a relative path or one inside the repo is refused (never replaced by the default). It places the worktrees crew places (`/crew:emergency`, `crew_worktrees.py path`) and, once the owner registers the opt-in `WorktreeCreate` hook, the ones Claude Code creates; without the hook Claude Code keeps using `.claude/worktrees/`. |

### `promote`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `promote.deadlineSeconds` | both | `null` | number of seconds, or null (coerced in `plugin/crew/hooks/scripts/_promote_gate.py`) | 1.3.41 | How many seconds the promote gate (`promote-gate.sh`) may run, counted from the moment its shell began, before it gives up and blocks (a hook that times out is not a block, so the gate stops itself first). null derives it from the guard's hook timeout less a 4 s margin: 16 s of the 20 s row. A number above the timeout less 2 s (18 s of 20) is clamped to that, so the setting can never let the gate outlive its hook; zero, a negative, a string or a boolean reads as null. The hook timeout is the guard's row in the dispatcher's table, not a setting. |

### `reaper`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `reaper.enabled` | both | `false` | boolean (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | Whether scheduled and session-start passes of the orphan reaper (`crew_reaper.py --scheduled`) do anything. false by default; a manual `crew_reaper.py` run always works and is a dry run unless given `--apply`. Read from the machine file only: a repo value is ignored, because the reaper ends processes on this machine. |
| `reaper.dryRun` | both | `true` | boolean (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | When true (the default) a scheduled or session-start pass only logs what it would end to `~/.claude/crew/reaper.log`; set false to let it end processes. Only a scheduled pass reads it; a manual run ends processes only with `--apply`. |
| `reaper.spinCpuPct` | both | `50` | percent of one core (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | An orphan is SPINNING when it used at least this percentage of one core over the reaper's short sample (5 s) and is older than `spinMinAgeMin`. A number above 0; anything else reads as 50. |
| `reaper.spinMinAgeMin` | both | `15` | number of minutes (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | Minutes an orphan must be running before the spinning rule (and the self-matching `until pgrep -f` watcher rule) may end it. A number above 0; anything else reads as 15. |
| `reaper.blockedMinAgeHours` | both | `2` | number of hours (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | Hours an orphan using under 1% of a core must be running before it counts as BLOCKED and may be ended. A number above 0; anything else reads as 2. |
| `reaper.protectedRegex` | both | `null` | regular expression, or null (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | A regular expression; a process whose image name or command line matches is never ended, it REPLACES the built-in list (claude, node, MCP servers, ai-connect, psmux/tmux, tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm, Defender, ssh). null keeps the built-in list; an invalid expression reads as null. |
| `reaper.intervalMin` | both | `10` | whole number of minutes (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | Minutes between runs of the scheduled task `crew_reaper.py --install-task` creates, and the least gap between two session-start passes. A whole number from 1; anything else reads as 10. The task is never installed by default. |
| `reaper.onSessionStart` | both | `false` | boolean (coerced in `plugin/crew/hooks/scripts/crew_reaper.py`) | 1.3.50 | When true and `reaper.enabled` is true, the SessionStart context hook starts one detached reaper pass (at most one per `intervalMin`) and does not wait for it. false by default. |

### `emergency`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `emergency.standDown` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/_common.sh` (expects boolean) | 0.11.0 or earlier | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.maxTtlMinutes` | repo | `480` | integer (coerced in `plugin/crew/hooks/scripts/crew_incident.py`) | 0.11.0 or earlier | Longest incident lifetime; never below `ttlMinutes`. |

### `notify`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `notify.provider` | both | `null` | telegram, teams, none or null; any other value sends nothing (coerced in `plugin/crew/hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.tokenEnv` | machine-only | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Name of the environment variable holding the Telegram bot token; null may be filled from the notify skill's `bot_token_env`. Honoured from the machine file only. |
| `notify.chatId` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |
| `notify.events` | both | `["blocker", "deploy", "question"]` | list of event names; an unknown name is dropped with a notice (coerced in `plugin/crew/hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Events that notify: `deploy`, `question`, and `blocker` (T-0060's four blocker reasons). The pre-1.0 names `gate`, `waiting`, `phase`, `review` and `done` are mapped with a notice. A list is one leaf. |

### `platform`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `platform.os` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected OS, stamped by platform-sync. |
| `platform.wsl` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects boolean or null) | 0.11.0 or earlier | Detected WSL, stamped by platform-sync. |
| `platform.shell` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Windows host IP seen from WSL. |

### `pm`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `pm.authority` | both, widening warned | `"report-only"` | `report-only` \| `act` \| `autonomous` | 0.11.0 or earlier | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.maxDispatches` | both | `3` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | Roles the PM may dispatch in one pass. |

### `graph`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `graph.out` | repo | `"graphify-out"` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects path) | 0.11.0 or earlier | Where the code graph is written. |

### `install`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `install.policy` | both, ratchet | `"manual"` | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | 0.19.18 | Whether crew may install a missing prerequisite. |

### `guards`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `guards.profile` | both, ratchet | `"off"` | `off` \| `standard` \| `strict` | 1.2.62 | One word for the twelve guards: `off` (today's defaults), `standard` or `strict`. Expands per layer; each guard's ratchet then runs on the expanded values. |
| `guards.overrides` | both, ratchet | `{}` | object of guard name to tier (checked in `plugin/crew/hooks/scripts/crew_guards.py`) | 1.2.62 | `guards.overrides.<guard>`: one guard's tier, replacing the profile's value for it. Each entry is checked against that guard's own tiers; a bad one reads as the floor. |
| `guards.git.allow` | both | `null` | null, `"off"`, `"all"` or a list of git subcommand names (coerced in `plugin/crew/hooks/scripts/crew_gitallow.py`) | 1.3.82 | The owner's switch that stops crew's command guards blocking or asking on git commands: `"all"` lets a line of only plain git commands past the force-push rule and the promote gate (unless a declared deploy is itself a git command); a list of subcommands (`["commit", "push"]`) lets only those through, with every option they take (listing `push` lets `push --force` through). null or `"off"` changes nothing. Machine file only, and only after `/crew:confirm-config` twice (`crew_confirm_config.py propose --key guards.git.allow --value ...`); a value written any other way, or any later change to the machine file outside crew's config writer, reads as off, and a repo `"off"` or unreadable repo file vetoes it. FAIL-CLOSED ALLOWLIST: a line is exempt only when every command on it is exactly `git` with plain literal words (no `$`, backtick, glob, brace, leading `~`, parenthesis, PowerShell expression or `%NAME%`; nothing else on the line); a git command carrying `-c`, a command to run (`rebase --exec`, `push --receive-pack`, `submodule foreach`, ...) or a `git config` write is never exempt. |

### `production`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `production.databases` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects list of globs) | 0.19.30 | Globs naming production databases. |
| `production.hosts` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects list of globs) | 0.19.30 | Globs naming production hosts. |

### `cloud`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `cloud.awsProfiles` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | AWS profiles this repo may use. |
| `cloud.awsRegions` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | AWS regions this repo may use. |
| `cloud.azureSubscriptions` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | Azure subscriptions this repo may use. |

### `environments`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `environments.nonProd` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects list of globs) | 1.0.37 | Terraform targets that are not production and may run unattended. |
| `environments.prodUnattended` | both, ratchet | `false` | `false` \| `true` (ratchet: narrower layer wins; listed narrowest first) | 1.0.37 | Whether production terraform may run unattended; `true` only when both layers say so. |
| `environments.workflows` | repo | `{}` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects object of glob to string) | 1.1.16 | Deploy workflow globs, each mapped to its environment or `input:<name>`. |
| `environments.preProduction` | repo | `{}` | not validated - read by `plugin/crew/hooks/scripts/crew_preprod.py` (expects object of exact name to {reason, targets}) | 1.3.20 | Environments labelled production that are not live yet: exact name -> `reason` (+ optional exact `targets`); judged non-production by the cloud guard, with an audit line. |

### `change`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `change.requireForProduction` | both, ratchet | `false` | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | 0.19.31 | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |

### `git`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `git.forbiddenTrailers` | both | `[]` | list of trailer tokens (letters, digits and `-`, no `:`) (checked in `plugin/crew/hooks/scripts/crew_trailers.py`) | 1.0.328 | Commit trailer tokens the owner forbids, reported by `/crew:done`. The two layers combine by union, so a repo can add a token and never remove the machine owner's; a value that is not a list of tokens makes the list unknown, never empty (docs/crew/config-rationale.md). |

### `scope`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `scope.mode` | repo | `"off"` | `off` \| `report` \| `block` \| `auto` | 1.0.25 | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | repo | `false` | `false` \| `true` (checked in `plugin/crew/hooks/scripts/crew_ticket.py`) | 1.0.25 | Whether a CLI-written approval receipt counts; only exactly `true` allows it. `autopilot.approval: self` or `risk` needs it, and `autopilot.mode: plan` or `backlog`, to approve anything. A hand edit by the owner in the repo's `.crew/config.json` (`"scope": {"allowCliApproval": true}`); `crew_config.py --set` refuses it. |

### `autopilot`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `autopilot.mode` | both, stricter wins | `"off"` | `off` \| `plan` \| `backlog` (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`); personal: listed strictest first, the stricter wins | 1.0.41 | Only the exact strings `plan` (one ticket per run) and `backlog` (L-0541: a goal's tickets in dependency order, inside the caps) arm `/crew:autopilot`; anything else reads as off, with a warning. |
| `autopilot.maxPhases` | both, stricter wins | `12` | positive integer (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`); personal: the smaller wins | 1.0.41 | Phases one run may take; anything but a positive integer reads as 12, with a warning. |
| `autopilot.deploy` | both, stricter wins | `"none"` | `none` \| `nonprod` \| `all`; personal: listed strictest first, the stricter wins | 1.0.42 | Where a deploy may run without asking; anything else reads as `none`. |
| `autopilot.approval` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | 1.0.42 | Who approves a ticket under autopilot; anything else reads as `human`. `risk` and `self` also need `autopilot.mode: plan` (or `backlog`) and `scope.allowCliApproval: true` (a hand edit of the repo's `.crew/config.json`); a refused `approve` lists each unmet one, with its value as written, the file that holds it and, under `risk`, the spec risk that blocks. |
| `autopilot.questions` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | 1.0.42 | Who answers a ticket's open questions under autopilot; anything else reads as `human`. |
| `autopilot.maxAutoReplans` | repo | `0` | non-negative integer (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`) | 1.0.339 | Successor plans autopilot may start by rejecting an out-of-rounds BLOCK review itself; 0 is off, and anything but a non-negative integer reads as 0, and above 5 as 5, with a warning. |
| `autopilot.ship` | repo | `"merge"` | `pr` \| `merge` | 1.0.349 | After `/crew:done`: `pr` pushes and opens the PR; `merge` also merges it (a merge commit) once the required checks allow. Anything else reads as `pr`, with a warning. |
| `autopilot.sleep.schedule` | repo | `null` | HH:MM-HH:MM or null (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.0.332 | A nightly window, `HH:MM-HH:MM` in machine local time (may cross midnight); inside it the two sleep overrides apply. Anything else is could not tell: only a stricter override applies. |
| `autopilot.sleep.approval` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.0.332 | `autopilot.approval` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.questions` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.0.332 | `autopilot.questions` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.deploy` | repo | `null` | `null` \| `nonprod` \| `none` (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.1.21 | `autopilot.deploy` inside the sleep window (L-0654): null keeps the day value, `nonprod` or `none` replaces it; anything else, `all` included, is refused with a warning. Asleep, an effective `all` reads as `nonprod`: production never runs unattended asleep. |
| `autopilot.maxTicketsPerRun` | repo | `3` | positive integer (checked in `plugin/crew/hooks/scripts/crew_autopilot_backlog.py`) | 1.1.21 | Tickets one goal run (one session) may start; the next one stops the run. Anything but a positive integer reads as 3, with a warning. |
| `autopilot.maxTokensPerSession` | repo | `2000000` | positive integer (checked in `plugin/crew/hooks/scripts/crew_autopilot_backlog.py`) | 1.1.21 | Input plus output tokens one goal session may spend, each assistant message counted once, before the run stops; a transcript that cannot be read stops too. Anything but a positive integer reads as 2000000, with a warning. |
| `autopilot.maxLanes` | repo | `null` | positive integer or null (checked in `plugin/crew/hooks/scripts/crew_wave.py`) | 1.1.6 | Lanes one `/crew:autopilot wave` runs at once; null is the resolved `pm.maxDispatches`, a larger value is capped to it and anything but a positive integer reads as it, each with a warning. |
| `autopilot.reviewPolicy` | repo | `"stop"` | `stop` \| `clean-only` \| `fix-and-rereview` | 1.1.6 | What autopilot does with a review verdict. A wave lane: `stop` ends at the first verdict, `clean-only` takes a CLEAN round on to the done checks, `fix-and-rereview` fixes within the ledger's rounds. A single-ticket run (T-0067): only `fix-and-rereview` acts, fixing a non-final FINDINGS round's BLOCK and FIX lines itself (the `fix` phase) and re-reviewing. Anything else reads as `stop`, with a warning; no setting accepts a review. |

### `tickets`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `tickets.baseBranch` | repo | `null` | branch name or null (checked in `plugin/crew/hooks/scripts/scope_base.py`) | 1.0.158 | The branch ticket branches are cut from; null tries origin/HEAD's target, then origin/main, then main. A value that is not a branch name, or names no commit, makes the scope base could not tell. |

### `route`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `route.enabled` | both | `false` | `false` \| `true` (checked in `plugin/crew/hooks/scripts/crew_route.py`) | 1.0.42 | Route plain-text prompts to `/crew:` commands; only the JSON value `true` arms it. |

### `unattendedCloud`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `unattendedCloud.aws.readOnly.profile` | machine-only | `null` | profile name, or null (coerced in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.10 | The AWS profile an unattended run exports credentials from (`aws configure export-credentials`); it must yield temporary credentials. Machine file only. |
| `unattendedCloud.aws.readOnly.identity` | machine-only | `null` | ARN prefix ending in `/`, or null (coerced in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.10 | The assumed-role ARN prefix STS must report for that profile, ending in `/`; null refuses every launch. Machine file only. |
| `unattendedCloud.aws.readOnly.region` | machine-only | `null` | region, or null (coerced in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.10 | The AWS region the unattended run gets; null is `us-east-1`. Machine file only. |
| `unattendedCloud.aws.nonProd` | machine-only | `{}` | None (checked in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.10 | Environment name -> `{profile, identity, region}` for `launch --environment NAME`; usable only where the repo's `environments.nonProd` agrees. Machine file only. |

## Coming (not in code yet)

Keys from approved tickets that have not landed. Each moves into the table above when its ticket lands, because it is then in the code; a test fails until it does (`test_no_coming_key_is_in_code`).

### T-0030

| Setting | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `coord.ttlMinutes` | new key | set when T-0030 lands | 30 |  | Lifetime of a cross-session coordination claim (1-10080). |
| `coord.channel` | new key | set when T-0030 lands | set when T-0030 lands |  | Where sessions coordinate. |

### T-0050

| Setting | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `scope.allowCliApproval` | changes layer | both, stricter wins | false |  | Becomes settable in the global file, the stricter layer winning, once its reader (`crew_ticket.cli_approval_allowed`) reads the global layer in a harness-only follow-up to T-0050. |
