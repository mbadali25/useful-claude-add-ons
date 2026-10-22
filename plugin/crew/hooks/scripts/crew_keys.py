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
  ratchet tables, `crew_guards.PERSONAL_KEYS` and `crew_config.REPO_VETO_ONLY`,
  so it follows the code.

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
import crew_notify
import crew_platform
import crew_sleep
import crew_state
import crew_ticket
import crew_tracker

KINDS = ("tuple", "ratchet", "branch", "type", "open-table", "prose", "unvalidated")

# L-0725: every row carries one of these, so a split into plugins can count the
# core plugin's own keys. `autopilot`, `trackers` and `cloud` are the families
# L-0724 moves out. The assignment is `_FAMILY_OF` below, applied once after
# `KEY_META` is built, so a new row with no family is a test failure rather
# than an omission nobody sees.
FAMILIES = ("core", "providers", "guards", "cloud", "trackers", "autopilot",
            "context", "notify", "memory", "platform")

# Built once, so `values_of("qa.provider")` is the same object every call and
# its tail holds `QA_PROVIDERS`' own items.
QA_PROVIDER_VALUES = ("auto",) + crew_state.QA_PROVIDERS
# T-0053: a sleep override is a policy or null ("not overridden"); its tail
# holds `crew_autopilot.POLICIES`' own items.
SLEEP_OVERRIDE_VALUES = (None,) + crew_autopilot.POLICIES


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
            "source": source, "type": type_, "values_by_os": values_by_os,
            "family": None}


def _unv(summary, since, source, type_):
    return _row(summary, "unvalidated", since=since, source=source, type_=type_)


def _rat(summary, since):
    return _row(summary, "ratchet", since=since)


_S = "hooks/scripts/"

