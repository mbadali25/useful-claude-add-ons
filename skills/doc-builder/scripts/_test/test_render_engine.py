"""The renderer is a deliberate, labelled choice - and Gate 2 has three outcomes.

Four properties, and the second is the one that earns this file:

1. `render_engine.choose_engine` never substitutes one engine for another. The
   answer comes from `--renderer` or from an explicit platform branch, and it
   always carries the reason it was reached.
2. `verify_borders.py` reports a PDF that Word did not render as UNAVAILABLE and
   exits non-zero. Never PASS, never silently skipped. Gate 2 asks whether WORD
   clips a screenshot border; a LibreOffice render cannot answer that in either
   direction, and a gate that skips itself while reporting green is the exact
   bug this repository keeps paying for.
3. A conversion that exits 0 produced a file - on BOTH engines. `to_soffice`
   and `build_report.to_word` run the same three checks through the same
   function, `render_engine.conversion_problem`.
4. LibreOffice converts a document it did not generate without reaching the
   network. `harden_profile` seeds the throwaway soffice profile, and
   `test_a_remote_reference_is_not_fetched_during_conversion` proves it against
   a real soffice by watching a loopback HTTP server that the unhardened
   conversion hits.

Sabotage check for (2): delete the `kind != WORD` branch in verify_borders.main
and `test_libreoffice_pdf_is_unavailable_not_pass` goes red - the LibreOffice
PDF prints `PASS` and the run exits 0.

WHAT THE pymupdf STUB DOES AND DOES NOT COVER
---------------------------------------------
PyMuPDF is NOT installed on every machine that runs this suite (it is a wheel,
and a PEP 668 host cannot pip-install it), so `pymupdf` is stubbed. The stub is
deliberate rather than a shortcut, and it has two shapes:

* `_StubDoc` with NO pages, used wherever the test is about provenance. With
  empty metadata `render_source` must fall back to `render_engine.pdf_producer`,
  the stdlib byte scan, so the path exercised is the one that runs on a machine
  with no third-party PDF library at all.
* `_PixelPage`, which returns a real 600x500 RGB raster and a real image bbox.
  `_ink_mask`, `_coverage` and a NON-ZERO `missing` all run for real against the
  installed numpy and Pillow - so `test_a_clipped_top_edge_is_a_real_fail`
  measures pixels and asserts the FAIL path returns 1. Until 2026-09-22 every
  PASS/FAIL assertion here was about a PDF with zero images and nothing reached
  those three functions at all.

Still NOT covered, and no test here should be read as covering it: the bridge
from a real PDF to those pixels. `pymupdf.open`, `page.get_pixmap(dpi=300)` and
`page.get_image_info()` are stubbed, so their argument handling, the 72->300 dpi
SCALE against a real renderer's coordinate space, and PyMuPDF's own bbox
convention are unverified here. `_PixelPage` renders what this suite believes
PyMuPDF returns. Proving that belief needs PyMuPDF installed and a real
Word-rendered PDF, which is Gate 2 itself, on Windows.
"""

import os
import subprocess
import sys
import types

import pytest

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import render_engine  # noqa: E402


# -- a PDF's Producer, read with the stdlib alone ------------------------------

def _minimal_pdf(producer_literal=None, producer_hex=None):
    """A syntactically valid one-page PDF carrying the given /Producer.

    Hand-built rather than rendered: this suite is about reading the Producer,
    and building one by hand is the only way to assert on a Word-produced PDF
    from a host that has no Word.
    """
    if producer_hex is not None:
        producer = b"/Producer<" + producer_hex + b">"
    elif producer_literal is not None:
        producer = b"/Producer (" + producer_literal + b")"
    else:
        producer = b""
    body = (b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"3 0 obj<<" + producer + b">>endobj\n"
            b"trailer<</Root 1 0 R/Info 3 0 R>>\n%%EOF\n")
    return body


def _write(tmp_path, name, blob):
    path = tmp_path / name
    path.write_bytes(blob)
    return str(path)


