"""
Verify that every screenshot border actually RENDERS in a built SOP PDF.

Why this exists: the red picture outline is stroked OUTSIDE the image's layout
box. If wp:effectExtent does not reserve room for it, Word clips it at the text
boundary and the top border silently disappears. The .docx looks correct, the
structural checker passes, and a casual render looks fine -- at 100 dpi a
0.75pt line is sub-pixel. Only measuring pixels catches it.

    python verify_borders.py "C:\\path\\My SOP.pdf" -v
    python verify_borders.py                 # every PDF in the brand's masters_dir

Exit code is non-zero if any edge is missing.

This is GATE 2. Gate 1 (check_conformance.py) reads the .docx and cannot see
layout; this reads the rendered PDF. Neither substitutes for the other.

Third-party requirements: PyMuPDF (imported as pymupdf), numpy, Pillow, and
python-docx for the count cross-check against the matching .docx.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pymupdf
from PIL import Image

import resolve_brand

DPI = 300
SCALE = DPI / 72.0
BAND = 5          # px either side of the nominal edge to search for the stroke
INSET = 4         # px ignored at each corner
PRESENT = 0.90    # >= this fraction of the edge painted => border present
MISSING = 0.50    # <  this fraction => border missing


TOLERANCE = 90    # per-channel distance from the brand's border colour that still counts as its ink


def _target_rgb():
    h = IMAGE_BORDER_RED.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _ink_mask(page):
    """Pixels close to the ACTIVE BRAND's border colour. Was hard-coded to
    pure red, which failed a correctly built document under any pack whose
    sop.image_border is not red - a false failure on the one gate that exists
    because a real defect shipped for four months."""
    pix = page.get_pixmap(dpi=DPI)
    a = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).astype(int)
    tr, tg, tb = _target_rgb()
    return ((abs(a[:, :, 0] - tr) < TOLERANCE) & (abs(a[:, :, 1] - tg) < TOLERANCE)
            & (abs(a[:, :, 2] - tb) < TOLERANCE))


_red_mask = _ink_mask  # old name, kept for any caller that imported it


def _coverage(mask, x0, y0, x1, y1):
    """Fraction of each edge that carries red ink, searching a small band."""
    h, w = mask.shape
    clip = lambda v, hi: max(0, min(int(v), hi))
    x0, x1 = clip(x0, w - 1), clip(x1, w - 1)
    y0, y1 = clip(y0, h - 1), clip(y1, h - 1)
    out = {}
    for name, horizontal, at in (("top", True, y0), ("bottom", True, y1),
                                 ("left", False, x0), ("right", False, x1)):
        lo, hi = clip(at - BAND, (h if horizontal else w) - 1), clip(at + BAND, (h if horizontal else w) - 1)
        if horizontal:
            band = mask[lo:hi + 1, x0 + INSET:x1 - INSET + 1]
        else:
            band = mask[y0 + INSET:y1 - INSET + 1, lo:hi + 1]
        if band.size == 0:
            out[name] = 0.0
            continue
        along = band.any(axis=0 if horizontal else 1)
        out[name] = float(along.mean())
    return out


def _expected_bordered_count(pdf_path):
    """How many bordered screenshots the matching .docx says there should be.
    Guards against a screenshot losing ALL four edges and being mistaken for
    an unbordered decorative image."""
    docx_path = os.path.splitext(pdf_path)[0] + ".docx"
    if not os.path.exists(docx_path):
        return None
    try:
        import docx as _docx
        from docx.oxml.ns import qn as _qn
        d = _docx.Document(docx_path)
        n = 0
        for inline in d.element.body.findall(".//" + _qn("wp:inline")):
            # ANY outlined inline counts, whatever its colour. Counting only the
            # brand colour let a document bordered in the WRONG colour pass
            # this gate with "0 bordered screenshots" - the PDF showed no ink
            # of the expected colour and the docx declared none of it either.
            # Gate 1 names the colour mismatch; this makes Gate 2 fail loudly
            # on it too instead of agreeing with the wrong answer.
            if "<a:ln" in inline.xml:
                n += 1
        return n
    except Exception:
        return None


IMAGE_BORDER_RED = "FF0000"   # overwritten from the brand pack in main()


def check_pdf(path):
    """Return (rows, problems). One row per drawn image per page.

    Classification:
      ok        - all four edges painted
      clipped   - some edges painted, some missing (the effectExtent failure)
      unbordered- no red ink on any edge (the footer logo, decorative art)
    """
    doc = pymupdf.open(path)
    rows, problems = [], 0
    for pno in range(doc.page_count):
        page = doc[pno]
        infos = page.get_image_info()
        if not infos:
            continue
        mask = _red_mask(page)
        for idx, info in enumerate(infos, 1):
            bx0, by0, bx1, by1 = info["bbox"]
            cov = _coverage(mask, bx0 * SCALE, by0 * SCALE, bx1 * SCALE, by1 * SCALE)
            bad = [k for k, v in cov.items() if v < MISSING]
            if not bad:
                kind = "ok"
            elif len(bad) == 4:
                kind = "unbordered"
            else:
                kind = "clipped"
                problems += len(bad)
            rows.append(dict(page=pno + 1, img=idx, cov=cov, bad=bad, kind=kind))

    expected = _expected_bordered_count(path)
    seen = sum(1 for r in rows if r["kind"] in ("ok", "clipped"))
    if expected is not None and seen != expected:
        problems += abs(expected - seen)
        rows.append(dict(page=0, img=0, cov={}, bad=[], kind="count",
                         note="docx declares %d bordered screenshot(s), %d found in the PDF"
                              % (expected, seen)))
    return rows, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--verbose", "-v", action="store_true")
    resolve_brand.add_brand_argument(ap)
    args = ap.parse_args()

    global IMAGE_BORDER_RED
    brand = resolve_brand.resolve(args.brand)
    IMAGE_BORDER_RED = brand.sop["image_border"].upper()

    paths = args.paths or sorted(
        glob.glob(os.path.join(brand.require_masters_dir(), "*.pdf"))
    )
    if not paths:
        print("No PDFs found.", file=sys.stderr)
        return 2

    total_missing, failed = 0, 0
    for path in paths:
        name = os.path.basename(path)
        try:
            rows, missing = check_pdf(path)
        except Exception as exc:
            print("ERROR %-52s %s" % (name[:52], exc))
            failed += 1
            continue
        total_missing += missing
        status = "FAIL " if missing else "PASS "
        bordered = sum(1 for r in rows if r["kind"] in ("ok", "clipped"))
        print("%s%-58s %d bordered screenshot(s), %d edge(s) clipped"
              % (status, name[:58], bordered, missing))
        for r in rows:
            if r["kind"] == "count":
                print("        !! %s" % r["note"])
            elif r["kind"] == "clipped" or (args.verbose and r["kind"] != "unbordered"):
                cov = ", ".join("%s %.0f%%" % (k, v * 100) for k, v in r["cov"].items())
                flag = "  <-- %s CLIPPED" % "/".join(r["bad"]) if r["bad"] else ""
                print("        p%d img%d: %s%s" % (r["page"], r["img"], cov, flag))
        if missing:
            failed += 1

    print("\n%d PDF(s) checked, %d with missing borders, %d edges missing total."
          % (len(paths), failed, total_missing))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
