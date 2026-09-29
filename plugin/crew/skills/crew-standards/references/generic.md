---
set: GEN
applies-to: ["**"]
---

# Generic development standards (GEN)

Crew-generic build-time standards, mined from crew's own QA review findings (T-0085). Each one is
earned by BLOCK/FIX findings from at least three distinct reviewed change sets; a class earned by fewer
lives in the repository overlay that found it. Findings are cited by ticket, review round, reviewed
head (`@sha`; `+dirty` means the reviewed bytes were not at that commit) and the reviewer's quoted
claim, cut with `[...]`. `main(pmunnamed)`, `main(T1-T4)` and `main(B1-B3)` are three reviews of crew's
`main` that predate ticket numbering; the last two share the head `@8b8a4028+dirty` and are distinct by
their bundles (different bytes, and main(B1-B3)'s carries four files and whole branches main(T1-T4)'s
does not), not by the head. A self-check's examples are examples of its class, not its
definition: when a standard fires on a fix, run its self-check over the fixed line's whole class again.

## GEN-01 Unknown stays unknown

**Rule.** Where a probe, read, parse, import or subprocess can fail, "could not tell" is its own value
and reaches the verdict unchanged. It never becomes absent, gone, default policy, fresh, green or
success. An absence signal proves absence only when the probe could see: ENOENT from a filesystem that
may not be mounted, ESRCH from inside a pid namespace, `lexists` False after a `PermissionError` on a
parent, or empty output from a failed command is could-not-tell. "Absent" is proven only when the leaf
is missing (ENOENT) and its parent is readable; a failed read whose leaf `lexists()` is False because
the parent is not a directory or cannot be read is unknown. A could-not-tell branch emits the safe
superset it announces, and a test compares the message against what was emitted. Two probes that disagree give unknown.
A partial result (short write, truncated read, partial exit status) is not success. Any failure,
malformed input included, reaches the caller as unknown and never raises, and the fail-closed path
cannot itself raise.

**Why.** 26 findings across 10 change sets: a live pid read as gone, an unreadable config read as the
default policy, `gh` exiting 1 read as green, a crash inside a guard, a short `os.write` treated as
success before the only copy was deleted. Crew's repository CLAUDE.md, "Lessons": "The recurring bug is an unknown
collapsing into the safe-looking value."

**Change sets.** 10: T-0072, T-0030, T-0009, T-0028, main(T1-T4), T-0011, T-0016, T-0010, T-0075, T-0008

**Applies when.** A step or diff branches on `os.kill`, `stat`/`lstat`/`lexists`, `open`, `json.load`,
a subprocess exit status, a config probe, or an equality against one state of a multi-state helper
(`== "corrupt"`); any `except`, `or {}`, `.get(key, default)`, `if not x: return default`; any
function documented "never raises", "fails closed" or "refuses unless"; `os.write`/`send` return
values; decoding with `errors="replace"`.

**Self-check.**
1. For every `except`, fallback and default in the diff: if this branch runs, can the caller tell the
   result from success and from genuine absence? Pass: yes, every site.
2. For every absence signal (ENOENT, ESRCH, `lexists`/`exists` False, empty output): does it prove the
   thing is absent, or only that this probe cannot see it (procfs not mounted, `hidepid`, a pid
   namespace, `PermissionError` on a parent, a parent that is not a directory, so the lookup fails
   with `ENOTDIR`)? Where two probes disagree, is the result unknown? Pass: each is proven absent (the
   leaf is ENOENT under a readable parent) or returns unknown.
3. For every helper the diff calls whose result has an absent, none or default state: open the helper
   and confirm that state excludes could-not-look. A comparison against one bad value (`== "corrupt"`)
   also treats unknown as bad. Pass: yes for each helper, by reading its body.
4. For every partial result (a write's returned byte count, a read's length, a subprocess that
   produced some rows and a non-zero status): is it distinguished from success before any
   irreversible step? Pass: yes.
5. Does the fail-closed path format anything that can raise (`str(exc)`, `repr(input)`, an f-string on
   untrusted objects, a path join on bytes)? Pass: no, or it is wrapped.
6. Feed malformed data (valid JSON/TOML of the wrong shape) to each new reader. Pass: unknown, no
   traceback.
7. For every could-not-tell branch that announces a fallback ("only the always-on sets are listed"):
   does it emit that fallback, and does a test compare the message against what was emitted? Pass: yes.
   Example starting grep, not the definition: `except|or \{\}|\.get\(|lexists|exists\(|returncode|errors="replace"|== "(corrupt|absent|missing)"|os\.write`.

**Earned by.**
- T-0030 r1 @e2a23f08, BLOCK `plugin/crew/hooks/scripts/crew_coord.py:198` (the code is
  `except FileNotFoundError: return PidProbe("gone", None, True)`, re-read at that commit): "_linux_probe
  reads a LIVE pid as gone with measured=True whenever os.kill has already shown the process exists
  [...] but /proc/<pid>/stat cannot be opened (/proc not mounted in a sandbox or container, or hidepid
  [...])"
- T-0030 r2 @a3dc57f9, BLOCK `plugin/crew/hooks/scripts/crew_coord.py:235`: "_linux_probe treats
  ProcessLookupError as proof the pid is gone (measured=True), but Claude Code's own Linux sandbox runs
  every Bash command under bubblewrap with an unconditional --unshare-pid [...]"