@pytest.mark.parametrize("producer,expected", [
    ("Microsoft® Word for Microsoft 365", "word"),
    ("Microsoft Word 2016", "word"),
    ("LibreOffice 26.2.5.2 (X86_64)", "libreoffice"),
    ("OpenOffice 4.1.14", "libreoffice"),
    ("Skia/PDF m120", "other"),
    ("", "unknown"),
    ("   ", "unknown"),
    (None, "unknown"),
])
def test_classify_producer_has_four_answers_and_unknown_is_not_word(producer, expected):
    assert render_engine.classify_producer(producer) == expected


def test_pdf_producer_reads_a_literal_string(tmp_path):
    path = _write(tmp_path, "word.pdf",
                  _minimal_pdf(producer_literal=b"Microsoft\xae Word for Microsoft 365"))
    assert render_engine.classify_producer(render_engine.pdf_producer(path)) == "word"


def test_pdf_producer_reads_a_utf16_hex_string(tmp_path):
    """LibreOffice writes /Producer<FEFF...> - hex, UTF-16BE, BOM first."""
    text = "LibreOffice 26.2.5.2 (X86_64)"
    blob = _minimal_pdf(producer_hex=(b"FEFF" + text.encode("utf-16-be").hex().upper().encode()))
    path = _write(tmp_path, "lo.pdf", blob)
    assert render_engine.pdf_producer(path) == text
    assert render_engine.classify_producer(render_engine.pdf_producer(path)) == "libreoffice"


def test_a_pdf_with_no_producer_is_unknown_not_word(tmp_path):
    path = _write(tmp_path, "bare.pdf", _minimal_pdf())
    assert render_engine.pdf_producer(path) is None
    assert render_engine.classify_producer(render_engine.pdf_producer(path)) == "unknown"


def test_an_unreadable_file_is_unknown_not_word(tmp_path):
    assert render_engine.pdf_producer(str(tmp_path / "absent.pdf")) is None


# -- the engine is chosen, never fallen back into ------------------------------

def test_explicit_renderer_always_wins_and_says_so():
    for name in render_engine.ENGINES:
        engine, why = render_engine.choose_engine(name)
        assert engine == name
        assert "explicit" in why


def test_unknown_renderer_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        render_engine.choose_engine("pandoc")


def test_default_engine_is_a_platform_branch_with_its_reason(monkeypatch):
    monkeypatch.setattr(render_engine.sys, "platform", "linux")
    engine, why = render_engine.choose_engine(None)
    assert engine == render_engine.LIBREOFFICE
    assert "only renderer" in why
    monkeypatch.setattr(render_engine.sys, "platform", "win32")
    engine, why = render_engine.choose_engine(None)
    assert engine == render_engine.WORD
    assert "reference renderer" in why


def test_every_converted_file_is_labelled_with_its_engine():
    assert "Microsoft Word" in render_engine.engine_label(render_engine.WORD)
    label = render_engine.engine_label(render_engine.LIBREOFFICE, "LibreOffice 26.2.5.2")
    assert "NOT Microsoft Word" in label
    assert "fidelity is reduced" in label


def test_word_renderer_on_a_non_windows_host_refuses_instead_of_substituting(tmp_path):
    """--renderer word off Windows must stop, not quietly use LibreOffice."""
    src = tmp_path / "doc.html"
    src.write_text("<html><body>x</body></html>", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_report.py"), "--help"],
                       capture_output=True, text=True, check=False, cwd=SCRIPTS)
    assert "--renderer" in r.stdout
    if sys.platform == "win32":
        pytest.skip("this host has Word as its reference renderer")
    sys.path.insert(0, SCRIPTS)
    import build_report  # pylint: disable=import-outside-toplevel
    assert build_report.convert(str(src), want_pdf=True, renderer="word") != 0
    assert not (tmp_path / "doc.pdf").exists()


# -- Gate 2's third value ------------------------------------------------------

# A page raster big enough to hold the bbox below with room for BAND either side.
CANVAS_W, CANVAS_H = 600, 500
BBOX = (10.0, 10.0, 110.0, 90.0)          # PDF points, as page.get_image_info reports
EDGES = ("top", "bottom", "left", "right")

