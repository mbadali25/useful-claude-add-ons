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

_ERROR_SEVERITIES = ("WARN", "FATAL")
# OK is a confident, documented "this check found nothing" - not an unmapped
# value - so it is translated to INFO before normalize.sev_from_text ever
# sees it, and comes back known=True rather than falling back as a guess.
_OK_ALIAS = "OK"


def is_available():
    return base.which("testssl.sh") is not None or base.which("testssl") is not None


def run(target, outdir, opts):
    binary = base.which("testssl.sh") or base.which("testssl")
    if not binary:
        return None

    out_path = Path(outdir) / "testssl.json"
    argv = [binary, "--jsonfile", str(out_path)]
    if opts.get("connect_timeout"):
        argv += ["--connect-timeout", str(opts["connect_timeout"])]
    if opts.get("openssl_timeout"):
        argv += ["--openssl-timeout", str(opts["openssl_timeout"])]
    argv.append(target)

    timeout = opts.get("timeout", _DEFAULT_TIMEOUT)
    base.run_tool(argv, timeout=timeout, cwd=opts.get("cwd"))
    return out_path


def _load(raw_path):
    with open(raw_path, encoding="utf-8") as fh:
        return json.load(fh)


def _split_cve(value):
    if not value:
        return []
    return [c.strip() for c in str(value).split(",") if c.strip()]


def _matched_at(item):
    ip = item.get("ip") or ""
    port = item.get("port") or ""
    return "%s:%s" % (ip, port) if port else ip


def parse(raw_path, target):
    """Return the real findings from a testssl run. Never raises on a
    WARN/FATAL entry - those are dropped here and picked up by
    parse_errors() instead, so they can never become a finding.
    """
    findings = []
    for item in _load(raw_path):
        raw_sev = (item.get("severity") or "").strip().upper()
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
        raw_sev = (item.get("severity") or "").strip().upper()
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
