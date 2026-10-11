# Handoff (public copy)

Copied from the laptop's .work/HANDOFF.md, TRANSFER HANDOFF section only, and redacted for a public repo.
The sections it refers to below it, and its LOCAL ONLY part, stay on the laptop. See README.md.

## TRANSFER HANDOFF 2026-10-11 15:02 CDT

Written for a fresh session on a DIFFERENT computer that has only a clone of origin. Every sha below was read
from `git` or `gh` between 15:01 and 15:02 CDT on 2026-10-11; every time is from `date`. Where something was not
re-checked at that moment it says so. Nothing in this section is an approval of anything: the owner decisions are
listed with their exact width, and anything outside that width goes back to the owner.

The sections below this one ("RESUME CHECKPOINT ..." and the dated log lines) are the working record of the same
day. They are older, name agents and laptop paths, and are superseded by this section wherever they differ.

### 1. Main, and what merged today

- origin/main = `a656ef84f6dca94a4abc73934eab6e886bd54e0d`: "Merge pull request #605 from
  mbadali25/L-0790-hermetic-firewall-test", merged 14:58:57 CDT. A merge commit with parents `987ea4fb8` and
  `ee9b9c2c1`. ai-connect is 0.1.5 on main; crew is 1.2.30.
- Merged today: #582 (L-0710, merge commit `987ea4fb8`, crew 1.2.30) and #605 (L-0790, above).
- Main's push CI on `a656ef84f`, as of 15:01, not re-checked since: Runner auto-start, Instruction budgets and
  MCP servers succeeded; Marketplace and Shell suites in progress; the Pytest workflow queued. READ IT BEFORE
  RELYING ON MAIN BEING GREEN.
- Main's scheduled CI run of 2026-10-11 (run 38145816635, on `987ea4fb8`) was RED on two elapsed-time tests; the
  push run on the same sha was green. See L-0793 and owner decision 6. The next scheduled run is due 2026-10-12.
- #605 is MERGED, NOT VERIFIED BEYOND WHAT RAN. Not run for it: `scripts/_test/drift-detection.sh`; anything on
  Windows; the three crew-windows CI jobs (they did not start for that PR). Both of its security passes ran on
  the same model family as the author; the two Codex review rounds are its independent reads.

### 2. Open PRs (heads from `gh pr view` at 15:01 CDT)

Crew versions held by open PRs: #597 1.2.31, #604 1.2.31 (a clash: whichever merges second takes the next free
number), #584 1.2.32, #600 1.2.33. Re-check main's version right before every merge.

**#584, L-0709, branch `L-0709-hermetic`, head `344dd3a6e85a06d4dfc0eef7adafb02d808158aa`. NEXT IN THE ORDER.**
- What it is: every crew test runs under a home of its own.
- Phase: review accepted (round 6, owner-accepted); main merged in today as `344dd3a6e` (merges `a656ef84f`;
  hand-resolved only CHANGELOG.md and README.md; `check-marketplace.py` passes; crew stays 1.2.32). CI on the new
  head was still running at 15:01 (4 pass, 15 pending): NOT read as green.
- Proven, all on the PREVIOUS head `bdc7bc55a`, none re-measured on `344dd3a6e`: local `scripts/gate-runner.py`
  45 of 46 steps PASS; pytest-combined `20936 passed, 283 skipped`; the two
  `test_crew_context_wrappers.py::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false` cases
  (`[config0-False]`, `[None-False]`) PASSED by name, which is the pair that fails on main; sabotage step FAIL
  with 16 entries not RED (11 STILL GREEN, 5 RED BUT UNPROVEN), all 16 reproduced on main `987ea4fb8`.
- Not run on any head: a true `verify-gate.sh --all` (so /crew:done check 2 is NOT satisfied); verify.json
  rules[28] (the ai-connect suite); `drift-detection.sh`; the 17 platform-only sabotage entries; /crew:done.
