# L-0509 Complete archive: every ticket reader finds done tickets under Complete/, and ticket IDs beyond T- work everywhere          status: spec   risk: high

Anchored to origin/main `6813749b` (crew 1.0.70). Direction: `.work/tickets/L-0509/direction.md`
(approved 2026-09-30 under standing authority, Option 1). Every `path:line` below was re-read at
that commit from an export of origin/main; re-check with `git diff --name-only 6813749b..HEAD -- <path>`
before trusting one.

## Intent

Every crew reader and writer finds a ticket whether its folder is live (`.work/tickets/<ID>/`) or
archived (`.work/tickets/Complete/<ID>/`), and its Obsidian note whether live
(`<boardDir>/<ID>.md`) or archived (`<boardDir>/Complete/<ID>.md`), through one resolver whose
"could not tell" (a failing `stat`, or both locations present) is its own outcome and never reads as
absent. `Complete` is a reserved name, never a ticket id. Every id site accepts any
`[A-Z][A-Z0-9]*-[0-9]+` id (`T-`, `L-`, `W-` alike) from one shared definition. A new
`crew_tracker.py archive --ticket <ID>` moves ONE done/merged ticket's folder, note and Done-lane
card with crew's existing atomic write discipline; the one-time move of the existing backlog is an
ops step after this lands, not part of this diff.

## Exclusions

- The one-time archive of existing done tickets is NOT run by this ticket (owner decision
  2026-09-30). The PR body names it as the post-merge ops step, with `.work/HANDOFF.md:27`'s
  exclusions (cloud tickets T-0500..T-0507 and T-0104..T-0108, T-0508, any ticket a live lane
  references).
- `crew_tracker.py archive` never edits `.work/INDEX.md`: the row keeps its `done`/`merged` status,
  which is what keeps the id taken (`crew_tracker.py:1345-1347`). No INDEX reader changes
  (direction finding 6).
- No bulk mode (`--all-done`), no un-archive, no `--reopen` past an archive, no auto-archive in
  `/crew:done` (direction questions 4-6). `move` of an archived ticket refuses and says so.
- No new config key (so no CONFIG.md change), no new hook registration in
  `plugin/crew/hooks/hooks.json`, no new slash command.
- The ticket note is never rewritten (`crew_tracker.py:1236-1240`): its `ticket:` `file://` link to
  the live folder (`:1227-1233`) goes stale after archive; accepted (direction question 7).
- Existing `T-` ids are never renamed; no INDEX or board text is migrated.
- The loose path-safe id (`crew_ticket.py:159`) is not tightened to the strict shape (direction
  question 9); both shapes move to `crew_common` and every copy aliases one.
- `scope_report.py` is unchanged: it reads only the 0.x `.work/tickets/<id>.md` file of the ticket
  INDEX says is open (`scope_report.py:41,62,165-178`), and an archived ticket is never open.
- Approval receipts and review ledgers under `<git-common-dir>/crew/` are not moved or re-keyed.
- Approval-state writes under `.work/tickets/Complete/` by anything but `archive` are not added:
  every writer that creates a folder creates the live one (`absent` returns the live path).

## Evidence

Anchor: origin/main `6813749b`, crew `1.0.70` (`plugin/crew/.claude-plugin/plugin.json:3`).

The resolver and its callers:
- `plugin/crew/hooks/scripts/crew_ticket.py:218-219` - `ticket_dir(top, ticket)` joins
  `.work/tickets/<id>` after `check_ticket` (`:177-181`), with no I/O.
- Callers: `crew_ticket.py:455,462` (`read_contract`, `validate`), `:875`, `:947`, `:956`
  (`resolve_active`, `:931-958`), `:1014`; `crew_autopilot.py:277,409,635,657,1228,1267,1424,1508`;
  `crew_route.py:174` (`_resolve`, no `TicketError` handler); `approval_hook.py:244-249`
  (`_is_folder`, catches `TicketError` -> False, i.e. refuse).
