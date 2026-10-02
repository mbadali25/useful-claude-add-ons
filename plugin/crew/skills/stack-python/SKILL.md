---
name: stack-python
description: |
  Python-specific pitfalls, checks and verify.json wiring - mutable defaults, exception
  widening, the async model, text/bytes encoding - and a pointer to the gated PYTHON standards
  set and its candidates. Use when the repo has pyproject.toml,
  setup.py or requirements.txt, or the user asks to write or review Python, fix an async race,
  or asks why a script wrote a broken file or a shared list keeps growing across calls.
---

# Stack: Python

## When this applies

Any repo with `pyproject.toml`, `setup.py` or `requirements.txt`. Find the interpreter before
the bug - a virtualenv, a `tool.poetry` block or a pinned `python_requires` names which
interpreter the tests actually run under, and it is frequently not the one on `PATH`.

## Pitfalls that cost time

- **A mutable default argument is evaluated once, at definition.** `def f(x=[])` shares that
  list across every call for the life of the process. The same trap sits in a dataclass field
  or a class attribute holding a dict.
- **Exception handling that widens is exception handling that lies.** A bare `except:` catches
  `KeyboardInterrupt` and `SystemExit`; `except Exception` around a whole function turns a
  typo into a logged warning. Catch what you can act on, at the line that raises, and
  `raise` alone to re-raise - `raise e` truncates the traceback. PYTHON-11 is the gated form.
- **Truthiness is not presence.** `if not value` treats `0`, `""`, `[]` and `None` the same.
  Where the question is "was this supplied", test `is None`.
- **The async model is where the concurrency bugs are.** A coroutine created and not awaited
  never runs and warns at garbage-collection time, often into a log nobody reads. A blocking
  call inside `async def` (`requests`, `time.sleep`, a sync DB driver) stalls the whole loop.
  `asyncio.gather` over an unbounded list opens unbounded concurrency against whatever is on
  the other end.
- **Text and bytes are not interchangeable, and neither are line endings.** `open(p, "w")` is
  text mode - every `\n` becomes `\r\n` on Windows, which is how a shell script ships with a
  broken shebang. Pass `newline="\n"` when the consumer cares. `open(p, "w")` also truncates
  at open time, so a write whose *argument expression* raises leaves a zero-byte file - build
  the full string first, then open. PYTHON-01 (encoding, errors, newline) and PYTHON-04
  (replace, never rewrite in place) are the gated forms.
- **Imports are executable.** Module-level work runs on import in whatever order the first
  importer chose; a circular import fails on only one of the two entry paths.
- **Dependencies are a decision.** Name any package added, what it replaced, and why the
  standard library would not do. Pin it the way the repo already pins.

## Standards

The gated Python standards are `crew-standards/references/python.md`, set `PYTHON`, applied to
any change that touches a `.py` file and answered in the required self-check (the
`crew-standards` skill). Each is earned by findings from at least three distinct reviewed
change sets and cites them:

- PYTHON-01 Every text open and decode states its encoding, error handler and newline
- PYTHON-03 Records split on the separator the protocol defines, and one-line output is one line
- PYTHON-04 A file someone else reads is replaced, never rewritten in place
- PYTHON-06 Launch a child as an argv list, by a resolved path, through an interpreter Windows can run
- PYTHON-07 Every wait has a bound, and the bound uses a clock that cannot go backwards
- PYTHON-08 A child process gets a constructed environment and an explicit home
- PYTHON-10 Parsed JSON and TOML are checked for shape before they are indexed, hashed, joined or sorted
- PYTHON-11 The `try` body is the one call whose failure is being classified
- PYTHON-13 Paths are compared and contained only after canonicalisation, and junctions count

## Candidate standards (not gated)

Written up by T-0086's research, but earned by fewer than three reviewed change sets, so they
are guidance here and not rows of the self-check. Each is promoted into `python.md`, keeping its
id, when a third reviewed change set earns it.

- PYTHON-02 (0 change sets): console and pipe output survives a non-UTF-8 stdout - ASCII or a
  reconfigured stream, `PYTHONIOENCODING` for a child, portable `strftime` directives only.
- PYTHON-05 (1: T-0003): an exclusive-create lock treats Windows `PermissionError` as
  contention, and a failed stale-lock removal falls through to the same deadline and sleep.
- PYTHON-09 (2: T-0075, main(T1-T4)): `None`, absent, `False` and `0` are four different
  answers - test presence with `in` or `is None`, and a bool with `type(v) is bool`.
- PYTHON-12 (2: T-0072, T-0009): a last-resort handler formats nothing that can raise - no
  `str(exc)`, `repr()` or mixed-type `sorted()` on objects the code did not build.
- PYTHON-14 (2: T-0010, T-0008): a regex that recognises input is tested against every form
  the input really takes (`re.DOTALL`, `\Z` or `re.fullmatch`, dot-directories, continuations).
- PYTHON-15 (2: T-0030, main(B1-B3)): Unix-only and C-library-extension stdlib names
  (`os.getuid`, `os.killpg`, `signal.SIGKILL`, `os.O_NOFOLLOW`) are guarded where they are
  called, tests included.
- PYTHON-16 (0): a test that mutates a `.py` in place runs with `-B` or clears `__pycache__`,
  because a same-size edit restored within a second leaves a stale `.pyc`.
- PYTHON-17 (2: T-0075, T-0072): a CLI entry point is `main(argv=None) -> int`, refuses bad
  input with exit 2 and one stderr line, and never prints a traceback for input errors.

## Verification

Run whatever the repo runs (`pytest`, `unittest`, `tox`) with the repo's own interpreter and
report the exit code, never the summary line. `pylint` prints a score line that looks like a
pass while messages are still failing - read the status, not the tail. Split a run that
outlives the tool timeout rather than backgrounding it.

## verify.json rule to propose

```json
{
  "paths": ["**/*.py", "**/*.pyi"],
  "run": [
    "sh -c 'python3 -m ruff --version >/dev/null 2>&1 || { echo \"TOOL MISSING: ruff is not importable by this python3, so the lint pass DID NOT RUN. This is a missing tool, not a passing or failing check. Install ruff to check locally.\" >&2; exit 77; }; python3 -m ruff check .'"
  ],
  "reach": "local",
  "why": "ruff catches the common defects above before a human reads the diff"
}
```

Check whether the target repo's `.crew/verify.json` already has a `**/*.py` rule before adding
a second one that duplicates it - multiple matching rules simply both run, which wastes time
rather than breaking anything, but a `why` nobody can justify gets deleted later as cargo
cult. Nothing in this repo writes rules into `verify.json` on a skill's behalf (see the
`crew-verification` skill) - add or extend by hand.

## LSP

Use the official Python LSP plugin (decided for crew 1.0) rather than Serena, which was
evaluated and skipped for this stack.
