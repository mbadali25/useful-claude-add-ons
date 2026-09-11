"""sqlmap adapter - the one ACTIVE=True scanner in the registry.

sqlmap sends real attack traffic (SQL injection payloads) at the target, so
it carries gates beyond the normal active/DEFAULT_ENABLED gate routine.py
applies from these module constants:

1. A confirm token. `run()` refuses outright - before anything is built into
   an argv, let alone executed - unless `opts["confirm"]` is truthy. This is
   the explicit approval token spec section 8 and the plan both require, and
   it is checked here rather than trusted to whatever calls in from
   routine.py (Task 14/15, not yet built): a defense that holds regardless of
   who constructs `opts`.
2. A concrete injection point. sqlmap targets one parameterized URL, never a
   blind sweep across a site (spec section 8) - `run()` also refuses a
   target with no query string, since that is not "an injection point" in
   any meaningful sense.

Cross-adapter contract (standardized after this file's first commit):
`run(target, outdir, opts) -> (raw_path: str | None, result: base.ToolResult)`.
`raw_path` is None whenever sqlmap was not actually run, or ran but left no
session artifacts; `result` is always returned, including for the two gates
above, so routine.py can always fall back to it for `error:<reason>` /
`error:timeout` in the per-cell run manifest (spec section 6 step 5). A
declined gate is deliberately NOT an error, though: it returns a ToolResult
whose `returncode` is the Python value `None` - never an int, unlike every
real invocation (a normal exit, or the -1 sentinel base.run_tool itself uses
for a timeout or a missing binary) - so `result.returncode is None` is an
unambiguous "we chose not to fire" signal a caller can use to record
skipped-active rather than mistaking a deliberately declined sqlmap run for
a broken one in the coverage table. Unlike every other adapter in this
package, sqlmap's "raw path" is a session DIRECTORY, not a single file - the
native artifact is the small tree `--output-dir` produces (`log` +
`session.sqlite` under a per-host folder), and `parse()` is written to
accept either that folder directly or the `--output-dir` root above it.

There is no --report-json flag (spec 13.9, confirmed against
lib/core/optiondict.py) - sqlmap leaves behind an --output-dir session tree
(a per-host folder holding `log` and `session.sqlite`) plus stdout, and this
parser reads only the former, never stdout. A CONFIRMED injection is one
sqlmap actually persisted, with a recorded Type and Payload; probed-and-
negative parameters are discarded and never written anywhere. sqlmap exits 0
on normal completion whether or not anything was found, so parse() has no
returncode parameter to look at in the first place - the exit code cannot
leak into the finding count even by accident.

A note on where "persisted" facts really live: sqlmap's own session.sqlite is
a HashDB cache (see its lib/utils/hashdb.py) - a single `storage` table whose
values are zlib+pickle blobs keyed by an internal hash, not humanly-readable
Type/Payload rows. Unpickling that blob to recover structured facts would mean
replicating sqlmap's internal cache format (which shifts across versions) and
running unpickle against a blob this process did not itself just create in
memory - both fragile and needless risk for no benefit, since sqlmap already
writes the exact same Type/Title/Payload facts as stable, documented plain
text in the `log` file living next to session.sqlite in that same output
directory. This adapter therefore treats `log` as the source of truth for
confirmed injections and treats session.sqlite only as corroborating evidence
that a session actually ran (its presence, not its content, is checked) -
this is a correction to the plan's phrasing worth flagging back, not a
shortcut around it: it satisfies "read session artifacts, never scrape
stdout" using the one artifact of the pair that is actually safe and stable
to parse.
"""
import re
from pathlib import Path
from urllib.parse import urlparse

from . import base
import normalize as n

NAME = "sqlmap"
KINDS = ["web"]
ACTIVE = True
ACTIVE_OPTS = []          # single mode - always active, no safe/active split
DEFAULT_ENABLED = False

CONFIRM_KEY = "confirm"   # opts[CONFIRM_KEY] must be truthy or run() refuses

# Type text that means the confirmed technique reaches actual database
# content (a UNION query returns arbitrary column data; stacked queries run
# arbitrary attacker SQL), vs. techniques that only prove the injection
# exists (boolean-based / time-based / error-based blind). Matched against
# the lowercased "Type:" line from the log (spec: "confirmed injection ->
# high; stacked-queries or UNION with database access -> critical").
_CRITICAL_MARKERS = ("union", "stacked queries")

_PARAM_HEADER = re.compile(
    r'^Parameter:\s*(?P<param>\S+)\s*\((?P<place>[^)]*)\)\s*$', re.MULTILINE)
_TRIPLE = re.compile(
    r'Type:\s*(?P<type>[^\r\n]+)\r?\n\s*Title:\s*(?P<title>[^\r\n]+)\r?\n'
    r'\s*Payload:\s*(?P<payload>[^\r\n]+)')


