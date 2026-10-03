# T-0050 global defaults for crew settings, config rebuild from templates plus the owner's profile, automatic backups          status: spec   risk: high
## Decisions (owner, Matthew Badali, 2026-09-26; `direction.md`)
- "Just like the previous setting, there needs to be a global config for crew and also configuration templates to rebuild in case something gets lost or needs to be regenerated."
- The owner's personal defaults live in `~/.claude/crew/config.json`, and a repo value overrides them. Permission-widening keys stay safe: a global `approval: self` or `deploy: nonprod` applies only where the repo does not set a stricter value, and a repo `human`, `none` or `off` always wins (the ratchet idea the guards use). The owner confirms the direction per key at spec (Unknowns).
- Rebuild regenerates a lost or corrupt config from the template plus the owner's saved profile, as a dry run first and then `--apply`. Every crew write to either config is backed up first, the last N are kept, and `--restore <stamp>` puts one back. `--show` marks every value with its layer.
## Intent
The owner sets personal crew defaults once, in `~/.claude/crew/config.json`, and every repo on the machine inherits them. The globally settable set grows by the personal `autopilot` keys (`mode`, `maxPhases`, `approval`, `questions` today, and each later autopilot key its own ticket declares) and by `scope.allowCliApproval`. Those keys combine per key through a new table in `crew_guards` (`PERSONAL_KEYS`): the stricter of the layers that set the key wins, a layer that is silent imposes nothing, and neither the templates nor `/crew:init` spell those keys, so a template default never shadows the owner's choice. `/crew:config` gains `--rebuild --repo|--global` (template plus `~/.claude/crew/profile.json`, with a copy in the vault when `memory.vaultPath` is set), `--restore <stamp>`, `--backups`, `--set`/`--unset` with `--repo`, and a `--show` that marks every leaf `default`, `global`, `repo` or `repo-only`, names a layer holding a value down, and flags template shadows and profile drift. Every crew writer of either config file first saves a timestamped copy under `~/.claude/crew/backups/`, keeps the last 20, and refuses to write when the backup fails. Nothing is written without `--apply`.
## Exclusions
- No environment, tracker, board, `graph.*`, `platform.*`, `verify`, `tier`, `roles`, `scope.mode` or `autopilot.knownFailures` becomes global. Each describes one checkout. `is_global_path` keeps refusing them on write and `filter_global` keeps dropping them on read.
- No change to the existing ratchet (`RATCHETED_KEYS`, `effective_ratcheted`, `resolve_ratcheted`) or to how `install.policy`, `guards.*` and `change.requireForProduction` combine. `PERSONAL_KEYS` is a second table with its own rule, and no key is in both.
- No change to the approval path beyond where `scope.allowCliApproval` is read. `approval_hook.py` is untouched. The scope guard's refusals are untouched, and a CLI receipt still needs `allowCliApproval` to resolve exactly `true`.
- No automatic rebuild. SessionStart's `heal_config` keeps writing crew's defaults, not the profile's values, and names `/crew:config --rebuild --repo` in its message. A SessionStart hook is not the owner's yes.
- No hook. A hand edit of either file (an editor, or Claude's Write or Edit tool) is not backed up. `--set --repo` is the backed-up route, and `--show` reports profile drift.
- No automatic removal of a template-written repo value that shadows a global one. `--show` names it and `--unset --repo` removes it on the owner's `--apply`.
- No `.crew/crew.json` backup: `crew_migrate` owns that file, with its own manifest and rollback.
- No generated settings reference: T-0048 owns that, and reads the rows `--show` produces.
- No change to T-0010's, T-0011's, T-0012's, T-0029's or T-0045's policy semantics. They gain a global layer only, through the table row each one adds.
## Evidence
Anchors are origin/main 1e0706ac unless labelled. Branch-only anchors are labelled with the branch and head.
- The layering: repo over global over defaults, merged by `crew_state.merge_defaults`, with the global layer pruned to `default_global_config()` first (`plugin/crew/hooks/scripts/crew_config.py:25-46`, `resolve_config` `:748-787`, `filter_global` `:653-673`, `is_global_path` `:676-692`). A repo `null` does not shadow a global value (`null_shadows` `:558-601`).
- `scope` and `autopilot` are REPO ONLY in `default_config()` (`plugin/crew/hooks/scripts/crew_config.py:362-374`). `default_global_config()` (`:378-540`) already carries `qa`, `dev`, `secondOpinion` (`:468-477`), `resume` (`:507`), `install`, `guards` and `change`. So `resume` and the provider and model choices the direction names are already global.
- The ratchet: `RATCHETED_KEYS` (`plugin/crew/hooks/scripts/crew_guards.py:489-509`), and `effective_ratcheted` takes the lower rank with absent as the default floor (`:524-550`). Under that rule a global `approval: self` over a repo that sets nothing would resolve to the floor, so it cannot carry a personal default. `resolve_ratcheted` reads both layers raw (`plugin/crew/hooks/scripts/crew_config.py:790-847`). `_widens` marks a widening by rank (`:2173-2193`).
- `crew_guards.py` imports only `fnmatch`, `os` and `shlex` (`plugin/crew/hooks/scripts/crew_guards.py:28-30`), so a PreToolUse path can import it cheaply.
- `cli_approval_allowed` reads only the repo's `.crew/config.json` (`plugin/crew/hooks/scripts/crew_ticket.py:634-639`). `accepted` demotes a non-user-prompt receipt without it (`:642-650`), and the scope guard calls `accepted`. `crew_ticket.py` imports only the standard library and `crew_common` (`:121-133`).
- `crew_autopilot.settings` reads the `autopilot` block through `resolve_config` (`plugin/crew/hooks/scripts/crew_autopilot.py:592-618`), so a key that joins the global layer reaches it with no reader change. On T-0029-wave 1f54089e (branch-only; it carries T-0010 abd4f29b), `AUTOPILOT_DEFAULTS` is `{"mode": "off", "maxPhases": 12, "approval": "risk", "questions": "risk"}` (`plugin/crew/hooks/scripts/crew_state.py:1091`), and `_policy_setting` reads anything outside `human|self|risk` as `human` with a warning (`plugin/crew/hooks/scripts/crew_autopilot.py:697-706`).
- Later autopilot keys, each branch-only:
  - T-0011-build: `ship` (`pr|merge`, default `merge`), `knownFailures` and `ciTimeoutMinutes` (`plugin/crew/hooks/scripts/crew_state.py:1092`, `SHIP_POLICIES` `plugin/crew/hooks/scripts/crew_autopilot.py:181`).
  - T-0029 plans `maxLanes` and `reviewPolicy` (`.work/tickets/T-0029/plan.md:31`). T-0045 plans `deploy: none|nonprod` (`.work/tickets/T-0045/spec.md:3`). T-0012 plans `mode: backlog` and per-run caps (`.work/tickets/T-0012/plan.md:36-39`).
- The templates equal the defaults byte for byte:
  - The repo template carries `"scope": {"mode": "off", "allowCliApproval": false}` and `"autopilot": {"mode": "off", "maxPhases": 12}` (`plugin/crew/templates/config.template.json:194-201`), which `test_default_config_matches_the_committed_template` pins (`plugin/crew/tests/test_crew_config.py:47-58`).
  - The global template is pinned the same way (`:61-72`), and the crew-setup inline copy parsed (`:121`, copy at `plugin/crew/skills/crew-setup/SKILL.md:168-169`).
  - Every initialised repo therefore holds `autopilot.mode: "off"` explicitly, and a global `plan` could never reach it under any rule in which a repo `off` wins.
- The declared-leaf count is 119 (`plugin/crew/tests/test_crew_config.py:275`). `test_autopilot_defaults_are_the_config_block` pins `default_config()["autopilot"]` (`plugin/crew/tests/test_crew_autopilot.py:1074-1076`).
- Writers of a crew config file today:
  - `write_global_config` (`plugin/crew/hooks/scripts/crew_config.py:2536-2580`) is the global writer. `crew_autoclear_setup` goes through it (`plugin/crew/hooks/scripts/crew_autoclear_setup.py:256`, `:269`, `:398`) and writes repo files directly (`_atomic_write_json` `:451-463`, the batch in `apply_migrate_to_repo` `:493`, `:653`).
  - `crew_platform.heal_config` writes `default_config()` over a missing or corrupt repo file (`plugin/crew/hooks/scripts/crew_platform.py:191`, `:295-301`), and `apply_changes` writes platform facts (`:420-447`).
  - `crew_upgrade` writes the upgraded repo file (`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1328-1346`) after a one-time `.crew/config.json.v1.bak` (`backup_config` `:885-897`).
  - None of them keeps a timestamped history.
- `/crew:config` today never writes `.crew/config.json`, "that is `/crew:init`" (`plugin/crew/commands/config.md:35-37`). The walkthrough's rules are dry run, then `--apply`, merge and never replace, and ask before writing outside the repo (`plugin/crew/skills/crew-setup/global-config.md:18-44`). Step 1's `--explain` covers only the globally settable keys (`:51-73`; `explain_config` `plugin/crew/hooks/scripts/crew_config.py:1538-1656`).
- Test isolation: `plugin/crew/tests/conftest.py:25-44` points both `crew_config.GLOBAL_CONFIG_PATH` and `crew_state.GLOBAL_CONFIG_PATH` at a missing tmp file for every test. A backup directory derived from that path is isolated too.
- The machine today (machine-local, read 2026-09-26): `~/.claude/crew/config.json` holds only `guards` (`:2`) and `context.autoClear.enabled` (`:8-10`). The main checkout's untracked `.crew/config.json` carries the owner's autopilot values, with a hand backup in `/root/crew-tmp/` (`.work/HANDOFF.md:105-108`).
- The vault guard judges only `.md`, `.canvas` and `.base` writes (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:318`), so a `profile.json` in the vault is not a note.
## Unknowns
- Owner decision - which keys are global. Recommendation:
  - Global now: the personal `autopilot` keys and `scope.allowCliApproval`.
  - Already global on main, unchanged: `resume` and the provider and model choices (`qa`, `dev`, `secondOpinion`).
  - Repo-only: environments, tracker and board paths, `scope.mode` (whether the scope guard enforces is a fact about the checkout, and T-0029 refuses a wave without it), and `autopilot.knownFailures` (it names one repo's tests).
- Owner decision - the ratchet direction per key. Recommendation, strictest first:

  | key | order, strictest first | rule |
  |---|---|---|
  | `autopilot.mode` | `off`, `plan` (T-0012 adds `backlog` after `plan`) | tiers |
  | `autopilot.maxPhases` | a smaller positive int is stricter | int-min |
  | `autopilot.approval` | `human`, `risk`, `self` | tiers |
  | `autopilot.questions` | `human`, `risk`, `self` | tiers |
  | `scope.allowCliApproval` | `false`, then exactly `true` | tiers |

  Each later key's ticket adds its own row, and a test fails until it does:
  - `autopilot.ship`: `pr`, `merge`
  - `autopilot.deploy`: `none`, `nonprod`
  - `autopilot.reviewPolicy`: `stop`, `clean-only`, `fix-and-rereview`
  - `autopilot.maxLanes`, `maxTicketsPerRun` and `maxTokensPerSession`: int-min
  - `autopilot.ciTimeoutMinutes`: plain precedence (a wait, not a permission)
  - `autopilot.knownFailures`: repo-only
- Owner decision - a repo value wider than the global one. Recommendation: the guards' rule. When both layers set a key, the stricter wins, so a repo `self` under a global `human` reads `human`, and `--show` names the global layer as holding it down. A layer that is silent imposes nothing, so a global `self` over a silent repo is `self`. An unrecognised value ranks below the floor, is returned raw, and the reader's own validation reads it as its floor with a warning (T-0010's `_policy_setting` does this). The alternative is plain precedence, where the repo always decides: it allows a per-repo widening, but a cloned repo's config could then widen past the machine owner's explicit global value.
- Owner decision - template defaults shadow the global layer. Recommendation: neither template, nor crew-setup's inline copy, nor `heal_config` spells a personal key. `default_config()` and `default_global_config()` keep them as the defaults layer and the prune shape. New `template_config()` and `global_template_config()` omit them, and the committed templates equal those. Existing repos keep their explicit values: `--show` flags each personal key whose repo value equals the built-in default while the global layer sets another, and `--unset --repo <key>` removes it on the owner's `--apply`. Nothing removes one automatically, because a deliberate repo `risk` looks exactly like a template-written one.
- Owner decision - where the profile lives (direction). Recommendation: both, as the direction recommends. The profile is `~/.claude/crew/profile.json`, with a copy at `<memory.vaultPath>/crew/profile.json` when the resolved global `memory.vaultPath` names an existing directory, so it syncs with the vault. On rebuild:
  - When both copies read and agree, rebuild uses them.
  - When they differ, the newer `saved_at` is used, and the dry run names both.
  - When one is unreadable, rebuild uses the other and says so.
  - When a copy is present but unreadable and the other is absent, rebuild refuses (exit 3).
  - When both are absent, rebuild refuses unless `--no-profile` is given.
- Owner decision - what the profile holds, and when it is written. Recommendation:
  - Contents: per layer, every leaf that differs from that layer's template or is absent from it, excluding `schema` and `platform.*`. Unknown keys are kept. Repos are keyed by the normalised `origin` URL (credentials stripped, scheme and host lower-cased, a trailing `.git` and `/` removed, and the scp form `host:path` read as `host/path`), or by `path:<main worktree realpath>` when there is no origin.
  - Writes: refreshed after every write `/crew:config` makes, and captured on demand by `--save-profile [--repo|--global]` (a dry run, then `--apply`). Never written by `heal_config`, `platform-sync`, `crew_upgrade` or `crew_autoclear_setup`, so a defaults rewrite never overwrites the owner's values.
- Owner decision - backups. Recommendation: `~/.claude/crew/backups/global/<stamp>.json`, and for repos `backups/repo/<top-dirname>-<sha256(realpath)[:10]>/<stamp>.json` with a `source` file naming the path. The stamp is UTC `YYYYMMDDTHHMMSSZ`, with `-2`, `-3` on a collision. Files are 0600 in 0700 directories. The newest 20 per file are kept. If the backup fails, the write is refused and the file is left untouched, for every writer. `CREW_BACKUP_DIR` overrides the root, for tests.
- Owner decision - `/crew:config` writes the repo file. Recommendation: yes, but only for `--rebuild --repo`, `--restore --repo`, `--set --repo` and `--unset --repo`, each a dry run until `--apply`, and each backed up. This reverses `config.md:35-37` and is flagged in the CHANGELOG as a behaviour change.
- Owner decision - landing order. Recommendation: land after T-0010 if T-0010 is on main by then, with rows for every autopilot key on main at landing. If T-0010 has not landed, T-0050 lands with the `mode`, `maxPhases` and `allowCliApproval` rows. The forcing test (every `AUTOPILOT_DEFAULTS` key has a row or is listed repo-only) then fails T-0010's merge until T-0010 adds its two rows, and the same holds for T-0011, T-0012, T-0029 and T-0045.
- Accepted risk: the profile's repo key follows T-0030's hard-won lesson only partly. Two local clones with no origin and the same path, or URL spellings that differ in case on a case-sensitive host, can share or split a key. A rebuild always shows its dry run first.
- Accepted risk: the vault copy syncs by whatever syncs the vault. It holds config values, not secrets: crew stores env var names, never tokens.
- Not measured: the import cost `cli_approval_allowed` adds by reading the global file on a PreToolUse path. It is measured in plan Step 2, and must stay within 20 ms over the repo-only read on this machine.
- Codex is out until 2026-10-01, so the review is same-family. Accepted as risk.
## Touch
- plugin/crew/hooks/scripts/crew_guards.py
- plugin/crew/hooks/scripts/crew_config.py
- plugin/crew/hooks/scripts/crew_state.py
- plugin/crew/hooks/scripts/crew_ticket.py
- plugin/crew/hooks/scripts/crew_backup.py
- plugin/crew/hooks/scripts/crew_platform.py
- plugin/crew/hooks/scripts/crew_autoclear_setup.py
- plugin/crew/skills/crew-graph/scripts/crew_upgrade.py
- plugin/crew/templates/config.template.json
- plugin/crew/templates/global.template.json
- plugin/crew/skills/crew-setup/SKILL.md
- plugin/crew/skills/crew-setup/global-config.md
- plugin/crew/commands/config.md
- plugin/crew/tests/conftest.py
- plugin/crew/tests/test_crew_config.py
- plugin/crew/tests/test_crew_config_personal.py
- plugin/crew/tests/test_crew_config_rebuild.py
- plugin/crew/tests/test_crew_backup.py
- plugin/crew/tests/test_crew_ticket.py
- plugin/crew/tests/test_scope_guard.py
- plugin/crew/tests/test_platform_sync.py
- plugin/crew/tests/test_autoclear_setup.py
- plugin/crew/tests/test_upgrade.py
- plugin/crew/tests/sabotage_config_layers.py
- plugin/crew/tests/sabotage.py
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json
- .crew/verify.json
- CHANGELOG.md
## Acceptance checks
- [ ] `crew_guards.PERSONAL_KEYS` holds the rows above for every personal key on main at landing, and `effective_personal(dotted, repo, global, default)` implements the rule: the stricter of the layers that set the key, a silent layer imposes nothing, `null` is silent, an unrecognised value ranks below the floor and is returned raw, and int-min ignores an invalid layer when the other is valid. `test_every_autopilot_key_has_a_personal_row_or_is_repo_only` iterates `crew_state.AUTOPILOT_DEFAULTS`. Tests in `test_crew_config_personal.py`.
- [ ] Must-block (`test_crew_config_personal.py`, through `resolve_config` and `crew_autopilot.settings`), one test each:
  - `global-self-repo-human`: a global `approval: self` against a repo `human` resolves `human`
  - `global-self-repo-risk`: resolves `risk`
  - `repo-self-global-human`: resolves `human`, and `--show` names global as holding it down
  - `global-plan-repo-off`: `mode` resolves `off`
  - `global-typo`: a global `approval: "slef"` over a silent repo reads `human` with the warning
  - `global-maxphases-smaller-wins`: a global 5 and a repo 20 give 5
  - `global-knownfailures-refused`: refused on `--set` (exit 2) and dropped on read
  - `global-scope-mode-refused`: the same for `scope.mode`
- [ ] Must-block, allowCliApproval (`test_crew_ticket.py`, `test_scope_guard.py`):
  - `global-true-repo-false`: `cli_approval_allowed` is false, `accepted` demotes a CLI receipt, and the scope guard refuses an edit that only that receipt would allow
  - `global-true-repo-corrupt`: false
  - `global-corrupt-repo-absent`: false
  - `cli_approval_allowed` agrees with `resolve_config(root)["scope"]["allowCliApproval"] is True` across the full matrix of repo and global values (absent, `null`, `false`, `true`, `"true"`, a corrupt file)
- [ ] Must-allow:
  - `global-self-repo-silent`: resolves `self`
  - `global-self-repo-null`: resolves `self`
  - `global-true-repo-silent`: `cli_approval_allowed` is true
  - `repo-only-unchanged`: every non-personal key resolves exactly as before, checked against a snapshot of `resolve_config` on the existing fixtures
- [ ] Templates: `config.template.json` and crew-setup's inline copy equal `template_config()`, and `global.template.json` equals `global_template_config()`. None of them spells a personal key (`test_no_template_spells_a_personal_key`). `default_config()["autopilot"]` is still `AUTOPILOT_DEFAULTS`, and the declared-leaf count in `test_crew_config.py` is re-measured with its reason written beside it. `heal_config` writes `template_config()`.
- [ ] Backups (`test_crew_backup.py`), for every writer: `write_global_config`, a `/crew:config` repo write, `heal_config`, `apply_changes`, `crew_autoclear_setup`'s repo writes and `crew_upgrade`. Each saves the pre-write bytes (corrupt bytes included) under the backup root before replacing the file. Must-block: an unwritable backup root refuses the write and leaves the file byte-identical (one case per writer). Rotation keeps the newest 20. A same-second collision gets `-2`. No test writes under the real `~/.claude/crew/backups`: the full suite's before-and-after listing of that directory is identical.
- [ ] Rebuild (`test_crew_config_rebuild.py`):
  - must-allow `corrupt-repo-rebuilt-from-profile`: `--rebuild --repo` on a corrupt `.crew/config.json` prints a dry run, then `--apply` writes `template_config()` plus the profile's values, and the corrupt bytes are in a backup
  - must-block `rebuild-never-writes-without-apply`: after a dry run the file bytes and mtime, the backup directory and the profile are unchanged
  - must-block `rebuild-profile-unreadable`: exit 3, nothing written
  - must-block `rebuild-profile-absent`: refused without `--no-profile`
  - must-allow `rebuild-global-from-profile`
  - must-allow `vault-copy-newer-wins-and-is-named`
  - must-allow `vault-copy-unreadable-uses-home-copy-and-says-so`
- [ ] Restore: `--restore <stamp> --repo|--global` is a dry run until `--apply`. It backs up the current file first, then writes the stamped bytes. An unknown stamp exits 2 and writes nothing. `--backups` lists the stamps newest first (tests).
- [ ] Profile: a `/crew:config --set` or `--unset` with `--apply` refreshes that layer's profile section (and the vault copy when configured). `heal_config`, `apply_changes`, `crew_upgrade` and `crew_autoclear_setup` never change it (`test_defaults_writers_never_touch_profile`). `--save-profile` is a dry run until `--apply`.
- [ ] `--show` (`--explain --all`) prints every leaf of `default_config()` with its value and layer (`default`, `global`, `repo`, `repo+global`), marks repo-only keys, and prints `held down by <layer>` for ratcheted and personal keys. Its findings include `shadow` (a repo personal key equal to the built-in default while the global layer sets another) and `profile drift`. It writes nothing (tests).
- [ ] Sabotage (`sabotage_config_layers.py`, registered in `sabotage.py`), each mutation turning its named test red:
  - `effective_personal` takes the wider value
  - a silent layer counts as the floor
  - an unrecognised value ranks above the floor
  - `cli_approval_allowed` ignores the repo `false`
  - a template spells `autopilot.mode`
  - a rebuild writes on a dry run
  - a writer skips its backup
  - a failed backup still writes
  - rotation deletes the newest
  - restore skips backing up the current file
  - `heal_config` refreshes the profile
  - an unreadable vault copy is treated as absent when the home copy is also absent
  - plus one must-allow non-vacuity mutation: a silent repo not inheriting the global value
- [ ] `.crew/verify.json` gains a rule mapping `crew_guards.py`, `crew_config.py`, `crew_backup.py`, `crew_ticket.py` and the new tests to `python3 -m pytest plugin/crew/tests/test_crew_config_personal.py plugin/crew/tests/test_crew_config_rebuild.py plugin/crew/tests/test_crew_backup.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_ticket.py -q`, with measured seconds and a `why`. `python3 scripts/check-marketplace.py` passes.
- [ ] Docs:
  - `config.md` documents the new flags and the reversed "never writes `.crew/config.json`" rule.
  - `global-config.md` asks about the autopilot keys and `scope.allowCliApproval` with their widening lines, and explains shadows, rebuild, restore and backups.
  - CONFIG.md documents `PERSONAL_KEYS` and the rule, and re-measures the global-settable and repo-only counts in sections 10 and 11.
  - The README documents the global defaults, rebuild and backups.
  - BUDGETS.md's Markdown total is re-measured.
- [ ] The crew version is set at landing to one patch above origin/main's crew version at that time, in plugin.json, marketplace.json and PLUGINS.md in the last plugin/crew commit. The CHANGELOG entry flags the behaviour changes: new repos no longer spell the personal keys; `/crew:config` can write the repo file; and a global value can hold a repo value down.