- T-0072 r3 @2fa75f79, BLOCK `plugin/crew/hooks/scripts/crew_autopilot.py:740` (the line is
  `if crew_config.layer_state(path, environments=True) == "corrupt":`): "An unreadable machine-config
  parent can collapse to `layer_state == "absent"` because `os.path.lexists` returns false when its stat
  probe gets `PermissionError` [...]"
- T-0011 r1 @4dcf45e4, BLOCK `plugin/crew/hooks/scripts/crew_autopilot.py:336`: "Exit 1 with passing rows
  and an error is accepted as green; stderr and the missing failure row are ignored."
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/review_verdict.py:170`: "Malformed JSON content
  parts crash both probe classification and review finalisation instead of producing unknown or
  INCOMPLETE"
- main(T1-T4) r2 @8b8a4028+dirty, FIX `plugin/crew/hooks/scripts/pm_journal.py:181` (file removed in
  c3bd8dfd): "A short os.write is treated as success and the only source copy is deleted, permanently
  truncating the journal entry"
- Amendment, owner-approved 2026-09-28 from T-0085 review round 1's proposals 2 and 3 (not in the
  mined count above): T-0085 r1 @8ab20e16, FIX `plugin/crew/hooks/scripts/crew_standards.py:506`:
  "gate_applies treats read_approval's "absent" as "no receipt, gate does not apply".
  `crew_ticket._read_json` returns "absent" whenever `lexists` is False after a failed read, including
  an unreadable or non-directory parent. [...]"; T-0085 r1 @8ab20e16, FIX
  `plugin/crew/hooks/scripts/crew_standards.py:571`: "When the manifest has no usable file lists,
  checklist_block prints "only the always-on sets are listed" and returns without listing a single
  standard. [...]"

**Source.** https://docs.python.org/3/library/os.html, `os.write`: "Return the number of bytes actually
written." (self-check 4; re-read raw 2026-09-28).


## GEN-02 Shared files change atomically

**Rule.** A file, lock or record another process can touch is changed with one atomic operation that
fails if its precondition no longer holds: `O_CREAT|O_EXCL`, `os.link`, a compare-and-swap on a recorded
digest, or a lock held across the whole read-modify-write. A lock is released only after verifying its
owner. A source is deleted only after its copy is verified complete. Staging names are per-writer. A
multi-step save that fails partway reports exactly which steps landed. (Checks that authorize a later
action, remote state included, are GEN-03. Partial writes are GEN-01.)

**Why.** 12 findings, 4 change sets: backups overwritten, config deleted without a backup, two writers
inside one ledger lock, a shared staging name. Crew's repository CLAUDE.md, "Landmines", records the single-process form
(`open(p, "w")` truncates before the payload exists).

**Change sets.** 4: T-0075, T-0003, main(T1-T4), T-0030

**Applies when.** `exists`/`lexists`/`stat` followed by `os.replace`/`rename`/`remove`; read-modify-write
of a JSON or config file; stale-lock takeover or release; a fixed temp or staging filename; deleting an
original after writing a copy; two files written in sequence as one save.

**Self-check.**
1. For every existence check and lock operation: is the following action an atomic primitive that fails
   if the checked state changed in between? Pass: yes, every site.
2. Write the interleaving test: pause right after the check, change the state from a second writer,
   resume. Pass: the test goes red with the guard removed (GEN-04).
3. Is every staging or temp name unique per writer? Pass: yes.

**Earned by.**
- T-0003 r1 @cf3bc0d8, FIX `plugin/crew/hooks/scripts/crew_endpoints.py:312`: "The stale-lock takeover is a
  check-then-remove race, so two writers can both hold the ledger lock. [...] B's `os.remove(path)`
  deletes A's live lock [...]"
- T-0003 r2 @d43fed8b, BLOCK `plugin/crew/hooks/scripts/crew_endpoints.py:340`: "The put-back leaves a
  window where two writers can both hold the lock. [...]"
- T-0075 r3 @1fbc70fb, BLOCK `plugin/crew/hooks/scripts/crew_config_files.py:252`: "destination refusal is
  a check-then-replace race, so a backup created after `lexists` is overwritten and lost"
- T-0075 r2 @b4911045, BLOCK `plugin/crew/hooks/scripts/crew_config_menu.py:664`: "A concurrent config
  replacement after backup verification is deleted without being backed up [...]"
- T-0030 r1 @e2a23f08, FIX `plugin/crew/hooks/scripts/crew_coord.py:323`: "update_identity does a
  read-modify-write of <git-common-dir>/crew/coord-identity.json with no lock. [...] concurrent claim or
  recover calls from two worktrees lose each other's entries."


## GEN-03 The irreversible action carries what was checked

**Rule.** An approval, receipt, preview, dry run, validation or CI result authorizes an action only when
the action itself carries the checked value, so the executor refuses if it changed: `gh pr merge
--match-head-commit <sha>`, a compare-and-swap, an expected digest, the same plan object the preview
showed. A separate re-read immediately before the action does NOT count; it leaves a window between the
re-read and the action. Where the tool offers no binding, the implement notes say so and name the
remaining window as an accepted risk. Every input the check read (commit, file digest including
"absent", argv, stdin, redirected files, every dispatch on the line) is part of the binding, and each
fact (checkout root, HEAD, ledger) is resolved once and reused. Preconditions already known to fail are
resolved before any quota-bearing request or reservation is spent.

**Why.** 17 findings, 5 change sets: merges of commits nobody reviewed, an approval reused for another
deployment, a typed delete confirmation applied to a file edited after the preview, a review round
spent on a probe whose outcome was already fixed. A rule saying "re-verified immediately before the
irreversible step" is not enough, and T-0011 r1 shows that construction failing: at 4dcf45e4
`crew_autopilot.py:472-478` the code re-reads HEAD and the PR's `headRefOid`, refuses on a mismatch, and
then calls `_run_gh(top, merge_argv(...))` (re-read at that commit). It was still a BLOCK, because a push
can land between the re-read and the merge.

**Change sets.** 5: T-0011, T-0075, T-0009, T-0028, T-0072

**Applies when.** Anything that approves, merges, ships, deletes, deploys or spends a quota after an
earlier check; approval markers keyed on argv; dry-run-then-apply; polling loops that cache what they
read; resolving the same path, root or HEAD twice.

**Self-check.**
1. List every irreversible or quota-spending action in the diff. For each: does the action pass the
   checked values to an executor that refuses when they changed? Pass: yes, as a precondition the
   executor enforces; or the notes name the tool's missing binding and the window.
2. Is any authorizing fact read twice? Pass: no.
3. For approval markers: would changing any one input (stdin body, redirected file, second dispatch,
   config mapping) change the marker key? Pass: yes for each.
4. Is every precondition that can already be known to fail checked before the reservation or request?
   Pass: yes.

**Earned by.**
- T-0011 r1 @4dcf45e4, BLOCK `plugin/crew/hooks/scripts/crew_autopilot.py:478`: "The merge request does not
  bind the validated HEAD, so it can merge a different commit."
- T-0011 r2 @b5bffe4e, BLOCK `plugin/crew/hooks/scripts/crew_autopilot.py:535`: "The merge's expected HEAD
  is captured after CI, so it can authorize another commit using the previous commit's checks."
- T-0009 r2 @b979d640, BLOCK `plugin/crew/hooks/scripts/crew_guards.py:2444`: "Approval keys omit stdin
  source paths and pipeline transformations, so approval for one command authorizes a different
  deployment"
- T-0075 r3 @1fbc70fb, BLOCK `plugin/crew/hooks/scripts/crew_config_menu.py:818`: "the apply CLI creates a
  fresh delete plan, so the typed confirmation is not bound to the preview the owner reviewed"
- T-0028 r2 @0aab3a8f, FIX `plugin/crew/hooks/scripts/review_run.py:623`: "When the `before` fingerprint is
  None, the round is already certain to end INCOMPLETE [...]. run() still spends the probe request,
  reserves the round and launches the full review anyway. [...]"
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/review_run.py:896`: "A successor-plan race spends a
  review round on a failed quota probe, violating the pre-reservation requirement"

