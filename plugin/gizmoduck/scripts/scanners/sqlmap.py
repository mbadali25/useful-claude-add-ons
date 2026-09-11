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

Round 2 fix: `run()` now returns the exact session directory it resolved
(via `_find_session_dir`), never the bare `--output-dir` root. run() is the
only place that ever holds the real URL sqlmap was pointed at, so it is the
only place that can reliably pick the one child folder belonging to this
target; handing back the root instead threw that identity away and forced
`parse()` to re-derive it later from a manifest name that may not even be a
URL. `_resolve_session_for_parse`'s candidate-matching logic (below) now
exists solely for `parse()` being called on a root with no prior run() in
this process - pre-existing/leftover artifacts - and refuses to guess
whenever that specific situation is unresolvable, rather than picking a
plausible-looking candidate.

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
_TYPE_LINE = re.compile(r'^\s*Type:\s*[^\r\n]+$', re.MULTILINE)

# sqlmap's own timestamped log line, e.g. `[10:14:02] [INFO] testing...` -
# present even on a genuinely clean run (see the `empty` fixture, which has
# no Parameter: block at all but plenty of these). Used, alongside
# _PARAM_HEADER, to tell real-but-empty sqlmap output apart from a file
# that isn't sqlmap output in the first place (defect 4).
_LOG_LINE = re.compile(r'^\[\d{2}:\d{2}:\d{2}\]\s*\[[A-Za-z]+\]', re.MULTILINE)

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
        # `--batch` alone answers sqlmap's own interactive prompts during
        # the scan, but on Windows sqlmap's cmdline parser
        # (lib/parse/cmdline.py) separately blocks on stdin with "Press
        # Enter to continue..." - a deliberate guard against someone
        # double-clicking the script - unless `--non-interactive` is
        # literally present in argv. This fires even on `--version` and is
        # NOT suppressed by `--batch`; without it, a routine run hangs until
        # base.run_tool's own timeout eventually kills it, which then
        # presents as a mysterious timeout rather than the hang it is.
        "--non-interactive",
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

    # CRITICAL defect fix (round 2): return the exact session directory
    # run() just resolved, not the --output-dir root. run() is the only
    # place that ever holds the real URL sqlmap was pointed at, and
    # _find_session_dir already used it to pick the one child folder that
    # actually belongs to this target - throwing that identity away and
    # handing back the bare root forced parse() to re-derive it later from
    # a manifest name that may not even be a URL (module docstring), which
    # is exactly the ambiguity that let sessions get misattributed or
    # silently dropped. Returning session_dir means the ordinary run()-then-
    # parse() cycle (routine.py's real call shape) never touches
    # _resolve_session_for_parse's candidate-matching logic at all - that
    # logic now exists solely for the "parse() called on a root with no
    # prior run() in this process" case (pre-existing/leftover artifacts).
    return str(session_dir), result


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


def _matches_target_host(child, target_host):
    """Whether candidate session directory `child` is plausibly the one
    scanned for `target_host` (already lowercased). Only meaningful when
    `target_host` is a real, known hostname - see _resolve_session_for_parse.

    A sidecar, when it exists and parses to a real hostname, is
    authoritative and decides this alone - even against the child's own
    folder name. That matters for a corrupted or reused directory whose
    sidecar disagrees with the name sqlmap itself gave the folder (round 2
    defect: "reports the injection against the wrong host"): trusting the
    folder name in that case would let a session actually recorded against
    some OTHER host get reported under this one purely because of where it
    happens to sit on disk. Only when there is no usable sidecar at all do
    we fall back to the folder's own name - which sqlmap itself always sets
    to the host it scanned (module docstring) - as the next best evidence.

    A sidecar that cannot be parsed as a URL at all (e.g. literally
    `http://[`) is treated the same as no sidecar, falling back to the
    folder name, rather than raising out of this boolean helper - the
    ValueError urlparse can raise on malformed authority text still must
    surface as base.ParseError somewhere in the parse() call chain (never
    crash the whole run), but one corrupt sidecar during candidate matching
    is exactly the kind of per-candidate noise this check should absorb.
    """
    sidecar = child / _TARGET_SIDECAR
    if sidecar.is_file():
        text = sidecar.read_text(encoding="utf-8", errors="replace").strip()
        try:
            declared = urlparse(text).hostname
        except ValueError:
            declared = None
        if declared:
            return declared.lower() == target_host
    return child.name.lower() == target_host


