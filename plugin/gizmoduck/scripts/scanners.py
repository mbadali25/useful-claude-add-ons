"""Scanner adapters: run a tool, return findings in Nuclei's JSONL record shape.

Every adapter returns a list of dicts shaped like a Nuclei result, so
`gizmoduck.load()` parses them without knowing which tool produced them and
`cmd_report` / `cmd_tickets` / `cmd_diff` merge them with Nuclei's own output
into ONE report at the existing Medium-and-above floor. That is the whole
design: normalise at the edge, so the reporting pipeline never grows a
per-tool branch.

The record shape `load()` reads:

    {"template-id": str, "type": str, "host": str, "matched-at": str,
     "timestamp": str,
     "info": {"name", "severity", "description", "remediation",
              "reference": [], "tags": [],
              "classification": {"cve-id": [], "cvss-score": ""}}}

Two rules every adapter follows:

1. **A tool that is not installed is not a clean result.** Adapters return a
   `ToolRun` carrying `status`, and a missing or failed tool is reported as
   such rather than contributing zero findings silently. Gizmoduck already
   refuses to write an empty findings file for a failed Nuclei run for exactly
   this reason; the same logic has to hold once there are five tools, or four
   silent failures look like a clean bill of health.

2. **Severity is never invented.** Where a tool supplies a severity it is
   mapped straight across. Where it does not (Checkov OSS emits
   `severity: null` on every finding), the adapter says so and floors those
   findings at Low rather than promoting them to Medium - promoting them would
   put hundreds of unranked results above the report's detail floor and bury
   the findings that were actually ranked.
"""
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

# Tools that scan a LIVE ENDPOINT (need a URL/host) versus tools that scan a
# SOURCE TREE (need a directory). A scan with no source path runs the first
# group and reports the second as skipped - not as clean.
ENDPOINT_TOOLS = ("nuclei", "sslyze", "zap")
SOURCE_TOOLS = ("trivy-fs", "trivy-config", "semgrep", "checkov")

# Opt-in. ZAP is a crawler-driven DAST that takes minutes per target and wants
# authentication to be worth running; Checkov is breadth without severity.
OPTIONAL_TOOLS = ("zap", "checkov")

TRIVY_SEV = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium",
             "LOW": "low", "UNKNOWN": "info"}
SEMGREP_SEV = {"ERROR": "high", "WARNING": "medium", "INFO": "info"}
ZAP_SEV = {"High": "high", "Medium": "medium", "Low": "low",
           "Informational": "info"}


class ToolRun:
    """What one tool did. `status` is one of ok / missing / failed / skipped."""

    def __init__(self, tool, status, findings=None, detail=""):
        self.tool = tool
        self.status = status
        self.findings = findings or []
        self.detail = detail

    def __repr__(self):
        return f"<ToolRun {self.tool} {self.status} n={len(self.findings)}>"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _rec(tool, ident, name, severity, where, host="", description="",
         remediation="", reference=None, tags=None, cve=None, cvss=""):
    """Build one Nuclei-shaped record."""
    return {
        "template-id": f"{tool}:{ident}",
        "type": tool,
        "host": host,
        "matched-at": where,
        "timestamp": _now(),
        "info": {
            "name": name,
            "severity": severity,
            "description": description or "",
            "remediation": remediation or "",
            "reference": reference or [],
            "tags": sorted(set((tags or []) + [tool])),
            "classification": {"cve-id": cve or [], "cvss-score": cvss or ""},
        },
    }


def _which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _run(cmd, timeout, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, check=False,
                          timeout=timeout, cwd=cwd)


