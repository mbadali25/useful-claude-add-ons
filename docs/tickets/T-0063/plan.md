# T-0063 plan            spec: .work/tickets/T-0063/spec.md

Work in a fresh worktree, `/repos/personal/uca-t-0063`, on branch `T-0063-build` off origin/main. Copy `.work/tickets/T-0063/` into it and confirm the copy with `cmp`. The anchors are origin/main `502cb137` (crew 1.0.42). Re-grep each quoted string before its step. If a line has moved (T-0064 edits `_graph` in `crew_refresh_check.py`; T-0010, T-0029 and T-0067 edit `crew_autopilot.py` and `autopilot.md`), re-anchor from the new line and keep the test unchanged.

Every step writes its must-refuse test and its must-allow neighbour first, and watches both fail for the stated reason. Then it implements, then it adds sabotage mutations that must go red. Heavy runs (pytest, `sabotage.py`) are serial under `flock /root/crew-tmp/heavy.lock` with `TMPDIR=/root/crew-tmp/t-0063`, after `free -g`.

No second opinion is needed. The design has three parts. First, a second INDEX read that runs only when the local row is missing, plus a comparison when both rows exist. Second, a set of uncommitted paths under directories the module already defines. Third, a hash lookup in a file graphify already writes. Steps 1, 2 and 3 are independent. Step 4 depends on step 2. Steps 5 and 6 run last.

### Step 1: autopilot reads the INDEX row through the main checkout
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/tests/sabotage_autopilot.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0063 python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q -p no:cacheprovider
Risk: med. A row read from the wrong checkout could drive a ticket whose direction nobody approved. The disagreement stop and the unreadable-main test bound it, and the folder is never read from the main checkout.
- [ ] Tests first, in `plugin/crew/tests/test_crew_autopilot.py`, under a new section `# --- T-0063: the main checkout's INDEX ---`. Add a fixture `_lane(tmp_path)`: `make_repo(tmp_path / "main", mode="off")`, one commit, then `git worktree add <tmp>/lane -b lane`. It returns `(main, lane)`. `.work/` is ignored in the fixture's `.gitignore`, as it is here, so the lane starts with no INDEX.
  - `test_next_reads_the_index_row_from_the_main_checkout`: `_index(main, "T-1 | ready | high | r | title")`, and the ticket folder (direction, spec, plan) is written into the lane only. `crew_autopilot.next_phase(str(lane), "T-1")` has `phase` other than `direction-approval`. `result["index_source"]` equals `os.path.join(os.path.realpath(main), ".work", "INDEX.md")`, and that path is in `result["evidence"]`.
  - `test_next_no_row_in_either_checkout_stops`: neither INDEX has a row. The result is `direction-approval`, stop True, and the reason contains both INDEX paths.
  - `test_next_disagreeing_rows_stop`: the lane row `ready`, the main row `done`. Stop True, the reason starts `index-disagreement:` and names both paths and both cells.
  - `test_next_agreeing_rows_proceed`: both `ready`. No `index-disagreement`.
  - `test_next_local_row_answers_without_a_main_row`: the lane row `ready` and no main row. It proceeds, and `index_source` is the lane's INDEX.
  - `test_next_folder_only_in_the_main_checkout_stops_naming_it`: the folder is in main only, and the row is in main. Stop True. The reason contains the main folder path and `cp -r`, and `evidence` does not contain the main `spec.md`.
  - `test_resume_folder_only_in_the_main_checkout_stops_naming_it`: `resume_target(str(lane), "T-1")` with the folder in main only. Stop True, and the reason names the main folder.
  - `test_an_unreadable_main_checkout_is_cannot_tell`: monkeypatch `crew_autopilot._main_checkout` to return `(None, "git worktree list failed: boom")`, with no lane row. Stop True, the reason contains `boom`, and it does not contain "has no table row" said of the main checkout.
  - `test_resume_finds_the_open_ticket_through_the_main_checkout_index`: no pointer, no lane INDEX, the main INDEX has one open row, and the folder is in the lane. `resume_target(str(lane))["ticket"] == "T-1"`, with `source` `.work/INDEX.md (main checkout)`.
  - Run them and watch them fail (AttributeError on `index_source`, or the wrong phase).
