# Changelog

All notable changes to this repository are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows the `version` field on each plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) rather than a single repo-wide version, since skills ship independently.

## [Unreleased]

### Fixed

- **`crew` 0.19.80: five review findings on `/crew:debug` (0.19.66).** Codex
  (gpt-6-astra) reviewed the command and its bundled `find-polluter.sh`.
  `commands/debug.md` claimed the missing `Write`/`Edit` grant was "the
  enforcement" for the Iron Law; it is not — `Bash` can write a file as
  readily as `Edit` can, so the passage now says plainly that the tool grant
  removes the convenient path to a fix, not that it makes one impossible,
  matching the wording `dba.md`/`qa-reviewer.md` already use for this same
  distinction. `find-polluter.sh` shipped at file mode `100644`, so upstream's
  documented `./find-polluter.sh ...` invocation fails with "permission
  denied" on Linux; the index mode is now `100755`. Three more defects are
  inherited from upstream `superpowers:systematic-debugging` 6.3.0 and are
  now fixed in crew's copy only (see `plugin/crew/NOTICE.md` and `TODO.md`
  for the upstream reproduction so they can be filed there too): a test
  filename containing whitespace was split into two invalid runner
  arguments by unquoted word-splitting; a non-zero exit from the test
  runner (e.g. a missing `npm`, exit 127) was discarded by `|| true` and
  reported as a clean run; and an investigation that executed zero tests
  — an unmatched pattern, or every candidate skipped because the pollution
  check already existed — reported "all tests clean" instead of refusing to
  conclude. Regression cases for all four fixed items (the prose plus the
  three script behaviours) are in `plugin/crew/tests/test_debugging_method.py`,
  each sabotage-tested.

### Added

- **`crew` 0.19.79: a debugging method, and the routing that dispatches it.**
  Crew shipped 27 commands and 19 skills and not one of them was about finding
  a cause: `grep -cil 'debug\|root cause'` over `commands/` and `skills/`
  returned nothing that described a method, and no role's job was diagnosis.
  The gap showed up as the thing everyone does instead — fix where the error
  surfaced, ship, watch it return under another symptom. New skill
  `crew-debugging` and new command `/crew:debug`, adapted from
  `superpowers:systematic-debugging` (Jesse Vincent, MIT; full notice now in
  the new `plugin/crew/NOTICE.md`, which is this plugin's first). The method is
  upstream's, wording intact — the Iron Law, the four phases, the red flags and
  the rationalisation table. What crew changed is where Phase 1 gets its
  evidence: the intersecting `.crew/codemap/<subsystem>.md` `## Landmines`
  sections, `.crew/codemap/schema-<datasource>.md` when the defect touches
  data, `graphify-out/graph.json` for a cross-file backward trace, and
  `.crew/verify.json` for the command the gate will actually run. Upstream's
  four adversarial pressure tests ship too, deliberately: the method without
  them is a document everyone agrees with and nobody follows at the moment it
  matters, which is the moment it was written for. `/crew:debug` holds no
  `Write` and no `Edit`, so "diagnosis does not patch" is a tool grant rather
  than a request. `commands/work.md` routes a defect ticket to it before
  planning, and `agents/developer.md` runs it before proposing a fix — a copy
  nobody dispatches is a file, not an integration. Where
  `superpowers:systematic-debugging` is installed it is preferred and the
  bundled copy stands down, following `crew-house-style`'s existing
  availability idiom: condition only on installed-or-not, and report that a
  failed `Skill` invocation proves the skill is absent from **this session**,
  not from the machine. Regression test:
  `plugin/crew/tests/test_debugging_method.py`.

  0.19.65 is skipped here; it is in flight on another branch.

### Changed

- **`crew` 0.19.66:** declared licence corrected to GPL-2.0-only to match the
  repository LICENSE; no code change.
- **`gizmoduck` 0.5.3:** declared licence corrected to GPL-2.0-only to match
  the repository LICENSE; no code change.
- **`localgpu` 0.1.19:** declared licence corrected to GPL-2.0-only to match
  the repository LICENSE; no code change.
- **`obsidian-vault` 0.3.9:** declared licence corrected to GPL-2.0-only to
  match the repository LICENSE; no code change.
- **`rule-of-two` 0.1.3:** declared licence corrected to GPL-2.0-only to match
  the repository LICENSE; no code change.

- **`crew` 0.19.65: `pm_brief.py`'s graph-refresh recommendation actually
  reads the graph.** `_graph_fields` read `state.get("graph")`, a key
  `crew_state.collect()` never sets -- the real value lives at
  `state["knowledge"]["graph"]`. `graph` was therefore always `{}`,
  `reportTracked` always falsy, and the brief recommended
  `graphify . --no-viz --code-only` even in a repo (this one included) that
  tracks `GRAPH_REPORT.md` and needs `graphify update .`. The bundled test
  fixtures matched the bug's own shape (`graph={...}` at the top level of a
  hand-built state dict), so they passed against it; fixed to nest under
  `knowledge`, and a new test drives the real `crew_state.collect()` against a
  fixture repo so the fixture shape cannot drift from the emitter's again.
- **`crew` 0.19.78: a mandatory check no longer jumps its own rule's `run`
  order, and is no longer charged twice.** Two
  FIXes from the Codex on `75452c67..9504d6e6`, both in the dedup code
  0.19.94 introduced.
  **0.19.94 attached mandatory-ness to a COMMAND**, hoisting each mandatory
  command to the front of the run list and charging it there. Both halves
  were wrong, and the first fails in the expensive direction rather than the
  loud one. A rule declaring `run: ["prepare", "check"]` has stated a
  dependency; with `check` in `always` the gate ran `check` FIRST -- measured,
  both flavours -- so the check fails for a reason that is not the user's and
  they go debugging their own code while the gate is what reordered it. A
  check that reports the wrong cause is worse than no check. The second half
  charged the hoisted command its rule's cost and then charged the rule again:
  a 40s rule running `[A, B]` with `A` in `always` cost 40 + 40 under the 60s
  default and deferred `B` -- the per-command double-charge 0.19.92 removed,
  reintroduced from the other end.
  **The obligation now attaches to the RULE that carries it.** A rule is
  unconditional when it states no cost or when any command it names is
  unconditional; it then runs WHOLE, in its own `run` order, charged once.
  That is forced rather than chosen: a rule runs whole or defers whole
  (0.19.92) and a command keeps its place inside it, so `check` cannot run
  without the `prepare` in front of it. `/crew:verify`'s documentation of the
  field says both consequences, including that marking one command of a rule
  makes the whole rule unconditional.
  **The five neighbouring merge shapes were walked deliberately** rather than
  left for the next review, and each is now a case in a table asserted in both
  flavours: `always` plus two costed rules; two costed rules and no `always`;
  an unpriced rule sharing a command with a costed one; an empty `always`; a
  rule every command of which is mandatory. All five were already correct
  under the fix; the table is there so a later change to the merge has to keep
  them correct. A second table re-checks the ordering invariant over the same
  shapes.
  Sabotage: eight mutations, each RED and each restored byte-identical --
  **four of them re-anchored rather than added.** Lifting the obligation to
  the rule deleted the code four existing mutations pointed at, and a
  whole-file anchor check caught all four at zero hits; they were re-aimed at
  the new seam instead of dropped, because the defects they prove are still
  live. **And two new ones came back GREEN first.** The hoist-and-charge
  mutation did not fail the charging case, because a mandatory rule now runs
  whole whatever it is charged -- inflating `spent` stops changing which of
  ITS commands run and only changes what is left for everything else. The
  charge invariant needed a second rule to be observable at all: 40s mandatory
  plus 15s deferrable under a 60s budget, where charging once fits both and
  charging twice defers a rule there was room for.
- **`crew` 0.19.77: deduplication can no longer weaken a check's obligation,
  and a submodule's contents are in the fingerprint.** Two FIXes from the whole-range Codex on `dedd1150..75452c67`;
  the third item is deferred and `TODO.md` says why.
  **The obligation, stated as a property rather than an exemption.** The same
  command string reaches the run list from several sources and is merged into
  one entry, and the merged entry must carry the STRONGEST obligation of any
  source: `always` is unconditional, a rule with no `seconds` is
  unconditional-until-priced, and only a rule that states `seconds` is
  deferrable. It resolved the other way, because the classification asked
  only "does this command have a cost?" and any one priced rule set one.
  Measured in BOTH flavours: `"always": ["sh -c \"exit 1\""]` beside a 90s
  rule naming the same command DEFERRED the mandatory check, so a failing
  check the map calls unconditional never ran and the gate exited 0. Writing
  it as a property rather than as "exempt `always`" turned up a second case
  nobody had reported -- a command named by an unpriced rule AND a priced one
  was deferred too -- which has its own must-block case. Forced commands are
  still CHARGED against the budget so the printed arithmetic stays honest;
  the cost simply cannot buy their deferral.
  **A submodule hashed as "absent".** A gitlink is a directory, `open()` on a
  directory raises, and the digest recorded the same constant a DELETED file
  gets -- so a check reading `sub/a.txt` was skippable by editing
  `sub/a.txt`, whose gitlink sha does not move. Measured: Stop exit 0 with
  SKIPPED, `--all` exit 2, gitlink steady at `160000 4a179f05...`. Third
  instance of one class, after the staged contents and the trimmed path, and
  it is now a row in the same invariant table. A gitlink is hashed by
  recursing through `fingerprint` itself -- a submodule needs exactly the
  coverage its parent needs, and a bespoke walk would be a second
  implementation to keep in step. Dispatched on the INDEX MODE (`160000`)
  rather than on `os.path.isdir`, because git also emits a bare directory as
  its collapsed entry for a wholly untracked one and that is not a repository
  to recurse into. Depth-bounded, with a distinct marker at the limit so a
  too-deep submodule can never read as an absent one.
  Sabotage, six mutations, each RED and each restored byte-identical -- and
  **one came back GREEN first, which is the entry worth reading.** The
  property table's submodule row passed with the gitlink fix deleted, and the
  cause was the FIXTURE, not the gate: writing the committed bytes back left
  the submodule CLEAN, so `sub` was absent from the changed set, the seeding
  run checked nothing, and the later edit moved the digest merely by making a
  path APPEAR. Exactly the shape this module warns about for ordinary files.
  The fixture now seeds the submodule dirty-but-passing and asserts `sub` is
  in the changed set, so it cannot go vacuous silently again.
- **`crew` 0.19.76: a deadline the gate cannot parse now means the lock is
  NOT held, and the test that was supposed to prove cross-flavour agreement
  now needs the feature to pass.**
  Two FIXes and a NIT from the Codex review of `30eebdd9..0462ddc1`, the
  lock-window commit.
  **The deadline read repaired a malformed value into a permissive one.**
  `verify-gate.sh` parsed `.crew/.verify-gate.lock/deadline` with
  `tr -dc "0-9"`, which DELETES the characters it does not like rather than
  refusing the value -- so `-9999999999` became `9999999999`, a deadline in
  the year 2286. Measured before the fix: the gate backed off announcing
  "may run for another 8210194761s", exit 0, verification silently off for
  the rest of the century. That is this repository's recurring defect
  inverted: not an unknown collapsing into a safe-looking value, but a
  broken one being mended into it. The value is now REJECTED unless it is a
  pure run of digits (whitespace stripped first, because the `.ps1` flavour
  writes this file with a native line ending), and an unparseable deadline
  falls through to the age window -- the same discipline as `DEFERRED_COUNT`
  defaulting to 1.
  **The two flavours also disagreed above Int32 max,** which the finding did
  not name and which the fix closes: measured on an aged token with a
  deadline of `9999999999`, bash backed off while PowerShell RAN, because
  `[int]` overflows and the catch silently produced 0. That is not a
  synthetic input -- every legitimate deadline crosses Int32 max on
  2038-01-19. PowerShell now matches `^[0-9]+$` and casts to `[long]`.
  **The cross-flavour test passed without the feature it was named after.**
  It fabricated the lock, the token and the deadline itself, and the token it
  planted was fresh enough that the AGE WINDOW forced the back-off it
  asserted. Verified rather than taken on the reviewer's word: with deadline
  publication deleted from BOTH gates the old case passed in 1.67s, and the
  rewritten one fails. It now starts a real gate of the WRITER flavour as the
  holder and asserts the token is already PAST the TTL before challenging,
  so the back-off is attributable to the deadline and to nothing else.
  **`CREW_VERIFY_LOCK_TTL=08` hit octal arithmetic.** All digits, so it
  passed the filter and then died inside `$(( ))`: two
  `value too great for base (error token is "08")` lines and NO deadline
  published at all, while the gate still exited 0 -- a test seam silently
  disabling the mechanism it exists to exercise. `10#` reads it as decimal,
  which is also what makes it agree with PowerShell, where `[int]"08"` was
  always 8.
  Sabotage, five mutations, each RED and each restored byte-identical:
  restoring the `tr -dc` coercion; restoring the `[int]` cast; deleting
  deadline publication from `verify-gate.sh` and again from
  `verify-gate.ps1` (separately, because the cross-flavour case runs both
  directions and one flavour still publishing leaves the other green); and
  removing `10#` from the TTL seam.
- **`crew` 0.19.75: the Stop gate's skip can no longer wave through a tree
  `--all` fails on, and a rule is no longer split by its own budget.**
  Three findings from the Codex review of `dedd1150..30eebdd9`, two of them
  one defect.
  **The two BLOCKs are a single class, and are fixed as one.** Both were
  "the fingerprint hashes something other than what the check will actually
  read", and both produced the identical signature: Stop exited 0 with
  SKIPPED while `--all` exited 2 on the same tree. `verify_fingerprint.py`
  hashed the working tree but not the INDEX, so a check reading
  `git show :a.txt` was skippable by staging failing contents behind a
  passing working copy; and it stripped whitespace off every path handed to
  it, so a rule on `" leading.txt"` was verified against the digest of
  `leading.txt` -- a different file, which hashes as absent. Each is now
  covered at its cause (the staged blob id and every stage come out of the
  `git ls-files -s` call that was already being made for the mode; the path
  list is kept verbatim, split the way the matcher splits its own copy), and
  the CLASS is covered by a property test over a table of tree states:
  *if `--all` fails on a tree, a Stop on that tree must not skip.* Both
  reproductions were measured before the fix and are cases in that table.
  **The FIX is a specification error, not an implementation one.** The budget
  spec said "run matched rules in ascending `seconds`" and never said what
  the unit was, so every COMMAND in a rule was charged the whole rule's cost:
  a rule with `"seconds": 40` and two commands ran the first, priced the
  second at another 40, and deferred it under the 60s default -- splitting
  the rule and reporting the unrun half as unverified. `seconds` now prices
  the RULE and is charged once; a rule runs whole or defers whole, in both
  flavours and in `/crew:verify`'s own documentation of the field.
  Sabotage, five mutations, each red and each restored byte-identical:
  reverting the index entry to the mode alone (red on both the digest case
  and the property table); restoring the `.strip()` on the path list; and
  restoring the per-command selection in `verify-gate.sh` and again in
  `verify-gate.ps1` -- separately, because the arithmetic is a python heredoc
  on one side and PowerShell on the other, and a fix applied to one flavour
  reads as done. The `.sh` mutation left the `[ps1]` parameter green and vice
  versa, which is what proves each flavour's code path actually runs.
  A first attempt at the budget mutations inflated `spent` after the decision
  rather than in it, came back GREEN on a one-rule map, and is recorded in
  `sabotage.py` beside the real one.
- **`crew` 0.19.74: a rule longer than the lock TTL no longer loses its lock
  mid-run.**
  This is the fourth FIX from the Codex review of 0.19.65-0.19.70, the last
  of the six review items. Cutting `LOCK_TTL` to 180s in 0.19.65 was
  justified by a heartbeat, but the heartbeat fires only BETWEEN rules, so a
  SINGLE rule longer than the TTL still let the other gate flavour reclaim a
  live lock and run concurrently -- two gates, two verdicts, one turn. Not
  hypothetical: this repo's own `.crew/verify.json` declares a 185s rule
  against a 180s TTL.
  The reviewer's stated preference was a background heartbeat running DURING
  the rule; that was not taken, because a backgrounded toucher is ORPHANED
  when the holder is SIGKILLed, and an orphan that keeps refreshing the token
  disables verification permanently. Bounding that needs either pid
  liveness -- measured unreliable on this platform, a hard-killed Git Bash
  pid reported ALIVE at +0.5s, +5s and +15s -- or a pipe-EOF trick whose
  PowerShell equivalent is different machinery, which is exactly the
  `.sh`/`.ps1` drift this pair exists to avoid.
  Instead the holder now publishes a DEADLINE, sized from the map's own
  measured numbers: `max(LOCK_TTL, 2 x the largest stated cost among the
  selected rules)`, same arithmetic in both shells, no background process,
  bounded by construction. A challenger honours the deadline when one exists
  and falls back to the age window when it does not, so a lock written by an
  older version ages exactly as before. `CREW_VERIFY_LOCK_TTL` is an
  environment-only test seam so the regression suite exercises the boundary
  in seconds rather than minutes; it is deliberately not read from config.
  The cost, stated rather than hidden: a hard-killed holder now holds the
  lock for up to that window instead of `LOCK_TTL` -- 370s rather than 180s
  on this repo. The residual gap, not closed: a rule with no stated `seconds`
  contributes 0 to the window and keeps today's behaviour.
  Sabotage: removing the in-rule deadline republish (both before the first
  rule and after each one) in both flavours turned the must-allow case RED
  in both, naming the reclaim ("the holder published no deadline... will
  reclaim a live lock"); restored byte-identical by sha256 in both.

- **`crew` 0.19.73: a deferred rule no longer removes a file from
  verification for good.** Codex review of 0.19.65-0.19.70 found one BLOCK
  and four FIX; this is all of them but the lock heartbeat.
  **The BLOCK.** The gate keeps two records of a clean run:
  `.crew/.verify-verified-at`, the commit SHA later runs diff against, and
  the fingerprint. The fingerprint had a guard; **the SHA baseline had none**,
  and it is the one that decides what lands in the changed set at all. So a
  Stop that DEFERRED a rule still advanced the baseline, the deferred file
  dropped out of `CHANGED` for every later run, and `--all` -- which
  correctly ignores the fingerprint -- was still diffing against the advanced
  marker. Reproduced: commit a file mapped to a failing 90s rule, Stop
  (deferred, exit 0), then `--all` -> exit 0 with the failing check executed
  ZERO times. It survived review because the guard a reader looks for is
  present and correct on the twin, so its absence reads as deliberate.
  **The mirror.** The fingerprint's guard was `[ -z "$NOTICES" ]` -- a
  string-emptiness test doing a boolean's job. `NOTICES` is prose and is
  non-empty for two different facts, "a rule was deferred" and "a rule had
  no stated cost", and only the first means "not verified". A rule that ran
  and PASSED therefore suppressed recording, disabling the unchanged-turn
  skip for every map that is not fully costed -- which is most of them,
  including this repo's. The matcher now emits the deferred COUNT as its own
  machine-readable record and both records share one predicate,
  `fully_verified` / `$fullyVerified`. An unreadable count resolves to
  "assume a deferral", never to the permissive value.
  **Three more.** The fingerprint excluded all of `.crew/`, so a repo that
  MAPS a `.crew/` path could change its contents, keep the passing digest and
  skip verification -- now only the files this gate itself writes are
  excluded, by name. Non-ASCII paths came back from git escaped and
  double-quoted under the default `core.quotePath`, naming no real file, so
  they hashed as absent and later edits kept a passing digest; both flavours
  now force it off at every path-listing call. And the digest hashed bytes
  but not the git file MODE: a committed chmod was caught via HEAD, a STAGED
  one was not, so a check depending on `+x` could be skipped on the tree that
  had just changed it.
  Sabotage 10/10 RED, all three files restored byte-identical. Four of those
  ten came from re-running it: two were invalid mutations of mine, and two
  were genuine test weaknesses -- the quotePath check was line-granular while
  the bash flavour puts BOTH git calls on one line, so dropping the flag from
  one half stayed green; and nothing covered the fail-closed default at all.

- **`crew` 0.19.72: the gate stops re-proving a tree it just proved.** Stop
  fires once per TURN, so a turn that changed nothing the gate depends on ran
  the whole map again to reach the answer it reached a minute ago. The event
  is not the gate; the STATE is -- the same argument `pm_pulse.py` makes in
  its own header, pointed at a different verdict.
  New `hooks/scripts/verify_fingerprint.py` digests HEAD, the changed paths
  AND THE BYTES of each, plus `verify.json` and `config.json` (which decide
  which commands run and how many fit). Contents, not `stat()`: an mtime
  comparison is wrong in the direction that matters, since a same-size write
  at the same granularity reads as unchanged and the gate would skip a real
  edit. It lives in ONE .py used by both flavours, for the reason
  `scope_report.py` gives -- a hash reimplemented in bash and again in
  PowerShell is two implementations that drift, and a gate that skips on one
  shell and runs on the other is worse than either answer. A case asserts
  directly that a marker written by one flavour is honoured by the other.
  **The marker is only ever written after a CLEAN, COMPLETE run.** Not after
  a failure, and -- the subtler half -- not after the Stop budget deferred a
  rule. That run exits 0, but a deferred rule was never checked, so recording
  it would turn "we ran out of budget" into "this tree is verified" and the
  deferred check would never run again on an unchanged tree. Both halves have
  their own must-block case in both flavours.
  **The skip is never silent.** 0.19.65 existed because a silent `exit 0` was
  byte-identical to a pass; the gate names the digest it matched and says the
  checks were SKIPPED, not re-run. `--all` / `-All` ignores the marker as
  well as the budget. No python means no fingerprint and no skip.
  `.crew/` is excluded from the digest, and that is load-bearing rather than
  tidy: the gate writes its own markers there, so with it included every run
  invalidated the digest it had just recorded and the skip NEVER FIRED ONCE.
  Measured during this change, and it now has a case of its own.
  Sabotage 9/9 RED across both flavours and the shared module, all three
  files restored byte-identical.

- **`crew` 0.19.71: the Stop gate spends a budget instead of the whole
  afternoon.** `.crew/verify.json` carried each rule's cost as PROSE inside
  its `why` -- "8s", "29s", "245s" -- and nothing could read it, so the
  gate had no way to spend a turn's time cheapest-first. Rules now take a
  real `"seconds": N` field (`why` keeps the reason), and both flavours read
  it against `verify.stopBudgetSeconds`, default 60.
  Matched rules run in ascending cost while the total fits; what does not is
  deferred and NAMED with its price -- `deferred to /crew:verify: <cmd>
  (<n>s)` -- so a skipped check is visible rather than merely absent. `--all`
  (`-All` on PowerShell) removes the budget, which is what /crew:verify uses
  to run the whole map.
  **Unknown cost is not free.** A rule with no `seconds` RUNS -- deferring it
  would mean acting on a number nobody wrote down -- the output says its cost
  is UNSTATED, and it is left OUT of the budget arithmetic rather than given
  a guessed value, so the stated total is never a fiction. Most of this
  repo's own rules are deliberately left in that state: only the ones
  actually timed carry a number, because filling the rest in by guesswork is
  exactly what the field replaces. A malformed `.crew/config.json` falls back
  to the 60s DEFAULT and never to unbounded -- "could not read the config"
  must not quietly become "no limit".
  A deferral can never change the exit code, and a rule that RUNS and fails
  still exits 2 beside one that was deferred; both have their own case.
  Measured on a quiet tree: pytest gate set 72s, whole crew suite ~185s (the
  midpoint of five runs spanning 157-201s, which is itself a reason to treat
  it as approximate), ruff+pylint 38s, check-marketplace 9s, smoke 5s,
  self-claims 3s, pwsh 2s, validate-prompts 1s.
  Sabotage 8/8 RED across both flavours -- budget ignored, deferrals
  unreported, unstated cost treated as free or dropped from the run set, bad
  config falling back to unbounded, and `--all` still budgeting -- both gate
  files restored byte-identical. The two flavours are also asserted to select
  and report identically: a budget that picks different checks per shell
  would make the verdict depend on which hook fired first.

- **`crew` 0.19.70: pm-pulse.ps1 stops dropping the PM's blocking findings
  to a shadowed python.** The same resolver defect as 0.19.67, in a
  DIFFERENT blocking hook, and deliberately its own commit and its own bump
  so reverting one cannot silently take the other.
  `pm-pulse.ps1:12-13` was byte-identical to the line 0.19.67 replaced:
  `(Get-Command python3, python | Select-Object -First 1).Source`, with
  neither the CommandType guard nor the WindowsApps filter. **What it cost
  here is worse.** The next line is `if (-not $py) { exit 0 }`, and this hook
  exits 2 to block the stop and hand the PM's findings back to the model.
  `hooks.json` registers it with no `-NoProfile`, so a `function python { }`
  in a user profile is returned ahead of any python.exe with an EMPTY
  `.Source` -- which then failed that test and exited 0. Every PM finding,
  including the blocking ones, dropped in silence on a machine with python
  installed: a hook wearing the exit code of a pass, which is this repo's
  named recurring defect. The Store alias fails the other way, resolving and
  being invoked.
  The resolver is duplicated inline rather than dot-sourced, following the
  decision `verify-gate.ps1`'s own header records: a function arriving by
  dot-source is invisible to `scripts/check-powershell.ps1`'s static check.
  That decision is defensible; leaving the copies unguarded would not be, so
  a parity case compares the two executable bodies (comments excluded -- the
  two files explain different costs and SHOULD differ there).
  Sabotage 5/5 RED, both .ps1 files restored byte-identical. One of the five
  is again the call site rather than the resolver: reverting it left the
  first five cases green, the SECOND time that gap appeared in two commits,
  so the case that catches it uses an OBSERVABLE stub -- a .cmd that writes a
  marker when run. An exit code cannot tell "skipped the stub" from "ran it
  and it failed"; the marker can only exist if it was executed.

- **`crew` 0.19.69: verify-gate.ps1 resolves python the way it already
  resolved bash, and both flavours name a missing scope script.** Two
  findings from a security review of the 0.19.63 scope layer.
  The interpreter for the scope report was
  `(Get-Command python3, python | Select-Object -First 1).Source` -- four
  lines away from `Resolve-CrewBash` in the SAME file, which filters on
  `CommandType -eq 'Application'` and excludes the WindowsApps App Execution
  Alias for exactly these reasons. One file, two resolvers, one hardened.
  Both vectors are live rather than theoretical: `hooks.json` passes no
  `-NoProfile`, so a `function python { }` in a user profile is loaded and
  returned AHEAD of any python.exe with an empty `.Source`, which then failed
  the truth test and made the gate report "no python" on a machine that has
  python -- the unknown collapsing into a safe-looking value again. And the
  Store's `python.exe` alias is a real Application with a real `.Source`, so
  it resolved and was INVOKED. Now `Resolve-CrewPython`, carrying the same
  guard, with `-PrintPython` as its probe seam beside `-PrintBash`. The
  System32 filter the bash resolver has is deliberately absent: WSL ships a
  bash launcher there, nothing ships a python one.
  Second, the `.ps1` invoked `scope_report.py` with no `Test-Path`, while the
  `.sh` tests both `-n "$SCOPE_PY"` and `-f`, so a missing script reached
  python and a raw "can't open file" line was printed as the scope report.
  Both flavours now check both preconditions AND report them apart: the `.sh`
  previously answered "(no python; scope not checked)" for a missing script
  too, so fixing only the `.ps1` would have introduced the drift the pair
  exists to prevent.
  Sabotage 5/5 RED, both gate files restored byte-identical. Two of those
  five came from re-running it rather than trusting the first tally: the
  original four all probed `Resolve-CrewPython` through `-PrintPython`, so
  reverting the CALL SITE to the old one-liner left them green -- a guard
  that is correct and unreached -- and collapsing the `.sh` branches again
  left them green too, because none of them execute the bash flavour. The
  suite now drives the real gate for both.

- **`crew` 0.19.68: the scope report stops calling in-scope files out of
  scope, and stops losing files to a prefix.** Three defects, each measured
  before it was touched, all in `scope_report.py` -- the report-only line
  both gates print.
  (1) `declared_paths` read the ticket from `.work/tickets/<id>.md` only.
  Jira, ServiceDesk Plus and Obsidian Kanban modes keep it at
  `.work/cache/<id>.md` (`commands/work.md` step 1), so the report said
  "the ticket file is missing" for tickets that exist -- on THIS repo,
  whose tracker is obsidian, on every turn. Both locations are now read, in
  work.md's order, and the unknown branch names both rather than sending the
  reader to check one path and conclude the other was never searched.
  (2) `_BOOKKEEPING` was one tuple behind a single `str.startswith`, so
  `TODO.md` in it swallowed `TODO.mdx` and `TODO.md.py` -- both measured
  True. A real source file dropping out of a scope report as "crew's own
  bookkeeping" is the exact collapse this file's own docstring forbids. The
  directories stay a prefix test; the file is now an exact one.
  (3) **The important one.** `fnmatch` has no real `**`:
  `fnmatch("main.py", "**/*.py")` is False while
  `fnmatch("src/main.py", "**/*.py")` is True, so a ticket declaring
  `**/*.py` had its own root-level files reported OUTSIDE the scope it had
  just declared. A scope line that names in-scope files is how the whole
  feature gets ignored. This was also a PARITY defect and the fix is not a
  second matcher: `verify-gate.sh` already handled it (its embedded
  `def matches` tests the `**/`-stripped form), and `scope_report` now
  carries that same matcher with a test that lifts the gate's copy out of
  the script and compares the two over a case table. Behavioural parity, not
  a text compare, so a comment edit does not fail it but a semantic drift
  does. The report keeps two extra bare-directory forms on top, because a
  hand-written `- touch:` line names directories where a `verify.json` rule
  writes globs; that widening is asserted to be a SUPERSET of the gate in
  one direction only, so the report can never invent a violation the gate
  would not also see.
  `scope_report.py` had NO tests at all; it now has 16. Sabotage 4/4 RED
  (one per defect, plus making the report narrower than the gate), file
  restored byte-identical. Found while re-running the 0.19.65 sabotage:
  the `.sh` and `.ps1` gate matchers themselves disagree -- `verify-gate
  .ps1:381` carries a fourth candidate (`**` -> `*`) the `.sh` has not.
  Recorded in TODO.md rather than fixed here, since it is a change to a
  blocking hook and belongs with its own bump and sabotage run.

- **`crew` 0.19.67: backing off is no longer indistinguishable from passing,
  and a long gate keeps its lock.** A lock left by a hard-killed holder made
  every later gate exit 0 in 474ms with no output (measured 2026-09-18), for
  up to the 700s TTL. `verify-gate.sh:189` had already recorded that symptom
  as a known unfixed limitation and `verify-gate.ps1:216` had seen it in
  another repo, so this is not a new discovery -- what was missing was saying
  it out loud. Back-off now prints
  `verify-gate: backed off, lock held by <token> (<age>s, ttl <n>s); NOTHING
  WAS VERIFIED this turn.` The four must-allow lock cases now assert that line
  instead of `stderr == ""`: asserting silence is what let the ambiguity
  stand. **No pid liveness check** -- measured dead on this platform in the
  script's own 2026-09-13 note, where a hard-killed Git Bash pid reported
  ALIVE at +0.5s, +5s and +15s. Instead the lock gained a HEARTBEAT, touched
  after each rule, so its age means "no rule has finished in this long" and
  the TTL only has to exceed the slowest single rule. That allowed 700 -> 180.
  The first heartbeat was a no-op and every existing test passed anyway: it
  touched the token while the age was read from the directory, and a directory
  mtime does not move when a file inside it is rewritten (measured: dir
  unchanged across a token rewrite two seconds later). Both flavours now date
  the lock by its token. The gate also prints elapsed per rule and a total, so
  `verify.json`'s stated costs can be re-timed from output rather than memory:
  measured here, pytest gate set 72s, pylint 37s, whole run 125s.
  Two catches worth keeping visible, because both are about tests rather than
  code. The broken heartbeat passed every existing test, since none of them
  asserted that a long run KEEPS its lock -- the suite covered the lock going
  stale and never the opposite. And the first test written for it recomputed
  the age in Python instead of running the gate, so it passed against a
  sabotaged script: it reported ALL RED while three mutations went green. That
  is the trap this suite's own docstring names, "mocking that would test the
  mock", committed by the person who had just read the warning. The tests now
  run the real gate in both flavours. `_TTL` was also hand-copied into two
  test files and went stale at the cut; a stale copy does not fail, it moves
  the boundary under test away from the real one and keeps passing, so it now
  carries a guard asserting it matches both scripts -- the same defect and the
  same fix as the five hand-copied skill-count sites.
  A THIRD catch, found by re-running the sabotage rather than trusting the
  previous run's tally. The two heartbeat cases pre-age the token with
  `os.utime` and then assert on what the gate READS -- which proves the lock
  is dated by its token rather than by the directory, and is a different
  property from the heartbeat actually firing. Every fixture in both lock
  files writes deliberately-broken `verify.json` to force the early exit, so
  no rule had ever run and `lock_touch` / `Update-CrewLock` could be deleted
  outright with all 23 cases still green. Measured: making `lock_touch` a
  no-op left the suite passing. Both flavours now carry
  `test_the_heartbeat_actually_rewrites_the_token_during_a_run`, which runs
  the real gate over a parsing `verify.json` and has the rules themselves
  read the token's mtime from inside the run. Sabotage is 7/7 RED across
  both flavours (announcement, TTL, heartbeat write, and dating by the
  directory again), both gate files restored byte-identical.
- **`crew` 0.19.79: `test_codemap_read_path.py` survives a rewrap.** Its
  assertions matched prose exactly with no whitespace normalisation, so any
  edit that reflowed a line in an agent file failed a test whose subject had
  not changed — and a test that fails for that reason is one people learn to
  fix by deleting the assertion. Now uses the same `_norm()` helper
  `test_scope_discipline.py` already had.

- **`crew` 0.19.64: `scope_report.py` passes the repo's own pylint gate.** No
  behaviour change; all five report branches re-verified identical. Six
  `C0209` findings converted to f-strings. The bump exists because a lint-only
  edit is still a content change: `claude plugin update` compares the declared
  version, so an installed `0.19.63` would never receive it. The gate caught
  the missing bump on the commit after the fix, which is the drift check doing
  exactly what root `CLAUDE.md` describes.

- **`crew` 0.19.63: the code map reaches the reviewer that actually runs, and
  the gate reports scope.** 0.19.61 taught `qa-reviewer.md` to read the
  codemap, but `qa-reviewer` is the FALLBACK reviewer: `/crew:review` tries
  Codex then Copilot first, and the shared `prompt.txt` all three providers
  read had no codemap content -- `grep -ci 'codemap|landmine' review.md` was 0.
  On any machine with Codex installed the wiring reached nobody. The landmine
  and `## Written by / Read by` sections of intersecting notes are now built
  into that shared prompt, keeping the byte-identical-across-providers
  invariant the file exists to protect. The match is a substring test and
  over-matches (7 of 10 notes on a 13-file diff here); that is stated in the
  command rather than described as precision, and the output is capped at 200
  lines with a truncation notice, because a silently cut landmine list reads
  the same as a short one. `verify-gate.sh` and `.ps1` gained a REPORT-ONLY
  scope layer: changed files compared against the open ticket's declared
  `- touch:` paths, printed as `outside-scope:`. It can never change the exit
  code. Every branch that cannot answer says why -- no open ticket, no declared
  paths, ticket file missing are three distinct sentences, because an empty
  report must only ever mean "checked, nothing outside". Crew's own bookkeeping
  (`.work/`, `.crew/`, `TODO.md`) is excluded: a ticket edit is the process
  working, not scope creep. Logic lives in one `scope_report.py` called by both
  flavours, for the reason `pm-pulse.sh` gives. The `/goal` evidence command
  changed from `git status --porcelain` to `git diff --name-only <base>` plus
  untracked: porcelain compares against the index, so a mid-ticket `git commit`
  empties it while the branch still carries the change, and it also shows files
  dirty before the ticket began. `developer.md` now forbids committing, which
  nothing did before. Six new gate cases, sabotage-tested: five mutations, all
  red, both files restored byte-identical.
  Also folds four findings from a Codex review of 0.19.61-62 (0 BLOCK, 4 FIX).
  Three were one defect: the 0.19.62 scope clause was pasted identically into
  four roles whose contracts differ. `dba` and `qa-reviewer` hold
  `Read, Grep, Glob, Bash, Skill` and no `Write` or `Edit`, so telling them to
  append to `TODO.md` asked for shell redirection -- which works, which makes
  it worse than an outright failure; they now report the finding and the
  dispatching session files it. `qa-reviewer`'s contract is defect lines or
  exactly `CLEAN`, so its Deferred section is removed entirely and an unrelated
  defect becomes a `NIT` finding: with the section, no clean review could
  satisfy both rules. And the `/goal` template forbade modifying tracked files
  outside the ticket while the same clause required appending to `TODO.md`,
  which is tracked -- so a correct deferral read to the evaluator as a
  violation and the only compliant behaviour was to stop deferring. The
  template now carves out `TODO.md`, `.crew/` and `.work/`, matching what
  `scope_report.py` already excluded. `test_scope_discipline.py` was rewritten
  to assert the role-appropriate form for each file, and to check the tool
  grants the split claims, rather than one identical string across five files:
  a uniform assertion is precisely what let this through.

- **`crew` 0.19.62: the roles that touch code now carry the scope rule the PM
  already had, and `/crew:work` emits a goal line that can actually be
  checked.** Crew advertises itself in `plugin/README.md` and `README.md` as
  "bounded so it fixes only what blocks the job and tickets the rest", and
  before this the rule lived in exactly one place: `pm_pulse.py:188-189` and
  `:215-217`, the PM's hook text. Measured across the roles that edit and
  review code, `grep -ci 'defer|out of scope|unrelated'` returned 0 for
  `developer.md`, `qa-reviewer.md`, `smoke-author.md`, `dba.md` and
  `work.md`; `smoke-author.md` had no scope language at all. The instruction
  existed only where it was already being followed. All four roles now carry
  an identical scope clause -- fix what blocks, file the rest to `TODO.md`
  with its `path:line` and reason -- and end their reports with
  `## Deferred — and where it went`, required even when empty, with
  "Nothing deferred." as the written-out empty case. An absent section read
  identically whether the role found nothing or found something and fixed it
  quietly, which is the ambiguity that made veering invisible.
  `/crew:work` gains step 4b: a ready-to-paste `/goal` line built from the
  ticket's "Done when", the `.crew/verify.json` commands its paths map to
  plus the ticket's own new test, and a scope constraint. Crew does not set
  the goal -- `/goal` is a built-in the user types -- it composes it. The
  implementation step now ends by printing `git status --porcelain` verbatim
  including when empty, because the goal evaluator runs no commands and opens
  no files: a constraint whose evidence is never printed returns Met because
  nothing contradicted it, not because it held. Regression suite
  `plugin/crew/tests/test_scope_discipline.py`, sabotage-tested: nine
  mutations across five files, all red, all files restored byte-identical.

- **`crew` 0.19.61: the roles that touch code now read the code map, and
  onboarding writes a schema note.** Crew has written a per-repo "what breaks
  here" store since the codemap shipped -- each note's `## Landmines` section
  -- and never told the doing-and-reviewing roles to open it. Measured before
  this change: `grep -ci codemap` returned 0 for `commands/review.md`,
  `commands/work.md`, `agents/developer.md`, `agents/dba.md`,
  `agents/qa-reviewer.md` and `agents/smoke-author.md`. Every reviewer
  re-derived the repo's failure modes from the diff plus `CLAUDE.md` in an
  empty context, every time. The four doing roles now open the intersecting
  notes, read `## Landmines` by name, run the per-path
  `git diff --name-only <anchor>..HEAD` re-check rather than treating a lagging
  anchor as a wrong note, and report which notes they read -- because a note
  skipped and a note checked are indistinguishable in a summary that mentions
  neither. `/crew:onboard` gains a step 5 that writes
  `.crew/codemap/schema-<datasource>.md`: columns, keys, indexes and a
  `## Written by / Read by` block, every row citing the migration line that
  creates it. It lives under `codemap/` deliberately, so it inherits the anchor
  machinery and the `knowledgeBehind` trigger instead of needing new plumbing.
  Schema that cannot be traced to a file goes in `## Unverified`, and a repo
  with no database gets "no datasource found" rather than an invented file.
  Regression suite `plugin/crew/tests/test_codemap_read_path.py`,
  sabotage-tested: four mutations, all red, restore byte-identical.

- **`crew` 0.19.60: dispatch-narration labeling extended to substantive
  claims, not just "I dispatched X."** `pm.md`'s existing "A dispatch is a
  tool call, not a sentence" rule caught a claim of work done but not a claim
  of fact, and a PM brief or report is exactly where an unverified claim
  becomes settled fact for the lane that receives it. Added a sibling rule,
  "Every claim is labeled, not just dispatch claims": every load-bearing
  claim in a PM brief or report now carries measured / relayed / hypothesis
  provenance, with a corollary that an URGENT label is a claim about cost,
  not certainty. Sourced from TheSelectSource `TO-DO.md` F465, where an
  unlabeled relayed claim was passed on as settled fact four times in two
  days, caught only by the recipient's own measuring each time.
  `crew-pm/SKILL.md`'s narration-failure section now points at the new rule.

- **`crew` 0.19.59: the ancestor walk used a cmdlet that does not exist on
  Linux.** CI runs the PowerShell static check on Linux pwsh, where the CIM
  cmdlet the walk called is absent, so `every Verb-Noun call resolves` failed
  for `auto-clear.ps1`. It passed locally on Windows, where that cmdlet does
  exist -- CI is the stricter environment and therefore the correct one.
  Replaced with `Get-Process` and its `.Parent` property, a PS6+ member of
  `System.Diagnostics.Process`. The walk is unchanged in behaviour: verified
  to reach the same `WindowsTerminal pid=17600` at the same depth, and the
  static check now reports 40 files all clean.

- **`crew` 0.19.58: `CREW_AUTOCLEAR_INHIBIT`, because the suite could type
  into a real terminal.** Caught by the Stop gate, and the more serious half of
  this change. `test_auto_clear.py` runs the REAL script with no `--dry-run`;
  before 0.19.57 the missing-`windowTitle` refusal was what kept it from
  dispatching keystrokes -- by accident, not by design. Resolving the terminal
  automatically removed that refusal and the suite reported `sent`.

  pytest descends from the user's terminal, so the resolved owner IS that
  terminal, the foreground check passes three seconds later, and `/clear` lands
  in the session running the tests. The guard is in the SCRIPT, not the
  fixture, because anyone running crew's suite downstream faces the same thing
  and does not know to set it.

  Placed at the SEND SITE. Checking it before every other decision made 20
  cases assert the inhibit message instead of the refusal they were written
  for; only the keystroke is suppressed.

  The repointed test may NOT assert whether the walk resolves: it does from a
  plain shell and does not from under pytest, measured both ways, which is why
  the gate saw `sent` where a local run saw a refusal. It asserts the
  invariant instead -- the old unconditional `windowTitle is required` refusal
  is gone.

- **`crew` 0.19.57: auto-clear finds its own terminal. No `windowTitle`
  needed.** Asked for directly: window detection should be automatic.

  `context.autoClear.windowTitle` was only ever a SAFETY CHECK -- the child
  process reads the foreground window's title after its delay and refuses to
  send if it does not match. It was never used to FIND a window. So the check
  is now exact instead of textual: `auto-clear.ps1` walks its own ancestors to
  the first process that OWNS A WINDOW, and the child compares the foreground
  window's owning PROCESS ID to it.

  Better on every axis that matters here. It cannot go stale -- a Windows
  Terminal title follows the active tab, and the detector read three different
  titles for the same window in one session (`? SRL`, `? Remove production
  guards`, `? srl`), so any stored value is wrong within the hour. It cannot
  match the wrong window -- two windows can share a title substring, they
  cannot share a process id. And it needs no configuration.

  **`MainWindowHandle` is the test, not a process name**, and the first attempt
  got this wrong in a way worth recording: a name list containing `pwsh`
  matched the hook itself at depth 0, because the hook IS pwsh -- it would have
  compared the foreground window against a process that owns no window at all.
  Every intermediate shell reports handle 0 and the terminal reports a handle,
  so the walk lands on the window the user is looking at, whichever terminal
  they use. Verified here: pwsh -> bash -> bash -> bash -> claude -> powershell
  -> `WindowsTerminal pid=17600`, at depth 6.

  `windowTitle` is KEPT as an explicit override, for a terminal that is not an
  ancestor of the hook. Title wins when set; the process id is the default.

### Removed

- **`crew` 0.19.57: the `autoClearInert` trigger, added in 0.19.54.** It fired
  when auto-clear was enabled on Windows with no `windowTitle`, because the
  script refused outright in that state. It does not refuse any more, so the
  trigger now reports a HEALTHY state as a finding -- and a brief that cries
  wolf is worse than one that says nothing.

  `read_auto_clear` still reports the facts (`enabled`, `windowTitle`, `os`);
  what goes is the judgement that those facts are a defect. `inert` is kept as
  a key and is now always `False`, so a reader gets an honest answer rather
  than a `KeyError`. Nothing Python can see at SessionStart distinguishes "will
  act" from "cannot act" any more -- only the script knows, at send time, and
  it writes that to `.crew/.autoclear.log`.

### Added

- **`crew` 0.19.56: `/crew:split <ISSUE-KEY>`, which splits an oversized Jira
  ticket into sub-tickets.** Jira only, deliberately: a files-mode ticket is a
  markdown file the user can split in an editor and an Obsidian card is theirs
  to drag, while Jira is the one tracker where splitting creates issues other
  people see. That is also why it asks before writing anything -- boards move
  and an unwanted child has to be deleted by hand in a UI.

  It judges size from evidence and names which it used: `health.rate` from
  `.crew/metrics.md` (`HEALTHY_HIGH` is 2.0), whether `ticketsTooLarge` is
  firing, how many subsystems the issue names, and whether its acceptance
  criteria can be verified together. **`health.rate` is a repo-wide average and
  is not a measurement of the issue in front of you** -- the command says so
  rather than presenting it as a verdict, and it will conclude an issue is NOT
  too large and stop, because a command that always finds work is one nobody
  can trust to say no.

  Every acceptance criterion must land on a child or stay on the parent; a
  criterion that lands nowhere is reported as a gap rather than dropped. The
  parent is never transitioned or closed -- whether a split parent becomes an
  epic, a tracking issue or is closed is a project convention this command
  cannot know.

  Wired into `agents/pm.md`'s `ticketsTooLarge` row with the two things a user
  would otherwise learn the hard way: the rate is repo-wide, and splitting one
  old ticket does NOT clear the trigger, because the rate falls when future
  tickets are smaller rather than when one is divided.

### Fixed

- **`crew` 0.19.56: `docs/diagrams/data-flow-crew-config.mmd` had never
  rendered, and two diagrams were broken by a format-string escape.**

  The escape first: refreshing the two diagrams rewrote their header through a
  `%`-formatted Python string, where `%%` means a LITERAL `%`. The generated
  line therefore opened with `%` instead of `%%`, Mermaid stopped recognising
  it as a comment, and `mmdc` reported `UnknownDiagramError: No diagram type
  detected` -- an error that names neither the line nor the character.

  The older one is worse and is not mine: `data-flow-crew-config.mmd` contains
  `\"report\"` inside a node label, which Mermaid cannot parse. Checked
  against `origin/main` rather than assumed -- the committed version fails with
  the identical error at the identical line, and `docs/diagrams/out/` held NO
  output for it at all. It has been in the repository, anchored and described
  as generated, without ever having been rendered. Now `#quot;`, and
  `render.sh` exits 0 with all six diagrams producing both an `.svg` and a
  `.png`.

- **`crew` 0.19.56: seven stale self-descriptions.** `26 commands` -> 27 for
  `/crew:split`; `20 hook entries (10 scripts)` -> `18 (9)` in the four places
  0.19.52 missed; and the README prose promising that hooks block
  `terraform apply`, force-push and destructive DDL, which has been false since
  the command guard was removed. A README that promises a guard the code no
  longer has is worse than one that never claimed it.

- **`crew` 0.19.55: `/crew:upgrade` never added the `context` block's keys, so
  auto-clear could not run on any upgraded repo.** Reported by a user who ran
  the 3 -> 7 migration and found `context.autoClear`, `context.autoWrapUp`,
  `context.autoResume` and `context.staleHandoff` still absent afterwards, no
  matter how often they re-forced it.

  The migration was not at fault. `CONFIG_BLOCKS` in `crew_upgrade.py` is a
  HAND-MAINTAINED tuple of top-level blocks; the upgrade adds exactly what is
  named there, and `context` was never in it. The module's own docstring
  predicted this shape of failure for the `qa`/`dev` table; `context` is the
  block that actually got missed.

  `context` could not simply be added, either: its defaults lived in
  `crew_config.py`, and `crew_config` imports `crew_upgrade`, not the reverse,
  so `CONFIG_BLOCKS` could not reach them. They now live in `crew_state`
  alongside `PM_DEFAULTS`, `QA_DEFAULTS`, `DEV_DEFAULTS`, `WORKTREE_DEFAULTS`,
  `INSTALL_DEFAULTS`, `GUARD_DEFAULTS` and `PRODUCTION_DEFAULTS` -- every other
  block that tuple already reaches.

  An existing `warnAt` / `reserveTokens` is PRESERVED, so an upgraded repo
  keeps `0.8` / `100000` and does not start clearing at 50% until those are set
  deliberately. The new defaults reach configs that never had the keys.

- **`crew` 0.19.55: four defects in `crew_upgrade.py`, three of them reported
  by a peer Claude session that ran `/crew:upgrade --force` against a different
  repository.** All four printed identically to a correct run, which is why
  they survived. Each was re-checked here before being acted on.

  **1. A key removed ON PURPOSE came back.** That repo had deleted
  `qa.copilot` and left `qa.copilotNote` beside it reading "Do not re-add it as
  null; pin a real model or omit the key." The upgrade re-inserted
  `{"model": null}`, because a defaults-seeding pass cannot distinguish "never
  set" from "deliberately removed" -- both are an absent key. A sibling
  `<key>Note` is now honoured as a tombstone and the skip is reported.
  **This narrows a known failure rather than fixing the class**: a key removed
  WITHOUT a Note is still re-seeded, and adding `context` above widens the same
  door for everything under it. Said in the code, not left to be discovered.

  **2. `UPGRADE.md`'s contradictions section was regenerated from scratch,
  destroying hand annotations.** Four `RESOLVED 2026-09-15` blocks became zero,
  reproduced on a second run. Worse than ordinary data loss, because that
  repo's `CLAUDE.md` tells readers to consult that list BEFORE trusting any
  codemap section -- so the regeneration silently re-opened resolved
  contradictions inside the file used to decide what to trust, and read
  identically whether a finding was re-derived or a resolution forgotten.
  Annotated lines are now carried forward, keyed on the conflict text, and the
  report states how many were carried.

  **3. The `anchor:` was bumped on a DERIVE-only re-verification.**
  `graph_reconcile.reconcile` skips KEEP at the top of its loop, so `touched`
  can only ever contain DERIVE headings -- `Does`, `Landmines` and `Unverified`
  are never read. Adding two derived lines stamped the whole note at HEAD.
  Reproduced HERE, not only reported: `.crew/codemap/crew.md` was stamped
  `f9bb78a6 -> ea8a014` on 12 added lines while **18 of its 40 cited files had
  moved**. `crew_state.knowledge.behind` and the PM pulse both trust that
  anchor, so the run turned a correct "behind" into a false "current" on the
  stalest notes in the map. `anchor:` now keeps its meaning and the weaker fact
  gets its own `derived-anchor:` line.

  **4. The conflict detector compared every backticked token as a path.**
  `abspath`, `blake2b`, `None`, `Front::dispatch()`, `--worktree-path` were all
  reported as "in the map but not in the graph". Measured here before the fix:
  186 contradictions, nearly all symbols; the peer measured 239 of 456. A list
  that is mostly false is a list nobody reads, which is how a real
  contradiction hides -- and is how defect 2 stayed invisible. `is_path_token`
  now decides, with its own false-negative limit stated: a BARE single-segment
  name is never compared, because nothing distinguishes a bare directory from a
  bare symbol.

  Test surface: `test_upgrade.py`'s three anchor tests asserted the behaviour
  defect 3 removed, so they are repointed at `derived-anchor:` rather than
  deleted -- the logic each guards (lands on head at every sha length, names a
  real commit, does not eat a hex repo name) still matters -- and each gained
  an assertion that `anchor:` was left alone.

### Added

- **`crew` 0.19.54: crew detects the terminal window title instead of refusing
  to guess it.** `crew_state.py --detect-window-title` reads the real window
  titles from the OS and prints each as JSON with a `stable` flag.

  0.19.53 told the PM not to set `context.autoClear.windowTitle` because
  "guessing a window title is guessing which window gets typed into". That is
  right about guessing and wrong about measuring - the title can be read, and a
  value read is not a value invented.

  **What it does not do is pretend the answer is durable.** A Windows Terminal
  title follows its ACTIVE TAB, so a detected value can be correct when written
  and wrong on the next switch - which is worse than refusing, because it looks
  like it worked. Every candidate therefore carries `stable` and, when false,
  the reason. `agents/pm.md` now says to show the candidate and that reason,
  propose a substring that survives a tab change, and leave the setting to the
  user: a detected title is evidence for the decision, not a substitute for it.

  Measured while building it: the detector read `? SRL` early in the session
  and `? Remove production guards` an hour later, from the same window. The
  instability warning is not theoretical.

  Windows only - the posix flavour targets a tmux pane by id and needs no
  title, so it returns an empty list rather than a fabricated candidate. Four
  cases cover it, including that a missing PowerShell returns no candidates
  rather than raising, since this runs from a SessionStart path where an
  exception would take the whole brief with it.

### Added

- **`crew` 0.19.53: a `crew-best-practices` skill, and ADR 0003 for the three
  rules crew deliberately breaks.** Integrates
  <https://rosmur.github.io/claudecode-best-practices/>, a synthesis of roughly
  twelve practitioner sources.

  The audit found most of it already true of crew and said so rather than
  re-implementing it: planning (`/crew:plan`), context management (the
  `context-watch` / `handoff-write` / `handoff-read` hooks are its "Document &
  Clear" pattern), quality gates (`verify-gate`), multi-instance review with a
  different model family (`/crew:review`), dev docs, and scripts attached to
  skills.

  **Three of its rules call crew's architecture an anti-pattern** - 54
  specialised agents against its clone pattern, 26 slash commands against its
  "long list ... is an anti-pattern", and being a multi-agent system at all.
  `docs/adr/0003-crew-departs-from-three-community-best-practices.md` records
  each departure WITH ITS COST, so the next reader who finds that document does
  not re-derive the argument or act on it.

  Also recorded: **§4.3.2 says "Don't block at write time - let the agent
  finish its plan, then check the final result."** That is exactly what 0.19.52
  did in removing the PreToolUse command guard and keeping the Stop gate,
  reached independently and before either of us read the source.

  The skill carries the rule set in three reference files (`practices.md`,
  `claude-md.md`, `contradictions.md`). The last one quotes the FIVE
  contradictions the document records about itself, because a synthesis of
  twelve practitioners is routinely cited as consensus when its own §5 says
  five of its central questions are unsettled.

  Two of its numbers are marked as not transferring: "clear at 60k tokens" was
  written for a 200k window and is 6% of a 1M one, and its 2000-token CLAUDE.md
  limit is wrong for this repository, whose length is a landmine list earned by
  shipped defects.

### Changed

- **`crew` 0.19.53: three `SKILL.md` files split under the 500-line
  progressive-disclosure limit.** The source document's §4.3.1 measures 40-60%
  fewer tokens loaded per session from this shape. Nothing was deleted - each
  span moved whole with a pointer left in its place:

  | Skill | Was | Now | Extracted to |
  |---|---|---|---|
  | `crew-setup` | 618 | 442 | `trackers.md`, `claude-md-authoring.md` |
  | `crew-verification` | 588 | 464 | `credentials-and-playwright.md` |
  | `crew-providers` | 566 | 468 | `alternative-providers.md` |

  Every bundled `SKILL.md` is now under 500 lines; the largest is 468. The main
  files keep the path every reader walks, and the references hold what only
  some readers need.

### Removed

- **`crew` 0.19.52: the PreToolUse command guard is gone.** `guard.sh` and
  `guard.ps1` are deleted and unregistered from `hooks/hooks.json`. Crew no
  longer inspects any Bash or PowerShell command before it runs.

  Requested because the guard blocked ordinary development work. The
  `prod`/`production` whole-word rule was the one that fired most and had **no
  config key at all** - no value of `guards.prodDatabase` could switch it off,
  and it matched the word anywhere in a command string, including inside a
  commit message or a `gh pr comment` body. The two keys that *do* read as the
  production guards are inert in any repo that has declared no
  `production.databases` or `production.hosts` patterns, so the setting that
  looked like the fix was not one.

  **What still blocks, unchanged:** `promote-gate` (dirty tree, missing sha,
  absent verify evidence), `verify-gate` (the Stop gate over
  `.crew/verify.json`), `guards.mergeGate` for `/crew:gate`, and the PM's four
  `AUTONOMOUS_STOPS`. `crew_guards.py` is kept - `mergeGate` and
  `change.requireForProduction` still resolve through it. Five of the six
  `guards.*` keys still parse and ratchet but now govern nothing, and
  `README.md` and `CONFIG.md` say so in the tables rather than leaving them
  reading as live.

  `hooks.json` drops from 20 entries across 10 scripts to 18 across 9.

  Test surface: `run-tests.sh` loses its five guard sections (the PATH-scrub
  machinery stays, because promote-gate's own coverage depends on it);
  `test_guard_bypasses.py`, `test_guard_powershell.py` and
  `test_guard_command_spelling.py` are deleted, all three existing solely for
  the removed scripts; `test_guards.py` loses its 16 script-executing tests and
  keeps its 114 config/ratchet ones; `test_malformed_production_never_permits.py`
  loses 4 script cases and keeps its module cases;
  `test_unmanaged_repo_is_left_untouched.py` loses one; `sabotage.py` loses 9
  of 155 mutations.

### Changed

- **`crew` 0.19.52: context clearing is aggressive by default, and the
  wrap-up/clear/resume loop is closed.** Five `context.*` defaults moved. All
  remain configurable and none ratchets, so any can be set back.

  | Key | Was | Now |
  |---|---|---|
  | `context.warnAt` | `0.8` | `0.5` |
  | `context.reserveTokens` | `100000` | `0` |
  | `context.autoWrapUp` | `false` | `true` |
  | `context.autoResume` | `false` | `true` |
  | `context.autoClear.enabled` | `false` | `true` |

  **`warnAt` alone would have changed nothing.** The threshold is the LATER of
  `warnAt * budget` and `budget - reserveTokens`. At `0.5`/`100000` a 1M window
  still fired at 900k because the floor won, so the floor had to go to 0 for
  the percentage to become operative. A 1M window now warns at 500k.

  The five form one loop: `autoWrapUp` makes the threshold message a directive
  asking for the change in flight to be finished or abandoned and the ticket
  updated; `autoClear` types `/clear` on the turn AFTER the handoff appears;
  `autoResume` folds that note plus its next action into the following
  session's brief.

  **Enabled is not the same as acting.** `autoClear` still refuses unless
  `.crew/.handoff-requested` exists, the handoff is newer than the request and
  clears `minHandoffLines`; on Windows it refuses without
  `context.autoClear.windowTitle`, because SendKeys types into whatever has
  focus. Both flavours read the RAW config and require `enabled is True`, so
  the new default reaches a repo only once its config carries the key - a
  pre-0.19.52 config stays off until `/crew:upgrade`.

  `budgetTokens` auto-detection is unchanged. Not changed because it already
  worked: `pm_brief` keys its once-per-session claim on session AND source, so
  `/clear` re-fires the brief and a fresh PM is spawned.

### Added

- **`crew` 0.19.52: an `autoClearInert` trigger, so auto-clear cannot be on and
  silent.** On Windows with no `windowTitle` the setting reads as ON and can
  never act, and the refusal only ever reaches `.crew/.autoclear.log`. That is
  the failure mode this repository's CLAUDE.md names first: an unknown
  collapsing into the safe-looking value. `crew_state.read_auto_clear` makes it
  its own value (`inert`), a trigger carries it into the PM brief at every
  session start, and `agents/pm.md` says to hand the user the one config key
  rather than dispatch a role or guess a window title.

  **Deliberately not claimed for posix**: that flavour has three methods and
  real fallbacks, so calling it inert would be a guess wearing the label the
  key exists to remove. The Windows refusal is measured. Five cases cover it,
  four asserting silence.

### Fixed

- **`crew` 0.19.52: two tests killed `pwsh` before it could run the script
  under test.** `test_verify_gate_bash_resolver.py` faked `SystemRoot` in the
  subprocess environment so tier b's System32 filter would apply. pwsh 7.6.6
  reads `SystemRoot` during startup - `InitialSessionState`'s static
  constructor reaches `SecuritySupport.GetSaferPolicy` - and a tree with no
  real System32 aborts the interpreter with `Win32Exception (126): The
  specified module could not be found`, rc `2148734499`, before a line of the
  script runs.

  Isolated to one variable rather than inferred from the stack trace: faking
  `PATH` alone reproduces nothing, faking `SystemRoot` alone reproduces it
  exactly. The fix sets `$env:SystemRoot` INSIDE `-Command`, so pwsh boots
  against the real System32 while the script still sees the fake tree - which
  is all the filter compares against.

### Added

- **Menu item 25, `perplexity-mcp`: register the Perplexity MCP server.** Off by
  default like every row from 9 on, and added at the END of both catalogs so no
  existing number moves. Registers `npx -y @perplexity-ai/mcp-server` with
  `--env PERPLEXITY_API_KEY=<key>`, through the same `add_mcp_server` /
  `Add-McpServer` helper every other row uses, so an already-registered server is
  reported and skipped rather than re-added. The key comes from
  `--perplexity-api-key` / `-PerplexityApiKey`, falling back to `PERPLEXITY_API_KEY`
  in the environment; with neither — or with a blank or whitespace-only value — the
  item prints where to create one and **skips**, because a server registered with an
  empty key looks installed and can never authenticate. Neither script ever echoes,
  logs or interpolates the key, and `scripts/_test/menu-groups.sh` case 8 asserts
  that with a sentinel key: it greps the whole captured run for the value and fails
  if it appears. That suite's stub records the `claude` command line in a file rather
  than on stdout for exactly that reason. This is the server
  [`web-research`](skills/web-research/) calls.
- **`check_menu_parity` also counts `MENU_NAME`.** `MENU_KEYS` order and
  `MENU_DEFAULT` length were checked; the labels array was not, so a row added to
  `MENU_KEYS` alone passed every gate and shifted every label after it onto the next
  item's text — the `obsidian-mcp` bug, recorded further down this file. Sabotaged:
  deleting the new label fails the check with "MENU_NAME has 24 labels but MENU_KEYS
  has 25 rows".
- **`web-research` 1.0.0: makes live-web research fire on intent rather than on
  the word "perplexity".** It registers nothing — the `perplexity` MCP server is
  already registered globally, and the skill's whole job is routing: which of
  `perplexity_search` / `_ask` / `_research` / `_reason` fits the question,
  when recency and domain filters matter, and where the boundary sits.
  The routing carries one fact the server's own tool descriptions do not: in
  `@perplexity-ai/mcp-server` **1.2.1**, `perplexity_research` accepts **no
  filters at all** — `researchInputSchema` is `{ messages }` and the handler
  passes `undefined` options — so a recency or domain argument sent to the one
  tool you would most want to filter is dropped silently and the call still
  succeeds. `perplexity_search` likewise takes no `search_context_size`, but does
  take `max_results`, `max_tokens_per_page` and `country`. Both read out of
  `dist/server.js`, tabulated per tool, and marked as a fact about 1.2.1 that the
  live schema overrides.
  Two boundaries are stated rather than implied. Library, framework, SDK, API,
  CLI and **cloud-service** reference goes to **Context7**, not here, because
  "find current docs for X" is the one phrase both surfaces match; the split is
  documentation (how a thing is used) versus currency (what is true about it
  now), stated in the skill's own words rather than by citing a machine-local
  rules file that no installer of the skill would have. And when the server is
  down, `WebSearch`/`WebFetch` is a **weaker**
  answer — no recency filter, no domain restriction, no citation structure — so
  the skill requires saying so rather than downgrading silently.
  The trigger is description matching, which is probabilistic and not
  enforceable. `SKILL.md` says that about itself in its own words and points the
  user at the lever they own (a line in their `CLAUDE.md`). No hook ships with
  it: this repo defaults hooks to OFF and requires a sabotage-tested regression
  suite, which routing guidance does not warrant.
  No credential is in any file — the API key stays in the existing global
  registration, and the operator section names the env var — `PERPLEXITY_API_KEY`,
  the name `dist/index.js` itself reads — without ever printing its value. Its
  connectivity probe is `claude mcp list`, run and verified to print
  `perplexity: npx -y @perplexity-ai/mcp-server - ✔ Connected` and no key. The
  skill also warns against the probe that looks obvious and is not:
  `npx -y @perplexity-ai/mcp-server --help` parses no argv, so it hangs on stdin
  with a key and exits 1 without one.

### Fixed — install scripts

- **A key given as `--perplexity-api-key=<key>` was printed on the terminal.** The
  `=` spelling matched no arm of the argument loop, so it fell through to
  `*) echo "Unknown option: $1"`, which echoed the whole token — the secret, verbatim,
  into the terminal and any log capturing it — and the run then carried on as though
  no key had been given and skipped the row. Both key flags now accept the `=` form
  (`--obsidian-mcp-key` has the same shape and the same hole, so it is fixed in the
  same line), and the unknown-option arm reports `--some-flag=<redacted>` for a
  `=` token and `<redacted value>` for a bare one. PowerShell had the identical
  defect one layer lower: it does not bind `-Name=value` at all, and its binder error
  quoted the whole token, so the fix there is a `ValueFromRemainingArguments`
  parameter that catches unbound tokens before the binder can print them. A
  consequence worth knowing: an unrecognised option on Windows now warns and the run
  continues, as it always has on Linux, where it used to abort the run.
- **The Perplexity row's closing note was printed on Linux and not on Windows.** The
  `.sh` prints it after `add_mcp_server` returns, which includes the
  already-registered path; the `.ps1` passed it as `-Note`, which `Add-McpServer`
  emits only where it actually registered. Windows showed the SKIP alone. The `.ps1`
  now prints the note itself, after the call.
- **`scripts/_test/ps-install-keys.sh`: the first committed check that runs
  `install-prerequisites.ps1`.** Nineteen cases over the key-taking row — no key, a
  whitespace-only key, the flag, the `=` spelling, the environment fallback, unknown-
  option redaction, and the already-registered path including that note — under a stub
  `claude` that records its command line to a file rather than stdout, so "the key is
  never printed" cannot pass for the wrong reason. It SKIPS loudly off Windows, where
  that script cannot start. Sabotage-proven: restoring `-Note` fails the note case,
  and dropping the `=` handling fails four.
- **`INSTALLATION.md` no longer claims "Neither script ever prints the key."** It was
  an unqualified security absolute that the repro above falsified, and nothing checks
  it. It now states what the item's own output does and does not contain.

### Changed

- **`web-research` 1.0.1: the operator section now describes both ways the server
  arrives.** It read "Perplexity is registered **globally** ... Nothing in this repo
  registers it, and nothing should" — a design assertion that menu item 25 reverses,
  and the kind of half-change that looks correct until someone holds both halves.
  Rewritten to name the two paths (by hand in `~/.claude.json`, or by the
  installers' row 25) and to say the skill does not care which; `claude mcp list`
  is still the probe. The same claim in the file's opening paragraph and in the
  marketplace description went with it, and the catalog rows in `README.md` and
  `skills/README.md` no longer say "already registered globally". Either path
  leaves the key on disk in the MCP registration, which the section now states,
  since that is the one copy anything should reference.

### Fixed

- **`crew` 0.19.50: two fixture failures that read as test results.** Codex
  round 4 - one BLOCK, one FIX, both in `scripts/_test/crew-ignore-policy.py`
  rather than the checker, and both the same class: a suite reporting on itself
  rather than on the code.
  The fixture ran `git add -A -f` with `check=False` and discarded the result.
  The checker reads its sources from `git ls-files`, so an empty index means it
  never sees the shipped template - and the "template losing its marker" case,
  which expects exactly one `does not carry` finding, then PASSES because the
  fixture was never built. Reproduced directly before fixing: with the index
  staged and with it empty, that case produced the same single finding both
  times. Staging is now checked, and so is the resulting index - every file
  written must appear in `git ls-files`, or the fixture raises. This is the
  neighbour of the `git init` check added in 0.19.49, which is the shape every
  round of this review has had.
  The suite-agreement check grepped one file for single lines starting with
  `assert` that contained both `.approved-*` and `.index(`. It now parses with
  `ast` and inspects whole `Assert` statements via `ast.unparse`, so the same
  contradiction written across several lines - the form a reformat produces -
  is caught. It also asserts the expected test EXISTS by name, because the
  grep version passed on an empty file, a renamed test and a deleted one: a
  check that can pass by finding nothing is the same bug one level up.

- **`crew` 0.19.49: the fix for a false PASS on a leading space became a false
  FAIL on a trailing one.** Round 2 blocked because `.strip()` normalised a
  broken rule into a valid one. The fix made handling verbatim. Round 3 blocks
  because verbatim comparison rejects `.crew/* `, which git honours - the same
  rung-short pattern, inverted. The right answer was neither: git treats the two
  ends of a line differently, so presence checks now use `_git_canonical`, while
  the behavioural probe still sees the original text.
  Probed directly rather than taken from the documentation, and one result is
  not what "strip trailing whitespace" would predict: a trailing SPACE is
  stripped by git, a trailing TAB is **not** (`.crew/*<TAB>` matched nothing), a
  backslash-escaped trailing space is literal, a leading space is significant,
  and a trailing `\r` is removed. A blanket `rstrip()` would have accepted the
  tab - so that mutation is now its own regression case.
  **Two committed suites disagreed about what was correct.**
  `test_verify_absent_and_diagram_kind.py` asserted `.crew/.approved-*` must sit
  below the un-ignore list, while `scripts/_test/crew-ignore-policy.py` asserted
  the alternate ordering PASSES. Both green, and whichever a reader opened first
  looked authoritative. The ordering assertion is gone - git says position does
  not matter - and the agreement between the two suites is now itself checked, so
  this specific contradiction cannot come back silently.
  That test file was a SIXTH file carrying the withdrawn claims, and the 0.19.48
  sweep reported five. The sweep was the problem: it grepped `--include="*.md"`
  for particular wordings, so a `.py` file asserting the same thing in code was
  invisible to it. Re-run across every tracked file with no extension filter and
  on the concept rather than the phrasing.
  The suite is now runnable by someone other than its author. In a shell with
  `GIT_WORK_TREE` set it reported 28 of 34 failures - the fixture's own `git
  init` failing, nothing to do with the code under test. Its git calls are
  scrubbed, a failed fixture init raises instead of cascading, and it passes
  identically under `GIT_WORK_TREE`, `GIT_DIR`, `GIT_CONFIG_GLOBAL` and
  `MSYS_NO_PATHCONV`, and from a fresh clone.
  One self-inflicted bug worth recording: the scrub first called `clean_env()`
  as the argument of an `os.environ.update()` that followed `os.environ.clear()`,
  so it read an already-emptied environment and python could not find git at all.
  Same shape as this repo's `open(p, "w")` landmine - the destructive call
  happening before the value it needs exists. Compute first, then clear.
  Also removed five stray `\r\r\n` sequences in `check-marketplace.py` left by
  line-based patching on a CRLF file; pylint reported them as
  `E0001: invalid non-printable character U+000D` while the gate still ran.

- **`crew` 0.19.48: the round-1 fix normalised the bug away, and the probe that
  replaced it could not tell a fatal git error from a clean result.** Codex
  re-reviewed and returned two BLOCKs, both inside the code written to fix the
  previous round - this repo's documented pattern of a fix being right about its
  own case and one rung short of its neighbour.
  `_active_rules` called `.strip()`, so `!.crew/endpoints.json` and
  ` !.crew/endpoints.json` became the same string: the checker REPAIRED a broken
  rule and then verified the repair. Measured - with the leading space git leaves
  `.crew/endpoints.json` IGNORED while the next line's `.crew/verify.json` is
  correctly un-ignored. Rules are now kept verbatim. The comment test was
  measured too, and only a line whose FIRST character is `#` is a comment: git
  treats `  # foo` as a pattern, so stripping before that test would have
  dropped a line git obeys.
  `_ignore_behaviour` read any non-zero `git check-ignore` status as "not
  ignored", merging 1 (checked, not ignored) with 128 (fatal, no answer), and
  discarded the `git init` status entirely. Mocking either produced an empty
  finding list and a clean report - the recurring bug this repo names, an unknown
  wearing the label of a check that happened. 0, 1 and everything else are now
  three outcomes, and anything that is not 0 or 1 is reported as UNVERIFIABLE
  rather than resolved either way.
  The probe is isolated from the machine, and the two halves of that were
  measured rather than asserted. The environment scrub is load-bearing: with
  `GIT_WORK_TREE` inherited, `git init` exits 128 and the probe answers nothing;
  stripping `GIT_*` fixes it, run both ways. The `-c core.excludesFile=` flags
  are NOT demonstrated to change any verdict - a repository `.gitignore` outranks
  both `core.excludesFile` and `info/exclude` in git's precedence, so nothing at
  those layers can overturn a rule under test. They are kept as free insurance
  and documented as unproven, because the alternative is a comment claiming a
  guarantee nobody checked.
  `.crew/verify.json`'s interpreter resolution now tries `pwsh.exe` and the
  Windows locations with and without the suffix: under WSL the reachable binary
  is the Windows one and is named `pwsh.exe`, so the previous list reported TOOL
  MISSING on a box where PowerShell was installed and usable.
  Two rationale corrections from 0.19.47 had not propagated. `plugin/crew/
  README.md`, `crew-setup/SKILL.md`, `phases.md`, `CLAUDE.md` and
  `plugin/PLUGINS.md` still said the ordering of `.crew/.approved-*` was
  load-bearing, or that the GATE writes the approval marker. The operator creates
  it; the gate writes `.crew/.deploy-in-flight`. Found by grepping the claim
  rather than the three cited lines.

- **`crew` 0.19.47: the checker shipped in 0.19.46 read comments as rules, and
  three mutations proved it.** Codex review of PR #161 returned DO NOT MERGE.
  `check_crew_ignore_policy` extracted paths from the raw source block, so a
  COMMENTED-OUT negation still counted, a deleted rule whose explanatory comment
  named the path still counted, and a deleted `.crew/*` whose comment mentioned
  it still satisfied the base-ignore check. Each mutation produced zero
  failures. Extraction now runs over ACTIVE rules only - non-blank, non-comment.
  The deeper fix is that the check stopped reading the rules and started running
  them. `_ignore_behaviour` writes the rules into a throwaway repo and asks
  `git check-ignore` what they actually do. That is the same program that
  decides it for real, and it subsumes every ordering question at once -
  including `.crew/*` written BELOW the negations, which suppresses all three
  while satisfying every is-this-line-present assertion. All four mutations were
  re-applied to the real files and the real gate went RED for each.
  Two claims this repo made about itself were disproven by that probe and are
  corrected rather than quietly dropped. `.crew/.approved-*` and `.crew/*.lock`
  are **redundant** belt-and-braces: with both deleted, `git check-ignore`
  returns byte-identical verdicts, so omitting the explicit rule does NOT make
  the approval marker trackable, and the `.gitignore` comment plus `TODO.md`
  section that said otherwise were wrong. The gate also does not WRITE that
  marker - the operator creates it (`promote-gate.sh:235`); the file the gate
  writes is `.crew/.deploy-in-flight` (`:288`).
  **`.crew/verify.json` was not clone-safe and the sweep that said it was looked
  for the wrong thing.** It searched for `C:\` and `/Users/` and never for the
  Git Bash `/c/...` form, which is exactly what rule 129 contained: a hardcoded
  `"/c/Program Files/PowerShell/7/pwsh"`. `verify-gate.sh` executes that and
  blocks completion on a non-zero exit, so this PR - which is what makes the map
  travel - would have blocked every Linux clone, including one with pwsh ON
  PATH. The rule now resolves its interpreter: bare `pwsh` first, then the two
  Windows locations, and exit 127 with TOOL MISSING on stderr when none
  resolves, because a tool that could not run must never report as a check that
  passed. The withdrawn clone-safety claim is recorded in `.gitignore` rather
  than deleted - "already checked for absolute paths" is what stopped anyone
  looking twice.
  `TODO.md` also claimed `declare_endpoint` was the only writer of
  `endpoints.json`, quoting that function's own docstring, which asserts it and
  is wrong about its own module: `record_scan_artifact` at
  `crew_endpoints.py:757` writes the ledger too. Neither is on a promote or
  incident path, so `promote-gate.sh` still does not change - but the evidence
  under that conclusion did.
  One more found while sabotage-testing: the 0.19.46 CHANGELOG entry named the
  marker, which silently made an append-only history file a marked source. It
  passed only because the policy it describes is today's; the next entry
  recording a change to the list would have failed for being accurate about the
  past. History is excluded, with a regression case.

- **`crew` 0.19.46: the repo stated three `.crew/` ignore policies at once, and
  one of them was in the same file that contradicted it.** `.gitignore` ignored
  `.crew/*` and re-admitted `codemap/` and `endpoints.json` - then, fifty lines
  below those negations, a comment block asserted that ".crew/ and .work/ are
  ALREADY fully ignored above" and that "the whole of crew's state - config.json,
  verify.json, STATUS.md, INDEX.md, PROMOTIONS.md - is local to each machine and
  never committed". Both halves shipped, in one file, for months. Elsewhere
  `README.md` said `.crew/config.json` "is committed" and used that as the entire
  rationale for the `platform-sync` hook; `commands/review.md` and
  `crew-verification/SKILL.md` each carried a paragraph correcting an *earlier*
  wrong claim in the opposite direction. The policy, now stated in one form
  everywhere: `.crew/*` is ignored and a NAMED list is un-ignored -
  `!.crew/codemap/`, `!.crew/endpoints.json`, `!.crew/verify.json`. `.work/`
  stays ignored entirely, `config.json` stays machine-local, and
  `.crew/.approved-*` sits BELOW the negations so promote-gate's own approval
  marker can never become trackable.
  `check_crew_ignore_policy` in `scripts/check-marketplace.py` is what stops it
  drifting again: the list is read from `.gitignore` (the only copy git obeys)
  and every file carrying the `crew-ignore-policy:list` marker must state the
  same set. Marker-keyed on purpose, like `check_self_claims` - `TODO.md` and
  `commands/review.md` mention one or two paths in passing and must NOT be read
  as declaring the list. `scripts/_test/crew-ignore-policy.py` asserts that
  silence alongside the failures, 16 cases, and each of the four guard branches
  was sabotaged individually and confirmed to take the suite red.
  The marker carries a colon because the first version did not: a bare
  `crew-ignore-policy` is a legal filename, and the CI step that runs the suite
  names the file, so `.github/workflows/marketplace.yml` was flagged for
  declaring a policy it was only citing.
  Review caught a live false positive before merge, worth keeping visible: the
  ordering assertion searched the WHOLE markdown file, so one sentence written
  below §3c's fence would move the last `!.crew/` past `.crew/.approved-*` and
  fail a correct template - the "fails correct lines" mode, inside the check
  written to prevent it. Ordering is now scoped to the fenced block, with a
  must-allow case for prose on either side of it. The same round found the
  no-fenced-block path reporting "does not carry the marker" about a file that
  plainly does; carrying the marker and declaring a list are now separate facts.
  **This repo now tracks `.crew/verify.json`, which is a practice change rather
  than a docs fix.** Its own `CLAUDE.md` already described that file as "the
  mechanism" for per-path verification while nothing tracked it, so every clone
  read "no verification map" and selected no specialist - indistinguishable from
  "no rule matched". Checked clone-safe first: no URL, hostname or Windows
  absolute path. One thing the check surfaced and did not fix -
  `.crew/verify.json:129` runs `"/c/Program Files/PowerShell/7/pwsh"`, an
  absolute path in Git Bash form that carries no secret but cannot run on a
  Linux clone.
  `promote-gate.sh` was **not** changed. Its clean-tree check does run before the
  step that tells you to create the approval marker, but under this list no file
  that is both tracked and written during a promote or an incident exists -
  `git check-ignore` on ten candidate paths, plus `crew_endpoints.py:258`
  naming `declare_endpoint` as the sole writer of `endpoints.json`. The reorder
  is written down in `TODO.md` with the evidence instead, because a blocking hook
  needs a sabotage-tested regression suite and spending one on an unreachable
  deadlock buys nothing. The reachable version of that deadlock is a consuming
  repo that adopts the un-ignore list but omits `.crew/.approved-*`, and the
  shipped template in `crew-setup/SKILL.md` §3c now lists it explicitly.
  `test_verify_absent_and_diagram_kind.py` had a trip-wire asserting the map was
  NOT tracked, whose docstring said that if it ever became tracked "this test
  fails and the wording in review.md gets revisited instead of quietly going
  stale". It fired, and the wording was revisited. It is re-armed pointing the
  other way, and now also pins the ordering the policy depends on.

- **`crew` 0.19.45: `crew_state.py` split, because the alternative was shaving
  another comment.** The module was 3299 lines against `max-module-lines =
  3300`. It had been one line from failing CI three times, and each time
  somebody shaved a comment to buy room - trading documented reasoning for a
  line count. `.pylintrc:113` says what to do on the third occasion, and this is
  that. The boundary is where the AST put it rather than where the ticket
  guessed: scanning every top-level symbol's references showed the slice closed
  except for three outbound edges, with no cycle, and one question running
  through all of it - has the artefact's recorded sha moved since. Moving only
  the named helpers would have left the module around 3210, one comment from the
  ceiling again, so the whole slice moved. 474 lines are byte-identical and no
  comment was shaved to make it fit. `crew_state.py` 3299 to 2858;
  `crew_freshness.py` 537; `max-module-lines` unchanged.
  21 names moved and all stay reachable through `crew_state`, following
  `crew_guards`' re-export shape rather than inventing a second convention.
  Zero call sites needed editing - every external caller already spelled them
  `crew_state.<name>` - and an AST scan confirmed no test rebinds a moved name
  with `monkeypatch.setattr`, which would have bound the copy rather than the
  original.
  One sabotage mutation was anchored inside the moved lines, found by scanning
  every mutation's anchor text against the moved block by AST rather than by
  eye; its `FILE` constant moved with it and it is still red.
  `CLAUDE.md`'s Memory section cited `crew_state.py:409` and `:467` for the
  anchor comparison. Both numbers were ALREADY wrong before this change - the
  comparisons were at `:991` and `:1074` - and both have now moved file as well
  as line. They name `crew_freshness.py` and the right lines, the expression is
  corrected to what is actually greppable, and a clause is added for the third
  hit that grep returns, which is `_read_graph`'s fast path and not the codemap
  one.
  Equivalence was checked directly rather than only by the suite: every moved
  function, constant and pattern dumped through the `crew_state.` surface before
  and after, identical.

- **`crew` 0.19.44: fourteen things this repo said about itself that were not
  true.** Each was checked against the code before it was changed.
  "Every hook is registered once, as bash" - in the README and in
  `_common.sh`'s own header - when `hooks.json` has 20 entries naming 20
  distinct scripts, 10 pairs each registered twice, once as bash and once as
  its `.ps1` twin with `shell: powershell`; the "so `bash` must be on `PATH`"
  conclusion went with it. Seven agents described as "read-only" whose
  frontmatter carries `Bash`. Four agent names appearing twice in the roster
  table, which is now 54 rows and 54 unique names, one per agent file. "step
  10" for the docs step, which is 12, in three places. The review fallback
  written "Codex or Claude", omitting Copilot, which sits between them in
  `order`. `crew_tool_dispatch` called unused when it is called at `guard.sh:7`
  and `promote-gate.sh:27`. "python3 is not required" stated without scope -
  true of hooks, which all go through `crew_py()`, false of command files,
  which invoke it by name. A citation to `verify-anchors.py`, a file that does
  not exist anywhere in this repo. `crew-setup` claiming the `--brand` wiring
  "does not exist" when `crew-house-style` passes it, `CONFIG.md` names that
  file as the consumer, and a committed regression test asserts it by running
  doc-builder's own argparse. And five bare `python` invocations in
  `emergency.md`, under prose claiming every call resolves `python3`/`python`/
  `py`, which was false in both directions.
  Four suite counts re-measured by RUNNING each suite rather than reading a
  number: `run-tests.sh` 77 to 177, `validate-prompts.py` 110 to 298, pytest
  234 to 1404, `setup-walkthrough.sh` 32 unchanged. The README's decomposition
  of `run-tests.sh` into 20/14/12/15 is replaced by the line the runner
  actually prints, because it prints one total and no breakdown and inventing a
  new split would be the same defect again. The same four counts in
  `PLUGINS.md` are corrected here, that file being the only place left carrying
  the old ones. NO claim marker was added and none can be: `check_self_claims`
  implements exactly `skills-count` and `plugin-version:<name>`, neither can
  express a suite count, and any other type is a hard error by design - so the
  numbers stay unmarked, which is the silence `scripts/_test/self-claims.py`
  asserts, and the README now says so rather than leaving it to be guessed.
  Two reported items came back differently. "crew's eleven" was a real defect
  whose fix is NOT a corrected count: a committed test's docstring already
  states this repo's decided policy for that exact string - the roster is a
  moving number nothing checks, so remove the count rather than correct it.
  And `crew-context`'s per-repo handoff marker is a FALSE POSITIVE, left
  unchanged: it carries no `session_id`, the claim is taken atomically by
  `set -o noclobber` and `FileMode::CreateNew`, and SessionStart clears it - the
  doc accurately documents a known bug and says so.
  `newline="
"` added to the two `write_text` calls that write
  `_verify/smoke.sh`; the third already carried it. The reported CONSEQUENCE
  did not reproduce - the CRLF form ran under Git Bash's `bin/bash.exe` in
  3.07 s, rc 0, output identical to the LF form - so this is a hardening against
  a documented landmine rather than the repair of an observed failure, and the
  comment says which.

- **`crew` 0.19.43: the agent prompts claimed a mechanism crew does not have.**
  Thirty fabricated blocks are gone from sixteen files under
  `plugin/crew/agents/`: fifteen `Progress tracking:` blocks, each a fenced JSON
  object of invented counters (`files_reviewed: 47`, `uptime: "99.97%"`,
  `messages_processed: "234K/min"`), and fifteen `Delivery notification:`
  blocks, each a quoted sentence the agent is told to emit about work it has not
  measured. Crew implements no notification channel and counts none of those
  things, so an agent following them performed a ritual with no receiver while a
  reader believed crew had a reporting mechanism it does not have. Found
  repo-wide rather than from the review's list; `multi-agent-coordinator.md`'s
  `- Progress tracking` bullet is deliberately kept, being a coordination
  pattern in a list rather than a block.
  Seventeen agents across five overlapping clusters now say what they are NOT
  for, naming the concrete alternative, in `description:` - which is what the
  dispatcher routes on.
  `qa-reviewer.md`'s model claims were FALSE as written rather than merely
  unhedged, so the file says so instead of softening them into something
  unfalsifiable: `QA_DEFAULTS["roles"]` and `DEV_DEFAULTS["roles"]` are both
  empty, and `crew-providers/SKILL.md` says in its own words that its table is
  "a configuration to adopt, not what crew ships". The Sol and Luna pins
  therefore hold only where a repo wrote them, and "most dev work is
  codex-authored, so those pins never fire on it" is conditional on a second pin
  that does not ship either. Both branches are stated, the frequency claim is
  removed rather than reworded, and the file now says no proportion is available
  to the reviewer.
  The review's other suggestion for `qa-reviewer` - read `crew_config.py
  --models` rather than assume - is deliberately NOT taken: that command is this
  repo's own example of the recurring bug, deriving author family from config
  describing the NEXT run and barring Codex, the only independent reviewer, on a
  Claude-authored diff.

- **`crew` 0.19.42: a rule crew could not represent was split, not refused.**
  The ordered rule list was newline-delimited text, so a `run` entry in
  `.crew/verify.json` carrying a newline split into two rules and the second
  half ran as a command nobody wrote. Four readers had the same shape:
  `verify-gate.sh`, `verify-gate.ps1`, and `crew-setup`'s `resolve-tools.sh`
  and `map-audit.sh`. The REJECTION is the fix and the separator is the belt -
  all four refuse any `run` / `always` / `default` entry (plus
  `environments[].{deploy,smoke,regression,verify}` in `resolve-tools.sh`)
  containing `
`, `
`, `` or ``, with an identical named
  `PARSE_ERROR` naming the entry, the character and the entry's opening text;
  `verify-gate.sh` then frames its records with `` between and ``
  inside. `verify-gate.ps1` never had the framing bug - it reads objects, not
  text - but takes the same rejection, because without it the same map blocks
  the turn on bash and passes on PowerShell. A `2>/dev/null` in
  `resolve-tools.sh` that would have swallowed the refusal is gone.
  Separately, three NON-CONTENTION lock collapses in both flavours - `mkdir`
  failing with no lock directory present, the lock path being a regular file,
  and a lock directory whose age cannot be read - each read as "someone holds
  the lock" and exited 0, which is the stale-lock fail-open that made a manual
  re-run exit 0 in under a second. Each now runs the checks WITHOUT the lock
  and says so on stderr.
  Still open, deliberately: a lock left by a HARD-KILLED holder stands later
  gates down for the rest of the 700 s age window. The obvious narrowing is a
  same-flavour PID liveness check, and its premise was measured false here - a
  bash process was started, its `$$` recorded, hard-killed, and a second bash
  asked `kill -0 <pid>` at +0.5 s, +5 s and +15 s; all three reported the dead
  process ALIVE, while a pid that never existed correctly reported "No such
  process". Shipping that check would turn "could not tell" into a confident
  "the holder is alive". The measurement is recorded in `verify-gate.sh` and in
  both lock test docstrings instead of the check.
  0.19.41 was this change with its CHANGELOG committed CRLF into a blob this
  repo stores LF, which turns every later diff of this file into a whole-file
  rewrite. Renormalised here rather than by amending the pushed commit: the
  force push that would have taken is refused by `guard.sh`, correctly, and
  fixing forward costs one version number and no rewritten history.

- **`crew` 0.19.40: a config crew could not read was read as a config that
  permitted.** Three defects, one shape - the state "crew does not know" had no
  value of its own, so each collapsed into the value that permits.
  `production.hosts: "prod-web-*"`, a string where a list belongs and the single
  most likely way to write the key wrong, returned `[]` from
  `production_patterns`, and `prod_decision` reads `[]` as "nothing declared, so
  nothing matches, so allow" - the host restriction was off at every level
  including `prodServer: none`, while the config still read as though production
  had been declared. `production_declaration` returns five states now, not a
  list: `declared`, `absent`, `empty`, `malformed`, `unreadable`. Only the
  middle two mean nothing was declared; the other two allow at `full` and allow
  a read-classified command at `read` - the levels where the unknown changes
  nothing - and block otherwise, with a non-empty target, because both shells
  return silently on an empty one.
  `promote-gate.sh` collapsed absent, unreadable and not-a-map into
  `except Exception: sys.exit(0)`, so a stray comma removed every pre-deploy
  check while the deploy went ahead looking gated, output byte-identical to
  "this command deploys nothing"; the exit status carries the distinction now
  and every reason goes to stderr. `[ -f ]` became `[ -e ]` - a directory named
  `.crew/verify.json` is not an opt-out - and `deploy: "deploy-prod"` as a bare
  string, which the loop iterated by CHARACTER so that it matched any command
  containing a `d`, is normalised to one entry.
  `promote-gate.ps1`'s `Get-Content` failure is non-terminating, so a directory
  in place of the map left `$vm` null, the catch never fired, and
  `-not $vm.environments` read the corruption as "nothing declared" and exited
  0; `-ErrorAction Stop` plus type checks on the document, on `environments`, on
  each environment and on each `deploy`.
  Separately, `_log_guard` no longer creates `.crew/`. The caller skipped only
  refusals in a repo with no `.crew/`, which is the half that never fires - one
  allowed `ssh` created the directory, the next SessionStart resolved its root
  from bare `.crew/` presence, and `heal_config` wrote a full default config
  into a repo that never opted in.
  `crew_guards.py` is unchanged: the unknown is kept away from `prod_decision`
  rather than taught to it. Six new sabotage mutations, all red.

  0.19.39 was this change with one defect still in it, caught by CI and never
  released: `production_declaration` opens `.crew/config.json`, and when
  `.crew` is itself a plain FILE the two platforms raise different exceptions
  for that one tree - POSIX `NotADirectoryError`, Windows `FileNotFoundError`.
  Only the second was caught, so the state came back `absent` on Windows and
  `unreadable` on Linux, and `unreadable` blocks every `ssh` at
  `prodServer: none` in a repo that never opted in. Both read `absent` now,
  which is what `crew_platform.main` means by a root - a `.crew/` DIRECTORY -
  while a directory in place of the config FILE is still `unreadable`. The
  test that should have caught it built the tree and let the platform pick the
  exception, so it could only exercise the runner's own OS; the new pair
  raises each explicitly.

- **`crew` 0.19.38: six ways a command was spelled past a guard.** Each is the
  same shape - a spelling the guard did not recognise collapsing into the
  safe-looking answer, with nothing saying a check had been skipped.
  `env <write>` classified as a read, because `env` sat on the read-command
  list and the classifier stopped at the executable name; it is a wrapper now,
  and an `env` carrying `-i`, `-u`, `-S` or `--chdir` is unclassifiable rather
  than clear. `ip link set eth0 down` classified as a read, because the
  subcommand table is keyed on what `ip link` names, which is an object and not
  a verb. `psql -c 'select 1' -c 'delete from orders'` was classified on its
  first payload only, and psql, mysql and sqlcmd all take the flag more than
  once. `/usr/bin/ssh prod-web-1 ...` reached no resolver in either flavour,
  because both host-tool selectors required the executable to follow whitespace
  or a separator - so `prodServer` was bypassed at `none` by typing a path, and
  in the other direction an absolute-path `psql` was refused even at `full`.
  A command carrying two secret reads, the first captured and the second
  printed, satisfied a check that asked about ANY occurrence; both flavours
  count now. And on Windows, Git Bash rewrote `--command '/usr/bin/ssh ...'`
  into a native path before python saw it, so crew classified `Program` rather
  than `ssh` and wrote a command nobody typed into `.crew/guard.log`.
  Seven sabotage mutations, one per defect plus the `.ps1` twin of two, all
  red; `plugin/crew/tests/test_guard_command_spelling.py` carries the
  must-block and must-allow pair for each.

- **`crew` 0.19.37: `verify-gate.ps1` ran every rule in one process and let
  each rule change the next one's world.** Measured on aws-managed-services on
  2026-09-13, where the gate failed at every Stop with `bash -n scripts/x.sh`,
  pytest "no tests ran" and ruff `E902 cannot find the path` for files that
  exist. Rule 11 of that run was `cd drata-insights/frontend && npm test`;
  `Invoke-Expression` runs in the gate's own scope, so the `cd` moved its
  working directory and rules 12-27 ran from the wrong place. Three more
  defects fell out of the same loop, each confirmed with a two-line pwsh
  experiment before being believed: `$ok = $?` after Invoke-Expression was
  Invoke-Expression's OWN status, so a failed `cd` and a command that does not
  exist both read as passes (six rules of that run passed silently);
  `FDM_MODULE=x bash case.sh` - bash syntax the sh twin evals natively - was a
  command named `FDM_MODULE=x`, and by the previous point also a pass; and the
  lock's Exiting handler compared a RELATIVE token path, found nothing once the
  cwd had moved, kept the lock, and the next Stop within the 700 s TTL was
  silently ungated after a failing one.

  The loop now returns to the project root before every rule and after the
  last, captures the rule's own `$?` inside a `& { }` block with the `2>&1` on
  the block (a redirect on Invoke-Expression itself drops a native command's
  stderr, which is a failing case script's whole report; a parse error is a
  failed rule, not a crashed gate), peels leading `NAME=value` pairs into
  `$env:` for that one rule and removes them again (a `$null` restore leaves
  the variable present and empty, so absent-before is removed, not set), and
  resolves the lock path absolutely. `verify-gate.sh` never had any of this: it
  evals each rule inside `$(...)`, a subshell.

  **Then the loop stopped reimplementing bash and started using it.** Folded
  in from PR #151 (another session, measured on TheSelectSource): rules are
  bash strings, so they are handed to `bash -c` inside
  `Push-Location`/`Pop-Location` and judged on the child's exit status.
  That deletes the three workarounds above rather than keeping them - bash
  does `NAME=value` natively, IS bash, and reports its own status - and it
  fixes one they could not: `--grep @flow` parsed as a splat of an unset
  `$flow`, a PowerShell PARSE failure that survives anything built on
  `Invoke-Expression`. 66 lines out, 41 in. #151's own fixtures quoted the
  interpreter for PowerShell, a rule shape only half the matched pair could
  ever execute; they are bash-quoted now. Ten cases in
  `tests/test_verify_gate_rule_cwd.py`; reverting the loop to
  `Invoke-Expression` reddens five of them.

- **`crew` 0.19.35: two defects in 0.19.34, both one rung from the fix that
  introduced them.** Found by a Rule of Two review, each reproduced before being
  believed. This is CLAUDE.md's "re-review the fix to a guard as hard as the
  guard" landing on the guard fix from the previous release.

  `_CITED_PATH_RE` carried an extension allowlist — py, sh, ps1, yaml, json, md,
  which is the set *this* repo contains — and it **failed open**. A map citing
  `src/OrderService.cs:1` beside `appsettings.json` yielded only the json, so once
  the C# moved the map reported `behind: []`. Any .NET, TypeScript, Go or
  Terraform repo got a freshness signal structurally unable to see its own source,
  and every fixpoint fixture used `.py` so the suite could not see it. Measured on
  this repo, the widened pattern gives the `mcp-servers` map **10 TypeScript
  files** it had been blind to. Existence is now the only gate, with a test that
  widening did not turn every code span into a pathspec.

  "A diagram cites no file paths" was **false**, and had been written into a code
  comment as the justification for using the whole-tree deny-list. `crew-diagrams`
  writes `%% Anchors: a/b.py, c/d.sh` for exactly this purpose. Measured here, 4
  of 6 diagrams had **zero** changed files among their own declared anchors while
  the deny-list called all 6 stale — so the wrong claim was also the reason the
  count would not come down, and four correct diagrams would have been redrawn.
  `diagramsStale` 6 → 2. A diagram with no anchors line still falls back to the
  deny-list, asserted, since an empty pathspec would make every unanchored diagram
  read current forever.

  `knowledgeBehind` stays 8 — this repo is all `.py` and `.sh`, so the widened
  pattern changes nothing here. It was never this repo the allowlist broke.

- **`crew` 0.19.34: `knowledgeBehind` and `diagramsStale` had no fixpoint, so
  refreshing could never clear them.** Both compared `anchor == HEAD` and
  nothing else. `.crew/codemap/` and `docs/diagrams/` are **tracked**, so
  recording a refresh takes a commit — and that commit moves HEAD past the sha
  the refresh just wrote. The map was behind again the instant it was saved.

  Measured in a throwaway fixture rather than argued: a codemap anchored at
  HEAD reports `behind: []` while uncommitted and `behind: ['sub']` once
  committed.

  `_read_graph` already carried this fix and names the failure in its own
  comment — "treating it that way gave this trigger NO FIXPOINT". It had been
  applied to the graph trigger only.

  `read_knowledge` now asks what its docstring always claimed it asked:
  `git diff --name-only <anchor>..HEAD -- <the paths the map cites>`, with empty
  output read as current despite the lag. That comparison was documented and
  never implemented, so every map went behind on any commit anywhere in the
  repo — the same as no signal at all. `read_diagrams` takes the deny-list form,
  since a diagram draws nodes rather than `path:line`; `docs/**` being excluded
  is what makes it terminate.

  `None` stays distinct from `False` throughout: an unresolvable sha, a missing
  git or a failed diff resolves to **stale**, and `unresolvable` remains its own
  third value. A rotted citation narrows nothing — paths that no longer exist are
  dropped, so a map whose citations broke falls back to the wider comparison
  rather than reading current *because* it cites a deleted file.

  Effect here: `knowledgeBehind` 10 → 8 (two maps were already current, agreeing
  with an independent per-path sweep run before any code changed);
  `diagramsStale` 6 → 6, which is correct — this makes the triggers clearable, it
  does not declare stale things fresh.

### Added

- **`crew` 0.19.33: tests for two properties CLAUDE.md calls load-bearing and
  nothing checked.** Both were found by mutation rather than by reading: each
  change left the **entire** crew suite green at exit 0, so the suite could not
  tell the working code from the broken code.

  `reportTracked` decides which graph-refresh command the pulse recommends, and
  the two are not interchangeable — `graphify . --no-viz --code-only` skips
  `GRAPH_REPORT.md`, so in a repo that tracks the pair it leaves the two tracked
  files describing different builds. Renaming the key in
  `crew_state._read_graph` degraded the pulse to the forbidden form silently,
  because the only tests touching it hand-build a `graph` dict and call
  `pm_brief.render` — they exercise the consumer and never the producer. The
  case that earns its place asserts an **untracked** `GRAPH_REPORT.md` on disk
  does *not* count: the code asks git, not the filesystem, and one stray local
  artefact must not flip the recommendation for everyone who cloned.

  Anchor truncation — both sides cut to 7, so 8- and 40-character anchors match
  as exactly as 7-character ones — is what stops a reader rewriting correct
  anchors. Changing every `[:7]` to `[:40]` left the suite green. Now covered at
  both sites carrying a copy of the comparison, each with a control asserting a
  genuinely older anchor is still behind.

  The third site is **not** pinned, and the test says so rather than implying
  coverage: `_read_graph`'s fast path falls through to the deny-list diff, so
  the same mutation changes no output and no behavioural test can catch it.

  Sabotage-verified both ways: the rename reddens 4 of 10, the truncation
  reddens exactly the 2 that can be reddened.

### Fixed

- **`crew` 0.19.32: ruff flagged 36 deliberate re-exports, and one test failed
  for running `/crew:verify`.** Two defects that only surface once something
  actually runs the checks, which is how both survived: ruff is not in this
  repo's CI, and the test needed a crew command to have been used.

  `crew_state.py`'s `crew_guards` re-export block carries a
  `pylint: disable=unused-import` and a comment saying why. Ruff does not read
  pylint pragmas, so all 36 names were errors the moment anything ran
  `ruff check .` — which a verification map's python rule is the first thing
  here to do. Suppressed **per name**, and deliberately **not** with `__all__`:
  ruff accepts `__all__` as proof of re-export, but it doubles as the module's
  advertised public surface, and one listing only the `crew_guards` names would
  declare `read_metrics`, `evaluate_triggers` and the rest private while every
  caller spells them `crew_state.<name>`. Trading a lint error for a false
  statement about the module is not a fix. Sabotage-verified: an unused
  `import uuid` added to the same file still exits 1, so the suppression is
  narrow — which is the whole argument for it.

  `test_verify_json_really_is_ignored_here` asserted the wrong thing. Its
  docstring says it fails if `.crew/verify.json` becomes **tracked**; what it
  asserted was that the file is **absent from disk**. Those are different
  claims, and `/crew:verify` is a command crew ships whose entire job is
  writing that file — so the first time anyone ran it, crew's own suite went
  red over a file crew had just been asked to create, pointing at a wording
  question in `review.md` that had not changed. It now asserts not-tracked via
  `git ls-files --error-unmatch`, verified to discriminate rather than merely
  pass.

### Added

- **`crew` 0.19.31: `/crew:change`, change requests into SDP, Jira or a file,
  and a gate that refuses to file an unanswered one.** One process, three
  backends, chosen by crew's existing `tracker`: SDP files against the
  configured `change.sdpTemplate` through the SDP tooling, Jira creates the
  configured `change.jiraIssueType`, and `local` writes
  `.work/changes/<id>.md`. The content is identical in all three. Missing
  tooling for the chosen backend is a **stop that names the install** — never a
  quiet fall-through to `local`, which would file a production change into a
  text file nobody reads.

  **The ten questions are the feature, and they are enforced in Python rather
  than in prose.** The template's own rule is that every question must be
  answered; a command file can say that and cannot enforce it, because nothing
  parses a command file at runtime and "I checked the answers" is exactly the
  shape of claim that collapses an unknown into the safe-looking value. So
  `plugin/crew/hooks/scripts/crew_change.py` is a pure validator with no I/O:
  `new` gates questions 1-9 and names every one that is empty or a placeholder,
  `close` gates question 10 — the post-change validation results — and nothing
  else. The asymmetry is deliberate: requiring 10 at filing time would make the
  gate unsatisfiable and teach the operator that `N/A` is how you get past it.
  25 placeholder spellings are refused (`TBD`, `N/A`, `see above`, `none`, `?`,
  …), matched against the whole normalised answer so "none of the databases are
  affected" passes; `no` is deliberately not on the list, because it is a true
  answer to "has there been a notification sent".

  **Schema 7** adds the `change` block to both config layers, and
  `change.requireForProduction` joins the ratchet table as a permission a repo
  may turn **on** and may never turn off — the opposite direction to every
  other ratcheted key, achieved by ordering its tiers `(True, False)` so the
  existing `min(rank(repo), rank(global))` yields it with no second mechanism.
  It is also the one ratcheted key whose default is not its floor: absent reads
  as the shipped `false`, while a malformed value reads as `true` and fails
  closed. Default `false` keeps today's `/crew:promote` behaviour exactly.
  When it is on, promote's first gate requires an approved change for **this**
  sha, read from the backend every time — a cached `approved` is a claim about
  the past — with "could not read the state" and "outside the change window"
  both stops rather than passes.
- **`github` 1.0.0: a merge-gate script that reads both of GitHub's gate
  surfaces, not whichever one the repo happens to use.** `skills/github/
  scripts/merge_gate.sh` is the twin of `skills/bitbucket/scripts/
  merge_gate.sh`, and it settles the open question in `docs/guard-overrides.md`:
  the export captures **classic branch protection and rulesets together**, each
  carrying its own `state`, and `unreadable` is a third value that never folds
  into `absent`. Two live probes decided that. Reading a protected branch
  without admin answers `404 {"message":"Not Found"}` while reading an
  unprotected one answers `404 {"message":"Branch not protected"}` -- same
  status, and `repos/cli/cli/branches/trunk/protection` gives the first from a
  token without admin on a branch that *is* protected, so anything but that
  exact message is "could not read". And `GET repos/{o}/{r}/rulesets` returns
  rows with no `rules` and no `conditions` (checked against
  `repos/facebook/react/rulesets`), so an export built from the list restores a
  ruleset with the right name and no protection in it, with nothing in the file
  saying so. Every ruleset is fetched by id.

  Exit semantics mirror Bitbucket's -- 3 means nothing was deleted, 4 means
  partial writes and names what landed -- with exit 3 widened to three causes:
  a ruleset condition the script cannot evaluate, a gate surface it could not
  read, and an **organization or enterprise ruleset that gates the branch and
  that `DELETE` on the repo endpoint cannot remove**, where removing everything
  else would leave the gate partly on while reporting success
  (`--allow-inherited` accepts that trade deliberately).

  Two deliberate divergences from the Bitbucket twin, both documented in
  `SKILL.md` so nobody "fixes" them back: `enable` has **no preset** and exits 2
  without `--from-export`, because a preset invents a gate rather than putting
  back the one that was removed; and `--dry-run` sends **no request and writes
  no file, the export included**, so it prints the call sequence rather than a
  per-object plan.

  The export is validated **against the API's own declaration, re-read from
  disk, before any `DELETE`**: the ruleset count must account for every listed
  row, and `classic.state: "present"` must carry a real protection object. A 200
  whose body is valid JSON but not a protection document otherwise validates
  clean, survives the delete, and only fails at restore time -- with the gate
  already gone. Both mismatches abort with nothing written and nothing deleted.

  `--allow-inherited` turns the exit-3 refusal into exit 0 on a branch that is
  still gated, so the run now also prints a `WARNING:` on **stderr** naming how
  many inherited rulesets stand. A caller that reads only the status -- which is
  the normal case -- would otherwise read "gate off" forever after.

  `scripts/_test/merge_gate.sh` is 153 offline checks against a stubbed `gh`
  (`GH_CMD`), no network and no credentials. Six sabotages were run red first:
  collapsing any 404 into "not protected", turning the `enable` refusal into a
  silent success, treating an inherited ruleset as an ordinary skip, POSTing an
  exported ruleset verbatim, dropping the classic-present/object export check
  (which let the delete land), and dropping the `--allow-inherited` stderr
  warning. Each went red on the cases that name it.
- **`crew` 0.19.30: guardrails you can turn down per machine, a `/crew:gate`
  command, and schema 6.** Crew's command guard refused a fixed set of
  dangerous actions with no way to opt out. Schema 6 adds `guards` —
  `terraformApply`, `forcePush`, `adminMerge`, `mergeGate`, each `block` |
  `ask` | `allow` and all four defaulting to `block`, plus `prodDatabase` and
  `prodServer` as `none` | `read` | `full` defaulting to `none` — plus `github.mergeGate`
  as the twin of `bitbucket.mergeGate` minus `preset`, which is not copied
  because it binds to nothing (`CONFIG.md` §8).

  **`ask` is a marker, not a prompt, and it had to be.** A `PreToolUse` hook
  has no interactive stdin: exit 2 blocks, and the retry blocks again. An `ask`
  implemented as a question would have been `block` under a second name — a key
  with no reachable behaviour. So `ask` refuses, prints the *exact* command,
  and names `.crew/.approved-guard-<name>-<sha256(command)[:16]>`, the same
  shape and directory as `promote-gate.sh`'s `.approved-<env>-<sha>`. Keyed on
  the command, so approving one force push does not approve the next, and it
  **expires 15 minutes after it is created**: `.crew/` is gitignored and
  nothing prunes it, so an approval with no time bound is a standing
  per-command `allow` that outlives the session, the task and the person who
  gave it. `promote-gate.sh`'s marker needs no bound because its key is a
  commit sha; keying on the command text gives that up, so the bound is
  explicit.
  **Under `allow` nothing is silent**: every decision appends a row to
  `.crew/guard.log`, not only the permissive ones.

  **Two more keys, one more vocabulary.** `guards.prodDatabase` and
  `guards.prodServer` are `none` | `read` | `full` rather than
  `block` | `ask` | `allow`, and they answer a different question: how much of
  production may crew reach. `none` refuses every command aimed at a declared
  target; `read` permits only what crew can POSITIVELY classify as read-only —
  SELECT-only SQL, a named read-only program over `ssh`, an AWS `describe-`/
  `list-`/`get-` verb — and treats everything it cannot classify, an
  interactive `psql` session included, as a write; `full` permits everything
  and logs each one. `ask` is deliberately absent: a marker file per distinct
  SQL string is a prompt nobody reads by the tenth query.

  **The level is a machine fact; what is production is not.** The two levels
  ratchet across both layers like the rest. The glob lists they match against,
  `production.databases` and `production.hosts`, are **repo-only** — absent
  from the global template, pruned out of a global file and reported there —
  because `prod-db-*` names one cluster in one repo and something else in the
  next. **With no patterns declared the guard matches nothing**, which is how
  the strictest level ships as the default and changes nobody's behaviour at
  upgrade; the older unconfigurable `prod`-in-an-argument rule is untouched
  until a pattern is declared, and stands down only for commands a declared
  pattern already matched.

  **Two of these are NEW refusals, and no default turns a new refusal into an
  old one.** `guards.adminMerge` refuses `gh pr merge --admin`, which no crew
  guard refused before, and `guards.terraformApply` now covers `tofu` as well
  as `terraform` — OpenTofu is a drop-in fork, so naming one of the two refused
  nothing the moment a repo switched. Measured against 0.19.25 before the
  change: **both** flavours exited 0 for `gh pr merge --admin`, `tofu apply`
  and `tofu -chdir=infra destroy`, while the `terraform` and force-push
  controls exited 2. The migration report, the `/crew:upgrade` CLI,
  `upgrade.md`, `CONFIG.md` §16 and both READMEs say so rather than letting
  "the default is `block`, so nothing changed" cover it.

  **A repo may only narrow.** These four and `install.policy` resolve to the
  *lower* of the repo and machine-global layers rather than by precedence: crew
  reads config out of cloned repositories, and under precedence a repo shipping
  `guards.forcePush: allow` would grant itself force-push rights on the machine
  of whoever cloned it. That ratchet is now **one table** —
  `crew_guards.RATCHETED_KEYS`, with `effective_ratcheted` the only place that
  takes the minimum and `crew_config.resolve_ratcheted` the only place that
  reads both layers raw. `effective_install_policy` and
  `resolve_install_policy` survive as thin wrappers, so no call site had to be
  rewritten to prove the generalisation happened. `pm.authority` is
  deliberately *not* in that table: it ratchets for the widening warning only.

  **`/crew:gate <disable|enable|status> <github|bitbucket>`** owns the
  take-it-down-and-put-it-back workflow. It reads `guards.mergeGate` **first**,
  before resolving a provider or finding a script — a policy read after the
  provider is resolved is a policy read after a real `export` API call has
  already hit a live repository. A missing provider skill is a **stop**, never
  a warning, and the only restore is `enable --from-export <the file disable
  wrote>`. `/crew:promote`'s section now routes through it and covers both
  providers instead of Bitbucket alone.

  `crew_guards.py` is a real module split, not tidying: the `guards` block took
  `crew_state.py` to 3341 lines against `.pylintrc`'s 3300 ceiling, and that
  file's own comment says the third raise must be a split instead. The slice
  moved is the one that already had a seam — "may crew do this, and how much
  narrowing did the two layers agree on" — and `crew_state` re-exports every
  name, with `tests/test_module_split.py` extended to assert each resolves to
  the object `crew_guards` defines.

### Fixed

- **`crew` 0.19.28: five backlog items, and the one that mattered is the Stop
  gate.** The gate diffed the WORKING TREE against HEAD, so a committed change
  was invisible to it and **`git commit` was a complete bypass** -- the same
  file exited 2 while dirty and 0 once committed. A gate you can pass by running
  `git commit` is not a gate. The baseline is now the last commit the gate
  itself verified (`.crew/.verify-verified-at`, machine-local, written only on a
  pass), falling back to the merge-base with the default branch, falling back to
  HEAD. The alternative -- a turn-start marker written by another hook -- was
  rejected because an absent marker would degrade to the old behaviour, and a
  gate that silently verifies less when its input is missing is the failure this
  repo keeps paying for. One narrowing survives and is asserted rather than
  hidden: on the default branch with no marker there is no branch point, so a
  commit still ends that one turn, and the marker is written on every clean exit
  so the window is one turn wide. Both flavours changed; nine cases in
  `test_verify_gate_baseline.py`, sabotage-verified three ways.

- **`crew` 0.19.28: the test suite mistook a bash it found for a bash that
  works.** Under PowerShell `shutil.which("bash")` returns `C:\WINDOWS\system32\bash.EXE`
  -- WSL's -- which cannot open a Windows path and exits 127 for every script
  handed to it. `_HAS_BASH` was then True, so the `sh` flavour was parametrized
  IN and **52 tests failed** with `assert 127 == 2`; two agents independently
  reported that as pre-existing breakage on `main`. `crew_fixtures.resolve_bash()`
  now proves a candidate by running a probe script and checking a sentinel exit
  code, and returns None when none works so the flavour is skipped with a
  printed reason. The logic was copied in six modules and a seventh had no
  resolver at all -- that seventh is why the first pass still left 16 failures.
  Measured: 52 -> 0 under PowerShell, resolving to `C:\Program Files\Git\bin\bash.exe`,
  with `PATH` untouched so the `check-marketplace.py` hang is not reintroduced.

- **`crew` 0.19.28: the upgrade CLI announced schema 3's new keys and not
  schema 5's.** `installKeysAdded` reached `.crew/codemap/UPGRADE.md` and never
  the terminal, because there was a branch for `providerKeysAdded` and no
  matching one for it. A key governing whether crew may run install commands is
  exactly what the block's own comment means by "must not learn about later" --
  and it arrives as `manual`, which is the reassurance, and only reassures if it
  is said.

- **`crew` 0.19.28: the pulse recommended a graph refresh that its host repo's
  CLAUDE.md forbids.** Not fixed by swapping the string, which would be right
  here and wrong in every repo that does not track `GRAPH_REPORT.md`. The state
  now reports whether that report is TRACKED beside `graph.json` -- asked of
  git, since an untracked report is a local artefact -- and the pulse names
  `graphify update .` only then. Unknown keeps the older `--no-viz` form. The
  three prose call sites still say the fixed command and are recorded as the
  remaining half.

- **`crew` 0.19.28: a comment claiming "the 21 commands and 10 agents".** Both
  wrong (24 and 54). Replaced with the scope and an `ls`, rather than a fresh
  pair of numbers with the same decay rate and no reader.
- **`crew` 0.19.30: `/crew:config --explain` contradicted the run for every
  ratcheted key.** It printed the *merged* value, and ratcheted keys do not
  resolve by precedence — so a repo `install.policy: auto` over a
  machine-global `manual` printed `install.policy  repo  "auto"` while crew
  behaved as `manual`. Measured, not reasoned about, and wrong in the direction
  that reads as "you have it" for a key deciding what crew may run. It now
  prints the effective value and, beneath the table, names which layer is
  holding each key down and what each layer asked for.

- **`crew` 0.19.30: the schema-5 migration told the CLI nothing.** It added
  `install.policy`, wrote its paragraph into `.crew/codemap/UPGRADE.md` and
  printed nothing at the CLI — so a repo with no codemap directory (which is
  where that file is written) gained a key governing whether crew may run
  commands on the machine and learned about it nowhere. A filed defect, fixed
  rather than repeated for schema 6's list.

- **`crew` 0.19.30: three `consider-using-f-string` warnings from 0.19.25's
  `graphStale` fix.** Not this change's, and named rather than absorbed: they
  were pushed to `main` and make the pylint job red on `main` today,
  independently of anything here. Three lines, fixed in their own commit.

- **`crew` 0.19.25: `CONFIG.md` cites symbols instead of line numbers.** When
  the citations were last measured, **11 of 13 checkable line numbers were
  wrong** -- `read_global_config` cited at 585 and living at 666,
  `resolve_config` at 638 and living at 719, `collect` at 2727 and living at
  2888. Every wrong one still landed on real code in the wrong function, which
  is the shape that survives a citation check and does not survive reading: a
  reader who opens the line finds plausible code and has no signal that they are
  in the wrong place. 69 line-numbered citations are gone. 15 became
  `file::symbol`, verified to resolve against the module-level definitions of
  the file they name. 28 key-reference rows dropped the line number entirely --
  the row already names the config key, and that key was verified to appear in
  the cited script for all 23 scripts. 22 `.md` citations and 13 orphaned bare
  `:NNN` back-references were resolved the same way. The line number was never
  used to choose a symbol, because a stale line number is not evidence: where
  the prose named a symbol and the line disagreed, the prose won.

- **`obsidian-vault` 0.3.8: a second client's identity removed from the shipped
  examples and from `TODO.md`.** A different sub-company from the one the three
  entries above covered, scrubbed the same way and with the same replacement
  vocabulary, so no example loses what it taught. In `obsidian-vault`, a vault
  name embedding that client's brand appeared in the install command's
  per-machine vault table, in `vault_profiles.py`'s commentary on the profile
  set, and in both test modules -- the docstring fixture table, the
  measured-notes key, the zero-plugin classification tuple, and the
  not-installed diagnose fixture. The renamed vault still differs from the
  other zero-plugin vault it sits beside, so the detection cases that depend on
  telling two plugin-less vaults apart still do. Root `TODO.md` carried four
  references to the consumer repo one finding was filed from, two of them file
  paths inside that repo; they stay paths, so the finding still says where its
  evidence lives. `TODO.md` sits outside every entry and bumps nothing, and no
  other marketplace entry carried the marker.

  **Git history is again deliberately not rewritten**, for the reason the entry
  below gives.

- **`gizmoduck` 0.5.2, `obsidian-vault` 0.3.7, `claude-memories-vault` 1.1.1:
  the same customer's identifiers removed from the entries `crew` 0.19.24 could
  not reach.** That change scrubbed `plugin/crew/` and reported, without
  touching, the hits sitting in other marketplace entries -- each needs its own
  version bump, so each waited for one. Scrubbed here with the same replacement
  vocabulary, so every example still teaches what it taught: in `gizmoduck`, a
  ticket-key prefix in both bootstrap comments and across four test modules and
  a fixture, the customer's project name in the checkov scanner tests, and two
  of its public hostnames in test and spec prose; in `obsidian-vault`, a vault
  name embedding the customer's abbreviation and full brand, across two command
  docs, `vault_ops.py`, `vault_profiles.py` and both test modules; in
  `claude-memories-vault`, a session-note title in the frontmatter example. The
  two `docs/superpowers/` files carrying the same markers are not a marketplace
  entry and bump nothing.

  Hostnames became RFC 2606 reserved names rather than another plausible
  domain. `gizmoduck` is a vulnerability scanner and those strings appear as
  scan targets, so a replacement that resolves to a real third party would be
  worse than what was being fixed.

  The vault tests exist to prove a chosen vault name can differ from its
  directory basename, so both sides were renamed to names that still differ --
  collapsing them to one string would leave the suite green while proving
  nothing.

  **Git history is again deliberately not rewritten**, for the same reason:
  force-pushing a public marketplace breaks every clone and every commit-pinned
  install URL in the README.

- **`crew` 0.19.24: a customer's identifiers removed from the shipped examples.**
  Five files under `plugin/crew/` carried real values from a client engagement
  rather than invented ones: a live 12-digit AWS account number and two
  production resource names in the `crew-runbooks` worked runbook, a project
  name, an S3 bucket and a database name in the `crew-setup` Terraform
  `CLAUDE.md` example, a ticket key in the `crew-docs` CHANGELOG sample, and the
  same resource name again inside the explanatory comments in `guard.sh` and
  `guard.ps1`. All replaced with generic-but-plausible equivalents, so every
  example still teaches what it taught -- the runbook still shows an account
  precondition and a rule/alias/rule rollback, and the guard comments still
  explain why a hyphen-joined middle segment of `prod` must not fire the
  environment check.

  **Git history is deliberately not rewritten.** This scrubs the working tree
  and everything installed from it going forward; the values remain reachable in
  older commits by design, because force-pushing a public marketplace would
  break every clone and every commit-pinned install URL in the README. Treat the
  underlying account as one whose id is public and rely on its IAM posture, not
  on the id being secret.

  Verified by sweeping every tracked file for bare 12-digit numbers and for the
  customer's name fragments; the only remaining 12-digit runs are documented
  all-zero/all-one placeholders, log timestamps, an example task id, and a
  substring of a SHA-256 hash. Hits outside `plugin/crew/` are reported on the
  pull request rather than changed here, since each sits in a different
  marketplace entry and would need its own version bump.

- **`crew` 0.19.23: four gates that failed open, found by the Rule of Two.**
  The first real run of `rule-of-two` was against `plugin/crew/` itself. Both
  families returned VIABLE WITH CHANGES; these are the findings that let unsafe
  work through, each reproduced with a control before it was touched.

  **Three guard bypasses, and none was a sloppy regex.** All three fail open in
  **both** flavours, each in that shell's own syntax, so fixing one side would
  have left the other open -- the drift class CLAUDE.md already records.

  - `terraform -chdir=infra apply` ran unguarded. `GIT_PRE` exists two lines
    below precisely to swallow options between a command and its subcommand;
    the terraform rule beside it never got the same treatment. Now `TF_PRE`.
  - `git push 2>&1 --force origin main` ran unguarded, and this is the sharpest
    example this repo has produced of **re-reviewing the fix to a guard as hard
    as the guard**: `[^;&|]*` was a deliberate, correct narrowing, added
    because a greedy `.*` reached an unrelated `-f` three commands later and
    blocked ordinary pushes. `2>&1` contains an `&`, so the scan stopped before
    `--force` was ever reached. The fix opened the hole. `ARG` now crosses `&`
    only when it is part of a redirection, so `&&`, a trailing `&` and `|` stop
    the scan exactly as before -- asserted by a test that keeps the original
    false-block case passing.
  - `git reset HEAD --hard` ran unguarded: `--hard` had to follow `reset`
    immediately. `--soft HEAD~1` still does not match.
  - A compound command that captured something unrelated printed the secret.
    The "safe shape" test asked whether an assignment appeared **anywhere** in
    the command, not whether the secret read was the thing being assigned. An
    unrelated capture was accepted as evidence that the dangerous half had been
    captured.

  **The promote gate treated its own failure as permission to deploy.**
  `VERDICT` comes from a command substitution, so a raising python wrote a
  traceback to stderr and nothing to stdout, and `[ -n "$VERDICT" ]` read that
  as "no unmet preconditions". Measured: `last verified: 2026-99-99` exited
  **0**, created `.deploy-in-flight`, and printed **nothing** -- behaviour
  byte-identical to a valid, current rollback. The date is now reported as its
  own unmet precondition, and the check's exit status fails closed regardless.
  The `.ps1` twin had the same shape twice: `ParseExact` throwing on the same
  input, and `catch { exit 0 }` on a `verify.json` that will not parse -- which
  made corruption indistinguishable from a repo that opted out of gating.

  **`/crew:pm` did not load at all.** `commands/pm.md:3` carried an unquoted
  `argument-hint:` whose value is a bracketed, nested flow sequence; PyYAML
  refuses it at the `|`. The validator that should have caught it reported 293
  passes and 0 failures, because `frontmatter()` split each line on the first
  `:` instead of parsing YAML -- **a validator whose parse is weaker than the
  loader's cannot fail where the loader fails; it can only agree with itself.**
  It now uses `yaml.safe_load`, records a failure naming the YAML error, and
  exits 1 rather than degrading if PyYAML is absent; the Marketplace workflow
  installs it as its own step. Control run: restoring the old line turns the
  validator red and names the character.

  **`crew_upgrade.py` half-ran and then reported success.** A `derived` key
  that is not a plain subsystem name stored `{"skipped": ...}` alone, and
  `_report` reads `conflicts`, `added` and `touched` from every entry -- so
  `KeyError` fired *after* the schema had been stamped, no report was written,
  and a retry said "already current". The skip entry now has a result's shape,
  the four reads are defensive, and the skip is named in the report.

  **Documentation corrected where it was actively wrong.**
  `crew-verification/SKILL.md:147` said `.crew/verify.json` "is committed and
  shared". It is not -- `.gitignore` ignores `.crew/*`. `commands/review.md`
  carried the same sentence and was fixed in 0.19.21; this is its neighbour,
  found by a review rather than by the first fix, which is the argument for
  checking the neighbour every time. `commands/review.md:14` also gained the
  `mkdir -p .work/review` that `mktemp -d` needs, since `mktemp` creates the
  leaf and never the parents.

  **One test was green where nobody looks and red on the maintainer's machine.**
  `pm_brief.main` resolves `payload["cwd"] or $CLAUDE_PROJECT_DIR or getcwd()`,
  so a test pinning the fallback with `monkeypatch.chdir` pinned only the third
  rung. Cleared suite-wide in `conftest.py` beside the global-config fixture,
  which exists for exactly this reason; a test that wants the variable still
  sets it and still wins.

  Four sabotage entries, 121 mutations. `test_guard_bypasses.py` (10 cases,
  both flavours) and `test_promote_gate_fails_closed.py` (4) are new, and every
  bypass was run RED against the unfixed guard before the fix landed.

  **Not fixed, recorded instead:** the Stop gate cannot see a **committed**
  change, so committing ends a turn it would otherwise block. Reproduced and
  written into `verify-gate.sh:63` and TODO.md -- closing it means choosing a
  baseline for "this turn", which changes behaviour in every gated repo and is
  a design decision, not a bug fix.

- **`rule-of-two` 0.1.2: a recorded model id is now checked against the alias
  beside it.** `render_report` printed each side's model id verbatim -
  "requested as `X`" - with nothing checking that `X` belongs to the same
  family as the alias next to it, while `resolve_family` read only the alias.
  A mis-pasted `--model-id` in `commands/review.md` step 3 therefore named the
  wrong family's model on the page while coverage still computed
  `TWO_CROSS_FAMILY` and the banner still said "The Rule of Two held" - a
  wrong value wearing the label of a check that happened, which is this repo's
  recurring shape. It was disclosed in 0.1.1's pull request as a known gap and
  left unfixed there because it costs its own version bump; this is that bump.

  `verify_model_id` resolves **both** recorded names and returns the
  contradiction. A disagreement - or an id that resolves to no known family,
  because unknown must never read as corroboration - downgrades coverage to
  the new `TWO_FAMILY_UNVERIFIED`.

  **Downgraded, not refused.** Every other degraded input in this script is
  reported rather than aborted on (`cmd_assemble` says exactly that of an
  unreadable result file, `run_codex` of every failure) because the report is
  how anyone finds out. A refusal would throw away two real reviews over a
  typo and leave the operator who made it nothing on the page to correct it
  from. So the banner quotes which two names disagree and what each resolved
  to, the title withdraws the Rule of Two name, the "what is missing" section
  fires, and the offending id stays in its bullet **marked rather than
  dropped** - the person who has to fix it needs to see the value they pasted.

  The new outcome is asked **before** the `UNKNOWN` check. Both are
  unsatisfied, so `coverage_is_satisfied` does not care, but only the
  unverified banner prints the contradiction: an unresolvable alias sitting
  next to a mis-pasted id would otherwise be reported as a plain "could not
  tell" with nobody told that two recorded names actively disagree.
  `compute_coverage` takes the new flag with **no default**, because a check
  that never ran silently becoming "nothing wrong" is the exact failure this
  file exists to police.

  An **absent** id is an absence, not a disagreement. Nothing is claimed about
  a name that was never recorded, the "requested as" clause was already
  suppressed when it is empty, and `run_codex` records no id at all - so
  treating an absence as unverified would downgrade every real report and make
  the outcome meaningless. The check still runs symmetrically on both sides,
  since `hydrate_state` reads a state file someone else wrote and a guard
  installed on one side only is this repo's documented shape.

  The suite covers the mismatch, the unresolvable id, the corroborating pair
  (which must still say the rule held) and the absent id, and `--sabotage`
  gained an entry restoring the 0.1.1 behaviour exactly - the id's family
  still resolved, nothing comparing it. State the invariant and re-measure the
  numbers rather than trusting these: 296 checks and 8 sabotages at the time
  of writing, up from 267 and 7.

- **`rule-of-two` 0.1.1: five defects its first real run against another
  artifact exposed.** Four of them were invisible to the plugin's own
  self-reviews, because a self-review runs installed, in this repo, on a tree
  the reviewer already knows.

  **The two reviewers were not allowed to work the same way, and the report
  did not say so.** `run_codex` dispatches under `codex exec -s read-only`,
  which cannot write - not even the temporary directory a test suite needs -
  so Codex could not do `templates/rubric.md` step 3 ("run what is runnable")
  while the Claude reviewer, holding a Bash tool, could. Every difference
  between the two reports was therefore ambiguous between procedure and
  judgement, which is precisely the confound that rubric warns about, and
  nothing on the page said which. **Reported rather than equalised**: the
  sandbox stays `read-only` and `render_method_note` prints the asymmetry
  directly under the coverage banner whenever Codex ran. `workspace-write`
  against a throwaway copy was considered and rejected - the live checkout must
  never be writable to a reviewer, so it needs a copy, and even with one the
  two methods stay unequal because the Claude side is not sandboxed the same
  way. The note is phrased as capability, not observation: whether the Claude
  reviewer actually ran anything is recorded nowhere, and it must not imply it
  was. Step 3 of the rubric now tells a reviewer that cannot execute to say so
  under "What I could not check", so the doc no longer orders both to do what
  one cannot.

  **The 900-second default could never fire.** A single Bash call from Claude
  Code is killed at 600s, so a foreground review died as a *tool* failure and
  `run_codex` never reached its own `TimeoutExpired` branch - the "codex did
  not run" outcome this plugin is built around, lost to a number. Now 480,
  with `CALLER_TIMEOUT_CEILING_SECONDS` stating the ceiling it is chosen
  against so the suite asserts the relationship rather than a remembered
  figure. `cmd_codex` carried a second copy of 900 as a literal default, so
  lowering the table alone would have fixed the configured path and left the
  defaulted one - right about its own case, one rung short of its neighbour.
  Detached launch is deliberately *not* offered as an alternative.

  **`commands/review.md` read `codex_available`, a key `cmd_config` stopped
  emitting.** `config.md` was updated at the rename and its neighbour was not,
  and the suite already asserted `"codex_available" not in payload` while
  nothing checked the file telling an operator to read it. The new check
  **derives** the emitted key set by running `config` and reading the keys
  back, then fails on any snake_case token in a command file that is neither
  emitted nor in a short, reasoned allowlist - so the next rename goes red
  without anyone remembering to add it.

  **The commands could not run from a checkout.** `${CLAUDE_PLUGIN_ROOT}` is
  set only when the plugin is installed, and an unset variable expands to
  nothing, so every invocation became `/scripts/rule_of_two.py` - not an error
  anyone could act on, just a path nobody wrote. Both command files now default
  it and walk up from `$PWD` for the plugin directory, failing loudly if
  neither resolves. The agent-dispatch half genuinely cannot work this way:
  `rule-of-two:reviewer-claude` is a plugin-registered subagent type, so from a
  clone the Claude dispatch fails and is recorded with `--failed`. The README
  says that plainly rather than leaving someone to discover it.

  **Report headings collided.** A review arrives in the rubric's section order,
  so it carries its own `## Defects` - pasted raw under `## Reviewer A
  (Claude)`, that sat at the same level as the section containing it, twice,
  making Reviewer B's findings read as a sibling of Reviewer A's.
  `_demote_headings` pushes a body's headings down two levels, clamps at H6,
  and leaves fenced blocks alone so a `# comment` in a code block is not
  rewritten. In code rather than in the rubric, because rubric item 16 calls
  prose telling a model to compute what a function could compute a defect.

  **One item of the brief did not survive checking.** It asked for
  `PYTHONIOENCODING=utf-8` to be documented as required on Windows "per the
  README". No file in this repository has ever mentioned that variable, and it
  is not required: `_make_stdout_safe` reconfigures stdout and stderr to UTF-8
  on startup. Measured rather than argued - with `PYTHONIOENCODING=cp1252`
  forced, `assemble` on an em-dash-and-curly-quote review exits 0 and the suite
  passes. Documenting a requirement the code does not have would have been a
  claim outrunning its evidence, in a plugin whose rubric hunts exactly that,
  so `review.md`, `config.md` and the README instead say plainly that no
  variable is needed and cite the function that makes it true.

  Two sabotages were added for the two new guards (bodies pasted in raw; the
  method note removed) and both were seen to go red. Read `SABOTAGES` and the
  suite's own tail for the counts rather than a number written here.

### Added

- **`crew` 0.19.22: two unknowns that reported themselves as clean.** One bug
  in two places, both the shape this repo keeps hitting -- something that could
  not be checked reported as something that was checked and found nothing.

  `read_diagrams` matched a kind with `stem == kind or stem.startswith(kind +
  "-")`, so `process-bitbucket-svg.mmd` satisfied the obligation for `process`.
  A repo holding only the narrow diagram reported `missing: []` and looked
  fully documented while having no process overview at all -- and the repo with
  only the specific one is exactly the repo that needed telling. Now exact
  stem only. `data-flow` is the case a prefix rule handled worst, being
  hyphenated itself, so `data-flow-crew-config` satisfied it; there is a test
  for precisely that. **No change to this repo**, which has all three exact
  stems, and a test records that rather than leaving it as a claim in a PR.

  `/crew:review` step 0b read `.crew/verify.json` and, finding nothing,
  selected no specialists and moved on. `.gitignore:282` ignores `.crew/*`, so
  that file is machine-local and **absent on every fresh clone until
  `/crew:init` writes it** -- meaning "I could not look" and "I looked and
  found nothing" produced identical output on every new checkout. Step 0b now
  has three named outcomes and must say which one happened; the fall-through
  that collapsed them ("If no matched rule names an agent, skip to step 1") is
  gone, because a paragraph added above a live fall-through fixes nothing.

  Two corrections in the same file, both found while fixing the above. The GAP
  paragraph justified itself with "`.crew/verify.json` is committed and travels
  between machines" -- it is not committed and never has been here. The
  conclusion was right and the reason was backwards, which is worse than a
  wrong conclusion: it sends the reader hunting a tracked file that does not
  exist. And "not only crew's eleven" was written at `579a7cd9`, when
  `plugin/crew/agents/` held exactly 11 files; it holds 54. The number is
  removed rather than corrected, the shape `plugin/PLUGINS.md` already uses,
  because a roster count nothing checks re-stales on the next agent added.

  Both fixes are sabotage-tested, and both controls were run by hand: reverting
  `read_diagrams` turns two tests red naming the kind that vanished, and
  restoring the three `review.md` defects turns three red. 11 new tests in
  `plugin/crew/tests/test_verify_absent_and_diagram_kind.py`.

  One committed assertion **encoded the bug** and had to be inverted:
  `plugin/crew/hooks/scripts/_test/run-tests.sh:976` read "Prefix matching:
  data-flow-orders.mmd satisfies the data-flow KIND" and asserted
  `missing == []`. It now asserts `["data-flow", "process"]`. That suite is run
  by CI's Marketplace job and is not part of the pytest set, which is how it
  reached CI red after a green local pytest run -- the `check` job runs seven
  steps and `check-marketplace.py` is only the first.

  Shipped as 0.19.22, not 0.19.21: the assertion fix was a second commit
  touching `plugin/crew/`, and `check-marketplace.py`'s version rule is
  **history-based** -- it compares the last commit that set the version against
  the last commit that touched the plugin. Running the checker on a dirty
  working tree cannot see that, which is exactly why the bump belongs in the
  final commit.

- **`rule-of-two` 0.1.0: two adversarial reviewers from different model
  families, and a report that says so when only one of them ran.** A Claude
  subagent on Fable and a Codex agent on `gpt-6-astra` tear apart the same
  Claude Code agent, skill or plugin against one shared rubric
  (`templates/rubric.md`), neither seeing the other's findings, and return a
  viability verdict with cited defects and the edits worth making. Scope is
  artifacts only - not architecture, plans, product ideas or code diffs.

  The load-bearing property is that **coverage is a reported outcome**. If
  Codex is missing, unauthenticated, times out or its model is retired, the
  report's own title says this is one review and not two; if the two model
  names cannot be resolved to families, it says "could not tell" rather than
  claiming independence. Title and banner are both derived in code from a
  five-value coverage enum in which `UNKNOWN` is a real value, and the word
  "independent" appears in the report only when two reviewers ran and resolved
  to different families. That is the repo's recurring bug - an unknown
  collapsing into the safe-looking value - and it is asserted against the
  *rendered report*, not the function that computes it.

  `scripts/_test/test_rule_of_two.py` carries 228 checks with the subprocess
  layer stubbed, so no real `codex` is launched; `--sabotage` breaks one guard
  at a time (the banner, the title, the evidence gate, family-alias matching,
  the verdict line) and asserts the suite goes red, then restores it.

  Model spellings were verified rather than asserted, with a control in each
  case: `claude-fable-5-1` exits 0 where an invented name exits 1 with
  `[claude-code:unrecognized_model]`, and `codex exec -m gpt-6-astra` replies
  where an invented name exits 1 with "model is not supported". Both controls
  are quoted in the plugin's README.

  No hooks, and no dependency on `crew` - it carries its own two-model config
  and never reads crew's, though it will offer findings to crew as tickets if
  a `.crew/` directory happens to be there.

- **`crew` 0.19.14: the pm can now route the trigger 0.19.13 added, and
  `UPGRADE.md` stops carrying a line nothing can read.** Two gaps left by that
  release, both of the same shape -- a value that exists in the code and does
  not reach the person who has to act on it.

  `knowledgeUnverifiable` had no row in `plugin/crew/agents/pm.md`'s dispatch
  table. The trigger fired, the brief printed the finding, and the pm's own
  routing table listed ten of the eleven other triggers and not that one. It
  now has a row that says what makes it different from `knowledgeBehind`: there
  is no diff to re-read, so the claims have to be derived from source again,
  which is also why it sorts above.

  `crew_upgrade.py` wrote `graph anchor: <sha>` into `.crew/codemap/UPGRADE.md`.
  `_NOT_SUBSYSTEMS` excludes that file from `read_knowledge` and `_ANCHOR_RE`
  requires `anchor:` at line start, so the line was read by **nothing** -- it
  could be reported as neither behind nor unresolvable, while looking
  machine-checked to a human. Anchor-shaped, unreadable and eventually dead is
  worse than either honest state, and it is the category 0.19.13 did not cover:
  that release made `unresolvable` a reported value of its own, but a line no
  regex matches never reaches the reporting path at all. The writer now emits
  `graph build compared against: <sha>` followed by three lines saying plainly
  that it is not an anchor, that nothing re-verifies this file, and that the
  sha may stop resolving. `test_report_header_is_not_anchor_shaped` asserts
  against **both** anchor regexes rather than against the literal text, so any
  accepted anchor spelling reintroduced later goes red; sabotage-tested by
  restoring the old line, which fails with the offending line quoted.

  The committed `.crew/codemap/UPGRADE.md` was updated to the header the fixed
  writer emits, with the four lines lifted out of the writer's own source
  rather than retyped, so the data file cannot drift from the code that
  generates it.

- **`crew` 0.16.33: a lingering handoff note is now archived, not just warned
  about.** `pm_brief`'s `handoffPending` finding, and `handoff-read`'s printed
  path, both only ever asked whether `.work/HANDOFF.md` existed -- true the
  same way for a note written five minutes ago and one still describing a
  gate that closed hours ago, after two more commits landed on top of it.
  That happened for real: a handoff said "at the spec-review gate" long after
  the gate closed, and the next session started acting on a next action that
  was already done.

  `crew_state.handoff_staleness` now judges the note on two signals before
  `handoff-read` (and, under `context.autoResume`, `pm_brief` itself) prints
  or injects it: **age**, from the note's own `written:` line (falling back
  to file mtime when that line is missing, the weaker of the two since an
  edited file's mtime moves without the header changing to match), and
  **reality drift**, comparing the note's `head:`/`branch:` lines against the
  checkout right now. A `head:` this repository cannot find, or cannot reach
  from `HEAD`, cannot be verified at all -- the same "unknown resolves to
  stale" rule the codemap and diagram anchors already use for missing
  provenance. A verifiable `head:` that is `staleHandoff.maxCommitsBehind` or
  more commits behind reports exactly how far the note has fallen behind
  (default 3); a `branch:` that no longer matches the checkout is flagged on
  its own, since a merge can leave the noted head a true ancestor of `HEAD`
  while the session has moved off the branch entirely. `staleHandoff.
  maxAgeHours` defaults to 72 -- generous on purpose, since archiving a note
  someone is still using is worse than leaving a stale one for one more day.

  A note either signal flags is **archived, never deleted** -- moved to
  `.crew/handoffs/HANDOFF-<timestamp>.md`, timestamped and never overwritten
  (`crew_state.archive_stale_handoff`). This is the one automatic action
  crew's own "ask before removing a role or deleting anything" rule still
  allows: moving a file sideways into a dated archive is not deleting it, and
  a stale note left visibly in that archive is recoverable in a way a deleted
  one never is. A note judged fresh -- or one crew cannot judge at all,
  because it carries none of the template's header lines -- is left exactly
  where it was; `read_work`'s plain existence check and the `handoffPending`
  finding it feeds are untouched.

  Both `handoff-read.sh` and its `.ps1` twin call the same check (through
  `crew_state.py --archive-stale-handoff`), and `pm_brief._resume_context`
  calls it directly for the `autoResume` path, which has no human read step
  to catch a stale note the printed path still leaves in place. Every call
  fails open: a check that cannot run (no python, no git, a locked file)
  falls through to the exact behaviour crew had before this feature existed,
  because a hook that breaks startup over a staleness check is worse than one
  honestly-stale note.

- **`exchange-mailbox-cleanup` 1.0.0 and `exchange-mailbox-restore` 1.0.0: two
  Exchange Online runbooks turned into operator walkthroughs.** Built from
  `Mailbox-Cleanup-Training-Runbook` (41 steps, Phases A-E) and
  `Mailbox-Restore-And-Hold-Removal-Runbook` (triage plus five mutually
  exclusive paths) in the `infrastructure-scripts` repo. The audience is a
  non-technical operator, so the skills ask one question at a time and validate
  before advancing.

  **The skills print commands; the operator runs them.** `Connect-ExchangeOnline`
  and `Connect-IPPSSession` are interactive and a tool call cannot answer a
  modern-auth prompt, so the skill prints an exact command, the operator pastes
  it into their own window, and the skill reads back the CSV or log it wrote.
  The credential never reaches the agent.

  Targeted at **Windows PowerShell 5.1**, gated by `#Requires -PSEdition Desktop`
  and written in the subset that also runs on 7.6+. Two experts argued opposite
  sides and both concluded 5.1; the deciding fact came from the one arguing
  against it -- `ExchangeOnlineManagement` 3.10.1 raised its PowerShell 7 floor
  to 7.6 ("Windows PowerShell 5.1 is not affected"), and this repo's own CI runs
  7.4, already below it. 5.1 imposes no such floor and is in-box on both machines
  the operator touches, so there is one icon to recognise.

  Six real defects in the source runbooks are worked around and documented. The
  worst is silent rather than destructive: the preservation baseline ran at
  Step 4 but the eDiscovery grant that makes it work was Step 14, so the first
  compliance search returned zero and read as "nothing to preserve" -- on a
  mailbox about to be deleted. The grant now runs first. Separately, all three
  driver scripts call `Disconnect-ExchangeOnline` in a `finally` block, tearing
  down the operator's session mid-runbook, so a reconnect is printed after every
  script step.

  Every irreversible step needs a typed phrase naming the count -- `DELETE 3`,
  `RECOVER 1`, `DESTROY 1`. A bare `yes` never proceeds. Licence removal is
  refused outright rather than gated, because removing it disconnects the mailbox
  permanently after 30 days regardless of hold state.

  Logs are read through `read_log.py`, which decodes defensively: UTF-16 BOM
  first, then strict `utf-8-sig`, then BOM-less UTF-16 by NUL position, and
  `cp1252` last because it never raises. The scripts write `.csv` with
  `-Encoding UTF8` but `.log` with bare `Add-Content`, which lands in cp1252 --
  and a reader that assumes UTF-8 turns every accented name into mojibake with
  no error.

- **`doc-builder` 1.1.0 and `solomon-doc-builder` 1.1.0: `report-builder` and
  `solomon-sop-maker` merged into one implementation with a swappable brand
  pack.** Both original pipelines survive because neither can do the other's
  job: findings and tabular content go HTML-to-Word, step-by-step procedures
  with screenshots go python-docx OOXML, which is the only path that writes
  `a:ln` and `wp:effectExtent` -- without them Word strokes a picture border
  outside `wp:extent` and clips it. A routing rule at the top of `SKILL.md`
  picks before writing starts.

  **A brand pack that is installed is applied.** `resolve_brand.py` scans
  sibling skill directories at runtime, so installing `solomon-doc-builder`
  makes Solomon the default for every document rather than something to
  remember to ask for. That also takes it out of the trigger space entirely --
  it is a data directory, not a rival skill. `--brand` always overrides, two
  packs with no `--brand` refuses and names them, none falls back to neutral.

  `preflight.py` detects, installs and verifies dependencies. Installs go
  `pip install --user` or into a skill-owned venv, never system-wide, because a
  managed workstation rarely has local administrator rights. Probes run in a
  fresh interpreter -- CPython caches a failed import for the life of a process,
  so probe-install-reprobe in one process reports "still missing" even when the
  wheel landed. Word's presence is read from the registry without starting Word,
  and a locked target is detected and named before Word is ever launched.

  **1.1.0 fixes the packaging gap, without touching `resolve_brand.py`.**
  `.claude-plugin/marketplace.json` has no field for "installing this also
  installs that" -- each skill is its own entry, and `claude plugin install`
  takes exactly one plugin name -- so `doc-builder` alone never brought
  `solomon-doc-builder` with it. The one mechanism this marketplace has for a
  single install bringing more than one thing is the `plugin/` bundle
  (`crew`, `gizmoduck`, `localgpu`, `obsidian-vault`), and it was rejected here
  on purpose: that bucket defaults **off** in the bootstrap scripts because a
  plugin can register hooks, and moving a hookless skill and its pure-data
  brand pack into it would flip them from on-by-default to off-by-default --
  a regression neither skill needs. A scratch-built plugin-cache fixture
  (`skills/doc-builder/scripts/_test/test_resolve_brand.py`, new) proved
  instead that `resolve_brand.py`'s existing "plugin cache" search step
  already climbs from `doc-builder`'s own installed location to the
  marketplace folder and finds `solomon-doc-builder` there with zero code
  changes, whether the two are checkout siblings or two separately installed
  plugins sharing one marketplace's cache directory. So the fix is entirely
  documentation: `SKILL.md` for both skills, both marketplace descriptions,
  `skills/README.md`, the root `README.md` mirror, and `MARKETPLACE.md` all
  now say plainly that Solomon styling needs `solomon-doc-builder` installed
  alongside `doc-builder` (one extra command, not a second architecture), and
  that `--brand neutral` / `DOC_BUILDER_BRAND=neutral` is the opt-out --
  previously documented only in `resolve_brand.py`'s own module docstring.

- **Four crew agents: `powershell-5.1-expert`, `powershell-7-expert`,
  `exchange-online-specialist`, `skill-author`.** The two PowerShell files are
  written to argue honestly rather than loyally -- each names the strongest
  argument against its own position and states that conceding is a successful
  outcome. Two advocates who both spin produce a debate with no answer.

### Changed

- **`mermaid-svg-bitbucket` 1.2.2: `--check` now exits 1 on `UNVERIFIED`, not
  0.** 1.2.0 taught `--check` to open the SVG instead of trusting
  `svg.exists()`. A manifest predating `version: 2` has no `svgHash` to compare,
  so it got a structural check instead -- non-empty, an `<svg` element, a
  closing tag -- and reported `UNVERIFIED` while exiting 0. The caveat was in
  the output; the exit code, which is the only part CI reads, still said pass.

  That is the same defect 1.2.0 was written to fix, one layer down: a green line
  meaning less than its reader assumes. Structurally-intact with no recorded
  hash is the strongest claim the tool can honestly make, and that is an
  argument for saying so loudly rather than for passing. It now exits 1.

  The red is one-time and the failure names the command that ends it: one
  `render_mermaid.py --force`, then commit the re-rendered SVGs and the
  rewritten manifest. `--force` is load-bearing in that sentence -- the source
  hash already matches, so `current` is true at
  `skills/mermaid-svg-bitbucket/scripts/render_mermaid.py:390` and a plain run
  skips the file at `:413` without ever reaching the line that records
  a hash. A message naming a fix that does not fix it would have been the
  cheaper mistake to make and the more expensive one to find.

  `UNVERIFIED` and `DAMAGED` share the exit code and stay separate findings in
  the text, because they are not the same news: `DAMAGED` says the SVG is
  provably not what was rendered, `UNVERIFIED` says nothing about the SVG at
  all. The report also prints stale, damaged and unverified in **one** pass
  before a single exit -- the old shape returned on stale-or-damaged before the
  unverified section ran, so the count of what could not be checked disappeared
  from the output whenever anything else was also wrong. Now that unverified is
  itself a failure, that shape would have dropped a whole category of finding,
  and `test_damaged_and_unverified_are_both_reported` holds it open.

  Changing the summary's wording quietly disarmed an existing assertion.
  `test_damaged_svg_is_reported_and_fails` ended on
  `assert "up to date" not in out.split("DAMAGED")[0]`, and the failure summary
  no longer contains that phrase for any input -- so the line passed whether or
  not the bug it guarded for existed. It now asserts the counts the summary
  actually prints. Keyed on the new wording it reddens on sabotage; keyed on the
  old, it could not.

  Sabotage-tested twice: reverting the unverified branch to `return 0` reddens
  both new tests (2 failed, 12 passed), and dropping `damaged` from the verified
  count reddens five (5 failed, 9 passed). Each test asserts the exit code and
  the message text separately, so a right-code/useless-text regression still
  fails. Suite: 14 passed, 0 failed.

  There is no `mermaid-svg-bitbucket` 1.2.1, and the gap is the rule working.
  This shipped as 1.2.1 first; the re-keyed assertion landed as a follow-up
  commit, and `check-marketplace.py` failed it -- `skills/mermaid-svg-bitbucket/`
  had changed *after* the commit that set the version, which is exactly the
  "already-installed copies stay stale" case the checker exists for. Rewriting
  history to fold the two together is blocked here by the force-push guard, so a
  late fix costs a version. That is the intended price, not a workaround.

- **`report-builder` 2.0.0 and `solomon-sop-maker` 2.0.0 are now redirect
  stubs.** Both descriptions open with "Do NOT use this skill - use
  `doc-builder` instead", so nothing referencing the old names breaks and
  neither wins a trigger. `solomon-sop-maker` was never registered in
  `marketplace.json` at all; it is now, as a deprecated stub.

  `solomon-sop-maker` arrived carrying a **nested `.git/`** -- a real repository
  with two commits and no remote, so its history existed in exactly one place
  and would have vendored as an empty gitlink. It was bundled to
  `docs/archive/solomon-sop-maker-history.bundle`, the bundle was proved to
  restore both commits with authorship intact, and only then was the nested
  repository removed.

### Fixed

- **`crew` 0.19.20: the agent count was wrong in eleven places and right in
  none, and the cause was a table nobody had counted.** Every current-state
  claim about how many agents `crew` registers disagreed with the plugin and
  with the others -- `11`, `14`, `29` and `50` all shipped simultaneously. The
  measured figure is **54**, established two ways that agree:
  `ls plugin/crew/agents/*.md` returns 54 files, each carrying a `name:`
  frontmatter key with no README or template among them, and
  `crew_state.ROLE_TIERS` (13) + `crew_state.SPECIALIST_ROLES` (40) + `pm` is
  the same 54, with both set differences against the filenames empty.

  The `29` traces to `plugin/PLUGINS.md`'s agent table, which has exactly 29
  data rows -- 13 tiered, 15 specialists, and `pm` -- because it was written
  when there were 15 specialists and never grew with `SPECIALIST_ROLES`.
  `marketplace.json`'s description is that table transcribed, parenthetical and
  all. **So correcting only the `29` there would have shipped a sentence
  asserting `13 + 15 + 1 = 54`**: the `15` had to move to `40` in the same
  edit, and a fix that changed the headline number alone would have looked
  right while reading as arithmetic nonsense. That is the reason this entry
  names the cause rather than the number.

  Eleven sites, not the seven `TODO.md` recorded -- a sweep for the same claim
  found four the recorded list had missed, which is that entry's own lesson
  ("a finding that records which places are RIGHT acquires an expiry date")
  arriving on schedule. Where the prose allowed it the figure is **gone**
  rather than corrected: `plugin/PLUGINS.md` and `plugin/crew/README.md` now
  say every command and every agent is an instruction to a model, and
  `PLUGINS.md`'s agent heading names `agents/*.md` instead of a count, with a
  new line marking the table beneath it abridged so the next reader who counts
  its rows is not misled the same way. `plugin/crew/README.md:1982` gained the
  `ls` re-measure and an explicit warning not to count the rows above it --
  that table lists `skill-author` twice, so a row count gives 41 specialists
  where the code has 40. `tests/test_role_ladder.py` compares sets in both
  directions, so the duplicate passes it.

  `scripts/install-prerequisites.{sh,ps1}` changed identically and
  width-neutrally (`11`->`54`, `21`->`24`, two digits for two), so no picker
  line changed length and `pick_fit` / `Format-PickerLine` are untouched. No
  check catches this class: `check_docs` never opens `plugin/PLUGINS.md`, and
  `check_menu_parity` compares the two scripts' menu *keys*, not their
  descriptive text -- which is precisely how they stayed a matched pair while
  both were wrong.

  Also in this release: `plugin/crew/CONFIG.md`'s "Why there is no
  `docs.reportBuilder`" section argued the abstract case -- routing is derived,
  a third authority, a key with no consumer -- but never stated the concrete
  fact that settles it. There is exactly **one** builder to choose between.
  `skills/report-builder/` is a deprecated stub whose frontmatter reads "Do NOT
  use this skill" and which ships no scripts; `skills/solomon-doc-builder/` is
  a brand pack, a `SKILL.md` over `assets/` and likewise no scripts; every
  builder script lives in `skills/doc-builder/scripts/`. So "a different report
  builder" is, in every case anyone has wanted, a different *brand pack* --
  and `docs.reportTheme` already selects one by name.

- **`jira-manager` 1.0.1 and `power-automate-api` 1.0.1: fifteen defects, across
  three review rounds.** Implemented by Codex (gpt-6-astra), reviewed three
  times by Claude Sonnet 5. The dispatch was RECORDED before the run, so the
  independence guard read `author family: gpt (recorded at dispatch)` rather
  than inferring it from config -- the reviewer was provably a different family
  from the author, which is the first time in this release that claim rested on
  a fact instead of a guess.

  The eight ticketed defects came from the Codex review of #81 and were
  deliberately left in `TODO.md` at the time. In `pa.py`: a custom
  `--client-id` was not cached, so refresh silently fell back to the default;
  snapshot filenames used second resolution, so two patches of one flow inside
  a second overwrote each other's ROLLBACK state; DNS, connection, timeout and
  decode errors escaped as tracebacks; and the printed rollback command omitted
  `--org` and `--flow`. In `jira-api.sh`: the no-auth cloud-id helper was
  unusable because sourcing demanded credentials first; sourcing permanently
  enabled `nounset` and `pipefail` in the CALLER's shell; mutation helpers
  returned success and printed completion text on 4xx/5xx; and account-search
  values were not URL-encoded.

  **Round 2 found two BLOCKs.** `curl --fail` made "return non-zero on 4xx/5xx"
  literally true by DISCARDING the response body -- every error across all
  twenty helpers became `curl: (22) ... error: 400`, and Jira's
  `errorMessages` payload is the only thing separating "field not on screen"
  from "invalid transition id" from "token missing read:jira-work", which
  `SKILL.md`'s own recovery steps depend on reading. It regressed the READ
  helpers too, which nothing asked to change. Now `--fail-with-body`, which
  keeps both the status and the body; `SKILL.md` states the resulting
  `curl >= 7.76` floor and names the distros that ship older.

  The second BLOCK was neither skill's version being bumped, so
  `claude plugin update` would have reported "already at the latest version"
  and left every installed copy on the broken scripts forever. Caused by this
  session's own brief to Codex, which said "do not bump any version".

  **Round 3 found a regression introduced by round 2's own fix.** `_arg`
  replaced `shlex.quote` with double-quoting applied only when it saw
  whitespace -- and a Windows snapshot path has neither whitespace nor a quote,
  so it came back BARE and bash ate every backslash: `C:\Users\...\f.json`
  arrived as `C:Usersd3ade...json`. That is the failure ticket 4 was filed for,
  re-introduced by ticket 4's fix. It was also wrong in all three shells it
  targeted. Reverted to `shlex.quote`, with a separate labelled
  cmd.exe/PowerShell line that is SUPPRESSED rather than mis-quoted when a
  value contains a character plain double quotes cannot carry.

  `SNAPSHOT_DIR` was wrong twice before it was right. CWD-relative wrote
  verbatim live-tenant dumps to a path no ignore rule covered -- how a real
  snapshot reached this public repo earlier in this release. Anchoring it to
  `__file__` fixed that and introduced worse: writing inside the installed
  plugin, where `claude plugin update` can delete the only copy of a rollback.
  It is now `~/.pa-api-cache/snapshots`, the shape `CACHE_DIR` already had.

  And round 3 caught the landmine this repo documents in another costume:
  `snapshot()` caught the write error and died cleanly, but
  `NamedTemporaryFile(delete=False)` had ALREADY created the file, so a failed
  write left a ZERO-BYTE snapshot carrying a valid-looking name -- which, since
  these sort by timestamp, became the NEWEST rollback for that flow. The
  partial file is now removed before `die()`.

  One NIT filed as cosmetic turned out to be a destructive path traversal.
  curl applies RFC 3986 dot-segment removal, so `PROJ-1/../PROJ-2` RETARGETS
  the request -- and `jira_delete_issue` was one of seven unencoded
  interpolations. All ten path segments now go through a shared `_jira_uri`
  helper. Verified: `PROJ-1%2F..%2FPROJ-2`, with `PROJ-123` untouched.

  Everything above was verified by RUNNING it rather than reading it: the
  quoted path round-tripping through `bash -c` byte-identically, `pipefail`
  giving exit 28 where it gave exit 0, `--fail-with-body` returning the JSON
  body alongside exit 22, the zero-byte leak leaving an empty directory, and
  jq-absent producing rc=127 naming jq instead of rc=0 and a bogus request.


### Added

- **`report-builder` skill.** Human-facing reports authored as HTML and
  converted to `.docx` / `.pdf` by Word. Built from an existing hard-won spec
  rather than invented: **the browser is not the target, Word's HTML parser
  is**, and it drops correct CSS *silently and completely* -- no error, no
  console message, just a flat document that reads as though nobody styled it.

  Five traps, each measured against the Word object model rather than assumed.
  Two are worse than unstyled because they produce invisible text: `var()` does
  not degrade, it drops the whole declaration, so
  `background:var(--x); color:#fff` renders white on white; and two class names
  on one element (`class="chip chip-fail"`) applies **neither** rule. Also
  `:nth-child` and the structural pseudo-classes, `::before`/`::after`, and
  flex/grid -- including `display:block` on a `<span>`.

  The skill defaults to a **concise** report: one-paragraph lede carrying the
  headline, at most five summary cards, one findings table. When the depth
  genuinely matters it writes a second `-Detail-` document rather than
  inflating the first. Length is not thoroughness; it is the main reason a
  report goes unread.

  `scripts/_test/checklist.sh` runs the skill's own pre-ship checklist against
  an artifact the builder actually emitted -- 15 assertions. That exists
  because the builder **failed its own checklist on the first run**: its
  emitted stylesheet carried a CSS comment reading ":nth-child does nothing
  here", which is inert to Word and indistinguishable from the real defect to
  the grep the skill tells readers to run. A check that cannot tell a violation
  from a mention of the violation is not a check.

  `reports/` and `docs/` are deliberately different places. `docs/` holds
  documentation that describes the system and lives in git; `reports/` holds
  dated generated output about a point in time, is gitignored, and reads as an
  attack plan if it leaks.

### Changed

- **crew 0.16.30: the repo CLAUDE.md template gains a `## Documentation`
  section**, so it reaches every repo `/crew:init` sets up and `/crew:upgrade`
  refreshes. Documentation a human reads ships as HTML, PDF or DOCX; Markdown
  stays correct for the repo itself (README, CLAUDE.md, CHANGELOG, ADRs, code
  maps) and for working notes. The rule is not "never Markdown" -- it is "do
  not hand a human a `.md` file and call it the documentation". All of it lives
  under a folder named `docs`, at the repository root or at the root of the
  project folder it belongs to.

  Wired through `claude-md-audit.sh`'s `canon()` and `label()` as well as the
  template, because a heading the audit does not recognise is reported as an
  EXTRA -- the audit would have recommended against the very section the
  template ships.

  While doing it: `round-trip.sh` hardcoded `-ne 7` for the concern count and
  failed with "the extraction or list is broken" when the LIST was what moved.
  The count now derives from `CONCERNS`. A count that must be edited in two
  places to add one concern is a tripwire on the maintainer, not on the
  contract.


### Fixed

- **crew 0.16.29: the verify gate told a matcher that could not RUN apart from
  a `verify.json` that could not be PARSED.** Two bugs in one path, authored in
  an earlier session and landed here with the regression suite CLAUDE.md
  requires of a blocking guard.

  The changed-file list went to the embedded matcher on **argv**, and `E2BIG`
  counts argv PLUS the environment — so a hook invoked with a large environment
  failed to exec even when the list itself was small. Measured 2026-09-07: 74
  files, 2.6KB of paths, a 7.9KB environment, `Argument list too long`. The
  list now goes through a temp file.

  The second bug is the one that cost the time. Any non-zero status from the
  matcher was reported as `.crew/verify.json could not be parsed`, so an exec
  failure sent the reader off to debug a healthy config. Exit 3 — raised only
  by the explicit `json.load` guard — now means the file is bad; every other
  non-zero status says the matcher could not run and says so in as many words.
  **Both still fail CLOSED.** The severity was never the bug; the diagnosis
  was. This is the same shape as `render.sh`, `1d61342c` and the null-shadow
  fix earlier in this release: a wrong answer that is indistinguishable from a
  right one until someone acts on it.

  Three cases added to `hooks/scripts/_test/run-tests.sh`, two must-block and
  one must-allow, and sabotage-tested in both directions: reverting the
  diagnosis split misreports the unrunnable matcher as a parse failure and
  turns exactly that test red; removing the temp-file indirection turns three
  red. The suite is 134/0 restored.

  **`verify-gate.ps1` needs no matching change, which is worth recording**
  because a `.sh`/`.ps1` pair diverging is a standing landmine here. The
  PowerShell half is structurally immune to both defects: it matches
  in-process, so there is no exec to overflow, and its `try/catch` wraps only
  `ConvertFrom-Json`, so "could not be parsed" is only ever printed when
  parsing is what failed. The bash half has been brought to parity with what
  PowerShell already did correctly, rather than the usual direction.

  The `.bak-20260907-145114` sibling that had been sitting beside the script is
  removed rather than committed — a stray backup of a guard is exactly the file
  someone later mistakes for the live one.

### Fixed

- **crew 0.16.28: the codemap anchor WRITER corrupted every sha that was not
  exactly seven characters.** `crew_upgrade.py`'s `_ANCHOR_LINE_RE` was
  `^(anchor:\s*\S*@?)([0-9a-f]{7,40})` -- a greedy prefix and no end anchor.
  `[0-9a-f]{7,40}` is satisfied by the LAST seven hex characters on the line,
  so the prefix absorbed everything before them and the rewrite left them
  attached:

      anchor: repo@1f97e51c   (8 chars)  ->  anchor: repo@1d61342c
      anchor: repo@<40 chars>            ->  anchor: repo@<first 33><new sha>

  Seven was the only length that survived, which is why it shipped: every
  anchor written by hand in this repo was seven, and the committed test
  (`test_anchor_is_bumped_only_on_a_touched_file`) asserts `head in text` --
  a SUBSTRING check that a corrupted `repo@1<head>` also passes -- against a
  fixture whose anchor is `0000000`. The test and the fixture were each one
  rung short of the defect.

  The corrupted value still parses: `crew_state._ANCHOR_RE` reads `1d61342c`
  as a well-formed sha. It simply names a commit that does not exist, so the
  freshness check reports that map behind HEAD forever and refreshing it never
  clears the warning. Found by running `/crew:onboard --refresh` and reading
  what it wrote, not by review.

  This does NOT contradict CLAUDE.md's "anchor length does not matter" note.
  That entry is about `crew_state._ANCHOR_RE`, the COMPARISON, which is
  correct and already end-anchored, and it is silent on the writer -- a
  different regex in a different file. Both are now covered.

  Fixed with a lazy prefix and an end-of-line lookahead:
  `^(anchor:\s*\S*?@?)([0-9a-f]{7,40})(?=\s*$)`. Verified at 7, 8, 12 and 40
  characters, on a bare `anchor: <sha>` with no repo name, on a repo named
  `deadbeef` (hex, so a greedy or eager pattern would eat the NAME), and with
  trailing whitespace. Three regression tests assert the anchor READS BACK as
  head through `_ANCHOR_RE` and RESOLVES to a real commit -- never that head
  appears somewhere in the file. Sabotage-tested: restoring the old pattern
  turns all three red.

  The five anchors this bug wrote during the refresh (`crew`, `repo-docs`,
  `marketplace-registration`, `verification-harness`, `install-scripts`) are
  repaired to `d61342c3`, and each was checked with `git rev-parse` rather
  than assumed.

### Changed

- **Five codemap subsystems refreshed and re-anchored to `d61342c3`.** Chosen
  by the per-path check CLAUDE.md prescribes, not by the anchor lag: the pulse
  reported all ten maps behind HEAD, and `git diff --name-only <anchor>..HEAD
  -- <paths the map documents>` showed only five with real changes behind them.
  `localgpu`, `mcp-servers`, `obsidian-vault`, `skills-itsm` and
  `skills-security-ops` come out empty and are deliberately left at
  `1f97e51c`; re-anchoring them would assert a verification nobody performed.

- **`repo-docs.md`'s `render.sh` citations are repo-relative.** They read
  `render.sh:20` and `render.sh:32-35`, and TWO files carry that name --
  `plugin/crew/skills/crew-diagrams/scripts/render.sh` and its `_test/`
  sibling -- so the bare form was ambiguous as well as unpasteable into
  `git diff -- <path>`, which is the whole re-verification mechanism. All
  three cited lines were checked before rewriting: `:20` creates `out/`,
  `:32-35` is the `cygpath` block, `:45` is the `mmdc` call.

  Worth recording that the reconcile's own 62-item conflict list did NOT flag
  this. Every one of those items is a map token graphify has no AST node for
  -- bash variables, `pscustomobject` keys, CLI strings -- and all 16 cited
  paths were checked and exist. On a repo that is mostly shell and markdown
  that list is ~100% false positives, while a genuinely broken anchor passes
  silently, because the graph has no node for either `render.sh`.

- **`.crew/config.json` gained the eight tier-2 roles it was already entitled
  to** (`smoke-author`, `dba`, `browser-tester`, `analyst`, `planner`,
  `infrastructure-architect`, `scribe`, `researcher`), taking the roster from
  5 to 13. `--force` fills in the ladder the declared tier already grants; the
  tier itself is unchanged. Kept at the user's direction.


### Fixed

- **crew 0.16.27: a repo `null` no longer shadows a machine-global value.**
  The bug the `worktree.root` work exposed, and it was never about
  `worktree.root`: `/crew:init` writes `templates/config.template.json`, which
  spells out EVERY key including the ones whose default is `null`.
  `merge_defaults` treats that null as a supplied value, so it beat the global
  layer -- and the machine-global file therefore did nothing for any repo crew
  had ever initialised, which is every managed repo.

  Measured on the committed template, with a global value set for each:
  `memory.vaultPath`, `qa.codex.model`, `notify.chatId`,
  `secondOpinion.model` and `worktree.root` all resolved to `None`. Five keys,
  not one. The global layer has been advertised since 0.16.0 and was inert for
  all of them.

  Fixed as `crew_config.null_shadows` / `without_null_shadows`, which is
  `_layer_supplies`' existing rule one case wider -- an empty dict "mentions a
  key without deciding its value", and so does a null. Deliberately NARROW: it
  fires only where the global layer actually supplies something, so
  `context.reserveTokens: null` still means "off" rather than silently becoming
  the 100000 default. A blanket "null means unset" would have broken that, and
  the README documents it.

  Deliberately NOT fixed in `merge_defaults`: `crew_upgrade.upgrade_config`
  shares that function, and changing null semantics there would rewrite users'
  files during migration rather than only resolving them for a read.

  Both `resolve_config` and `/crew:config`'s source column call the same
  helper, so the value the run uses and the layer the report names cannot
  disagree -- the failure this module already carries scar tissue for.

  The regression suite is sabotage-tested, and the first version of it FAILED
  that test: it exercised the helper directly, so deleting the call from
  `resolve_config` left it green. Two end-to-end tests through `resolve_config`
  and `explain_config` were added for exactly that gap; removing either call
  site now fails one named test.

- **crew 0.16.27: `worktree_path` neutralises both separators, and `:`.** The
  shipped regex was `[\/]+`, which inside a character class is an escaped
  forward slash and matches `/` alone, so a backslash travelled through intact
  and `feat\x` resolved one directory DEEPER than every other worktree. Found
  by re-running the control rather than reading it, and independently by the
  security review. `_SEPARATORS` is now derived from `os.sep`/`os.altsep`
  instead of written as a regex literal, because the escaping is what went
  wrong -- the same trap then bit twice more in this change's own docstrings.

  `:` joins them for a Windows-only reason: `myrepo-release:v1` is NTFS
  alternate-data-stream syntax, naming a stream rather than a directory. git's
  ref-format forbids both `\` and `:`, so neither is reachable from a real
  branch -- but this function's signature is a string, and a contract nothing
  tests is a comment.

- **crew 0.16.27: the worktree leaf carries a repo digest.** The leaf was
  `<basename>-<branch>`, and an earlier docstring claimed that let several
  repos share one root safely. It does not: two checkouts called `myrepo` under
  different parents -- two clients, one project name -- produce the same leaf
  for the same branch, so one repo's `/crew:emergency` worktree lands in or is
  mistaken for the other's, with both directories looking correct. Raised by
  the security review. A 6-character `blake2b` of `normcase(realpath())`
  disambiguates them and is stable across symlinks, drive-letter case and
  separator spelling.

- **crew 0.16.27: `worktree.root` is reachable from a command.** Codex called
  the key unused and was right -- it resolved, and nothing a command could run
  returned the answer, so two lanes placing worktrees would each invent their
  own path. `crew_state.py --worktree-path <branch>` (or `-` for the root)
  prints it, resolved through `crew_config.resolve_config` so the machine-global
  file actually applies. `/crew:emergency` and `/crew:scale` now call it.

  Both commands' prose was also corrected: a subagent's `isolation: worktree`
  is placed by the harness and crew cannot redirect it. The first draft of this
  change implied otherwise, which would have sent someone setting
  `worktree.root` and watching it do nothing.

- **The AWS Pricing installer row refuses to register when `uv` fails.**
  `claude mcp add` records a command without running it, so a failed
  `pip install uv` followed by an unconditional add registered a server whose
  executable was absent -- surfacing later, inside a session, with nothing
  pointing back at the install step. Both scripts now check the install and the
  resulting PATH, and skip with a reason. Raised by Codex against both halves.

### Security

- **A real Power Automate tenant snapshot was committed and pushed to this
  public repository.** `skills/power-automate-api/scripts/pa-snapshots/flow-*.json`
  carried two SharePoint site URLs and 68 GUIDs (flow, connection-reference,
  list and environment ids). No tokens, passwords or email addresses. Found by
  the Codex QA review of PR #81, not by a human reading the diff -- a 51KB JSON
  blob in a 59-file changeset is precisely what nobody opens.

  The owner's decision, recorded rather than paraphrased: leave what is already
  published, and stop it recurring. Nothing was rewritten or force-pushed. The
  file is untracked and `skills/power-automate-api/.gitignore` now ignores the
  snapshot directory wholesale, so the next one cannot arrive the same way.
  `pa.py` writes those snapshots at runtime as rollback state; they were never
  meant to be tracked.


### Added

- **`VoltAgent/awesome-claude-code-subagents` joins the community row**, as
  `voltagent-infra` and `voltagent-qa-sec`. It goes in the existing `COMMUNITY`
  group rather than a new menu row, so no sub-picker group was added and
  `check_group_parity` needed no new case.

  Chosen from evidence in this repo rather than from a listing: the 21 agent
  files added to `plugin/crew/agents/` in this same release map onto VoltAgent's
  ten bundles almost one-to-one -- `penetration-tester`, `code-reviewer` and
  `compliance-auditor` are `voltagent-qa-sec`; `platform-engineer` and
  `database-administrator` are `voltagent-infra`; `fintech-engineer` and
  `payment-integration` are `voltagent-domains` -- and `agents/design-bridge.md`
  already names `VoltAgent/awesome-design-md` in its own description. The repo
  was already consuming this source by copy-paste.

  That is the argument for registering it rather than copying from it. The
  copy-paste route is what produced the defect fixed above: 21 files landed in
  `agents/` registered in nothing, so `/crew:pm onboard <name>` called every one
  of them unrecognised and `test_every_agent_definition_is_a_role_crew_knows`
  went red. Installed plugins also carry version bumps; a pasted file is a
  frozen snapshot.

  Only two of the ten bundles are listed, the two that match what this repo
  does. `wshobson/agents` (marketplace `claude-code-workflows`) was the
  runner-up and is genuinely relevant -- it is multi-harness across Codex and
  Copilot, which suits crew's QA providers -- but it publishes 94 plugins, and a
  94-row sub-picker is the opposite of the context trimming this release is
  otherwise doing.

  `scripts/_test/menu-groups.sh` moves with it: the community group is 7 plugins
  across 4 marketplaces now, not 5 across 3, and the `all` case selects 7. Those
  numbers are the dedup assertion -- a marketplace behind several plugins is
  registered once -- so they have to be restated, not relaxed.

- **Three documentation MCP servers, as menu rows 22-24.** `aws-docs-mcp`
  registers AWS Knowledge (`https://knowledge-mcp.global.api.aws/mcp`),
  `aws-pricing-mcp` installs `awslabs.aws-pricing-mcp-server` over `uvx`, and
  `ms-learn-mcp` registers Microsoft Learn
  (`https://learn.microsoft.com/api/mcp`). All three are appended to the end of
  `MENU_KEYS`, so nothing already numbered moved and a saved `--select` keeps
  meaning what it meant. All three default to off, like every other MCP row.

  Two of the three are remote HTTP endpoints with **no credentials at all** —
  nothing to install, nothing to expire, which is the reliability argument for
  preferring them. Both were probed live before being added: each answered a
  real MCP `initialize` and returned its tool list. AWS Knowledge is separate
  from the existing `aws-mcp` row on purpose — that one reads a real account
  and this one reads published documentation, so a machine that may not have
  the first can still have the second. AWS Pricing is the one that does need
  credentials, because the Price List API is an API call rather than a document
  fetch and the role needs `pricing:*`; the calls themselves are free.

  Microsoft Learn is one server for three of this repo's domains rather than
  three servers: `learn.microsoft.com` carries the Azure, SharePoint and Power
  Automate / Power Platform documentation, so `intune-graph`,
  `power-automate-api` and the SharePoint skills all resolve against it.

- **Three skills join the marketplace: `jira-manager`, `knowbe4-admin` and
  `power-automate-api`.** Each is registered in every place a registration has
  to touch at once — the marketplace entry, both README catalog tables, both
  install scripts' skill catalogs, and `INSTALLATION.md`'s per-skill install
  commands — so `scripts/check-marketplace.py` passes rather than reporting a
  half-registration nobody can tell the intent of. `skills/knowbe4-admin/`
  arrived nested one level too deep (`skills/knowbe4-admin/knowbe4-admin/`),
  which put `SKILL.md` where the checker's manifest rule cannot see it; it is
  flattened here.

  `skills/task-observer/` also arrived, and is NOT registered. Menu item 8 of
  both install scripts already clones the same skill from
  `rebelytics/one-skill-to-rule-them-all`, and the two copies were
  byte-identical, so registering it would have shipped the skill twice to
  anyone who ticked both rows. The upstream row stays; the repo copy was
  removed. Menu numbering is unchanged, which is the point — `--select 9,12`
  keeps meaning what it meant.

- **crew 0.16.26: `worktree.root`, and 21 more domain specialists.**

  `worktree.root` says where `git worktree add` puts a crew worktree.
  `/crew:emergency` runs two candidate fixes in a worktree each and tier 3 in
  `/crew:scale` is parallel sessions across worktrees, so the directory they
  land in was already a real question with no answer but git's habit of the
  checkout's parent — which is the wrong disk on a machine whose repos live on
  a small system drive, and an index rebuild per worktree on one that syncs
  that parent to cloud storage. It is inheritable from
  `~/.claude/crew/config.json`, because which disk has room is a fact about the
  machine and not about a checkout.

  The setting resolves in one place, `crew_state.worktree_root` /
  `worktree_path`, rather than at each call site: two emergency lanes started
  seconds apart have to agree on the path or the second adds a worktree the
  first cannot find. `null` keeps the old behaviour exactly, so a config that
  never gains the key behaves as it always did and no worktree already on disk
  is stranded. `~` and environment variables are expanded — `~/worktrees` is
  what a person types, and without the expansion `os.path.join` makes a literal
  `~` directory that looks like it worked. A relative path resolves against the
  repo rather than the process's working directory, because a hook runs from
  wherever the session happens to be. The leaf carries the repo name
  (`<repo>-<branch>`), which is what lets several repos share one root without
  two branches called `fix` colliding, and a `/` in a branch name becomes `-`
  so the worktree does not land a directory level deeper than everything that
  lists the root.

  The 21 new agent files were sitting in `plugin/crew/agents/` unregistered.
  That is the exact defect `test_every_agent_definition_is_a_role_crew_knows`
  exists to catch: an `agents/<name>.md` in neither `ROLE_TIERS` nor
  `SPECIALIST_ROLES` dispatches nothing, and the only symptom is
  `/crew:pm onboard <name>` calling it unrecognised forever. All 21 are
  registered as specialists — they carry no evidence about how much crew a repo
  needs, so no tier grants them — in `crew_state.SPECIALIST_ROLES` and in both
  markdown tables the committed tests check it against. `SPECIALIST_ROLES` goes
  15 -> 36; the tier ladder is unchanged at 13. Sixteen of the files also
  declared `model: opus` or `model: haiku`, which `validate-prompts.py` rejects:
  every role but `pm` and `qa-reviewer` runs on `sonnet` by design, and
  inheriting or raising the tier per agent makes the model depend on whoever
  spawned it.

### Changed

- **The installer no longer registers the `claude-code-plugins` marketplace.**
  It existed solely to carry `frontend-design`, which `claude-plugins-official`
  also publishes and which the installer already registers for `superpowers`.
  `TEAM_SPEC` in both scripts now points there, so the plugin still installs
  and one fewer marketplace gets cloned and refreshed on every machine. Nothing
  in the catalog is lost.

### Fixed

- **crew 0.16.23 -> 0.16.25: the sabotage harness can no longer report PASS
  over a tree it corrupted.** `tests/sabotage.py` mutates real source in place,
  and `d362a2bd` shipped `crew_state.py` with one of those mutations still in
  it — a killed run skipped the `finally`, the next run's `shutil.copy` put the
  mutated file over the good backup, and the suite printed PASS because nothing
  compared the restored bytes to anything. Found by a human reading a diff,
  which is the one thing a regression suite exists to stop being the only
  detector.

  Five guards, in the order the defects bite. `main` **refuses to start** when
  a `<file>.bak` is present — that file is the only surviving original, so the
  run that would destroy it stops, names it, and prints the `mv` that undoes
  the mutation still in the tree. `install_exit_handlers` restores on `atexit`
  and on SIGTERM/SIGINT/SIGBREAK/SIGHUP, each looked up by name because
  SIGBREAK is Windows-only and SIGHUP POSIX-only; `finally` unwinds on an
  exception and on KeyboardInterrupt but not on the external timeout that
  actually kills these runs — and a restore that *fails* there stays registered
  so the atexit pass retries it, rather than being cleared and forgotten.
  `apply_mutation` raises rather than copying over an existing backup, and
  writes each backup under `.bak.partial` before renaming it into place, so a
  `.bak` is never half-written: the startup guard trusts that name as the only
  good copy, and a partial one would turn its `mv` instruction into the thing
  that destroys an intact source. And a sha256 per target, taken before the
  first mutation, is compared after **every** restore — on the loop's path, the
  signal path and the atexit path alike, since verifying one and claiming all
  four is this repo's own signature defect. A mismatch prints both digests and
  fails the suite, so the PASS line can no longer outrun the tree it describes.
  SIGKILL stays uncatchable; the startup refusal is what covers it, on the next
  run.

  `*.bak` and `*.bak.partial` are now in `.gitignore` — the existing `env.bak/`
  and `venv.bak/` entries are directories and never matched a backup file,
  which is how one got committed. A *tracked* `.bak` is the damaging case now
  that the harness refuses to start when it sees one: it would gate the suite
  off permanently on every clone. Ignoring does not preserve any `git status`
  signal (ignored files are hidden from it); the filesystem check at startup is
  what replaces that, and `git status --ignored` shows one by eye.

  16 tests in `tests/test_sabotage_harness.py`, none of which touch a real
  source file, plus ten independent mutations of the new guards themselves,
  10/10 red. That independent run earned its keep immediately: it caught one of
  these new tests being **vacuous** — it asserted a `.bak.partial` was gone
  after the run, which `apply_mutation` makes true whether or not the sweep
  that removes it exists.

- **`mcp-servers`: a per-package test run can no longer exercise last build's
  code.** Every package points `main`/`exports` — and its tests — at `dist/`,
  so editing `packages/core/src` and running `npm test -w packages/graph`
  skipped the root build and tested a stale core, invisibly: the consumer's own
  build was current and the behaviour under test was not. `scripts/check-dist-fresh.mjs`
  is now each package's `pretest`; it compares the newest `.ts` under `src/`
  and `test/` against the newest `.js` under `dist/`, and refuses the run while
  naming the directory that moved. 14 tests of its own, wired into the root
  `npm test`.

  A consumer is checked by checking **core itself, recursively** — not by
  comparing the consumer's `dist` against `core/src`. The distinction is the
  whole point: a consumer imports `core/dist` at runtime, so a consumer
  rebuilt after a core source edit has a `dist` newer than everything and still
  loads stale core. Two other fail-open shapes went with it. An unreadable
  source directory now raises instead of contributing mtime `0`, which compares
  older than everything and reads as fresh — the guard passing on a tree it
  could not see. And equal timestamps are **stale**, not fresh: measured on
  this repo, a real `npm run build` leaves every package's newest `dist/*.js`
  strictly newer than its newest `src/*.ts` (11.9s for core) with
  sub-millisecond mtime fractions, because tsc reads before it writes — so
  accepting equal only ever admits a genuine edit landing in the same coarse
  tick as an older build.

  The TODO entry that opened this asked for "a CI check that rebuilds and
  diffs". That was aimed at a hole that does not exist — `dist/` is untracked,
  and the root `test` script already builds core first, so CI cannot test stale
  JS. The entry was rewritten to say what is actually true rather than ticked
  against its original wording.

### Added

- **crew 0.16.22 -> 0.16.23: twelve domain specialists, and the drift check the
  registration surface needed once it grew.** Eleven language and platform
  roles — `php-pro`, `python-pro`, `dotnet-core-expert`,
  `dotnet-framework-4.8-expert`, `angular-architect`, `react-specialist`,
  `rust-engineer`, `sql-pro`, `terraform-engineer`, `network-engineer`,
  `windows-infra-admin` — plus `qa-researcher`, which holds the Perplexity MCP
  tools and checks what a diff assumes about the outside world against live
  sources. `SPECIALIST_ROLES` goes 3 -> 15; the tier ladder is unchanged, so
  no repo gains a role it did not ask for and onboarding one still leaves
  `tier` alone.

  Coverage was mined from the VoltAgent subagent collection and every file
  rewritten: the originals open by querying a context manager crew does not
  have, assert targets nobody can verify ("PHPStan level 9", "coverage
  exceeding 80%"), and route to agents that do not exist in this marketplace.
  Each new file instead names the file that proves the repo needs it, the
  `dev.roles.<name>` key that decides its model, the failures the role
  actually walks into, and what it refuses to do — `terraform-engineer` never
  runs `apply` or a state operation, `windows-infra-admin` never runs the
  change against a live domain, `network-engineer` never touches a live
  device.

  **Three roles that were requested are not here, and that is the change.**
  `cloud-architect`, `security-engineer` and `database-administrator` each
  duplicated a ladder role, so the coverage was folded into the role that
  already owns the seam rather than shipped as a fourth opinion:
  `infrastructure-architect` gains multi-cloud and hybrid estates, migration
  sequencing and RTO/RPO-first DR; `security` gains the CI/CD pipeline, the
  supply chain, least-privilege grants and per-change threat modelling; `dba`
  gains backup, replication, failover and pooling as questions a change can
  invalidate. Three specialists that sit *next to* a ladder role rather than
  on top of one say so in their own files: `sql-pro` writes what `dba`
  reviews, `terraform-engineer` writes the HCL whose topology
  `infrastructure-architect` reviews, and `network-engineer` owns the packet
  path where `infrastructure-architect` owns AWS account and VPC structure.

  **A registration surface of fifteen needed a guard the surface of three did
  not.** `tests/test_role_ladder.py` now checks `SPECIALIST_ROLES` against
  `crew-pm/onboarding.md`'s table *and* crew README's roster table, and checks
  every `agents/*.md` back against the code. That last direction had no
  coverage at all before this: a specialist could ship as a file nobody
  registered, and the only symptom is `/crew:pm onboard <name>` reporting it
  as unrecognised, forever — silently, on the user's machine. Prose that
  enumerated the three specialists by name now points at the table, because a
  list in two places drifts and the prose copy is not the one a test reads.
  Sabotaged one at a time, all five red: a table row missing from code, a
  table row that acquired a tier, a ladder row dropped from the README, a name
  misspelt in `SPECIALIST_ROLES`, and an unregistered agent file.

  **One behaviour change to watch for.** `.crew/verify.json`'s `agents` field
  resolves a bare name to crew's own role first. Twelve names that previously
  resolved to another collection's agent — `php-pro`, `react-specialist`,
  `terraform-engineer` and the rest — now resolve to crew's. Nothing errors;
  the review simply comes back in a different voice. Namespace the name if you
  meant the other one. Recorded in `crew-verification/SKILL.md`.

  **Perplexity is an agent, not a `qa.provider`.** `qa.provider`, `qa.roles.*`,
  the fallback chain and the self-review family guard are untouched, so
  `/crew:review` routes exactly as it did. What family a web-grounded answer
  belongs to, and what a fallback that produces a different *kind* of review
  means, both need deciding before a name goes in that table — and
  `resolve_role` accepting any provider name (open in `TODO.md`) is why a
  half-answer there would fail open rather than loudly. The remaining half is
  tracked in `TODO.md`; crew README section 12b says plainly what does and
  does not exist today.

  The Codex gate returned seven blocking findings, all of them corrections to
  claims in the new agent prose, and all seven accepted: `strict_types` is
  decided by the *calling* file rather than the called one; an Angular guard
  hangs on an observable that never **emits**, not one that never completes;
  two Rust async runtimes link and run fine and break on nested `block_on` or
  a cross-executor API call; a function on an indexed column is non-sargable
  only against a plain column index, not against an expression or
  function-based one; `HttpContext.Current` flows across an await under
  ASP.NET's synchronization context and is lost when you leave it on purpose;
  "a connection that opens and then hangs" splits into three different faults
  with three different probes, and "not a firewall" is not one of them; and
  `netcoreapp*`/`net5.0` had no stated owner between the two .NET roles. Two
  non-blocking findings were taken as well.

### Changed

- **crew 0.16.20 -> 0.16.22: `crew_state.py` split at the endpoint ledger.**
  It reached pylint's `max-module-lines=3300` in the previous release and was
  merged five lines under the ceiling, which made the next comment a CI
  failure. No behaviour moves. The seam is the endpoint ledger (lines
  522-1476): the one block that reads and writes a file
  (`.crew/endpoints.json`) nothing else in the module touches, and from which
  `crew_state` needs exactly five names back. `crew_common.py` holds
  `read_text`, `git_out`, `dict_or_empty` and the git timeout, because both
  halves need them — in `crew_endpoints` they would make `crew_state` import a
  git timeout from a module named for endpoints, and left in `crew_state` they
  would make the import run both ways. `crew_state` re-exports all three, so
  `crew_config`, `pm_brief` and `crew_upgrade` reach them by the spelling they
  already use. 3300 -> 2293 + 978 + 80 lines.

  The failure a split like this hides is a patch target that silently stops
  patching. `tests/test_endpoints.py` set `crew_state.gizmoduck_installed` by
  string, and `read_endpoints` looks that name up in *its own* module globals
  — so re-exporting it would have rebound a name nothing reads, and 21
  gizmoduck-installed tests would have run against the real detector and
  passed for the wrong reason. `crew_state` deliberately does not re-export
  it; the tests name `crew_endpoints`. `tests/sabotage.py` treats a
  non-matching anchor as a failure rather than a skip, so its 35 moved
  mutations were repointed by matching each anchor's text against the three
  modules rather than by hand.

  **The compatibility claim is narrower than "nothing changed", and the
  review was right to say so.** Calling `crew_state.read_text(...)` still
  works and still returns the same thing. *Patching* `crew_state.read_text` —
  or `git_out`, `dict_or_empty`, `load_endpoints`, `scan_artifact_path`, or
  either remaining re-export — no longer changes what the moved functions do,
  because they resolve those names in their own module. Nothing in the repo
  does that today (swept by AST, not grep), so no test regressed; but the next
  one to try it would get a `setattr` that succeeds and accomplishes nothing,
  which is this repo's recurring bug class exactly. `tests/test_module_split.py`
  is the structural guard: it fails on any string-keyed patch of a re-exported
  name through `crew_state`, names the module to patch instead, asserts each
  re-export `is` the owner's object rather than merely present, and asserts
  `gizmoduck_installed` stays un-re-exported. All three sabotage-tested
  independently.

  744 passed, 1 skipped; sabotage suite PASS;
  `plugin/crew/hooks/scripts/_test/run-tests.sh` 128 passed.

- **localgpu 0.1.16 -> 0.1.18: `mcp-init` serialises before it opens.**
  `open(p, "w")` truncates at open time, so a write whose argument raises
  leaves a zero-byte file — and the target here is a repo's entire
  `.mcp.json`, every other server in it included. Nothing that reaches that
  line can make `json.dumps` raise today (`doc` came out of `json.loads`,
  `entry` is str-only), so this is not a fix for a live bug: the ordering is
  what keeps that a fact about today rather than something the next editor has
  to re-derive. `cli/_test/test_cli.py` pins it by making the serialisation
  raise and asserting the file survives; sabotage-tested by reversing the two
  lines, which turns that test red on the message it names. The stub raises
  only for the whole-document dict and records that it did, so an *earlier*
  `json.dumps` on another branch cannot abort the run before the write and
  leave the file intact for the wrong reason. 274 -> 275 passed, 1
  skipped.

  The same trap emptied `plugin/gizmoduck/commands/scan.md` to zero bytes
  during this work, and the "restore" that followed then succeeded against the
  empty baseline. It is now in `CLAUDE.md`'s Landmines with the AST scan that
  measured it: eight tracked writes carry the shape, three are test fixtures,
  one writes a temp file that is `os.replace`d, and the one that can actually
  fire — `skills/intune-graph/scripts/export_report.py:90`, `BadZipFile` out
  of `src.read()` — is named there rather than fixed here, since it needs its
  own skill bump.

### Added

- **localgpu 0.1.8 -> 0.1.9: `unignore`, the escape hatch the credential
  patterns needed.** `DEFAULT_IGNORE`'s `*.key` (added in 0.1.8, alongside
  `.env`, `*.pem` and the rest) is broad enough to catch legitimate non-secret
  files too - a localization resource, a keystore-adjacent asset - and until
  now there was no way to re-include one: `ignore` accumulates across config
  layers by design, and a file it caught stayed caught, silently, forever.

  `"unignore": ["*.key"]` in either config layer now drops that whole pattern
  from the effective `ignore` list. Pattern removal, not a per-file exemption
  - `"unignore": ["*.key"]` un-ignores every `.key` file, not one path - which
  is the simpler, more honest shape: it reads as "undo this default" rather
  than a second filter checked against every path in `is_ignored` alongside
  `ignore`. `unignore` layers the same way `ignore` does, as a union across
  both config layers rather than one overriding the other. Three entries
  cannot be lifted this way regardless of what a config asks for - `.git`,
  `.localgpu`, `node_modules` - because indexing those was never a preference,
  it was a mistake, and `unignore` only undoes preferences.

  `mcp/_test/test_unignore.py` builds a fixture repo and asserts on the
  *stored chunk text*, matching `test_secrets.py`'s shape: a file excluded
  only by a liftable default is indexed once unignored, a secret excluded by
  a pattern the user did not lift is not, and the hard floor holds against an
  explicit attempt to lift it. `mcp/_test/test_config.py` covers the merge in
  isolation - pattern removal, cross-layer accumulation, the hard floor, and
  the same bare-string rejection `ignore` already gets. Sabotage-tested:
  disabling pattern removal, dropping the hard floor, and dropping the
  bare-string type check each turned the matching test red on the behaviour
  named, independently. 228 -> 234 tests; `_verify/smoke.sh` stayed 10/10.

- **`localgpu` 0.1.5 - a new plugin that puts the GPU in this machine behind a
  repository.** Ollama serves `nomic-embed-text` and
  `qwen2.5-coder:7b-instruct-q4_K_M` on `127.0.0.1:11434`; an MCP server chunks a
  tree, embeds it into a vector store under `$LOCALGPU_HOME/index/`, and exposes
  `search_code`, `index_status` and `index_refresh` over it. Six commands -
  `setup`, `doctor`, `index`, `search`, `ask`, `crew` - and one bundled skill
  holding the paths, the two config layers and the VRAM rules every command reads
  before acting. No prompt, no file and no embedding leaves the machine, which is
  the whole reason to run it: code that is not permitted to reach a vendor API
  still gets search by meaning.

  **A `localgpu` CLI ships with it, and a translating proxy underneath.**
  `pyproject.toml` installs one console script into `$LOCALGPU_HOME/venv` -
  editable on purpose, because `cli/localgpu_cli.py` resolves its sibling `mcp/`
  directory from its own `__file__` and a copied install puts that `__file__` in
  `site-packages`, where `mcp/` does not exist. `localgpu shell` starts
  `cli/anthropic_proxy.py` on a loopback port and launches a **separate** `claude`
  process against it, so the current session and `.crew/config.json` are untouched;
  `localgpu proxy` runs the same proxy in the foreground for debugging or for a
  non-Claude client. The proxy exists because the two ends do not otherwise meet:
  `ANTHROPIC_BASE_URL` makes a client POST `/v1/messages` in the Anthropic Messages
  format, while Ollama's OpenAI-compatible surface is `/v1/chat/completions` with a
  different body, so pointing one straight at the other 404s on every request. It
  serves `POST /v1/messages` (streaming and not), `GET /v1/models` and `GET /health`,
  carries system prompts, multi-turn text, tool definitions, tool calls, tool
  results, stop sequences and sampling options across intact, and reports rather
  than fakes what cannot cross - images become a visible placeholder, thinking
  blocks are never synthesised, `cache_control` is accepted and ignored with zero
  cache hits reported, and the token counts are Ollama's rather than Anthropic's.
  It also recovers tool calls the model writes as prose: the shipped
  `qwen2.5-coder:7b-instruct-q4_K_M` puts `{"name": ..., "arguments": {...}}` in
  `content` and leaves `tool_calls` empty, which Claude Code reads as text - the
  tool never runs, `stop_reason` stays `end_turn`, and nothing errors. The
  promotion is deliberately narrow (tools actually offered, the entire body one
  JSON value, an object or list of objects, every name one of the offered tools),
  because the cost of a false positive is inventing a call nobody asked for. The
  child process is launched with `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_PROFILE`
  removed, since either outranks the API key and would send the session silently
  back to the real API. `cli/_test/` holds 46 tests over all of this - the wire
  format as pure functions, plus the proxy on a real bound socket against a fake
  Ollama - with a sabotage log recording four regressions reintroduced and
  confirmed red.

  **It registers no hooks, so nothing starts running when it is enabled.** There
  is deliberately no background indexer and no watcher - the index goes stale
  until someone runs `/localgpu:index`. A hook here would mean GPU work firing on
  somebody else's schedule, and on an 8 GB card that is not free: it evicts
  whatever model was resident.

  The heavy parts are not installed by installing the plugin. Ticking `localgpu`
  in either bootstrap script copies commands, a skill and Python source and
  downloads nothing; Ollama, the virtualenv and roughly 5 GB of weights come from
  `/localgpu:setup`, per repository, after it has shown the plan and asked. It
  will not install Ollama silently either - that registers a background service
  and a GPU runtime, so the command stops and points at the installer.

  The design constraint everything bends around is that a 7B model at 4-bit
  quantization is several tiers below the model reading the commands.
  `/localgpu:ask` therefore labels its output `qwen2.5-coder:7b (local)` rather
  than folding it into the session's prose, refuses to answer on thin retrieval,
  and always prints the `file:line` excerpts it was given; `/localgpu:crew` is
  report-only and writes nothing, not `.crew/config.json` and not an environment
  variable. An unattributed 7B claim inheriting a frontier model's credibility is
  the failure mode the plugin is written around - which is why `localgpu shell`
  prints, on every launch, that *everything* in that session is the 7B including
  any `/crew:*` command run inside it. Nothing enforces that; a review written
  there is labelled exactly like any other, so the shell is for exploring and
  drafting and not for gates.

- **`crew` 0.16.9 - four landmines from `CLAUDE.md`'s "Landmines" section, live
  in the repo a second time, fixed by reusing the reference implementation
  each already has.**

  `pm-brief.sh`, `pm-pulse.sh`, `platform-sync.sh` and `handoff-read.sh` each
  resolved Python with `command -v python3 || command -v python`, missing the
  `py` launcher and standing down with `exit 0` and nothing on stderr -
  landmine #2 verbatim, and sharpest on `pm-pulse.sh`: its own header explains
  that swallowing exit 2 drops the PM's blocking findings, and this line
  swallowed the whole hook. All four now source `_common.sh` and call
  `crew_py()`, printing a diagnostic to stderr before standing down -
  `handoff-read.sh` already had `_common.sh` sourced and `crew_py()` called
  five lines below the bad line, and did not use it there.

  `crew-setup/scripts/platform.sh` and `detect.sh` probed for PowerShell with
  a bare `command -v pwsh`, which misses `pwsh.exe` installed at the
  well-known Program Files path when it is not on `PATH` - verified on a
  machine `.crew/STATUS.md` documents as running 7.6.5, where the bare probe
  reported no PowerShell at all. Both now check
  `C:/Program Files/PowerShell/7/pwsh.exe` before falling back to `PATH`, the
  same idiom `_common.sh` and `_verify/smoke.sh` already used.

- **`crew` 0.16.7: three domain specialists, and four more guard defects.**

  `sharepoint-developer`, `power-automate-specialist` and `node-developer` join
  as full agents with their own refusal boundaries — a SharePoint change never
  breaks permission inheritance to make something work, and a Power Automate
  flow that has a trigger is already live, so neither touches a production
  tenant unasked.

  They sit **off the tier ladder**, which is the design rather than an
  oversight. Every ladder role closes a defect class any repo can have, so
  `roles_for_tier` grants every rung up to the declared tier — which is exactly
  how this repo, with no database and no UI, ended up holding `dba` and
  `browser-tester`. "This repo does SharePoint" is not a defect class; it is a
  fact about one checkout, knowable on day one. On the ladder, every tier-2
  repo on the machine would be handed a SharePoint developer it will never
  dispatch, and the tier column would stop meaning anything.

  So `crew_state.SPECIALIST_ROLES` holds them, no tier ever grants one,
  `known_role` stops `/crew:upgrade` reporting a deliberately-onboarded
  specialist as an unrecognised name on every run, and `/crew:pm onboard`
  justifies one from what is actually in the repo — a `package.json` with a
  server entry point, an SPFx `config/package-solution.json`, an exported flow
  definition — rather than from a pattern in `.crew/metrics.md`. Onboarding one
  leaves `tier` alone: the crew has specialised, not grown.

### Fixed

- **`crew` 0.16.10: two independent sets of fail-open guard fixes, merged.**
  Upstream's 0.16.7 fixed four guard defects in the Python hook modules
  (`crew_config.py`, `crew_platform.py`, `crew_state.py`, `pm_brief.py`); this
  branch's 0.16.8 and 0.16.9 fixed three more in the shell wrappers
  (`_test/run-tests.sh`'s PATH scrub putting CWD on `PATH`, and four hook
  wrappers standing down with nothing on stderr). Different defects, different
  files, found independently — `crew_state.py` auto-merged, so both sets are in
  this release rather than one silently replacing the other. The version is
  0.16.10 rather than 0.16.9 because the merge brings upstream content in under
  a number set before that content existed, and `claude plugin update` compares
  the declared version: shipping it as 0.16.9 would leave every installed copy
  reporting "already at the latest version" while holding the old code. The
  0.16.7 entries below are upstream's own and keep their number — that version
  shipped and is installable, so relabelling it would falsify the record for
  people who have it.

- **`crew` 0.16.7: a later dispatch cleared the family that wrote the diff.**

  `dispatch.json` held a single `dev` slot. Codex implements; a Claude
  developer dispatch runs afterwards on the same branch for something
  unrelated and overwrites the slot; `/crew:review` then reads a matching
  branch, declares Claude the author, bars Claude — and clears **Codex** to
  review the diff Codex wrote.

  It was invisible by construction. The overwriting record is newer than the
  merge-base, so the staleness check cannot disprove it, and the report says
  `recorded at dispatch`, which reads as verified rather than guessed. Nothing
  binds a dispatch to the commits it produced, so the honest answer is that any
  family dispatched on the branch in front of the reviewer may have written
  what is under review. All of them are now struck. Over-barring costs a rung;
  under-barring costs the entire point of the guard.

  The first fix reintroduced the same bug one line further down, by filtering
  that new history on the *last record's* branch instead of the checkout's.
  Those are the same value in the proven path and differ in the stale one,
  which is the path that matters — so `tests/sabotage.py` now carries exactly
  that mutation, because a suite that exercises only the proven path stays
  green with the bug restored.

- **`crew` 0.16.7: the dispatch record was written non-atomically.** Opening
  the live file `"w"` truncates it before the JSON is complete, and
  `read_dispatch` collapses malformed JSON to `{}` — so a concurrent reader saw
  *no* dispatch and fell back to reading the config, which describes the next
  run rather than the one under review. The guard failing open during an
  ordinary race is the worst version of this, because nothing about it looks
  like a failure. Sibling-then-rename with a PID-scoped temp, matching the
  config writes.

- **`crew` 0.16.7: a `.crew/config.json` of `{}` switched crew off
  permanently.** It parses, so `heal_config` adopted it as healthy — and
  `crew_state.collect` derives `isCrew` from the parsed config's truthiness, so
  every hook stood down, the PM brief and pulse skipped, and nothing ever said
  why. The second face is worse: `schema` reads as `SCHEMA_CURRENT` when the
  config is falsy, so `/crew:upgrade` answered "already current" forever and
  the repo could never migrate out of it. An empty object carries no
  hand-edits, which is the whole reason the healthy branch exists, so it now
  heals like a zero-byte file. No backup is taken: a backup of `{}` is a file
  whose only content is the absence of content.

- **`crew` 0.16.7: `/crew:model` printed `eligible` for a family it could not
  name.** `order_candidates` has always refused an unpinned `copilot` — Copilot
  hosts several families and an unset model does not say which, so it may be
  serving the author's own family. The human-facing role table said `eligible`
  at the same config. The gate was right and the report was optimistic, which
  is the worse half to get wrong, because a reader acts on the table. The new
  `crew_config.role_status` says `CANNOT PROVE INDEPENDENCE` instead, and `dev`
  rows now say `implements` rather than borrowing a verdict from a check that
  was never run on them — `model_report` resolves them with no author, on
  purpose, because the guard governs who may review and not who may write.

- **`crew` 0.16.7: two dispatch writers could both publish, and one would
  lose.** `.work/dispatch.json` was a single file that every dispatch read,
  modified and rewrote, so two dispatches each reading history H and
  publishing `H + itself` erased one another — and if the erased one wrote the
  diff, its family was never struck. The PM dispatches up to three roles at a
  time. Writing atomically only stops a torn read. A lock does not close it
  either: it has to be reclaimable, or one killed dispatch wedges the repo
  forever, and reclaiming is two calls against a pathname that a rival can
  replace in between — Windows has no inode, so "remove this only if it is
  still the file I looked at" cannot be said. Verifying the write and
  republishing does not close it either; that holds only for the writer that
  lands last, and three writers lose the middle one permanently.

  So there is no shared file left to race. Each dispatch writes its own
  immutable file under `.work/dispatch.d/` and the reader merges the
  directory. `dispatch.json` keeps a best-effort pointer to the most recent
  one, because `/crew:review` reads its mtime and `/crew:model` prints it, and
  losing that race now costs a display field rather than a record. **Both
  paths are gitignored by `/crew:init`** — ignoring the file and not the
  directory would commit the actual record.

  Three properties fall out of the shape rather than out of care: a malformed
  entry costs one entry instead of collapsing the whole record to `{}` and
  sending the guard back to the config; a bookkeeping write that fails cannot
  abort the dispatch; and a repo upgraded mid-branch has its pre-0.16.7 record
  adopted into the store before the slot holding it is overwritten.

- **`crew` 0.16.7: the dispatch history carried no ordering of its own.** The
  reader assumed the list it found was already newest-first, so a file laid
  out any other way decided which family survived the bound. Entries now
  record `at`, and an entry's own file mtime is a second witness to the same
  event. Neither is trusted to rank the store against the legacy file: a
  `dispatch.json` carrying far-future timestamps — a clock that ran ahead, a
  hand edit, a restored backup — would otherwise evict the dispatch that had
  just happened. The store outranks the legacy file structurally, so no value
  inside that file can promote it.

- **`crew` 0.16.7: a slot in the dispatch history could be spent on
  something that was not evidence.** The history is bounded, and the bound
  evicting the wrong entry is the same failure as never recording it — the
  family that wrote the diff is absent from `devHistory` and is cleared to
  review its own work. Three ways in, all closed:

  An entry with **no `provider`** named no author, so `author_families` always
  skipped it — and it was still consuming a slot. Ten hand-edited or truncated
  files ahead of a real dispatch emptied the history of the family that wrote
  the code. Something that is not evidence cannot displace something that is.

  The bound was **per store rather than per branch**, and the branch filter
  runs after the trim. A repo with a few active branches reaches ten
  dispatches in a day, and those evicted the record for the branch actually
  under review. The guard's question is "who was dispatched HERE"; a bound
  that answers it by discarding what happened here is the bug.

  Moving it inside the branch was not enough, and the next review round said
  why: **any** cap on families within a branch has the same input. Dispatch
  the family that writes the diff, then enough newer dispatches with distinct
  families, and the author is pushed out of its own branch's history while the
  report still says the provenance was proven. Raising the number moves the
  input and keeps the failure. So there is no cap there at all — the
  family-keyed dedup is the whole bound a branch gets, and it is enough,
  because a family appears at most once in one however many model ids it walks
  through. What is capped is **branches**, the axis that actually grows, at
  the fifty most recently dispatched — and never the branch currently checked
  out, which is resolved lazily and only when the cap would otherwise bite.

  **Pruning** counted raw files across every branch and family, so the same
  busy repo could push its own only record past the hygiene cap and delete
  it. The pruner now computes what the reader would keep, the same way the
  reader computes it, and never removes one of those — a directory larger
  than intended is untidy, a missing author family is a guard handing a diff
  to the model that wrote it.

  Records **adopted** out of a pre-0.16.7 `dispatch.json` carry that file's
  claim about when they happened, so they rank below everything the store
  wrote itself — a claim is what the tier exists not to trust. Adopted with
  their stated timestamp, one carrying a far-future `at` became the newest
  record in the repo and took the slot whose branch decides whether provenance
  is proven.

  A fourth, in the same family of mistake: adopting a pre-0.16.7 record was
  gated on "the store is empty", which closed permanently the first time that
  write failed transiently. It now compares the record itself, so it retries —
  and the slot holding it is not overwritten until the copy has landed, since
  a retry that reads from a record the failing call destroyed is not a retry.

- **`crew` 0.16.7: an unknown author family was reported as proven
  provenance.** A dispatch recorded on this branch by an unpinned `copilot`
  has no determinable family — Copilot hosts several and an unset model does
  not say which — so `family()` answers `None`, correctly. The author set was
  then emptied and handed back labelled `dispatch`, documented as "the guard
  is judging what actually ran": nothing struck, every reviewer eligible, and
  a report claiming the provenance was proven. It is now its own source,
  `unknown`, and `independentReviewer` is `false` whenever it applies —
  independence is a claim about the author's family, and there is none to be
  independent of. Nothing is barred on it, because barring a real reviewer on
  a value nobody established is the opposite error. Pinning
  `dev.copilot.model` is what resolves it.

- **`crew` 0.16.7: one unnamed family beside a named one still read as
  proven.** The entry above closed the case where EVERY recorded family was
  unknown. The mixed case walked straight past it: the `None` was discarded
  before the emptiness test ran, so `{None, "gpt"}` arrived as `{"gpt"}` and
  was returned labelled `dispatch`. An unpinned Copilot serving Claude writes
  the diff, codex is dispatched on the same branch afterwards, and the guard
  reports proven provenance for gpt — clearing Claude to review Claude's own
  work. One unnamed family now makes the whole source `unknown`, while the
  families that COULD be named stay in the set and stay struck: they ran, and
  dropping them to keep the old empty-set shape would clear the one reviewer
  there is positive evidence against.

- **`crew` 0.16.7: a dispatch the store refused to take was silent.**
  `record_dispatch` threw away `_append_dispatch`'s answer, so a dispatch
  whose entry file could not be written left no trace at all. The next
  dispatch of another family on the same branch was then reported as
  `dispatch` — a positive provenance claim — with the family that actually
  wrote the diff absent from the set. There is no durable marker to leave
  instead, because the write that failed is the store and a marker file lands
  in the directory that just refused one. So the failure stops being silent:
  the returned record carries `unrecorded`, and the dispatch CLI prints what
  could not be written and exits non-zero.

- **`crew` 0.16.7: evidence that could not be read was reported as evidence
  that never existed.** `_read_record_file` reduced a malformed `dispatch.json`
  to `{}` and said nothing; `_dispatch_entries` skipped an unparseable entry
  file the same way. Both are right not to raise and wrong about the
  consequence: a 0.16.6 record left malformed by a killed write is the only
  trace its dispatch left, so once a later dispatch of another family lands on
  the same branch, the guard returned that family labelled `dispatch` with the
  author gone — and with no record at all it returned `config`, which states
  that nothing was recorded, a claim no read of an unopenable file can make.
  Anything the store could not read now makes the provenance `unknown`, while
  every family it COULD read stays in the set and stays struck. Deliberately
  not scoped to a branch: a file that will not parse cannot be attributed to
  one, so it over-bars everywhere until it is deleted.

- **`crew` 0.16.7: the next dispatch erased the sign that anything was lost.**
  The entry above is only worth having if it survives one more dispatch, and it
  did not. `_adopt_slot` answered "may be overwritten" for an unparseable
  `dispatch.json` on the grounds that a rewrite loses nothing — true until the
  reader learned to distrust one, and false after it. `_write_slot` then
  replaced the bad file with a well-formed record, the next read saw nothing
  lost, and the guard went back to reporting proven provenance with the author
  missing. The slot is now refused while it cannot be read, which costs a stale
  display field and holds the guard closed until a human clears the file. And
  the report names that file: `unreadable` carries the names rather than a bare
  `true`, because the condition is repo-wide, permanent, and nothing below
  `DISPATCH_FILES_MAX` prunes it — "delete the unparseable file" is not guidance
  if it does not say which one.

- **`crew` 0.16.7: the pruner deleted the evidence that evidence was lost.**
  A reader that answers `unknown` over a file it could not parse is undone by a
  pruner that removes the file. `_prune_dispatch_dir` called
  `_dispatch_entries` with no `lost` list, so a malformed entry was skipped
  silently, never reached `protected`, and was deleted as an aged file — after
  which the next read found a clean directory, set no `unreadable`, and
  returned `dispatch` with whatever that entry held gone and nothing left to
  say it had ever been there. Unreadable files are protected now, for a
  stronger reason than live records are: a live record can be reconstructed
  from the merged history, and this file is the only thing between a lost
  dispatch and a confident answer about it. It leaves when a human deletes it.

- **`crew` 0.16.7: a record that named no author was treated as no record.**
  An entry that parses and carries a `kind` but no `provider` was skipped in
  silence, so a nameable dispatch on the same branch then answered `dispatch`
  over it. Skipping it is right — something that is not evidence must not
  spend a slot in the bound — but "it names no author, so it cannot BE the
  author" is the same mistake in a fifth place: a record of someone this store
  cannot name is not a record of nobody, it is `unknown`. It is skipped AND
  reported now, in `_merge_history`, because that is the one funnel entry
  files, the legacy `<kind>History` and the legacy slot all run through —
  reporting it upstream would have closed the store and left the legacy path
  silent.

- **`crew` 0.16.7: evidence is reported at the filter that drops it.** The two
  fixes above put the report in the right place for the paths they could see —
  `_dispatch_entries` for the store, `_merge_history` for everything reaching
  the merge — and both were undone by a filter running *earlier* that discarded
  the thing silently, so it never arrived to be reported. `_dispatch_entries`
  skipped every non-`.json` name, so a `.tmp` left behind by a crash between
  `_append_dispatch`'s write and its rename — a dispatch that may well have
  landed — was passed over without a word, and the next readable entry answered
  `dispatch` over it. `_history_items` did the same to non-dict members of a
  legacy `<kind>History`, to a `<kind>History` that was not a list at all, and
  to the legacy `<kind>` slot: it appended the slot only when the slot already
  named a provider, which made it the one record shape the `_merge_history`
  report above could never see. Each drop now says so, at the filter that makes
  it, and the slot goes through whatever it holds so the no-provider call stays
  in exactly one place.

- **`crew` 0.16.7: the hook count in crew's README.** The prose said eight
  scripts and sixteen entries while the table directly beneath it already
  listed all ten across five events, 20 entries.

- **`crew` 0.16.8: the machine-global config gets a template, a walkthrough,
  and a migration that finishes the job.**

  `~/.claude/crew/config.json` sets defaults for every crew repo on a machine,
  and nothing in crew ever wrote it, asked about it, or said it existed.
  `skills/crew-setup/SKILL.md` said so in as many words: "Nothing in setup
  creates the global file; a user who wants one writes it by hand." Writing it
  by hand required knowing the file existed, where it lived, which keys it
  accepted, and how it layered.

  Not hypothetical. On the author's machine that file carried `tier`, `roles`,
  `qa` and `sdp` and had **no `pm` block at all**, so every crew repo resolved
  to `pm.authority: report-only` while the user believed the PM was autonomous.
  The global file was valid, the repos were valid, and the resulting behaviour
  was a default nobody chose. It was found because someone opened the file for
  an unrelated reason.

  `templates/global.template.json` and `crew_config.default_global_config()`
  are the shape, held byte-for-byte identical by the same committed test the
  repo template has. It is deliberately not a copy of the repo template:
  `tracker`, `jira.project`, `obsidian.boardDir`, `graph.out` and `platform.*`
  are facts about one checkout, and shipping them globally invites a vault path
  set once that every repo inherits. What is left is what is a property of the
  machine or the person — `pm.authority`, the `qa` and `dev` provider tables,
  `secondOpinion`, `notify`, `memory.vaultPath`. It carries no `schema`:
  `resolve_config` exempts that key structurally so a global value can never
  make an unmigrated repo look current, and a template shipping it would hand
  every user the exact value that exemption exists to ignore.

  `/crew:config` is the walkthrough, reachable standalone for a user with no
  repo in mind and offered from `/crew:init` Phase 1. Its point is the
  **source** column: `crew_config.py --explain` prints every globally-settable
  key with its effective value and the layer that decided it — `repo`,
  `global`, or `default` — which is precisely the question the incident above
  could not answer. `--check-global` prints the findings.

  Four properties the writer enforces in code rather than in prose, each with
  a test that goes red when it is removed. It **merges**, so a key in an
  existing global file that the walkthrough never asked about survives. It
  **refuses** any path outside `default_global_config()`, by name, exit 2 —
  which keeps repo facts out of a file every repo reads and makes
  `graph.obsidian.confirmed` structurally un-grantable from a guided flow,
  since that flag is consent to write outside the repo, not a capability. It
  is a **dry run by default**; `--apply` is a second call. And it **marks a
  widening of `pm.authority`** on both the plan and the write. `/crew:upgrade`
  reports on the global file and fixes none of it, per `upgrade.md` §5 "Report
  — do not resolve": it is the user's own configuration, outside the repo,
  which is the strongest version of that rule this plugin has.

- **`crew` 0.16.8: a per-role provider table, and the family guard made
  visible in state (`schema` 2 → 3).**

  `qa` and `dev` each gain a `roles` table and a `fallback`, so
  `qa.roles.review` and `qa.roles.smoke` can be different models from
  different families. Both arrive **empty**: the migration writes no pin
  nobody chose, and an existing repo dispatches exactly as it did before it
  ran. `/crew:init` and `/crew:upgrade` offer the recommended table rather
  than leaving the user to find the keys.

  `crew_config.model_report()` — what `crew_config.py --models` and
  `/crew:model` print — carries two new keys alongside the per-role rows:

  - **`qaFallThrough`** — the evidence. One entry per provider in `qa.order`,
    in order, each with its `provider`, `model`, derived `family`, whether it
    is on `PATH`, and, when it cannot review, the single reason: absent from
    `PATH`, no `qa.<provider>.model` pinned so its family is unknowable, or
    same family as the author.
  - **`independentReviewer`** — the conclusion. `false` means every candidate
    in `qa.order` is unreachable or speaks as the family that wrote the diff,
    which is the one state `/crew:review` cannot fix by trying harder: it
    falls back to the `qa-reviewer` subagent and labels the result
    same-family. It runs; it does not count as an independent review.

  **A fifth round found the probe itself failing open.** `in_git_repo`
  returned a bool, so git being absent or timing out collapsed to False --
  which the rule reads as the safe "no repository here" case, and therefore
  as proof. It is tri-state now, and distinguishes git RUNNING and answering
  no (an answer) from git failing to run at all (unknown); only an explicit
  False proves anything. Also `sabotage.py` could restore from a backup
  `shutil.copy` had only partly written: copy never touches the source, so a
  failed copy leaves the original intact and restoring from the partial
  backup is exactly what would corrupt it. The two failures are handled
  separately now.

  **A fourth round found the same guard wrong a second time.** Plain
  inequality trusted a record written WHILE detached: that record stores
  `branch: null`, so reading it from another detached state compared
  None == None and read as proof. Branch values alone cannot decide this --
  the harmless missing branch (a directory with no branches at all) and the
  dangerous unreadable one look identical. `in_git_repo` separates them, and
  provenance is now proven in exactly two shapes: a readable branch matching
  the record's, or no repository paired with a record naming no branch.

  **A third round gated the merge and found two more.** `current_branch`
  returns None for a detached HEAD -- which is also the normal state during a
  rebase -- and the staleness guard read that as "this checkout has no
  branches" and trusted the record. Dispatch on `main`, detach, and only the
  recorded family was struck while the configured one stayed clear to review
  its own diff. The test is now plain inequality between the record's branch
  and the checkout's: both absent is a real match (a non-git checkout has
  nothing to switch between), one absent is not. And `sabotage.py` took its
  backup outside the `try`, so a failed write could leave a truncated source
  file behind; restoration is exception-safe and idempotent now.

  **A second Codex round on the fix commit confirmed all eleven and found two
  more, both about how stale provenance is represented.** A dispatch record
  with no `branch` was TRUSTED -- written before 0.16's field existed, it
  cannot prove which branch it came from, so striking only its family left
  the configured one clear to review its own diff. It now fails closed, with
  one exception that is not over-barring: a checkout with no branch at all has
  nothing to switch between, so it keeps the record. And `/crew:review` can
  judge a record stale by mtime, which only it can measure -- `--author-stale`
  carries that verdict into the resolved report, so `authorFamilies` holds
  both families and the command's own prose finally has data behind it. The
  `AUTHORS` variable that reads it is now consumed rather than assigned and
  abandoned, alongside `ELIGIBLE`, the report's own guard-applied candidate
  list.

  `plugin/crew/tests/sabotage.py` reintroduces three of these bugs and asserts
  the suite goes red for each. A test that stays green with the behaviour
  deleted is not coverage, and three of them shipped into this PR before Codex
  named them.

  **Codex gated this change on the PR and found eleven defects; all eleven are
  fixed here.** The four that would have shipped working-looking behaviour:

  - `upgrade_config` destroyed a wrong-typed NESTED value (`qa.codex: "human"`),
    reported `unmigrated: []`, and stamped the schema current -- a migration
    that ate a hand-written value and called itself clean. `merge_defaults`
    now takes a `discarded` list, the block is left exactly as written, and
    the schema is not stamped, so the next run retries it.
  - `/crew:review` re-parsed `.crew/config.json` for the model to invoke, so
    `qa.roles.review` and the entire machine-global layer were invisible to
    the only command that runs a review: `/crew:model` reported the pinned
    reviewer while `/crew:review` ran the block default. It now resolves
    through `crew_config.py --models --json`, and the report grew `qaProviders`
    so nothing has to reopen the repo file to find a provider's model.
  - `author_family` read `dev.provider` and ignored `dev.roles.*`, so a repo
    pinning `developer` to codex under a `claude` block reported the author as
    `claude` -- striking claude and clearing CODEX to review a codex-written
    diff. It is now `author_families`, returns a frozenset, and a record naming
    a different branch fails closed by striking both.
  - `independentReviewer` treated presence on `PATH` as an eligible reviewer,
    so a logged-out CLI made it `true`. `order_candidates` now accepts a
    `probe`, and `independentReviewerProbed` says whether capability was
    measured or merely assumed.

  Also: the config rewrite is atomic (`os.replace`) rather than a truncate in
  place; three tests that would have passed with the behaviour deleted were
  rewritten and sabotage-tested; `pm.maxDispatches` is globally settable again;
  and the agent files no longer claim Codex runs "by default" when a fresh
  install ships `dev.provider: "claude"` with an empty `dev.roles`.

  Neither key is a new rule. The interlock — the family that wrote the code
  may not review it, guard evaluated before any pin — is unchanged; what
  changed is that its consequence is now in the report instead of being
  something a reader had to infer from four `BARRED` rows. The author family
  itself now comes from what was recorded at dispatch (`.work/dispatch.json`,
  gitignored) and falls back to reading the config only when nothing has run
  in the checkout — labelled as such, because that describes the next
  dispatch rather than the diff in front of the reviewer.

- **`crew` 0.16.8: `upgrade_config` migrated two blocks and claimed to have
  migrated all of them.**

  Reported by the user 2026-09-05: `/crew:upgrade` did not pick up the provider
  and roles changes. The whole of the migration was `pm`, `graph`, and
  `schema = SCHEMA_CURRENT` — stamped unconditionally. Its docstring still read
  "v1 config -> v2": written for that one migration, never extended when 0.14.4
  added the `qa`/`dev` provider table or when 0.15.x added three roles. So a
  config predating 0.14.4 came out of an upgrade marked current while missing
  `qa.order` and the entire `dev` block, and an absent `qa.order` made
  `/crew:model` report zero candidates and "no independent reviewer" for a setup
  that reviews fine.

  `qa` and `dev` now migrate, from `crew_state.QA_DEFAULTS` and `DEV_DEFAULTS`
  — moved there so a freshly created repo and a freshly upgraded one land on
  identical values by construction, the same rule `PM_DEFAULTS` already
  followed.

  `roles` migrates by **adding**, not by reporting: a config already at tier N
  gets every ladder role at or below N that it is missing. An upgrade that
  reported the change and left the user to re-derive it would be the same
  "a default nobody chose" failure. Two things that does not license, because
  they are different decisions from adding capability: it cannot grow a crew
  past the tier the config itself declares — moving up is `/crew:scale`, with
  evidence — and it never removes anything, because removing a role destroys
  the coverage that would have told you whether the removal was right, so
  `/crew:pm offboard` keeps its explicit-yes gate. `tier` is recomputed
  afterwards, and the run states the roles it added and the tier it moved from
  and to, at the CLI and in `.crew/codemap/UPGRADE.md`, every run including
  when the answer is none — a crew that silently grows is the thing
  `/crew:scale` exists to catch.

  `schema` is stamped only when every block actually migrated. A `pm`, `graph`,
  `qa`, `dev` or `roles` value that arrived as the wrong type would have been
  silently discarded by `merge_defaults`; it is now left exactly as written,
  named in the report, and the status is `upgraded with unmigrated blocks`, so
  the repo still reports an upgrade as needed rather than being marked done
  with a block nobody migrated. `upgrade_config` returns `(config, notes)` for
  this reason: what the run has to say is not optional decoration.

- **`crew` 0.16.8: the three agents added in 0.15.x joined the tier ladder, and
  the ladder moved into code.**

  `infrastructure-architect`, `scribe` and `researcher` shipped as definitions
  with no row in `crew-scaling`'s tier table, so `/crew:scale` would not propose
  them and `/crew:pm` would not onboard them from evidence. All three are now
  tier 2, beside `dba` and `docs-writer`: each closes a defect class that only
  appears once a repo is doing enough of that kind of work to have the evidence.

  The ladder itself is `crew_state.ROLE_TIERS`, because computing a tier from a
  role list is arithmetic, and parsing a heading in a skill file to decide what
  an upgrade writes would make the doc load-bearing and the code advisory.
  `crew-scaling/SKILL.md` and `crew-pm/onboarding.md` still describe it for a
  human, and `tests/test_role_ladder.py` asserts all three agree — a row added
  to one and not the others fails CI.

- **`crew` 0.16.8: `merge_defaults` said "recurses one level" and does not.**
  It calls itself whenever both sides hold a dict, to whatever depth the
  default has — which is why a supplied `qa` naming only `provider` still comes
  out with `qa.codex.model`. The new `crew_config._layer_supplies`, which
  mirrors this function to answer "which layer decided this value", depends on
  the real behaviour, so a docstring describing something else stopped being
  merely inaccurate. Two implementations of one merge policy drift silently --
  the source column would name the wrong layer and every test would still
  pass -- so `tests/test_crew_config.py` now pins them to each other by
  running both over every settable key and over each of the three ways the
  policy can branch, rather than by asserting the mirror in a comment.

- **`crew` 0.16.8: stale reference tables in `plugin/crew/README.md`.** §25 said
  21 commands and 11 agents, and listed neither `/crew:model`, `/crew:roster`,
  nor the three agents 0.15.x added. `PLUGINS.md` had been updated and the
  plugin's own README had not, which is the worse half to miss: it is the file
  someone reads after installing. Both are now 24 and 14, and `PLUGINS.md`'s
  own header count (`21 commands`) and `validate-prompts.py` check count (110)
  were stale by the same release and are corrected too.

- **`obsidian-vault` 0.3.0: vault profiles, note templates, and a bridge status
  that tells four failures apart.**

  A vault is either authored, where a person reads it, or generated, where only
  Claude greps it. `hooks/scripts/vault_profiles.py` is the single definition of
  what belongs in each, read by install, by the profile report, and by optimize —
  install and strip are the same decision from two sides, and two lists would
  have drifted. `vault_ops.py profile` reports the detected kind with the
  evidence behind it, from note count, plugin count, a graphify manifest or the
  `code-graph` plugin, and whether notes carry the contract's frontmatter. Never
  a flag the user sets, always overridable.

  The sets were read off working vaults rather than invented. `bridge` is
  `obsidian-local-rest-api` alone — the floor, without which a vault is invisible
  to Claude. `graph` adds `code-graph` and deliberately nothing else. `authored`
  is the fuller human set, with omnisearch and text-extractor only below 50,000
  notes. A bare `enable-plugin --apply` writes only the bridge floor; every
  other plugin has to be named, because enabling a set behind one yes is the
  blanket-confirmation this plugin's own optimize command already refuses. A
  split stays the last resort, its seam is provenance rather than size, and the
  report counts the wikilinks it would break.

  `templates/` closes a gap that had been costing a retry on every note:
  `vault_guard.py` enforced the six-key contract but nothing helped satisfy it,
  so a conforming note was written by hand and fixed afterwards. Six templates —
  `memory`, `concept`, `decision`, `session`, `source`, `design` — each verified
  against the guard as the PostToolUse hook invokes it, passing on the first
  write with no advisory. `/obsidian-vault:note` creates one. `design` ships as a
  `type: concept` variant: the guard has no type enum, so a new type would have
  passed while being invisible to the contract's type keys and to any Dataview
  query built on them.

- **`crew` 0.15.2: every agent can now reach a skill, and the UPDATE.md gate
  actually runs.** 0.15.1 gave the `Skill` tool to the eight agents that named a
  crew skill in their prose. That fixed the agents whose instructions were
  already broken and left the other six unable to reach `find-skills` — or any
  skill — at all, which is a capability question rather than a bug: an agent
  that discovers mid-task that a skill exists for what it is doing should be
  able to load it. `analyst`, `dba`, `developer`, `explorer`, `researcher` and
  `security` now hold it too, so all fourteen do. `Skill` loads instructions and
  grants no write capability, so `explorer` stays read-only, which is the whole
  reason it is safe to dispatch without a plan.

- **`scripts/sync-updates.py --check` runs in CI.** It shipped in 0.15.1 as a
  gate nothing invoked. That is worse than having no gate: the mirrored blocks
  carry a comment saying they are generated, so a reader takes them as current,
  and the one mechanism that could contradict that was never run. Now a stale
  mirror fails `Marketplace / check` the way a stale plugin version already
  does. Sabotage-tested against a hand-edited block: tampered exits 1, clean
  exits 0.

- **`UPDATE.md` per component directory, mirrored into the READMEs by a
  generator that can fail CI.** `plugin/`, `skills/` and `mcp-servers/` each own
  an `UPDATE.md` listing what is newly *possible* there — distinct from
  `CHANGELOG.md`, which records everything including fixes. Each file's sections
  are mirrored into that directory's `README.md` and into the root `README.md`
  between `<!-- BEGIN <dir>/UPDATE.md -->` markers, reusing the convention the
  root README already used for its folder mirrors rather than inventing a second
  one.

  The difference from those existing blocks is that these have
  `scripts/sync-updates.py`. The older mirrors are maintained by hand and nothing
  notices when the source moves on — survivable for a table that changes a few
  times a year, not for a "what's new" list whose entire value is being current.
  `--check` writes nothing and exits 1 when a block is stale, 2 on a structural
  fault it will not paper over.

  Two rules fall out of splicing one text into two directory depths, and both are
  enforced rather than merely documented. Headings are demoted one level, since a
  mirrored section always sits under a heading its host supplies. And relative
  links are rejected outright: `../CHANGELOG.md` resolves from
  `plugin/README.md` and 404s from the root, so no relative target can be correct
  in both. That second rule was in the module docstring with nothing checking it,
  and the very first `UPDATE.md` written against it shipped a
  `../.claude-plugin/marketplace.json` link that had to be caught by eye — a rule
  a generator states and does not check is worse than no rule, because it reads
  as guaranteed. Sabotage-tested: injecting a relative link exits 2, removing it
  exits 0.

### Fixed

- **`localgpu` 0.1.10: `unignore` discarded an unliftable entry in silence.**
  `.git`, `.localgpu` and `node_modules` are a floor `unignore` cannot lift, and
  that is right — but `load_config` enforced it with
  `set(unignore) - UNLIFTABLE_IGNORE`, which drops the entry and says nothing. A
  user who wrote `"unignore": [".git"]` got no error, no warning, and no effect,
  and would reasonably go hunting their own config for a typo that was never
  there. It now raises `ConfigError` naming the refused entries and saying why
  each one is a mistake rather than a preference. The floor is unchanged; only
  how it says no. Sabotage-proven: reverting to the silent drop turns both floor
  tests red.

- **`scripts/install-prerequisites.ps1` - `Format-PickerLine` reserved one
  character for a three-character `...` ellipsis, returning `Width + 2` on
  every clipped line.** Measured before the fix: `Width=20 -> 22`,
  `Width=40 -> 42`, `Width=80 -> 82`. The keys/hint lines are called with
  `$winW - 1`, so an 80-column console emitted 81 characters and wrapped,
  desyncing the cursor-up redraw the picker's own comment warns about. The
  bash twin's `pick_fit` was already correct (a 1-character `…`, reserving
  1); `.ps1` now reserves 3 for `...` instead of switching to the Unicode
  ellipsis, keeping the file's existing ASCII-only convention (its keys line
  already spells out `Up/Down` rather than using bash's arrow glyphs) - the
  fix is that the returned length no longer exceeds `Width`, not which
  ellipsis is used.

  The title-underline line in both flavours sized its dash count from the
  **unclipped** title (`${#PICK_TITLE}` in `.sh`, `$Title.Length` in `.ps1`)
  instead of the fitted one, so a long title produced a dash line far wider
  than the console and wrapped independently of the label-clipping fix
  above. Both now size the dashes from the title text actually returned by
  the fitter. `.ps1` also had no width floor at all - `Get-PickerConsole`
  returns raw `[Console]::WindowWidth`, and only the label width had a
  floor - so a narrow window could wrap the underline regardless; it now
  floors at 40, matching bash's `term_cols()`.

- **localgpu 0.1.7 -> 0.1.8: a security review found the indexer had no
  automatic defence against embedding secrets.** `DEFAULT_IGNORE` covered
  `.git`, VCS directories, build/dependency directories and binary
  extensions, but no `.env`, no credential or key patterns, and it never
  consulted a project's own `.gitignore`. Because the indexer embeds file
  *contents* into an on-disk vector store, a `.env` or private key not
  excluded by name got a second, less-guarded copy written to disk - one a
  later release cannot undo, since the embedding is already there. Two
  changes, both dependency-free (this package stays standard-library-only
  except numpy):

  `DEFAULT_IGNORE` in `mcp/config.py` now also excludes `.env` and its
  dotted variants (`.env.*` - matching the family, not the bare
  "env.production" some tools use instead, which cannot be told apart from
  an ordinary filename by name alone), `*.pem`, `*.key`, `*.p12`, `*.pfx`,
  `id_rsa*` and `credentials.json`.

  `iter_files`/`is_ignored` in `mcp/indexer.py` now honour a `.gitignore`
  found directly under the indexed root, in a documented subset: comments
  and blank lines skipped, a leading `/` anchors a pattern to that root
  (matched only against the full relative path, never as a bare name or an
  interior segment), `**/`/`*`/`?`/`[...]` pass straight to `fnmatch`, and a
  trailing `/` is treated like no trailing `/` at all. **Not supported:
  negation (`!pattern`) is silently dropped rather than mis-applied, and
  nested `.gitignore` files below the indexed root are not read.**

  `mcp/_test/test_secrets.py` builds a fixture repo with a `.env`, a
  `*.pem`, a file excluded only via `.gitignore`, and an ordinary source
  file, then asserts on the *stored chunk text* fed to the embedder - not
  merely on which files got indexed - since content reaching the vector
  store is the actual risk. Sabotage-tested: removing the `.env` pattern
  and disabling the `.gitignore` handling each turned this test red on the
  exact secret named in the assertion, independently. 227 -> 228 tests;
  `_verify/smoke.sh` stayed 10/10.

- **localgpu 0.1.6 -> 0.1.7: three more defects, found by a reviewer running
  mutation tests against `anthropic_proxy.py` rather than reading it.**

  **The context-window guard could fail open.** `resolve_num_ctx` folded "the
  model really has this context window" and "the probe to find out failed"
  into the same fallback number, and the caller cached whichever one it got
  as if both were equally trustworthy. One slow `/api/show` probe - Ollama
  loading another model, a cold start - pinned `DEFAULT_NUM_CTX` (32768) for
  the rest of the process even against a model whose real window was 8192,
  with every later request's budget computed from the wrong number and no
  log line to say so. That is the exact silent-truncation bug this module
  exists to prevent, reinstated by a network blip. `_probe_num_ctx` now
  returns `None` on any failure instead of guessing a number, and only a
  successful probe is cached — a failed one falls back for that one request
  only and is retried, with a verbose-gated log line, on the next.

  **The context guard measured base64 that would never be sent.**
  `check_fits_context` estimated the request's size from the untranslated
  Anthropic body, where a pasted image is still full base64; what actually
  reaches Ollama is a ~30-character placeholder (`_blocks_to_text` replaces
  every image block before translation). A 100 KB image estimated roughly
  44,500 tokens against the ~29 the model would actually see, so the guard
  refused a turn its own module docstring promises degrades gracefully
  instead. `estimate_prompt_tokens` now measures the translated
  (`to_ollama_messages`/`to_ollama_tools`) form.

  **The same estimator over-counted non-English text.** `json.dumps` defaults
  to `ensure_ascii=True`, escaping every CJK character as a six-character
  `\uXXXX` sequence before the count was ever divided down — 4000 CJK
  characters estimated roughly 8,010 tokens, refusing an ordinary non-English
  conversation at a fraction of the model's real capacity.
  `estimate_prompt_tokens` now serializes with `ensure_ascii=False`.
  `_CHARS_PER_TOKEN_ESTIMATE` (3, deliberately conservative for dense code)
  was left untouched — a prior attempt at this file changed the divisor alone
  and made both over-counts worse instead of fixing which bytes were counted.

  Every fix carries a regression test sabotaged individually: reverted,
  confirmed red against the exact numbers above, restored, confirmed green.
  Two existing tests were hollow in a way an independent reviewer proved by
  running them against a `resolve_num_ctx` that was nothing but
  `return default` — `test_num_ctx_is_auto_detected_end_to_end`'s fixture
  advertised the same context length as `DEFAULT_NUM_CTX`, so it passed
  whether or not the probe ran at all; its fixture now advertises a distinct
  8192. 223 -> 227 tests; `_verify/smoke.sh` stayed 10/10.

- **localgpu 0.1.2 -> 0.1.4: two independent reviewers found 1 BLOCK and 18
  FIX/NIT in code that had already passed 175 unit tests and 9 smoke checks,
  and a second pass over the fix found 6 more in the failure paths it added.**
  Codex (OpenAI) and Copilot pinned to kimi-k3 (Moonshot) each reviewed the
  branch from an identical prompt — both different families from the author,
  which is the point: five lanes and the main session, all Claude, had run
  green over defects neither this session's tests nor its own review caught.

  **The BLOCK.** `_strip_fence` discarded trailing text, so a fenced JSON
  example followed by disclaiming prose — including "Do not execute this
  example" — was promoted to a real `tool_use`. A model quoting documentation,
  or repeating a file it had just read, could cause a tool to actually run.
  Trailing text now disqualifies the promotion, with six must-not-fire tests
  and a control proving genuine calls still work.

  **The proxy** no longer reports failure as success: an explicit error chunk
  or a stream that simply stops now emits an SSE error event instead of
  `end_turn`. An upstream out-of-memory — likely on an 8 GB card — used to
  arrive as a normal, complete, truncated answer.

  **The index** gained the guard it was missing: `search_code` now checks the
  embed model, not just `refresh`. An index built with model A could be
  queried with model B's embeddings — same dimension, incompatible vector
  space, silently wrong ranking, no error.

  **Config is no longer type-blind.** `"ignore": "node_modules"` as a bare
  string used to iterate into the patterns n, o, d, e… and report success. It
  now names the key, the type found, and the fix.

  **Concurrency is now genuinely locked, not merely detected.** A
  per-vectors-file RLock serialises search/add/compact in-process, and an
  OS-level file lock wraps `index_refresh` so two Claude sessions cannot both
  compact the same index.

  One finding was investigated and rejected rather than fixed: the claim that
  `shutil.which("claude")` returns a `.cmd` that `subprocess.run` cannot
  launch. Verified on the development machine — `claude` resolves to a native
  `.EXE`, and even with a real `.cmd` shim, Python passes
  `lpApplicationName=NULL` so `CreateProcess` routes it to `cmd.exe`. That
  failure mode is Node's `child_process`, not Python's; adding `shell=True`
  would have introduced injection risk to fix nothing.

  Every fix carries a regression test sabotaged individually: reverted,
  confirmed red, restored, confirmed green. 175 -> 201 tests. The version bump
  itself needed a second commit — the fix commit changed `plugin/localgpu/**`
  without bumping the version, which `_verify/run-all.sh`'s drift check caught;
  `_verify/smoke.sh` stayed 10/10 regardless, since it omits that check on
  budget grounds.

  **A second Codex pass over the fixed code — not a fresh review of the
  original branch — found 6 more, all in failure paths written that same
  day.** The review was re-run exactly once rather than looped, and the
  pattern is worth naming: fixing 19 defects in fresh code opened new edges,
  which is what a second look is for.

  - **A regression from round 1's own fix.** Tracking tool calls off whichever
    chunk carries them meant the accumulator *assigned* instead of appending,
    so with a call split across two chunks only the last one executed. Now
    `.extend()`s. No amount of reviewing the original code would have found
    this; only reviewing the fix did.
  - **Malformed recovered arguments** (`{"name":"tool","arguments":"not
    json"}`) became a `tool_use` with `input: {}` — a tool running with no
    arguments is a different call, not a degraded one, so this is now
    rejected outright. The real Ollama `tool_calls` path still degrades to
    empty on purpose; it carries its own contract test for that.
  - **A mid-stream timeout wrote a second HTTP response into the
    already-chunked body**, corrupting the connection for anything reusing
    it. Sabotage reproduced it as a real client-side
    `http.client.IncompleteRead`, not a synthetic assertion.
  - **Silent, permanent data loss.** A file whose re-embed failed after
    tombstoning, then had its content restored, matched on stored hash and
    was skipped — leaving every chunk dead and the file unsearchable forever,
    with no error. A hash match is no longer treated as proof that live
    chunks exist.
  - **The embed-model guard was bypassable by its own precondition.** A
    failed *initial* refresh leaves no manifest, so "no manifest" read as "no
    mismatch," and a later same-width model was certified over mixed vectors.
    Absence now means "nothing built" only when the store is also empty.
  - **A Linux-only cross-process compaction race**, undocumented as a full
    fix because it cannot be reproduced on this Windows machine: a generation
    counter turns a silent wrong answer into a loud, retryable error instead.
    Its test is explicitly labelled a simulation.

  175 -> 207 tests across the two rounds. Bumped in `plugin.json`,
  `marketplace.json`, and `pyproject.toml`.

- **crew 0.15.3 - `claude-md-audit.sh` rejected the very heading it recommends.**
  `canon()` maps a heading to the concern it covers; six of its seven arms use a
  prefix wildcard (`where*`, `scope*`, `stop*`, `promotion*`, `reporting*`,
  `memory*`) but the commands arm was a bare `commands` with none. The script's own
  `label()` tells the user the canonical heading is
  `## Commands - build, test, verify, regression, promote`, which lowercases to
  `commands - build, ...` and matches neither `commands` nor `build*`. So the audit
  reported that section MISSING and listed it under `extra` in the same run, and a
  user who followed the recommendation could never make it pass. One character:
  `commands*`.

  The real fix is the test beside it. `skills/crew-setup/scripts/_test/round-trip.sh`
  feeds every `label()` output back through `canon()` and asserts it resolves to the
  concern it came from - the contract between the two functions, which nothing
  checked. It fails if fewer than seven concerns are examined, so a broken extraction
  cannot report green over zero cases. Sabotage-tested: reintroducing the missing
  wildcard turns it red.

- **`obsidian-vault` 0.3.0: `diagnose` printed a FAIL and exited 0.** A scoped
  run prints every port collision on the machine - which is the point of a wide
  diagnosis, since a collision the selected vault is not part of is often what
  explains its symptoms - but the exit code counted only the selected vaults. So
  `diagnose --vault memory` could print `[FAIL] port 27126 is claimed by ...` for
  two unrelated vaults and then exit 0, contradicting itself and the exit-code
  table in `doctor.md`.

  Neither obvious fix was right. Hiding the out-of-scope collision would delete
  the most useful line on the screen; counting it would tell someone who asked
  about one vault that their question failed because two others clash. So the
  label carries the scope instead: a collision involving the selection is
  `[FAIL]` and moves the exit code, one elsewhere on the machine is still
  printed as `[ELSEWHERE]`, names the vaults it belongs to, and does not. The
  `--json` output carries the same distinction as `in_scope`, so a consumer
  reading the collisions and the exit code cannot reach the contradiction
  either. An unscoped run is unchanged: every collision is in scope.

- **`obsidian-vault` 0.3.0: a mistyped `--port` became a working config for a
  port nobody chose.** `add-vault --port` accepted any integer and wrote it;
  a later read passed it through the config repairer, which substitutes the
  default port and carries on, so `217123` silently became `27123` and looked
  like it had worked. Both paths now ask one question, `port_in_range()`, and
  answer it differently on purpose: a value already written in a config is still
  repaired, because a hook that dies on a typo it did not make helps nobody,
  while a value being *accepted from a person* is rejected. Repairing input at
  the point of entry is what turns a typo into a silent wrong answer.

  The stale "installs it, enables it" claim also outlived the rename in one more
  place, `obsidian-setup/SKILL.md`. Grepped rather than spot-fixed; that was the
  only survivor, and it now states the manual download prerequisite and the
  reason for it.

- **`obsidian-vault` 0.3.0: `fix-ports --vault X` edited X's neighbour.** The
  same shape as writing to an unconfigured vault, one level up: `--vault` scoped
  which collisions to act on but never constrained which vault moved, so
  scoping to the vault holding the port wrote the *other* vault's `data.json`.
  Being in config is consent to be managed by this plugin; it is not consent to
  be edited by a command pointed at something else, and a scripted
  `fix-ports --vault memory --apply` in a hook never reads a plan first. Moving
  a vault the user did not name is now refused and names it, with the unscoped
  run as the way to actually fix the collision - refused rather than silently
  skipped, because the collision is real and the diagnosis just named it.

  The refusal also carries the field that actually collides. It hardcoded
  `port`, which the printer labels HTTPS, so a collision existing only on
  `insecurePort` was refused for an HTTPS change nobody had contemplated. Both
  refusal paths now derive the claimed keys the same way the move path does, so
  a vault claiming one port on both protocols is refused for both.

  A configured vault with no recorded path was also reported as one whose
  directory had been deleted: the reason was decided from a display string that
  is never empty, which made the no-path branch unreachable. It is decided from
  whether a path was found.

- **`obsidian-vault` 0.3.0: `fix-ports` could rewrite a vault nobody configured,
  and an empty selection reported success.** Fencing `--all` off from
  unconfigured vaults was done at the three commands that route through
  `select()`. `fix-ports` is the one acting command that does not - it goes
  straight from discovery into the planner - so it could still pick a
  discovered-but-unconfigured vault as the mover and write that vault's own
  `data.json`, a heavier write than the MCP config the earlier fix protected.

  It now moves only configured vaults, and a collision whose mover is
  unconfigured is **refused by name** rather than worked around. Silently
  choosing a different mover would hide a real conflict and relocate a vault
  that was not at fault, so the output says which vault has to `add-vault`
  first. `scan` still sees everything, because a diagnosis that cannot see the
  vault causing a collision cannot explain it, and `graph-health` reaches a
  vault only through a configured `layout` or an explicit `--vault`.

  Separately, filtering `--all` down to configured vaults could produce an empty
  selection that exited 0 - a configured vault whose directory was deleted,
  renamed, or sits on an unmounted drive is in config and not in discovery.
  Reporting success for work nobody did is the failure this file's exit codes
  exist to prevent, so every such vault is now named with its path and the
  reason, and keeps the exit non-zero.

  The `claude mcp get` parser also gained direct tests against real captured
  output, and now treats a redaction marker as *unknown* rather than as a key.
  As of 2026-09-05 this machine prints the token verbatim and no redaction
  occurs; the guard is insurance against a format change, because that failure
  would be silent and destructive - every run would rewrite a correct
  registration and nothing would look wrong.

- **`obsidian-vault` 0.3.0: a rotated key was never noticed, and `--all` reached
  vaults nobody had configured.** `register` compared the registered URL to the
  target and reported "already registered" when they matched. `claude mcp list`
  prints name and URL only, so that was evidence about the URL and nothing else:
  a rotated `apiKey` left the URL identical and the bridge permanently
  unauthenticated, and the command documented as the fix for exactly that
  reported success and did nothing, forever. `claude mcp get` does print the
  stored header, so the key is now read back and compared. When it cannot be
  read, the registration is rebuilt rather than assumed current - re-registering
  a correct server costs one CLI call, and assuming a stale one is correct is
  the failure this command exists to fix.

  Separately, `--all` acted on every vault discovered on the machine rather than
  every vault in config, so `register --all --apply` would write a user-scope MCP
  server for a vault the user had never put under this plugin, and
  `enable-plugin --all --apply` would edit its `community-plugins.json`. Both
  now stop at the config. Discovery itself is unchanged and deliberately wide -
  an unconfigured vault can still be the one causing a port collision, and a
  diagnosis that cannot see it cannot explain it - but naming a vault with
  `--vault` is consent and sharing a disk is not. Anything skipped is named in
  the output rather than quietly dropped.

  The profile detector's structural fallback also stopped asserting two things
  it had not checked. Reaching that branch means both authored signals fell
  *under* their thresholds, and under is not zero - so a vault with one enabled
  authored plugin was told "no plugin from the authored set is enabled", after
  which `optimize` could propose disabling the Dataview that renders its notes.
  It now reports the counts it measured and marks the verdict unconfident when
  any authored plugin is on.

- **`obsidian-vault` 0.3.0: the install step did not install, and setup could
  not name a new vault.** `install-plugin` enabled a plugin whose files were
  already on disk. On a fresh vault - its primary scenario - it printed manual
  UI steps and stopped, while `/obsidian-vault:install` and `init` presented it
  as *the* installation step and everything downstream assumed it had happened.

  It is now `enable-plugin`, which is what it does, with `install-plugin` kept
  as an alias so nothing breaks mid-flight. The download stays a stated manual
  prerequisite rather than becoming a fetch, and that is deliberate: an Obsidian
  community plugin is unsigned `main.js` on a GitHub release, with no publisher
  signature and no authoritative checksum, and it runs with Obsidian's own
  privileges over every note in the vault. There is nothing to verify a download
  against, and writing unverifiable executable code into someone's editor is not
  an install worth automating. A vault missing the bridge now reports `NOT
  DOWNLOADED`, the exact route through Obsidian's own installer, and - for the
  Local REST API specifically - that the vault is invisible to Claude until it
  is done.

  Separately, a vault whose chosen name differed from its directory basename
  could not be set up at all. An unconfigured vault is discovered under its
  folder name, and the config entry that would make the chosen name resolvable
  was written at the *end* of setup - after the enable, port and registration
  steps had already tried to address it and failed with "unknown vault". The new
  `add-vault` subcommand writes that entry, and `init` now runs it first. It
  merges rather than replaces, and carries a legacy `vaultPath` config across
  instead of silently unconfiguring the vault that was already working. Both produce a silent port, so both read as "down" — and one vault's
  window exiting was indistinguishable from an unrelated port collision. The
  hook now separates `NOT OPEN`, `NO SERVER`, `NOT ANSWERING YET` and `UP`. The
  third is the one that was costing time: on a large vault a socket that accepts
  without answering means indexing is still running, which is not a fault to
  chase.

  There is now a fifth verdict, `DOWN, CAUSE NOT DETERMINED`, and it is the
  point of the change rather than a fallback. The previous diagnostic named a
  cause with confidence and was wrong, sending its reader to the one file that
  was already correct — a confident wrong answer costs more than an honest gap.
  Guidance is derived only from evidence the script actually checked; where two
  causes cannot be separated it says so and names the check that would separate
  them; where a check could not run it says that rather than omitting it.

  Process attribution is honest about its own limits. No Obsidian process names
  its vault on any platform, so command lines are useless everywhere. Window
  titles name it on Windows and are read in-process. On macOS and Linux the
  script reports presence only and declares attribution undetermined rather than
  guessing, and two vaults sharing a folder name are undetermined rather than a
  coin flip.

- **`obsidian-vault` 0.2.0: the plugin can repair a vault bridge instead of
  describing how to.** Its connection handling was prose — `bridge_status.py`
  probed and reported, the vault guard and capture hooks ran, and everything
  else was a command file telling the session what to type. Nothing restarted a
  server, nothing wrote `data.json`, and the codegraphs vault's own health was
  never checked, only whether `graphify` existed.

  `hooks/scripts/vault_ops.py` is the action layer: `scan`, `diagnose`,
  `add-vault`, `fix-ports`, `reload`, `register`, `enable-plugin` and
  `graph-health`.
  Dry-run by default, writing only under `--apply`, `--json` on the read-only
  subcommands, and exit 0 healthy, 1 problems found, 2 usage error.
  `/obsidian-vault:repair` and `/obsidian-vault:install` are new and drive it;
  `/obsidian-vault:doctor` stays read-only and now enforces that through its
  tool list rather than asserting it in prose; `/obsidian-vault:graph` gained
  the `graph-health` check. Every hand-typed procedure the script replaced —
  the registry read, the plugin install, the `claude mcp add` block, the
  end-to-end curl — was deleted from `init`, the `obsidian-setup` skill and the
  plugin README rather than left standing beside it.

- **Eight crew agents cited a skill they had no way to load.** Naming a skill in
  an agent's prose does not load it; the agent needs `skills:` frontmatter or the
  `Skill` tool, and not one crew agent had either. So `browser-tester`,
  `qa-reviewer` and `smoke-author` pointed at `crew-verification`, `pm` at
  `crew-pm`, `planner` at `crew-diagrams` and `crew-providers`, `scribe` at
  `crew-context` and `crew-memory`, `infrastructure-architect` at `crew-cloud`
  and `crew-terraform`, and `docs-writer` at `crew-diagrams` and the
  `crew-house-style` skill that defines its whole new export behaviour — and
  every one of those references was decoration. Five of the eight predate this
  release.

  This is the same defect as the `explorer` write order fixed in 0.14.7: an
  instruction with no route to execute, which fails silently and looks like the
  model ignoring its brief. A reviewer found the `docs-writer` instance; the
  ripple check across all fourteen agents found the other seven.

- **`crew` 0.15.1: three new agents, a house-style skill, and a documentation
  role that stops handing people raw markdown.**

  `infrastructure-architect` designs and reviews AWS network and account
  architecture — VPC and CIDR planning that survives growth, routing and egress,
  Transit Gateway against peering against Direct Connect and when each is wrong,
  security groups against NACLs, Route 53 split-horizon, ingress, landing-zone
  shape, failure domains, and cost as a design constraint rather than an
  afterthought. It is read-only and forbids `apply` in both its description and
  its body: it holds `Bash` for `terraform validate` and describe-only calls, and
  routes authoring to `crew:developer` and `crew-terraform`. The reference corpus
  has an Azure equivalent and no AWS one, so this is written from scratch.

  `scribe` keeps the durable record — ADRs, `CHANGELOG` entries, handoff notes,
  and what was tried and rejected. Its seam against `docs-writer` is what a
  reader can recover from source: `docs-writer` documents what the code does,
  `scribe` records the alternatives that lost, the constraint that forced the
  choice, and the condition that would reopen it. It never rewrites an existing
  ADR or a released changelog section; corrections are new entries that
  supersede, and say so.

  `researcher` answers only what lives outside this repository — library and SDK
  behaviour, version and migration questions, vendor limits, standards, prior
  art. The seam is enforced by its tool set rather than by prose: it holds web
  and Context7 tools and no `Grep`, because anything inside the repo belongs to
  `explorer` or `analyst`. Every claim carries its source, and it refuses to
  answer a version, limit or API-surface question from memory, since those rot.

  `crew-house-style` owns house style for a document handed to a human — palette,
  heading hierarchy, capitalization, and whether the artifact should be PDF,
  DOCX, HTML or plain markdown. It deliberately owns no generation: it routes to
  `anthropic-office-skills:docx`/`pdf`/`pptx`, `ppt-master` and `visio-diagrams`,
  and where none of those is installed it falls back to markdown and says so in
  the handoff rather than improvising a generator.

  `docs-writer` gained the directive behind that skill and the return contract it
  never had. A document a human consumes as a finished artifact ships as HTML,
  DOCX or PDF; repo-native files the repo itself reads — `CHANGELOG.md`,
  `README.md`, `CLAUDE.md`, ADRs — stay markdown. The export is **additional**:
  the `docs/*.md` deliverables remain the source of truth, so everything that
  reads those paths keeps reading them. It also stops claiming `docs/adr/`, which
  is now `scribe`'s.

  `dba` covered no engine in particular; it now names four. SQL Server, MySQL and
  PostgreSQL are separated where they genuinely differ — what a DDL statement
  locks, whether a failed migration leaves the database half-applied, which index
  types exist, how each is asked for a plan — and stated once where they agree.
  DynamoDB gets its own section rather than a row, because the review questions
  are not the relational ones: partition key design and hot partitions, access
  patterns preceding the schema, an LSI that cannot be added after creation,
  eventual consistency on GSI reads, and why "add an index later" is a relational
  habit that does not transfer.

  `planner` gained a return contract, a "what you never do" section, and the
  failure modes it was not naming: designing for a scale that does not exist,
  the abstraction added for a second call site, reversibility as the tiebreak
  when two options are close, and stating which assumption, if wrong, invalidates
  the design. It also has to say when the proposed approach is fine and it has
  nothing to add — a second opinion that always finds something is noise.

  The three new agents ship **without a tier**. They dispatch normally when
  named, but they are not rows in `crew-scaling`'s tier table, so `/crew:scale`
  will not propose them and `/crew:pm` will not onboard them from evidence.

- **`UPDATE.md` per component directory, with a generator behind it.**
  `plugin/`, `skills/` and `mcp-servers/` each own an `UPDATE.md` listing what is
  newly *possible* there, newest first — the counterpart to this file, which
  records everything including fixes. Each one is mirrored into its own
  `README.md` and into the repository `README.md` between
  `<!-- BEGIN <dir>/UPDATE.md -->` markers, reusing the convention the existing
  `skills/README.md` and `plugin/README.md` mirror blocks already use.

  Those existing blocks are hand-maintained, which is why they drift.
  `scripts/sync-updates.py` regenerates every `UPDATE` block from its source and
  takes `--check`, which writes nothing and exits 1 naming the stale files. It is
  dependency-free python3. Two rules fall out of rendering one text at two
  directory depths and the script enforces both: headings are demoted one level,
  because a mirrored section always sits under a heading its host supplies, and
  the mirrored sections carry no relative links — `../CHANGELOG.md` is correct in
  at most one of the two hosts, so links stay in the preamble above the first
  `##` heading, which is never mirrored.

### Fixed

- **`crew` 0.15.0: eight agents cited a skill they had no way to load.** An
  agent that names a `crew` skill does not thereby load it — that needs `skills:`
  frontmatter — so the instruction silently did not happen, on every run, with
  nothing in the transcript to say a step had been skipped. Codex caught it on
  `docs-writer`, which the same release had just pointed at `crew-house-style`;
  the ripple check found it was systemic. `browser-tester`, `docs-writer`,
  `infrastructure-architect`, `planner`, `pm`, `qa-reviewer`, `scribe` and
  `smoke-author` now declare what they cite, five of them fixing a defect that
  predates this release.

  This is the same defect class as 0.14.7's `explorer` bug, one layer up: an
  agent told to do something the harness gives it no route to do. The tools an
  agent holds and the skills it declares are both part of whether an instruction
  in its prose can execute at all, and neither is checked by anything that reads
  the file.

- **`crew` 0.14.7: two shipped agents told an agent to do something it could not
  do, and gated a safety rail on the one path where it matters.**

  `explorer.md` declared `tools: Read, Grep, Glob` and then ordered the agent to
  "append durable findings to memory" — no `Write`, no `Edit`, no `Bash`, so no
  route to do it at all. Every explorer run silently dropped the step, and step
  1's "check your project memory first" read a store that nothing ever wrote: a
  loop that never closed. The agent now returns the durable part in a
  `**Durable:**` block for its caller to persist, and the prose says *why* it
  cannot write, so the next reader does not "fix" this by adding `Bash` to a
  deliberately read-only investigator. Step 1 now names `.crew/codemap/` and
  carries `crew-memory`'s index-first rule and `anchor:` check, instead of
  inviting the directory sweep that skill warns costs 40k tokens to answer a
  400-token question.

  `pm.md` said "Everything below the next heading applies **only under `act`**"
  and then placed three `report-only` instructions below it — the state read on
  "every invocation", the plan-as-deliverable rule, and "Under `report-only`,
  the report *is* the deliverable". The serious half is that the three guards in
  `## Acting` were gated off too: the user's priority outranking the PM's,
  **removal and deletion needing an explicit yes**, and announcing an expensive
  run. Because an explicit instruction can make the PM act in a `report-only`
  repo, the rails were switched off on exactly the path where nobody had
  reviewed a config to decide what the PM may destroy. The gate now covers
  dispatching and nothing else, and says so.

  `## Reading state` also moves above `## Authority`, closing a circularity: the
  PM was told to read `pm.authority` first, while the instruction to run
  `crew_state.py` — which is how it learns that value — sat below the gate keyed
  on it.

  Repo hygiene in the same change: `.crew/` is now gitignored (it holds
  machine-specific absolute vault paths and a `pm.authority` trust decision no
  clone should inherit), as is `.github/copilot/` (the Copilot CLI writes it on
  `--model` and it silently shadows crew's own `qa.copilot.model`). The
  `graphify-out/` rule became an allowlist after a Codex review found the
  denylist missed four of the eight artifacts a build produces.

  Gitignoring `.crew/` surfaced a test that had been passing for the wrong
  reason. `test_pm_brief.py::test_main_exits_zero_on_garbage_stdin` asserts
  that unparseable stdin produces no output, but unparseable stdin carries no
  `cwd`, so `main` falls back to the process directory — and running the suite
  from a checkout that has its own `.crew/` made that a real crew repo with
  real triggers, so the brief was correctly non-empty and the test failed. It
  passed in CI only because nothing there is checked out with a `.crew/`. Both
  stdin-fallback tests now `monkeypatch.chdir(tmp_path)`, so they assert
  "garbage in, nothing out" rather than "whoever ran me happened to stand
  somewhere quiet". 410 passed, 1 skipped.

- **`crew` 0.14.6: the re-review caught that 0.14.5 fixed a stale model name in
  one file and left it in four.** Re-running the Copilot reviewer on the fixed diff
  confirmed all seven original findings closed, then found the ripple I had not:
  `gemini-3.1-pro-preview` still stood in `README.md`, `crew-setup/SKILL.md`,
  `providers.sh` and `/crew:model`'s own worked example, all recommending a model
  that fails at startup. Every occurrence now names `gemini-3.7-flash` and says to
  verify the name rather than trust the doc.

  Two more real BLOCKs, both in code I had touched that same pass:

  - `BASE=$(git merge-base HEAD "$(git symbolic-ref ... | sed ... || echo main)")`
    never falls back. `||` binds to the whole pipeline and `sed` exits 0 even when
    `symbolic-ref` failed, so a clone without `refs/remotes/origin/HEAD` hands
    `merge-base` an empty string. Now branches on the ref itself; verified to
    resolve `main` in both cases where the old form gave `""`.
  - `.get(key, {})` does not defend against a key that is **present and null** -
    it returns `None`, and `.get` on `None` is an `AttributeError`. A config with
    `"codex": null` crashed the extraction. Now `or {}` at every hop.

  Also: `qa.order` absent made `/crew:model` report zero candidates and "no
  independent reviewer" for a setup that reviews fine; `phases.md` told setup to
  write `none` into `qa.provider`/`dev.provider`, which `/crew:model` rejects and
  `/crew:review` cannot resolve to any rung; and three files still advertised 21
  slash commands against an actual 23.

  Rejected: the duplicate `### Fixed` heading in this changelog. One heading per
  entry is this file's existing convention, 42 of them and counting.
### Fixed

- **`crew` 0.14.5: the first real cross-family QA review found seven defects in
  0.14.0-0.14.4, and this fixes them.** Copilot on `gemini-3.7-flash` reviewed the
  branch - the first time crew's Copilot rung has ever run end to end - and caught
  what four passes of self-review did not:

  - **`review.md` crashed on the configs it was written for.** Step 2 read
    `["qa"]["codex"]` by direct index, so any config predating those sub-blocks died
    with `KeyError: 'codex'` before the review started. Reproduced against this
    repo's own `.crew/config.json`. Now `.get()` at every level, and verified to
    still *read* values rather than merely stop crashing.
  - **Steps 2a/2b `cat` a prompt file that was only written after step 2c.** The
    prompt is now written in step 2, before any provider block reads it, with an
    unquoted heredoc so `$SCRATCH` expands - a reviewer handed the literal string
    `$SCRATCH/diff.txt` opens nothing and reports CLEAN on a file it never read.
  - **Step 1 told `/crew:review` to stop when no independent reviewer survives,
    contradicting `README.md`, `agents/pm.md` and `crew-pm`,** which all document
    `qa-reviewer` as the fallback. Resolved toward the documented behaviour: it
    runs and is labelled same-family, and is never recorded as independent.
  - **The Kimi recipe defined a Codex provider without selecting it.** Missing the
    top-level `model_provider = "moonshot"`, the call goes to OpenAI with a Kimi
    model name - after the diff is uploaded.
  - **`/crew:model` reported the wrong reason for a real condition.** An unset
    Copilot model collapsed to `"?"` on both sides of the family comparison, so
    `dev.provider: copilot` with no model pinned reported `BARRED` instead of
    `SKIPPED`. Now `None`, which never compares equal to itself here.
  - Duplicate `Step 2c` heading; "there is no API for this, read or write" sitting
    eight lines below the command that reads it; `21 slash commands` in the
    marketplace description when there are 23.

  **The model table recommended a model that does not exist.**
  `gemini-3.1-pro-preview` and `mai-code-1-flash` both fail with `Model "<name>"
  from --model flag is not available`; `gemini-3.7-flash` is what works. The
  section also sent you to `copilot help` to list models, and no such listing
  exists - `--model list` is rejected like any other bad name. Replaced with two
  methods that work: read `~/.copilot/logs/*.log`, or pass a candidate and read the
  rejection, which fails at startup before any diff is sent.

  One finding was rejected: `--deny-tool write` is correct. `copilot help
  permissions` documents `write(path?)` as matching "tools that create and modify
  files", and the suggested `edit`/`create` tool names do not exist.
### Fixed

- **`crew` 0.14.4: the 421 guidance shipped a guess as a cause, and its advice was
  wrong.** 0.14.3 told you a `421 Misdirected Request` meant GitHub was
  mid-propagation on your seat SKU, and to wait 15-30 minutes. The propagation
  observation was real - one account returned four entitlement states in eleven
  minutes, occasionally pairing a SKU with the wrong API host - but it was
  correlation reported as cause, and the remedy was then falsified: ten consecutive
  failures across forty minutes.

  One thing is genuinely established and is now all the skill claims: a 421 means
  the **policy gate passed**, since it replaces `Access denied by policy settings`
  rather than appearing with it. The cause is recorded as unknown.

  The section now also lists what was ruled out by test rather than by reasoning -
  fresh `copilot login`, deleting the user cache, token env vars, proxy and TLS
  settings, a CLI upgrade, pinning `--model` to skip the model-list fetch, and
  retrying - so the next person does not re-run forty minutes of the same
  experiments. The action is a support ticket with a Request ID and the SKU/host
  rows, and leaving `qa.copilot.model` unset meanwhile: a permanently-erroring
  provider is worse than an absent one.

### Changed

- **`crew` 0.14.3: enabling Copilot is a three-gate sequence, and crew now says
  so before you pin a model.** Setting `qa.copilot.model` is the switch that turns
  the Copilot rung on. While it is `null`, `/crew:review` skips Copilot and
  announces the skip once per review; setting it on a Copilot that does not
  actually work converts that clean message into a recurring error on a path the
  user now believes is covered. The docs treated "install the CLI" as setup, which
  clears exactly one of the three gates.

  The gates, in order, because each one's failure is invisible until the previous
  one passes: (1) the CLI must be allowed by **account policy** - readable at
  `orgs/<org>/copilot/billing` -> `cli`, and settable only in a browser, since
  Copilot exposes no policy write in REST or GraphQL; (2) the CLI must hold its
  **own** token from `copilot login`, because a `GH_TOKEN`/`GITHUB_TOKEN`/
  `COPILOT_GITHUB_TOKEN` silently outranks it; (3) one real call must return, judged
  by **exit code**.

  Gates 1 and 2 emit byte-identical errors, which is why the order is the fix
  rather than the checklist. `providers.sh` now reports gate 2 from
  `~/.copilot/config.json` and warns when a borrowed token would override it - both
  free, no API call. Also documents `421 Misdirected Request` as *progress*: it
  means the policy gate passed and the seat SKU is mid-propagation, handing the CLI
  a `business` host for an `enterprise` plan. Waiting is the fix; reinstalling is
  not.

### Fixed

- **`crew` 0.14.2: the documented Kimi-through-Codex recipe could not have
  worked.** `crew-providers` shipped a `[model_providers.moonshot]` block with no
  `wire_api`, written when Codex still spoke `chat/completions`. OpenAI deprecated
  that protocol in December 2025 and removed it in early 2026; on Codex 0.146.0
  `wire_api = "chat"` is a hard config-load error, not a fallback. The block now
  sets `wire_api = "responses"`.

  This looked like it killed the route, since Moonshot is normally described as a
  chat/completions API. It does not - Moonshot serves `/v1/responses` as well,
  confirmed by probe: `/v1/responses` and `/v1/chat/completions` both return 401
  while `/v1/models` returns 404, and that 404 is the control that makes the 401s
  mean something rather than being a gateway rejecting everything.

  Also documents the `Model metadata ... not found. Defaulting to fallback
  metadata` warning, because a wrong model name *warns and keeps going* rather
  than failing - Codex then guesses the context window. That is the review-shaped
  failure this skill exists to catch, so it is now named in the skill.

### Added

- **`crew` 0.14.1: a `verify.json` rule can dispatch any installed subagent, not
  just crew's eleven.** The `agents` key already pulled specialists into
  `/crew:review` on a path match; it was limited to crew's own roles, which meant
  a machine carrying two dozen domain specialists from other marketplaces could
  not reach any of them from the gate. A bare name now resolves to crew's role
  first (`security` -> `crew:security`) and then to any other installed agent;
  namespace it when both exist and you mean the other one.

  The value is dispatch *from evidence*: a change under `iam/` pulls in the IAM
  auditor every time, rather than when somebody remembers that agent exists.

  The safeguard is the load-bearing half. `.crew/verify.json` is committed and
  travels between machines, so a rule naming an agent the author has and a
  teammate does not would quietly review less on the second machine while
  producing output indistinguishable from a full pass - the same failure class as
  a QA provider that authenticates and then returns nothing. A named-but-missing
  agent is therefore reported as a gap and logged to `.crew/metrics.md`, so
  `/crew:scale` can see that a rule has asked for something eleven times and never
  got it.

- **`crew` 0.14.0: QA and implementation become a provider table, and the family
  that wrote the code is barred from reviewing it.** `qa` grows an `order`
  (`codex`, `copilot`, `claude`) plus a per-provider block, and a new `dev` block
  lets Codex or Copilot write the change instead of `crew:developer`. Both are
  additive: `merge_defaults` recurses one level, so an existing `schema: 2` config
  picks up every new key with no migration and no schema bump.

  GitHub Copilot is worth the rung because it is a gateway to families nothing
  else here reaches - `gemini-*` (Google) and `mai-*` (Microsoft MAI). It is
  **skipped unless `qa.copilot.model` is pinned away from `claude-*`**, because
  Copilot's own default is `claude-sonnet-4.6`: an unpinned Copilot would be a
  same-family review presented as an independent one, which is worse than the
  `qa-reviewer` fallback that at least announces its own weakness.

  The interlock is the load-bearing part. `/crew:review` reads `dev.provider` and
  strikes the author's family from the walk at review time, without consulting
  `qa.order` - and stops rather than reviewing when nothing independent is left.

  `qa.codex.model` and `qa.codex.reasoningEffort` close a gap where crew hardcoded
  nothing for Codex while its own providers skill said not to hardcode model
  names. Both default to `null`, meaning "pass no flag", so an upgraded repo
  invokes exactly the command it did before. `reasoningEffort` takes `none`,
  `minimal`, `low`, `medium`, `high`, `xhigh`, `max`; a wrong value is rejected by
  Codex with a 400 naming the supported set rather than silently ignored.

- **`crew` 0.14.0: `/crew:model` and `/crew:roster`.** `/crew:model` reports which
  model backs each role and probes that it answers, then sets `qa.*` / `dev.*`
  keys with validation - refusing a `claude-*` Copilot reviewer and an invalid
  reasoning effort, while deliberately *not* validating model names against an
  allowlist, since catalogs churn. `/crew:roster` lists every role, which are
  active in this repo versus available but off, and which are backed by an
  external provider and so invisible in the agents table.

- **`crew` 0.12.4: an SOP and a SOC 2 policy for pre-deployment security
  review.** Two cross-linked documents under `plugin/crew/docs/`. The rule they
  state is that no website reaches production without both a peer security
  review and an external vulnerability scan of the deployed hostname - the two
  are not interchangeable, because the review reads the change while the scan
  tests what is actually serving, and a reviewed change can still deploy onto a
  host running an end-of-life web server.

  Both are marked DRAFT with no owner, approver or effective date, and the
  policy says outright that it is a template until those exist. The Trust
  Services Criteria mapping is labelled provisional and says to confirm it with
  the auditor. A policy is evidence because a named person approved it on a
  date; shipping one that implies otherwise is the first thing an auditor pulls
  on.

  Three constraints are written in because they were learned rather than
  reasoned about: scan the public hostname from outside rather than the origin,
  since an edge that terminates TLS makes the origin's configuration invisible
  to the internet; never commit raw scanner JSONL, which embeds full HTTP
  responses and has twice captured live session tokens that keyword secret
  scanning failed to detect; and state the limits alongside the result, because
  a clean signature-based scan oversold is worse than no scan.

  Reports are published to `<project>/docs/security/` in a monolith or
  `docs/security/` at the root of a single-project repository, date-stamped so a
  later run cannot overwrite the comparison point.

- **`gizmoduck` 0.2.1: reports itemise Critical/High/Medium and count the rest,
  and rendering moves into its own module.** A scan of a healthy site returned 1
  Medium and 42 Info, and the report listed all 43 — so the one finding somebody
  was expected to fix sat underneath forty-two version banners, DNS records and
  "a form exists". Low and Info are now counted in the severity table and
  dropped. The table labels each row `itemised` or `count only` and a line
  states how many were suppressed, so the omission is visible rather than
  looking like truncation.

  `--min-severity` now raises that floor and never lowers it: `high` reports
  High and Critical, while `info` gets the counts it implies rather than pages
  of noise. `report`'s per-command default moved High -> Medium to match, which
  is the bug the first cut shipped with — every test passed `--min-severity
  info` explicitly, so the default path was never exercised and the Medium was
  silently suppressed. Running it with no flags is what caught it. `tickets`
  deliberately stays at High: a Medium is worth reading without being worth
  auto-opening a ticket for.

  New `scripts/report_template.py` owns HTML/PDF rendering; `gizmoduck.py` keeps
  the data prep and delegates. Its module docstring carries the constraint that
  matters: **wkhtmltopdf renders through Qt WebKit 4.8**, which predates
  flexbox, grid and custom properties and silently produces an unstyled column
  instead of an error, so every layout is built from tables and verified in the
  PDF rather than a browser. Findings are numbered in severity order, since that
  number is the remediation order.

  `dedupe()` also gained `raw_count` alongside `instances`. `instances` counts
  distinct locations, not detections — `http-missing-security-headers` fires
  once per absent header — so a summary reading 42 Info beside rows summing to
  20 looked like a rendering fault. Both numbers are now reported and labelled.
  Additive: `tickets` and `diff` read `instances` and are unchanged.

### Fixed

- **`crew` 0.13.1: the command guard's git rules were bypassed by every option
  form.** `guard.sh` and `guard.ps1` both required the subcommand to sit
  immediately after `git`, so `git -C <path> push --force`, `git -c a=b push
  -f` and `git --git-dir=... reset --hard` walked past the force-push,
  `reset --hard` and `clean -f` rules alike — which is exactly the spelling a
  worktree-per-agent setup types. Both flavours now swallow any run of leading
  git options between `git` and the subcommand, and `git push origin +main`
  (a force push carrying no `--force` token) blocks too. `--follow-tags`,
  `git -C <path> status`, `git clean -n` and `git stash push` stay allowed.

  `guard.ps1` had no test coverage at all — the same asymmetry
  `test_gates_powershell.py` exists for. `plugin/crew/tests/test_guard_powershell.py`
  now runs the same must-block/must-allow matrix against it. Both suites were
  sabotage-tested: restoring the old adjacent-only patterns turns
  `run-tests.sh` red on 15 cases and the new file red on 8, each naming the
  command that got through.

- **`crew` 0.12.3: the Stop hook's verify gate ran twice on any machine with
  both shells installed.** `hooks.json` registers `verify-gate.sh` AND
  `verify-gate.ps1` for every Stop, so a single-shell machine always gets
  exactly one gate run - that is the whole reason both are registered. Most
  Windows dev boxes have both, since Git for Windows ships `bash.exe`
  alongside native PowerShell, so both ran the full smoke/verify gate on every
  turn: duplicate work up to the 600s hook timeout, and two processes racing
  on the same scratch files.

  Statically deferring to one flavour was rejected. `Resolve-CrewBash` finds a
  real `bash.exe` on nearly every Windows box, so "defer when bash exists"
  would leave `verify-gate.ps1` permanently unreachable and its incident and
  config lanes untestable. Each script now takes a short-lived per-turn lock
  at `.crew/.verify-gate.lock` immediately before the expensive part;
  whichever process gets there first does the real work and the other backs
  off, and the winner's exit code still governs the turn.

  **The lock records a timestamp, never a PID.** A PID-based first draft of
  this fix was a no-op in the one situation the lock exists for. The two
  flavours do not share a PID namespace on Windows - `$PID` in PowerShell is a
  Windows pid, `$$` in Git Bash is an MSYS pid - and neither can test the
  other's for liveness: `kill -0` on a live Windows pid reports dead, and
  `Get-Process -Id` on a live MSYS pid reports dead. Each side therefore
  called the other's held lock stale, reclaimed it, and ran the gate anyway.
  It failed the other way too, since the two id spaces overlap numerically: a
  coincidental match reads as a live holder and the gate is silently skipped,
  which this script's own header calls worse than the double-run. Age now
  comes from the lock directory's own mtime, which `mkdir` stamps as it
  creates the directory, so there is no half-written state to misread and no
  window in which a lock exists with no age.

  The holder removes its own lock as it exits (a bash `trap` on EXIT INT TERM,
  `Register-EngineEvent PowerShell.Exiting` on the other side), so the 700s age
  window - comfortably above the hook's own 600s timeout - is the backstop for
  a hard-killed holder rather than the primary path. Two simultaneous
  reclaimers of the same abandoned lock settle it with a token write and a
  one-second re-read, on the reclaim path only, so the common path pays
  nothing.

  The lock sits deliberately AFTER the emergency lane and the empty-changed-set
  exit: the holder is what removes the lock, so a turn that does no work must
  not claim one.

  Covered by `tests/test_verify_gate_lock.py` and `tests/test_verify_gate_lock_sh.py`
  (seeded-lock cases per flavour, plus a direct assertion that the lock records
  no PID) and by `tests/test_verify_gate_lock_concurrent.py`, which runs the
  real bash/PowerShell pair against a smoke script that appends one line per
  execution and counts the lines. That last one is the test the first draft
  needed: both flavours passed their own seeded-lock suites while the lock did
  nothing, because each seeded a lock in the shape its own shell writes.
  Sabotage-tested - restoring the PID-based lock makes the concurrent case
  report two smoke runs.

- **`crew` 0.12.2: the `pm_pulse` stand-down now has the regression test it
  always owed.** The repo's own rule is that a hook which can block ships with
  must-block and must-allow cases, sabotage-tested — and 0.12.1 changed
  `pm_pulse`'s blocking behaviour past the per-session cap while the suite
  stayed at 101 passed, which said the suite did not cover the path, not that
  the change was safe. Two cases added: the pulse that trips the cap blocks
  once, and a genuinely new state afterwards does not block again.

  The first draft of the second case passed under sabotage, for the wrong
  reason — it changed `tier` and `roles`, which the fingerprint does not cover,
  so the digest never moved and the case would have gone green against a broken
  hook. It moves `handoffPending` now, which is one of the five fields the
  fingerprint is actually built from. Sabotage-tested properly after that:
  keying the over-cap claim back on `digest` turns it red, restoring the fixed
  marker turns it green.

- **`gizmoduck` 0.1.3: `diff` keeps its Low severity floor.** 0.1.2 moved
  `--min-severity` from one global default to per-command resolution and swept
  `diff` in with `report` and `tickets` at High. `commands/diff.md` passes
  `${3:-low}`, so the command path never changed — but a hand-run
  `gizmoduck.py diff old.jsonl new.jsonl` had its floor silently raised, on the
  one question where a Medium appearing for the first time is the answer. The
  floors are now explicit per command and match what each command file passes.

- `plugin/PLUGINS.md`'s `obsidian-vault` version row read 0.1.0 against a
  registered 0.1.2. `check-marketplace.py` compares `marketplace.json` history
  to file changes and cannot see a stale version string in prose, so this kind
  of drift passes CI silently.

### Changed

- **`crew` 0.13.1: six recurring failure shapes moved from "a lesson someone
  remembers" into the role and command instructions.**
  - `qa-reviewer` and `/crew:review` now treat any test, guard or assertion a
    diff adds as the primary subject of the review, with the shapes that stay
    green forever named (a floor far below the real count, stale expected
    data, a parse check reported as an execution, a sample that cannot
    discriminate, an assertion on the run rather than the job). `/crew:review`
    re-runs the author's mutation instead of reading a transcript of it, and
    treats an unverified control as a BLOCK.
  - `/crew:review` lands its verdict with `gh pr review`, not `gh pr comment`.
    A verdict that exists only as a comment cannot be acted on by anything.
  - `dba` and `crew-verification`: a migration is BLOCKING until it has been
    applied to a real or ephemeral database inside the change, with the
    changelog row selected back and a width assertion on every string literal.
    Parse-check plus review is a different claim from "it runs".
  - `/crew:promote` gains a pre-deploy reconcile gate (hash the live artifact
    against the source tree and classify every difference, so a branch that
    was never reconciled cannot roll production backwards), and now asserts on
    the deploy *job* and the artifact on the box rather than on the workflow's
    green tick.
  - `pm`: the line between coordinating and operating, drawn as a table —
    applying migrations, triggering deploys and infra recon are dispatched,
    not done. The PM never holds a merge decision, and re-engages live roles
    rather than accumulating idle ones.
  - `security`: a literal infrastructure endpoint in committed config is a
    finding on its own, because the fact acquires copies and infra work
    updates one of them. A credential already suppressed in a scanner baseline
    is still BLOCKING and still needs rotating.
  - `/crew:ticket`: the ticket key exists before the branch does, one owner per
    branch is recorded in the ticket rather than in chat, and decisions land in
    the ticket before anyone acts on a relayed version of them.

### Added

- **`gizmoduck` 0.1.0 — a third plugin under `plugin/`.** Runs
  [Nuclei](https://github.com/projectdiscovery/nuclei) against hosts and
  websites, diffs the run against a baseline so what is *new* is visible,
  renders a triaged report as Markdown/HTML/PDF, and turns Critical and High
  findings into ServiceDesk Plus tickets keyed on `[Nuclei <template-id>]` so a
  second run adds a note instead of a duplicate. Six commands over one Python
  CLI; **no hooks and no agents**, so nothing runs unless you type a command.
  Registered in `marketplace.json`, `plugin/README.md`, `plugin/PLUGINS.md`,
  the root `README.md`, and both install scripts — the repo-plugins picker now
  offers three entries, and `menu-groups.sh` asserts against 3 rather than 2.
  Nuclei is MIT-licensed and self-hosted, so no findings leave the machine;
  only scan assets you own or have written permission to test.

  Hardened before registering it, off the back of two Codex review passes. A
  `nuclei` that fails — bad target, missing templates, no network — used to
  write an empty findings file and exit 0, which is indistinguishable from a
  clean scan and poisons the next run's baseline; it now fails loudly and
  writes nothing. Exit 1 is the ambiguous case, since `-ec` uses it to mean
  "findings exist" and it is also a plain failure code: findings on stdout
  settle it, and exit 1 with an empty stdout is treated as the failure it is. Both bootstrap scripts fail when the template download fails,
  for the same reason: an engine with no templates reports every target as
  healthy. `update` checks its return codes instead of printing `done`. A
  `wkhtmltopdf` that is installed but broken falls through to WeasyPrint
  instead of taking the report command down with it. `--min-severity` now
  resolves per command — High for `report`, `tickets`, and `diff`, everything
  for `summary` and `parse` — so a hand-run `tickets` cannot quietly open a
  ticket per Info finding. Missing positional arguments produce an argparse
  error naming what is missing rather than a `TypeError`. The report's
  "Hosts scanned" line said no such thing — it counts hosts *with findings* —
  and now says so. Both bootstrap scripts pointed at a `/scan-site` command
  that does not exist; it is `/gizmoduck:scan`.

- **`crew` 0.12.0: `developer`, the eleventh agent.** Implements one scoped
  change in its own context and returns a summary — never reviews its own diff,
  never merges, pushes, or rewrites history. Tier 1 in `crew-scaling`'s ladder,
  and the one role in `crew-pm/onboarding.md` justified by a delegation
  decision rather than by a defect class in `.crew/metrics.md`: the question is
  whether the PM is expected to take work from assigned to done on its own. A
  PM with no developer either narrates or does the work itself. `onboarding.md`
  also gained the full role roster, since a name in `config.json.roles` with no
  `agents/<role>.md` behind it dispatches nothing and fails silently.

### Changed

- **`crew` 0.12.0: the PM is standing, and it wears one hat.** Three defects
  fixed together, because they were the same defect seen from three angles.

  *It kept disappearing.* The PM was spawned fresh per invocation, so it knew
  the state JSON and nothing else — not what it dispatched an hour ago, not
  what the user vetoed, not why a trigger was judged not worth acting on. It is
  now spawned once per session under the name `crew-pm` and stays addressable;
  `/crew:pm` calls `ListAgents` and messages the existing one rather than
  spawning a second. It also no longer ends when the queue empties: it reports
  what is outstanding and waits. The flat-roster limit still applies — a
  session that is itself a teammate cannot spawn a named one, so that path
  dispatches unnamed and says out loud that the PM will not persist.

  *It did other people's jobs.* `agents/pm.md` now states the PM's own hat —
  assess scope, onboard and offboard, communicate, keep tickets current — and
  carries a routing table from kind-of-work to role: implementation to
  `developer`, review through `/crew:review`, security/dba/docs/explorer/
  planner/analyst/smoke-author/browser-tester to the role that owns each. Its
  own writes stay scoped to `.crew/`, ticket text, `TODO.md`, and generated
  diagrams.

  *It narrated instead of dispatching.* Its characteristic failure was
  producing a convincing plan — lanes, roles, an order — and ending the turn
  without a single Agent call, which the relaying session then passed upward as
  progress. `pm.md` now requires a real Agent call with a read result behind
  every role named as dispatched, calls out future tense as the tell, and asks
  for independent roles in one message so they actually run concurrently.
  `/crew:pm` refuses to relay a report written in the future tense and sends it
  back once instead.

  Two more from the same Codex review. `/crew:pm`'s `allowed-tools` did not
  grant `ListAgents` or `SendMessage`, so the command that is supposed to find
  and continue the standing PM could do neither — both are now granted, and
  `validate-prompts.py` knows the names. Separately, `pm_pulse`'s per-session
  cap did not actually stand the hook down: past the cap, every *new*
  fingerprint still claimed cleanly and blocked the turn to repeat the same
  "standing down" line. The stand-down claim is now keyed on a fixed marker
  rather than on the state, so it is said once and then the hook is genuinely
  quiet.

- **`crew` 0.12.0: model tiers are declared, not inherited.** Every agent used
  to sit on `inherit` or an ad-hoc `opus`, which made the tier depend on
  whoever spawned it. Now: `pm` on `opus`, because every dispatch decision
  derives from the picture it holds and a bad assignment is inherited by every
  role below; `qa-reviewer` on `opus`, because it shares a model family with
  the author and the tier is the only compensation left when Codex is absent;
  every working role on `sonnet` — narrow brief, clean context, one
  deliverable. `validate-prompts.py` enforces the map and rejects `inherit`
  outright; sabotage-tested by flipping `explorer` back to `inherit` and
  confirming the suite goes red.

  QA itself still defaults to **Codex** — `qa.provider` ships as `auto`, so a
  machine with `codex` on `PATH` gets a different model family reviewing, and
  `/crew:review` says which reviewer ran. `qa-reviewer` now says so too if
  something dispatches it directly and skips that check, because skipping it
  does not merely swap reviewers, it swaps a different family for the same one
  that wrote the code and reports the result as though nothing changed.

  These are model *tiers*, not pinned versions: an agent asks for a tier and
  gets whatever the session's strongest model at that tier is. A plugin cannot
  pin a point release, and the docs no longer imply one.

### Added

- **`mcp-servers` install scripts can now enable write access at registration
  time.** `MCP_MS_ALLOW_WRITES` is a boolean gate, not a credential, so unlike
  `MS_ADMIN_*`/`MS_USER_*` it is safe to bake into a server's own `claude mcp
  add --env` rather than requiring it in the launching shell too — scoped to
  that server, not every process on the machine. Set it in the shell running
  `install-prerequisites.sh`/`.ps1` before the `ms-mcp` item runs and every
  server it registers gets writes enabled; left unset, every server registers
  read-only and the item prints the exact per-server one-liner to flip it
  later. `mcp-servers/README.md` gained a section spelling out both the
  per-server and global ways to set it, since the answer wasn't written down
  anywhere before now — only its meaning was.

### Added

- **`mcp-servers` 0.2.0 — the three admin-scope servers authenticate with no
  app registration at all, if you're already signed in with `az login`.**
  `@badali404/mcp-ms-core`'s new `buildAdminCredential()` (replacing
  `getAdminCredential()`) tries a credential chain in order: (1) client
  secret via `ClientSecretCredential`, app-only, unchanged — used whenever
  all three `MS_ADMIN_TENANT_ID`/`_CLIENT_ID`/`_CLIENT_SECRET` are set; (2)
  `AzureCliCredential`, delegated, zero prompts against an existing
  `az login` session; (3) `DeviceCodeCredential`, delegated, an interactive
  one-time-per-process sign-in as the last resort — using
  `MS_ADMIN_CLIENT_ID` as a public-client app id if set, else the Azure
  CLI's own well-known client id. `MS_ADMIN_AUTH=secret|cli|device` forces
  one link instead of the auto fallback. Device-code prompts go to
  **stderr only**, never stdout (the MCP JSON-RPC channel). Each server's
  `doctor` subcommand now reports which link authenticated and whether the
  resulting token is app-only or delegated, alongside the scopes/roles it
  decodes from the token as before. `mcp-o365-user` is unaffected — its
  device-code-only, `/me`-scoped auth is deliberately not part of this
  chain and was not widened. `@azure/identity`'s persistent token cache was
  evaluated and not enabled (it needs a separate native-dependency plugin
  package); a device-code sign-in is a per-process-launch prompt, not
  persisted across restarts, by design. 19 new offline tests
  (`packages/core/test/adminAuth.test.ts`) cover the fallback order,
  `MS_ADMIN_AUTH` forcing each mode, stderr-not-stdout for the device-code
  prompt, and `doctor` reporting the resolved mode. All five packages
  bumped `0.1.3` → `0.2.0` in lockstep (core pin updated in all four
  servers); `mcp-servers/README.md`, `docs/remaining-setup.md` (now a
  3-tier walkthrough: `az login` only / device code with a public-client
  app / full app-only registration), `INSTALLATION.md`, and both install
  scripts updated — the `ms-mcp` item now also checks `az account show` as
  sufficient to register the admin servers, still writing no secrets.

- **`mcp-servers/` — four local Microsoft MCP servers on one shared auth/HTTP
  workspace package.** `mcp-msgraph` (tenant directory), `mcp-intune` (device
  management), `mcp-o365-admin` (mailboxes/licenses/password reset — all
  app-only, tenant-wide), and `mcp-o365-user` (the signed-in user's own
  mail/calendar/files, delegated device-code sign-in). Not marketplace
  plugins — npm packages under `mcp-servers/packages/`, npm-workspace-linked
  against `@badali404/mcp-ms-core`, built with the official
  `@modelcontextprotocol/sdk`. Every write/destructive tool is gated behind
  **both** `MCP_MS_ALLOW_WRITES=1` and a per-call `confirm: true`; every
  server ships a `doctor` subcommand that acquires a real token and prints
  the scopes/roles actually granted. Offline test suite (mocked `fetch`, no
  live tenant) via `npm test`; wired into
  `.github/workflows/mcp-servers.yml`.

  Azure Resource Manager is deliberately not a fifth server: the official
  `@azure/mcp` already covers ARM comprehensively (dozens of service-scoped
  tool groups, plus generic `arm` CRUD), so this repo does not duplicate it —
  see `mcp-servers/README.md` for the reasoning.

  **Menu item 21, `ms-mcp` — off by default, needs tenant credentials.**
  Unlike the item 9–12 MCP servers, none of these four are on npm yet, so the
  item can't `npx -y <pkg>@latest` them: it detects `mcp-servers/package.json`
  under the current directory (this script never resolves its own location),
  builds it with `npm install && npm run build`, then runs `npm install -g .`
  inside each server package it has credentials for and registers the
  resulting global bin name (`mcp-msgraph`, `mcp-intune`, `mcp-o365-admin` —
  need `MS_ADMIN_TENANT_ID` + `MS_ADMIN_CLIENT_ID` + `MS_ADMIN_CLIENT_SECRET`;
  `mcp-o365-user` — needs `MS_USER_CLIENT_ID`), printing what's missing and
  skipping rather than failing otherwise. The global install works pre-publish
  because these are npm workspace members — it symlinks rather than
  reinstalling, so the dependency on `@badali404/mcp-ms-core` still resolves
  through the workspace's hoisted `node_modules` instead of 404ing against the
  registry.

  **The npx path is now real, not just documented.** Five packages carry
  `publishConfig`/`files`/`bin` shaped for `npm publish`: `files` is scoped to
  `dist/src` only (no compiled test output in the tarball — verified with
  `npm pack --dry-run` per package), and each server's `build` script chmods
  its compiled `cli.js` to `0o755` so the `#!/usr/bin/env node` shebang is
  executable on Linux (Windows needs neither — npm's own `.cmd`/`.ps1` shims
  handle it there). `.github/workflows/publish-mcp-servers.yml` publishes all
  five — core first, since the four servers pin an exact
  `"@badali404/mcp-ms-core": "0.1.0"` dependency — on a pushed `mcp-servers-v*`
  tag, via `npm publish --provenance --access public` authenticated with an
  `NPM_TOKEN` repository secret. Until the `@badali404` npm scope exists and
  that secret is set and a tag is actually published, `npx -y @badali404/<pkg>`
  cannot resolve anything — `mcp-servers/README.md` says so plainly and
  documents `npm install -g` (Option B, what the installer now uses) and the
  direct-path form (Option A) as the two working interim installs.

### Fixed

- **`crew` 0.11.4 — `crew:pm` could fail to dispatch with "Teammates cannot
  spawn other teammates."** `pm.md` (the only crew role with the `Agent` tool)
  had no guidance on whether to pass a `name` when dispatching a role, so it
  could end up spawning dispatched roles as named, addressable teammates. The
  runtime's team roster is flat -- a teammate (which the PM itself may be,
  depending on how it was invoked) cannot spawn further named teammates, only
  plain subagents. `pm.md`'s "Dispatching" section now says explicitly: never
  pass `name` to the Agent tool when dispatching a role. Every dispatched role
  is read and reported on within the same turn it was sent, so none of them
  ever needed to be individually addressable afterward.

- **`mcp-servers/` QA pass: a merge-blocking `npm publish --provenance`
  failure, a status-vs-parse ordering bug, and no throttling handling.** All
  five `package.json` now carry `"repository"` (type/url/directory) —
  `--provenance` refuses to publish without it, which would have killed the
  publish workflow's very first step. `GraphClient`'s `request()` and
  `getAllPages()` used to call `JSON.parse` before checking `res.ok`; a
  non-JSON error body (a WAF's HTML, a plain-text 5xx from an intermediate
  proxy) threw a `SyntaxError` and lost the real status code. Both now read
  the body first, parse it as JSON only if it looks like JSON, and fall back
  to the raw text inside a proper `GraphApiError` that still carries the
  status. Neither method handled `429` at all — Graph throttles routinely in
  real tenants — so both now share a bounded retry (max 3 attempts) that
  honors `Retry-After` (seconds or an HTTP date) and caps the wait at 30s.
  `getAllPages()` also used to truncate silently at `maxPages`, presenting a
  partial list as if it were complete; it now returns `{ items, truncated }`,
  and every server's list tool (`pagedResult()`, new in
  `packages/core/src/toolResult.ts`) appends a plain-text note to the tool
  result when truncated, so the model knows more data may exist. `post`/
  `patch`/`put`/`delete` on `GraphClient` now carry a doc comment stating they
  perform no write-gating themselves — every caller routes through
  `assertWriteAllowed` by convention, not by the type system. 12 call sites
  across all four servers and 2 in `packages/core/test/graphClient.test.ts`
  updated for the new return shape; new tests cover a non-JSON 500/502/503, a
  204 and an empty-200 body, a 429 that retries then succeeds, a 429 that
  exhausts its retry budget, a capped wait, and both `truncated: true` and
  `truncated: false`. `Install-MsMcpGlobal` (defined nested inside an
  `Invoke-Step` scriptblock in `install-prerequisites.ps1`, unlike this
  script's other helpers) was sabotage-tested against
  `scripts/check-powershell.ps1` — a typo'd call is caught (the checker's AST
  walk recurses into nested scriptblocks) — so it was left in place rather
  than moved to the top level.
- **New plugin `obsidian-vault` 0.1.1 - one or more Obsidian vaults as Claude
  Code's durable, token-efficient memory.** Cross-platform
  (Windows/Linux/macOS), no vault path hardcoded, and **multi-vault by
  design**: `~/.claude/obsidian/config.json` models named vaults
  (`vaults: { memory: {...}, codegraphs: {...} }`) because a machine-generated
  vault (a `graphify` code-graph export) commonly runs into the hundreds of
  thousands of notes on the same machine as a hand-curated one, on its own
  Local REST API port - so this plugin registers one MCP server per vault,
  never one server juggling two, and applies the frontmatter/ASCII/canvas
  contract guard only to the default vault.

  `/obsidian-vault:init` sets up the Local REST API bridge and per-vault MCP
  registration; `bridge-status`, `vault-guard`, and `vault-capture` hooks
  (each a `.sh`/`.ps1` pair sharing one Python module) probe every configured
  vault's bridge at session start, enforce the configurable contract on edit
  (every check OFF by default), and queue sessions for gardening.
  `obsidian-vault:gardener` and `obsidian-vault:reflector` agents distill and
  recall, with an explicit rule against fabricating a citation.
  `/obsidian-vault:canvas` and `/obsidian-vault:map` generate structural aids;
  `/obsidian-vault:graph` builds (`graphify . --no-viz --code-only`) and
  exports (`graphify export obsidian`, a separate subcommand - `--obsidian` on
  the build command is silently ignored) into a dedicated codegraphs vault
  laid out `<org>/<repo>/`, with a stub note left in the default vault. Ships
  with a committed, sabotage-tested regression suite for the one blocking hook
  (12 cases; the ASCII check was disabled once during development to confirm
  the suite goes red).

  **Named `obsidian-vault`, not `obsidian`**, specifically to avoid colliding
  with a third-party plugin already named plainly `obsidian` (from the
  `obsidian-skills` marketplace, wired into `install-prerequisites.sh` item
  18). `vault-automation/` (Windows-only prior art for the same
  capture/gardener idea) is marked superseded in its own README pointing here,
  but its scripts are left in place because the root `README.md` still
  documents them as a runnable quickstart. `claude-obsidian-setup/` targets a
  different thing - vault creation for the third-party `claude-obsidian`
  plugin's own conventions - and was left untouched. See
  `plugin/obsidian-vault/README.md`'s "Related" section for the full
  accounting.
- **`crew` 0.11.3 - config becomes two layers: an optional machine-global
  file plus the per-repo one.** `~/.claude/crew/config.json`, written by
  hand (no command creates it), sets defaults for every crew repo on the
  machine; the repo's own `.crew/config.json` still wins where both set the
  same thing. Merged one level deep with the same policy `/crew:upgrade`
  already used to bring a v1 config's `pm` and `graph` blocks forward - now
  named `crew_state.merge_defaults` and shared by both, instead of a second
  implementation that could quietly diverge. A malformed global file is
  treated exactly like an absent one and never touched. Two things
  deliberately skip this layering: `schema`, which is a fact about the repo
  file's own version and would otherwise look current the moment any global
  file exists; and the heal path plus `platform-sync`, which write only the
  repo file, always.

  - **crew-graph's Obsidian export gets a configurable target layout.**
    `graph.obsidian.layout` is `"flat"` (default, unchanged behaviour -
    `graph.obsidian.dir` is the export target verbatim) or `"org/repo"`
    (`dir` is a per-org folder and the skill appends `/<repo>` under it, for
    a vault laid out as `<vault>/<org>/<repo>/`). The export subcommand
    syntax and the `graph.obsidian.confirmed` consent gate are unchanged.
  - **0.11.1 -> 0.11.2:** CI caught a pylint `consider-using-dict-items` in
    a test, and fixing it exposed a real cyclic import between
    `crew_state` and `crew_config` (the first draft of this layering had
    `crew_state.collect` reach back into `crew_config` to resolve the
    global layer). `collect()` now takes the resolved config as a plain
    `cfg_override` argument; `crew_config.layered_state(root)` is the new
    composition point that supplies one. `pylint $(git ls-files '*.py')`
    exits `0`.
  - **0.11.2 -> 0.11.3, three QA guard gaps:** `hook_once.claim()` no
    longer fails open when `session_id` is absent - it derives a
    calendar-day fallback key instead, so the `.sh`/`.ps1` pair can no
    longer race a duplicate write when the payload happens to carry no
    session id. `resolve_config()` now exempts `schema` structurally
    rather than by caller discipline - a global file carrying one can no
    longer leak into an unmigrated v1 repo's resolved config. And the
    template-drift test now also covers the inline JSON copy in
    `crew-setup/SKILL.md`, extracted and compared parsed rather than
    byte-wise, so a field added to `default_config()` and forgotten in
    the doc fails CI too.

- **`crew` 0.11.0 - `.crew/config.json` recreates itself when it goes missing
  or stops parsing.** The `platform-sync` `SessionStart` hook, which already
  repaired the `platform` block, now also recreates the whole file: missing
  or empty gets fresh defaults straight away, a present-but-malformed file
  gets copied aside to `config.json.broken` first (never overwriting an
  earlier `.broken` from a prior bad session), and anything that already
  parses as an object is left alone byte for byte. **Guard: only where
  `.crew/` already exists** - a plain git repo with no crew setup is never
  colonized just because a session opened in it. Recreating the file resets
  every human choice - `tracker`, `roles`, `tier`, and the rest - back to
  defaults, and the one-line report says so and points at `/crew:init` to
  re-record them.

  - **One source for the defaults, not three.** `hooks/scripts/crew_config.py`
    is the new module that owns `default_config()`, built from
    `crew_state.PM_DEFAULTS`, `crew_upgrade.GRAPH_BLOCK`, and
    `crew_state.SCHEMA_CURRENT` rather than a fourth hand-copied literal. The
    committed template `templates/config.template.json` - what `/crew:init`
    writes - and the heal path both call it, and a test asserts the template
    equals its output byte-for-byte so the two can never quietly drift apart.

- **`crew` 0.10.0 - an Obsidian Kanban board is now a fourth ticket tracker,
  alongside `files`, `jira` and `sdp`.** Set `tracker: "obsidian"` and point
  `obsidian.vaultPath` at a vault. The board is a markdown file the
  [Kanban plugin](https://github.com/mgmeyers/obsidian-kanban) round-trips, so
  crew writes files and Obsidian draws a board.

  - **No connector, and therefore a different precondition.** Jira and SDP are
    offered during setup only when their MCP tools answer. Obsidian has nothing
    to probe, so what has to resolve is a vault directory that exists on this
    machine. Bolting that onto the MCP sentence would have produced a tracker
    that looks configured and is not.
  - **The vault is the remote, exactly as Jira is.** Ticket notes and the board
    live in the vault; `.work/cache/T-####.md` is the terse local mirror
    `/crew:work` reads, so the vault is touched at pickup and completion only.
    The key keeps its `T-####` shape, so nothing that recognises a ticket by its
    `LETTERS-digits` form needed changing — no Python moved for this release.
    It is also the reason this mode, alone among the non-file trackers, keeps
    `.work/INDEX.md`: the session brief finds the open ticket by reading that
    file, and `SDP-40219` was never going to be in it while `T-0042` can be. So
    the Obsidian tracker closes a blind spot Jira and SDP still have.
  - **Five lanes, and dragging a card is how status changes.** Backlog, Ready,
    In Progress, Review, Done, renameable via `obsidian.columns`. On pull the
    card's lane wins for status and the note wins for content; on push crew
    writes both. That rule is stated because both sides here are local markdown
    and both look equally authoritative, which makes the divergence hazard
    *worse* than Jira's rather than absent. `/crew:obsidian-sync` refuses to
    fall back to file tickets for the same reason `/crew:jira-sync` does.
  - **The board is edited in place, never regenerated.** Three parts are
    load-bearing and a naive rewrite destroys all three, after which the file
    silently opens as plain text instead of a board: the `kanban-plugin: board`
    frontmatter, the trailing `%% kanban:settings` block, and the `**Complete**`
    marker in the done lane. An archive sits below a `***` break under
    `## Archive` and is left alone. Format verified against the plugin's own
    parser at 2.0.51, not reconstructed from memory.
  - **New command `/crew:obsidian-sync <T-####> [--push]`**, argument shape
    identical to the other two syncs. 21 commands now; `validate-prompts.py` is
    at 110 checks.

  Two things the docs say plainly rather than leaving to be discovered: the
  vault lives outside the repo, so ticket state does not travel with a branch
  and is not on a colleague's machine — that is the trade for a board you can
  drag cards on. And crew never commits the vault.

### Fixed

- **`crew` 0.9.1 - two test-suite defects, both found by CI rather than by
  reading.** `test_pm_brief.py` re-imported `json` inside a function that
  already had it at module scope; pylint reported W0404 and exited 4 while
  still printing "rated at 10.00/10", which is exactly why this repo's rule is
  to judge pylint by its EXIT CODE and never by the rating line.

  The second was pre-existing and latent: `test_a_hand_edited_schema_does_not_
  crash_collect` named its scratch directories `s{abs(hash(str(bad))) % 9999}`.
  Python randomises string hashing per process, so on some seeds two of the
  five values collide, `make_repo` dies on `FileExistsError`, and the suite
  fails for a reason having nothing to do with what the test checks. Observed
  failing locally on that collision, then confirmed fixed across five explicit
  `PYTHONHASHSEED` values. Named by index now.

### Fixed

- **`infra-work-ticketing` 1.1.1 - dropped a stray `.claude/settings.local.json`
  that shipped with the skill.** It registered a `SessionStart` hook pointing at
  `C:/Users/d3ade/.local/bin/headroom.EXE`, a binary on one machine. Anyone who
  installed the skill and opened a session inside its directory got
  `No such file or directory` from a hook they never configured. Nothing else in
  the skill used it.

### Added

- **`crew` 0.9.0 - PM autonomy is now a switch, with guardrails.** 0.8.0 gave
  the PM assign authority unconditionally, which is the right behaviour for
  someone who asked for it and the wrong default for everyone else. It is now
  `pm.authority` in `.crew/config.json`.

  - **`report-only` (default) vs `act`.** `report-only` recommends and stops;
    `act` dispatches roles and refreshes diagrams on its own. The default is
    deliberate: a plugin update must not turn someone's PM autonomous
    underneath them, because consent to install is not consent to delegate.
    The field already existed in `PM_DEFAULTS`, in the config templates and in
    `README.md` - documented as "always `report-only`" and read by nothing.
    It is now the actual switch.

  - **It fails closed.** An unrecognised value resolves to `report-only`
    rather than raising or guessing, because for a field that grants
    permissions the failure direction has to be the restrictive one. `"Act"`,
    `"ACT"` and `" act "` are accepted as `act` - same intent typed carelessly,
    not a different one. Normalisation happens once in `collect()`, so no
    consumer downstream ever re-decides what a typo means and they cannot
    disagree.

  - **The pulse says different things.** Under `act` the `Stop` hook emits a
    work order; under `report-only` it emits recommendations and explicitly
    forbids dispatching. Sending the wrong one would make the setting a lie -
    config saying "ask me" while the hook said "go".

  - **The rabbit-hole rule.** Autonomy's failure mode is not doing the wrong
    thing, it is doing too many things: refresh a diagram, notice a bug, fix
    it, notice thin tests, write tests, and the diagram is still stale. So a
    problem the PM stumbles on is fixed **only when it blocks a finding it was
    already working** - build broken, harness will not run, migration will not
    parse. Unblocking the current job is finishing the job. Everything else is
    recorded and left alone: a ticket when `tracker` is set, otherwise a
    `TODO.md` line with the reason it was deferred. The report must say what
    was deferred and where it went, because a guardrail whose effects are
    invisible reads as the PM having found nothing.

  - **`pm.maxDispatches`** (default 3) caps roles per pass. Blockers found
    mid-task do not count against it.

  - **`/crew:pm authority [report-only|act]`** reads or sets it, and
    `/crew:init` now asks as its fourth setup question, defaulting to
    `report-only` on any hesitation. `/crew:pm assign` still acts anywhere -
    typing it *is* the explicit instruction - and says when the config
    disagrees, so a user who wanted it permanent learns there is a setting.

  - 24 new cases (shell suite 95 -> 101, pytest 306 -> 324), sabotage-tested:
    making an unknown authority widen to `act` instead of failing closed turns
    both suites red.

- **`crew` 0.8.0 - the PM assigns work, and re-engages itself when state
  changes.** Three related gaps, reported together: the PM only ever spoke at
  session start, so a session that opened clean and then closed a ticket or
  broke a gate heard nothing; the `pm` agent was structurally unable to act on
  what it found, holding no `Write` tool and returning a report that the user
  then had to act on themselves; and architecture, process and data-flow
  diagrams had no staleness signal at all, so nothing ever noticed they had
  drifted.

  - **New `pm-pulse` `Stop` hook.** Re-engages the PM when the project's state
    actually transitioned - a ticket closed, a gate broke, diagrams fell behind
    HEAD. The gate is a **state fingerprint, not the event**: `Stop` fires once
    per turn, and a brief on every turn is the noise that makes people switch
    the PM off, at which point they get nothing. Turns that change nothing stay
    silent.

    It blocks (exit 2) to hand its findings back to the model, because stdout
    on `Stop` reaches the user but never the session - a PM that cannot be
    heard by the thing doing the work cannot assign any. Three loop guards:
    `stop_hook_active` is honoured first and unconditionally, the fingerprint
    marker means one state can only interrupt once, and the hook stands down
    after 12 pulses in a session rather than becoming the thing you disable.

    `hook_once` is deliberately **not** used - its own module docstring says
    why. Its marker is keyed on `(hook, session)` and never cleared, so a claim
    taken on turn 1 silences the hook for the rest of the session, which is
    exactly what this hook must not do. Keying the marker on the fingerprint
    instead de-duplicates the `.sh`/`.ps1` pair and gates on state change with
    one mechanism.

  - **The `pm` agent now dispatches.** It gains `Write`, `Edit` and `Agent`,
    and a dispatch table mapping each trigger to the role that closes it. A
    manager whose only output is a recommendation is a manager the user has to
    manage. Three bounds keep it honest: a **stated user priority outranks**
    the PM's trigger ordering, and it says so when it re-orders; **removal and
    deletion still need an explicit yes** - offboarding, deleting a codemap or
    diagram, rewriting `metrics.md` - because adding capability is reversible
    and removing it destroys the evidence that would say whether removing it
    was right; and a multi-agent run is **announced before** it happens. Writes
    stay scoped to `.crew/` and `docs/diagrams/`. `/crew:pm assign` is the
    manual entry point.

  - **Diagram freshness is now a tracked fact.** `crew_state.py` reads
    `docs/diagrams/*.mmd`, parses the short sha out of the documented
    `%% Generated from <repo>@<sha>` header, and reports `diagrams.behind` and
    `diagrams.missing`. Two new triggers, `diagramsStale` and `diagramsMissing`,
    sort **below** `graphStale` and `knowledgeBehind` on purpose: a diagram
    regenerated from a code map that is itself behind HEAD is stale output
    wearing a fresh anchor, which is worse than the diagram it replaced because
    it no longer advertises its age. `diagramsMissing` stays quiet until there
    is a codemap, so a fresh setup is not nagged about three diagrams on
    session one.

    Diagrams are the **only** documentation artifact the crew regenerates
    unasked. That is not a general licence: they carry a machine-checkable
    anchor, so "is this still true" has a real answer. Prose docs keep
    `crew-docs`'s deliberate *do not touch* default, because whether a change
    deserves a CHANGELOG entry is a judgement about what users can observe and
    no sha answers it.

  - Found while writing the tests: reusing the codemap's `_ANCHOR_RE` for
    diagrams reads **every** correctly-anchored diagram as stale. That regex
    requires the line to start with `anchor:`, which is a syntax error in a
    Mermaid source - provenance there has to live inside a `%%` comment. The
    bug looks like the feature working, right up until nothing is ever current.
    `_DIAGRAM_ANCHOR_RE` handles the documented header and the hand-written
    `%% anchor:` form.

  - 40 new cases in `run-tests.sh` (50 -> 90), sabotage-tested both ways:
    removing the `stop_hook_active` guard and reverting the anchor regex each
    turn the suite red.

- **`crew` 0.7.0 - the `platform` block repairs itself at session start.** It is
  the one block in `.crew/config.json` that is committed and is therefore wrong
  for everybody who did not run `/crew:init` - and `windowsHostIp` is wrong for
  the same person after a reboot, because WSL2's gateway changes. Open a repo on
  Windows that was set up in WSL and the session now opens with
  `## platform - config said linux, this is windows-bash; updated 5 field(s)`,
  itemised, and the config already fixed.
  - **One rule makes it safe: it writes derived facts and nothing else.** The
    seven writable keys are `os`, `wsl`, `wslVersion`, `distro`, `shell`,
    `repoFilesystem` and `windowsHostIp` - each an answer to "what machine is
    this", which nobody hand-edits usefully. A test pins that list, because
    adding a preference to it would turn the hook into something that overrules
    people.
  - **Preferences are reported, never rewritten:** an `autoClear.method` that
    only exists on the other platform (which would otherwise make auto-clear
    stand down silently), a clone under `/mnt/` where every file operation goes
    through the Windows translation layer, CRLF in a committed `.sh` that bash
    reports as "bad interpreter: ...^M". `tracker`, `qa`, `roles`, `tier`,
    `notify`, `emergency`, the context thresholds and `verifyGate` are never
    touched.
  - This is why it may write when the PM may not: the PM's subject is
    *judgement*, and whether a role earns its context is not a fact.
    `platform.os` is a fact, it is wrong on the other machine, and being asked
    about it once per clone would be worse than having it fixed. It still says
    what it changed - a silent config edit would be indefensible.
  - It does not write when nothing changed, so it never dirties a tree just by
    opening a session, and it preserves the file's existing line endings - a
    CRLF config rewritten as LF is a whole-file diff for whoever committed it.
    A read-only checkout, or no python, reports what it *would* have changed.
  - Detection covers native Linux, WSL1, WSL2 (including reading the gateway as
    the Windows host address), macOS, native Windows, and Git Bash on Windows -
    which `sys.platform` cannot distinguish from a cmd session, so `MSYSTEM`
    decides whether crew should be writing bash or PowerShell here.
  - Both flavours are thin wrappers over one python module
    (`hooks/scripts/crew_platform.py`), the `pm-brief` pattern. For a hook that
    writes config, two implementations that disagree about what they write is
    the last thing anybody wants, and this plugin's `.sh`/`.ps1` pairs have
    drifted for a whole release before.
  - `tests/test_platform_sync.py`, 29 cases. The detection paths are exercised
    by faking `platform.system()` and the `/proc` files WSL is recognised by,
    because a suite that only covers the OS it runs on is how a cross-platform
    bug survives.
  - Found while writing it: reading the config in text mode let universal-newline
    translation strip CRLF before anything could see it, so the
    line-ending-preserving write silently rewrote a CRLF config as LF.

- **`crew` 0.6.2 - `context.autoClear`, experimental, off by default.** A matched
  pair of scripts that type `/clear` into the terminal once the handoff note is
  written. This does **not** contradict the standing correction that a hook
  cannot clear its own session - it does not touch the conversation. It drives
  the *terminal*, typing at the prompt the way a human would, which is a
  different mechanism with a different failure mode.
  - That failure mode is why it is experimental: typing into a terminal is only
    safe if you know which terminal. `tmux` targets `$TMUX_PANE` by id and never
    touches focus, so in tmux this needs no configuration beyond
    `enabled: true`. `xdotool`, `wtype` and the Windows `SendKeys` path all
    depend on focus, so they **require** `context.autoClear.windowTitle` and
    refuse rather than guessing; `wtype` additionally needs `unsafeFocus: true`,
    because Wayland offers no way to check what has focus at all. The Windows
    child re-checks the foreground window's title immediately before typing, so
    alt-tabbing during the delay cancels the send rather than redirecting it.
  - Five conditions before it types anything: `enabled` exactly `true` (the
    string `"true"` is not), the handoff was actually requested this session,
    the note exists and is **newer** than that request, it has at least
    `minHandoffLines` non-blank lines (default 5 - clearing on a two-line
    placeholder loses the work and leaves a note that says "continue the work"),
    and nothing has claimed the one-per-session attempt.
  - The attempt is claimed immediately **before** the send, not with the
    conditions, so a misconfiguration does not burn the session's only try -
    fixing `windowTitle` mid-session actually retries. A `--dry-run` does not
    claim it either.
  - Every refusal is written to `.crew/.autoclear.log`, because a `Stop` hook's
    stderr is invisible when it exits 0 and without it "nothing happened" cannot
    be told apart from "the feature is broken".
  - `--dry-run` / `-DryRun` prints the method, target, command and delay it would
    use and sends nothing; `--force` / `-Force` skips the handoff conditions so
    the plan can be inspected outside a real session.
  - `tests/test_auto_clear.py` - 32 cases across both flavours, every one either
    `--dry-run` or against a fake `tmux`/`xdotool` on `PATH`, so no test can send
    a keystroke to the machine running it. Sabotage-tested three ways: moving the
    claim back into the conditions block (5 red), dropping the CR strip (12 red),
    and allowing a focus-based method with no window title (1 red).
  - A third bug, found by CI rather than by me: on a Linux runner with pwsh
    installed, `auto-clear.ps1` ran every condition, claimed the
    one-per-session attempt and reported "sent" - on a platform where its
    SendKeys path cannot type anything. Reporting success while delivering
    nothing is worse than failing, because the log then says it worked. It now
    exits immediately unless `$IsWindows`, the suite treats that flavour as
    native-Windows-only, and a new case pins the stand-down on a non-Windows
    pwsh. 0.6.0 and 0.6.1 were set on the branch and never published; the
    released version is 0.6.2, which also carries the ANEWINF-758 pytest
    determinism fix this branch merged in from `main`.
  - Two bugs found by running it rather than reading it, both now covered. The
    config was read as tab-separated fields with a tab as the field separator,
    and a tab is IFS *whitespace*, so bash collapsed consecutive separators and
    an empty `windowTitle` - the default - shifted every later field left by
    one. And python on Windows writes CR-LF, so every value arrived with a
    trailing carriage return: the `enabled` comparison failed and the script
    exited having done nothing. Both were invisible failures from a `Stop`
    hook, which is the worst kind.

- **`crew` 0.5.2 - ServiceDesk Plus as a third tracker.** `tracker: "sdp"` plus
  `/crew:sdp-sync <REQUEST-ID> [--push]`, mirroring the Jira path rather than
  inventing a second shape: pull keeps id, subject, status, requester, priority,
  category and the last three notes and discards the rest, `/crew:work` reads
  that cache instead of the API, and sync happens at pickup and completion only.
  `/crew:ticket` and `/crew:work` both learned the mode, and `/crew:init` offers
  it as the third answer to the tracker question - **only when the `sdp_*` tools
  are actually reachable**, since a repo configured for an API nobody can call
  stops every later command on the same missing precondition.
  - **The local key is `SDP-<id>`, not the bare request number.** SDP ids are
    plain integers and the rest of crew recognises a ticket by its
    `LETTERS-digits` shape, so a bare `40219` is invisible to the session brief,
    to `/crew:work` and to the index. Both halves of that claim are now pinned by
    tests, because the failure mode is silence: every SDP repo would report "no
    ticket open" forever.
  - Three things the command has to get right that Jira does not have: notes are
    **requester-visible** unless private (`sdp.noteVisibility` defaults to
    `private`, and that is not a substitute for scrubbing), a bad field value
    **rejects the whole write** rather than partially applying it (resolve
    against `sdp_list_metadata` first), and **closing is not crew's decision** -
    `sdp.closeOnDone` defaults to `false`, so push transitions a request and
    leaves closure to whoever owns the queue.
  - No `.mcp.json` ships for it, deliberately: the SDP connector is normally
    registered at user or session scope, and a per-repo one would prompt for
    approval in every repository where the plugin is enabled.
  - New config block `"sdp": { "portal": null, "noteVisibility": "private",
    "closeOnDone": false }`. Documented in `crew/README.md` 13b, the
    configuration table, `PLUGINS.md`, and both setup docs.

- **`crew` 0.5.1 — `/crew:emergency`, a time-boxed lane for when something is
  actually broken.** The gates that normally earn their keep are, during an
  outage, standing between you and the fix, and the honest options are to work
  around them silently or to make standing them down a decision with a record
  and a clock on it. `/crew:emergency <what is broken>` writes
  `.crew/incident.json`; while it exists and its `expiresAtEpoch` is in the
  future, `verify-gate` exits 0 without running the checks and `promote-gate`
  computes its preconditions, records the ones that failed, and allows the
  deploy. `status`, `extend [minutes]` and `end` are the rest of the surface.
  Declaring also fans out read-only investigation lanes in parallel — what
  changed in the window before the symptom, what shares the failing path, the
  most probable causes with the cheapest observation that would kill each, plus
  `security` and `dba` lanes when the symptom calls for them.
  - **It expires on its own.** The gates compare an integer epoch, so nothing
    runs and no file is touched to re-gate. Forgetting to close an incident is
    the realistic failure — nobody forgets to declare one during an outage — and
    it cannot leave a repository permanently ungated. `emergency.ttlMinutes`
    defaults to 120; `extend` is capped by `emergency.maxTtlMinutes` (480) and
    measured from *now* each time, so repeated extensions cannot compound.
  - **The command guard never stands down.** `guard.sh` / `guard.ps1` has no
    incident branch and must not get one. Standing down a check that says a
    change is wrong is a trade; standing down the one that stops a change being
    unrecoverable — a force push, a destructive Terraform verb, a history
    rewrite, a secret read into the transcript — is not, and an incident is
    precisely when someone is tired enough to need it.
  - **The debt list is the deliverable.** Every skipped gate is recorded to
    `.crew/incident-skips.log`, one row per gate and reason rather than one per
    turn, and `end` turns it into `.work/INCIDENT-<id>.md` plus an archived
    record under `.crew/incidents/`. Deleting the state file is what puts the
    gates back, and it happens only after the archive is on disk.
  - **Every session start says so.** `incidentActive` and `incidentUnclosed`
    are the two highest-priority PM triggers, above `upgradeNeeded`, and the
    incident line sits in the brief's quiet lines so no line cap can truncate
    it away. A session that does not know the gates are off is a session about
    to merge unverified work believing it was checked.
  - **A repository can forbid the whole thing.** `emergency.standDown: false`
    keeps every gate gating; the incident is still declared, recorded, briefed,
    and still spawns its lanes.
  - Covered by `tests/test_incident.py` (24 cases), 15 new cases in
    `hooks/scripts/_test/run-tests.sh` — including that the guard still blocks
    during an incident and that an expired one gates again — and
    `tests/test_gates_powershell.py`, which runs the same scenarios against the
    `.ps1` gates. All sabotage-tested in both flavours.

### Fixed

- **`crew` 0.5.4 - ANEWINF-758: the `plugin/crew` pytest suite was
  nondeterministic, 87-97 of ~182 tests passing on identical code across
  consecutive runs.** Every `git` `subprocess.run` call in the suite - and
  two in production code - left `stdin` at its default, so `git` inherited
  whatever OS handle the parent process's stdin currently pointed at.
  pytest's fd-based output capturing tears down and rebuilds file descriptor
  0 on every test's setup/teardown, so an inherited handle can go stale
  mid-suite; on Windows that surfaces as `OSError: [WinError 6] The handle
  is invalid` inside `subprocess._make_inheritable`, and the documented
  equivalent on a CI runner whose own stdin is a pipe is `EBADF`. A second,
  quieter instance of the same bug lived in `crew_state.py`'s `git_out()`
  and `crew_upgrade.py`'s `_head()`: both wrap their `subprocess.run` call in
  `except (OSError, subprocess.SubprocessError): return None`, written to
  turn "git is absent" into a soft `None` - which also silently swallowed
  the transient handle-invalid error and returned a wrong-but-non-crashing
  `None` on an unpredictable subset of runs. All eight call sites (four in
  `tests/crew_fixtures.py`, one each in `tests/test_crew_fixtures.py` and
  `tests/test_gates_powershell.py`, plus the two production sites) now pin
  `stdin=subprocess.DEVNULL`, removing the dependency on the inherited
  handle entirely. Proven with five consecutive full-suite runs reporting
  an identical pass count and exit 0 each time; before the fix, five
  consecutive runs ranged from 74 failed/113 passed to all passing with no
  code change in between.
- **`crew` 0.5.3 - a comment, from an advisory review.** `read_skips` now
  dedupes on `(gate, detail)`, which made the per-gate loop in `report()`
  look like a redundant second dedupe worth deleting. It is not: what it does
  that `read_skips` does not is drop empty details, which would otherwise
  print as a bare bullet - and the count beside it is distinct debts rather
  than how many turns declined to run something. Both are now stated where
  someone would go to simplify it.

- **`crew` 0.5.1 - findings from the Codex review pass, fixed before merge.** 0.5.0
  was set on the branch and never published; the released version is 0.5.1.

  - `crew_incident_active` in `_common.sh` pulled `expiresAtEpoch` out with
    `sed`, so `{ not json "expiresAtEpoch": 9999999999` stood every gate down in
    bash while the PowerShell twin's `ConvertFrom-Json` correctly rejected it -
    a gate switchable off by a typo, and a flavour disagreement in the
    fail-*open* direction. It now parses the document in full and treats every
    failure, including no python at all, as "no incident". Two regression cases
    cover it, and the old implementation demonstrably read that epoch.
  - Skip-log rows are deduplicated on read as well as on write, so a race
    between the two hook flavours can no longer inflate the count of what is
    owed, and tabs, carriage returns and newlines are normalised out of gate
    names and details in all three implementations - a `rollbackReason` with a
    newline in it would otherwise forge a row.
  - `end()` re-reads the state file and refuses to close an incident whose id
    changed underneath it, before writing anything: a declaration landing mid
    close would otherwise be archived under the previous id and deleted,
    re-gating a repository someone had just declared an incident for.
  - `_write_state` uses a pid-unique temp file, so two writers cannot interleave
    into one and publish a torn document.
  - Documented rather than fixed, both in `crew/README.md` 24: the expiry is
    wall-clock, so a machine whose clock moves backwards extends the window; and
    the `.crew/.handoff-requested` marker is per repository rather than per
    session, so two sessions in one repo share one context warning. The second
    is pre-existing and wrong rather than deliberate - the fix is to key it on
    the payload's `session_id`.

- **`crew` 0.5.1 — the context watch no longer asks for a handoff with 200k
  tokens still free.** `context.warnAt` was tuned when every window was 200k,
  where 0.8 leaves 40k: about enough to finish a thought and write the note. The
  same 0.8 on a 1M window leaves 200,000 tokens unused and still asks you to
  wrap up, which is a whole 200k session's worth of room thrown away — and no
  percentage fixes it, because the right amount of headroom is an absolute
  number. The threshold is now the **later** of `warnAt * budget` and
  `budget - context.reserveTokens` (new, default 100000), so the floor can only
  ever push the warning later: a 200k window still fires at exactly 80% (40k
  < 100k, so the percentage wins) and a 1M session moves from 80% to 90%.
  `reserveTokens: 0` or `null` restores the pure percentage, and `warnAt: 0`
  still fires immediately — the floor is skipped entirely for it rather than
  quietly outranking the one explicit override. The warning now names which rule
  fired, with both figures and the remaining headroom, so a threshold behaving
  oddly is visible instead of mysterious. New cases in
  `tests/test_context_watch.py` pin the no-regression case, the 1M case, the
  default, the `warnAt: 0` override, and full stderr parity between the two
  flavours on the new branch.
- **`crew` 0.5.1 — the once-per-session handoff marker is now claimed
  atomically** (`noclobber` in bash, `FileMode::CreateNew` in PowerShell). On
  Windows with Git Bash installed both flavours of the `Stop` hook really do
  run, and a test-then-create let both through, so the same warning was emitted
  twice. The PowerShell side also had to take the absolute path: `[System.IO.
  File]` resolves a relative one against `[Environment]::CurrentDirectory`,
  which `Set-Location` does not update, so the claim would have landed in
  whatever directory the hook was spawned from.
- **`crew` 0.5.1 — `Resolve-CrewBash`'s PATH fallback could return an empty
  interpreter.** A `bash` function or alias defined in a PowerShell profile is
  returned by `Get-Command bash -All` ahead of any `bash.exe` with an empty
  `.Source`; `.StartsWith()` on that throws and returning it handed
  `& $bashExe` nothing, so the gate reported a smoke failure that was really a
  resolution failure. Tier b now takes `Application` entries only — the same
  guard the git walk-up already had.
- **`validate-prompts.py` counted a slash-command reference as a subagent
  dispatch.** `/crew:pm` in a command's prose is a pointer to another command,
  not an `Agent` call, but several names are both an agent and a command — so
  `scale.md`, which only mentions `/crew:pm`, was told to declare a tool it
  never uses. The check now excludes the slashed form.

### Changed

- **`scripts/check-powershell.ps1` now checks every tracked `.ps1`, not just the
  installer.** It defaulted to `install-prerequisites.ps1` alone, which left the
  crew plugin's hook scripts — the ones that run from a hook on someone else's
  machine, where a thrown exception is invisible — completely unguarded by the
  one check that catches a call to a function that does not exist. All 18 files
  pass; sabotage-tested by mis-naming a call in `verify-gate.ps1`, which the old
  default would not have caught. `-Path` still checks a single file. The first
  CI run of the wider check immediately earned it, by failing on the
  `ScheduledTasks` cmdlets in `vault-automation/setup-vault-automation.ps1`:
  that module ships with Windows and does not exist on the Linux runner, so
  those calls resolve for a developer and not for CI. They are in the
  `$externallyProvided` allowlist by exact name rather than by a
  `*-ScheduledTask*` pattern, so a typo in one of them is still caught -
  verified by introducing one.
- **CI runs the crew hook regression suite and the prompt validator.** Both were
  committed, documented as the safety net for hooks that can block a turn, and
  run only when somebody remembered to. A gate that stops gating still exits 0,
  which is exactly the kind of regression a suite nobody runs cannot catch.

### Fixed

- **`crew` 0.4.5 — the Windows `Stop` hook ran the verify smoke inside WSL.**
  With WSL installed, PowerShell resolves a bare `bash` to
  `C:\Windows\system32\bash.exe`, so `verify-gate.ps1` ran `_verify/smoke.sh`
  in a distro with no terraform, no python and a different `~`, and reported
  `SMOKE: 0/9 FAIL` on trees where Git Bash reads 12/12 — a blocking gate
  failing for a reason that had nothing to do with the repository.
  `Resolve-CrewBash` in `hooks/scripts/verify-gate.ps1` now walks up from
  `git.exe`'s own directory to `bin\bash.exe` or `usr\bin\bash.exe`, falls
  back to `Get-Command bash -All` minus System32 and WindowsApps, and only then
  to a bare `bash`, so nothing changes off Windows. Both call sites use it —
  the `smoke.sh` invocation and the `run: ["bash ..."]` rules from
  `.crew/verify.json` — and the failure output now names the interpreter it
  used. `tests/test_verify_gate_bash_resolver.py` covers the four resolution
  shapes: System32 first on PATH, a `mingw64` install, the WindowsApps
  execution alias, and a `git` defined as a PowerShell function, which used to
  throw a terminating error out of the hook. The PATH fallback carries the same
  guard as the walk-up, for the same reason: a `bash` function or alias in a
  PowerShell profile is returned by `Get-Command bash -All` ahead of any real
  executable with an empty `.Source`, which the gate would have run as an empty
  interpreter and reported as a smoke failure.
  0.4.4 was set on the branch and never published; the released version is
  0.4.5.
- **`crew` 0.4.5 also carries the five ANEWINF-720 silent-failure fixes**, which
  merged without a version bump and so never reached an installed copy: the
  rollback gate fails closed instead of skipping when `.crew/verify.json` omits
  `rollback`, generated `STATUS.md` and `verify.json` state that enforcement is
  session-local, `/crew:review` writes ticket-scoped scratch paths rather than
  racing concurrent reviews, the tool matcher sees commands invoked from inside
  a script, and the guard no longer fires on an incidental substring match.

- **`crew` 0.4.3 — the context watch no longer ends Windows sessions on turn one,
  and knows that Claude 5 models have a 1M window.** Three causes, all in the
  `Stop` hook pair `hooks/scripts/context-watch.{sh,ps1}`:
  - `context-watch.ps1` still estimated occupancy from transcript file size
    (`bytes/4*0.75`) against a hardcoded 200k. The transcript is cumulative, so on
    real sessions that read 158%, 195% and 664% — the handoff prompt fired on the
    first turn of every Windows session. It now reads the transcript's last
    `message.usage` record exactly as the bash flavour does, with the same model
    table, the same observed-peak correction, and byte-identical output.
  - The model table in both flavours said `opus`, `sonnet` and `fable` are 200k.
    `claude-opus-5`, `claude-sonnet-5` and `claude-fable-5` ship with 1M; the
    observed-peak self-correction only rescued that past 190k, so the 160k–190k
    band fired falsely on every Claude 5 session. The table now carries the 1M
    entries above the generic 200k ones. The observed-peak correction also went
    the other way: it tripped at 95% of the table figure, so a Claude 5 session
    that legitimately passed 950k of a correct 1M entry was bumped to the 2M
    tier and the gate never fired. It now triggers only on a peak the window
    could not have held.
  - A pinned `context.budgetTokens` the session has already exceeded (an older
    `/crew:init` wrote `200000` into every config) is now overridden by the
    observed peak and reported as `configured+observed`. A stale pin the session
    is still *under* cannot be detected; set it to `null`.
  - Subagent turns were never counted — Claude Code writes them to
    `<session>/subagents/*.jsonl`, which the watch does not open — and that is
    now stated in the docs and pinned by a test; inline `isSidechain` records from
    older builds are skipped explicitly.
  - `tests/test_context_watch.py` previously fed both flavours a byte blob with
    no usage record, so the PowerShell drift was invisible. It now feeds real
    usage transcripts for every branch (Claude 5 at 170k must not fire, Haiku at
    170k must, stale pin override, subagent exclusion) and compares the two
    flavours' full stderr on the measured path.

### Removed

- **The `claude-mem` and VoltAgent menu items are gone from both install scripts.**
  They were items 9 and 10, both on by default, so a bootstrap run installed a memory
  plugin, Bun as its worker runtime, a `CLAUDE_MEM_WORKER_PORT` patch to
  `settings.json`, and ten VoltAgent subagent plugins whether or not you wanted any of
  them. All of that is out: the `--voltagent` / `-VoltAgent` flag and its sub-picker
  group, the `VOLTAGENT_*` / `$script:VoltAgentCatalog` catalogs, `install_bun` /
  `Install-Bun`, and `set_claude_mem_worker_port` / `Set-ClaudeMemWorkerPort`. The menu
  is now 20 items, 8 of them on by default. **Everything after the hole shifted down by
  two** — the MCP servers are 9–12, Supabase 13, Context7 14, Playwright CLI 15, SkillUI
  16, Strix 17, Obsidian 18, this repo's plugins 19, `graphify` 20 — so any script
  passing `--select` by *number* needs updating; the stable keys (`--select
  supabase,strix`) do not. Both scripts were changed together and verified to produce
  the same 20-row menu and the same answer for `--select 19` / `-Select 19`. The
  removal is documented across `README.md` (both tables, the switch table, and every
  per-item note that names a number), `INSTALLATION.md`, `MARKETPLACE.md` and
  `SECURITY.md`; `scripts/_test/menu-groups.sh` now exercises the range and
  out-of-range cases against the skills group instead of the VoltAgent one, and
  `check-marketplace.py` no longer expects a `VOLTAGENT_KEYS` array. Nothing already
  installed on a machine is touched — uninstall those plugins by hand if you want them
  gone (`claude plugin uninstall claude-mem@thedotmack`, and likewise for each
  `voltagent-*@voltagent-subagents`). The removed flag fails differently on the two
  platforms, so a script still passing it needs editing either way: `--voltagent a,b`
  on the `.sh` warns `Unknown option` twice (once for the flag, once for its argument,
  which no longer gets shifted past) and then installs the rest of the selection, while
  `-VoltAgent a,b` on the `.ps1` is a parameter-binding error and the script does not
  run at all.

### Fixed

- **`crew` 0.4.2 — every PowerShell hook was dead on Windows, and the command guard
  blocked nothing there for the second time.** `hooks.json` wrote each PowerShell entry
  as `& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/x.ps1'`. For a `shell: powershell` entry
  Claude Code substitutes that placeholder as a PowerShell *environment reference*, and
  PowerShell does not expand anything inside single quotes — so `&` was handed the token
  verbatim and the hook died with "is not recognized as a name of a cmdlet". Only the two
  `SessionStart` hooks reported it visibly, because they are the ones that fire at
  startup; `guard.ps1`, `promote-gate.ps1`, `handoff-write.ps1`, `notify.ps1`,
  `verify-gate.ps1` and `context-watch.ps1` were failing just as silently. Fixing the
  quoting exposed a second failure underneath it: `& script.ps1` inside PowerShell's
  `-Command` does not propagate the script's exit code, so a guard's `exit 2` arrived as
  1 — a non-blocking error — and the command ran anyway. Every PowerShell entry now
  double-quotes the path and ends with `; exit $LASTEXITCODE`, verified end to end
  against `guard.ps1` (blocking `git push --force`, exit 2; allowing `Get-ChildItem`,
  exit 0). The bash entries got the same double-quoting, which they needed for a home
  directory with a space in it. `scripts/check-marketplace.py` grew a
  `check_hook_commands` check that fails CI on either mistake, and both new rules are
  written into `CLAUDE.md`. This was not an install-script problem — the repo and
  installed copies were byte-identical, so every Windows install of `crew` had it.

### Changed

- **Re-pinned the README's one-liner install URLs** from `8fc09be` to `ae58c21`, per the
  rule in `CLAUDE.md`. `8fc09be` predates the menu trim above, so the documented
  one-liner was still installing `claude-mem`, Bun and the ten VoltAgent packs by
  default, and still numbering its menu 1–22.
- **Re-pinned the README's one-liner install URLs** from `f59faf1` to `7059ede`, per the
  rule in `CLAUDE.md`. The old pin predated everything below, so the documented one-liner
  was still handing people the installer with the broken `claude plugin update` call.

### Fixed

- **Every installed skill was frozen at whatever it looked like on the day it was first
  published.** `claude plugin update` decides whether to re-copy a plugin by comparing
  declared versions, and no skill in this marketplace had ever had its `version` bumped -
  all 25 sat at `1.0.0` from the day they were added. Nineteen of them had had real
  content changes since. The CLI answered every update with "already at the latest
  version (1.0.0)" and copied nothing, so anyone who ran the installer once was still
  running the original text of every skill, with no indication anything was wrong. The
  matching `claude plugin update` bug (below) had been masking it behind a warning that
  looked like the real explanation. The 18 skills whose files had changed since their
  version was set are now `1.1.0`; `crew` goes to `0.3.0` (its `0.2.0` was declared a
  commit before the Windows hook fix landed, and two further changes landed after that).
  The seven skills whose files genuinely had not changed are left at `1.0.0`.

### Added

- **`crew` 0.3.0 — a report-only project manager, a code graph, and a v1→v2
  upgrade path.** Three connected pieces, all off by default in what they can
  do to `.crew/config.json`:
  - **The PM.** `/crew:pm` (status with no argument; `onboard <role>` /
    `offboard <role>` with explicit yes/no confirmation before either touches
    config) and the `crew:pm` subagent, which holds no `Write` tool at all —
    it reads `crew_state.py`'s output, correlates the full metrics history or
    audits every codemap anchor when that would cost more context in the main
    session than the answer is worth, and returns a report plus one
    recommendation, under 200 words. It never applies anything; the session
    that invoked it acts, or not. A new `SessionStart` hook, `pm-brief.sh` /
    `.ps1`, runs the same state read at the start of every session and prints
    a prioritized brief — schema drift, a stale or missing code graph, a
    pending handoff, review health — before you type anything. Two related
    `context` settings, both default `false`: `autoWrapUp` changes what the
    `Stop` hook tells the session to do at the warning threshold (reach a
    stopping point and write the handoff, rather than just ask), and
    `autoResume` opens the next session already holding the last handoff as
    `additionalContext` — `initialUserMessage` was ruled out because it is
    confirmed only for non-interactive `-p` runs. Neither setting makes
    `/clear` itself automatic; no hook can trigger one.
  - **The code graph.** The `crew-graph` skill wraps the third-party
    `graphify` CLI (PyPI package `graphifyy`, double-y) to build and query a
    code graph at `graph.out` (default `graphify-out/graph.json`), gated on
    `--no-viz --code-only` for a keyless build. Freshness is read from
    `graphify`'s own `built_at_commit` field in
    `graph.json`, never a file timestamp — a `git pull` that predates the
    last build now correctly reports as stale instead of falsely current.
    Exporting into Obsidian needs an explicit `graph.obsidian.confirmed` set
    by hand; nothing sets it for you.
  - **The upgrade path.** `/crew:upgrade` brings a pre-schema config (no
    `schema` key, now `schema: 1`) forward to `schema: 2`: backs up
    `.crew/codemap/` before any other write, builds the graph if it's
    missing or stale, derives `Entry points` / `Owns data` / `Calls out to`
    per subsystem from the graph, and writes `.crew/codemap/UPGRADE.md`
    reporting contradictions and stale-on-purpose anchors rather than
    resolving either automatically. `## Does`, `## Landmines`, and
    `## Unverified` pass through byte-identical, always. An anchor only
    bumps on a section actually re-verified this run.

  `.crew/config.json` gains `schema`, a `pm` block (`enabled`, `mode`,
  `quietLines`, `maxLines`, `authority` — always `report-only`), and a
  `graph` block (`out`, `obsidian.confirmed`) — see `plugin/crew/README.md`
  §11. The plugin now registers 10 subagents, 18 slash commands, and 16
  bundled skills, up from 9/14/14.
- **Both `.sh` and `.ps1` are now wired for every hook event, not just
  `PreToolUse`.** `verify-gate.ps1`, `context-watch.ps1`, and
  `handoff-read.ps1` existed on disk but were never referenced in
  `hooks.json`; `handoff-write.ps1` and `notify.ps1` are new. 8 scripts × 2
  flavours = 16 hook entries across the same 5 events (including the
  `promote-gate.sh`/`.ps1` pair added below), registered unconditionally —
  one flavour is expected to fail per machine, and that is by design, not a
  regression. On Windows this closes the gap the 0.2.0 entry below flagged
  as a known, documented-not-fixed limitation; on Linux with no `pwsh`, the
  real hook-runner behaviour remains unverified rather than assumed fine.
- **The `repo-plugins` install item (21) now detects a global `find-skills`
  collision instead of only documenting it.** If
  `~/.claude/skills/find-skills` exists — from menu item 5, or a direct
  `npx skills add vercel-labs/skills --skill find-skills` — the step warns
  that two active copies of `find-skills` can both trigger on the same
  prompt and prints the manual `rm -rf` to remove the global one. Detection
  only; it never deletes anything itself.
- **Menu item 22, `graphify` — off by default, no new flag.** Installs the
  `graphify` CLI (`uv tool install graphifyy`) and registers it
  **per-repository**, never globally, with `graphify install --project`.
  Reuses `--select` / `-Select` like every other item. Installing it alone
  does nothing; `crew`'s `crew-graph` skill and `/crew:upgrade` are what call
  it.
- **`--dry-run` / `-DryRun`.** Settles the selection, prints it, and stops without
  installing anything - the quickest way to see what a set of flags actually resolves
  to, and what `scripts/_test/menu-groups.sh` uses so a test run cannot reach `apt-get`
  or `npm install -g`.
- **Every menu row that installs more than one thing now has a sub-picker.** Only the
  repo's own skills row did; the team, community, VoltAgent and repo-plugin rows were
  all-or-nothing, so wanting one of the three team plugins, or two of the ten VoltAgent
  packs (154 subagents), meant taking the lot or editing the script. All five rows are
  now marked `>` in the menu, open their own picker on the right arrow, and carry a live
  `N of M` count. New flags for the non-interactive path, matching `--skills`:
  `--team` / `-Team`, `--community` / `-Community`, `--voltagent` / `-VoltAgent`,
  `--plugins` / `-Plugins`, each taking names, numbers, `all` or `none`. A name matches
  the plugin key or the short label the picker shows, so `--voltagent infra` and
  `--voltagent voltagent-infra` are the same thing. Naming items inside a row also
  selects that row - which is what makes `--plugins crew` work at all, since that row is
  off by default - but never overrides a choice made at the menu. Only the marketplaces behind a ticked plugin are registered now, so
  `--team excalidraw-generator` adds one marketplace instead of three. The five catalogs
  are the single source for the menu label, the picker, the flag and the install loop,
  so a row cannot say "3 of 3" and then install something else - all five, including the
  skills, go through one `install_group` / `Install-Group`. That also fixed a smaller
  thing: a marketplace behind several ticked plugins is registered once rather than once
  per plugin, so the community row no longer re-clones `claude-settings` three times.

- **Content-drift detection in both install scripts.** A version bump fixes today's
  staleness; this stops it recurring silently. For an already-installed plugin the
  scripts compare the commit its marketplace is on against the commit Claude Code
  recorded at install time, and then ask git whether *that plugin's* files changed
  between the two - one commit anywhere in a marketplace moves `HEAD` for everything it
  publishes, so this also keeps unrelated commits off the slow path. If the files did
  change and `claude plugin update` still copies nothing, that is the unbumped-version
  case, and the scripts now say so plainly instead of reporting the plugin as current.
  New `--force-refresh` / `-ForceRefresh` reinstalls such a plugin (`claude plugin
  uninstall --keep-data` then install), which is the only way to make the CLI re-copy it.
  Anything the check cannot answer - no `git`, no history, a commit pruned by a
  force-push - falls back to the previous CLI path. Regression suite:
  `scripts/_test/drift-detection.sh` (15 assertions over 7 scenarios, asserting on the
  bytes on disk and not only on what the script printed; sabotage-tested by
  reintroducing both original bugs).
- **`scripts/check-marketplace.py` + a `Marketplace` CI workflow.** Fails when a skill's
  files have changed since its version was last set - the bug above, caught in the repo
  instead of on users' machines - and checks every registration rule in `CLAUDE.md`:
  directories registered in `marketplace.json` and vice versa, required fields, `source`
  paths, no nested `marketplace.json`, `SKILL.md` frontmatter names matching their
  directories, `plugin.json` versions agreeing with the marketplace, the `SKILL_KEYS` /
  `SkillCatalog` catalogs in both install scripts matching in content and order, and a
  table row in each of the three catalog docs. Sabotage-tested against eight
  reintroduced faults. It also holds the two install scripts to `CLAUDE.md`'s rule
  that they are a matched pair: same menu keys, same order, same default flags, and
  the same entries in every sub-picker group - a mismatch there makes `--select 3,7`
  mean different things on Windows and Linux and silently invalidates every doc that
  names an item by number.
- **`scripts/check-powershell.ps1` + `scripts/_test/menu-groups.sh`.** The PowerShell
  script is Windows-only end to end, so a call to a function that does not exist parses
  cleanly, is never reached on a CI runner, and only fails on the one platform that
  matters - which is how a mis-named picker call got through review here and would have
  killed every sub-picker on Windows. `check-powershell.ps1` resolves every `Verb-Noun`
  call against the script's own functions and the available cmdlets, with a short,
  justified allowlist for names a runtime `Import-Module` supplies. `menu-groups.sh`
  covers the sub-picker catalogs, the `--<group>` spec parser and the parent-implication
  rule (32 assertions). Both were sabotage-tested; the menu suite caught a weakness in
  its own first draft, which asserted on the message a flag printed rather than on the
  row actually being installed.

### Fixed

- **Install scripts — installing this repo's skills took minutes, and every re-run
  warned about all of them.** Two problems compounded. First, `claude plugin update`
  was called with a bare plugin name; the CLI only accepts `name@marketplace` and
  rejects a bare name with `Plugin "<name>" not found`, so *every* update in a re-run
  failed and printed `'claude plugin update <name>' failed - keeping the installed
  version.` — 25 spawned CLI processes that could not have succeeded, plus 25 warnings
  that read like real breakage. Second, both scripts reloaded the entire plugin list
  (`claude plugin list --json`) after every single install, doubling the CLI spawns on
  a fresh run. `install_plugin` / `Install-ClaudePlugin` now compare the marketplace
  clone's HEAD commit against the commit Claude Code recorded for the installed copy
  (`installed_plugins.json`) and skip the update spawn entirely when they match, pass
  the fully qualified `name@marketplace` when they do not, and add a freshly installed
  plugin to the in-memory cache instead of re-reading the whole list. Both SHA lookups
  are file reads, and either one being unavailable (no `git`, an unreadable state file,
  a plugin installed from a different marketplace) reports "cannot tell" and falls back
  to the old CLI path. Measured on the 25-skill item: re-run 38.5s -> 5.8s, fresh
  install 51s -> 32s, and no spurious warnings.

- **`crew` 0.2.0 — the Windows hooks never ran.** `guard.sh` and `verify-gate.sh` exited 0
  on MSYS/MINGW to "defer" to `.ps1` twins, and the twins were registered with a
  `shell: powershell` field that Claude Code does not read — `verify-gate.ps1`,
  `context-watch.ps1` and `handoff-read.ps1` were referenced by nothing at all, and
  `handoff-write.ps1` did not exist. The net effect on Windows was a command guard that
  blocked nothing and a `Stop` gate that ran nothing, which reads as "the gate passed"
  rather than "the gate never ran". Each hook is now registered once as bash and hands
  control to its twin from inside the script (`crew_win_dispatch` in
  `hooks/scripts/_common.sh`, `exec` so stdin passes through); `handoff-write.ps1` has
  been written. Verified by test: `terraform apply -auto-approve` now exits 2 on Windows.
- **`crew` — the verification map silently skipped every root-level file.** `fnmatch` and
  PowerShell's `-like` both let `*` span `/`, so a `**/*.tf` rule demanded a literal slash
  and never matched `main.tf` — exactly the file a Terraform module keeps at its root.
  With `"unmapped": "fail"` that meant editing `main.tf` failed the gate *and* skipped
  fmt, validate and tflint. Both gate implementations now also test the `**/`-stripped
  form.
- **`crew` — a failing `Stop` check could pin the session.** `verify-gate.sh` never read
  stdin, so it could not see `stop_hook_active` and blocked its own retry. Both
  implementations now honour it.
- **`crew` — `python3` was a hard dependency** of five hook scripts, and Git Bash ships
  without it. They now resolve `python3`, then `python`, then `py`; `guard.sh` prefers
  `jq`. With none available the hook says so on stderr instead of failing open silently.
- **`crew` — `terraform-docs .` in the gate edited the tree it was gating.** The writing
  form rewrites `README.md`, making it a changed file with no rule on the next run, which
  trips `unmapped: fail` on the gate's own edit. Every example now uses
  `--output-check`, which fails on a stale README and writes nothing.
- **`crew` — `$LASTEXITCODE` was read after `Invoke-Expression`** in `verify-gate.ps1`.
  A cmdlet leaves the previous value in place, so a stale 0 read as a pass. It is now
  reset before each command and `$?` is checked alongside it.
- **`crew` — dead agent frontmatter.** `effort: high` (2 files) and `memory: project`
  (6 files) are not part of the subagent schema and were silently ignored, so
  `qa-reviewer` was not running at the high effort its file claimed. Removed.

- **`crew` — the command guard was judging bash with PowerShell rules on Windows.**
  Found by the second QA pass, and introduced by the first: dispatch branched on the
  OS, so a `Bash` tool call on Windows was handed to `guard.ps1`. That inverted the
  secret rule in both directions - it blocked the correct capture form
  (`DB_PASS=$(...)`) and let `vault kv get ... > secret.txt` through. Dispatch now
  branches on `tool_name`, which is what actually determines the language a command is
  written in. The other five hooks judge no command, are reached through `bash`, and
  no longer branch at all.
- **`crew` — the secret rule treated persistence as an exemption.** A `>` redirect or a
  `| tee` marked a command safe, so writing a secret to disk passed while printing one
  blocked - and the block message recommended a form the guard itself rejected. Both
  now block; the only exemption is assigning to a variable.
- **`crew` — the production guard matched `prod` as a substring**, blocking
  `aws s3 ls s3://my-product-images`, `select * from products` and
  `reproducible-builds`. Now a whole-token match. A guard people route around is not a
  guard.
- **`crew` — an ERE portability bug made the capture allowlist match nothing.** `\(`
  is a literal paren in POSIX ERE but a group opener in some greps ("Unmatched ( or
  \("). Bracket expressions are used instead.
- **`crew` — the verify loop could eat its own command list.** `eval "$c"` shared stdin
  with the `while read` over the here-string, so a check that reads stdin silently
  consumed the remaining checks. Now `</dev/null`.
- **`crew` — `context-watch.sh` called `python3` directly in six places**, every one
  suppressed with `2>/dev/null`, so on a host with only `python` the context warning
  silently never fired. It resolves once through `crew_py` and says so on stderr if
  there is none.
- **`crew` — `claude-md-audit.sh` required bash 4.** `declare -A` is a parse error on
  macOS's stock bash 3.2. Rewritten without associative arrays or process substitution.
- **`crew` — `_verify/run-all.sh --read-only` used a denylist.** An unmarked case ran
  against production; only a self-declared `# writes: yes` skipped it. It is now an
  allowlist - a case runs under `--read-only` only if it declares `# readonly: yes`,
  and skips are reported.
- **`crew` — `git branch --show-current` needs git 2.22+**, and the `|| echo 'not a git
  repo'` fallback made an older git look like a missing repo. Uses `rev-parse
  --abbrev-ref HEAD`.

- **`crew` — `/crew:reference`, the API and feature reference.** The code map answers
  "where does this live"; nothing answered "what can this system do, and how do I call
  it". `docs/reference/api.md` enumerates every endpoint with its auth, body, returns,
  **side effects, error responses and idempotency** - the parts that are not guessable
  from the name - and `docs/reference/features.md` covers the headless capabilities
  nobody documents: scheduled jobs and what a missed run does, queue consumers, admin
  scripts, feature flags. Every entry is anchored to `file:line` so it can be
  re-verified, `--audit` reports drift in both directions without rewriting anything,
  and unconfirmed entries are left visible as `undocumented - needs a human`. Wired
  into `/crew:onboard` as the second of four artifacts and owned by `crew:docs-writer`.

- **`crew` — promotion is now enforced by a hook, not by instructions.**
  `promote-gate.sh` (`PreToolUse`) fires on any command matching a declared `deploy`
  entry and refuses it unless, for the sha at HEAD, every `requires` environment has an
  all-pass row in `.work/PROMOTIONS.md`, the `rollback` runbook exists with
  `last verified` inside 90 days, `requireHuman` has an approval marker, and the tree is
  clean. `verify-gate.sh` additionally refuses to end a turn after a deploy that wrote
  no promotion row. What a hook still cannot see is the middle - that smoke, regression
  and verify actually ran after the deploy - and `/crew:promote` now says so explicitly
  rather than implying coverage.
- **`crew` — `resolve-tools.sh`: platform detection that adapts instead of just
  reporting.** It reads `.crew/verify.json`, extracts the first word of every command,
  and reports each tool as native, WSL-only, or missing. The WSL-only case is the
  expensive one: a bare `terraform validate` on a machine where terraform lives only
  inside WSL fails with "command not found", and the gate reports that as a *failed
  check* rather than a missing tool. Resolve once at setup, write `wsl.exe -e terraform`
  into the map, never branch at runtime.
- **`crew` — two more committed suites.** `setup-walkthrough.sh` builds a mixed-stack
  scratch repo and runs every script phases 0-8 invoke (32 assertions);
  `validate-prompts.py` checks all 16 commands, 9 agents and 14 skills for frontmatter
  that parses, tools that exist, referenced agents and paths that resolve, read-only
  agents that hold no write tools, and subagent-spawning commands that are permitted to
  (91 checks). Both sabotage-tested. Neither proves the prompts produce good work -
  only a live session on a real ticket does that.

- **`crew` — a committed regression suite for the hooks**,
  `hooks/scripts/_test/run-tests.sh`. 38 cases: 20 the command guard must block, 14 it
  must allow, plus the verify gate's root-level glob matching and its
  `stop_hook_active` exit. `guard.sh` shipped two real regressions in two review
  passes and both were found by running it rather than reading it, so the suite is
  itself sabotage-tested — reintroducing the substring `prod` match, the `>`-as-
  exemption secret bug, or removing the stop-loop check each turns it red.

### Removed

- **`crew` — `skills/crew-setup/templates/smoke.sh`**, orphaned by the `_verify/`
  restructuring and diverging from the new `--env`-aware interface.
- **`crew` — four duplicate trees.** `docs/README.md` was byte-identical to `README.md`;
  `examples/` was byte-identical to `skills/crew-setup/` and referenced by nothing;
  `docs/crew-howto.pdf` was a third copy of the README in an undiffable format; and
  `plugin/crew/.claude-plugin/marketplace.json` was a stub naming a nonexistent source,
  which this repo's `CLAUDE.md` already forbids. ~380 KB, no functional change.

### Added

- **`crew` — `/crew:promote <development|qa|production>`, with `--dry-run` and
  `--status`.** Promotion runs as five separate gates — pre-deploy, deploy, smoke,
  regression, post-soak verify — stopping at the first failure. Smoke and regression are
  deliberately distinct: smoke passing tells you the deploy landed and says nothing about
  the module three directories over that just broke. The sequence is declared in an
  `environments` block in `.crew/verify.json` rather than remembered, production requires
  a rollback runbook verified inside 90 days and explicit human approval, and every
  promotion appends a row — failures included — to `.work/PROMOTIONS.md`, which is the
  only honest answer to "is production running what qa signed off on". New setup Phase 8
  builds the block by asking what actually deploys each environment and what actually
  proves it worked.
- **`crew` — `_verify/` as the canonical home for checks.** Setup looks for `_verify/`
  first (then `qa/`, `spec/`, `_test*/`) and adopts an existing convention rather than
  duplicating it; where none exists it creates `_verify/` from a template carrying
  `README.md`, `smoke.sh`, `run-all.sh` and `cases/`. The README is part of the
  deliverable: a layout table for what each check covers and a status table for when each
  last proved it could fail. `/crew:verify` cross-checks it against `.crew/verify.json`
  and reports drift both ways — a script with no rule never runs, and a rule naming a
  script the README omits is a check nobody knows about. `scripts/smoke.sh` is still
  honoured; the gate checks `_verify/smoke.sh` first and falls back.
- **`crew` — promotion discipline in the CLAUDE.md templates.** Both the generic and the
  Terraform template now carry the judgment half: the fixed `development -> qa ->
  production` order, the same sha through all three, smoke *and* regression *and*
  post-soak verification after every deploy, no production deploy without a verified
  rollback, and a failed gate restarting the whole sequence rather than resuming.

- **A `plugin/` tree, and the `crew` plugin in it — the repo's first entry that is a
  plugin rather than a skill.** `crew` 0.2.0 is a virtual dev team for multi-repo legacy
  work: 9 context-isolated subagents, 16 slash commands, 14 bundled skills, and 7 hooks
  across 5 events (`PreToolUse`, `Stop`, `PreCompact`, `SessionStart`, `Notification`).
  Beyond the safety gates it now carries a handoff note across a `/clear` or an
  auto-compact, and watches context use. Roles
  exist only where they buy an isolated context window, a restricted tool set, or
  genuinely independent eyes — project management, BA, and architecture are files and
  commands, not agents. Codex QA, Jira, Obsidian memory, and Teams/Telegram notifications
  are all optional. Registered in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)
  with `source` `./plugin/crew`, so `claude plugin install crew@useful-claude-add-ons`
  works the same way a skill install does.
- **`plugin/README.md` — the plugins counterpart to `skills/README.md`**, with the same
  five-column overview table, inlined into the root `README.md` between
  `<!-- BEGIN plugin/README.md -->` markers exactly as the skills table is. It leads with
  the distinction that actually matters: a skill is a document Claude reads, whereas a
  plugin can register subagents, slash commands, and **hooks** — and a hook runs whether
  or not Claude agrees with it.
- **`plugin/PLUGINS.md` — the per-plugin reference the catalog points at.** `skills/` gets
  away with one file because a skill is one `SKILL.md`; a plugin is a bundle, so the
  catalog row cannot carry the detail. This is where every command, agent, bundled skill,
  and hook is listed, with the hooks first, because they are the only part that runs
  without being asked. It also records what is *not* wired: only `PreToolUse` pairs a
  `.sh` with a `shell: powershell` twin, so `verify-gate.ps1`, `context-watch.ps1`, and
  `handoff-read.ps1` sit on disk unreferenced and the `Stop` gate never fires on a
  Windows box with no `bash` on `PATH`. Documented rather than fixed — it is a change to
  `crew`'s runtime behaviour, not to its packaging.
- **Menu item 21, `This repo's plugins`, in both bootstrap scripts — off by default.**
  Appended at the end of the menu so items 1–20 keep their numbers and no existing
  `--select 3,7` invocation changes meaning. New `PLUGIN_KEYS` / `PLUGIN_NAME` arrays in
  the `.sh` and `$script:PluginCatalog` in the `.ps1` mirror the skill catalogs. The item
  adds this repo's marketplace itself, so it stands alone whether or not item 3 ran, and
  finishes by printing the per-repository setup (`/crew:init`, `/crew:onboard`,
  `/crew:verify`). It is unticked by default *on purpose*: every other menu row installs
  something Claude may choose to use, whereas `crew`'s `PreToolUse` hook blocks
  `terraform apply`/`destroy`, destructive DDL, force push, hard reset, and any command
  that would print a secret, and its `Stop` hook fails a turn whose checks go red. Those
  are deterministic and start the moment the plugin is enabled, which is not something a
  bootstrap run should add without the box being ticked.
- **A plugin registration rule in `CLAUDE.md`**, alongside the existing skill rule: the
  same four places, plus two that only apply to plugins — a hook-bearing plugin defaults
  to OFF in the menu, and every hook script ships in both `.sh` and `.ps1` flavours,
  because a bash-only hook is silently inert on Windows and reads as "the gate passed"
  rather than "the gate never ran".

### Fixed

- **Section-comment numbering in both install scripts had drifted by one from item 14
  onward** — `obsidian-mcp` was inserted at position 14 without renumbering the comments
  below it, so the block installing menu item 20 was labelled `# --- 19. Obsidian`.
  Comment-only; no behaviour change. Verified by parsing `MENU_KEYS`/`MENU_DEFAULT` out
  of the `.sh` and `$script:Catalog` out of the `.ps1` and diffing them: 21 keys each,
  same order, same defaults.

### Changed

- **`plugin/crew/.claude-plugin/plugin.json` no longer ships placeholder metadata** —
  its author was `{ "name": "you" }`. It now carries the repo's owner, homepage, and
  repository. A stray `plugin/crew/.claude-plugin/marketplace.json` naming a marketplace
  `my-marketplace` owned by `you` was removed: the repo root's marketplace is the only
  one here, and a nested one makes the plugin directory look like a second marketplace.

- **`claude-memories-vault` and `claude-memories-canvas` skills — the conventions of the
  `claude-memories` Obsidian vault, written on the workstation during the 2026-08-19
  memory migration and only now given a canonical home.** `claude-memories-vault` covers
  the folder layout, the six required frontmatter fields, the `type`/`status` value sets
  the `HOME.md` Dataview queries filter on, how wikilinks resolve by *filename* on Windows
  (a `:` cannot appear in one, so the link must match the file and not the prose), the
  `vault-lock.ps1` write lock the nightly gardener respects, the single-writer rule on
  `inbox/pending-reflect.md`, and the decision rule for vault versus Claude Code
  auto-memory. `claude-memories-canvas` covers the `wiki/maps` node and edge schema
  actually in use, the colour and id styles, the column-and-group geometry, and the two
  rules that make a canvas findable at all: facts live in notes because a canvas-only fact
  is invisible to search, and every canvas is linked from its `Project - *.md` because
  canvases do not backlink.

  Both keep the concrete `C:\repos\claude-memories` path rather than a placeholder — the
  same choice `vault-automation/` already makes with its `-VaultPath` default — because
  these are the conventions of one real vault and a parameterised version has never been
  tested. Both name their siblings explicitly in the `description`: the generic
  `obsidian-canvas` for any other vault, and `obsidian-vault-server` for hosting one.
  `obsidian-canvas` gained a matching one-line pointer back.

- **`obsidian-vault-server` skill — a self-hosted Obsidian vault on a headless Ubuntu
  host.** The real Obsidian desktop app in a container (Sync has no headless client, so
  there is no other way), signed in to an obsidian.md account, with the
  `obsidian-local-rest-api` plugin's built-in MCP endpoint reached over an SSH tunnel —
  no separate MCP server process. Three references cover install, the Claude wiring, and
  getting a workstation's plugins onto the server. The safety rails are the point: the
  container's web GUI has a terminal with passwordless `sudo`, so the skill treats
  firewalling it and never overwriting the REST API key as non-negotiable rather than
  advisory.

- **`claude-obsidian-setup/` now installs the Obsidian community plugin set.** The setup
  scripts installed *Claude Code* plugins but never the Obsidian plugins a working vault
  needs. `obsidian-plugin-profile.json` pins 15 community plugins with their repos plus
  the 27 core plugins to enable, and `install-obsidian-plugins.ps1` / `.sh` install them
  from GitHub releases. Same house contract as the setup scripts: dry run by default,
  `--apply` / `-Apply` to write, PASS/FIX/FAIL against stable check ids, idempotent.
  Additive — `community-plugins.json` and `core-plugins.json` are unioned with whatever
  the vault already enables, in both the list and object-map shapes. Verified on both
  platforms: 15/15 at pinned versions, second run all PASS, pre-existing entries kept.

- **Menu item: `obsidian-mcp` — register the Obsidian vault server's MCP endpoint.** Off
  by default, on both scripts, with identical keys and order. Not a launched command: the
  endpoint is a plugin already running in the vault-server container, listening on the
  *server's* loopback, so the URL is a local port forwarded by SSH. The API key is
  per-deployment and cannot be baked in, so without `-ObsidianMcpKey` /
  `--obsidian-mcp-key` the item explains how to get one and skips rather than failing.
  `Add-McpServer` / `add_mcp_http_server` gained header support for the bearer token.

- **`vault-automation/` — self-feeding vault pipeline.** New component that automates
  the Obsidian memory loop end to end: Claude Code `SessionEnd`/`PreCompact` hooks
  queue every session into `inbox/pending-reflect.md`; a nightly `Claude Vault
  Gardener` scheduled task runs headless Claude to distill queued sessions into
  source-cited `wiki/concepts` pages and `wiki/daily` digests (with a provenance pass
  that promotes well-attested concepts); a `HOME.md` Dataview dashboard surfaces
  stale/unsourced concepts and the live queue; five community plugins installed
  file-level. Obsidian-Sync-aware: git is an optional layer (`-UseGit`/`-GitRemote`)
  and the gardener skips git operations on git-less vaults. Dry-run by default,
  idempotent, documented in `vault-automation/README.md` (incl. run-the-gardener-on-
  one-machine-only and cost/safety notes). Root README gained a "Vault automation"
  section with the run commands.

### Fixed

- **`install-prerequisites.sh` aborted on startup with `MENU_DEFAULT[$_i]: unbound
  variable`.** The `obsidian-mcp` menu item was added to `MENU_KEYS` but never to the two
  arrays that run parallel to it, leaving 20 keys against 19 defaults and 19 names. Under
  `set -u` the `MENU_STATE` initialiser walked off the end of `MENU_DEFAULT` and killed
  the script before it drew anything, so *no* item could be installed on Linux — not just
  the Obsidian one. `MENU_NAME` was short in the same way, and because the gap sat at
  index 13, every label from `obsidian-mcp` onward was displaying the *next* item's text:
  row 14 read "Supabase plugin", row 19 read "Strix", and row 20 had no label at all.
  Both arrays now carry all 20 entries, matching `$script:Catalog` in the `.ps1` key for
  key, name for name, and default for default.

  The menu-numbering fallout was documentation-only but wide: `README.md` and
  `INSTALLATION.md` both still described a 19-item menu, so every reference to items
  14–19 was off by one from the moment `obsidian-mcp` landed. Renumbered to 15–20, with
  the item itself now documented in the menu table, the "what each item installs" table,
  the MCP-servers walkthrough, and the switch table — `--obsidian-mcp-url` and
  `--obsidian-mcp-key` had never been listed there either.

- **The installers' skill catalogs had fallen two skills behind the marketplace.**
  `obsidian-canvas` and `obsidian-vault-server` were registered in
  `.claude-plugin/marketplace.json` and `skills/README.md` but never added to
  `SKILL_KEYS`/`SKILL_NAME` in `install-prerequisites.sh` or `$script:SkillCatalog` in
  the `.ps1`, so the per-skill picker offered 21 of the 23 that existed and neither could
  be selected by name. Both were also missing from the `<!-- BEGIN skills/README.md -->`
  mirror in the root `README.md`, which had silently stopped being a mirror. Both are in
  the catalogs and the mirror now, alongside the two new
  `claude-memories-*` skills, and the hard-coded counts in `README.md` and
  `INSTALLATION.md` — plus the stale "all nineteen" in both installer headers — now read
  25, matching the directory count, the marketplace manifest, and both catalogs.

- **`claude-obsidian-setup` — a Python below the 3.11 floor is now repaired rather than
  only reported.** Both scripts previously stopped with "install python3.11+ yourself" on
  any distro whose `python3` predates 3.11. That was over-broad: it treated the hardest
  case as if it were the only one. They now, in order, (1) use a newer versioned
  interpreter that is already installed, (2) install one — `python3.13`/`3.12`/`3.11` —
  from the repositories **already configured on the machine** and use it alongside the
  untouched system `python3`, or (3) stop with the concrete remedy. `update-alternatives`
  is never touched and no third-party repository is ever added, so the original objection
  still applies to the only case it was ever true of.

  Every downstream invocation now runs through a selected-interpreter variable rather than
  a hardcoded `python3`. Verified by putting a stub `python3` reporting 3.10 first on
  `PATH`: the script found the real `python3.12`, used it, and produced a complete 14-file
  vault with `doctor ok` and `lint 0 issues`.

- **`claude-obsidian-setup/setup-claude-obsidian.sh` creates the product checkout's parent
  explicitly.** `git clone` does create missing parents — this was verified, and the review
  finding that claimed otherwise was wrong — so nothing was broken. The `mkdir -p` removes
  the dependency on that behaviour and makes an unwritable root fail obviously.

### Added

- **Menu item 19 — Obsidian desktop + `claude-obsidian` and `obsidian-skills`
  plugins.** Off by default, on both scripts, with identical keys, order, and default
  flags. The app is not on npm, so it installs from a package manager: Chocolatey then
  winget on Windows, flatpak then snap on Linux — distro repositories generally do not
  carry it. Chocolatey needs elevation; without it the app is skipped with a warning and
  the two plugins still install. The item then registers
  `AgriciDaniel/claude-obsidian` (the vault engine: transactional writes, provenance
  ledgers, deterministic lint, the `/claude-obsidian:*` skills) and
  [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) (Obsidian's own
  upstream references for Obsidian Flavored Markdown, Bases, JSON Canvas, the Obsidian
  CLI, and Defuddle).

  The item deliberately stops there. Creating a vault writes to disk under a reviewed
  transaction, so it is a separate, explicitly previewed step rather than a side effect
  of a bootstrap run. `--obsidian-repo-root` / `-ObsidianRepoRoot` sets the root the item
  suggests for it (default `C:\repos` on Windows, `~/repos` on Linux).

- **`claude-obsidian-setup/` — vault setup for Windows (WSL) and Linux.** A matched pair
  of installers that bring both platforms to the same claude-obsidian standard, plus a
  README. Dry-run by default, idempotent, `PASS`/`FIX`/`FAIL` per check against stable
  check ids, non-zero exit on failure, and a closing `doctor` + `lint` against the new
  vault. Vault creation follows the product's own preview-then-apply contract: run the
  plan, read back its `approved_plan_sha256`, pass that exact hash to `--apply`.

  Everything hangs off one root — `C:\repos` / `~/repos` — so `-RepoRoot` /
  `--repo-root` relocates the vault and the product checkout together;
  `-VaultPath`/`--vault` and `-ProductRoot`/`--product` override either half.

  The Windows script exists mostly to repair four failures that are otherwise silent and
  hard to diagnose:

  1. **Native Windows cannot write to a vault at all.** Mutation safety is bound to POSIX
     directory descriptors and `fcntl.flock`; native Python has no `fcntl`, so the core
     refuses every write with `UNSUPPORTED_PLATFORM`. Reads and dry-runs work natively —
     writes are routed through WSL, which is why the vault is created from inside it.
  2. **`python3` resolves to a Microsoft Store stub.** Windows ships no `python3.exe`, so
     the name hits the App Execution Alias and prints an install advert instead of running
     Python — breaking the plugin's `SessionStart`/`Stop` hooks and every documented
     `python3 …` command. Fixed with a hard link `python3.exe → python.exe`.
  3. **`/mnt/c` mounts without `metadata`.** DrvFs then rejects `chmod` with `EPERM` and
     every apply dies with `CORRUPT_RUNTIME_STATE: cannot write confined bundle copy`.
     This cannot be fixed by remounting live; it needs an `[automount]` stanza in
     `/etc/wsl.conf` and a full `wsl --shutdown`. The existing file is backed up first.
  4. **Git identity does not cross the WSL boundary.** `checkpoint` runs inside WSL, where
     Windows' `git config --global` is invisible, so it fails `GIT_FAILED: Author identity
     unknown`. Fixed by setting identity repo-locally, which both environments read.

### Fixed

- **Both install scripts — Superpowers came from a second marketplace and could land
  disabled.** Item 4 registered `obra/superpowers-marketplace` unconditionally, but
  `install_plugin` / `Install-ClaudePlugin` detect plugins by *bare name*. On any machine
  that already had `superpowers@claude-plugins-official` — which items 6 and 7 register —
  the install was skipped, leaving an orphaned `superpowers-marketplace` registration and
  a second, disabled `superpowers@superpowers-marketplace` entry: exactly the duplicate
  [`skills/claude-code-tuneup`](skills/claude-code-tuneup/references/symptoms.md) tells you
  to clean up. Item 4 now takes Superpowers from `anthropics/claude-plugins-official`, the
  marketplace the scripts already register elsewhere, so there is one source for it.

  Superpowers for Claude Code is plugin-only by design and cannot be installed by copying
  `skills/` into `~/.claude/skills/`: its `SessionStart` hook resolves
  `${CLAUDE_PLUGIN_ROOT}`, which only exists for plugins, and that hook is what injects
  `using-superpowers` and makes the other skills fire. Six of the fourteen skills also
  cross-reference each other as `superpowers:<name>`, which unprefixed personal skills
  would break.

  Existing machines keep the stray `superpowers-marketplace` registration — the scripts
  deliberately do not remove marketplaces, since a bootstrap installer should not delete
  something a user may have added on purpose. Drop it with
  `claude plugin marketplace remove superpowers-marketplace`.

- **Both install scripts — an installed-but-disabled plugin is now switched back on.**
  Installing a plugin and having it load are different things: a plugin disabled in
  `settings.json` is installed, at the right scope, and completely inert. New
  `ensure_plugin_enabled` / `Enable-ClaudePlugin` run on the *already-installed* paths
  (update and already-current skip) and call `claude plugin enable --scope` when no enabled
  copy of the name exists. Best-effort by design — the plugin is installed either way, so a
  failure warns instead of failing the step.

  **Not** called after a fresh install: `claude plugin install` already enables what it
  installs. The first cut of this called it there too, which broke a brand-new machine —
  a just-installed plugin can still read as disabled in `claude plugin list --json`, so
  every plugin in the run got an enable attempt, and the CLI's benign "already enabled at
  user scope" reply was reported as a failed step. 18 of them on one run.

  Three separate defects behind that, all fixed:

  - `Enable-ClaudePlugin` used `2>$null` with no `try`/`catch`. Under
    `$ErrorActionPreference = 'Stop'` a native command's stderr line — or any non-zero exit
    when `$PSNativeCommandUseErrorActionPreference` is `$true` — becomes a *terminating*
    error, so `Invoke-Step` marked the step failed. The same hazard is already documented
    at the Claude Code update check. Both preference variables are now shadowed
    function-locally, and the whole call is wrapped, so this function cannot throw.
  - Success was judged from the CLI's message. It can't be: `claude plugin enable` reports
    "is already enabled at user scope" even for a plugin that does not exist. Both scripts
    now judge the outcome from `claude plugin list --json` instead.
  - The bash version was a silent no-op. `local spec="$1" name="${spec%%@*}"` doesn't work
    — bash declares every name in a `local` before expanding the values, so `$spec` read
    the empty new local and `name` was always empty. Assigned on its own line now, matching
    the existing style in `install_plugin`.

- **`install-prerequisites.ps1` — a disabled duplicate could mask an enabled plugin.**
  `Get-ClaudePlugins` keys its map on the bare name with last-write-wins, so with both
  `superpowers@claude-plugins-official` (enabled) and `superpowers@superpowers-marketplace`
  (disabled) installed, the disabled copy won on id sort order and the plugin was reported
  as disabled. An enabled entry now wins over a disabled one.

- **`install-prerequisites.sh` — `json_query` output is stripped of trailing `\r`.** Under
  Git Bash / WSL interop on Windows both `jq` and `python3` emit CRLF, leaving a stray
  carriage return on the last tab-separated field. Every caller compares that field exactly
  (`"$enabled" = "1"`, `"$repo" = "$id"`), so `marketplace_installed` could miss a
  marketplace matched by repo, and the new enablement check read every plugin as disabled.

### Added

- `skills/notify` — **two-way Telegram now works in both directions.** `--wait` only ever
  covered replies to a question Claude asked; a message the user sent on their own
  initiative was thrown away twice over. The dispatcher's `_on_message` dropped anything
  that matched no pending question, and direct mode fast-forwarded its `getUpdates`
  offset past everything already queued before it started listening — so a message typed
  while Claude was busy, or between questions, was silently discarded.

  New `scripts/inbox.py` is the store both halves share: `<spool>/inbox.jsonl` for
  inbound messages and `<spool>/state/offset.json` for the `getUpdates` offset. The
  offset has to be shared rather than per-process because Telegram answers a second
  concurrent `getUpdates` with `409 Conflict` — the daemon owns polling when it is up,
  the client polls only when it is not, and either way the next read resumes where the
  last one stopped.

  `notify.py --inbox` hands Claude what is waiting (exit 0 with messages, 5 without, so
  it works as a "did they say anything?" check in a loop), `--peek` leaves them
  unconsumed, `--wait` blocks for up to `--timeout` seconds, and `--job` filters to one
  topic. A read consumes what it returns, so no message is delivered twice. In topics
  mode the arriving thread is reversed through `topics.json` to attribute the message to
  the right job.

  Appends guard against a fused record: a write killed mid-line leaves no trailing
  newline, and appending onto it would produce one unparseable line and lose the *new*
  message as well as the broken one, so `append()` closes the dangling line first.

- `skills/claude-code-tuneup` — audits a Claude Code installation for what is making it
  slow or bloated and hands back a ranked cleanup plan. `scripts/cc_audit.py` (stdlib
  only, read-only) inventories every settings file in scope, loose skills in
  `~/.claude/skills/` against skills provided by installed plugins, `enabledPlugins`,
  hooks from both settings *and* every plugin's `hooks/hooks.json`, subagents, rules
  files, `CLAUDE.md` sizes, MCP servers, marketplaces, and the plugin cache.

  It catches the duplicate-install case in **both** plugin layouts — a plugin bundling
  `skills/<name>/SKILL.md`, and a plugin whose root *is* the skill, which is what this
  repo's own marketplace publishes. Missing the second layout is why a naive check finds
  none of this repo's skills duplicated. Duplicates are labelled
  `plugin@marketplace`, because the same plugin name published by two marketplaces is
  exactly the case worth catching, and a loose copy shadowing a *disabled* plugin is
  reported separately from one shadowing an enabled plugin — only the latter costs
  context.

- **Menu item 9 (claude-mem) now installs Bun.** claude-mem's hooks run its worker under
  Bun (`package.json` declares `engines.bun >= 1.0.0`) via `scripts/bun-runner.js`, which
  resolves the interpreter with `where`/`which bun` and only then falls back to
  `$HOME/.bun/bin/bun`. Neither install script ever installed it and the plugin's own
  hooks cannot bootstrap it, so on a fresh machine every claude-mem hook failed with
  "Bun not found". Windows uses `choco install bun` when Chocolatey is present *and* the
  run is elevated — the shim lands a real `bun.exe` on `PATH`, which is what
  `bun-runner.js` looks for first — and falls back to bun's per-user installer
  otherwise, since that needs no Administrator rights and writes the documented
  fallback path. Linux prefers `npm install -g bun` (keeping bun on the same `PATH` as
  node) and falls back to `bun.sh/install`; no distro ships a bun package, so there is
  no `as_root` path. Both halves detect first: an existing bun, however it was
  installed, is left alone.

### Removed

- **Perplexity MCP server** — dropped from both install scripts. It was menu item 13
  (off by default), the only row that needed an API key, so the whole up-front key
  prompt goes with it: `read_mcp_api_key` / `read_mcp_api_keys` and `PERPLEXITY_KEY`
  in the `.sh`, `Read-McpApiKey` / `Read-McpApiKeys` and `$script:ApiKeys` in the
  `.ps1`. Every remaining row now installs without asking for anything mid-menu.

  **Menu numbers below it shift by one on both platforms**: MCP servers are 11–13,
  Supabase 14, Context7 15, Playwright CLI 16, SkillUI 17, Strix 18. Scripted runs
  that pass positions (`--select 15,19`) need updating; the stable keys
  (`--select supabase,strix`) were unaffected and remain the better habit. The
  `perplexity-mcp` key itself is gone, so a run that names it now selects nothing for
  that token. An already-registered `perplexity` server is left alone — remove it by
  hand with `claude mcp remove perplexity` if you want it gone.

- `skills/ppt-master` — a vendored copy of the upstream `hugohe3/ppt-master` plugin
  (12,230 files, 88 MB) that was never registered in `marketplace.json`, either
  README, or either install script's skill catalog, so nothing here ever offered it.
  The installer already installs the same plugin from its own marketplace as part of
  menu item 6 (Community marketplaces + plugins), so removing the copy changes nothing
  for anyone running the bootstrap — it just stops the repo carrying 88 MB of upstream
  code it would have to re-sync by hand. This also clears the Pylint CI failure: 845
  of the 855 findings were in that tree.

### Added

- `skills/notify` — **a body over Telegram's 4096-character limit now splits across
  several messages** instead of failing the send. `tg.split_body()` breaks on a
  newline where it can, then a hard cut, and it splits the *raw* text before
  HTML-escaping so a break can never land inside an `&amp;` entity and invalidate
  the message. Whitespace is preserved exactly — rejoining the parts reproduces the
  input byte for byte. Parts are headed `(1/3)`, `(2/3)`, …

  The budget is computed against the **assembled** message, not the body chunk
  alone. Each part carries a `<b>subject (cont.) (2/3)</b>` header, the subject is
  caller-supplied, and escaping can grow it 5×, so a fixed reserve was not enough —
  a 300-character subject produced a 4,346-character message that Telegram would
  have rejected. The header cost is now measured per call and a pathological subject
  is truncated rather than eating the whole budget.

  Buttons go on the last part only, and `send_message()` returns that last message,
  so `notifyd`'s `message_id → req_id` correlation still resolves a button tap or a
  reply to the final part. Replying to an *earlier* part is not indexed and falls
  back to the newest open question in that topic. Parts are spaced one second apart
  to stay under Telegram's per-chat rate limit; `--dry-run` reports the part count.

### Fixed

- `skills/notify/scripts/notify.py` — stdout and stderr are reconfigured to UTF-8 with
  `errors="replace"` at startup. On a Windows console (cp1252) printing a body that
  contained any non-ASCII character — an em dash, an emoji, non-Latin text — raised
  `UnicodeEncodeError` and killed the run, which made `--dry-run` unusable for exactly
  the messages worth checking before sending.

- `skills/notify/scripts/*.py` — the four config reads now pass `encoding="utf-8"` to
  `Path.read_text()`. Without it Python picks the locale encoding, which is cp1252 on
  Windows, and a UTF-8 `config.json` then fails in one of two ways depending on the
  character. Most non-ASCII text decodes silently wrong: an em dash (`E2 80 94`)
  becomes `â€”` in the message that gets sent. Text whose UTF-8 bytes include one of
  the five undefined cp1252 positions (`81 8D 8F 90 9D`) raises `UnicodeDecodeError`
  and takes the run down — Japanese `あ` is `E3 81 82`, so a config with CJK in it
  crashes outright. Both are Windows-only. Also split the comma-form imports and
  wrapped two over-length lines, so `pylint $(git ls-files '*.py')` is back to
  10.00/10.

### Added

- `skills/notify` — a new skill (1.0.0) that pings you out of band about a session or
  job: a two-way Telegram bot (a `question` event blocks until you reply from your
  phone, and a `notifyd` dispatcher gives each concurrent job its own forum topic) or
  email over SMTP or an M365/Gmail MCP connector. Registered in `marketplace.json`,
  both READMEs, `INSTALLATION.md`, and both install scripts, taking this repo's
  catalog from 19 skills to 20.

- `scripts/install-prerequisites.ps1` / `.sh` — **the `notify` skill asks about setup.**
  It is the only skill here that needs anything on the machine, so ticking it prints
  its prerequisites alongside the menu (Python 3.8+, a `@BotFather` token, a `chat_id`,
  `TELEGRAM_BOT_TOKEN` exported, a config file, polling mode with no webhook) and then
  asks whether to scaffold `~/.config/notify/config.json`. Answering yes checks for
  Python and writes a starter config; it never overwrites an existing one and never
  writes the bot token anywhere. `--notify-setup` / `-NotifySetup` answers yes without
  asking; `--all` / `--non-interactive` prints the prerequisites and skips the
  scaffold. Because `notify` is a sub-picker entry rather than a top-level menu key,
  the gate reads the skill catalog (`skill_selected` / `Test-SkillSelected`) instead of
  `is_selected` / `Test-Selected`, which would never match.

- `CLAUDE.md` — repo-level instructions for Claude Code. Two documentation rules are
  stated as requirements rather than suggestions: an edit to either install script
  must update `README.md` (menu table, "what each item installs" table, switch table,
  and any prose that names an item by number) in the same change, and a new directory
  under `skills/` is not finished until it is registered in all four places —
  `marketplace.json`, `skills/README.md`, `README.md`, and both install scripts.

- `scripts/install-prerequisites.ps1` / `.sh` — **the Claude Code CLI row now checks
  for an update** when `claude` is already installed, instead of reporting the version
  and moving on. It compares the local version against the npm registry and runs
  `npm install -g @anthropic-ai/claude-code@latest` only when they differ. The version
  is read from the last line of `claude --version` (which prints
  `2.1.226 (Claude Code)`, and can be preceded by a wrapper's banner).
  `-NoUpdate` / `--no-update` reports the installed version and skips the check.

- `scripts/install-prerequisites.ps1` / `.sh` — **five new opt-in menu items**:
  - **Supabase** (15) — `supabase@claude-plugins-official`, through the same
    detect-then-install helper as every other plugin.
  - **Context7** (16) — `npx -y ctx7@latest setup`. The wizard is interactive, so bash
    hands it the terminal explicitly (under `curl | bash`, fd 0 is still the script);
    with no terminal at all both scripts print the command rather than hang.
  - **Playwright CLI** (17) — `npm install -g @playwright/cli@latest`, detected by
    whether `playwright-cli` already resolves on `PATH`.
  - **SkillUI** (18) — `skillui`, plus `playwright` and its Chromium build. Playwright
    is installed **globally**; upstream's `npm install playwright` would leave a
    `node_modules` tree in whatever directory the script was run from. Both Playwright
    steps warn rather than fail the item. A quick start is printed afterwards; you're
    asked up front, and `--skillui-guide` / `-SkillUIGuide` answers yes without asking.
  - **Strix** (19) — upstream's own installer, `curl -sSL https://strix.ai/install |
    bash`. Installing it is not enough to run it, so the next steps (Docker running,
    `STRIX_LLM`, `LLM_API_KEY`) print on every run, including one that skipped the
    install. Windows has no POSIX shell, so the script runs the installer through WSL,
    falls back to Git Bash, and warns with the manual command if neither exists.

- `scripts/install-prerequisites.ps1` / `.sh` — the install menu is now a **cursor
  picker**: ↑/↓ to move, Space to tick, Enter to start, `A`/`N`/`D` for all/none/
  defaults, `Q` or Escape to cancel. Rows scroll inside a viewport when the window
  is short, and every printed line is clipped to the window width, because a
  wrapped line breaks the redraw and smears the menu over whatever was above it.
  The numbered prompt is still there as the fallback and is chosen automatically
  when raw key input is not possible — no terminal, no `stty`, `TERM=dumb`,
  PowerShell ISE, a redirected console, or a window under ten lines. Bash restores
  the saved `stty` state and the cursor from an `EXIT`/`INT` trap so Ctrl-C in the
  menu cannot leave the user's shell with echo off.

- `scripts/install-prerequisites.ps1` / `.sh` — **individual skills can be
  installed instead of all nineteen**. Pressing → on the repo's row opens a second
  picker listing every skill in this repo; `-Skills 'cloudflare,drata'` /
  `--skills cloudflare,drata` does the same non-interactively and also accepts
  `all`, `none`, and positions (`1,4-6`). It composes with `-All` /
  `-NonInteractive`, so CI can install everything except the skills, or only the
  skills. The catalog (`SKILL_KEYS` in bash, `$script:SkillCatalog` in PowerShell)
  is now the single source of both the picker rows and the install loop, replacing
  the duplicated `own_plugins` / `$ownPlugins` arrays. The repo's menu row shows a
  live count (`+ 3 of 19 skills`) rather than a hardcoded nineteen.

- `skills/infra-work-ticketing` — `ticketctl.py` gained **`update`** and
  **`close`**, so the API fallback covers all four write verbs rather than just
  `create` and `note`. `update` sets title, status, priority, category,
  subcategory, group, technician, urgency, impact, type and (on SDP) the
  resolution and an `--update-reason` for the audit trail; `close` takes a closure
  comment, `--closure-code`, and `--requester-ack`. On Jira, `close` looks the
  transition up by name from the issue's own transition list rather than
  hardcoding an id, and `--category` maps to a component — the nearest equivalent
  Jira has. Both go through the same build/execute split as the existing verbs, so
  `--dry-run` covers them.

  Two limits are documented rather than papered over. **Closing through
  `ticketctl.py` is not equivalent to `sdp_close`**: SDP Cloud v3 has no close
  sub-resource, so the fallback PUTs a terminal status plus `closure_info` to the
  edit endpoint and a desk with mandatory closure rules can reject it. And
  **nothing can create or rename a category** — the v3 API documents no endpoint
  for the taxonomy and the connector's metadata tool is read-only, so that stays
  an SDP admin-UI job. Setting the category on a ticket works from either path.

- `skills/infra-work-ticketing` — an `mcp` block in the config file records how
  ticket writes are routed: connector name, endpoint, tool prefix, whether to
  prefer MCP, and which `ticketctl.py` provider takes over when it refuses.
  `ticketctl.py doctor` prints the resolved routing and probes the connector's
  `/health` (5-second timeout, `--no-mcp-probe` to skip). Routing metadata only —
  the connector authenticates per person through Claude Code, so no credential
  belongs in the block. `INFRA_TICKET_PREFER_MCP` and `INFRA_TICKET_MCP_ENDPOINT`
  override it per session.

### Removed

- `scripts/install-prerequisites.ps1` / `.sh` — **six menu items**: the Firecrawl,
  Chrome DevTools, and Glyphs MCP servers, the OmniRoute gateway, Headroom, and GSD.
  The helpers that existed only for them went with them: `tcp_port_open` and
  `add_mcp_http_server` in bash, `Test-TcpPort`, `Get-PythonLauncher`,
  `Add-UserScriptsToPath` and `Get-PipxPythonArgs` in PowerShell, along with the
  `FIRECRAWL_API_KEY` prompt, the OmniRoute guided-setup question, and the Headroom
  mode question. The `-HeadroomMode` / `--headroom-mode` switch is gone.

  The menu is 19 items rather than 20, and items 1–10 are the default set (was 1–11).
  Item numbers below 10 are unchanged; everything above shifted. Scripted runs should
  use the stable keys (`--select supabase,strix`) rather than positions.

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — the per-skill picker's descriptions are
  fuller: each of the nineteen rows now names what the skill actually does rather than
  restating its title (`cloudflare - Cloudflare v4: DNS, WAF, cache, Workers, Zero
  Trust`). Text is sourced from the skills table in `README.md`. The rows are written
  for a window of about 95 columns; narrower consoles clip them with an ellipsis, as
  they already did for the longest of the old labels.

### Fixed

- `skills/infra-work-ticketing` — a `ticketctl.py` write that failed while
  *planning* rather than sending was not queued, so the text was lost. Resolving
  `#40219` to an internal id is itself an API call, which means a down service desk
  failed in exactly that window. Planning is now inside the guarded region for
  `note`, `update` and `close`. `--dry-run` still never queues.

- `scripts/install-prerequisites.ps1` / `.sh` — a picker that failed *after* the
  capability gate passed did not fall back. In bash the failure return was ignored,
  leaving an empty selection that printed `Nothing to do.` and exited 0 — the same
  output as a deliberate cancel. In PowerShell, `$ErrorActionPreference = 'Stop'`
  meant a `SetCursorPosition` throw (a window shrunk between frames) killed the
  whole installer. Both now drop through to the numbered menu and say why. The
  capability gate only ever proved the picker could *start*.

- `scripts/install-prerequisites.sh` — the `/dev/tty` probe printed
  `No such device or address` to stderr on hosts without a controlling terminal.
  The redirection is now grouped so `2>/dev/null` actually covers it.

- `scripts/install-prerequisites.ps1` — hiding the cursor threw
  `"The handle is invalid"` on hosts that don't implement `Console.CursorVisible`,
  which would have taken the whole menu down with it. It is cosmetic, so it is now
  best-effort.

- `skills/visio-diagrams` — creates, edits, and verifies Microsoft Visio `.vsdx`
  files. Two paths from one spec: a stdlib-only writer (`vsdx_writer.py` +
  `diagram_from_spec.py`) that generates a native `.vsdx` plus an SVG preview
  with no Visio install and no third-party packages, so it runs in CI and on
  air-gapped boxes; and PowerShell COM automation (`New-VisioDiagram.ps1`) for
  real stencil masters, themes, containers, and swimlanes. Also covers reading
  and retitling an existing `.vsdx` via the `vsdx` package (the template + data
  pattern that preserves corporate stencils). Leads by challenging whether Visio
  is the right output at all, and refuses to call a file verified when
  `verify_vsdx.py` could only check OPC structure. Two reference files (`.vsdx`
  OOXML format and symptom → cause table, COM automation). Registered in
  `.claude-plugin/marketplace.json` and both install scripts — 19 skills total.

- `skills/claude-code-defaults` — configures how Claude Code itself behaves by
  default. Separates instructions (`CLAUDE.md`, `.claude/rules/`, loaded into
  context) from enforcement (`settings.json`, permission `allow`/`ask`/`deny`,
  hooks, applied by the client), and routes a request to the right file at the
  right scope — user, project, local, or managed. Inventories existing config
  and merges rather than clobbering, backs up before editing, validates the JSON,
  and verifies via `/status`, `/context`, and `/doctor`. Four reference files
  (permissions, CLAUDE.md, settings keys, copy-paste templates for solo/shared/
  locked-down/fleet). Refuses to hand out `bypassPermissions` as a default.
  Registered in `.claude-plugin/marketplace.json` and both install scripts —
  18 skills total.

- `scripts/install-prerequisites.ps1` / `.sh` — the VoltAgent
  [`awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents)
  collection is now installed as plugins from its own marketplace
  (`voltagent-subagents`), all ten category plugins: `voltagent-core-dev`,
  `-lang`, `-infra`, `-qa-sec`, `-data-ai`, `-dev-exp`, `-domains`, `-biz`,
  `-meta`, `-research`.

- `scripts/install-prerequisites.ps1` — `-InstallScope` (aliased to the old
  `-PluginHubScope`) now applies `--scope` to *every* marketplace and plugin
  install, not just the community set. Same for `--scope` on the Linux script.

- `skills/terraform-docs-readme` — regenerates a Terraform module's `README.md`
  with `terraform-docs`. Covers first-time setup (`.terraform-docs.yml`, the
  `main.tf` narrative header block, `footer.md`, the `BEGIN_TF_DOCS`/`END_TF_DOCS`
  injection markers) as well as re-runs after variables, outputs, or resources
  change, and diagnoses the usual failures — missing markers, a header that
  isn't picked up, a footer that isn't rendered, a version older than 0.16.
  Ships a stdlib-only, read-only preflight script and copy-ready assets.
  Registered in `.claude-plugin/marketplace.json` and in both install scripts.

- `skills/cisco-meraki` — Cisco Meraki Dashboard API v1 skill for a single
  organization, covering MX/MS/MR. Reads inventory, device status, the network
  event log, the org configuration change log, MX security/IDS events, and Air
  Marshal; runs live diagnostics (ping, cable test, throughput, ARP/MAC table,
  wake-on-LAN); and makes configuration changes behind a snapshot → diff →
  confirm gate with single-command rollback. Bulk changes route through staged
  Action Batches so Meraki validates the payload server-side before commit.
  Stdlib-only Python, no pip install. Includes the repo's first unit test suite
  (`python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py"`).

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — **all marketplace and plugin
  installs now use the native `claude plugin marketplace add` and `claude plugin
  install` commands.** The `npx -y claudepluginhub <repo>` wrapper is gone, along
  with the `Invoke-PluginHub` / `pluginhub` helpers that called it. The wrapper
  registered each repo as a *local directory* marketplace under a generated name
  (`cpd-<repo>-user`) that the scripts' own detection could not match, so those
  plugins were reinstalled on every run, and it was a recurring source of Windows
  failures. Marketplace names are now taken from each repo's own
  `.claude-plugin/marketplace.json` — notably `fcakyon/claude-codex-settings`
  publishes itself as `claude-settings`, which the old name-or-repo detection
  never matched either.
- `scripts/install-prerequisites.ps1` / `.sh` — claude-mem installs through its
  marketplace (`claude plugin marketplace add thedotmack/claude-mem` +
  `claude plugin install claude-mem@thedotmack`) instead of
  `npx claude-mem install`. Upstream documents both paths. `find-skills` and GSD
  still use `npx`: neither publishes a Claude Code marketplace.
- `MARKETPLACE.md` / `INSTALLATION.md` — bootstrap command lists rewritten to
  match, with the repo-name-vs-marketplace-name trap called out explicitly, and
  a troubleshooting row for leftover `cpd-*-user` marketplaces.

### Removed

- `scripts/install-prerequisites.ps1` — the `Resolve-GitRoot` and
  `Register-GitBash` helpers, plus the `C:\repos\awesome-claude-code-subagents`
  clone and its `bash install-agents.sh` invocation. Its Linux counterpart
  (`~/repos/...` clone) is gone too. That step needed Git Bash on Windows and so
  failed outright on a non-elevated run, where Chocolatey — and therefore `git` —
  had already been skipped. An existing checkout from an earlier run is now
  unused and safe to delete.
- `aiskillstore/marketplace` and its `xlsx` / `mcp-integration` entries. That
  repo is the Skill Store content repo, not a Claude Code marketplace (no
  `.claude-plugin/marketplace.json`), so there is no native
  `claude plugin install` for it. `anthropic-office-skills@claude-settings`
  replaces `xlsx`; either skill can still be installed by hand with
  `npx skillstore add aiskillstore/<skill>`.

- `scripts/install-prerequisites.ps1` / `.sh` — the `find-skills`
  (`vercel-labs/skills`) step is now prompted rather than unconditional, and is
  detected before it runs. It installs as a user-level skill, not a Claude Code
  plugin, so detection is a filesystem check on
  `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/find-skills/SKILL.md`. Already
  installed: the prompt offers a re-install for updates; `-NoUpdate` /
  `--no-update` skips it entirely. The step now also verifies the skill actually
  landed on disk instead of trusting the installer's exit code.

### Fixed

- `skills/terraform-docs-readme` arrived double-nested
  (`skills/<name>/<name>/SKILL.md`) with a leftover `terraform-docs.zip` and a
  zip-oriented `INSTALL.md` — the same layout problem fixed for `aws-opensearch`
  and `intune-graph` in the 2026-07-28 baseline. Flattened to the standard
  `skills/<name>/SKILL.md` layout; the duplicate tree, the archive, and the
  now-inaccurate `INSTALL.md` were removed (installation for this repo's skills
  is covered by `INSTALLATION.md` and `MARKETPLACE.md`).
- `INSTALLATION.md`'s "What the own-marketplace step installs" list was stale at
  10 skills and missing `cisco-meraki`, `infra-work-ticketing`, `repo-docs`,
  `shipstation`, `web-testing-playwright`, and `work-log-reporter`. Now lists all
  17, matching `marketplace.json`, `skills/`, and both install scripts.

## [2026-07-28]

### Added

- DevOps scaffolding for distributing skills to the team: `Skill-Authoring-Standard.md`, `Skill-Pipeline.md`, `SECURITY.md`, `INSTALLATION.md`, `MARKETPLACE.md`, this `CHANGELOG.md`.
- `.claude-plugin/marketplace.json` — registers this repo as a Claude Code plugin marketplace with one plugin entry per skill.
- `scripts/install-prerequisites.ps1` and `scripts/install-prerequisites.sh` — bootstrap Git, AWS CLI (Windows) / native package manager (Linux), Node.js, Python, the Claude Code CLI itself (with `PATH` export), and the team's standard marketplaces/plugins (Superpowers, find-skills, GSD, claude-mem, frontend-design, excalidraw-generator).
- Populated `skills/README.md` with a skill overview table (name, category, purpose, invocation mode) for all 10 skills.
- Root `README.md` now embeds the skills overview and links every new doc.
- Populated root `.gitignore`.

### Fixed

- `aws-opensearch` and `intune-graph` skill directories were double-nested (`skills/<name>/<name>/SKILL.md`), breaking the standard `skills/<name>/SKILL.md` discovery convention and marketplace `source` paths. Flattened to the standard layout.

### Skills present as of this baseline

`aws-opensearch`, `bitbucket`, `checkpoint-email`, `cloudflare`, `drata`, `i-have-adhd`, `intune-graph`, `mermaid-svg-bitbucket`, `sophos-central`, `wazuh-onprem` — see [`skills/README.md`](skills/README.md) for details on each.
