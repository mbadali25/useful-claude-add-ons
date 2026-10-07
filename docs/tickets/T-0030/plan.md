# T-0030 plan (successor 2026-09-29: merge main, fix review round 6)            spec: .work/tickets/T-0030/spec.md

This is the narrow successor plan the owner ordered on 2026-09-29 ("Reject + narrow successor (Recommended)", READY BACKLOG RUN). Review round 6 (Codex, FINDINGS: 0 BLOCK, 6 FIX, 2 NIT, head `b20cf9ee`, base `3c1f94a9`, bundle `0c7ca3a7cc27`) was the last round of the budget, and the owner's rejection of it is in the ledger (`review_ledger.py --reject`, 2026-09-29T10:04:58+00:00). The plan it follows is kept unchanged as `.work/tickets/T-0030/plan-2026-09-27-r6.md` (sha256 `b08dd115ea3c3fe8ec0bf9870e2ffdece29572a86a53cf240a0ff54baaf9e0d4`). Its Steps 1-8 are built and on `T-0030-coord` at `b20cf9ee`. Its Step 9 was approved but never built, and this plan replaces it. This plan adds nothing to the ticket's scope. It does four things: merge origin/main, fix the six FIX lines of round 6, re-bump crew, and refresh. The two NITs are not in this plan. They go to a follow-up ticket filed after merge, with their lines copied verbatim.

Source of the findings: `/repos/personal/uca-t0030/.work/review/T-0030-coord--dtqJtS/out.txt`. It has 37 READ lines for 37 of 37 parts, then 6 FIX and 2 NIT. Each step below quotes the location of its FIX line. The line numbers are as of `b20cf9ee`. `crew_coord.py` and `test_crew_coord.py` are not on origin/main, so the merge in Step 1 does not move them.

Worktree `/repos/personal/uca-t0030`, branch `T-0030-coord`. Do these before Step 1:
- Copy `/repos/personal/useful-claude-add-ons/.work/tickets/T-0030/{spec.md,plan.md,plan-2026-09-27-r6.md}` into `/repos/personal/uca-t0030/.work/tickets/T-0030/`, then `cmp` each copy.
- If `.crew/config.json` is missing, or its `scope.allowCliApproval` is not true, copy `/repos/personal/useful-claude-add-ons/.crew/config.json` there. The file is untracked and is never committed.

Rules for every step:
- Crew scripts come from the worktree's own `plugin/crew/hooks/scripts`, which after Step 1 means origin/main's plus this branch's.
- Every pytest, sabotage, gate and graphify run goes through `TMPDIR=/root/crew-tmp/t-0030 /root/crew-tmp/heavy-run <command>`, one at a time, with `free -g` checked first. An exit 137 there is the 6G cap. Quote it verbatim and never raise the cap.
- Tests come first in every fix step. Each new test runs and fails on the unchanged code, and its red output is kept for the PR body.
- Commit after each step with no Co-Authored-By trailer. No force-push, rebase or squash.