# Basename -> list of edge-tuples, one per page. Set per test; the fixture clears
# it. A basename absent from here means a document with no pages at all, which is
# the provenance-only stub.
PAGES = {}


class _PixelPage:
    """One page carrying one image, rastered for real.

    `_ink_mask` runs `Image.frombytes` and numpy over `samples`, and `_coverage`
    measures the result, so both run against the installed Pillow and numpy
    rather than being skipped. The stroke colour is read from
    `verify_borders.IMAGE_BORDER_RED` at call time, which `main` has already set
    from the brand pack - so this keeps working if a pack changes its colour.
    """

    def __init__(self, edges):
        self.edges = tuple(edges)

    def get_image_info(self):
        return [{"bbox": BBOX}]

    def get_pixmap(self, dpi=None):          # noqa: ARG002 - matches PyMuPDF's signature
        import numpy as np                   # pylint: disable=import-outside-toplevel
        import verify_borders as vb          # pylint: disable=import-outside-toplevel
        a = np.full((CANVAS_H, CANVAS_W, 3), 255, dtype=np.uint8)
        ink = vb._target_rgb()               # pylint: disable=protected-access
        s = vb.SCALE
        x0, y0 = int(BBOX[0] * s), int(BBOX[1] * s)
        x1, y1 = int(BBOX[2] * s), int(BBOX[3] * s)
        for name in self.edges:
            if name == "top":
                a[y0 - 1:y0 + 2, x0:x1 + 1] = ink
            elif name == "bottom":
                a[y1 - 1:y1 + 2, x0:x1 + 1] = ink
            elif name == "left":
                a[y0:y1 + 1, x0 - 1:x0 + 2] = ink
            elif name == "right":
                a[y0:y1 + 1, x1 - 1:x1 + 2] = ink
        return types.SimpleNamespace(width=CANVAS_W, height=CANVAS_H, samples=a.tobytes())


class _StubDoc:
    """The stand-in for `pymupdf.open`.

    Metadata is empty on purpose, so `render_source` must fall back to the stdlib
    Producer scan of the real file on disk. Pages come from PAGES; with no entry
    the document has none, which is the shape every provenance test wants. A
    basename containing "broken" raises, because "this PDF could not be read" is
    its own outcome and the verdict block has to keep reporting it alongside the
    others.
    """
    metadata = {}

    def __init__(self, path):
        name = os.path.basename(path)
        if "broken" in name:
            raise RuntimeError("not a PDF: cannot open broken file")
        self._pages = [_PixelPage(e) for e in PAGES.get(name, [])]
        self.page_count = len(self._pages)

    def __getitem__(self, i):
        return self._pages[i]


# -- a matching .docx, hand-built so no writer library is needed ---------------

_DOCX_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
_DOCX_CT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/></Types>')
_DOCX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>')


def _write_docx(path, bordered=0, plain=0):
    """A .docx declaring `bordered` outlined inline pictures. Zip-built by hand.

    `_expected_bordered_count` only needs `wp:inline` elements whose XML contains
    `<a:ln`, so this is the smallest package python-docx will open. Building it
    by hand keeps the WRITE side free of python-docx; reading it still needs it,
    which is what the cross-check needs anyway.
    """
    import zipfile  # pylint: disable=import-outside-toplevel

    def inline(has_border):
        ln = ('<a:ln w="9525"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></a:ln>'
              if has_border else "")
        return ('<w:p><w:r><w:drawing><wp:inline><a:graphic><a:graphicData>'
                f'<pic:pic><pic:spPr>{ln}</pic:spPr></pic:pic>'
                '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')

    body = "".join(inline(True) for _ in range(bordered)) + \
           "".join(inline(False) for _ in range(plain))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {_DOCX_NS}><w:body>{body}<w:p/></w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _DOCX_CT)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/document.xml", document)
    return str(path)


def _sibling_docx(pdf_path, bordered=0, plain=0):
    return _write_docx(os.path.splitext(pdf_path)[0] + ".docx", bordered, plain)


