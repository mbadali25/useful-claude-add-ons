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
- A **ratcheted** key (`install.policy`, every `guards.*`,
  `change.requireForProduction`, `environments.prodUnattended`) resolves to
  the narrower of the two values, so a cloned repo cannot widen what your
  machine allows.
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
- **Notifications.** In the machine file, set `notify.provider` and the
  environment variable names in `notify.urlEnv` / `notify.tokenEnv`. The
  secret stays in your environment, never in the file. Those two are
  machine-only: a repo file's value is ignored with a notice.

The reasoning behind each key is in `plugin/crew/CONFIG.md`, which ships with
the plugin.

## Reference (generated)

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand:
`python3 scripts/check-marketplace.py` fails when this file is stale.

**149 keys**: 87 settable in the machine-global file, 62 repo-only.

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

### Top-level keys

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `schema` | repo | `7` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.11.0 or earlier | Config schema version; `/crew:migrate` upgrades an older one. |
| `tier` | repo | `0` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.11.0 or earlier | Setup tier recorded by `/crew:init`. |
| `roles` | repo | `["explorer", "reviewer"]` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects list of role names) | 0.11.0 or earlier | Optional roles installed in this repo. |
| `tracker` | repo | `"files"` | `files` \| `obsidian` \| `jira` \| `sdp` | 0.11.0 or earlier | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `verifyGate` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/verify-gate.sh` (expects boolean) | 0.11.0 or earlier | Run the Stop verify gate. |

### `qa`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `qa.provider` | both | `"auto"` | `auto` \| `claude` \| `codex` \| `copilot` \| `kimi` | 0.11.0 or earlier | Who reviews: `auto` walks `qa.order`; a named provider is used as-is. |
| `qa.order` | both | `["codex", "kimi", "copilot", "claude"]` | list of: `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | The reviewers `auto` tries, in order. A list is one leaf, replaced wholesale. |
| `qa.fallback` | both | `"claude-sonnet-5"` | not validated - read by `plugin/crew/commands/review.md` (expects model id) | 0.16.6 | Claude model used when no other reviewer is available. |
| `qa.codex.model` | both | `null` | not validated - read by `plugin/crew/commands/review.md` (expects string or null) | 0.14.6 | Codex model for review; null passes no flag. |
| `qa.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `plugin/crew/commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | both | `null` | not validated - read by `plugin/crew/commands/review.md` (expects string or null) | 0.14.6 | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | both | `null` | not validated - read by `plugin/crew/commands/review.md` (expects string or null) | 1.0.39 | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `qa.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `plugin/crew/hooks/scripts/crew_config.py`) | 0.16.6 | Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a pin beats the provider block for that role. |

### `dev`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `dev.provider` | both | `"claude"` | `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | Who implements. |
| `dev.fallback` | both | `"claude-sonnet-5"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects model id) | 0.16.6 | Claude model used when the dev provider is unavailable. |
| `dev.codex.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Codex model for implementation. |
| `dev.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `plugin/crew/commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for implementation. |
| `dev.copilot.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Copilot model for implementation. |
| `dev.kimi.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 1.0.39 | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `plugin/crew/hooks/scripts/crew_config.py`) | 0.16.6 | Per-role dev pins, as `qa.roles`. |

### `worktree`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `worktree.root` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects path or null) | 0.16.27 | Where crew creates linked worktrees; null uses the default. |

### `secondOpinion`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `secondOpinion.provider` | both | `"none"` | not validated - read by `plugin/crew/commands/plan.md` (expects string) | 0.11.0 or earlier | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | both | `"cli"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string) | 0.11.0 or earlier | How the second opinion is reached. |
| `secondOpinion.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.11.0 or earlier | Second-opinion model. |
| `secondOpinion.keyEnv` | both | `"GEMINI_API_KEY"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string) | 0.11.0 or earlier | Environment variable holding the provider's API key. |
| `secondOpinion.sendsCode` | both | `false` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects boolean) | 0.11.0 or earlier | Whether code may be sent to the second-opinion provider. |

