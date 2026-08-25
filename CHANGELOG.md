# Changelog

All notable changes to this repository are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows the `version` field on each plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) rather than a single repo-wide version, since skills ship independently.

## [Unreleased]

### Added

- **`crew` 0.5.2 - ServiceDesk Plus as a third tracker.** `tracker: "sdp"` plus
  `/crew:sdp-sync <REQUEST-ID> [--push]`, mirroring the Jira path rather than
  inventing a second shape: pull keeps id, subject, status, requester, priority,
  category and the last three notes and discards the rest, `/crew:work` reads
  that cache instead of the API, and sync happens at pickup and completion only.
  `/crew:ticket` and `/crew:work` both learned the mode, and `/crew:init` offers
  it as the third answer to the tracker question - **only when the `sdp_*` tools
  are actually reachable**, since a repo configured for an API nobody can call
  stops every later command on the same missing precondition.
  - **The local key is `SDP-<id>`, not the bare request number.** SDP ids are
    plain integers and the rest of crew recognises a ticket by its
    `LETTERS-digits` shape, so a bare `40219` is invisible to the session brief,
    to `/crew:work` and to the index. Both halves of that claim are now pinned by
    tests, because the failure mode is silence: every SDP repo would report "no
    ticket open" forever.
  - Three things the command has to get right that Jira does not have: notes are
    **requester-visible** unless private (`sdp.noteVisibility` defaults to
    `private`, and that is not a substitute for scrubbing), a bad field value
    **rejects the whole write** rather than partially applying it (resolve
    against `sdp_list_metadata` first), and **closing is not crew's decision** -
    `sdp.closeOnDone` defaults to `false`, so push transitions a request and
    leaves closure to whoever owns the queue.
  - No `.mcp.json` ships for it, deliberately: the SDP connector is normally
    registered at user or session scope, and a per-repo one would prompt for
    approval in every repository where the plugin is enabled.
  - New config block `"sdp": { "portal": null, "noteVisibility": "private",
    "closeOnDone": false }`. Documented in `crew/README.md` 13b, the
    configuration table, `PLUGINS.md`, and both setup docs.

- **`crew` 0.5.1 — `/crew:emergency`, a time-boxed lane for when something is
  actually broken.** The gates that normally earn their keep are, during an
  outage, standing between you and the fix, and the honest options are to work
  around them silently or to make standing them down a decision with a record
  and a clock on it. `/crew:emergency <what is broken>` writes
  `.crew/incident.json`; while it exists and its `expiresAtEpoch` is in the
  future, `verify-gate` exits 0 without running the checks and `promote-gate`
  computes its preconditions, records the ones that failed, and allows the
  deploy. `status`, `extend [minutes]` and `end` are the rest of the surface.
  Declaring also fans out read-only investigation lanes in parallel — what
  changed in the window before the symptom, what shares the failing path, the
  most probable causes with the cheapest observation that would kill each, plus
  `security` and `dba` lanes when the symptom calls for them.
  - **It expires on its own.** The gates compare an integer epoch, so nothing
    runs and no file is touched to re-gate. Forgetting to close an incident is
    the realistic failure — nobody forgets to declare one during an outage — and
    it cannot leave a repository permanently ungated. `emergency.ttlMinutes`
    defaults to 120; `extend` is capped by `emergency.maxTtlMinutes` (480) and
    measured from *now* each time, so repeated extensions cannot compound.
  - **The command guard never stands down.** `guard.sh` / `guard.ps1` has no
    incident branch and must not get one. Standing down a check that says a
    change is wrong is a trade; standing down the one that stops a change being
    unrecoverable — a force push, a destructive Terraform verb, a history
    rewrite, a secret read into the transcript — is not, and an incident is
    precisely when someone is tired enough to need it.
  - **The debt list is the deliverable.** Every skipped gate is recorded to
    `.crew/incident-skips.log`, one row per gate and reason rather than one per
    turn, and `end` turns it into `.work/INCIDENT-<id>.md` plus an archived
    record under `.crew/incidents/`. Deleting the state file is what puts the
    gates back, and it happens only after the archive is on disk.
  - **Every session start says so.** `incidentActive` and `incidentUnclosed`
    are the two highest-priority PM triggers, above `upgradeNeeded`, and the
    incident line sits in the brief's quiet lines so no line cap can truncate
    it away. A session that does not know the gates are off is a session about
    to merge unverified work believing it was checked.
  - **A repository can forbid the whole thing.** `emergency.standDown: false`
    keeps every gate gating; the incident is still declared, recorded, briefed,
    and still spawns its lanes.
  - Covered by `tests/test_incident.py` (24 cases), 15 new cases in
    `hooks/scripts/_test/run-tests.sh` — including that the guard still blocks
    during an incident and that an expired one gates again — and
    `tests/test_gates_powershell.py`, which runs the same scenarios against the
    `.ps1` gates. All sabotage-tested in both flavours.

### Fixed

- **`crew` 0.5.1 - findings from the Codex review pass, fixed before merge.** 0.5.0
  was set on the branch and never published; the released version is 0.5.1.

  - `crew_incident_active` in `_common.sh` pulled `expiresAtEpoch` out with
    `sed`, so `{ not json "expiresAtEpoch": 9999999999` stood every gate down in
    bash while the PowerShell twin's `ConvertFrom-Json` correctly rejected it -
    a gate switchable off by a typo, and a flavour disagreement in the
    fail-*open* direction. It now parses the document in full and treats every
    failure, including no python at all, as "no incident". Two regression cases
    cover it, and the old implementation demonstrably read that epoch.
  - Skip-log rows are deduplicated on read as well as on write, so a race
    between the two hook flavours can no longer inflate the count of what is
    owed, and tabs, carriage returns and newlines are normalised out of gate
    names and details in all three implementations - a `rollbackReason` with a
    newline in it would otherwise forge a row.
  - `end()` re-reads the state file and refuses to close an incident whose id
    changed underneath it, before writing anything: a declaration landing mid
    close would otherwise be archived under the previous id and deleted,
    re-gating a repository someone had just declared an incident for.
  - `_write_state` uses a pid-unique temp file, so two writers cannot interleave
    into one and publish a torn document.
  - Documented rather than fixed, both in `crew/README.md` 24: the expiry is
    wall-clock, so a machine whose clock moves backwards extends the window; and
    the `.crew/.handoff-requested` marker is per repository rather than per
    session, so two sessions in one repo share one context warning. The second
    is pre-existing and wrong rather than deliberate - the fix is to key it on
    the payload's `session_id`.

- **`crew` 0.5.1 — the context watch no longer asks for a handoff with 200k
  tokens still free.** `context.warnAt` was tuned when every window was 200k,
  where 0.8 leaves 40k: about enough to finish a thought and write the note. The
  same 0.8 on a 1M window leaves 200,000 tokens unused and still asks you to
  wrap up, which is a whole 200k session's worth of room thrown away — and no
  percentage fixes it, because the right amount of headroom is an absolute
  number. The threshold is now the **later** of `warnAt * budget` and
  `budget - context.reserveTokens` (new, default 100000), so the floor can only
  ever push the warning later: a 200k window still fires at exactly 80% (40k
  < 100k, so the percentage wins) and a 1M session moves from 80% to 90%.
  `reserveTokens: 0` or `null` restores the pure percentage, and `warnAt: 0`
  still fires immediately — the floor is skipped entirely for it rather than
  quietly outranking the one explicit override. The warning now names which rule
  fired, with both figures and the remaining headroom, so a threshold behaving
  oddly is visible instead of mysterious. New cases in
  `tests/test_context_watch.py` pin the no-regression case, the 1M case, the
  default, the `warnAt: 0` override, and full stderr parity between the two
  flavours on the new branch.
- **`crew` 0.5.1 — the once-per-session handoff marker is now claimed
  atomically** (`noclobber` in bash, `FileMode::CreateNew` in PowerShell). On
  Windows with Git Bash installed both flavours of the `Stop` hook really do
  run, and a test-then-create let both through, so the same warning was emitted
  twice. The PowerShell side also had to take the absolute path: `[System.IO.
  File]` resolves a relative one against `[Environment]::CurrentDirectory`,
  which `Set-Location` does not update, so the claim would have landed in
  whatever directory the hook was spawned from.
- **`crew` 0.5.1 — `Resolve-CrewBash`'s PATH fallback could return an empty
  interpreter.** A `bash` function or alias defined in a PowerShell profile is
  returned by `Get-Command bash -All` ahead of any `bash.exe` with an empty
  `.Source`; `.StartsWith()` on that throws and returning it handed
  `& $bashExe` nothing, so the gate reported a smoke failure that was really a
  resolution failure. Tier b now takes `Application` entries only — the same
  guard the git walk-up already had.
- **`validate-prompts.py` counted a slash-command reference as a subagent
  dispatch.** `/crew:pm` in a command's prose is a pointer to another command,
  not an `Agent` call, but several names are both an agent and a command — so
  `scale.md`, which only mentions `/crew:pm`, was told to declare a tool it
  never uses. The check now excludes the slashed form.

### Changed

- **`scripts/check-powershell.ps1` now checks every tracked `.ps1`, not just the
  installer.** It defaulted to `install-prerequisites.ps1` alone, which left the
  crew plugin's hook scripts — the ones that run from a hook on someone else's
  machine, where a thrown exception is invisible — completely unguarded by the
  one check that catches a call to a function that does not exist. All 18 files
  pass; sabotage-tested by mis-naming a call in `verify-gate.ps1`, which the old
  default would not have caught. `-Path` still checks a single file. The first
  CI run of the wider check immediately earned it, by failing on the
  `ScheduledTasks` cmdlets in `vault-automation/setup-vault-automation.ps1`:
  that module ships with Windows and does not exist on the Linux runner, so
  those calls resolve for a developer and not for CI. They are in the
  `$externallyProvided` allowlist by exact name rather than by a
  `*-ScheduledTask*` pattern, so a typo in one of them is still caught -
  verified by introducing one.
- **CI runs the crew hook regression suite and the prompt validator.** Both were
  committed, documented as the safety net for hooks that can block a turn, and
  run only when somebody remembered to. A gate that stops gating still exits 0,
  which is exactly the kind of regression a suite nobody runs cannot catch.

### Fixed