@pytest.fixture(name="verify_borders")
def _verify_borders(monkeypatch):
    stub = types.ModuleType("pymupdf")
    stub.open = _StubDoc
    monkeypatch.setitem(sys.modules, "pymupdf", stub)
    sys.modules.pop("verify_borders", None)
    PAGES.clear()
    import verify_borders as vb  # pylint: disable=import-outside-toplevel
    yield vb
    PAGES.clear()
    sys.modules.pop("verify_borders", None)


def _run_gate2(verify_borders, monkeypatch, capsys, path):
    monkeypatch.setattr(sys, "argv", ["verify_borders.py", path, "--brand", "neutral"])
    code = verify_borders.main()
    return code, capsys.readouterr().out


def test_libreoffice_pdf_is_unavailable_not_pass(verify_borders, monkeypatch, capsys, tmp_path):
    text = "LibreOffice 26.2.5.2 (X86_64)"
    path = _write(tmp_path, "sop.pdf",
                  _minimal_pdf(producer_hex=b"FEFF" + text.encode("utf-16-be").hex().upper().encode()))
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 3, out
    assert "UNAVL" in out
    assert "Gate 2 DID NOT RUN" in out
    assert "Gate 2 result: UNAVAILABLE" in out
    assert "not a pass" in out.lower()
    assert "Gate 2 result: PASS" not in out
    assert "ADVISORY" in out


def test_a_producerless_pdf_is_unavailable_not_pass(verify_borders, monkeypatch, capsys, tmp_path):
    """Could-not-tell survives as its own value. It must not read as Word."""
    path = _write(tmp_path, "mystery.pdf", _minimal_pdf())
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 3, out
    assert "could not be determined" in out
    assert "Gate 2 result: PASS" not in out


def _word_pdf(tmp_path, name="word.pdf"):
    return _write(tmp_path, name,
                  _minimal_pdf(producer_literal=b"Microsoft\xae Word for Microsoft 365"))


def test_a_word_rendered_pdf_runs_the_gate_and_passes(verify_borders, monkeypatch, capsys, tmp_path):
    pytest.importorskip("docx")
    path = _word_pdf(tmp_path)
    _sibling_docx(path, bordered=0)
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 0, out
    assert "Gate 2 result: PASS" in out
    assert "UNAVL" not in out


def test_one_unavailable_among_passes_still_fails_the_run(verify_borders, monkeypatch, capsys, tmp_path):
    """A mixed run must not round up to green - the third value survives."""
    pytest.importorskip("docx")
    good = _word_pdf(tmp_path)
    _sibling_docx(good, bordered=0)
    bad = _write(tmp_path, "lo.pdf", _minimal_pdf(producer_literal=b"LibreOffice 26.2.5.2"))
    _sibling_docx(bad, bordered=0)
    monkeypatch.setattr(sys, "argv", ["verify_borders.py", good, bad, "--brand", "neutral"])
    code = verify_borders.main()
    out = capsys.readouterr().out
    assert code == 3, out
    assert "Gate 2 result: UNAVAILABLE for 1 of 2" in out


# -- Gate 2's OTHER way of not running: the .docx cross-check ------------------
#
# BLOCK found by QA 2026-09-22. `_expected_bordered_count` swallowed every
# exception and returned None, so "the cross-check did not run" and "the
# cross-check found nothing wrong" were one value, and a PDF with no sibling
# .docx printed `Gate 2 result: PASS` and exited 0 on a measurement that never
# happened.

def test_a_pdf_with_no_sibling_docx_is_unavailable_not_pass(verify_borders, monkeypatch,
                                                            capsys, tmp_path):
    path = _word_pdf(tmp_path)
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 3, out
    assert "Gate 2 DID NOT RUN - no .docx cross-check" in out
    assert "there is no word.docx beside the PDF" in out
    assert "Gate 2 result: PASS" not in out
    assert "ADVISORY" in out


def test_python_docx_absent_makes_the_crosscheck_unavailable(verify_borders, monkeypatch,
                                                             capsys, tmp_path):
    """The package that reads the .docx is one of the things that can be missing."""
    pytest.importorskip("docx")
    path = _word_pdf(tmp_path)
    _sibling_docx(path, bordered=0)
    monkeypatch.setitem(sys.modules, "docx", None)      # `import docx` now raises
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 3, out
    assert "python-docx is not installed" in out
    assert "Gate 2 result: PASS" not in out


