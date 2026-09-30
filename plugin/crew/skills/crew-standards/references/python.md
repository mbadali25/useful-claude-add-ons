---
set: PYTHON
applies-to: ["**/*.py"]
---

# Python development standards (PYTHON)

Build-time standards for Python 3, applied when any changed file matches `**/*.py` (T-0086, slice 1).
Each standard refines the GEN standard its Rule names and supplies the Python mechanics; it does not ask
GEN's question a second time. A standard ships here only when findings from at least three distinct
reviewed change sets earn it. A change set is a crew review (a ticket's round, or one of the `main(...)`
reviews GEN describes) or a fix commit whose own message or CHANGELOG entry records that a review found
the defect; a commit that belongs to a ticket counts as that ticket, once. `crew-1.0.9`, `crew-1.0.13`
and `crew-1.0.20` are the independent-review rounds of those crew versions on the `crew-1.0` branch,
squash-merged into `main` as `6c497a14`; `THDDEV-1134` is a security-review round in the private
TheHomeDepot repository. Official documentation, session notes and `CLAUDE.md` lines are not change
sets: a doc is kept as **Source**, quoted from docs.python.org at "Python 3.14.7 documentation", each
sentence re-read from the raw page. Ids keep the research numbering, so a gap (02, 05, 09, 12, 14-17)
is a candidate listed in the `stack-python` skill; promoting one keeps its id. A self-check's grep is an
example starting grep, not the definition.

## PYTHON-01 Every text open and decode states its encoding, error handler and newline

**Rule.** Refines GEN-01 (`errors="replace"` is one of its triggers). Every `open()` in text mode,
`Path.read_text`/`write_text`, `bytes.decode`, `str.encode`, `TextIOWrapper` and
`subprocess.run(..., text=True)` passes `encoding=` explicitly (`"utf-8"` unless a format says
otherwise). The `errors=` handler is chosen for the data: `"strict"` where bad input must be refused or
reported; `"surrogateescape"` where arbitrary bytes must round-trip unchanged (paths, git output,
patches); `"replace"`/`"ignore"` only for display text that is never re-written, re-parsed or reviewed.
A writer that may receive a lone surrogate (anything from `json.loads`) uses `"backslashreplace"` or
`"surrogatepass"` deliberately, and catches `UnicodeError`, which is a `ValueError`, not an `OSError`.
Every text write that another tool reads states `newline=` (`"\n"` for anything bash, git or a POSIX
tool consumes). Input from Windows tools (PowerShell 5.1 scripts, piped CLI output) is decoded with a
named fallback chain (BOM check, UTF-8, then the ANSI codepage), never a silent `"replace"`.

**Why.** The locale default is UTF-8 on the Linux machines the code is written on and cp1252 on Windows,
so the bug is invisible until a non-ASCII byte arrives on the other platform. 3 findings across 3 change
sets: a patch silently corrupted before review, a "best-effort" logger that aborted its caller on a lone
surrogate, a scan that could not see a cp1252 script.

**Change sets.** 3: main(T1-T4), crew-1.0.13, T-0002

**Applies when.** Any `open(`, `read_text`, `write_text`, `.decode(`, `.encode(`, `text=True`,
`universal_newlines=`, `json.load(open(...))`, or a write whose output is later read by a shell, git, a
reviewer or a parser.

**Self-check.**
1. Does every text-mode open, decode and encode in the diff pass `encoding=`? Pass: yes, every site
   (run the tests once with `python -X warn_default_encoding` and see no `EncodingWarning` from changed
   lines).
2. For each `errors=`: is the data ever re-written, re-parsed, hashed or shown to a reviewer? Pass: if
   yes, the handler is `strict` or `surrogateescape`, never `replace`/`ignore`.
3. For each writer of text that can contain data from `json.loads` or a subprocess: tested with
   `"\ud800"` in the payload? Pass: no traceback, and the except clause (if any) names `UnicodeError`.
4. For each file written for bash, git or a POSIX tool: `newline="\n"` present, and the worktree bytes
   checked with `od -c` or `file` (not `git show`, which can render CRLF regardless)? Pass: yes.
5. For each input that may come from a Windows tool: tested with a cp1252 non-ASCII byte and with a BOM?
   Pass: decoded correctly or refused loudly, never garbled.
   Example starting grep, not the definition: `open\(|read_text|write_text|\.decode\(|\.encode\(|text=True|errors=`.