- Self-built paths that bypass it: `review_prompt.py:103,108` (`_spec_block`), `:129`
  (`_plan_block`), `:220` (webtest findings); `review_run.py:386` (`work_dir` default for
  `review.json`); `webtest_guard.py:431` (`exclusions`), `:457` (`findings_path`);
  `crew_resume.py:501` (`progress_fingerprint`), `:704` (resume decision "does not exist");
  `scope_guard.py:189` (`own = f".work/tickets/{ticket}/"`, the always-writable prefix, rule 5 at
  `:22-25`); `crew_migrate.py:497` (0.20 migration write target); `crew_tracker.py:1228` (note link
  at create).
- `plugin/crew/hooks/scripts/crew_common.py:1-22` - standard library only, fail-soft, imported by
  `crew_ticket`, `crew_tracker`, `crew_status`, `crew_resume`, `review_run`, `webtest_guard`,
  `crew_autopilot`, `crew_route`, `crew_state`; NOT by `review_prompt.py:33-40`,
  `review_ledger.py:69-78`, `crew_migrate.py:75-82`, `crew_metrics.py:89-100`.

Folder enumeration:
- `plugin/crew/hooks/scripts/crew_status.py:102-118` - `_ticket_lines` counts every directory under
  `.work/tickets/` (`:108`), so `Complete` would be counted as one ticket.
- `plugin/crew/hooks/scripts/crew_migrate.py:359-383` - `_ticket_candidates` skips directories
  (`:372-373`) and reads only `*.md`; `Complete/` is already ignored there.

Id shapes (seven copies):
- Loose, anchored: `crew_ticket.py:159`, `review_ledger.py:90`, `crew_metrics.py:119`
  (`^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$`); `check_ticket` at `crew_ticket.py:177`,
  `review_ledger.py:102`, `crew_metrics.py:131`. `"Complete"` matches all three.
- Strict: `crew_state.py:197` (`([A-Z][A-Z0-9]*-\d+)`, unanchored search; `\d` is any Unicode
  digit), `crew_autopilot.py:229` (`^[A-Z][A-Z0-9]*-[0-9]+$`), `crew_tracker.py:112`
  (`[A-Z][A-Z0-9]*-\d+\Z`), `crew_tracker.py:752-753` (`_FIRST_ID` board composite),
  `crew_migrate.py:132` (`_ID_RE`), `:148` (`_TARGET_RE` composite), `:345` (inline search),
  `crew_resume.py:84` (`_TICKET_ID_RE`). All accept `L-0509` and `W-0001` today.
- The one hard prefix: `crew_migrate.py:351-356` `_cache_source` - `SDP-` -> sdp, `^T-\d+$` ->
  obsidian/files-cache, everything else -> `jira`, so an `L-` cache file is labelled jira.
- `crew_tracker.py:1551-1552` - CLI refuses a non-matching `--ticket` with "must be a ticket id like
  T-0042".
- Prompt text naming `T-####`: `plugin/crew/commands/brainstorm.md:25,28,31,32,38`,
  `plugin/crew/commands/fix.md:26`, `plugin/crew/commands/obsidian-sync.md:3`,
  `plugin/crew/commands/runbook.md:3`. `test_crew_state.py:337` cites `T-####` in a docstring only.

Obsidian:
- `plugin/crew/hooks/scripts/crew_tracker.py:987-1037` - `_vault_paths(root, settings, names)`;
  a name with `/` or `\` is refused (`:1017-1018`); each file is confinement-checked
  (`:1020-1022`) and refused when not a regular file (`:1023-1024`).
- `:1283-1299` `_card_owner` -> `OURS|FOREIGN|UNKNOWN`; a missing note is `UNKNOWN` with
  `note_exists` False (`:1290-1291`).
- `:1343-1385` `_obsidian_create`: INDEX first (`:1345-1347`), then note owner (`:1353-1358`),
  then exclusive note create (`:1370-1376`).
- `:1388-1424` `_obsidian_move`: `find_card` (`:865-875`) fails "no card for <id> on the board"
  once the card is gone.
- `:1427-1449` `_obsidian_read`: returns `could not read` on a missing card.
- `:785-799` `_region_end` stops the lanes at `***` + `## Archive`; `:846-862` `_cards` lists
  cards above it; `:926-950` `move_card`; `:1208-1224` `_board_write` (atomic, pinned directory).
