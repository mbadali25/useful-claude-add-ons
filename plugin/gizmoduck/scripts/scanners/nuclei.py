"""Nuclei adapter - a refactor of the existing cmd_scan()/load() into the
adapter shape, not a new parser (plan, Task 5).

run() builds its argv with gizmoduck.nuclei_argv(), the builder cmd_scan()
uses too (T-0108: safe -etags/-rl defaults live there once) - it does not
call cmd_scan() itself, because cmd_scan owns the single-scanner
CLI's own stdout-filtering and file-write/exit-code policy, which this
adapter must not duplicate or let drift from. It shares only the argv builder,
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

HIGH defect fix: run()'s own JSON-line filter used to fold two different
situations into the same empty output file - a genuinely clean scan (no
finding lines because there were none to have) and a REJECTED one, where
stdout had real content (a bare `[]`, or `[FATAL] could not load templates`)
but none of it survived the "starts with `{`" filter. Both used to write an
empty `nuclei.jsonl` when the exit code happened to be 0, and parse() then
read that empty file as "ran clean" either way - indistinguishable from a
real clean scan. Since `[FATAL] could not load templates` is the exact
failure mode bootstrap hard-fails on for a template download error, letting
it through here as "clean" would silently defeat that safeguard downstream.
Fixed by treating any NON-empty stdout that yields zero finding lines as a
failure (returning `(None, result)`) regardless of the exit code, and
reserving the "write an empty file" path for stdout that was truly empty to
begin with - `-silent`'s real signature for "ran, found nothing".
"""
import json
import os
import sys

from . import base

NAME = "nuclei"
KINDS = ["web", "host"]
ACTIVE = False
ACTIVE_OPTS = ["nuclei_intrusive"]  # drops the safe -etags; recorded ran(safe+intrusive)
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


# Keys in a Nuclei config.yaml that re-include excluded templates, fuzz, or
# move the rate cap without any flag on the command line. goflags matches a
# config key against every registered flag name, short and long, so both are
# listed. A key set to null, "", [] or false sets nothing; 0 does (rl: 0 is
# uncapped).
RISKY_CONFIG_KEYS = frozenset({
    "itags", "include-tags", "it", "include-templates",
    "rl", "rate-limit", "rlm", "rate-limit-minute", "rld", "rate-limit-duration",
    "per-host-rate-limit", "dast", "fuzz", "dts", "dast-server",
    "config", "tp", "profile",
})


def _go_user_config_dir():
    """Go's os.UserConfigDir(), or None where Go returns an error."""
    if os.name == "nt":
        return os.environ.get("APPDATA") or None
    if sys.platform == "darwin":
        home = os.environ.get("HOME")
        return os.path.join(home, "Library", "Application Support") if home else None
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return xdg if os.path.isabs(xdg) else None
    home = os.environ.get("HOME")
    return os.path.join(home, ".config") if home else None


def nuclei_config_files():
    """Every config.yaml Nuclei v3.11.1 may merge into a run: goflags' own
    (`<UserConfigDir>/nuclei/config.yaml`, else `./nuclei/config.yaml`),
    nuclei's fallback (`.nuclei-config/nuclei/config.yaml`), and
    `$NUCLEI_CONFIG_DIR/config.yaml` when that is set."""
    base_dir = _go_user_config_dir()
    if base_dir:
        paths = [os.path.join(base_dir, "nuclei", "config.yaml")]
    else:
        paths = [os.path.join(".", "nuclei", "config.yaml"),
                 os.path.join(".nuclei-config", "nuclei", "config.yaml")]
    custom = os.environ.get("NUCLEI_CONFIG_DIR")
    if custom:
        paths.append(os.path.join(custom, "config.yaml"))
    return list(dict.fromkeys(paths))


def _sets_something(value):
    return not (value is None or value is False or value == "" or value == [])


def check_nuclei_config():
    """None when no Nuclei config file loosens the safe defaults, else the
    refusal message. A missing file is fine; one that exists but cannot be
    read or parsed is refused - "could not tell" is not "nothing set"."""
    for path in nuclei_config_files():
        if not os.path.lexists(path):
            continue
        try:
            import yaml
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except Exception as exc:  # noqa: BLE001 - every failure is "could not tell"
            return (f"nuclei config {path} exists but could not be read or parsed "
                    f"({type(exc).__name__}: {exc}); refusing to run, because it may "
                    f"loosen the safe defaults. Fix or remove it")
        if data is None:
            continue
        if not isinstance(data, dict):
            return (f"nuclei config {path} is not a YAML mapping; refusing to run, "
                    f"because what it sets could not be told. Fix or remove it")
        risky = sorted(k for k, v in data.items()
                       if isinstance(k, str) and k in RISKY_CONFIG_KEYS and _sets_something(v))
        if risky:
            return (f"nuclei config {path} sets {', '.join(risky)}, which would loosen "
                    f"gizmoduck's safe defaults with no flag to show it; refusing to run. "
                    f"Remove those keys, and use the manifest options nuclei_intrusive "
                    f"and nuclei_rate_limit instead")
    return None