- Next step: (1) confirm CI green on the head; (2) `npm --prefix mcp-servers ci`; (3) the rules[28] procedure in
  section 6; (4) a true `--all` gate in the form of section 6; (5) /crew:done, with done-waiver.md re-measured
  for the new head; (6) the package to the lead, and the lead's go before any merge.
- Waits on: nothing but that work. It is the PR that makes other gates able to pass, because it fixes the two
  tests that fail on main on a host with a crew config in the user's home.

**#604, L-0789, branch `L-0789-diagram-reanchor`, head `b129d3030c507851d2a81fb7d2b8d65f48d35257`.**
- What it is: re-anchors two diagrams (data-flow-crew-config and its ratchet part). Not sha-only: one box label
  and one comment were corrected and the embed in plugin/crew/README.md regenerated, so it carries a crew bump.
- Phase: implemented, NO review round spent. GitHub shows it CONFLICTING with main at 15:01 (bookkeeping files
  are the likely cause; not examined).
- Proven on `b129d3030`: CI 30 pass; a true `--all` gate ended rc=2 whose only test failure is the two on-main
  cases (`2 failed, 19683 passed, 283 skipped`); rules[29] 0 fail after `npm ci`; the wallclock half
  `74 passed, 6 skipped`.
- Not run: the review round; rules[28]; `drift-detection.sh`; /crew:done as a whole.
- Next step: after #584 is on main, merge main, run a gate that can pass, then its one Codex round WITHOUT
  `--allow-unverified`, /crew:done, merge on the lead's go. It will meet a CONTENT conflict with #603 on
  docs/diagrams/data-flow-crew-config-ratchet.mmd (see #603).

**#603, L-0772 fix-forward, branch `L-0772-fix`, head `6767f6365d9fd3dc14ce32bb6e47fb8f60e479ca`.**
- What it is: fixes to the env-dump guard after the review of the already-merged #599.
- Phase: rounds 1 and 2 spent (2 rejected), successor plan approved, round 3 unspent. The head holds the 4
  security BLOCK fixes plus 11 further fixes from the same security report. GitHub: MERGEABLE, BEHIND main.
- Proven on `6767f6365`: env-guard suites `1709 passed, 2 skipped`; hand sabotage 20 of 20 red with
  byte-identical restores; a true `--all` gate ended rc=2 with only rules[16]
  (`2 failed, 20419 passed, 285 skipped`, the two on-main cases) and rules[28] skipped; the wallclock half
  `74 passed, 6 skipped`; CI 29 pass and 1 fail, the fail being the Marketplace version-drift line, expected
  until the bump at landing. Windows, measured by another machine: five runs on this head with 6, 7, 8, 8 and 6
  failures, none outside the 8 known env-guard parity cases, which also fail on main's tip.
- Not run: review round 3; a security pass on this head; the gate-runner's full sabotage step (treated as needed
  before /crew:done); check 4; `check-marketplace.py` locally; rules[28].