- `:1054-1206` - the no-follow directory walk (`_hold_dirs`, `_open_pinned`, `_pinned`) every vault
  write goes through.
- `:547-549` `_common_dir`; the active-ticket map is `<git-common-dir>/crew/active-ticket`
  (`crew_ticket.py:905-907`), a JSON map from worktree top to ticket id (`:85-97`).
- Owner statement (2026-09-30, relayed, not measured here): Obsidian resolves `[[ID]]` by basename,
  so a note moved into `Complete/` keeps resolving.

Readers that need nothing (INDEX rows are kept):
- `crew_state.py:370-399` `read_work`; `crew_autopilot.py:242-262`; `crew_ticket.py:815-840`
  `_index_closed`; `crew_tracker.py:692-745`; `crew_status.py:111-114`; `crew_migrate.py:342-348`;
  `crew_resume.py:467-484`.
- Receipts: `crew_ticket.py:222-227` `approval_path` under `<git-common-dir>/crew/tickets/<id>/`;
  `read_contract` (`:451-455`) hashes bytes, not paths.

Tests and harnesses:
- `plugin/crew/tests/test_crew_ticket.py`, `test_crew_tracker.py` (+ `tracker_fixtures/`),
  `test_status.py`, `test_migrate.py` (+ `migrate_fixtures/`), `test_scope_guard.py`,
  `test_crew_route.py`, `test_review_prompt.py`, `test_review_ledger.py`, `test_crew_metrics.py`,
  `test_crew_resume.py`, `test_webtest_guard.py`, `test_crew_state.py`, `test_crew_autopilot.py`,
  `test_approval_hook.py`, `test_review_run_launch.py`, `test_lifecycle_commands.py`.
- Sabotage: `plugin/crew/tests/sabotage.py` appends each `sabotage_*.py` list;
  `sabotage_tracker.py:1-20` (tracker rows, targets `crew_tracker.py`, `brainstorm.md`, `fix.md`);
  `sabotage_scope.py` (rows already target `crew_ticket.py`, 4 hits).

Verify map (`.crew/verify.json` at `6813749b`, by rule index):
- 8 (`crew_state.py`, `crew_common.py` -> `test_crew_state.py` and nine more), 11 (`crew_ticket.py`
  -> `test_approval_digest.py test_crew_ticket.py`), 25 (`scope_guard.py` -> `test_scope_guard.py`
  and five more), 26 (`crew_resume.py`), 29 (`crew_tracker.py` -> `test_crew_tracker.py`), 30
  (`crew_route.py`), 31 (`approval_hook.py`, `crew_ticket.py`), 32 (`review_run.py`,
  `crew_common.py` -> `test_review_limit.py test_worktree_config.py`), 33 (`review_*.py` ->
  `test_review_*.py`), 27/28 (`crew_autopilot.py`).
- No pytest rule maps `crew_status.py`, `crew_migrate.py`, `crew_metrics.py` or `webtest_guard.py`
  (only rules 0 and 15, the marketplace check and ruff).

Documents that describe ticket location or ids (project CLAUDE.md doc rule; all at `6813749b`):
- `plugin/crew/README.md:751` (a ticket is a directory `.work/tickets/<id>/`), `:760` (active
  ticket), `:792` (threat model), `:1602` (tracker interface), `:1687` (ticket content in
  `.work/tickets/<id>/` for every mode), `:1719` (board edits).
- `plugin/crew/commands/brainstorm.md:25-38`, `fix.md:26-28`, `obsidian-sync.md:3,37`,
  `runbook.md:3`, `status.md:30`.