- [ ] Implement in `plugin/crew/hooks/scripts/crew_autopilot.py`:
  - `_main_checkout(top)` returns `(path, why)`. It runs `git_out(top, "worktree", "list", "--porcelain")`. The first `worktree <path>` record is the main checkout. A `bare` record, a failed call or an unreadable path gives `(None, why)`. It compares with `os.path.realpath`. When the result equals `top`, it returns `(None, "")`, meaning this is the main checkout and there is nothing else to read.
  - `_index_rows(top)` (`:152-159`) gains an `index_path` parameter and returns `(ticket, line)` from that file.
  - Replace `_index_status(top, ticket)` (`:162-171`) with `_index_row(top, ticket)`, which returns `{"status", "source", "other", "why"}`. It reads the local row first. When there is no local row, it reads the main checkout's. When both rows exist and the cells differ, `status` is `None` and `other` holds both. `why` carries the `_main_checkout` failure.
  - In `_phase` (`:314-347`), use `_index_row`. Evidence gets the INDEX path that answered (absolute when it is outside `top`). The result gains `index_source`. A disagreement returns `answer("direction-approval", True, "index-disagreement: …")`. A missing row names both paths, or the failure `why`.
  - Before `_index_row` in `_phase` (after `folder`, `:317`): when the local folder is missing, check `<main>/.work/tickets/<id>/`. When it exists there, stop with `"{ticket}'s folder is only in the main checkout ({path}); copy it here first: cp -r {path} {local} - autopilot never reads a ticket's contract from another checkout"`. `resume_target` (`:537`) gets the same check and the same wording.
  - `open_index_tickets(top)` (`:181-189`) takes the local rows, plus main rows for tickets with no local row. It still requires the local folder. `resume_target` (`:554-562`) labels that source `.work/INDEX.md (main checkout)` when the row came from the main checkout.
  - Add `("index-disagreement", "the worktree's and the main checkout's .work/INDEX.md rows for the ticket disagree")` to `FIXED_STOPS` (`:116-133`). Update the docstring's phase table row (`:18`) and add a paragraph after `:20`, keeping the file under `max-module-lines`.
  - Keep `main` (`:639`) printing the same one-line format. `index_source` is in `--json` only.
- [ ] Sabotage, appended to `AUTOPILOT_MUTATIONS` in `plugin/crew/tests/sabotage_autopilot.py`:
  - "the main checkout is never consulted" makes `_main_checkout` return `(None, "")` (red on `tests/test_crew_autopilot.py::test_next_reads_the_index_row_from_the_main_checkout`).
  - "disagreeing rows: the local one wins silently" (red on `test_next_disagreeing_rows_stop`).
  - "a main-only folder is not named" drops the main-folder check in `_phase` (red on `test_next_folder_only_in_the_main_checkout_stops_naming_it`).
  - "a listing failure reads as no row" drops `why` from the reason (red on `test_an_unreadable_main_checkout_is_cannot_tell`).
- [ ] `test_command_names_every_fixed_and_human_stop` goes red until step 5 names `index-disagreement` in `autopilot.md`. That is expected here, and step 5 turns it green.
- [ ] Run the Test command. Everything is green except that one test, which is named in the step report.

