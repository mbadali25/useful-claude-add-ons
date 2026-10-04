# T-0071 direction          status: direction   risk: high
## Ask
Filed on acceptance on 2026-09-27. The owner accepted T-0021's review round 5 FINDINGS (review_ledger: "round 5 FINDINGS accepted by the owner at 2026-09-27T14:05:45+00:00", bundle `0037527a793a`, head `74f52fae`, Codex / gpt family). The seven accepted FIXes are fixed here, not on T-0021's branch. The reviewer's lines, verbatim (the review output file in the T-0021 worktree):

1. **PRIORITY** `FIX|plugin/crew/hooks/scripts/crew_tracker.py:501|Lowercasing SSH usernames and repository paths merges distinct repositories, allowing foreign-card ownership checks to pass.|Reproduced normalization in memory: ssh://Alice@host/~/repo.git and ssh://alice@host/~/repo.git yield identical identities; so do /Repo.git and /repo.git under the same account. Their distinct case-sensitive server directories are consequently treated as one owner; vault writes traced, not run.`
2. `FIX|plugin/crew/hooks/scripts/crew_tracker.py:523|file:// authorities and Windows drive prefixes are treated as literal path text, giving the same repository different identities and refusing its own cards.|Reproduced with mocked Git output: file://localhost/srv/app.git resolves to the checkout's common directory, while /srv/app.git resolves to the origin path. Git's read-only trace confirms localhost is discarded. file:///C:/repos/app.git also retains the erroneous leading slash before the drive; Windows consequence traced, not run.`
3. `FIX|plugin/crew/hooks/scripts/crew_tracker.py:1299|Concurrent forward moves can move a completed card backwards without --reopen, leave INDEX and board disagreeing, and both report success.|Reproduced with in-memory backends: pause A's review move after its INDEX update; let B finish its done move; resume A's board write. Final INDEX is done, board is Review, and A reports updated: Done -> Review. Filesystem interleaving traced, not run.`
4. `FIX|plugin/crew/hooks/scripts/crew_tracker.py:1154|The note reader strips a literal terminal quote from an unquoted repo-id, rejecting the creating repository and potentially accepting another repository as owner.|Reproduced _card_owner with in-memory bytes containing "- repo-id: /srv/app.git'": the captured owner is /srv/app.git. _note_text writes identities unquoted, so an origin path ending in an apostrophe produces this mismatch; full create/move traced, not run.`
5. `FIX|plugin/crew/commands/fix.md:26|The initial create has no Jira/SDP delegation handling: it uses a local T-id and can stop on delegated exit 3 without creating the remote ticket.|Traced, not run: configure tracker.kind=jira or sdp and follow /crew:fix step 1. create returns exit 3 with MCP creation instructions; the explicit exit-3 handling at line 35 applies only to later calls, while step 1 requires stopping on other failures.`
6. `FIX|plugin/crew/hooks/scripts/crew_tracker.py:846|The checkbox matcher accepts a marker without following whitespace, so accepted cards can reach Done without a valid Markdown checkbox.|Reproduced in memory: replace the fixture card with "- [ ]T-0042" and move it to done. The result is "- [x]T-0042", which still lacks the whitespace required after the checkbox marker.`
7. `FIX|plugin/crew/tests/test_crew_tracker.py:1572|POSIX-specific race tests run unconditionally in the Windows default suite and fail without exercising their intended race.|Traced, not run on Windows: _DIR_FD is false, so the patched _open_pinned is never called for the pinned/replaced cases; outside/Board.md never exists and line 1584 raises FileNotFoundError. The note-pinning test has the same assumption, and test_board_keeps_its_mode also unconditionally expects POSIX mode 0664.`

#1 is the priority: case-folding the whole origin URL merges two repositories into one owner identity, which is the one finding that lets another repository's checkout pass the ownership check and move a card it does not own. The other six either refuse a legitimate operation, leave a board and INDEX disagreeing, or are Windows-only test defects.

Every anchor is BRANCH-ONLY: `T-0021-tracker` at `74f52fae` (crew 1.0.43). None of it is on main yet.
## Options
none yet - to be settled at /crew:brainstorm. Not started.
## Open questions
- #1: which parts of a URL may be case-folded (scheme and host are case-insensitive; user and path are not on every server).
- #5 (`fix.md` Jira/SDP create) and #7 (Windows-only tests) sit outside T-0021's round-4 Step 7 scope; say whether they belong here or in their own ticket.
## Approval
Status `direction`: minted on acceptance, not started. Depends on T-0021 landing.

## From T-0021's landing (CI, 2026-09-27)
CI Pytest run 36334828578, crew-shell-matrix (windows-latest), T-0021-land at 4d2ad22a. Owner decision 2026-09-27: merge #243, send these here.
- #7 confirmed in CI: `test_board_dir_moved_out_of_the_vault_after_pinning_writes_nothing_there[pinned]` and `[replaced]` (`FileNotFoundError: ... \\out\\Board.md`), `test_board_keeps_its_mode` (`assert ('0o666', 'Review') == ('0o664', 'Review')`), and the two note-dir tests. The note-dir tests and `[temp]` also expose a real Windows behaviour gap, filed separately as T-0077; fix the tests here, the behaviour there.
- New, not in #7: `test_resolve_compares_the_effective_vault` - `AssertionError: assert ('could not t...alse, 1, True) == ('could not t...True, 1, True)`. Detection works on Windows (kind is `could not tell`, the first vault is named); the second vault's path is not found in the message text. Likely path rendering/escaping (backslashes) in the problem string - UNCONFIRMED; check whether the message shows the path in a form a user can match.

