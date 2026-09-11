"""testssl.sh adapter - TLS/cipher/vuln checks per host.

Uses `--jsonfile`, never `--jsonfile-pretty`: the pretty variant nests results
under a header block and can emit invalid JSON on some runs (upstream issue
#1699), while `--jsonfile` is flat - one self-contained object per check,
carrying `id, ip, port, severity, finding` plus `cve`/`cwe` where the check
maps to one.

The severity field is one of eight real values: OK, INFO, LOW, MEDIUM, HIGH,
CRITICAL, WARN, FATAL. Only the first six describe the target. WARN and FATAL
mean testssl itself hit a client-side problem running that particular check
(a stale CRL fetch, a refused connection) - they are not a security rating,
and mapping them as one would make a broken scan report as a vulnerability.
`parse()` excludes them from the finding list entirely; `parse_errors()` is
the additive hook `routine` (Task 15) calls to fold them into the per-cell
run-manifest entry for this (target, tool) instead of losing them.

Exit code is never used to gate success here: testssl.sh reserves 50-200 for
a severity-scored exit, 1 for a generic error, and 242-255 for internal
errors (spec 13.12) - none of that is "did this run produce a usable file".
`--connect-timeout`/`--openssl-timeout` are per-connection and per-check, so
they cannot cap the whole scan; `base.run_tool`'s own timeout is the real
guard (spec 13.13).
"""
import json
import os
from pathlib import Path

from . import base
import normalize

NAME = "testssl"
KINDS = ["web", "host"]
ACTIVE = False
ACTIVE_OPTS = []  # single mode - nothing here makes a run active
DEFAULT_ENABLED = True

# testssl.sh has no whole-scan cap of its own (spec 13.13); this is the
# fallback base.run_tool timeout when the manifest/opts don't set one.
_DEFAULT_TIMEOUT = 900

# testssl.sh hard-requires `hexdump` and refuses to run at all without it
# ("You need to install hexdump for this program to work."). Git for
# Windows' bundled Git Bash - the bash this adapter actually runs
# testssl.sh under on an operator's machine - ships xxd/od but not hexdump;
# a sibling MSYS2 install commonly does. These are fallback locations to
# search, never a patch to testssl.sh itself (out of bounds - vendored
# upstream script).
_MSYS2_HEXDUMP_CANDIDATES = tuple(
    p for p in (
        os.environ.get("GIZMODUCK_MSYS2_BIN"),
        r"C:\tools\msys64\usr\bin",
        r"C:\msys64\usr\bin",
    ) if p
)

# bootstrap.ps1 only ever git-clones testssl.sh on Windows - nothing puts a
# directly executable testssl.sh/testssl on PATH there the way bootstrap.sh's
# `ln -sf .../testssl.sh /usr/local/bin/testssl.sh` does on Linux. This is
# where that clone actually lands (Join-Path $env:LOCALAPPDATA "Programs"
# "testssl.sh"). A GIZMODUCK_TESTSSL_SH override takes precedence for an
# operator who put it somewhere else.
_TESTSSL_SCRIPT_CANDIDATES = tuple(
    p for p in (
        os.environ.get("GIZMODUCK_TESTSSL_SH"),
        (str(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "testssl.sh" / "testssl.sh")
         if os.environ.get("LOCALAPPDATA") else None),
    ) if p
)

_ERROR_SEVERITIES = ("WARN", "FATAL")
# OK is a confident, documented "this check found nothing" - not an unmapped
# value - so it is translated to INFO before normalize.sev_from_text ever
# sees it, and comes back known=True rather than falling back as a guess.
_OK_ALIAS = "OK"


def _find_testssl_script():
    for candidate in _TESTSSL_SCRIPT_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _resolve_command():
    """The argv prefix to invoke testssl.sh with, or None if no usable route
    exists. Prefers a directly-executable testssl.sh/testssl on PATH (the
    Linux install: bootstrap.sh symlinks it with +x and its own shebang, so
    the kernel handles the interpreter itself) - else falls back to running
    the git-cloned script explicitly through bash, since that is the only
    thing bootstrap.ps1 ever provides on Windows and is the verified working
    invocation there (`bash testssl.sh ...`).
    """
    binary = base.which("testssl.sh") or base.which("testssl")
    if binary:
        return [binary]
    script = _find_testssl_script()
    bash = base.which("bash")
    if script and bash:
        return [bash, script]
    return None