# dotted key -> row. Order follows `default_config()`. `since` is the first
# crew version whose committed template declared the key, backfilled once from
# git history (T-0048); a later key sets it in its land commit.
KEY_META = {
    "schema": _unv("Config schema version; `/crew:migrate` upgrades an older one.",
                   FIRST, _S + "crew_state.py", "integer"),
    # --- qa / dev: providers and models
    "qa.provider": _row("Who reviews: `auto` walks `qa.order`; a named provider is used "
                        "as-is.", "tuple", QA_PROVIDER_VALUES, FIRST),
    "qa.order": _row("The reviewers `auto` tries, in order. A list is one leaf, replaced "
                     "wholesale.", "tuple", crew_state.QA_PROVIDERS, "0.14.6",
                     type_="list of"),
    "qa.fallback": _unv("Model a gone pin falls back to, on its family's provider (L-0712).",
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
    "dev.fallback": _unv("Model a gone dev pin falls back to, on its family's provider.",
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
    # --- secondOpinion
    "secondOpinion.provider": _unv("Second-opinion provider for plans; `none` is off.",
                                   FIRST, "commands/plan.md", "string"),
    "secondOpinion.mode": _unv("How the second opinion is reached.", FIRST,
                               "skills/crew-providers/SKILL.md", "string"),
    "secondOpinion.model": _unv("Second-opinion model.", FIRST,
                                "skills/crew-providers/SKILL.md", "string or null"),
    # --- trackers
    "tracker": _row("Where tickets live; `crew_tracker.resolve` answers `could not tell` "
                    "when two configs disagree.", "tuple", crew_tracker.KINDS, FIRST),
    "jira.project": _unv("Jira project key. No consumer found (CONFIG.md section 9).",
                         FIRST, "commands/jira-sync.md", "string or null"),
    "jira.cloudId": _unv("Jira cloud id, cached by `/crew:jira-sync`; read by nothing.",
                         "0.19.10", "commands/jira-sync.md", "string or null"),
    "obsidian.vaultPath": _unv("Vault holding the board; falls back to "
                               "`memory.vaultPath` and must hold `.obsidian/`.", FIRST,
                               _S + "crew_tracker.py", "path or null"),
    "obsidian.boardDir": _unv("Board folder inside the vault (relative, no `..`).", FIRST,
                              _S + "crew_tracker.py", "path or null"),
    # --- memory
    "memory.mode": _unv("Where memory lives (`repo`, or a vault).", FIRST,
                        "skills/crew-memory/SKILL.md", "string"),
    "memory.vaultPath": _unv("The Obsidian vault used for memory.", FIRST,
                             _S + "crew_recall.py", "path or null"),
    "verifyGate": _unv("Run the Stop verify gate.", FIRST, _S + "verify-gate.sh",
                       "boolean"),
    # --- context
    "context.enabled": _unv("Run the context watcher.", FIRST, _S + "context-watch.sh",
                            "boolean"),
    "context.warnAt": _unv("Fraction of the budget at which the watcher warns, wraps up and "
                           "auto-clears; default 0.4 since 1.2.40 (was 0.5), an explicit "
                           "value is kept.", FIRST,
                           _S + "context-watch.sh", "number"),
    "context.reserveTokens": _unv("Tokens held back from the budget; `null` means off.",
                                  FIRST, _S + "context-watch.sh", "integer or null"),
    "context.autoClear.enabled": _row("Auto-clear after a wrap-up. Only the machine file "
                                      "can arm it (exactly `true`); a repo `false` vetoes "
                                      "it.", "branch", (None, True, False), "0.19.10",
                                      _S + "crew_autocycle.py"),
    "context.autoClear.method": _row("How `/clear` is typed. `auto` picks per platform; a "
                                     "method this OS lacks stands auto-clear down.",
                                     "tuple", AUTOCLEAR_METHOD_VALUES, "0.19.10",
                                     values_by_os=crew_platform._AUTOCLEAR_METHODS),  # pylint: disable=protected-access
    "context.autoClear.delaySeconds": _row("Delay before typing; an unusable value warns and "
                                           "reads as 3.", "type", since="0.19.10",
                                           source=_S + "crew_autocycle.py",
                                           type_="number"),
    "context.autoClear.minHandoffLines": _row("Shortest handoff that may be cleared after; "
                                              "a non-number reads as 5.", "type",
                                              since="0.19.10",
                                              source=_S + "crew_autocycle.py",
                                              type_="number"),
    "context.autoClear.onlyRepos": _row("Narrowing only, machine file only: null narrows "
                                        "nothing, a list arms only those repos, `[]` or a "
                                        "non-list arms nothing.", "type", since="1.0.25",
                                        source=_S + "crew_autocycle.py",
                                        type_="list of absolute repo paths, or null"),
    "context.autoClear.onlySessions": _row("As `onlyRepos`, for session ids; with both set, "
                                           "both must match.", "type", since="1.0.25",
                                           source=_S + "crew_autocycle.py",
                                           type_="list of session ids, or null"),
    "context.autoClear.wrapUp": _row("Auto wrap-up before auto-clear (T-0017): the warning "
                                     "becomes the wrap-up procedure and the clear waits for "
                                     "its results. Only the machine file arms it (exactly "
                                     "`true`), only where `enabled` is armed; a repo `false` "
                                     "vetoes it.", "branch", (None, True, False), "1.0.334",
                                     _S + "crew_autocycle.py"),
    "resume.auto": _row("Auto-resume after `/clear` or a manual `/compact`. Only the "
                        "machine file can arm it (exactly `true`); a repo `false` vetoes "
                        "it.", "branch", (None, True, False), "1.0.40",
                        _S + "crew_resume.py"),
    # --- emergency
    "emergency.standDown": _unv("Whether a declared incident may stand gates down; "
                                "`false` forbids it.", FIRST, _S + "_common.sh", "boolean"),
    "emergency.maxTtlMinutes": _row("Longest incident lifetime; never below "
                                    "`ttlMinutes`.", "type", since=FIRST,
                                    source=_S + "crew_incident.py", type_="integer"),
    # --- notify (crew_notify.py since T-0051; notify.sh / notify.ps1 are wrappers)
    "notify.provider": _row("Where notifications go: `telegram`, `teams` or `none` (off). A "
                            "repo null inherits the machine provider; a repo `none` opts "
                            "this repo out.", "type", since=FIRST,
                            source=_S + "crew_notify.py",
                            type_="telegram, teams, none or null; any other value sends "
                                  "nothing"),
    "notify.tokenEnv": _unv("Name of the environment variable holding the Telegram bot "
                            "token; null may be filled from the notify skill's "
                            "`bot_token_env`. Honoured from the machine file only.", FIRST,
                            _S + "crew_notify.py", "string or null"),
    "notify.chatId": _unv("Telegram chat id; null may be filled from the notify skill's "
                          "`chat_id`, and the skill's example value counts as unset.",
                          FIRST, _S + "crew_notify.py", "string or null"),
    "notify.events": _row("Events that notify: `deploy`, `question`, and `blocker` "
                          "(T-0060's four blocker reasons). The pre-1.0 names `gate`, "
                          "`waiting`, `phase`, `review` and `done` are mapped with a "
                          "notice. A list is one leaf.", "type", since=FIRST,
                          source=_S + "crew_notify.py",
                          type_="list of event names; an unknown name is dropped with a "
                                "notice"),
    # --- platform (written by platform-sync)
    "platform.os": _unv("Detected OS, stamped by platform-sync.", FIRST,
                        _S + "crew_platform.py", "string or null"),
    "platform.wsl": _unv("Detected WSL, stamped by platform-sync.", FIRST,
                         _S + "crew_platform.py", "boolean or null"),
    "platform.shell": _unv("Detected shell, stamped by platform-sync.", FIRST,
                           _S + "crew_platform.py", "string or null"),
    "platform.windowsHostIp": _unv("Windows host IP seen from WSL.", FIRST,
                                   _S + "crew_platform.py", "string or null"),
    # T-0044: machine file only; a repo copy is ignored and reported.
    "unattendedCloud.aws.readOnly.profile": _row(
        "The AWS profile an unattended run exports credentials from (`aws configure "
        "export-credentials`); it must yield temporary credentials. Machine file only.",
        "type", since="1.1.10", source=_S + "crew_unattended.py", type_="profile name, or null"),
    "unattendedCloud.aws.readOnly.identity": _row(
        "The assumed-role ARN prefix STS must report for that profile, ending in `/`; "
        "null refuses every launch. Machine file only.", "type", since="1.1.10",
        source=_S + "crew_unattended.py", type_="ARN prefix ending in `/`, or null"),
    "unattendedCloud.aws.readOnly.region": _row(
        "The AWS region the unattended run gets; null is `us-east-1`. Machine file only.",
        "type", since="1.1.10", source=_S + "crew_unattended.py", type_="region, or null"),
    "unattendedCloud.aws.nonProd": _row(
        "Environment name -> `{profile, identity, region}` for `launch --environment NAME`; "
        "usable only where the repo's `environments.nonProd` agrees. Machine file only.",
        "open-table", since="1.1.10", source=_S + "crew_unattended.py"),
    # --- pm
    "pm.authority": _row("How much the PM may do unasked. A widening is warned about; the "
                         "two layers combine by precedence.", "tuple",
                         crew_state.AUTHORITIES, FIRST),
    "pm.maxDispatches": _row("Roles the PM may dispatch in one pass.", "type", since=FIRST,
                             source=_S + "crew_state.py", type_="integer"),
    # --- graph
    "graph.out": _unv("Where the code graph is written.", FIRST, _S + "crew_state.py",
                      "path"),
    # --- docs
    # --- merge gates
    # --- git
    "git.forbiddenTrailers": _row("Commit trailer tokens the owner forbids, reported by "
                                  "`/crew:done`. The two layers combine by union, so a "
                                  "repo can add a token and never remove the machine "
                                  "owner's; a value that is not a list of tokens makes "
                                  "the list unknown, never empty (CONFIG.md section 22).",
                                  "branch", since="1.0.328",
                                  source=_S + "crew_trailers.py",
                                  type_="list of trailer tokens (letters, digits and "
                                        "`-`, no `:`)"),
    # --- install and guards (ratcheted: the tiers live in crew_guards)
    "install.policy": _rat("Whether crew may install a missing prerequisite.", "0.19.18"),
    "guards.profile": _row("One word for the twelve guards: `off` (today's defaults), "
                           "`standard` or `strict`. Expands per layer; each guard's "
                           "ratchet then runs on the expanded values.", "tuple",
                           crew_guards.GUARD_PROFILES, "1.2.62"),
    "guards.overrides": _row("`guards.overrides.<guard>`: one guard's tier, replacing "
                             "the profile's value for it. Each entry is checked against "
                             "that guard's own tiers; a bad one reads as the floor.",
                             "open-table", since="1.2.62", source=_S + "crew_guards.py",
                             type_="object of guard name to tier"),
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
    "environments.workflows": _unv("Deploy workflow globs, each mapped to its environment "
                                   "or `input:<name>`.", "1.1.16", _S + "crew_config.py",
                                   "object of glob to string"),
    # --- change requests
    "change.requireForProduction": _rat("Require an approved change request before "
                                        "`/crew:promote production`: a repo may turn it "
                                        "on, never off.", "0.19.31"),
    # --- scope
    "scope.mode": _row("Whether the scope guard enforces a ticket's Touch list; a value "
                       "outside these fails closed to `block`.", "tuple",
                       crew_ticket.MODES, "1.0.25"),
    "scope.allowCliApproval": _row("Whether a CLI-written approval receipt counts; only "
                                   "exactly `true` allows it.", "branch", (False, True),
                                   "1.0.25", _S + "crew_ticket.py"),
    # --- autopilot
    "autopilot.mode": _row("Only the exact strings `plan` (one ticket per run) and `backlog` "
                           "(L-0541: a goal's tickets in dependency order, inside the caps) "
                           "arm `/crew:autopilot`; anything else reads as off, with a "
                           "warning.", "branch", ("off", "plan", "backlog"),
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
    "autopilot.maxAutoReplans": _row("Successor plans autopilot may start by rejecting an "
                                     "out-of-rounds BLOCK review itself; 0 is off, and "
                                     "anything but a non-negative integer reads as 0, and "
                                     "above 5 as 5, with a warning.", "branch", None, "1.0.339",
                                     _S + "crew_autopilot.py", type_="non-negative integer"),
    "autopilot.sleep.schedule": _row("A nightly window, `HH:MM-HH:MM` in machine local time "
                                     "(may cross midnight); inside it the two sleep "
                                     "overrides apply. Anything else is could not tell: "
                                     "only a stricter override applies.", "branch",
                                     since="1.0.332", source=_S + "crew_sleep.py",
                                     type_="HH:MM-HH:MM or null"),
    "autopilot.sleep.approval": _row("`autopilot.approval` inside the sleep window; null "
                                     "keeps the day value; anything else counts as human, "
                                     "the strictest, with a warning.", "branch", SLEEP_OVERRIDE_VALUES,
                                     "1.0.332", _S + "crew_sleep.py"),
    "autopilot.sleep.questions": _row("`autopilot.questions` inside the sleep window; null "
                                      "keeps the day value; anything else counts as human, "
                                      "the strictest, with a warning.", "branch", SLEEP_OVERRIDE_VALUES,
                                      "1.0.332", _S + "crew_sleep.py"),
    "autopilot.sleep.deploy": _row("`autopilot.deploy` inside the sleep window (L-0654): null "
                                   "keeps the day value, `nonprod` or `none` replaces it; "
                                   "anything else, `all` included, is refused with a warning. "
                                   "Asleep, an effective `all` reads as `nonprod`: production "
                                   "never runs unattended asleep.", "branch",
                                   (None,) + crew_sleep.DEPLOY_OVERRIDES, "1.1.21",
                                   _S + "crew_sleep.py"),
    "autopilot.ship": _row("After `/crew:done`: `pr` pushes and opens the PR; `merge` also "
                           "merges it (a merge commit) once the required checks allow. "
                           "Anything else reads as `pr`, with a warning.", "tuple",
                           crew_autopilot.SHIP_POLICIES, "1.0.349"),
    "autopilot.maxTicketsPerRun": _row("Tickets one goal run (one session) may start; the "
                                       "next one stops the run. Anything but a positive "
                                       "integer reads as 3, with a warning.", "branch", None,
                                       "1.1.21", _S + "crew_autopilot_backlog.py",
                                       type_="positive integer"),
    "autopilot.maxTokensPerSession": _row("Input plus output tokens one goal session may "
                                          "spend, each assistant message counted once, "
                                          "before the run stops; a transcript that "
                                          "cannot be read stops too. Anything but a "
                                          "positive integer reads as 2000000, with a "
                                          "warning.", "branch", None, "1.1.21",
                                          _S + "crew_autopilot_backlog.py",
                                          type_="positive integer"),
    "autopilot.maxLanes": _row("Lanes one `/crew:autopilot wave` runs at once; null is the "
                               "resolved `pm.maxDispatches`, a larger value is capped to it and "
                               "anything but a positive integer reads as it, each with a "
                               "warning.", "branch", None, "1.1.6", _S + "crew_wave.py",
                               type_="positive integer or null"),
    "autopilot.reviewPolicy": _row("What autopilot does with a review verdict. A wave lane: "
                                   "`stop` ends at the first verdict, `clean-only` takes a CLEAN "
                                   "round on to the done checks, `fix-and-rereview` fixes within "
                                   "the ledger's rounds. A single-ticket run (T-0067): only "
                                   "`fix-and-rereview` acts, fixing a non-final FINDINGS round's "
                                   "BLOCK and FIX lines itself (the `fix` phase) and re-reviewing. "
                                   "Anything else reads as `stop`, with a warning; no setting "
                                   "accepts a review.", "tuple",
                                   ("stop", "clean-only", "fix-and-rereview"), "1.1.6"),
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


# Family by key. Exact keys first, then the first path segment. Anything not
# named is `core`. Counting the core plugin's keys is "every family but
# autopilot, trackers and cloud" (L-0724).
_FAMILY_OF_KEY = {
    "tracker": "trackers",
    "tickets.baseBranch": "core",
    "resume.auto": "context",
    "environments.prodUnattended": "cloud",
    "environments.nonProd": "cloud",
    "environments.workflows": "cloud",
}
_FAMILY_OF_SEGMENT = {
    "qa": "providers", "dev": "providers", "secondOpinion": "providers",
    "guards": "guards",
    "cloud": "cloud", "production": "cloud", "unattendedCloud": "cloud",
    "jira": "trackers", "obsidian": "trackers", "sdp": "trackers",
    "bitbucket": "trackers", "github": "trackers",
    "autopilot": "autopilot",
    "context": "context", "resume": "context",
    "notify": "notify",
    "memory": "memory",
    "platform": "platform", "shellRoute": "platform",
}


def family_of(key):
    """The family `key` belongs to, from `_FAMILY_OF_KEY` then its first
    segment, else `core`."""
    if key in _FAMILY_OF_KEY:
        return _FAMILY_OF_KEY[key]
    return _FAMILY_OF_SEGMENT.get(key.split(".", 1)[0], "core")


for _key, _row_ in KEY_META.items():
    _row_["family"] = family_of(_key)


def _coming(key, ticket, change, summary, default, layer, values=None):
    return {"key": key, "ticket": ticket, "change": change, "summary": summary,
            "default": default, "layer": layer, "values": values}


# Keys from approved tickets that have not landed, read from each ticket's
# spec on 2026-10-03. `change` is `new key`, or `changes <what>` for a key
# already in KEY_META. Defaults and layers are the spec's words, not a guess.
COMING = (
    _coming("coord.ttlMinutes", "T-0030", "new key",
            "Lifetime of a cross-session coordination claim (1-10080).", "30",
            "set when T-0030 lands"),
    _coming("coord.channel", "T-0030", "new key",
            "Where sessions coordinate.", "set when T-0030 lands",
            "set when T-0030 lands"),
    # T-0050 landed the five personal `autopilot` keys (`layer_of` now says
    # `both, stricter wins` for them, from `crew_guards.PERSONAL_KEYS`). This
    # row is the part of its spec it left out under the T-0087 harness rule:
    # the reader, `crew_ticket.cli_approval_allowed`, is review harness.
    _coming("scope.allowCliApproval", "T-0050", "changes layer",
            "Becomes settable in the global file, the stricter layer winning, once "
            "its reader (`crew_ticket.cli_approval_allowed`) reads the global layer "
            "in a harness-only follow-up to T-0050.", "false",
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


# context.autoClear's machine-only keys, and the notify keys crew_notify honours
# from the machine file alone (T-0051: each names the variable whose value becomes
# the request URL, so a cloned repo may not choose it).
_MACHINE_ONLY = (tuple("context.autoClear." + k for k in crew_state.AUTOCLEAR_MACHINE_ONLY_KEYS)
                 + tuple("notify." + k for k in crew_notify.GLOBAL_ONLY_KEYS))


def layer_of(key):
    """Which layer may set `key`, derived from the code that enforces it:
    `machine-arms` (`crew_config.REPO_VETO_ONLY`: only the machine file arms
    it, a repo may only veto), `machine-only` (read from the machine file
    alone), `repo`, `both, stricter wins` (`crew_guards.PERSONAL_KEYS`, T-0050),
    `both, ratchet`, `both, widening warned` or `both`."""
    if key in crew_config.REPO_VETO_ONLY:
        return "machine-arms"
    if key in _MACHINE_ONLY or key.split(".", 1)[0] in crew_state.UNATTENDED_CLOUD_MACHINE_ONLY:
        return "machine-only"
    if not crew_config.is_global_path(key):
        return "repo"
    if key in crew_guards.PERSONAL_KEYS:
        return "both, stricter wins"
    if crew_guards.ratchet_spec(key) is not None:
        return "both, ratchet"
    if key in ("guards.profile", "guards.overrides"):
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
