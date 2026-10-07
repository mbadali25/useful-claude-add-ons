# T-0071 tracker follow-up: repo identity keeps case, file:// origins, moves converge on INDEX, quote and checkbox reads, fix.md under Jira/SDP          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket (there was none). Written against origin/main `155fe6d8` (crew 1.0.322) from direction.md's "Direction check 2026-10-04", option 1. The owner was not available: every default is listed under Unknowns and in direction.md's "Open questions for the owner". There is no plan.md.

Scope against the original seven accepted findings: #1, #2, #3, #4, #5, #6 are here. #7 is already merged (T-0077). The sabotage mutations for these fixes are **L-0669** (`children/1/`), a tooling-only PR that lands after this one.

## Intent
A card on a shared Obsidian board is owned by exactly the repository that made it. Two repositories whose origin URLs differ only in the case of the user or path are two owners, and one repository reached through `file://`, `file://localhost` or a bare path is one owner. Two overlapping `move` calls leave INDEX and the board agreeing. A hand-typed checkbox with no space is repaired, a stray quote in a note is not stripped, and `/crew:fix` creates its ticket through MCP when the tracker is Jira or ServiceDesk Plus.

## Design (the six fixes)
All line numbers are `plugin/crew/hooks/scripts/crew_tracker.py` at origin/main unless a path is given.