**Earned by.**
- main(T1-T4) r2 @8b8a4028+dirty, FIX `plugin/crew/hooks/scripts/review_patch.py:67`: "The patch is
  decoded with errors=replace, silently corrupting non-UTF-8 text before review"
- crew-1.0.13 review fix, commit `476048af` (origin/crew-1.0), "crew_autocycle.py: log_autoclear survives
  a lone surrogate instead of raising": "message can carry a lone UTF-16 surrogate (a \ud800 escape from
  an unknown JSON key, which json.loads decodes without complaint but cannot re-encode as UTF-8). A
  strict handle.write() under encoding="utf-8" then raised UnicodeEncodeError - a ValueError, not the
  OSError the except caught"
- T-0002 review round 1 fix, commit `114b5e6a` (shipped in `f2bb919b`, #230), "crew 1.0.29: SendWait
  scan reads UTF-32 BOM and BOM-less ANSI scripts too": "A cp1252 .ps1 (what Windows PowerShell 5.1 reads
  a BOM-less file as) with a non-ASCII byte fails UTF-8 and, at even length, 'decodes' as UTF-16
  garbage, so its SendWait call was invisible."

**Source.**
- https://docs.python.org/3/library/io.html, "Text Encoding": "The default encoding of TextIOWrapper and
  open() is locale-specific (locale.getencoding())." "This causes bugs because the locale encoding is not
  UTF-8 for most Windows users." "it is highly recommended that you specify the encoding explicitly when
  opening text files." Same page: "you can enable the -X warn_default_encoding command line option or
  set the PYTHONWARNDEFAULTENCODING environment variable, which will emit an EncodingWarning when the
  default encoding is used."
- https://docs.python.org/3/library/functions.html#open: "'ignore' ignores errors. Note that ignoring
  encoding errors can lead to data loss." "'surrogateescape' will represent any incorrect bytes as low
  surrogate code units ranging from U+DC80 to U+DCFF." "If newline is '' or '\n', no translation takes
  place."
- https://docs.python.org/3/library/exceptions.html, `UnicodeError`: "It is a subclass of ValueError."

## PYTHON-03 Records split on the separator the protocol defines, and one-line output is one line

**Rule.** Refines GEN-06 (the line protocol). Text another program produced or will consume (JSONL
events, `key=value` verdict lines, reviewer output, log lines) is split on `"\n"` (after stripping a
trailing `"\r"` where CRLF is allowed), never with `str.splitlines()`, which also breaks on `\v`, `\f`,
`\x1c`-`\x1e`, `\x85`, U+2028 and U+2029. A sanitiser for line output escapes every character
`splitlines()` treats as a break, not only C0/C1 controls. A CLI documented as one line per record
emits `json.dumps(obj)` with no `indent`.

**Why.** 3 findings across 3 change sets: a raw U+2028 inside a Codex event cut the JSON mid-record and
scored a review round INCOMPLETE; a peer-written string could forge an unlabelled status line through the
same character; a `--json` flag emitted pretty-printed multi-line output against a one-line contract.

**Change sets.** 3: T-0079, T-0030, T-0072

**Applies when.** `splitlines(`, `.split("\n")`, iterating a file of records, a sanitiser for text that
is printed into line-oriented output, `json.dumps(..., indent=...)` on a path that prints to stdout.

**Self-check.**
1. Does the diff call `splitlines()` on text that is not purely human prose? Pass: no.
2. Feed each new parser and sanitiser a record containing U+2028, U+0085 and `\x1c` inside a JSON string
   value. Pass: one record in, one record out.
3. For each stdout path with a documented line count, every flag included: count the lines. Pass: equal
   to the documented count.

**Earned by.**
- T-0079 commit `e9b02f79`, "T-0079: split reviewer output on newline only (U+2028 amendment)":
  "review_verdict.parse and codex_final_message split with str.splitlines(), which also breaks at
  U+2028/U+2029/U+0085 and the C0 separators; a raw U+2028 inside a Codex event cut it mid-JSON and scored
  T-0072 round 4 INCOMPLETE."
- T-0030 r1 @e2a23f08, FIX `plugin/crew/hooks/scripts/crew_coord.py:101`: "safe() strips only C0/C1
  control characters. It leaves U+2028/U+2029 (which str.splitlines treats as line breaks) and bidi
  overrides. A peer-written holder.session can therefore forge a separate status line with no
  [peer-written] label"
- T-0072 r4 @37fa2322, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:1204`: "`deploy-allowed --json`
  always emits pretty-printed multi-line stdout, contradicting the documented one-line CLI [...]"; fixed
  in `0f488706`.

**Source.** https://docs.python.org/3/library/stdtypes.html#str.splitlines: "This method splits on the
following line boundaries. In particular, the boundaries are a superset of universal newlines." Its
table lists `\n`, `\r`, `\r\n`, `\v`, `\f`, `\x1c`, `\x1d`, `\x1e`, `\x85`, `\u2028` and `\u2029`.

## PYTHON-04 A file someone else reads is replaced, never rewritten in place

**Rule.** Refines GEN-02. To change a file another process, user or later step reads: build the full
content in memory; `tempfile.mkstemp(dir=<the destination's directory>, prefix=".<name>-")`; write,
`flush()`, `os.fsync()`; copy the destination's mode onto the temp if it exists; `os.replace(tmp,
dest)`; remove the temp in a `finally` if the replace did not happen. On Windows, `os.replace` onto a
file another process holds open can fail with `PermissionError`; retry a bounded number of times (not
until a wall-clock deadline, PYTHON-07), then report failure. `os.replace` makes one file's swap atomic;
it is not a lock: a read-modify-write of a shared file still needs GEN-02's lock or compare-and-swap, or
the last writer drops the first writer's keys. Several files saved as one operation clean up every
staged temp on any failure and report which files landed.

**Why.** `open(p, "w")` truncates before the payload exists. 4 findings across 4 change sets: a staged
multi-file save left orphaned temps; two atomic replaces still lost concurrent updates; a Windows retry
loop spun forever on a frozen clock.

**Change sets.** 4: T-0075, T-0030, crew-1.0.9, T-0003

**Applies when.** Any write to a path that exists before the write, any config, ledger, state or JSON
file, any `os.replace`/`os.rename`/`shutil.move`, any multi-file save.

**Self-check.**
1. For each write to a pre-existing path: is it a temp in the same directory then `os.replace`, with the
   content computed before any `open`? Pass: yes (`with open(dest, "w")` on an existing file is a
   fail).
2. Is the temp removed on every failure path (`finally`)? Pass: yes, with a test that makes `os.replace`
   raise and asserts no temp remains.
3. Is the file read-modify-written by more than one process? Pass: no, or a lock or compare-and-swap per
   GEN-02 covers the whole read-modify-write.
4. Is any Windows retry bounded by an attempt count? Pass: yes, and a test freezes `time.time` and
   `time.monotonic` and still sees it terminate.
5. Does the replace keep the old file's mode (`mkstemp` creates the file readable and writable by its
   owner only)? Pass: yes, or the notes say why that mode is intended.

**Earned by.**
- T-0075 r2 @b4911045, FIX `plugin/crew/hooks/scripts/crew_config.py:2974`: "Concurrent repo writes
  merge against stale snapshots, so the later atomic replace silently discards the earlier session's
  unrelated update"
- T-0030 r1 @e2a23f08, FIX `plugin/crew/hooks/scripts/crew_coord.py:323`: "update_identity does a
  read-modify-write of <git-common-dir>/crew/coord-identity.json with no lock. [...] The last os.replace
  wins"
- crew-1.0.9 review fix, commit `f415703c` (origin/crew-1.0): "crew_autoclear_setup.py's
  apply_migrate_to_repo commit loop [...] had no cleanup of its own: an os.replace failure partway
  through left every unconsumed staged temp file behind. Now wrapped in try/finally"
- T-0003 Codex BLOCK fix, commit `10ac72ce` (shipped in `a1828a5d`, #235): "_replace_with_retry retried
  PermissionError until a time.time() deadline while holding the ledger lock; a clock stepped backwards,
  or a constant time.time, kept it spinning forever (Codex BLOCK). It now makes at most
  _REPLACE_RETRY_ATTEMPTS (20) tries"

**Source.**
- https://docs.python.org/3/library/functions.html#open: "open for writing, truncating the file first".
- https://docs.python.org/3/library/os.html#os.replace: "If dst exists and is a file, it will be
  replaced silently if the user has permission." "If successful, the renaming will be an atomic
  operation (this is a POSIX requirement)." `os.fsync`: "first do f.flush(), and then do
  os.fsync(f.fileno()), to ensure that all internal buffers associated with f are written to disk."
- https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp: "The file is readable and writable
  only by the creating user ID."
- The Windows `PermissionError` on replace is T-0003's measurement, not a sentence in the docs.

## PYTHON-06 Launch a child as an argv list, by a resolved path, through an interpreter Windows can run

**Rule.** Refines GEN-06 (the shell sink) and GEN-08. `subprocess` calls take an argv list and
`shell=False`; a command string with interpolated values and `shell=True` is refused. The executable is
resolved to an absolute path (`shutil.which`, then `os.path.abspath`) before any `cwd=` change; a
relative `PATH` hit is made absolute. Python is launched as `sys.executable`. On Windows a `.bat`/`.cmd`
or an extensionless shebang script cannot be launched directly: run it through its interpreter
(`[bash, script]`, or `["cmd", "/c", ...]` with the documented batch-escaping caveat) or find the `.cmd`
shim. A command printed for a user to run is quoted for the shell that will run it: `shlex.quote` is
POSIX only; for cmd.exe and PowerShell use their own quoting or print the argv as JSON.

**Why.** 3 findings across 3 change sets, each failing only on the platform the author did not run: a
relative `PATH` entry broken by `cwd=`, a shebang script native Windows `CreateProcess` cannot start, a
printed restore command cmd.exe could not execute.

**Change sets.** 3: T-0028, T-0030, T-0075

**Applies when.** `subprocess.run`/`Popen`/`call`/`check_output`, `os.system`, `shutil.which`, `cwd=`,
any string printed as "run this".

**Self-check.**
1. Is every `subprocess` argument a list with `shell=False`? Pass: yes, or `shell=True` with a fixed
   literal command and a comment saying why.
2. Is the executable absolute before `cwd=` takes effect? Pass: yes (test: put the tool in `./bin`,
   prepend `./bin` to `PATH`, run with a different `cwd`).
3. Can each launched file be started by Windows `CreateProcess` directly (a real `.exe`)? Pass: yes, or
   it is launched through its interpreter.
4. For each printed command: which shell runs it, and was it executed in that shell in a test? Pass: yes.

**Earned by.**
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/kimi_probe.py:269`: "A working Kimi binary found
  through a relative PATH entry becomes unlaunchable in the probe's temporary directory"
- T-0030 r6 @b20cf9ee, FIX `plugin/crew/tests/test_crew_coord.py:505`: "The default Windows suite still
  launches a POSIX shell script directly through native Python subprocess, so the receivepack test
  cannot succeed."
- T-0075 r1 @87627d86, BLOCK `plugin/crew/hooks/scripts/crew_config_menu.py:528`: "The printed restore
  command uses POSIX shlex quoting and cannot execute under Windows cmd.exe"

**Source.** https://docs.python.org/3/library/subprocess.html, "Security Considerations": "If the shell
is invoked explicitly, via shell=True, it is the application's responsibility to ensure that all
whitespace and metacharacters are quoted appropriately to avoid shell injection vulnerabilities." "On
Windows, batch files (*.bat or *.cmd) may be launched by the operating system in a system shell
regardless of the arguments passed to this library." Same page, `Popen`: "For maximum reliability, use a
fully qualified path for the executable." "passing sys.executable is the recommended way to launch the
current Python interpreter again".

## PYTHON-07 Every wait has a bound, and the bound uses a clock that cannot go backwards

**Rule.** Refines GEN-01 (a timeout is could-not-tell, not success). Every
`subprocess.run`/`communicate`/`wait` has `timeout=`. On `TimeoutExpired` from `communicate`, kill the
child and call `communicate()` again with its own timeout, because a descendant that escaped the kill
can hold the pipe open; then close the pipes and report the timeout. Kill a process group by its
leader's pid only while `proc.poll() is None` (a reaped pid can be reused). Deadlines use
`time.monotonic()`; retries are bounded by a count. A deadline check runs on every path through a loop,
the "passing" and "retry now" paths included. Opening a path the code did not create checks it is a
regular file first (`os.stat` and `stat.S_ISREG`, or `O_NONBLOCK`), because opening a FIFO blocks. A
network or subprocess read has a byte cap.

**Why.** 7 findings across 5 change sets: a post-kill `communicate()` that could block forever and a
pid-reuse kill; a retry loop on `time.time()` that spun forever and a stale-lock loop that skipped its
deadline; a passing poll that skipped the timeout check and merged late; a fingerprint walk that blocked
on a FIFO; an unbounded HTTP response read.

**Change sets.** 5: crew-1.0.20, T-0003, T-0011, T-0028, THDDEV-1134

**Applies when.** `subprocess`, `communicate`, `wait`, `while True`, `time.time()` in a deadline or
duration, `os.kill`/`os.killpg`, any directory walk that opens files, `resp.read()`.

**Self-check.**
1. Does every subprocess call and wait in the diff have `timeout=`? Pass: yes.
2. After `TimeoutExpired`: kill, then a second bounded `communicate`? Pass: yes, with a test whose child
   spawns a detached grandchild that keeps the pipe.
3. Is any `time.time()` used to measure a duration or a deadline? Pass: no (`time.monotonic()`).
4. For each loop with a deadline: does every `continue` and every early-success path pass the deadline
   check? Pass: yes (test: freeze the clock, or make the check pass after the deadline, and assert the
   loop still ends as a timeout).
5. Does any walk open files it did not create without checking they are regular? Pass: no.

**Earned by.**
- crew-1.0.20 review fix, commit `af5cadd2` (origin/crew-1.0), "Three BLOCK findings from an
  independent review": "review_run.py's launch() killed a timed-out provider's process group by bare pid
  without checking the leader was still alive; once reaped, that pid is free for reuse." and "The
  post-kill communicate() had no timeout, so a descendant that escaped the kill (still holding the pipe)
  could block past --timeout indefinitely."
- T-0003 Codex BLOCK fixes, commits `10ac72ce` (quoted under PYTHON-04: a `time.time()` deadline "kept it
  spinning forever") and `a7ad99b3` (shipped in `a1828a5d`, #235): "_acquire_endpoints_lock took
  `continue` after a stale-lock os.remove whether or not the remove succeeded. When it raised OSError
  (PermissionError on Windows, a read-only directory) every pass skipped both the monotonic deadline
  check and the sleep, so declare_endpoint busy-spun forever"
- T-0011 r1 @4dcf45e4, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:460`: "A passing poll bypasses
  the timeout check, allowing merges after ciTimeoutMinutes expires."
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/review_run.py:225`: "Fingerprinting can block
  indefinitely on a FIFO, outside the reviewer timeout"
- THDDEV-1134 security review round 2, TheHomeDepot commit `84328fb9`: "push_truckload() read the full
  HTTP response body into memory with no size bound before parsing. New MAX_SRL_RESPONSE_BYTES (64 KiB)
  cap"

**Source.**
- https://docs.python.org/3/library/subprocess.html#subprocess.Popen.communicate: "The child process is
  not killed if the timeout expires, so in order to cleanup properly a well-behaved application should
  kill the child process and finish communication". The docs' kill-then-`communicate()` example has no
  second timeout; the escaped-descendant case that needs one is crew-1.0.20's, not the docs'.
- https://docs.python.org/3/library/time.html#time.monotonic: "The clock is not affected by system clock
  updates." `time.time`: "it can return a lower value than a previous call if the system clock has been
  set back between the two calls."

## PYTHON-08 A child process gets a constructed environment and an explicit home

**Rule.** Refines GEN-08 and GEN-04. Environment a function depends on (`GIT_OPTIONAL_LOCKS=0`, a
dropped secret token, a pinned locale) is set by that function for its own child, not by `main()`, so a
library caller gets the same behaviour. Children get `env=` built from a copy with secrets removed. A
path under the user's home honours the tool's override variable (`CLAUDE_CONFIG_DIR` and the like)
before `~`. Tests that run a child process isolate both `HOME` and `USERPROFILE` (Windows
`expanduser` ignores `HOME` since 3.8), because an in-process monkeypatch does not reach a child. A
probe that launches another agent or tool passes an explicit `cwd` and the restricted profile, and runs
after any "before" snapshot it is meant to be covered by. The call site that builds the child's env and
argv is tested, not only the helper.

**Why.** 6 findings across 5 change sets: a library entry point that rewrote `.git/index` because the
env was set only in `main()`; a test child that read the owner's real global config, and the same fix
incomplete on Windows until `USERPROFILE` was set; a hardcoded `~/.claude` ignoring the config-dir
override; an unrestricted probe launched in the reviewed repository before the tamper snapshot; a test
that checked the env helper and not the call site.

**Change sets.** 5: T-0008, T-0023, T-0016, T-0028, T-0030

**Applies when.** `subprocess` with or without `env=`, `os.environ[...] =` in `main()`, `expanduser`,
`Path.home()`, a test that spawns the code under test as a child.

**Self-check.**
1. Is any env var the behaviour depends on set outside the function that spawns the child? Pass: no.
2. Does each child's `env` exclude secrets it does not need? Pass: yes, tested at the call site.
3. Does each home-relative path check the tool's override variable first? Pass: yes.
4. Does each test that spawns a child set both `HOME` and `USERPROFILE` to a temp directory? Pass: yes.

**Earned by.**
- T-0008 r1 @33ba3adb, FIX `plugin/crew/hooks/scripts/crew_refresh_check.py:258`: "ticket_freshness, the
  entry point T-0004 imports, rewrites .git/index. GIT_OPTIONAL_LOCKS=0 is set only in main() (:328), so
  for a library caller the working-tree `git diff` refreshes the index stat cache"
- T-0023 commits `311388b7`, "test_cli_settings_and_decide_exit_zero ran crew_route.py in a child
  process, which conftest's GLOBAL_CONFIG_PATH monkeypatch cannot reach, so the child read the real
  ~/.claude/crew/config.json.", and `488053fc` (review round 1): "_env set HOME only, which Windows'
  expanduser ignores. It and test_crew_route's CLI helper now set HOME and USERPROFILE to the same empty
  directory"
- T-0016 r1 @1275d2c4, FIX `plugin/crew/hooks/scripts/crew_autocycle.py:519`: "The record lookup
  hardcodes ~/.claude/sessions and ignores CLAUDE_CONFIG_DIR"
- T-0028 r1 @6f005fa2, FIX `plugin/crew/hooks/scripts/kimi_probe.py:219`: "The live probe launches
  `kimi -p` with the default agent profile [...] runs in the inherited cwd (the repo under review), and
  runs before tree_fingerprint's `before` snapshot."
- T-0030 r1 @e2a23f08, FIX `plugin/crew/hooks/scripts/crew_coord.py:679`: "Its argv, its interval, its
  start_new_session setting, and its use of child_env() to drop CLAUDE_CODE_MESSAGING_TOKEN can all break
  silently. test_heartbeat_child_environment_drops_the_messaging_token (:708) checks the helper, not the
  call site."

**Source.** https://docs.python.org/3/library/os.path.html#os.path.expanduser: "On Unix, an initial ~ is
replaced by the environment variable HOME if it is set" "On Windows, USERPROFILE will be used if set,
otherwise a combination of HOMEPATH and HOMEDRIVE will be used." "Changed in version 3.8: No longer uses
HOME on Windows."

## PYTHON-10 Parsed JSON and TOML are checked for shape before they are indexed, hashed, joined or sorted

**Rule.** Refines GEN-07 (the Python mechanics of "validated for type and shape"). After
`json.loads`/`json.load`/`tomllib.loads`, nothing is indexed, used as a dict key, joined, iterated,
passed to `dict()` or compared until an `isinstance` check has established its type, at every nesting
level the code touches. Syntactically valid input of the wrong shape (a list where an object was
expected, an int where a string was, an inline table where a name was) returns the reader's unknown or
refusal value, never a `TypeError`, `AttributeError` or `KeyError`. Where the data comes from outside,
decide explicitly about what the `json` module accepts by default: `NaN`/`Infinity`
(`parse_constant=`), duplicate keys where the last one wins (`object_pairs_hook=`), and lone surrogates
(PYTHON-01).

**Why.** 4 findings across 3 change sets: `{"text": 1}` crashed string joining in review finalisation;
an array as a provider reference crashed `dict.get` (unhashable); `{"machine": 1}` crashed on
`dict(1)`; a lone surrogate from `json.loads` crashed a writer later.

**Change sets.** 3: T-0028, T-0075, crew-1.0.13

**Applies when.** `json.load(s)`, `tomllib.load(s)`, `yaml.safe_load`, reading any stored record or
provider output.

**Self-check.**
1. For each new reader: fed `[]`, `1`, `"x"`, `null`, `{"key": []}` and `{"key": {"nested": 1}}` in
   place of each object it expects? Pass: unknown or refusal each time, no traceback.
2. Is any parsed value used as a dict key or set member before it is proven hashable (a `str` or an
   `int`)? Pass: no.
3. For external input: fed `NaN`, a duplicated key, and `"\ud800"`? Pass: each is refused or handled by
   a documented choice.

**Earned by.**
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/review_verdict.py:170`: "Malformed JSON content
  parts crash both probe classification and review finalisation instead of producing unknown or
  INCOMPLETE"
- T-0028 r4 @dae560cc, FIX `plugin/crew/hooks/scripts/kimi_probe.py:179`: "Syntactically valid TOML with
  a malformed provider reference crashes instead of returning unknown"
- T-0075 r2 @b4911045, FIX `plugin/crew/hooks/scripts/crew_config_menu.py:777`: "The save CLI validates
  only the outer change-set object and crashes on non-object layer values instead of refusing them with
  exit 2"
- crew-1.0.13 review fix, commit `476048af` (quoted under PYTHON-01): the lone surrogate came from
  `json.loads`, "which json.loads decodes without complaint but cannot re-encode as UTF-8".

**Source.** https://docs.python.org/3/library/json.html, "Standard Compliance and Interoperability": "by
default, this module accepts and outputs Infinity, -Infinity, and NaN as if they were valid JSON number
literal values"; "By default, this module does not raise an exception; instead, it ignores all but the
last name-value pair for a given name" "The object_pairs_hook parameter can be used to alter this
behavior."

## PYTHON-11 The `try` body is the one call whose failure is being classified

**Rule.** Refines GEN-01. When an exception class carries meaning (`FileNotFoundError` = absent,
`ProcessLookupError` = gone), the `try` block contains only the probe call. Paths, arguments and lookups
it needs are computed before the `try`, so the same exception class raised by preparation cannot be
misread as the probe's answer. Know each error's family: `UnicodeError` and `json.JSONDecodeError` are
`ValueError`s, not `OSError`s; a wrong-type input raises `TypeError`; an application exception is none
of these. A handler that must turn every failure into a verdict names all of them or catches
`Exception` at the boundary (never a bare `except:`), and keeps the cause with `raise ... from exc` when
it re-raises.

**Why.** 5 findings across 3 change sets: an absence handler that also caught the same exception from
finding the checkout and downgraded `refuse` to `ask`; a non-`OSError` failure treated as absence; a
bytes root that raised `TypeError` in a path join before the probe; a save that caught only `OSError`
and let a domain exception escape after half the write; a `UnicodeEncodeError` that walked past
`except OSError`.

**Change sets.** 3: T-0072, T-0075, crew-1.0.13

**Applies when.** Any `try` whose `except` clause maps an exception class to a meaning; any "best
effort" or "never raises" function.

**Self-check.**
1. For each `try` whose handler assigns a meaning: does the body contain only the one call whose failure
   that meaning describes? Pass: yes (a join, lookup or conversion inside it is a fail).
2. Make each preparation step raise the handled class (patch it). Pass: the result is not the handler's
   meaning.
3. For each "best effort" or "never raises" function: which exception families can its body raise
   (`OSError`, `ValueError` including `UnicodeError`, `TypeError`, domain exceptions)? Pass: every one
   reaches the intended verdict, tested.
4. Does every re-raise that converts an exception use `from exc`? Pass: yes.

**Earned by.**
- T-0072 r3 @2fa75f79, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:714`: "The missing-path handler
  also catches `FileNotFoundError` or `NotADirectoryError` raised while finding the checkout,
  misreporting that failed incident check as absence and downgrading the required `refuse` to `ask`"
- T-0072 r2 @ec5d2ff2, FIX `plugin/crew/hooks/scripts/crew_autopilot.py:708`: "A non-OSError failure
  while checking the incident path becomes `ask`, contradicting the rule that only
  FileNotFoundError/NotADirectoryError mean absent"; and T-0072's round-5 fix, commit `0f488706`: "a
  bytes path joined onto the str incident path raised TypeError before _probe, and the crash asked
  instead of refusing"
- T-0075 r1 @87627d86, FIX `plugin/crew/hooks/scripts/crew_config_menu.py:401`: "Save catches only
  OSError after prevalidation, so a concurrent repo deletion or corruption raises RepoWriteRefused after
  the machine layer was written and escapes without the required partial-write report"
- crew-1.0.13 review fix, commit `476048af` (quoted under PYTHON-01): "raised UnicodeEncodeError - a
  ValueError, not the OSError the except caught"

**Source.**
- https://docs.python.org/3/library/exceptions.html, `UnicodeError`: "It is a subclass of ValueError."
- https://docs.python.org/3/tutorial/errors.html, "Exception Chaining": "To indicate that an exception is
  a direct consequence of another, the raise statement allows an optional from clause" "This can be
  useful when you are transforming exceptions."

## PYTHON-13 Paths are compared and contained only after canonicalisation, and junctions count

**Rule.** Refines GEN-06 (containment at the sink). Two paths (or a path and a `file://` URL, or a
relative remote path) are compared for identity only after the same canonicalisation: resolve relative
paths against the directory they are relative to, convert `file://` to a path, then `os.path.realpath`
(and `os.path.normcase` on Windows). Containment is `os.path.commonpath([root, candidate]) == root` on
resolved paths, never `startswith` or `os.path.commonprefix`. A "not a link" check uses
`os.path.islink(p) or os.path.isjunction(p)` (3.12+) or, better, compares the resolved path with the
expected one, because a Windows junction is not a symlink. `str` and `bytes` paths are never mixed; a
function that accepts path-like input refuses `bytes` or converts it with `os.fsdecode` first. A
producer and its consumer apply the same rule (a backup accepted by delete is accepted by restore).

**Why.** 5 findings across 4 change sets: a junction-redirected `.crew` passed an `islink` check;
relative and `file://` spellings of one repository produced two claim keys and two holders; delete
accepted a symlinked config whose backup restore then refused; a `bytes` root crashed a path join.

**Change sets.** 4: main(B1-B3), T-0030, T-0075, T-0072

**Applies when.** `os.path.join`, `realpath`, `abspath`, `resolve`, `islink`, `startswith` on a path,
comparing remotes or paths for identity, any "must be under X" check, any path from config, argv or git.

**Self-check.**
1. For each path identity comparison: are both sides canonicalised by the same function, relative and
   `file://` forms included? Pass: yes (test: two spellings of one location give one key).
2. For each containment check: `commonpath` on resolved paths? Pass: yes (test with `root + "-evil"` as
   a sibling, which `startswith` accepts).
3. For each link check: does it also catch a junction, or compare the resolved target? Pass: yes, or
   `NOT RUN ON WINDOWS` recorded.
4. Fed a `bytes` path and a `pathlib.Path`? Pass: `bytes` refused cleanly, `Path` accepted.

**Earned by.**
- main(B1-B3) r3 @8b8a4028+dirty, BLOCK `plugin/crew/hooks/scripts/pm_journal.py:147` (file removed in
  c3bd8dfd): "An out-of-repo .crew directory is rejected only when os.path.islink() recognizes it;
  Windows directory junctions resolve outside the repo but are not symlinks, allowing reads and appends
  outside containment"
- T-0030 r5 @81617867, FIX `plugin/crew/hooks/scripts/crew_coord.py:749`: "Relative local origin paths
  are not resolved against the repository root, so two spellings of one repository produce separate
  claims and permit two holders."
- T-0030 r6 @b20cf9ee, FIX `plugin/crew/hooks/scripts/crew_coord.py:889`: "file:// origins bypass
  realpath resolution, so equivalent local origins can grant two holders for one ticket."
- T-0075 r3 @1fbc70fb, BLOCK `plugin/crew/hooks/scripts/crew_config_menu.py:752`: "delete accepts a
  symlink to valid JSON but the resulting backup is rejected by restore's realpath/location rule,
  breaking the verified-restorable guarantee"
- T-0072 round-5 fix, commit `0f488706` (quoted under PYTHON-11): a bytes root joined onto a str path
  raised `TypeError`.

**Source.** https://docs.python.org/3/library/os.path.html#os.path.isjunction: "Return True if path
refers to an existing directory entry that is a junction. Always return False if junctions are not
supported on the current platform." Same page, `os.path.commonprefix`: "If you need a common path
prefix, then the algorithm implemented in this function is not secure. Use commonpath() for finding a
common path prefix."
