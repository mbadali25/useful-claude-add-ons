"""Adapter registry. Kind -> default adapter names, and name -> module.

No tfsec: its engine was folded into Trivy in 2023 and its rules stopped
moving in 2025, so IaC coverage runs through trivy's misconfig scanner
instead (spec 13.4).
"""
from . import (nuclei, zap, nikto, nmap, testssl,
               trivy, depcheck, checkov, sqlmap, semgrep)

ADAPTERS = {m.NAME: m for m in
            (nuclei, zap, nikto, nmap, testssl, trivy, depcheck, checkov,
             sqlmap, semgrep)}

KIND_DEFAULTS = {
    "web":  ["nuclei", "zap", "nikto", "nmap", "testssl"],
    "host": ["nuclei", "nmap", "testssl"],
    "iac":  ["checkov", "trivy"],
    "deps": ["trivy", "depcheck"],
    # Source code. Every other kind reads something the code PRODUCED - a
    # running endpoint, a lockfile, a rendered plan - so all of them are
    # blind to a check that is MISSING. An authorization gate that was
    # never written has no signature, no CVE and no misconfigured
    # resource; the endpoint answers 200 exactly as it should.
    "code": ["semgrep"],
}


def get(name):
    if name not in ADAPTERS:
        raise KeyError("unknown scanner %r; known: %s"
                       % (name, ", ".join(sorted(ADAPTERS))))
    return ADAPTERS[name]