- **`crew` 0.4.5 — the Windows `Stop` hook ran the verify smoke inside WSL.**
  With WSL installed, PowerShell resolves a bare `bash` to
  `C:\Windows\system32\bash.exe`, so `verify-gate.ps1` ran `_verify/smoke.sh`
  in a distro with no terraform, no python and a different `~`, and reported
  `SMOKE: 0/9 FAIL` on trees where Git Bash reads 12/12 — a blocking gate
  failing for a reason that had nothing to do with the repository.
  `Resolve-CrewBash` in `hooks/scripts/verify-gate.ps1` now walks up from
  `git.exe`'s own directory to `bin\bash.exe` or `usr\bin\bash.exe`, falls
  back to `Get-Command bash -All` minus System32 and WindowsApps, and only then
  to a bare `bash`, so nothing changes off Windows. Both call sites use it —
  the `smoke.sh` invocation and the `run: ["bash ..."]` rules from
  `.crew/verify.json` — and the failure output now names the interpreter it
  used. `tests/test_verify_gate_bash_resolver.py` covers the four resolution
  shapes: System32 first on PATH, a `mingw64` install, the WindowsApps
  execution alias, and a `git` defined as a PowerShell function, which used to
  throw a terminating error out of the hook. The PATH fallback carries the same
  guard as the walk-up, for the same reason: a `bash` function or alias in a
  PowerShell profile is returned by `Get-Command bash -All` ahead of any real
  executable with an empty `.Source`, which the gate would have run as an empty
  interpreter and reported as a smoke failure.
  0.4.4 was set on the branch and never published; the released version is
  0.4.5.
- **`crew` 0.4.5 also carries the five ANEWINF-720 silent-failure fixes**, which
  merged without a version bump and so never reached an installed copy: the
  rollback gate fails closed instead of skipping when `.crew/verify.json` omits
  `rollback`, generated `STATUS.md` and `verify.json` state that enforcement is
  session-local, `/crew:review` writes ticket-scoped scratch paths rather than
  racing concurrent reviews, the tool matcher sees commands invoked from inside
  a script, and the guard no longer fires on an incidental substring match.

- **`crew` 0.4.3 — the context watch no longer ends Windows sessions on turn one,
  and knows that Claude 5 models have a 1M window.** Three causes, all in the
  `Stop` hook pair `hooks/scripts/context-watch.{sh,ps1}`:
  - `context-watch.ps1` still estimated occupancy from transcript file size
    (`bytes/4*0.75`) against a hardcoded 200k. The transcript is cumulative, so on
    real sessions that read 158%, 195% and 664% — the handoff prompt fired on the
    first turn of every Windows session. It now reads the transcript's last
    `message.usage` record exactly as the bash flavour does, with the same model
    table, the same observed-peak correction, and byte-identical output.
  - The model table in both flavours said `opus`, `sonnet` and `fable` are 200k.
    `claude-opus-5`, `claude-sonnet-5` and `claude-fable-5` ship with 1M; the
    observed-peak self-correction only rescued that past 190k, so the 160k–190k
    band fired falsely on every Claude 5 session. The table now carries the 1M
    entries above the generic 200k ones. The observed-peak correction also went
    the other way: it tripped at 95% of the table figure, so a Claude 5 session
    that legitimately passed 950k of a correct 1M entry was bumped to the 2M
    tier and the gate never fired. It now triggers only on a peak the window
    could not have held.
  - A pinned `context.budgetTokens` the session has already exceeded (an older
    `/crew:init` wrote `200000` into every config) is now overridden by the
    observed peak and reported as `configured+observed`. A stale pin the session
    is still *under* cannot be detected; set it to `null`.
  - Subagent turns were never counted — Claude Code writes them to
    `<session>/subagents/*.jsonl`, which the watch does not open — and that is
    now stated in the docs and pinned by a test; inline `isSidechain` records from
    older builds are skipped explicitly.
  - `tests/test_context_watch.py` previously fed both flavours a byte blob with
    no usage record, so the PowerShell drift was invisible. It now feeds real
    usage transcripts for every branch (Claude 5 at 170k must not fire, Haiku at
    170k must, stale pin override, subagent exclusion) and compares the two
    flavours' full stderr on the measured path.

### Removed

- **The `claude-mem` and VoltAgent menu items are gone from both install scripts.**
  They were items 9 and 10, both on by default, so a bootstrap run installed a memory
  plugin, Bun as its worker runtime, a `CLAUDE_MEM_WORKER_PORT` patch to
  `settings.json`, and ten VoltAgent subagent plugins whether or not you wanted any of
  them. All of that is out: the `--voltagent` / `-VoltAgent` flag and its sub-picker
  group, the `VOLTAGENT_*` / `$script:VoltAgentCatalog` catalogs, `install_bun` /
  `Install-Bun`, and `set_claude_mem_worker_port` / `Set-ClaudeMemWorkerPort`. The menu
  is now 20 items, 8 of them on by default. **Everything after the hole shifted down by
  two** — the MCP servers are 9–12, Supabase 13, Context7 14, Playwright CLI 15, SkillUI
  16, Strix 17, Obsidian 18, this repo's plugins 19, `graphify` 20 — so any script
  passing `--select` by *number* needs updating; the stable keys (`--select
  supabase,strix`) do not. Both scripts were changed together and verified to produce
  the same 20-row menu and the same answer for `--select 19` / `-Select 19`. The
  removal is documented across `README.md` (both tables, the switch table, and every
  per-item note that names a number), `INSTALLATION.md`, `MARKETPLACE.md` and
  `SECURITY.md`; `scripts/_test/menu-groups.sh` now exercises the range and
  out-of-range cases against the skills group instead of the VoltAgent one, and
  `check-marketplace.py` no longer expects a `VOLTAGENT_KEYS` array. Nothing already
  installed on a machine is touched — uninstall those plugins by hand if you want them
  gone (`claude plugin uninstall claude-mem@thedotmack`, and likewise for each
  `voltagent-*@voltagent-subagents`). The removed flag fails differently on the two
  platforms, so a script still passing it needs editing either way: `--voltagent a,b`
  on the `.sh` warns `Unknown option` twice (once for the flag, once for its argument,
  which no longer gets shifted past) and then installs the rest of the selection, while
  `-VoltAgent a,b` on the `.ps1` is a parameter-binding error and the script does not
  run at all.

### Fixed

- **`crew` 0.4.2 — every PowerShell hook was dead on Windows, and the command guard
  blocked nothing there for the second time.** `hooks.json` wrote each PowerShell entry
  as `& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/x.ps1'`. For a `shell: powershell` entry
  Claude Code substitutes that placeholder as a PowerShell *environment reference*, and
  PowerShell does not expand anything inside single quotes — so `&` was handed the token
  verbatim and the hook died with "is not recognized as a name of a cmdlet". Only the two
  `SessionStart` hooks reported it visibly, because they are the ones that fire at
  startup; `guard.ps1`, `promote-gate.ps1`, `handoff-write.ps1`, `notify.ps1`,
  `verify-gate.ps1` and `context-watch.ps1` were failing just as silently. Fixing the
  quoting exposed a second failure underneath it: `& script.ps1` inside PowerShell's
  `-Command` does not propagate the script's exit code, so a guard's `exit 2` arrived as
  1 — a non-blocking error — and the command ran anyway. Every PowerShell entry now
  double-quotes the path and ends with `; exit $LASTEXITCODE`, verified end to end
  against `guard.ps1` (blocking `git push --force`, exit 2; allowing `Get-ChildItem`,
  exit 0). The bash entries got the same double-quoting, which they needed for a home
  directory with a space in it. `scripts/check-marketplace.py` grew a
  `check_hook_commands` check that fails CI on either mistake, and both new rules are
  written into `CLAUDE.md`. This was not an install-script problem — the repo and
  installed copies were byte-identical, so every Windows install of `crew` had it.

### Changed

- **Re-pinned the README's one-liner install URLs** from `8fc09be` to `ae58c21`, per the
  rule in `CLAUDE.md`. `8fc09be` predates the menu trim above, so the documented
  one-liner was still installing `claude-mem`, Bun and the ten VoltAgent packs by
  default, and still numbering its menu 1–22.
- **Re-pinned the README's one-liner install URLs** from `f59faf1` to `7059ede`, per the
  rule in `CLAUDE.md`. The old pin predated everything below, so the documented one-liner
  was still handing people the installer with the broken `claude plugin update` call.

### Fixed

- **Every installed skill was frozen at whatever it looked like on the day it was first
  published.** `claude plugin update` decides whether to re-copy a plugin by comparing
  declared versions, and no skill in this marketplace had ever had its `version` bumped -
  all 25 sat at `1.0.0` from the day they were added. Nineteen of them had had real
  content changes since. The CLI answered every update with "already at the latest
  version (1.0.0)" and copied nothing, so anyone who ran the installer once was still
  running the original text of every skill, with no indication anything was wrong. The
  matching `claude plugin update` bug (below) had been masking it behind a warning that
  looked like the real explanation. The 18 skills whose files had changed since their
  version was set are now `1.1.0`; `crew` goes to `0.3.0` (its `0.2.0` was declared a
  commit before the Windows hook fix landed, and two further changes landed after that).
  The seven skills whose files genuinely had not changed are left at `1.0.0`.

### Added

- **`crew` 0.3.0 — a report-only project manager, a code graph, and a v1→v2
  upgrade path.** Three connected pieces, all off by default in what they can
  do to `.crew/config.json`:
  - **The PM.** `/crew:pm` (status with no argument; `onboard <role>` /
    `offboard <role>` with explicit yes/no confirmation before either touches
    config) and the `crew:pm` subagent, which holds no `Write` tool at all —
    it reads `crew_state.py`'s output, correlates the full metrics history or
    audits every codemap anchor when that would cost more context in the main
    session than the answer is worth, and returns a report plus one
    recommendation, under 200 words. It never applies anything; the session
    that invoked it acts, or not. A new `SessionStart` hook, `pm-brief.sh` /
    `.ps1`, runs the same state read at the start of every session and prints
    a prioritized brief — schema drift, a stale or missing code graph, a
    pending handoff, review health — before you type anything. Two related
    `context` settings, both default `false`: `autoWrapUp` changes what the
    `Stop` hook tells the session to do at the warning threshold (reach a
    stopping point and write the handoff, rather than just ask), and
    `autoResume` opens the next session already holding the last handoff as
    `additionalContext` — `initialUserMessage` was ruled out because it is
    confirmed only for non-interactive `-p` runs. Neither setting makes
    `/clear` itself automatic; no hook can trigger one.
  - **The code graph.** The `crew-graph` skill wraps the third-party
    `graphify` CLI (PyPI package `graphifyy`, double-y) to build and query a
    code graph at `graph.out` (default `graphify-out/graph.json`), gated on
    `--no-viz --code-only` for a keyless build. Freshness is read from
    `graphify`'s own `built_at_commit` field in
    `graph.json`, never a file timestamp — a `git pull` that predates the
    last build now correctly reports as stale instead of falsely current.
    Exporting into Obsidian needs an explicit `graph.obsidian.confirmed` set
    by hand; nothing sets it for you.
  - **The upgrade path.** `/crew:upgrade` brings a pre-schema config (no
    `schema` key, now `schema: 1`) forward to `schema: 2`: backs up
    `.crew/codemap/` before any other write, builds the graph if it's
    missing or stale, derives `Entry points` / `Owns data` / `Calls out to`
    per subsystem from the graph, and writes `.crew/codemap/UPGRADE.md`
    reporting contradictions and stale-on-purpose anchors rather than
    resolving either automatically. `## Does`, `## Landmines`, and
    `## Unverified` pass through byte-identical, always. An anchor only
    bumps on a section actually re-verified this run.

  `.crew/config.json` gains `schema`, a `pm` block (`enabled`, `mode`,
  `quietLines`, `maxLines`, `authority` — always `report-only`), and a
  `graph` block (`out`, `obsidian.confirmed`) — see `plugin/crew/README.md`
  §11. The plugin now registers 10 subagents, 18 slash commands, and 16
  bundled skills, up from 9/14/14.