- `plugin/crew/skills/crew-setup/trackers.md:114-116`.
- `docs/guides/crew/src/daily-workflow-scope.md:16`, `docs/guides/crew/src/troubleshooting.md:157`;
  `docs/guides/crew/src/build.py:68-74` folds them into `crew-1.0-daily-workflow.*` and
  `crew-1.0-troubleshooting.*`.
- `plugin/PLUGINS.md:14` (version claim), `:17` (counts - unchanged: no command, skill or hook
  added).
- `plugin/crew/BUDGETS.md:10` (`crew-markdown-lines` claim).
- Command budget: every `commands/*.md` is held to 120 lines; `fix.md` is 108, `obsidian-sync.md`
  110, `brainstorm.md` 92.

## Unknowns

- **Obsidian basename resolution of `[[ID]]` after the note moves.** Owner statement, not measured
  here. Resolved by: the post-merge ops step checks one archived card's backlinks in Obsidian before
  looping; the code does not depend on it. Accepted as risk.
- **Obsidian saving the board while `archive` edits it.** `_board_write` re-reads and retries
  (`WRITE_TRIES = 3`, `crew_tracker.py:109`), as every board write does today. Accepted as risk,
  same as `move`.
- **A crash between the three halves of `archive`** (folder moved, note not). Resolved by design:
  each half is idempotent and re-running `archive` completes the rest; the resolver reports a
  both-present state as could-not-tell rather than picking one. Tests pin the re-run.
- **Windows.** `os.rename` of a directory with a file open inside it fails on Windows; `archive`
  reports that half FAILED and changes nothing else. The `.ps1` wrappers are not involved (no hook
  changes). Not reproduced on a Windows box here; the PR body says so.
- **Prefix choice for a new ticket** (direction question 8) is prose, read by the model from
  `.work/INDEX.md`. A misfire mints a wrong-prefix id that `create` still accepts. Accepted as risk;
  follow-up config key only if it happens.
- **Tightening `crew_state._TICKET_RE` from `\d` to `[0-9]`** drops non-ASCII digits. No INDEX row
  in this repo uses one (`grep -P '[^\x00-\x7F]' .work/INDEX.md` is resolved at implement and quoted);
  accepted as risk.
- **Callers that do not catch `TicketError`** (`crew_route.py:174`, `crew_autopilot.py` sites, the
  `crew_ticket.py` CLI) newly see it for could-not-tell. Resolved at implement: each is walked in
  Step 3 and either already handles it or gains a handler that refuses/stops naming the reason;
  tests pin `crew_route` and `crew_autopilot resume` with a could-not-tell ticket.

## Touch

