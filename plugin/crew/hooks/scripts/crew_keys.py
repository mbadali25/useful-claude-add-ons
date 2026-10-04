"""One row per crew config key: what it means, what values it takes, and the
crew version it arrived in. The settings reference is generated from this
table (`docs/guides/crew/src/config_reference.py`, T-0048), and so is the key
table inside `CONFIG.md`.

**The one rule: a value tuple a validator reads is REFERENCED here, never
copied.** `qa.provider`'s values are `crew_state.QA_PROVIDERS` itself, a
ratcheted key's are the tiers in `crew_guards.RATCHETED_KEYS`, and so on. A
copy would be a second definition, and a second definition is the drift this
module exists to remove: the validator would change and the reference would
keep printing the old list. `tests/test_crew_keys.py` holds every such row to
`is`, not `==`.

Where a validator is a code branch rather than a tuple (`autopilot.mode`,
`autopilot.maxPhases`, `resume.auto`, `context.autoClear.enabled`,
`route.enabled`), the row declares the values (kind `branch`) and a test runs
each one, and one undeclared value, through the real reader. Where crew
validates nothing, the row says `unvalidated` and names the file that reads
the key; the reference then prints "not validated", never an implied check.

What this module does NOT hold:
- defaults: `crew_config.default_config()` / `default_global_config()` own
  them, and the generator reads them from there;
- the layer: `layer_of` derives it from `crew_config.is_global_path`, the
  ratchet tables and `crew_config.REPO_VETO_ONLY`, so it follows the code.

`COMING` holds keys from approved tickets that have not landed, each naming
its ticket. A test fails when one of them is in the code, so the landing
ticket moves its row into `KEY_META` and sets `since`.

Nothing imports this module except the generator and the tests, so it may
import the readers without a cycle. Standard library only.
"""
from __future__ import annotations

import crew_autopilot
import crew_config
import crew_guards
import crew_platform
import crew_shell
import crew_state
import crew_ticket
import crew_tracker

KINDS = ("tuple", "ratchet", "branch", "type", "open-table", "prose", "unvalidated")

# Built once, so `values_of("qa.provider")` is the same object every call and
# its tail holds `QA_PROVIDERS`' own items.
QA_PROVIDER_VALUES = ("auto",) + crew_state.QA_PROVIDERS


def _union_in_order(table):
    out = []
    for values in table.values():
        for value in values:
            if value not in out:
                out.append(value)
    return tuple(out)


# Every method any platform delivers, in first-seen order; the per-OS table is
# carried beside it as `values_by_os` (the object `crew_platform.concerns`
# reads).
AUTOCLEAR_METHOD_VALUES = _union_in_order(
    crew_platform._AUTOCLEAR_METHODS)  # pylint: disable=protected-access

# The first template (e9bf1438, crew 0.11.0) predates the version history the
# backfill can see, so a key it already declared reads "0.11.0 or earlier".
FIRST = "<=0.11.0"


def _row(summary, kind, values=None, since=None, source=None, type_=None,
         values_by_os=None):
    return {"summary": summary, "kind": kind, "values": values, "since": since,
            "source": source, "type": type_, "values_by_os": values_by_os}


def _unv(summary, since, source, type_):
    return _row(summary, "unvalidated", since=since, source=source, type_=type_)


def _rat(summary, since):
    return _row(summary, "ratchet", since=since)


_S = "hooks/scripts/"

