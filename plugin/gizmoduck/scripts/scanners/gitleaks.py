"""Gitleaks adapter - committed secrets, for `kind: secrets`.

Why gitleaks and not trufflehog. Both find secrets; they differ in what they
do next. Trufflehog's headline feature is *verification* - it sends each
candidate credential to the provider's API to see whether it is live. A CI
job doing that sends every secret it finds, from every branch, to a third
party on every run, which is exactly the traffic a security scan should not
generate. Gitleaks is offline: regex and entropy rules, one static Go binary,
MIT licensed, JSON and SARIF reports, and `git --log-opts` so a PR check scans
only the commits the PR adds. bootstrap.sh pins its version and verifies the
release checksum; `git` and `dir` subcommands need 8.19 or later.

Two modes, chosen by `opts["gitleaks_mode"]`:

    git   `gitleaks git <path> --log-opts <range>` - commits in a range (the
          tier-1 PR check: base..HEAD, so only what the PR adds)
    dir   `gitleaks dir <path>` - the checked-out tree (tier 2 and the sweep)

`--redact` is always passed: the report is uploaded as a pipeline artifact,
and a report that reprinted the secret would leak it a second time. The parser
never copies `Secret` or `Match` into a finding either.

Severity. Gitleaks assigns none, so one is assigned here and the finding is
NOT tagged `severity-assigned` - that tag would make the CI gate treat every
secret as unknown. The assignment is a rule, not a default: a credential in
the repository is usable by anyone who can read it, so a provider-specific
rule (an AWS key, a GitHub token, a private key) is `critical`. The one
exception is `generic-api-key`, gitleaks' entropy-based catch-all, which is
the rule that produces most false positives - `high`, so it still fails a
tier-2 gate but does not block a tier-1 PR check on its own.

Exit status is never read (base.py): `--exit-code 0` is passed so a leak
does not look like a crash, and the parsed report decides.
"""
import json
import os

import normalize as n
from . import base

NAME = "gitleaks"
KINDS = ["secrets"]
ACTIVE = False
ACTIVE_OPTS = []
DEFAULT_ENABLED = True
DEFAULT_TIMEOUT = 1200
REPORT_FILENAME = "gitleaks.json"

_LOWER_CONFIDENCE_RULES = {"generic-api-key"}


def is_available():
    return base.which("gitleaks") is not None


def run(target, outdir, opts=None):
    opts = opts or {}
    binary = base.which("gitleaks")
    if not binary:
        return None, base.ToolResult(returncode=-1, stdout="", stderr="gitleaks not found on PATH",
                                     timed_out=False)
    os.makedirs(outdir, exist_ok=True)
    raw_path = os.path.join(outdir, REPORT_FILENAME)
    if os.path.isfile(raw_path):
        os.remove(raw_path)
    if opts.get("gitleaks_mode") == "git":
        argv = [binary, "git", target]
        if opts.get("gitleaks_log_opts"):
            argv += ["--log-opts", opts["gitleaks_log_opts"]]
    else:
        argv = [binary, "dir", target]
    argv += ["--report-format", "json", "--report-path", raw_path, "--redact",
             "--no-banner", "--exit-code", "0"]
    result = base.run_tool(argv, timeout=opts.get("timeout", DEFAULT_TIMEOUT), cwd=opts.get("cwd"))
    if result.timed_out or not os.path.isfile(raw_path):
        return None, result
    return raw_path, result


def parse(raw_path, target):
    try:
        with open(raw_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError as e:
        raise base.ParseError(f"{raw_path}: could not read file: {e}") from e
    if not content.strip():
        raise base.ParseError(f"{raw_path}: empty output")
    try:
        data = json.loads(content)
    except ValueError as e:
        raise base.ParseError(f"{raw_path}: invalid JSON: {e}") from e
    if not isinstance(data, list):
        raise base.ParseError(f"{raw_path}: not a gitleaks report (expected a JSON array)")
    findings = []
    for item in data:
        if not isinstance(item, dict):
            raise base.ParseError(f"{raw_path}: report contains a {type(item).__name__}, expected an object")
        rule = str(item.get("RuleID") or "secret")
        path = str(item.get("File") or "")
        line = item.get("StartLine")
        where = f"{path}:{line}" if isinstance(line, int) and line > 0 else path
        commit = str(item.get("Commit") or "")[:12]
        severity = n.SEV_NUM["high" if rule in _LOWER_CONFIDENCE_RULES else "critical"]
        desc = str(item.get("Description") or rule)
        finding = n.make_finding(
            tool=NAME, target=target, rule_id=rule, name=f"Secret in repository: {desc}"[:160],
            severity=severity, type="secret", matched_at=where,
            description=(f"gitleaks rule {rule} matched {where}" + (f" in commit {commit}" if commit else "")
                         + ". The value is redacted here and in the raw report."),
            remediation="Revoke and rotate the credential first; removing it from the code or history does "
                        "not un-leak it.",
            tags=["secret"])
        finding["path"] = path
        finding["line"] = line if isinstance(line, int) else None
        findings.append(finding)
    return findings
