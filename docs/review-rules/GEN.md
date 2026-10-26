<!-- crew-standards-export digest=df6052ac0825389b086b6ca038d9f2c0e191ea1a5407dee8f55424f8dff3a8e6 crew=1.2.89 -->
# Review rules: set GEN

Applies to: always (`**`).
Generated from crew's standards by `crew_standards.py export --write`; do not edit by hand. Check a change against every standard here whose scope matches the files it touches.

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

## GEN-02 Shared files change atomically

**Rule.** A file, lock or record another process can touch is changed with one atomic operation that
fails if its precondition no longer holds: `O_CREAT|O_EXCL`, `os.link`, a compare-and-swap on a recorded
digest, or a lock held across the whole read-modify-write. A lock is released only after verifying its
owner. A source is deleted only after its copy is verified complete. Staging names are per-writer. A
multi-step save that fails partway reports exactly which steps landed. (Checks that authorize a later
action, remote state included, are GEN-03. Partial writes are GEN-01.)

**Self-check.**
1. For every existence check and lock operation: is the following action an atomic primitive that fails
   if the checked state changed in between? Pass: yes, every site.
2. Write the interleaving test: pause right after the check, change the state from a second writer,
   resume. Pass: the test goes red with the guard removed (GEN-04).
3. Is every staging or temp name unique per writer? Pass: yes.

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

**Self-check.**
1. List every irreversible or quota-spending action in the diff. For each: does the action pass the
   checked values to an executor that refuses when they changed? Pass: yes, as a precondition the
   executor enforces; or the notes name the tool's missing binding and the window.
2. Is any authorizing fact read twice? Pass: no.
3. For approval markers: would changing any one input (stdin body, redirected file, second dispatch,
   config mapping) change the marker key? Pass: yes for each.
4. Is every precondition that can already be known to fail checked before the reservation or request?
   Pass: yes.

## GEN-04 Every behaviour has a control that fails, in both directions