# dotted key -> row. Order follows `default_config()`. `since` is the first
# crew version whose committed template declared the key, backfilled once from
# git history (T-0048); a later key sets it in its land commit.
KEY_META = {
    "schema": _unv("Config schema version; `/crew:upgrade` migrates an older one.",
                   FIRST, _S + "crew_state.py", "integer"),
    "tier": _unv("Setup tier recorded by `/crew:init`.", FIRST, _S + "crew_state.py",
                 "integer"),
    "roles": _unv("Optional roles installed in this repo.", FIRST, _S + "crew_state.py",
                  "list of role names"),
    # --- qa / dev: providers and models
    "qa.provider": _row("Who reviews: `auto` walks `qa.order`; a named provider is used "
                        "as-is.", "tuple", QA_PROVIDER_VALUES, FIRST),
    "qa.order": _row("The reviewers `auto` tries, in order. A list is one leaf, replaced "
                     "wholesale.", "tuple", crew_state.QA_PROVIDERS, "0.14.6",
                     type_="list of"),
    "qa.fallback": _unv("Claude model used when no other reviewer is available.",
                        "0.16.6", "commands/review.md", "model id"),
    "qa.codex.model": _unv("Codex model for review; null passes no flag.", "0.14.6",
                           "commands/review.md", "string or null"),
    "qa.codex.reasoningEffort": _row("Codex reasoning effort for review; null passes no "
                                     "flag.", "prose",
                                     ("none", "minimal", "low", "medium", "high",
                                      "xhigh", "max"),
                                     "0.14.6", "commands/review.md"),
    "qa.copilot.model": _unv("Copilot model for review; null uses the CLI default.",
                             "0.14.6", "commands/review.md", "string or null"),
    "qa.kimi.model": _unv("Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); "
                          "null uses the CLI's own default.", "1.0.39",
                          "commands/review.md", "string or null"),
    "qa.roles": _row("Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a "
                     "pin beats the provider block for that role.", "open-table",
                     since="0.16.6", source=_S + "crew_config.py",
                     type_="object of role pins; each pin's provider is checked"),
    "dev.provider": _row("Who implements.", "tuple", crew_state.DEV_PROVIDERS, "0.14.6"),
    "dev.fallback": _unv("Claude model used when the dev provider is unavailable.",
                         "0.16.6", "skills/crew-providers/SKILL.md", "model id"),
    "dev.codex.model": _unv("Codex model for implementation.", "0.14.6",
                            "skills/crew-providers/SKILL.md", "string or null"),
    "dev.codex.reasoningEffort": _row("Codex reasoning effort for implementation.",
                                      "prose",
                                      ("none", "minimal", "low", "medium", "high",
                                       "xhigh", "max"),
                                      "0.14.6", "commands/review.md"),
    "dev.copilot.model": _unv("Copilot model for implementation.", "0.14.6",
                              "skills/crew-providers/SKILL.md", "string or null"),
    "dev.kimi.model": _unv("Kimi Code model id for implementation, as `qa.kimi.model`.",
                           "1.0.39", "skills/crew-providers/SKILL.md", "string or null"),
    "dev.roles": _row("Per-role dev pins, as `qa.roles`.", "open-table", since="0.16.6",
                      source=_S + "crew_config.py",
                      type_="object of role pins; each pin's provider is checked"),
    "worktree.root": _unv("Where crew creates linked worktrees; null uses the default.",
                          "0.16.27", _S + "crew_state.py", "path or null"),
    # --- secondOpinion
    "secondOpinion.provider": _unv("Second-opinion provider for plans; `none` is off.",
                                   FIRST, "commands/plan.md", "string"),
    "secondOpinion.mode": _unv("How the second opinion is reached.", FIRST,
                               "skills/crew-providers/SKILL.md", "string"),
    "secondOpinion.model": _unv("Second-opinion model.", FIRST,
                                "skills/crew-providers/SKILL.md", "string or null"),
    "secondOpinion.keyEnv": _unv("Environment variable holding the provider's API key.",
                                 FIRST, "skills/crew-providers/SKILL.md", "string"),
    "secondOpinion.sendsCode": _unv("Whether code may be sent to the second-opinion "
                                    "provider.", FIRST, "skills/crew-providers/SKILL.md", "boolean"),
    # --- trackers
    "tracker": _row("Where tickets live; `crew_tracker.resolve` answers `could not tell` "
                    "when two configs disagree.", "tuple", crew_tracker.KINDS, FIRST),
    "jira.project": _unv("Jira project key. No consumer found (CONFIG.md section 9).",
                         FIRST, "commands/jira-sync.md", "string or null"),
    "jira.cloudId": _unv("Jira cloud id, cached by `/crew:jira-sync`; read by nothing.",
                         "0.19.10", "commands/jira-sync.md", "string or null"),
    "sdp.portal": _unv("ServiceDesk Plus portal.", FIRST, "commands/sdp-sync.md",
                       "string or null"),
    "sdp.noteVisibility": _unv("Visibility of notes crew writes to SDP.", FIRST,
                               "commands/sdp-sync.md", "string"),
    "sdp.closeOnDone": _unv("Close the SDP request when the ticket is done.", FIRST,
                            "commands/sdp-sync.md", "boolean"),
    "obsidian.vaultPath": _unv("Vault holding the board; falls back to "
                               "`memory.vaultPath` and must hold `.obsidian/`.", FIRST,
                               _S + "crew_tracker.py", "path or null"),
    "obsidian.boardDir": _unv("Board folder inside the vault (relative, no `..`).", FIRST,
                              _S + "crew_tracker.py", "path or null"),
    "obsidian.board": _unv("Board file name.", FIRST, _S + "crew_tracker.py",
                           "file name"),
    "obsidian.columns.backlog": _unv("Board column for backlog tickets.", FIRST,
                                     _S + "crew_tracker.py", "string"),
    "obsidian.columns.ready": _unv("Board column for ready tickets.", FIRST,
                                   _S + "crew_tracker.py", "string"),
    "obsidian.columns.inProgress": _unv("Board column for tickets in progress.", FIRST,
                                        _S + "crew_tracker.py", "string"),
    "obsidian.columns.review": _unv("Board column for tickets in review.", FIRST,
                                    _S + "crew_tracker.py", "string"),
    "obsidian.columns.done": _unv("Board column for done tickets.", FIRST,
                                  _S + "crew_tracker.py", "string"),
    # --- memory
    "memory.mode": _unv("Where memory lives (`repo`, or a vault).", FIRST,
                        "skills/crew-memory/SKILL.md", "string"),
    "memory.vaultPath": _unv("The Obsidian vault used for memory.", FIRST,
                             _S + "crew_recall.py", "path or null"),
    "memory.inject": _unv("Inject the handoff and recall at session start; only an "
                          "explicit `false` stops it.", "1.0.25", _S + "crew_context.py",
                          "boolean"),
    "memory.recall.vaults": _unv("This repo's vault priority for recall; empty uses the "
                                 "obsidian config's roles.", "1.0.25",
                                 _S + "crew_recall.py", "list of vault names"),
    "memory.recall.maxChars": _row("Recall output budget; a non-positive or non-integer "
                                   "value reads as 800.", "type", since="1.0.25",
                                   source=_S + "crew_recall.py", type_="positive integer"),
    "verifyGate": _unv("Run the Stop verify gate.", FIRST, _S + "verify-gate.sh",
                       "boolean"),
    # --- context
    "context.enabled": _unv("Run the context watcher.", FIRST, _S + "context-watch.sh",
                            "boolean"),
    "context.warnAt": _unv("Fraction of the budget at which the watcher warns.", FIRST,
                           _S + "context-watch.sh", "number"),
    "context.budgetTokens": _unv("Context budget in tokens; null uses the model's.", FIRST,
                                 _S + "context-watch.sh", "integer or null"),
    "context.reserveTokens": _unv("Tokens held back from the budget; `null` means off.",
                                  FIRST, _S + "context-watch.sh", "integer or null"),
    "context.handoffPath": _unv("Where the handoff is written.", FIRST,
                                _S + "crew_autocycle.py", "path"),
    "context.keepTranscripts": _unv("Transcripts kept by the handoff writer.", FIRST,
                                    _S + "handoff-write.sh", "integer"),
    "context.autoClear.enabled": _row("Auto-clear after a wrap-up. Only the machine file "
                                      "can arm it (exactly `true`); a repo `false` vetoes "
                                      "it.", "branch", (None, True, False), "0.19.10",
                                      _S + "crew_autocycle.py"),
    "context.autoClear.method": _row("How `/clear` is typed. `auto` picks per platform; a "
                                     "method this OS lacks stands auto-clear down.",
                                     "tuple", AUTOCLEAR_METHOD_VALUES, "0.19.10",
                                     values_by_os=crew_platform._AUTOCLEAR_METHODS),  # pylint: disable=protected-access
    "context.autoClear.windowTitle": _unv("Window title to match before typing.",
                                          "0.19.10", _S + "auto-clear.ps1",
                                          "string or null"),
    "context.autoClear.command": _unv("What is typed.", "0.19.10", _S + "crew_autocycle.py",
                                      "string"),
    "context.autoClear.delaySeconds": _row("Delay before typing; an unusable value warns and "
                                           "reads as 3.", "type", since="0.19.10",
                                           source=_S + "crew_autocycle.py",
                                           type_="number"),
    "context.autoClear.minHandoffLines": _row("Shortest handoff that may be cleared after; "
                                              "a non-number reads as 5.", "type",
                                              since="0.19.10",
                                              source=_S + "crew_autocycle.py",
                                              type_="number"),
    "context.autoClear.unsafeFocus": _unv("Consent to `wtype` typing into whatever has "
                                          "focus. No longer read: `auto-clear.sh` refuses "
                                          "`wtype` whatever this says.", "0.19.11",
                                          _S + "auto-clear.sh", "boolean"),
    "context.autoClear.onlyRepos": _row("Narrowing only, machine file only: null narrows "
                                        "nothing, a list arms only those repos, `[]` or a "
                                        "non-list arms nothing.", "type", since="1.0.25",
                                        source=_S + "crew_autocycle.py",
                                        type_="list of absolute repo paths, or null"),
    "context.autoClear.onlySessions": _row("As `onlyRepos`, for session ids; with both set, "
                                           "both must match.", "type", since="1.0.25",
                                           source=_S + "crew_autocycle.py",
                                           type_="list of session ids, or null"),
    "context.autoWrapUp": _unv("Ask for a wrap-up when the budget runs low.", "0.19.10",
                               _S + "context-watch.sh", "boolean"),
    "context.autoResume": _unv("Retired: read by nothing since 1.0.0; kept so "
                               "`/crew:migrate` carries it.", "0.19.10",
                               "commands/migrate.md", "boolean"),
    "context.staleHandoff.maxAgeHours": _unv("A handoff older than this is archived.",
                                             "0.16.33", _S + "crew_state.py", "integer"),
    "context.staleHandoff.maxCommitsBehind": _unv("A handoff this many commits behind is "
                                                  "archived.", "0.16.33",
                                                  _S + "crew_state.py", "integer"),
    "resume.auto": _row("Auto-resume after `/clear` or a manual `/compact`. Only the "
                        "machine file can arm it (exactly `true`); a repo `false` vetoes "
                        "it.", "branch", (None, True, False), "1.0.40",
                        _S + "crew_resume.py"),
    "resume.typeDelaySeconds": _row("Wait before auto-resume types its command: before the "
                                    "tmux ready probe, and the only wait on Windows. Read "
                                    "from the machine file only.", "type", since="1.0.321",
                                    source=_S + "crew_autocycle.py",
                                    type_="whole seconds; fraction cut, negative or "
                                          "non-number reads as the default"),
    "resume.readyTimeoutSeconds": _row("How long the tmux ready probe waits for an idle, "
                                       "empty input line before it types nothing. Read "
                                       "from the machine file only.", "type",
                                       since="1.0.321", source=_S + "crew_autocycle.py",
                                       type_="whole seconds; fraction cut, negative or "
                                             "non-number reads as the default"),
    # --- emergency
    "emergency.standDown": _unv("Whether a declared incident may stand gates down; "
                                "`false` forbids it.", FIRST, _S + "_common.sh", "boolean"),
    "emergency.ttlMinutes": _row("Default incident lifetime; a non-integer reads as the "
                                 "default.", "type", since=FIRST,
                                 source=_S + "crew_incident.py", type_="integer"),
    "emergency.maxTtlMinutes": _row("Longest incident lifetime; never below "
                                    "`ttlMinutes`.", "type", since=FIRST,
                                    source=_S + "crew_incident.py", type_="integer"),
    # --- notify
    "notify.provider": _unv("Where notifications go; `none` is off.", FIRST,
                            _S + "notify.sh", "string"),
    "notify.urlEnv": _unv("Environment variable holding the webhook URL.", FIRST,
                          _S + "notify.sh", "string or null"),
    "notify.tokenEnv": _unv("Environment variable holding the token.", FIRST,
                            _S + "notify.sh", "string or null"),
    "notify.chatId": _unv("Chat id for chat providers.", FIRST, _S + "notify.sh",
                          "string or null"),
    "notify.events": _unv("Events that notify. A list is one leaf.", FIRST,
                          _S + "notify.sh", "list of event names"),
    # --- platform (written by platform-sync)
    "platform.os": _unv("Detected OS, stamped by platform-sync.", FIRST,
                        _S + "crew_platform.py", "string or null"),
    "platform.wsl": _unv("Detected WSL, stamped by platform-sync.", FIRST,
                         _S + "crew_platform.py", "boolean or null"),
    "platform.shell": _unv("Detected shell, stamped by platform-sync.", FIRST,
                           _S + "crew_platform.py", "string or null"),
    "platform.windowsHostIp": _unv("Windows host IP seen from WSL.", FIRST,
                                   _S + "crew_platform.py", "string or null"),
    "shellRoute.mode": _row("The shell long-running jobs use on native Windows; null "
                            "inherits, and an unknown value reads as `auto` and is named.",
                            "tuple", crew_shell.MODES, "1.0.54"),
    "shellRoute.distro": _unv("WSL distro to route to; null takes the default distro.",
                              "1.0.54", _S + "crew_shell.py", "string or null"),
    # --- pm
    "pm.enabled": _unv("Run the PM brief.", FIRST, _S + "crew_state.py", "boolean"),
    "pm.mode": _unv("How the PM brief adapts its length.", FIRST, _S + "crew_state.py",
                    "string"),
    "pm.quietLines": _row("PM brief length when nothing changed.", "type", since=FIRST,
                          source=_S + "crew_state.py", type_="integer"),
    "pm.maxLines": _row("Longest PM brief.", "type", since=FIRST,
                        source=_S + "crew_state.py", type_="integer"),
    "pm.authority": _row("How much the PM may do unasked. A widening is warned about; the "
                         "two layers combine by precedence.", "tuple",
                         crew_state.AUTHORITIES, FIRST),
    "pm.ticketGranularity": _row("How big a ticket the PM cuts.", "tuple",
                                 crew_state.TICKET_GRANULARITIES, "0.16.34"),
    "pm.maxDispatches": _row("Roles the PM may dispatch in one pass.", "type", since=FIRST,
                             source=_S + "crew_state.py", type_="integer"),
    # --- graph
    "graph.enabled": _unv("No consumer found (CONFIG.md section 9).", FIRST,
                          "skills/crew-graph/SKILL.md", "boolean"),
    "graph.tool": _unv("No consumer found (CONFIG.md section 9).", FIRST,
                       "skills/crew-graph/SKILL.md", "string"),
    "graph.out": _unv("Where the code graph is written.", FIRST, _S + "crew_state.py",
                      "path"),
    "graph.mode": _unv("No consumer found (CONFIG.md section 9).", FIRST,
                       "skills/crew-graph/SKILL.md", "string"),
    "graph.commitHook": _unv("No consumer found (CONFIG.md section 9).", FIRST,
                             "skills/crew-graph/SKILL.md", "boolean"),
    # --- docs
    "docs.theme": _unv("House-style theme for built documents; null uses the "
                       "skill's own choice.", "0.16.33", "skills/crew-house-style/SKILL.md",
                       "string or null"),
    "docs.reportTheme": _unv("Theme for findings reports.", "0.16.33",
                             "skills/crew-house-style/SKILL.md", "string or null"),
    # --- merge gates
    "bitbucket.mergeGate.enabled": _unv("Let `/crew:promote` drive the Bitbucket merge "
                                        "gate.", "0.16.33", "commands/promote.md",
                                        "boolean"),
    "bitbucket.mergeGate.branch": _unv("Branch the Bitbucket merge gate protects.",
                                       "0.16.33", "commands/promote.md", "string or null"),
    "bitbucket.mergeGate.preset": _unv("Selects nothing today (CONFIG.md section 9).",
                                       "0.16.33", "commands/promote.md", "string"),
    "github.mergeGate.enabled": _unv("Let `/crew:promote` drive the GitHub merge gate.",
                                     "0.19.30", "commands/promote.md", "boolean"),
    "github.mergeGate.branch": _unv("Branch the GitHub merge gate protects.", "0.19.30",
                                    "commands/promote.md", "string or null"),
    # --- git
    "git.forbiddenTrailers": _row("Commit trailer tokens the owner forbids, reported by "
                                  "`/crew:done`. The two layers combine by union, so a "
                                  "repo can add a token and never remove the machine "
                                  "owner's; a value that is not a list of tokens makes "
                                  "the list unknown, never empty (CONFIG.md section 22).",
                                  "branch", since="1.0.356",
                                  source=_S + "crew_trailers.py",
                                  type_="list of trailer tokens (letters, digits and "
                                        "`-`, no `:`)"),
    # --- install and guards (ratcheted: the tiers live in crew_guards)
    "install.policy": _rat("Whether crew may install a missing prerequisite.", "0.19.18"),
    "guards.terraformApply": _rat("`terraform apply` and friends.", "0.19.30"),
    "guards.forcePush": _rat("`git push --force`.", "0.19.30"),
    "guards.adminMerge": _rat("`gh pr merge --admin`.", "0.19.30"),
    "guards.mergeGate": _rat("Taking a live repo's merge gate down (read by "
                             "`/crew:gate`).", "0.19.30"),
    "guards.cloudDestructive": _rat("Destructive cloud CLI commands.", "1.0.25"),
    "guards.sqlDestructive": _rat("Destructive SQL.", "1.0.25"),
    "guards.prodDatabase": _rat("How much of a declared production database crew may "
                                "reach.", "0.19.30"),
    "guards.prodServer": _rat("How much of a declared production host crew may reach.",
                              "0.19.30"),
    "guards.roleWrites": _rat("Enforce each role's write scope. Default `off`; a "
                              "malformed value reads as `block`.", "0.19.92"),
    "guards.cloudGuard": _rat("Whether the cloud guard judges commands at all. Default "
                              "`off`; `report` logs only.", "1.0.25"),
    "production.databases": _unv("Globs naming production databases.", "0.19.30",
                                 _S + "crew_config.py", "list of globs"),
    "production.hosts": _unv("Globs naming production hosts.", "0.19.30",
                             _S + "crew_config.py", "list of globs"),
    "cloud.awsProfiles": _unv("AWS profiles this repo may use.", "1.0.25",
                              _S + "cloud_guard.py", "list of names"),
    "cloud.awsRegions": _unv("AWS regions this repo may use.", "1.0.25",
                             _S + "cloud_guard.py", "list of names"),
    "cloud.azureSubscriptions": _unv("Azure subscriptions this repo may use.", "1.0.25",
                                     _S + "cloud_guard.py", "list of names"),
    "environments.nonProd": _unv("Terraform targets that are not production and may run "
                                 "unattended.", "1.0.37", _S + "crew_config.py",
                                 "list of globs"),
    "environments.prodUnattended": _rat("Whether production terraform may run unattended; "
                                        "`true` only when both layers say so.", "1.0.37"),
    # --- change requests
    "change.requester": _unv("Who requests the change.", "0.19.31", _S + "crew_change.py",
                             "string or null"),
    "change.implementor": _unv("Who implements the change.", "0.19.31",
                               _S + "crew_change.py", "string or null"),
    "change.requireForProduction": _rat("Require an approved change request before "
                                        "`/crew:promote production`: a repo may turn it "
                                        "on, never off.", "0.19.31"),
    "change.sdpTemplate": _unv("SDP template for a change request.", "0.19.31",
                               _S + "crew_change.py", "string"),
    "change.jiraIssueType": _unv("Jira issue type for a change request.", "0.19.31",
                                 _S + "crew_change.py", "string"),
    "change.category": _unv("Change category.", "0.19.31", _S + "crew_change.py",
                            "string or null"),
    # --- scope
    "scope.mode": _row("Whether the scope guard enforces a ticket's Touch list; a value "
                       "outside these fails closed to `block`.", "tuple",
                       crew_ticket.MODES, "1.0.25"),
    "scope.allowCliApproval": _row("Whether a CLI-written approval receipt counts; only "
                                   "exactly `true` allows it.", "branch", (False, True),
                                   "1.0.25", _S + "crew_ticket.py"),
    # --- autopilot
    "autopilot.mode": _row("Only the exact string `plan` arms `/crew:autopilot`; anything "
                           "else reads as off, with a warning.", "branch", ("off", "plan"),
                           "1.0.41", _S + "crew_autopilot.py"),
    "autopilot.maxPhases": _row("Phases one run may take; anything but a positive integer "
                                "reads as 12, with a warning.", "branch", None, "1.0.41",
                                _S + "crew_autopilot.py", type_="positive integer"),
    "autopilot.deploy": _row("Where a deploy may run without asking; anything else reads "
                             "as `none`.", "tuple", crew_autopilot.DEPLOY_VALUES, "1.0.42"),
    "autopilot.approval": _row("Who approves a ticket under autopilot; anything else reads "
                               "as `human`.", "tuple", crew_autopilot.POLICIES, "1.0.42"),
    "autopilot.questions": _row("Who answers a ticket's open questions under autopilot; "
                                "anything else reads as `human`.", "tuple",
                                crew_autopilot.POLICIES, "1.0.42"),
    # --- tickets
    "tickets.baseBranch": _row("The branch ticket branches are cut from; null tries "
                               "origin/HEAD's target, then origin/main, then main. A "
                               "value that is not a branch name, or names no commit, "
                               "makes the scope base could not tell.", "branch",
                               since="1.0.158", source=_S + "scope_base.py",
                               type_="branch name or null"),
    # --- route
    "route.enabled": _row("Route plain-text prompts to `/crew:` commands; only the JSON "
                          "value `true` arms it.", "branch", (False, True), "1.0.42",
                          "hooks/scripts/crew_route.py"),
}


