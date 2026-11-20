# crew configuration key index

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand: `python3 scripts/check-marketplace.py` fails when this file is stale.

103 keys: 64 settable in the machine-global file, 39 repo-only.

One line per key below. Everything else is in `docs/configuration/` beside this file:

- `docs/configuration/reference.md`: the two layers and their exceptions, the human-only opt-out, the run approval, git commands, guard profiles, verify-gate trust, migrating and removed keys, and one table per family with each key's allowed values and arrival version.
- `docs/configuration/guide.md`: how to configure crew, with examples.
- `docs/configuration/keys.json`: the same per-key facts, for tools.
- `docs/configuration/config.blank.json` and `docs/configuration/global.blank.json`: copy-safe blanks, one per layer.
- `docs/configuration/template.annotated.md`: both blanks with each key's facts beside it.
- The reasoning behind the keys: `docs/crew/config-rationale.md`.

| Key | Layer | Default | Family | Summary |
|---|---|---|---|---|
| `schema` | repo | `8` | `core` | Config schema version; `/crew:migrate` upgrades an older one. |
| `qa.provider` | both | `"auto"` | `providers` | Who reviews: `auto` walks `qa.order`; a named provider is used as-is. |
| `qa.order` | both | `["codex", "kimi", "copilot", "claude"]` | `providers` | The reviewers `auto` tries, in order. A list is one leaf, replaced wholesale. |
| `qa.fallback` | both | `"claude-sonnet-5"` | `providers` | Model a gone pin falls back to, on its family's provider (L-0712). |
| `qa.codex.model` | both | `"gpt-6.2-sol"` | `providers` | Codex model for review; defaults to `gpt-6.2-sol` (1.3.166), null passes no flag. |
| `qa.codex.reasoningEffort` | both | `null` | `providers` | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | both | `null` | `providers` | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | both | `null` | `providers` | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `qa.roles` | both | `{}` | `providers` | Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a pin beats the provider block for that role. |
| `dev.provider` | both | `"claude"` | `providers` | Who implements. |
| `dev.fallback` | both | `"claude-sonnet-5"` | `providers` | Model a gone dev pin falls back to, on its family's provider. |
| `dev.codex.model` | both | `null` | `providers` | Codex model for implementation. |
| `dev.codex.reasoningEffort` | both | `null` | `providers` | Codex reasoning effort for implementation. |
| `dev.copilot.model` | both | `null` | `providers` | Copilot model for implementation. |
| `dev.kimi.model` | both | `null` | `providers` | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | both | `{}` | `providers` | Per-role dev pins, as `qa.roles`. |
| `secondOpinion.provider` | both | `"none"` | `providers` | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | both | `"cli"` | `providers` | How the second opinion is reached. |
| `secondOpinion.model` | both | `null` | `providers` | Second-opinion model. |
| `tracker` | repo | `"files"` | `trackers` | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `jira.project` | repo | `null` | `trackers` | Jira project key. No consumer found (docs/crew/config-rationale.md). |
| `jira.cloudId` | repo | `null` | `trackers` | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |
| `obsidian.vaultPath` | repo | `null` | `trackers` | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | repo | `null` | `trackers` | Board folder inside the vault (relative, no `..`). |
| `memory.mode` | both | `"repo"` | `memory` | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | both | `null` | `memory` | The Obsidian vault used for memory. |
| `verifyGate` | repo | `true` | `core` | Run the Stop verify gate. |
| `context.enabled` | repo | `true` | `context` | Run the context watcher. |
| `context.warnAt` | repo | `0.4` | `context` | Fraction of the budget at which the watcher warns, wraps up and auto-clears; default 0.4 since 1.2.40 (was 0.5), an explicit value is kept. |
| `context.reserveTokens` | repo | `0` | `context` | Tokens held back from the budget; `null` means off. |
| `context.autoClear.enabled` | machine-arms | `null` | `context` | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.method` | both | `"auto"` | `context` | How `/clear` is typed. `auto` picks per platform; a method this OS lacks stands auto-clear down. |
| `context.autoClear.delaySeconds` | both | `3` | `context` | Delay before typing; an unusable value warns and reads as 3. |
| `context.autoClear.minHandoffLines` | both | `5` | `context` | Shortest handoff that may be cleared after; a non-number reads as 5. |
| `context.autoClear.onlyRepos` | machine-only | `null` | `context` | Narrowing only, machine file only: null narrows nothing, a list arms only those repos, `[]` or a non-list arms nothing. |
| `context.autoClear.onlySessions` | machine-only | `null` | `context` | As `onlyRepos`, for session ids; with both set, both must match. |
| `context.autoClear.wrapUp` | machine-arms | `null` | `context` | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |
| `resume.auto` | machine-arms | `null` | `context` | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `humanOnly.approve` | human-only opt-out | `null` | `core` | The owner's opt-out of `/crew:approve` being human-only. null or `true` keeps it human-only; `false` opts out only from the machine file or an untracked repo file, only after `/crew:confirm-config` twice, and a `true` in either layer vetoes. crew 1.3.27: with an opt-out in force a cli-recorded approval counts (`crew_ticket.cli_approval_allowed`). |
| `humanOnly.promoteMarker` | human-only opt-out | `null` | `core` | The same opt-out for the production promote marker `.crew/.approved-<env>-<sha>`, under the same rules. crew 1.3.9: no hook acts on it yet, and no hook today checks who created the marker. |
| `worktrees.root` | both | `null` | `core` | The base directory for this repo's git worktrees, OUTSIDE the repo: they go in `<root>/<repo>-<digest>/<name>`. null is `~/.claude/crew/worktrees`; `~` is expanded, a relative path or one inside the repo is refused (never replaced by the default). It places the worktrees crew places (`/crew:emergency`, `crew_worktrees.py path`) and, once the owner registers the opt-in `WorktreeCreate` hook, the ones Claude Code creates; without the hook Claude Code keeps using `.claude/worktrees/`. |
| `promote.deadlineSeconds` | both | `null` | `core` | How many seconds the promote gate (`promote-gate.sh`) may run, counted from the moment its shell began, before it gives up and blocks (a hook that times out is not a block, so the gate stops itself first). null derives it from the guard's hook timeout less a 4 s margin: 16 s of the 20 s row. A number above the timeout less 2 s (18 s of 20) is clamped to that, so the setting can never let the gate outlive its hook; zero, a negative, a string or a boolean reads as null. The hook timeout is the guard's row in the dispatcher's table, not a setting. |
| `verify.stopBudgetSeconds` | repo | `60` | `core` | How many seconds the Stop row of the verify gate (`verify-gate.sh`) may spend running rules, cheapest first, before it defers the rest to CI and names them. Default 60, which is what the gate used before the key was settable. A write must be a whole number from 1 to 540 (the Stop hook's timeout less the gate's 60 s margin); anything else is refused, never stored as a value the gate would quietly replace with 60. null removes the setting. Repo file only: what a rule costs is a fact about the checkout. `--all` and `--ci` ignore it. A hand-edited string, boolean or negative reads as 60, never as no limit (a number the writer would refuse, such as 0 or 1e9, is still taken as written). |
| `reaper.enabled` | both | `false` | `core` | Whether scheduled and session-start passes of the orphan reaper (`crew_reaper.py --scheduled`) do anything. false by default; a manual `crew_reaper.py` run always works and is a dry run unless given `--apply`. Read from the machine file only: a repo value is ignored, because the reaper ends processes on this machine. |
| `reaper.dryRun` | both | `true` | `core` | When true (the default) a scheduled or session-start pass only logs what it would end to `~/.claude/crew/reaper.log`; set false to let it end processes. Only a scheduled pass reads it; a manual run ends processes only with `--apply`. |
| `reaper.spinCpuPct` | both | `50` | `core` | An orphan is SPINNING when it used at least this percentage of one core over the reaper's short sample (5 s) and is older than `spinMinAgeMin`. A number above 0; anything else reads as 50. |
| `reaper.spinMinAgeMin` | both | `15` | `core` | Minutes an orphan must be running before the spinning rule (and the self-matching `until pgrep -f` watcher rule) may end it. A number above 0; anything else reads as 15. |
| `reaper.blockedMinAgeHours` | both | `2` | `core` | Hours an orphan using under 1% of a core must be running before it counts as BLOCKED and may be ended. A number above 0; anything else reads as 2. |
| `reaper.protectedRegex` | both | `null` | `core` | A regular expression; a process whose image name or command line matches is never ended, it REPLACES the built-in list (claude, node, MCP servers, ai-connect, psmux/tmux, tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm, Defender, ssh). null keeps the built-in list; an invalid expression reads as null. |
| `reaper.intervalMin` | both | `10` | `core` | Minutes between runs of the scheduled task `crew_reaper.py --install-task` creates, and the least gap between two session-start passes. A whole number from 1; anything else reads as 10. The task is never installed by default. |
| `reaper.onSessionStart` | both | `false` | `core` | When true and `reaper.enabled` is true, the SessionStart context hook starts one detached reaper pass (at most one per `intervalMin`) and does not wait for it. false by default. |
| `emergency.standDown` | repo | `true` | `core` | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.maxTtlMinutes` | repo | `480` | `core` | Longest incident lifetime; never below `ttlMinutes`. |
| `notify.provider` | both | `null` | `notify` | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.tokenEnv` | machine-only | `null` | `notify` | Name of the environment variable holding the Telegram bot token; null may be filled from the notify skill's `bot_token_env`. Honoured from the machine file only. |
| `notify.chatId` | both | `null` | `notify` | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |
| `notify.events` | both | `["blocker", "deploy", "question"]` | `notify` | Events that notify: `deploy`, `question`, and `blocker` (T-0060's four blocker reasons). The pre-1.0 names `gate`, `waiting`, `phase`, `review` and `done` are mapped with a notice. A list is one leaf. |
| `platform.os` | repo | `null` | `platform` | Detected OS, stamped by platform-sync. |
| `platform.wsl` | repo | `null` | `platform` | Detected WSL, stamped by platform-sync. |
| `platform.shell` | repo | `null` | `platform` | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | repo | `null` | `platform` | Windows host IP seen from WSL. |
| `pm.authority` | both, widening warned | `"report-only"` | `core` | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.maxDispatches` | both | `3` | `core` | Roles the PM may dispatch in one pass. |
| `graph.out` | repo | `"graphify-out"` | `core` | Where the code graph is written. |
| `install.policy` | both, ratchet | `"manual"` | `core` | Whether crew may install a missing prerequisite. |
| `guards.profile` | both, ratchet | `"off"` | `guards` | One word for the twelve guards: `off` (today's defaults), `standard` or `strict`. Expands per layer; each guard's ratchet then runs on the expanded values. |
| `guards.overrides` | both, ratchet | `{}` | `guards` | `guards.overrides.<guard>`: one guard's tier, replacing the profile's value for it. Each entry is checked against that guard's own tiers; a bad one reads as the floor. |
| `guards.git.allow` | both | `null` | `guards` | The owner's switch that stops crew's command guards blocking or asking on git commands: `"all"` lets a line of only plain git commands past the force-push rule and the promote gate (unless a declared deploy is itself a git command); a list of subcommands (`["commit", "push"]`) lets only those through, with every option they take (listing `push` lets `push --force` through). null or `"off"` changes nothing. Machine file only, and only after `/crew:confirm-config` twice (`crew_confirm_config.py propose --key guards.git.allow --value ...`); a value written any other way, or any later change to the machine file outside crew's config writer, reads as off, and a repo `"off"` or unreadable repo file vetoes it. FAIL-CLOSED ALLOWLIST: a line is exempt only when it is ONE command, exactly `git` with plain literal words (no `$`, backtick, glob, brace, leading `~`, parenthesis, PowerShell expression or `%NAME%`; no separator, redirection, heredoc, continuation or comment, so a chain is judged as before); a git command carrying `-c`, a command to run (`rebase --exec`, `push --receive-pack`, `submodule foreach`, ...) or a `git config` write is never exempt. |
| `production.databases` | repo | `[]` | `cloud` | Globs naming production databases. |
| `production.hosts` | repo | `[]` | `cloud` | Globs naming production hosts. |
| `cloud.awsProfiles` | repo | `[]` | `cloud` | AWS profiles this repo may use. |
| `cloud.awsRegions` | repo | `[]` | `cloud` | AWS regions this repo may use. |
| `cloud.azureSubscriptions` | repo | `[]` | `cloud` | Azure subscriptions this repo may use. |
| `environments.nonProd` | repo | `[]` | `cloud` | Terraform targets that are not production and may run unattended. |
| `environments.prodUnattended` | both, ratchet | `false` | `cloud` | Whether production terraform may run unattended; `true` only when both layers say so. |
| `environments.workflows` | repo | `{}` | `cloud` | Deploy workflow globs, each mapped to its environment or `input:<name>`. |
| `environments.preProduction` | repo | `{}` | `cloud` | Environments labelled production that are not live yet: exact name -> `reason` (+ optional exact `targets`); judged non-production by the cloud guard, with an audit line. |
| `tiers` | both, ratchet | `{}` | `cloud` | Machine-owned tier per target (`<kind>:<name>` -> `{"tier": "dev"\|"qa"\|"prod"}`); dev < qa < prod < unknown, an unlisted target is `unknown`, and a repo entry may only narrow. Written whole (`--set tiers=<map>`). Read through `crew_tiers` only, never the merged value; report-only until R-01. |
| `change.requireForProduction` | both, ratchet | `false` | `core` | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |
| `git.forbiddenTrailers` | both | `[]` | `core` | Commit trailer tokens the owner forbids, reported by `/crew:done`. The two layers combine by union, so a repo can add a token and never remove the machine owner's; a value that is not a list of tokens makes the list unknown, never empty (docs/crew/config-rationale.md). |
| `scope.mode` | repo | `"off"` | `core` | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | repo | `false` | `core` | Whether a CLI-written approval receipt counts; only exactly `true` allows it. `autopilot.approval: self` or `risk` needs it, and `autopilot.mode: plan` or `backlog`, to approve anything. A hand edit by the owner in the repo's `.crew/config.json` (`"scope": {"allowCliApproval": true}`); `crew_config.py --set` refuses it. |
| `autopilot.mode` | both, stricter wins | `"off"` | `autopilot` | Only the exact strings `plan` (one ticket per run) and `backlog` (L-0541: a goal's tickets in dependency order, inside the caps) arm `/crew:autopilot`; anything else reads as off, with a warning. |
| `autopilot.maxPhases` | both, stricter wins | `12` | `autopilot` | Phases one run may take; anything but a positive integer reads as 12, with a warning. |
| `autopilot.deploy` | both, stricter wins | `"none"` | `autopilot` | Where a deploy may run without asking; anything else reads as `none`. |
| `autopilot.approval` | both, stricter wins | `"risk"` | `autopilot` | Who approves a ticket under autopilot; anything else reads as `human`. `risk` and `self` also need `autopilot.mode: plan` (or `backlog`) and `scope.allowCliApproval: true` (a hand edit of the repo's `.crew/config.json`); a refused `approve` lists each unmet one, with its value as written, the file that holds it and, under `risk`, the spec risk that blocks. |
| `autopilot.questions` | both, stricter wins | `"risk"` | `autopilot` | Who answers a ticket's open questions under autopilot; anything else reads as `human`. |
| `autopilot.maxAutoReplans` | repo | `0` | `autopilot` | Successor plans autopilot may start by rejecting an out-of-rounds BLOCK review itself; 0 is off, and anything but a non-negative integer reads as 0, and above 5 as 5, with a warning. |
| `autopilot.ship` | repo | `"merge"` | `autopilot` | After `/crew:done`: `pr` pushes and opens the PR; `merge` also merges it (a merge commit) once the required checks allow. Anything else reads as `pr`, with a warning. |
| `autopilot.sleep.schedule` | repo | `null` | `autopilot` | A nightly window, `HH:MM-HH:MM` in machine local time (may cross midnight); inside it the two sleep overrides apply. Anything else is could not tell: only a stricter override applies. |
| `autopilot.sleep.approval` | repo | `null` | `autopilot` | `autopilot.approval` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.questions` | repo | `null` | `autopilot` | `autopilot.questions` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.deploy` | repo | `null` | `autopilot` | `autopilot.deploy` inside the sleep window (L-0654): null keeps the day value, `nonprod` or `none` replaces it; anything else, `all` included, is refused with a warning. Asleep, an effective `all` reads as `nonprod`: production never runs unattended asleep. |
| `autopilot.maxTicketsPerRun` | repo | `3` | `autopilot` | Tickets one goal run (one session) may start; the next one stops the run. Anything but a positive integer reads as 3, with a warning. |
| `autopilot.maxTokensPerSession` | repo | `2000000` | `autopilot` | Input plus output tokens one goal session may spend, each assistant message counted once, before the run stops; a transcript that cannot be read stops too. Anything but a positive integer reads as 2000000, with a warning. |
| `autopilot.maxLanes` | repo | `null` | `autopilot` | Lanes one `/crew:autopilot wave` runs at once; null is the resolved `pm.maxDispatches`, a larger value is capped to it and anything but a positive integer reads as it, each with a warning. |
| `autopilot.reviewPolicy` | repo | `"stop"` | `autopilot` | What autopilot does with a review verdict. A wave lane: `stop` ends at the first verdict, `clean-only` takes a CLEAN round on to the done checks, `fix-and-rereview` fixes within the ledger's rounds. A single-ticket run (T-0067): only `fix-and-rereview` acts, fixing a non-final FINDINGS round's BLOCK and FIX lines itself (the `fix` phase) and re-reviewing. Anything else reads as `stop`, with a warning; no setting accepts a review. |
| `tickets.baseBranch` | repo | `null` | `core` | The branch ticket branches are cut from; null tries origin/HEAD's target, then origin/main, then main. A value that is not a branch name, or names no commit, makes the scope base could not tell. |
| `route.enabled` | both | `false` | `core` | Route plain-text prompts to `/crew:` commands; only the JSON value `true` arms it. |
| `unattendedCloud.aws.readOnly.profile` | machine-only | `null` | `cloud` | The AWS profile an unattended run exports credentials from (`aws configure export-credentials`); it must yield temporary credentials. Machine file only. |
| `unattendedCloud.aws.readOnly.identity` | machine-only | `null` | `cloud` | The assumed-role ARN prefix STS must report for that profile, ending in `/`; null refuses every launch. Machine file only. |
| `unattendedCloud.aws.readOnly.region` | machine-only | `null` | `cloud` | The AWS region the unattended run gets; null is `us-east-1`. Machine file only. |
| `unattendedCloud.aws.nonProd` | machine-only | `{}` | `cloud` | Environment name -> `{profile, identity, region?}` (region optional, default `us-east-1`) for `launch --environment NAME`; usable only where the repo's `environments.nonProd` agrees. Machine file only. |