### Step 2: the refresh check says `fresh-uncommitted`
Files: plugin/crew/hooks/scripts/crew_refresh_check.py, plugin/crew/tests/test_refresh_check.py, plugin/crew/tests/sabotage_refresh.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0063 python3 -m pytest plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_scope_guard_refresh_artifacts.py plugin/crew/tests/test_completion_audit_refresh_artifacts.py -q -p no:cacheprovider
Risk: high. This check can refuse `/crew:done`. A false `fresh` loses refreshed artifacts at close. A false `fresh-uncommitted` blocks every ticket, and the ignored-output test bounds that.
- [ ] Tests first, in `plugin/crew/tests/test_refresh_check.py`, reusing `_repo`, `_codemap`, `_diagram`, `_graph` and `_check` (`:62-102`). Add `_write`-only variants that do not commit:
  - `test_refreshed_but_uncommitted_codemap_is_fresh_uncommitted`: `_codemap(root, "app", start, ["src/app.py"])`, commit a change to `src/app.py`, then write (do not commit) the map anchored at HEAD. The artifact and the overall result are `fresh-uncommitted`, and `result["uncommitted"] == [".crew/codemap/app.md"]`.
  - `test_cli_fresh_uncommitted_exits_one`: the same fixture through `_run_cli`. The return code is 1, and stdout has `fresh-uncommitted` and `commit` on the top line.
  - `test_untracked_refresh_artifact_is_fresh_uncommitted`: a new, untracked `docs/diagrams/architecture.mmd` anchored at HEAD, reached by the change. The overall result is `fresh-uncommitted`.
  - `test_staged_refresh_artifact_is_fresh_uncommitted`: the codemap case with `git add` and no commit. Still `fresh-uncommitted`.
  - `test_ignored_graph_output_is_not_uncommitted`: `.gitignore` holds `graphify-out/*` and `!graphify-out/graph.json`, and an untracked `graphify-out/manifest.json` exists. The result stays `fresh` (the must-allow case).
  - `test_uncommitted_out_of_scope_refresh_path_still_counts`: an uncommitted `.claude/rules/x.md` with every artifact fresh. The overall result is `fresh-uncommitted`, and `uncommitted` lists it.
  - `test_stale_outranks_fresh_uncommitted`: one stale map and one uncommitted fresh map. The overall result is `stale`.
  - `test_a_library_call_never_rewrites_the_index` (`:316`) is extended with an uncommitted refresh artifact, so the new listing is proven read-only too.
  - Run them and watch them fail (`fresh` where `fresh-uncommitted` is expected).
- [ ] Implement in `plugin/crew/hooks/scripts/crew_refresh_check.py`:
  - Add `FRESH_UNCOMMITTED = "fresh-uncommitted"` beside `FRESH` (`:152`).
  - Add `_uncommitted(top, dirs, untracked)`. It returns the sorted paths under `dirs` from `_moved_in_tree(top, "HEAD", dirs)` (`:294`), plus the members of `untracked` under `dirs` (`_reaches`), or `None` when git cannot answer. `None` makes the result `unknown` with the stop "git could not list uncommitted refresh artifacts". It never reads as clean.
  - In `ticket_freshness` (`:576-653`), compute it from `refresh_artifact_paths(top, cfg)` after the artifacts. An artifact whose status is `fresh` and whose own file is listed becomes `fresh-uncommitted`, with the reason `"… ; its refreshed file is uncommitted: commit it"`. The own file is `.crew/codemap/<name>.md` for a codemap, the diagram source and same-stem renders in the diagrams dir for a diagram, and anything under `graph.out` for the graph.
  - Replace `overall` (`:629`) with: `unknown`, else `stale`, else `fresh-uncommitted` when any artifact is `fresh-uncommitted` or `uncommitted` is non-empty, else `fresh`. Add `"uncommitted": [...]` to the result, and to `_unmeasured` as `[]`. `_unconfirmed` (`:554`) also turns `fresh-uncommitted` into `unknown`.
  - In `_render` (`:655-673`), add the line `  uncommitted: <few> - commit these, then re-run` when the list is non-empty. `main` (`:693`) still returns 0 only on `FRESH`.
  - Update the docstring's "Four values" section (`:73`) to five values, with one paragraph explaining that `fresh` means current and committed.