- **Both `.sh` and `.ps1` are now wired for every hook event, not just
  `PreToolUse`.** `verify-gate.ps1`, `context-watch.ps1`, and
  `handoff-read.ps1` existed on disk but were never referenced in
  `hooks.json`; `handoff-write.ps1` and `notify.ps1` are new. 8 scripts × 2
  flavours = 16 hook entries across the same 5 events (including the
  `promote-gate.sh`/`.ps1` pair added below), registered unconditionally —
  one flavour is expected to fail per machine, and that is by design, not a
  regression. On Windows this closes the gap the 0.2.0 entry below flagged
  as a known, documented-not-fixed limitation; on Linux with no `pwsh`, the
  real hook-runner behaviour remains unverified rather than assumed fine.
- **The `repo-plugins` install item (21) now detects a global `find-skills`
  collision instead of only documenting it.** If
  `~/.claude/skills/find-skills` exists — from menu item 5, or a direct
  `npx skills add vercel-labs/skills --skill find-skills` — the step warns
  that two active copies of `find-skills` can both trigger on the same
  prompt and prints the manual `rm -rf` to remove the global one. Detection
  only; it never deletes anything itself.
- **Menu item 22, `graphify` — off by default, no new flag.** Installs the
  `graphify` CLI (`uv tool install graphifyy`) and registers it
  **per-repository**, never globally, with `graphify install --project`.
  Reuses `--select` / `-Select` like every other item. Installing it alone
  does nothing; `crew`'s `crew-graph` skill and `/crew:upgrade` are what call
  it.
- **`--dry-run` / `-DryRun`.** Settles the selection, prints it, and stops without
  installing anything - the quickest way to see what a set of flags actually resolves
  to, and what `scripts/_test/menu-groups.sh` uses so a test run cannot reach `apt-get`
  or `npm install -g`.
- **Every menu row that installs more than one thing now has a sub-picker.** Only the
  repo's own skills row did; the team, community, VoltAgent and repo-plugin rows were
  all-or-nothing, so wanting one of the three team plugins, or two of the ten VoltAgent
  packs (154 subagents), meant taking the lot or editing the script. All five rows are
  now marked `>` in the menu, open their own picker on the right arrow, and carry a live
  `N of M` count. New flags for the non-interactive path, matching `--skills`:
  `--team` / `-Team`, `--community` / `-Community`, `--voltagent` / `-VoltAgent`,
  `--plugins` / `-Plugins`, each taking names, numbers, `all` or `none`. A name matches
  the plugin key or the short label the picker shows, so `--voltagent infra` and
  `--voltagent voltagent-infra` are the same thing. Naming items inside a row also
  selects that row - which is what makes `--plugins crew` work at all, since that row is
  off by default - but never overrides a choice made at the menu. Only the marketplaces behind a ticked plugin are registered now, so
  `--team excalidraw-generator` adds one marketplace instead of three. The five catalogs
  are the single source for the menu label, the picker, the flag and the install loop,
  so a row cannot say "3 of 3" and then install something else - all five, including the
  skills, go through one `install_group` / `Install-Group`. That also fixed a smaller
  thing: a marketplace behind several ticked plugins is registered once rather than once
  per plugin, so the community row no longer re-clones `claude-settings` three times.

- **Content-drift detection in both install scripts.** A version bump fixes today's
  staleness; this stops it recurring silently. For an already-installed plugin the
  scripts compare the commit its marketplace is on against the commit Claude Code
  recorded at install time, and then ask git whether *that plugin's* files changed
  between the two - one commit anywhere in a marketplace moves `HEAD` for everything it
  publishes, so this also keeps unrelated commits off the slow path. If the files did
  change and `claude plugin update` still copies nothing, that is the unbumped-version
  case, and the scripts now say so plainly instead of reporting the plugin as current.
  New `--force-refresh` / `-ForceRefresh` reinstalls such a plugin (`claude plugin
  uninstall --keep-data` then install), which is the only way to make the CLI re-copy it.
  Anything the check cannot answer - no `git`, no history, a commit pruned by a
  force-push - falls back to the previous CLI path. Regression suite:
  `scripts/_test/drift-detection.sh` (15 assertions over 7 scenarios, asserting on the
  bytes on disk and not only on what the script printed; sabotage-tested by
  reintroducing both original bugs).
- **`scripts/check-marketplace.py` + a `Marketplace` CI workflow.** Fails when a skill's
  files have changed since its version was last set - the bug above, caught in the repo
  instead of on users' machines - and checks every registration rule in `CLAUDE.md`:
  directories registered in `marketplace.json` and vice versa, required fields, `source`
  paths, no nested `marketplace.json`, `SKILL.md` frontmatter names matching their
  directories, `plugin.json` versions agreeing with the marketplace, the `SKILL_KEYS` /
  `SkillCatalog` catalogs in both install scripts matching in content and order, and a
  table row in each of the three catalog docs. Sabotage-tested against eight
  reintroduced faults. It also holds the two install scripts to `CLAUDE.md`'s rule
  that they are a matched pair: same menu keys, same order, same default flags, and
  the same entries in every sub-picker group - a mismatch there makes `--select 3,7`
  mean different things on Windows and Linux and silently invalidates every doc that
  names an item by number.
- **`scripts/check-powershell.ps1` + `scripts/_test/menu-groups.sh`.** The PowerShell
  script is Windows-only end to end, so a call to a function that does not exist parses
  cleanly, is never reached on a CI runner, and only fails on the one platform that
  matters - which is how a mis-named picker call got through review here and would have
  killed every sub-picker on Windows. `check-powershell.ps1` resolves every `Verb-Noun`
  call against the script's own functions and the available cmdlets, with a short,
  justified allowlist for names a runtime `Import-Module` supplies. `menu-groups.sh`
  covers the sub-picker catalogs, the `--<group>` spec parser and the parent-implication
  rule (32 assertions). Both were sabotage-tested; the menu suite caught a weakness in
  its own first draft, which asserted on the message a flag printed rather than on the
  row actually being installed.

### Fixed

- **Install scripts — installing this repo's skills took minutes, and every re-run
  warned about all of them.** Two problems compounded. First, `claude plugin update`
  was called with a bare plugin name; the CLI only accepts `name@marketplace` and
  rejects a bare name with `Plugin "<name>" not found`, so *every* update in a re-run
  failed and printed `'claude plugin update <name>' failed - keeping the installed
  version.` — 25 spawned CLI processes that could not have succeeded, plus 25 warnings
  that read like real breakage. Second, both scripts reloaded the entire plugin list
  (`claude plugin list --json`) after every single install, doubling the CLI spawns on
  a fresh run. `install_plugin` / `Install-ClaudePlugin` now compare the marketplace
  clone's HEAD commit against the commit Claude Code recorded for the installed copy
  (`installed_plugins.json`) and skip the update spawn entirely when they match, pass
  the fully qualified `name@marketplace` when they do not, and add a freshly installed
  plugin to the in-memory cache instead of re-reading the whole list. Both SHA lookups
  are file reads, and either one being unavailable (no `git`, an unreadable state file,
  a plugin installed from a different marketplace) reports "cannot tell" and falls back
  to the old CLI path. Measured on the 25-skill item: re-run 38.5s -> 5.8s, fresh
  install 51s -> 32s, and no spurious warnings.

- **`crew` 0.2.0 — the Windows hooks never ran.** `guard.sh` and `verify-gate.sh` exited 0
  on MSYS/MINGW to "defer" to `.ps1` twins, and the twins were registered with a
  `shell: powershell` field that Claude Code does not read — `verify-gate.ps1`,
  `context-watch.ps1` and `handoff-read.ps1` were referenced by nothing at all, and
  `handoff-write.ps1` did not exist. The net effect on Windows was a command guard that
  blocked nothing and a `Stop` gate that ran nothing, which reads as "the gate passed"
  rather than "the gate never ran". Each hook is now registered once as bash and hands
  control to its twin from inside the script (`crew_win_dispatch` in
  `hooks/scripts/_common.sh`, `exec` so stdin passes through); `handoff-write.ps1` has
  been written. Verified by test: `terraform apply -auto-approve` now exits 2 on Windows.
- **`crew` — the verification map silently skipped every root-level file.** `fnmatch` and
  PowerShell's `-like` both let `*` span `/`, so a `**/*.tf` rule demanded a literal slash
  and never matched `main.tf` — exactly the file a Terraform module keeps at its root.
  With `"unmapped": "fail"` that meant editing `main.tf` failed the gate *and* skipped
  fmt, validate and tflint. Both gate implementations now also test the `**/`-stripped
  form.
- **`crew` — a failing `Stop` check could pin the session.** `verify-gate.sh` never read
  stdin, so it could not see `stop_hook_active` and blocked its own retry. Both
  implementations now honour it.
- **`crew` — `python3` was a hard dependency** of five hook scripts, and Git Bash ships
  without it. They now resolve `python3`, then `python`, then `py`; `guard.sh` prefers
  `jq`. With none available the hook says so on stderr instead of failing open silently.
- **`crew` — `terraform-docs .` in the gate edited the tree it was gating.** The writing
  form rewrites `README.md`, making it a changed file with no rule on the next run, which
  trips `unmapped: fail` on the gate's own edit. Every example now uses
  `--output-check`, which fails on a stale README and writes nothing.
- **`crew` — `$LASTEXITCODE` was read after `Invoke-Expression`** in `verify-gate.ps1`.
  A cmdlet leaves the previous value in place, so a stale 0 read as a pass. It is now
  reset before each command and `$?` is checked alongside it.