def _json_from_file(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# sslyze - TLS protocol and certificate posture
# --------------------------------------------------------------------------

def run_sslyze(host, timeout=300):
    """Real TLS posture. Nuclei's ssl templates fingerprint (issuer, SAN list,
    negotiated version); this decides whether the configuration is WRONG."""
    exe = _which("sslyze")
    cmd_prefix = [exe] if exe else None
    if cmd_prefix is None:
        # sslyze ships as a module; a venv install may not expose the script.
        import sys
        cmd_prefix = [sys.executable, "-m", "sslyze"]

    target = host.split("://")[-1].split("/")[0]
    if ":" not in target:
        target += ":443"

    tmp = os.path.join(tempfile.gettempdir(), f"gizmo-sslyze-{os.getpid()}.json")
    try:
        proc = _run(cmd_prefix + ["--json_out=" + tmp, "--quiet", target], timeout)
    except subprocess.TimeoutExpired:
        return ToolRun("sslyze", "failed", detail=f"timed out after {timeout}s")
    if not os.path.exists(tmp):
        return ToolRun("sslyze", "failed",
                       detail=(proc.stderr or proc.stdout or "no JSON written").strip()[:300])

    try:
        data = _json_from_file(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    results = data.get("server_scan_results") or []
    if not results:
        return ToolRun("sslyze", "failed", detail="no server_scan_results")
    r = results[0]
    if r.get("scan_status") != "COMPLETED":
        return ToolRun("sslyze", "failed",
                       detail=f"scan_status={r.get('scan_status')}")
    sr = r.get("scan_result") or {}
    out = []

    def accepted(key):
        v = (sr.get(key) or {}).get("result") or {}
        return len(v.get("accepted_cipher_suites") or [])

    # Obsolete protocol versions. These are the findings that matter and the
    # ones a fingerprinting template will not raise.
    for key, label, sev in (
        ("ssl_2_0_cipher_suites", "SSL 2.0", "critical"),
        ("ssl_3_0_cipher_suites", "SSL 3.0", "critical"),
        ("tls_1_0_cipher_suites", "TLS 1.0", "medium"),
        ("tls_1_1_cipher_suites", "TLS 1.1", "medium"),
    ):
        n = accepted(key)
        if n:
            out.append(_rec(
                "sslyze", f"protocol-{label.lower().replace(' ', '-').replace('.', '-')}",
                f"{label} is enabled ({n} cipher suites accepted)", sev, target, host=target,
                description=(f"The server negotiates {label}, which is deprecated and "
                             f"disallowed by PCI DSS and current TLS guidance."),
                remediation=f"Disable {label} and serve TLS 1.2 and 1.3 only.",
                tags=["tls", "protocol"]))

    if accepted("tls_1_2_cipher_suites") == 0 and accepted("tls_1_3_cipher_suites") == 0:
        out.append(_rec("sslyze", "no-modern-tls",
                        "Neither TLS 1.2 nor TLS 1.3 is accepted", "high", target,
                        host=target,
                        description="No modern TLS version was negotiated.",
                        remediation="Enable TLS 1.2 and TLS 1.3.", tags=["tls"]))

    # Named vulnerabilities. Each result object differs, so each is read by the
    # field that actually carries the verdict.
    def flag(key, field, name, sev, remediation):
        res = (sr.get(key) or {}).get("result") or {}
        if res.get(field):
            out.append(_rec("sslyze", key.replace("_", "-"), name, sev, target,
                            host=target, remediation=remediation,
                            tags=["tls", "vuln"]))

    flag("heartbleed", "is_vulnerable_to_heartbleed",
         "Vulnerable to Heartbleed (CVE-2014-0160)", "critical",
         "Upgrade OpenSSL and rotate any key material that was reachable.")
    flag("openssl_ccs_injection", "is_vulnerable_to_ccs_injection",
         "Vulnerable to OpenSSL CCS injection (CVE-2014-0224)", "high",
         "Upgrade OpenSSL.")
    flag("tls_compression", "supports_compression",
         "TLS compression is enabled (CRIME)", "medium",
         "Disable TLS-level compression.")

    reneg = (sr.get("session_renegotiation") or {}).get("result") or {}
    if reneg.get("supports_secure_renegotiation") is False:
        out.append(_rec("sslyze", "insecure-renegotiation",
                        "Secure renegotiation is not supported", "medium", target,
                        host=target,
                        remediation="Enable RFC 5746 secure renegotiation.",
                        tags=["tls"]))

    robot = (sr.get("robot") or {}).get("result") or {}
    rr = str(robot.get("robot_result") or "")
    # sslyze's enum spells the SAFE outcomes NOT_VULNERABLE_* , so a substring
    # test for "VULNERABLE" matches every healthy server. Exclude the negative
    # forms explicitly: a false High on a correctly configured host is worse
    # than a missed finding, because it trains the reader to discount the tool.
    _rr = rr.upper()
    if "VULNERABLE" in _rr and not _rr.startswith("NOT_VULNERABLE"):
        out.append(_rec("sslyze", "robot", f"Vulnerable to ROBOT ({rr})", "high",
                        target, host=target,
                        remediation="Disable RSA key exchange cipher suites.",
                        tags=["tls", "vuln"]))

    # Certificate validity. A chain that does not validate, or a hostname that
    # does not match, is a real finding rather than inventory.
    cert = (sr.get("certificate_info") or {}).get("result") or {}
    for dep in cert.get("certificate_deployments") or []:
        for val in dep.get("path_validation_results") or []:
            if val.get("was_validation_successful") is False:
                store = ((val.get("trust_store") or {}).get("name")) or "a trust store"
                out.append(_rec("sslyze", "cert-untrusted",
                                f"Certificate chain does not validate against {store}",
                                "high", target, host=target,
                                description=str(val.get("openssl_error_string") or "")[:300],
                                remediation="Serve the full chain with a trusted CA.",
                                tags=["tls", "certificate"]))
        if dep.get("leaf_certificate_subject_matches_hostname") is False:
            out.append(_rec("sslyze", "cert-hostname-mismatch",
                            "Certificate does not match the requested hostname",
                            "high", target, host=target,
                            remediation="Reissue with the correct SAN entries.",
                            tags=["tls", "certificate"]))

    return ToolRun("sslyze", "ok", out)


# --------------------------------------------------------------------------
# trivy - dependency CVEs, committed secrets, and IaC misconfiguration
# --------------------------------------------------------------------------

def _trivy(subcmd, path, extra, timeout, tool_name):
    exe = _which("trivy", "trivy.exe")
    if not exe:
        return ToolRun(tool_name, "missing",
                       detail="trivy not on PATH; run the bootstrap script")
    cmd = [exe, subcmd, path, "--format", "json", "--quiet"] + list(extra)
    try:
        proc = _run(cmd, timeout)
    except subprocess.TimeoutExpired:
        return ToolRun(tool_name, "failed", detail=f"timed out after {timeout}s")
    if not proc.stdout.strip():
        if proc.returncode != 0:
            return ToolRun(tool_name, "failed",
                           detail=(proc.stderr or "").strip()[:300])
        return ToolRun(tool_name, "ok", [])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return ToolRun(tool_name, "failed", detail=f"unparseable JSON: {exc}")
    return data


def run_trivy_fs(source, timeout=900):
    """Dependency CVEs and committed secrets across every lockfile in the tree."""
    data = _trivy("fs", source, ["--scanners", "vuln,secret"], timeout, "trivy-fs")
    if isinstance(data, ToolRun):
        return data
    out = []
    for res in data.get("Results") or []:
        where = res.get("Target", source)
        for v in res.get("Vulnerabilities") or []:
            pkg = v.get("PkgName", "")
            fixed = v.get("FixedVersion")
            out.append(_rec(
                "trivy-fs", v.get("VulnerabilityID", "vuln"),
                f"{pkg} {v.get('InstalledVersion','')}: {v.get('Title') or v.get('VulnerabilityID','')}",
                TRIVY_SEV.get((v.get("Severity") or "").upper(), "info"),
                where, description=(v.get("Description") or "")[:600],
                remediation=(f"Upgrade {pkg} to {fixed}." if fixed
                             else "No fixed version published yet."),
                reference=[u for u in [v.get("PrimaryURL")] if u],
                tags=["dependency", "cve"],
                cve=[v.get("VulnerabilityID")] if v.get("VulnerabilityID", "").startswith("CVE") else [],
                cvss=str(((v.get("CVSS") or {}).get("nvd") or {}).get("V3Score") or "")))
        for s in res.get("Secrets") or []:
            # Never carry the matched value: the point is that a secret is in
            # the tree, and a report that quotes it republishes it.
            out.append(_rec(
                "trivy-fs", s.get("RuleID", "secret"),
                f"Possible committed secret: {s.get('Title') or s.get('RuleID','')}",
                TRIVY_SEV.get((s.get("Severity") or "").upper(), "high"),
                f"{where}:{s.get('StartLine','')}",
                description="A credential-shaped string was found in the repository. "
                            "The value is deliberately not reproduced here.",
                remediation="Rotate the credential, then purge it from history.",
                tags=["secret"]))
    return ToolRun("trivy-fs", "ok", out)


def run_trivy_config(source, timeout=900):
    """IaC misconfiguration. Preferred over Checkov because Trivy ranks its
    findings: Checkov OSS returns `severity: null` on every result, which
    cannot be placed against a Medium-and-above reporting floor."""
    data = _trivy("config", source, [], timeout, "trivy-config")
    if isinstance(data, ToolRun):
        return data
    out = []
    for res in data.get("Results") or []:
        where = res.get("Target", source)
        for m in res.get("Misconfigurations") or []:
            loc = (m.get("CauseMetadata") or {}).get("StartLine")
            out.append(_rec(
                "trivy-config", m.get("ID") or m.get("AVDID") or "misconfig",
                m.get("Title") or m.get("ID", ""),
                TRIVY_SEV.get((m.get("Severity") or "").upper(), "info"),
                f"{where}:{loc}" if loc else where,
                description=(m.get("Description") or "")[:600],
                remediation=m.get("Resolution") or "",
                reference=[u for u in [m.get("PrimaryURL")] if u],
                tags=["iac", "terraform"]))
    return ToolRun("trivy-config", "ok", out)


# --------------------------------------------------------------------------
# semgrep - static analysis
# --------------------------------------------------------------------------

def run_semgrep(source, config="p/security-audit", timeout=1800):
    """SAST. This is the only tool in the suite that can see an authorization
    gate that is missing, which no unauthenticated endpoint scan can reach."""
    exe = _which("semgrep", "semgrep.exe")
    if not exe:
        return ToolRun("semgrep", "missing",
                       detail="semgrep not on PATH; run the bootstrap script")
    try:
        proc = _run([exe, "--config", config, "--json", "--quiet",
                     "--timeout", "120", source], timeout)
    except subprocess.TimeoutExpired:
        return ToolRun("semgrep", "failed", detail=f"timed out after {timeout}s")
    if not proc.stdout.strip():
        return ToolRun("semgrep", "failed",
                       detail=(proc.stderr or "no output").strip()[:300])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return ToolRun("semgrep", "failed", detail=f"unparseable JSON: {exc}")

    out = []
    for r in data.get("results") or []:
        extra = r.get("extra") or {}
        meta = extra.get("metadata") or {}
        cwe = meta.get("cwe")
        cwe = cwe if isinstance(cwe, list) else ([cwe] if cwe else [])
        out.append(_rec(
            "semgrep", r.get("check_id", "rule"),
            (extra.get("message") or r.get("check_id", "")).strip().split("\n")[0][:160],
            SEMGREP_SEV.get((extra.get("severity") or "").upper(), "info"),
            f"{r.get('path','')}:{(r.get('start') or {}).get('line','')}",
            description=(extra.get("message") or "")[:600],
            remediation=(extra.get("fix") or ""),
            reference=([meta["shortlink"]] if meta.get("shortlink") else [])
                      + list(meta.get("references") or [])[:3],
            tags=["sast"] + [str(c) for c in cwe][:2]))
    return ToolRun("semgrep", "ok", out)


# --------------------------------------------------------------------------
# checkov - optional IaC breadth
# --------------------------------------------------------------------------

def run_checkov(source, timeout=900):
    """Opt-in. Far more IaC checks than Trivy, but Checkov OSS returns
    `severity: null` for every finding - the severity field is populated by the
    commercial platform, not the open-source CLI. Those findings are floored at
    Low so they are counted without displacing ranked results above the report's
    Medium detail floor. Anything genuinely carrying a severity is mapped."""
    exe = _which("checkov", "checkov.exe", "checkov.cmd")
    if not exe:
        return ToolRun("checkov", "missing",
                       detail="checkov not on PATH; run the bootstrap script")
    try:
        proc = _run([exe, "-d", source, "--compact", "-o", "json", "--quiet"], timeout)
    except subprocess.TimeoutExpired:
        return ToolRun("checkov", "failed", detail=f"timed out after {timeout}s")
    if not proc.stdout.strip():
        return ToolRun("checkov", "failed",
                       detail=(proc.stderr or "no output").strip()[:300])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return ToolRun("checkov", "failed", detail=f"unparseable JSON: {exc}")

    blocks = data if isinstance(data, list) else [data]
    out = []
    unranked = 0
    for block in blocks:
        for c in ((block.get("results") or {}).get("failed_checks") or []):
            sev = (c.get("severity") or "").lower()
            if sev not in TRIVY_SEV.values():
                sev = "low"
                unranked += 1
            rng = c.get("file_line_range") or []
            out.append(_rec(
                "checkov", c.get("check_id", "check"),
                c.get("check_name", c.get("check_id", "")), sev,
                f"{c.get('file_path','')}:{rng[0] if rng else ''}",
                description=(c.get("description") or "")[:600],
                reference=[u for u in [c.get("guideline")] if u],
                tags=["iac"]))
    detail = (f"{unranked} finding(s) carried no severity from Checkov OSS and "
              f"were floored at Low") if unranked else ""
    return ToolRun("checkov", "ok", out, detail)


# --------------------------------------------------------------------------
# OWASP ZAP - optional authenticated DAST
# --------------------------------------------------------------------------

def run_zap(url, timeout=3600, minutes=5):
    """Opt-in. The crawler-driven DAST Nuclei is not: Nuclei matches templates
    for known issues, so custom app-logic and authorization flaws are out of its
    reach by construction. Runs the baseline scan; an authenticated scan needs
    a context file this adapter does not generate."""
    exe = _which("zap.sh", "zap.bat", "zap-baseline.py", "zap")
    if not exe:
        return ToolRun("zap", "missing",
                       detail="ZAP not on PATH; install it or pass --with-zap only "
                              "on a machine where it is present")
    tmp = os.path.join(tempfile.gettempdir(), f"gizmo-zap-{os.getpid()}.json")
    cmd = [exe, "-cmd", "-quickurl", url, "-quickout", tmp, "-quickprogress"]

    # zap.bat and zap.sh both invoke their jar by a RELATIVE path
    # (`java -jar zap-2.17.0.jar`), so they only work when the process's working
    # directory is the ZAP install directory. Launched from anywhere else they
    # print "Error: Unable to access jarfile zap-2.17.0.jar" - AND EXIT 0. A
    # returncode check would read that as success, which is why the report file
    # is what this function actually tests.
    zap_home = os.path.dirname(os.path.abspath(exe))
    try:
        proc = _run(cmd, timeout, cwd=zap_home)
    except subprocess.TimeoutExpired:
        return ToolRun("zap", "failed", detail=f"timed out after {timeout}s")
    if not os.path.exists(tmp):
        blob = f"{proc.stdout}\n{proc.stderr}"
        if "Unable to access jarfile" in blob:
            return ToolRun("zap", "failed",
                           detail=f"ZAP could not find its jar from {zap_home}; "
                                  f"the install looks incomplete")
        return ToolRun("zap", "failed",
                       detail="ZAP wrote no report: " + blob.strip()[:200])
    try:
        data = _json_from_file(tmp)
    except (json.JSONDecodeError, OSError) as exc:
        return ToolRun("zap", "failed", detail=f"unreadable report: {exc}")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    out = []
    for site in data.get("site") or []:
        for a in site.get("alerts") or []:
            inst = (a.get("instances") or [{}])[0]
            out.append(_rec(
                "zap", a.get("pluginid", "alert"), a.get("alert") or a.get("name", ""),
                ZAP_SEV.get(a.get("riskdesc", "").split(" ")[0], "info"),
                inst.get("uri") or url, host=url,
                description=(a.get("desc") or "")[:600],
                remediation=(a.get("solution") or "")[:600],
                reference=[r for r in (a.get("reference") or "").split("\n") if r][:3],
                tags=["dast"],
                cve=[], cvss=str(a.get("cweid") or "")))
    return ToolRun("zap", "ok", out)


# --------------------------------------------------------------------------
# suite driver
# --------------------------------------------------------------------------

DEFAULT_TOOLS = ("nuclei", "sslyze", "trivy-fs", "trivy-config", "semgrep")


def run_suite(target, source=None, with_zap=False, with_checkov=False,
              semgrep_config="p/security-audit"):
    """Run every enabled tool and return (findings, [ToolRun]).

    Nuclei is NOT run here - gizmoduck.cmd_scan owns it, because it already
    handles the failed-scan-is-not-a-clean-scan case and the severity/extra
    passthrough. This returns everything else.
    """
    runs = []
    runs.append(run_sslyze(target))

    if source:
        runs.append(run_trivy_fs(source))
        runs.append(run_trivy_config(source))
        runs.append(run_semgrep(source, semgrep_config))
        if with_checkov:
            runs.append(run_checkov(source))
    else:
        for t in ("trivy-fs", "trivy-config", "semgrep"):
            runs.append(ToolRun(t, "skipped",
                                detail="no --source given; source tools need a directory"))
        if with_checkov:
            runs.append(ToolRun("checkov", "skipped", detail="no --source given"))

    if with_zap:
        runs.append(run_zap(target))

    findings = []
    for r in runs:
        findings.extend(r.findings)
    return findings, runs