def _coming(key, ticket, change, summary, default, layer, values=None):
    return {"key": key, "ticket": ticket, "change": change, "summary": summary,
            "default": default, "layer": layer, "values": values}


# Keys from approved tickets that have not landed, read from each ticket's
# spec on 2026-10-03. `change` is `new key`, or `changes <what>` for a key
# already in KEY_META. Defaults and layers are the spec's words, not a guess.
COMING = (
    _coming("autopilot.ship", "T-0011", "new key",
            "After `/crew:done`, open a PR (`pr`) or also merge it once required checks "
            "are green (`merge`).", "merge", "repo", ("pr", "merge")),
    _coming("autopilot.knownFailures", "T-0011", "new key",
            "Required checks that may fail without blocking a merge, matched by exact "
            "name.", "[]", "repo"),
    _coming("autopilot.ciTimeoutMinutes", "T-0011", "new key",
            "How long ship waits for CI; still pending at the timeout stops.", "60",
            "repo"),
    _coming("autopilot.maxTicketsPerRun", "T-0012", "new key",
            "Tickets one goal run may work before it stops.", "3", "repo"),
    _coming("autopilot.maxTokensPerSession", "T-0012", "new key",
            "Token cap for one goal session.", "2000000", "repo"),
    _coming("autopilot.mode", "T-0012", "changes values",
            "Adds `backlog`: work a goal's tickets one at a time.", "off", "repo",
            ("off", "plan", "backlog")),
    _coming("context.autoClear.wrapUp", "T-0017", "new key",
            "Machine opt-in for the automatic wrap-up; only exactly `true` arms it.",
            "null", "machine-arms"),
    _coming("guards.deployWorkflow", "T-0009", "new key",
            "Whether crew may dispatch a deploy workflow.", "block", "both, ratchet"),
    _coming("environments.workflows", "T-0009", "new key",
            "Deploy workflows per environment.", "{}", "repo"),
    _coming("autopilot.maxLanes", "T-0029", "new key",
            "Parallel lanes one autopilot wave may run; may only lower the limit.",
            "the resolved pm.maxDispatches", "repo"),
    _coming("autopilot.reviewPolicy", "T-0029", "new key",
            "What a lane does with review findings.", "stop", "repo",
            ("stop", "clean-only", "fix-and-rereview")),
    _coming("coord.ttlMinutes", "T-0030", "new key",
            "Lifetime of a cross-session coordination claim (1-10080).", "30",
            "set when T-0030 lands"),
    _coming("coord.channel", "T-0030", "new key",
            "Where sessions coordinate.", "set when T-0030 lands",
            "set when T-0030 lands"),
    _coming("autopilot.mode", "T-0050", "changes layer",
            "The personal autopilot keys become settable in the global file; the "
            "stricter layer wins.", "off", "both, stricter wins"),
    _coming("scope.allowCliApproval", "T-0050", "changes layer",
            "Becomes settable in the global file; the stricter layer wins.", "false",
            "both, stricter wins"),
)


