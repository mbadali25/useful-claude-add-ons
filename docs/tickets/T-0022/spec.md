# T-0022 /crew:autopilot docs phase and tracker phase          status: spec   risk: high
## Decisions (proposed by the planner 2026-09-25; owner to confirm at approval)
- Phase order is implement -> docs -> refresh artifacts (T-0008) -> review -> done. The docs phase sits where T-0008 put the refresh, between `/crew:docs` and `/crew:review` in `implement.md` step 6, so the reviewer reads the finished documents and the review receipt covers them. Nothing writes a tracked document after the receipt.
- The docs check is read-only, like T-0008's: `crew_docs_check.py --ticket <id>` reports each document `updated`, `not needed (<reason>)` or `MISSING`, and `/crew:done` runs it as a verifying check that never writes.
- The CHANGELOG rule is mechanical and cannot be waived: a marketplace entry whose source changed in this ticket must gain an `[Unreleased]` line naming the entry and its current version. README, SECURITY.md and TODO.md are judgement: `not needed` is accepted only with a recorded reason.
- Autopilot fixes documents by running `/crew:docs <id>` with the MISSING list, at most twice; still MISSING -> stop.
- Tracker updates run after every phase change, including `done` after the receipt, through T-0021's `crew_tracker`. That is safe for the receipt only because every tracker write lands outside the review bundle; this ticket proves it with a test against `review_patch`'s own hash, not by argument.
- A tracker `could not update` stops autopilot with the reason and the retry command. It does not undo the phase.
## Intent
`/crew:autopilot` keeps a ticket's documents and its tracker current without a human remembering either. A docs phase before review runs `/crew:docs`, then a read-only check that names every document as updated, not needed (with a reason) or MISSING, refusing a changed plugin with no CHANGELOG entry; `/crew:implement` and `/crew:done` run the same check. A tracker step after each phase change moves the ticket in files, Obsidian, Jira or SDP through T-0021's interface and stops loudly when it cannot.
## Exclusions
- No tracker backend code: T-0021 owns `crew_tracker.py`. This ticket calls `create`, `move` and `read` and defines none of them.
- No phase machine: T-0004 owns `crew_autopilot.py next_phase` and its branches. This ticket adds the `docs` and `docs-after-review` branches and the tracker step to it.
- No refresh logic: T-0008 owns `crew_refresh_check.py`; this ticket only orders the docs phase before it.
- No doc written after an accepted receipt, and no re-review triggered by autopilot: a MISSING document found after the receipt stops for a human, as T-0004's `stale-after-review` does.
- No writing SECURITY.md content about an unfixed issue (`plugin/crew/skills/crew-docs/SKILL.md:81-83`); the check only asks whether the reporting policy needs a change.
- No ADR, runbook or diagram rules: diagrams are T-0008's; ADRs and runbooks stay `/crew:docs` judgement, reported `not measured`.
- No new hook, config key or guard change.
## Evidence
- The docs pass today is prose with no record: `/crew:docs` walks the trigger table and states a decision per document (`plugin/crew/commands/docs.md:9-23`); "None of them" is "valid and common" (`:22-23`); it takes no ticket argument (`:3`). `implement.md:85-90` runs it between tests and `/crew:review`; `done.md:7-44` checks receipt, gate and completion audit and never looks at documents.
- The judgement rules: `plugin/crew/skills/crew-docs/SKILL.md:24-29` (CHANGELOG when callers can observe a change; README when setup, commands or the mental model changed; SECURITY.md when reporting, supported versions or a disclosed issue changed, never for routine fixes; TODO.md only for work deferred with a reason); `:81-83` never describe an open hole; `:95-96` a TODO entry says why and what unblocks it.
- CHANGELOG shape here: `## [Unreleased]` at `CHANGELOG.md:5`, entries led by the entry name and version, e.g. `CHANGELOG.md:9`. Marketplace entries carry `name`, `source` (`./skills/<n>` or `./plugin/<n>`) and `version` (`.claude-plugin/marketplace.json`, 39 entries at origin/main).
- Nothing checks CHANGELOG entries today: `check_versions` refuses a changed source with no version bump, comparing committed trees (`scripts/check-marketplace.py:518-551`); CHANGELOG is deliberately exempt from policy checks as history (`:1181-1187`).
- The ticket's changed paths: `scope_base.resolve` (`plugin/crew/hooks/scripts/scope_base.py:242`) and `completion_audit.changed_paths` (`plugin/crew/hooks/scripts/completion_audit.py:79`), base against the working tree plus untracked - the same source T-0008 uses.
- Why docs must precede review: the bundle stages the whole worktree except `.work/` (`plugin/crew/hooks/scripts/review_patch.py:96-97`, `:286`, `:308`), and `check_receipt` rebuilds it and refuses a changed tree (`plugin/crew/hooks/scripts/review_ledger.py:366`, `:387-394`).
- Why tracker writes may follow review, rule by rule against that bundle: files kind writes `.work/INDEX.md` (excluded, `review_patch.py:96-97`); Obsidian writes a vault outside the worktree (the pathspec is `-- .`, `:286`, `:308`) or an in-worktree vault that git ignores (`ls-files --others --exclude-standard`, `:286`), and T-0021 refuses an in-worktree vault git does not ignore; Jira and SDP write remote systems plus `.work/cache/` (excluded) and, once, `jira.cloudId` into `.crew/config.json` (`plugin/crew/commands/jira-sync.md:25`), which is ignored here (`.gitignore:292`). `.work/tickets/<id>/docs.json` is under `.work/` too, so recording a docs decision never stales a receipt.
- The phase machine this extends (T-0004, in progress, not on main): `next_phase` branches 8-14 in `.work/tickets/T-0004/plan.md` step 2 - no rounds -> implement; FINDINGS -> accept-review; receipt false and refresh not fresh -> refresh; receipt false and fresh -> review; receipt true and refresh stale -> `stale-after-review` stop; then done.
- T-0008 (in progress): the refresh sits after `/crew:docs` and before `/crew:review` in `implement.md` step 6 and is `/crew:done` check 4 (`.work/tickets/T-0008/spec.md` Decisions); its release-bookkeeping paths (`CHANGELOG.md`, `plugin/PLUGINS.md`, `.claude-plugin/marketplace.json`, `*/.claude-plugin/plugin.json`, `plugin/*/BUDGETS.md`) never make an artifact stale on their own.
- T-0021 (spec): `crew_tracker.create/move/read`, states `updated|unchanged|could not update|delegated|not applicable`, exit 3 for delegated (`.work/tickets/T-0021/spec.md`).
- The lifecycle cap: `plugin/crew/tests/test_lifecycle_commands.py:25-28`; `done.md` is 66 lines and `implement.md` 96 at origin/main, before T-0008 and T-0021 add theirs.
## Unknowns
- **Depends on T-0004 (hard):** `crew_autopilot.py` and `commands/autopilot.md` do not exist until it lands; steps 3-4 start after it merges.
- **Depends on T-0008 (hard for ordering):** the docs phase is placed before its refresh. If T-0008 has not landed, the docs phase still precedes review and the refresh ordering is re-checked when it does.
- **Depends on T-0021 (hard for the tracker step):** until it lands, the tracker step returns `unavailable` and autopilot stops naming T-0021 - never skips silently.
- Which paths are "security-relevant": a named glob list in `crew_docs_check.SECURITY_PATHS` (hook scripts named `*guard*`, `approval_hook.py`, `promote-gate.*`, every `hooks.json`, `scripts/install-prerequisites.*`, `.github/workflows/**`, `SECURITY.md`). A change there makes SECURITY.md a judgement that needs a reason; anywhere else it is `not needed (no security-relevant path changed)`. The list is judgement; accepted as risk and printed by `--explain`.
- What counts as a README-visible change of an entry: its `commands/**`, `agents/**`, `skills/*/SKILL.md`, `hooks/hooks.json`, `CONFIG.md`; the root README when the set of marketplace entry names changes. Judgement, accepted.
- TODO.md's source of deferred findings: `/crew:docs <id>` records them in `.work/tickets/<id>/docs.json` `deferred`; the check requires each to appear in TODO.md's added lines. Deferrals nobody records are invisible to it; accepted as the limit.
- Reusing T-0008's release-bookkeeping list: import it if T-0008 exports it as a constant, else define it here with a test pinning the two lists equal.
- A repo without `.claude-plugin/marketplace.json`: the whole repo is one unit and CHANGELOG becomes judgement with a reason; no CHANGELOG.md -> `not applicable`.
- On a repo where `.crew/config.json` is tracked, Jira's first `cloudId` write would enter the bundle; it happens at the first sync (brainstorm), before any review. Accepted.
- Version: the next free crew patch at approval (1.0.29-1.0.39 assigned to T-0003..T-0013; T-0016..T-0020 planned concurrently).
## Touch
- `plugin/crew/hooks/scripts/crew_docs_check.py`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/docs.md`
- `plugin/crew/commands/implement.md`
- `plugin/crew/commands/done.md`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/skills/crew-docs/SKILL.md`
- `plugin/crew/tests/**`
- `.crew/verify.json`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `TODO.md`
## Acceptance checks
- [ ] `crew_docs_check.py --ticket <id>` prints one line per document - CHANGELOG, each affected README, SECURITY.md, TODO.md - as `updated`, `not needed (<reason>)` or `MISSING`, plus `adr, runbooks: not measured`; exit 0 only when none is MISSING or unknown (`test_docs_check.py`).
- [ ] A ticket changing `plugin/<n>/` with no `[Unreleased]` line naming `<n>` and its marketplace version reads CHANGELOG `MISSING`, and a reason in docs.json does not waive it (must-refuse). A ticket changing only release-bookkeeping paths, or only `.work/`, does not require an entry (must-allow).
- [ ] README and SECURITY.md: a triggering change with neither an edit nor a recorded reason reads `MISSING`; with a reason, `not needed (<reason>)`; SECURITY.md with no security-relevant path is `not needed` without a reason (tests).
- [ ] TODO.md: each `deferred` item in docs.json missing from TODO.md's added lines reads `MISSING` (test).
- [ ] No scope base -> `unknown`, refusing, with the scope_base reason (test). The check writes nothing (tree byte-identical after a run).
- [ ] `/crew:docs <id>` records its per-document decisions and deferrals in `.work/tickets/<id>/docs.json`; `implement.md` step 6 orders tests, `/crew:docs`, the docs check, the refresh, then `/crew:review`; `done.md` runs the docs check and says it never edits a document; all within the 120-line cap (`test_lifecycle_commands.py`).
- [ ] `crew_autopilot.next_phase`: receipt not current and docs check failing -> `docs` with `/crew:docs <id>` (before `refresh`); MISSING after two docs runs -> stop naming the documents; receipt current and docs MISSING -> `docs-after-review` stop that writes nothing (tests).
- [ ] `crew_autopilot.py tracker --ticket <id>`: derives the status from disk, calls `crew_tracker.move`, returns `unchanged` when the tracker already agrees, stops on `could not update` with the reason and retry command, hands `delegated` back as the command to run, and stops with "T-0021 not landed" when the module is absent (tests).
- [ ] `test_tracker_move_after_receipt_keeps_bundle_hash`: `review_patch.compute`'s `bundle_sha256` is identical before and after a `move` for files kind, an Obsidian vault outside the worktree, and an ignored in-worktree vault; and for an unignored in-worktree vault T-0021 refuses and the hash is unchanged.
- [ ] `sabotage_docs.py`, registered at `plugin/crew/tests/sabotage.py:2927`: waiving CHANGELOG with a reason, reading `unknown` as ok, and ordering docs after review each turn a named test red.
- [ ] `.crew/verify.json` maps `crew_docs_check.py` and its tests to `python3 -m pytest plugin/crew/tests/test_docs_check.py -q`; `python3 scripts/check-marketplace.py` passes; version bumped with a CHANGELOG entry; README documents the phases and the three verdicts.