## Update 2026-09-27
Item #7 (test_board_keeps_its_mode skip on Windows; test_resolve_compares_the_effective_vault compares repr) was fixed in T-0077 (merged #247, f96e9ec9, crew 1.0.49). Drop it from this ticket.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); the local heavy-run wrapper exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; each choice below is the recommended option, taken as the default and listed again under "Open questions for the owner".

**Still true (five of the seven, all on main now, none fixed).** T-0021 merged, so the anchors are no longer branch-only. `git log origin/main -- plugin/crew/hooks/scripts/crew_tracker.py` shows no commit after T-0077 and T-0088 that touches these lines. Re-run in memory on 2026-10-04 against origin/main's `crew_tracker.py` (functions called directly, no vault, no pytest):
- #1 `normal_url` (`:565`, `url.strip().lower()`): `ssh://Alice@host/~/repo.git` and `ssh://alice@host/~/repo.git` give one id; `git@host:Team/Repo.git` gives `git@host:team/repo`.
- #2 `_local_path` (`:587`): `file://localhost/srv/app.git` gives `localhost/srv/app.git` (relative, so `repo_id` falls to the common dir); `file:///C:/repos/app.git` gives `/C:/repos/app.git`.
- #4 `_NOTE_REPO_ID` (`:1279`): `- repo-id: /srv/app.git'` is read as `/srv/app.git`.
- #6 `_BOX` (`:910`) and `_checkbox` (`:913`): `- [ ]T-0042` moved to done becomes `- [x]T-0042`.
- #3 `_obsidian_move` (`:1388-1424`): the board lane (`key`, `:1389`) is fixed before the INDEX write (`:1421`) and never re-read, so the reviewer's interleaving still applies. Traced, not run.
- #5 `plugin/crew/commands/fix.md:26-33`: step 1 still mints a local `T-####` and stops on "any other failure"; `create` under Jira or SDP returns `delegated` with exit 3 (`crew_tracker.py:1472-1473`, `:117`). The exit-3 handling at `fix.md:35` covers later calls only.

**Changed.**
- #7 (Windows-only tests) is done: T-0077 merged it (CHANGELOG.md:2740, "T-0071 #7, two Windows-only tracker tests made portable"; `test_crew_tracker.py:960` skip, `:1546` `_HELD_BY_HANDLE`). Dropped, as the 2026-09-27 update already said.
- The tooling-PRs-land-alone rule (T-0087) now exists. `plugin/crew/tests/sabotage*.py` is in `HARNESS` (`scripts/check-tooling-pr.py:78`), and `crew_tracker.py` and `commands/fix.md` are in neither `HARNESS` nor `ALONGSIDE`. So the fixes and their sabotage mutations cannot share a PR. This ticket is the fix PR; the mutations are L-0669 (`children/1/`).
- `crew_ticket.py:1216` (mint's note take-back) now calls `crew_tracker._card_owner(paths, repo_id(top))`. `crew_ticket.py` is harness, so `_card_owner`'s signature and 3-tuple, and `repo_id`'s signature, must not change.
- Measured 2026-10-04, git 2.53.0 on Linux: `git ls-remote` answers the same bare repository for `file://<path>`, `file://localhost<path>`, `file://LOCALHOST<path>` and `file://otherhost<path>`. POSIX git discards any authority.

## Options
1. **Fix all six in place, smallest change each, fail closed (recommended, taken).**
   - #1: fold only what is case-insensitive everywhere: the scheme and the host (with its port). The username and the path keep their case. A note written by an older crew for a mixed-case origin then no longer matches; it stays refused, and the refusal names the one-line fix. No automatic acceptance of the old lowercased id: that id is exactly the ambiguous one.
   - #2: a `file://` URL's authority is not path text. On POSIX any authority is dropped (what git does, measured). On Windows an empty or `localhost` authority is dropped and the slash before a drive letter goes; any other authority keeps today's behaviour (the common dir), because git for Windows was not measured here.
   - #3: the board half places the card where INDEX says the ticket is at write time, read inside the board's atomic update, not where this call meant to put it. Two overlapping moves then converge on INDEX's final status, whichever board write lands last.
   - #4: a quote is stripped from a note's `repo-id:` only as a matched pair around the whole value.
   - #5: `fix.md` step 1 reads the tracker kind first, as `brainstorm.md` step 1 does, and under Jira or SDP creates the item through MCP and uses its key.
   - #6: a checkbox marker with no space after it is repaired to marker, space, text.
2. Accept an old lowercased id as "ours" for existing notes (compatibility read). Rejected: it keeps finding #1 open for every note already written.
3. Fold the path for a list of hosts known to be case-insensitive. Rejected: a guessed list fails correct lines on any other host, and an unknown must not collapse into the safe-looking value.
4. For #3, take a lock file across the INDEX and board writes. Rejected: a new cross-platform lock is a second mechanism beside `_atomic_update`'s re-read, and the vault is shared across repos that do not share a lock.

## Recommendation
Option 1. One PR for the six fixes with their tests and docs, then L-0669 (sabotage mutations) as a tooling-only PR.

## Open questions for the owner
- #1 compatibility: notes already written for an origin with capitals in its user or path will be refused until their `repo-id:` line is edited by hand (default taken). Say if a one-time compatibility read is wanted instead (option 2).
- #1 scope: should the path be folded for named case-insensitive hosts (option 3)? Default: no.
- #2 on Windows: a non-`localhost` `file://` authority keeps the common-dir identity until someone measures git for Windows. Acceptable?
- #5 stays in this ticket (the direction's own open question). Default: yes, it is six lines of command prose and its test.
