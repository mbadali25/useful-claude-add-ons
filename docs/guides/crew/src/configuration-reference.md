# crew 1.0 - configuration reference

This document has two parts. The first is short and hand-written: how crew's two
config files combine, how to see what is in force, and the common setups. The
second is generated from the code and lists every key.

## How the two files combine

crew reads two JSON files:

- `~/.claude/crew/config.json` - the **machine-global** file. Your personal
  defaults for every repo on this machine: providers and models, notifications,
  auto-clear, the guards.
- `.crew/config.json` - the **repo** file. Facts about one checkout: the
  tracker, the board, scope enforcement, autopilot, production declarations.

The repo file wins over the machine file, which wins over crew's defaults. Three
exceptions, each named in the Layer column below:

- A **repo-only** key in the machine file takes effect nowhere. It is pruned on
  read and refused on write.
- A **ratcheted** key (`install.policy`, every `guards.*`,
  `change.requireForProduction`, `environments.prodUnattended`) resolves to
  the narrower of the two values, so a cloned repo cannot widen what your
  machine allows.
- A **machine-armed** key (`resume.auto`, `context.autoClear.enabled`) can be
  turned on only in the machine file. A repo can only switch it off.

A `null` in the repo file over a machine value inherits the machine value. The
`/crew:init` template writes every key, which would otherwise shadow your
machine defaults.

## Seeing what is in force

- `/crew:config --show` prints every machine-settable key, its value and the
  layer it came from, and names any key that takes effect nowhere.
- `/crew:config` with no argument is a menu that writes either file through the
  validated path. It shows a dry run first, refuses unknown keys and
  out-of-range values, and marks a widening with `!`.
- From a shell:
  `python3 plugin/crew/hooks/scripts/crew_config.py --explain` is the same
  table, and `--models` is the per-role provider table.

## Common setups

- **Personal defaults once, for every repo.** Put providers, models,
  `notify.*` and the guards in `~/.claude/crew/config.json`. Leave repo files
  to repo facts.
- **Self-approval under autopilot.** In the repo file, set
  `scope.allowCliApproval: true` and `autopilot.mode: "plan"`, then choose
  `autopilot.approval` (`human`, `self` or `risk`). Review acceptance and
  production deploys still stop for you.
- **Notifications.** In the machine file, set `notify.provider` and the
  environment variable names in `notify.urlEnv` / `notify.tokenEnv`. The
  secret stays in your environment, never in the file.

The reasoning behind each key is in `plugin/crew/CONFIG.md`, which ships with
the plugin.

## Reference (generated)

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand:
`python3 scripts/check-marketplace.py` fails when this file is stale.

**129 keys**: 72 settable in the machine-global file, 57 repo-only.

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
- **machine-arms**: only the global file can turn it on (exactly `true`); a repo may only veto it with `false` (`crew_config.REPO_VETO_ONLY`).
- **machine-only**: read from the global file alone; a repo's own value is never consulted.

### Top-level keys

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `schema` | repo | `7` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.11.0 or earlier | Config schema version; `/crew:upgrade` migrates an older one. |
| `tier` | repo | `0` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.11.0 or earlier | Setup tier recorded by `/crew:init`. |
| `roles` | repo | `["explorer", "reviewer"]` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects list of role names) | 0.11.0 or earlier | Optional roles installed in this repo. |
| `tracker` | repo | `"files"` | `files` \| `obsidian` \| `jira` \| `sdp` | 0.11.0 or earlier | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `verifyGate` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/verify-gate.sh` (expects boolean) | 0.11.0 or earlier | Run the Stop verify gate. |

### `qa`

| Key | Layer | Default | Values | Since | Summary |
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

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `dev.provider` | both | `"claude"` | `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | Who implements. |
| `dev.fallback` | both | `"claude-sonnet-5"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects model id) | 0.16.6 | Claude model used when the dev provider is unavailable. |
| `dev.codex.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Codex model for implementation. |
| `dev.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `plugin/crew/commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for implementation. |
| `dev.copilot.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Copilot model for implementation. |
| `dev.kimi.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 1.0.39 | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `plugin/crew/hooks/scripts/crew_config.py`) | 0.16.6 | Per-role dev pins, as `qa.roles`. |

