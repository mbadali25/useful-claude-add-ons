# Crew notes

Notes left for the `crew-lin` session (the session that owns crew's development) by other sessions,
to pick up when it is back online. Newest first. Remove an entry once it has been handled.

## 2026-10-13: crew 1.2.34, guard.log no longer stores the raw command (PR #635)

**From:** the `tss-lin` session (TheSelectSource on `dadeush-buntu`). It did this on the owner's
instruction (mbadali, first-hand, 2026-10-13: "Fix it yourself, but make a note somewhere in crew
notes.md to send over to the crew when crew-lin is back online") because `crew-lin` was offline.
`crew-lin`'s checkout and branch (`feat/lsp-plugins-terraform-angular-sql`) were not touched. The
work was done in a separate worktree, branch `fix/crew-guard-log-redact`, cut from `origin/main` at
`1fbc10d8d`.

**What was fixed.** With `guards.cloudGuard` on, `cloud_guard.py` wrote the whole command line as
the last field of every `.crew/guard.log` row it logged, denials included. Inline credentials
(`mysql -p<pw>`, `curl -u user:pw`, `Authorization:` headers, `*_SECRET*=`) were therefore stored in
clear. The writer moved to `plugin/crew/hooks/scripts/guard_log_redact.py`
(`cloud_guard._log = guard_log_redact.append_row`). It now writes the target and the command
redacted and capped at 200 characters, with the command led by `sha256:<12 hex>` of the redacted
text (never the raw line). Tests: `plugin/crew/tests/test_cloud_guard_log_redact.py`. Sabotage:
`GUARD_LOG_MUTATIONS` in `plugin/crew/tests/sabotage_cloud.py`. PR #635 has the full description
and the "Not verified" list.

**For `crew-lin` to check:**

1. **Release and version pin.** The PR sets crew to **1.2.34**. If another crew PR takes 1.2.34
   first, re-bump this one at landing (`plugin.json`, `marketplace.json`, `PLUGINS.md`, the
   CHANGELOG heading, then `scripts/sync-updates.py`).
2. **Marketplace re-pin.** After it merges, re-pin wherever installs are pinned to a commit, so
   machines actually receive 1.2.34. The TheSelectSource machines run crew 1.2.30 from the
   marketplace cache. This PR does not change either install script, so the README install-URL
   re-pin rule does not apply by itself.
3. **Existing `.crew/guard.log` files.** Rows written by 1.2.33 and earlier still hold commands as
   typed. Decide whether to purge them on machines where the guard was on, and whether crew should
   do that itself (for example a one-time rewrite or truncate in `heal_config`/SessionStart), or
   leave it to the release note. Rotate anything found. `.crew/*` is git-ignored by crew's shipped
   template, so the log should not normally be committed. That was read from this repo's CLAUDE.md
   ignore-policy section, not checked in each consuming repo.
4. **Neighbouring writer, not changed.** `crew_config._maybe_log` (`crew_config.py --guard <name>
   --record`) also writes the raw command to guard.log. A grep found no shipped caller that passes
   `--record`. Decide whether to route it through `guard_log_redact.log_text` too. Three tests in
   `tests/test_guards.py` assert the verbatim command there and would need to change.
5. **Code map.** `.crew/codemap/crew.md` cites `cloud_guard.py` line numbers that this PR shifted
   (+1 after the new import at `:133`, then fewer after the writer moved out). Those citations were
   not re-anchored.
6. **Gaps.** The bash and pwsh driver matrices (`-m slow`), `--all` and the full sabotage suite were
   not run by `tss-lin`. See the PR.

**Write-up of the defect:** `/repos/anew/TheSelectSource/.work/tss-lin-2026-10-13/crew-guard-log-defect-writeup.md`
(on `dadeush-buntu`, in TheSelectSource's ignored `.work/`, not in this repo).
