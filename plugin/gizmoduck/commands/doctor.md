---
description: Check the Gizmoduck toolchain (nuclei, templates, python, PDF)
---
Run `gizmoduck.py doctor` and report what's installed vs missing. If nuclei or templates are
missing, tell the user to run bootstrap.sh (WSL/Linux) or bootstrap.ps1 (Windows).
It also prints the tool home and each set lookup override (`GIZMODUCK_ZAP_HOME`,
`GIZMODUCK_NIKTO_PL`, `GIZMODUCK_TESTSSL_SH`). A `!!` override points at nothing and disables
that tool instead of falling back to PATH: tell the user to fix or unset it. These lines never
change doctor's exit status.

A scanner whose own probe passes but cannot actually run is reported as missing too: testssl
without `hexdump` (testssl.sh's `--version` succeeds without it, then every scan refuses).