def is_available():
    return _resolve_command() is not None


def _hexdump_dir():
    """A directory to prepend to PATH so testssl.sh's subprocess can find
    `hexdump`, or None when one is already resolvable (Linux/macOS, or an
    MSYS2 install already on the caller's PATH) - see the module comment on
    _MSYS2_HEXDUMP_CANDIDATES for why this is needed at all under Git Bash.
    """
    if base.which("hexdump"):
        return None
    for candidate in _MSYS2_HEXDUMP_CANDIDATES:
        if candidate and (Path(candidate) / "hexdump.exe").is_file():
            return candidate
    return None


def run(target, outdir, opts):
    """Invoke testssl.sh and return (raw_path, ToolResult).

    raw_path is None when nothing was written - either the binary was never
    found, the process timed out, or it exited without producing a file.
    Otherwise it is the path to the jsonfile output. The ToolResult is
    always returned, even when raw_path is None, so routine can record
    `error:timeout` or `error:<message>` per spec section 6 step 5 - a
    fake ToolResult stands in for the "never started" case since there is
    no subprocess to report on.

    testssl.sh's own exit code is not read here to decide success or
    failure: 50-200 is a severity-scored exit, not an error range
    (spec 13.12), so ToolResult.returncode alone would mislead routine into
    treating a normal scored exit as a failure. `timed_out` and whether
    raw_path exists are what this function actually gates on.

    A different, content-level error also exists: individual WARN/FATAL
    checks *inside* an otherwise-successful jsonfile. Those never reach this
    ToolResult - they are exposed via the documented parse_errors() function
    below, which routine should call alongside parse() whenever raw_path is
    not None.
    """
    command = _resolve_command()
    if command is None:
        return None, base.ToolResult(
            -1, "",
            "testssl.sh not found (no binary on PATH, and no cloned "
            "testssl.sh + bash available)", False)

    out_path = Path(outdir) / "testssl.json"

    # DEFECT 1 (critical): establish freshness BEFORE invoking the tool. A
    # stale jsonfile left in outdir from a previous run would otherwise still
    # be sitting at out_path after a failed invocation that wrote nothing new,
    # and `out_path.exists()` below would hand it back as if it were this
    # run's evidence - a failed scan inheriting the previous run's clean
    # bill of health.
    if out_path.exists():
        out_path.unlink()

    argv = command + ["--jsonfile", str(out_path)]
    if opts.get("connect_timeout"):
        argv += ["--connect-timeout", str(opts["connect_timeout"])]
    if opts.get("openssl_timeout"):
        argv += ["--openssl-timeout", str(opts["openssl_timeout"])]
    argv.append(target)

    timeout = opts.get("timeout", _DEFAULT_TIMEOUT)

    # testssl.sh hard-requires `hexdump` and fails immediately without it,
    # with a bare "You need to install hexdump for this program to work."
    # that gives a Windows operator no idea what to do about it. If it is
    # not resolvable anywhere - not on PATH, and no MSYS2 candidate found
    # either - decline right here with an actionable message instead of
    # ever invoking testssl.sh and burying that behind its own error.
    hexdump_dir = _hexdump_dir()
    if hexdump_dir is None and not base.which("hexdump"):
        return None, base.ToolResult(
            -1, "",
            "testssl.sh requires `hexdump`, which is not on PATH and no "
            "MSYS2 install was found (checked C:\\tools\\msys64\\usr\\bin, "
            "C:\\msys64\\usr\\bin, and $GIZMODUCK_MSYS2_BIN) - install "
            "MSYS2, or set GIZMODUCK_MSYS2_BIN to a directory containing "
            "hexdump.exe, then retry", False)

    # Git Bash's own bin has no `hexdump` (module comment); testssl.sh hard-
    # fails before doing anything else without one. base.run_tool has no env
    # parameter (shared plumbing, out of scope here), so this temporarily
    # prepends a directory that does have it to this process's PATH for the
    # one subprocess call, then always restores it - never a permanent
    # change to this process's environment. (hexdump_dir was already
    # resolved above, to gate the "nowhere to be found" case before ever
    # building this far.)
    old_path = os.environ.get("PATH", "")
    if hexdump_dir:
        os.environ["PATH"] = hexdump_dir + os.pathsep + old_path
    try:
        result = base.run_tool(argv, timeout=timeout, cwd=opts.get("cwd"))
    finally:
        if hexdump_dir:
            os.environ["PATH"] = old_path

    if result.timed_out or not out_path.exists():
        return None, result
    return out_path, result