### `jira`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `jira.project` | repo | `null` | not validated - read by `plugin/crew/commands/jira-sync.md` (expects string or null) | 0.11.0 or earlier | Jira project key. No consumer found (CONFIG.md section 9). |
| `jira.cloudId` | repo | `null` | not validated - read by `plugin/crew/commands/jira-sync.md` (expects string or null) | 0.19.10 | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |

### `sdp`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `sdp.portal` | repo | `null` | not validated - read by `plugin/crew/commands/sdp-sync.md` (expects string or null) | 0.11.0 or earlier | ServiceDesk Plus portal. |
| `sdp.noteVisibility` | repo | `"private"` | not validated - read by `plugin/crew/commands/sdp-sync.md` (expects string) | 0.11.0 or earlier | Visibility of notes crew writes to SDP. |
| `sdp.closeOnDone` | repo | `false` | not validated - read by `plugin/crew/commands/sdp-sync.md` (expects boolean) | 0.11.0 or earlier | Close the SDP request when the ticket is done. |

### `obsidian`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `obsidian.vaultPath` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Board folder inside the vault (relative, no `..`). |
| `obsidian.board` | repo | `"Board.md"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects file name) | 0.11.0 or earlier | Board file name. |
| `obsidian.columns.backlog` | repo | `"Backlog"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for backlog tickets (`direction`, `ready`, `needs-owner`). |
| `obsidian.columns.ready` | repo | `"Ready"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for ready tickets. |
| `obsidian.columns.inProgress` | repo | `"In Progress"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for tickets in progress. |
| `obsidian.columns.review` | repo | `"Review"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for tickets in review. |
| `obsidian.columns.done` | repo | `"Done"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for closed tickets (`done`, `cancelled`, `superseded`; each checked). |

### `memory`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `memory.mode` | both | `"repo"` | not validated - read by `plugin/crew/skills/crew-memory/SKILL.md` (expects string) | 0.11.0 or earlier | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_recall.py` (expects path or null) | 0.11.0 or earlier | The Obsidian vault used for memory. |
| `memory.inject` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/crew_context.py` (expects boolean) | 1.0.25 | Inject the handoff and recall at session start; only an explicit `false` stops it. |
| `memory.recall.vaults` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_recall.py` (expects list of vault names) | 1.0.25 | This repo's vault priority for recall; empty uses the obsidian config's roles. |
| `memory.recall.maxChars` | repo | `800` | positive integer (coerced in `plugin/crew/hooks/scripts/crew_recall.py`) | 1.0.25 | Recall output budget; a non-positive or non-integer value reads as 800. |