**Source.** https://cli.github.com/manual/gh_pr_merge, `--match-head-commit`: "Commit SHA that the pull
request head must match to allow merge" (self-check 1's example; re-read raw 2026-09-28).


## GEN-04 Every behaviour has a control that fails, in both directions

**Rule.** Every behaviour the diff adds or the spec promises (a guard, a refusal, an unknown verdict, a
launch's argv and env, a report line only `main()` prints, a positive path) has a test that goes red
when it is removed or weakened. Every guard also has a must-allow test that goes red when it over-fires
on a legitimate input. The mutations are run before review and recorded, not left for the reviewer.
The self-check evidence maps each mutation an acceptance check names to a sabotage entry by label, not
by count, and every refusal branch in a new guard has at least one test that fails when the branch is
replaced with `pass`. Tests assert the property on the real shape of the input, not a proxy.

**Why.** 15 findings, 8 change sets, of tests that could not fail. Crew's repository CLAUDE.md, "Stop and ask", already
requires, for a blocking hook, "a committed regression suite with must-block and must-allow cases,
sabotage-tested". About ten findings across GEN-02, GEN-05, GEN-11 and REPO-02 are the opposite
failure, code that refuses or wedges a legitimate case (help flags denied, valid literals refused, an
unreadable stale lock wedged forever, a known writer blamed on the reviewer), so the must-allow direction is half of this standard.

**Change sets.** 8: T-0030, T-0016, T-0028, T-0008, T-0072, main(B1-B3), T-0003, main(pmunnamed)

**Applies when.** Any new branch that refuses, denies, returns unknown or bounds something; any launch
of a subprocess with built argv/env; any `main()`-only statement; any doc or CHANGELOG line saying "X is
prevented" or "X is untouched"; any test that reads a file as text; any fixture standing in for a
real-world shape.

**Self-check.** For each item in the diff apply the mutation in a scratch copy, run the tests mapped to
that file, and record "mutation -> failing test" in the implement notes. Pass: at least one test fails
for every mutation.
1. Code mutations: `if cond:` to `if False:`; `all(` to `any(`; delete the guard line; move the guarded
   statement outside its guard; drop one call argument; replace an env var or kwarg with its default;
   delete a statement that only `main()` runs; force a positive-path value to a constant
   (`anchor = None`).
2. Text mutations, for a test that reads a prompt, doc or shell script as text: negate the sentence,
   move the guarded command outside its guard (leave the `if` line in place), rephrase the forbidden
   instruction.
3. Must-allow: for each guard, a legitimate input it must let through (a help flag, a valid quoted
   literal, an unreadable but stale lock, a write by a known other party). Pass: the test goes red when
   the guard is widened to refuse it.
4. Does any fixture already fail for a reason other than the one under test? Pass: no.
5. For each mutation the spec's acceptance checks name: the label of the sabotage entry that makes it
   (a count of entries is not evidence). For each refusal branch in a new guard: replace the branch
   with `pass` and name the test that goes red. Pass: every named mutation has a labelled entry, and
   every refusal branch a red test.

**Earned by.**
- T-0016 r2 @57656e34, BLOCK `plugin/crew/hooks/scripts/crew_autocycle.py:658`: "The new guard "window has
  no owning process -> refuse when a live sibling exists" [...] has no failing control. [...]"
- T-0030 r1 @e2a23f08, FIX `plugin/crew/hooks/scripts/crew_coord.py:679`: "The detached heartbeat launch in
  _maybe_start_heartbeat has no test at all, because every test passes --no-heartbeat [...] Its argv,
  its interval, its start_new_session setting, and its use of child_env() [...]"
- T-0028 r1 @6f005fa2, FIX `plugin/crew/tests/test_kimi_docs.py:103`: "`all("--probe-kimi" in text for _ in
  probe_lines)` never uses its loop variable, so it only checks that the string appears somewhere in the
  file. [...]" (its regression is moving the probe command out of its `if [ "$PROBE_KIMI" = 1 ]` block,
  a text mutation)
- T-0030 r2 @a3dc57f9, FIX `plugin/crew/tests/test_crew_coord.py:743`: "The corrupt-claim case [...] is
  refused by the timestamp check whatever parse_claim does with the holder. The holder-validation branch
  [...] therefore has a test that cannot fail. [...]"
- main(B1-B3) r3 @8b8a4028+dirty, FIX `plugin/crew/tests/test_upgrade.py:428`: "The regression tests call
  run() only, so removing main()'s newly added report printing leaves every B1 test green [...]"
- Must-allow, T-0009 r2 @b979d640, FIX `plugin/crew/hooks/scripts/crew_guards.py:2305`: "Help requests are
  classified as deployments and denied, preventing inspection of CLI usage"; T-0003 r2 @d43fed8b, FIX
  `plugin/crew/hooks/scripts/crew_endpoints.py:361`: "A stale lock whose content cannot be read is now never
  taken over, so the ledger stays wedged [...]"
- Amendment, owner-approved 2026-09-28 from T-0085 review round 1's proposal 6 (not in the mined count
  above): T-0085 r1 @8ab20e16, FIX `plugin/crew/tests/sabotage_standards.py:17`: "The acceptance check
  requires an "overlay may drop a plugin id" mutation. None of the 8 mutations targets the overlay
  plugin-id guards [...]. The reuse guard has no test at all [...]"


## GEN-05 Recognise a narrow allowlist; everything else is could-not-tell

**Rule.** Code that classifies text another program interprets (shell, PowerShell, Markdown, a CLI's
human output, prompt prose, citation syntax) accepts only forms it can parse with certainty and returns
could-not-tell for anything else. It does not try to model the whole grammar. Prefer the tool's
machine-readable output (`--json`, NUL-separated, porcelain) to parsing human text; when parsing text
cannot be avoided, cite the source that proves the separator cannot occur inside a field. Each accepted
form is tested for its allow reading as well as its deny reading. A classifier inside a test is still a
classifier.

**Why.** 28 findings, 17 of them from T-0009's five rounds, which found shell and PowerShell forms one at
a time (redirects, `0>&3`, bracket globs, clustered flags, parameter abbreviations, aliases). For the
Markdown case the owner withdrew fuller fence handling and chose the allowlist: T-0043 `spec.md:31-32`
(owner, 2026-09-27): "Only a column-0 fence closed by a column-0 run of the same marker, at least as long
and with nothing after it, is tracked. Every other fence-shaped line [...] stops the ticket [...] This rule
is chosen over more CommonMark emulation." Listing forms one at a time is the approach that took five
rounds.

**Change sets.** 7: T-0009, T-0043, T-0011, main(pmunnamed), T-0030, T-0008, T-0010

**Applies when.** A regex or tokenizer over command lines; Markdown fence or heading detection;
`split("\t")` or `strip()` over tabular CLI output; matching refs or URLs returned by a tool; a test
that regex-matches prose.

**Self-check.**
1. Does the classifier return could-not-tell for any input outside its written allowlist? Pass: yes,
   with a test feeding a form it has never seen.
2. Is a machine-readable output available from the tool, and is it used? Pass: yes, or the notes cite
   why not and the source proving the separator is safe.
3. Is each allowlisted form tested for its allow reading and its deny reading? Pass: yes.
   Examples of forms reviewers found (examples, not the class): shell redirects and fd duplication,
   globs, aliases, line continuations, clustered short flags, `--help`; PowerShell parameter
   abbreviation and runtime-built targets; Markdown fence length and indentation; prose negation and
   comma-joined contradictory clauses.

**Earned by.**
- T-0009 r2 @b979d640, BLOCK `plugin/crew/hooks/scripts/cloud_guard.py:681`: "The stdin uncertainty check
  ignores `0>&3`, trusting a staging body that a later descriptor duplication replaces with production"
- T-0009 r4 @6d0f5a69, BLOCK `plugin/crew/hooks/scripts/crew_guards.py:2197`: "PowerShell target parameters
  are recognized only by their full names, so valid unique abbreviations bypass dispatch detection"
- T-0043 r2 @36700870, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:256`: "A fence inside a list at
  two-space indentation survives leaving the list, swallowing the following Open questions section and
  bypassing the HUMAN_STOP."
