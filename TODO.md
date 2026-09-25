# TODO

Findings queued for a later PR. Each carries the `path:line` it came from so it
can be re-verified rather than re-discovered — and so an item that turns out to
be wrong can be closed on evidence.

- `plugin/crew/tests/test_auto_cycle.py` (24 failures, measured both
  before and after crew-1.0-win-ps1-ac's fix, identical set both times):
  bash/tmux/symlink-flavour tests fail on this Windows dev host for
  environment reasons unrelated to that ticket -- no tmux on PATH, no
  window belongs to a non-interactive runner's ancestor chain, and
  `test_write_clear_resume_carries_the_next_action_end_to_end[*-sh]`'s
  `tmux pane %7 could not be confirmed` reads as a real host gap, not a
  script defect. Not fixed here: it is not in the one file
  crew-1.0-win-ps1-ac owns (`auto-clear.ps1` + its tests), and the
  before/after comparison is exactly what shows it predates that change.
- **Root cause, refining the entry above**: `plugin/crew/hooks/scripts/crew_autocycle.py:360-365`
  (`_ppid`, `subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], ...)`) always fails on this
  Windows dev host — its `/usr/bin/ps` is cygwin `ps` 3.6.10, whose own `--help` lists only
  `[-aefls] [-u UID] [-p PID]`, no `-o` at all (`ps: unknown option -- o`). `_ppid` swallows that
  as `int(out.strip() or 0)` → `0`, so `ancestors()` (`:368-374`) always returns just `[self]` for
  every caller, regardless of what invoked it. That is why the tmux-method ownership check
  (`:502`, `pane_pid not in ancestors()`) always refuses here, and hence part of the 24-failure
  set above — measured directly (`ca.ancestors()` from a plain `py -c` returns `[<own pid>]`,
  nothing else). Not fixed here: `crew_autocycle.py` is under `plugin/crew/hooks/scripts/`, out of
  scope for a test-harness ticket (lane C2), and likely belongs with whichever ticket owns the
  bash/tmux flavour of this suite.
- `plugin/crew/tests/test_auto_cycle.py`'s `test_the_detached_sender_does_not_outlive_
  kill_process_group` (added by lane C2) proves the real detached sender is reaped on Windows via
  a Job Object, `skipif`'d to Windows only. **Not closed on POSIX**: `auto-clear.sh:225-229`
  launches the sender with `setsid bash "$send_script" ... & disown`, which moves it into a NEW
  process group — `kill_process_group`'s POSIX branch signals `os.killpg(proc.pgid)` on the
  LEADER's own recorded pgid, which `setsid` has already left by the time the sender runs, so the
  signal cannot reach it there the way the Windows Job Object does (job membership and POSIX
  sessions are unrelated concepts; a session escape does not exempt a process from a Windows job).
  Closing this on Linux CI (`.github/workflows/pytest-crew.yml`'s `crew-shell-matrix` /
  `ubuntu-latest`) needs a different mechanism — reading the sender's own pid and reaping it
  directly, or bounding `delaySeconds` in the test — and is out of scope for this Windows-lane
  ticket.
- `test_verify_gate_stop_gate_record.py::test_34d_a_second_mktemp_failure_refuses_rather_than_wedges`
  failed twice in a row on this shared, concurrently-loaded machine (returncode assertion the first
  time, `elapsed < 10` at `10.3s` the second, immediately re-run alone) — consistent with the
  10s bound being genuinely tight under load rather than a regression from lane C2's diff (which
  never touches this rule's code path). Not investigated further: outside lane C2's two items, and
  a borderline timing assertion under concurrent load is exactly the shape CLAUDE.md's own
  "Run the states; do not reason about them" lesson warns against over-diagnosing from one host.
- `plugin/crew/tests/sabotage_autocycle.py` has no per-mutation CLI filter
  (`argparse` only exposes `--scratch`), so a newly registered mutation
  can only be proven through the full run (slow, and the bash-flavour
  mutations hit the same tmux/symlink gap above on this host) or through
  a manual sabotage/revert cycle done by hand, as crew-1.0-win-ps1-ac's
  `Get-CrewChildTabRecheck skips the post-delay tab check again` entry
  was. Not fixed here: adding a filter is a change to the harness itself,
  not to `auto-clear.ps1`.

- `scripts/_test/web-testing.sh:97` lifts `load_mcp_servers` out of
  `scripts/install-prerequisites.sh` without its `claude_available` dependency
  (defined at `scripts/install-prerequisites.sh:508`, outside the lifted awk
  range), so every run prints `claude_available: command not found` to stderr.
  Harmless today - the resulting nonzero status makes `load_mcp_servers`
  return early exactly like a real "claude not on PATH" case would, so no
  assertion is affected - but it is noise a future reader could mistake for a
  real failure. Not fixed here: out of the paths this ticket (crew 1.0 web
  testing lane B) was scoped to.

Opened 2026-09-05 from the codemap pass (`.crew/codemap/`). Every citation here
was checked against source when it was written; anchor `fe538879`.

## Blast radius — act on these first

### 1. `gizmoduck` opened real SDP tickets with no per-item gate — CLOSED 2026-09-05

**Fixed in gizmoduck 0.3.0.** `cmd_tickets`
(`plugin/gizmoduck/scripts/gizmoduck.py:289`) now takes a `create` argument,
wired to a `--create` flag on the CLI. Without it the function never builds the
`description` field, so a plain `tickets` run returns `"mode": "preview"` with
subjects, severities and target counts and **no ticket body**. That is the part
that matters: the flag withholds the payload rather than labelling it. An
earlier draft of this fix emitted the full records under an `authorized: false`
banner, which is a gate in name and a create-ready payload in fact — this repo's
signature defect, and it was caught in review before it shipped.

The three command surfaces that instruct the write were rewritten to match:
`commands/tickets.md` previews and asks before it reaches for `--create`,
`commands/scan.md` no longer files anything on its own, and
`skills/gizmoduck/SKILL.md` step 4 documents both runs and states plainly that
the `[Nuclei <id>]` de-dupe search is not the confirmation — it chooses between
creating a request and noting an open one, and both of those write.

Prose alone could not have closed this. The reason the entry stayed open through
several rounds was that nothing in the plugin performed the write, so there was
no line to put a check on; the answer was to stop producing the thing the write
needs.

**Two things this did not settle, recorded so they are not mistaken for closed:**

- **Whether the SDP MCP server confirms before `sdp_create` is still unread.**
  It was the decisive unknown when this entry was half-closed, and it is still
  unmeasured — settling it needs a way to observe `sdp_create` without filing a
  real ticket. It no longer blocks *this* item, because the gate above does not
  depend on the answer, but a different caller of those tools gets no protection
  from anything written here.
- **`skills/infra-work-ticketing/SKILL.md:209-211` still instructs the
  opposite** — "create the ticket and report what you made in the same turn - no
  confirmation round-trip." That skill is org-wide and was deliberately left
  alone: gizmoduck's commands no longer hand it a fileable payload, but any
  other path that invokes it directly is unchanged. Whether that instruction is
  right for the skill's own purpose is a separate question from this one.

### 2. `mcp-servers/core` credential chain caches its winner permanently

`AdminCredentialChain` (`mcp-servers/packages/core/src/adminAuth.ts:48-109`)
stores whichever link first succeeds in `this.resolved` and never retries an
earlier link for the process lifetime. Deliberate — the comment at `:44-46`
says so — but the consequence is that fixing `MS_ADMIN_CLIENT_SECRET` after
`cli` or `device` has won changes nothing until restart, and nothing says so.

Not necessarily a code change. A log line naming which link won, once, would
turn a silent wrong-identity into an obvious one.

### 3. `scopesOverride` silently broadens a narrow scope request

`src/adminAuth.ts:29-36`, `:127`, `:144` force `.default` for the `secret` and
`cli` links regardless of what the caller asked for. Only `device` honours
caller-supplied delegated scopes (`:159`).

Code that requests a narrow scope and receives `.default` did not fail — it was
never asked. That is the wrong default for a least-privilege story and should
at minimum be loud.

## Correctness and verification gaps

### 4. ~~`vault_guard.py` blocks every edit to a vault's own `CLAUDE.md`~~ — DONE

**Shipped 2026-09-05 as `obsidian-vault` 0.3.2, PR #69 (`3167721f`).** Seven
review rounds; the seventh ran against the merged head and came back CLEAN.

The fix is narrower than the plan below, and deliberately so. An early version
skipped `check_note` entirely for the exempt basenames — which also dropped the
required-keys, title-matches-filename and updated-date checks, while the comment
beside it still claimed the exemption was "frontmatter-only". A guarantee written
narrower than the code it describes is the same defect class as a guard that
fails open while looking like it checked. What shipped instead is an
`fm_optional` parameter suppressing **exactly one** issue, `NO FRONTMATTER`, so a
`README.md` that does carry frontmatter is still held to every other rule.
`ASCII_EXEMPT_NAMES` stays `{"claude.md"}` and was **not** widened. The suite
went from 44 to 57 assertions, each exempt name checked in both directions and
asserting the specific violation text rather than only an exit code.

The original entry follows, for the record.

`plugin/obsidian-vault/hooks/scripts/vault_guard.py:35` exempts `CLAUDE.md`
from the ASCII check **by design**, but not from the frontmatter check — so the
vault's instructions file is required to carry note frontmatter it can never
have. Every edit to it blocks.

Hit twice on 2026-09-05 while widening the `wiki/decisions` scope. The write
still lands (`PostToolUse`), so it is noise rather than prevention — but it is
noise on a legitimate, necessary edit, and it trains people to ignore the
guard. Extend the existing exemption to cover the frontmatter rule.

**A fix is already written and stashed**, not lost: `git stash list` ->
`TODO#4: vault_guard frontmatter exemption`. It adds
`FRONTMATTER_EXEMPT_NAMES = {"claude.md", "readme.md", "agents.md",
"gemini.md"}` and skips `check_note` for those basenames. It was kept out of
the crew 0.16.0 PR on purpose - an `obsidian-vault` file changing in that PR
would force an `obsidian-vault` version bump into a crew change. Before
shipping it: it has no regression test, and `CLAUDE.md` requires one for a
hook that can block. `git stash pop` it, add the must-block/must-allow cases,
bump `obsidian-vault` to 0.3.1.

### 5. `core` consumers import the built artifact; `dist/` staleness — CLOSED 2026-09-06

**The premise this was opened on was wrong in the direction that matters, and
the fix is narrower than the entry asked for.** Rewritten rather than ticked,
because a closure citing the wrong hole sends the next reader hunting a CI
problem that does not exist.

What is true: `mcp-servers/packages/core/package.json:11-14` does point `main`,
`types` and `exports` at `./dist/src/index.js`, and the tests import `dist/`
too, so compiled output really is what runs.

What is not: **`dist/` is untracked** — `git ls-files mcp-servers/packages/core/dist`
returns nothing — so "a CI check that rebuilds and diffs" has nothing to diff
against. And CI cannot test stale JS in the first place: `mcp-servers/package.json`'s
`test` is `npm run build && ...`, whose `build` is `npm run build -w packages/core
&& npm run build --workspaces`, so core is rebuilt first on every run.

The real hole is one invocation wide: `npm test -w packages/graph`, run after
editing `packages/core/src`, skips the root build and tests last build's core.
The consumer cannot see it — its own `dist` is current, its own tests compile,
and the behaviour under test is stale.

Closed by `mcp-servers/scripts/check-dist-fresh.mjs`, wired as every package's
`pretest`: newest `.ts` under `src/` and `test/` against newest `.js` under
`dist/`. A consumer is checked by checking **core itself, recursively** —
comparing the consumer's `dist` to `core/src` was the first shape and it is
wrong in the fail-open direction, since a consumer rebuilt after a core edit
then has the newest `dist` in the tree and still loads a stale `core/dist` at
runtime.

Two more fail-open shapes closed with it. An unreadable source directory raises
rather than contributing mtime `0` — `0` compares older than everything and
reads as fresh, so the guard would pass having seen nothing. And equal
timestamps are **stale**: measured on this repo, `npm run build` leaves every
package's newest `dist/*.js` strictly newer than its newest `src/*.ts` (11.9s
for core) with sub-millisecond mtime fractions, because tsc reads before it
writes — so accepting equal only ever admits a real edit landing in the same
coarse tick as an older build.

14 tests at `mcp-servers/scripts/_test/check-dist-fresh.test.mjs`, run by
`npm run test:scripts` which the root `npm test` now includes. Verified by
execution, not by reasoning: `touch packages/core/src/index.ts` then `npm test
-w packages/graph` exits 1 with `STALE BUILD -- @badali404/mcp-ms-core:
compiled output is not newer than core/src -- and @badali404/mcp-msgraph
imports it at runtime`, and passes again after `npm run build`.

### 6. `check_skill_manifests` is unread

`scripts/check-marketplace.py:122`. Confirmed to exist and to sit between
`check_registration` and `check_plugin_manifests`. Which SKILL.md frontmatter
fields it cross-checks against the marketplace entry is unknown, so
`.crew/codemap/skills.md` records the four-place registration rule without
being able to say what this function adds to it.

### 7. The install-scripts matched-pair rule has an enforcer — CLOSED 2026-09-06

Found, not written. `scripts/check-marketplace.py:194` `check_menu_parity`
parses `MENU_KEYS` out of the `.sh` and `Key = '...'` out of the `.ps1`'s
`$script:Catalog`, and fails when the two lists differ **as lists** — so a row
present in one, or the same rows in a different order, is caught, which is what
makes `--select 3,7` mean the same thing on both platforms. The same function
compares `MENU_DEFAULT` against the `.ps1`'s `Default = $true|$false` and names
each row that is ticked by default in one script and not the other, which is
the "default flags" half of CLAUDE.md's rule.

`scripts/check-marketplace.py:233` `check_group_parity` does the same for all
four sub-pickers (`own-skills`, `team`, `community`, `repo-plugins`), and also
fails an empty group — a sub-picker that would render nothing.

Nothing to build. The entry was opened because the check had not been located,
which is a different finding from it being absent, and the two are worth
keeping distinguishable.

## A green check on a stacked PR is a claim about its BASE, not about `main`

Found 2026-09-12 merging #101 and #102. Not a code bug — a review-process one,
and the first of today's five that is about how work is checked rather than what
the code does.

#102 was opened with `--base pylint-to-zero` because it depended on #101. While
#101 was open, `gh pr checks 102` read **12 passed, 0 failed** and
`mergeStateStatus=CLEAN`. Both were true, and both were about `pylint-to-zero`.

When #101 merged, **GitHub did not retarget #102.** Its base stayed pointed at a
branch that no longer existed. #102's head was `7e690647`, which is not a
descendant of `e46d5ba8` — the `ignored-modules` fix #101 shipped — so it still
carried an rcfile without `docx`, `pymupdf` or `PIL`. Retargeted to `main` by
hand, and the same PR read **3 build failures**, on 3.11, 3.12 and 3.13, for
exactly the bug #101 had just fixed. The other 9 checks stayed green throughout.

So the sequence that ships a regression is: read CLEAN, watch the parent merge,
merge on the reading you already have. Nothing announces that the reading went
stale, because nothing changed about the PR — what changed is the question the
answer was to.

**What to do instead**, in order:

1. After the parent lands, **retarget the stacked PR to `main` yourself** —
   `gh pr edit <n> --base main`. Do not assume GitHub did it.
2. Merge `main` into the branch. A rebase would be cleaner history, but this
   repo's guard hook refuses a force push, so a merge commit is the available
   move, not a preference.
3. **Re-read the checks after the retarget**, never before, and merge on that
   reading with `--match-head-commit`.

Verify against the ref you are merging INTO. This is the same rule the
`check-marketplace` correction records — a measurement without its ref can only
be believed, not checked — arriving by a different route: there the ref was a
dirty working tree, here it was a base branch that had been deleted.

## The paired one: a gate that skips its own check and still passes

`scripts/check-marketplace.py` prints

    note: not a git checkout - skipping the version-drift check

and then exits 0. So a run against a `git archive` export passes **without
running the check that matters**, and version drift — the thing the gate exists
for — goes unmeasured while the output says "all checks passed".

Hit 2026-09-12 while closing the "Five marketplace entries are shipping stale"
entry. It was caught only because the checker names the skip out loud, which is
the design property worth copying: where a check can decline to run, "could not
tell" has to be its own visible value rather than collapsing into the passing
one. Use `git worktree add --detach <tmp> origin/main` to measure a named ref;
an archive is not a git checkout.

## The third: an empty result from a misused API is indistinguishable from a real absence

Found 2026-09-12, one step short of being published. Checking whether
`filter_global` silently swallows a scalar landing where a block is expected
(`{"qa": 5}` -- it keeps it and reports `ignored: []`), the next question was
whether the `_prune` comment's claim that `_layer_supplies` "already reports
that correctly" was true. `inspect_global` was called as
`inspect_global(path)`.

The signature is `inspect_global(root, path=None)`, and it RETURNS a dict
rather than printing. So the call did not fail. It bound the path to `root`,
found no config there, and returned a result that read as "nothing to report"
-- one step from the conclusion "the comment claims coverage that does not
exist."

Called properly, `inspect_global(root, path)["findings"]` emits
`[missing-keys] not set globally, so the built-in default applies: qa.provider,
qa.order, qa.fallback, ...`, listing every `qa.*` leaf. The comment is true and
there is no gap.

**A function that answers a different question does not look like an error.**
It looks like an answer. Before reporting an absence -- a missing finding, an
empty list, a check that found nothing -- confirm the call was the one you
meant: check the signature, and prove the probe can produce a non-empty result
at all by feeding it a case that must trip it.

## The fourth: `git stash` captured a tree believed to be clean

Found 2026-09-12, and the only one of these whose cost would have landed in a
merged commit rather than in a report.

Switching branches mid-task, `git stash -q -u` was run on a working tree
believed clean. It was not: the post-commit graphify hook had regenerated
`graphify-out/GRAPH_REPORT.md` and `graphify-out/graph.json`, which are
generated artifacts CLAUDE.md says must never be hand-edited or committed. The
stash captured both silently -- a stash of nothing and a stash of two generated
files look identical at the prompt.

`git stash show --name-only stash@{0}` named them, the finding-1 commit was
confirmed intact, and the stash was dropped rather than popped. Had it been
popped later and swept into `git add -A`, the generated graph would have gone
into a crew PR.

**Check what a stash captured before trusting that it captured nothing**, the
same way you check what a gate measured. `git stash list` shows that a stash
exists; only `git stash show --name-only` says what is in it. The hook that
makes this likely is the repo's own: it rebuilds the graph after every commit
and every branch switch, so the tree is rarely clean for long after a commit.

## The fifth: a test that pins a number proves the number is stable, not right

Found 2026-09-12, and it is the one that indicts a check rather than a claim.

The 0.19.10 change declared nine previously-undeclared config keys and added
`assert len(declared) == 84`, with a docstring saying in as many words: "a
tenth key arriving undeclared is the same bug again, and a membership-only test
would pass while it happened."

There already was a tenth. `context.autoClear.unsafeFocus` is read at
`auto-clear.sh:93` and gates the `wtype` method at `:187`. The test shipped
green at 84 because 84 was what the tree held, not what was correct. **A pinned
number is a regression detector, not a correctness check** -- it freezes
whatever the author counted, including a miscount, and then defends it.

It is still worth pinning: the count is the only thing that will catch the
ELEVENTH key. But the number itself has to be derived by a method that could
have disagreed with the author, and here it could not: the author enumerated
the keys by reading the `.ps1` consumers, and the assertion counted exactly
what that enumeration produced. The check and the thing it checked shared a
source.

So when pinning a count, say in the test where the number came from, and make
the derivation independent of the enumeration it is meant to guard. The tenth
key was found by reading the `.sh` consumers -- a source the first pass had
not used -- not by any test.

## The sixth: measuring a tree mid-branch-switch

Recorded 2026-09-12, hit by a second person reviewing the above. A verification
script run against `HEAD` returned the pre-change counts (75 leaves / 38
global) on a checkout that was already at the post-change commit: the working
tree was mid-switch to another branch when the script read it. Re-run on a
settled tree it returned 85 / 44.

One step from reporting that a change was not present when it was. The repo's
own lesson covers it -- run the states, do not reason about them -- and this
adds the corollary: **check that the tree you measured is the tree you meant.**
A background hook that rebuilds on branch switch, which this repo has, widens
the window in which that is false.

## The seventh: a correction that outlives the thing it corrected

Found 2026-09-12, and the only one on this list that is CREATED by fixing
something.

`plugin/crew/README.md` §11 carried a sample `.crew/config.json` that had
drifted badly. Before it was dealt with, a pointer paragraph was added saying,
in effect: "the sample JSON and table above are older than `CONFIG.md` and
disagree with it; where they differ, `CONFIG.md` is the one that was checked."
True and useful at the time.

The next change deleted the sample. The pointer paragraph survived it, and now
told readers to distrust a sample that was no longer there -- a confident
sentence about a thing that did not exist, left behind by the act of removing
the thing.

**Deletion is exactly when this happens**, because the person removing content
is thinking about the content and not about what referred to it. A correction,
a caveat, a "see the table above", a test name that describes the old
behaviour: each is a reference, and a reference outliving its referent is worse
than no reference, because it reads as current.

When you delete something, grep for what pointed at it. Here that was one
paragraph in the same file, found only because the deleted region was re-read
afterwards rather than assumed correct.

These seven and the struck "already red on `main`" claim are one failure in
eight costumes: a check that did not run, a check that ran against the wrong
ref, a check that answered a different question, an API that answered a
different question, a state believed known without being read, a check that
froze its author's own miscount, a measurement of a tree that was moving
underneath it, and a correction still standing after its subject was deleted.
Each produces a confident sentence that is not true, and none of them looks
like a failure at the moment it happens.

Two sentences cover all eight. Prove the thing you believe is empty actually
is. And make the check's source independent of the thing it is checking --
where they share one, the check can only confirm, never contradict.

## Deferred by design, not oversight

- **`plugin/crew` is unmapped** in `.crew/codemap/`. It is the file set the
  in-flight PR is rewriting; mapping it now yields `DERIVE` facts from
  `fe538879` and judgment from a moved-on working tree. Run
  `/crew:onboard --refresh plugin/crew` after that PR merges.
- **Unmapped smaller areas**, in node order: `mcp-servers/` root (65),
  `mcp-servers/graph` / `intune` / `o365-admin` / `o365-user` (54 each),
  `claude-obsidian-setup/` (48), `vault-automation/` (22).
- **`/crew:diagram`** — deferred until the codemap covers `plugin/crew`, so the
  diagram does not need redrawing immediately.

## Found during the 0.16.8 merge review, deferred as out of scope

### `crew_py` can hand back a Python that is not a Python

`plugin/crew/hooks/scripts/_common.sh:38-43`. `crew_py()` returns the first of
`python3`, `python`, `py` that `command -v` resolves, and never checks that it
runs. On Windows, `command -v python3` succeeds on the App Execution Alias in
`%LOCALAPPDATA%\Microsoft\WindowsApps` — a stub that opens the Microsoft Store
and is not an interpreter. `crew_py` hands that stub to `guard.sh`, whose
`$PY -c ...` then produces nothing, so `CMD` comes back empty and
`[ -z "$CMD" ] && exit 0` fires: **the command guard stands down silently, on
exactly the platform where it has already shipped broken once.** A working `py`
sitting further down the list is never reached, because the first match wins.

Addressed 2026-09-24 (crew 1.0 burn-in fix3 round 2): `crew_py` now walks every PATH match and prefers the first that runs `-c pass` within 3s; with nothing runnable it still returns the first match, so its fail-closed callers keep refusing rather than standing down.

Confirmed by experiment, not inferred: with jq hidden and `C:\Python\314`
removed from PATH, `plugin/crew/hooks/scripts/_test/run-tests.sh` goes from
`128 passed, 0 failed` to `77 passed, 51 failed` — the must-BLOCK cases stop
blocking. `py -c "print(1)"` works fine in that same shell; `python3` is the
stub that wins.

Not fixed here on scope discipline: this is pre-existing in `_common.sh`, not
introduced by the branch under review, and `crew_py` is called from several
hooks — changing it is its own ticket with its own must-block/must-allow
regression cases, per the CLAUDE.md rule for anything that can block. The
`_test/run-tests.sh` guard added in this branch now *detects* the condition and
fails loudly, so the suite can no longer go green against a stood-down guard;
the underlying resolver is still wrong.

Fix shape when it is picked up: have `crew_py` execute each candidate
(`"$c" -c "print(1)"`) and return the first that actually runs, rather than the
first that resolves. Add a must-block case that runs with the stub first on
PATH.

### `CHANGELOG.md`'s "0.16.8: the machine-global config..." entries are mislabeled