- `plugin/crew/hooks/scripts/crew_common.py`
- `plugin/crew/hooks/scripts/crew_ticket.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_route.py`
- `plugin/crew/hooks/scripts/approval_hook.py`
- `plugin/crew/hooks/scripts/scope_guard.py`
- `plugin/crew/hooks/scripts/crew_tracker.py`
- `plugin/crew/hooks/scripts/crew_status.py`
- `plugin/crew/hooks/scripts/crew_migrate.py`
- `plugin/crew/hooks/scripts/crew_resume.py`
- `plugin/crew/hooks/scripts/crew_metrics.py`
- `plugin/crew/hooks/scripts/review_prompt.py`
- `plugin/crew/hooks/scripts/review_run.py`
- `plugin/crew/hooks/scripts/review_ledger.py`
- `plugin/crew/hooks/scripts/webtest_guard.py`
- `plugin/crew/tests/test_crew_ticket.py`
- `plugin/crew/tests/test_crew_state.py`
- `plugin/crew/tests/test_crew_tracker.py`
- `plugin/crew/tests/tracker_fixtures/**`
- `plugin/crew/tests/test_status.py`
- `plugin/crew/tests/test_migrate.py`
- `plugin/crew/tests/test_scope_guard.py`
- `plugin/crew/tests/test_crew_route.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_approval_hook.py`
- `plugin/crew/tests/test_review_prompt.py`
- `plugin/crew/tests/test_review_ledger.py`
- `plugin/crew/tests/test_review_run_launch.py`
- `plugin/crew/tests/test_crew_metrics.py`
- `plugin/crew/tests/test_crew_resume.py`
- `plugin/crew/tests/test_webtest_guard.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/tests/scope_fixtures.py`
- `plugin/crew/tests/sabotage_tracker.py`
- `plugin/crew/tests/sabotage_scope.py`
- `plugin/crew/commands/brainstorm.md`
- `plugin/crew/commands/fix.md`
- `plugin/crew/commands/obsidian-sync.md`
- `plugin/crew/commands/runbook.md`
- `plugin/crew/commands/status.md`
- `plugin/crew/skills/crew-setup/trackers.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md` (line-count claim, owner standing rule 2026-09-28)
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `TODO.md` (/crew:done check 3 files findings here)
- `.crew/verify.json` (one new rule for the unmapped modules; why texts of the mapped rules)
- `docs/guides/crew/src/daily-workflow-scope.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/crew-1.0-daily-workflow.html` (rebuilt by build.py)
- `docs/guides/crew/crew-1.0-daily-workflow.docx` (rebuilt by build.py)
- `docs/guides/crew/crew-1.0-daily-workflow.pdf` (rebuilt by build.py)
- `docs/guides/crew/crew-1.0-troubleshooting.html` (rebuilt by build.py)
- `docs/guides/crew/crew-1.0-troubleshooting.docx` (rebuilt by build.py)
- `docs/guides/crew/crew-1.0-troubleshooting.pdf` (rebuilt by build.py)
- `.crew/codemap/*.md` (refresh artifact, standing rule)
- `.claude/rules/*.md` (refresh artifact, standing rule)
- `docs/diagrams/*.mmd` (refresh artifact, standing rule)
- `graphify-out/graph.json` (refresh artifact, graphify update)
- `graphify-out/GRAPH_REPORT.md` (refresh artifact, graphify update)

## Acceptance checks

- [ ] `crew_common.locate_ticket(top, ticket)` returns `(path, where)`: live dir present -> `live`;
      only `.work/tickets/Complete/<ID>/` present -> `complete`; neither -> `absent` with the LIVE
      path; both -> `could not tell` naming both; a `stat` raising `PermissionError` (monkeypatched)
      on either candidate -> `could not tell`, never `absent`; `FileNotFoundError` and
      `NotADirectoryError` -> absent for that candidate. It never raises. Tests in
      `test_crew_ticket.py` (`test_locate_*`, one per row; verify rule 11).
- [ ] `crew_ticket.ticket_dir` returns the archived path for an archived ticket, the live path for a
      live or absent one, and raises `TicketError` ("could not tell where <ID> lives: ...") for
      could-not-tell; `check_ticket("Complete")`, `("complete")`, `("COMPLETE")` raise, and so do
      `review_ledger.check_ticket` and `crew_metrics.check_ticket` (`test_crew_ticket.py`,
      `test_review_ledger.py`, `test_crew_metrics.py`).
- [ ] `resolve_active` honours a pointer to an archived ticket (not broken) and reports a
      could-not-tell ticket as broken with the reason; `validate`, `read_contract` and an existing
      approval receipt stay valid after the folder moves (receipt digest unchanged -
      `test_crew_ticket.py::test_approval_survives_archive`).
- [ ] Every self-built site routes through the resolver: `review_prompt` spec/plan/webtest blocks,
      `review_run`'s default `work_dir`, `webtest_guard.exclusions`/`findings_path`,
      `crew_resume.progress_fingerprint` and the resume decision, `crew_route._resolve`,
      `crew_autopilot` resume, and `approval_hook._is_folder` each find an archived ticket (one test
      each in its own test file). A structural test
      (`test_crew_ticket.py::test_no_module_builds_ticket_paths_itself`) parses every
      `hooks/scripts/*.py` and fails on a `".work", "tickets"` join or `.work/tickets/` f-string
      outside `crew_common`, `crew_ticket`, and the named allowlist (`crew_status` enumeration,
      `crew_migrate` 0.20 layout, `crew_tracker._note_text`).