1. **Identity keeps case (#1, PRIORITY).** `normal_url` (`:555`) stops lowercasing the whole URL. It folds only the scheme and the host with its port. The ssh username and the path keep their case. The `.git` suffix and trailing `/` are dropped as today, `.git` matched as written (lower case only). scp-style `user@Host:Path` folds `Host` only. Userinfo rules are unchanged (ssh keeps the user and drops a password; every other scheme drops all userinfo).
   - Old notes. A note written by an older crew holds the all-lowercase id. When the note's id differs from this repo's id only by case, the card stays refused (FOREIGN, exit 1, nothing written) and `_foreign`'s message gains one clause after its existing text: the note may carry this repo's id as older crew wrote it, and if the card is this repo's the fix is to change the line to `repo-id: <this repo's id>`. The existing sentence (`belongs to another repo (...)`) stays byte-identical in front of it. No automatic acceptance.
2. **`file://` authority and drive letters (#2).** `_local_path` (`:577`) parses the authority instead of treating it as path text. The platform is a parameter of a small pure helper, so both branches are tested on every OS.
   - POSIX: any authority is dropped; the path is what follows it (git 2.53.0 does this, measured).
   - Windows: an empty or `localhost` authority (any case) is dropped, and the `/` before a drive letter goes (`file:///C:/repos/app.git` is `C:/repos/app.git`). Any other authority returns what it returns today, so `repo_id` keeps the common-dir identity for it.
   - Percent-decoding of the path is unchanged.
3. **Moves converge on INDEX (#3).** In `_obsidian_move` (`:1388`), the board `edit` (`:1409`) no longer uses the lane computed at `:1389`. Inside the board's `_atomic_update` compute it re-reads the ticket's INDEX row (`_files_read`) and places the card in the lane for the status INDEX holds then.
   - INDEX row unreadable, or its status not in `LANE_FOR_STATUS`: the board is not written; the board line is `could not update` with `could not tell where INDEX has <ticket> now (<why>)`, exit 1.
   - INDEX status differs from the one this call asked for: the card goes to INDEX's lane and the line says so (`... (INDEX moved on to <status>)`).
   - `_atomic_update`'s existing re-read before replace (`:475`) makes a board changed by the other session recompute, which re-reads INDEX again.
4. **Quotes in a note's `repo-id:` (#4).** `_NOTE_REPO_ID` (`:1279`) and `_card_owner` (`:1283`) strip a quote only as a matched pair around the whole value (`"x"` or `'x'`). A lone leading or trailing quote is part of the id. `_card_owner` keeps its signature and its 3-tuple.
5. **`/crew:fix` under Jira and SDP (#5).** `plugin/crew/commands/fix.md` step 1 reads the tracker kind first (`crew_tracker.py resolve --root .`), the way `brainstorm.md:22-40` does. Files and Obsidian: unchanged text. Jira and ServiceDesk Plus: create the item through MCP as brainstorm step 1 says, use its key as `<id>`, cache at `.work/tickets/<KEY>/`; no local `T-####`, and a `delegated` line or exit 3 from `create` is that instruction, not a failure to stop on. `could not tell` stops.
6. **Checkbox spacing (#6).** `_BOX` (`:910`) and `_CHECKED` (`:751`) match a marker only when a space, a tab or the end of the line follows. `_checkbox` (`:913`) repairs `- [ ]T-0042` and `- [x]T-0042` to marker, one space, text, checked or not for the lane.

**Lines that must stay byte-identical**, because `plugin/crew/tests/sabotage_tracker.py` (harness, not editable in this PR) anchors on them:
- `        return normal_url(url)\n` (`:611`)
- `        url = f"{scheme}://{keep}{host.rpartition('@')[2]}{slash}{path}"\n` (`:572`)
- `    if ":" in head and not ntpath.splitdrive(url)[0]:\n        return None\n` (`:589-590`)
- `        if os.path.isabs(local) or ntpath.isabs(local):\n            return os.path.realpath(local)\n        return os.path.realpath(common)\n` (`:612-614`)
- `    if code == 2:\n        return os.path.realpath(common)\n` (`:615-616`)
- `    files = _files_move(root, ticket, status, reopen)\n    if files["state"] == FAILED:\n        return [files]\n` (`:1421-1423`)
- `        fixed[card["start"]] = _checkbox(lines[card["start"]], key)\n` (`:940`)
- `        if moved_from == columns[key] and new == "".join(current["lines"]):\n` (`:1413`). Fix 3 changes which lane `edit` uses, so keep the name `key` bound to the lane in use on this line.
- `    if not problem and here is None:\n        problem = _no_identity(root)\n` (`:1395-1396`)
- in `fix.md`: `If a line says \`id taken\`, that id is not yours`, `On any other failure, stop: show me its lines and write nothing under that id`, and the `move ... --to review` call line.

Before editing, grep `sabotage_tracker.py` for every string it anchors in `crew_tracker.py`, `fix.md` and `brainstorm.md` and re-check this list; each must still occur exactly as often as it does on origin/main.

## Exclusions
- No edit to any `HARNESS` path (`scripts/check-tooling-pr.py:58-87`): not `plugin/crew/tests/sabotage*.py`, not `crew_ticket.py` (its caller at `:1216` keeps working because signatures do not change), not `review_*.py`, `scope_guard.py` or `verify-gate.*`. New mutations are L-0669.
- No automatic acceptance of an old lowercased id, no note rewrite, no migration command. Crew never rewrites a ticket note.
- No list of case-insensitive hosts. No path folding for any host.
- No lock file and no new cross-process mechanism for #3.
- No change to `LANE_FOR_STATUS` or `STATUS_ORDER` (that is L-0530 / L-0571), to the vault walk or pinning (T-0081), or to `resolve`.
- No change to the Jira or SDP sync commands, and no MCP call from `crew_tracker.py`.
- No new hook, no new config key, no change to `.crew/verify.json`.
- #7 (Windows-only tests): already merged with T-0077.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04. Reproductions marked "run" called the functions directly in memory; nothing wrote to a vault.
- plugin/crew/hooks/scripts/crew_tracker.py:555-574 `normal_url`; :565 `url = url.strip().lower()`. Run: `ssh://Alice@host/~/repo.git` and `ssh://alice@host/~/repo.git` return the same id; `git@host:Team/Repo.git` returns `git@host:team/repo`.
- plugin/crew/hooks/scripts/crew_tracker.py:577-591 `_local_path`; :587 slices off `file://` and unquotes the rest. Run: `file://localhost/srv/app.git` returns `localhost/srv/app.git`; `file:///C:/repos/app.git` returns `/C:/repos/app.git`.
- plugin/crew/hooks/scripts/crew_tracker.py:594-617 `repo_id`: a non-absolute local path falls to the common dir (:614).
- Measured, git 2.53.0 on Linux, throwaway bare repo: `git ls-remote` exits 0 for `file://<path>`, `file://localhost<path>`, `file://LOCALHOST<path>` and `file://otherhost<path>`.
- plugin/crew/hooks/scripts/crew_tracker.py:1279 `_NOTE_REPO_ID = ...['\"]?(.+?)['\"]?[ \t\r]*$`. Run: `- repo-id: /srv/app.git'` yields `/srv/app.git`. :1227-1233 `_note_text` writes the id unquoted (:1232).
- plugin/crew/hooks/scripts/crew_tracker.py:1283-1299 `_card_owner`; :1302-1304 `_foreign`; :1307-1309 `_unclaimed`.
- plugin/crew/hooks/scripts/crew_ticket.py:1216 calls `crew_tracker._card_owner(paths, crew_tracker.repo_id(top))` and unpacks three values.
- plugin/crew/hooks/scripts/crew_tracker.py:751 `_CHECKED`, :910 `_BOX`, :913-923 `_checkbox`. Run: `_checkbox("- [ ]T-0042", "done")` returns `- [x]T-0042`.
- plugin/crew/hooks/scripts/crew_tracker.py:1388-1424 `_obsidian_move`: `key` set at :1389, the INDEX row read once at :1392, `edit` at :1409-1417 uses `key`, INDEX written at :1421, board at :1424. :1208-1224 `_board_write`; :449-491 `_atomic_update`, re-read before replace at :475. :692-717 `_files_move`; :720-735 `_files_read`.
- plugin/crew/hooks/scripts/crew_tracker.py:1465-1478 `create`; :1472-1473 returns `DELEGATED` for Jira and SDP; :116 `_CREATE_DELEGATED`; :117 `_EXIT` maps `DELEGATED` to 3.
- plugin/crew/commands/fix.md:26-33 step 1 (local `T-####`, then `create`, "On any other failure, stop"); :35-38 the exit-3 rule for "every later tracker call". plugin/crew/commands/brainstorm.md:22-40 the resolve-first wording to mirror. fix.md is 109 lines; the command budget is 120 (`plugin/crew/BUDGETS.md`).
- Tests that pin today's behaviour and must change: plugin/crew/tests/test_crew_tracker.py:1241-1251 `test_repo_id_normalises_the_origin_url` (expects `owner/repo` lowercased), :1254-1262 `test_note_records_repo_id_without_credentials` (expects `team/repo`). Neighbours to keep green: :2083 `test_file_url_escapes_are_decoded`, :2100-2111 `test_repo_id_keeps_an_ssh_username_and_drops_secrets`, :2215 and :2224 the boxless-card tests.
- plugin/crew/tests/test_lifecycle_commands.py:338 `test_a_taken_id_is_never_written_under` and its `TAKEN_RULE` / `STOP_RULE` strings read fix.md's step 1.
- plugin/crew/tests/sabotage_tracker.py anchors: :340 (`return normal_url(url)`, also the replacement text at :556), :355 (the userinfo f-string), :641-654 (the `_files_move` gate), :661 (`_checkbox` call), :512-515 and :608-612 (fix.md).
- scripts/check-tooling-pr.py:58-87 `HARNESS` includes `plugin/crew/tests/sabotage*.py` and `crew_ticket.py`; :99-118 `ALONGSIDE` has no production path.
- .crew/verify.json:368-374 maps `crew_tracker.py` and `test_crew_tracker.py` to `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q`.
- Docs that state the old rule: plugin/crew/README.md:1726-1734 ("the origin URL lowercased"), docs/guides/crew/src/memory-and-obsidian.md:278-282 ("lowercased"), docs/guides/crew/src/troubleshooting.md:428-435 (the refusal lines), .crew/codemap/crew.md:1126-1140.
- #7 done: CHANGELOG.md:2740-2742.
- Nothing on main fixes #1-#6: `git log origin/main -- plugin/crew/hooks/scripts/crew_tracker.py` ends at `55b4ca2d` (T-0088) and `ba2ee465` (T-0077), neither touching these functions.

## Unknowns
- Old notes for mixed-case origins are refused until edited by hand. Default taken; owner may ask for a compatibility read instead. Accepted as risk until answered.
- Git for Windows and a non-`localhost` `file://` authority: not measured. Default: behaviour unchanged for that case (common-dir identity). Resolved when someone runs `git ls-remote file://<host>/<share>/...` on Windows; a follow-up, not this ticket.
- The drive-letter branch runs only on Windows in production. It is covered here through the pure helper; a native run is the crew-shell-matrix Windows CI job on the PR. If that job is not available, say so in the PR body.
- #3 is proven by a forced interleaving in one process (the second move is run from inside a patched `_files_move`), not by two real processes. Accepted: it is the reviewer's own reproduction.
- #3 converges only when every INDEX writer follows with a board write. A session killed between the two leaves the board behind; `read` already reports that disagreement (:1444-1445). Accepted, unchanged.
- An id that itself starts and ends with the same quote character (a path named that way) still loses the pair when read back. Accepted as risk; state it in the README.
- L-0530 / L-0571 may add statuses to `LANE_FOR_STATUS` first. Fix 3 reads the table, so it needs no change either way; re-read `:91-99` before planning.
- The crew patch version is the next free one at implement time.

## Size and split
- Production lines added: about 95 (`crew_tracker.py` about 85: identity 30, file URL 20, converge 20, quotes 8, checkbox 7; `commands/fix.md` about 10). Under the 300-line rule.
- No new parser and no new state machine: four existing matchers are narrowed. One new guard (fix 3's INDEX re-read).
- Harness: the fixes are feature work and their mutations live in `plugin/crew/tests/sabotage_tracker.py`, a `HARNESS` path. So the mutations are split out as **L-0669** (`children/1/spec.md`), tooling-only, landing after this PR.

## Touch
- `plugin/crew/hooks/scripts/crew_tracker.py`
- `plugin/crew/commands/fix.md`
- `plugin/crew/tests/test_crew_tracker.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/tests/tracker_fixtures/**`
- `plugin/crew/README.md` section 13c, "Whose card"
- `plugin/crew/commands/obsidian-sync.md` only if its ownership sentence at line 102 needs the old-note clause
- `docs/guides/crew/src/memory-and-obsidian.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/**` the HTML, DOCX and PDF rebuilt by the guide build script
- `.crew/codemap/crew.md`
- `docs/diagrams/**` regenerated anchors only
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting changes); `.crew/verify.json` (the rule at :368-374 already covers both files); every `HARNESS` path.

## Acceptance checks
Commands run from the repo root; on a memory-bound host each pytest command goes through the heavy-run wrapper. Rule: `.crew/verify.json` crew_tracker rule (:368-374) unless another is named.
- [ ] #1 must-block: two repos on one board whose origins differ only in user case (`ssh://Alice@host/~/repo.git`, `ssh://alice@host/~/repo.git`) and only in path case (`https://example.invalid/Team/Repo.git`, `https://example.invalid/team/repo.git`): the second repo's `move` exits 1, says `belongs to another repo`, and vault and repo are byte-identical. `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q -k test_origins_differing_only_in_case_are_two_repos`
- [ ] #1 must-allow: scheme and host case do not split a repo (`HTTPS://Example.invalid/Team/Repo.git` and `https://example.invalid/Team/Repo` give one id; `git@GitHub.example:Team/Repo.git` keeps `Team/Repo`). `-k test_repo_id_folds_only_scheme_and_host`. `test_repo_id_normalises_the_origin_url` and `test_note_records_repo_id_without_credentials` are updated to the case-preserving ids; credentials are still absent from the note.
- [ ] #1 old note: a note holding the all-lowercase form of this repo's mixed-case id refuses `move` (exit 1, nothing written) and the line names `repo-id: <this repo's id>` as the fix. `-k test_a_lowercased_old_note_is_refused_with_the_fix`
- [ ] #2: `file://<abs>`, `file://localhost<abs>`, `file://LOCALHOST<abs>` and the bare `<abs>` give one `repo_id`, and `git ls-remote` on the `localhost` form answers that same bare repo. `-k test_file_url_authority_is_not_path_text`
- [ ] #2 drive letters, through the pure helper with the platform passed in: Windows gives `C:/repos/app.git` for `file:///C:/repos/app.git` and for `file://localhost/C:/repos/app.git`; POSIX keeps `/C:/repos/app.git`; a non-`localhost` authority on Windows is not turned into a local path. `-k test_file_url_drive_prefix_by_platform`
- [ ] #3: with move A (to review) paused after its INDEX write while move B (to done) completes, A's board write leaves INDEX `done`, the card in Done, checked, below `**Complete**`, and A's board line names the lane INDEX holds. `-k test_overlapping_moves_leave_board_and_index_agreeing`
- [ ] #3 could-not-tell: INDEX row gone or carrying an unknown status at board-write time leaves the board byte-identical, exit 1, line contains `could not tell where INDEX has`. `-k test_board_is_not_moved_when_index_cannot_be_read_at_write_time`
- [ ] #4 must-block: a note with `- repo-id: /srv/app.git'` is foreign to a repo whose id is `/srv/app.git`. Must-allow: `"<id>"` and `'<id>'` (matched pairs) and the bare id are ours; a CRLF note still reads. `-k "test_note_repo_id_quote"`
- [ ] #6: `- [ ]T-0042` moved to done is `- [x] T-0042`; `- [x]T-0042` moved to review is `- [ ] T-0042`; the two boxless-card tests still pass. `-k "test_checkbox_without_a_space_is_repaired or checkboxless"`
- [ ] #5: fix.md step 1 names `crew_tracker.py resolve`, the Jira/SDP MCP create and its key, before any `.work/tickets/` write, and still carries `TAKEN_RULE` and `STOP_RULE`. `python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py -q -k "test_fix_mints_through_mcp_under_jira_and_sdp or test_a_taken_id_is_never_written_under or test_every_tracker_call_in_commands_carries_the_prefix"`. fix.md stays at or under 120 lines: `git show HEAD:plugin/crew/commands/fix.md | wc -l`.
- [ ] Whole files pass: `python3 -m pytest plugin/crew/tests/test_crew_tracker.py plugin/crew/tests/test_lifecycle_commands.py -q` and, because mint reads `_card_owner`, `python3 -m pytest plugin/crew/tests/ -q -k "mint"`.
- [ ] Each new test was seen failing before its fix (test-first; quote the red line in the phase evidence).
- [ ] No harness path changed and every existing mutation still applies: `python3 scripts/check-tooling-pr.py` exits 0 with `tooling-pr: no harness path changed`, `git diff --name-only origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py' plugin/crew/hooks/scripts/crew_ticket.py` prints nothing, and the tracker mutations still go red: `python3 plugin/crew/tests/sabotage.py` (heavy; run once, serially, before review).
- [ ] Docs: README section 13c, the guide's "Whose card it is" and the code map no longer say "lowercased" for the whole URL and state scheme-and-host folding, the old-note refusal, the `file://` rule, the matched-quote rule and the converge-on-INDEX rule; troubleshooting gains the old-note refusal line with its fix; guide outputs rebuilt (`python3 docs/guides/crew/src/build.py`). `git grep -n "URL lowercased\|URL, lowercased" -- plugin/crew/README.md docs/guides/crew/src` prints nothing.
- [ ] crew bumped to the next free patch in `plugin.json` and `marketplace.json`, PLUGINS.md's version row and a CHANGELOG entry that flags the identity change as **breaking for notes written with a mixed-case origin**; after the commit `python3 scripts/check-marketplace.py` passes.
- [ ] Lint as CI: `python3 -m pylint -j 4 plugin/crew/hooks/scripts/crew_tracker.py plugin/crew/tests/test_crew_tracker.py` reports no new finding.

## Dependencies
Must land first:
- T-0021 (merged): the tracker these findings were accepted on.
- T-0077 (merged): fixed #7 and added the Windows directory holds; this spec's line numbers are after it.
- T-0087 (merged): the tooling-PRs-land-alone rule that puts the mutations in L-0669.
- T-0019 (in-progress in INDEX; its mint code is on origin/main at `crew_ticket.py:1216`): the second caller of `_card_owner`. No order forced; the signature is frozen here.

Same file, no order forced (merge main before review if one lands first): T-0081 (direction; vault walk identity), L-0530 and L-0571 (direction; `LANE_FOR_STATUS` rows), T-0022 (approved; autopilot tracker phase calls `move`), T-0052 (spec; split through mint).

Blocks: L-0669 (the sabotage mutations for these fixes). Nothing else in INDEX names T-0071.

## Split
- L-0669 (child 1 of T-0071, filed 2026-10-04): sabotage mutations for the T-0071 tracker fixes (tooling PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
