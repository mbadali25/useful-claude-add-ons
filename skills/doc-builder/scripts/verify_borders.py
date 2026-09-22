"""
Verify that every screenshot border actually RENDERS in a built SOP PDF.

Why this exists: the red picture outline is stroked OUTSIDE the image's layout
box. If wp:effectExtent does not reserve room for it, Word clips it at the text
boundary and the top border silently disappears. The .docx looks correct, the
structural checker passes, and a casual render looks fine -- at 100 dpi a
0.75pt line is sub-pixel. Only measuring pixels catches it.

    python verify_borders.py "C:\\path\\My SOP.pdf" -v
    python verify_borders.py                 # every PDF in the brand's masters_dir

This is GATE 2. Gate 1 (check_conformance.py) reads the .docx and cannot see
layout; this reads the rendered PDF. Neither substitutes for the other.

THREE OUTCOMES, NOT TWO
-----------------------
The question Gate 2 asks is "does WORD clip this screenshot border?", because
the defect is Word stroking the outline outside `wp:extent`. A PDF that Word did
not render cannot answer that question in either direction -- LibreOffice lays
the picture out itself and its answer is about LibreOffice.

So every PDF comes out as one of:

  PASS    Word rendered it and every border painted.
  FAIL    Word rendered it and at least one edge is missing.
  UNAVAIL Gate 2 DID NOT RUN, for either of two reasons: Word did not render the
          PDF (or what did could not be determined), or the matching .docx
          cross-check could not be read. The pixel measurement is still printed,
          labelled ADVISORY, because it is useful; it is not a result about Word
          and must never be reported, summarised or carried forward as a pass.

That third value is the whole point. A gate that silently skips itself and then
reports the run as green is the exact shape of bug this repository keeps paying
for: an unknown collapsing into the safe-looking value. Both UNAVAIL reasons
above were once that bug -- the .docx one shipped inside the change that added
the first.

Exit codes. Every outcome that occurred prints its own `Gate 2 result:` line;
the code carries the most actionable one:

  0  every PDF Gate 2 could check PASSed, and there was at least one.
  1  at least one FAILed. A definite failure outranks everything below it.
  2  nothing to check, or a PDF could not be read.
  3  no failures, but at least one UNAVAILABLE -- non-zero on purpose, so a CI
     step or a shell `&&` cannot read "Gate 2 never ran" as success.

WHAT THIS GATE DOES NOT ENFORCE. Whether Word rendered the PDF is read from the
PDF's own /Producer string, which a text editor changes in one byte. The check
defeats ACCIDENT -- converting with LibreOffice and forgetting -- and it does not
defeat an operator routing around their own gate. See limit 2 in
render_engine.py's module docstring for why a sidecar was considered and
rejected.

Third-party requirements: PyMuPDF (imported as pymupdf), numpy, Pillow, and
python-docx for the count cross-check against the matching .docx. The
render-source check in render_engine is stdlib.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pymupdf
from PIL import Image

import render_engine
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
    def clip(v, hi):
        return max(0, min(int(v), hi))
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
    """(count, why_not) - how many bordered screenshots the matching .docx declares.

    Exactly one of the pair is None. The cross-check is what catches a screenshot
    that lost ALL FOUR edges: the pixel measurement then sees no ink and calls it
    `unbordered`, indistinguishable from a decorative image that never had a
    border. Only the .docx knows how many there should be.

    Until 2026-09-22 this swallowed every failure - python-docx absent, a corrupt
    .docx, no sibling file at all - and returned a bare None, which `check_pdf`
    read as "nothing to compare". So "the cross-check did not run" and "the
    cross-check found nothing wrong" were the same value, and a PDF with no
    sibling .docx printed `PASS` and exited 0 on a measurement that never
    happened. Could-not-tell is now its own value and every caller has to carry
    it.
    """
    docx_path = os.path.splitext(pdf_path)[0] + ".docx"
    if not os.path.exists(docx_path):
        return None, (f"there is no {os.path.basename(docx_path)} beside the PDF, so how many "
                      "bordered screenshots it should contain is unknown")
    try:
        import docx as _docx  # pylint: disable=import-outside-toplevel
        from docx.oxml.ns import qn as _qn  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, (f"python-docx is not installed ({exc}), so the .docx cross-check cannot "
                      "run. Run preflight.py")
    try:
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
    except Exception as exc:  # pylint: disable=broad-except
        return None, f"{os.path.basename(docx_path)} could not be read ({exc!r})"
    return n, None


IMAGE_BORDER_RED = "FF0000"   # overwritten from the brand pack in main()


def render_source(path, doc=None):
    """(producer_text, 'word'|'libreoffice'|'other'|'unknown') for an existing PDF.

    PyMuPDF's metadata is preferred because it reads an Info dictionary that
    lives inside a compressed object stream, which a raw byte scan cannot see;
    render_engine's stdlib scan is the fallback. When both come back empty the
    answer is 'unknown', and unknown is NOT 'word'.

    ADVISORY, not enforced. This reads what the PDF says about itself. It is the
    difference between a gate that cannot skip itself and one that cannot skip
    itself BY ACCIDENT, and only the second is true here.
    """
    producer = None
    if doc is not None:
        meta = doc.metadata or {}
        producer = meta.get("producer") or meta.get("creator") or None
    if not producer:
        producer = render_engine.pdf_producer(path)
    return producer, render_engine.classify_producer(producer)


def check_pdf(path):
    """Return (rows, problems, source, crosscheck_problem). One row per drawn image per page.

    `source` is (producer_text, kind) from render_source -- returned from here
    rather than looked up separately so the PDF is opened once and the
    measurement and its provenance can never describe different files.

    `crosscheck_problem` is why the .docx count comparison did not happen, or
    None if it did. It is returned rather than absorbed because a pixel sweep
    that ran without it cannot see a screenshot that lost all four edges, and
    `main` has to turn that into UNAVAILABLE rather than PASS.

    Classification:
      ok        - all four edges painted
      clipped   - some edges painted, some missing (the effectExtent failure)
      unbordered- no red ink on any edge (the footer logo, decorative art)
    """
    doc = pymupdf.open(path)
    source = render_source(path, doc)
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
            rows.append({"page": pno + 1, "img": idx, "cov": cov,
                         "bad": bad, "kind": kind})

    expected, crosscheck_problem = _expected_bordered_count(path)
    seen = sum(1 for r in rows if r["kind"] in ("ok", "clipped"))
    if expected is not None and seen != expected:
        problems += abs(expected - seen)
        rows.append({"page": 0, "img": 0, "cov": {}, "bad": [],
                     "kind": "count",
                     "note": f"docx declares {expected:d} bordered "
                             f"screenshot(s), {seen:d} found in the PDF"})
    return rows, problems, source, crosscheck_problem


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--verbose", "-v", action="store_true")
    resolve_brand.add_brand_argument(ap)
    args = ap.parse_args()

    global IMAGE_BORDER_RED  # pylint: disable=global-statement
    brand = resolve_brand.resolve(args.brand)
    IMAGE_BORDER_RED = brand.sop["image_border"].upper()

    paths = args.paths or sorted(
        glob.glob(os.path.join(brand.require_masters_dir(), "*.pdf"))
    )
    if not paths:
        print("No PDFs found.", file=sys.stderr)
        return 2

    total_missing, failed, unavailable, errored = 0, 0, 0, 0
    for path in paths:
        name = os.path.basename(path)
        try:
            rows, missing, (producer, kind), crosscheck = check_pdf(path)
        except Exception as exc:
            print(f"ERROR {name[:52]!s:<52} {exc}")
            errored += 1
            continue
        bordered = sum(1 for r in rows if r["kind"] in ("ok", "clipped"))
        if kind != render_engine.WORD:
            # The third value. The measurement below is real and worth printing,
            # but it measures how THIS renderer laid the picture out. Gate 2 asks
            # about Word. Counting it as a pass here is the bug; counting it as a
            # failure is a different lie. It is neither.
            unavailable += 1
            said = (f"rendered by {producer}" if producer
                    else "the rendering program could not be determined")
            print(f"UNAVL {name[:58]!s:<58} Gate 2 DID NOT RUN - {said}")
            print("        Gate 2 asks whether WORD clips the screenshot border. A PDF Word did "
                  "not render\n        cannot answer that. This is not a pass and must not be "
                  "recorded as one.")
            print(f"        ADVISORY (this render only, NOT Gate 2): {bordered:d} bordered "
                  f"screenshot(s), {missing:d} edge(s) clipped")
            if args.verbose:
                _print_rows(rows, args.verbose)
            continue
        if not missing and crosscheck:
            # The second way Gate 2 can fail to run, and it hid behind a PASS
            # until 2026-09-22. A screenshot that lost ALL FOUR edges leaves no
            # ink, so the pixel sweep records it as `unbordered` and counts zero
            # problems; only the .docx count says how many there should have
            # been. Without that count the sweep is silent about the exact
            # defect this gate exists for, and silence is not a pass. A real
            # FAIL is a definite answer and is reported as FAIL below even when
            # the cross-check is missing.
            unavailable += 1
            print(f"UNAVL {name[:58]!s:<58} Gate 2 DID NOT RUN - no .docx cross-check")
            print(f"        {crosscheck}.")
            print("        A screenshot that lost all four edges leaves no ink and reads as an\n"
                  "        unbordered decorative image. Only the .docx count separates the two,\n"
                  "        so a clean pixel sweep without it is not a pass.")
            print(f"        ADVISORY (pixels only, NOT Gate 2): {bordered:d} bordered "
                  f"screenshot(s), {missing:d} edge(s) clipped")
            if args.verbose:
                _print_rows(rows, args.verbose)
            continue
        total_missing += missing
        status = "FAIL " if missing else "PASS "
        print(f"{status}{name[:58]!s:<58} {bordered:d} bordered screenshot(s), {missing:d} edge(s) clipped")
        if crosscheck:
            print(f"        !! the .docx cross-check did not run ({crosscheck}); the FAIL above "
                  "rests on the pixel measurement alone.")
        _print_rows(rows, args.verbose)
        if missing:
            failed += 1

    checked = len(paths) - unavailable - errored
    print(f"\n{len(paths):d} PDF(s) seen: {checked - failed:d} PASS, {failed:d} FAIL, "
          f"{unavailable:d} UNAVAILABLE (Gate 2 did not run), {errored:d} unreadable. "
          f"{total_missing:d} edge(s) missing across the PDFs Gate 2 could actually check.")
    # The verdict repeats the third value rather than letting the reader infer
    # it from an exit code. Every line derived from "could not tell" has to keep
    # saying "could not tell" -- so EVERY outcome that occurred prints its own
    # line, and only then does one exit code get chosen.
    #
    # This used to be a chain of early returns headed by `if errored: return 2`.
    # A run with a genuine border failure plus one unreadable PDF therefore said
    # ERROR and exited 2 where it had previously exited 1, and any run that
    # errored at all suppressed the UNAVAILABLE line entirely -- the same bug
    # this file exists to prevent, one rung further out. Print first, decide
    # after.
    if failed:
        print(f"Gate 2 result: FAIL - {failed:d} of the {checked:d} PDF(s) Gate 2 could check "
              "have a clipped border.")
    if errored:
        print(f"Gate 2 result: ERROR - {errored:d} PDF(s) could not be read.")
    if unavailable and checked == 0:
        print("Gate 2 result: UNAVAILABLE - no PDF could be checked (Word did not render it, or "
              "the .docx cross-check was unavailable), so Gate 2 did not run at all. This is NOT "
              "a pass.")
    elif unavailable:
        print(f"Gate 2 result: UNAVAILABLE for {unavailable:d} of {len(paths):d} PDF(s); the "
              f"other {checked:d} were checked. The run as a whole is not a pass.")
    # A definite failure outranks a could-not-read, which outranks a
    # could-not-run: the most actionable answer is the one the exit code carries,
    # and the lines above carry the rest.
    if failed:
        return 1
    if errored:
        return 2
    if unavailable:
        return 3
    print("Gate 2 result: PASS.")
    return 0


def _print_rows(rows, verbose):
    """The per-image coverage lines, shared by the PASS/FAIL and UNAVAILABLE paths."""
    for r in rows:
        if r["kind"] == "count":
            print(f"        !! {r['note']}")
        elif r["kind"] == "clipped" or (verbose and r["kind"] != "unbordered"):
            cov = ", ".join(f"{k} {v * 100:.0f}%" for k, v in r["cov"].items())
            flag = f"  <-- {'/'.join(r['bad'])} CLIPPED" if r["bad"] else ""
            print(f"        p{r['page']:d} img{r['img']:d}: {cov}{flag}")


if __name__ == "__main__":
    raise SystemExit(main())