def _resolve_session_for_parse(raw_path, target):
    """Locate the session folder parse() should read from raw_path.

    Now that run() returns the exact session directory it resolved (round 2
    fix), the ordinary run()-then-parse() cycle never reaches the
    candidate-matching logic below at all: raw_path already IS a session
    folder, and the first check below returns it immediately. Everything
    past that point exists only for parse() being called directly against a
    root that holds pre-existing artifacts from outside this process - a
    root with no run() call in this call chain to have already resolved the
    ambiguity. Guessing in that situation is what caused every round 2
    defect (misattribution, false-clean, a stale leftover getting picked),
    so this resolver refuses whenever it cannot be certain, rather than
    picking a plausible-looking candidate.

    raw_path pointing directly at a session folder (holding `log` or
    `session.sqlite` itself) is unambiguous - return it unchanged, exactly
    like run()'s own resolver (`_find_session_dir`).

    With exactly one candidate under raw_path: if `target` carries a real,
    known hostname and that one candidate's identity (_matches_target_host)
    contradicts it, that is active evidence the session isn't the one being
    asked about - not "nothing to disambiguate" - so this is a confident
    negative, not a blind pick. Otherwise (target is opaque, or the
    candidate matches) it is used, since there truly is nothing else it
    could be.

    With two or more candidates: a known `target` hostname narrows by
    identity - a unique match is used, zero matches is a confident negative
    (parse() then correctly reads no session for this host), and more than
    one match is still ambiguous enough to refuse. An opaque `target` (a
    bare manifest name, routine.py's real call shape when reached without a
    resolved session dir) gives no signal to narrow with at all: this
    resolver no longer falls back to "trust whichever sidecar merely agrees
    with its own folder name" - that heuristic correlates with nothing
    about the actual target being asked about, and is exactly what let a
    stale, internally-consistent leftover session get silently selected and
    reported as a clean scan. Refuses instead.
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
    if not candidates:
        return raw_path

    try:
        target_host = urlparse(target).hostname if target else None
    except ValueError:
        target_host = None
    if target_host:
        target_host = target_host.lower()

    if len(candidates) == 1:
        only = candidates[0]
        if target_host is not None and not _matches_target_host(only, target_host):
            return raw_path
        return only

    if target_host is not None:
        matches = [c for c in candidates if _matches_target_host(c, target_host)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            # Known host, confirmed absent from every candidate: a
            # determined negative, not a gap (defect 2's original intent,
            # preserved).
            return raw_path
        raise base.ParseError(
            "sqlmap output directory %r holds %d sessions that all appear "
            "to belong to target %r; refusing to guess which is "
            "authoritative" % (str(raw_path), len(matches), target))

    # Opaque manifest name (not a URL) with 2+ untargeted candidates: no
    # signal correlates any of them with what's actually being asked about.
    raise base.ParseError(
        "sqlmap output directory %r holds %d candidate sessions and "
        "target %r is not a URL, so none of them can be confirmed or "
        "ruled out; refusing to guess which one (if any) belongs to "
        "this target" % (str(raw_path), len(candidates), target))


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
        try:
            host = urlparse(url).hostname
        except ValueError:
            host = None
        if host:
            return host, url
    return session_dir.name, session_dir.name


def _looks_like_sqlmap_log(text):
    """Whether `text` carries at least one marker sqlmap itself writes -
    either a timestamped `[HH:MM:SS] [LEVEL]` log line (present even on a
    genuinely clean run - see the `empty` fixture, which has no Parameter:
    block at all but plenty of these) or a `Parameter:` block header.

    Neither marker present means this file isn't sqlmap output at all - a
    garbage file, an unrelated log, wholly truncated content - which must
    raise base.ParseError rather than silently being read as zero findings.
    A real clean run and unreadable output are not the same claim
    (defect 4; base.ParseError's own docstring).
    """
    return bool(_LOG_LINE.search(text) or _PARAM_HEADER.search(text))


def _iter_confirmed(text):
    """Yield each confirmed (param, place, type, title, payload) record.

    DEFECT 4 fix: for each Parameter: block, every `Type:` line found must
    resolve into one complete Type/Title/Payload triple. A block with more
    `Type:` lines than complete triples means a record started but never
    finished - e.g. a scan killed mid-write, cutting the block off after
    `Title:` and before `Payload:`. That is not "this parameter turned out
    clean" (which would simply have no Type: line at all, as in the `empty`
    fixture) - it is unusable, truncated evidence, and must raise
    base.ParseError instead of silently yielding nothing for it.
    """
    headers = list(_PARAM_HEADER.finditer(text))
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        param, place = header.group("param"), header.group("place")

        triples = list(_TRIPLE.finditer(block))
        type_lines = _TYPE_LINE.findall(block)
        if len(triples) != len(type_lines):
            raise base.ParseError(
                "sqlmap log has a Parameter block for %r (%s) with %d "
                "Type: line(s) but only %d complete Type/Title/Payload "
                "record(s) - the log looks truncated or corrupted, not a "
                "clean run" % (param, place, len(type_lines), len(triples)))

        for m in triples:
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

    try:
        text = log_path.read_text(errors="replace")
    except OSError as e:
        raise base.ParseError("could not read sqlmap log %s: %s" % (log_path, e)) from e

    # DEFECT 4 fix: a log that exists but isn't readable as sqlmap output at
    # all - a garbage file, an unrelated log, wholly corrupted content -
    # must raise base.ParseError rather than read as a clean scan just
    # because _iter_confirmed's regex happens to find no Parameter: blocks
    # in it. A genuinely clean sqlmap run still carries its own timestamped
    # log lines (see the `empty` fixture) even with zero injection points,
    # so this check does not affect a real clean scan.
    if not _looks_like_sqlmap_log(text):
        raise base.ParseError(
            "%s does not look like sqlmap log output; refusing to read it "
            "as a clean scan" % log_path)

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
