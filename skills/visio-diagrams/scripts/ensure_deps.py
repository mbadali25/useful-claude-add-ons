#!/usr/bin/env python3
"""
ensure_deps.py - Install the optional packages this skill uses.

Nothing here is needed to CREATE a .vsdx. vsdx_writer.py is stdlib-only by
design, so diagram generation still works on an air-gapped box with no pip
access. These packages only unlock verification, YAML specs, and PNG previews.

    python ensure_deps.py              # install anything missing
    python ensure_deps.py --check      # report only, install nothing, exit 1 if gaps
    python ensure_deps.py vsdx pyyaml  # install specific ones

If installation fails (proxy, offline, locked-down runtime) this exits 0 and
tells you what degrades. A failed optional install must never block the actual
task -- fall back to JSON specs and skip the round-trip check.
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys

# package name on PyPI -> (import name, what breaks without it)
DEPS = {
    "vsdx":     ("vsdx",     "verification round-trip; reading/editing existing .vsdx"),
    "pyyaml":   ("yaml",     "YAML specs (JSON specs still work)"),
    "cairosvg": ("cairosvg", "rendering the SVG preview to PNG (SVG itself still written)"),
}


def installed(pkg: str) -> bool:
    return importlib.util.find_spec(DEPS[pkg][0]) is not None


def pip_install(pkgs: list[str]) -> bool:
    """Try a plain install first; retry with --break-system-packages for
    PEP-668 environments (Debian/Ubuntu system Python, most containers)."""
    base = [sys.executable, "-m", "pip", "install", "--quiet", *pkgs]
    for args in (base, base + ["--break-system-packages"]):
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=180)
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"  pip failed to run: {e}", file=sys.stderr)
            return False
        if r.returncode == 0:
            return True
        if "externally-managed-environment" not in (r.stderr or ""):
            print(f"  {(r.stderr or '').strip().splitlines()[-1:] or ['pip error']}",
                  file=sys.stderr)
            return False
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packages", nargs="*", metavar="PACKAGE",
                    help=f"subset to handle (default: all of {', '.join(DEPS)})")
    ap.add_argument("--check", action="store_true",
                    help="report status only; exit 1 if anything is missing")
    a = ap.parse_args()

    unknown = [p for p in a.packages if p not in DEPS]
    if unknown:
        ap.error(f"unknown package(s): {', '.join(unknown)}. "
                 f"Choose from: {', '.join(DEPS)}")
    want = a.packages or list(DEPS)

    missing = [p for p in want if not installed(p)]
    present = [p for p in want if p not in missing]

    for p in present:
        print(f"  ok      {p}")

    if a.check:
        for p in missing:
            print(f"  MISSING {p:9} -> disables: {DEPS[p][1]}")
        return 1 if missing else 0

    if not missing:
        print("All optional dependencies present.")
        return 0

    print(f"Installing: {', '.join(missing)}")
    ok = pip_install(missing)

    still = [p for p in missing if not installed(p)]
    for p in [p for p in missing if p not in still]:
        print(f"  installed {p}")

    if still:
        print("\nCould not install: " + ", ".join(still))
        print("Generating .vsdx still works -- vsdx_writer.py is stdlib-only.")
        print("Degraded capabilities:")
        for p in still:
            print(f"  - no {p}: {DEPS[p][1]}")
        if "pyyaml" in still:
            print("\nWorkaround: write the spec as JSON instead of YAML.")
        if "vsdx" in still:
            print("\nWorkaround: skip the round-trip check and tell the user the")
            print("output is unverified -- do not imply it was validated.")
    # Exit 0 regardless: a missing optional dep is not a task failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
