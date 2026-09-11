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
"""
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
        raise FileNotFoundError(
            "nuclei not found on PATH. Run bootstrap.sh (Linux/WSL) or "
            "bootstrap.ps1 (Windows) first.")

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

    # Same rule as cmd_scan() (gizmoduck.py:63-84): only lines that look like
    # JSON objects are kept, and a failed run - no findings and a non-zero,
    # non-"findings-exist" exit - writes nothing, so a dead scan can't be
    # mistaken downstream for a clean one. Exit 1 with findings on stdout is
    # `-ec`'s "findings exist" signal, not a failure.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]
    if result.returncode != 0 and not (result.returncode == 1 and lines):
        # No output file written - per the standardized run() contract, that
        # means the path side of the tuple is None, not a path that doesn't
        # exist on disk. The ToolResult (including timed_out) still comes
        # back so routine.py can record error:timeout / error:<returncode>
        # instead of mistaking "didn't run" for "ran clean".
        return None, result
    with open(raw_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    return raw_path, result


def parse(raw_path, target):
    """Delegate entirely to gizmoduck.load(): this adapter's whole purpose is
    to reuse that normalization, not re-derive it (plan, Task 5). Only
    `tool`/`target` are added on top of load()'s existing 14-key shape.

    Pure: no subprocess, no network. A missing output file yields an empty
    list rather than raising - a broken run is the caller's (routine.py's)
    concern to record, not this function's to crash over.
    """
    if not os.path.isfile(raw_path):
        return []
    findings = _gizmoduck().load(raw_path)
    for f in findings:
        f["tool"] = NAME
        f["target"] = target
    return findings
