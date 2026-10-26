<!-- crew-standards-export digest=df6052ac0825389b086b6ca038d9f2c0e191ea1a5407dee8f55424f8dff3a8e6 crew=1.2.86 -->
# Review rules: set PYTHON

Applies to: files matching `**/*.py`.
Generated from crew's standards by `crew_standards.py export --write`; do not edit by hand. Check a change against every standard here whose scope matches the files it touches.

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

## PYTHON-03 Records split on the separator the protocol defines, and one-line output is one line

**Rule.** Refines GEN-06 (the line protocol). Text another program produced or will consume (JSONL
events, `key=value` verdict lines, reviewer output, log lines) is split on `"\n"` (after stripping a
trailing `"\r"` where CRLF is allowed), never with `str.splitlines()`, which also breaks on `\v`, `\f`,
`\x1c`-`\x1e`, `\x85`, U+2028 and U+2029. A sanitiser for line output escapes every character
`splitlines()` treats as a break, not only C0/C1 controls. A CLI documented as one line per record
emits `json.dumps(obj)` with no `indent`.

**Self-check.**
1. Does the diff call `splitlines()` on text that is not purely human prose? Pass: no.
2. Feed each new parser and sanitiser a record containing U+2028, U+0085 and `\x1c` inside a JSON string
   value. Pass: one record in, one record out.
3. For each stdout path with a documented line count, every flag included: count the lines. Pass: equal
   to the documented count.

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

## PYTHON-06 Launch a child as an argv list, by a resolved path, through an interpreter Windows can run

**Rule.** Refines GEN-06 (the shell sink) and GEN-08. `subprocess` calls take an argv list and
`shell=False`; a command string with interpolated values and `shell=True` is refused. The executable is
resolved to an absolute path (`shutil.which`, then `os.path.abspath`) before any `cwd=` change; a
relative `PATH` hit is made absolute. Python is launched as `sys.executable`. On Windows a `.bat`/`.cmd`
or an extensionless shebang script cannot be launched directly: run it through its interpreter
(`[bash, script]`, or `["cmd", "/c", ...]` with the documented batch-escaping caveat) or find the `.cmd`
shim. A command printed for a user to run is quoted for the shell that will run it: `shlex.quote` is
POSIX only; for cmd.exe and PowerShell use their own quoting or print the argv as JSON.

**Self-check.**
1. Is every `subprocess` argument a list with `shell=False`? Pass: yes, or `shell=True` with a fixed
   literal command and a comment saying why.
2. Is the executable absolute before `cwd=` takes effect? Pass: yes (test: put the tool in `./bin`,
   prepend `./bin` to `PATH`, run with a different `cwd`).
3. Can each launched file be started by Windows `CreateProcess` directly (a real `.exe`)? Pass: yes, or
   it is launched through its interpreter.
4. For each printed command: which shell runs it, and was it executed in that shell in a test? Pass: yes.

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

**Self-check.**
1. Does every subprocess call and wait in the diff have `timeout=`? Pass: yes.
2. After `TimeoutExpired`: kill, then a second bounded `communicate`? Pass: yes, with a test whose child
   spawns a detached grandchild that keeps the pipe.
3. Is any `time.time()` used to measure a duration or a deadline? Pass: no (`time.monotonic()`).
4. For each loop with a deadline: does every `continue` and every early-success path pass the deadline
   check? Pass: yes (test: freeze the clock, or make the check pass after the deadline, and assert the
   loop still ends as a timeout).
5. Does any walk open files it did not create without checking they are regular? Pass: no.

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

**Self-check.**
1. Is any env var the behaviour depends on set outside the function that spawns the child? Pass: no.
2. Does each child's `env` exclude secrets it does not need? Pass: yes, tested at the call site.
3. Does each home-relative path check the tool's override variable first? Pass: yes.
4. Does each test that spawns a child set both `HOME` and `USERPROFILE` to a temp directory? Pass: yes.

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

**Self-check.**
1. For each new reader: fed `[]`, `1`, `"x"`, `null`, `{"key": []}` and `{"key": {"nested": 1}}` in
   place of each object it expects? Pass: unknown or refusal each time, no traceback.
2. Is any parsed value used as a dict key or set member before it is proven hashable (a `str` or an
   `int`)? Pass: no.
3. For external input: fed `NaN`, a duplicated key, and `"\ud800"`? Pass: each is refused or handled by
   a documented choice.

## PYTHON-11 The `try` body is the one call whose failure is being classified

**Rule.** Refines GEN-01. When an exception class carries meaning (`FileNotFoundError` = absent,
`ProcessLookupError` = gone), the `try` block contains only the probe call. Paths, arguments and lookups
it needs are computed before the `try`, so the same exception class raised by preparation cannot be
misread as the probe's answer. Know each error's family: `UnicodeError` and `json.JSONDecodeError` are
`ValueError`s, not `OSError`s; a wrong-type input raises `TypeError`; an application exception is none
of these. A handler that must turn every failure into a verdict names all of them or catches
`Exception` at the boundary (never a bare `except:`), and keeps the cause with `raise ... from exc` when
it re-raises.

**Self-check.**
1. For each `try` whose handler assigns a meaning: does the body contain only the one call whose failure
   that meaning describes? Pass: yes (a join, lookup or conversion inside it is a fail).
2. Make each preparation step raise the handled class (patch it). Pass: the result is not the handler's
   meaning.
3. For each "best effort" or "never raises" function: which exception families can its body raise
   (`OSError`, `ValueError` including `UnicodeError`, `TypeError`, domain exceptions)? Pass: every one
   reaches the intended verdict, tested.
4. Does every re-raise that converts an exception use `from exc`? Pass: yes.

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

**Self-check.**
1. For each path identity comparison: are both sides canonicalised by the same function, relative and
   `file://` forms included? Pass: yes (test: two spellings of one location give one key).
2. For each containment check: `commonpath` on resolved paths? Pass: yes (test with `root + "-evil"` as
   a sibling, which `startswith` accepts).
3. For each link check: does it also catch a junction, or compare the resolved target? Pass: yes, or
   `NOT RUN ON WINDOWS` recorded.
4. Fed a `bytes` path and a `pathlib.Path`? Pass: `bytes` refused cleanly, `Path` accepted.

