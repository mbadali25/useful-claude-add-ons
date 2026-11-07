#!/usr/bin/env python3
"""promote-gate.sh's allow fast path (crew 1.2.114): prove, in ONE python,
that a command deploys nothing, so the gate can stop there.

    python3 _promote_fast.py < <hook payload>      (cwd: the project dir)

Exit 99 means ALLOW: every check below passed. Any other outcome - 0, a
traceback's 1, a kill - means "not proved", and promote-gate.sh then runs its
full gate, unchanged, which decides exactly as it always did. So this file can
only ever skip work the full gate would have ended in an allow; it never
blocks, and nothing it prints is read (the gate sends its output to
/dev/null). 99, not 0: an empty or truncated file also exits 0.

Why: on Git Bash every process start is an MSYS fork, and the full gate took
some forty of them to clear `echo hi` - the jq or `python -c` payload reads,
`git hash-object`, two more pythons, and the `tr` and `uname` around them.
With several lanes running at once that is what timed the guards out.

What has to hold, each the same question the full gate asks:

1. The payload is a JSON object whose `tool_input.command` is a string of
   plain printable ASCII (tab and newline allowed), not blank once trailing
   newlines go. The full gate reads it with jq (or python), drops trailing
   newlines (`$(...)`) and CRs; on that text the two readings are equal.
2. MSYS argument conversion leaves it alone. The full gate hands the command
   to native python as an ARGUMENT, and Git Bash rewrites an argument that
   starts like a POSIX path (`/x`, `x=/y`, `-I/y`) into a Windows one, so the
   full gate matches the rewritten text. This reads the payload instead, so
   it refuses any command whose first word holds `/` or `\\` (measured on
   Git Bash: a `/` later in the argument is left alone). Off Windows nothing
   is rewritten and the rule only costs a fall-through.
3. The map is committed as it is: `.crew/verify.json` exists, HEAD has it,
   and its bytes, or its bytes with every CRLF made LF (a `core.autocrlf`
   checkout), hash to HEAD's blob. Then the full gate's `git hash-object`
   finds no dirt, or finds only an end-of-line rewrite of the same JSON, and
   the committed map it would match as well holds the same document.
4. The containment match names no environment and refuses nothing. It is not
   a copy: the heredoc that promote-gate.sh runs for it is read out of
   promote-gate.sh and run here with the same argument and environment, so
   the two can never disagree.
   One difference in how it runs: the full gate runs that heredoc as
   `python -`, whose first import path is the cwd (the project dir), so a
   project file named like one of its imports (`json.py`) would shadow the
   standard library there. A project holding such a file falls through.
5. `_promote_dispatch.decide()` returns nothing and raises nothing, as the
   full gate's second python step would print nothing.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

ALLOW = 99
_HERE = os.path.dirname(os.path.abspath(__file__))
_GATE = os.path.join(_HERE, "promote-gate.sh")
_MAP = ".crew/verify.json"
_MATCH_START = ('ENVNAMES=$(CREW_HEAD_MAP="$HEAD_MAP" CREW_MAP_DIRTY="$MAP_DIRTY" '
                '"$PY" - "$CMD" <<\'PY\'\n')
_MATCH_END = "\nPY\n"
_PLAIN = frozenset(chr(c) for c in range(0x20, 0x7F)) | {"\t", "\n"}


def _command(raw):
    """Check 1 and 2: the command, or None."""
    doc = json.loads(raw.decode("utf-8"))
    tool_input = doc.get("tool_input") if isinstance(doc, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not set(command) <= _PLAIN:
        return None
    command = command.rstrip("\n")
    words = command.split(None, 1)
    if not words or "/" in words[0] or "\\" in words[0]:
        return None
    return command


def _left():
    """Seconds left before the gate's own deadline, at most 5."""
    try:
        deadline = int(os.environ.get("CREW_GATE_DEADLINE", ""))
    except ValueError:
        return 5.0
    return min(5.0, deadline - time.time() - 2)


def _head_map():
    """HEAD's blob id for the map, as the full gate's `git rev-parse` gives it."""
    git = shutil.which("git")
    left = _left()
    if git is None or left <= 0:
        return None
    proc = subprocess.run([git, "rev-parse", "-q", "--verify", "HEAD:./" + _MAP],
                          capture_output=True, check=False, timeout=left,
                          stdin=subprocess.DEVNULL)
    blob = proc.stdout.decode("ascii", "replace").strip()
    if proc.returncode != 0 or len(blob) not in (40, 64) or blob.strip("0123456789abcdef"):
        return None
    return blob


def _blob_id(data, algo):
    digest = hashlib.new(algo)
    digest.update(b"blob %d\0" % len(data))
    digest.update(data)
    return digest.hexdigest()


def _committed_as_is(blob):
    """Check 3."""
    with open(_MAP, "rb") as handle:
        data = handle.read()
    algo = "sha1" if len(blob) == 40 else "sha256"
    return blob in (_blob_id(data, algo), _blob_id(data.replace(b"\r\n", b"\n"), algo))


def _match_source():
    """The containment match's python, exactly as promote-gate.sh runs it."""
    with open(_GATE, encoding="utf-8") as handle:
        text = handle.read()
    if text.count(_MATCH_START) != 1:
        return None
    start = text.index(_MATCH_START) + len(_MATCH_START)
    end = text.find(_MATCH_END, start)
    return None if end == -1 else text[start:end + 1]


def _shadowed(source):
    """Whether the cwd holds a module the heredoc imports (check 4's note)."""
    for line in re.findall(r"^(?:import|from)\s+([\w., ]+)", source, re.M):
        for name in re.findall(r"\w+", line.split(" import ")[0]):
            if name != "import" and (os.path.exists(name + ".py") or os.path.isdir(name)):
                return True
    return False


def _matches_nothing(command, source):
    """Check 4: the heredoc, run as `"$PY" - "$CMD"` with a clean map."""
    if _shadowed(source):
        return False
    code = compile(source, "promote-gate.sh (containment match)", "exec", dont_inherit=True)
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = ["-", command]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                exec(code, {"__name__": "__main__"})  # pylint: disable=exec-used
                status = 0
            except SystemExit as stop:
                status = 0 if stop.code is None else stop.code
    finally:
        sys.argv = saved
    return status == 0 and out.getvalue() == ""


def _dispatches_nothing(command):
    """Check 5, as `_promote_dispatch.py "$CMD"` reads its argument."""
    import _promote_dispatch  # pylint: disable=import-outside-toplevel
    text = command.replace("\r", "").rstrip("\n")
    return not text.strip() or _promote_dispatch.decide(text, "bash") == []


def allowed(raw):
    command = _command(raw)
    if command is None or not os.path.isfile(_MAP):
        return False
    blob = _head_map()
    if blob is None or not _committed_as_is(blob):
        return False
    # What the full gate exports to both of its python steps for a clean map.
    os.environ["CREW_HEAD_MAP"] = blob
    os.environ["CREW_MAP_DIRTY"] = ""
    source = _match_source()
    if source is None or not _matches_nothing(command, source):
        return False
    return _dispatches_nothing(command)


def main():
    try:
        return ALLOW if allowed(sys.stdin.buffer.read()) else 0
    except BaseException:  # pylint: disable=broad-except
        # A doubt of any kind is "not proved": the full gate decides.
        return 0


if __name__ == "__main__":
    sys.exit(main())
