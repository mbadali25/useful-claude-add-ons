"""Nuclei adapter - a refactor of the existing cmd_scan()/load() into the
adapter shape, not a new parser (plan, Task 5).

run() builds the same core argv cmd_scan() already builds (gizmoduck.py:63) -
it does not call cmd_scan() itself, because cmd_scan owns the single-scanner
CLI's own stdout-filtering and file-write/exit-code policy, which this
adapter must not duplicate or let drift from. It borrows only the argv shape,
then applies base.run_tool's own timeout handling, mirroring cmd_scan's
"never write a findings file for a failed scan" rule on top.

run() returns the standardized `(raw_path | None, base.ToolResult)` tuple
(team-lead's cross-adapter contract decision): `raw_path` only when the
findings file was actually written, `None` otherwise (including a timeout -
base.run_tool never raises on one, it just sets `result.timed_out`). The
ToolResult always comes back so routine.py can record `error:timeout` /
`error:<n>` per-cell in the run manifest - a path string alone can't carry
that.

parse() delegates entirely to gizmoduck.load() and only adds the `tool`/
`target` keys the plan's Global Constraints introduce - it must stay
byte-identical to today's load() output for the same input (see
test_scanner_nuclei.py), because that equality is the regression guard for
every other adapter: they all normalize into this same finding shape, and
Nuclei's own path is the one input nobody can afford to reshape by accident.

The one addition on top of load()'s output is the `severity-assigned`
provenance marker (Global Constraints): load() folds a missing or
unrecognized `info.severity` into the same Info fallback as a real Info
assessment, with nothing left in its return value to tell the two apart.
parse() re-reads each raw record's `info.severity` (cheaply - it doesn't
re-derive load()'s normalization, just this one flag) purely to decide
whether to append that tag; every other field stays exactly what load()
produced.

parse() must never turn a parse failure into an empty finding list - `[]`
means only "nuclei ran and found nothing". Malformed or truncated JSONL
raises `base.ParseError` instead, so routine.py records `error:parse:<detail>`
for that cell rather than reporting a broken scan as a clean target.
"""
import json
import os

from . import base

NAME = "nuclei"
KINDS = ["web", "host"]
ACTIVE = False
ACTIVE_OPTS = []
DEFAULT_ENABLED = True

DEFAULT_TIMEOUT = 1800  # seconds; base.run_tool is the real guard (spec 13.13)


def _gizmoduck():
    """Load gizmoduck.py, which sits one directory up from this adapter.

    Mirrors gizmoduck.py's own `_template_module()` pattern for
    report_template.py (gizmoduck.py:274-291): a plain import works once
    scripts/ is already on sys.path (true under pytest.ini's
    `pythonpath = scripts`, and true for gizmoduck.py's own in-process
    callers), with a by-path fallback for anything that imported this
    adapter from elsewhere.
    """
    try:
        import gizmoduck
        return gizmoduck
    except ImportError:
        import importlib.util
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "gizmoduck.py")
        spec = importlib.util.spec_from_file_location("gizmoduck", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def is_available():
    return _gizmoduck().find_nuclei() is not None


def run(target, outdir, opts=None):
    """Build the same argv cmd_scan() uses and hand it to base.run_tool.

    `opts` recognizes `severity` (comma list, same as cmd_scan's --severity),
    `extra` (a string of additional raw nuclei flags, same as cmd_scan's
    --extra), and `timeout` (seconds; falls back to DEFAULT_TIMEOUT).
    """
    gz = _gizmoduck()
    opts = opts or {}
    exe = gz.find_nuclei()
    if not exe:
        # Standardized run() contract (team-lead cross-adapter decision):
        # return the (None, ToolResult) tuple every other adapter returns
        # for "couldn't run", rather than raising. Raising here bypassed
        # routine.py's normal per-tool `skipped-missing` recording.
        return None, base.ToolResult(
            returncode=-1, stdout="",
            stderr="nuclei not found on PATH. Run bootstrap.sh (Linux/WSL) "
                   "or bootstrap.ps1 (Windows) first.",
            timed_out=False)

    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "nuclei.jsonl")

    cmd = [exe, "-jsonl", "-silent", "-nc"]
    cmd += ["-l", target] if os.path.isfile(target) else ["-u", target]
    severity = opts.get("severity")
    if severity:
        cmd += ["-severity", severity]
    extra = opts.get("extra")
    if extra:
        cmd += extra.split()

    result = base.run_tool(cmd, timeout=opts.get("timeout", DEFAULT_TIMEOUT))

    if result.timed_out:
        # A timed-out invocation's stdout may be truncated mid-JSON, so
        # nothing is written rather than handing parse() something that
        # looks parseable but isn't trustworthy (mirrors checkov.py).
        return None, result

    # Nmap is the only adapter in this package permitted to gate findings on
    # exit status (base.py). Nuclei's findings come from parsed output only:
    # only lines that look like JSON objects are kept, full stop - a nonzero
    # exit code never discards output that's actually there. The exit code
    # is consulted only when there is NO candidate output at all, to decide
    # whether an empty result means "ran clean, found nothing" (exit 0) or
    # "failed before producing anything" (nonzero) - it never overrides
    # actual finding content either way.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines and result.returncode != 0:
        # No output file written - per the standardized run() contract, that
        # means the path side of the tuple is None, not a path that doesn't
        # exist on disk. The ToolResult still comes back so routine.py can
        # record error:<returncode> instead of mistaking "didn't run" for
        # "ran clean".
        return None, result
    with open(raw_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    return raw_path, result


_KNOWN_SEVERITIES = {"critical", "high", "medium", "low", "info"}


def _severity_known(raw_severity):
    """Whether info.severity was a real, recognized value - as opposed to
    missing or unrecognized text, which gizmoduck.load() folds into the same
    Info fallback (SEV_NUM.get(..., 0)) as a genuine Info assessment.
    """
    return bool(raw_severity) and raw_severity.strip().lower() in _KNOWN_SEVERITIES


def parse(raw_path, target):
    """Delegate entirely to gizmoduck.load(): this adapter's whole purpose is
    to reuse that normalization, not re-derive it (plan, Task 5). Only
    `tool`/`target` are added on top of load()'s existing 14-key shape, plus
    a `severity-assigned` tag on findings whose info.severity was missing or
    unrecognized (see _severity_known) - load() has no way to mark that
    itself, and without the marker an assigned default is indistinguishable
    from a real assessment in the report.

    Pure: no subprocess, no network. An empty output file is nuclei's own
    "ran clean, found nothing" and yields []. A MISSING file does not: `[]`
    must mean only "the tool ran and found nothing", and a path that isn't
    there is "we cannot tell" rather than that claim - routine only calls
    parse() when run() actually returned this path, so a missing file here
    means something vanished between the two that nobody would ever notice
    if it silently rendered as a clean target. Raises base.ParseError, same
    as any other unreadable output.
    """
    if not os.path.isfile(raw_path):
        raise base.ParseError("nuclei output file not found: %s" % raw_path)

    gz = _gizmoduck()
    try:
        findings = gz.load(raw_path)
        with open(raw_path, encoding="utf-8") as fh:
            raw_records = [json.loads(ln) for ln in fh if ln.strip()]
    except (ValueError, TypeError, AttributeError, OSError) as e:
        raise base.ParseError(
            "could not parse nuclei output %s: %s" % (raw_path, e)) from e

    for record, f in zip(raw_records, findings):
        severity = (record.get("info") or {}).get("severity")
        if not _severity_known(severity):
            f["tags"] = list(f["tags"]) + ["severity-assigned"]
        f["tool"] = NAME
        f["target"] = target
    return findings