def is_available():
    return base.which("sqlmap") is not None


def _has_injection_point(target):
    """sqlmap targets one parameterized URL, never a blind sweep (spec s8)."""
    return bool(urlparse(target).query)


def _declined(reason):
    """A ToolResult for a run() gate that refused before any subprocess.

    `returncode=None` is the point: base.run_tool never produces that value
    for a real invocation (success and every failure path it has - a normal
    exit, or its own -1 sentinel for a timeout/missing binary - are always
    ints), so `result.returncode is None` is an unambiguous, type-level
    signal that this run never actually fired. routine.py should read that
    as skipped-active, never error.
    """
    return base.ToolResult(returncode=None, stdout="", stderr=reason, timed_out=False)


def run(target, outdir, opts):
    opts = opts or {}
    if not opts.get(CONFIRM_KEY):
        return None, _declined(
            "sqlmap declined: opts[%r] is required and was not set; sqlmap "
            "sends real SQL injection traffic and will not fire on an "
            "implicit default" % CONFIRM_KEY)
    if not _has_injection_point(target):
        return None, _declined(
            "sqlmap declined: %r has no query string; sqlmap targets a "
            "specific injection point, never a blind sweep" % target)

    timeout = int(opts.get("timeout", 300))
    time_limit = int(opts.get("time_limit", timeout))
    argv = [
        opts.get("sqlmap_bin", "sqlmap"),
        "-u", target,
        "--batch",
        "--time-limit=%d" % time_limit,
        "--output-dir=%s" % outdir,
    ]
    result = base.run_tool(argv, timeout=timeout, cwd=None)
    if result.timed_out:
        return None, result

    session_dir = _find_session_dir(outdir)
    if not (session_dir / "log").is_file() and not (session_dir / "session.sqlite").is_file():
        # sqlmap exits 0 whether or not it found anything (spec 13.9), and
        # can also exit 0 having written nothing at all - so success here is
        # decided by whether a session actually landed on disk, never by
        # result.returncode.
        return None, result
    return str(outdir), result


def _find_session_dir(raw_path):
    """Locate the per-host session folder holding `log` under raw_path.

    sqlmap creates a subfolder per target host under --output-dir. Accept
    raw_path pointing either directly at that folder (what our fixtures and
    tests use) or at the --output-dir root sqlmap itself was given (what
    run() actually passes as outdir), searching one level down for whichever
    child looks like a session folder.
    """
    raw_path = Path(raw_path)
    if (raw_path / "log").is_file() or (raw_path / "session.sqlite").is_file():
        return raw_path
    if raw_path.is_dir():
        for child in sorted(raw_path.iterdir()):
            if child.is_dir() and (
                (child / "log").is_file() or (child / "session.sqlite").is_file()
            ):
                return child
    return raw_path


def _iter_confirmed(text):
    headers = list(_PARAM_HEADER.finditer(text))
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        param, place = header.group("param"), header.group("place")
        for m in _TRIPLE.finditer(block):
            yield (param, place.strip(), m.group("type").strip(),
                   m.group("title").strip(), m.group("payload").strip())


def parse(raw_path, target):
    session_dir = _find_session_dir(raw_path)
    log_path = session_dir / "log"
    if not log_path.is_file():
        # No log at all means no session ran, or nothing survived long
        # enough to be persisted - either way, zero findings, never a
        # low-severity "nothing found" placeholder (spec 13.9).
        return []

    text = log_path.read_text(errors="replace")
    host = urlparse(target).hostname or target
    findings = []
    for param, place, type_, title, payload in _iter_confirmed(text):
        type_slug = re.sub(r'[^a-z0-9]+', '-', type_.lower()).strip('-')
        place_slug = re.sub(r'[^a-z0-9]+', '-', place.lower()).strip('-') or "req"
        rule_id = "%s-%s-%s" % (param, place_slug, type_slug)
        severity = 4 if any(marker in type_.lower() for marker in _CRITICAL_MARKERS) else 3
        findings.append(n.make_finding(
            tool=NAME,
            target=target,
            rule_id=rule_id,
            name="SQL injection: %s (%s) - %s" % (param, place or "?", type_),
            severity=severity,
            severity_known=True,
            type="sqli",
            host=host,
            matched_at=target,
            description=title,
            remediation=("Use parameterized queries / prepared statements for "
                         "the %r parameter; never concatenate user input into "
                         "SQL." % param),
            reference=["https://cwe.mitre.org/data/definitions/89.html"],
            tags=["sqlmap", "confirmed"] + ([place_slug] if place_slug != "req" else []),
        ))
    return findings