def test_a_corrupt_sibling_docx_is_unavailable_not_pass(verify_borders, monkeypatch,
                                                        capsys, tmp_path):
    pytest.importorskip("docx")
    path = _word_pdf(tmp_path)
    (tmp_path / "word.docx").write_bytes(b"this is not a zip")
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 3, out
    assert "could not be read" in out
    assert "Gate 2 result: PASS" not in out


# -- the pixel half, measured rather than skipped ------------------------------

def test_a_fully_bordered_screenshot_passes_on_a_real_pixel_sweep(verify_borders, monkeypatch,
                                                                  capsys, tmp_path):
    """_ink_mask and _coverage run for real here; `missing` is genuinely 0."""
    pytest.importorskip("docx")
    path = _word_pdf(tmp_path)
    _sibling_docx(path, bordered=1)
    PAGES["word.pdf"] = [EDGES]
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 0, out
    assert "PASS " in out
    assert "1 bordered screenshot(s), 0 edge(s) clipped" in out


def test_a_clipped_top_edge_is_a_real_fail(verify_borders, monkeypatch, capsys, tmp_path):
    """The defect Gate 2 exists for: three edges painted, the top one gone.

    Non-zero `missing` from a real measurement, and the FAIL path returns 1 -
    neither of which any test here reached before 2026-09-22.
    """
    pytest.importorskip("docx")
    path = _word_pdf(tmp_path)
    _sibling_docx(path, bordered=1)
    PAGES["word.pdf"] = [("bottom", "left", "right")]
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 1, out
    assert "FAIL " in out
    assert "1 edge(s) clipped" in out
    assert "top CLIPPED" in out
    assert "Gate 2 result: FAIL" in out


def test_a_screenshot_that_lost_all_four_edges_is_caught_by_the_docx_count(
        verify_borders, monkeypatch, capsys, tmp_path):
    """No ink at all reads as `unbordered`. Only the .docx knows better."""
    pytest.importorskip("docx")
    path = _word_pdf(tmp_path)
    _sibling_docx(path, bordered=1)
    PAGES["word.pdf"] = [()]
    code, out = _run_gate2(verify_borders, monkeypatch, capsys, path)
    assert code == 1, out
    assert "docx declares 1 bordered screenshot(s), 0 found in the PDF" in out


# -- the verdict reports every outcome, and the code carries the sharpest ------
#
# `if errored: return 2` used to be evaluated before `if failed: return 1`, so a
# real border failure alongside one unreadable PDF said ERROR and exited 2, and
# any run that errored at all suppressed the UNAVAILABLE line entirely.

def test_a_real_failure_and_an_unreadable_pdf_report_both_and_exit_1(
        verify_borders, monkeypatch, capsys, tmp_path):
    pytest.importorskip("docx")
    bad = _word_pdf(tmp_path)
    _sibling_docx(bad, bordered=1)
    PAGES["word.pdf"] = [("bottom", "left", "right")]
    broken = _write(tmp_path, "broken.pdf", b"not a pdf at all")
    monkeypatch.setattr(sys, "argv", ["verify_borders.py", bad, broken, "--brand", "neutral"])
    code = verify_borders.main()
    out = capsys.readouterr().out
    assert code == 1, out
    assert "Gate 2 result: FAIL" in out
    assert "Gate 2 result: ERROR" in out


def test_an_unreadable_pdf_does_not_suppress_the_unavailable_verdict(
        verify_borders, monkeypatch, capsys, tmp_path):
    lo = _write(tmp_path, "lo.pdf", _minimal_pdf(producer_literal=b"LibreOffice 26.2.5.2"))
    broken = _write(tmp_path, "broken.pdf", b"not a pdf at all")
    monkeypatch.setattr(sys, "argv", ["verify_borders.py", lo, broken, "--brand", "neutral"])
    code = verify_borders.main()
    out = capsys.readouterr().out
    assert code == 2, out
    assert "Gate 2 result: ERROR" in out
    assert "Gate 2 result: UNAVAILABLE" in out


