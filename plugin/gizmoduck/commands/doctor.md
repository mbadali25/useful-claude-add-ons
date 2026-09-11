---
description: Check the Gizmoduck toolchain (nuclei, templates, the scanner suite, PDF)
---
Run `gizmoduck.py doctor` and report what's installed vs missing, tool by tool.

`doctor` reports three groups:

- **Core** — nuclei, its templates, python, wkhtmltopdf. A missing nuclei or missing
  templates fails the check: nuclei with no templates finds nothing and exits 0, which
  is indistinguishable from a clean scan.
- **Scanner suite** — sslyze, trivy, semgrep. These run on every scan. A missing one
  fails the check too, because a scan that quietly drops three of five tools reads as
  a clean result.
- **Optional** — OWASP ZAP and checkov. Absent is a valid state; these never fail the
  check. They run only with `--with-zap` / `--with-checkov`.

If anything in the first two groups is missing, tell the user to run `bootstrap.sh`
(Linux/macOS/WSL) or `bootstrap.ps1` (Windows) — those install the whole suite, not
just nuclei.

Two failure modes worth naming when you see them:

- **wkhtmltopdf installed but not on PATH.** Common on Windows, because winget installs
  it to `C:\Program Files\wkhtmltopdf\bin` without adding that directory. The symptom is
  that HTML reports work and PDFs are silently absent. The bootstrap now fixes the PATH
  entry; for an existing install, add that directory to the user PATH.
- **A tool resolving inside an unrelated virtualenv.** `sslyze` and `semgrep` are Python
  tools, so `doctor` can report them present because some other project's venv happens to
  be active. Check the printed path is one the account will have on PATH during an
  unattended scan, not a venv that was active only while doctor ran.