### `worktree`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `worktree.root` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects path or null) | 0.16.27 | Where crew creates linked worktrees; null uses the default. |

### `secondOpinion`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `secondOpinion.provider` | both | `"none"` | not validated - read by `plugin/crew/commands/plan.md` (expects string) | 0.11.0 or earlier | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | both | `"cli"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string) | 0.11.0 or earlier | How the second opinion is reached. |
| `secondOpinion.model` | both | `null` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string or null) | 0.11.0 or earlier | Second-opinion model. |
| `secondOpinion.keyEnv` | both | `"GEMINI_API_KEY"` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects string) | 0.11.0 or earlier | Environment variable holding the provider's API key. |
| `secondOpinion.sendsCode` | both | `false` | not validated - read by `plugin/crew/skills/crew-providers/SKILL.md` (expects boolean) | 0.11.0 or earlier | Whether code may be sent to the second-opinion provider. |

### `jira`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `jira.project` | repo | `null` | not validated - read by `plugin/crew/commands/jira-sync.md` (expects string or null) | 0.11.0 or earlier | Jira project key. No consumer found (CONFIG.md section 9). |
| `jira.cloudId` | repo | `null` | not validated - read by `plugin/crew/commands/jira-sync.md` (expects string or null) | 0.19.10 | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |

### `sdp`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `sdp.portal` | repo | `null` | not validated - read by `plugin/crew/commands/sdp-sync.md` (expects string or null) | 0.11.0 or earlier | ServiceDesk Plus portal. |
| `sdp.noteVisibility` | repo | `"private"` | not validated - read by `plugin/crew/commands/sdp-sync.md` (expects string) | 0.11.0 or earlier | Visibility of notes crew writes to SDP. |
| `sdp.closeOnDone` | repo | `false` | not validated - read by `plugin/crew/commands/sdp-sync.md` (expects boolean) | 0.11.0 or earlier | Close the SDP request when the ticket is done. |

### `obsidian`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `obsidian.vaultPath` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Board folder inside the vault (relative, no `..`). |
| `obsidian.board` | repo | `"Board.md"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects file name) | 0.11.0 or earlier | Board file name. |
| `obsidian.columns.backlog` | repo | `"Backlog"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for backlog tickets. |
| `obsidian.columns.ready` | repo | `"Ready"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for ready tickets. |
| `obsidian.columns.inProgress` | repo | `"In Progress"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for tickets in progress. |
| `obsidian.columns.review` | repo | `"Review"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for tickets in review. |
| `obsidian.columns.done` | repo | `"Done"` | not validated - read by `plugin/crew/hooks/scripts/crew_tracker.py` (expects string) | 0.11.0 or earlier | Board column for done tickets. |

### `memory`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `memory.mode` | both | `"repo"` | not validated - read by `plugin/crew/skills/crew-memory/SKILL.md` (expects string) | 0.11.0 or earlier | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_recall.py` (expects path or null) | 0.11.0 or earlier | The Obsidian vault used for memory. |
| `memory.inject` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/crew_context.py` (expects boolean) | 1.0.25 | Inject the handoff and recall at session start; only an explicit `false` stops it. |
| `memory.recall.vaults` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_recall.py` (expects list of vault names) | 1.0.25 | This repo's vault priority for recall; empty uses the obsidian config's roles. |
| `memory.recall.maxChars` | repo | `800` | positive integer (coerced in `plugin/crew/hooks/scripts/crew_recall.py`) | 1.0.25 | Recall output budget; a non-positive or non-integer value reads as 800. |

### `context`

