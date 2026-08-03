#!/usr/bin/env python3
"""
verify_vsdx.py - Round-trip a generated .vsdx through the real Visio parser.

    python verify_vsdx.py out.vsdx

Installs the `vsdx` package automatically if it is missing. If that install
fails, this reports UNVERIFIED and exits 2 -- it never pretends a file is good.

What this proves: the OPC package is well formed, parts resolve, shapes carry
text and coordinates, and glue entries exist.

What this does NOT prove: that Microsoft Visio itself opens the file cleanly.
Visio is stricter than any third-party parser. Always ask the user to open it
once and confirm, rather than reporting it as verified.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

REQUIRED_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "visio/document.xml",
    "visio/_rels/document.xml.rels",
    "visio/pages/pages.xml",
    "visio/pages/_rels/pages.xml.rels",
}


def ensure_vsdx() -> bool:
    if importlib.util.find_spec("vsdx"):
        return True
    print("vsdx package not found; installing...")
    base = [sys.executable, "-m", "pip", "install", "--quiet", "vsdx"]
    for args in (base, base + ["--break-system-packages"]):
        try:
            if subprocess.run(args, capture_output=True, text=True,
                             timeout=180, check=False).returncode == 0:
                break
        except (subprocess.TimeoutExpired, OSError):
            break
    return importlib.util.find_spec("vsdx") is not None


def check_package(path: Path) -> list[str]:
    """Structural checks that need no third-party code, so they run even offline."""
    problems = []
    if not zipfile.is_zipfile(path):
        return ["not a ZIP archive -- this is not a .vsdx"]
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if z.testzip() is not None:
            problems.append("corrupt ZIP entry")
        if not names or names[0] != "[Content_Types].xml":
            problems.append("[Content_Types].xml is not the first entry "
                            "(Visio will report unreadable content)")
        for part in sorted(REQUIRED_PARTS - set(names)):
            problems.append(f"missing required part: {part}")
        if not any(n.startswith("visio/pages/page") and n.endswith(".xml")
                   and "_rels" not in n for n in names):
            problems.append("no page content part (visio/pages/pageN.xml)")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"not found: {path}")
        return 2

    print(f"File     : {path}  ({path.stat().st_size:,} bytes)")

    problems = check_package(path)
    if problems:
        print("\nSTRUCTURE: FAILED")
        for p in problems:
            print(f"  - {p}")
        print("\nSee references/vsdx-format.md section 7 for symptom -> cause.")
        return 1
    print("Structure: ok (OPC parts present, ordering correct)")

    if not ensure_vsdx():
        print("\nUNVERIFIED: could not install the `vsdx` package (offline or proxied).")
        print("Structural checks passed, but the parse round-trip did not run.")
        print("Report this to the user as UNVERIFIED, not as validated.")
        return 2

    from vsdx import VisioFile
    try:
        with VisioFile(str(path)) as v:
            pages = v.get_page_names()
            print(f"Parse    : ok ({len(pages)} page(s): {', '.join(pages)})")
            total_shapes = total_glue = 0
            for i, name in enumerate(pages):
                pg = v.get_page(i)
                shapes = pg.all_shapes
                total_shapes += len(shapes)
                total_glue += len(pg.connects)
                print(f"\n  Page '{name}'  {pg.width} x {pg.height} in")
                for s in shapes:
                    txt = (s.text or "").strip().replace("\n", " ")
                    print(f"    id={s.ID:<4} {txt[:34]!r:38} @ ({s.x}, {s.y})")
                print(f"    glue entries: {len(pg.connects)}")
    except Exception as e:
        print(f"\nPARSE FAILED: {type(e).__name__}: {e}")
        print("The package is well formed but the XML content is not valid Visio.")
        return 1

    # Each connector should contribute two <Connect> rows (begin + end).
    if total_glue % 2:
        print("\nWarning: odd number of glue entries -- a connector is glued at "
              "only one end and will not follow its shape.")

    print(f"\nRESULT: parses cleanly. {total_shapes} shapes, {total_glue} glue entries.")
    print("NOT PROOF Visio opens it -- ask the user to open it once and confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