`CHANGELOG.md:420` and five more at 469-650, all `crew 0.16.8: ...`. That
content actually shipped as **0.16.6**: `git show abe639ce:plugin/crew/.claude-plugin/plugin.json`
reads `"version": "0.16.6"`, and `abe639ce` (PR #65) is a real ancestor of
`origin/main` — so 0.16.6 is what anyone installing from `main` at that commit
actually got. This branch's own history even carried an intermediate state at
`4b92b518` (an earlier merge of `origin/main`) where `plugin.json` briefly read
**0.16.7** for the same content, before a later local commit moved on to
`0.16.8` for unrelated work (the PATH-scrub fix) and, at some point since, a
local edit relabeled this already-shipped entry's text from 0.16.6 to 0.16.8.

Found during the `origin/main` merge that brought in crew 0.16.7 (three
specialists, four dispatch-guard defects) and bumped this branch to 0.16.10.
The rule applied throughout that merge was: relabel a still-unreleased
CHANGELOG entry to the version it actually ships under; never relabel one
that already shipped. By that rule, 0.16.8 here is the mistake the rule
forbids — it should read 0.16.6.

Not fixed in that merge commit, on scope discipline: this divergence predates
the merge, is already committed, and spans ~200 lines of long-shared
CHANGELOG text that git did not flag as conflicting. `CLAUDE.md` is explicit
that renumbering historical prose outside the change at hand falsifies the
record in the other direction, and correcting it *approximately* inside an
unrelated merge commit is how a record gets quietly worse rather than better.

Fix shape when it is picked up: change the six `0.16.8:` labels at the lines
above back to `0.16.6:`, and confirm no other file (`plugin/UPDATE.md`,
`README.md`, `plugin/README.md`) repeats the same mislabel via its
`scripts/sync-updates.py` mirror.

## Moved to CLAUDE.md: `pathlib.write_text` converts a `.sh` to CRLF on Windows

Applied to `CLAUDE.md`'s Landmines list with the user's explicit yes. Kept as a
pointer rather than deleted outright, so anyone who remembers reading it here
finds where it went instead of concluding it was dropped.

## Nit: the request body is translated twice per request

`plugin/localgpu/cli/anthropic_proxy.py`. `check_fits_context` (via
`estimate_prompt_tokens`) and `to_ollama_request` each independently call
`to_ollama_messages`/`to_ollama_tools` on the same body, so the translation runs
twice per request rather than once and reused.

Both functions are pure and in-memory with no I/O, so this is discarded work, not
a correctness problem. Explicitly **not** worth blocking a release on and not
worth a version bump of its own — fold it into whatever next has a reason to
touch that file. Recorded because it becomes invisible the moment the session
that found it ends.

Note for whoever does fold it in: `check_fits_context(body, num_ctx)` at
`:1083`/`:1093` passing the raw `body` is **correct** as written, because
`estimate_prompt_tokens` translates internally. Changing those call sites to pass
`to_ollama_request(...)`'s output would double-translate and measure the wrong
thing. The obvious-looking fix is a bug.

## Correction: nothing under `.crew/` is committed, and one commit message says otherwise

**RESOLVED 2026-09-14, except item 1.** The closing paragraph's proposal was taken:
`!.crew/verify.json` is on the named un-ignore list and this repo tracks its own
map, so items 2 and 3 no longer describe the repo. Item 4 was already resolved
earlier by `!.crew/codemap/`. Item 1 stands as a permanent note about `ae1c92ee`
and must not be deleted — an amended-away wrong commit message is still wrong in
the history other lanes have read. The rest is kept below as the record of what
the policy was and why it changed.

`.gitignore` ignored the whole of `.crew/` deliberately, with a stated rationale —
`obsidian.vaultPath` and `boardDir` are absolute paths valid on one machine, and
`pm.authority` is a trust decision a clone should not inherit. That is correct
and should stay. But three consequences were not obvious and bit this session:

**1. `ae1c92ee`'s commit message is wrong.** It reads "Record both round-3 review
passes, and rebuild the code graph". The `.crew/metrics.md` append it describes
happened on disk and is still there, but `git add -A` silently skipped it as an
ignored path, so the commit contains only `graphify-out/graph.json` and
`plugin/localgpu/cli/anthropic_proxy.py`. The message claims a file the commit
could not have held. Not amended, because the commit is several deep and other
lanes have read it; recorded here instead so the history is not trusted blindly.

**2. The `/crew:review` skill's stated assumption is false in this repo.** It says
`.crew/verify.json` "is committed and travels between machines", and reasons from
that when deciding whether a rule naming an uninstalled agent is a gap. Here it
travels nowhere. A rule added on one machine is invisible on every other.

**3. Half of the CLI-suite gate fix does not travel.** `_verify/run-all.sh` now
runs `plugin/localgpu/cli/_test` and that change IS committed, so the gate is
fixed for everyone. The matching `.crew/verify.json` rule that maps
`plugin/localgpu/cli/**` to `run-all.sh` is local-only. The important half
travels; the routing half does not, and a fresh clone gets it back from
`/crew:init`.

**4. The codemap is local-only too.** `.crew/codemap/` now holds four subsystem
files and `crew_state.py` counts `knowledge.subsystems: 4` on this machine — but
a fresh clone reads 0 again. That is by design, not a defect: a clone runs
`/crew:init`. Worth knowing before anyone treats the codemap as a shipped
artifact.

If the intent is for `verify.json` specifically to travel while the rest of
`.crew/` stays machine-local, that is a one-line negation in `.gitignore`
(`!.crew/verify.json`) plus a decision about whether its `agents` lists are
portable. Not doing it unasked — it changes what a clone inherits.

**Done, with the `agents` decision made the other way.** The lists are NOT
assumed portable; `commands/review.md` and `crew-verification/SKILL.md` now say
that tracking the map makes a named-but-missing agent *more* likely, because a
committed map reaches machines whose roster nobody checked, and the existing GAP
report is what covers it. One thing surfaced that the clone-safety check missed:
`.crew/verify.json:129` runs `"/c/Program Files/PowerShell/7/pwsh"`, an absolute
Windows path in Git Bash form. It carries no username, host or secret, so it is
safe to commit, but that rule cannot run on a Linux clone. Left as-is — it is a
live rule in this repo's own map and rewriting it is not this change's job.

## Reorder promote-gate's clean-tree check below `requireHuman` — NOT reachable here, do not ship it blind

`plugin/crew/hooks/scripts/promote-gate.sh:158` (`# 4. clean tree`) blocks on a
dirty working tree before the `requireHuman` step at `:234` tells you to create
`.crew/.approved-<env>-<sha>`. The `.ps1` has the same shape. The claimed failure
is a deadlock: the gate blocks on a dirty tree, the fix for the block is to write
a file into `.crew/`, and writing it dirties the tree again.

**Measured 2026-09-14: not reachable under this repo's policy, and not reachable
via the un-ignore list on any flow.** `git check-ignore` on ten candidate paths
says `.crew/.approved-*`, `.crew/.deploy-in-flight`, `.crew/.verify-verified-at`,
`.crew/.verify-gate.lock`, `.crew/config.json` and `.crew/STATUS.md` are all
IGNORED; only `codemap/`, `endpoints.json` and `verify.json` are tracked. None of
those three is written by a promote or an incident:

- `codemap/` is written by `/crew:onboard`.
- `endpoints.json` has **two** writers, not one. `declare_endpoint`
  (`plugin/crew/hooks/scripts/crew_endpoints.py:258`) is reachable through
  `crew_state.py`'s `--declare-endpoint` CLI from the PM/work ticket flow, and
  `record_scan_artifact()` at `crew_endpoints.py:757` also writes the ledger,
  reached via `crew_state.py:2846` and instructed by
  `plugin/gizmoduck/commands/report.md:37`.
  **This correction is why the entry is worth re-reading rather than trusting.**
  An earlier version of this section said `declare_endpoint` was "the only
  writer of `endpoints.json` at all" — quoting that function's own docstring,
  which says exactly that and is wrong about its own module. A docstring is a
  claim, not a measurement. Neither writer is on a promote or an incident path,
  so the conclusion below is unchanged; the evidence under it was not.
- `verify.json` is written by `/crew:verify`, which is map authoring, not a
  deploy.
- The incident path writes `.crew/incident-skips.log` and `.crew/incidents/`
  (`commands/emergency.md:90,101`), both ignored.

**A residual risk was claimed here and it does not exist.** This section said a
consuming repo that adopts the un-ignore list but omits `.crew/.approved-*`
tracks the approval marker and opens the deadlock. That is false, and it was
asserted from reading the rules rather than running them. `.crew/*` already
ignores the marker and none of the three negations re-admits it: with both
`.crew/.approved-*` and `.crew/*.lock` deleted from this repo's `.gitignore`,
`git check-ignore` still reports `.crew/.approved-production-abc` and
`.crew/x.lock` as IGNORED, and the three un-ignored paths as tracked — byte for
byte the same verdicts as with them present. Omitting the explicit rule changes
nothing.

So the explicit entries are documentation, not mechanism, and `§3c` ships them
for that reason. `check_crew_ignore_policy` now settles this class of question by
building a throwaway repo and asking `git check-ignore` rather than by reading
the lines, which is what would have caught the claim when it was written.

So the code change is written down here rather than made. `promote-gate.sh` is a
**blocking** hook, and this repo's `CLAUDE.md` requires a committed,
sabotage-tested regression suite with must-block and must-allow cases before one
changes. Doing that for a deadlock nobody can currently reach spends the suite on
a hypothetical. If a flow ever writes a tracked `.crew/` path during a promote,
the fix is: move the `# 4. clean tree` block below the `requireHuman` verdict in
**both** shells, and the must-allow case is "`verify.json` tracked and dirty,
marker creation still reachable".

## Landmine candidate: an 8-character anchor can never match, and fails silently

**Staged here for a human to approve into `CLAUDE.md`'s Landmines list**, the same
way the `write_text` CRLF entry was. An agent asking for a project-instruction
change is not authorisation. Content below is ready to move verbatim.

`crew_state.py` decides whether a codemap or diagram is stale by comparing its
recorded anchor against `git rev-parse --short=7 HEAD` (`read_knowledge` and
`read_diagrams`). But the anchor patterns — `_ANCHOR_RE` and
`_DIAGRAM_ANCHOR_RE` — both accept `[0-9a-f]{7,40}`. So an anchor written with
`--short=8` **parses perfectly and then never equals HEAD**. There is no error,
no warning, and no hint in the output; every affected map or diagram simply
reports `behind` forever, including immediately after someone "refreshes" it.

The tell is that *all* of them flip to `behind` at once, right after the edit
that was supposed to fix them — which reads as the refresh having failed rather
than the anchor format being wrong. Write anchors with
`git rev-parse --short=7`.

**Related, and not a bug to fix:** `graphStale` and `diagramsStale` are
structurally unsatisfiable for any *tracked* artifact. The anchor names a commit,
and committing the file advances HEAD past the commit it names, so a committed
anchored artifact can never report itself current. Re-anchoring makes another
commit and reproduces the condition — there is no fixed point. The codemap under
`.crew/` escapes this only because it is gitignored, so re-anchoring it creates no
commit. Treat both triggers as artifacts; a diagram's anchor honestly records the
commit it was **drawn from**, which is what a provenance header is for.

## Briefing style: state claims as claims, and say that refuting them is a win

Three times in one session the most valuable thing a subagent did was refute a
confident claim in its own brief:

- The codemap lane checked "a user who tries to lift an unliftable entry is told,
  not silently ignored" and found `load_config` dropped it in silence — which
  became the localgpu 0.1.10 fix.
- `qa-proxy` refuted the framing that B1/B2/F1/F5 were one design error, and the
  correction carried a hard ordering constraint: fixing the clamp before the
  estimator would have capped every reply while no test went red.
- The diagram lane checked "`/localgpu:setup` is a six-step flow" against
  `setup.md:7`, which says "Seven steps, in order". `bootstrap.sh` is the one with
  six.

In all three the brief was confident and wrong, and the lane caught it only
because it went to source instead of transcribing. Make that deliberate rather
than lucky: in any lane brief, mark which statements are verified and which are
claims to check, and say explicitly that refuting the brief is a valid and valued
outcome. A lane that believes its brief is a lane that can only find the bugs you
already suspected.

## Crew's agent count is wrong in seven places and right in none — CLOSED 2026-09-12

**Closed 2026-09-12 at `39b8fefa`** (clean tree, `HEAD == origin/main`). Measured
**54 agents, 24 commands, 17 skills, 20 hook entries across 5 events**, two ways
that agree: `ls plugin/crew/agents/*.md | wc -l` gives 54, every file carrying a
`name:` frontmatter key with no README or template among them; and
`crew_state.ROLE_TIERS` (13) + `crew_state.SPECIALIST_ROLES` (40) + `pm` = 54,
with both set differences against the filenames empty. Re-run those two rather
than trusting this paragraph.

**Where the `29` came from — no previous pass identified it.** `plugin/PLUGINS.md`'s
agent table has exactly 29 data rows: 13 tiered + 15 specialists + `pm`. It was
written when there were 15 specialists and never grew with `SPECIALIST_ROLES`.
`marketplace.json`'s "29 ... (13 tiered, 15 domain specialists)" is that table
transcribed. So correcting only the `29` there would have shipped a sentence
asserting `13 + 15 + 1 = 54`; the `15` had to move to `40` in the same edit. The
table itself was left at 29 rows — writing 25 specialist rows is authoring, not
counting — but the heading above it no longer states a number and a new line
marks it abridged, so the next reader who counts rows is not misled the same way.

**Eleven sites changed, not seven.** A sweep for the same claim found four the
table below missed, which is that table's own lesson arriving on schedule. Where
the prose allowed it the figure is gone rather than corrected.

| Site | Was | Now |
|---|---|---|
| `scripts/install-prerequisites.sh:899`, `.ps1:855` | `11 agents, 21 commands` | `54 agents, 24 commands` — identical text in both, and width-neutral, so `pick_fit` / `Format-PickerLine` are unaffected |
| `.claude-plugin/marketplace.json:217` | `29 ... (13 tiered, 15 domain specialists` | `54 ... (13 tiered, 40 domain specialists` — description string only, no version field touched |
| `plugin/PLUGINS.md:17` | `29 agents` | `54 agents` |
| `plugin/PLUGINS.md:153` | `### Agents — 14, tiered plus the manager` | `### Agents — one per \`agents/*.md\`` — no figure; a new paragraph beneath marks the table abridged and gives the ladder/specialist/manager breakdown. No `.md` anywhere links to the old anchor (checked), and the section has no TOC entry |
| `plugin/PLUGINS.md:456` | `The 24 commands and 29 agents are` | `Every command and every agent is` |
| `README.md:165` | `50 subagents` | `54 subagents` |
| `plugin/crew/README.md:1982` | `50 agents — 13 ..., 36 domain specialists` | `54 agents — 13 ..., 40 domain specialists`, plus the `ls` re-measure |
| `README.md:883` | `29 agents, ...` | `54 agents, ...` — **not in the old table** |
| `plugin/README.md:414` | `50 agents, ...` | `54 agents, ...` — **not in the old table** |
| `plugin/crew/README.md:2051` | `The 24 commands and 29 agents are` | `Every command and every agent is` — **not in the old table** |
| `INSTALLATION.md:250` | `11 subagents, 23 slash commands, 16 bundled skills` | `54 subagents, 24 slash commands, 17 bundled skills` — **not in the old table**; the commands and skills figures went with it rather than leaving a line this change had already touched two-thirds wrong |

**Do not count the rows of `plugin/crew/README.md`'s specialist table.** It lists
`skill-author` twice, so a row count gives 41 specialists where the code has 40.
`tests/test_role_ladder.py` compares *sets* in both directions, so the duplicate
passes it. That is why the re-measure line added at `:1982` points at
`ls plugin/crew/agents/*.md` and explicitly not at the table above it. The
duplicate row is left in place — it is a separate finding from the count.

**Fixed 2026-09-13 (crew 0.19.28).** That comment no longer carries a count at
all: it names the two directories and says to `ls` them, because a count in a
comment nothing reads is a fact with a decay rate and no reader. It said "the 21
commands and 10 agents"; the real figures when it was corrected were 24 and 54.
As filed, it read:
`plugin/crew/hooks/scripts/_test/setup-walkthrough.sh:9` says "the 21 commands and
10 agents" in a comment — the same claim, but in a test file rather than anything
a user reads. `README.md:590`, `plugin/README.md:370` and `plugin/UPDATE.md:366`
say "taking crew to 14 agents" inside release-note sections, where it is a true
statement about 0.15.1 and **must not** be changed.

`python3 scripts/check-marketplace.py` passes. It cannot catch this class, and the
"Why no check catches it" note below still holds. No version was bumped and
`CHANGELOG.md` was not touched, by instruction; `scripts/_test/drift-detection.sh`
was run green at `69678908` by the user for this change and was not re-run here.

---

**Re-measured 2026-09-12 at `e7cc93a2`. Every figure below replaces one from the
2026-09-06 pass, and the heading changed with them** — this entry used to read
"wrong in three places, right in four".

Actual on disk: **54 agents, 24 commands**. The 54 is `13` (`ROLE_TIERS`) `+ 40`
(`SPECIALIST_ROLES`) `+ pm`, checked in both directions — no role named in code
lacks an agent file, and no agent file is unreachable from the roster. Re-measure
with `ls plugin/crew/agents/*.md` and `ls plugin/crew/commands/*.md` rather than
trusting this line; that instruction is the only part of the old entry that
survived contact with a second measurement.

| Location | Says | Actual |
|---|---|---|
| `scripts/install-prerequisites.sh:899`, `.ps1:855` | `11 agents, 21 commands` | 54 / 24 |
| `plugin/PLUGINS.md:17` | `29 agents, 24 commands` | 54 / 24 |
| `plugin/PLUGINS.md:153` | `Agents — 14, tiered plus the manager` | 54 |
| `plugin/PLUGINS.md:454` | `24 commands and 29 agents` | 54 |
| `README.md:165` | `50 subagents, 24 slash commands` | 54 |
| `plugin/crew/README.md:1978` | `50 agents — 13 tiered, 36 specialists, and pm` | 54 = 13 + 40 + pm |
| `.claude-plugin/marketplace.json` crew description | `29 ... (13 tiered, 15 domain specialists ...)` | 54 = 13 + 40 + pm |

**The "right in four" claim has inverted, and that is the durable lesson here.**
The 2026-09-06 entry named four places as correct: `marketplace.json`'s crew
description, `plugin/PLUGINS.md:17`, `plugin/README.md:370` and `README.md:773`.
None of them is a correct current-state claim today. Two were never current-state
claims at all — `plugin/README.md:370` is a line inside the `### crew 0.15.1`
changelog section, where "14 agents" is a true statement about 0.15.1 and not
about now — and `README.md:773` is now an unrelated PowerShell fence.

A finding that records which places are RIGHT acquires an expiry date the moment
it is written, because nothing re-checks a claim that something is correct. The
wrong sites at least get re-read when someone fixes them. This is the same shape
as ["a correction that outlives the thing it corrected"](#the-seventh-a-correction-that-outlives-the-thing-it-corrected)
above. If you record a correct-list again, record the command that regenerates
it, not the list.

**Why no check catches it.** `check_catalogs`, `check_menu_parity` and
`check_group_parity` compare keys and booleans, never descriptive strings, so
four separate places can state the count wrongly while the gate stays green.
`check_docs` (`scripts/check-marketplace.py:263-277`) reads three files and
never opens `plugin/PLUGINS.md` at all.

The two
scripts agree with each other, so the matched-pair rule is satisfied — they are
consistently wrong, which is why no check catches it. `check-marketplace.py`
compares the *menu keys* between the two scripts, not the descriptive text, and
nothing compares that text against the plugin it describes.

This is the first thing a user reads when deciding what to install, and it
undersells the plugin by a third.

**Not fixed in this PR deliberately, and the reason is process rather than
scope.** `CLAUDE.md` requires that after a change to either install script,
`scripts/_test/drift-detection.sh` is run by hand — it cannot run in CI — and the
README's install URLs, which are pinned to a commit SHA, are re-pinned. PR #67
has just been brought current with a verified drift run against its exact tip.
A one-line label fix would invalidate that run and buy another manual pass plus a
re-pin, for text that is wrong but harmless.

Fix in a follow-up alongside the other deferred items. When it is done, consider
whether the check that would have caught it is worth writing: the counts are
derivable from `ls plugin/crew/agents/*.md` and `commands/*.md`, so a smoke check
comparing the installer's advertised numbers against the directory contents is
about ten lines and would cover every plugin's menu line, not just crew's.

## The eighth: a re-derivation cannot be verified by the thing doing the re-deriving

Found 2026-09-12, during the pass that re-anchored the five codemap notes.

`.crew/codemap/crew.md` was re-derived from source and its header said so: "the
live claims below were taken from the source at this anchor, not carried forward
and re-pointed." A sweep afterwards — diff the new file against its previous
version, flag every citation sitting on a **byte-identical** line — found **33
citations that had simply been carried forward**. The header was true of the
paragraphs that were rewritten and false of the ones that were not, and nothing
in the file distinguished them to a reader.

Twelve of the 33 were wrong, and wrong by hundreds of lines rather than by one:
`TRIGGERS` was cited at `crew_state.py:486`, a blank line inside
`archive_stale_handoff`'s docstring, and is at `:833`. `DISPATCH_PATH` was cited
at `:1048`, a `hashlib.blake2b` call, and is at `:1592`.

**The 21 that were correct are what makes this dangerous.** Those files had not
moved between the two anchors, so a spot check would have landed on a correct
citation about two times in three and concluded the file was fine.

This is trap five's shape — the check and the thing checked sharing a source —
but sharper, because here the *claim* and the *evidence for it* were the same
act. Re-reading your own re-derivation cannot find the paragraphs you did not
re-derive: every paragraph you actually rewrote reads correctly when you check
it, and the ones you skipped are invisible from inside the work precisely
because you never looked at them.

**The reusable form.** After any refresh of a document that cites code, diff it
against the version it replaced and treat every surviving line carrying a
`path:line` as unverified until something independent resolves it. Those are
exactly the lines the refresh did not touch. The cheap version of the check —
does every citation name a file that exists, with the cited line in range and
not blank — costs about twenty lines and catches the whole class, including the
two of the twelve that pointed at blank lines.

It nearly was not run at all. Every citation had been verified *before* being
written and nothing verified them after, and the pass was one step from being
declared done.

## The staleness triggers are unsatisfiable for tracked artifacts

`crew_state.py` flags `graphStale`, `diagramsStale` and `knowledgeBehind` on a
strict `anchor != HEAD` comparison. All three artifacts are tracked
(`graphify-out/graph.json`, `docs/diagrams/*.mmd`, `.crew/codemap/*.md`), so
committing a refresh advances HEAD past the sha the refresh just recorded. The
condition is true the instant it is fixed and can never be cleared.

Evidence, at HEAD `dc32c12` against anchor `b56d41f`:

    $ git diff --name-only b56d41f..HEAD
    .crew/codemap/UPGRADE.md
    .crew/codemap/crew.md
    .crew/codemap/localgpu.md
    .crew/codemap/marketplace-registration.md
    .crew/codemap/verification-harness.md
    .gitignore
    docs/diagrams/architecture.mmd
    docs/diagrams/data-flow.mmd
    docs/diagrams/process.mmd
    graphify-out/graph.json

Ten files, and **not one is a source file** — the maps, the diagrams, the graph
and a comment-only `.gitignore` change. Every subsystem the codemap documents is
current in substance; the lag is the self-reference, not drift. Re-running
`/crew:onboard --refresh` or `/crew:diagram refresh` here would rewrite files
byte-for-byte identical and advance HEAD again.

The comparison needs to be "has any path this artifact documents changed since
its anchor", not "does its anchor equal HEAD". Until then the pulse reports
three permanent false positives, which is how a real staleness signal gets
trained away.

`plugin/crew/hooks/scripts/crew_state.py` — the anchor comparison.

## `/localgpu:ask` has no empty-argument branch

`plugin/localgpu/commands/ask.md:8` interpolates `$ARGUMENTS` straight into
prose — "`$ARGUMENTS` is the question" — and nothing in the file branches on it
being empty. Invoked with no question the command renders its whole body,
including the retrieval procedure and the VRAM warning, with a blank where the
question should be. There is no instruction for that state, so the reading model
has to invent one.

Observed twice in one session, both times as a bare `/localgpu:ask`.

The fix is a guard at the top: if `$ARGUMENTS` is empty, print the
`argument-hint` line (`<question> [--k N] [--glob <pattern>]`) and stop, without
loading the rest. Cheap, and it turns a confusing non-response into a usable one.

**Check the sibling commands for the same shape before fixing just this one.**
`/localgpu:search` takes the same flags and almost certainly has the same gap;
`gizmoduck`'s `scan`, `report`, `tickets` and `diff` all take required
arguments. A command whose entire body is instructions for work it cannot do is
worse than an error, because it reads as though it is working.

`plugin/localgpu/commands/ask.md:3` carries a correct `argument-hint` already —
the metadata is right, nothing consumes it on the empty path.

## `resolve_role` accepted any provider name, and the review gate failed open — CLOSED 2026-09-06

**Fixed before this closure was written, not by it.** The analysis below is
kept verbatim because it is the record of what the hole was; what follows
immediately is where each half of it is now closed, cited so the claim can be
re-checked rather than believed.

- `plugin/crew/hooks/scripts/crew_state.py` defines `QA_PROVIDERS` and bars an
  unrecognised QA provider as **item 0 of `resolve_role`, before the family
  check is reached** — with the reason this entry asked for stated in the
  announce line: an unrecognised name "is not a reviewer at all, and
  `family() is None` for it must never read as no conflict."
- The write side refuses too: `crew_config.validate_providers` rejects a
  provider outside the set and **names the offending key**, covering
  `qa.provider`, `qa.order` and `qa.roles.<role>.provider` — the two holes the
  table below called out. `crew_config.order_candidates` marks such a row
  ineligible with the same reason, so `auto` cannot walk into one either.
- Regression coverage exists on both sides, in
  `plugin/crew/tests/test_provider_table.py`: must-block for a pinned
  `localgpu` reviewer, for an unpinned one (the worse case — `family` is
  `None`), and for a name crew has never heard of; refusal-with-key-named for
  each of the three config shapes; must-allow for `auto`, which is not in
  `QA_PROVIDERS` and must still resolve.

One thing deliberately left as it is: the bar sets `barred: True` and appends
to `announce` but leaves `barredBy: None`. That is not an oversight —
`crew_config.py:1041` documents it and `:1073` branches on it, because
`barredBy` names a *family* and an unrecognised provider has none. "BARRED —
same `None` family as the author" would be a worse line than the one that
actually prints.

Verified by execution at `1394aab6`, not inferred — that ref is the state the
entry describes, which predates the fix.

### No code validates a provider name

The closed set `{claude, codex, copilot}` appears three times in the Python and
is never a check:

- `crew_config.py:792` — builds a dict of names for the report
- `crew_config.py:794` — `onPath` probe for codex/copilot
- `crew_state.py:1334` — the default `qa.order`

`resolve_role` (`crew_state.py:1612`) takes the name verbatim:

    provider = pin.get("provider") or block.get("provider") or "claude"

The only validation that exists is **prose in `commands/model.md:105-119`,
executed by a model**. Hand-editing `.crew/config.json` bypasses it completely,
and so does a model that reads the table imprecisely.

### The table itself has two holes

| Key | Documented rule | Hole |
|---|---|---|
| `dev.provider` | `claude`, `codex`, or `copilot` | closed |
| `qa.provider` | `auto`, or a name in `qa.order` | **`qa.order` has no rule, so adding `localgpu` there makes `qa.provider: localgpu` valid** |
| `qa.roles.<role>` | "a `{provider, model}` object. Any role name is accepted" | **says nothing about the provider VALUE. `qa.roles.review.provider: localgpu` passes.** |

So the restriction on `dev.provider` is real and the same restriction on the
reviewer seat does not exist.

### What resolve_role then returns

Config: `dev.provider: codex` / `gpt-6-astra` (author family `gpt`), reviewer
pinned to `localgpu`.

    provider   = 'localgpu'
    model      = 'qwen2.5-coder:7b-instruct-q4_K_M'
    family     = 'qwen'
    barred     = False
    announce   = []

`qwen != gpt`, so the family-independence guard **passes cleanly**. The 7B is
affirmatively cleared to review GPT-authored code.

Unpinned is worse. `qa.provider: localgpu` with no model:

    family     = None
    barred     = False
    announce   = []

`family` is `None`, and the guard reads
`if out["family"] is not None and out["family"] in authors` — so it **does not
run at all**. Not "a different family cleared it": the check is skipped.

### The part that makes it undetectable

`announce` is `[]` in both cases, against a docstring that states the contract
directly (`crew_state.py:1643-1646`):

> `announce` is never empty when something happened. A review that quietly ran
> on the fallback is indistinguishable from one that ran on the pin, and the
> difference matters most exactly when the pin was chosen to get a different
> family onto the diff.

An unknown provider is precisely "something happened", and nothing is said. The
config file reports a reviewer is configured, `resolve_role` agrees, and a 7B
that agrees fluently produces output indistinguishable from a real pass. Same
shape as every other defect in this file: **the signal and its absence look
identical.**

### Fix shape

`resolve_role` must not silently accept a provider it has no runner for. Either
bar it, or at minimum append to `announce` — a review that ran on an unknown
provider must never be reportable as clean without saying so. `family()`
returning `None` for an unrecognised provider must not be treated as "no family
conflict"; unknown is not the same as independent.

Needs must-block / must-allow regression cases and sabotage testing per
CLAUDE.md, since it governs a gate that can block.

**Taken, in full: barred rather than merely announced.** See the closure at the
top of this entry for where each part lives.

## `sabotage.py` could leave a live mutation in the tree and still report PASS — CLOSED 2026-09-06

Fixed in crew 0.16.24. All four defects below are closed; the analysis is kept
because it is what the fix was built against, and because defect 1's residue is
permanent and needs to stay visible.

| Defect | Where it is closed now |
|---|---|
| 1. `finally` does not survive a kill | `install_exit_handlers` registers `atexit` plus SIGTERM/SIGINT/SIGBREAK/SIGHUP, each looked up with `getattr(signal, name, None)` because SIGBREAK is Windows-only and SIGHUP POSIX-only. A restore that FAILS on that path stays in `_LIVE` so the atexit pass retries it. **SIGKILL is still uncatchable and always will be** — defect 2's guard is what covers it, on the next run. |
| 2. The next run destroys the only good copy | `main` calls `stale_backups` before touching anything, prints the `mv <target>.bak <target>` line that undoes the mutation still in the tree, and exits 2 without mutating. `apply_mutation` raises rather than copying over an existing `.bak`, and builds each backup as `<target>.bak.partial` before `os.replace`-ing it into position — so a `.bak` is complete or absent, never half-written. That last part is not decoration: the startup guard tells the user to move a `.bak` over the target, so a partial one would make that instruction the thing that destroys an intact source. |
| 3. The restore is never verified | A sha256 per target is taken before the first mutation, held in module state, and compared after every restore **on all three paths** — the loop's `finally`, the signal handler and atexit. A mismatch prints both digests and fails the suite, so `PASS` can no longer be printed over a modified tree. Verifying only the loop's path while claiming all three would be the same defect wearing the fix's label. |
| 4. `crew_state.py.bak` is tracked | It is no longer tracked (`git ls-files '*.bak'` is empty), and `*.bak` plus `*.bak.partial` are in `.gitignore` — the existing `env.bak/`/`venv.bak/` entries are directories and never matched a file. The reason recorded there is that a **tracked** `.bak` now gates the suite off on every clone, since the harness refuses to start when it sees one. Ignoring does not preserve a `git status` signal; ignored files are hidden from it, and the filesystem check at startup is what replaces that. |

Coverage: `plugin/crew/tests/test_sabotage_harness.py`, 16 tests, none of which
touch a real source file — a regression suite for a harness that corrupts files
must not be able to corrupt what it is testing against. Sabotage-tested
independently: ten mutations, one per guard, 10/10 red.

That independent run paid for itself on the first pass by catching one of these
new tests being **vacuous**: it asserted a `.bak.partial` was gone after the
run, which `apply_mutation` makes true whether or not the sweep that removes it
exists. It now observes the state at the moment the first mutation is applied,
which only the sweep can produce. Worth recording because it is the exact thing
this suite exists to find, found in the suite's own coverage.

**Not taken: mutating a copy under a temp tree.** It removes the whole class,
and it is the right answer eventually. It is not this change because `run_test`
invokes pytest against the real checkout, so relocating the mutation means
relocating the suite it is trying to make go red — a bigger change than the
four guards above, and one that would land untested alongside them.

Landed in `d362a2bd`: `plugin/crew/hooks/scripts/crew_state.py:1191` shipped as
`if False:
        frozen = frozen` instead of the real
`if isinstance(frozen, str): frozen = frozen.replace("\\", "/")`. That is the
"frozen artifact path is stored with native separators" mutation. A path frozen
on Windows then never matches on Linux, so a completed scan reads as unscanned
forever on any other machine. Found by review, not by any gate.

`plugin/crew/tests/sabotage.py` mutates real source in place: `apply_mutation`
(:980) copies `target` to `target + ".bak"`, writes the mutation, and `restore`
(:1024) does `shutil.move(backup, target)`. `main` (:1041-1043) wraps only the
`run_test` call in `try/finally: restore(target)`.

Four distinct defects, in the order they bite:

1. **`finally` does not survive a kill.** It unwinds on exceptions, including
   `KeyboardInterrupt` -- but a `SIGTERM` or `SIGKILL` from an external timeout
   terminates without unwinding, so neither `restore` nor any cleanup runs. The
   mutated file and its `.bak` both survive. This is the most likely cause here:
   the run was killed by a harness timeout mid-mutation.

2. **The next run destroys the only good copy.** After a killed run leaves
   `crew_state.py.bak`, the next `apply_mutation` does
   `shutil.copy(target, target + ".bak")` unconditionally -- overwriting the
   good backup with the ALREADY-MUTATED file. The harness's own mutation table
   flags exactly this class for the code under test (:174-176, *"Skipping the
   backup when the name is taken destroys the newer original and then reports
   that it was saved"*) and the harness itself does it. There is no startup
   guard that refuses to run, or recovers, when a stale `.bak` is present.

3. **The restore is never verified.** Nothing compares the file to its pre-run
   content after `restore`. `main` prints PASS from `ok`, which tracks only
   whether each mutation went red -- so a restore that silently failed is
   indistinguishable from one that worked. Signal and absence identical, which
   is the failure mode this repo keeps shipping.

4. **`crew_state.py.bak` is tracked in HEAD** (`7c420e90`, swept in by
   `git add -A`; the removal in `d362a2bd` did not take). It is not stray lane
   litter -- it IS the harness's backup, and a `.bak` appearing in `git status`
   is the diagnostic tell that a run died mid-mutation. Tracking it removes that
   signal and makes defect 2 permanent, since the file is always present.

Fix shape: restore on every exit path including signals (`signal` handlers plus
`atexit`, not `finally` alone); refuse to start -- or recover from -- a stale
`.bak` rather than overwriting it; verify the restored bytes against a hash
taken before the first mutation and fail the suite loudly if they differ;
untrack the `.bak` and add it to `.gitignore`. Consider mutating a copy under a
temp tree instead of real source, which removes the whole class.

Verified while scoping this: exactly one sabotage-shaped line exists in all of
HEAD's Python (`crew_state.py:1191`), and the HEAD-vs-worktree diff for that
file is exactly those two lines -- so the working-tree restore is complete and
nothing else was left mutated.
## `render.sh` cannot render a diagram on Windows — it hands `mmdc` a `/tmp` path

`skills/crew-diagrams/scripts/render.sh` writes a puppeteer config to a Git
Bash `/tmp/puppeteer-XXXX.json` and passes that POSIX path to `mmdc`, which is
a Windows Node program that cannot resolve it. Every render fails identically:

```
FAIL  architecture.svg
Configuration file "/tmp/puppeteer-DQrB.json" doesn't exist
```

Six for six on 2026-09-05 (`architecture`, `data-flow`, `process`, `.svg` and
`.png` each), exit 1.

**This is not a Mermaid problem, and that is the part worth writing down.** The
same three sources render cleanly when `mmdc` is invoked directly with a
Windows-resolvable output path — 71632, 40140 and 75882 bytes of SVG. Anyone
reading only the render log would conclude the diagrams are broken and start
editing correct Mermaid, which is the expensive wrong turn this entry exists to
prevent.

Fix shape when it is picked up: resolve the temp path through `cygpath -w`
(or write the config beside the output directory) before handing it to `mmdc`,
on the branch that already knows it is on Windows. The `_test` fixture should
assert a non-zero output file, not just exit 0 — the failure above still wrote
`docs/diagrams/out/` and reported a summary line, so an exit-code-only check
would have passed it.

Found while re-anchoring the diagrams after PR #69, 2026-09-05. Anchor
`3167721f`. Measured, not inferred: both the failing and the passing
invocations were run.

## `crew_state.py` is 3283 lines and should be split — CLOSED 2026-09-06

**Done in crew 0.16.22** (PR #76, `ac93221d`). Split three ways:
`crew_state.py` 3300 -> 2293 lines, the endpoint ledger into
`crew_endpoints.py`, and the three shared readers into `crew_common.py`.
`max-module-lines` was not raised. Both hazards named below were real and were
handled: the codemap citations were re-anchored, and every `sabotage.py` anchor
was re-verified as matching exactly once in the file its mutation names. A
third hazard the entry did not predict turned up and is worth carrying forward
— a re-export is a second binding, so `monkeypatch.setattr(crew_state, "<moved
name>")` now succeeds and rebinds a name nothing reads;
`tests/test_module_split.py` is the guard for it.

The original entry, kept because its reasoning is what made the split safe:

It went 2154 -> 3283 on the endpoint-ledger branch, a 52% increase in one
module. `.pylintrc`'s `max-module-lines` was raised 2400 -> 3300 to let CI pass,
which unblocks a branch and fixes nothing: the ceiling now tracks the file
rather than constraining it, and that is the second time it has been raised for
exactly that reason (2000 -> 2400 before it).

The module now holds at least five separable concerns: config/schema resolution,
the dispatch record, the codemap and diagram anchor comparisons, the provider
and family guards, and the endpoint ledger. The last is the newest and the most
self-contained -- `read_endpoints`, `declare_endpoint`, `scan_artifact_path`,
`_candidate_record`, `_artifact_confirms_scan`, `gizmoduck_installed` and the
monorepo detection - and is the obvious first extraction.

Two things make this harder than it looks, and both belong in the ticket rather
than being discovered halfway:

- **Every `path:line` citation in `.crew/codemap/crew.md` points into this
  file.** A split invalidates all of them at once, so the codemap refresh is
  part of the work, not a follow-up.
- **`sabotage.py`'s mutation table addresses this file by line-anchored
  content.** Mutations that no longer match anything do not fail loudly -- they
  are simply not applied, and the suite still reports PASS. Any split has to
  re-verify that every mutation still binds, or the harness silently covers less
  while looking identical. That is the same signal-and-absence failure this file
  is full of.

Do not raise `max-module-lines` a third time.

**It was raised a third time, on 2026-09-22, to 3400.** Recorded here rather
than left contradicting `.pylintrc`, because two files stating opposite rules is
how the next reader "reconciles" them into whichever one they found first. The
raise was taken under a CI deadline and it did not close this item -- it
reopened it. `crew_state.py` is 3376 lines again, nine days after the
`crew_guards` split was supposed to have settled it, and `plugin/crew/tests/
sabotage.py` (3342) crossed the old ceiling at the same time, so there are now
TWO modules owed a split rather than one. `.pylintrc` carries the full reason
alongside the number. The hazards this entry names are unchanged and still
apply to whoever does the split.

## Perplexity is an agent, not a `qa.provider` — the routing half is not done

Opened 2026-09-06 with crew 0.16.23, which added `crew:qa-researcher`
(`plugin/crew/agents/qa-researcher.md`): a domain specialist holding the
`mcp__perplexity__*` tools that checks what a diff assumes about the outside
world against live sources. That half shipped and is usable today.

What did not ship is Perplexity as a selectable reviewer. `qa.provider` and
`qa.roles.*` still resolve to the same set they did before
(`plugin/crew/hooks/scripts/crew_config.py`), so `/crew:review`'s routing, the
fallback chain and the self-review family guard are untouched. That was
deliberate — the guard bars a reviewer whose family matches the author's, and
Perplexity's family, fallback behaviour and what "the model that reviewed this"
even means for a web-grounded answer all need deciding before a name is added
to that table. `resolve_role` accepting any provider name (the open entry above)
is the reason a half-answer here would fail open rather than loudly.

Three questions to settle before writing any code:

- **What family does it report?** A wrong answer either bars a reviewer that is
  genuinely independent, or clears one that is not. "Could not tell" has to
  survive into every row derived from it.
- **What does it review?** It is strong on "is this deprecated / is there an
  advisory" and weak at reading a diff's logic. A `qa.provider` slot implies the
  second, which is the thing it is worst at.
- **What happens when the MCP server is absent?** The agent stops and says so.
  A provider entry would need the same, and `qa.fallback` is the existing
  mechanism — but a fallback that silently produces a different kind of review
  is not the same check.

Until then, the honest description is the one in crew's README section 12b:
Perplexity is an opt-in second pass alongside the code review, not a reviewer
crew can route to.

## Session transcripts and subagent tool-result files write raw file content to disk with no secret redaction

Filed from a consumer repo (AcmeSelect), where the pattern was found
concretely and is tracked there as `TO-DO.md` F155/F157, and cross-referenced
against SRL's own counterpart ticket `SRL-997`. Recorded here per that repo's
own `.crew/secrets.md` §10: "a value printed into a tool result... is written
to the session transcript on disk, carried into every compaction summary, and
repeated into every subagent that inherits that context. It cannot be
un-printed." That is a property of this harness's transcript persistence, not
of any one project, so fixing it only in the consumer repo leaves it live in
every other repo this plugin touches.

**What was actually observed, twice, in one session, in that repo — despite
the operator having already read the exact warning beforehand:** a `Read`/`sed
-n` pass over that repo's committed `config/env.{development,production}.php`
files printed a production and a development database password verbatim into
the session's own tool-result output and `.jsonl` transcript; a later `grep`
for a literal username value did the same for a production DB username. Both
are now sitting in plaintext in local transcript/tool-result files
(`~/.claude/projects/<repo>/**/*.jsonl` and equivalent subagent transcript
files) purely as a side effect of reading files the project's own convention
already flagged as sensitive — no malice, no unusual command, just the
default behavior of a normal file-read tool call in this harness.

**Why "just don't do that" is not a fix.** Two independent lanes in that
repo's history made the identical mistake on the same day, one via a `sed`
redaction with a quoting bug that printed the value it was trying to hide, one
via an early `grep` used to locate a value before comparing it. A third
instance (this one) happened in a *different* session, after the operator had
read the written-down rule immediately beforehand. A rule that only humans (or
Claude) have to remember correctly, every single time, forever, across every
project, is not a control — it is hope with a docs page. The actual fix has
to sit in the harness or the plugin's tool-interception layer, not in prose a
lane might not re-read at the right moment.

**Where this plugin already has the right shape of hook, and could extend
it:**

- `plugin/crew/hooks/hooks.json:11-19` already registers a `PreToolUse`
  matcher on `Bash` (`guard.sh`/`guard.ps1`) that runs *before* every shell
  command and can `exit 2` to block it outright — see the `block()` helper and
  the destructive-operation rules in `plugin/crew/hooks/scripts/guard.sh:17-32`
  (terraform apply/destroy, destructive DDL, force-push, `rm -rf /`, etc.).
  That is the exact interception point a "do not raw-read a declared secret
  file" rule would need, and the file already has the regex-and-`block()`
  idiom to add it in.
- **What such a rule could plausibly catch:** a `cat`/`sed`/`grep`/`echo`/`type`
  (or shell redirection like `< file`) invocation whose argument matches a
  project-declared secret-bearing path. A repo that documents its own
  secret-bearing files (as `.crew/secrets.md` already asks every onboarded
  repo to do, listing exact paths) gives the hook a concrete, low-noise
  denylist to match against, rather than needing a generic entropy heuristic.
  Denying the raw read and pointing at the hash-compare procedure
  (`.crew/secrets.md` §10's own "hash, do not read" idiom) would close the
  *shell-command* half of this exposure — the half both real incidents and
  this one went through.
- **What that fix does NOT close, and is the harder half:** any read of such a
  file through the `Read` tool itself (not `Bash`), which is a first-class,
  non-shell tool this plugin's hooks do not currently intercept at all before
  a repo-declared secret path — and which is exactly the tool that produced
  the specific 2026-09-06 exposure described above (a direct `Read`/file-view
  call on the config files, not a shell command). A `PreToolUse` matcher on
  `Read` (this harness does support multi-tool matchers the same way it
  supports `Bash`/`PowerShell` today) checking `tool_input.file_path` against
  the same declared-secret-path list would be the natural second half.
- **What neither of the above closes:** once a tool call is *allowed* to run
  and returns content, this harness's own transcript writer persists that
  content to the `.jsonl` file on disk with no redaction pass, and no hook in
  this plugin runs *after* that point with write access back into the
  transcript file. A `PostToolUse` hook could observe the outbound content and
  warn, but by the time it fires the content is already on disk — the
  transcript-writing step itself is core-harness behavior outside this
  plugin's reach, and closing this half would need a request into the host
  CLI/SDK, not a plugin change. Recorded here as the ceiling on what a
  plugin-side fix can achieve, not skipped over.

**Fix shape, in priority order (each independently useful, none complete on
its own):**

1. Extend `guard.sh`/`guard.ps1`'s existing `PreToolUse`/`Bash` matcher with a
   `block()` rule for raw-read commands against paths a project declares
   secret-bearing (read that project's own `.crew/secrets.md` "declared"
   locations, if present, as the denylist source — no new config surface
   needed).
2. Add a parallel `PreToolUse` matcher on the `Read` tool (and any other
   first-class file-reading tool this harness exposes) applying the same
   denylist to `tool_input.file_path`.
3. File the transcript-redaction gap as a request against the host CLI/SDK
   itself, since no hook available to a plugin today can act on content
   already written to a `.jsonl` transcript.

**Not fixed here — this is the finding, not the patch.** No code in this pass
was changed; `AcmeSelect/TO-DO.md` F157 is the record of the concrete
2026-09-06 instance and the workaround applied there (comparing secret values
by `strpos()`/hash entirely inside a single script process rather than via any
shell command, going forward, in that one repo, for that one task).

**Related.** `SRL-997` (the same check-shape gap, filed independently in a
different consumer repo); `AcmeSelect/TO-DO.md` F155 (the original,
broader finding — committed secrets appearing in transcripts generally) and
F157 (this specific incident plus the `_verify` control that incident's task
was building); `AcmeSelect/.crew/secrets.md` §9-§10 (the procedure this
gap makes hard to follow reliably by hand).


## Two install-script invariants CLAUDE.md states that the scripts do not hold

Both verified 2026-09-06 at `1f97e51c` by reading the worktree. Found while
re-reading `.crew/codemap/install-scripts.md`, whose per-path diff against its
anchor was **empty** — neither of these is drift; both were true at the previous
anchor too.

### 1. `json_query` resolves `python3` only — not `python`, not `py`

`scripts/install-prerequisites.sh:164-176` tries `jq`, then `python3`, then
`return 1`. CLAUDE.md's landmine says: "Git Bash ships without `python3`.
Resolve `python3`/`python`/`py` and fail loudly on stderr rather than
suppressing the error and exiting 0." Both back ends carry `2>/dev/null`, so a
back end that runs and fails is indistinguishable from one that is absent.

`jq` is tried first, so this bites only where `jq` is absent AND `python3` is
absent while `python` or `py` is present — an ordinary Git Bash box with the
Windows Python launcher.

Traced consequence: `json_query` returns 1 -> `PLUGINS_CACHE` is empty
(`:248`) -> `plugin_version` returns 1 for every name (`:260`) -> every plugin
reads as not-installed and is reinstalled. That is loud rather than silent,
which is the only reason this is not urgent. It still violates the stated rule,
and the `2>/dev/null` is the part that makes a diagnosis expensive.

### 2. The scroll line bypasses `pick_fit` / `Format-PickerLine`

CLAUDE.md: "Nothing may bypass `pick_fit` / `Format-PickerLine`. Clipping is
degradation; a line that *wraps* throws off the cursor-up redraw count and
smears the menu over what was above it."

The `showing N-M of T` line is printed directly in both scripts —
`scripts/install-prerequisites.sh:1271-1272` (`printf`) and
`scripts/install-prerequisites.ps1:1140-1141` (`Write-Host ... PadRight`) —
without passing through either clipper.

It cannot wrap today: the string is bounded near 24 characters and both scripts
floor the width at 40 columns (`sh:1150`, `ps1:1105`). So this is currently
harmless *by arithmetic, not by construction* — the invariant is stated
absolutely and holds only incidentally. Worth either routing through the
clipper or amending CLAUDE.md to name the exemption; leaving it undocumented is
what makes the next reader distrust the rule.

Related: the two clippers are **not** interchangeable — `pick_fit` reserves one
character for a single-character ellipsis, `Format-PickerLine` reserves three
for `...` and additionally pads. A line tuned against one can overflow the
other.


## `wazuh-onprem` writes production config with no confirmation, and redacts nothing

Both verified 2026-09-06 at `1f97e51c` by reading the worktree. Found while
re-reading `.crew/codemap/skills-security-ops.md`, whose per-path diff against
its anchor was **empty**. Neither is drift.

### 1. `manager_config.py apply` has no confirmation of any kind

The `apply` subparser (`skills/wazuh-onprem/scripts/manager_config.py:251-254`)
accepts only `--block`, `--anchor` and `--restart`. There is no `--yes`, because
there is no prompt: a grep of the whole file for `input(`, `confirm`, `--yes`,
`_auto_confirm` and `getpass` returns nothing.

`cmd_apply` (`:170-223`) backs up, then `sudo cp`s the candidate over the live
`ossec.conf` at `:200`, in one non-interactive run. It does validate after the
copy and roll back on failure — real, enforced, and worth keeping — but the
rollback protects against a *bad config*, not against an *unintended run*.

The only restraint on intent is prose at `skills/wazuh-onprem/SKILL.md:144`.
Compare `meraki_config.py`, the sibling skill: its apply is safe by control
flow — `:152-187` cannot reach the PUT at `:176` without taking the snapshot
at `:157` — and it carries `HARD_BLOCKS`/`check_hard_block` plus batch caps.
One skill enforces; the other describes.

### 2. Zero redaction, while two commands emit the whole config

`grep -rniE 'redact|scrub|mask|sanitiz' skills/wazuh-onprem/scripts/` returns
nothing. Meanwhile `cmd_diff` writes the full live `ossec.conf` to stdout
(`:167`) and `cmd_fetch` writes it to `--out` (`:148`). That file carries
integration webhook URLs and authd keys.

This compounds the already-recorded finding that session transcripts write raw
secret content with no redaction (commit `1f97e51c`): the output of a single
`manager_config.py diff` lands verbatim in a transcript.

`meraki_diff.py:32-42` does display-path redaction, so the pattern exists in
this repo already and was simply not applied here.


## Queued 2026-09-08 — Codex QA findings on the new skills' own scripts

Raised by the Codex review of PR #81 (`gpt-5.6-luna`, `model_reasoning_effort=high`)
against `1f97e51c...HEAD`. Every one is **inside the two new skills' scripts**, not
in the marketplace wiring that PR added — they are pre-existing bugs in code that
was written before the PR and merely registered by it, which is why they were
ticketed rather than fixed in the same change. Anchor: `9370ad02`.

Not independently re-verified line by line; each is the reviewer's own repro,
kept in its words so a reader can check it rather than trust it.

### `skills/power-automate-api/scripts/pa.py`

1. **`pa.py:143` — a custom `--client-id` is not cached**, so a token refresh
   silently falls back to `DEFAULT_CLIENT_ID` and later SharePoint calls fail.
   Repro: log in with `--client-id`, expire the token, run a command that
   refreshes.
2. **`pa.py:360` — snapshot filenames use second-resolution timestamps**, so two
   patches of the same flow inside one second overwrite each other's rollback
   state. Repro: start two same-flow patch processes within one second and list
   the snapshot files. (Note this is the rollback safety net, so the failure is
   silent until a rollback is actually needed.)
3. **`pa.py:69` — DNS, connection, timeout and non-JSON responses escape as
   unhandled tracebacks** rather than a diagnosed error. Repro: point a command
   at an unreachable or malformed endpoint.
4. **`pa.py:472` — the rollback command it prints omits the required `--org` and
   `--flow` arguments**, so copying it verbatim fails immediately. Repro:
   complete a patch and run the printed command. Worst of the four: the one
   moment a user needs it, it does not work.

### `skills/jira-manager/scripts/jira-api.sh`

5. **`jira-api.sh:33` — the documented no-auth cloud-ID helper is unusable**,
   because sourcing the file requires the email and API-token variables first.
   Repro: set only `JIRA_WORKSPACE`, source, call `jira_get_cloud_id`.
6. **`jira-api.sh:31` — sourcing permanently enables `nounset` and `pipefail` in
   the CALLER's shell.** A helper meant to be sourced must not change the shell
   it is sourced into. Repro: source it in a shell with `set +u`, then expand an
   unset variable.
7. **`jira-api.sh:124` — mutation helpers return success and print completion
   text on 4xx/5xx.** Repro: edit or delete a nonexistent issue, check `$?`.
   This is the "fails open while looking like it worked" shape this repo keeps
   paying for.
8. **`jira-api.sh:131` — account-search values are not URL-encoded**, so any
   name with a space fails lookup. Repro: `jira_find_account_id "Jane Doe"`.

## Ticket B: `docs.theme` has no consumer, and its default is silently overridden

Raised 2026-09-12 by team-lead, who measured it correctly: `docs.theme` and
`docs.reportTheme` are settable in BOTH config layers and six files in
`plugin/crew` mention them -- two templates, two tests, `crew_upgrade.py` and
`crew-setup/SKILL.md`. Every one is a template, a test or a migration. **No code
in crew consumes either key.** Confirmed independently here with the same grep.

Two premises in the original report need correcting before anyone works this,
because both would send the work in the wrong direction.

**1. A resolver already exists, and it is good.**
`skills/doc-builder/scripts/resolve_brand.py` (with
`scripts/_test/test_resolve_brand.py`) resolves a brand-pack name through a
five-step order -- `--brand`, `DOC_BUILDER_BRAND`, sibling skill directories,
the plugin cache, then neutral -- and announces which step matched. The
fall-through to neutral is announced LOUDLY and names every location searched,
which is most of the "skill not installed" degraded path the ticket asks for.
So the work is NOT "write a resolver". It is narrower: **crew stores a theme
name and never passes it to the resolver that already exists.** The wiring is
the ticket.

**2. The two brand-pack layouts are deliberate, not an inconsistency.**
The report warned that a resolver assuming one uniform layout "will find
`neutral` and miss `solomon`". It is the other way round, and by design. Every
discovery glob is `<skill>/assets/brand.json` -- the FLAT shape, which is what
`solomon-doc-builder/assets/brand.json` has. The nested
`doc-builder/assets/brands/neutral/brand.json` is excluded from discovery on
purpose (`_is_own`) because neutral is the built-in fallback rather than a
discovered pack. Verified by running it: `--list` reports `neutral (built in)`
and finds `solomon` under sibling skills.

**The actual defect, found by running the resolver rather than reading it.**
With both skills installed and no `--brand`, resolution prints:

```
brand: solomon -- the only brand pack found in sibling skill directories
```

Neutral is not a candidate, so "the only pack found" is solomon and there is no
ambiguity to stop on. A user whose crew config says `docs.theme: "neutral"` --
the shipped default, which `/crew:config --show` will print back to them -- gets
**solomon-branded documents**. That is one client's footer on another client's
report, which is the exact failure `resolve_brand.py`'s own docstring says its
ambiguity check exists to prevent. It happens only because the key has no
consumer, so the check never sees the user's stated answer.

So this is worse than a key that quietly does nothing. It is a key whose
documented default is actively contradicted by whatever pack happens to be
installed, while the config UI reports the default as being in effect.

**The wrong brand is also a partly broken one, which misdirects the diagnosis.**
Confirmed on this machine and reproduced independently by team-lead: solomon's
pack resolves `masters_dir` to `C:/repos/OnboardingSOPs/sops_new`, and the
script prints it as `(NOT FOUND on this machine)`. So a user who never chose
solomon gets a brand whose template directory does not exist, and the first
failure they hit is a MISSING TEMPLATE rather than a wrong footer. That points
the diagnosis at doc-builder's assets, or at their own checkout, and away from
branding entirely -- which is where the actual defect is. A wrong answer that
fails in an unrelated-looking way costs more than one that fails plainly.

`--list` makes the same point: `neutral` is shown, labelled `(built in)`. It is
VISIBLE and still not a candidate, so nothing reads as missing and no ambiguity
stop fires. Everything looks correct from the outside.

**Acceptance criterion for this ticket:** an unresolvable or unset theme must
not fall through to "whatever happens to be installed". Fail loud, or fall back
to neutral and say so, the way the resolver already does for a genuinely missing
pack.

Repro, both halves:

```
python skills/doc-builder/scripts/resolve_brand.py            # -> solomon
python skills/doc-builder/scripts/resolve_brand.py --brand neutral  # -> neutral
```

Scope when this is picked up: pass `docs.theme` through to `--brand` /
`DOC_BUILDER_BRAND`, and decide what an unresolvable theme name does. It must
NOT fall through to "whatever is installed" -- that is the bug above. Fail loud
or fall back to neutral and say so, the way the resolver already does for a
missing pack.

### Design settled 2026-09-12: crew passes the name through, it resolves nothing

Crew reads the merged `docs.theme` and passes `--brand <name>`; `docs.reportTheme`
goes to the findings-report script. Two keys are implementable because the two
pipelines are separate scripts. Crew adds the one thing doc-builder lacks -- a
per-repo setting with a machine-global default, which neither a per-invocation
flag nor a machine-wide env var can express. Keep the layering and add nothing
else. Do NOT write a second resolver.

**The refusal is real, and it is narrower than it sounds. Measured, not read.**
With two discovered packs the resolver exits 1 and names them:

```
$ DOC_BUILDER_SKILLS_DIR=<two packs> resolve_brand.py
More than one brand pack is installed (...): alpha, beta.
Pass --brand <name> (or set DOC_BUILDER_BRAND) to say which one this document is for.
exit=1
```

With exactly ONE discovered pack it returns that pack silently, exit 0. `neutral`
is never a discovery candidate, so this repo -- doc-builder plus
solomon-doc-builder -- is the one-pack case. **The refusal therefore does not
protect the common configuration**, which is a single client brand installed.
That is not an argument against pass-through; it is the argument FOR it, because
pass-through is what creates protection in exactly the case the refusal leaves
open.

**`docs.theme` does NOT ship as `null`. It ships as `"neutral"`.** Verified in
all three places that define it -- `crew_upgrade.DOCS_BLOCK` (`theme: "neutral"`,
`reportTheme: None`) and both templates. Only `reportTheme` is null. The design
note that "both are null in the templates today" is wrong on the half that
matters, and building on it would ship a behaviour change nobody chose:

- Under pass-through with the default untouched, every repo passes
  `--brand neutral`. That is an explicit instruction, so it **overrides an
  installed client pack**. Today that pack wins; afterwards neutral would.
  Upgrading crew would silently DE-BRAND an existing Solomon user's documents,
  and the config file would not have changed to explain it.
- `null` meaning "pass no `--brand`, let doc-builder resolve" is the right
  semantic, and it preserves the refusal exactly -- but today it only describes
  `reportTheme`.

**The `null` default cost a MANDATORY migration, and that is coupled to the
(a)/(b)/(c) decision below.** `run()` returns "already current" for any config
at or above `SCHEMA_CURRENT` and never calls `upgrade_config`, so the rewrite
reaches an existing repo only if the schema is bumped. It went 3 -> 4. That
makes every crew repo on every machine report `upgradeNeeded` at session start
until someone runs `/crew:upgrade`, which also backs up the codemap and
reconciles it -- a whole-population migration spent on a key that has never done
anything. Correct groundwork under (a) or (c); under (b) it is two mandatory
migrations back to back, 4 to add a default nobody can observe and 5 to remove
it. Take the merge and the scoping decision together. Commit `69c4a9fe` -- the
two false doc claims -- is separable, needs only a patch bump, and is true under
all three.

**RATIFIED AND SHIPPED 2026-09-12, crew 0.18.0: option 2, `theme: null`, with
the migration.** Team-lead took the recommendation and resolved the cost rather
than accepting it. The migration ambiguity I raised -- telling a deliberately
typed `neutral` from a template-inherited one -- dissolves, and the reason is
worth keeping: **`docs.theme` has never had a consumer**, so no user has ever
been able to set it and observe an effect, so no existing value can encode a
considered preference. It is inherited or it is inert. There is no third case to
preserve, which is why rewriting is safe here and would not be for any key that
ever worked. That sentence is now in the migration's own comment, because the
next reader will meet it expecting the usual rule and needs to see why this is
the documented exception rather than a violation of it.

Residual cost, accepted and stated in the release note: someone who typed
`"neutral"` meaning it retypes it once the key works. They get neutral anyway
unless a pack is installed, so the window is narrow.

The original framing of the two options is kept below, because the reasoning is
what justifies the migration comment.

So the ticket carries a decision, and the recommendation is the second option:

1. Keep `theme: "neutral"`. Predictable, and the config then means what it says
   -- but the first upgrade silently stops applying an installed brand pack.
2. **(Recommended)** Ship `theme: null` and treat null as "pass no `--brand`".
   Pass-through then only ever NARROWS from doc-builder's own behaviour, the
   upgrade is a no-op for every existing user, and pinning a brand becomes an
   opt-in the user performs deliberately. Cost: the migration has to move an
   existing `"neutral"` forward, and `"neutral"` typed deliberately must stay
   distinguishable from `"neutral"` inherited from a template nobody edited --
   which is why this is a decision and not a default.

Degraded path: use what exists. `resolve_brand.py` already reports what would be
used and why, and `--list` enumerates visible packs. Do not invent separate
detection. It must degrade rather than throw when doc-builder is not installed
at all -- a second code path, and it needs its own test.

**The refusal is not a guard pass-through must avoid defeating -- it is a guard
pass-through EXTENDS.** Team-lead adopted this framing over their own after the
measurement above: the refuse-to-guess behaviour fires only at two or more
discovered packs, `neutral` is never a discovery candidate, so the ordinary
configuration -- one client pack installed -- is the one-pack case where the
refusal never fires at all. Pass-through is therefore not a risk to an existing
safety property; it is the safety property for exactly the case the existing one
leaves open. Use this framing, not "must not defeat the refusal".

**Does `solomon-doc-builder` need a crew reference once this lands? No, and 0 is
the correct final number.** Pass-through means crew hands over a NAME and
doc-builder discovers the pack; crew never has to know that `solomon` exists.
Adding a reference would hardcode one client's name into a general-purpose
plugin, which is the coupling pass-through exists to avoid. So its 0 is correct
for a different reason than `report-builder`'s 0 -- that one is a deprecated
stub, this one is a plugin that is correctly ignorant of its clients. Neither
should be "fixed" to make a count look better.

### Blocker found 2026-09-12: there is no call site, and the routing table names a different tool

Measured before writing any wiring, and it changes the ticket's size. Both
findings below are about crew as it ships at 0.17.0.

**1. No crew agent or command invokes doc-builder.** Grepping `plugin/crew` for
`doc-builder`, `DOC_BUILDER`, `resolve_brand` and `--brand`, outside tests, returns
FOUR files and not one of them is an invocation: `crew_config.py:383` (a help
string naming the key), `crew_upgrade.py` (the migration block and its comment),
and `crew-setup/SKILL.md` (the setup doc). `agents/docs-writer.md:49` says a
document "ships as HTML, DOCX or PDF" and names no tool at all. So "pass the
configured name through as `--brand`" has nothing to pass it FROM. Pass-through
is still the right design; it just has no attachment point yet, and building one
is a larger change than wiring an existing one.

**2. Crew's document routing table exists, and doc-builder is not in it.**
`plugin/crew/skills/crew-house-style/SKILL.md:63-70` is the "Generating it"
section, and it is explicit -- "Route to the skill that owns the format. Do not
reimplement any of them" -- then routes DOCX to `anthropic-office-skills:docx`,
PDF to `anthropic-office-skills:pdf`, decks to `anthropic-office-skills:pptx` or
`ppt-master`, and `.vsdx` to `visio-diagrams`. **doc-builder appears nowhere.**

That is the real mismatch, and it is bigger than a missing call site.
`docs.theme` names a doc-builder brand pack, while crew's own documented
generation path goes to a tool that has no brand packs and would not know what to
do with the name. Wiring `--brand` into the route that exists is not possible,
because that route does not lead to doc-builder. So the ticket implies one of
three decisions, and this is a scoping question for whoever owns crew's document
story rather than something to settle inside a wiring ticket:

- **(a)** Add doc-builder to the house-style routing table as the owner of
  branded DOCX/PDF, and pass `--brand` there. Largest change: it edits crew's
  documented generation policy, not just a config key.
- **(b)** Leave the routing table alone and drop `docs.theme` / `docs.reportTheme`
  entirely, since crew does not use the tool they configure. Smallest change, and
  honest -- but it discards a setting someone wanted.
- **(c)** Keep the keys, keep them inert, and say so everywhere they appear.
  Already done as of this branch's first commit, which is why the two false
  present-tense claims are now corrected. This is the current state, and it is a
  stopping point rather than a fix.

**The degraded path the ticket asks for is already written, three lines below the
routing table.** `crew-house-style/SKILL.md:74-80` tells the crew that these are
user- and plugin-level skills crew does not bundle, that the one you want may be
missing, and to hand over the markdown saying "PDF export unavailable,
`anthropic-office-skills:pdf` is not installed" rather than improvising a
generator. Whatever lands for doc-builder should match that sentence shape rather
than invent a second convention.

**Corrected on this branch already (commit 1 of B):** `crew_upgrade.py:71` and
`crew-setup/SKILL.md:201` both described the pass-through in the PRESENT TENSE,
and both justified the `"neutral"` default with "the default resolves to exactly
what doc-builder already falls back to" -- which is false, as measured above:
doc-builder falls back to neutral only when no pack is discovered, and returns
the installed pack otherwise. That false premise is the entire stated reason the
default is `"neutral"` rather than `null`, so correcting it strengthens the
`theme: null` recommendation from a preference to a correction: the author's own
stated intent was "the default changes nothing about how documents come out
today", and `null` is what implements that intent while `"neutral"` overrides an
installed pack. Each key's `null` then means one thing -- "I have no answer, ask
the next authority" -- which for `reportTheme` is `theme` and for `theme` is
doc-builder's own resolution. One rule, not two.

**`report-builder`'s 0 references are correct, not a gap.** Its SKILL.md
declares it a deprecated stub as of 2026-09-10, superseded by `doc-builder`, and
its 2.0.0 catalog entry already says so. An earlier concern of mine that the
entry misdescribed the skill was unfounded -- team-lead checked and I am
recording the correction here so nobody re-opens it. `solomon-doc-builder` also
has 0 references in `plugin/crew`; that one IS the gap above, since it is the
pack the theme key is supposed to select. For contrast, `doc-builder` has 3 and
`bitbucket` has 8.

## A raw `Agent` dispatch writes no record, so crew misreports its own authorship

Found 2026-09-11, during the bitbucket merge-gate work. Belongs with the ticket C
/ D config work, not chased on its own.

`.work/dispatch.d/` holds exactly one record on this branch — a `developer` from
2026-09-06, made on `main`. Six roles were dispatched on `bitbucket-merge-gate`
in this session and not one of them was recorded, because the recorder fires on
crew's own command paths and a bare `Agent` tool call is not one of them.

The consequence is not a missing log line. `crew_state.py` and
`crew_config.py --models` read that store to answer "who wrote this diff", and
with a record that predates the merge-base they correctly report:

```
author family: claude  (STALE RECORD - the dispatch was made on a different
branch, so BOTH the recorded family and the config family are struck)
last dev dispatch: role=developer provider=claude model=None branch=main |
current branch=bitbucket-merge-gate
```

That is the guard failing *safe* — striking both families costs a reviewer rung
rather than clearing one wrongly — so nothing shipped unreviewed. But it fails
safe by accident: the store is not empty-and-honest, it is stale-and-confident,
and the guard only survives because the staleness check happens to catch it. A
record from a dispatch made on THIS branch would read as fresh and authoritative
while describing none of the work under review. That is the same class as
`crew_config.py --models` deriving author family from config describing the next
run — an unknown wearing the label of a check that happened.

Two candidate fixes, neither chosen: have the `Agent` path write a record, or
have the readers treat "no record for any commit in this range" as its own value
distinct from a stale one. The second is the one that matches this repo's
standing rule that a probe which can fail needs "could not tell" as a real value.

Re-measure before acting: `ls .work/dispatch.d/` and
`python3 <crew>/hooks/scripts/crew_config.py --root . --models`.

**Narrowed 2026-09-12, on the ticket C/D branch, where this was folded in as
instructed.** The choice between the two candidate fixes is no longer open, and
it was settled by what is reachable rather than by preference: **the first is
not implementable from inside crew.** The `Agent` tool is supplied by the
harness, not by the plugin; crew registers `PreToolUse`, `Stop`, `PreCompact`
and `SessionStart` hooks and none of them can interpose on a bare `Agent` call
to write a record for it. So "have the `Agent` path write a record" is a change
to Claude Code, not to this repo, and listing it as an option here reads as a
choice somebody could take.

That leaves the reader-side fix, which is also the one this repo's standing rule
already points at: **"no record covers any commit in this range" must be its own
value, distinct from "a record exists and is older than the range".** Today both
collapse into `STALE RECORD`, which is why the current behaviour is
stale-and-confident rather than empty-and-honest. Not done on this branch -- it
is a change to the author-family guard, and C/D were an authority and config
change; mixing them would have put a guard edit inside a release whose test
matrix is about something else.

**A second defect, found while running the suite for C/D.** Two tests in
`plugin/crew/tests/test_provider_table.py` call `crew_state.author_families(".")`
-- a literal `"."`, so they read whatever dispatch store is in the CURRENT
WORKING DIRECTORY rather than a fixture:

- `test_an_unset_copilot_model_is_not_barred_against_another_unset_one`
- `test_author_family_honours_a_per_role_dev_pin_over_the_block_default`

Both pass in a CLEAN checkout and both fail on any developer machine that has
ever used crew here, because `.work/` is gitignored and therefore absent from a
fresh clone but present locally. Measured rather than inferred: a worktree at
`7a234ba0` passes 124/124, and the same worktree with this repo's real
`.work/dispatch.json` and `.work/dispatch.d/` copied in fails exactly these two.

Say "clean checkout", not "CI". **CI does not currently run these tests at
all** -- the `Pytest (crew + gizmoduck plugins)` job collects 954 items and dies
on 12 gizmoduck `ImportError`s before executing one of them, so its log reports
neither test by name. An earlier draft of this entry said "both pass in CI",
which is an overclaim of exactly the kind this file exists to stop: it cites a
green signal that was never produced. The clean-worktree run is the real
evidence, and it is enough.

So this is environmental and pre-existing, not from the C/D branch -- but it
means the local suite is not the suite a clean checkout runs, and a developer
who sees these two red learns to ignore red. Fix belongs with the reader-side work above, since it is
the same store: pass a `tmp_path` root like the neighbouring tests do.

**FIXED 2026-09-12 on `crew-docbuilder-route` (crew 0.19.2).** Both now take
`tmp_path`. Swept the suite for the same shape: the only other literal `"."` is
an unrelated branch-name fixture. Note which half was wrong -- the tests were
right about the code and wrong about the world, so the green they produced on a
clean machine was exactly as untrustworthy as the red they produced here. The
reader-side fix above ("no record covers this range" as its own value) is
untouched and still open; this entry closes only the fixture bug.

## No claim of the form "CI proves X" is available for any crew or gizmoduck test

Recorded 2026-09-12 so the four ticketed failures above and below are read
correctly. The `Pytest (crew + gizmoduck plugins)` job collects 954 items and
dies on 12 gizmoduck `ImportError`s before executing one of them. It therefore
reports NO test by name, passing or failing.

The consequence is easy to state and easy to forget: **until those imports are
fixed, "CI is green on this test" is not a sentence anyone can say about
anything in that job.** The only evidence available is a local run, and the only
honest phrasing is "clean checkout" or "local, at <ref>". An earlier entry here
said two tests "pass in CI"; they do not, because nothing in that job passes or
fails -- it never runs. Corrected, and recorded here rather than only at the
entry, because the trap is general.

The jobs that DO produce usable signal are `Marketplace` (`check`) and the
`test (ubuntu-latest)` / `test (windows-latest)` pair. Cite those freely.

### Root-caused and fixed 2026-09-12: PyYAML was never installed

Diagnosed by team-lead from run 34701704505 and confirmed here by reproducing
it: `ModuleNotFoundError: No module named 'yaml'`.
`.github/workflows/pytest-crew.yml` installed only `pytest~=8.0`, while
`plugin/gizmoduck/scripts/routine.py` and `scripts/scanners/zap.py` both import
yaml and the tests pull them in transitively. Collection dies, and ONE
interrupted collection takes the whole job down -- so crew's tests never ran
either, on any of 3.11, 3.12 and 3.13.

Reproduced locally by blocking the yaml import rather than by reading the log:
same 12 collection errors, exactly. With `pyyaml` installed the same command
runs **1282 passed, 4 failed, 1 skipped**, and the 4 are the already-ticketed
stale ones below. So the job goes from useless to red-that-runs.

The comment at `:25-29` asserted gizmoduck's suite was "stdlib-only subprocess
tests, no extra install step needed". That was false and it is exactly what
would have stopped the next person adding the dependency, so it is rewritten
rather than merely supplemented.

### Still open: the job reports crew's failures under gizmoduck's path

Found while verifying the above, NOT fixed, because fixing it changes what the
job collects and that deserves its own look. In the combined run all four crew
failures are printed as `plugin/gizmoduck/test_provider_table.py` and
`plugin/gizmoduck/test_role_ladder.py` -- files that do not exist. Neither
test is gizmoduck's.

The cause is `plugin/gizmoduck/pytest.ini`. With two args whose common ancestor
is `plugin/`, pytest finds no config there and falls back to searching each
arg's ancestors, hitting gizmoduck's ini and adopting `plugin/gizmoduck` as
rootdir -- so every path is rendered relative to it. Its `addopts = -q` is also
silently applied to the whole run.

**Correction, same day, by running the workflow's command verbatim rather than
an approximation of it.** This entry claimed `-q` is "why the job's output has
no header line naming the rootdir". That is false about the job: the workflow
runs `pytest ... -v`, the command line is applied after `addopts`, so `-v` wins
and the header IS printed -- `rootdir: .../plugin/gizmoduck`, naming the cause
outright. The header was missing from MY simulations, which omitted `-v`; I
then attributed my own missing header to the job. The rootdir misattribution is
real and unchanged; only the explanation of why nobody noticed was wrong, and
it was wrong in the direction that makes the CI log look less informative than
it is.

**The trap in fixing it:** that same ini supplies `pythonpath = scripts`, and
gizmoduck's tests may depend on it. Adding a repo-root pytest config would take
the ini out of play and could break them for a reason unrelated to the change.
Splitting the workflow into two steps (with `if: always()`) keeps each suite
under its own rootdir and is the likelier right answer, but it must be verified
by running, not reasoned about. Until then a CI reader looking up a gizmoduck
path will find nothing there, which is the same misdiagnosis shape as the
`PSModulePath` and Exchange-module traps.

With the four failures below now fixed, the combined run is **1286 passed, 1
skipped, 0 failed**, so there are no misattributed paths to look at at the
moment. That makes this cheaper to leave open and easier to forget: the next
failure in either suite is the one that gets misfiled.

## Nothing checks that shipped prose states the right version

Recorded 2026-09-12, on `crew-docbuilder-route`. Team-lead's finding, and it is
sharper than the bug that produced it.

`validate-prompts.py` returned **293 passed, 0 failed** and the hook suite
**134 passed, 0 failed** while two stale schema numbers sat in command prose; a
sweep then found four more, including `README.md` calling the current schema 2
in three places, one of them the settings table. Both gates were green
throughout. They check structure -- frontmatter, required sections, referenced
files -- and nothing at all about whether a sentence stating a version states
the current one.

So: **a green prompt-validation run is not evidence that shipped documentation
matches the code.** Right now nothing produces that evidence.

The `pm_brief` `upgradeNeeded` message is the same class and shows the cost.
It asserted "config has no schema" for every repo; bumping `SCHEMA_CURRENT` to
4 aimed that at the entire installed population, in the trigger that sorts
third and therefore leads the brief. Not one gate moved. It was caught by a
person reading the file.

A checkable rule exists for at least the schema case, because `SCHEMA_CURRENT`
is a single constant: any prose naming a schema number could be checked against
it. `plugin/crew/tests/test_pm_brief.py::test_the_brief_and_upgrade_md_agree_on_the_current_migration`
is the first instance of that idea -- it fails if a future bump ships without
its `commands/upgrade.md` section 5 entry -- but it covers exactly one pair of
files. The general sweep is not written.

## The sabotage harness could not restore twice on 2026-09-12, and left a live mutation each time

Found while adding the five `upgradeNeeded` mutations. Both runs died with:

```
OSError: [WinError 1224] The requested operation cannot be performed on a file
with a user-mapped section open
WARNING: could not restore .../crew_state.py: [WinError 1224] ...
```

once at mutation 46 on `crew_state.py` and once at mutation 15 on
`crew_upgrade.py`. The third run of the same suite passed 103/103. So it is
intermittent, and the cause was not identified -- something on this machine
transiently holds a mapped section on a just-written `.py`, which on Windows is
what a scanner does immediately after a write.

**The harness's own design is what made this safe, and it is worth saying which
part.** The `.bak` was the good copy both times, the startup guard refuses to
run while one exists, and the file left in the tree was verifiably the mutated
one -- `git diff` showed a mutation nobody wrote. Recovery was `cp` the `.bak`
over the target and delete it, then confirm against `git diff`. Do NOT delete a
`.bak` without diffing it against the target first: the target is the corrupt
side, not the backup.

### The fix, and the ACCEPTANCE CONDITION it does not ship without

`shutil.copy2` has no retry. A transient sharing violation is exactly the
failure a short backoff absorbs, and absorbing it would turn a crashed run that
leaves a live mutation into a slightly slower clean one. Not done here: it is a
change to the safety mechanism itself, and that branch was a docs-routing
release.

**REQUIREMENT on whoever takes this, not advice.** The retry is not finished
until the copy has been made to fail on purpose and the retry has been watched
absorb it. A passing sabotage suite is NOT evidence the retry works -- the
suite passes when no copy fails, which is the ordinary case and was the case
on two of three runs the day this was found. Ship it on a green suite alone
and the retry is untested code in the one path that exists to prevent a
corrupted tree.

That is not a general caution; it is this exact defect class, and it has now
cost time here five times in one week -- the schema-3 migration that was dead
on arrival, the `PSModulePath` scrub, the `grep`-killed harness, the
`find_module` import blocker that blocked nothing, and a claim in this very
file that `addopts = -q` hid a CI header the job in fact prints. Each looked
live and was not, and each was caught by running the mechanism rather than
reading it. A retry loop is an unusually good hiding place for the same shape,
because the happy path exercises none of it.

Concretely: make `shutil.copy2` raise `OSError` on its first call or two (patch
it, or hold a real mapped section on the target), confirm the run completes and
the tree is clean afterwards, and confirm an error that does NOT clear still
surfaces as a failure rather than being swallowed by the loop.

## The specialist role tables disagree with the code, on `main`

Found 2026-09-12, running the full crew suite for the C/D branch. Pre-existing:
`plugin/crew/tests/test_role_ladder.py` fails these two at `7a234ba0` itself,
before any of this branch's commits.

```
FAILED test_onboarding_specialist_table_matches_the_code_set
FAILED test_the_readme_roster_table_matches_the_code
```

`crew_state.SPECIALIST_ROLES` names four roles that neither the onboarding table
nor the README roster lists: `powershell-7-expert`, `powershell-5.1-expert`,
`skill-author`, `exchange-online-specialist`. The code is the side with more, so
these are roles that exist and are undiscoverable rather than documented roles
that vanished -- a reader of either table cannot learn they can onboard them.

Belongs with ticket B (the crew referencing work), which is already about crew's
tables disagreeing with what is installed. Not fixed here on scope discipline:
C/D was an authority and config change, and these two suites were red before it
started and are equally red after.

**FIXED 2026-09-12 on `crew-docbuilder-route` (crew 0.19.2)**, which is where
ticket B landed. All four rows added to both `plugin/crew/README.md` and
`plugin/crew/skills/crew-pm/onboarding.md`, written from each agent's own
frontmatter description rather than invented. The tables were telling the truth
and the code was the side with more, exactly as this entry read it.

## RESOLVED 2026-09-12 — Five marketplace entries are shipping stale (inherited, not from this branch)

**All five are bumped and the gate is green.** Closed rather than deleted: the
table below is what "shipping stale" looked like, and rediscovering that costs
more than the space it takes. The evidence that closed it:

| Entry | Was | Now |
|---|---|---|
| `skills/exchange-mailbox-cleanup` | 1.0.0 | **1.0.2** |
| `skills/exchange-mailbox-restore` | 1.0.1 | **1.0.2** |
| `skills/jira-manager` | 1.0.0 | **1.0.1** |
| `skills/power-automate-api` | 1.0.0 | **1.0.2** |
| `plugin/gizmoduck` | 0.2.5 | **0.4.0** |

Measured the way the entry itself asks for — on a named ref, not a working tree.
`git worktree add --detach <tmp> origin/main`, then `python3
scripts/check-marketplace.py` in that worktree: **"all checks passed", exit 0**,
with zero drift reported. The worktree matters: run against a `git archive`
export the checker prints "note: not a git checkout - skipping the version-drift
check" and passes without testing the thing at issue, so a green result there
would have meant nothing.

A caution earned the same day, recorded because it nearly landed in a PR body:
this checker was reported as "already red on `main`" during the pylint work, and
it was not. The red came from uncommitted edits in the working tree of the
machine running it. A checker result without its ref is not a measurement.

The original entry follows, unchanged.

---


Found 2026-09-11 while running `python3 scripts/check-marketplace.py` as the gate
for the bitbucket merge-gate work. The gate reported **6 problems, 0 of them
introduced by branch `bitbucket-merge-gate`**; `plugin/crew` was the one that
branch owed and it has since been bumped, leaving **5**. Each is a directory that changed
after its `version` was last set, so `claude plugin update` compares the declared
version, finds no change, and every already-installed copy reports "already at
the latest version" forever. Nothing in the repo looks wrong; the bug exists only
on other people's machines.

Measured per entry as `git log --oneline <sha-version-was-set>..origin/main --
<dir>` — all six are already red on `origin/main`, so none of this is caused by
uncommitted work:

| Entry | Version | Set at | Commits on `origin/main` since |
|---|---|---|---|
| `skills/exchange-mailbox-cleanup` | 1.0.0 | `b678e3cf` | 4 |
| `skills/exchange-mailbox-restore` | 1.0.1 | `b678e3cf` | 1 |
| `skills/jira-manager` | 1.0.0 | `ee9fcc2e` | 3 |
| `skills/power-automate-api` | 1.0.0 | `ee9fcc2e` | 3 |
| `plugin/gizmoduck` | 0.2.5 | `9338e89d` | 76 |
| ~~`plugin/crew`~~ | ~~0.16.33~~ | ~~`a1363e48`~~ | ~~5~~ — **fixed, now 0.16.34** |

Deferred rather than fixed, for two different reasons:

- The five above touch nothing this branch changed, so bumping them here is scope
  creep — and each bump pushes a plugin update to every machine that installed
  it, which is a shipping decision, not a lint fix. They need the user's call on
  whether to bump all five in one housekeeping commit or leave them.
- `plugin/crew` was the exception: commits `089af55e` and `f8bdb25e` on this
  branch touch five files under `plugin/crew/`, so that bump **was** owed by this
  branch, and it landed in the branch's final commit at 0.16.34 — both
  `.claude-plugin/marketplace.json` and `plugin/crew/.claude-plugin/plugin.json`,
  which must always match.

Re-measure before acting. These counts are facts about `origin/main` at
`bd4d125a`, and the gate is the only thing that tracks them.

### Not ticketed, decided instead

The review's one BLOCK — a real tenant snapshot committed under
`skills/power-automate-api/scripts/pa-snapshots/` and pushed to this public
repo — was raised with the user on 2026-09-08. They chose to leave what is
already published and stop it recurring: the file is untracked and
`skills/power-automate-api/.gitignore` now ignores the whole snapshot
directory. Nothing was rewritten or force-pushed. Recorded here because "we
decided not to" is the half that otherwise gets rediscovered as a new finding.

## The crew suite and the marketplace checker need contradictory shells on Windows

Filed 2026-09-13 against `main` at `819bf382`. Three findings, all reproduced
here rather than relayed; the first two are one problem seen from two ends.

### 1. ~~Under PowerShell the crew suite runs against WSL bash and 52 tests fail~~ — CLOSED 2026-09-13 (crew 0.19.28)

**CLOSED.** `crew_fixtures.resolve_bash()` now PROVES a candidate by running a
probe script at a Windows path and checking a sentinel exit code, so "found" is
no longer mistaken for "working". It returns None when nothing works, and the
`sh` flavour is then SKIPPED with a printed reason instead of parametrized in to
fail.

The logic lived copied in SIX test modules, and a seventh (`test_auto_clear.py`)
had a bare `shutil.which` with no resolver at all. That seventh is why the first
pass still left 16 failures, and it is the check-the-neighbouring-case lesson
arriving on schedule. Measured under PowerShell: **52 failures -> 0**. The `sh`
flavour is not skipped there but RESOLVED, to `C:\Program Files\Git\bin\bash.exe`.
1411 passed under Git Bash and under PowerShell.

**`### 2` below is NOT reopened by this.** The fix resolves the interpreter
rather than prepending Git's `bin` to `PATH`, so `git` is untouched and the
`check-marketplace.py` hang is not reintroduced. That entry stays open.

`plugin/crew/tests/test_context_watch.py:40` resolves the shell with
`shutil.which("bash")`. Under PowerShell that returns
`C:\WINDOWS\system32\bash.EXE` -- WSL, measured here, not inferred. WSL bash
cannot open a Windows path, so every script it is handed exits 127 and the
assertions read `assert 127 == 2`.

52 tests fail that way: `test_context_watch.py` (27), `test_auto_clear.py` (16),
`test_verify_gate_lock_sh.py` (7), `test_verify_gate_lock_concurrent.py` (2).
The same suite under Git Bash: 931 passed.

`_resolve_bash` (`:27-51`) already knows Git for Windows ships two bashes and
upgrades `usr/bin/bash.exe` to the `bin/` shim -- but only when the resolved
path contains both `usr` and `bin` (`:45`). `C:\WINDOWS\system32\bash.EXE`
contains neither, so it is used as found.

**The defect is not the wrong path, it is that `_HAS_BASH` is then `True`.**
`:53-57` treats "a bash was found" as "a working bash was found", so the `sh`
flavour is *parametrized in* and fails, where an honest "no usable bash" would
have skipped. That is this repo's recurring shape: an unknown collapsing into
the safe-looking value. Two agents independently hit it and both first reported
it as "pre-existing failures on `main`" -- a harness assumption wearing the
label of a regression, which is the expensive half.

### 2. The fix for #1 makes `scripts/check-marketplace.py` hang

Prepending `C:\Program Files\Git\bin` to `PATH` is what gives #1 a working
bash. It also moves `git` from `/mingw64/bin/git` to
`/c/Program Files/Git/bin/git`, and the checker -- which shells out to git at
`scripts/check-marketplace.py:36` and `:318` -- then never returns.

Reproduced here once at a 100s timeout (exit 124) after the agents reproduced
it twice at 120s; the same command exits 0 in seconds without the prepend. So
the two gates currently want opposite environments, and anyone who fixes one by
editing `PATH` breaks the other. Neither is fixed. What is needed is for
`_resolve_bash` to reject a non-MSYS bash outright rather than for callers to
launder `PATH`.

### 3. ~~`crew_upgrade.py` prints schema 3's added keys at the CLI and not schema 5's~~ — CLOSED 2026-09-13 (crew 0.19.28)

**CLOSED.** `main()` gained the missing branch and prints `installKeysAdded`
with its floor in the same breath -- the floor is the reassurance, and it only
reassures if it is said. Covered by
`test_the_cli_announces_the_new_key_and_does_not_only_write_it_to_a_file`, and
sabotage-verified: stubbing the branch to `if False` turns it red.

`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:845-850` prints
`providerKeysAdded`. There is no matching branch for `installKeysAdded`, which
schema 5 populates; the key reaches `.crew/codemap/UPGRADE.md` and never the
terminal.

Defensible on its own -- `install.policy` lands as `manual`, which is what crew
already did, so nothing changes behaviour. Recorded anyway because the block's
own comment at `:840-842` gives the rule it breaks: printed at the CLI "not only
buried in UPGRADE.md", for the things "a user must not learn about later". A new
key governing whether crew may run install commands is squarely in that class,
even at its floor. One `if` and a line of text.

**Not verified:** no fix is attempted for any of the three, and
`scripts/_test/drift-detection.sh` was not run for this entry.

## ~~Crew's graph-refresh string contradicts this repo's CLAUDE.md since #121~~ — CLOSED 2026-09-13 (crew 0.19.28)

**CLOSED for the pulse, and deliberately not by swapping the string.**
`_read_graph` now reports `reportTracked` -- whether `GRAPH_REPORT.md` beside
`graph.json` is TRACKED, asked of git rather than of the filesystem, because an
untracked report is a local artefact and does not make the pair something the
repo maintains. `pm_brief._graph_fields` turns that into `{graphCommand}`:
`graphify update .` where the report is tracked, `graphify . --no-viz
--code-only` where it is not, and the same where the answer is unknown -- the
older default, and the safe one on the majority case.

**The other three call sites named above are still fixed prose** --
`commands/onboard.md`, `commands/upgrade.md` and `crew-graph/SKILL.md` -- and
are the remaining half of this finding. They were out of scope for this change.

Filed 2026-09-13 against `main` at `af9995ed`. Recorded, not to be chased.

Four places in crew tell the user to refresh the graph with
`graphify . --no-viz --code-only`:

- `plugin/crew/hooks/scripts/pm_brief.py:148` (the pulse text, which is where
  this surfaced)
- `plugin/crew/commands/onboard.md:14` and `commands/upgrade.md:56`, both
  saying "both flags required"
- `plugin/crew/skills/crew-graph/SKILL.md:44`

Since #121 this repo's `CLAUDE.md` documents `graphify update .` instead,
because **this** repo tracks the pair `graphify-out/graph.json` +
`GRAPH_REPORT.md` and `update` is what keeps the two consistent. So crew's own
hook now instructs a command its host repo's CLAUDE.md tells you not to use.

**The obvious fix is the wrong one.** Swapping the string to `graphify update .`
would be correct here and wrong generally: crew ships to many repos, and
`--code-only` is right wherever `GRAPH_REPORT.md` is not tracked. The string is
not the bug -- crew recommending a fixed command regardless of how the host
repo stores its graph is. A real fix reads `graph.mode`, or detects a tracked
report beside `graph.json`, and says the command that matches what it found.

Cost if taken: four call sites plus whatever decides the command, and it lands
in crew, so it owes a bump and a CHANGELOG entry. Not costed further.

**Not verified:** no fix attempted, and no check of how many other repos on
this machine track the pair -- which is the number that decides whether the
detecting version is worth writing at all.

## ~~The Stop gate cannot see a committed change, and closing that is a design call~~ — CLOSED 2026-09-13 (crew 0.19.28)

**CLOSED. The design call was made rather than escalated.**

The baseline is now the last commit the gate itself verified
(`.crew/.verify-verified-at`, machine-local, written ONLY on a pass), falling
back to the merge-base with the default branch, falling back to HEAD.

The rejected alternative was a marker written at turn start by another hook. It
dates the turn precisely, but an absent marker degrades to the old behaviour,
and a gate that silently verifies less when its input is missing is this repo's
recurring bug. This baseline fails the other way: unknown means checking MORE.

**One narrowing survives, and it is asserted rather than hidden.** ON the
default branch with no marker yet there is no branch point -- merge-base(HEAD,
main) IS HEAD -- so a commit still ends that one turn. It lasts exactly one
turn, because the marker is written on every clean exit including the "nothing
changed" one.
`test_on_the_default_branch_with_no_marker_a_commit_still_ends_the_turn` records
it and tells its reader to delete it if the window is ever closed.

Both flavours changed. Nine cases in `plugin/crew/tests/test_verify_gate_baseline.py`,
sabotage-verified three ways: reverting the baseline to HEAD turns 4 red,
trusting an unresolvable marker turns 1 red, and writing the marker before the
checks run turns 1 red.

Filed 2026-09-13 against `main` at `a2e57ad9`. Found by the Rule of Two review
of `plugin/crew/` (Codex, D5) and reproduced here before filing.

`plugin/crew/hooks/scripts/verify-gate.sh:63` and `verify-gate.ps1:161` compute
the changed set as the working tree against `HEAD` plus untracked files. A
change that has been **committed** is therefore invisible to the gate, and
committing is sufficient to end a turn the gate would otherwise have blocked.

Reproduced with a rule mapping `**/*.py` to a command that exits 1:

| state of the same one-line `mod.py` | exit | verdict |
|---|---|---|
| uncommitted | 2 | BLOCKED, `VERIFY FAILED: python3 -c ...` |
| committed, nothing else changed | 0 | turn allowed to end |

**Not fixed here on purpose.** The gate has no notion of "this turn", and
giving it one means choosing a baseline, which changes behaviour in every repo
that has a gate:

- **merge-base with the default branch** -- correct for a feature branch,
  wrong on a long-lived branch where it would re-verify weeks of history every
  turn, and wrong on a repo that commits straight to `main`.
- **a marker written at turn start** -- precise, but SessionStart and Stop are
  different hooks and nothing currently pairs them; a missing marker would have
  to fail closed or the gate gains a new silent-skip of its own.
- **`@{u}..HEAD`** -- cheap, but meaningless before a first push and on any
  repo with no upstream.

None is obviously right, and the wrong one either annoys every user every turn
or quietly verifies less than today. Pick deliberately.

What was fixed is the documentation: `verify-gate.sh:63` now states the scope
in the file, because until today a reader could not tell this boundary from an
oversight, and a gate whose limits are unstated gets trusted past them.

**Not verified:** the `.ps1` twin was read, not executed, for this specific
behaviour; the bash reproduction above is the measured one.

## `plugin/crew/CONFIG.md` cites `crew_config.py` at lines that moved - 9 of the 11 checkable ones are wrong

Found 2026-09-13 at `a573ca24` while re-deriving the config data-flow diagram,
which had to resolve the same symbols and got different answers.

**Measured, not eyeballed.** A script AST-walked the four crew modules for every
`def`/`class`/module-level assignment, then matched every
`` `name` ... `<module>.py:<N>` `` pair in `plugin/crew/CONFIG.md`,
`plugin/crew/README.md`, `plugin/PLUGINS.md` and the root `README.md`. Eleven
citations name a symbol the walk can resolve. **Nine of them point at the wrong
line**, all in `CONFIG.md`, all into `crew_config.py` or `crew_state.py`:

| CONFIG.md | Symbol | Cited | Actually |
|---|---|---|---|
| `:29` | `read_global_config` | `crew_config.py:585` | `:666` |
| `:38` | `write_global_config` | `crew_config.py:1388` | `:1597` |
| `:43` | `resolve_config` | `crew_config.py:638` | `:719` |
| `:85` | `null_shadows` | `crew_config.py:448` | `:529` |
| `:90` | `_layer_supplies` | `crew_config.py:717` | `:863` |
| `:133` | `provider_problems` | `crew_config.py:611` | `:692` |
| `:193` | `leaf_paths` | `crew_config.py:432` | `:513` |
| `:283` | `normalise_granularity` | `crew_state.py:1220` | `:1365` |
| `:626` | `collect` | `crew_state.py:2727` | `:2888` |

**Why this is the expensive shape rather than a typo.** Every one of those lines
exists and holds real code. `crew_config.py:611` is `ignored.extend(dropped)`
inside `_prune`; `crew_config.py:717` is inside `resolve_config`. A reader who
follows the citation lands in the same file, in a plausible neighbourhood, and
has no signal that they are reading the wrong function. That is the repo's named
failure again - a wrong answer wearing the shape of a checked one - and it is
exactly what the codemap's own "12 were wrong, all in the files that grew" note
describes, one directory over.

**Scope beyond the eleven.** `CONFIG.md` carries **40** `<module>.py:<N>`
citations in total (21 `crew_config.py`, 9 `crew_state.py`, 6
`crew_platform.py`, 2 `pm_brief.py`, 2 `crew_incident.py`). The eleven above are
only those where a symbol name sits close enough to the citation for a script to
pair them. The other 29 name no resolvable symbol on the same line, so **nothing
here says they are right - only that this check could not look at them.** Assume
the same rate until someone measures it.

**Not fixed here, and the reason is mechanical.** `plugin/crew/CONFIG.md` is
inside a plugin directory, so touching it is a content change that needs a
`version` bump in both `.claude-plugin/marketplace.json` and
`plugin/crew/.claude-plugin/plugin.json`. This was found during a
documentation-only pass that deliberately touches no plugin directory. Fix it in
the next crew release.

**The durable fix is not re-pointing them.** Re-pointing lasts until the next
commit that grows `crew_config.py`, which is how these nine got here. Two options
worth weighing when it is picked up:

- Drop the line numbers from `CONFIG.md` and cite the symbol alone. The name is
  greppable and does not rot; the line number buys precision that survives about
  a week.
- Or add a checker: the AST walk above is roughly forty lines and could join
  `check-marketplace.py` as a tenth check. That turns "nine citations are wrong"
  into a CI failure the first time it happens rather than a discovery six
  releases later.

**Re-measure rather than trusting this table.** The nine figures are a fact about
`a573ca24`; every line number in the right-hand column moves whenever
`crew_config.py` does.

## `plugin/PLUGINS.md`'s catalog Version rows are checked by nothing

Found while fixing crew's row after #135 synced gizmoduck's and obsidian-vault's.
The row itself is fixed in this commit; the gap that let it rot is not.

`scripts/check-marketplace.py` cross-checks two of the three places a version
appears - `check_plugin_manifests` fails when a plugin's own `plugin.json`
disagrees with `.claude-plugin/marketplace.json` (`:155-163`). The third place,
the `| **Version** | x.y.z |` row in each `plugin/PLUGINS.md` catalog block, is
compared against neither. The string `PLUGINS.md` does not appear anywhere in
`check-marketplace.py`; the only thing that reads the file's neighbours is the
table-row link check at `:270`, and it asserts a link *exists*, never that a
number is right.

**Measured at `e1f14516`:** crew's row said `0.16.22`, set at `ac93221d` on
2026-09-06. The real version was `0.19.24`. **37 distinct crew versions shipped
in the seven days between**, with the gate green on every one. gizmoduck's was
three minors behind until #135. Only two of five rows were ever wrong at once,
which is why this reads as tidy rather than broken.

### Why this one is worse than an ordinary stale number

`PLUGINS.md` is the catalog a person reads to decide what to install and whether
they already have it. A row saying `0.16.22` beside an install command that
fetches `0.19.24` does not look stale - it looks like the version you are about
to get. Nothing on the page is marked as possibly-behind, so there is no cue to
re-check, and the number is *precise*, which reads as measured.

This is the shape the repo keeps paying for: not a missing value, but a wrong
one wearing the confidence of a checked one. The version-drift check at `:298`
exists precisely because "nothing in the repo looks wrong; the bug exists only
on other people's machines" - and it guards `marketplace.json` while the
human-facing catalog beside it is unguarded.

### The fix

One comparison, in `check_catalogs` or beside it: for each entry, parse the
`| **Version** | ... |` row inside that plugin's `PLUGINS.md` block and fail
when it differs from the entry's version. The data is already in hand - the
function receives `entries`, each carrying `name` and `version` - so this is a
parse of one file, not new plumbing.

Two things to get right, both learned from the checks already here:

- **Key on the block, not on the file.** `PLUGINS.md` holds five catalog blocks
  and the regex must bind a Version row to the heading above it, or a single
  correct row anywhere satisfies every plugin. The same failure shape as the
  `N skills` checker sketched in the entry above: a pattern that cannot tell
  which thing a number describes passes while wrong.
- **Editing `plugin/PLUGINS.md` does not bump anything, and must not.** The
  version-drift check at `:318-319` diffs `bump..HEAD -- <source>`, where
  `source` is `plugin/crew` for crew. `plugin/PLUGINS.md` sits one level above
  that path, so a catalog fix is correctly invisible to it - which is also why
  this commit carries no version bump, and why the row can rot for 37 releases
  without a single gate noticing.

**This is the third finding this week pointing at the same remedy** - the
`plugin/crew/CONFIG.md` citation entry and the `28 skills` entry reach it
independently. All three are "a claim about this repo, stated in prose, checked
by nothing". Worth deciding once whether `check-marketplace.py` grows a section
for that class rather than three tickets that each add one bespoke comparison.

**Re-measure rather than trusting this entry.** The 37 is a fact about
`e1f14516`; the five rows are right as of this commit and nothing keeps them
that way.

## The skills count was stale in five places, and one of them had a checker watching it

Fixed in this commit. Recorded because four of the five drifted the ordinary
way and the fifth did not, and the fifth is the interesting one.

**The marketplace holds 34 skills.** `34` is the `./skills/` prefix rule
`scripts/check-marketplace.py:396-397` uses.

| Site | Said | Fixed by |
|---|---|---|
| `README.md:51` | `28 of 28 skills` | hand edit |
| `README.md:151` | `all 28 skills in skills/` | hand edit |
| `INSTALLATION.md:18` | `28 of 28 skills` | hand edit |
| `INSTALLATION.md:44` | `the 28 skills in this repo` | hand edit |
| `skills/README.md:79` | `The 25 skills registered in ... are unchanged` | **deleting a duplicate generated block** |

`28` was correct on 2026-09-08, written at `ee9fcc2e`; `3dfd4265` on 09-09 was
the last commit where it really was 28. It went 28 -> 29 (`9e3fc6d1`) -> 34
(`a573ca24`). Four days of drift in numbers nothing checks.

### The fifth site is a different bug, and a worse one

`skills/README.md:79` was not an unchecked number. It sat inside a
`<!-- BEGIN skills/UPDATE.md -->` block, generated by `scripts/sync-updates.py`
from `skills/UPDATE.md` - and **that source was already correct**, reading
"Nine new skills, taking the marketplace from 25 to 34" at `skills/UPDATE.md:17`.
A generator whose whole job is to keep the two in step had been running, and
`--check` runs in CI at `.github/workflows/marketplace.yml:33`, and both were
green.

The cause: `skills/README.md` carried **two** `skills/UPDATE.md` marker pairs.
`splice()` located them with `text.find()`, which returns the FIRST of each, so
it rewrote the first block and never saw the second. The first block then
matched, `text != read(path)` was False, and the run printed `already current`
while a second block below it announced 25 skills. `--check` exited 0 on the
same reasoning. `mcp-servers/README.md` carried the same duplication, still
byte-identical and therefore harmless - armed but not yet fired.

So the fifth site is not "a claim nothing checks". It is **a claim a checker
looked at, approved, and was structurally unable to see** - which is strictly
worse, because the green `--check` in CI is affirmative evidence that somebody
verified it. This is the repo's named bug class with the safe-looking value
supplied by the guard itself.

`splice()` now refuses a duplicate pair outright (exit 2, the code its own
docstring reserves for "a structural problem the script will not paper over"),
and both duplicate blocks are deleted. The guard was confirmed by running it
against the live defect before the fix: exit 2 naming `skills/README.md`, then
exit 2 naming `mcp-servers/README.md` - a file this note's author had not
suspected and would not have checked.

### What this means for the marker-keyed count check

The planned `check-marketplace.py` self-consistency check keys on an explicit
marker beside each number, because a bare `N skills` regex cannot tell a
marketplace total from a plugin's own bundle - the same pattern scored 32
apparent hits and 0 real ones across this repo.

**That design would not have caught this site.** The marked number would live in
the canonical block, which was always correct; the stale duplicate would carry
its own marked number and go on lying, or carry none and be skipped. A checker
that verifies claims one at a time cannot see that a claim has been *copied* and
that only one copy is maintained. Structural duplication needs the structural
guard, which is why it lives in the generator rather than waiting for the
count check.

**Re-measure rather than trusting this entry.** `34` is a fact about this
commit and changes the next time a skill is registered.


## `pm_brief._graph_fields` reads a key `crew_state` never sets, so the graph command is always the fallback

**Resolved 2026-09-19** at `642be34a09d0668b144c25e9fe003930ba30b445` on branch
`crew-pmbrief-graphkey`. `pm_brief.py:298` now reads
`state.get("knowledge", {}).get("graph", {})` (via `dict_or_empty`, matching the
idiom already at `:313`), and the three fixtures below that put `graph` at the top
level are rebuilt to nest it under `knowledge`. A new test,
`test_real_collect_recommends_graphify_update_when_report_is_tracked`, drives the
real `crew_state.collect()` against a fixture repo rather than a hand-built dict, so
the fixture cannot drift from the emitter's shape again -- the exact gap this entry
names below. Sabotage-verified: reverting `:298` to `state.get("graph")` turns both
the rebuilt fixture test and the new collect()-driven test red, and the ORIGINAL
top-level-graph fixture (recovered from `dedd1150`) passes silently against that
same revert, confirming the finding below. Left the rest of this entry in place
rather than deleting it -- it is the record of how the bug was found.

Filed 2026-09-18 by the PM, on branch `crew-0.19.61-schema-readpath`, against
`main` at `7c5b884b`. **Does not block crew 0.19.61; not fixed here.**

`plugin/crew/hooks/scripts/pm_brief.py:298` reads `state.get("graph")`. The
state dict does not have `graph` at the top level -- `crew_state.collect()`
puts it at `state["knowledge"]["graph"]`. So `dict_or_empty` returns `{}`,
`tracked` is `None`, and `:301-302` always takes the `else` branch.

Measured in this repo, which tracks the pair:

    reportTracked: True
    graphCommand: {'graphCommand': 'graphify . --no-viz --code-only'}

The two lines disagree in one call. `reportTracked` is read correctly by
`crew_state`, and thrown away by the consumer.

**This is the entry above (`Crew's graph-refresh string contradicts this
repo's CLAUDE.md since #121`, CLOSED 2026-09-13) being wrong.** The fix
shipped, the detection works, and the interpolation has never once produced
`graphify update .` in a real repo. Do not re-close that entry on the strength
of the code reading the way it is meant to; run the two-line probe above.

**The test encodes the bug rather than catching it.**
`plugin/crew/tests/test_pm_brief.py:212-216` builds its state with
`_with("graphStale", graph={...})` -- `graph` at the TOP level, which is the
shape the buggy line reads and not the shape `crew_state.collect()` emits. So
the assertion `"graphify update ." in out` passes against a state no hook ever
sees. Fixing `pm_brief.py` alone will turn that test red; the test is half the
fix, and it is the half that decides whether this recurs.

**Cost:** one line in `pm_brief.py`, plus rebuilding the three cases in
`test_pm_brief.py` from `crew_state.collect()` output rather than a hand-built
dict. Lands in crew, so it owes a bump and a CHANGELOG entry.

**Why it is worth more than its size.** This is the repo's named recurring
defect exactly -- an unknown collapsing into the safe-looking value. The
fallback branch is documented at `:292-295` as the safe majority case, so a
reader who finds it taken concludes it was chosen, not that the probe came back
empty. A "could not tell" that renders as a confident recommendation.

**Not verified:** whether the same top-level-vs-nested mistake appears in the
other `_*_fields` helpers in `pm_brief.py`. `_incident_fields` shares the
contract and was not checked.

## `work.ticket` is an input to the pulse fingerprint, never a suppressor

Filed 2026-09-18 by the PM. **Does not block crew 0.19.61; not fixed here.**

`plugin/crew/hooks/scripts/pm_pulse.py:107` puts the open ticket into the state
fingerprint. Nothing anywhere suppresses the pulse while a ticket is open. The
fingerprint gate (`:93-112`) means the pulse does NOT fire every Stop -- the
common claim that it does is wrong, and `:12` says so: "the event is not the
gate; a STATE FINGERPRINT is." But `triggers` is also in the digest, so a graph
going stale or a diagram falling behind DURING a ticket changes the digest and
the pulse speaks the full finding list mid-task. That is a real vector for
work veering off the task in hand.

**Why it was not taken in the focus slice (crew 0.19.62).** `pm-pulse.sh` can
`exit 2` to block -- its own header says so, and says `exec` matters because a
swallowed 2 reads as a non-blocking error. Root `CLAUDE.md` requires any hook
that can block to carry a committed regression suite with must-block and
must-allow cases, sabotage-tested. Cheap in code, not cheap in verification,
and strictly more expensive than the role-prompt scope clause that addresses
the same complaint.

**Note the pulse already carries the focus instruction** at `:188-189` (`act`)
and `:215-217` (`autonomous`): "fix an unrelated problem only when it BLOCKS
one of them, and ticket or TODO the rest". The PM is told; the roles that
touch code are not. That asymmetry, not the pulse, is the main finding.

## Three prose sites still name `graphify . --no-viz --code-only` unconditionally

Filed 2026-09-18 by the PM. **Does not block crew 0.19.61; not fixed here.**

The remaining half of the CLOSED entry above, re-confirmed at `7c5b884b`:
`plugin/crew/commands/onboard.md:14` and `plugin/crew/commands/upgrade.md:56`
(both saying "both flags required"), and
`plugin/crew/skills/crew-graph/SKILL.md:44`. These are fixed prose with no
access to `reportTracked`, so they cannot interpolate the way the pulse text
does. Whatever fixes them is a different fix from the one-line bug above, and
should not be bundled with it.


## Generated checkers from the defect ledger — sequenced after crew 0.19.62

Filed 2026-09-18 by the PM. **Not deferred indefinitely; blocked on data.**

The ambition is that the crew builds and commits the checkers it needs rather
than each role re-typing the check by hand. Crew already has the pattern in one
place: `plugin/crew/agents/smoke-author.md:46-73` writes a check, writes its
`.crew/verify.json` rule, then mutation-proves the rule goes red. That is
generate-and-prove, scoped to smoke checks only.

`plugin/crew/skills/crew-lint/` is NOT that mechanism and should not be
mistaken for it: the directory contains `SKILL.md` and nothing else -- no
scripts, no templates. An agent reads it and types commands.

**Why it cannot ship before the ledger has run.** The trigger is a defect that
escaped every mapped command AND matches a class already recorded once; the
second occurrence generates the checker. Today `/crew:review` records only
counts -- `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`
(`plugin/crew/commands/review.md:409`) -- so no class is ever stored and there
is nothing to generate from. crew 0.19.62 adds the class row. This work needs
weeks of those rows before it has input.

**Design constraints already settled**, so they are not re-derived later: a
generated checker takes its file list as argv so it composes with
`.crew/verify.json`; it ships with a fixture it must flag and one it must not;
registration is a second commit after evidence of it going red on the real
defect; it enters as `provisional` (runs, reports, never fails the build) and
is promoted only on a real catch. **Every checker prints its inspected count
and exits non-zero on zero inspected** -- the vacuous-pass class (bad glob,
inspects nothing, exits 0) is one rule to kill and this repo has already been
bitten by an "INSPECTED 0" that read as a real result.

## Playbooks as a tracked artifact — scheduled as crew 0.19.64

Filed 2026-09-18 by the PM. **Scheduled, not deferred. Shape informed by
slices 0.19.61-0.19.63 rather than decided before them.**

A playbook is task-shaped -- "to change X in this repo, do A then B then C, and
the thing that bites you is D" -- and is a different artifact from a runbook.
`plugin/crew/skills/crew-runbooks/SKILL.md:8-12` says so itself: "it is 3am,
this is broken, what do I type? ... **Not** 'how the system works'". Runbooks
are symptom-indexed incident response.

**What slices 1-3 are expected to tell its design.** 0.19.61 wired the doing
roles to the codemap for the first time. Whether roles actually consume a
written-down repo procedure, and in what shape they use it, is unmeasured
today; that measurement is the design input here. It is no longer the decision
whether to build -- the user has accepted the cost.

**The cost accepted, enumerated so a partial change cannot happen.** A new
`.crew/playbooks/` directory needs the un-ignore list changed in every place
that states it, and `scripts/check-marketplace.py::check_crew_ignore_policy`
asserts that list is the same set in all of them. Enumerate every site with
`path:line` BEFORE touching the first: root `CLAUDE.md`, crew-setup's shipped
template, and every doc stating the list. A partial allowlist change is worse
than none.

## ~~Repo LICENSE is GPL-2.0 while crew's plugin.json declares MIT~~ — CLOSED 2026-09-19

Filed 2026-09-18 by the PM. **Pre-existing, not introduced here, not touched.**

**CLOSED.** All five `plugin/*/.claude-plugin/plugin.json` now declare
`"license": "GPL-2.0-only"` (crew and localgpu corrected from `MIT`;
gizmoduck, obsidian-vault and rule-of-two, which had no `license` key,
gained one). `scripts/check-marketplace.py` gained `check_license_consistency`
so this cannot drift back silently — see `scripts/_test/license-consistency.py`
for the sabotage-tested regression suite. Root `README.md`'s License section
now states GPL-2.0 applies to every plugin and points at
`plugin/crew/NOTICE.md` for the third-party MIT attribution named below, which
this resolution does not touch. Commit sha: `910cbc2e`.

`LICENSE` at the repo root is GNU GPL v2. `plugin/crew/.claude-plugin/plugin.json:12`
declares `"license": "MIT"`. Both were true before this work.

Surfaced now because crew 0.19.63 copies MIT-licensed material into
`plugin/crew/skills/crew-debugging/` (superpowers' `systematic-debugging`,
Copyright (c) 2025 Jesse Vincent). That copy is lawful either way -- MIT is
GPL-2-compatible -- and the attribution obligation is discharged by the
`NOTICE.md` that slice ships, independently of how this mismatch resolves. So
this is not a blocker for 0.19.63.

**It is still worth resolving**, because a consumer reading `plugin.json`
concludes crew is MIT and a consumer reading `LICENSE` concludes GPL-2, and
those imply different obligations on anyone redistributing the plugin alone.
Needs an owner decision, not a fix chosen by an agent.


## `/crew:work`'s runbook step fires on a judgement call, so it is unobservable

Filed 2026-09-18 by the PM, crew 0.19.63. **Not a wiring gap -- a trigger gap.**

Recorded precisely because the obvious version of this finding is WRONG and was
stated wrongly in conversation before an independent review caught it:
`crew-runbooks` IS already reached from `/crew:work`. `plugin/crew/commands/work.md`
step 11 runs `/crew:runbook --from-ticket $1`, and that predates all of this
work. `plugin/crew/skills/crew-setup/phases.md:453` reaches it too. Anyone
re-deriving "crew-runbooks is not wired in" will be re-deriving a fact error.

The real defect is the CONDITION. Step 11 fires when the ticket "involved an
operational procedure that will be repeated, is destructive, or lived only in
someone's head" -- three judgement calls, evaluated by the same session that
wants to finish. Nothing observable decides it, so nothing can check whether it
was skipped, and a skipped step looks exactly like a step that correctly
declined. That is the same shape as every other finding in this file: the
uninformative outcome and the reassuring one are indistinguishable.

**Proposed fix:** an observable field on the ticket -- `destructive: yes|no`
alongside the existing `risk:` line in `commands/ticket.md:20` -- so step 11
keys off a recorded answer instead of a re-judgement, and a ticket that never
answered is its own third state rather than defaulting to "no".

**Cost:** the ticket template, step 11's condition, and whatever writes tickets
in each tracker mode. Lands in crew, owes a bump.

**Also true and separate:** `crew-lint` has three citations outside its own
SKILL.md -- `plugin/crew/README.md:1489`, `plugin/PLUGINS.md:245`, and
`plugin/crew/skills/crew-setup/phases.md:329` -- and an earlier count of two
here was wrong. What holds is that none of them is a code path: no `TRIGGERS`
entry, no command or hook invokes it, and `ls plugin/crew/skills/crew-lint/`
returns `SKILL.md` alone, so it generates nothing. It runs once at setup and is
unreachable afterwards.

## Sabotage runs mutate the shared worktree while Stop hooks can fire

Filed 2026-09-18 by the PM, crew 0.19.63. **Process defect, not a code defect.**

A sabotage run breaks a file, runs a suite, and restores it. It does this in
the working tree that every other session on this machine is also using, and
two Stop hooks (`verify-gate`, `pm-pulse`) fire from those sessions at any turn
end. On 2026-09-18 the windows overlapped: a peer session's Stop read
`verify-gate.sh` at `21:26:09.486` while `write_bytes` had truncated it and not
yet finished writing, and the hook reported

    verify-gate.sh: line 429: syntax error near unexpected token `fi'
    outside-scope: (no python; scope not checked)

Both were artefacts. The file's mtime and the sabotage log's final write were
125ms apart, and that mutation was the last of five cases; the restore was
byte-identical. It took three separate checks to establish that, and one of
them -- a mid-run integrity check of my own -- compared against a remembered
sha and reported "intact" about a file that was 21 bytes short, exactly the
length difference of the live mutation.

**Two distinct lessons, and the second is the expensive one.** First, a
truncating write is observable by anyone reading the file, so a sabotage
harness must not run against a shared tree: use a git worktree, or take the
gate's own `.crew/.verify-gate.lock` for the duration. Second, a remembered
number is not a measurement -- an integrity check has to compare against the
value the mutating process itself recorded, not one written down earlier, or
it will confidently clear a mutated file.

**This is the second cross-session interference case in this repository's
lineage.** The first is in root `CLAUDE.md`: a background `graphify` rebuild
launched by `git checkout -b` overwrote a build mid-measurement, and the
node-set diff that followed compared the hook's output with itself and
reported a false zero. Same shape -- a concurrent writer nobody accounted for,
producing a result that looked clean.


## This checkout IS every session's plugin install - uncommitted hook edits run machine-wide

Filed 2026-09-18. **Third cross-session interference case. Standing hazard,
not an incident.**

`~/.claude/plugins/known_marketplaces.json` registers `useful-claude-add-ons`
with `"source": "directory"` pointing at this repository's path. So
`CLAUDE_PLUGIN_ROOT` resolves to this working tree, and **every uncommitted
edit under `plugin/crew/hooks/` executes as every session's hooks on this
machine, on the next turn end.** Not on next install. Not on restart.

Observed 2026-09-18: a peer session's Stop hook died with
`verify-gate.sh: syntax error line 398` from a slice-3 edit that was mid-write
in this checkout. The peer's hook command named this repo's live path, and the
peer was working in a *different repository*.

In that session's words, sharper than ours: "Tonight that was a syntax error,
which is the benign version: it failed loudly. The bad version is an edit that
is syntactically valid and semantically half-done, which would run silently."

That session also **deliberately did not revert the 20 lines**, because
discarding another session's uncommitted work is not its call. So neither side
could safely fix it. That is why the rule below is worktree-only rather than
"be careful".

**RULE, effective immediately: do not edit `plugin/crew/hooks/` in this
checkout.** Use a worktree:

    git -c core.hooksPath=/dev/null worktree add ../crew-wt-<slice> <branch>

The `hooksPath` override stops `post-checkout` launching a background graphify
rebuild. Merge back only committed, gate-green work.

**The three interference cases are one finding.** The graphify clobber (root
`CLAUDE.md`), the sabotage-window truncation (above), and this. This checkout
is shared infrastructure for every session on the box; the sabotage harness,
the hook scripts, and every tracked artifact a hook rebuilds all have to treat
it that way.

## `installed_plugins.json` records 0.19.56 while 0.19.63 executes

Filed 2026-09-18. **Record only - do not fix in the Stop-hook slice.**

The plugin cache records crew at `0.19.56`; the tree that actually runs is at
`0.19.63`. On a `directory`-source install the declared version describes
nothing that executes. Root `CLAUDE.md`'s first stop-and-ask is built on
`claude plugin update` comparing the *declared version*, so on this install
shape that comparison is against a number with no relationship to the running
code. Belongs with `scripts/_test/drift-detection.sh`, the check root
`CLAUDE.md` already says CI cannot run.

## `tests/sabotage.py` must not be killable into a silent half-restore

Filed 2026-09-18. Generalised from a peer repo that restored a leftover stub
five times in one night.

A harness that mutates files and restores them in a `finally` leaves the tree
mutated when the process is killed. A leftover stub, or a one-word sabotage in
a real check file, makes the next gate pass in milliseconds against nothing.

**Design, from the repo where it bit:**
1. Before the first write, record every file the run will touch AND its
   pre-mutation hash into a marker file.
2. The harness refuses to start, and the gate refuses to run, while that
   marker exists with hashes that do not match the tree.
3. **Check every artefact the harness touches, not the easiest to detect.** A
   guard that checks only the stub passes a tree with a sabotaged check still
   in it.
4. **A refusal stops the whole gate.** The observed failure was a gate that
   proceeded to `smoke.sh` after the self-test refused: fake passes stacked on
   a failure reported for the wrong reason. This is a block, so it needs the
   must-block case.

A killed run then leaves a marker naming exactly what to restore, instead of a
tree that looks fine.

## `scope_report.py`: three defects found by Codex on c7e3a91b..cc433e6a

Filed 2026-09-18. **Fold into the Stop-hook slice; all three verified here.**

1. **Synced trackers are invisible.** `declared_paths` reads
   `.work/tickets/<id>.md` only. Jira, ServiceDesk Plus and Obsidian Kanban
   modes keep the ticket at `.work/cache/<id>.md` (`commands/work.md:16`), so
   on every synced-tracker repo the report says "ticket file is missing" for a
   ticket that exists. **This repo's `tracker` is `obsidian`, so it is wrong
   here, not only in the jira repo.**
2. **The bookkeeping exclusion is a prefix test.** `_BOOKKEEPING` holds
   `TODO.md` and the check is `str.startswith`, so `TODO.md.py` and `TODO.mdx`
   are silently excluded. Measured: both return True.
3. **`fnmatch` has no real `**`.** Measured: `fnmatch("main.py", "**/*.py")`
   is False while `fnmatch("src/main.py", "**/*.py")` is True, so a ticket
   declaring `**/*.py` has its root-level files reported as OUT of scope. This
   is the worst of the three - a report that names in-scope files is how the
   line gets ignored, which is the exact failure the slice exists to prevent -
   and it is a parity defect: the gate's own bash matcher treats the pattern
   differently from the report that describes it.

**Resolved in `crew` 0.19.66** (commit on `crew-0.19.65-stophook`). All
three fixed in `plugin/crew/hooks/scripts/scope_report.py`, with the file's
first test suite (`plugin/crew/tests/test_scope_report.py`, 16 cases) and a
4/4 RED sabotage run. Defect 3 was fixed by REUSING the gate's matcher rather
than writing a second one: `verify-gate.sh` already stripped the `**/` form
correctly, so the report was the only copy that was wrong.

## The two gate matchers disagree with each other

Filed 2026-09-18, found while fixing the above. **Not blocking that work, so
not folded into it:** this is a change to a hook that can `exit 2`, so under
CLAUDE.md it needs its own bump, its own must-block/must-allow cases and its
own sabotage run, and it must not ride along in a commit about a report-only
script -- a revert of one would silently take the other.

`verify-gate.ps1:381` builds a fourth match candidate that
`verify-gate.sh:418-425` does not:

    .ps1:  $cands.Add(($Pattern -replace '[*][*]', '*'))

So for a pattern like `a/**/b` the PowerShell gate also tries `a/*/b` while
the bash gate does not. The two flavours can therefore select DIFFERENT rule
sets for the same changed file on the same repo, which is the same class of
defect as a `.ps1` guard that stands down on Windows: the gate that runs
depends on which shell the hook fired in. `-like` is also not `fnmatch`,
so the character-class forms may differ again.

Not yet measured: whether any pattern in this repo's `.crew/verify.json`
actually lands in the gap. Measure that first - if nothing here hits it, the
fix is still worth making but the urgency is a different number.

## CHANGELOG.md is not CRLF-normalised by git on this machine

Filed 2026-09-19 during the 0.19.65-0.19.70 run. **Did not block the work --
it was repaired in the working tree each time -- but it will bite the next
person, silently, and the repair is not obvious.**

Measured. `core.autocrlf` is `true` at SYSTEM scope here. For every other
file touched in this run -- `.ps1`, `.py`, `.json`, `PLUGINS.md` -- the
worktree copy was CRLF and git normalised it to LF in the index, so the
commits are clean. `CHANGELOG.md` is the exception: worktree CRLF **and**
index CRLF, against a HEAD blob that is pure LF. Staging it therefore
produced a 13,086-line whole-file diff (6,561 CRLF lines) instead of the
36-line entry that was actually written.

Byte counts, `git cat-file blob` on each side rather than `git show` (which
renders CRLF whatever the blob holds under `autocrlf=true`, so it cannot be
used to check this):

    HEAD:CHANGELOG.md   CR=0     LF=6525   <- stored LF
    worktree            CR=6562  LF=6561   <- one LONE CR, a stray \r\r\n

    index after add     CR=6562  LF=6561   <- NOT normalised

Why only this file has not been established. It has no `.gitattributes`
entry, so `autocrlf` alone governs it, and git skips the conversion for a
blob its own heuristic calls binary -- `file`(1) reports `data` for both the
worktree copy and the HEAD blob, which is consistent with that but does not
prove it. **Measure before acting on the guess.**

Repair, each time: rewrite the file LF-only in binary mode, then re-stage.
A `*.md text eol=lf` line in `.gitattributes` would fix it at the root for
everyone, which is why it is filed rather than done: that changes what git
stores for every markdown file in the repo and belongs in its own commit
with its own before/after byte census, not folded into a hook change.

Two traps worth keeping visible, because both cost time here:

1. **`grep -c $'\r$'` lies.** In Git Bash it reported 3 CRLF lines in a
   control file written with pure LF. Every count taken that way was wrong
   and briefly looked like `verify-gate.sh` had been corrupted to CRLF, which
   it had not. Count raw CR bytes instead: `tr -cd '\r' | wc -c`.
2. **A `
` in a heredoc arrives with one backslash stripped.** Writing
   `printf '%s
'` through the tool that edits these scripts lands a LITERAL
   NEWLINE inside the format string. It is harmless there -- the output is
   identical -- and three such lines are already committed in
   `verify-gate.sh`. It is NOT harmless in python source, where it produced
   an unterminated string literal. Build backslashes with `chr(92)`.

## Which PowerShell does `"shell": "powershell"` launch?

Filed 2026-09-19 from the `powershell-security-hardening` pass on
`verify-gate.ps1` and `pm-pulse.ps1`. **Recorded rather than chased:** it was
not resolved, and it decides whether one of that pass's round-1 notes applies
at all, so leaving it unstated would let the next reader assume either answer.

`plugin/crew/hooks/hooks.json` registers the PowerShell flavour of each hook
with `"shell": "powershell"`. Whether Claude Code resolves that to **Windows
PowerShell 5.1** (`powershell.exe`) or **PowerShell 7** (`pwsh.exe`) has not
been established here.

It matters for at least one concrete thing: `$PSNativeCommandUseErrorActionPreference`
exists only in PowerShell 7.3+, so a note about it is either load-bearing or
inert depending on the answer — and nothing in this repo currently records
which. The gates' own test suites all invoke `pwsh` explicitly
(`shutil.which("pwsh")`), so **the suites prove behaviour under 7 and say
nothing about 5.1**, which is the gap: if the harness actually launches 5.1,
every `.ps1` regression case in this repo is testing an interpreter the hook
never runs on.

How to settle it, cheaply and without guessing: have the hook record its own
interpreter once — `$PSVersionTable.PSVersion` and
`$PSVersionTable.PSEdition` written to a scratch file from inside a real
hook invocation — rather than reasoning from the string `"powershell"`. Do
not infer it from what is on `PATH`; the harness may resolve it differently.

Until then, treat "the .ps1 hooks run under PowerShell 7" as an **assumption
this repo has not verified**, not as a fact.

---

## Found while fixing the 0.19.92 fingerprint/budget review items, NOT fixed

Three things noticed inside `verify-gate.{sh,ps1}` and `verify_fingerprint.py`
while closing the two BLOCKs and the budget FIX. None of them blocked that
work, so none of them was widened into it.

### 1. A filename containing a NEWLINE still breaks the whole gate, not only the digest

`plugin/crew/hooks/scripts/verify-gate.sh:166` and
`plugin/crew/hooks/scripts/verify-gate.ps1:247` produce one newline-delimited
`CHANGED` list, and THREE readers consume it: the matcher heredoc, the scope
report, and `verify_fingerprint.py`. 0.19.92 fixed the digest's half by
keeping each line verbatim instead of stripping it, which closes the measured
case (` leading.txt`). A path with an embedded newline is still split into two
by every one of those three readers, so it matches no rule, is reported as two
unmapped paths and hashes as two absent files.

The review suggested `-z` and splitting on NUL. That was **not** taken here
and the reason is the reason it is written down rather than done quietly: the
fix has to move the SHARED channel, not just the fingerprint's feed. Giving
`verify_fingerprint.py` its own `-z` listing would mean two listings of the
same tree that can disagree, and the one the rules are matched against would
still be the newline one — the digest would then cover a path set the checks
never saw, which is the same class of defect 0.19.92 exists to fix. Doing it
properly means `-z` in both flavours plus NUL framing through the matcher,
`scope_report.py` and the `eval` read loop, which is its own change with its
own must-block cases.

### 2. An `always` command can still be deferred by the budget

`plugin/crew/hooks/scripts/verify-gate.sh:639` appends `always` commands to
the list after the rule loop. If the same command string also appears in a
priced rule, it carries that rule's cost and can be deferred with it — so a
command declared "always" does not always run. Pre-existing and untouched by
0.19.92 (the per-rule change preserves the old classification exactly). The
fix is probably to exempt `always` from the budget entirely, but that is a
policy decision about what `always` means, not a bug fix.

### 3. `sabotage.py` needs its budget mutations re-checked if the arithmetic moves

`plugin/crew/tests/sabotage.py` now anchors on the whole budget decision block
in each flavour, because a one-line mutation of `spent` did NOT reproduce the
defect and came back green. Anchors that large drift easily; the cheap check
is the loop in the sabotage suite's own header contract — every anchor must
match exactly once — and it is worth running before trusting the pair.

### 4. `HOLDER_AT` uses the same `tr -dc` coercion the deadline just lost

`plugin/crew/hooks/scripts/verify-gate.sh:408` reads the lock's age with
`lock_mtime ... | tr -dc '0-9'` -- the identical idiom that made
`-9999999999` into a deadline in 2286, four lines above the line 0.19.93
fixed. It was checked rather than assumed, and it is being left alone on
measurement rather than on taste:

* `lock_mtime` is `stat -c %Y` (`plugin/crew/hooks/scripts/verify-gate.sh:323`),
  which returns a non-negative epoch, so there is no sign for the coercion to
  eat. It is inert on every input either `stat` can produce.
* Its failure DIRECTION is the opposite of the deadline's. A mangled
  `HOLDER_AT` reads as a very old lock, so the gate RECLAIMS and runs the
  checks. The deadline's coercion made the gate stand down; this one would
  make it work.

Making it strict is two characters and would send a garbage mtime down the
existing "age cannot be read" branch, which is more honest than reclaiming on
a repaired number. It did not block 0.19.93 and it is not a defect today, so
it is written down instead of folded in.

### 5. The lock deadline is derived from PREDICTED cost, and an unpriced rule predicts nothing

Reproduced, on the 0.19.94 tree. TTL forced to 3s, a map whose only rule is
unpriced and runs `sleep 12`. At t=6 the holder was still inside the rule, the
published deadline read `start + 3` (window = `max(TTL, 2 x max stated cost)`
and the stated cost is zero), the token was 6s old against the 3s TTL, and a
second gate **ran `sleep 12` concurrently**. Two gates, one turn -- the exact
thing the lock exists to prevent, and the same defect the deadline was added
to fix, surviving for every rule that states no `seconds`.

Prediction is wrong in both directions: it under-protects the unpriced rule
and over-protects a priced rule that finishes early.

**Why this is not fixed here, and it is a construction problem rather than an
arithmetic one.** "Still working" is a liveness fact, and no value published
BEFORE a rule starts can carry it -- every such value is a prediction. The
holder cannot refresh the deadline during its own rule because it is blocked
in `eval`, and the two ways out were both already closed:

* **pid liveness** is measured unreliable on this platform
  (`plugin/crew/hooks/scripts/verify-gate.sh`, the 2026-09-13 note: a
  hard-killed Git Bash pid reported ALIVE at +0.5s, +5s and +15s);
* **a background toucher** is ORPHANED when the holder is SIGKILLed, and an
  orphan that keeps refreshing disables verification permanently -- which is
  strictly worse than the bug.

**The construction that does work, written down so the next session does not
re-derive it.** Invert which process is backgrounded. Run the RULE in the
background and keep the toucher in the FOREGROUND:

    { eval "$c" > "$out" 2>&1 </dev/null; echo $? > "$done"; } &
    while [ ! -f "$done" ]; do sleep 5; lock_extend; done

The holder polls for a sentinel instead of asking whether a pid is alive, so
the measured-unreliable check is not needed. If the holder is SIGKILLed the
FOREGROUND loop dies with it, so **nothing is left behind that can refresh the
deadline** -- the orphaned process is the rule, which touches no lock. That
closes the objection that killed the background toucher, and it extends the
deadline by wall-clock exactly while a rule is actually running, priced or
not.

**Why it is not in 0.19.94.** It rewrites the rule-execution path in BOTH
flavours -- output capture and exit-status handling are load-bearing there
(the gate prints `tail -25` of the captured output on failure), and the `.ps1`
runs each rule through bash with its own capture machinery. That is its own
commit with its own must-block cases, and bundling it with a digest change and
a budget change on the closing commit of a branch is how a scoped change
becomes an incident. The repro above is the starting point; the in-rule probe
in `plugin/crew/tests/test_verify_gate_lock_window.py` is the shape of the
test (an UNPRICED rule, asserting the deadline mtime advances mid-run).

### 6. An untracked COLLAPSED directory still hashes as absent

Noticed while fixing the gitlink case and deliberately not folded in. Git
emits a bare directory name for a wholly untracked directory, and
`verify_fingerprint.py` hashes that as "absent" -- the same constant a
deleted file gets. The submodule fix dispatches on the index mode `160000`,
so it does not touch this: an untracked directory has no index entry at all.

Not measured as exploitable and not obviously a defect: hashing such a
directory means walking it, and the directory in question is as likely to be
`node_modules` as anything a rule reads. The safe version is probably to walk
it only when a rule actually matches it. Recorded rather than guessed at.

### 7. Nested submodules past the depth limit share one marker

`plugin/crew/hooks/scripts/verify_fingerprint.py` bounds submodule recursion
at `_MAX_SUBMODULE_DEPTH = 4` and hashes the constant
`"submodule-depth-limit"` beyond it. The marker carries no path, so **every**
submodule at or past the limit hashes to the same value: with five levels of
nesting, a change inside the fifth does not move the digest, and neither does
swapping one too-deep submodule for another.

Repro: build six repositories, `git submodule add` each into the one above it,
map a rule to the outermost gitlink with a check reading the innermost file,
let the gate record a fingerprint, then edit the innermost file. Stop skips;
`--all` fails. Note that `-c protocol.file.allow=always` is required for every
`submodule add` against a local path, and that the fixture has to leave each
submodule DIRTY or the gitlink is not in the changed set at all (see the
0.19.94 note on that, which cost a vacuous test).

**The fix is a per-path marker** -- hash the path alongside the constant, so
two different too-deep submodules are two different values, e.g.
`"submodule-depth-limit:" + rel`. That restores "different inputs, different
digests" at the boundary without recursing further. It does NOT make the
contents covered; nothing below the limit can be, which is the point of having
one.

Not fixed because nobody has that layout: the limit is four, the repo has
zero submodules, and the reachable case needs five levels of nesting. Written
down with the repro so it is a ticket rather than a rediscovery.

## Mandatory-first scheduling runs shared checks before their prerequisites

Filed from an independent review of the branch that lands crew 0.19.67-0.19.78.
**Not fixed by decision** -- the honest fix is map-level and the gate cannot
derive it from the map as it exists. Recorded verbatim as the review wrote it:

```
FIX|plugin/crew/hooks/scripts/verify-gate.sh:766|Mandatory-first scheduling runs shared checks before their prerequisites; verify-gate.ps1 has the same defect.|Match rules [prepare,check] costing 5s and [check,mandatory] costing 10s, with always=[mandatory] and budget=60. Previously prepare preceded check; now execution is check,mandatory,prepare, causing checks dependent on prepare to fail.
```

Both flavours carry it: `verify-gate.sh` sorts `must` ahead of `may`
(`plugin/crew/hooks/scripts/verify-gate.sh:763`) and `verify-gate.ps1` does the
same thing at its own scheduler. A command shared by two rules is charged once
and run at the position the FIRST scheduled rule gives it, so promoting a
mandatory rule can pull a shared command ahead of a command that, in the other
rule's `run` list, precedes it.

**Why this is not being fixed here.** The reasoning, so the next reader does
not redo it: the honest fix is at the map level, not the scheduler's. It is
(a) a command that depends on a sibling is not shared across rules -- it is
that rule's own command and gets its own charge, and (b) a warning when two
rules that share a command disagree on its position in their `run` lists.
Neither is derivable from `.crew/verify.json` as the schema stands: a `run`
list is an ordered list of commands with no declared dependencies between
them, so the gate cannot tell "prepare must precede check" from "prepare and
check happen to be written in that order". Any scheduler-only fix would have
to assume the second is the first, which would re-serialise rules that do not
need it and silently spend budget doing so.

So this needs a schema decision before it needs code. Until then the gate is
correct about what it was told and wrong about what was meant, and that is
worth having written down rather than half-fixed.
## `crew`'s licence is declared two ways

Filed 2026-09-18 during the 0.19.66 debugging slice. **Pre-existing; did not
block that work and was deliberately not fixed there.**

- `LICENSE:1` — the repository root declares **GPL-2.0**.
- `plugin/crew/.claude-plugin/plugin.json:15` — the crew plugin declares
  `"license": "MIT"`.

Why it did not block the slice: the question that slice actually had to answer
was whether MIT-licensed material from `superpowers:systematic-debugging` could
be carried here and what notice it needs. Both answers are unchanged by which
of the two declarations governs `crew` itself — MIT into GPL-2.0 is compatible
in that direction, and the attribution obligation is discharged by
`plugin/crew/NOTICE.md` either way.

Why it should not be "tidied" by whoever reads this next: picking one changes
the terms this plugin ships under, for everyone who has already installed it.
That is an owner's decision and an ADR, not a drive-by edit. Note also that
nothing currently checks the two against each other, so this will not resurface
on its own — `check_self_claims` has no `license` claim type, and adding one
would be a separate change with its own argument to make.

## `find-polluter.sh` has four upstream defects, unfixed there

Filed 2026-09-18 during the 0.19.66/0.19.67 debug-command fixes, extended
2026-09-19 with one more (Codex, gpt-6-astra found all four, across two
review rounds). A second finding from the same 2026-09-19 round -- multiple
'**' in a test pattern silently matching a narrower set -- was INITIALLY
filed here too and is now removed: it turned out to be a defect in code
crew itself added (the `**/` collapse alternative and its comment at
find-polluter.sh:52-55 do not exist upstream), not an inherited one. See
`plugin/crew/NOTICE.md`'s modification list for that one instead --
filing it upstream would waste a maintainer's time on a bug that is ours.
Crew's copy under
`plugin/crew/skills/crew-debugging/find-polluter.sh` fixed all four
locally; as far as this session checked, upstream
`superpowers:systematic-debugging` 6.3.0's
`skills/systematic-debugging/find-polluter.sh` still carries all four, so
they should be filed there rather than assumed fixed by crew's copy
diverging.

1. **Whitespace in a test filename splits one test into two invalid runner
   arguments.** The original loop was `for TEST_FILE in $TEST_FILES`, which
   word-splits on IFS. Reproduction: create `src/has space.test.ts`, run
   with pattern `src/**/*.test.ts`; the script invokes `npm test ./src/has`
   and `npm test space.test.ts` as two separate calls, neither of which is
   the real file.
2. **A runner that cannot even execute is reported as a clean run.** The
   original line was `npm test "$TEST_FILE" > /dev/null 2>&1 || true`, which
   discards the exit status unconditionally. Reproduction: put an `npm` on
   PATH that exits 127 (command not found), run against any matching test
   file; the script prints "No polluter found - all tests clean!" and exits
   0.
3. **An investigation that executed zero tests reports a clean verdict
   anyway.** Reproduction: an unmatched test pattern, or a pollution-check
   path that already exists before the first candidate runs (every
   candidate then hits the "already exists, skipping" branch) — either way
   no test is ever actually run, and the script still exits 0 with "all
   tests clean!".
4. **The discovery pipeline hides `find` failures and reports incomplete
   coverage as clean.** `find ... | sort -u` inside a bare `VAR=$(...)`
   assignment discards `find`'s own exit status — `sort`'s success masks
   it. Reproduction: make `find` emit one passing test path and exit 1 (an
   unreadable subtree containing the polluter reproduces this on a real
   filesystem; a stub `find` on PATH reproduces it portably); `sort`
   succeeds, and the script proceeds with the partial list and exits 0
   reporting "all tests clean" — the polluter it never looked at is never
   found. Not reproducible via `chmod 000` on Windows Git Bash: measured,
   `find` still descends into a chmod-000 directory there and exits 0, so
   the regression test for this one uses a stub `find` and skips the
   chmod-000 variant on that platform with a stated reason.

Crew's fixes and their sabotage-tested regression cases are in
`plugin/crew/skills/crew-debugging/find-polluter.sh`'s header comment and
`plugin/crew/tests/test_debugging_method.py`.
## PM reporting-contract fix - crew 0.19.82 (placeholder)
## PM reporting-contract fix - crew 0.19.83 (placeholder)

Filed 2026-09-19, fixed same day on branch `crew-pm-reporting-contract`.
The standing `crew-pm` agent ran ~3h, wrote four version bumps of code
itself instead of dispatching a developer, and after being resumed sent no
report across five explicit status requests over ~50 min. Fixed in
`agents/pm.md` (mid-pass reporting cadence, interrupt rule, checkable
one-hat path list), mirrored one-line in `SKILL.md` and `commands/pm.md`,
regression-tested in `test_pm_reporting_contract.py`. See CHANGELOG.md for
the full account and commit sha for the fix.

**Unresolved caveat, left as the analyst reported it:** whether the five
status requests were ignored or merely queued behind long tool sequences
was not settled. Not investigated further here because it does not change
the fix - requiring an answer before the next tool call covers both
readings - but a future session diagnosing a similar silence should not
assume this was resolved.

## Stop gate per-rule record (crew 0.19.93, branch `crew-stop-gate-record`) - deferred items

Filed 2026-09-19 alongside the fix for the 7+ minute Stop gate
(`plugin/crew/hooks/scripts/verify-gate.sh`, `.ps1`, `verify_record.py`,
`verify_price.py`). These do not block that fix; they are follow-ups the
brief named or that surfaced while building it.

Four items previously listed here — `requiresCleanTree`, the "Template"
deliverable, the pm-pulse triggers, and the `HOOKS.md` doc update — were
reversed by the PM the same day, on the user's explicit instruction to build
the whole brief rather than scope down, and are now built rather than
deferred: `requiresCleanTree` shares the reach exclusion plumbing in
`verify-gate.sh`/`.ps1`; `plugin/crew/skills/crew-setup/examples/
verify-terraform.json` (the actual shipped map the brief meant) now carries
illustrative `seconds`/`reach` on every priced rule; the three pm-pulse
triggers (`verifyMarkerStale`, `verifyRulesUnpriced`, `verifyReachUndeclared`)
are in `crew_state.py`/`pm_brief.py`, sabotage-tested against a fixture; and
`CONFIG.md` gained §18 describing the per-rule record, since `HOOKS.md`
still does not exist anywhere in this repo.

- **`scripts/_test/drift-detection.sh` was not run.** Root `CLAUDE.md`
  requires it by hand before a change to the plugin update path, and it
  drives the real `claude` CLI so CI cannot run it either. Not run in this
  session; say so rather than implying it passed.
## Filed 2026-09-20 by the T-0003 developer (crew 0.19.95), not fixed there

- `.crew/codemap/crew.md` has no `## Landmines` section at all (its headings
  run Inventory / Hooks / ... / Unverified), and it does not mention the Stop
  gate's baseline (`.crew/.verify-verified-at`, `verify-gate.sh:70-74`),
  `scope_report.py`, or the new `scope_base.py`. `developer.md` step 2 sends
  every developer to that section first; on this subsystem there is nothing
  to read. Not blocking T-0003: the landmine it would have named is the one
  T-0003 fixed. Refresh with `/crew:onboard --refresh crew`.
- `.crew/verify.json` has no pytest rule naming
  `plugin/crew/tests/test_scope_report.py`, `test_scope_discipline.py` or the
  new `test_scope_base.py`, and none whose paths cover
  `plugin/crew/hooks/scripts/scope_report.py` or `scope_base.py` beyond the
  catch-all check-marketplace + pylint rules. Those three suites run from the
  gate only through the 185s whole-suite rule, i.e. when `conftest.py`,
  `crew_fixtures.py`, `context.py` or `sabotage.py` change. A behavioural
  regression in the scope layer alone is not caught at Stop. Not fixed under
  T-0003 because its scope says "do not touch: the verify map"; add a rule
  (`/crew:verify`) mapping the two scripts and three suites.

## Filed 2026-09-22 by the crew-house-style HTML print-rules developer, not fixed here

- **The four `docs/guides/crew/crew-*.html` guides have no generator and nothing
  binds them to the house style.** `plugin/crew/tests/test_docs_routing.py`
  now goes red if the HTML route loses the print rules or the `<thead>`
  requirement, but nothing asserts the four shipped files still carry them --
  a hand edit can drop the `@media print` block from
  `docs/guides/crew/crew-overview.html:20-24` (and its three siblings) and every
  check stays green. Not fixed here: the brief scoped the regression test to
  the house style, and a crew test asserting things about repo docs outside
  `plugin/crew/` couples crew's suite to files that may be deleted.

- **The `.docx` half of the print discipline is inherited, not asserted, and
  was verified only through LibreOffice.** In the regenerated
  `docs/guides/crew/crew-*.docx`, `word/document.xml` contains zero `w:keepNext`
  elements: LibreOffice's HTML import drops `page-break-after:avoid`
  outright (measured -- adding the same rule outside `@media print` changed
  nothing). Headings keep with the next paragraph only because
  `word/styles.xml` defines `Heading1/2/3` as `w:basedOn="Heading"` and
  `Heading` carries `<w:keepNext/>`. A soffice round-trip to PDF shows no
  stranded heading, so the inheritance does hold in LibreOffice's layout
  engine; Microsoft Word was not available here and was not checked. Not
  blocking: the PDFs are rendered from the HTML by chromium and carry the
  rules directly.

- **Regenerating those `.docx` files needs a post-processing step that lives
  in no committed script.** LibreOffice's Writer/Web HTML import resolves
  `table { width:100% }` against the page width rather than the text column,
  so every table came out ~3 cm past the right margin (measured:
  `w:tblW w:w="11339" w:type="dxa"` against a text column of 9638 twips).
  The fix applied by hand was to restate the section as Letter with 1-inch
  margins and every `w:tblW` as `5000 pct`, which is what Microsoft Word had
  emitted for the same CSS in the committed originals. Anyone re-running the
  conversion without it ships tables running off the paper. Not fixed here:
  these guides have no build script to put it in, which is the same gap as
  the first entry.

## Filed 2026-09-22 by the doc-builder LibreOffice-renderer developer, not fixed there

- LibreOffice's HTML importer applies **only simple selectors**, so on the report
  path it silently drops the table grid
  (`skills/doc-builder/scripts/build_report.py:166`), the navy header shading
  (`skills/doc-builder/scripts/build_report.py:168`), the zebra rows
  (`skills/doc-builder/scripts/build_report.py:170`), the meta-table key shading
  (`skills/doc-builder/scripts/build_report.py:174`) and the summary-card panels
  (`skills/doc-builder/scripts/build_report.py:185`). Measured 2026-09-22, LibreOffice 26.2.5.2 on
  Ubuntu 26.04; the selector-by-selector table is in
  `skills/doc-builder/references/word-traps.md`, "What LibreOffice silently
  drops". Not fixed here: the stylesheet's current shape was measured against
  Word, which stays the reference renderer, and rewriting it into bare classes
  for LibreOffice would need its own re-measurement on BOTH engines or it trades
  a flat report on Linux for an unstyled one on Windows. The ticket asked for the
  reduced fidelity to be stated, and it is, in four places a user reads.
- `.claude-plugin/marketplace.json`'s `doc-builder` description still reads
  "through Word", and both install-script catalog rows still read
  "DOCX/PDF via Word" (`scripts/install-prerequisites.sh:1032`,
  `scripts/install-prerequisites.ps1:918`). All three are now inaccurate.
  Not fixed here: the ticket forbids touching `marketplace.json` (another
  session owns it and the PM applies bumps centrally), and both install scripts
  are dirty with another session's work. `check-marketplace.py` passes either
  way, so this blocks nothing - but the three must change together when they do.

## Filed 2026-09-22 by the crew QA-fix developer, not fixed there

- `crew-house-style`'s four `resolve_brand.py` citations are correct today and
  bound by nothing: `plugin/crew/skills/crew-house-style/SKILL.md:168`
  (`resolve_brand.py:78-82`, and `:317` on the next line),
  `plugin/crew/skills/crew-house-style/SKILL.md:170` (`:66-67`) and
  `plugin/crew/skills/crew-house-style/SKILL.md:185`
  (`resolve_brand.py:298-317`, and `:301` two lines below). Verified by hand at
  this commit - all five resolve to what the prose says. The new
  `test_the_cited_lines_of_the_generator_hold_what_crew_says_they_hold` covers
  only the two `build_report.py` citations in the `### HTML` route, so the same
  rot that moved `155-157` to `165-167` would go unnoticed here. Not fixed:
  binding them needs the three continuation citations (`:317`, `:66-67`,
  `:301`) rewritten repo-relative first - a bare `:317` cannot be parsed
  without guessing which file it continues, and CLAUDE.md forbids the bare form
  for exactly that reason - which is a prose change to a section this ticket's
  defects do not touch, and it carries its own version bump.
- The sabotage suite reports 11 STILL GREEN mutations on Linux, all
  pre-existing and none in `test_docs_routing.py`. Measured at this tree with
  `plugin/crew/tests/sabotage.py` run in five index slices. Ten of them report
  `1 skipped` under the mutation, so the named test never executed: nine name
  PowerShell in their label and one is `the bash gate stops publishing a
  deadline at all`. **The eleventh is different and is a real hole**: `the
  frozen artifact path is stored with native separators` reports `1 passed`
  with the mutation applied, so the test ran and did not notice. Not fixed:
  the skipping ten need the suite run where those tests execute, which this
  Linux box is not - `pwsh` IS on PATH here (`/snap/bin/pwsh`) and they skip
  anyway, so the skip condition has NOT been identified and must not be
  assumed to be a missing interpreter. The vacuous one is in the frozen-
  artifact path, nowhere near this ticket's files.

## Filed 2026-09-22 by the doc-builder QA/security-fix developer, not fixed there

- **Requested during the ticket, out of its scope: add the
  `anthropics/claude-plugins-community` marketplace and install `eli5` from it
  in both install scripts.** `eli5` is not in this repository (no `skills/eli5`,
  no `plugin/eli5`), so it can only come from that marketplace. The pattern to
  copy already exists twice: `scripts/install-prerequisites.sh:2302-2304`
  (`add_marketplace "anthropics/claude-plugins-official" ...` then
  `install_plugin "claude-code-setup@claude-plugins-official"`) and
  `:2673-2676`; the PowerShell halves are `Add-Marketplace`/`Install-Plugin`
  around `scripts/install-prerequisites.ps1:537` and `:899`. The second half of
  the request, the **`github` skill, is already installed** - it is in the skill
  list at `scripts/install-prerequisites.sh:1144` with its menu description at
  `:1182`, so nothing is needed for it. Not fixed here for two reasons, both
  hard: this ticket's scope is `skills/doc-builder/**` only, and both install
  scripts are already dirty with a concurrent session's uncommitted edits -
  CLAUDE.md requires a registration to land in ONE commit across the
  marketplace entry, the catalog row, `plugin/PLUGINS.md` and both install
  scripts in the same order with the same text, and a half-landed one fails the
  checker with no way to tell which half was intended.

## Filed 2026-09-22 by the install-script uv security/QA fix developer, not fixed there

- **`install_packages` still uses `pacman -Sy` without `-u`**, at
  `scripts/install-prerequisites.sh:2086`
  (`pacman) as_root pacman -Sy --noconfirm "${missing[@]}" ;;`). That is the
  partial-upgrade idiom Arch documents as the way to break an install: refresh
  the databases, then install packages built against libraries the rest of the
  system has not been upgraded to. The same idiom was fixed in
  `install_pipx_package` at `scripts/install-prerequisites.sh:337`, which now
  runs `pacman -S --needed --noconfirm python-pipx` - no refresh, so no partial
  upgrade, and it falls through to the next rung if the local database is too
  stale. Not fixed here because `install_packages` serves the whole
  prerequisites row (git, nodejs, npm, python3, pip3) rather than the uv chain
  that ticket covered, so changing it changes a row nobody asked about; and
  because the two safe forms differ in blast radius (`-Syu <pkg>` full-upgrades
  a stranger's machine, no-refresh can fail on a stale database) and picking
  between them for the prerequisites row is its own decision.

- **The astral.sh installer pin is recorded as EMPTY, so that rung is skipped**,
  at `scripts/install-prerequisites.sh:281-282` (`UV_INSTALLER_VERSION=""` /
  `UV_INSTALLER_SHA256=""`). The mechanism that fetches by pinned version over
  https-only and verifies a sha256 before running anything is in place and
  tested; the two values are not, because the ticket that added them forbade
  downloading the installer, and inventing a version/digest pair would have
  been worse than leaving them empty - a wrong digest fails closed but lies
  about having been measured. Until an operator reads
  `https://astral.sh/uv/<version>/install.sh`, runs `sha256sum` on it and fills
  both in, a host with no pipx and no pip-able Python loses that rung and gets
  the loud failure block instead. `scripts/_test/uv-install.sh` case 7d pins
  the skipped-when-unpinned behaviour and cases 7, 7a, 7b, 7c and 7f pin the
  fetch-and-verify path against a fixture digest, so filling the values in is a
  two-line change with the checks already written.

- **Two more unconditional `export PATH="$HOME/.local/bin:$PATH"` prepends**, at
  `scripts/install-prerequisites.sh:2631` (strix) and
  `scripts/install-prerequisites.sh:2764` (graphify). Same shape as the defect
  fixed in `uv_on_path` at `scripts/install-prerequisites.sh:219-240`: a
  user-writable directory goes ahead of `/usr/bin` for every later step in the
  run, whether or not the thing it was added for is actually there, and with no
  guard against the run being root with an unprivileged `HOME` (`sudo -E`, an
  `env_keep` carrying HOME, `su` without `-`). They are milder than the uv one
  was - each is reached at most once, where `uv_on_path` was called up to nine
  times and stacked duplicates - but they are the same class, and `uv_home_is_safe`
  (`scripts/install-prerequisites.sh:205`) is already there to gate them. Not
  fixed here: both belong to rows (strix, graphify) outside the uv chain that
  ticket covered, and each needs its own fixture case in
  `scripts/_test/uv-install.sh` or a suite of its own before being touched.

## Two shell suites under `scripts/_test/` are run by nothing - OPEN 2026-09-22

`.github/workflows/marketplace.yml` names each shell suite explicitly (`:74`
menu-groups, `:84` check-powershell, `:90` ps-install-keys) rather than globbing
`scripts/_test/*.sh`, and `.crew/verify.json`'s rule for
`scripts/install-prerequisites.{sh,ps1}` runs only `bash _verify/smoke.sh`. So
`scripts/_test/uv-install.sh` (150 cases) and `scripts/_test/mcp-preflight-catalog.sh`
(109 cases) are green locally and are executed by neither CI nor the local Stop gate.
Both were sabotage-proven when written, which is exactly the property an unwired suite
stops carrying forward. Wiring them needs two lines in
`.github/workflows/marketplace.yml` beside `:90` and one `run` entry in
`.crew/verify.json`'s install-script rule. Not done in the ticket that wrote the second
suite: its scope was `scripts/install-prerequisites.{sh,ps1}` and `scripts/_test/**`
only, and both target files were being edited concurrently by other agents.

## `ensure_uv` can succeed on a host where `uvx` does not resolve - OPEN 2026-09-22

`uv_on_path` (`scripts/install-prerequisites.sh:225`) is satisfied by EITHER `uv` or
`uvx`, but the two rows that call `ensure_uv` register a command whose literal first
word is `uvx` (`scripts/install-prerequisites.sh:2602` aws-api,
`scripts/install-prerequisites.sh:2650` aws-pricing). Since the launcher check added
on 2026-09-22 (`mcp_launcher_resolves`, `scripts/install-prerequisites.sh:923`) those
two rows now FAIL on a host that has `uv` and not `uvx`, where they previously
registered a server that could not start. The new behaviour is the correct one and is
not a regression to undo - but the message the operator gets blames the MCP row rather
than naming the uv install that produced a half-usable toolchain. The narrow fix is
for `ensure_uv` to require `uvx` specifically when its caller is going to register a
`uvx` command. Not fixed here: it changes `ensure_uv`'s contract for all three of its
callers and belongs with `scripts/_test/uv-install.sh`, not with the MCP ticket.

## Sabotage-testing in a SHARED worktree put a sabotage into a commit - OPEN 2026-09-22

Two incidents in one turn, one cause: a sabotage driver that edits the live working
tree, restores it, and verifies the restore byte-identically. Byte-identical restore
is not enough when other agents read or commit that tree in between.

1. **A commit captured the sabotage window.** `3cca6482` ("crew 0.19.98") contains
   `scripts/install-prerequisites.ps1` with `Invoke-SkillPreflights` *called* at
   `:2124` and *defined nowhere* - because another agent committed the whole tree
   during the ~20s the Defect-1 sabotage was applied. HEAD therefore ships a `.ps1`
   that dies at runtime on every Windows run. The working tree is correct and the
   restore was verified byte-identical; the damage is entirely in the recorded
   history. Fixed by whoever commits next - nothing needs re-writing, the correct
   text is already in the tree.
2. **The host's coreutils were destroyed a second time.** Sabotage-testing
   `scripts/_test/uv-install.sh`'s `stub()` guard by removing its `rm -f` and running
   the WHOLE suite reproduced the original defect exactly: `mkfixture` symlinked
   `$fx/bin/<tool>` at `/usr/bin/<tool>`, and the stub writes followed those links
   into the uutils multicall binary - 116 hardlinks, one 101-byte shell stub.
   Repaired in place from `/var/cache/apt/archives/rust-coreutils_0.10.0-1ubuntu2~26.04.1_amd64.deb`
   (already cached; nothing installed, no network), preserving the hardlink set.
   `dpkg -V rust-coreutils` and `dpkg -V dash` are both clean.

The harness half is FIXED, not deferred: both suites now copy the real tools into
`$TMP` (`mkrealbin`, `scripts/_test/uv-install.sh:105` and
`scripts/_test/mcp-preflight-catalog.sh:80`) and symlink only at those copies, so a
write-through can no longer reach anything outside `$TMP` whether or not `rm -f` is
present. Case 0 in each suite asserts that invariant, and both the invariant and the
`rm -f` are sabotage-proven with `dpkg -V` clean throughout.

What is NOT fixed, and is the entry here: the sabotage driver itself still edits the
live tree. It should run against a throwaway copy or a `git worktree`, so no window
exists in which a concurrent committer can snapshot a deliberately broken file. That
needs a shared helper under `scripts/_test/` and agreement on where sabotage runs
live; it was out of scope for the ticket that discovered it.

## Open items handed off 2026-09-22

`.work/HANDOFF.md` is gitignored and the session task list does not survive a
context clear, so the open items live here where they are tracked.

**Needs the operator, not an agent**

- **Launch Obsidian once** and open `/repos/claude-memories`. The Local REST API
  plugin writes its `apiKey` on first run; nothing exists on disk until then, and
  the MCP registration cannot proceed without it. Fully quit from the tray and
  relaunch - closing the window only minimises, and Obsidian reads its plugin list
  at launch. Then `vault_ops.py fix-ports`, `register --apply`, `diagnose`. Point
  the MCP server at the HTTP port (`insecurePort`), never HTTPS - Node rejects the
  self-signed cert and a green `curl -k` proves nothing.
- **Vault host contract.** `/repos/claude-memories/CLAUDE.md:8` names only
  `dadeush-lenovo` and `dadeush-desktop`; `:211` retires `/root` and `/home` paths
  as "other host" at once. This Linux box is neither, so every session run here is
  destined to be discarded by the gardener. Four live transcripts on this host are
  in no queue. Three proposed edits are in the session scratchpad; the file is
  **CRLF on all 275 lines** and rewriting it as LF turns a three-line change into a
  275-line diff replicated by Sync. Decided: permanent host, so the edits apply.
- **Solomon logo.** It IS committed - the wordmark is at `word/media/image4.png`
  inside `skills/solomon-doc-builder/assets/sop_template.docx`. `build_sop.py`
  reaches it via the template; `build_report.py` does not, so branded HTML and
  reports get colours and fonts but no masthead. Extract it to a standalone
  `assets/logo.png`, reference it from `brand.json`, bump `solomon-doc-builder`
  (1.1.0). Separately, `sop.assets_dir` points at `/repos/OnboardingSOPs/assets`,
  which is genuinely absent here - that holds SOP screenshots, not the logo.
- **Outlook on Linux.** No native client exists or is planned. Outlook PWA via Edge
  is installed. Alternatives: `outlook-ew` snap (unofficial) or Evolution +
  `evolution-ews` (native GNOME). Verify EWS is still available for Exchange Online
  before configuring Evolution - do not assert it from memory.
- **Splashtop is attended-only** as installed. The session is Wayland, so the first
  connection needs someone to click Approve here, there is no sharing at the GDM
  login screen, and the lock screen revokes the restore token. Unattended needs
  automatic login plus the "Allow Locked Remote Desktop" GNOME extension - both
  real security trade-offs.
- **`/crew:verify --all` has never run green.** Three rules are permanently over the
  60s Stop budget (81s, 96s, 185s) and stay UNVERIFIED. The repair of that command
  is the headline fix in PR #205 and is undemonstrated.

**Engineering, unassigned**

- **Windows-compatibility audit across 36 skills and 5 plugins. NEVER DISPATCHED.**
  crew-pm confirmed this directly: "It has never been dispatched. Do not let my
  earlier silence read as in-progress." Wants 3-4 agents by skill group, not one.
  Checklist is CLAUDE.md's Landmines section. Report findings before fixing - each
  fix lands per marketplace entry with its own bump.
- **Re-render the guides so brand resolution applies.** All four `crew-*` guides and
  `obsidian-claude-guide` carry `#1F4E79`, the neutral navy, and no Solomon colour.
  Note the limit: `build_report.py`'s `build()` emits no `<h3>`, so a narrative
  document past H2 does not fit that pipeline - it stays hand-written but must call
  `resolve_brand.py` instead of copying the palette hex.
- **Wire `uv-install.sh` (162 cases) and `mcp-preflight-catalog.sh` (122) into CI and
  `.crew/verify.json`.** Neither is run by anything today. A regression suite nobody
  runs is worse than none, because its presence reads as coverage.
- **DONE 2026-09-22: regression case for the write-through-symlink harness defect.**
  `uv-install.sh` already had it (case 0 + case 26); `mcp-preflight-catalog.sh` did
  not - only case 0's structural invariant, no canary write-through proof. Added
  case 26 there too, mirroring `uv-install.sh`'s. Both sabotage-tested (mkrealbin's
  `cp` reverted to `ln -s`; both suites go red) and restored byte-identical.
  A follow-up independent review then found the sabotage-testing METHOD itself
  unsafe: `mkrealbin`'s `chmod +x "$REALBIN/$t"` had no guard, so a sabotaged
  entry that was a symlink got `chmod`'d anyway, following the link - it touched
  the host's real `/usr/bin/find` ctime during that review's own sabotage run
  (mode stayed 755, `dpkg -V` stayed clean, but a real file was written to).
  Fixed in both suites: `chmod` now requires `[ -f ] && [ ! -L ]` first and exits 2
  otherwise, so a reverted `mkrealbin` aborts on its FIRST sabotaged entry, before
  any `chmod` call - re-sabotaged and reproduced safely by a decoy-only harness
  (every name mkrealbin copies gets a wrapper under its own `mktemp -d` that execs
  the real tool by absolute path, so even `command -v find` cannot resolve to a
  host path during the test) and by re-sabotaging the shipped files directly
  (exit 2 immediately, host `find`/`mktemp` ctime and mode unchanged, `dpkg -V`
  clean). Also closed in the same pass: an unguarded empty-`$TMP` would have made
  every `"$TMP"/*` bound match the literal pattern `/*` (any absolute path), so
  `mktemp -d` failing now refuses with exit 2 rather than continuing; the "HOST's
  mktemp is untouched" checks compared `--help`'s exit code, which a replacement
  stub exiting 0 would pass just as well as the real binary, so they now compare a
  sha256 taken at run start against one taken at the check site.
- **The sabotage driver edits the live tree**, so a concurrent committer can snapshot
  a deliberately broken file. It did: `3cca6482` shipped a call to an undefined
  function. Should use `git worktree`.
- **`ensure_uv` is satisfied by `uv` alone** while the aws-api and aws-pricing rows
  register `uvx` - those rows fail correctly but name the wrong step.
- **`check_group_parity` compares catalog KEYS only, never Spec strings**, so passing
  a repo name where the marketplace local name belongs stays GREEN.
  `mcp-preflight-catalog.sh` case 22 catches it; the main gate cannot see the class.
- **Refresh the code graph** after merge: `graphify update .`, never
  `graphify . --no-viz --code-only`. Graph is at `8c8353f5`.
- **Session capture on this host.** The `obsidian-vault` plugin's SessionEnd hook is
  active but nothing reached the queue, because no vault was configured until this
  session. Confirm it now appends - do not infer "no hook" from "no lines".
- **The 81-entry gardener backlog** can only be worked on `dadeush-lenovo` or
  `dadeush-desktop`. 15 are deliberately deferred as too large (9.3MB-66MB); 10
  belong to LENOVO; ~66 untriaged, ~9 likely empty-shell.
- **Per-rule `seconds` never gets re-measured per host, so a rule declared over budget
  on one machine is chronic on every machine.** `.crew/verify.json:73` declares 81s for
  rules[3] and `:99` 96s for rules[4]; measured on the Linux host 2026-09-22 they are
  16s and 15s, both far inside the 60s Stop budget. The timings cache exists
  (`plugin/crew/hooks/scripts/verify_record.py:560`, `if rule.get("unknown")`) but only
  fills for a rule with NO declared `seconds`, so a stale declared number can never be
  corrected by measurement - only by `--price --force`, which dirties a tracked file.
  Did not block: `/crew:verify --all` now clears both rules regardless of the price.
- **`map-audit.sh` false-positives on a `run` command that `cd`s first.** It reports
  `hooks/scripts/_test/validate-prompts.py` as "a rule pointing at a file that does not
  exist"; the command is `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`
  and the file is really at `plugin/crew/hooks/scripts/_test/validate-prompts.py`
  (`.crew/verify.json:167`). A false "missing check" in an audit whose whole job is
  finding missing checks trains its reader to skim it. Did not block: 0 orphaned, which
  is the line that mattered for this task.
- **`.crew/verify.json:3` still reads `"anchor": "repo@5238be3d"`**, ~40 commits behind
  HEAD, so nothing in the file's `_note` can be re-checked by the path-diff method
  CLAUDE.md prescribes. Did not block: my task changed rules, not the anchor contract,
  and re-anchoring is a judgement about when the whole map was last re-derived.
- **`.crew/codemap/verification-harness.md` (anchor `ea8a014`) has a NON-empty path
  diff** on its own five cited paths - `.crew/verify.json`, `_verify/smoke.sh`,
  `verify-gate.sh`, `verify_record.py` and more all moved since. Per INDEX.md that is
  `knowledge.behind` with the cheap test already run and failed, so the note needs
  re-verification, not just a re-anchor. Did not block: I read it and used only the
  claims I re-derived from the code myself.
- **17 tests in `plugin/crew/tests/test_context_watch.py` go red under the in-flight
  flavour-guard work** (the uncommitted `if ($env:OS -ne 'Windows_NT') { exit 0 }` block
  in 14 `.ps1` files plus the two new `_test/test_flavour_guard.py`). The `[ps1]`
  parametrisations drive `context-watch.ps1` on Linux, where the new guard makes it
  exit 0 silently. Measured 2026-09-22: pristine HEAD `31393918` is 52/0 green; with the
  guard applied, 17 failed / 1667 passed. Not mine and not blocking - filed so whoever
  owns that change sees it before committing.
- **`_verify/smoke.sh` still calls only eight of `main()`'s checks and now misses
  eight** (`main()` at `scripts/check-marketplace.py:1588`, `check_description_claims` at
  `:867`, `check_catalog_claims` at `:1030` - all three re-measured with `grep -n` as the
  LAST step, after every edit in this change including the two NIT docstring expansions
  that moved them further than the previous pass's citations said; `run_marketplace_check`
  at `_verify/smoke.sh:72-98`) - `check_description_claims` and `check_catalog_claims`,
  both added in this change, are absent from its list the same way `check_self_claims` already was
  (`.crew/codemap/marketplace-registration.md`, finding 3). Did not block: this change's own
  edits ended up touching `.claude-plugin/marketplace.json`, `scripts/check-marketplace.py`,
  `scripts/_test/self-claims.py`, `scripts/install-prerequisites.sh` and
  `scripts/install-prerequisites.ps1` (the "26 commands" defect the new `check_catalog_claims`
  was written to catch), and, once QA found two more sites carrying the same wrong number,
  `plugin/crew/README.md`, `plugin/crew/skills/crew-best-practices/SKILL.md`, and
  `.crew/codemap/install-scripts.md` (updated to describe the fix, its own anchor unmoved) -
  but never `_verify/smoke.sh`, which this is a pre-existing, already-documented drift against
  (finding 3, cited above) that I only added two more names to, not a file this task had reason
  to touch.
- **`check_self_claims`'s own file-discovery has the same "git failure collapses to a
  safe-looking value" shape this round's FIX just removed from `count_plugin_commands`
  and `count_plugin_agents` - and the `plugin-commands:` marker branch this same round
  added is itself one of the markers this makes unreachable, not merely "affected along
  with every other marker."** `scripts/check-marketplace.py:700` -
  `for path in sorted(git("ls-files", "*.md").split()):` - uses the shared `git()`
  helper, which still returns `''` on any git failure rather than raising or returning
  `None`. In a ROOT that is not a git working tree, this reads as "zero markdown files
  to scan", so `check_self_claims` silently checks NOTHING - every `<!-- claim: ... -->`
  marker in the repo, `plugin-commands:` included, passes unchecked, EVEN THOUGH
  `count_plugin_commands` itself now correctly reports "could not verify" rather than a
  false zero (this round's FIX): that correct behaviour is never reached, because the
  outer discovery loop never gets as far as reading the file the marker lives in. Found
  while sabotage-testing this round's FIX (a `plugin-commands:` marker propagation test
  built against a non-git ROOT returned 0 problems for this reason, not because the
  marker logic itself was wrong - see the comment in `scripts/_test/self-claims.py`
  right before the `no_git_description_problems` case). Did not block: this round's QA
  named `count_plugin_commands`/`count_plugin_agents` (`:601`) specifically, not this
  earlier call, and `check_self_claims` predates this ticket entirely.
- **`verify_price.py` (`plugin/crew/hooks/scripts/verify_price.py:69-89`, `_time_rule`)
  shares the same "Git Bash has no python3" landmine `verify-gate.sh`/`.ps1` were just
  fixed for.** `--price` runs a rule's own `run` commands (most of which hardcode
  `python3`) through `bash -c cmd` with no shim on PATH, so an operator who runs
  `verify-gate.sh --price` on a Windows machine where only `python`/`py` resolves would
  hit the same false "command not found" the Stop-gate fix (T-item-10) just resolved for
  ordinary rule execution. Did not block/fix here: the ticket named `verify-gate.sh` and
  `verify-gate.ps1` specifically as the surfaces to fix; `--price` is a separate,
  operator-only entry point with its own bash resolution (`_bash()`,
  `verify_price.py:57-66`) that would need the identical shim built a second time.
- **`pm-pulse.ps1`'s `Resolve-CrewPython` (`plugin/crew/hooks/scripts/pm-pulse.ps1:36-63`)
  is the weaker, metadata-only resolver (WindowsApps path filter, no execute-to-verify
  probe) while its bash twin `pm-pulse.sh` calls `crew_py_strict`, the execute-verify
  version. Windows audit wave 3 hardened `context-watch.sh`, `pm-brief.sh` and
  `platform-sync.sh` (and their `.ps1` twins) to match `crew_py_strict`'s strength on
  both flavours, and role-write-guard.ps1 already carries the strict pattern, but
  pm-pulse.ps1 was left as-is: it is a pre-existing mismatch, not introduced by this
  change, and pm-pulse.{sh,ps1} were not in this ticket's named file list. A candidate
  that prints a plausible path via shell metadata alone (not proven by execution) would
  still be accepted by pm-pulse.ps1 where pm-pulse.sh would reject it. Did not block:
  fixing it means widening a file this ticket did not name.

- **`vault-capture.ps1` discards `vault_capture.py`'s own exit code, unlike its
  `.sh` twin.** `plugin/obsidian-vault/hooks/scripts/vault-capture.ps1:115` runs
  `& $py (Join-Path $dir 'vault_capture.py') $Trigger` then unconditionally
  `exit 0`, pre-dating the Windows-audit-wave-3 change to this file (confirmed by
  reading the version before this ticket's edit - same unconditional `exit 0`).
  `vault-capture.sh` `exec`s python instead, so its own exit code IS
  `vault_capture.py`'s. The divergence is invisible for the hook path (SessionEnd/
  PreCompact ignore a non-blocking hook's exit code either way) but bites the
  `--selftest` CLI diagnostic specifically: `vault_capture.py --selftest` exits 1
  and writes "selftest FAIL: no vault resolved" on stderr when no vault is
  configured, and a human or script driving that through `vault-capture.ps1
  -Trigger --selftest` sees exit 0 (success) despite the FAIL on stderr - exit code
  and message disagree. Did not block Windows audit wave 3: that ticket's brief
  scoped the interpreter-resolver shape and the UTF-8 stdin decode, not
  `--selftest` exit-code parity between the two flavours, and the asymmetry
  predates this change.

## Filed 2026-09-22 by the mermaid-svg-bitbucket CRLF-digest fix developer, corrected 2026-09-22

An earlier version of this entry said a Windows clone's checked-out SVG bytes would show
as changed under `git diff`/`git status`, and proposed `*.svg -text` in the repo-root
`.gitattributes` as the fix. Both halves of that were wrong, on review, and it is worth
keeping the correction visible rather than quietly rewriting the entry, per this file's own
"a correction that outlives the thing it corrected" pattern.

- **`git status`/`git diff` do NOT show a converted checkout as changed.** That was the
  premise for treating this as visible drift, and it inverts how `core.autocrlf` actually
  works: on comparison, git runs the working-tree content back through its "clean" filter
  (the same direction as a commit would use) before diffing it against the index/blob, which
  reverses whatever the checkout's "smudge" filter did. A CRLF working-tree copy of an
  LF-committed SVG that hasn't been otherwise touched compares as clean, not modified - the
  same normalize-before-compare behavior that makes `.sh` scripts (this repo's existing
  `*.sh text eol=lf` case) look unchanged in git even when their checked-out bytes carry
  CRLF. `svg_digest()`'s normalization (`skills/mermaid-svg-bitbucket/scripts/render_mermaid.py:77`)
  closes the one place this repo's own tooling looks at raw bytes without going through git's
  compare-time filter - `--check`'s hash comparison - which is the part git's own filters
  don't reach.
- **Real mmdc output has nothing for a line-ending translation to act on.** Measured: this
  skill's one committed real-render fixture, `tests/fixtures/sample.svg` (10937 bytes), contains
  zero `\n` and zero `\r` bytes - it is emitted as a single line. A file with no line breaks in
  it cannot differ by line-ending convention at all, on any host, with or without
  `svg_digest()`'s normalization. That makes the byte-reproducibility scenario this entry
  originally raised near-theoretical for a real render: it would need a diagram, or a
  mermaid-cli version, that pretty-prints its SVG output with embedded newlines, which is not
  what this skill has observed. (One fixture, one mermaid-cli version - this is not a claim
  that no mmdc output ever contains a newline, only that the one measured here doesn't.)
- **Conclusion: `.gitattributes` `*.svg -text`/`binary` is very likely not needed**, on the
  evidence above - git's own compare-time normalization already prevents the "looks changed on
  the other platform" failure mode this entry was originally written to describe, and the
  "committed bytes literally differ" failure mode has nothing to act on in a real render. Not
  proposed for implementation; nothing further queued here unless a future mermaid-cli version
  is observed emitting multi-line SVGs, at which point `svg_digest()`'s normalization already
  covers the `--check` side of that and this line should be revisited for the git-diff side.

## Filed 2026-09-23 by the crew PM, during the unnamed-PM fix, not fixed there

Deferred: outside that fix's scope (PM spawn/persistence). Measured at `8b8a4028`, crew 0.20.14.

### `/crew:upgrade` freezes built-in defaults into the repo layer, so the global layer can never reach an upgraded repo - OPEN

`upgrade_config` (`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:393`) merges every
`CONFIG_BLOCKS` default (`:290`) into `.crew/config.json`. Measured:
`upgrade_config({"schema":2,"pm":{"enabled":True}})` returns a `pm` block carrying
`authority: "report-only"` and `maxDispatches: 3`, with `schemaStamped: True`. The repo layer
outranks `~/.claude/crew/config.json` (`plugin/crew/hooks/scripts/crew_config.py:28-31`), so a
global `pm.authority` set AFTER `/crew:upgrade` is dead in every upgraded repo, and `--check-global`
then reports the repo layer as the decider, which reads as a choice the user made. Intersecting the
leaf keys of `default_global_config()` with the leaf keys of an upgraded empty config gives 48 frozen
keys, including `pm.authority`, `qa.order`, `qa.provider`, `dev.provider`, all `guards.*`, and
`install.policy`. `docs.theme` is the one key already handled (it is written as null = "ask the next
authority"; see `_DOCS_THEME_REWRITTEN_FROM`). Fix shape to evaluate: write globally settable keys
absent from the repo as absent/null rather than as the built-in value, and report which keys the
repo pins. Needs a crew version bump and a regression case in the upgrade suite.

### `/crew:upgrade` step 4b treats an absent global file as one finding among six - OPEN

`plugin/crew/commands/upgrade.md:107` lists `absent` alongside the other findings, but on a machine
with no global file (this host: `--check-global` prints `[absent] no global config at
/root/.claude/crew/config.json`) every crew repo whose own config does not set `pm.authority`
resolves to `report-only`. Combined with the freeze above, an upgraded repo is pinned there even
after the user creates the global file. Recommendation: when `absent` coincides with a repo whose
effective `pm.authority` came from built-in defaults, print it as a headline line naming the
effective authority and `/crew:config` as the fix, not as a list item.

### `/crew:upgrade` does not migrate PM spawn or persistence - OPEN (informational)

Nothing in `commands/upgrade.md` or `crew_upgrade.py` touches how the PM is spawned or remembered
(grep: the only `crew-pm` hit is `upgrade.md:262`, about anchor freshness). This is correct as long
as that behaviour lives in the plugin's command/agent text rather than in repo config, so updating
the plugin is the whole migration. Record it so nobody expects `/crew:upgrade` to fix the teammate bug.

### Concurrent PMs can dispatch the same trigger twice - OPEN (filed 2026-09-23, crew 0.20.15 review)

Codex round-2 review of the unnamed-PM change: `FIX|plugin/crew/agents/pm.md:922|The journal
serializes final notes but does not claim work, so concurrent PMs can dispatch the same role against
the same trigger`. Deferred: the old named-PM design prevented this only by "never run two" prose
and a ListAgents check, so it is not a regression of that change. Fix shape to evaluate: a
per-trigger claim file under `.work/` (O_CREAT|O_EXCL, like `pm_pulse.claim`) taken before dispatch.

### Shipped user-guide HTML still instructs a named `crew-pm` teammate - OPEN (filed 2026-09-23)

`docs/guides/crew/crew-technical-reference.html:111` and
`docs/guides/crew/crew-technical-reference-solomon.html:112` say "Standing teammate named `crew-pm`,
reached by `SendMessage`", which contradicts crew 0.20.15. Regenerate those guides; they were outside
the fix's `plugin/crew/` scope.

### Unnamed-PM change (crew 0.20.15): residual Codex round-5 findings, uncommitted diff - OPEN (filed 2026-09-23)

Loop stopped after 5 review rounds by PM decision; raw output in `.work/review/main-pmunnamed-gDjlF3/out.txt`.
- `BLOCK|plugin/crew/agents/pm.md:941|The fixed CREW_EOF delimiter permits heredoc termination and shell-command injection despite quoting` - the doc forbids a line equal to the delimiter but nothing enforces it. Fix shape: a random per-entry delimiter, or a `crew_state.py --append-journal` helper that takes the text on stdin and writes it from Python (removes the shell from the path entirely).
- `BLOCK|plugin/crew/commands/pm.md:31|SendMessage addresses teammates, not resumable unnamed subagents` - PM DISPUTES: this session's harness returned "Use SendMessage with to: '<agentId>' ... to continue this agent" for every unnamed subagent, and code.claude.com/docs/en/sub-agents.md (relayed via claude-code-guide) documents resuming subagents. Not executed end-to-end from `/crew:pm`; verify by hand once 0.20.15 is installed.
- FIX x3 in `plugin/crew/tests/test_pm_unnamed_spawn.py` (:306 comma-joined contradictory clause bypasses the forbidding prefix; :411 quoted-heredoc test does not require a heredoc; :506 post-positioned negation "read in full is not required" passes).

### `crew-technical-reference.docx` / `.pdf` still describe the named `crew-pm` teammate - OPEN (filed 2026-09-23)

The HTML guides were updated for crew 0.20.15 (`docs/guides/crew/crew-technical-reference{,-solomon}.html`),
but the `.docx` and `.pdf` siblings have no generator in the repo (see the earlier "no generator" entry)
and were not hand-edited. `crew:docs-writer` confirmed via `unzip -p ... word/document.xml` and
`pdftotext` that both still say "Standing teammate ... SendMessage ... ListAgents". Regenerate them
from the HTML with doc-builder (Word or LibreOffice) on a machine that has the toolchain.

### `crew:qa-reviewer` fallback is not handed the manifest-built patch - OPEN (filed 2026-09-23, T4)

`plugin/crew/agents/qa-reviewer.md:59` says "Start with `git diff` against the base branch" in prose, and
`/crew:review` step 2c does not pass it `$SCRATCH/diff.txt` or the `review_patch.py` manifest, so the
Claude fallback can still review a committed-only range on a dirty tree. Deferred from T4 (crew 0.20.15)
because a review redesign is being planned separately; fold into that.

### crew 0.20.15 T1-T4: Codex single-round findings, not fixed (filed 2026-09-23) - OPEN

Raw: `.work/review/main-T1-T4-CJlsZC/out.txt`. One round by the user's instruction; nothing below was fixed.
- BLOCK `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1306` - schema-current repos return "already current" before the T2 headline / pinned-at-default report runs. PM confirmed with a copy of this repo's config: output is `already current`. Every repo already upgraded to 0.20.14 therefore never sees either diagnostic. Highest priority of this list.
- BLOCK `plugin/crew/commands/review.md:459` - qa-reviewer fallback is not handed the manifest-built patch (same as the earlier qa-reviewer.md:59 entry).
- BLOCK `plugin/crew/hooks/scripts/pm_journal.py:178` - target not containment-checked; a symlinked `.crew/pm-journal.md` writes outside `.crew/`.
- FIX pm_journal.py: short `os.write` treated as success then source unlinked (:181); forged `## <timestamp>` header lines split entries (:196); 200-line bound not enforced for one oversized entry (:210); shared `.work/pm-entry.md` name races between concurrent PMs (agents/pm.md:946).
- FIX unquoted `${CLAUDE_PLUGIN_ROOT}` paths break on installs with spaces (commands/pm.md:77, commands/review.md:322).
- FIX review.md:34 specialist selection omits committed-only files; review_patch.py:67 decodes with errors=replace (non-UTF-8 bytes altered).
- FIX crew_upgrade.py:470 null pass-through defaults (docs.theme, worktree.root, qa.codex.model = null) falsely reported as pins.

### crew 0.20.15 B1-B3: Codex single-round residuals, not fixed (filed 2026-09-23) - OPEN

Raw: `.work/review/main-B1-B3-W6CLul/out.txt`. B2 drew no finding.
- BLOCK `plugin/crew/hooks/scripts/pm_journal.py:147` - `.crew` as a Windows directory junction is not `os.path.islink()`, so the out-of-repo `.crew` check can be bypassed. UNVERIFIED here (Linux host); reproduce on Windows with `mklink /J`. Fix shape: compare `realpath(root/.crew)` against `realpath(root)` rather than relying on islink.
- BLOCK `plugin/crew/hooks/scripts/pm_journal.py:245` - check-then-open race: swapping `.crew` for a symlink between the check and `os.open` redirects the append; `O_NOFOLLOW` guards only the last component and is 0 on Windows. Needs an attacker with concurrent write access to the checkout.
- FIX `crew_upgrade.py:1321` - report-only (already-current) path prints migration claims ("roles added", "schema 7 -> 7 ... added") for changes it never writes.
- FIX `tests/test_pm_journal.py:216` - no test covers `O_NOFOLLOW`; removing it leaves the suite green.
- FIX `tests/test_upgrade.py:428` - B1 tests call `run()` only; deleting `main()`'s new print path leaves them green.

### crew 0.20.17 (T1) review adapter: deferred, not fixed (filed 2026-09-23) - OPEN

- `plugin/crew/commands/review.md:124` - the bundle base is `git merge-base HEAD <default branch>`, not the ticket's recorded start commit (`hooks/scripts/scope_base.py`). The 04 spec says "committed changes since the ticket base"; they differ when a ticket starts mid-branch. Not in T1's list (0.20.15 owns the base), so left for the lifecycle rebuild. RESOLVED in the T1 review-fix commit: step 1a now takes `scope_base.py --base "$TICKET"`, merge-base only as a named fallback.
- `plugin/crew/hooks/scripts/review_ledger.py:238` - `--accept --by <who>` records who and when but authenticates nothing; any session can accept FINDINGS. Owner identity belongs with T3/T4 approval, not the ledger.
- `plugin/crew/hooks/scripts/review_verdict.py:46` - `READ|<part>` acknowledgements are the reviewer's own claim, not an observation of its file reads. They catch "answered after part 1"; they do not prove reading. A Codex event-stream check of actual reads would be stronger.
- `plugin/crew/tests/review_fixtures.py` - the fake reviewer's Windows `.cmd` shim and the crash test's SIGTERM fallback are UNVERIFIED on Windows (Linux host only).
- `plugin/crew/agents/qa-reviewer.md:237` - the self-derived fallback tells qa-reviewer to emit `NIT|self-derived|...` then `CLEAN`, but `plugin/crew/hooks/scripts/review_verdict.py:96` makes CLEAN beside any finding INCOMPLETE. Only reachable on a direct dispatch with no bundle (step 2c always hands one, via review_run.py), so it did not block the T1 review fixes.

### crew-1.0 T1: round-2 FINDINGS cannot be accepted - OPEN, fix queued with first lane integration (filed 2026-09-23)

After `1a16af5f`, recording FINDINGS on round 2 sets NEEDS_REPLAN immediately, so an owner cannot accept a
round-2 result that is only NIT/FIX. `docs/review/04-redesign.md` says "Exhaustion sets NEEDS_REPLAN";
PM reading (autonomous, taken): exhaustion = budget spent with nothing accepted. Change: round-2 FINDINGS
stays acceptable via `--accept`; NEEDS_REPLAN is entered by a refused third reservation (or an explicit
`--reject`), after which nothing is accepted. `1a16af5f`'s two BLOCK fixes were not Codex-reviewed (two-round
rule); review them with the lane-integration round.

### crew-1.0 T7 (lane A, obsidian-vault 0.4.0) deferred items - OPEN (filed 2026-09-23)

- `plugin/obsidian-vault/hooks/scripts/bridge_status.py:393` still reports `ignore`-role vaults at SessionStart.
- `doctor` does not fail when a second capture hook is registered (04a spec asks for it).
- `plugin/obsidian-vault/agents/gardener.md:27`: unverified whether `${CLAUDE_PLUGIN_ROOT}` is set in the subagent's shell.
- Windows: `.ps1` flavours and the Task Scheduler unit are generated text only, never run.
- Retire after the owner's yes: `skills/claude-memories-vault`, `skills/claude-memories-canvas` (registered), `vault-automation/` (unregistered, tracked).

### crew-1.0 T2 (lane D, additive) deferred items - OPEN (filed 2026-09-23)

- `plugin/crew/commands/review.md` still dispatches `qa-reviewer`; switch to `reviewer` in T4 or with the held deletion.
- `/crew:init` still writes `.crew/config.json` and no hook reads `.crew/crew.json` yet; quickstart tells users to run `/crew:migrate` after init. Cut over in T3/T4.
- Lane D's three sabotage mutations were run by hand, not added to `plugin/crew/tests/sabotage*.py`.
- "`/context` roster <=1.5k tokens" acceptance not measured (char estimate ~1.2k tokens for the four agents).
- Held deletion list (72 paths): `.work/laneD-held-deletions.txt` in lane D's worktree; awaits the owner's yes.

### crew-1.0 T6 (lane B) deferred items - OPEN (filed 2026-09-23)

- `plugin/crew/CONFIG.md:655` needs rows for `memory.recall.vaults`, `memory.recall.maxChars`, `memory.inject`.
- Recall proof ran against a stand-in CLI; re-run with obsidian-vault 0.4.0's real `vault_ops.py recall` after lanes A+B are merged (PM checked the arg contract matches: comma-split `--vaults`, `hooks/scripts/vault_ops.py` in `_CLI_RELATIVE`).
- `.crew/codemap/repo-docs.md` needs an explicit `paths:` line for the rules generator.
- Codex: context delivery to the model and project `profiles` unmeasured ("configured, not proven"); generated `.codex/hooks.json` holds machine-absolute paths.

### crew-1.0 T5 (lane C2, stack skills) note - OPEN

- `crew-terraform` and `crew-lint` kept; 04a suggests folding `crew-terraform` into `stack-terraform` (a removal; needs the owner's yes).

### crew-1.0 T5 (lane C, cloud guard) deferred items - OPEN (filed 2026-09-23)

- `plugin/README.md:414` says the command guard was removed / "18 hook entries"; update when cloud-guard is registered.
- `plugin/crew/README.md:618,975`, `plugin/crew/CONFIG.md:1221-1227` still describe the removed `guard.sh` (pre-existing stale).
- `plugin/crew/hooks/scripts/crew_config.py:2512` (`--guard`) judges `cloudGuard`/`roleWrites` with block/ask/allow and misreports both.
- Terraform `apply` identity comes from provider blocks, not checked; AWS Tools for PowerShell cmdlets not identity-checked.
- `_test/test_flavour_guard.py` only discovers hooks.json-registered scripts; run it against `cloud-guard.ps1` after registration.

### crew-1.0 T7 (obsidian-vault) round-2 FIX items, not fixed (filed 2026-09-23) - OPEN

Raw: scratchpad revA2-LTowwk/out.txt. Two-round budget spent; no BLOCKs.
- `vault_garden.py:212` manual ack accepts a pre-existing note: capture timestamps are minute-precision.
- `vault_garden.py:386` timed-out git command can overrun the deadline ~5 s while termination is awaited.
- `vault_garden.py:415` timeout reported as "not committed" when a hanging post-commit hook ran after the commit.
- `vault_garden.py:447` full-vault snapshot is outside the deadline; processor gets stale remaining time.
- `vault_import.py:147` suffix-collision idempotence fails when the source already carries `imported_from`.
- `vault_import.py:323` dry-run blocked by `outside-vault` exits 0.
- `vault_setup.py:264` any truthy role string (e.g. "archive") passes validation.
- `vault_garden.py` `run_processor` on timeout kills only `claude`, not its children (lane A fix developer).

### crew-1.0 T6 (lane B integration) items - OPEN (filed 2026-09-23)

- `plugin/crew/CONFIG.md:718` says "all 41" repo-only keys; there are 46; table omits `production.databases`/`production.hosts`, lists undeclared `verify.stopBudgetSeconds` (pre-existing).
- `plugin/crew/README.md:2386` hooks-with-no-tool-branch list: wrong count, omits `crew-context`, `platform-sync`, `pm-pulse`.
- Recall proof query came from the last user prompt, not the Agent call (`--no-session-persistence` leaves no transcript); prove the transcript path in a persisted session.
- The proof run left `~/.claude/projects/-tmp-claude-0--repos-personal-useful-claude-add-ons-1acab233-...-proof-project/.../subagents/agent-a74ce527b5ab3e7cb.meta.json` (198 bytes); owner's call to delete.

### `plugin/PLUGINS.md:234` "Bundled skills — 18" vs 19 rows; table lacks the 7 stack-* skills - OPEN (filed 2026-09-23)

### crew-1.0 T2 migrate/status round-2 findings, not fixed (filed 2026-09-23) - OPEN

Two-round budget spent. Raw: scratchpad revD2-YOncm9/out.txt.
- BLOCK `plugin/crew/hooks/scripts/crew_migrate.py:616` parent-directory symlink/junction race between `contained()` and `os.open()`; needs an actor swapping directories inside the repo during a user-run migration. Fix shape: open with `O_NOFOLLOW` via dir fds (`openat`-style) on POSIX; on Windows, re-check the handle's final path after open.
- BLOCK `crew_migrate.py:630` stale-plan check not atomic with `os.replace`; a target created in between is overwritten. Fix shape: `os.link`/`O_EXCL` placement for new targets, compare-and-swap via rename-into-place with a backup of the loser.
- Fix both before recommending `/crew:migrate` outside the owner's own machines.
- FIX `crew_migrate.py:728` rollback leaves a partial staging temp and marks the manifest rolled-back; later applies blocked.
- FIX `crew_status.py:63` `crew.json` containing JSON `null` treated as absent.
- NIT `crew_status.py:152` legacy metrics headers/separators counted as rows.

### crew-1.0 T6 lane B fix follow-ups - OPEN (filed 2026-09-23)

- `role-write-guard.ps1`, `pm-brief.ps1` have the same unbounded python probe the context wrapper had; pm-brief's must match role-write-guard's byte for byte.
- SubagentStart parallel attribution relies on `tool_use_id` in the payload; unverified that Claude Code sends it.
- `scripts/check-powershell.ps1` not run (sandbox refused direct pwsh).

### crew-1.0 T4: `docs/guides/crew/src/README.md:11-12` rows say "(not yet written)" for guides that exist - OPEN (filed 2026-09-23)
- Also: `plugin/crew/commands/review.md` is 552 lines against the 120-line command budget; T8 enforces budgets.

### crew-1.0 T5 cloud guard: residual risk after two review rounds - OPEN (filed 2026-09-23)

The guard parses shell text; two Codex rounds found 8 then 6 parser bypasses. A third pass (lane C fix2) closes
round 2's six without a further review round. Expect more: a text parser cannot model every shell/PowerShell
evaluation path. Posture: ships OFF (`guards.cloudGuard: off`); it is a drift/accident stop, not a security
boundary — cloud IAM and Terraform workspace policy remain the real control. Before recommending `block` mode
widely, run one more independent review round of `cloud_guard.py` on its own.

### crew-1.0 T3 round-2 findings (filed 2026-09-23) - OPEN

Budget spent. Raw: scratchpad revT3b-IQIPVp/out.txt.
Queued for an unreviewed final pass after the T3/T4 integration:
- BLOCK `completion-audit.sh:30` and `scope-guard.sh:33` (and ps1 twins): no-python fallback treats syntactically invalid JSON (`{"scope":{"mode":"off"},}`) as provably off -> fail open. Only a JSON that parses AND says off may be off.
- BLOCK `review_ledger.py:403` successor-plan continuation uses `status()` not `accepted()`, so a `cli` receipt resets NEEDS_REPLAN with allowCliApproval false.
- FIX `approval_hook.py:95` malformed payload containing `crew:approve` exits 0 silently; report the failure.
Accepted risk (stated threat model: guards stop drift and accidents, not a session deliberately forging local state with shell access; Stop audit + review are the backstop):
- BLOCK `scope_guard.py:87` nested `claude -p "/crew:approve T-1"` triggers the user-prompt hook.
- BLOCK `scope_guard.py:87` direct Python API call `crew_ticket.approve(..., via=USER_PROMPT)`.
- BLOCK `scope_guard.py:93` PowerShell `[IO.File]::WriteAllText` into the approval dir.
- FIX `review_ledger.py:430` approval writes don't take the ledger lock (race).
Stronger option if the owner wants approval to be a boundary: sign receipts with a key the session cannot read (e.g. an OS keyring entry written at install), verified by the guard.

### crew-1.0 T3 fix deferrals (filed 2026-09-23) - OPEN
- `scope_report.gate_matches` (verify-gate) still lets `*` cross `/`.
- Every Bash/PowerShell call now starts Python even with `scope.mode: off` when a config exists; add a shell fast path.

### crew-1.0 T3/T4 integration docs drift (filed 2026-09-23) - OPEN, fold into T8
- `plugin/crew/README.md` commands table lacks `/crew:debug`, `/crew:split`.
- `plugin/crew/skills/crew-best-practices/references/contradictions.md:20` says "19 bundled skills" (unmarked).
- `docs/guides/crew/src/README.md` omits `daily-workflow-scope.md`, `memory-recall-proof.md`.

### crew-1.0 T5 cloud guard fix2 follow-ups (filed 2026-09-23) - OPEN
- `plugin/crew/README.md:949-951` describes the old bash stand-down; SQL/help/WhatIf lines less precise now. Check `skills/crew-cloud/SKILL.md` for the same.
- Behaviour change: `psql`/`mysql` commands with backslash literals are refused (every server-mode reading is scanned). Deliberate false positive; revisit with a `cloud.sqlModes` pin if it bites.

### crew 1.0 release follow-ups (filed 2026-09-23) - OPEN
- After the 1.0 PR merges: re-pin both README install URLs to the merge SHA (`git rev-parse HEAD`); T11 changed both install scripts.
- `scripts/_test/drift-detection.sh` not run for T11 (drives the real claude CLI); run by hand before pushing the update path.
- Windows burn-in before the 1.0 PR merges: plan in `.work/windows-burn-in.md` (main checkout), run by the coordinator from a Windows session.

### crew creates `.crew/` in repos that are not crew repos - OPEN, queued after T2 removal (filed 2026-09-23)
- `plugin/crew/hooks/scripts/verify-gate.sh:496` does `mkdir -p .crew` with no crew-repo check; next SessionStart
  `crew_platform.py:522` treats the bare dir as crew and `heal_config` (`:547`) writes a default `config.json`.
  Measured on the owner's vault `/repos/claude-memories` (gardener's `claude -p`). `test_unmanaged_repo_is_left_untouched.py`
  never runs the Stop hooks in a plain repo. Fix + test: no crew hook creates `.crew/`; `crew_platform` requires config.json,
  not a bare dir; honour `CREW_HOOKS=off` (obsidian-vault 0.4.2 sets it for the gardener) in every crew wrapper.
- Owner cleanup (machine, not done): `/repos/claude-memories/.crew/` (config.json, 4 `.hook-*`, 2 `.pm-pulse-*`);
  3 queue items 17:55/17:58/18:01 with cwd `/repos/claude-memories` are the gardener's own sessions — remove before the next drain;
  `vault_ops.py reconcile --apply` acks the 5 already-distilled items.

### crew 1.0 T12-trim: instruction budget (filed 2026-09-23) - OPEN, after T2
T8 measured crew Markdown at 29,148 lines; ~17.8k after the T2 deletions; ~16.3k with the 10 to-trim commands at 120.
The 6,000 target is far off. Ticket: cut the held command/skill allowances in `plugin/crew/.budget-allowance.json`,
prioritising what loads into context (skill/agent descriptions, commands) over on-disk reference files; measure
per-session loaded characters as well as total lines; record both in `BUDGETS.md`. The scorecard prose row stays
**Behind** until this lands. The post-1.0 review decides whether 6,000 is the right target.
Also: wire `scripts/check_instructions.py` into CI once T2 clears its 4 intentional red findings
(`review.md:450,465` qa-reviewer dispatch; README `guard.sh`/`.ps1` citations).

### crew-1.0 auto-cycle (04013a07) follow-ups (filed 2026-09-23) - OPEN
- Integration: the lane changed `handoff-read.{sh,ps1}` to remove only this session's marker; if the T2 removal unregistered handoff-read, move that per-session marker cleanup into `crew_context.py`'s SessionStart path.
- `plugin/crew/hooks/scripts/crew_state.py:473` `read_auto_clear` docstring describes the old Windows targeting.
- `.crew/codemap/crew.md:415-441` cites the unkeyed marker; refresh after 1.0 merges (codemap refresh deferred).
- Windows Terminal tabs share a process; only `windowTitle` narrows it (documented, not enforced).

### crew 1.0 T2 removal follow-ups (filed 2026-09-23) - OPEN
Found while deleting the PM, pulse, journal and retired roles; none blocked T2.
- **Open incident is no longer announced at SessionStart.** `pm_brief.render` printed `EMERGENCY LANE OPEN`; neither `crew_context.py:708` (SessionStart) nor `crew_status.py` reads `crew_incident`. Gates still stand down and log skips. Add an incident line to the context hook's SessionStart items.
- **Dispatch log has no reader.** `crew_state.py:2412` `DISPATCH_LOG_DIR` / `--log-dispatch`: its only consumer was `pm_pulse._dispatch_gap_note`. Now state written to nowhere; retiring it means deleting `tests/test_dispatch_log.py` (needs owner OK - not in the T2 list).
- **`role_write_guard.py:243` keeps the path-scoped `pm` branch** for a role 1.0 no longer ships, and `_UNRESTRICTED_ROLES` is empty. Retire or re-scope the guard in its own ticket with its suite (`tests/test_role_write_guard.py`, ~2,100 lines built around `pm`).
- **Fallback deny mirrors are untested.** `role-write-guard.sh:126` / `role-write-guard.ps1` `$RestrictedRolesForFallback` claim a parity test in `tests/test_role_write_guard.py`; none exists (hand-sabotage: dropping `explorer` from the .sh mirror left the suite green). Pre-existing.
- **All five plugin evals test deleted agents** (`plugin/crew/evals/{pm-*,developer-*,qa-reviewer-*}`), and `scripts/run-plugin-evals.{sh,ps1}` default `EVAL_EXPECTED_FAIL_CASES=pm-does-not-write-code`. Retire or re-target (owner decision; not in the T2 list).
- **`sabotage.py:980` mutation names a test that does not exist** (`test_upgrade_config_adds_the_docs_and_bitbucket_blocks`); pre-existing at ed91114d, not caught by `test_sabotage_harness.py` (it checks anchors, not test names).
- **localgpu docs still name `qa-reviewer` and `/crew:roster`**: `plugin/localgpu/commands/crew.md:105,110,202`, `plugin/localgpu/README.md:283`. Separate marketplace entry; needs its own version bump.
- **`INSTALLATION.md:269` hooks table lists `guard.sh`** (removed in 0.19.52) and omits cloud-guard, approval-hook, scope-guard, completion-audit, role-write-guard, platform-sync. Pre-existing.
- **PM-only state with no consumer**: `crew_state.collect` still emits `schemaDeclared`/`schemaKeyPresent` (`crew_state.py:3008`), and `pm.*` / `context.autoResume` config keys are read only so `/crew:migrate` can carry them to `retired.*`. Kept deliberately for migrate; drop after the 1.0 migration window.
- **`.crew/codemap/crew.md` and `docs/diagrams/`** still describe pm-brief/pm-pulse and the 54-agent roster: `/crew:onboard --refresh crew`. Rendered guide HTML (`docs/guides/crew/*.html`) likewise - T10/owner decision.

### crew-1.0 T8 fix round deferrals (filed 2026-09-23) - OPEN
- `python3 scripts/check-marketplace.py` fails `check_versions` on this branch: "crew: plugin/crew/ has
  changed since version 0.20.25 was set (8dacc525 2026-09-23), but the version was not bumped." Confirmed
  pre-existing on the T8 lane base commit (3244a37e) - reproduces with `git status --short` showing no
  changes under `plugin/crew/` from this fix round. Out of scope here (this round only touched
  `scripts/check_instructions.py`, `scripts/check-marketplace.py`'s `crew-markdown-lines` claim code, and
  `scripts/_test/instruction-budgets.py`); whoever lands the next `plugin/crew/` content change on this
  lane needs to bump crew's version in `marketplace.json`.
- `scripts/check_instructions.py:517-528` (`_body_after_frontmatter`)'s `text.find("\n---", 3)` has the
  same imprecise-substring-match shape as the `_has_frontmatter` bug fixed this round (matches "\n----" or
  "\n--- trailing text" as a closing delimiter) - not fixed here because the finding handed to this round
  named only `_has_frontmatter` (`:180` at the time), and no fixture in this repo currently trips it
  (frontmatter blocks here don't contain a stray "---"-prefixed body line before the real close).

### crew 1.0.1: T2 removal review FIXes (filed 2026-09-23) - OPEN
Codex r1 on ed91114d..c3bd8dfd (modified files), 0 BLOCK:
- `plugin/crew/commands/upgrade.md:314` offers provider pins for deleted `infrastructure-architect`/`planner`.
- `plugin/crew/hooks/scripts/crew_context.py:138` unreadable config or non-boolean `memory.inject` (e.g. `"false"`) runs injection; decide: malformed -> off with a one-line warning.
- `plugin/crew/hooks/scripts/role_write_guard.py:243` retired `pm` still a path-scoped role; an unrelated agent named `pm` is denied ordinary writes.
- `plugin/crew/skills/crew-verification/SKILL.md:37` example assigns SQL changes to the deleted `dba` agent (use `security` or none; stack-sql skill).

### crew 1.0.0 final integration deferrals (filed 2026-09-23) - OPEN
- `docs/guides/crew/src/troubleshooting.md` does not link `auto-cycle.md`; the autocycle lane intended its auto wrap-up/clear/resume section to be reached from guide 5 (`docs/guides/crew/src/README.md` row 5a). Docs only; did not block the merge. — CLOSED 2026-09-23: linked from a new "Auto wrap-up, clear and resume" entry.
- `check-marketplace.py` fails on crew-1.0: "obsidian-vault: plugin/obsidian-vault/ has changed since version 0.4.2 was set (a11d25e6 2026-09-23)". Merging `crew-1.0-T7-drainfix2` (35476f6c) changed the plugin after 0.4.2 was registered. 0.4.2 is not on main (main has 0.3.16), so no installed copy is stale, but the gate stays red until obsidian-vault is bumped (0.4.3): `version_set_at` walks back to the oldest commit declaring 0.4.2, so re-writing the same version does not move it. Kept at 0.4.2 per the integration brief. — CLOSED 2026-09-23: bumped to 0.4.3.
- (1.0.1, final-integration review, raw scratchpad revFinal-FUYx5p) `crew_context.py:842` inject=false fast path skips fit(): long incident id can exceed the startup budget.
- `crew_context.py:843` claim() hash of the raw payload suppresses a second byte-identical compact/clear (banner + handoff) for 24 h.
- `handoff-read.sh:18`/`.ps1:26` missing session_id maps to shared `nosession`; decline cleanup instead.
- `handoff-read.sh:23`/`.ps1:32` seven-day sweep deletes other sessions' markers.
- `handoff-read.sh:44`/`.ps1:57` require legacy `.crew/config.json`; a crew.json-only 1.0 repo with inject=false gets no handoff.

### crew 1.0 guides: multi-line code blocks render with a blank line between every line (LibreOffice, quickstart p1) - OPEN, cosmetic (filed 2026-09-23)
- Seen in `docs/guides/crew/crew-1.0-quickstart.pdf` page 1; likely `<pre>` newline handling in `docs/guides/crew/src/build.py` / LibreOffice Writer/Web.

### Post-1.0: superpowers' systematic-debugging vs crew-debugging - OPEN (filed 2026-09-23, owner request)
Owner: "superpowers' systematic-debugging works great." After 1.0, compare it with crew's `crew-debugging` skill and
`/crew:debug`, then either vendor it (<=120 lines, licence checked — superpowers is MIT — credited in `plugin/crew/NOTICE.md`
like crew-brainstorm/plan/execute) or fold its method into `crew-debugging`. **Do not uninstall superpowers from the
owner's machine until this lands**, or the skill is lost. (The 04-redesign "uninstall superpowers" step waits on this.)

### crew 1.1.0: autopilot - OPEN, do not build before 1.0 ships (filed 2026-09-23, owner decision)
One setting, two levels, default `off`:
- `autopilot: plan` — after the owner approves a plan, `/crew:implement` runs every step, then tests, docs, review and done
  without check-ins. Stops only at AUTONOMOUS_STOPS, prod/cloud writes, a failed gate, an exhausted review budget, or a
  scope change needing re-approval.
- `autopilot: backlog` — `plan` plus: picks the next APPROVED ticket in `.work/tickets` when one finishes; never starts an
  unapproved ticket; per-session caps on tickets and tokens.
Enforced by the same hooks (approval receipts, scope guard, cloud guard, review ledger, completion audit), not prose.
1.0 part (folded into the web-testing lane): `/crew:migrate` maps `pm.authority: autonomous` to a visible note
"autopilot arrives in 1.1.0" instead of dropping it silently.

### crew 1.1.x: platform-native routing - OPEN, after 1.0 ships (filed 2026-09-24, owner decision)
Owner request, filed next to the 1.1.0 autopilot item above because both are "1.0 stops short of this on purpose."
This session did a `.sh`-only pipe-capture fix and left the `.ps1` twin as a TODO per the OWNER RULE (POSIX/bash/
Python/CI only in this repo, Windows/PowerShell product work is win-repo's) - that hand-off is manual today (a
TODO entry someone has to notice and pick up). 1.1.x's job is to make the hand-off a routed, tracked step instead.
- **How the PM learns which peer session runs which OS/shells.** Two candidate mechanisms, not yet decided between:
  a peer registry (sessions register their host OS/shell capability somewhere shared and durable) or a live
  `ListAgents` probe plus self-report (ask what is currently reachable, rather than trusting a stale registry).
  Either way: refs are per-viewer (a session id or branch name one agent can see is not guaranteed resolvable by
  another), so "bare names can be ambiguous" is a real failure mode to design against, not a footnote.
- **Routing rules by file type / test flavour.** `.ps1` files, any test carrying a `[ps1]` parametrize id, and
  Windows-only fixtures (a faked `$env:OS`, a `pwsh`-only skip condition) route to a session that can actually run
  them; POSIX-only work stays local. The rule has to be mechanical (grep-able from a diff), not a judgment call
  each hand-off re-derives.
- **Branch-and-integrate hand-off contract.** No version bumps and no pushes to the integration branch from the
  receiving session - the routed work lands as a reviewable diff, not a fait accompli. Root cause first (this
  repo's `/crew:debug` discipline applies across the hand-off too, not just within one session). Tests that go
  with a routed fix must be sabotage-checked before the hand-off is considered done, the same bar this session
  held itself to for the `.sh` pipe-capture fix and the bash-resolver guard test.
- **Fallback when no native session exists.** Do the work locally anyway rather than blocking on an unavailable
  peer, but label the result "not verified natively" wherever it is recorded (TODO.md, a commit message, a review
  note) - an unlabelled fix that was never run on the platform it targets is indistinguishable from one that was.
- **Acceptance criteria:** a `.ps1`-touching change filed from a POSIX-only session is automatically routed to (or
  flagged for) a session that can run it; a routed fix carries a sabotage-checked test before it is accepted back;
  a hand-off with no native session available still produces a fix, correctly labelled as unverified on that
  platform, rather than sitting un-actioned.

### crew 1.1.x: install the tools crew needs to run tests and do its work - OPEN, after 1.0 ships (filed 2026-09-24, owner decision)
Evidence (win-repo, Windows burn-in, 2026-09-24): `/crew:verify --all` reported two rules as exit 77 SKIP, "environment
absent", because `ruff` and `pylint` could not be imported, and diagnosing the hanging pytest rule needed `pytest-timeout`.
All three were installed by hand, and so were `pytest-xdist` (needed for a full run to finish: 427s with `-n auto`) and
`podman` in WSL2 (for the visual baseline). Today a missing tool silently narrows what a green verify covers.
- Each rule, role or skill declares the tools it needs (in `.crew/verify.json` rules, and in a manifest for everything else);
  for Python tools, name the interpreter that will run the rule.
- A single provisioning step (`/crew:init` phase, plus `/crew:verify --install-missing`) detects what is missing and installs
  it into that interpreter (uv/pip; winget/apt/brew for non-Python), in both a `.sh` and a `.ps1` flavour.
- It must be idempotent: a present tool reports "already installed".
- Every install needs a yes, shown with the exact command. Nothing installs silently from a hook.
Acceptance criteria:
- A fresh Linux and Windows host with ruff/pylint/pytest-timeout absent: `--install-missing` installs them, and a second
  run reports "already installed" for each.
- After provisioning, `/crew:verify --all` reports no exit-77 skips for those rules.
- A declined or failed install leaves the rule as a named SKIP with the reason, never a pass.
- A regression suite covers detect, install, already-installed and install-failed on both flavours.

### crew-1.0 retirement review FIX/NIT (filed 2026-09-23) - OPEN, fold into the web-testing integration
- `README.md:736` Documentation table still links deleted `vault-automation/`.
- `skills/obsidian-canvas/SKILL.md:18` points skill-only installs at `obsidian-memory-contract`, which ships only with the obsidian-vault plugin (repo-plugins row); say so or inline the minimal conventions.
- NIT `plugin/crew/tests/test_docs_routing.py:941` docstring says four guide artifacts; `_GUIDES` has one.
- NIT `scripts/install-prerequisites.sh:2430` comment says 36-skill (now 34); fix in both scripts only if the .ps1 has the same comment.

### crew 1.0 web integration deferrals (filed 2026-09-23) - OPEN
- `plugin/crew/README.md` command table: 32 rows vs 34 claimed; add `/crew:debug`, `/crew:split`.
- `scripts/install-prerequisites.sh:1050` / `.ps1:887` "25-skill item" comment: unclear referent; verify or remove (both scripts).

### crew 1.0 generated-rules gap fix: deferrals (filed 2026-09-23) - OPEN
- `plugin/crew/hooks/scripts/crew_instructions.py` `agents` and `codex` subcommands still have no caller in any command, skill or hook (only `rules` is wired, by `/crew:onboard` and `/crew:migrate`). `docs/review/04-redesign.md` "Codex parity" says hook delivery is probed at init, so `/crew:init` is the likely owner; the spec does not give AGENTS.md to migrate, so this fix did not.
- `docs/guides/crew/src/memory-and-obsidian.md:258` still carries the placeholder line "(written by the context-hook ticket)" under "Confirming recall reaches your sessions"; the rules subsection was added below it, the placeholder is another ticket's.
- `scripts/check_instructions.py` `check_generated_drift` is a no-op for a repo with a code map but no generated rule committed at all (never onboarded on 1.0), so "rules never generated" is not flagged; only drift of rules that exist is. Deliberate for this marketplace repo (no `.claude/rules/`), but a consuming repo gets no signal until its first generation.

### crew 1.0 Windows burn-in fix4: deferrals (filed 2026-09-24) - OPEN
- `plugin/crew/tests/test_context_watch.py`: the Windows burn-in (`docs/review/06-windows-burn-in.md` @ 0d9100bd, 2a) counts 1 failure here but names no test, and this file builds no PATH shim, so the per-flavour PATH fix does not reach it. Needs the Windows failure text; it passes 52/52 on Linux.
- Other tests still join a shim dir with `os.pathsep` and hand it to bash (`plugin/crew/tests/test_debugging_method.py:381`, `plugin/crew/tests/test_verify_gate_stop_gate_record.py:473`, `plugin/crew/hooks/scripts/_test/test_flavour_guard.py:318`, `plugin/crew/tests/review_fixtures.py:77`). Not in the burn-in's failure list (its sweep stopped at `test_crew_metrics.py`), so left alone rather than changed blind; `crew_fixtures.shell_path` / `write_shim` are the helpers to move them to once a Windows run shows them red.
- The shim fix is measured on Linux only: the Windows branches of `crew_fixtures.shell_path` / `write_shim` are unit-tested with `windows=True`, but the 35 Windows fixture failures have not been re-run on a Windows host.

### crew 1.0 burn-in FAIL 3 fix: deferrals (filed 2026-09-23) - OPEN (first two fixed)
- FIXED 2026-09-24 (burn-in fix3 round 2: `type -ap` walks every match; the xfail is now a passing test). Was: `plugin/crew/hooks/scripts/_common.sh:84` (`crew_py_strict`) and `plugin/crew/hooks/scripts/role-write-guard.sh:34` still take only the FIRST PATH match per name, so behind a BROKEN WindowsApps alias a same-named real python is reached by the .ps1 probe and not by bash: blocking hooks can disagree on that host. Pinned strict-xfail in `plugin/crew/tests/test_ps1_python_probe.py`. Not fixed here: walking every match breaks `test_context_watch_python_resolver.py`'s stub fixtures (real PATH behind stubs), which the slow-test lane owns.
- FIXED 2026-09-24 (burn-in fix3 round 2: a 3s watchdog that kills the process group, `taskkill /T` under MSYS). Was: Bash resolvers (`plugin/crew/hooks/scripts/_common.sh:85`, `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:88` and its two twins) have no probe timeout; the .ps1 probe kills a hung candidate at 3s. A hung candidate stalls the .sh until the harness timeout.
- `plugin/crew/hooks/scripts/context-watch.sh:210` / `context-watch.ps1` and `auto-clear` take no per-event claim; both flavours run on Windows. Each is a Stop-time BLOCK (exit 2) with its own session marker, so it was treated as blocking and left in both flavours; whether the marker race lets both block once is unmeasured.
- `plugin/obsidian-vault/hooks/scripts/vault_capture.py:107` dedupes per session by check-then-append (`already_queued`), not O_EXCL: both flavours on Windows can race and queue twice. obsidian-vault cannot import crew's `event_claim.py` (separate install).
- `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:51` says the two other bash wrappers "carry the same naive one-liner"; stale since 2026-09-22, predates this change.
- FIXED 2026-09-24 (burn-in fix3b, Codex r1 finding 3): `crew_py_strict` (`plugin/crew/hooks/scripts/_common.sh`) and its byte-copy `_resolve_role_write_python` (`plugin/crew/hooks/scripts/role-write-guard.sh`) now enforce a version floor -- `sys.version_info>=(3,8) and print(sys.executable)`, folded into the SAME single `-c` argument they already sent, rather than the .ps1 probe's full JSON-proof-of-implementation shape (CPython/PyPy, major/minor as a structured object). That narrower form was deliberate, not an oversight: a second, differently-shaped probe call is exactly what the note below warned would reject dozens of fixtures across `test_verify_gate_python3_shim.py` and `test_context_watch_python_resolver.py` that are narrow shell stubs answering only the ONE literal `-c` string these functions have always sent. Folding the floor into that same string costs nothing extra -- a delegating stub falls through to a real interpreter either way, and a Python < 3.8 now prints nothing (already rejected by the existing `[ -n "$real" ] || continue`). Consequence: this fix does NOT verify CPython/PyPy implementation or reject a version reported as non-integer strings the way the .ps1 probe's structured proof does -- only the version floor the review's reproduction actually exercised (a real Python 3.7). Regression: `test_resolver_rejects_a_proven_python_37` / `test_resolver_accepts_a_proven_python_38` (`test_context_watch_python_resolver.py`, parametrized over both bash copies) and `test_a_proven_python_37_is_rejected_by_both_flavours` (`test_ps1_python_probe.py`, the review's own repro shape).
- `plugin/crew/hooks/scripts/event_claim.py` `event_key`: a Notification or PreCompact payload carries no unique field, so two genuinely distinct invocations with byte-identical payloads inside WINDOW (60s) are still one event (Codex r1 :121). Documented in the module docstring and pinned by `test_a_byte_identical_payload_with_no_unique_field_is_one_event_inside_the_window`; not solvable without a field from the harness that tells the twin's copy from a second event.
- FIXED 2026-09-24 (r3 claims, item F): `plugin/crew/commands/webtest.md:83` and `plugin/crew/skills/stack-web/SKILL.md:72` now carry the `:Z` SELinux relabel `webtest_guard.py`'s `runtime_line()` prints. `plugin/crew/BUDGETS.md:10`'s Markdown line-count claim was recomputed in the same change (17,590 -> 17,596; this ticket owns that claim for this pass), and `plugin/crew/tests/test_webtest_podman.py` gained a regression test pinning both docs against `runtime_line()`'s own flag rather than each other.

### crew 1.0 r3 claims deferrals (filed 2026-09-24) - OPEN
- `plugin/crew/tests/test_map_audit_python_family.py`'s `_pathdir_with` (branch `crew/windows-test-fixes`, commit `8a1a7b8d`) still `shutil.copy2`s a bare `python3`/`python` binary rather than shimming with `exec "$real" "$@"` against `sys.executable`. On native Windows this fails at process start (`api-ms-win-crt-heap-l1-1-0.dll` missing, since `python.exe` loads its runtime DLL from its own directory) and, separately, `shutil.which` can resolve to a Microsoft Store App Execution Alias that cannot even be read to copy. Not ported here: item G's brief named three specific ports (cygpath POSIX form, the `os.access` precondition, `.cmd` shims in `build_fixture()`) and this file's fix was not among them; it passes 4/4 on Linux, where the defect cannot reproduce, so it is unverified either way in this session.

### crew 1.0.7 deferrals (filed 2026-09-24) - OPEN
- (a) crew 1.0 has two repo config files and no single authority: `crew_config.py`, auto-clear and `crew_autocycle` all read `.crew/config.json`; `crew_migrate.py --apply` writes `.crew/crew.json` (schema 1) and keeps `config.json` "retireable" (`plugin/crew/hooks/scripts/crew_migrate.py:11` names the two-file table, `:461` builds the migration plan against `.crew/config.json`, `:471` appends `.crew/config.json` to `plan["retireable"]`); `crew_status.py` reads `.crew/crew.json` (`plugin/crew/hooks/scripts/crew_status.py:63`); `crew_config.py` reads `.crew/config.json` directly for production-declaration checks (`plugin/crew/hooks/scripts/crew_config.py:1158`) and disagrees with `crew_status.py` about which file is the live one. Needs an owner decision which file is authoritative; not decided in this release integration because it is a cross-cutting design call, not a merge-caused defect.
- (b) the same unbounded stdin read G1 fixed in `verify-gate.ps1` (bounded via `OpenStandardInput()` + `CopyToAsync().Wait(5000)`) remains, in one of two shapes, across the rest of the carriers. Literal `[Console]::In.ReadToEnd()` (identical hang risk, unfixed): `plugin/crew/hooks/scripts/promote-gate.ps1:16`, `plugin/crew/hooks/scripts/context-watch.ps1:29`, `plugin/crew/hooks/scripts/handoff-read.ps1:178`. Already moved to a raw-byte stream read for OEM-codepage reasons, but that read (`$stdinStream.CopyTo($memStream)`) is still synchronous and unbounded, so the same hang remains under a different call shape: `plugin/crew/hooks/scripts/role-write-guard.ps1:193`, `plugin/crew/hooks/scripts/cloud-guard.ps1:204`, `plugin/crew/hooks/scripts/notify.ps1:304`, `plugin/crew/hooks/scripts/handoff-write.ps1:276`, `plugin/crew/hooks/scripts/crew-context.ps1:192`, `plugin/crew/hooks/scripts/completion-audit.ps1:184`, `plugin/crew/hooks/scripts/scope-guard.ps1:186`, `plugin/crew/hooks/scripts/approval-hook.ps1:185`. (`grep -n 'Console\]::In' plugin/crew/hooks/scripts/*.ps1` finds all eleven; the three literal ones are the only true `[Console]::In` hits, the rest are the comment on the same line explaining why they moved off it.)
- (c) `plugin/crew/tests/test_gate_command.py:56` (`shutil.which("bash")`) and `plugin/crew/tests/test_stack_skills.py:86,94` (bare `"bash"` in `_KIND_TOOLS` and `shutil.which("bash")`) resolve bash by bare name; neither has been re-checked against Windows `WinError 2` (bash not on PATH / found but not launchable the way `CreateProcess` needs). Not reproduced or fixed here — out of scope for this release integration, which found it while auditing bash-resolution landmines, not by running on Windows.
- (d) toast notification for auto-clear's `notify` on Windows is out of scope: no reliable toast API is reachable from a console process without registering an `AppUserModelID`, so `notify` stays a Stop-hook `systemMessage` only rather than a native OS toast.

### crew 1.0.10 deferrals (filed 2026-09-24, release integration / #224 residue) - OPEN
- `plugin/crew/tests/test_verify_gate_lock_window.py:299` (`test_each_flavour_honours_a_deadline_the_other_published`) still uses a fixed `time.sleep(6)` after starting the holder gate, then asserts the holder is still alive and reads its token/deadline once. `origin/todo/xdist-and-codex-profile-tickets` (99f69732, "the sibling sleep race") found and fixed the identical race on the 0.20.x line: both the deadline-exists and the token-older-than-TTL premises are timed from when the gate ACQUIRES the lock, not from `Popen`, so a slow fork/exec (bash.exe/pwsh startup) can land the fixed sleep before either publishes, sabotage-confirmed there by stubbing `lock_extend` to a no-op (26.84s, "deadline=False token age=0.56"). Not ported here: out of scope for STEP 2c, which asked specifically about `Resolve-CrewBash`; this is a different test in a different file, on the same general "fixed sleep races gate startup" theme as the STEP 1 W-a merge's own deterministic-TTL fix already in this tree (`test_a_rule_longer_than_the_ttl_keeps_its_lock`), which does NOT have this gap.

### crew 1.0.8 deferrals (filed 2026-09-24, Group 3 / crew_autoclear_setup.py) - OPEN
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py:107` (`_require_global_readable`) reads and validates the machine-global config file, then `write_autoclear_method`/`write_autoclear_enabled`/`apply_onlyRepos_narrowing` immediately call into `crew_config.write_global_config` (`plugin/crew/hooks/scripts/crew_config.py:2503`), which does its OWN independent second read via `plan_global_write` -> `read_global_config` (`crew_config.py:2416`, `:680`) rather than reusing the already-validated parsed object. `read_global_config` silently collapses a malformed file to `{}` by its own documented contract (needed for `resolve_config`'s never-raise promise from a SessionStart hook), so a TOCTOU window exists: if the file is corrupted between the validating read and the write's own re-read, the guard's validation is stale and the write can proceed against the `{}` collapse it exists to prevent. Not fixed here: closing it correctly needs `crew_config.py`'s write path to accept a pre-parsed base object instead of re-reading `path`, which is a `crew_config.py` API change reaching every other caller of `write_global_config`/`plan_global_write` (`pm.authority`, `install.policy`, etc.) - out of scope for a `crew_autoclear_setup.py`-scoped fix, and risky to make without dedicated review of those call sites. The window is already minimal (no I/O happens between the validating call and the write call in any of the three functions above).

### crew 1.0 auto-clear owner-stub revert deferral (filed 2026-09-24) - RESOLVED on `crew-1.0-win-tabcheck` (2026-09-24)
- `a5008632` (auto-clear.ps1: stub the owner-process lookup for fake test pids) was reverted at `a408ba54`: Codex found `CREW_AUTOCLEAR_OWNER_STUB` lets any environment falsify the window owner and bypass the WindowsTerminal tab-safety check, and an empty/unset stub value was treated as a known non-WT owner. `plugin/crew/tests/test_auto_cycle.py::test_the_window_is_identified_uniquely_or_not_at_all[title-one-ps1]` is now `xfail(strict=True)` (dynamically applied via `request.node.add_marker`, since the shared `_WINDOW_CASES` list also feeds `test_resolve_target_table`, which does not exercise the ps1 owner check at all) with reason "owner lookup seam: tracked for win-repo, see TODO". win-repo needs a test-only seam that production `auto-clear.ps1` cannot honour, so the CI matrix's `title-one` case (a uniquely-resolved fake pid, e.g. 999999, with no real backing process) can pass the window-uniqueness check without also tripping the real, unrelated `Get-Process` owner-safety decline. Not designed here: the seam's shape (env var vs. some other test-only hook) and whether it should live in test fixture code only or need a narrower production hook are win-repo's call per the OWNER RULE.
- **Resolved without any production seam.** Added a `_real_foreign_pid` pytest fixture (`plugin/crew/tests/test_auto_cycle.py`) that spawns a real, short-lived, non-ancestor process and swaps its genuine pid in for the fabricated `999999` in the `title-one` case only. `auto-clear.ps1`'s owner-safety `Get-Process` call then resolves a real process for real, and the `xfail(strict=True)` marker was removed — `test_the_window_is_identified_uniquely_or_not_at_all[title-one-ps1]` now passes genuinely (verified: 8/8 ps1 cases in `_WINDOW_CASES` pass under `--run-slow`). `CREW_AUTOCLEAR_OWNER_STUB` was not reintroduced anywhere in production code. Closed by `263e33ce` (`crew-1.0-win-tabcheck`).

## The verify gate's own tests race each other under `-n auto` - OPEN 2026-09-24

`plugin/crew/tests/test_verify_gate_stop_gate_record.py:1043`
(`test_22_a_missing_verify_record_refuses_to_sync...`) renames the shared
`verify_record.py` **in place** - no copy, no lock - so any xdist worker running
another test against that module at the same moment sees it missing.
`test_16_a_skip_after_a_pass_deletes_the_stale_fingerprint` (`:850`) and
`test_39_subshell_parentheses_still_defer` (`:1398`) are its measured victims.

Measured on `obsidian-vault/windowsapps-resolver` @ `2f359231`:

| How it was run | Result for this file |
|---|---|
| `pytest plugin/crew/tests/ -q -n auto` | **17 failed** (of 43 suite-wide) |
| `pytest plugin/crew/tests/test_verify_gate_stop_gate_record.py -q` | **88 passed, 0 failed** in 327s |

**Priority: ordinary. This is a test-suite defect, not a gate-evidence defect.**
An earlier draft of this entry argued it should come first, on the grounds that
the verify gate's own regression evidence could not be believed. That was wrong:
`.crew/verify.json` rule[8] is `python3 -m pytest plugin/crew/tests/ -q` -
**serial**, no xdist - so the gate never runs the suite the way that produces
these failures, and its evidence was never affected. Do not "fix" the gate for
this.

The damage is narrower and worth stating exactly: anyone who runs the suite the
fast way and reads the failure count as a defect count gets a number that is
wrong by 17. Both a human and an agent did precisely that on 2026-09-24 and
reasoned about the gate from it.

**It is also not crash-safe, which is worse than the race.** Observed
2026-09-24: a run killed part-way through left
`plugin/crew/hooks/scripts/verify_record.py` **deleted** from the working tree
with `verify_record.py.hidden-for-test` beside it, because the rename is
in-place and teardown never ran. Every subsequent run - serial included - then
died at collection:

```
ERROR collecting plugin/crew/tests/test_verify_gate_stop_gate_record.py
E   ModuleNotFoundError: No module named 'verify_record'
```

So an interrupted run does not merely lose its own result, it corrupts the
checkout for the next one. The hidden file was byte-identical to `HEAD` (modulo
line endings), so recovery is `git checkout --` plus deleting the stray, but
nothing announces that this is what happened.

FIX: give `test_22` its own copy of `verify_record.py`, or take a lock around
the rename. A copy fixes both halves - the race and the crash-safety - and a
lock fixes only the race. Scoped to this mechanism only; the entries below are
different mechanisms and must not be folded in.

## `test_verify_gate_lock_window.py`'s sleep-based assertions are host-timing dependent - OPEN 2026-09-24

Separate mechanism from the rename race above. Four failures under `-n auto`,
from assertions that a lock holder is still running after a fixed `sleep`
(`plugin/crew/tests/test_verify_gate_lock_window.py:142`, `:222`, `:280`).
Worker CPU contention breaks the assumption; they pass serially.

One of the four is **not** an xdist artifact and reproduces serially:
`test_a_zero_prefixed_ttl_is_decimal_and_still_publishes_a_deadline[sh]`
(`:613`) measures 12-16s against a `<=10s` expectation, because the first
`lock_extend` fires ~3s after process start on this Windows/Git-Bash host
(`plugin/crew/hooks/scripts/verify-gate.sh:487`). That is real fork/exec
overhead, not a calculation bug - the test encodes a host-speed assumption.

FIX: host-relative slack, or measure the interval rather than wall-clock.

## `test_verify_gate_python3_shim.py`'s PATH override is shadowed by Git Bash - OPEN 2026-09-24

Separate mechanism again, and not a race - it reproduces serially.
`test_the_cygpath_branch_is_taken_when_cygpath_is_present`
(`plugin/crew/tests/test_verify_gate_python3_shim.py:618`) puts a fake `cygpath`
on PATH, but Git Bash/MSYS unconditionally prepends `/usr/bin` - which holds the
real `cygpath.exe` - ahead of the override, so the test exercises the real
binary and never reaches its own branch. Proven by direct `subprocess.run`
repro.

FIX: PATH isolation that survives the MSYS prepend, or invoke the shim with an
explicit interpreter path rather than relying on lookup order.

## rule[8] does not terminate: one test hangs the gate, and the harness has no timeout - OPEN 2026-09-24

**This is why the crew verify marker cannot be written.** Not the two red tests
that were fixed in `e0278bc9` - `python3 -m pytest plugin/crew/tests/ -q`, which
is `.crew/verify.json` rule[8] verbatim, cannot be run to completion on this
host at all.

The hang:
`plugin/crew/tests/test_verify_gate_stop_gate_record.py:438::test_1_crlf_from_native_python_does_not_leak_an_inherited_credential[ps1]`.
90-second repro: `timeout 90 python -m pytest <nodeid> -q` exits 124, having
printed one dot - `[sh]` passes, `[ps1]` hangs. Reproduced on a **provably
quiet machine** (0 other gate processes, 0 concurrent suites): 0.00s of CPU
across 90s with the child still parked, stalling at the same 95% point as a
contended run. So it is a defect, not contention.

**CAUSE CORRECTED 2026-09-24, and the first answer was wrong.** This ticket
originally blamed `verify-gate.ps1:235`'s unconditional
`[Console]::In.ReadToEnd()`. That is not it. The real mechanism, established by
reproducing each step rather than by reading:

`Resolve-CrewPython` accepts the first PATH match for `python3`/`python` that
`Get-Command -All` reports as `CommandType: Application`. On Windows
`Get-Command` reports an **extensionless** file matching that bare name as an
Application too. This test plants exactly such a file - a CRLF shebang stub -
on PATH. `Resolve-CrewPython` returns the stub, and PowerShell's `&` has no
shebang support, so invoking it blocks forever. That is why the fixture's
`.crew/` held the lock and `verify.json` but neither record file: the gate
reached record-sync and never returned.

`[sh]` does not hang **by construction**: `crew_py_strict`
(`plugin/crew/hooks/scripts/_common.sh:82`) executes and probes each candidate
(`"$candidate" -c 'import sys; print(sys.executable)'`) and strips `\r`. Bash
runs a shebang script natively, so the stub forwards to the real interpreter and
the probe unwraps it to the real path.

The stdin reads are a **separate latent fragility**, not this bug: with stdin
left as a never-closed pipe both flavours park forever, and every spawn in the
suite closes stdin. Recorded because it was the leading theory twice and is
still worth its own fix someday.

FIXED in `31e1451c` by a shared `Test-CrewWindowsExecutable` guard - the
extension must be in `$env:PATHEXT` - applied to both `Resolve-CrewPython` call
sites and to `Resolve-CrewBash`'s PATH fallback. **The identical unguarded
pattern remains in `pm-brief.ps1`, `role-write-guard.ps1`,
`platform-sync.ps1` and `pm-pulse.ps1`** - reported, not fixed, and worth its
own ticket.

The remaining half, still worth doing:
**The harness could not notice, and that was the more valuable fix.** `:479`
spawned the gate with `capture_output=True` and **no `timeout=`**, which is what
converts a blocked gate into a non-terminating suite instead of one red test.
Fixed in `6cfe69e7` with `timeout=120` (the value already used for a full gate
invocation elsewhere in this suite), failing with a message naming the flavour.

**Nine sibling `test_verify_gate_*.py` files have the identical gap** and were
deliberately left alone to keep that commit scoped to the file that hung
rule[8]. They are the next occurrence waiting to happen, and they are a
mechanical fix.

**Correction, recorded so it does not reach anyone as a cause.** An earlier read
of this - mine - was that the `.ps1` flavour specifically blocks while `.sh`
does not. That holds for this test, but not as a general mechanism: an A/B probe
with stdin left as a never-closed pipe parks **both** flavours forever, because
the `.sh` blocks on the same read. Every spawn in the suite does close stdin, so
that is a separate latent fragility, not this bug. The stdin-inheritance family
is the same one as `codex exec` hanging on inherited stdin.

Locating method, worth reusing: `verify-gate.ps1:563` builds its lock token as
`ps1-$PID-...`, so grepping the pytest tmp tree for `ps1-<pid>-` names the
fixture directory, and pytest names fixture directories after the test.

## The generated `.codex/config.toml`'s `profiles` are ignored at project level - OPEN 2026-09-24

Found during the crew 1.0 Windows burn-in. Codex says so on **stderr every
run**, and the generated file itself already flagged this as UNVERIFIED.

`[profiles.review]` declares a read-only sandbox. At project level that profile
is **not applied**, so a reviewer launched with `--profile review` runs under
whatever the *user* config says - measured as `workspace-write` in the burn-in
run.

**Why this is its own ticket and not a line in another one.** The whole value of
a separate reviewer is that it is independent of the thing it reviews. A
reviewer that believes it is read-only and is in fact able to write the
workspace can modify the code it was asked to judge, and nothing in the run says
otherwise - the warning is on stderr, which nobody reads on a green run. This is
the same shape as the guard that stood down silently: a restriction that is
declared, believed, and not in force.

Related but distinct, from the same burn-in and NOT to be folded in:
`commandWindows` **does** fire in `codex exec` - only the PowerShell branch ever
ran, the bash one never did - but it needs **both** project trust and hook
trust, and Codex prints no warning when either is missing. That makes
`codex-probe`'s "configured, not proven" promotable to "proven" for
`SessionStart` and `UserPromptSubmit` on 0.154.0.

FIX: do not rely on a project-level profile for the reviewer's sandbox. Either
pass the sandbox explicitly on the command line, or verify at launch that the
profile took effect and refuse to review if it did not - a reviewer that cannot
confirm its own restriction should fail closed, not proceed.

### Local object store has 24 empty object files; branch `gizmoduck-ci-f2-fix` is unreadable - OPEN (filed 2026-09-24, PM)

Measured by the PM on 2026-09-24 at main bc6a3a09: `find .git/objects -type f -empty | wc -l` = 24, and
`git rev-parse refs/heads/gizmoduck-ci-f2-fix^{commit}` fails (`object file .git/objects/81/b347ba... is empty`).
`git fetch origin` aborts on it (`fatal: bad object refs/heads/gizmoduck-ci-f2-fix`), so origin refs in this
checkout are stale until it is fixed. `git ls-remote origin 'refs/heads/gizmoduck-ci*'` returns nothing, so
that branch's commits exist nowhere else. No other local branch ref is broken. Deferred, not repaired: every
repair (deleting the ref, pruning, `git gc`) destroys history and needs the owner's yes; the gizmoduck-ci
work itself lives on `gizmoduck-ci` @ 3966cb5f per the 2026-09-24 handoff. Do NOT run `git gc`/`prune`
before deciding. The empty files are most likely the result of a crash or a full disk mid-write; that cause was not verified.
Update 2026-09-24: crew:developer found no intact copy anywhere on this machine (packs, all worktree reflogs, and the
only other clone at `/root/.claude/plugins/marketplaces/useful-claude-add-ons`). The last reachable commit on that line is
`9aab4d38` (`gizmoduck-ci-f2`); the ref moved to 81b347ba without a reflog entry. All 24 empty objects have mtimes within
one ~3 s window (1790224088-1790224091), so this looks like a single batch truncation, cause not investigated. `git fetch
origin` still fails (exit 1) with or without `--negotiation-tip`. The ref delete is waiting on the owner's direct confirmation.
Update 2026-09-24: the owner chose "recover, then delete"; with no copy found, the ref was deleted (`git update-ref -d`),
and `git fetch origin` then exited 0. Still OPEN: the 24 empty objects remain and their cause is uninvestigated; there has been no gc/prune.

### Stopped PM left 15 uncommitted edits in worktree `crew-1.0-burnin-fix4` - OPEN (filed 2026-09-24, PM)

`.claude/worktrees/agent-a1576883b4819735f` (branch `crew-1.0-burnin-fix4` @ 72e9dead) is `locked` by
pid 2363532, which is no longer running; `git status --porcelain` shows 15 modified paths under `plugin/crew/hooks/scripts/`,
`plugin/crew/CONFIG.md` and `docs/guides/crew/src/`. This is most likely the partial burn-in fix work the
2026-09-24 handoff says to check before re-dispatching FAILs 1-7. Nobody has reviewed it. Whoever picks up the burn-in fixes should start from it rather than starting over.

### CLAUDE.md still lists `skills/intune-graph/scripts/export_report.py:90` as a live landmine - OPEN (filed 2026-09-24, PM)

crew:explorer reported on 2026-09-24 that 60c79407 (PR #210) fixed it (`_download` now stages writes through `mkstemp` and
`os.replace`, `skills/intune-graph/scripts/export_report.py:136-243`). CLAUDE.md's truncating-`open` landmine still calls
this "the live one" and says three unfixed files remain. Relayed, not re-read by the PM. A developer should re-run the AST scan that
paragraph describes and correct the count. Deferred because CLAUDE.md is not the PM's to edit and the codemap refresh did not depend on it.

### win-repo hand-offs from the merge/pipe-capture/test-hygiene pass (filed 2026-09-24) - OPEN

- `plugin/crew/hooks/scripts/verify-gate.ps1` twin of the `.sh` pipe-capture fix (`verify-gate.sh`, this session):
  when the per-rule output-capture temp file cannot be created, `.sh` now tries a second, repo-local location
  (`.crew/.verify-rule-out.XXXXXX`) before refusing the rule with a named reason, and reads back at most a
  1MiB-capped, size-snapshotted amount rather than the whole file. `.ps1`'s equivalent capture
  (`verify-gate.ps1:~1586`, a `Get-Content`-based read of a growing tempfile per this file's CLAUDE.md landmine
  entry) has neither: no repo-local fallback location, and no cap on a rule that legitimately writes a lot or
  backgrounds a continuously-writing grandchild. Not ported here per the OWNER RULE (POSIX/bash/Python/CI only
  in this repo; Windows/PowerShell product work is win-repo's).
- `plugin/crew/tests/test_auto_cycle.py:~287`
  (`test_context_watch_stdout_reaches_eof_promptly_even_with_a_long_delay`) deliberately spawns a REAL detached
  sender with `delaySeconds=30` to prove the hook's own stdout reaches EOF promptly despite it (a 5s read
  deadline), which is exactly what the test needs - but it does not reap the sender afterward, so the fake
  `tmux` shim's `sleep 30` keeps running for up to 30s past the test's own return, untracked. Not fixed here:
  scoped to this session's POSIX/pytest-hygiene pass, and the fix shape (capture and kill the sender's pid, or
  accept the leak as bounded and cheap at 30s) is a product-test call for whoever owns `test_auto_cycle.py`'s
  fixtures next, cross-referenced from `crew_fixtures.gate_processes` becoming autouse this same session (which
  does not cover this file - it only auto-tracks `popen_gate`/`run_gate` spawns, and this sender is launched a
  different way).

### pytest's own keep-3 temp-dir retention is defeated on Windows - OPEN (filed 2026-09-24, win-repo burn-in evidence)

`D:\temp\pytest-of-<user>` held 59 `pytest-N` directories (roughly 24k files/dirs total) on a Windows burn-in
host, when pytest's documented default keeps only the 3 most recent per base-temp root and removes the rest at
the start of the NEXT run. Not investigated here (POSIX/bash/Python/CI scope this session, and the cause is a
Windows-specific accumulation): candidates include a process holding a handle open in an old numbered dir
(Windows will not let pytest delete a directory an earlier PowerShell/git-bash child is still using, unlike
POSIX where an open-but-unlinked file is silently reclaimed later), a CI/test run that never let pytest reach
its own cleanup pass (killed instead of exiting), or `--basetemp` usage bypassing the keep-3 accounting entirely
for some runs while leaving others on the default root. Whoever owns this should first confirm which of those it
is before choosing a fix - deleting old directories blind, without knowing why they survived, risks deleting one
still legitimately in use.

### test_verify_gate_stop_gate_record.py is slow on Windows - not a hang, filed for visibility (2026-09-24, win-repo burn-in evidence)

463.61s wall time on a quiet Windows box, 2 failed / 89 passed. Distinguishing "slow" from "hung" matters here
because this repo's own CLAUDE.md has a lesson about exactly that confusion (a failing gate names the failure,
not the cause) - a bare "it took 463s" read next to `_GATE_TIMEOUT = 120` in the same test module could look like
a regression to the non-terminating-gate bug that constant's own comment describes, when it is not: 463s is the
sum of many sub-120s-bounded gate spawns across the whole file, not one gate that never returned. The 2 failures
are not itemised here (this entry exists to record the timing and the "not a hang" distinction, filed by win-repo
burn-in; the failures themselves need their own triage by whoever has the Windows host to reproduce them).

### win-repo hand-offs from Codex review, 2afa08df..8585c57d (filed 2026-09-24)

- `auto-clear.ps1:~729` - the WindowsTerminal tab-safety check runs BEFORE the configured delay elapses, so
  switching tabs during the delay window (after the check passed, before `/clear` actually sends) can send
  `/clear` to whatever tab is now focused rather than the one the check verified. Re-check tab ownership AFTER
  the delay, immediately before sending, not only before it.
  Re-checked after merging `263e33ce` (`crew-1.0-win-tabcheck`, 2026-09-24): still open. The tab-count/UIA
  decision (`Get-CrewWindowsTerminalTabState` / `Get-CrewSendKeysTabDecision`, `auto-clear.ps1:718-720`) runs in
  the parent, before `Start-Sleep -Seconds $Delay` (`:794`) hands off to the detached child. The child re-checks
  only `[CrewAC.Win]::GetForegroundWindow().ToInt64() -ne $Hwnd` against the exact window handle (`:804`) -
  a per-WINDOW check, not per-tab. A tab switch inside the same Windows Terminal window during the delay leaves
  the foreground window handle unchanged, so this re-check cannot catch it; 263e33ce hardened the pre-delay
  decision (multi-tab now never sends) but did not add a post-delay tab re-check, so the gap this entry names is
  unchanged.
- `test_ps1_python_probe.py:~93` - the `.cmd` stubs this test builds make the bash-parity cases hand a POSIX
  `/c/...`-style path to a native Windows `CreateProcess` call, which cannot resolve it. Needs either a
  path-translation step before the native call, or a test-only seam that supplies the Windows-native form to
  that specific code path without changing what production code receives.
- `crew_fixtures.py:~69` (`kill_process_group`'s Windows branch, `taskkill /T /F`) cannot find descendants once
  the direct child has already exited - `taskkill /T` walks the process tree from the still-running parent, and
  a parent that already exited leaves no tree to walk, the same gap this session's POSIX `killpg`-regardless fix
  (above, this same TODO pass) closed for `os.killpg` but did not - and per the OWNER RULE did not attempt to -
  close for Windows.
- `verify-gate.ps1:~1586` - a continuously-writing background process keeps `Get-Content` reading a growing
  tempfile, the `.ps1` counterpart of the `.sh` size/time cost this session's `verify-gate.sh` fix addresses
  (measured there: an uncapped read of a multi-GiB file took double-digit seconds and several GiB of RSS). Same
  fix shape likely applies - snapshot a size, cap the read - but is win-repo's to implement and verify on a real
  Windows host per the OWNER RULE.

### Windows burn-in families A and C - CLOSED, already fixed at `85dfa4a7` (filed 2026-09-24)

Searched this file's full history (`git log --all -p -- TODO.md`) and found no entry ever filed under the
literal names "family A" or "family C" - the letters name mechanisms in a burn-in report
(`docs/review/06-windows-burn-in.md` at `84f32325`, branch `crew-1.0-burnin-win-485a1b08`, never merged into
`crew-1.0`) rather than tracked TODO items here. Recorded here so nobody re-opens either as new:

- **Family A** (the auto-clear log armed whenever `.crew/` exists, independent of opt-in): the current tree
  gates on `enabled` FIRST and silently (`plugin/crew/hooks/scripts/auto-clear.ps1:137-141`, `Off is checked
  FIRST and silently`); the underlying home-directory bug that produced the burn-in's false read of "armed"
  (`[Environment]::GetFolderPath('UserProfile')` ignoring an overridden `$env:USERPROFILE`/`$env:HOME` on
  native Windows and reading the real machine config instead of the test's isolated one) is fixed at
  `auto-clear.ps1:132` and already present at `85dfa4a7`. A static regression tripwire (no env-var trick can
  reproduce the original bug on a Linux `pwsh` host) guards it:
  `test_auto_clear_ps1_resolves_home_from_the_env_not_the_shell_api`, `plugin/crew/tests/test_auto_clear.py:220`.
- **Family C** ("no matching terminal window" under pytest - the harness has no such window, not a product
  defect): not separately tracked, and correctly so per the burn-in report's own read (`Under pytest there is no
  such window, so this is the harness, not the product`).

### crew 1.0.x deferral: tests hardcode `windows=` against `crew_autocycle.normalise_repo_path`, contradicting the real host - OPEN (filed 2026-09-24, measured by win-repo-2)

Family E (win-repo-2's own burn-in triage, not the lettering in `docs/review/06-windows-burn-in.md` above).
Five tests call `crew_autocycle.normalise_repo_path` (and, through it, `in_scope`) with `windows=False`
literally, hardcoding POSIX rules regardless of the host the suite actually runs on:
`test_posix_repo_paths_normalise_to_one_form` (`test_auto_cycle.py:1409`),
`test_in_scope_does_not_collapse_backslash_and_slash_on_posix` (`:1427`/`:1428`),
`test_a_trailing_space_in_an_only_repos_entry_does_not_authorise_the_bare_path` (`:1444`/`:1445`),
`test_a_drive_letter_path_is_not_absolute_on_posix` (`:1455`/`:1456`), and
`test_normalise_repo_path_resolves_a_dotdot_after_a_symlinked_component` (`:1500`, `:1502`-`:1503`). On a real Windows
host these do not take the Windows branch at all: `normalise_repo_path` only resolves `os.name == "nt"` when its
caller leaves `windows` at the default `None` (`crew_autocycle.py:223`, `windows = os.name == "nt" if windows is
None else windows`), and every one of these five tests passes `windows=False` explicitly - so on a real Windows
host the POSIX rules run anyway, against path shapes and a filesystem that production would only ever have
reached through the Windows branch. That host/flag mismatch is what returns `""` (or an unresolved path,
for the symlink test) instead of the value each test asserts, not the Windows branch misreading a POSIX-shaped
input.

**Not a product defect.** Production never passes `windows=` at all: `plan()` (`crew_autocycle.py:526`) calls
`in_scope(cfg, root, session_id)` with no `windows` argument, so it always resolves against the real host via
the same `os.name == "nt"` default, and `in_scope` fails CLOSED on the `""` `normalise_repo_path` returns for an
unresolvable path (`if not here or here not in listed: return False`) - the narrowing simply declines rather
than misbehaving. The defect is entirely in the five tests asserting a platform contract they then contradict
by fixing the platform flag to the wrong value for the host they're run on.

Fix shape: these tests must derive `windows` from the real host (`os.name == "nt"`, matching production's own
default) rather than hardcoding `False`, or run the POSIX-shaped assertions only under a POSIX-forcing fixture
that also verifies the host actually is POSIX. Not designed here - the fixture shape is a test-suite call, not
a merge-caused defect, and is why this is filed as its own deferral rather than fixed inline.

## crew 1.0.x: Windows-only CI fixture failures (windows-latest, run 36086569186)

Filed from a full classification pass over all 48 failed node ids in that run. Fixed inline (non-.ps1,
cheap, safe, each with a test, all re-verified green on this pass): `review_run.py:118`'s `launch()` now
spawns in its own process group/session and kills the WHOLE tree on
timeout (`CREATE_NEW_PROCESS_GROUP` + `taskkill /T /F` on Windows), closing the same
"kills the direct child only, not the grandchild holding the pipe" shape already fixed for
`crew_fixtures.run_gate` - this is what made `test_run_timeout_is_incomplete` block until the *test
harness's* own 120s safety timeout instead of `review_run.py`'s own `--timeout 2`; `review_prompt.py`'s
five `os.path.relpath` call sites now go through a new `_relpath()` that forces forward slashes, closing
`test_build_falls_back_to_the_files_mode_ticket`'s `os.sep`-dependent `"(from .work\\tickets\\T9.md)"` vs
`"(from .work/tickets/T9.md)"` mismatch (prompt text is read by a reviewer model, not a shell, so a
platform-native separator was never the right shape on either host); `test_scope_guard.py`'s
`test_dotdot_through_a_symlink_resolves_where_the_os_does[module]` now asserts `0 if os.name == "nt" else
2` instead of a bare `2` - `role_write_guard._resolve_real_target` is DELIBERATELY platform-dependent for
this exact symlink+`..` shape (its own docstring, and `test_role_write_guard.py`'s
`@needs_windows`-guarded `test_windows_link_pointing_out_of_scope_with_dotdot_still_allows_bash` already
assert the Windows answer is ALLOW), and the test had never branched on host, so the failure was a test
bug, not the security regression it looked like; `test_webtest_scaffold.py`'s two default-behaviour tests
now force `os.name = "posix"` before calling `main()` - `--windows`'s own default is `os.name == "nt"`
(deliberate, confirmed by forcing `os.name = "nt"` locally and reading `.mcp.json`: it really does wrap
every MCP entry in `cmd /c` on that host, exactly what the CI failure showed), and these two tests were
asserting the un-wrapped shape unconditionally; `test_approval_hook.py`'s `[sh]` case used a hardcoded
`"/bin/bash"`, which doesn't exist on Windows at all (`FileNotFoundError [WinError 2]`) - now resolves
through the same `crew_fixtures.resolve_bash()` the rest of this suite already uses, with the same
skip-if-none guard the `ps1` case already has; `test_crew_instructions.py`'s `fake_codex` fixture wrote
only a bare POSIX shebang script with no extension, which Windows cannot execute at all (`CREW_CODEX_BIN`
names it verbatim - `_codex_bin()` only searches PATH/PATHEXT when the env var is unset), so
`codex_probe` correctly reported "unknown (could not run \`codex features list\`)" instead of "enabled" -
now also writes a `.cmd` companion (`review_fixtures.fake_reviewer_bin`'s already-established shape) and
points `CREW_CODEX_BIN` at whichever one `os.name` says will run.

**Not fixed, deferred** (Windows-only, or requires touching a file this ticket does not own):

- `test_review_ledger.py::test_run_reserves_before_launch_so_a_crash_still_spends_the_round` - the fake
  reviewer's crash simulation (`review_fixtures.py`'s `_FAKE`, mode `"crash"`) signals
  `os.kill(os.getppid(), SIGTERM)`, assuming its parent IS `review_run.py`. On Windows, launching the
  `codex.cmd` shim makes `cmd.exe` the direct child and the fake reviewer a GRANDCHILD, so
  `os.getppid()` names `cmd.exe`, not `review_run.py` - killing it never reaches the orchestrator, which
  then runs to completion and records `"completed"` instead of leaving the round `"reserved"`. Fixing
  `review_run.py`'s own timeout handling (done above) does not touch this: it is the crash-simulation IPC
  itself that targets the wrong process on Windows, not `review_run.py` behaving incorrectly. Needs
  `review_fixtures.py` to hand the fake reviewer `review_run.py`'s own PID some other way (an env var set
  before spawn, not `getppid()`).
- `test_approval_hook.py::_no_python_env` still hardcodes `/usr/bin`/`/bin` when assembling a "bash's own
  tools, no python" PATH (`test_approval_hook.py:145-151`) - real on POSIX, but Git-for-Windows' coreutils
  live under its own install tree, not those paths, so this fixture may still misbehave on Windows even
  after the `/bin/bash` fix above. No shared "find bash's sibling coreutils dir on Windows" helper exists
  in this codebase yet (the natural home, `crew_fixtures.py`, is outside this ticket's file list); needs a
  test-only Git-for-Windows install-tree locator, not attempted here.
- `test_completion_audit.py::test_a_filename_with_newlines_cannot_add_lines[module]` - creates a real file
  whose NAME contains `\n`/`\r`. NTFS's own filesystem API rejects that at `write_text()` time
  (`OSError: [Errno 22] Invalid argument`) - there is no code fix; the scenario this test reproduces
  (a maliciously newline-named path, which git itself can track) cannot be materialised as a real file on
  Windows at all. Windows-only, permanently, not a fixture bug to chase.
- The whole `test_auto_clear.py`/`test_auto_cycle.py` `[sh]` family (`tmux is not on PATH`, `xdotool is not
  on PATH`, and the knock-on `"the detached sender's bash was never invoked"` /
  `"could not be confirmed as the pane running this session"` failures downstream of that refusal): these
  tests exercise the `tmux`/`xdotool` auto-clear delivery methods (the `ps1`/WindowsTerminal method has
  its own, separate cases). **Root cause NOT confirmed here, flagged rather than guessed at**: the stub
  mechanism these tests use (`test_auto_clear.py:_stub` -> `crew_fixtures.write_shim`) already writes a
  `.cmd` twin specifically so a native Windows python can find it via `shutil.which`, so a naive
  "the stub has no Windows form" explanation (the shape of every OTHER fixture bug fixed in this pass)
  does not fit here without reading further - either windows-latest genuinely has neither tool on PATH
  (plausible, not checked against the runner image), or `auto-clear.sh`'s own tmux/xdotool
  availability check does not accept a `.cmd` shim the way `crew_py_strict`/`vault-guard.sh`/
  `role-write-guard.sh` were each hardened to accept one (in which case this is `auto-clear.sh`, not a
  test fixture, and NOT owned by the excluded-file list). Left uninvestigated under this ticket's time
  budget rather than mischaracterised either way; win-repo-2 should confirm on a real runner before
  assuming which.

  **Narrowed (runs 36106846833/36106851305), classified FIXTURE, still not confirmed on a real Windows
  host**: `test_config_values_survive_a_crlf_writing_python[sh]` (both `--session`-flavoured `tmux`
  cases) and `test_a_window_title_containing_spaces_survives_config_parsing[sh]` both fail with
  completely empty stdout, and the check that decides `tmux`/`xdotool` availability is NOT in
  `auto-clear.sh` at all - it is `crew_autocycle.py:497`/`:510`'s bare `shutil.which("tmux"/"xdotool")`,
  run inside the native-Windows python child `auto-clear.sh:103` execs, not by bash. So "auto-clear.sh's
  own check doesn't accept a `.cmd` shim" (this entry's second guess above) does not apply - there is no
  separate check to harden. The remaining candidate is the PATH itself: `crew_fixtures.shell_path("sh",
  [bindir])` builds a POSIX (`/c/...`), colon-joined PATH for bash to search, correctly and provably (bash
  itself resolves stubs built this way elsewhere in this same file without issue) - but `shutil.which` in
  this case runs in a python.exe CHILD process bash execs, which needs PATH back in native `;`-joined,
  backslash form to search it at all. Whether Git Bash's process-exec boundary reconverts a POSIX PATH
  back to native form for that child is exactly the open question this entry could not settle from a
  Linux sandbox; `test_a_method_that_cannot_verify_its_target_refuses_without_a_title[sh]` failing in the
  SAME two runs with the literal stderr `"method xdotool but xdotool is not on PATH"` - despite building
  its stub through the identical, already-correct `shell_path`/`write_shim` pair - corroborates that the
  shim is not reaching that child on this runner image, but does not distinguish "PATH round-trips
  wrong" from "the runner image lacks the tool" without a real Windows host to test against. Both named
  tests reproduce (pass) cleanly on Linux, which is consistent with a Windows-only PATH-propagation gap
  and inconsistent with either test asserting a live product regression in the tab-parsing or CRLF
  handling each claims to cover.
- `test_auto_cycle.py::test_in_scope_decides_the_scope_matrix_with_no_subprocess_on_every_os` - a NEW
  instance of the already-filed "Windows burn-in family E" entry above (hardcoded `windows=False` fed to
  `crew_autocycle.in_scope`, contradicting the real host), not previously named in that entry's five-test
  list. Same root cause, same fix shape, same owner (win-repo-2); not re-filed as a separate entry.
- `test_ps1_python_probe.py` (`test_a_working_windowsapps_alias_is_accepted_like_bash_accepts_it`,
  `test_a_broken_alias_falls_through_to_a_real_python_of_another_name`,
  `test_bash_strict_agrees_on_a_same_named_python_behind_a_broken_alias`,
  `test_the_burn_in_host_audits_in_both_flavours_instead_of_blocking_in_one`) - already filed above
  (`test_ps1_python_probe.py:~93`, this file, "Blast radius" section preceding the burn-in families): the
  `.cmd` stubs this test builds hand a POSIX `/c/...`-style path to a native Windows `CreateProcess` call,
  which cannot resolve it. Not re-filed.
- `test_verify_gate_stop_gate_record.py::test_34b_a_backgrounded_grandchild_holding_stdout_does_not_wedge_the_gate[ps1]` -
  already-known PRODUCT (verify-gate.ps1 B3), win-repo-2's, `.ps1`, not touched here.
- `test_verify_gate_stop_gate_record.py::test_34d_a_second_mktemp_failure_refuses_rather_than_wedges` -
  **root cause now confirmed FIXTURE, not product** (runs 36106846833/36106851305). The test shadows
  `mktemp` on PATH with a counting stub by building its own env as
  `PATH=str(py3_dir) + os.pathsep + str(stub_dir) + os.pathsep + os.environ.get("PATH", "")` -
  `os.pathsep` is `;` on Windows, and this is the ONLY PATH-shimming construction in this file (or in
  `test_auto_clear.py`) that does not route through `crew_fixtures.shell_path("sh", [...])`, the
  POSIX-converting helper every other Windows-covering test in this suite uses for exactly this reason.
  Reproduced directly on Linux: `bash -c 'PATH="/a;/b" command -v x'` never finds a stub in either `/a`
  or `/b`, because bash's own PATH search always splits on `:`, never `;`, regardless of host OS - a
  raw semicolon-joined PATH is one bogus directory to it. CI corroborates: the gate ran to completion in
  1s with `env pinned` and the rule output logged normally, as if every `mktemp` call succeeded - not
  the named refusal (`cannot create an output-capture file`) the sabotage is supposed to force. The
  product code this test targets (`verify-gate.sh:1600-1703`, the TMPDIR-then-`.crew/`-fallback-then-
  refuse sequence) matches its own docstring's description exactly, so there is no source-level gap to
  fix - only the test's own PATH construction. `test_run_gate_kills_the_whole_group_on_timeout_not_just_the_direct_child`
  was not re-investigated this pass (unrelated mechanism, no new evidence gathered) and remains as filed
  above - its assertion message's missing `f` prefix is still a live, separate test bug in the same file.

## verify-gate: own and reap each rule's descendants (job object / cgroup / process-group with a verifiable owner) - descoped from 1.0 after 5 review rounds; see CHANGELOG 1.0.21

Per-rule process-group tracking and kill-on-signal shipped across
1bba9725/71021c7f/4d235881/671832f1/484eeebf/af5cadd2, and five consecutive
review rounds each found the previous round's fix one case short. Removed
from crew 1.0 rather than attempted a sixth time; `CONFIG.md`'s
`verify.stopBudgetSeconds` section states the resulting limitation in one
line. The failure modes those rounds found, so whoever picks this back up
does not re-discover them one at a time:

- **Disk fill by an orphan writer.** A rule that backgrounds something and
  never waits on it itself kept appending to the gate's own (already
  unlinked) capture file after the rule was recorded PASSED, unbounded,
  until the disk filled.
- **Escape on gate kill.** Job-control shells commonly re-group themselves
  once `set -m` runs, which can take the rule's own tracking subshell out
  of the gate's process group too - signalling the gate's whole group from
  outside then killed the gate while a still-running rule survived it,
  unbounded.
- **An unlocked registry.** The shared cleanup registry and its
  TERM/INT/HUP/EXIT traps were defined only inside the locked branch, so a
  run that never took the lock at all had no registry and no traps to
  catch a signal with - "command not found" on stderr, and no cleanup ran.
- **pid/pgid reuse in both p- and g-mode.** A bare pid or process-group id
  recorded once can be freed by the OS and handed to an unrelated process
  by the time the cleanup trap fires; signalling it by bare number without
  re-proving ownership first can reach whatever the OS gave it to next.
- **A session-id proof that is not ownership.** Proving a `g`-mode id
  shares this gate's own session id rules out a `setsid`-created
  replacement, but a session id is a weaker claim than "this gate created
  this specific group," and the five rounds never closed that gap fully.
- **Leader-exited groups.** A rule's own process group can empty the
  instant its tracking subshell's `wait` returns (every member already
  exited), which frees that pgid for reuse before the cleanup trap even
  runs.

Whoever reopens this should reach for something with a verifiable owner
from the start - a Windows job object, a Linux cgroup, or a process group
whose creator can be re-proven at signal time by more than a session id -
rather than re-deriving pid/pgid ownership proofs from `/proc` and `ps` by
hand, which is what cost five rounds here.
### verify-gate.ps1 B4 fix (pipe-fallback): three pre-existing test failures on this host, unrelated to the fix - OPEN (filed 2026-09-25, win-repo)

Fixing B4 (`plugin/crew/hooks/scripts/verify-gate.ps1:1601`-area: a failed temp-file creation fell back to a
bare pipe capture, restoring the background-grandchild hang) surfaced three tests that are RED on this host at
**unmodified** `836a6646` too - confirmed by `git stash`-ing the fix and re-running each in isolation, same
failures, same numbers:

- `test_34b_a_backgrounded_grandchild_holding_stdout_does_not_wedge_the_gate[ps1]` -
  `plugin/crew/tests/test_verify_gate_stop_gate_record.py:1433`. Took 21.9s against its own 10s bound for a 20s
  background sleep. The PRIMARY (working) temp-file capture path - unrelated to the pipe-fallback branch this
  ticket fixed - already waits out a backgrounded grandchild's full lifetime on this host; a minimal repro
  (`& $bashExe -c $c > file 2>&1` with no fallback logic in play at all) reproduced the same bounded wait, so
  this is not the pipe wedge - it looks like a console/process-group inheritance quirk in how PowerShell here
  invokes `bash.exe`, orthogonal to file-vs-pipe capture. Not diagnosed further or fixed - the mechanism that
  would fix it is the per-rule process-group kill (`verify-gate.sh`'s `1bba9725`), which this ticket's brief
  explicitly forbade porting to `.ps1`.

  **CORRECTED 2026-09-25 (B3, sha `7d8a0002`, then amended): the paragraph above was wrong about there being
  no fix without the kill.** The wedge was never in the pipe-vs-file choice - it is that PowerShell's own
  `>`/`2>&1` redirect operators on a native command relay the child's output through a PIPE PowerShell itself
  manages (not a raw OS file handle), so a grandchild that merely inherits that pipe wedges the relay
  regardless of file-vs-pipe capture. Handing the rule command to bash through an env var and letting bash's
  own `eval "$CMD" > "$OUT" 2>&1 </dev/null` do the redirect gives the child a real file handle - measured
  8073ms -> 90ms on the identical repro this entry used, no process-group kill involved. `test_34b[ps1]` is
  green as of that commit. See `verify-gate.ps1`'s comment beside the `elseif ($ruleOutFile)` branch for the
  full mechanism and measurements.
- `test_34d_a_second_mktemp_failure_refuses_rather_than_wedges` - `:1646`. sh-flavour only
  (`@pytest.mark.skipif(_BASH is None...)`, no `flavour` parametrization, never touches `.ps1`); red before and
  after this ticket's `.ps1`-only change, so unrelated to it by construction.
- `test_run_gate_kills_the_whole_group_on_timeout_not_just_the_direct_child` - `:2063`, in
  `crew_fixtures.run_gate` itself (test harness code, not `verify-gate.ps1` or `.sh`). Also red unmodified.

None of the three blocked B4: the regression test added for that ticket
(`test_34d_ps1_a_temp_dir_failure_falls_back_to_crew_not_a_pipe`, same file, immediately after `test_34d`) is
green and was sabotage-confirmed red on the reverted code. Filed rather than fixed at the time because
root-causing the console/process-group behaviour behind `test_34b[ps1]` was excluded from that ticket's scope -
it was B3's, and is now fixed there (see the correction above). The other two bullets
(`test_34d_a_second_mktemp_failure_refuses_rather_than_wedges`, sh-only;
`test_run_gate_kills_the_whole_group_on_timeout_not_just_the_direct_child`, test-harness code) are unaffected
by B3 and remain open, unrelated to either ticket by construction.

Also noted, not fixed: `verify-gate.ps1:814` (the legacy `_verify/smoke.sh`/`scripts/smoke.sh` fallback, used
only when `.crew/verify.json` does not exist) captures via an unconditional bare pipe
(`$out = $null | & $bashExe $smoke 2>&1`) with no temp-file attempt and no `.crew/` fallback at all - a
different, unscoped pipe-capture site from the per-rule loop this ticket fixed. Same wedge shape, no
mitigation, not touched here.

## crew 1.0.x: deferred review findings at crew 1.0.24 (filed 2026-09-25, PM)

From the Codex delta reviews of integ-ps1 (gpt-5.6-sol, high, read-only). None blocked the 1.0 merge gate; handoff detail in `.work/ps1-blocks-for-win-repo-2-round3.md` (local).
- `plugin/crew/hooks/scripts/verify-gate.ps1:1684` - the transport variables that carry the rule command/output path into bash (`CREW_VERIFY_RULE_*`) stay visible to every rule, so a rule inspecting them behaves differently under the .ps1 flavour than under verify-gate.sh. Unset them inside the bash command before `eval`; add a parity test.
- `plugin/crew/hooks/scripts/verify-gate.ps1:1722` - the capped tail read seeks from the LIVE end of file (`Seek(-$readLen, End)`), not from the snapshotted `.Length`, so a leftover background writer still appending replaces the snapshot window with newer bytes. Still bounded (not a hang). Seek to `$snapshotLen - $readLen` from Begin, mirroring the .sh size snapshot + `tail -c`.
- `plugin/crew/hooks/scripts/verify-gate.ps1:1736` - a zero-byte partial read produces two NUL bytes because `$buffer[0..($totalRead - 1)]` with `$totalRead = 0` is `0..-1`. Special-case 0; check the file for the same idiom elsewhere.
- `plugin/crew/hooks/scripts/auto-clear.ps1` - the parent claims the one-shot `.crew/.autoclear-sent-<key>` marker BEFORE it spawns the sendkeys child, so a child that fails to start or to bind its parameters consumes the session's only attempt without typing anything. Pre-existing; claim in the child after it has verified and typed, or release the claim on child failure.
- `plugin/crew/tests/test_auto_clear_review_fixes.py:730` (Windows-only test) - the binding test's false case uses `Hwnd=0`, which equals `GetForegroundWindow()` when Windows returns NULL (locked/headless session), so the child reaches a real `SendWait` and could type `/clear` into another application. Use a real, known non-foreground window handle (or skip the false case when GetForegroundWindow() is 0).
- `plugin/crew/tests/test_verify_gate_stop_gate_record.py:1803` - the no-bash skip uses `crew_fixtures.resolve_bash()`, a different discovery algorithm from verify-gate.ps1's `Resolve-CrewBash` (which walks up from git.exe), so a Git for Windows install with only its `cmd` dir on PATH silently skips this test. Skip based on the gate's own `-PrintBash` result instead.

## sabotage.py's own aggregate run has the same SKIPPED-vs-PASSED gap (filed 2026-09-25)

`plugin/crew/tests/sabotage.py:2928` folds `AUTOCYCLE_MUTATIONS` into its own `MUTATIONS` tuple and
re-runs every entry through its own independent `run_test`/`main` (`plugin/crew/tests/sabotage.py:2945-3253`),
which still checks only `done.returncode` and has no SKIPPED-vs-PASSED distinction. So the
"Get-CrewChildTabRecheck skips the post-delay tab check again" entry (Windows-only target test) would
still misreport as "STILL GREEN -- TEST IS VACUOUS" under `python3 plugin/crew/tests/sabotage.py` on a
non-Windows host, the same bug this ticket fixed in `sabotage_autocycle.py`'s own harness. Not fixed here:
`sabotage_autocycle.py` does not import `sabotage.py`'s harness code (no shared function, only the
`AUTOCYCLE_MUTATIONS` tuple is imported the other way), so the ticket's "if sabotage_autocycle uses it"
condition for touching `sabotage.py` was not met, and running the full `sabotage.py` suite was outside this
ticket's required checks (only `sabotage_autocycle.py` was named). Left open for whoever owns `sabotage.py`.

## crew 1.0.x: sabotage/structural coverage gaps found reviewing crew 1.0.25 (filed 2026-09-25, PM)

From the Codex delta review of 3299d386..b780563d (gpt-5.6-sol, high, read-only). Test coverage only; the product code these tests guard is correct at 1.0.25.
- `plugin/crew/tests/sabotage_autocycle.py:~607` - by design (1.0.25), a mutation whose target test SKIPS on this host is reported SKIPPED and does not fail the run. Cost: on Linux the Windows-only child-tab-recheck mutation is unproven while the suite still prints PASS. Make the aggregate line say how many mutations were SKIPPED (e.g. "PASS (1 skipped: unproven on this host)") so an unproven mutation is visible, never silent.
- `plugin/crew/tests/test_auto_clear_child_tab_recheck_structure.py:~57` - the Linux structural twin only asserts the IsWindowsTerminal guard is the first statement; an unconditional `return @{ Decision = 'send'; Reason = '' }` placed right AFTER the guard stays green. Assert that the only `Decision = 'send'` return in Get-CrewChildTabRecheck is the tab-count == 1 branch (parse returns, not one literal spelling), and add that mutation to sabotage_autocycle.
- `plugin/crew/tests/test_verify_gate_bash_empty_refusal.py:~138` - the branch-order check still raises a bare ValueError (from `chain.index(..., guard_pos)`) before its explanatory assertion when the `elseif ($ruleOutFile)` marker moves before the guard; check presence/order with an assertion first.
---

## Deferred by the PM, assign pass 2026-09-24 (10 dispatches, authority autonomous)

### `/crew:verify --all` and the stale verify marker - DEFERRED (cost + standing veto)
Marker is 75 commits behind HEAD. NOT run this pass: `rule[8]` alone measured 1928s and
`test_verify_gate_stop_gate_record.py` about 750s; a full pass would consume the session. Independently,
the PM's standing file already records the user's 2026-09-24 ruling that the marker is never written over
the two known-red host-specific tests. So this stays deferred until those two are fixed AND a session has
the budget for a >2000s run.

### `ticketsTooLarge` trigger (health.rate 5.33 over 6 tickets) - DEFERRED, not actionable as stated
The metric counts BLOCK+FIX per ticket, which rises with review thoroughness as readily as with scope, and
`health.rate` is a REPO-WIDE average that is not evidence about any individual ticket. Splitting an old
ticket would not clear the trigger either - the rate falls when future tickets are smaller. No action taken.
Revisit if the rate keeps climbing across the next several tickets.

### Per-path triage of the 7 `knowledgeBehind` codemap notes - BLOCKED on a tool gap, not on the work
Two `crew:explorer` dispatches could not run `git diff --name-only <anchor>..HEAD -- <paths>` at all:
that role has no `Bash` and no `ctx_*` tools ("Bash is disabled for this session, in subagents as well as
here"). Re-dispatch to a shell-capable role. Groundwork already done and worth reusing:
- Every codemap anchor is written `useful-claude-add-ons@<sha>`. Passing the whole token to `git diff`
  returns a SILENT FALSE ZERO. Strip to the bare sha.
- Six of the seven share anchor `5d1fc5fd`; only `obsidian-vault.md` differs (`60c79407`). So this is TWO
  diffs, not seven.
- Cited-path sets were already extracted per note (see the PM journal entry for this pass).
- `verification-harness.md` has 31 citations into `.crew/verify.json`, which is gitignored and absent from
  the checkout, so a path diff on it comes out empty regardless - roughly a third of that note is not
  verifiable by this method at all.

### `INDEX.md` anchor column has drifted again - OPEN (filed 2026-09-24, PM)
`.crew/codemap/INDEX.md:104` lists `skills-security-ops.md` as `ea8a014`; that note's own `anchor:` line
(`.crew/codemap/skills-security-ops.md:2`) reads `bc6a3a09`. Relayed by crew:explorer, not re-read by the PM.
INDEX.md itself says this column must be re-derived mechanically or not at all. Fourth recurrence.

### Per-path verify of the 2 stale diagrams - BLOCKED on the same tool gap
Both `data-flow-crew-config` and `process-crew-brief` ARE anchored (`useful-claude-add-ons@60c79407`,
2026-09-22) - neither is unanchored. `crew_freshness.py:129` strips the `<repo>@` prefix itself, so the tool
is immune to the trap a human pasting the raw token is not. Line-citation spot-checks came back clean for
`process-crew-brief` (hypothesis: CURRENT DESPITE THE LAG, do not redraw) and clean for
`data-flow-crew-config` EXCEPT `role_write_guard.py`'s force-block citation, which shifted by one
(diagram says :811-812, actual :812-813) - commit `25c6b9d4` sits between the anchor and HEAD. Likely a
targeted edit to one node in the `Corrupt` subgraph, not a redraw.

### Item 3 (Windows Terminal tab check) - the ticket changed shape mid-pass, needs a FRESH brief
`origin/crew-1.0` advanced `2afa08df` -> `85dfa4a7` during this pass. Upstream commit `d12670c7` already
contains nearly the whole agreed design. The remaining delta is a CONFLICT, not an absence: upstream also
sends into a multi-tab window when a shell-set tab name matches `windowTitle` and reads as selected, which
the settled design explicitly forbids (tab names are shell-set; there is no tab-to-pid mapping). Prepared
patches are in the session scratchpad under `item3/`. Do not re-run the UIA investigation - it is done.

### Family C production fix - OPEN, highest-value unstarted item
`auto-clear.ps1:114` uses `[Environment]::GetFolderPath('UserProfile')`, which ignores an overridden
`USERPROFILE`/`HOME`, so the hook reads the real machine's `~/.claude/crew/config.json` under test. Accounts
for burn-in families A and C (21+ tests). Sibling `cloud-guard.ps1:162` already does the correct
`$env:USERPROFILE`-else-`$env:HOME` fallback; `crew_autocycle.py:70` does too. Measured, not relayed.
Already fixed on `origin/crew-1.0` (`562d13a1`, `394a98f3`) but NOT on `main`.

### Third auto-clear bug, distinct from families A-E - OPEN
`crew_autocycle.normalise_repo_path` (`crew_autocycle.py:192`) returns `''` for a real Windows directory;
5 tests in `test_auto_cycle.py` fail on pure in-process calls to it and `in_scope` (`:134`) with no
subprocess, window or config involved. Needs its own root-cause pass - it was hidden inside the burn-in's
"no terminal window" umbrella.

### Two new burn-in families, sha `3f347d52` - OPEN
Report at the session scratchpad, `burnin-3f347d52.md` (55 failures over 19 files). Family F: a
`subprocess.communicate(timeout=2)` that does not actually bound the call on Windows/Python 3.14 (verbatim
thread-join trace in the report). Family G: 10 assorted first-hand failures - `npx`/`cmd` wrapping, a
terraform/PSScriptAnalyzer rule not enforcing its own exit code, missing ticket content in a built prompt,
and a python-probe resolver returning empty in several fallback scenarios.

### Five new burn-in families, sha `2f7f71f7` - OPEN
Report at the session scratchpad, `burnin-2f7f71f7.md` (51 failures, every one attributed by nodeid).
F: a test fixture writes an unescaped Windows backslash path into TOML (verified with a `tomllib` repro).
G: `.ps1 -PrintPython` returns empty, including its own regression-guard test. G2: the resolver returns a
different real interpreter than the test's ground truth. H: `npx` wrapped in `cmd /c`. I: auto-clear
scope-matrix path normalisation. Plus 12 measured failures whose mechanism is not confidently diagnosed.
Family A is absent at this sha; family E did not reproduce.

### Exit-127 group is NOT one root cause - OPEN
`test_stack_skills.py:93` uses a bare, unproven `shutil.which("sh")` - the only one of the five files with
that pattern - reproduced live as `rc=127` where `77` was intended. `test_crew_instructions.py` has zero
subprocess calls, so a whole-file 127 there can only be the outer pytest launcher. The relayed
gizmoduck `test_powershell_rule_exits_nonzero_on_a_real_analyzer_violation` rc=0 claim is CONFIRMED, but it
is a different test node and does NOT explain the 127s.

### Stray file in the repo root - NEEDS AN EXPLICIT YES BEFORE DELETION
A dispatched role wrote a file whose NAME is a literal Windows path
(`D<colon>tempclaude...item3_base-auto-clear.ps1`) into the repo root - a path-quoting bug in that role, not
a repo defect. It is untracked. The PM did not delete it; deletion needs the operator's yes.

---

## PM assign wave 2, 2026-09-24 - status corrections and new deferrals

### `repospersonalcrew-1.0-win-fixtures/` is NOT debris - DO NOT REMOVE
`git worktree list` confirms it is a REGISTERED git worktree on branch `crew-1.0-win-fixtures` @ `2afa08df`,
whose path lost its drive separators (`C:\repos\personal\...` collapsed to `repospersonalcrew-...`). It reads
as an untracked directory in `git status --porcelain` and is not. Removing it is a git-destruction stop and
needs its own explicit yes from the operator. No role may touch it. Filed at the operator's instruction.

### A crew version bump is OWED and is not ours to make - RELAY TO THE CREW SESSION
After the item-2 rebase, `py scripts/check-marketplace.py` reports:
`crew: plugin/crew/ has changed since version 1.0.12 was set (85dfa4a7)... Bump it in marketplace.json.`
Standing constraint: the crew session owns bumping and Codex review, so this must be relayed rather than
fixed here. Per this repo's own CLAUDE.md the cost of shipping without the bump is invisible locally -
`claude plugin update` compares the declared version, so every machine that already installed it keeps the
old copy forever and reports "already at the latest version".

### CORRECTION to the wave-1 entry above: `.crew/verify.json` is TRACKED, not gitignored
Measured by an analyst via `git ls-files`, refuting a claim the PM put in its own brief. CLAUDE.md's
un-ignore list carries `!.crew/verify.json`. It changed +2/-2 between the anchor and HEAD (`seconds` 185 ->
1928, `why` text rewritten). So the earlier note that "roughly a third of verification-harness.md is not
verifiable by this method" is FALSE - a per-path diff does see that file. Do not repeat the caveat.

### CORRECTION to the wave-1 entry above: the `data-flow-crew-config` off-by-one is PRE-EXISTING
The stale citation is real - node `FORCE`, diagram line 157, says `role_write_guard.py:811-812` where the
actual is `:812-813`. But it was NOT caused by commit `25c6b9d4`: that commit touched only
`role-write-guard.ps1` and `.sh`, never `role_write_guard.py`, which has ZERO diff to HEAD. Measured. The
fix is a one-line citation edit, not a redraw, and it does not need a codemap pass first.

### Codemap re-derive budget - only ONE note is actually worth it
Measured per-path diffs against bare `5d1fc5fd` / `60c79407` (the `<repo>@<sha>` prefix stripped - passing
the whole token returns a silent false zero):
- CURRENT, do NOT re-derive: `install-scripts.md`, `mcp-servers.md` (both empty diffs).
- NEEDS RE-DERIVING, ranked by lines changed: `crew.md` (5890 over 51 files) > `verification-harness.md`
  (2252, `.crew/verify.json` + 20 test files; `check-marketplace.py` itself unchanged) > `repo-docs.md`
  (1685, but dominated by generated docx/pdf/html - the real prose delta is CHANGELOG.md, 3 `.mmd`
  diagrams, 7 new `docs/review/*.md` and `docs/runbooks/rollback.md`) > `obsidian-vault.md` (279) >
  `marketplace-registration.md` (8 lines, `plugin/PLUGINS.md` only).
`crew.md` is the only one where the re-derive cost is clearly justified. `marketplace-registration.md` is an
8-line touch-up.

### `process-crew-brief` diagram - CONFIRMED CURRENT, do not redraw
Per-path diff against bare `60c79407` touches only `role-write-guard.sh`/`.ps1` and `.crew/verify.json`, and
the diagram's own lines 9-10 pre-declare those as resolver hardening with `hooks.json` unchanged - confirmed,
`hooks.json` is not in the diff. Close the `diagramsStale` trigger for this one without work.

### Windows review owed on the 11-way ps1 resolver copy - NOT YET ACTIONABLE
While integrating win-stdin, the crew copied the `RedirectStandardInput` + `Close` probe change VERBATIM into
the other 10 `.ps1` hook scripts to keep the resolver block byte-identical across all 11. It was validated on
Linux only (`test_ps1_python_probe` 47/47 there). Needs a Windows review once it is on origin. Held, not
dispatched - 6 PM dispatch slots reserved for this and the Codex BLOCKs.

### Four Codex PowerShell BLOCKs at `85dfa4a7` - AWAITING DETAILS
Crew reports Codex found four PowerShell BLOCKs attributable to this session's work. Details not forwarded
yet, so nothing dispatched. A lane is held free.

### Self-disclosed constraint breach, recorded not punished
The item-2 rebase role used `git checkout --` once to revert a sabotage, against an explicit brief
constraint. The tree was clean beforehand and an empty diff confirmed nothing was lost; the role corrected
itself to `sed` for the second sabotage and disclosed both. Recorded because a self-disclosed breach only
stays cheap if it is written down.

### Orphaned pytest process on this machine - flagged, not killed
The family-A/C lane left a pytest run alive after its own Bash-timeout wrapper expired, producing two
contended suite summaries (24F/110P then 29F/105P, plus a `git init` `STATUS_DLL_NOT_FOUND`). Both numbers
were correctly discarded as noise. The role declined to kill blindly among ~37 unrelated `python.exe`
processes on this shared machine. Someone with the context should reap it.

### Deferred to crew 1.0.x - four test-harness defects, deliberately NOT fixed tonight
Ruled by the crew during the 1.0 ship pass, 2026-09-25. Each is a harness defect, not a product defect;
none blocks 1.0. No lane was spent on any of them. Recorded here so the deferral is distinguishable from
nobody having noticed.

1. `sabotage.py`'s 13 pwsh-dependent mutations are still GREEN at `ad18172b` - the mutations do not bite,
   so that slice of the sabotage harness is currently vacuous.
2. `test_ps1_python_probe.py:~93` - the `.cmd` stubs pass a POSIX `/c/...` path to `CreateProcess`, which
   cannot open it. The stub branch is therefore not exercising what it claims to.
3. `crew_fixtures.py:~69` - the `taskkill` teardown loses descendants, so a spawned tree survives the
   fixture and contends with the next test.
4. `test_auto_cycle.py:~287` - leaks a 30s detached sender per run.

### Deferred by the 1.0 ship pass - triggers left standing
`verifyMarkerStale`, `knowledgeBehind` (7 subsystems), `diagramsStale` (`data-flow-crew-config`,
`process-crew-brief`) and `ticketsTooLarge` were all live during the 1.0 pass and were deliberately not
worked - every lane went to a Windows BLOCKER instead. They are unchanged, not resolved.
