"""The three readers every crew script shares, and nothing else.

Split out of `crew_state.py` in 0.16.21 along with the endpoint ledger, which
had taken that module to pylint's `max-module-lines=3300` with five lines to
spare. These three live here rather than in either half because both halves
need them: putting them in `crew_endpoints` would make `crew_state` import a
git timeout from a module named for endpoints, and putting them in
`crew_state` would make the import run both ways.

`crew_state` re-exports all three, so `crew_config`, `pm_brief` and
`crew_upgrade` keep reaching them as `crew_state.read_text` and friends.

Standard library only, and every read fails soft, for the reason `crew_state`
does: this runs from a SessionStart hook, where an exception breaks every
session opened in the repository.
"""

import subprocess

GIT_TIMEOUT = 10


def read_text(path):
    """Return the file's text, or None if it cannot be read for any reason.

    utf-8-sig rather than utf-8: a BOM-prefixed file (Windows Notepad's
    default save) is otherwise valid utf-8 whose first character decodes as
    U+FEFF, which then makes json.loads reject an otherwise well-formed
    config as malformed. utf-8-sig strips a leading BOM when present and is
    a no-op on a plain utf-8 file, so every other reader here is unaffected.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except (OSError, ValueError):
        # ValueError covers a path Python rejects before touching the disk (an
        # embedded NUL raises rather than returning ENOENT). Unreachable from a
        # real filesystem, but this module must never raise from a SessionStart
        # hook under any input, so the cheap catch beats the argument about
        # reachability.
        return None


def git_out(root, *args):
    """Stripped stdout of a git command, or None on any failure.

    Failure includes git being absent and root not being a repository. Both
    are ordinary: the hook runs wherever the user opens a session.
    """
    try:
        done = subprocess.run(
            ("git",) + args, cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=GIT_TIMEOUT, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    # Without an explicit encoding, `text=True` decodes with the platform's
    # default (cp1252 on a Windows console) -- a diff containing one
    # undecodable byte then raises UnicodeDecodeError out of subprocess.run
    # itself, and this function's never-raises contract is what every
    # SessionStart caller relies on. utf-8/errors="replace" never raises and
    # never returns None for `done.stdout` (unlike the cp1252 path, which
    # left it None and made the `.strip()` below an AttributeError instead
    # of the intended "no diff" result).
    return done.stdout.strip()


def dict_or_empty(value):
    """`value` when it is genuinely a dict, else `{}`.

    `(cfg.get(k) or {})` is the tempting idiom and it is wrong: it guards a
    MISSING or falsy value but hands a wrong-typed truthy one straight through,
    so `"graph": "oops"` reaches `.get()` on a str and raises AttributeError.
    From a SessionStart hook that breaks every session opened in the repo.
    """
    return value if isinstance(value, dict) else {}