- Next step: after #584 is on main, merge main, run a gate that can pass, round 3 WITHOUT `--allow-unverified`
  (bundle wording: "the 4 BLOCK fixes plus 11 further fixes from the same security report, one of which has its
  must-block case on Linux only [redacted: c], follow-up L-0788"), a fresh security pass, the
  full gate with the sabotage step, check 4 BY HAND from `5eb635f2d` (owner decision; the tool reads "unknown"
  for a fix-forward under an already-merged ticket id), the version bump. One further owner-granted round exists
  only if round 3 leaves something that needs it.
- Conflict to expect: #603 and #604 both change data-flow-crew-config-ratchet.mmd. Whichever merges second
  re-takes the notes from the merged code, regenerates docs/diagrams/README.md, index.html and the plugin README
  embed, and re-anchors in-PR. It does not pick a side.

**#600, L-0777, branch `L-0777-kimi-agents`, head `46d015a35d7898d684dd16974ffad3895248e7a4`.**
- What it is: crew's explorer, researcher and security roles can dispatch to Kimi.
- Phase: round 4 (owner-granted final) accepted with 0 BLOCK / 4 FIX, follow-up L-0787. Main (`987ea4fb8`) was
  merged in today as `b1cb69ec3` with hand resolutions only in bookkeeping files, and the ticket's own diagram
  re-anchored as `46d015a35`; crew 1.2.33. It does NOT yet contain `a656ef84f`.
- Proven: CI on `46d015a35` 30 pass (one check failed on the first attempt and passed on re-run: see L-0793,
  recorded as ONE UNEXPLAINED occurrence, not cleared). On the previous head `ee19528bf`: gate-runner 43 PASS,
  pytest-combined failing only the two on-main cases (`2 failed, 20953 passed`), sabotage with 12 STILL GREEN
  and 5 RED BUT UNPROVEN, all 17 reproduced on main `987ea4fb8`; mcp-servers 69 tests, 0 fail.
- UPDATE 15:04 CDT: the local gate-runner run on `46d015a35` ENDED and was read by its lane: overall FAIL, 44
  PASS, 2 FAIL, 0 SKIP. pytest-combined `2 failed, 20992 passed, 283 skipped` (the two on-main cases); wallclock
  step `74 passed, 6 skipped`; mcp-servers PASS; sabotage FAIL with a non-red set IDENTICAL to the `ee19528bf`
  run (12 STILL GREEN, 5 RED BUT UNPROVEN, 17 platform-only), 2985 RED. The run overlapped two load windows on
  that machine (14:13:47 to 14:22:55 and 14:36:15 to 14:47:10 CDT); no verdict differed, so nothing needed a
  re-run. No process of that gate is running and the tree is clean (checked 15:04).
- GitHub shows #600 CONFLICTING with main at 15:04, so `46d015a35` is no longer the final head. A trial merge
  conflicts in CHANGELOG.md and README.md only.
- Not run: a true `verify-gate.sh --all` on any head and its separate wallclock run; rules[28]; /crew:done on
  this head or later (check 2 has no record); anything on a head that includes main `a656ef84f`.
- Next step: merge main again (bookkeeping only; stop on any code hunk), re-check the next free crew version,
  re-anchor the ticket's own diagram only if a cited file moved, push and get CI green on the new head; then
  gate-runner, `npm --prefix mcp-servers ci`, a true `--all` gate, the wallclock half, rules[28] by section 6,
  /crew:done, the package to the lead.
- Note: plugin/crew/hooks/scripts/crew_state.py is at 3399 of a 3400-line cap on this head. The next line added
  to that file needs a code change, not a bookkeeping merge.

**#597, L-0768, branch `L-0768-tree-policy`, head `3a11fb98dcc8ee6e413def106a7ed520b4956170`.**
- What it is: promote-gate reads deploy policy from the sha being deployed.
- Phase: reviewed; held. GitHub shows it CONFLICTING with main at 15:01 (not examined).
- Proven on `3a11fb98d`: CI 30 pass; a true `--all` gate ended rc=2 with only rules[16]
  (`2 failed, 19705 passed, 283 skipped`, the two on-main cases) and rules[28] skipped. On Windows, measured by
  another machine in Git Bash: a serial repeat `79 passed, 6 skipped`, no failures.
- Measured about the promote-gate deadline: #597 adds a net 3 git starts and 0 interpreter starts to every
  matched deploy that passes the tree checks. On one machine at load average 10 to 14 the added cost was below
  run-to-run noise (gate about 0.35s sh, about 1.6s ps1, on main and on the PR head), with 13.6s or more of the
  16s gate deadline left. That does not settle the loaded case.
- Not run: the idle and loaded timing cells (OWED before it lands; method in section 6); rules[28]; the wallclock
  half; /crew:done.
- Next step: the timing cells; then merge main, re-take the crew version, the gate, /crew:done, the package to
  the lead. If the added cost is a meaningful share of the remaining margin under load, #597 stops and goes to
  the lead.

**#598, L-0770, branch `L-0770-pinned-merged-main`, head `e14c8263dd3903f8f98edcdec876d64744a640d8`.**
- A harness PR, not worked today. CI 30 pass. L-0710 (merged as #582) has a recorded review round that waits on
  it. Queued after the PRs above. Its state beyond the head and CI was not re-checked today.

### 3. The agreed order

1. #584: merge main (done at `344dd3a6e`), rules[28] as root with a venv under the owner's conditions, a true
   `verify-gate.sh --all`, /crew:done, the merge go from the lead.
2. #604 and #603: merge main, then their review rounds behind a gate that can pass.
3. #600: as its own conditions clear.
4. #597: after the loaded timing cells.
5. Then #598 (with L-0710's recorded round), L-0747, L-0765.
Every merge verdict goes to the lead first. Nothing merges on a lane's own verdict.

### 4. Owner decisions of 2026-10-11 (Matthew, each given through a direct question; recorded as relayed)

1. L-0790 is fixed on main first (done: #605).
2. /crew:done check 4, diagram waiver, exactly this wide: waived for a diagram that was already stale on main
   before the PR and that the PR did not create, follow-up L-0791. Applies to #600, #584, #597, #603. Not
   covered: a diagram the PR wrote or redrew; a diagram the PR's own change makes materially wrong in a way
   L-0791 does not list; code maps and the graph (L-0764 covers those); a line that reads "unknown"; any other
   check. Lead ruling inside it: if the diagram's fix has landed on main and the PR has merged main, the PR
   re-anchors that diagram itself after checking its own diff changes nothing it draws.
3. #603: fix all 4 security BLOCKs; round 3 next; one further round only if needed; check 4 measured by hand
   from `5eb635f2d`.
4. An owner decision on this morning's incident is recorded locally [redacted: a]. Do not re-raise.
5. #605: one review round was allowed to start with `--allow-unverified`. Used. NO other PR uses the flag.
6. #605 round 2 (0 BLOCK / 2 FIX) accepted as edge-case-only, follow-up L-0792; then MERGE AS REVIEWED, with
   the security pass's FIX and 2 NITs in L-0792, check 4 under L-0764, and check 2 as his exception on the
   evidence set. For #605 ONLY. Other PRs get check 2 by tool, or go back to him.
7. The five RED BUT UNPROVEN sabotage entries: accepted on #600 and #584 as pre-existing on main, added to
   L-0766, repaired or retired later in a harness-only PR.
8. rules[28] after #605 is on main: may be run as root from a venv, under the conditions in section 6.
9. #603 may merge with the 8 Windows parity failures recorded as pre-existing on main. This removes the Windows
   hold only; every other condition on #603 stands.
10. Freeze triage: the six Windows tickets (W-0130 to W-0135) may be worked as bug fixes under the feature
    freeze. Nothing starts until slots are free and the lead says go; W-0132 and W-0131 first. W-0134 needs his
    direction first; W-0135 needs a reproduction first.
11. Freeze count: main's red scheduled run of 2026-10-11 does NOT reset the 7 green days; its two tests are
    ticketed as L-0793.
12. The installed crew plugin on the old machine is updated only after #605 and #584 are on main, by the lead
    with him. No lane runs a plugin update.
Earlier standing rules still in force: review round cap of 3 per ticket (the ledger's budget is 2; a third round
needs an approved successor plan); the standing post-accept staleness waiver (only merges, bumps and refreshes
after the accept, and the PR's own diff inside Touch); L-0764 for stale code maps and graph; no `--admin` merge;
crew PRs land as merge commits.

### 5. Lead rulings of the day that a new session must keep

- A waiver applies only on an exact match with its precedent or its written text. Otherwise stop before merging.
- L-0766's list is closed (12 STILL GREEN entries, later 5 added by owner decision 7). Quote it when relying on it.
- The staleness-waiver record is MEASURED: each non-merge post-accept commit by `git diff --name-only <sha>^
  <sha>`; each merge's hand-resolved paths by remerge-diff; the PR's own code and test delta unchanged since the
  accept by blob identity or `git patch-id --stable`; every sha listed. Never "no code in the range": a merge
  brings main's changes in.
- A deferred, skipped or not-run step is recorded as not run, never as PASS. A command that exits 137 around a
  session restart did not run.
- No SKIP is waived: `npm ci` so the mcp-servers rule runs.
- A CI failure on the final head stops the PR whatever a local gate says. A failure that passes on re-run is
  recorded as one unexplained occurrence with its saved log, not as cleared.
- #597 does not land with an unexplained intermittent promote-gate failure unless the cause is shown to be
  outside its diff (shown for the one occurrence seen; the timing cells are still owed).
- One fix in #603 stays although its must-block test runs on Linux only [redacted: c] (L-0788 carries the gap).
- Kanban cards: keep them current by Edit. The vault plugin's contract report on a card's existing frontmatter
  is not a refusal. Correct an `updated:` date an edit makes stale; change nothing else in a card's frontmatter.

### 6. How gates and risky steps must be run

- The gate that feeds /crew:done check 2 is `verify-gate.sh --all`, not `scripts/gate-runner.py`. Check 2 reads
  the verify-gate record and marker (plugin/crew/commands/done.md, "Check 2"); gate-runner's status file is not
  consulted. Gate-runner is still the only thing that runs the sabotage suite.
- Invocation that worked: from the worktree root, with `TMPDIR` unset, `CLAUDE_PROJECT_DIR` set to the worktree,
  stdin from /dev/null, `--all` as the literal first argument:
  `env -u TMPDIR CLAUDE_PROJECT_DIR=<worktree> bash plugin/crew/hooks/scripts/verify-gate.sh --all </dev/null`
  (through the machine's heavy-run wrapper where one exists; one heavy run per slot, check free memory first).
- Run `npm --prefix mcp-servers ci` first, or rules[29] skips: a fresh worktree has no node_modules.
- rules[16] is `pytest ... -m "not wallclock" || exit 1; exec pytest ... -m wallclock`. When the first half
  fails, the wallclock half never runs: run `python3 -m pytest plugin/crew/tests/ -q -m wallclock` separately.
- The stale `chronic` trap: a Stop-budget run of the gate writes a `chronic` record entry for rules[16]; a later
  `--all` run in which that rule FAILS does not replace the entry, so the summary prints "permanently over
  budget ... deferred to CI" for a rule that actually ran. Check the log for the rule's own timing line before
  believing it.
- On a host whose user home has a crew config with a `memory` block, the two `inject_is_false` cases fail on
  main, so no `--all` gate can record a pass there until #584 is on main.
- rules[28] (the ai-connect suite) as root, under owner decision 8: only on a tree that contains main
  `a656ef84f` or later; build a venv OUTSIDE the worktrees from plugin/ai-connect/requirements.txt and
  requirements-dev.txt; install nothing into the system python. The FIRST root run is the rule's exact
  verify.json command ALONE, not inside the gate, on ONE PR only, with the host firewall's stored rule files
  saved before and diffed after, and the system journal checked for privilege-escalation or firewall lines. If
  anything touched the firewall: STOP EVERYTHING, do not revert, tell the lead. Report that result before the
  full gate. Reason for the separate step: a change is then attributable to that one command.
- #597's timing cells: one representative case, main against the PR head, sh and ps1, at least 10 samples per
  cell, idle and under load (one busy-loop process per CPU under a 120-second timeout), load average stated per
  cell, and a check afterwards that none is left running. Never while a gate, sabotage or review run is active.
- Review: cross-family. Author family passed with `--authors`. Codex first, Kimi if Codex is at its limit, and
  say which ran. `--allow-unverified` is not available to any open PR.
- Records (handoff, tickets, INDEX, cards) are written with the Read, Edit and Write tools, never through a
  shell heredoc or a generated script.
- A guard or hook refusal is reported before any other route is tried, even when it looks like a false positive.
- Probes of guards: cases from a file, no test string reaching a real shell, a scrubbed environment.

### 7. Follow-up tickets and the later-ticket list

Filed (in .work/tickets/, all status `direction` unless said):
- L-0766: repair or retire sabotage entries that do not prove their mutation on main: the original 12 STILL
  GREEN plus, since today, 5 RED BUT UNPROVEN (two never test their mutation: a dangling test id; a mutation
  that is a syntax error; three are proven on Linux only). Harness work, lands alone.
- L-0787: the 4 FIX lines of #600's round 4.
- L-0788: env-guard items #603 does not fix, including one Linux-only must-block case [redacted: c].
- L-0791: redraw the stale config and brief diagrams (nine with measured defects, eleven more by name, one of
  which fails the readability check on main). It carries an OPEN QUESTION, not yet put to the owner: check 4
  compares each diagram's anchor with the PR's working tree, so a re-anchor on main cannot clear it for a PR
  that edits a cited file; L-0791 alone does not end the waiver.
- L-0792: ai-connect test follow-ups: three hermeticity gaps, the 2 FIX lines of #605's round 2, and the
  security pass's FIX (a changelog instruction that shows nothing in the state the incident happened in) and 2
  NITs.
- L-0793: two timing-fragile tests (a 6.0s heartbeat bound measured at 6.70s; a promote-gate case whose 16s
  deadline was spent), with cross-references to a promote-gate parity disagreement seen once in CI and to the
  Windows deadline observations. First step: the parity assert prints the gate's stderr.
- W-0130 to W-0135: filed on the Windows machine, not in this repo's INDEX. W-0130 a session-start hook that
  rewrites config; W-0131: the hook's python resolver can exhaust its time budget on Windows, so an armed guard refuses; detail in the ticket; W-0132: cloud guard has a must-block miss and over-blocks some prose; detail in the ticket; W-0133 agents
  that declare only the Bash tool; W-0134 the gate's choice of shell on Windows; W-0135 nested sub-agents not
  seeing a project agent type (not reproduced).
Not filed yet (ticket later):
- `crew_ticket.py mint` produced a T- id on a Linux box.
- The stale `chronic` gate record (section 6).
- The promote-gate false positives [redacted: d] reported from another repo against crew 1.2.5; unknown
  on main.
- Crew's Kanban card format does not meet the vault plugin's note contract.
- A question for whichever ticket next touches crew's hook launchers: does any launcher treat a clean exit with
  no verdict as allow? Not checked.
- Hosted Windows CI passes the env-guard parity cases that fail on a real Windows machine; cause not
  established. CI does not cover that class.

### 8. Waiting on the owner

- The installed crew plugin update on the old machine (after #584 is on main).
- W-0134's direction (which shell the gate should use on Windows).
- Carried from earlier: the L-0713 interactive /crew:init walkthrough; triage of L-0779, L-0782, L-0769, L-0763,
  L-0764, L-0766, L-0767, L-0785, L-0786; the scope of a runner start token on the runner-infrastructure repo.
- Not yet asked: L-0791's open question (section 7).

### 9. What does NOT travel with a clone of origin

`.work/` is git-ignored, and so is `.git/crew/`. A clone has NONE of: this file, .work/INDEX.md, the ticket
folders (specs, plans, done-waiver.md, evidence), the review ledgers and receipts, the Kanban board. A separate
copy onto a branch is being made for the handoff, INDEX and the active ticket folders. WITHOUT THE REVIEW
LEDGERS (`.git/crew/review/<ticket>.json` in the main checkout), another machine sees no review receipt for any
ticket: /crew:done check 1 will refuse on every PR until the ledgers are copied over or the reviews are recorded
again. Decide that before resuming #584.