- **`crew` — dead agent frontmatter.** `effort: high` (2 files) and `memory: project`
  (6 files) are not part of the subagent schema and were silently ignored, so
  `qa-reviewer` was not running at the high effort its file claimed. Removed.

- **`crew` — the command guard was judging bash with PowerShell rules on Windows.**
  Found by the second QA pass, and introduced by the first: dispatch branched on the
  OS, so a `Bash` tool call on Windows was handed to `guard.ps1`. That inverted the
  secret rule in both directions - it blocked the correct capture form
  (`DB_PASS=$(...)`) and let `vault kv get ... > secret.txt` through. Dispatch now
  branches on `tool_name`, which is what actually determines the language a command is
  written in. The other five hooks judge no command, are reached through `bash`, and
  no longer branch at all.
- **`crew` — the secret rule treated persistence as an exemption.** A `>` redirect or a
  `| tee` marked a command safe, so writing a secret to disk passed while printing one
  blocked - and the block message recommended a form the guard itself rejected. Both
  now block; the only exemption is assigning to a variable.
- **`crew` — the production guard matched `prod` as a substring**, blocking
  `aws s3 ls s3://my-product-images`, `select * from products` and
  `reproducible-builds`. Now a whole-token match. A guard people route around is not a
  guard.
- **`crew` — an ERE portability bug made the capture allowlist match nothing.** `\(`
  is a literal paren in POSIX ERE but a group opener in some greps ("Unmatched ( or
  \("). Bracket expressions are used instead.
- **`crew` — the verify loop could eat its own command list.** `eval "$c"` shared stdin
  with the `while read` over the here-string, so a check that reads stdin silently
  consumed the remaining checks. Now `</dev/null`.
- **`crew` — `context-watch.sh` called `python3` directly in six places**, every one
  suppressed with `2>/dev/null`, so on a host with only `python` the context warning
  silently never fired. It resolves once through `crew_py` and says so on stderr if
  there is none.
- **`crew` — `claude-md-audit.sh` required bash 4.** `declare -A` is a parse error on
  macOS's stock bash 3.2. Rewritten without associative arrays or process substitution.
- **`crew` — `_verify/run-all.sh --read-only` used a denylist.** An unmarked case ran
  against production; only a self-declared `# writes: yes` skipped it. It is now an
  allowlist - a case runs under `--read-only` only if it declares `# readonly: yes`,
  and skips are reported.
- **`crew` — `git branch --show-current` needs git 2.22+**, and the `|| echo 'not a git
  repo'` fallback made an older git look like a missing repo. Uses `rev-parse
  --abbrev-ref HEAD`.

- **`crew` — `/crew:reference`, the API and feature reference.** The code map answers
  "where does this live"; nothing answered "what can this system do, and how do I call
  it". `docs/reference/api.md` enumerates every endpoint with its auth, body, returns,
  **side effects, error responses and idempotency** - the parts that are not guessable
  from the name - and `docs/reference/features.md` covers the headless capabilities
  nobody documents: scheduled jobs and what a missed run does, queue consumers, admin
  scripts, feature flags. Every entry is anchored to `file:line` so it can be
  re-verified, `--audit` reports drift in both directions without rewriting anything,
  and unconfirmed entries are left visible as `undocumented - needs a human`. Wired
  into `/crew:onboard` as the second of four artifacts and owned by `crew:docs-writer`.

- **`crew` — promotion is now enforced by a hook, not by instructions.**
  `promote-gate.sh` (`PreToolUse`) fires on any command matching a declared `deploy`
  entry and refuses it unless, for the sha at HEAD, every `requires` environment has an
  all-pass row in `.work/PROMOTIONS.md`, the `rollback` runbook exists with
  `last verified` inside 90 days, `requireHuman` has an approval marker, and the tree is
  clean. `verify-gate.sh` additionally refuses to end a turn after a deploy that wrote
  no promotion row. What a hook still cannot see is the middle - that smoke, regression
  and verify actually ran after the deploy - and `/crew:promote` now says so explicitly
  rather than implying coverage.
- **`crew` — `resolve-tools.sh`: platform detection that adapts instead of just
  reporting.** It reads `.crew/verify.json`, extracts the first word of every command,
  and reports each tool as native, WSL-only, or missing. The WSL-only case is the
  expensive one: a bare `terraform validate` on a machine where terraform lives only
  inside WSL fails with "command not found", and the gate reports that as a *failed
  check* rather than a missing tool. Resolve once at setup, write `wsl.exe -e terraform`
  into the map, never branch at runtime.
- **`crew` — two more committed suites.** `setup-walkthrough.sh` builds a mixed-stack
  scratch repo and runs every script phases 0-8 invoke (32 assertions);
  `validate-prompts.py` checks all 16 commands, 9 agents and 14 skills for frontmatter
  that parses, tools that exist, referenced agents and paths that resolve, read-only
  agents that hold no write tools, and subagent-spawning commands that are permitted to
  (91 checks). Both sabotage-tested. Neither proves the prompts produce good work -
  only a live session on a real ticket does that.

- **`crew` — a committed regression suite for the hooks**,
  `hooks/scripts/_test/run-tests.sh`. 38 cases: 20 the command guard must block, 14 it
  must allow, plus the verify gate's root-level glob matching and its
  `stop_hook_active` exit. `guard.sh` shipped two real regressions in two review
  passes and both were found by running it rather than reading it, so the suite is
  itself sabotage-tested — reintroducing the substring `prod` match, the `>`-as-
  exemption secret bug, or removing the stop-loop check each turns it red.

### Removed

- **`crew` — `skills/crew-setup/templates/smoke.sh`**, orphaned by the `_verify/`
  restructuring and diverging from the new `--env`-aware interface.
- **`crew` — four duplicate trees.** `docs/README.md` was byte-identical to `README.md`;
  `examples/` was byte-identical to `skills/crew-setup/` and referenced by nothing;
  `docs/crew-howto.pdf` was a third copy of the README in an undiffable format; and
  `plugin/crew/.claude-plugin/marketplace.json` was a stub naming a nonexistent source,
  which this repo's `CLAUDE.md` already forbids. ~380 KB, no functional change.

### Added

- **`crew` — `/crew:promote <development|qa|production>`, with `--dry-run` and
  `--status`.** Promotion runs as five separate gates — pre-deploy, deploy, smoke,
  regression, post-soak verify — stopping at the first failure. Smoke and regression are
  deliberately distinct: smoke passing tells you the deploy landed and says nothing about
  the module three directories over that just broke. The sequence is declared in an
  `environments` block in `.crew/verify.json` rather than remembered, production requires
  a rollback runbook verified inside 90 days and explicit human approval, and every
  promotion appends a row — failures included — to `.work/PROMOTIONS.md`, which is the
  only honest answer to "is production running what qa signed off on". New setup Phase 8
  builds the block by asking what actually deploys each environment and what actually
  proves it worked.
- **`crew` — `_verify/` as the canonical home for checks.** Setup looks for `_verify/`
  first (then `qa/`, `spec/`, `_test*/`) and adopts an existing convention rather than
  duplicating it; where none exists it creates `_verify/` from a template carrying
  `README.md`, `smoke.sh`, `run-all.sh` and `cases/`. The README is part of the
  deliverable: a layout table for what each check covers and a status table for when each
  last proved it could fail. `/crew:verify` cross-checks it against `.crew/verify.json`
  and reports drift both ways — a script with no rule never runs, and a rule naming a
  script the README omits is a check nobody knows about. `scripts/smoke.sh` is still
  honoured; the gate checks `_verify/smoke.sh` first and falls back.
- **`crew` — promotion discipline in the CLAUDE.md templates.** Both the generic and the
  Terraform template now carry the judgment half: the fixed `development -> qa ->
  production` order, the same sha through all three, smoke *and* regression *and*
  post-soak verification after every deploy, no production deploy without a verified
  rollback, and a failed gate restarting the whole sequence rather than resuming.

- **A `plugin/` tree, and the `crew` plugin in it — the repo's first entry that is a
  plugin rather than a skill.** `crew` 0.2.0 is a virtual dev team for multi-repo legacy
  work: 9 context-isolated subagents, 16 slash commands, 14 bundled skills, and 7 hooks
  across 5 events (`PreToolUse`, `Stop`, `PreCompact`, `SessionStart`, `Notification`).
  Beyond the safety gates it now carries a handoff note across a `/clear` or an
  auto-compact, and watches context use. Roles
  exist only where they buy an isolated context window, a restricted tool set, or
  genuinely independent eyes — project management, BA, and architecture are files and
  commands, not agents. Codex QA, Jira, Obsidian memory, and Teams/Telegram notifications
  are all optional. Registered in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)
  with `source` `./plugin/crew`, so `claude plugin install crew@useful-claude-add-ons`
  works the same way a skill install does.
- **`plugin/README.md` — the plugins counterpart to `skills/README.md`**, with the same
  five-column overview table, inlined into the root `README.md` between
  `<!-- BEGIN plugin/README.md -->` markers exactly as the skills table is. It leads with
  the distinction that actually matters: a skill is a document Claude reads, whereas a
  plugin can register subagents, slash commands, and **hooks** — and a hook runs whether
  or not Claude agrees with it.
- **`plugin/PLUGINS.md` — the per-plugin reference the catalog points at.** `skills/` gets
  away with one file because a skill is one `SKILL.md`; a plugin is a bundle, so the
  catalog row cannot carry the detail. This is where every command, agent, bundled skill,
  and hook is listed, with the hooks first, because they are the only part that runs
  without being asked. It also records what is *not* wired: only `PreToolUse` pairs a
  `.sh` with a `shell: powershell` twin, so `verify-gate.ps1`, `context-watch.ps1`, and
  `handoff-read.ps1` sit on disk unreferenced and the `Stop` gate never fires on a
  Windows box with no `bash` on `PATH`. Documented rather than fixed — it is a change to
  `crew`'s runtime behaviour, not to its packaging.
- **Menu item 21, `This repo's plugins`, in both bootstrap scripts — off by default.**
  Appended at the end of the menu so items 1–20 keep their numbers and no existing
  `--select 3,7` invocation changes meaning. New `PLUGIN_KEYS` / `PLUGIN_NAME` arrays in
  the `.sh` and `$script:PluginCatalog` in the `.ps1` mirror the skill catalogs. The item
  adds this repo's marketplace itself, so it stands alone whether or not item 3 ran, and
  finishes by printing the per-repository setup (`/crew:init`, `/crew:onboard`,
  `/crew:verify`). It is unticked by default *on purpose*: every other menu row installs
  something Claude may choose to use, whereas `crew`'s `PreToolUse` hook blocks
  `terraform apply`/`destroy`, destructive DDL, force push, hard reset, and any command
  that would print a secret, and its `Stop` hook fails a turn whose checks go red. Those
  are deterministic and start the moment the plugin is enabled, which is not something a
  bootstrap run should add without the box being ticked.
- **A plugin registration rule in `CLAUDE.md`**, alongside the existing skill rule: the
  same four places, plus two that only apply to plugins — a hook-bearing plugin defaults
  to OFF in the menu, and every hook script ships in both `.sh` and `.ps1` flavours,
  because a bash-only hook is silently inert on Windows and reads as "the gate passed"
  rather than "the gate never ran".

### Fixed

- **Section-comment numbering in both install scripts had drifted by one from item 14
  onward** — `obsidian-mcp` was inserted at position 14 without renumbering the comments
  below it, so the block installing menu item 20 was labelled `# --- 19. Obsidian`.
  Comment-only; no behaviour change. Verified by parsing `MENU_KEYS`/`MENU_DEFAULT` out
  of the `.sh` and `$script:Catalog` out of the `.ps1` and diffing them: 21 keys each,
  same order, same defaults.

### Changed

- **`plugin/crew/.claude-plugin/plugin.json` no longer ships placeholder metadata** —
  its author was `{ "name": "you" }`. It now carries the repo's owner, homepage, and
  repository. A stray `plugin/crew/.claude-plugin/marketplace.json` naming a marketplace
  `my-marketplace` owned by `you` was removed: the repo root's marketplace is the only
  one here, and a nested one makes the plugin directory look like a second marketplace.

- **`claude-memories-vault` and `claude-memories-canvas` skills — the conventions of the
  `claude-memories` Obsidian vault, written on the workstation during the 2026-08-19
  memory migration and only now given a canonical home.** `claude-memories-vault` covers
  the folder layout, the six required frontmatter fields, the `type`/`status` value sets
  the `HOME.md` Dataview queries filter on, how wikilinks resolve by *filename* on Windows
  (a `:` cannot appear in one, so the link must match the file and not the prose), the
  `vault-lock.ps1` write lock the nightly gardener respects, the single-writer rule on
  `inbox/pending-reflect.md`, and the decision rule for vault versus Claude Code
  auto-memory. `claude-memories-canvas` covers the `wiki/maps` node and edge schema
  actually in use, the colour and id styles, the column-and-group geometry, and the two
  rules that make a canvas findable at all: facts live in notes because a canvas-only fact
  is invisible to search, and every canvas is linked from its `Project - *.md` because
  canvases do not backlink.

  Both keep the concrete `C:\repos\claude-memories` path rather than a placeholder — the
  same choice `vault-automation/` already makes with its `-VaultPath` default — because
  these are the conventions of one real vault and a parameterised version has never been
  tested. Both name their siblings explicitly in the `description`: the generic
  `obsidian-canvas` for any other vault, and `obsidian-vault-server` for hosting one.
  `obsidian-canvas` gained a matching one-line pointer back.

- **`obsidian-vault-server` skill — a self-hosted Obsidian vault on a headless Ubuntu
  host.** The real Obsidian desktop app in a container (Sync has no headless client, so
  there is no other way), signed in to an obsidian.md account, with the
  `obsidian-local-rest-api` plugin's built-in MCP endpoint reached over an SSH tunnel —
  no separate MCP server process. Three references cover install, the Claude wiring, and
  getting a workstation's plugins onto the server. The safety rails are the point: the
  container's web GUI has a terminal with passwordless `sudo`, so the skill treats
  firewalling it and never overwriting the REST API key as non-negotiable rather than
  advisory.

- **`claude-obsidian-setup/` now installs the Obsidian community plugin set.** The setup
  scripts installed *Claude Code* plugins but never the Obsidian plugins a working vault
  needs. `obsidian-plugin-profile.json` pins 15 community plugins with their repos plus
  the 27 core plugins to enable, and `install-obsidian-plugins.ps1` / `.sh` install them
  from GitHub releases. Same house contract as the setup scripts: dry run by default,
  `--apply` / `-Apply` to write, PASS/FIX/FAIL against stable check ids, idempotent.
  Additive — `community-plugins.json` and `core-plugins.json` are unioned with whatever
  the vault already enables, in both the list and object-map shapes. Verified on both
  platforms: 15/15 at pinned versions, second run all PASS, pre-existing entries kept.

- **Menu item: `obsidian-mcp` — register the Obsidian vault server's MCP endpoint.** Off
  by default, on both scripts, with identical keys and order. Not a launched command: the
  endpoint is a plugin already running in the vault-server container, listening on the
  *server's* loopback, so the URL is a local port forwarded by SSH. The API key is
  per-deployment and cannot be baked in, so without `-ObsidianMcpKey` /
  `--obsidian-mcp-key` the item explains how to get one and skips rather than failing.
  `Add-McpServer` / `add_mcp_http_server` gained header support for the bearer token.

- **`vault-automation/` — self-feeding vault pipeline.** New component that automates
  the Obsidian memory loop end to end: Claude Code `SessionEnd`/`PreCompact` hooks
  queue every session into `inbox/pending-reflect.md`; a nightly `Claude Vault
  Gardener` scheduled task runs headless Claude to distill queued sessions into
  source-cited `wiki/concepts` pages and `wiki/daily` digests (with a provenance pass
  that promotes well-attested concepts); a `HOME.md` Dataview dashboard surfaces
  stale/unsourced concepts and the live queue; five community plugins installed
  file-level. Obsidian-Sync-aware: git is an optional layer (`-UseGit`/`-GitRemote`)
  and the gardener skips git operations on git-less vaults. Dry-run by default,
  idempotent, documented in `vault-automation/README.md` (incl. run-the-gardener-on-
  one-machine-only and cost/safety notes). Root README gained a "Vault automation"
  section with the run commands.

### Fixed

- **`install-prerequisites.sh` aborted on startup with `MENU_DEFAULT[$_i]: unbound
  variable`.** The `obsidian-mcp` menu item was added to `MENU_KEYS` but never to the two
  arrays that run parallel to it, leaving 20 keys against 19 defaults and 19 names. Under
  `set -u` the `MENU_STATE` initialiser walked off the end of `MENU_DEFAULT` and killed
  the script before it drew anything, so *no* item could be installed on Linux — not just
  the Obsidian one. `MENU_NAME` was short in the same way, and because the gap sat at
  index 13, every label from `obsidian-mcp` onward was displaying the *next* item's text:
  row 14 read "Supabase plugin", row 19 read "Strix", and row 20 had no label at all.
  Both arrays now carry all 20 entries, matching `$script:Catalog` in the `.ps1` key for
  key, name for name, and default for default.

  The menu-numbering fallout was documentation-only but wide: `README.md` and
  `INSTALLATION.md` both still described a 19-item menu, so every reference to items
  14–19 was off by one from the moment `obsidian-mcp` landed. Renumbered to 15–20, with
  the item itself now documented in the menu table, the "what each item installs" table,
  the MCP-servers walkthrough, and the switch table — `--obsidian-mcp-url` and
  `--obsidian-mcp-key` had never been listed there either.

- **The installers' skill catalogs had fallen two skills behind the marketplace.**
  `obsidian-canvas` and `obsidian-vault-server` were registered in
  `.claude-plugin/marketplace.json` and `skills/README.md` but never added to
  `SKILL_KEYS`/`SKILL_NAME` in `install-prerequisites.sh` or `$script:SkillCatalog` in
  the `.ps1`, so the per-skill picker offered 21 of the 23 that existed and neither could
  be selected by name. Both were also missing from the `<!-- BEGIN skills/README.md -->`
  mirror in the root `README.md`, which had silently stopped being a mirror. Both are in
  the catalogs and the mirror now, alongside the two new
  `claude-memories-*` skills, and the hard-coded counts in `README.md` and
  `INSTALLATION.md` — plus the stale "all nineteen" in both installer headers — now read
  25, matching the directory count, the marketplace manifest, and both catalogs.

- **`claude-obsidian-setup` — a Python below the 3.11 floor is now repaired rather than
  only reported.** Both scripts previously stopped with "install python3.11+ yourself" on
  any distro whose `python3` predates 3.11. That was over-broad: it treated the hardest
  case as if it were the only one. They now, in order, (1) use a newer versioned
  interpreter that is already installed, (2) install one — `python3.13`/`3.12`/`3.11` —
  from the repositories **already configured on the machine** and use it alongside the
  untouched system `python3`, or (3) stop with the concrete remedy. `update-alternatives`
  is never touched and no third-party repository is ever added, so the original objection
  still applies to the only case it was ever true of.

  Every downstream invocation now runs through a selected-interpreter variable rather than
  a hardcoded `python3`. Verified by putting a stub `python3` reporting 3.10 first on
  `PATH`: the script found the real `python3.12`, used it, and produced a complete 14-file
  vault with `doctor ok` and `lint 0 issues`.

- **`claude-obsidian-setup/setup-claude-obsidian.sh` creates the product checkout's parent
  explicitly.** `git clone` does create missing parents — this was verified, and the review
  finding that claimed otherwise was wrong — so nothing was broken. The `mkdir -p` removes
  the dependency on that behaviour and makes an unwritable root fail obviously.

### Added

- **Menu item 19 — Obsidian desktop + `claude-obsidian` and `obsidian-skills`
  plugins.** Off by default, on both scripts, with identical keys, order, and default
  flags. The app is not on npm, so it installs from a package manager: Chocolatey then
  winget on Windows, flatpak then snap on Linux — distro repositories generally do not
  carry it. Chocolatey needs elevation; without it the app is skipped with a warning and
  the two plugins still install. The item then registers
  `AgriciDaniel/claude-obsidian` (the vault engine: transactional writes, provenance
  ledgers, deterministic lint, the `/claude-obsidian:*` skills) and
  [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) (Obsidian's own
  upstream references for Obsidian Flavored Markdown, Bases, JSON Canvas, the Obsidian
  CLI, and Defuddle).

  The item deliberately stops there. Creating a vault writes to disk under a reviewed
  transaction, so it is a separate, explicitly previewed step rather than a side effect
  of a bootstrap run. `--obsidian-repo-root` / `-ObsidianRepoRoot` sets the root the item
  suggests for it (default `C:\repos` on Windows, `~/repos` on Linux).

- **`claude-obsidian-setup/` — vault setup for Windows (WSL) and Linux.** A matched pair
  of installers that bring both platforms to the same claude-obsidian standard, plus a
  README. Dry-run by default, idempotent, `PASS`/`FIX`/`FAIL` per check against stable
  check ids, non-zero exit on failure, and a closing `doctor` + `lint` against the new
  vault. Vault creation follows the product's own preview-then-apply contract: run the
  plan, read back its `approved_plan_sha256`, pass that exact hash to `--apply`.

  Everything hangs off one root — `C:\repos` / `~/repos` — so `-RepoRoot` /
  `--repo-root` relocates the vault and the product checkout together;
  `-VaultPath`/`--vault` and `-ProductRoot`/`--product` override either half.

  The Windows script exists mostly to repair four failures that are otherwise silent and
  hard to diagnose:

  1. **Native Windows cannot write to a vault at all.** Mutation safety is bound to POSIX
     directory descriptors and `fcntl.flock`; native Python has no `fcntl`, so the core
     refuses every write with `UNSUPPORTED_PLATFORM`. Reads and dry-runs work natively —
     writes are routed through WSL, which is why the vault is created from inside it.
  2. **`python3` resolves to a Microsoft Store stub.** Windows ships no `python3.exe`, so
     the name hits the App Execution Alias and prints an install advert instead of running
     Python — breaking the plugin's `SessionStart`/`Stop` hooks and every documented
     `python3 …` command. Fixed with a hard link `python3.exe → python.exe`.
  3. **`/mnt/c` mounts without `metadata`.** DrvFs then rejects `chmod` with `EPERM` and
     every apply dies with `CORRUPT_RUNTIME_STATE: cannot write confined bundle copy`.
     This cannot be fixed by remounting live; it needs an `[automount]` stanza in
     `/etc/wsl.conf` and a full `wsl --shutdown`. The existing file is backed up first.
  4. **Git identity does not cross the WSL boundary.** `checkpoint` runs inside WSL, where
     Windows' `git config --global` is invisible, so it fails `GIT_FAILED: Author identity
     unknown`. Fixed by setting identity repo-locally, which both environments read.

### Fixed

- **Both install scripts — Superpowers came from a second marketplace and could land
  disabled.** Item 4 registered `obra/superpowers-marketplace` unconditionally, but
  `install_plugin` / `Install-ClaudePlugin` detect plugins by *bare name*. On any machine
  that already had `superpowers@claude-plugins-official` — which items 6 and 7 register —
  the install was skipped, leaving an orphaned `superpowers-marketplace` registration and
  a second, disabled `superpowers@superpowers-marketplace` entry: exactly the duplicate
  [`skills/claude-code-tuneup`](skills/claude-code-tuneup/references/symptoms.md) tells you
  to clean up. Item 4 now takes Superpowers from `anthropics/claude-plugins-official`, the
  marketplace the scripts already register elsewhere, so there is one source for it.

  Superpowers for Claude Code is plugin-only by design and cannot be installed by copying
  `skills/` into `~/.claude/skills/`: its `SessionStart` hook resolves
  `${CLAUDE_PLUGIN_ROOT}`, which only exists for plugins, and that hook is what injects
  `using-superpowers` and makes the other skills fire. Six of the fourteen skills also
  cross-reference each other as `superpowers:<name>`, which unprefixed personal skills
  would break.

  Existing machines keep the stray `superpowers-marketplace` registration — the scripts
  deliberately do not remove marketplaces, since a bootstrap installer should not delete
  something a user may have added on purpose. Drop it with
  `claude plugin marketplace remove superpowers-marketplace`.

- **Both install scripts — an installed-but-disabled plugin is now switched back on.**
  Installing a plugin and having it load are different things: a plugin disabled in
  `settings.json` is installed, at the right scope, and completely inert. New
  `ensure_plugin_enabled` / `Enable-ClaudePlugin` run on the *already-installed* paths
  (update and already-current skip) and call `claude plugin enable --scope` when no enabled
  copy of the name exists. Best-effort by design — the plugin is installed either way, so a
  failure warns instead of failing the step.

  **Not** called after a fresh install: `claude plugin install` already enables what it
  installs. The first cut of this called it there too, which broke a brand-new machine —
  a just-installed plugin can still read as disabled in `claude plugin list --json`, so
  every plugin in the run got an enable attempt, and the CLI's benign "already enabled at
  user scope" reply was reported as a failed step. 18 of them on one run.

  Three separate defects behind that, all fixed:

  - `Enable-ClaudePlugin` used `2>$null` with no `try`/`catch`. Under
    `$ErrorActionPreference = 'Stop'` a native command's stderr line — or any non-zero exit
    when `$PSNativeCommandUseErrorActionPreference` is `$true` — becomes a *terminating*
    error, so `Invoke-Step` marked the step failed. The same hazard is already documented
    at the Claude Code update check. Both preference variables are now shadowed
    function-locally, and the whole call is wrapped, so this function cannot throw.
  - Success was judged from the CLI's message. It can't be: `claude plugin enable` reports
    "is already enabled at user scope" even for a plugin that does not exist. Both scripts
    now judge the outcome from `claude plugin list --json` instead.
  - The bash version was a silent no-op. `local spec="$1" name="${spec%%@*}"` doesn't work
    — bash declares every name in a `local` before expanding the values, so `$spec` read
    the empty new local and `name` was always empty. Assigned on its own line now, matching
    the existing style in `install_plugin`.

- **`install-prerequisites.ps1` — a disabled duplicate could mask an enabled plugin.**
  `Get-ClaudePlugins` keys its map on the bare name with last-write-wins, so with both
  `superpowers@claude-plugins-official` (enabled) and `superpowers@superpowers-marketplace`
  (disabled) installed, the disabled copy won on id sort order and the plugin was reported
  as disabled. An enabled entry now wins over a disabled one.

- **`install-prerequisites.sh` — `json_query` output is stripped of trailing `\r`.** Under
  Git Bash / WSL interop on Windows both `jq` and `python3` emit CRLF, leaving a stray
  carriage return on the last tab-separated field. Every caller compares that field exactly
  (`"$enabled" = "1"`, `"$repo" = "$id"`), so `marketplace_installed` could miss a
  marketplace matched by repo, and the new enablement check read every plugin as disabled.

### Added

- `skills/notify` — **two-way Telegram now works in both directions.** `--wait` only ever
  covered replies to a question Claude asked; a message the user sent on their own
  initiative was thrown away twice over. The dispatcher's `_on_message` dropped anything
  that matched no pending question, and direct mode fast-forwarded its `getUpdates`
  offset past everything already queued before it started listening — so a message typed
  while Claude was busy, or between questions, was silently discarded.

  New `scripts/inbox.py` is the store both halves share: `<spool>/inbox.jsonl` for
  inbound messages and `<spool>/state/offset.json` for the `getUpdates` offset. The
  offset has to be shared rather than per-process because Telegram answers a second
  concurrent `getUpdates` with `409 Conflict` — the daemon owns polling when it is up,
  the client polls only when it is not, and either way the next read resumes where the
  last one stopped.

  `notify.py --inbox` hands Claude what is waiting (exit 0 with messages, 5 without, so
  it works as a "did they say anything?" check in a loop), `--peek` leaves them
  unconsumed, `--wait` blocks for up to `--timeout` seconds, and `--job` filters to one
  topic. A read consumes what it returns, so no message is delivered twice. In topics
  mode the arriving thread is reversed through `topics.json` to attribute the message to
  the right job.

  Appends guard against a fused record: a write killed mid-line leaves no trailing
  newline, and appending onto it would produce one unparseable line and lose the *new*
  message as well as the broken one, so `append()` closes the dangling line first.

- `skills/claude-code-tuneup` — audits a Claude Code installation for what is making it
  slow or bloated and hands back a ranked cleanup plan. `scripts/cc_audit.py` (stdlib
  only, read-only) inventories every settings file in scope, loose skills in
  `~/.claude/skills/` against skills provided by installed plugins, `enabledPlugins`,
  hooks from both settings *and* every plugin's `hooks/hooks.json`, subagents, rules
  files, `CLAUDE.md` sizes, MCP servers, marketplaces, and the plugin cache.

  It catches the duplicate-install case in **both** plugin layouts — a plugin bundling
  `skills/<name>/SKILL.md`, and a plugin whose root *is* the skill, which is what this
  repo's own marketplace publishes. Missing the second layout is why a naive check finds
  none of this repo's skills duplicated. Duplicates are labelled
  `plugin@marketplace`, because the same plugin name published by two marketplaces is
  exactly the case worth catching, and a loose copy shadowing a *disabled* plugin is
  reported separately from one shadowing an enabled plugin — only the latter costs
  context.

- **Menu item 9 (claude-mem) now installs Bun.** claude-mem's hooks run its worker under
  Bun (`package.json` declares `engines.bun >= 1.0.0`) via `scripts/bun-runner.js`, which
  resolves the interpreter with `where`/`which bun` and only then falls back to
  `$HOME/.bun/bin/bun`. Neither install script ever installed it and the plugin's own
  hooks cannot bootstrap it, so on a fresh machine every claude-mem hook failed with
  "Bun not found". Windows uses `choco install bun` when Chocolatey is present *and* the
  run is elevated — the shim lands a real `bun.exe` on `PATH`, which is what
  `bun-runner.js` looks for first — and falls back to bun's per-user installer
  otherwise, since that needs no Administrator rights and writes the documented
  fallback path. Linux prefers `npm install -g bun` (keeping bun on the same `PATH` as
  node) and falls back to `bun.sh/install`; no distro ships a bun package, so there is
  no `as_root` path. Both halves detect first: an existing bun, however it was
  installed, is left alone.

### Removed

- **Perplexity MCP server** — dropped from both install scripts. It was menu item 13
  (off by default), the only row that needed an API key, so the whole up-front key
  prompt goes with it: `read_mcp_api_key` / `read_mcp_api_keys` and `PERPLEXITY_KEY`
  in the `.sh`, `Read-McpApiKey` / `Read-McpApiKeys` and `$script:ApiKeys` in the
  `.ps1`. Every remaining row now installs without asking for anything mid-menu.

  **Menu numbers below it shift by one on both platforms**: MCP servers are 11–13,
  Supabase 14, Context7 15, Playwright CLI 16, SkillUI 17, Strix 18. Scripted runs
  that pass positions (`--select 15,19`) need updating; the stable keys
  (`--select supabase,strix`) were unaffected and remain the better habit. The
  `perplexity-mcp` key itself is gone, so a run that names it now selects nothing for
  that token. An already-registered `perplexity` server is left alone — remove it by
  hand with `claude mcp remove perplexity` if you want it gone.

- `skills/ppt-master` — a vendored copy of the upstream `hugohe3/ppt-master` plugin
  (12,230 files, 88 MB) that was never registered in `marketplace.json`, either
  README, or either install script's skill catalog, so nothing here ever offered it.
  The installer already installs the same plugin from its own marketplace as part of
  menu item 6 (Community marketplaces + plugins), so removing the copy changes nothing
  for anyone running the bootstrap — it just stops the repo carrying 88 MB of upstream
  code it would have to re-sync by hand. This also clears the Pylint CI failure: 845
  of the 855 findings were in that tree.

### Added

- `skills/notify` — **a body over Telegram's 4096-character limit now splits across
  several messages** instead of failing the send. `tg.split_body()` breaks on a
  newline where it can, then a hard cut, and it splits the *raw* text before
  HTML-escaping so a break can never land inside an `&amp;` entity and invalidate
  the message. Whitespace is preserved exactly — rejoining the parts reproduces the
  input byte for byte. Parts are headed `(1/3)`, `(2/3)`, …

  The budget is computed against the **assembled** message, not the body chunk
  alone. Each part carries a `<b>subject (cont.) (2/3)</b>` header, the subject is
  caller-supplied, and escaping can grow it 5×, so a fixed reserve was not enough —
  a 300-character subject produced a 4,346-character message that Telegram would
  have rejected. The header cost is now measured per call and a pathological subject
  is truncated rather than eating the whole budget.

  Buttons go on the last part only, and `send_message()` returns that last message,
  so `notifyd`'s `message_id → req_id` correlation still resolves a button tap or a
  reply to the final part. Replying to an *earlier* part is not indexed and falls
  back to the newest open question in that topic. Parts are spaced one second apart
  to stay under Telegram's per-chat rate limit; `--dry-run` reports the part count.

### Fixed

- `skills/notify/scripts/notify.py` — stdout and stderr are reconfigured to UTF-8 with
  `errors="replace"` at startup. On a Windows console (cp1252) printing a body that
  contained any non-ASCII character — an em dash, an emoji, non-Latin text — raised
  `UnicodeEncodeError` and killed the run, which made `--dry-run` unusable for exactly
  the messages worth checking before sending.

- `skills/notify/scripts/*.py` — the four config reads now pass `encoding="utf-8"` to
  `Path.read_text()`. Without it Python picks the locale encoding, which is cp1252 on
  Windows, and a UTF-8 `config.json` then fails in one of two ways depending on the
  character. Most non-ASCII text decodes silently wrong: an em dash (`E2 80 94`)
  becomes `â€”` in the message that gets sent. Text whose UTF-8 bytes include one of
  the five undefined cp1252 positions (`81 8D 8F 90 9D`) raises `UnicodeDecodeError`
  and takes the run down — Japanese `あ` is `E3 81 82`, so a config with CJK in it
  crashes outright. Both are Windows-only. Also split the comma-form imports and
  wrapped two over-length lines, so `pylint $(git ls-files '*.py')` is back to
  10.00/10.

### Added

- `skills/notify` — a new skill (1.0.0) that pings you out of band about a session or
  job: a two-way Telegram bot (a `question` event blocks until you reply from your
  phone, and a `notifyd` dispatcher gives each concurrent job its own forum topic) or
  email over SMTP or an M365/Gmail MCP connector. Registered in `marketplace.json`,
  both READMEs, `INSTALLATION.md`, and both install scripts, taking this repo's
  catalog from 19 skills to 20.

- `scripts/install-prerequisites.ps1` / `.sh` — **the `notify` skill asks about setup.**
  It is the only skill here that needs anything on the machine, so ticking it prints
  its prerequisites alongside the menu (Python 3.8+, a `@BotFather` token, a `chat_id`,
  `TELEGRAM_BOT_TOKEN` exported, a config file, polling mode with no webhook) and then
  asks whether to scaffold `~/.config/notify/config.json`. Answering yes checks for
  Python and writes a starter config; it never overwrites an existing one and never
  writes the bot token anywhere. `--notify-setup` / `-NotifySetup` answers yes without
  asking; `--all` / `--non-interactive` prints the prerequisites and skips the
  scaffold. Because `notify` is a sub-picker entry rather than a top-level menu key,
  the gate reads the skill catalog (`skill_selected` / `Test-SkillSelected`) instead of
  `is_selected` / `Test-Selected`, which would never match.

- `CLAUDE.md` — repo-level instructions for Claude Code. Two documentation rules are
  stated as requirements rather than suggestions: an edit to either install script
  must update `README.md` (menu table, "what each item installs" table, switch table,
  and any prose that names an item by number) in the same change, and a new directory
  under `skills/` is not finished until it is registered in all four places —
  `marketplace.json`, `skills/README.md`, `README.md`, and both install scripts.

- `scripts/install-prerequisites.ps1` / `.sh` — **the Claude Code CLI row now checks
  for an update** when `claude` is already installed, instead of reporting the version
  and moving on. It compares the local version against the npm registry and runs
  `npm install -g @anthropic-ai/claude-code@latest` only when they differ. The version
  is read from the last line of `claude --version` (which prints
  `2.1.226 (Claude Code)`, and can be preceded by a wrapper's banner).
  `-NoUpdate` / `--no-update` reports the installed version and skips the check.

- `scripts/install-prerequisites.ps1` / `.sh` — **five new opt-in menu items**:
  - **Supabase** (15) — `supabase@claude-plugins-official`, through the same
    detect-then-install helper as every other plugin.
  - **Context7** (16) — `npx -y ctx7@latest setup`. The wizard is interactive, so bash
    hands it the terminal explicitly (under `curl | bash`, fd 0 is still the script);
    with no terminal at all both scripts print the command rather than hang.
  - **Playwright CLI** (17) — `npm install -g @playwright/cli@latest`, detected by
    whether `playwright-cli` already resolves on `PATH`.
  - **SkillUI** (18) — `skillui`, plus `playwright` and its Chromium build. Playwright
    is installed **globally**; upstream's `npm install playwright` would leave a
    `node_modules` tree in whatever directory the script was run from. Both Playwright
    steps warn rather than fail the item. A quick start is printed afterwards; you're
    asked up front, and `--skillui-guide` / `-SkillUIGuide` answers yes without asking.
  - **Strix** (19) — upstream's own installer, `curl -sSL https://strix.ai/install |
    bash`. Installing it is not enough to run it, so the next steps (Docker running,
    `STRIX_LLM`, `LLM_API_KEY`) print on every run, including one that skipped the
    install. Windows has no POSIX shell, so the script runs the installer through WSL,
    falls back to Git Bash, and warns with the manual command if neither exists.

- `scripts/install-prerequisites.ps1` / `.sh` — the install menu is now a **cursor
  picker**: ↑/↓ to move, Space to tick, Enter to start, `A`/`N`/`D` for all/none/
  defaults, `Q` or Escape to cancel. Rows scroll inside a viewport when the window
  is short, and every printed line is clipped to the window width, because a
  wrapped line breaks the redraw and smears the menu over whatever was above it.
  The numbered prompt is still there as the fallback and is chosen automatically
  when raw key input is not possible — no terminal, no `stty`, `TERM=dumb`,
  PowerShell ISE, a redirected console, or a window under ten lines. Bash restores
  the saved `stty` state and the cursor from an `EXIT`/`INT` trap so Ctrl-C in the
  menu cannot leave the user's shell with echo off.

- `scripts/install-prerequisites.ps1` / `.sh` — **individual skills can be
  installed instead of all nineteen**. Pressing → on the repo's row opens a second
  picker listing every skill in this repo; `-Skills 'cloudflare,drata'` /
  `--skills cloudflare,drata` does the same non-interactively and also accepts
  `all`, `none`, and positions (`1,4-6`). It composes with `-All` /
  `-NonInteractive`, so CI can install everything except the skills, or only the
  skills. The catalog (`SKILL_KEYS` in bash, `$script:SkillCatalog` in PowerShell)
  is now the single source of both the picker rows and the install loop, replacing
  the duplicated `own_plugins` / `$ownPlugins` arrays. The repo's menu row shows a
  live count (`+ 3 of 19 skills`) rather than a hardcoded nineteen.

- `skills/infra-work-ticketing` — `ticketctl.py` gained **`update`** and
  **`close`**, so the API fallback covers all four write verbs rather than just
  `create` and `note`. `update` sets title, status, priority, category,
  subcategory, group, technician, urgency, impact, type and (on SDP) the
  resolution and an `--update-reason` for the audit trail; `close` takes a closure
  comment, `--closure-code`, and `--requester-ack`. On Jira, `close` looks the
  transition up by name from the issue's own transition list rather than
  hardcoding an id, and `--category` maps to a component — the nearest equivalent
  Jira has. Both go through the same build/execute split as the existing verbs, so
  `--dry-run` covers them.

  Two limits are documented rather than papered over. **Closing through
  `ticketctl.py` is not equivalent to `sdp_close`**: SDP Cloud v3 has no close
  sub-resource, so the fallback PUTs a terminal status plus `closure_info` to the
  edit endpoint and a desk with mandatory closure rules can reject it. And
  **nothing can create or rename a category** — the v3 API documents no endpoint
  for the taxonomy and the connector's metadata tool is read-only, so that stays
  an SDP admin-UI job. Setting the category on a ticket works from either path.

- `skills/infra-work-ticketing` — an `mcp` block in the config file records how
  ticket writes are routed: connector name, endpoint, tool prefix, whether to
  prefer MCP, and which `ticketctl.py` provider takes over when it refuses.
  `ticketctl.py doctor` prints the resolved routing and probes the connector's
  `/health` (5-second timeout, `--no-mcp-probe` to skip). Routing metadata only —
  the connector authenticates per person through Claude Code, so no credential
  belongs in the block. `INFRA_TICKET_PREFER_MCP` and `INFRA_TICKET_MCP_ENDPOINT`
  override it per session.

### Removed

- `scripts/install-prerequisites.ps1` / `.sh` — **six menu items**: the Firecrawl,
  Chrome DevTools, and Glyphs MCP servers, the OmniRoute gateway, Headroom, and GSD.
  The helpers that existed only for them went with them: `tcp_port_open` and
  `add_mcp_http_server` in bash, `Test-TcpPort`, `Get-PythonLauncher`,
  `Add-UserScriptsToPath` and `Get-PipxPythonArgs` in PowerShell, along with the
  `FIRECRAWL_API_KEY` prompt, the OmniRoute guided-setup question, and the Headroom
  mode question. The `-HeadroomMode` / `--headroom-mode` switch is gone.

  The menu is 19 items rather than 20, and items 1–10 are the default set (was 1–11).
  Item numbers below 10 are unchanged; everything above shifted. Scripted runs should
  use the stable keys (`--select supabase,strix`) rather than positions.

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — the per-skill picker's descriptions are
  fuller: each of the nineteen rows now names what the skill actually does rather than
  restating its title (`cloudflare - Cloudflare v4: DNS, WAF, cache, Workers, Zero
  Trust`). Text is sourced from the skills table in `README.md`. The rows are written
  for a window of about 95 columns; narrower consoles clip them with an ellipsis, as
  they already did for the longest of the old labels.

### Fixed

- `skills/infra-work-ticketing` — a `ticketctl.py` write that failed while
  *planning* rather than sending was not queued, so the text was lost. Resolving
  `#40219` to an internal id is itself an API call, which means a down service desk
  failed in exactly that window. Planning is now inside the guarded region for
  `note`, `update` and `close`. `--dry-run` still never queues.

- `scripts/install-prerequisites.ps1` / `.sh` — a picker that failed *after* the
  capability gate passed did not fall back. In bash the failure return was ignored,
  leaving an empty selection that printed `Nothing to do.` and exited 0 — the same
  output as a deliberate cancel. In PowerShell, `$ErrorActionPreference = 'Stop'`
  meant a `SetCursorPosition` throw (a window shrunk between frames) killed the
  whole installer. Both now drop through to the numbered menu and say why. The
  capability gate only ever proved the picker could *start*.

- `scripts/install-prerequisites.sh` — the `/dev/tty` probe printed
  `No such device or address` to stderr on hosts without a controlling terminal.
  The redirection is now grouped so `2>/dev/null` actually covers it.

- `scripts/install-prerequisites.ps1` — hiding the cursor threw
  `"The handle is invalid"` on hosts that don't implement `Console.CursorVisible`,
  which would have taken the whole menu down with it. It is cosmetic, so it is now
  best-effort.

- `skills/visio-diagrams` — creates, edits, and verifies Microsoft Visio `.vsdx`
  files. Two paths from one spec: a stdlib-only writer (`vsdx_writer.py` +
  `diagram_from_spec.py`) that generates a native `.vsdx` plus an SVG preview
  with no Visio install and no third-party packages, so it runs in CI and on
  air-gapped boxes; and PowerShell COM automation (`New-VisioDiagram.ps1`) for
  real stencil masters, themes, containers, and swimlanes. Also covers reading
  and retitling an existing `.vsdx` via the `vsdx` package (the template + data
  pattern that preserves corporate stencils). Leads by challenging whether Visio
  is the right output at all, and refuses to call a file verified when
  `verify_vsdx.py` could only check OPC structure. Two reference files (`.vsdx`
  OOXML format and symptom → cause table, COM automation). Registered in
  `.claude-plugin/marketplace.json` and both install scripts — 19 skills total.

- `skills/claude-code-defaults` — configures how Claude Code itself behaves by
  default. Separates instructions (`CLAUDE.md`, `.claude/rules/`, loaded into
  context) from enforcement (`settings.json`, permission `allow`/`ask`/`deny`,
  hooks, applied by the client), and routes a request to the right file at the
  right scope — user, project, local, or managed. Inventories existing config
  and merges rather than clobbering, backs up before editing, validates the JSON,
  and verifies via `/status`, `/context`, and `/doctor`. Four reference files
  (permissions, CLAUDE.md, settings keys, copy-paste templates for solo/shared/
  locked-down/fleet). Refuses to hand out `bypassPermissions` as a default.
  Registered in `.claude-plugin/marketplace.json` and both install scripts —
  18 skills total.

- `scripts/install-prerequisites.ps1` / `.sh` — the VoltAgent
  [`awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents)
  collection is now installed as plugins from its own marketplace
  (`voltagent-subagents`), all ten category plugins: `voltagent-core-dev`,
  `-lang`, `-infra`, `-qa-sec`, `-data-ai`, `-dev-exp`, `-domains`, `-biz`,
  `-meta`, `-research`.

- `scripts/install-prerequisites.ps1` — `-InstallScope` (aliased to the old
  `-PluginHubScope`) now applies `--scope` to *every* marketplace and plugin
  install, not just the community set. Same for `--scope` on the Linux script.

- `skills/terraform-docs-readme` — regenerates a Terraform module's `README.md`
  with `terraform-docs`. Covers first-time setup (`.terraform-docs.yml`, the
  `main.tf` narrative header block, `footer.md`, the `BEGIN_TF_DOCS`/`END_TF_DOCS`
  injection markers) as well as re-runs after variables, outputs, or resources
  change, and diagnoses the usual failures — missing markers, a header that
  isn't picked up, a footer that isn't rendered, a version older than 0.16.
  Ships a stdlib-only, read-only preflight script and copy-ready assets.
  Registered in `.claude-plugin/marketplace.json` and in both install scripts.

- `skills/cisco-meraki` — Cisco Meraki Dashboard API v1 skill for a single
  organization, covering MX/MS/MR. Reads inventory, device status, the network
  event log, the org configuration change log, MX security/IDS events, and Air
  Marshal; runs live diagnostics (ping, cable test, throughput, ARP/MAC table,
  wake-on-LAN); and makes configuration changes behind a snapshot → diff →
  confirm gate with single-command rollback. Bulk changes route through staged
  Action Batches so Meraki validates the payload server-side before commit.
  Stdlib-only Python, no pip install. Includes the repo's first unit test suite
  (`python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py"`).

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — **all marketplace and plugin
  installs now use the native `claude plugin marketplace add` and `claude plugin
  install` commands.** The `npx -y claudepluginhub <repo>` wrapper is gone, along
  with the `Invoke-PluginHub` / `pluginhub` helpers that called it. The wrapper
  registered each repo as a *local directory* marketplace under a generated name
  (`cpd-<repo>-user`) that the scripts' own detection could not match, so those
  plugins were reinstalled on every run, and it was a recurring source of Windows
  failures. Marketplace names are now taken from each repo's own
  `.claude-plugin/marketplace.json` — notably `fcakyon/claude-codex-settings`
  publishes itself as `claude-settings`, which the old name-or-repo detection
  never matched either.
- `scripts/install-prerequisites.ps1` / `.sh` — claude-mem installs through its
  marketplace (`claude plugin marketplace add thedotmack/claude-mem` +
  `claude plugin install claude-mem@thedotmack`) instead of
  `npx claude-mem install`. Upstream documents both paths. `find-skills` and GSD
  still use `npx`: neither publishes a Claude Code marketplace.
- `MARKETPLACE.md` / `INSTALLATION.md` — bootstrap command lists rewritten to
  match, with the repo-name-vs-marketplace-name trap called out explicitly, and
  a troubleshooting row for leftover `cpd-*-user` marketplaces.

### Removed

- `scripts/install-prerequisites.ps1` — the `Resolve-GitRoot` and
  `Register-GitBash` helpers, plus the `C:\repos\awesome-claude-code-subagents`
  clone and its `bash install-agents.sh` invocation. Its Linux counterpart
  (`~/repos/...` clone) is gone too. That step needed Git Bash on Windows and so
  failed outright on a non-elevated run, where Chocolatey — and therefore `git` —
  had already been skipped. An existing checkout from an earlier run is now
  unused and safe to delete.
- `aiskillstore/marketplace` and its `xlsx` / `mcp-integration` entries. That
  repo is the Skill Store content repo, not a Claude Code marketplace (no
  `.claude-plugin/marketplace.json`), so there is no native
  `claude plugin install` for it. `anthropic-office-skills@claude-settings`
  replaces `xlsx`; either skill can still be installed by hand with
  `npx skillstore add aiskillstore/<skill>`.

- `scripts/install-prerequisites.ps1` / `.sh` — the `find-skills`
  (`vercel-labs/skills`) step is now prompted rather than unconditional, and is
  detected before it runs. It installs as a user-level skill, not a Claude Code
  plugin, so detection is a filesystem check on
  `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/find-skills/SKILL.md`. Already
  installed: the prompt offers a re-install for updates; `-NoUpdate` /
  `--no-update` skips it entirely. The step now also verifies the skill actually
  landed on disk instead of trusting the installer's exit code.

### Fixed

- `skills/terraform-docs-readme` arrived double-nested
  (`skills/<name>/<name>/SKILL.md`) with a leftover `terraform-docs.zip` and a
  zip-oriented `INSTALL.md` — the same layout problem fixed for `aws-opensearch`
  and `intune-graph` in the 2026-07-28 baseline. Flattened to the standard
  `skills/<name>/SKILL.md` layout; the duplicate tree, the archive, and the
  now-inaccurate `INSTALL.md` were removed (installation for this repo's skills
  is covered by `INSTALLATION.md` and `MARKETPLACE.md`).
- `INSTALLATION.md`'s "What the own-marketplace step installs" list was stale at
  10 skills and missing `cisco-meraki`, `infra-work-ticketing`, `repo-docs`,
  `shipstation`, `web-testing-playwright`, and `work-log-reporter`. Now lists all
  17, matching `marketplace.json`, `skills/`, and both install scripts.

## [2026-07-28]

### Added

- DevOps scaffolding for distributing skills to the team: `Skill-Authoring-Standard.md`, `Skill-Pipeline.md`, `SECURITY.md`, `INSTALLATION.md`, `MARKETPLACE.md`, this `CHANGELOG.md`.
- `.claude-plugin/marketplace.json` — registers this repo as a Claude Code plugin marketplace with one plugin entry per skill.
- `scripts/install-prerequisites.ps1` and `scripts/install-prerequisites.sh` — bootstrap Git, AWS CLI (Windows) / native package manager (Linux), Node.js, Python, the Claude Code CLI itself (with `PATH` export), and the team's standard marketplaces/plugins (Superpowers, find-skills, GSD, claude-mem, frontend-design, excalidraw-generator).
- Populated `skills/README.md` with a skill overview table (name, category, purpose, invocation mode) for all 10 skills.
- Root `README.md` now embeds the skills overview and links every new doc.
- Populated root `.gitignore`.

### Fixed

- `aws-opensearch` and `intune-graph` skill directories were double-nested (`skills/<name>/<name>/SKILL.md`), breaking the standard `skills/<name>/SKILL.md` discovery convention and marketplace `source` paths. Flattened to the standard layout.

### Skills present as of this baseline

`aws-opensearch`, `bitbucket`, `checkpoint-email`, `cloudflare`, `drata`, `i-have-adhd`, `intune-graph`, `mermaid-svg-bitbucket`, `sophos-central`, `wazuh-onprem` — see [`skills/README.md`](skills/README.md) for details on each.