def is_available():
    return _gizmoduck().find_nuclei() is not None


def run(target, outdir, opts=None):
    """Build the same argv cmd_scan() uses and hand it to base.run_tool.

    `opts` recognizes `severity` (comma list, same as cmd_scan's --severity),
    `extra` (a string of additional raw nuclei flags, same as cmd_scan's
    --extra, minus the safety flags gizmoduck.nuclei_argv's strict mode
    refuses), `nuclei_intrusive` and `nuclei_rate_limit` (scan's --intrusive
    and --rate-limit), and `timeout` (seconds; falls back to DEFAULT_TIMEOUT).
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

    # strict: a tag, rate or attack flag in `extra` would make the recorded
    # ran(safe) mode lie, so it is refused here before anything runs (the
    # manifest parse refuses it too; a hand-built Manifest skips that check).
    try:
        cmd = gz.nuclei_argv(exe, target, opts.get("severity") or "", opts.get("extra") or "",
                             intrusive=opts.get("nuclei_intrusive", False),
                             rate_limit=opts.get("nuclei_rate_limit"), strict=True)
    except ValueError as exc:
        return None, base.ToolResult(returncode=-1, stdout="", stderr=str(exc),
                                     timed_out=False)

    refusal = check_nuclei_config()
    if refusal:
        return None, base.ToolResult(returncode=-1, stdout="", stderr=refusal,
                                     timed_out=False)

    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, "nuclei.jsonl")

    result = base.run_tool(cmd, timeout=opts.get("timeout", DEFAULT_TIMEOUT))

    if result.timed_out:
        # A timed-out invocation's stdout may be truncated mid-JSON, so
        # nothing is written rather than handing parse() something that
        # looks parseable but isn't trustworthy (mirrors checkov.py).
        return None, result

    # Nmap is the only adapter in this package permitted to gate findings on
    # exit status (base.py). Nuclei's findings come from parsed output only:
    # only lines that look like JSON objects are kept, full stop - a nonzero
    # exit code never discards output that's actually there.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]

    if not lines:
        # HIGH defect fix: no JSON finding lines survived the filter. That
        # is NOT automatically nuclei's real "ran clean, found nothing" -
        # this is also exactly what a rejected/filtered invocation looks
        # like, e.g. stdout of a bare `[]` or `[FATAL] could not load
        # templates` (the failure mode bootstrap hard-fails on for this
        # reason). A genuinely clean run with `-silent` produces truly EMPTY
        # stdout - nothing at all, not even non-JSON text. So: stdout that
        # had SOME content, none of which survived the filter, is treated as
        # a failure (never written, never handed to parse() as if it were a
        # clean scan) regardless of the exit code - a nonzero exit is a
        # second, independent signal for the same conclusion, not the only
        # one, since a broken invocation can still exit 0.
        if result.stdout.strip():
            return None, result
        if result.returncode != 0:
            # No output file written - per the standardized run() contract,
            # that means the path side of the tuple is None, not a path that
            # doesn't exist on disk. The ToolResult still comes back so
            # routine.py can record error:<returncode> instead of mistaking
            # "didn't run" for "ran clean".
            return None, result
        # Genuinely empty stdout and a clean exit: nuclei's real "ran,
        # found nothing" - falls through to write the (empty) file below.

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
        raise base.ParseError(f"nuclei output file not found: {raw_path}")

    gz = _gizmoduck()
    try:
        findings = gz.load(raw_path)
        with open(raw_path, encoding="utf-8") as fh:
            raw_records = [json.loads(ln) for ln in fh if ln.strip()]
    except (ValueError, TypeError, AttributeError, OSError) as e:
        raise base.ParseError(
            f"could not parse nuclei output {raw_path}: {e}") from e

    for record, f in zip(raw_records, findings):
        severity = (record.get("info") or {}).get("severity")
        if not _severity_known(severity):
            f["tags"] = list(f["tags"]) + ["severity-assigned"]
        f["tool"] = NAME
        f["target"] = target
    return findings