- [ ] Sabotage, appended to `REFRESH_MUTATIONS` in `plugin/crew/tests/sabotage_refresh.py`:
  - "uncommitted refresh artifacts read fresh" makes `_uncommitted` return `[]` (red on `tests/test_refresh_check.py::test_refreshed_but_uncommitted_codemap_is_fresh_uncommitted`).
  - "untracked refresh artifacts ignored" (red on `test_untracked_refresh_artifact_is_fresh_uncommitted`).
  - "fresh-uncommitted exits 0" (red on `test_cli_fresh_uncommitted_exits_one`).
  - "fresh-uncommitted outranks stale" swaps the precedence (red on `test_stale_outranks_fresh_uncommitted`).
  - "an unanswerable listing reads clean" maps `None` to `[]` (red on a new `test_uncommitted_listing_failure_is_unknown`, which monkeypatches `_moved_in_tree` to return None for HEAD).
- [ ] Run the Test command. It must be all green, including `test_every_refresh_sabotage_anchor_is_present_exactly_once`.

### Step 3: graphify's manifest confirms an unchanged graph
Files: plugin/crew/hooks/scripts/crew_refresh_check.py, plugin/crew/tests/test_refresh_check.py, plugin/crew/tests/sabotage_refresh.py, TODO.md
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0063 python3 -m pytest plugin/crew/tests/test_refresh_check.py -q -p no:cacheprovider
Risk: med. A false confirmation reads a stale graph as fresh. The old-hash, deleted-path and uncommitted-code tests bound it, and a manifest that cannot be read or parsed falls back to today's answer.
- [ ] Re-read every `save_manifest` / `_save_manifest` caller in the installed graphify (`grep -rn "save_manifest(" ~/.local/share/uv/tools/graphifyy/lib/python3.*/site-packages/graphify/`). Confirm that each one runs only after a successful `graph.json` write, or on the same-topology path (`watch.py:1958-1983`, `:2002-2031`, `:2175-2178`, `cli.py:4304`, `:4427`, `:4611` in 0.9.65). Record the version and the callers in the `_graph` docstring. If any caller breaks that rule, skip the rest of this step and file "manifest confirmation unsafe: <caller>" to `TODO.md` under the next T-number. The spec's Unknowns names that exit.
- [ ] Tests first, in `plugin/crew/tests/test_refresh_check.py`. The helper `_manifest(root, entries)` writes `graphify-out/manifest.json` as `{path: {"mtime": 0, "seen": 0, "ast_hash": md5, "semantic_hash": ""}}` and ignores it through `.gitignore` (`graphify-out/*` with `!graph.json` and `!GRAPH_REPORT.md`):
  - `test_graph_confirmed_by_the_manifest_is_fresh`: `_graph(root, start)`, commit a change to `src/app.py`, then `_manifest` with the MD5 of the new bytes. The graph is `fresh`, and the reason contains `manifest`.
  - `test_graph_manifest_with_an_old_hash_is_stale`: the manifest has the MD5 of the old bytes. The graph is `stale`, with the command `graphify update .`.
  - `test_graph_manifest_never_confirms_a_deleted_path`: the ticket deletes `src/other.py`, and the manifest has no entry for it (or the old one). The graph is `stale`.
  - `test_graph_manifest_does_not_confirm_uncommitted_code`: an uncommitted edit to `src/app.py` with a matching manifest. `stale`, with "commit, then refresh".
  - `test_graph_unparseable_manifest_is_the_sha_answer`: the manifest is `{`. The graph is `stale`, and the reason says the manifest was not usable.
  - `test_graph_manifest_confirms_only_every_reached_path`: two changed code files, and only one matches. `stale`.
  - Run them. The first fails (`stale`), and the rest pass already. Record which.