| Key | Layer | Default | Values | Since | Summary |
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
| `context.autoWrapUp` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/context-watch.sh` (expects boolean) | 0.19.10 | Ask for a wrap-up when the budget runs low. |
| `context.autoResume` | repo | `true` | not validated - read by `plugin/crew/commands/migrate.md` (expects boolean) | 0.19.10 | Retired: read by nothing since 1.0.0; kept so `/crew:migrate` carries it. |
| `context.staleHandoff.maxAgeHours` | repo | `72` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.16.33 | A handoff older than this is archived. |
| `context.staleHandoff.maxCommitsBehind` | repo | `3` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects integer) | 0.16.33 | A handoff this many commits behind is archived. |

### `resume`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `resume.auto` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `plugin/crew/hooks/scripts/crew_resume.py`) | 1.0.40 | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |

### `emergency`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `emergency.standDown` | repo | `true` | not validated - read by `plugin/crew/hooks/scripts/_common.sh` (expects boolean) | 0.11.0 or earlier | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.ttlMinutes` | repo | `120` | integer (coerced in `plugin/crew/hooks/scripts/crew_incident.py`) | 0.11.0 or earlier | Default incident lifetime; a non-integer reads as the default. |
| `emergency.maxTtlMinutes` | repo | `480` | integer (coerced in `plugin/crew/hooks/scripts/crew_incident.py`) | 0.11.0 or earlier | Longest incident lifetime; never below `ttlMinutes`. |

### `notify`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `notify.provider` | both | `"none"` | not validated - read by `plugin/crew/hooks/scripts/notify.sh` (expects string) | 0.11.0 or earlier | Where notifications go; `none` is off. |
| `notify.urlEnv` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/notify.sh` (expects string or null) | 0.11.0 or earlier | Environment variable holding the webhook URL. |
| `notify.tokenEnv` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/notify.sh` (expects string or null) | 0.11.0 or earlier | Environment variable holding the token. |
| `notify.chatId` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/notify.sh` (expects string or null) | 0.11.0 or earlier | Chat id for chat providers. |
| `notify.events` | both | `["phase", "gate", "waiting"]` | not validated - read by `plugin/crew/hooks/scripts/notify.sh` (expects list of event names) | 0.11.0 or earlier | Events that notify. A list is one leaf. |

### `platform`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `platform.os` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected OS, stamped by platform-sync. |
| `platform.wsl` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects boolean or null) | 0.11.0 or earlier | Detected WSL, stamped by platform-sync. |
| `platform.shell` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | repo | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Windows host IP seen from WSL. |

### `shellRoute`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `shellRoute.mode` | both | `null` (repo), `"auto"` (machine) | `auto` \| `wsl` \| `powershell` \| `gitbash` | 1.0.54 | The shell long-running jobs use on native Windows; null inherits, and an unknown value reads as `auto` and is named. |
| `shellRoute.distro` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_shell.py` (expects string or null) | 1.0.54 | WSL distro to route to; null takes the default distro. |

