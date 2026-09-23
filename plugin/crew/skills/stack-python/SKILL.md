---
name: stack-python
description: |
  Python-specific pitfalls, checks and verify.json wiring - mutable defaults, exception
  widening, the async model, text/bytes encoding. Use when the repo has pyproject.toml,
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
  `raise` alone to re-raise - `raise e` truncates the traceback.
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
  the full string first, then open.
- **Imports are executable.** Module-level work runs on import in whatever order the first
  importer chose; a circular import fails on only one of the two entry paths.
- **Dependencies are a decision.** Name any package added, what it replaced, and why the
  standard library would not do. Pin it the way the repo already pins.

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