def all_leaves():
    """Every declared leaf, repo order first, then any global-only leaf."""
    out = list(crew_config.leaf_paths(crew_config.default_config()))
    for key in crew_config.leaf_paths(crew_config.default_global_config()):
        if key not in out:
            out.append(key)
    return out


def values_of(key):
    """The values `key` takes: the tiers object for a ratcheted key (never a
    row's own copy), else the row's `values`, else None."""
    spec = crew_guards.ratchet_spec(key)
    if spec is not None:
        return spec[0]
    return KEY_META[key]["values"]


_MACHINE_ONLY = tuple("context.autoClear." + k for k in crew_state.AUTOCLEAR_MACHINE_ONLY_KEYS)


def layer_of(key):
    """Which layer may set `key`, derived from the code that enforces it:
    `machine-arms` (`crew_config.REPO_VETO_ONLY`: only the machine file arms
    it, a repo may only veto), `machine-only` (read from the machine file
    alone), `repo`, `both, ratchet`, `both, widening warned` or `both`."""
    if key in crew_config.REPO_VETO_ONLY:
        return "machine-arms"
    if key in _MACHINE_ONLY:
        return "machine-only"
    if not crew_config.is_global_path(key):
        return "repo"
    if crew_guards.ratchet_spec(key) is not None:
        return "both, ratchet"
    if key in crew_config._RATCHETED:  # pylint: disable=protected-access
        return "both, widening warned"
    return "both"


def problems():
    """Every way this table disagrees with the code, as text. Empty is good."""
    out = []
    leaves = all_leaves()
    for key in leaves:
        if key not in KEY_META:
            out.append(f"missing: {key} is a config leaf with no KEY_META row")
    for key in KEY_META:
        if key not in leaves:
            out.append(f"orphan: {key} has a KEY_META row and is not a config leaf")
    for key, row in KEY_META.items():
        if row["kind"] not in KINDS:
            out.append(f"bad kind: {key} has kind {row['kind']!r}")
        if crew_guards.ratchet_spec(key) is not None and row["values"] is not None:
            out.append(f"restated tiers: {key} is ratcheted; its row must not carry "
                       "values (crew_guards.RATCHETED_KEYS owns them)")
        if crew_guards.ratchet_spec(key) is not None and row["kind"] != "ratchet":
            out.append(f"ratchet kind: {key} is ratcheted and its kind is {row['kind']!r}")
        if not row["summary"]:
            out.append(f"no summary: {key}")
    return out


def coming_in_code():
    """`(key, ticket)` for every COMING `new key` row the code already declares."""
    leaves = set(all_leaves())
    return [(row["key"], row["ticket"]) for row in COMING
            if row["change"] == "new key" and row["key"] in leaves]