# -- soffice that is absent, or that exits 0 having written nothing ------------

def test_absent_soffice_is_reported_not_worked_around(monkeypatch, capsys, tmp_path):
    src = tmp_path / "doc.html"
    src.write_text("<html><body>x</body></html>", encoding="utf-8")
    monkeypatch.setattr(render_engine, "soffice_exe", lambda: None)
    assert render_engine.to_soffice(str(src), want_pdf=True) == 1
    err = capsys.readouterr().err
    assert "not installed or not on PATH" in err
    assert "apt install libreoffice-writer" in err
    assert not (tmp_path / "doc.pdf").exists()


def test_a_converter_that_exits_zero_having_written_nothing_is_a_failure(tmp_path):
    """soffice exits 0 on a locked profile. The exit code alone is not the check."""
    target = str(tmp_path / "out.pdf")
    assert render_engine._conversion_problem(target, -1.0) == "no output file was written"
    with open(target, "wb"):
        pass
    assert render_engine._conversion_problem(target, -1.0) == "the output file is zero bytes"
    with open(target, "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    stale = os.path.getmtime(target)
    assert render_engine._conversion_problem(target, stale) == "the existing output file was not replaced"
    assert render_engine._conversion_problem(target, stale - 1) is None
# -- both engines honour "a conversion that exits 0 produced a file" -----------
#
# SKILL.md states that rule flatly. Until 2026-09-22 `build_report.to_word`
# returned 0 without looking at the file, so the rule held on the LibreOffice
# side only - and a rule that holds on one engine is not a rule. Word is driven
# through a fake COM layer here because the real one exists only on Windows;
# what is under test is to_word's own bookkeeping, not Word.

def _fake_win32com(save_impl):
    """A `win32com.client` whose Word saves whatever `save_impl` decides to."""
    package = types.ModuleType("win32com")
    client = types.ModuleType("win32com.client")

    class _Doc:
        @staticmethod
        def SaveAs2(path, fmt):
            save_impl(path, fmt)

        @staticmethod
        def Close(_save_changes):
            return None

    class _Documents:
        @staticmethod
        def Open(_path, *_a):
            return _Doc()

    class _App:
        Visible = True
        DisplayAlerts = 1
        Documents = _Documents()

        @staticmethod
        def Quit():
            return None

    client.Dispatch = lambda _progid: _App()
    package.client = client
    return package, client


@pytest.fixture(name="build_report")
def _build_report():
    sys.path.insert(0, SCRIPTS)
    import build_report as br  # pylint: disable=import-outside-toplevel
    return br


def _with_fake_word(monkeypatch, save_impl):
    package, client = _fake_win32com(save_impl)
    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)


def test_word_saving_nothing_is_a_failed_conversion(build_report, monkeypatch, capsys, tmp_path):
    """SaveAs2 returning without writing must not come back as exit 0."""
    _with_fake_word(monkeypatch, lambda path, fmt: None)
    src = tmp_path / "doc.html"
    src.write_text("<html><body>x</body></html>", encoding="utf-8")
    rc = build_report.to_word(str(src), want_docx=False, want_pdf=True)
    err = capsys.readouterr().err
    assert rc == 1
    assert "no output file was written" in err
    assert "not a success" in err


def test_word_leaving_yesterdays_file_in_place_is_a_failed_conversion(
        build_report, monkeypatch, capsys, tmp_path):
    """The neighbouring case: the target exists and SaveAs2 does not replace it."""
    _with_fake_word(monkeypatch, lambda path, fmt: None)
    src = tmp_path / "doc.html"
    src.write_text("<html><body>x</body></html>", encoding="utf-8")
    stale = tmp_path / "doc.pdf"
    stale.write_bytes(b"%PDF-1.4 yesterday\n")
    os.utime(stale, (1_000_000, 1_000_000))
    rc = build_report.to_word(str(src), want_docx=False, want_pdf=True)
    err = capsys.readouterr().err
    assert rc == 1
    assert "the existing output file was not replaced" in err


