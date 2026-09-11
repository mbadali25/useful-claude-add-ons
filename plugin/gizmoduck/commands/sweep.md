---
description: Scan every site a repository declares, with the full tool suite
argument-hint: [repo-root] [--with-zap]
---
Run `gizmoduck.py sweep ${1:-.}` — the standard way to answer "run a security scan on
all the sites in this repository". Do **not** hand-roll a loop over targets; that is how
the conventions drift, and every one of the behaviours below exists because an ad-hoc
script got it wrong once.

What it does, per declared site:

1. Finds every module carrying a `public-endpoint.md` (override with `--declaration`),
   reading `url`, `status` and `kind` from its front matter.
2. Runs the **full suite**: nuclei and sslyze against the `url`, and trivy plus semgrep
   against that module's **own directory** — not the repo root, which would scan every
   module once per site.
3. Writes `findings.jsonl` plus `report.md`, `report.html` and `report.pdf` into
   `<module>/docs/security-scans/<date>/` (override the middle part with `--scan-dir`).
   Reports itemise **Medium and above**; Low and Info are counted in the severity table
   and stay in the JSONL.

Add `--with-zap` for crawler-driven DAST (roughly 30-60s per target on top) and
`--with-checkov` for IaC breadth. Both are off by default.

## Reading the result honestly

- **Exit 1 means at least one module did not scan cleanly**, not that findings exist.
  The summary names each one. Those modules' reports are INCOMPLETE, not clean — say so
  when reporting, rather than presenting a quiet report as a pass.
- **A module whose endpoint does not resolve is still scanned.** Dependencies, Terraform
  and source code do not care whether the endpoint is reachable. The sweep prints the DNS
  warning and runs the source tools anyway; only the endpoint tools fail.
- **A clean module still gets HTML and PDF.** Zero findings is a result somebody needs to
  open and file.
- **Check `doctor` first if a whole sweep comes back quiet.** A missing tool is reported
  per module, but across eighteen modules that line is easy to scroll past, and nuclei
  alone against authenticated apps behind a WAF returns almost nothing but Info-severity
  fingerprinting.

## After the sweep

Group findings by cause before reporting or ticketing. Edge-configuration findings — a
missing CSP header, absent anti-clickjacking — will repeat across most sites because they
come from one shared CloudFront/WAF configuration. Twenty Mediums that are one fix should
be reported as one fix, not twenty tickets. Dependency CVEs are the opposite: they are
per-module and each needs its own upgrade.

For ticketing, run `/gizmoduck:tickets` against a specific module's `findings.jsonl` —
the confirm-then-create gate is per batch and is not bypassed by a sweep.
