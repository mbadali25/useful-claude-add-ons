---
description: Check the Gizmoduck toolchain (nuclei, templates, python, PDF)
---
Run `gizmoduck.py doctor` and report what's installed vs missing. If nuclei or templates are
missing, tell the user to run bootstrap.sh (WSL/Linux) or bootstrap.ps1 (Windows).

A scanner whose own probe passes but cannot actually run is reported as missing too: testssl
without `hexdump` (testssl.sh's `--version` succeeds without it, then every scan refuses).