- [ ] Implement in `_graph` (`:489-506`). After `_judge` returns `STALE` with a reason that is not the uncommitted one (`_judge` gains a returned flag, `pending`, so the check reads no prose), call `_manifest_confirms(root, graph_out, code)`. It reads `<graph.out>/manifest.json` with `read_text` and `json.loads`. It returns `(True, "")` only when every path in `code` exists and has an entry whose `ast_hash` equals `hashlib.md5(bytes).hexdigest()` (with `usedforsecurity=False`), and `(False, why)` otherwise. On `True`, return `_entry("graph", graph_out, FRESH, f"graphify's manifest records the current content of every changed code path (topology unchanged since {sha[:12]})", command)`. Otherwise, keep the stale entry and append `why` when the manifest was missing or unparseable.
- [ ] Sabotage, in `sabotage_refresh.py`:
  - "the manifest hash is not compared" (red on `tests/test_refresh_check.py::test_graph_manifest_with_an_old_hash_is_stale`).
  - "the manifest confirms a deleted path" skips the existence check (red on `test_graph_manifest_never_confirms_a_deleted_path`).
  - "the manifest confirms uncommitted code" ignores `pending` (red on `test_graph_manifest_does_not_confirm_uncommitted_code`).
  - "one matching path confirms all" changes `all` to `any` (red on `test_graph_manifest_confirms_only_every_reached_path`).
- [ ] Run the Test command. It must be all green.

