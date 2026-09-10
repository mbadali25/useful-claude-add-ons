"""
Patch wp:effectExtent into existing SOP masters so their screenshot borders
stop being clipped at the top of a page.

Most masters predate the generator and have no JSON spec, so they cannot be
rebuilt -- they are edited in place instead. The edit is additive: it only adds
or widens wp:effectExtent on inline shapes, and touches nothing else.

    python fix_effect_extent.py --dry-run      # report what would change
    python fix_effect_extent.py                # patch (backs up first)
    python fix_effect_extent.py --name "*VPN*"
    python fix_effect_extent.py --dir "C:\\other\\masters" --dry-run

Masters are taken from the active brand pack's masters_dir unless --dir is
given. After patching, rebuild the PDFs (build_sop.py --to-pdf, or Word) and
re-run verify_borders.py.

Third-party requirement: python-docx.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys

import datetime as _dt

import docx
from docx.oxml.ns import qn

import resolve_brand
from build_sop import EFFECT_EXTENT_MIN, SopBuilder

BACKUP = "_backup_effectextent_" + _dt.date.today().strftime("%Y%m%d")


def audit(path):
    """(bordered_inlines, inlines_needing_a_fix)"""
    d = docx.Document(path)
    bordered = needing = 0
    for inline in d.element.body.findall(".//" + qn("wp:inline")):
        if "<a:ln" not in inline.xml:
            continue
        bordered += 1
        ee = inline.find(qn("wp:effectExtent"))
        if ee is None or any(int(ee.get(s) or 0) < EFFECT_EXTENT_MIN for s in "ltrb"):
            needing += 1
    return bordered, needing


def patch(path):
    d = docx.Document(path)
    changed = SopBuilder._reserve_effect_extent(d.element.body)
    if changed:
        d.save(path)
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="*", help='wildcard over basenames, e.g. "*VPN*"')
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dir", help="masters directory (default: the brand pack's masters_dir)")
    resolve_brand.add_brand_argument(ap)
    args = ap.parse_args()

    if args.dir:
        sops = os.path.abspath(args.dir)
        if not os.path.isdir(sops):
            print("Not a directory: %s" % sops, file=sys.stderr)
            return 2
    else:
        sops = resolve_brand.resolve(args.brand).require_masters_dir()
    paths = [p for p in sorted(glob.glob(os.path.join(sops, "*.docx")))
             if not os.path.basename(p).startswith("~$")]
    if args.name != "*":
        import fnmatch
        paths = [p for p in paths
                 if fnmatch.fnmatch(os.path.splitext(os.path.basename(p))[0], args.name)]
    if not paths:
        print("No masters matched.", file=sys.stderr)
        return 2

    backup_dir = os.path.join(sops, BACKUP)
    if not args.dry_run:
        os.makedirs(backup_dir, exist_ok=True)

    total = 0
    for path in paths:
        name = os.path.basename(path)
        bordered, needing = audit(path)
        if not needing:
            print("ok    %-58s %d bordered, none needing a fix" % (name[:58], bordered))
            continue
        if args.dry_run:
            print("WOULD %-58s %d of %d inline(s) need effectExtent" % (name[:58], needing, bordered))
            total += needing
            continue
        shutil.copy2(path, os.path.join(backup_dir, name))
        changed = patch(path)
        total += changed
        print("FIXED %-58s %d inline(s) patched" % (name[:58], changed))

    verb = "would be" if args.dry_run else "were"
    print("\n%d inline shape(s) %s patched across %d master(s)." % (total, verb, len(paths)))
    if not args.dry_run and total:
        print("Backups: %s" % backup_dir)
        print("Next: rebuild the PDFs, then run verify_borders.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