- [ ] Could-not-tell reaches every caller as a refusal, never as "no such ticket":
      `crew_route` returns `ask` with "could not tell where <ID> lives"; `crew_autopilot resume`
      stops with the same reason; `approval_hook` refuses the approval naming it
      (`test_crew_route.py`, `test_crew_autopilot.py`, `test_approval_hook.py`).
- [ ] Id shapes live once: `crew_common.TICKET_ID` (`^[A-Z][A-Z0-9]*-[0-9]+$`),
      `TICKET_ID_SEARCH`, `PLAIN_ID`, `ARCHIVE_DIR = "Complete"`, `reserved_id()`. A structural test
      (`test_crew_ticket.py::test_ticket_id_regexes_are_defined_once`) fails when any other module
      compiles `[A-Z][A-Z0-9]*-` or `[A-Za-z0-9][A-Za-z0-9._-]` itself. `L-0509`, `W-0001`, `T-0001`
      and `SDP-12` pass every site; `Complete` passes none (parametrised in `test_crew_ticket.py`,
      `test_crew_tracker.py`, `test_crew_state.py`).
- [ ] `crew_migrate._cache_source` labels a cache file by the configured tracker: `L-0509` under
      obsidian -> `obsidian`, under files -> `files-cache`; `SDP-` stays `sdp`; jira stays `jira`;
      a migrate whose target ticket is archived is listed as skipped, and a could-not-tell target is
      refused by apply (`test_migrate.py`, new verify rule).
- [ ] `crew_status` prints `tickets  <n> ticket dir(s), <m> archived in Complete/, <k> legacy
      file(s)`, never counts `Complete` as a ticket, and prints `archived: could not tell` when
      `Complete/` cannot be listed (`test_status.py`, new verify rule).
- [ ] Scope guard (a blocking-decision change, stated in the PR body): the always-writable "own
      files" prefix is the resolved folder. Must-allow: a Write to
      `.work/tickets/Complete/T-1/spec.md` while T-1 is active and archived. Must-block: a Write to
      `.work/tickets/Complete/T-2/spec.md` while T-1 is active (not in Touch); a Write to the live
      `.work/tickets/T-1/x.md` while T-1 is archived (would create the both-present state); every
      existing must-block/must-allow row unchanged; a could-not-tell active ticket refuses the edit
      naming the reason. Module + sh + ps1 flavours, `block` and `report` (`test_scope_guard.py`,
      verify rule 25).
- [ ] `crew_tracker.py archive --ticket <ID>` (files and obsidian): refuses unless INDEX status is
      `done` or `merged`; refuses when any worktree's active-ticket pointer names `<ID>` or the map
      cannot be read (could not tell); moves `.work/tickets/<ID>` to `.work/tickets/Complete/<ID>`
      (creating `Complete/`), refusing an existing destination; for obsidian moves the note to
      `<boardDir>/Complete/<ID>.md` only when `_card_owner` is OURS, through the no-follow directory
      walk, refusing an existing destination; removes the card's whole span from the Done lane via
      `_board_write` and refuses a card in any other lane; leaves INDEX.md byte-identical; a second
      run prints `unchanged` for every half; a run after a simulated crash between halves completes
      the rest. jira/sdp: folder only, tracker line `not applicable`. One line per half; exit codes as
      `move`. Tests in `test_crew_tracker.py` (verify rule 29).
- [ ] `crew_tracker` on an archived ticket: `read` returns `read` with `lane` `Complete/` and
      `archived: true` (not `could not read`); `move` fails with "<ID> is archived in Complete/;
      move its folder and note back by hand to reopen it", with and without `--reopen`; `create` of
      an id whose note is under `Complete/` fails `id taken` even with the INDEX row removed; a note
      present in both places is `could not tell` for all three (`test_crew_tracker.py`).