def _load(raw_path):
    """Read and validate the jsonfile shape, or raise base.ParseError.

    DEFECT 2: an empty, truncated or malformed jsonfile - and a
    well-formed-but-wrongly-shaped one, such as a top-level object instead of
    the documented array, or `[null]` - must never come back as `[]`/crash
    with an uncaught TypeError from `item.get(...)`. Both parse() and
    parse_errors() read through this one gate so neither can diverge on how
    a bad file is handled.
    """
    try:
        with open(raw_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise base.ParseError("testssl: could not read %s: %s" % (raw_path, e)) from e

    if not isinstance(data, list):
        raise base.ParseError(
            "testssl: expected a JSON array at the top level, got %r" % type(data).__name__)
    for item in data:
        if not isinstance(item, dict):
            raise base.ParseError("testssl: entry is not an object: %r" % (item,))
    return data


def _split_cve(value):
    if not value:
        return []
    return [c.strip() for c in str(value).split(",") if c.strip()]


def _matched_at(item):
    ip = item.get("ip") or ""
    port = item.get("port") or ""
    return "%s:%s" % (ip, port) if port else ip


def _raw_severity(item):
    """Uppercased `severity` text, or "" when absent. DEFECT 2 (MEDIUM):
    `severity` present but not a string (e.g. a stray int) used to reach
    `.strip()` on it directly and raise a raw AttributeError from both
    parse() and parse_errors() - routine's handler would then record
    error:AttributeError instead of naming the real problem.
    """
    value = item.get("severity")
    if value is not None and not isinstance(value, str):
        raise base.ParseError(
            "testssl: 'severity' must be a string, got %r" % type(value).__name__)
    return (value or "").strip().upper()


def parse(raw_path, target):
    """Return the real findings from a testssl run. Never raises on a
    WARN/FATAL entry - those are dropped here and picked up by
    parse_errors() instead, so they can never become a finding.
    """
    findings = []
    for item in _load(raw_path):
        raw_sev = _raw_severity(item)
        if raw_sev in _ERROR_SEVERITIES:
            continue

        text = "INFO" if raw_sev == _OK_ALIAS else (raw_sev or None)
        sev, known = normalize.sev_from_text(text)

        findings.append(normalize.make_finding(
            tool=NAME,
            target=target,
            rule_id=item.get("id"),
            name=item.get("finding") or item.get("id"),
            severity=sev,
            severity_known=known,
            host=item.get("ip") or "",
            matched_at=_matched_at(item),
            description=item.get("finding") or "",
            cve=_split_cve(item.get("cve")),
            tags=[item["cwe"]] if item.get("cwe") else [],
        ))
    return findings


def parse_errors(raw_path, target):
    """Return the WARN/FATAL entries as tool-error records, not findings.

    Each record is deliberately shaped nothing like a finding (no
    template_id, no severity_name, no int severity band) so it cannot be
    mistaken for one downstream - it carries only what a run-manifest cell
    needs: which check errored, on which target/tool, and why.
    """
    errors = []
    for item in _load(raw_path):
        raw_sev = _raw_severity(item)
        if raw_sev not in _ERROR_SEVERITIES:
            continue
        errors.append({
            "tool": NAME,
            "target": target,
            "id": item.get("id"),
            "severity": raw_sev,
            "message": item.get("finding") or "",
            "host": item.get("ip") or "",
            "port": item.get("port") or "",
        })
    return errors