### `pm`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `pm.enabled` | both | `true` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects boolean) | 0.11.0 or earlier | Run the PM brief. |
| `pm.mode` | both | `"adaptive"` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects string) | 0.11.0 or earlier | How the PM brief adapts its length. |
| `pm.quietLines` | both | `8` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | PM brief length when nothing changed. |
| `pm.maxLines` | both | `40` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | Longest PM brief. |
| `pm.authority` | both, widening warned | `"report-only"` | `report-only` \| `act` \| `autonomous` | 0.11.0 or earlier | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.ticketGranularity` | both | `"system"` | `session` \| `system` \| `change` | 0.16.34 | How big a ticket the PM cuts. |
| `pm.maxDispatches` | both | `3` | integer (coerced in `plugin/crew/hooks/scripts/crew_state.py`) | 0.11.0 or earlier | Roles the PM may dispatch in one pass. |

### `graph`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `graph.enabled` | repo | `true` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects boolean) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |
| `graph.tool` | repo | `"graphify"` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects string) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |
| `graph.out` | repo | `"graphify-out"` | not validated - read by `plugin/crew/hooks/scripts/crew_state.py` (expects path) | 0.11.0 or earlier | Where the code graph is written. |
| `graph.mode` | repo | `"code-only"` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects string) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |
| `graph.commitHook` | repo | `false` | not validated - read by `plugin/crew/skills/crew-graph/SKILL.md` (expects boolean) | 0.11.0 or earlier | No consumer found (CONFIG.md section 9). |

### `docs`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `docs.theme` | both | `null` | not validated - read by `plugin/crew/skills/crew-house-style/SKILL.md` (expects string or null) | 0.16.33 | House-style theme for built documents; null uses the skill's own choice. |
| `docs.reportTheme` | both | `null` | not validated - read by `plugin/crew/skills/crew-house-style/SKILL.md` (expects string or null) | 0.16.33 | Theme for findings reports. |

### `bitbucket`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `bitbucket.mergeGate.enabled` | both | `false` | not validated - read by `plugin/crew/commands/promote.md` (expects boolean) | 0.16.33 | Let `/crew:promote` drive the Bitbucket merge gate. |
| `bitbucket.mergeGate.branch` | both | `null` | not validated - read by `plugin/crew/commands/promote.md` (expects string or null) | 0.16.33 | Branch the Bitbucket merge gate protects. |
| `bitbucket.mergeGate.preset` | both | `"standard"` | not validated - read by `plugin/crew/commands/promote.md` (expects string) | 0.16.33 | Selects nothing today (CONFIG.md section 9). |

### `github`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `github.mergeGate.enabled` | both | `false` | not validated - read by `plugin/crew/commands/promote.md` (expects boolean) | 0.19.30 | Let `/crew:promote` drive the GitHub merge gate. |
| `github.mergeGate.branch` | both | `null` | not validated - read by `plugin/crew/commands/promote.md` (expects string or null) | 0.19.30 | Branch the GitHub merge gate protects. |

### `install`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `install.policy` | both, ratchet | `"manual"` | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | 0.19.18 | Whether crew may install a missing prerequisite. |

### `guards`

| Key | Layer | Default | Values | Since | Summary |
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

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `production.databases` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects list of globs) | 0.19.30 | Globs naming production databases. |
| `production.hosts` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects list of globs) | 0.19.30 | Globs naming production hosts. |

### `cloud`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `cloud.awsProfiles` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | AWS profiles this repo may use. |
| `cloud.awsRegions` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | AWS regions this repo may use. |
| `cloud.azureSubscriptions` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | Azure subscriptions this repo may use. |

### `environments`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `environments.nonProd` | repo | `[]` | not validated - read by `plugin/crew/hooks/scripts/crew_config.py` (expects list of globs) | 1.0.37 | Terraform targets that are not production and may run unattended. |
| `environments.prodUnattended` | both, ratchet | `false` | `false` \| `true` (ratchet: narrower layer wins; listed narrowest first) | 1.0.37 | Whether production terraform may run unattended; `true` only when both layers say so. |

### `change`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `change.requester` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string or null) | 0.19.31 | Who requests the change. |
| `change.implementor` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string or null) | 0.19.31 | Who implements the change. |
| `change.requireForProduction` | both, ratchet | `false` | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | 0.19.31 | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |
| `change.sdpTemplate` | both | `"Change Management Request"` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string) | 0.19.31 | SDP template for a change request. |
| `change.jiraIssueType` | both | `"Change"` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string) | 0.19.31 | Jira issue type for a change request. |
| `change.category` | both | `null` | not validated - read by `plugin/crew/hooks/scripts/crew_change.py` (expects string or null) | 0.19.31 | Change category. |

### `scope`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `scope.mode` | repo | `"off"` | `off` \| `report` \| `block` \| `auto` | 1.0.25 | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | repo | `false` | `false` \| `true` (checked in `plugin/crew/hooks/scripts/crew_ticket.py`) | 1.0.25 | Whether a CLI-written approval receipt counts; only exactly `true` allows it. |

### `autopilot`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `autopilot.mode` | repo | `"off"` | `off` \| `plan` (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`) | 1.0.41 | Only the exact string `plan` arms `/crew:autopilot`; anything else reads as off, with a warning. |
| `autopilot.maxPhases` | repo | `12` | positive integer (checked in `plugin/crew/hooks/scripts/crew_autopilot.py`) | 1.0.41 | Phases one run may take; anything but a positive integer reads as 12, with a warning. |
| `autopilot.deploy` | repo | `"none"` | `none` \| `nonprod` \| `all` | 1.0.42 | Where a deploy may run without asking; anything else reads as `none`. |
| `autopilot.approval` | repo | `"risk"` | `human` \| `self` \| `risk` | 1.0.42 | Who approves a ticket under autopilot; anything else reads as `human`. |
| `autopilot.questions` | repo | `"risk"` | `human` \| `self` \| `risk` | 1.0.42 | Who answers a ticket's open questions under autopilot; anything else reads as `human`. |