### Step 1: merge origin/main (a merge commit, mechanical conflicts only)
Files: CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/BUDGETS.md, .crew/verify.json, plugin/crew/tests/sabotage.py
Test: `git merge-tree --write-tree --name-only origin/main HEAD` before merging (the list below), then after the merge `TMPDIR=/root/crew-tmp/t-0030 /root/crew-tmp/heavy-run python3 -m pytest plugin/crew/tests/test_crew_coord.py -q -p no:cacheprovider` passes as it did on `b20cf9ee`, and `python3 scripts/check-marketplace.py` passes except for the version, which Step 8 sets
Risk: med. The branch is 449 commits behind origin/main (`2693d0fa`, crew 1.0.59, merge-base `3c1f94a9`). A conflict resolved by hand is unreviewed code. So every resolution must be a union of both sides or a regeneration, and anything behavioural is a STOP.
- [ ] `git fetch origin`, then `git merge --no-ff origin/main`. Never rebase. Measured 2026-09-29 against `2693d0fa`, `git merge-tree` reports 19 conflicted files:
  - version fields: `.claude-plugin/marketplace.json`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md`. Take origin/main's side. Step 8 re-bumps.
  - claim number: `plugin/crew/BUDGETS.md`. Take either side, then re-measure with `git ls-files 'plugin/crew/*.md' | xargs wc -l` and write that total. This is the BUDGETS.md standing rule (owner 2026-09-28).
  - `.crew/verify.json`: keep both sides' entries. That is origin/main's resume, autopilot, tracker, route and approval-hook entries plus this branch's `crew_coord.py` entry. The file must still parse (`python3 -c "import json;json.load(open('.crew/verify.json'))"`).
  - `plugin/crew/tests/sabotage.py` at the `MUTATIONS +=` line: keep origin/main's comment and tuple, then append `+ COORD_MUTATIONS`. The comment names `T-0030 coord` beside `T-0075 config menu`. The `from sabotage_coord import COORD_MUTATIONS` import merges cleanly. The module must stay within `.pylintrc`'s `max-module-lines=3400` (origin/main is at 3384).
  - refresh artifacts (`.claude/rules/*.md` x5, `.crew/codemap/*.md` x6, `graphify-out/GRAPH_REPORT.md`, `graphify-out/graph.json`): take origin/main's side in the merge. Step 9 regenerates them. This is the refresh-artifact standing rule (owner 2026-09-28), and it needs no Touch amendment.
- [ ] `CHANGELOG.md` and `plugin/crew/README.md` merge without conflict. Read the merged `CHANGELOG.md` top and confirm that T-0030's entry and every origin/main entry are both present.
- [ ] If the merge reports a conflict outside this list, or any hunk where one side's behaviour has to be chosen over the other's, STOP needs-owner and quote the hunk. Do not guess.
- [ ] Commit the merge: `Merge origin/main (2693d0fa or newer) into T-0030-coord: mechanical conflicts only`. The message lists each file and how it was resolved.

### Step 2: a `file://` origin is the local path it names (FIX crew_coord.py:889)
Files: plugin/crew/hooks/scripts/crew_coord.py, plugin/crew/tests/test_crew_coord.py
Test: `TMPDIR=/root/crew-tmp/t-0030 /root/crew-tmp/heavy-run python3 -m pytest plugin/crew/tests/test_crew_coord.py -q -p no:cacheprovider`. Each new test is watched red first.
Risk: high. Two keys for one repository means two holders for one ticket.
- [ ] Must-block test:
  - In `tmp_path`, `alias` is a symlink to `real`.
  - Clone a has origin `file://<tmp>/alias/coord.git`, and clone b has origin `<tmp>/real/coord.git`.
  - The second claim of T-1 is refused with the first holder named, and the channel holds one claims file.
- [ ] Must-allow test: two different bare remotes, one given as `file://` and one as a plain path, still give two keys, and both claims succeed.
- [ ] Fix `_resolved` (`:883`) and `_local_path` (`:763`) so that a `file://` origin is treated as the local path it names, never as an opaque URL:
  - percent-decode the path;
  - accept an empty or `localhost` authority only; any other host is could-not-tell (`UnknownKey`);
  - resolve the path with `os.path.realpath`, exactly as a plain local path is resolved.

  After the fix, `file:///var/run/x.git` and `/run/x.git` give one key when `/var/run` is a symlink to `/run`.

### Step 3: Azure DevOps markers are compared after percent-decoding (FIX crew_coord.py:816)
Files: plugin/crew/hooks/scripts/crew_coord.py, plugin/crew/tests/test_crew_coord.py
Test: as Step 2
Risk: high. An encoded `DefaultCollection` or `_git` gives a second key for the same repository.
- [ ] Must-block test. Each of these pairs gives one key, and the second holder's claim of T-1 is refused:
  - `https://org.visualstudio.com/DefaultCollection/_git/Repo` and `https://org.visualstudio.com/%44efaultCollection/_git/Repo`;
  - `.../_git/Repo` and `.../%5Fgit/Repo`.
- [ ] Must-allow test: a project named `My%20Project` still decodes to `my project` inside the key, and the old plan's Step 8 Azure form table stays green.
- [ ] Fix `_azure_parts` (`:801`): the structural markers `_git`, `v3` and `DefaultCollection` are compared only after each segment is percent-decoded with `_azure_part` (`:737`), never before. A segment that does not decode is could-not-tell.

### Step 4: local-origin keys keep case and `.git` (FIX crew_coord.py:862)
Files: plugin/crew/hooks/scripts/crew_coord.py, plugin/crew/tests/test_crew_coord.py, plugin/crew/README.md
Test: as Step 2
Risk: high. One key for two repositories refuses an unrelated session's claim.

This step follows the spec's Unknowns entry "Owner decision - local-origin key: case and .git" and takes its written recommendation. That is the standing rule for open questions (owner 2026-09-28).
- [ ] Must-block tests. In each pair, the second repository's claim of T-1 succeeds:
  - `/srv/git/Repo.git` and `/srv/git/repo.git` (two directories on a case-sensitive filesystem) give two keys;
  - `/srv/git/repo` and `/srv/git/repo.git` (both existing) give two keys.
- [ ] Must-allow tests:
  - One bare remote reached through two spellings of the same directory (a symlink, a trailing `/`, a `..` segment) gives one key.
  - Network-host keys are unchanged: the old plan's Step 8 host tables stay green, and `.git` is still stripped there.
- [ ] Fix: a local key no longer lowercases the path and no longer strips `.git`. It keys the directory git itself opens for that path, with the on-disk case preserved.
  - Re-read git's own suffix order for a path that does not exist as given from git's source (`enter_repo`, found by grep) at implementation. Record the git version and file you read in the commit message. Until then the order is not verified, as the spec says.
- [ ] Update the README's key paragraph (`plugin/crew/README.md:1619-1623`) to state the local rule.

### Step 5: a network URL with no host is could-not-tell (FIX crew_coord.py:783)
Files: plugin/crew/hooks/scripts/crew_coord.py, plugin/crew/tests/test_crew_coord.py, plugin/crew/README.md
Test: as Step 2
Risk: high. A guessed `file_` key for a malformed URL reaches the claim path.
- [ ] Must-block test: `https:///owner/repo`, `ssh:///owner/repo`, `https://user@/owner/repo` and `https://:443/owner/repo` each refuse the claim with the URL's shape named, and no claims file is written.
- [ ] Must-allow test: `https://github.com/owner/repo` and `file:///srv/git/repo.git` still give their keys.
- [ ] Fix `_split_url` (`:772`): a URL whose scheme is not `file` and whose host is empty once userinfo and port are dropped is could-not-tell (`UnknownKey`). It never becomes a `file_` local key.
- [ ] Add this case to the README's list of origins that read `unknown`.

### Step 6: a failed push-config probe is unknown, never absent (FIX crew_coord.py:683)
Files: plugin/crew/hooks/scripts/crew_coord.py, plugin/crew/tests/test_crew_coord.py
Test: as Step 2
Risk: high. A push that silently drops a configured push URL writes the claim somewhere nobody reads.
- [ ] Must-block test:
  - Stub `run_git` so that `config --get-all remote.origin.pushurl` exits 128, `get-url --push` prints `/intended.git`, and `remote.origin.url` is `/read-only.git`.
  - The claim exits `EXIT_UNKNOWN`, and no `git push` is called.
- [ ] Must-allow test: with every optional key absent (exit 1 for proxy, receivepack, vcs and pushurl), the claim still pushes to the url, as today.
- [ ] Fix `push_env`: it reads each `_PUSH_REMOTE_KEYS` probe's exit status.
  - 0 means the probe returned values.
  - 1 means the key is absent.
  - Anything else, or git failing to start, returns None. `write` then reports `unknown`, and nothing is pushed.

### Step 7: the fake ssh never execs a `#!` script directly (FIX test_crew_coord.py:505)
Files: plugin/crew/tests/test_crew_coord.py
Test: as Step 2
Risk: low. The change is test-only, but the Windows default suite cannot pass until it lands.
- [ ] Must-block test: a new test scans the module's fixtures and fails when any file handed to the fake ssh as a program starts with `#!`. It is red on `b20cf9ee`, which writes `#!/bin/sh`.
- [ ] Rewrite the receivepack wrapper as a Python script:
  - `FAKE_SSH` runs a program whose name ends in `.py` through `sys.executable`;
  - the wrapper touches the marker and runs `git receive-pack` on its path argument.
- [ ] Must-allow: `test_push_carries_the_remotes_receivepack_but_never_mirror` passes on Linux. The Windows run belongs to win-repo-2, and the report says it was not run here.

### Step 8: sabotage for every new branch, docs, and the version one past origin/main
Files: plugin/crew/tests/sabotage_coord.py, plugin/crew/tests/sabotage.py, plugin/crew/README.md, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/BUDGETS.md
Test: `TMPDIR=/root/crew-tmp/t-0030 /root/crew-tmp/heavy-run python3 plugin/crew/tests/sabotage.py` (the non-RED set equals origin/main's, and every coord mutation is RED); `python3 scripts/check-marketplace.py`; then the full crew suite serially through heavy-run
Risk: med. A version at or below origin/main's leaves every installed copy stale, and a sabotage that does not go red means a test that does not guard its branch.
- [ ] Add six mutations to `COORD_MUTATIONS`, each named against the test it must turn red:
  - `_resolved` returns a `file://` URL untouched;
  - Azure markers are compared before decoding;
  - local keys are lowercased again;
  - an empty network host is read as local;
  - a push-config probe exit of 128 is read as absent;
  - `FAKE_SSH` execs the program directly.
- [ ] Re-read `origin/main`'s crew version (`git fetch origin; git show origin/main:plugin/crew/.claude-plugin/plugin.json`). Set crew to one patch above it in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`. At `2693d0fa` that is 1.0.60, but T-0087 may take 1.0.60 first, so re-check.
- [ ] Update T-0030's CHANGELOG entry: the new version, the six fixes, and the case count copied from the real run.
- [ ] Re-measure BUDGETS.md's line claim.
- [ ] Docs. A plugin/crew change updates every document that describes it. The documents that describe the key rule are `plugin/crew/README.md` (Steps 4-5) and T-0030's CHANGELOG entry. `docs/guides/crew/src/*.md`, `plugin/crew/CONFIG.md` and `docs/diagrams/` do not describe `crew_coord.py` (grep `crew_coord|crew-coord` at `b20cf9ee` finds only README, CHANGELOG, codemap and graph). So the PR body says `Docs: guides/CONFIG/diagrams none - they do not describe crew_coord's key rule`.

### Step 9: refresh, gate evidence, ready for review round 7
Files: plugin/crew/README.md, CHANGELOG.md
Test: `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0030` (the check `/crew:done` runs) reads `fresh`; `python3 scripts/check-marketplace.py`; `python3 /root/crew-tmp/ruff-no-new.py /repos/personal/uca-t0030` (exit 1 is recorded for fix at land, exit 2 stops); `python3 -m pylint $(git ls-files "*.py")` passes as in CI
Risk: med. A refresh built by the wrong command leaves the two graph files describing different builds (CLAUDE.md "Memory").
- [ ] Re-anchor `.crew/codemap/**`, regenerate `.claude/rules/**`, and rebuild `graphify-out/**` with `graphify update .` (never `--no-viz --code-only`). Run the rebuild through heavy-run, once the background hook log `~/.cache/graphify-rebuild.log` has stopped growing. Read the node and link counts from both files before committing. This is the refresh-artifact standing rule, and the PR body says so.
- [ ] Before round 7, measure and state the bundle's part count. origin/main now carries T-0092 (crew 1.0.54), whose `review_patch.py` leaves `graphify-out/` out of every bundle. So round 6's size NIT is addressed by the merge rather than by a fix here, and the count is what confirms it.
- [ ] Commit `crew <version>: fix T-0030 review round 6 (0 BLOCK, 6 FIX; NITs to follow-up)`. The commit carries the measured `test_crew_coord.py` pass count and time, the sabotage RED list for every coord mutation, and the bare-remote reproduction of each fix, all copied from the real run.
- [ ] Review round 7 runs under the successor budget that this plan's approval opens. The reviewer is Claude, same-family, because Codex is out of credits until 2026-10-03. A `claude -p` reviewer is started with `--settings '{"disableAllHooks": true}'`. Its output is copied byte-for-byte.