def test_word_that_really_writes_reports_success_and_names_the_engine(
        build_report, monkeypatch, capsys, tmp_path):
    _with_fake_word(monkeypatch, lambda path, fmt: open(path, "wb").write(b"%PDF-1.4\n"))
    src = tmp_path / "doc.html"
    src.write_text("<html><body>x</body></html>", encoding="utf-8")
    rc = build_report.to_word(str(src), want_docx=False, want_pdf=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "wrote " in out
    assert "Microsoft Word (COM)" in out


# -- render_engine.py's own CLI says could-not-tell in its exit code -----------
#
# toolchain-usage.md advertises `python3 render_engine.py some.pdf` as "what
# actually rendered an existing PDF". It returned 0 unconditionally, so
# `render_engine.py /nonexistent.pdf && ...` ran the right-hand side.

def test_render_engine_cli_exits_2_on_a_pdf_it_cannot_read(capsys, tmp_path):
    rc = render_engine.main([str(tmp_path / "absent.pdf")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "CANNOT READ" in err


def test_render_engine_cli_exits_3_when_the_producer_is_unknown(capsys, tmp_path):
    path = _write(tmp_path, "bare.pdf", _minimal_pdf())
    rc = render_engine.main([path])
    captured = capsys.readouterr()
    assert rc == 3
    assert "could not be determined" in captured.err
    assert "unknown" in captured.out


def test_render_engine_cli_exits_0_when_the_producer_is_determined(capsys, tmp_path):
    path = _write(tmp_path, "lo.pdf", _minimal_pdf(producer_literal=b"LibreOffice 26.2.5.2"))
    assert render_engine.main([path]) == 0
    assert "libreoffice" in capsys.readouterr().out


def test_render_engine_cli_with_no_pdfs_is_a_capability_report(capsys):
    assert render_engine.main([]) == 0
    assert "engine   :" in capsys.readouterr().out


# -- LibreOffice is handed documents this skill did not generate ---------------

def test_the_soffice_profile_is_seeded_with_the_restrictions(tmp_path):
    written = render_engine.harden_profile(str(tmp_path))
    assert written.endswith(os.path.join("user", "registrymodifications.xcu"))
    text = open(written, encoding="utf-8").read()
    assert os.path.getsize(written) > 0
    for _, name, _ in render_engine._HARDENING:  # pylint: disable=protected-access
        assert f'oor:name="{name}"' in text
    assert "BlockUntrustedRefererLinks" in text
    assert "<value>3</value>" in text          # macro security: Very High
    assert "\r\n" not in open(written, newline="", encoding="utf-8").read()


@pytest.mark.skipif(render_engine.soffice_exe() is None, reason="LibreOffice is not installed")
def test_a_remote_reference_is_not_fetched_during_conversion(tmp_path):
    """The security fix, measured the way it was found.

    Two real conversions of the same HTML, which carries an <img> pointing at a
    loopback HTTP server. The CONTROL runs soffice with a bare profile and must
    hit that server - without it this test would pass on a machine where nothing
    could reach the network anyway, which is a green light that proves nothing.
    Slow (two soffice starts, a few seconds each) and worth it.
    """
    import http.server            # pylint: disable=import-outside-toplevel
    import pathlib                # pylint: disable=import-outside-toplevel
    import socketserver          # pylint: disable=import-outside-toplevel
    import threading              # pylint: disable=import-outside-toplevel

    hits = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):        # noqa: N802 - the name BaseHTTPRequestHandler dispatches to
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_a):
            return None

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        src = tmp_path / "remote.html"
        src.write_text(f'<html><body><p>hello</p>'
                       f'<img src="http://127.0.0.1:{port}/beacon.png" width="50" height="50">'
                       f'</body></html>', encoding="utf-8")

        control_profile = tmp_path / "bare-profile"
        control_out = tmp_path / "control"
        control_out.mkdir()
        subprocess.run([render_engine.soffice_exe(),
                        "-env:UserInstallation=" + pathlib.Path(control_profile).absolute().as_uri(),
                        "--headless", "--norestore", "--convert-to", "pdf",
                        "--outdir", str(control_out), str(src)],
                       capture_output=True, text=True, timeout=600, check=False)
        assert hits, ("the control conversion did not fetch the remote image, so this test "
                      "cannot tell a working restriction from a machine with no network")

        hits.clear()
        assert render_engine.to_soffice(str(src), want_pdf=True, quiet=True) == 0
        assert (tmp_path / "remote.pdf").exists()
        assert hits == [], f"soffice fetched {hits} while converting a hardened profile"
    finally:
        server.shutdown()
        server.server_close()


# -- preflight reports Gate 2 on everything Gate 2 needs ----------------------
#
# BLOCK found by QA 2026-09-22: Gate 2 was reported AVAILABLE on the strength of
# Word alone, while the section six lines above printed `MISSING PyMuPDF`.
# verify_borders.py would have died at `import pymupdf` and exited 1, which its
# own exit table defines as "at least one FAILed".

@pytest.fixture(name="preflight")
def _preflight():
    sys.path.insert(0, SCRIPTS)
    import preflight as pf  # pylint: disable=import-outside-toplevel
    return pf


def _gate2_section(out):
    assert "== Gate 2" in out, out
    return out.split("== Gate 2", 1)[1]


def _all_packages_ok(_python, _import_name, pip_name):
    return True, f"{pip_name} 9.9.9"


def test_preflight_reports_gate2_unavailable_when_pymupdf_is_missing(
        preflight, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "word_installed", lambda: (True, "Word 16.0 (sim)"))
    monkeypatch.setattr(render_engine, "soffice_version", lambda exe=None: "LibreOffice 26.2.5.2")
    monkeypatch.setattr(preflight, "probe",
                        lambda py, imp, pip: (False, "ModuleNotFoundError: pymupdf")
                        if pip == "PyMuPDF" else _all_packages_ok(py, imp, pip))
    rc = preflight.main([])
    gate2 = _gate2_section(capsys.readouterr().out)
    assert "UNAVAILABLE" in gate2
    assert "PyMuPDF" in gate2
    assert "Word can render the PDF this gate measures" not in gate2
    assert rc != 0


def test_preflight_reports_gate2_available_only_with_word_and_every_package(
        preflight, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "word_installed", lambda: (True, "Word 16.0 (sim)"))
    monkeypatch.setattr(render_engine, "soffice_version", lambda exe=None: "LibreOffice 26.2.5.2")
    monkeypatch.setattr(preflight, "probe", _all_packages_ok)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert "AVAILABLE    Word can render the PDF this gate measures" in _gate2_section(out)
    assert rc == 0
    assert "Ready." in out


def test_a_provisioned_non_windows_host_is_ready_and_still_says_gate2_cannot_run(
        preflight, monkeypatch, capsys):
    """Exit 0 has to be REACHABLE where Word cannot exist.

    On Linux `word_installed()` is always False, so the Gate 2 branch set rc=1
    unconditionally: a host with LibreOffice and every package installed printed
    "Not ready" and exited 1, and "exit 0 = ready" was unreachable on the one
    platform this change was written to support. The unknown still has to
    survive - into the closing line, which says in words what the 0 does not.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(preflight, "word_installed", lambda: (False, "not Windows"))
    monkeypatch.setattr(render_engine, "soffice_version", lambda exe=None: "LibreOffice 26.2.5.2")
    monkeypatch.setattr(preflight, "probe", _all_packages_ok)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Not ready" not in out
    assert "UNAVAILABLE" in _gate2_section(out)
    assert "is PERMANENT" in out
    assert "it does not mean Gate 2 passed" in out


def test_windows_without_word_is_still_not_ready(preflight, monkeypatch, capsys):
    """The neighbouring case. Absent Word IS fixable on Windows, so it is a fault."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(preflight, "word_installed",
                        lambda: (False, "Word.Application is not registered for COM"))
    monkeypatch.setattr(render_engine, "soffice_version", lambda exe=None: "LibreOffice 26.2.5.2")
    monkeypatch.setattr(preflight, "probe", _all_packages_ok)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "Not ready" in out
    assert "is PERMANENT" not in out
