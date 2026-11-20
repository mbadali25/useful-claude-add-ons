# crew configuration blanks

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand:
`python3 scripts/check-marketplace.py` fails when this file is stale.

This folder holds two blanks, whole config files with every key at crew's
default:

- `config.blank.json`, for a repo's `.crew/config.json`;
- `global.blank.json`, for the machine file `~/.claude/crew/config.json`.

Copying a blank into a layer that has no file changes nothing crew does until
you edit a value. To keep that true, each blank leaves out the keys whose value
at the default would still change something; each one is listed, with the
reason, under "Left out of this blank". Set one of those only when you want a
value other than the one you would otherwise get.

The repo blank is not the `/crew:init` template
(`templates/config.template.json`): that one also spells the two-layer keys at
their defaults, so it holds your machine values down. `keys.json` holds the
same facts for every key, for tools. The reasons behind the rules are in
`docs/crew/config-rationale.md`; every key's full description is in `plugin/crew/CONFIG.md`.

## Repo blank: `config.blank.json`

Copy to `.crew/config.json`. 59 keys in the blank, 37 left out.

### `core`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `schema` | `8` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | 0.11.0 or earlier | Config schema version; `/crew:migrate` upgrades an older one. |
| `verifyGate` | `true` | repo | not validated - read by `hooks/scripts/verify-gate.sh` (expects boolean) | 0.11.0 or earlier | Run the Stop verify gate. |
| `humanOnly.approve` | `null` | human-only opt-out | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | 1.3.9 | The owner's opt-out of `/crew:approve` being human-only. null or `true` keeps it human-only; `false` opts out only from the machine file or an untracked repo file, only after `/crew:confirm-config` twice, and a `true` in either layer vetoes. crew 1.3.27: with an opt-out in force a cli-recorded approval counts (`crew_ticket.cli_approval_allowed`). |
| `humanOnly.promoteMarker` | `null` | human-only opt-out | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | 1.3.9 | The same opt-out for the production promote marker `.crew/.approved-<env>-<sha>`, under the same rules. crew 1.3.9: no hook acts on it yet, and no hook today checks who created the marker. |
| `worktrees.root` | `null` | both | absolute path or null (coerced in `hooks/scripts/crew_worktrees.py`) | 1.3.19 | The base directory for this repo's git worktrees, OUTSIDE the repo: they go in `<root>/<repo>-<digest>/<name>`. null is `~/.claude/crew/worktrees`; `~` is expanded, a relative path or one inside the repo is refused (never replaced by the default). It places the worktrees crew places (`/crew:emergency`, `crew_worktrees.py path`) and, once the owner registers the opt-in `WorktreeCreate` hook, the ones Claude Code creates; without the hook Claude Code keeps using `.claude/worktrees/`. |
| `promote.deadlineSeconds` | `null` | both | number of seconds, or null (coerced in `hooks/scripts/_promote_gate.py`) | 1.3.41 | How many seconds the promote gate (`promote-gate.sh`) may run, counted from the moment its shell began, before it gives up and blocks (a hook that times out is not a block, so the gate stops itself first). null derives it from the guard's hook timeout less a 4 s margin: 16 s of the 20 s row. A number above the timeout less 2 s (18 s of 20) is clamped to that, so the setting can never let the gate outlive its hook; zero, a negative, a string or a boolean reads as null. The hook timeout is the guard's row in the dispatcher's table, not a setting. |
| `verify.stopBudgetSeconds` | `60` | repo | whole number of seconds, 1 to 540, or null (coerced in `hooks/scripts/verify-gate.sh`) | 1.3.158 | How many seconds the Stop row of the verify gate (`verify-gate.sh`) may spend running rules, cheapest first, before it defers the rest to CI and names them. Default 60, which is what the gate used before the key was settable. A write must be a whole number from 1 to 540 (the Stop hook's timeout less the gate's 60 s margin); anything else is refused, never stored as a value the gate would quietly replace with 60. null removes the setting. Repo file only: what a rule costs is a fact about the checkout. `--all` and `--ci` ignore it. A hand-edited string, boolean or negative reads as 60, never as no limit (a number the writer would refuse, such as 0 or 1e9, is still taken as written). |
| `reaper.protectedRegex` | `null` | both | regular expression, or null (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | A regular expression; a process whose image name or command line matches is never ended, it REPLACES the built-in list (claude, node, MCP servers, ai-connect, psmux/tmux, tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm, Defender, ssh). null keeps the built-in list; an invalid expression reads as null. |
| `emergency.standDown` | `true` | repo | not validated - read by `hooks/scripts/_common.sh` (expects boolean) | 0.11.0 or earlier | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.maxTtlMinutes` | `480` | repo | integer (coerced in `hooks/scripts/crew_incident.py`) | 0.11.0 or earlier | Longest incident lifetime; never below `ttlMinutes`. |
| `graph.out` | `"graphify-out"` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects path) | 0.11.0 or earlier | Where the code graph is written. |
| `scope.mode` | `"off"` | repo | `off` \| `report` \| `block` \| `auto` | 1.0.25 | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | `false` | repo | `false` \| `true` (checked in `hooks/scripts/crew_ticket.py`) | 1.0.25 | Whether a CLI-written approval receipt counts; only exactly `true` allows it. `autopilot.approval: self` or `risk` needs it, and `autopilot.mode: plan` or `backlog`, to approve anything. A hand edit by the owner in the repo's `.crew/config.json` (`"scope": {"allowCliApproval": true}`); `crew_config.py --set` refuses it. |
| `tickets.baseBranch` | `null` | repo | branch name or null (checked in `hooks/scripts/scope_base.py`) | 1.0.158 | The branch ticket branches are cut from; null tries origin/HEAD's target, then origin/main, then main. A value that is not a branch name, or names no commit, makes the scope base could not tell. |

### `providers`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `qa.codex.reasoningEffort` | `null` | both | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | `null` | both | not validated - read by `commands/review.md` (expects string or null) | 0.14.6 | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | `null` | both | not validated - read by `commands/review.md` (expects string or null) | 1.0.39 | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `dev.codex.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Codex model for implementation. |
| `dev.codex.reasoningEffort` | `null` | both | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for implementation. |
| `dev.copilot.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Copilot model for implementation. |
| `dev.kimi.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 1.0.39 | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `secondOpinion.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 0.11.0 or earlier | Second-opinion model. |

### `guards`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `guards.git.allow` | `null` | both | null, `"off"`, `"all"` or a list of git subcommand names (coerced in `hooks/scripts/crew_gitallow.py`) | 1.3.125 | The owner's switch that stops crew's command guards blocking or asking on git commands: `"all"` lets a line of only plain git commands past the force-push rule and the promote gate (unless a declared deploy is itself a git command); a list of subcommands (`["commit", "push"]`) lets only those through, with every option they take (listing `push` lets `push --force` through). null or `"off"` changes nothing. Machine file only, and only after `/crew:confirm-config` twice (`crew_confirm_config.py propose --key guards.git.allow --value ...`); a value written any other way, or any later change to the machine file outside crew's config writer, reads as off, and a repo `"off"` or unreadable repo file vetoes it. FAIL-CLOSED ALLOWLIST: a line is exempt only when it is ONE command, exactly `git` with plain literal words (no `$`, backtick, glob, brace, leading `~`, parenthesis, PowerShell expression or `%NAME%`; no separator, redirection, heredoc, continuation or comment, so a chain is judged as before); a git command carrying `-c`, a command to run (`rebase --exec`, `push --receive-pack`, `submodule foreach`, ...) or a `git config` write is never exempt. |

### `cloud`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `production.databases` | `[]` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | 0.19.30 | Globs naming production databases. |
| `production.hosts` | `[]` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | 0.19.30 | Globs naming production hosts. |
| `cloud.awsProfiles` | `[]` | repo | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | AWS profiles this repo may use. |
| `cloud.awsRegions` | `[]` | repo | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | AWS regions this repo may use. |
| `cloud.azureSubscriptions` | `[]` | repo | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | 1.0.25 | Azure subscriptions this repo may use. |
| `environments.nonProd` | `[]` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | 1.0.37 | Terraform targets that are not production and may run unattended. |
| `environments.workflows` | `{}` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects object of glob to string) | 1.1.16 | Deploy workflow globs, each mapped to its environment or `input:<name>`. |
| `environments.preProduction` | `{}` | repo | not validated - read by `hooks/scripts/crew_preprod.py` (expects object of exact name to {reason, targets}) | 1.3.20 | Environments labelled production that are not live yet: exact name -> `reason` (+ optional exact `targets`); judged non-production by the cloud guard, with an audit line. |

### `trackers`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `tracker` | `"files"` | repo | `files` \| `obsidian` \| `jira` \| `sdp` | 0.11.0 or earlier | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `jira.project` | `null` | repo | not validated - read by `commands/jira-sync.md` (expects string or null) | 0.11.0 or earlier | Jira project key. No consumer found (docs/crew/config-rationale.md). |
| `jira.cloudId` | `null` | repo | not validated - read by `commands/jira-sync.md` (expects string or null) | 0.19.10 | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |
| `obsidian.vaultPath` | `null` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | `null` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | 0.11.0 or earlier | Board folder inside the vault (relative, no `..`). |

### `autopilot`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `autopilot.maxAutoReplans` | `0` | repo | non-negative integer (checked in `hooks/scripts/crew_autopilot.py`) | 1.0.339 | Successor plans autopilot may start by rejecting an out-of-rounds BLOCK review itself; 0 is off, and anything but a non-negative integer reads as 0, and above 5 as 5, with a warning. |
| `autopilot.ship` | `"merge"` | repo | `pr` \| `merge` | 1.0.349 | After `/crew:done`: `pr` pushes and opens the PR; `merge` also merges it (a merge commit) once the required checks allow. Anything else reads as `pr`, with a warning. |
| `autopilot.sleep.schedule` | `null` | repo | HH:MM-HH:MM or null (checked in `hooks/scripts/crew_sleep.py`) | 1.0.332 | A nightly window, `HH:MM-HH:MM` in machine local time (may cross midnight); inside it the two sleep overrides apply. Anything else is could not tell: only a stricter override applies. |
| `autopilot.sleep.approval` | `null` | repo | `null` \| `human` \| `self` \| `risk` (checked in `hooks/scripts/crew_sleep.py`) | 1.0.332 | `autopilot.approval` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.questions` | `null` | repo | `null` \| `human` \| `self` \| `risk` (checked in `hooks/scripts/crew_sleep.py`) | 1.0.332 | `autopilot.questions` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.deploy` | `null` | repo | `null` \| `nonprod` \| `none` (checked in `hooks/scripts/crew_sleep.py`) | 1.1.21 | `autopilot.deploy` inside the sleep window (L-0654): null keeps the day value, `nonprod` or `none` replaces it; anything else, `all` included, is refused with a warning. Asleep, an effective `all` reads as `nonprod`: production never runs unattended asleep. |
| `autopilot.maxTicketsPerRun` | `3` | repo | positive integer (checked in `hooks/scripts/crew_autopilot_backlog.py`) | 1.1.21 | Tickets one goal run (one session) may start; the next one stops the run. Anything but a positive integer reads as 3, with a warning. |
| `autopilot.maxTokensPerSession` | `2000000` | repo | positive integer (checked in `hooks/scripts/crew_autopilot_backlog.py`) | 1.1.21 | Input plus output tokens one goal session may spend, each assistant message counted once, before the run stops; a transcript that cannot be read stops too. Anything but a positive integer reads as 2000000, with a warning. |
| `autopilot.maxLanes` | `null` | repo | positive integer or null (checked in `hooks/scripts/crew_wave.py`) | 1.1.6 | Lanes one `/crew:autopilot wave` runs at once; null is the resolved `pm.maxDispatches`, a larger value is capped to it and anything but a positive integer reads as it, each with a warning. |
| `autopilot.reviewPolicy` | `"stop"` | repo | `stop` \| `clean-only` \| `fix-and-rereview` | 1.1.6 | What autopilot does with a review verdict. A wave lane: `stop` ends at the first verdict, `clean-only` takes a CLEAN round on to the done checks, `fix-and-rereview` fixes within the ledger's rounds. A single-ticket run (T-0067): only `fix-and-rereview` acts, fixing a non-final FINDINGS round's BLOCK and FIX lines itself (the `fix` phase) and re-reviewing. Anything else reads as `stop`, with a warning; no setting accepts a review. |

### `context`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `context.enabled` | `true` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects boolean) | 0.11.0 or earlier | Run the context watcher. |
| `context.warnAt` | `0.4` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects number) | 0.11.0 or earlier | Fraction of the budget at which the watcher warns, wraps up and auto-clears; default 0.4 since 1.2.40 (was 0.5), an explicit value is kept. |
| `context.reserveTokens` | `0` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects integer or null) | 0.11.0 or earlier | Tokens held back from the budget; `null` means off. |
| `context.autoClear.enabled` | `null` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | 0.19.10 | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.wrapUp` | `null` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | 1.0.334 | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |
| `resume.auto` | `null` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_resume.py`) | 1.0.40 | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |

### `notify`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `notify.provider` | `null` | both | telegram, teams, none or null; any other value sends nothing (coerced in `hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.chatId` | `null` | both | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |

### `memory`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `memory.vaultPath` | `null` | both | not validated - read by `hooks/scripts/crew_recall.py` (expects path or null) | 0.11.0 or earlier | The Obsidian vault used for memory. |

### `platform`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `platform.os` | `null` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected OS, stamped by platform-sync. |
| `platform.wsl` | `null` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects boolean or null) | 0.11.0 or earlier | Detected WSL, stamped by platform-sync. |
| `platform.shell` | `null` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | `null` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | 0.11.0 or earlier | Windows host IP seen from WSL. |

### Left out of this blank

| Key | Why | Set it with |
|---|---|---|
| `qa.provider` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set qa.provider=JSON --apply --repo` |
| `qa.order` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set qa.order=JSON --apply --repo` |
| `qa.fallback` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set qa.fallback=JSON --apply --repo` |
| `qa.codex.model` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set qa.codex.model=JSON --apply --repo` |
| `qa.roles` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set qa.roles=JSON --apply --repo` |
| `dev.provider` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set dev.provider=JSON --apply --repo` |
| `dev.fallback` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set dev.fallback=JSON --apply --repo` |
| `dev.roles` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set dev.roles=JSON --apply --repo` |
| `secondOpinion.provider` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set secondOpinion.provider=JSON --apply --repo` |
| `secondOpinion.mode` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set secondOpinion.mode=JSON --apply --repo` |
| `memory.mode` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set memory.mode=JSON --apply --repo` |
| `context.autoClear.method` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set context.autoClear.method=JSON --apply --repo` |
| `context.autoClear.delaySeconds` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set context.autoClear.delaySeconds=JSON --apply --repo` |
| `context.autoClear.minHandoffLines` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set context.autoClear.minHandoffLines=JSON --apply --repo` |
| `reaper.enabled` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.enabled=JSON --apply --repo` |
| `reaper.dryRun` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.dryRun=JSON --apply --repo` |
| `reaper.spinCpuPct` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.spinCpuPct=JSON --apply --repo` |
| `reaper.spinMinAgeMin` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.spinMinAgeMin=JSON --apply --repo` |
| `reaper.blockedMinAgeHours` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.blockedMinAgeHours=JSON --apply --repo` |
| `reaper.intervalMin` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.intervalMin=JSON --apply --repo` |
| `reaper.onSessionStart` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set reaper.onSessionStart=JSON --apply --repo` |
| `notify.events` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set notify.events=JSON --apply --repo` |
| `pm.authority` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set pm.authority=JSON --apply --repo` |
| `pm.maxDispatches` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set pm.maxDispatches=JSON --apply --repo` |
| `install.policy` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set install.policy=JSON --apply --repo` |
| `guards.profile` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set guards.profile=JSON --apply --repo` |
| `guards.overrides` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set guards.overrides=JSON --apply --repo` |
| `environments.prodUnattended` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set environments.prodUnattended=JSON --apply --repo` |
| `tiers` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set tiers=JSON --apply --repo` |
| `change.requireForProduction` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set change.requireForProduction=JSON --apply --repo` |
| `git.forbiddenTrailers` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set git.forbiddenTrailers=JSON --apply --repo` |
| `autopilot.mode` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.mode=JSON --apply --repo` |
| `autopilot.maxPhases` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.maxPhases=JSON --apply --repo` |
| `autopilot.deploy` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.deploy=JSON --apply --repo` |
| `autopilot.approval` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.approval=JSON --apply --repo` |
| `autopilot.questions` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.questions=JSON --apply --repo` |
| `route.enabled` | a repo value, even at the default, overrides or narrows the machine file's value; set it in the repo file only to differ from your machine | `crew_config.py --set route.enabled=JSON --apply --repo` |

## Machine blank: `global.blank.json`

Copy to `~/.claude/crew/config.json`. 59 keys in the blank, 5 left out.

### `core`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `pm.authority` | `"report-only"` | both, widening warned | `report-only` \| `act` \| `autonomous` | 0.11.0 or earlier | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.maxDispatches` | `3` | both | integer (coerced in `hooks/scripts/crew_state.py`) | 0.11.0 or earlier | Roles the PM may dispatch in one pass. |
| `humanOnly.approve` | `null` | human-only opt-out | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | 1.3.9 | The owner's opt-out of `/crew:approve` being human-only. null or `true` keeps it human-only; `false` opts out only from the machine file or an untracked repo file, only after `/crew:confirm-config` twice, and a `true` in either layer vetoes. crew 1.3.27: with an opt-out in force a cli-recorded approval counts (`crew_ticket.cli_approval_allowed`). |
| `humanOnly.promoteMarker` | `null` | human-only opt-out | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | 1.3.9 | The same opt-out for the production promote marker `.crew/.approved-<env>-<sha>`, under the same rules. crew 1.3.9: no hook acts on it yet, and no hook today checks who created the marker. |
| `worktrees.root` | `null` | both | absolute path or null (coerced in `hooks/scripts/crew_worktrees.py`) | 1.3.19 | The base directory for this repo's git worktrees, OUTSIDE the repo: they go in `<root>/<repo>-<digest>/<name>`. null is `~/.claude/crew/worktrees`; `~` is expanded, a relative path or one inside the repo is refused (never replaced by the default). It places the worktrees crew places (`/crew:emergency`, `crew_worktrees.py path`) and, once the owner registers the opt-in `WorktreeCreate` hook, the ones Claude Code creates; without the hook Claude Code keeps using `.claude/worktrees/`. |
| `promote.deadlineSeconds` | `null` | both | number of seconds, or null (coerced in `hooks/scripts/_promote_gate.py`) | 1.3.41 | How many seconds the promote gate (`promote-gate.sh`) may run, counted from the moment its shell began, before it gives up and blocks (a hook that times out is not a block, so the gate stops itself first). null derives it from the guard's hook timeout less a 4 s margin: 16 s of the 20 s row. A number above the timeout less 2 s (18 s of 20) is clamped to that, so the setting can never let the gate outlive its hook; zero, a negative, a string or a boolean reads as null. The hook timeout is the guard's row in the dispatcher's table, not a setting. |
| `reaper.enabled` | `false` | both | boolean (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | Whether scheduled and session-start passes of the orphan reaper (`crew_reaper.py --scheduled`) do anything. false by default; a manual `crew_reaper.py` run always works and is a dry run unless given `--apply`. Read from the machine file only: a repo value is ignored, because the reaper ends processes on this machine. |
| `reaper.dryRun` | `true` | both | boolean (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | When true (the default) a scheduled or session-start pass only logs what it would end to `~/.claude/crew/reaper.log`; set false to let it end processes. Only a scheduled pass reads it; a manual run ends processes only with `--apply`. |
| `reaper.spinCpuPct` | `50` | both | percent of one core (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | An orphan is SPINNING when it used at least this percentage of one core over the reaper's short sample (5 s) and is older than `spinMinAgeMin`. A number above 0; anything else reads as 50. |
| `reaper.spinMinAgeMin` | `15` | both | number of minutes (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | Minutes an orphan must be running before the spinning rule (and the self-matching `until pgrep -f` watcher rule) may end it. A number above 0; anything else reads as 15. |
| `reaper.blockedMinAgeHours` | `2` | both | number of hours (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | Hours an orphan using under 1% of a core must be running before it counts as BLOCKED and may be ended. A number above 0; anything else reads as 2. |
| `reaper.protectedRegex` | `null` | both | regular expression, or null (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | A regular expression; a process whose image name or command line matches is never ended, it REPLACES the built-in list (claude, node, MCP servers, ai-connect, psmux/tmux, tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm, Defender, ssh). null keeps the built-in list; an invalid expression reads as null. |
| `reaper.intervalMin` | `10` | both | whole number of minutes (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | Minutes between runs of the scheduled task `crew_reaper.py --install-task` creates, and the least gap between two session-start passes. A whole number from 1; anything else reads as 10. The task is never installed by default. |
| `reaper.onSessionStart` | `false` | both | boolean (coerced in `hooks/scripts/crew_reaper.py`) | 1.3.50 | When true and `reaper.enabled` is true, the SessionStart context hook starts one detached reaper pass (at most one per `intervalMin`) and does not wait for it. false by default. |
| `install.policy` | `"manual"` | both, ratchet | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | 0.19.18 | Whether crew may install a missing prerequisite. |
| `change.requireForProduction` | `false` | both, ratchet | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | 0.19.31 | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |
| `git.forbiddenTrailers` | `[]` | both | list of trailer tokens (letters, digits and `-`, no `:`) (checked in `hooks/scripts/crew_trailers.py`) | 1.0.328 | Commit trailer tokens the owner forbids, reported by `/crew:done`. The two layers combine by union, so a repo can add a token and never remove the machine owner's; a value that is not a list of tokens makes the list unknown, never empty (docs/crew/config-rationale.md). |
| `route.enabled` | `false` | both | `false` \| `true` (checked in `hooks/scripts/crew_route.py`) | 1.0.42 | Route plain-text prompts to `/crew:` commands; only the JSON value `true` arms it. |

### `providers`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `qa.provider` | `"auto"` | both | `auto` \| `claude` \| `codex` \| `copilot` \| `kimi` | 0.11.0 or earlier | Who reviews: `auto` walks `qa.order`; a named provider is used as-is. |
| `qa.order` | `["codex", "kimi", "copilot", "claude"]` | both | list of: `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | The reviewers `auto` tries, in order. A list is one leaf, replaced wholesale. |
| `qa.fallback` | `"claude-sonnet-5"` | both | not validated - read by `commands/review.md` (expects model id) | 0.16.6 | Model a gone pin falls back to, on its family's provider (L-0712). |
| `qa.codex.model` | `"gpt-6.2-sol"` | both | not validated - read by `commands/review.md` (expects string or null) | 0.14.6 | Codex model for review; defaults to `gpt-6.2-sol` (1.3.166), null passes no flag. |
| `qa.codex.reasoningEffort` | `null` | both | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | `null` | both | not validated - read by `commands/review.md` (expects string or null) | 0.14.6 | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | `null` | both | not validated - read by `commands/review.md` (expects string or null) | 1.0.39 | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `qa.roles` | `{}` | both | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | 0.16.6 | Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a pin beats the provider block for that role. |
| `dev.provider` | `"claude"` | both | `claude` \| `codex` \| `copilot` \| `kimi` | 0.14.6 | Who implements. |
| `dev.fallback` | `"claude-sonnet-5"` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects model id) | 0.16.6 | Model a gone dev pin falls back to, on its family's provider. |
| `dev.codex.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Codex model for implementation. |
| `dev.codex.reasoningEffort` | `null` | both | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | 0.14.6 | Codex reasoning effort for implementation. |
| `dev.copilot.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 0.14.6 | Copilot model for implementation. |
| `dev.kimi.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 1.0.39 | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | `{}` | both | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | 0.16.6 | Per-role dev pins, as `qa.roles`. |
| `secondOpinion.provider` | `"none"` | both | not validated - read by `commands/plan.md` (expects string) | 0.11.0 or earlier | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | `"cli"` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string) | 0.11.0 or earlier | How the second opinion is reached. |
| `secondOpinion.model` | `null` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | 0.11.0 or earlier | Second-opinion model. |

### `guards`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `guards.profile` | `"off"` | both, ratchet | `off` \| `standard` \| `strict` \| `balanced` | 1.2.62 | One word for the twelve guards: `off` (today's defaults), `standard`, `strict` or `balanced` (`standard` with `terraformApply` and `deployWorkflow` at `tiered`: the machine tier map decides). Expands per layer; each guard's ratchet then runs on the expanded values. |
| `guards.overrides` | `{}` | both, ratchet | object of guard name to tier (checked in `hooks/scripts/crew_guards.py`) | 1.2.62 | `guards.overrides.<guard>`: one guard's tier, replacing the profile's value for it. Each entry is checked against that guard's own tiers; a bad one reads as the floor. |
| `guards.git.allow` | `null` | both | null, `"off"`, `"all"` or a list of git subcommand names (coerced in `hooks/scripts/crew_gitallow.py`) | 1.3.125 | The owner's switch that stops crew's command guards blocking or asking on git commands: `"all"` lets a line of only plain git commands past the force-push rule and the promote gate (unless a declared deploy is itself a git command); a list of subcommands (`["commit", "push"]`) lets only those through, with every option they take (listing `push` lets `push --force` through). null or `"off"` changes nothing. Machine file only, and only after `/crew:confirm-config` twice (`crew_confirm_config.py propose --key guards.git.allow --value ...`); a value written any other way, or any later change to the machine file outside crew's config writer, reads as off, and a repo `"off"` or unreadable repo file vetoes it. FAIL-CLOSED ALLOWLIST: a line is exempt only when it is ONE command, exactly `git` with plain literal words (no `$`, backtick, glob, brace, leading `~`, parenthesis, PowerShell expression or `%NAME%`; no separator, redirection, heredoc, continuation or comment, so a chain is judged as before); a git command carrying `-c`, a command to run (`rebase --exec`, `push --receive-pack`, `submodule foreach`, ...) or a `git config` write is never exempt. |

### `cloud`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `environments.prodUnattended` | `false` | both, ratchet | `false` \| `true` (ratchet: narrower layer wins; listed narrowest first) | 1.0.37 | Whether production terraform may run unattended; `true` only when both layers say so. |
| `tiers` | `{}` | both, ratchet | object of `<kind>:<name>` to {tier} (checked in `hooks/scripts/crew_tiers.py`) | 1.3.190 | Machine-owned tier per target (`<kind>:<name>` -> `{"tier": "dev"\|"qa"\|"prod"}`); dev < qa < prod < unknown, an unlisted target is `unknown`, and a repo entry may only narrow. Written whole (`--set tiers=<map>`). Read through `crew_tiers` only, never the merged value; report-only until R-01. |
| `unattendedCloud.aws.readOnly.profile` | `null` | machine-only | profile name, or null (coerced in `hooks/scripts/crew_unattended.py`) | 1.1.10 | The AWS profile an unattended run exports credentials from (`aws configure export-credentials`); it must yield temporary credentials. Machine file only. |
| `unattendedCloud.aws.readOnly.identity` | `null` | machine-only | ARN prefix ending in `/`, or null (coerced in `hooks/scripts/crew_unattended.py`) | 1.1.10 | The assumed-role ARN prefix STS must report for that profile, ending in `/`; null refuses every launch. Machine file only. |
| `unattendedCloud.aws.readOnly.region` | `null` | machine-only | region, or null (coerced in `hooks/scripts/crew_unattended.py`) | 1.1.10 | The AWS region the unattended run gets; null is `us-east-1`. Machine file only. |
| `unattendedCloud.aws.nonProd` | `{}` | machine-only | object: environment name -> {profile, identity, region?} (checked in `hooks/scripts/crew_unattended.py`) | 1.1.10 | Environment name -> `{profile, identity, region?}` (region optional, default `us-east-1`) for `launch --environment NAME`; usable only where the repo's `environments.nonProd` agrees. Machine file only. |

### `context`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `context.autoClear.enabled` | `null` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | 0.19.10 | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.method` | `"auto"` | both | `auto` \| `none` \| `notify` \| `tmux` \| `xdotool` \| `wtype`; per OS: linux: auto, none, notify, tmux, xdotool, wtype; macos: auto, none, notify, tmux; windows: auto, none, notify; windows-bash: auto, none, notify, tmux | 0.19.10 | How `/clear` is typed. `auto` picks per platform; a method this OS lacks stands auto-clear down. |
| `context.autoClear.delaySeconds` | `3` | both | number (coerced in `hooks/scripts/crew_autocycle.py`) | 0.19.10 | Delay before typing; an unusable value warns and reads as 3. |
| `context.autoClear.minHandoffLines` | `5` | both | number (coerced in `hooks/scripts/crew_autocycle.py`) | 0.19.10 | Shortest handoff that may be cleared after; a non-number reads as 5. |
| `context.autoClear.onlyRepos` | `null` | machine-only | list of absolute repo paths, or null (coerced in `hooks/scripts/crew_autocycle.py`) | 1.0.25 | Narrowing only, machine file only: null narrows nothing, a list arms only those repos, `[]` or a non-list arms nothing. |
| `context.autoClear.onlySessions` | `null` | machine-only | list of session ids, or null (coerced in `hooks/scripts/crew_autocycle.py`) | 1.0.25 | As `onlyRepos`, for session ids; with both set, both must match. |
| `context.autoClear.wrapUp` | `null` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | 1.0.334 | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |
| `resume.auto` | `null` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_resume.py`) | 1.0.40 | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |

### `notify`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `notify.provider` | `null` | both | telegram, teams, none or null; any other value sends nothing (coerced in `hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.tokenEnv` | `null` | machine-only | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Name of the environment variable holding the Telegram bot token; null may be filled from the notify skill's `bot_token_env`. Honoured from the machine file only. |
| `notify.chatId` | `null` | both | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | 0.11.0 or earlier | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |
| `notify.events` | `["blocker", "deploy", "question"]` | both | list of event names; an unknown name is dropped with a notice (coerced in `hooks/scripts/crew_notify.py`) | 0.11.0 or earlier | Events that notify: `deploy`, `question`, and `blocker` (T-0060's four blocker reasons). The pre-1.0 names `gate`, `waiting`, `phase`, `review` and `done` are mapped with a notice. A list is one leaf. |

### `memory`

| Key | Blank value | Layer | Allowed values | Since | What it does |
|---|---|---|---|---|---|
| `memory.mode` | `"repo"` | both | not validated - read by `skills/crew-memory/SKILL.md` (expects string) | 0.11.0 or earlier | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | `null` | both | not validated - read by `hooks/scripts/crew_recall.py` (expects path or null) | 0.11.0 or earlier | The Obsidian vault used for memory. |

### Left out of this blank

| Key | Why | Set it with |
|---|---|---|
| `autopilot.mode` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.mode=JSON --apply --global` |
| `autopilot.maxPhases` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.maxPhases=JSON --apply --global` |
| `autopilot.deploy` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.deploy=JSON --apply --global` |
| `autopilot.approval` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.approval=JSON --apply --global` |
| `autopilot.questions` | a personal key: at its default it holds your machine value down (stricter wins) | `crew_config.py --set autopilot.questions=JSON --apply --global` |