### `route`

| Key | Layer | Default | Values | Since | Summary |
|---|---|---|---|---|---|
| `route.enabled` | both | `false` | `false` \| `true` (checked in `plugin/crew/hooks/scripts/crew_route.py`) | 1.0.42 | Route plain-text prompts to `/crew:` commands; only the JSON value `true` arms it. |

## Coming (not in code yet)

Keys from approved tickets that have not landed. Each moves into the table above when its ticket lands, because it is then in the code; a test fails until it does (`test_no_coming_key_is_in_code`).

### T-0009

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `guards.deployWorkflow` | new key | both, ratchet | block |  | Whether crew may dispatch a deploy workflow. |
| `environments.workflows` | new key | repo | {} |  | Deploy workflows per environment. |

### T-0011

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `autopilot.ship` | new key | repo | merge | `pr` \| `merge` | After `/crew:done`, open a PR (`pr`) or also merge it once required checks are green (`merge`). |
| `autopilot.knownFailures` | new key | repo | [] |  | Required checks that may fail without blocking a merge, matched by exact name. |
| `autopilot.ciTimeoutMinutes` | new key | repo | 60 |  | How long ship waits for CI; still pending at the timeout stops. |

### T-0012

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `autopilot.maxTicketsPerRun` | new key | repo | 3 |  | Tickets one goal run may work before it stops. |
| `autopilot.maxTokensPerSession` | new key | repo | 2000000 |  | Token cap for one goal session. |
| `autopilot.mode` | changes values | repo | off | `off` \| `plan` \| `backlog` | Adds `backlog`: work a goal's tickets one at a time. |

### T-0013

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `resume.typeDelaySeconds` | new key | machine | measured by T-0013 |  | Delay before typing the resume command where no ready-probe exists. |
| `resume.readyTimeoutSeconds` | new key | machine | 15 |  | How long the ready-probe waits before giving up. |

### T-0017

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `context.autoClear.wrapUp` | new key | machine-arms | null |  | Machine opt-in for the automatic wrap-up; only exactly `true` arms it. |

### T-0029

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `autopilot.maxLanes` | new key | repo | the resolved pm.maxDispatches |  | Parallel lanes one autopilot wave may run; may only lower the limit. |
| `autopilot.reviewPolicy` | new key | repo | stop | `stop` \| `clean-only` \| `fix-and-rereview` | What a lane does with review findings. |

### T-0030

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `coord.ttlMinutes` | new key | set when T-0030 lands | 30 |  | Lifetime of a cross-session coordination claim (1-10080). |
| `coord.channel` | new key | set when T-0030 lands | set when T-0030 lands |  | Where sessions coordinate. |

### T-0050

| Key | Change | Layer | Default | Values | Summary |
|---|---|---|---|---|---|
| `autopilot.mode` | changes layer | both, stricter wins | off |  | The personal autopilot keys become settable in the global file; the stricter layer wins. |
| `scope.allowCliApproval` | changes layer | both, stricter wins | false |  | Becomes settable in the global file; the stricter layer wins. |