- [ ] `_vault_paths` accepts `Complete/<name>` only through the `ARCHIVE_DIR` constant (a configured
      `board` or ticket name with a separator is still refused), and the archived note gets the same
      confinement, regular-file and git-ignore checks (`test_crew_tracker.py`).
- [ ] sabotage, each a row naming one test and each RED through `python3 plugin/crew/tests/sabotage.py`
      (run through heavy-run), quoted in the PR body: (a) `locate_ticket` returns `absent` when `stat`
      raises; (b) `locate_ticket` prefers live when both exist; (c) `check_ticket` stops refusing
      `Complete`; (d) `crew_status` counts `Complete` as a ticket; (e) `archive` skips the INDEX
      done/merged check; (f) `archive` skips the active-pointer check; (g) `archive` overwrites an
      existing destination; (h) `_obsidian_create` stops checking the archived note; (i) the guard's
      own-files prefix goes back to the literal live path. Rows (a)-(c), (i) in `sabotage_scope.py`,
      (d)-(h) in `sabotage_tracker.py`.
- [ ] Prompts: `brainstorm.md` and `fix.md` say "the next free number above every id in
      `.work/INDEX.md`, with this box's prefix (`T-` when none)"; `obsidian-sync.md:3` and
      `runbook.md:3` hint `<ID>`; `status.md` names the archived count; no command file names
      `T-####` (`test_lifecycle_commands.py::test_no_command_hard_codes_the_t_prefix`); every
      command file stays within its 120-line budget.
- [ ] Docs: README `:751` (Complete/ layout and the resolver's could-not-tell), `:792` (threat model:
      archive is an unguarded shell command, refuses active tickets, widens nothing because the
      resolver is uniform), `:1602`-area tracker section (the `archive` verb, its halves, its
      refusals, that the one-time backlog move is an ops step), `:1687`; `trackers.md` (archived
      notes); `obsidian-sync.md:37`; both guide sources and their six rebuilt outputs; CHANGELOG
      entry; BUDGETS.md claim re-measured; crew version one patch past origin/main at push
      (1.0.71 as of `6813749b`) in `plugin.json`, `marketplace.json` and `PLUGINS.md:14` with claim
      markers; `python3 scripts/check-marketplace.py` green.
- [ ] `.crew/verify.json`: a new rule maps `crew_status.py`, `crew_migrate.py`, `crew_metrics.py`,
      `webtest_guard.py` and their tests to `python3 -m pytest plugin/crew/tests/test_status.py
      plugin/crew/tests/test_migrate.py plugin/crew/tests/test_crew_metrics.py
      plugin/crew/tests/test_webtest_guard.py -q` with a measured time; rules 8, 11, 25, 29 `why`
      texts name L-0509; `test_refresh_check.py::test_every_module_the_refresh_allowance_touches_runs_a_pytest_rule`
      green.
- [ ] Suites green through heavy-run: the full crew suite `python3 -m pytest plugin/crew/tests/ -q
      -n 4 -m "not wallclock"` then `-m wallclock` serially; `python3 -m pylint -j 4 $(git ls-files
      "*.py")` as CI; `python3 /root/crew-tmp/ruff-no-new.py <worktree>` exit 0 or findings recorded
      per the fix-at-land rule; `python3 scripts/check-marketplace.py` exit 0.
- [ ] PR body states: the scope-guard blocking-decision change (own-files prefix follows the
      resolver) and that no hook is added; the new `archive` verb; `Docs:` list including "CONFIG.md:
      none - no config key"; the BUDGETS.md and refresh-artifact standing rules; the sabotage RED
      quotes; Windows not reproduced; and the post-merge ops step (run `archive` per done/merged
      ticket, excluding T-0500..T-0507, T-0104..T-0108, T-0508 and any ticket a live lane
      references; check one archived card's `[[ID]]` backlinks in Obsidian first).