**Rule.** Every behaviour the diff adds or the spec promises (a guard, a refusal, an unknown verdict, a
launch's argv and env, a report line only `main()` prints, a positive path) has a test that goes red
when it is removed or weakened. Every guard also has a must-allow test that goes red when it over-fires
on a legitimate input. The mutations are run before review and recorded, not left for the reviewer.
The self-check evidence maps each mutation an acceptance check names to a sabotage entry by label, not
by count, and every refusal branch in a new guard has at least one test that fails when the branch is
replaced with `pass`. Tests assert the property on the real shape of the input, not a proxy.

**Self-check.**
For each item in the diff apply the mutation in a scratch copy, run the tests mapped to
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

## GEN-05 Recognise a narrow allowlist; everything else is could-not-tell

**Rule.** Code that classifies text another program interprets (shell, PowerShell, Markdown, a CLI's
human output, prompt prose, citation syntax) accepts only forms it can parse with certainty and returns
could-not-tell for anything else. It does not try to model the whole grammar. Prefer the tool's
machine-readable output (`--json`, NUL-separated, porcelain) to parsing human text; when parsing text
cannot be avoided, cite the source that proves the separator cannot occur inside a field. Each accepted
form is tested for its allow reading as well as its deny reading. A classifier inside a test is still a
classifier.

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

**Self-check.**
1. For each interpolation of external text: which sink, which escaping? Test with a value containing a
   newline, U+2028, the heredoc delimiter on its own line, `;`, `$(...)` and a space in a path. Pass:
   the sink receives it inert.
2. Does stdout's line count equal the documented count for every flag combination? Pass: yes, tested.
3. For each open/append under a repo path: is containment enforced by the open or verified after it,
   with a test that swaps a component for a symlink or junction after any earlier check? Pass: yes, or
   a stated platform limitation.

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

## GEN-08 Portable across Windows and POSIX

**Rule.** Code and tests run on every platform the default suite covers. Every call to an API documented
as Unix-only (for example `os.getuid`, `os.fork`, `fcntl`, `pwd`, `os.getpgid`, `os.killpg`,
`signal.SIGKILL`, launching a shebang script directly) is platform-guarded, and the changed tests run on
the Windows default-suite job before review. Commands printed for a user suit the shell that will run
them. Windows sharing violations on rename and create are retried or designed out. A relative `PATH`
entry is resolved before changing directory. (Shell quoting is GEN-06.)

**Self-check.**
1. Is every Unix-only API call platform-guarded? Pass: yes (a starting grep for the calls above is an
   example, not the check).
2. Was each Windows-relevant path run on Windows? Pass: yes, or the implement notes say
   `NOT RUN ON WINDOWS: <path>` for each path not run. A missing line is a fail.
3. Does any printed command assume POSIX quoting where cmd.exe or PowerShell will run it? Pass: no.

**Supplement (.crew/standards.md).**
`CLAUDE_PLUGIN_ROOT` in shell text is quoted (GEN-06), and `pwsh` is named absolutely (CLAUDE.md
"Landmines"). `pathlib.write_text` on a `.sh` passes `newline="\n"` (CLAUDE.md "Landmines").

## GEN-09 What the change says is true at this commit

**Rule.** Every statement the change ships is true of the code at the same commit: docs and guides,
command prompts, comments, docstrings, CHANGELOG lines and code-map DERIVED claims. Any file a tool
parses (a template its validator reads, a Markdown file a graph builder scans, a verify map) is run
through that tool after the edit and its output compared (sections, parsed paths, node counts). A
"measured", "tested" or "reproduced" claim names an artifact tracked at this commit, or is marked
local-only with its machine and path and phrased as unverifiable by other clones.

**Self-check.**
1. For each changed behaviour, search the repo's doc set (the overlay names it) for the old
   description. Pass: no stale hit.
2. For each file a tool parses, run the tool and compare its output with the intent, in a test where the
   repo has one (the full validator, not part of it). Pass: yes.
3. Does every measured/tested/reproduced claim name a tracked artifact, or say local-only with machine
   and path? Pass: yes.

**Supplement (.crew/standards.md).**
Doc set to search for the old description: `plugin/crew docs README.md CHANGELOG.md plugin/PLUGINS.md
CLAUDE.md .crew/codemap`; a `plugin/crew/` change updates every document CLAUDE.md "Scope discipline"
lists, or says `Docs: none - <why>` in its PR body or a `Docs:` commit trailer. Parsed files: spec
templates through `crew_ticket.validate` (not `sections()` alone); `.crew/codemap/*.md` through `graphify update .` with
node and link counts compared; a number this repository states about itself carries a
`<!-- claim: ... -->` marker so `scripts/check-marketplace.py` checks it.

## GEN-10 External behaviour is measured, not assumed

**Rule.** Every behaviour of a third-party CLI, API or platform the design depends on (what a flag
does, whether a hook runs, what a message addresses, what a queue overrides) is cited to its source at
a pinned version or its official documentation, or exercised by a test. What was not measured is stated
as an assumption in the spec's Unknowns.

**Self-check.**
1. List every third-party behaviour the change relies on. For each, name the source (URL fetched, or
   file at a pinned version) or the test that exercises it. Pass: every row has one, or is an Unknown in
   the spec.

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

**Self-check.**
1. New enum member: search for an existing sibling everywhere; every table, switch and prompt that lists
   siblings lists the new one. Pass: yes.
2. Never-writes / sole-writer: a before/after directory snapshot test through every entry point. Pass:
   exists and is green.
3. Each early return and success branch: does the bound or timeout still apply? Pass: yes, tested.
4. Each spec Exclusion: a test that it does not happen. Pass: yes.
5. A record written under policy A, read after switching to policy B where both authorize it. Pass:
   accepted.

**Supplement (.crew/standards.md).**
Sibling search root: `plugin/crew`. A new marketplace entry is registered in every place CLAUDE.md
"Scope discipline" lists, in the same commit.

## GEN-12 Verification evidence matches the final HEAD

**Rule.** Before review: every changed path maps to a verify rule whose run includes the tests covering
it; the verify gate's last clean pass equals HEAD on a clean tree; its per-rule record lists no rule
still NOT VERIFIED, or each outstanding rule is named in the implement notes with its reason; the repo's
lint gates pass; provenance numbers in the verify map are re-measured for the final tree; no working
marker is left in the checkout. Where the repo already computes this comparison, the self-check runs
that code rather than restating it (GEN-07). The paths and commands come from the repo's overlay.

**Self-check.**
1. Does the last clean verify pass equal `git rev-parse HEAD` on a clean tree? Pass: yes.
2. Is the per-rule record empty, or is each outstanding rule named with its reason in the notes? Pass:
   yes.
3. Does each changed file match a rule whose run includes its tests? Pass: yes.
4. Do the lint commands the gate defines exit 0, and is no working marker left? Pass: yes.

**Supplement (.crew/standards.md).**
Receipts: `.crew/.verify-verified-at` equals `git rev-parse HEAD` on a clean tree and
`.crew/.verify-gate.record.json`'s `rules` is empty or explained, the same comparison as
`review_prompt.py`'s `_receipts_block` (`verified == head and not manifest.get("dirty")`); no
`.crew/.scope-base` left in the bundle; lint = `.crew/verify.json`'s ruff and pylint rule. Heavy suites
run one at a time on a shared host.