- T-0011 r2 @b5bffe4e, BLOCK `plugin/crew/hooks/scripts/crew_autopilot.py:344` (the line is
  `parts = line.split("\t")` over `gh`'s human table): "Unescaped tabs in check names defeat exact
  knownFailures matching and can hide pending states." Its reviewer linked go-gh's tableprinter; this
  lane did not fetch that source.
- main(pmunnamed) r5, FIX `plugin/crew/tests/test_pm_unnamed_spawn.py:506`: "The full-read guard detects
  only negation before "in full," so a negated full-read requirement can remain green"
- Allow direction, T-0009 r5 @cc754aa0, FIX `plugin/crew/hooks/scripts/crew_guards.py:2554`: "PowerShell
  rejects commas even inside a whole single-quoted literal, narrowing the specified literal grammar and
  refusing valid input values"

**Source.** https://cli.github.com/manual/gh_pr_checks: `--json` "Output JSON with the specified
fields"; "When the --json flag is used, it includes a bucket field, which categorizes the state field
into pass, fail, pending, skipping, or cancel."; "Additional exit codes: 8: Checks pending".
https://git-scm.com/docs/git-status: `--porcelain` "will remain stable across Git versions and
regardless of user configuration"; with `-z`, "pathnames are printed as is and without any quoting".
(Self-check 2. All re-read raw 2026-09-28.)


## GEN-06 Hostile text and paths are neutralised at the sink

**Rule.** Text from a peer, a user, a file or argv is escaped for the sink it enters. Shell: pass it as
argv or a file, never inside a fixed heredoc delimiter or a double-quoted string, and quote every
interpolated path (install paths contain spaces on every platform). Line protocol: escape `\n`, `\r`,
U+2028, U+2029 and bidi controls; stdout carries exactly the documented number of lines for every flag
combination, `--json` included. Structured files: no user text can forge a header. Paths under a
repository-controlled directory: containment is enforced by the open itself or proven after it (open
each component without following links, for example a directory-fd chain, or compare the opened
handle's identity with the resolved path after opening). A check before the open does not count. Where
the platform cannot do this, refuse, or record it as a stated limitation.

**Why.** 11 findings, 5 change sets: shell injection through a heredoc terminator and a double-quoted
`printf`, forged verdict lines, a `--json` flag that broke a one-line contract, an unquoted plugin root,
journal appends redirected outside `.crew/` after a containment check.

**Change sets.** 5: main(T1-T4), main(B1-B3), T-0072, T-0030, main(pmunnamed)

**Applies when.** Interpolating external values into shell, heredocs or a printed "run this" command;
printing into line-oriented stdout; appending user text to a structured file; opening or appending under
`.crew/` or any repo path.

**Self-check.**
1. For each interpolation of external text: which sink, which escaping? Test with a value containing a
   newline, U+2028, the heredoc delimiter on its own line, `;`, `$(...)` and a space in a path. Pass:
   the sink receives it inert.
2. Does stdout's line count equal the documented count for every flag combination? Pass: yes, tested.
3. For each open/append under a repo path: is containment enforced by the open or verified after it,
   with a test that swaps a component for a symlink or junction after any earlier check? Pass: yes, or
   a stated platform limitation.

**Earned by.**
- T-0030 r2 @a3dc57f9, FIX `plugin/crew/hooks/scripts/crew_coord.py:728`: "_presented builds the
  recommended command from the peer-written claim['repo'] and claim['ticket'] without safe(). [...]"
- T-0072 r2 @ec5d2ff2, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:1194`: "The flat CLI echoes an
  invalid environment or class without escaping, so one invocation can emit multiple apparent verdict
  lines and break/spoof the consumer protocol"
- T-0072 r4 @37fa2322, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:1204`: "`deploy-allowed --json`
  always emits pretty-printed multi-line stdout, contradicting the documented one-line CLI [...]"
- main(pmunnamed) r5, BLOCK `plugin/crew/agents/pm.md:941` (file removed in c3bd8dfd): "The fixed CREW_EOF
  delimiter permits heredoc termination and shell-command injection despite quoting"
- main(T1-T4) r2 @8b8a4028+dirty, FIX `plugin/crew/commands/pm.md:77`: "The caller-side journal command
  leaves CLAUDE_PLUGIN_ROOT unquoted, so recording user decisions fails on install paths containing
  spaces"
- main(B1-B3) r3 @8b8a4028+dirty, BLOCK `plugin/crew/hooks/scripts/pm_journal.py:245` (file removed in
  c3bd8dfd): "O_NOFOLLOW protects only the final pathname component, so replacing .crew with an external
  symlink after the containment check still redirects the append; on Windows [...] the flag is zero"

**Source.** https://docs.python.org/3/library/os.html, paths relative to directory descriptors: "If
dir_fd is not None, it should be a file descriptor referring to a directory, and the path to operate on
should be relative"; support is per function and per platform: "You can check whether or not dir_fd is
supported for a particular function on your platform using os.supports_dir_fd. If it’s unavailable,
using it will raise a NotImplementedError." (Re-read raw 2026-09-28.) The page does not state Windows
support for `dir_fd` or give an availability note for `O_NOFOLLOW`; the zero-on-Windows fact is the
main(B1-B3) r3 reviewer's, not the documentation's.


## GEN-07 One validated contract between producer and consumer

**Rule.** Every CLI argument and structured input (JSON, TOML, config layers, stored records) is
validated for type and shape, completely, at the boundary: wrong type, non-object, empty string,
forbidden keys at nested depth, bad keys already present. A CLI refuses bad input with exit 2 and a
message and no traceback. Null is refused unless a spec line says null means unset for that key, and
the code comment cites that line; a null or missing value that falls to a default is also checked
against GEN-01. Values that readers compare with `is` are type-checked by the writer (`0`, `1`, `""` for
booleans). Where two places must agree (what a menu offers and what the writer accepts, what delete
produces and what restore accepts, the preview and the apply, the primary and fallback reviewer's
input), both call the same function on the same WHOLE input the consumer validates (the merged object,
not the fragment), and a round-trip test proves the consumer accepts what the producer emits.

**Why.** 18 findings, 3 change sets (14 from T-0075): choices offered and then refused at Save, a
verified backup that restore rejects, a fallback reviewer given a different patch, null slipping past
an enum check, previews listing changes apply never makes. One T-0075 defect (validate the leaves, write the
parent block) shows why these are one standard: it is both an incomplete validation and a producer
the consumer disagrees with.

**Change sets.** 3: T-0075, main(T1-T4), main(B1-B3)

**Applies when.** `argparse`/`sys.argv`; `json.loads`/`tomllib.loads`; enum checks; writers for layered
config; a second code path that recomputes a list, validation or preview that exists elsewhere; a
fallback path; any producer whose output another command consumes.

**Self-check.**
1. For each new input: tested with a list, an int, an empty string, a non-object and a forbidden key one
   level down? Pass: yes. Run each new subcommand with `''`, `1` and `{`. Pass: exit 2, no `Traceback`.
2. Is null refused, or does a cited spec line allow it for this key? Pass: one of the two.
3. Does validation run on exactly the full value that will be written, untouched siblings and
   pre-existing keys included? Pass: yes.
4. Does each consumer-side check call the same function on the same whole input the producer
   validates? Pass: yes (find duplicates with `grep -rn` on the concept).
5. Round-trip test for every producer/consumer and preview/apply pair, starting from a pre-existing
   invalid or foreign state. Pass: the consumer accepts exactly what the producer emits; preview rows
   equal applied changes.

**Earned by.**
- T-0075 r2 @b4911045, FIX `plugin/crew/hooks/scripts/crew_config.py:2606`: "Null bypasses enum validation
  even though it is outside every tuple returned by enum_values [...]". The author had considered null:
  the docstring at `:2600-2603` reads "`None` is accepted for every enum key: a null reads as "unset" and
  falls to the default" (re-read at that commit), so "was null tested?" would have passed.
- T-0075 r2 @b4911045, FIX `plugin/crew/hooks/scripts/crew_config_menu.py:178`: "Choice filtering checks
  only the proposed value, not the merged file the writer validates [...]". The line already calls the
  writer's validator, `crew_config._value_problems({dotted: value})`; the defect is the input.
- T-0075 r3 @1fbc70fb, BLOCK `plugin/crew/hooks/scripts/crew_config.py:2756`: "both planners validate a
  block's leaves but assign the original parent block, dropping untouched sibling and unknown keys and
  hiding leaf-level widening"
- T-0075 r1 @87627d86, FIX `plugin/crew/hooks/scripts/crew_config.py:2918`: "Integer 0 passes the
  false-or-null veto check because 0 equals False in Python, but the auto-clear and resume readers use
  identity checks [...]"
- T-0075 r2 @b4911045, BLOCK `plugin/crew/hooks/scripts/crew_config_menu.py:659`: "Delete accepts malformed,
  empty, or non-object configs, then prints a restore command that restore-repo refuses [...]"
- main(T1-T4) r2 @8b8a4028+dirty, BLOCK `plugin/crew/commands/review.md:459`: "The Claude fallback is never
  given the manifest-built patch, so dirty and untracked content can still receive a false CLEAN"
- main(B1-B3) r3 @8b8a4028+dirty, FIX `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1321`: "The
  report-only path emits full migration claims for changes it never writes, including “roles added” and
  “schema 7 -> 7 ... added” keys". A distinct change set from main(T1-T4) at the same dirty head: the
  cited line is in the report-only branch (`:1315-1324` of that review's bundle), and main(T1-T4)'s
  bundle adds none of those lines to the same file.


## GEN-08 Portable across Windows and POSIX

**Rule.** Code and tests run on every platform the default suite covers. Every call to an API documented
as Unix-only (for example `os.getuid`, `os.fork`, `fcntl`, `pwd`, `os.getpgid`, `os.killpg`,
`signal.SIGKILL`, launching a shebang script directly) is platform-guarded, and the changed tests run on
the Windows default-suite job before review. Commands printed for a user suit the shell that will run
them. Windows sharing violations on rename and create are retried or designed out. A relative `PATH`
entry is resolved before changing directory. (Shell quoting is GEN-06.)

**Why.** 6 findings, 4 change sets, each a Windows-only failure the Linux run could not show. CLAUDE.md
"Landmines" records the same family for this repository's tooling.

**Change sets.** 4: T-0003, T-0030, T-0075, T-0028

**Applies when.** Shelling out; printing a command to run; renaming or removing files other processes may
hold open; adding tests to a suite the Windows job runs; `shutil.which` followed by a `cwd` change.

**Self-check.**
1. Is every Unix-only API call platform-guarded? Pass: yes (a starting grep for the calls above is an
   example, not the check).
2. Was each Windows-relevant path run on Windows? Pass: yes, or the implement notes say
   `NOT RUN ON WINDOWS: <path>` for each path not run. A missing line is a fail.
3. Does any printed command assume POSIX quoting where cmd.exe or PowerShell will run it? Pass: no.

**Earned by.**
- T-0075 r1 @87627d86, BLOCK `plugin/crew/hooks/scripts/crew_config_menu.py:528`: "The printed restore
  command uses POSIX shlex quoting and cannot execute under Windows cmd.exe [...]"
- T-0003 r2 @d43fed8b, BLOCK `plugin/crew/hooks/scripts/crew_endpoints.py:457`: "On Windows a release can
  fail, and the lock then leaks for 30s. [...] the holder's rename during a read fails with WinError 32.
  [...]"
- T-0030 r5 @81617867, FIX `plugin/crew/tests/test_crew_coord.py:1081`: "The new default suite contains
  unguarded POSIX APIs and fails the Windows CI job."
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/kimi_probe.py:269`: "A working Kimi binary found
  through a relative PATH entry becomes unlaunchable in the probe's temporary directory"


## GEN-09 What the change says is true at this commit

**Rule.** Every statement the change ships is true of the code at the same commit: docs and guides,
command prompts, comments, docstrings, CHANGELOG lines and code-map DERIVED claims. Any file a tool
parses (a template its validator reads, a Markdown file a graph builder scans, a verify map) is run
through that tool after the edit and its output compared (sections, parsed paths, node counts). A
"measured", "tested" or "reproduced" claim names an artifact tracked at this commit, or is marked
local-only with its machine and path and phrased as unverifiable by other clones.

**Why.** 17 findings, 7 change sets: prompts contradicting the code they drive, templates refused by
`/crew:approve`, a test that checked a template with the wrong half of the validator, a codemap edit
that broke graphify's fence scanner, a safety design citing a spike file that exists nowhere. The repo's
owner rule (crew's repository CLAUDE.md, 2026-09-26) already requires the doc set to change in the same PR; this adds the
truth check.

**Change sets.** 7: T-0010, T-0001, T-0008, T-0015, T-0043, T-0030, T-0016

**Applies when.** Any behaviour change described anywhere in the doc set; any file read by a parser; any
CHANGELOG line claiming a fix; any claim of measurement.

**Self-check.**
1. For each changed behaviour, search the repo's doc set (the overlay names it) for the old
   description. Pass: no stale hit.
2. For each file a tool parses, run the tool and compare its output with the intent, in a test where the
   repo has one (the full validator, not part of it). Pass: yes.
3. Does every measured/tested/reproduced claim name a tracked artifact, or say local-only with machine
   and path? Pass: yes.

**Earned by.**
- T-0001 r1 @fd88cb73, FIX `plugin/crew/commands/fix.md:46`: "The Touch placeholder is a single bullet
  reading "globs" (plural) [...] parse_touch accepts exactly one path per bullet, so the spec is
  refused."
- T-0001 r1 @fd88cb73, FIX `plugin/crew/tests/test_spec_templates_validate.py:34`: "Test checks only
  sections(), never parse_touch, which is also part of crew_ticket.validate [...]"
- T-0043 r1 @e17bf526, FIX `.crew/codemap/crew.md:450`: "The new leading backtick quotation triggers
  graphify's fence scanner, removing all subsequent sections from the refreshed graph [...]"
- T-0010 r3 @18bc5a93, FIX `plugin/crew/README.md:818`: "The phase table still states that every
  unaccepted approval stops for the human, contradicting the new self/risk policy path [...]"
- T-0016 r2 @57656e34, FIX `TODO.md:11`: "Acceptance check 1 is unmet. [The ticket's] spike.md does
  not exist in this checkout, in the main worktree, or anywhere on the host. Yet the safety design and its
  docs cite it as measured [...]" (the spike file lived under a gitignored directory, so it could never
  exist at a commit)


## GEN-10 External behaviour is measured, not assumed

**Rule.** Every behaviour of a third-party CLI, API or platform the design depends on (what a flag
does, whether a hook runs, what a message addresses, what a queue overrides) is cited to its source at
a pinned version or its official documentation, or exercised by a test. What was not measured is stated
as an assumption in the spec's Unknowns.

**Why.** 3 findings, 3 change sets: `SendMessage` addressed teammates, not unnamed subagents; a merge
queue overrode `--merge`; `git push` ran the repo's pre-push hooks on every claim. Each design was
correct for the tool it imagined.

**Change sets.** 3: main(pmunnamed), T-0011, T-0030

**Applies when.** Any new call to `gh`, `git`, a platform API or a Claude Code tool whose behaviour the
code's correctness rests on.

**Self-check.**
1. List every third-party behaviour the change relies on. For each, name the source (URL fetched, or
   file at a pinned version) or the test that exercises it. Pass: every row has one, or is an Unknown in
   the spec.

**Earned by.**
- main(pmunnamed) r5, BLOCK `plugin/crew/commands/pm.md:31` (file removed in c3bd8dfd): "SendMessage
  addresses teammates, not resumable unnamed subagents; continuity by agent id therefore never resumes the
  PM transcript"
- T-0011 r1 @4dcf45e4, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:478`: "A required merge queue can
  override --merge with squash/rebase and continue merging after ship reports a stop."
- T-0030 r1 @e2a23f08, FIX `plugin/crew/hooks/scripts/crew_coord.py:444`: "The push runs the repo's pre-push
  hook (husky, lefthook and the like) on every claim and release [...]"

**Source.** https://cli.github.com/manual/gh_pr_merge: "When targeting a branch that requires a merge
queue, no merge strategy is required." (Re-read raw 2026-09-28.)


## GEN-11 Named requirements hold on every path

**Rule.** Four triggers, each with its own check. (1) A new member of an enumeration (a provider, a policy
value) appears everywhere an existing sibling does. (2) A second entry point (a library function beside
`main()`) keeps every requirement; for never-writes, sole-writer and only-X requirements the test
snapshots the affected directories, `.git/index` included, before and after the real call through every
entry point; reading the function body is not evidence. (3) An early return or success branch does not
skip a bound, timeout or refusal. (4) Each spec Exclusion has a test that the excluded thing does not
happen. And one dimension: a stored record written under one policy or config is still judged by the
policy that was in force when it was written, where both authorize it. (A spec line that simply was not
implemented is `/crew:implement`'s acceptance trace, not this standard.)

**Why.** 13 findings, 6 change sets: a new provider missing from a strike table, "never writes" true only
through `main()`, a "sole writer" whose callee wrote two more files, a timeout skipped on the success
branch, honest earlier answers invalidated by a policy change.

**Change sets.** 6: T-0010, main(T1-T4), T-0008, T-0028, T-0011, T-0030

**Applies when.** Adding an enum member; adding an entry point; spec lines saying never, only, sole,
every, bounded; an early return; a spec Exclusion; reading records written under an earlier config.

**Self-check.**
1. New enum member: search for an existing sibling everywhere; every table, switch and prompt that lists
   siblings lists the new one. Pass: yes.
2. Never-writes / sole-writer: a before/after directory snapshot test through every entry point. Pass:
   exists and is green.
3. Each early return and success branch: does the bound or timeout still apply? Pass: yes, tested.
4. Each spec Exclusion: a test that it does not happen. Pass: yes.
5. A record written under policy A, read after switching to policy B where both authorize it. Pass:
   accepted.

**Earned by.**
- T-0028 r1 @6f005fa2, FIX `plugin/crew/commands/review.md:211`: "Step 1b's "`dev.provider` -> Struck from
  QA" table has rows for claude, codex and copilot but none for kimi. [...]"
- T-0008 r1 @33ba3adb, FIX `plugin/crew/hooks/scripts/crew_refresh_check.py:258`: "ticket_freshness, the
  entry point T-0004 imports, rewrites .git/index. GIT_OPTIONAL_LOCKS=0 is set only in main() [...]"
- T-0010 r4 @216ee85f, BLOCK `plugin/crew/hooks/scripts/crew_autopilot.py:871`: "approve violates the
  amendment's sole-receipt write boundary by calling crew_ticket.approve, which also creates
  scope-tickets.json [...]"
- T-0011 r1 @4dcf45e4, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:460`: "A passing poll bypasses the
  timeout check, allowing merges after ciTimeoutMinutes expires."
- T-0010 r1 @e4a12179, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:879`: "Historical `taken:` records
  are compared with the current policy, so changing policy invalidates honest prior answers [...]"


## GEN-12 Verification evidence matches the final HEAD

**Rule.** Before review: every changed path maps to a verify rule whose run includes the tests covering
it; the verify gate's last clean pass equals HEAD on a clean tree; its per-rule record lists no rule
still NOT VERIFIED, or each outstanding rule is named in the implement notes with its reason; the repo's
lint gates pass; provenance numbers in the verify map are re-measured for the final tree; no working
marker is left in the checkout. Where the repo already computes this comparison, the self-check runs
that code rather than restating it (GEN-07). The paths and commands come from the repo's overlay.

**Why.** 16 findings, 5 change sets, ten of them BLOCKs: receipts missing or stale at the reviewed head,
tests unmapped, a gate log that predates the final HEAD. A check that the receipt files exist is not
enough: in crew's own repository on 2026-09-28 both existed while `.crew/.verify-verified-at` named
`d9da1409` (dated Sep 22), HEAD was `c5f4aa62`, and the record listed rules as skipped and chronic.

**Change sets.** 5: T-0072, T-0009, T-0075, T-0028, T-0010

**Applies when.** Always, at the end of `/crew:implement`; also whenever a test file is added or a path
changes that the verify map does not yet name.

**Self-check.**
1. Does the last clean verify pass equal `git rev-parse HEAD` on a clean tree? Pass: yes.
2. Is the per-rule record empty, or is each outstanding rule named with its reason in the notes? Pass:
   yes.
3. Does each changed file match a rule whose run includes its tests? Pass: yes.
4. Do the lint commands the gate defines exit 0, and is no working marker left? Pass: yes.

**Earned by.**
- T-0072 r1 @43bf7a95, BLOCK `.crew/verify.json:293`: "The required clean verify-gate pass is unevidenced:
  both .crew/.verify-verified-at and .crew/.verify-gate.record.json are missing [...]"
- T-0072 r4 @37fa2322, BLOCK `.crew/.verify-gate.record.json:1`: "the mandatory final-HEAD verify gate has no
  receipt or required `/root/crew-tmp/t-0072/verify-gate-all.log`, so the change was bundled without
  satisfying the final gate acceptance check"
- T-0072 r4 @37fa2322, BLOCK `.crew/.scope-base:1`: "an ignored scope marker remained in the checkout before
  the bundle was created [...]"
- T-0028 r1 @6f005fa2, FIX `.crew/verify.json:263`: "The new Kimi rule's paths leave out
  test_review_verdict.py, test_kimi_docs.py [...]"
- T-0010 r4 @216ee85f, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:1326`: "_one_line is defined twice
  at module scope, so the repository's required pylint gate reports function-redefined"