### Step 4: autopilot commits refreshed artifacts instead of calling them fresh
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/tests/sabotage_autopilot.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0063 python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_refresh_check.py -q -p no:cacheprovider
Risk: med. A commit command that names the wrong paths commits work outside the refresh. The command is built from `uncommitted` only, and a test pins its exact text.
- [ ] Tests first, in `plugin/crew/tests/test_crew_autopilot.py`. Extend the `_refresh` fixture (`:104`) to accept `uncommitted=[...]`, returning the `ticket_freshness` shape with status `fresh-uncommitted`:
  - `test_next_commit_refresh_before_review`: no receipt, `fresh-uncommitted` with `[".crew/codemap/app.md", "docs/diagrams/a b.mmd"]`. The phase is `commit-refresh` and stop is False. The command is `git add -- .crew/codemap/app.md 'docs/diagrams/a b.mmd' && git commit -m "T-1: commit refreshed artifacts"`.
  - `test_next_commit_refresh_after_an_accepted_review`: the receipt is current, with the same paths. The phase is `commit-refresh` and stop is False, never `done` and never `stale-after-review`.
  - `test_next_done_only_when_committed`: the receipt is current and the state is `fresh`. The phase is `done` (today's behaviour).
  - `test_next_commit_refresh_with_no_paths_stops`: `fresh-uncommitted` with an empty `uncommitted`, which cannot happen but is handled. Stop True, and never `done`.
  - `test_committing_refreshed_artifacts_keeps_the_review_bundle`: a real repo from `make_repo`, a scope base, a committed code change, and an uncommitted `.crew/codemap/app.md`. `review_ledger._current_hash(root, base)` before and after `git add … && git commit` is equal.
  - Run them and watch the first two fail (today: `unsettled`, a stop).
- [ ] Implement in `_refresh_state` (`:259-286`). `status == "fresh-uncommitted"` returns `{"state": "uncommitted", "paths": result.get("uncommitted") or [], ...}`. In `_review_phase` (`:434-448`), before both the `not ok` branch and the post-receipt branch: `uncommitted` with paths gives `answer("commit-refresh", False, f"refreshed artifacts are uncommitted: {few}; the review bundle is the working state, so this commit leaves any receipt current", command)`, with the command built with `shlex.quote`. `uncommitted` without paths is a stop. Add the docstring rows for `commit-refresh` to the phase table (`:14-37`).
- [ ] Sabotage, in `sabotage_autopilot.py`:
  - "fresh-uncommitted reads as fresh" maps the new state to `FRESH` (red on `tests/test_crew_autopilot.py::test_next_commit_refresh_after_an_accepted_review`).
  - "the commit names no paths" drops the paths from the command (red on `test_next_commit_refresh_before_review`).
  - "an empty list proceeds" (red on `test_next_commit_refresh_with_no_paths_stops`).
- [ ] Run the Test command. It must be all green apart from the step 1 command-text test, which step 5 fixes.

### Step 5: the documents that describe these behaviours
Files: plugin/crew/commands/autopilot.md, plugin/crew/commands/done.md, plugin/crew/commands/implement.md, plugin/crew/README.md, .crew/codemap/crew.md, docs/diagrams/process-crew-lifecycle.mmd, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/**, .crew/verify.json
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0063 python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_refresh_check.py -q -p no:cacheprovider && (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)
Risk: low. The command-text tests pin the stop ids and the 120-line budget.
- [ ] `autopilot.md`, net zero lines (`wc -l` is 120 or less before and after). In `:55-57`, the refresh bullet also says that a `commit-refresh` phase's printed `git add -- … && git commit` is run as printed. In `:90-94`, name `index-disagreement` beside `direction-unknown`, and say "no INDEX row here or in the main checkout". In `:73-80`, add "`fresh-uncommitted` is committed, never reviewed or closed over". Shorten neighbouring wording to keep the count.
- [ ] `done.md` check 4 (`:52`): "Any `stale`, `unknown` or `fresh-uncommitted` line refuses done". `fresh-uncommitted` goes back to `/crew:implement` step 6 to commit. Committing does not stale the receipt, because the bundle is the working state.
- [ ] `implement.md` step 6 (`:95-104`): re-run until it says `fresh`. `fresh-uncommitted` means commit the paths it lists.
- [ ] `plugin/crew/README.md`: the `crew_refresh_check.py` row (`:762`), the "Artifacts stay current" paragraph (`:764`: five values, the uncommitted rule, the manifest confirmation), the autopilot paragraphs (`:819` refresh, `:821` "Which ticket" with the main-checkout read, `:823` stops with `index-disagreement`), and `commit-refresh` wherever the phases are listed.
- [ ] `.crew/codemap/crew.md`: the autopilot section (`:464-492`) and the refresh-check section (`:607-640`), each DERIVED with fresh `path:line` anchors and a new `anchor:` at the implement commit.
- [ ] `docs/diagrams/process-crew-lifecycle.mmd`: the implement-step comment (`:53-54`) and the done check 4 comment (`:66`). Add `fresh-uncommitted` to the refresh loop node label, then re-render with `/crew:diagram refresh` (`render.sh`), and check that the SVG exists and is non-empty.
- [ ] `docs/guides/crew/src/troubleshooting.md` gets two entries in the guide's symptom -> check -> fix form: "autopilot stops with `cannot tell whether <id>'s direction is approved` in a worktree" and "refresh-check says `fresh-uncommitted`". Then rebuild with `python3 docs/guides/crew/src/build.py` and confirm that the HTML, DOCX and PDF changed, with nonzero sizes.
- [ ] `.crew/verify.json`: re-time the refresh-check rule (`:264-280`) and the autopilot rule (`:293-300`) with the Test command's wall time. Change `seconds` only if the measured figure rounds to a different number, and say what was measured in `why`.
- [ ] Run the Test command. It must be all green.

### Step 6: release bookkeeping and the gates
Files: CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md
Test: python3 scripts/check-marketplace.py && flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0063 python3 plugin/crew/tests/sabotage.py
Risk: low. The bump is the "Stop and ask" rule, and the checker enforces it.
- [ ] Bump crew to the next free patch version above origin/main's at commit time, in both `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Add a CHANGELOG entry naming T-0063's three changes. Update `plugin/PLUGINS.md`'s crew row only where it states the version.
- [ ] Run `python3 scripts/check-marketplace.py`. It must exit 0.
- [ ] Run `sabotage.py` under the lock. Every new mutation from steps 1 to 4 goes red on its named test, and no existing one turns green. Report the counts verbatim.
- [ ] Run the two verify rules' `run` commands from `.crew/verify.json` and `crew_refresh_check.py --root . --ticket T-0063` on the worktree. The last one must say `fresh` after the refresh commits, which is this ticket used on itself. State that `drift-detection.sh` was not run, and why.