### `context`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `context.enabled` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects boolean) | 0.11.0 or earlier | Run the context watcher. |
| `context.warnAt` | repo | `0.5` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects number) | 0.11.0 or earlier | Fraction of the budget at which the watcher warns. |
| `context.budgetTokens` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects integer or null) | 0.11.0 or earlier | Context budget in tokens; null uses the model's. |
| `context.reserveTokens` | repo | `0` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects integer or null) | 0.11.0 or earlier | Tokens held back from the budget; `null` means off. |
| `context.handoffPath` | repo | `".work/HANDOFF.md"` | not validated - read by `plugin/crew/hooks/scripts/crew_autocycle.py` (expects path) | 0.11.0 or earlier | Where the handoff is written. |
| `context.keepTranscripts` | repo | `5` | not validated - read by `plugin/crew/hooks/scripts/handoff-write.sh` (expects integer) | 0.11.0 or earlier | Transcripts kept by the handoff writer. |
| `context.autoClear.enabled` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 0.19.10 | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.method` | both | `"auto"` | `auto` \| `none` \| `notify` \| `tmux` \| `xdotool` \| `wtype` \| `sendkeys`; per OS: linux: auto, none, notify, tmux, xdotool, wtype; macos: auto, none, notify, tmux; windows: auto, none, notify, sendkeys; windows-bash: auto, none, notify, tmux, sendkeys | 0.19.10 | How `/clear` is typed. `auto` picks per platform; a method this OS lacks stands auto-clear down. |
| `context.autoClear.windowTitle` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/auto-clear.ps1` (expects string or null) | 0.19.10 | Window title to match before typing. |
| `context.autoClear.command` | both | `"/clear"` | not validated - read by `plugin/crew/hooks/scripts/crew_autocycle.py` (expects string) | 0.19.10 | What is typed. |
| `context.autoClear.delaySeconds` | both | `3` | number (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 0.19.10 | Delay before typing; an unusable value warns and reads as 3. |
| `context.autoClear.minHandoffLines` | both | `5` | number (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 0.19.10 | Shortest handoff that may be cleared after; a non-number reads as 5. |
| `context.autoClear.unsafeFocus` | repo | `false` | not validated - read by `plugin/crew/hooks/scripts/auto-clear.sh` (expects boolean) | 0.19.11 | Consent to `wtype` typing into whatever has focus. No longer read: `auto-clear.sh` refuses `wtype` whatever this says. |
| `context.autoClear.onlyRepos` | machine-only | `null` | list of absolute repo paths, or null (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.25 | Narrowing only, machine file only: null narrows nothing, a list arms only those repos, `[]` or a non-list arms nothing. |
| `context.autoClear.onlySessions` | machine-only | `null` | list of session ids, or null (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.25 | As `onlyRepos`, for session ids; with both set, both must match. |
| `context.autoClear.wrapUp` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.334 | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |
| `context.autoWrapUp` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects boolean) | 0.19.10 | Ask for a wrap-up when the budget runs low. |
| `context.autoResume` | repo | `true` | not validated - read by `plugin/crew/commands/migrate.md` (expects boolean) | 0.19.10 | Retired: read by nothing since 1.0.0; kept so `/crew:migrate` carries it. |
| `context.staleHandoff.maxAgeHours` | repo | `72` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.16.33 | A handoff older than this is archived. |
| `context.staleHandoff.maxCommitsBehind` | repo | `3` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.16.33 | A handoff this many commits behind is archived. |

### `resume`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `resume.auto` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_resume.py`) | 1.0.40 | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `resume.typeDelaySeconds` | both | `2` | whole seconds; fraction cut, negative or non-number reads as the default (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.321 | Wait before auto-resume types its command: before the tmux ready probe, and the only wait on Windows. Read from the machine file only. |
| `resume.readyTimeoutSeconds` | both | `15` | whole seconds; fraction cut, negative or non-number reads as the default (coerced in `plugin/crew/hooks/scripts/crew_autocycle.py`) | 1.0.321 | How long the tmux ready probe waits for an idle, empty input line before it types nothing. Read from the machine file only. |

### `emergency`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `emergency.standDown` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/_common.sh` (expects boolean) | 0.11.0 or earlier | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.ttlMinutes` | repo | `120` | integer (coerced in `plugin/crew/hooks/scripts/crew_incident.py`) | 0.11.0 or earlier | Default incident lifetime; a non-integer reads as the default. |
| `emergency.maxTtlMinutes` | repo | `480` | integer (coerced in `plugin/crew/hooks/scripts/crew_incident.py`) | 0.11.0 or earlier | Longest incident lifetime; never below `ttlMinutes`. |

### `notify`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `notify.provider` | both | `null` | telegram, teams, none or null; any other value sends nothing (coerced in `plugin/crew/hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.urlEnv` | machine-only | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Name of the environment variable holding the Teams webhook URL. Honoured from the machine file only; a repo's is ignored with a notice. |
| `notify.tokenEnv` | machine-only | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Name of the environment variable holding the Telegram bot token; null may be filled from the notify skill's `bot_token_env`. Honoured from the machine file only. |
| `notify.chatId` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |
| `notify.events` | both | `["blocker", "deploy", "question"]` | list of event names; an unknown name is dropped with a notice (coerced in `plugin/crew/hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Events that notify: `deploy`, `question`, and `blocker` (T-0060's four blocker reasons). The pre-1.0 names `gate`, `waiting`, `phase`, `review` and `done` are mapped with a notice. A list is one leaf. |
| `notify.realertHours` | both | `6` | number of hours; negative or non-number reads as the default (coerced in `plugin/crew/hooks/scripts/crew_notify.py`) | 1.0.350 | The same event + ticket + reason is sent once per this many hours; a question pings once per waiting episode. |
| `notify.questionTypes` | both | `null` | list of notification_type strings, or null; a non-list reads as null and a non-string entry is dropped (coerced in `plugin/crew/hooks/scripts/crew_notify.py`) | 1.0.350 | The Claude Code `notification_type` values that count as a question; null uses the built-in five (`crew_notify.QUESTION_TYPES`). |

### `platform`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `platform.os` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected OS, stamped by platform-sync. |
| `platform.wsl` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects boolean or null) | 0.11.0 or earlier | Detected WSL, stamped by platform-sync. |
| `platform.shell` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Windows host IP seen from WSL. |

### `shellRoute`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `shellRoute.mode` | both | `null` (repo), `"auto"` (machine) | `auto` \| `wsl` \| `powershell` \| `gitbash` | 1.0.54 | The shell long-running jobs use on native Windows; null inherits, and an unknown value reads as `auto` and is named. |
| `shellRoute.distro` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_shell.py` (expects string or null) | 1.0.54 | WSL distro to route to; null takes the default distro. |

### `pm`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `pm.enabled` | both | `true` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects boolean) | 0.11.0 or earlier | Run the PM brief. |
| `pm.mode` | both | `"adaptive"` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects string) | 0.11.0 or earlier | How the PM brief adapts its length. |
| `pm.quietLines` | both | `8` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | PM brief length when nothing changed. |
| `pm.maxLines` | both | `40` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | Longest PM brief. |
| `pm.authority` | both, widening warned | `"report-only"` | `report-only` \| `act` \| `autonomous` | 0.11.0 or earlier | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.ticketGranularity` | both | `"system"` | `session` \| `system` \| `change` | 0.16.34 | How big a ticket the PM cuts. |
| `pm.maxDispatches` | both | `3` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | Roles the PM may dispatch in one pass. |

### `graph`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `graph.enabled` | repo | `true` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects boolean) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |
| `graph.tool` | repo | `"graphify"` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects string) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |
| `graph.out` | repo | `"graphify-out"` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects path) | 0.11.0 or earlier | Where the code graph is written. |
| `graph.mode` | repo | `"code-only"` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects string) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |
| `graph.commitHook` | repo | `false` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects boolean) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |

### `docs`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `docs.theme` | both | `null` | not validated - read by `plugin/crew/skills/crew-house-style/SKILL.md` (expects string or null) | 0.16.33 | House-style theme for built documents; null uses the skill's own choice. |
| `docs.reportTheme` | both | `null` | not validated - read by `plugin/crew/skills/crew-house-style/SKILL.md` (expects string or null) | 0.16.33 | Theme for findings reports. |

### `bitbucket`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `bitbucket.mergeGate.enabled` | both | `false` | not validated - read by `plugin/crew/commands/promote.md` (expects boolean) | 0.16.33 | Let `/crew:promote` drive the Bitbucket merge gate. |
| `bitbucket.mergeGate.branch` | both | `null` | not validated - read by `plugin/crew/commands/promote.md` (expects string or null) | 0.16.33 | Branch the Bitbucket merge gate protects. |
| `bitbucket.mergeGate.preset` | both | `"standard"` | not validated - read by `plugin/crew/commands/promote.md` (expects string) | 0.16.33 | Selects nothing today (CONFIG.md section 9). |

### `github`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `github.mergeGate.enabled` | both | `false` | not validated - read by `plugin/crew/commands/promote.md` (expects boolean) | 0.19.30 | Let `/crew:promote` drive the GitHub merge gate. |
| `github.mergeGate.branch` | both | `null` | not validated - read by `plugin/crew/commands/promote.md` (expects string or null) | 0.19.30 | Branch the GitHub merge gate protects. |

### `install`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `install.policy` | both, ratchet | `"manual"` | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | 0.19.18 | Whether crew may install a missing prerequisite. |

### `guards`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `guards.terraformApply` | both, ratchet | `"block"` | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | 0.19.30 | `terraform apply` and friends. |
| `guards.forcePush` | both, ratchet | `"block"` | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | 0.19.30 | `git push --force`. |
| `guards.adminMerge` | both, ratchet | `"block"` | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | 0.19.30 | `gh pr merge --admin`. |
| `guards.mergeGate` | both, ratchet | `"block"` | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | 0.19.30 | Taking a live repo's merge gate down (read by `/crew:gate`). |
| `guards.cloudDestructive` | both, ratchet | `"block"` | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | 1.0.25 | Destructive cloud CLI commands. |
| `guards.sqlDestructive` | both, ratchet | `"block"` | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | 1.0.25 | Destructive SQL. |
| `guards.prodDatabase` | both, ratchet | `"none"` | `none` \| `read` \| `full` (ratchet: narrower layer wins; listed narrowest first) | 0.19.30 | How much of a declared production database crew may reach. |
| `guards.prodServer` | both, ratchet | `"none"` | `none` \| `read` \| `full` (ratchet: narrower layer wins; listed narrowest first) | 0.19.30 | How much of a declared production host crew may reach. |
| `guards.roleWrites` | both, ratchet | `"off"` | `block` \| `report` \| `off` (ratchet: narrower layer wins; listed narrowest first) | 0.19.92 | Enforce each role's write scope. Default `off`; a malformed value reads as `block`. |
| `guards.cloudGuard` | both, ratchet | `"off"` | `block` \| `report` \| `off` (ratchet: narrower layer wins; listed narrowest first) | 1.0.25 | Whether the cloud guard judges commands at all. Default `off`; `report` logs only. |

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

### `change`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `change.requester` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string or null) | 0.19.31 | Who requests the change. |
| `change.implementor` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string or null) | 0.19.31 | Who implements the change. |
| `change.requireForProduction` | both, ratchet | `false` | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | 0.19.31 | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |
| `change.sdpTemplate` | both | `"Change Management Request"` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string) | 0.19.31 | SDP template for a change request. |
| `change.jiraIssueType` | both | `"Change"` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string) | 0.19.31 | Jira issue type for a change request. |
| `change.category` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string or null) | 0.19.31 | Change category. |

### `git`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `git.forbiddenTrailers` | both | `[]` | list of trailer tokens (letters, digits and `-`, no `:`) (checked in `plugin/crew/hooks/scripts/crew_trailers.py`) | 1.0.328 | Commit trailer tokens the owner forbids, reported by `/crew:done`. The two layers combine by union, so a repo can add a token and never remove the machine owner's; a value that is not a list of tokens makes the list unknown, never empty (CONFIG.md section 22). |

### `scope`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `scope.mode` | repo | `"off"` | `off` \| `report` \| `block` \| `auto` | 1.0.25 | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | repo | `false` | `false` \| `true` (checked in `plugin/crew/hooks/scripts/crew_ticket.py`) | 1.0.25 | Whether a CLI-written approval receipt counts; only exactly `true` allows it. |

### `autopilot`

| Setting | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `autopilot.mode` | both, stricter wins | `"off"` | `off` \| `plan` (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`); personal: listed strictest first, the stricter wins | 1.0.41 | Only the exact string `plan` arms `/crew:autopilot`; anything else reads as off, with a warning. |
| `autopilot.maxPhases` | both, stricter wins | `12` | positive integer (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`); personal: the smaller wins | 1.0.41 | Phases one run may take; anything but a positive integer reads as 12, with a warning. |
| `autopilot.deploy` | both, stricter wins | `"none"` | `none` \| `nonprod` \| `all`; personal: listed strictest first, the stricter wins | 1.0.42 | Where a deploy may run without asking; anything else reads as `none`. |
| `autopilot.approval` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | 1.0.42 | Who approves a ticket under autopilot; anything else reads as `human`. |
| `autopilot.questions` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | 1.0.42 | Who answers a ticket's open questions under autopilot; anything else reads as `human`. |
| `autopilot.maxAutoReplans` | repo | `0` | non-negative integer (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`) | 1.0.339 | Successor plans autopilot may start by rejecting an out-of-rounds BLOCK review itself; 0 is off, and anything but a non-negative integer reads as 0, and above 5 as 5, with a warning. |
| `autopilot.sleep.schedule` | repo | `null` | HH:MM-HH:MM or null (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.0.332 | A nightly window, `HH:MM-HH:MM` in machine local time (may cross midnight); inside it the two sleep overrides apply. Anything else is could not tell: only a stricter override applies. |
| `autopilot.sleep.approval` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.0.332 | `autopilot.approval` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.questions` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `plugin/crew/hooks/scripts/crew_sleep.py`) | 1.0.332 | `autopilot.questions` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.ship` | repo | `"merge"` | `pr` \| `merge` | 1.0.349 | After `/crew:done`: `pr` pushes and opens the PR; `merge` also merges it (a merge commit) once the required checks allow. Anything else reads as `pr`, with a warning. |
| `autopilot.knownFailures` | repo | `[]` | list of check names (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`) | 1.0.349 | Required checks whose `fail` does not block a merge, matched by exact name; anything but a list of strings reads as `[]`, with a warning. |
| `autopilot.ciTimeoutMinutes` | repo | `60` | positive integer (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`) | 1.0.349 | Minutes `ship` waits for the required checks; still pending, or green only after it, stops. Anything but a positive integer reads as 60, with a warning. |
| `autopilot.maxLanes` | repo | `null` | positive integer or null (checked in `plugin/crew/hooks/scripts/crew_wave.py`) | 1.1.6 | Lanes one `/crew:autopilot wave` runs at once; null is the resolved `pm.maxDispatches`, a larger value is capped to it and anything but a positive integer reads as it, each with a warning. |
| `autopilot.reviewPolicy` | repo | `"stop"` | `stop` \| `clean-only` \| `fix-and-rereview` | 1.1.6 | What a wave lane does with its review verdict: `stop` ends at the first verdict, `clean-only` takes a CLEAN round on to the done checks, `fix-and-rereview` fixes within the ledger's rounds. Anything else reads as `stop`, with a warning; no setting lets a lane accept a review. |

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
| `unattendedCloud.aws.readOnly.profile` | machine-only | `null` | profile name, or null (coerced in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.8 | The AWS profile an unattended run exports credentials from (`aws configure export-credentials`); it must yield temporary credentials. Machine file only. |
| `unattendedCloud.aws.readOnly.identity` | machine-only | `null` | ARN prefix ending in `/`, or null (coerced in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.8 | The assumed-role ARN prefix STS must report for that profile, ending in `/`; null refuses every launch. Machine file only. |
| `unattendedCloud.aws.readOnly.region` | machine-only | `null` | region, or null (coerced in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.8 | The AWS region the unattended run gets; null is `us-east-1`. Machine file only. |
| `unattendedCloud.aws.nonProd` | machine-only | `{}` | None (checked in `plugin/crew/hooks/scripts/crew_unattended.py`) | 1.1.8 | Environment name -> `{profile, identity, region}` for `launch --environment NAME`; usable only where the repo's `environments.nonProd` agrees. Machine file only. |

## Coming (not in code yet)

Keys from approved tickets that have not landed. Each moves into the table above when its ticket lands, because it is then in the code; a test fails until it does (`test_no_coming_key_is_in_code`).

### T-0009

| Setting | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `guards.deployWorkflow` | new key | both, ratchet | block |  | Whether crew may dispatch a deploy workflow. |
| `environments.workflows` | new key | repo | {} |  | Deploy workflows per environment. |

### T-0012

| Setting | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `autopilot.maxTicketsPerRun` | new key | repo | 3 |  | Tickets one goal run may work before it stops. |
| `autopilot.maxTokensPerSession` | new key | repo | 2000000 |  | Token cap for one goal session. |
| `autopilot.mode` | changes values | repo | off | `off` \| `plan` \| `backlog` | Adds `backlog`: work a goal's tickets one at a time. |

### T-0030

| Setting | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `coord.ttlMinutes` | new key | set when T-0030 lands | 30 |  | Lifetime of a cross-session coordination claim (1-10080). |
| `coord.channel` | new key | set when T-0030 lands | set when T-0030 lands |  | Where sessions coordinate. |

### T-0050

| Setting | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `scope.allowCliApproval` | changes layer | both, stricter wins | false |  | Becomes settable in the global file, the stricter layer winning, once its reader (`crew_ticket.cli_approval_allowed`) reads the global layer in a harness-only follow-up to T-0050. |
