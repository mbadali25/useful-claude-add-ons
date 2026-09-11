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

`run()`'s first argument is the target's *location* (routine.py passes it
`_location(target)`, i.e. the manifest's `url` field - a real URL, always).
`parse()`'s second argument is a different thing entirely: routine.py calls
`mod.parse(raw_path, target.name)`, where `target.name` is the operator-
chosen manifest label (spec section 5) - a string like "prod-web" with no
guaranteed relationship to the host actually scanned, and frequently not a
URL at all. Deriving `host`/`matched_at` by calling `urlparse()` on that
argument - what this module's `parse()` originally did - silently produces
`None`/garbage the moment a manifest name isn't itself a URL, which is the
common case once routine.py (rather than a direct unit test passing a URL
by hand) is the real caller. `host`/`matched_at` are therefore sourced only
from session artifacts: a small sidecar file `run()` writes into the
session directory recording the exact URL sqlmap was pointed at
(`_write_target_sidecar`), or - lacking that, e.g. artifacts from before
this fix - the session directory's own name, which sqlmap itself always
sets to the scanned host. `target` is still used for the finding's own
`target` field (spec section 6) and, in `run()`, for the query-string gate
and argv construction - both legitimate there because `run()`'s `target`
really is the location.

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

# Sidecar run() drops in the session directory it actually used, recording
# the real URL sqlmap was pointed at - see the module docstring's "run()'s
# first argument is the target's location..." paragraph for why parse()
# cannot recover this from its own `target` argument.
_TARGET_SIDECAR = ".gizmoduck-sqlmap-target"


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

    session_dir = _find_session_dir(outdir, target)
    if not (session_dir / "log").is_file() and not (session_dir / "session.sqlite").is_file():
        # sqlmap exits 0 whether or not it found anything (spec 13.9), and
        # can also exit 0 having written nothing at all - so success here is
        # decided by whether a session actually landed on disk, never by
        # result.returncode. Note this is deliberately NOT the same check as
        # "does parse() have something to read" - session.sqlite alone still
        # counts as a session having happened here; parse() is where an
        # incomplete session (session.sqlite but no log) turns into an error
        # instead of a silent empty result. See parse()'s docstring.
        return None, result
    _write_target_sidecar(session_dir, target)
    return str(outdir), result


def _write_target_sidecar(session_dir, url):
    """Persist the exact URL sqlmap was pointed at, next to its own session
    artifacts.

    `target` here is `run()`'s argument, which - unlike parse()'s - really
    is the location (see module docstring). Writing it down is what lets
    parse() (called later, possibly by routine.py with only the manifest's
    bare name) recover the real host/matched-at without guessing. This is
    our own metadata, not scraped sqlmap output - the "never scrape stdout"
    rule elsewhere in this file is about *tool* output, not about a caller
    remembering its own inputs. Best-effort: a failure to write this must
    never turn a completed scan into a failed one.
    """
    try:
        (Path(session_dir) / _TARGET_SIDECAR).write_text(url, encoding="utf-8")
    except OSError:
        pass


def _find_session_dir(raw_path, target):
    """Locate the per-host session folder holding `log` under raw_path.

    sqlmap creates a subfolder per target host under --output-dir. Accept
    raw_path pointing either directly at that folder (what our fixtures and
    tests use) or at the --output-dir root sqlmap itself was given (what
    run() actually passes as outdir), searching one level down for whichever
    child belongs to `target`'s host.

    That host match matters: a bare --output-dir root can (and in practice
    will, across repeated runs against different hosts) hold more than one
    child folder. Picking "whichever child has artifacts, alphabetically
    first" - the previous behaviour - attributes findings to a host that was
    never tested, and lets an alphabetically-earlier empty session hide a
    later vulnerable one for a different host entirely. Only a folder whose
    name actually matches the requested host is eligible; if none does, we
    fall through to raw_path itself, which parse() then reads as having no
    log/session.sqlite for this target - i.e. zero findings, never someone
    else's.
    """
    raw_path = Path(raw_path)
    if (raw_path / "log").is_file() or (raw_path / "session.sqlite").is_file():
        return raw_path
    if raw_path.is_dir():
        host = (urlparse(target).hostname or target).lower()
        for child in sorted(raw_path.iterdir()):
            if child.is_dir() and child.name.lower() == host and (
                (child / "log").is_file() or (child / "session.sqlite").is_file()
            ):
                return child
    return raw_path


def _resolve_session_for_parse(raw_path, target):
    """Locate the session folder parse() should read from raw_path.

    This is deliberately a separate resolver from the one run() uses
    (`_find_session_dir`): run()'s `target` is guaranteed to be the real
    location, so matching a child folder by its urlparse()'d hostname is
    sound there. parse()'s `target` is the manifest's opaque name (module
    docstring) - it may not parse as a URL at all, so it cannot be used the
    same way here.

    raw_path pointing directly at a session folder (holding `log` or
    `session.sqlite` itself) is unambiguous - return it unchanged, exactly
    like run()'s resolver. A raw_path that is instead an --output-dir root
    can hold more than one child that looks like a session (stale leftovers
    from a previous host, a shared root). With exactly one such child there
    is nothing to disambiguate - use it. With more than one, the only
    trustworthy signal is the sidecar run() wrote into the session directory
    it actually used (`_write_target_sidecar`): never an arbitrary
    alphabetical pick, and never a guess derived from `target`.
    """
    raw_path = Path(raw_path)
    if (raw_path / "log").is_file() or (raw_path / "session.sqlite").is_file():
        return raw_path
    if not raw_path.is_dir():
        return raw_path

    candidates = [
        child for child in sorted(raw_path.iterdir())
        if child.is_dir() and (
            (child / "log").is_file() or (child / "session.sqlite").is_file()
        )
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return raw_path

    target_host = urlparse(target).hostname if target else None
    matches = []
    for child in candidates:
        sidecar = child / _TARGET_SIDECAR
        if not sidecar.is_file():
            continue
        declared_host = urlparse(
            sidecar.read_text(encoding="utf-8", errors="replace").strip()).hostname
        if not declared_host:
            continue
        if target_host is not None:
            if declared_host == target_host:
                matches.append(child)
        elif declared_host == child.name:
            # `target` gave us no hostname to check against (a bare
            # manifest name) - fall back to internal consistency: trust a
            # sidecar only when it agrees with the folder sqlmap itself
            # created it under.
            matches.append(child)

    if len(matches) == 1:
        return matches[0]
    # Zero or multiple equally-plausible candidates: refuse to guess. The
    # caller ends up with no log/session.sqlite at raw_path itself, which
    # parse() reads as zero findings - never someone else's (defect 2).
    return raw_path


def _session_location(session_dir, target):
    """The (host, matched_at) pair to stamp on findings from session_dir.

    Never derived from `target` (see module docstring) - it is the sidecar
    run() wrote (the one authoritative source: the exact URL sqlmap was
    pointed at), or, lacking that, the session directory's own name, which
    sqlmap itself always sets to the host/IP it scanned. Both sources are
    real session artifacts; neither is a guess.
    """
    sidecar = session_dir / _TARGET_SIDECAR
    if sidecar.is_file():
        url = sidecar.read_text(encoding="utf-8", errors="replace").strip()
        host = urlparse(url).hostname
        if host:
            return host, url
    return session_dir.name, session_dir.name


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
    session_dir = _resolve_session_for_parse(raw_path, target)
    log_path = session_dir / "log"
    if not log_path.is_file():
        if (session_dir / "session.sqlite").is_file():
            # session.sqlite is proof sqlmap actually started against this
            # host, but `log` - the only file this parser ever reads facts
            # from - never got written. That is not "ran clean", it is
            # "we don't know what this run found" (most likely --time-limit
            # or a kill cut it off mid-scan, before it persisted results).
            # run() and parse() must agree on what counts as usable evidence:
            # run() reports a session happened (raw_path is not None), and
            # parse() is where an unusable one becomes an explicit error
            # rather than silently collapsing into zero findings - the
            # single worst outcome for the one adapter here that fires real
            # attack traffic (base.ParseError's docstring; spec 13.9).
            raise base.ParseError(
                "sqlmap session at %r has session.sqlite but no log - the "
                "scan was interrupted before results were persisted; this "
                "is not a clean run" % str(session_dir))
        # No artifacts at all means no session ever ran for this host -
        # zero findings, never a low-severity "nothing found" placeholder
        # (spec 13.9).
        return []

    text = log_path.read_text(errors="replace")
    host, matched_at = _session_location(session_dir, target)
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
            matched_at=matched_at,
            description=title,
            remediation=("Use parameterized queries / prepared statements for "
                         "the %r parameter; never concatenate user input into "
                         "SQL." % param),
            reference=["https://cwe.mitre.org/data/definitions/89.html"],
            tags=["sqlmap", "confirmed"] + ([place_slug] if place_slug != "req" else []),
        ))
    return findings
