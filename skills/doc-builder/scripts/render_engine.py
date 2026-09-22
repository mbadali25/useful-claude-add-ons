#!/usr/bin/env python3
"""Which program renders doc-builder's .docx / .pdf, and how that answer is labelled.

Two engines can do it, they are not equivalent, and the difference has to stay
visible on every artifact and in every line derived from one:

  word         Microsoft Word, driven over COM (Windows only, pywin32). The
               REFERENCE renderer -- every rule in references/word-traps.md was
               measured against it.
  libreoffice  `soffice --headless --convert-to`. The only engine that exists on
               Linux and macOS, because Microsoft ships no Word desktop app for
               Linux at all. Fidelity is reduced, measurably: LIBREOFFICE_FIDELITY.

The rule this module exists to enforce, and the reason the skill used to refuse
LibreOffice outright: the engine is a DELIBERATE choice and the output names it.
A LibreOffice render nobody labelled is worse than no render, because the reader
believes Word produced it and the differences below are invisible to them. What
was banned is the SILENT, UNLABELLED substitution - not LibreOffice.

The third value. Anything asking "did Word render this?" has three answers, not
two: yes, no, and could-not-tell. `classify_producer` returns all three and
callers must never fold the last two into a pass. Gate 2 (verify_borders.py) is
the one that matters: it asks whether WORD clips a screenshot border, and no
LibreOffice render can answer that question in either direction.

Stdlib only, on purpose. preflight.py imports it before anything is installed,
and `pdf_producer` has to work on a machine with no PyMuPDF.

TWO LIMITS, stated here because both were once written down as guarantees they
are not.

1. LibreOffice is run RESTRICTED, which is not sandboxed. Its HTML and OOXML
   importers resolve external references by design: a remote `<img>` is fetched
   while the document converts, which both leaks that the document was rendered
   and pulls whatever answers into the output. `to_soffice` therefore seeds its
   throwaway profile (`harden_profile`) before soffice starts - macro execution
   off, macro security Very High, active content off, untrusted referer links
   blocked. Measured 2026-09-22, LibreOffice 26.2.5.2 on Ubuntu 26.04: an HTML
   carrying `<img src="http://127.0.0.1:PORT/beacon.png">` hits that server on an
   unseeded profile and does not on a seeded one; seeding ONLY
   `BlockUntrustedRefererLinks` reproduces the block, and the other three
   together do not. `--safe-mode` is deliberately NOT passed - it discards the
   user profile, which is exactly where these settings live. Nothing here
   restricts what LibreOffice may read from the local filesystem.

2. The /Producer check is ADVISORY. `classify_producer` reads a string the PDF
   declares about itself, and a text editor turns "LibreOffice" into "Microsoft
   Word" in one edit. It defeats ACCIDENT - converting with the wrong engine and
   forgetting, which is the failure that actually happens here - and it does not
   defeat intent. A sidecar naming the engine `to_soffice` really invoked was
   considered and rejected: it would be a file beside the PDF, no less editable
   than the PDF, and requiring one would report every Word render made outside
   this skill as UNAVAILABLE. So do not describe Gate 2 as a gate that cannot
   skip itself; it is a gate that cannot skip itself BY ACCIDENT.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

WORD = "word"
LIBREOFFICE = "libreoffice"
ENGINES = (WORD, LIBREOFFICE)

# Printed to stderr before any LibreOffice conversion, and quoted in SKILL.md.
# Specific on purpose: "fidelity may differ" tells a reader nothing they can act
# on. Measured 2026-09-22, LibreOffice 26.2.5.2 on Ubuntu 26.04.
LIBREOFFICE_FIDELITY = (
    "LibreOffice is not Word. On the REPORT (HTML) path its importer applies only SIMPLE\n"
    "  selectors - a bare `.class` or a bare element. Every compound or descendant selector is\n"
    "  dropped silently, which costs the table grid, the navy header shading, the zebra rows,\n"
    "  the summary-card panels and the meta-table key shading. The masthead, the lede, the\n"
    "  handling banner and every severity chip (bare classes) DO render. On the SOP path the\n"
    "  input is real OOXML rather than HTML, so far more survives - but nothing here is\n"
    "  evidence about how Word lays the same document out. See references/word-traps.md,\n"
    "  \"What LibreOffice silently drops\"."
)

# Windows and macOS put soffice somewhere PATH does not reach.
_SOFFICE_FALLBACKS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)

# --convert-to values. The filter is named explicitly rather than left to
# LibreOffice's guess, so the .docx is always the OOXML one Word opens.
_FILTERS = {"docx": "docx:MS Word 2007 XML", "pdf": "pdf"}

# Seeded into the throwaway user profile before soffice starts. Every name and
# path below was checked against the schema this machine ships
# (/usr/lib/libreoffice/share/registry/main.xcd); see limit 1 in the module
# docstring for what was measured.
_HARDENING = (
    ("/org.openoffice.Office.Common/Security/Scripting", "MacroSecurityLevel", "3"),
    ("/org.openoffice.Office.Common/Security/Scripting", "DisableMacrosExecution", "true"),
    ("/org.openoffice.Office.Common/Security/Scripting", "DisableActiveContent", "true"),
    ("/org.openoffice.Office.Common/Security/Scripting", "BlockUntrustedRefererLinks", "true"),
    ("/org.openoffice.Office.Writer/Content/Update", "Field", "false"),
)

# NOT set, on purpose: /org.openoffice.Office.Writer/Content/Update `Link`. It is
# an int whose schema label reads "Always/On request/Never" without saying which
# integer is which, and the default is 1. Converting a document with a linked
# section under each of 0, 1 and 2 resolved the link in none of them, so that
# experiment could not pin the order down - and writing an unverified integer
# here could turn link updating ON rather than off. `BlockUntrustedRefererLinks`
# is the item that was measured to stop the fetch; this one would be belt to its
# braces, and a guessed belt is worse than none.


def _hardening_xcu():
    """The `registrymodifications.xcu` text seeded into a fresh soffice profile."""
    rows = "".join(
        f'  <item oor:path="{path}"><prop oor:name="{name}" oor:op="fuse">'
        f"<value>{value}</value></prop></item>\n"
        for path, name, value in _HARDENING)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry"\n'
            '           xmlns:xs="http://www.w3.org/2001/XMLSchema"\n'
            '           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            f"{rows}</oor:items>\n")


def harden_profile(profile_dir):
    """Write `_HARDENING` into `profile_dir` so soffice reads it on first start.

    Returns the path written. The whole text is computed into a variable BEFORE
    the file is opened: `open(p, "w")` truncates at open time, so a write whose
    argument expression raises leaves a zero-byte file - and a zero-byte
    `registrymodifications.xcu` is a profile carrying no restrictions at all,
    which is the one failure mode this function must not have.
    """
    text = _hardening_xcu()
    user_dir = os.path.join(profile_dir, "user")
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, "registrymodifications.xcu")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def soffice_exe():
    """Absolute path to soffice, or None. PATH first, then the known install dirs."""
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for cand in _SOFFICE_FALLBACKS:
        if os.path.isfile(cand):
            return cand
    return None


def soffice_version(exe=None):
    """`LibreOffice 26.2.5.2 (X86_64)`-style version text, or None if it will not run.

    Runs the binary rather than reading a registry key: a soffice on PATH that
    cannot start is not an available renderer, and reporting it as one is how a
    preflight comes out green on a machine that cannot convert anything.
    """
    exe = exe or soffice_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return (r.stdout.strip().splitlines() or [""])[0].strip() or None


def engine_label(engine, detail=None):
    """The exact words printed beside every file this skill converts."""
    if engine == WORD:
        return "Microsoft Word (COM)" + (f" {detail}" if detail else "")
    if engine == LIBREOFFICE:
        return (f"{detail or 'LibreOffice'} (soffice) - NOT Microsoft Word, "
                "layout fidelity is reduced")
    return str(engine)


def choose_engine(requested=None):
    """(engine, why). Never guesses, and never substitutes when one fails.

    `requested` is --renderer, or None. With None the answer comes from an
    EXPLICIT platform branch, not from trying Word and catching the error:
    outside Windows, Microsoft ships no Word desktop app, so LibreOffice there
    is not a fallback - it is the only renderer that exists. On Windows the
    answer is Word, and if Word cannot run the caller stops and says so rather
    than quietly converting with something else.
    """
    if requested:
        if requested not in ENGINES:
            raise ValueError(f"unknown renderer {requested!r}; choose one of {', '.join(ENGINES)}")
        return requested, f"--renderer {requested} (explicit)"
    if sys.platform == "win32":
        return WORD, ("no --renderer given; this is Windows, where Word is the reference "
                      "renderer. Pass --renderer libreoffice to override.")
    return LIBREOFFICE, (f"no --renderer given; this is {sys.platform}, where Microsoft ships no "
                         "Word desktop app, so LibreOffice is the only renderer there is.")


def _targets(src, want_docx, want_pdf):
    base = os.path.splitext(os.path.abspath(src))[0]
    out = []
    if want_docx:
        out.append(("docx", base + ".docx"))
    if want_pdf:
        out.append(("pdf", base + ".pdf"))
    return out


def to_soffice(src, want_docx=False, want_pdf=False, quiet=False):
    """Convert `src` next to itself with LibreOffice. Returns a process exit code.

    Every converted file is announced WITH the engine that made it. That naming
    is the whole point of routing through here rather than calling soffice
    inline.

    soffice exits 0 on failures it does not consider fatal - a locked user
    profile is the common one - so the exit code alone is not the check. Each
    target is confirmed to exist, be non-empty, and be NEWER than the moment the
    conversion started. A converter that exits 0 having written nothing, or
    having left yesterday's file in place, is the failure this guards.
    `build_report.to_word` applies the same three checks to the Word side, so
    "a conversion that exits 0 produced a file" holds on both engines or neither.

    soffice runs against a throwaway profile seeded by `harden_profile`, so a
    document this skill did not generate cannot make the importer fetch a remote
    reference. See limit 1 in the module docstring for what that does and does
    not cover.
    """
    exe = soffice_exe()
    if not exe:
        print("LibreOffice (soffice) is not installed or not on PATH - cannot convert. "
              "The source file was still written.\n"
              "  Debian/Ubuntu: sudo apt install libreoffice-writer\n"
              "  macOS:         brew install --cask libreoffice\n"
              "  Windows:       winget install TheDocumentFoundation.LibreOffice",
              file=sys.stderr)
        return 1
    version = soffice_version(exe)
    if not version:
        print(f"{exe} is present but `--version` did not run - it is not a usable renderer. "
              "Nothing was converted.", file=sys.stderr)
        return 1

    targets = _targets(src, want_docx, want_pdf)
    for _, target in targets:
        if os.path.abspath(target) == os.path.abspath(src):
            print(f"cannot convert: the output would overwrite the input ({target}).",
                  file=sys.stderr)
            return 1
        why = _locked(target)
        if why:
            print(f"cannot convert: {why}. Close {os.path.basename(target)} and run again.",
                  file=sys.stderr)
            return 1

    if not quiet:
        print(f"renderer : {engine_label(LIBREOFFICE, version)}\n  {LIBREOFFICE_FIDELITY}",
              file=sys.stderr)

    out_dir = os.path.dirname(os.path.abspath(src)) or "."
    # A private user profile, for two reasons. This host may run a live desktop
    # LibreOffice session, and a headless convert sharing that profile either
    # blocks on its lock or silently does nothing and still exits 0. And because
    # the profile is ours alone, it can be seeded with the restrictions in
    # `_HARDENING` without touching anything the operator uses interactively.
    profile = tempfile.mkdtemp(prefix="doc-builder-soffice-")
    try:
        harden_profile(profile)
        for kind, target in targets:
            before = os.path.getmtime(target) if os.path.exists(target) else -1.0
            cmd = [exe, "-env:UserInstallation=" + _file_uri(profile), "--headless",
                   "--norestore", "--convert-to", _FILTERS[kind], "--outdir", out_dir,
                   os.path.abspath(src)]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
            except subprocess.TimeoutExpired:
                print(f"soffice timed out converting to {kind}. Nothing written for {target}.",
                      file=sys.stderr)
                return 1
            problem = conversion_problem(target, before)
            if r.returncode != 0 or problem:
                print(f"soffice failed to produce {os.path.basename(target)}"
                      f" (exit {r.returncode:d}{'; ' + problem if problem else ''}).\n"
                      f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}", file=sys.stderr)
                return r.returncode or 1
            print(f"wrote {target}  [renderer: {engine_label(LIBREOFFICE, version)}]")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return 0


def conversion_problem(target, before_mtime):
    """Why `target` is not a freshly written file, or None.

    Public because BOTH engines have to answer this question with the same three
    checks. `build_report.to_word` calls it after every SaveAs2; a rule enforced
    on one engine is not a rule.
    """
    if not os.path.exists(target):
        return "no output file was written"
    if os.path.getsize(target) == 0:
        return "the output file is zero bytes"
    if os.path.getmtime(target) <= before_mtime:
        return "the existing output file was not replaced"
    return None


_conversion_problem = conversion_problem  # the pre-0.2 private name


def _file_uri(path):
    """file:// URI for a local directory, correct for a path containing spaces."""
    return pathlib.Path(path).absolute().as_uri()


def _locked(path):
    """preflight.locked(), imported late so preflight can import THIS module."""
    try:
        from preflight import locked  # pylint: disable=import-outside-toplevel,cyclic-import
    except ImportError:
        return None
    return locked(path)


# -- what rendered a PDF that already exists -----------------------------------

_WORD_PRODUCER = re.compile(r"microsoft.{0,3}\s*word|microsoft.{0,3}\s*office", re.I)
_LO_PRODUCER = re.compile(r"libreoffice|openoffice", re.I)


def classify_producer(producer):
    """'word' | 'libreoffice' | 'other' | 'unknown' - three real answers plus a name.

    `unknown` is a VALUE, not an error, and it is deliberately not merged into
    'other': a PDF whose Producer could not be read has not been shown to come
    from anything, and a Gate that treats "could not tell" as "not Word" is at
    least honest, while one that treats it as "Word" is the bug this whole
    module exists to prevent. Callers must refuse to pass on either.

    ADVISORY, not enforced: `producer` is what the PDF says about itself, and one
    byte of it decides this answer. See limit 2 in the module docstring - this
    stops the wrong engine sneaking through unnoticed, not an operator routing
    around their own gate.
    """
    if not producer or not str(producer).strip():
        return "unknown"
    text = str(producer)
    if _WORD_PRODUCER.search(text):
        return WORD
    if _LO_PRODUCER.search(text):
        return LIBREOFFICE
    return "other"


def pdf_producer(path):
    """The /Producer (else /Creator) string of a PDF, read with the stdlib alone.

    PyMuPDF does this properly and verify_borders.py prefers it; this exists so
    preflight and any machine without PyMuPDF can still answer the question.

    Returns None when the value cannot be read -- which includes a PDF that
    keeps its Info dictionary inside a compressed object stream, where a raw
    byte scan genuinely cannot see it. None means unknown, and unknown must not
    read as Word.
    """
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return None
    for key in (b"/Producer", b"/Creator"):
        for m in re.finditer(re.escape(key) + rb"\s*(\(|<)", blob):
            value = _pdf_string(blob, m.end() - 1)
            if value:
                return value
    return None


def _pdf_string(blob, start):
    """Decode the PDF string beginning at `start` -- literal `(...)` or hex `<...>`."""
    if blob[start:start + 1] == b"<":
        end = blob.find(b">", start)
        if end < 0:
            return None
        raw = re.sub(rb"[^0-9A-Fa-f]", b"", blob[start + 1:end])
        if len(raw) % 2:
            raw = raw[:-1]
        try:
            data = bytes.fromhex(raw.decode("ascii"))
        except ValueError:
            return None
        if data[:2] == b"\xfe\xff":
            return data[2:].decode("utf-16-be", "replace").strip("\x00").strip()
        return data.decode("latin-1", "replace").strip()
    depth, i, out = 0, start, bytearray()
    while i < len(blob):
        c = blob[i:i + 1]
        if c == b"\\":
            out += blob[i + 1:i + 2]
            i += 2
            continue
        if c == b"(":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif c == b")":
            depth -= 1
            if depth == 0:
                return out.decode("latin-1", "replace").strip()
        out += c
        i += 1
    return None


def add_renderer_argument(ap):
    """--renderer, worded the same way on every script that converts."""
    ap.add_argument("--renderer", choices=list(ENGINES), default=None,
                    help="which program converts the document: 'word' (Microsoft Word over "
                         "COM, Windows only, the reference renderer) or 'libreoffice' "
                         "(soffice --headless, reduced fidelity, the only option on Linux "
                         "and macOS). Default: word on Windows, libreoffice elsewhere - "
                         "stated on stderr every run, never a silent fallback")


def main(argv=None):
    """Report what this machine can render with, and what already rendered a PDF.

    Exit codes, because `toolchain-usage.md` advertises the PDF form as "what
    actually rendered an existing PDF" and anything shell-`&&`-ing it reads 0 as
    an answer:

      0  every named PDF was read AND its producer determined (word, libreoffice
         or other). With no PDFs named it is a capability report and always 0.
      2  a named PDF could not be read at all - missing, or not readable.
      3  a named PDF was read and its producer COULD NOT BE DETERMINED. That is
         the third value; folding it into 0 is the bug this module exists to
         prevent, and it was folded into 0 here until 2026-09-22.

    Highest code wins, and every line is still printed, so one unreadable file
    never hides what the others said.
    """
    import argparse  # pylint: disable=import-outside-toplevel
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_renderer_argument(ap)
    ap.add_argument("pdfs", nargs="*", help="PDFs to report the rendering engine of")
    args = ap.parse_args(argv)

    engine, why = choose_engine(args.renderer)
    print(f"engine   : {engine}\nwhy      : {why}")
    print(f"word     : {'available (COM)' if _word_com_available() else 'ABSENT'}")
    version = soffice_version()
    print(f"soffice  : {version or 'ABSENT'}")

    rc = 0
    for path in args.pdfs:
        unreadable = _unreadable(path)
        if unreadable:
            print(f"{os.path.basename(path)}: CANNOT READ - {unreadable}", file=sys.stderr)
            rc = max(rc, 2)
            continue
        producer = pdf_producer(path)
        kind = classify_producer(producer)
        print(f"{os.path.basename(path)}: producer={producer!r} -> {kind}")
        if kind == "unknown":
            print(f"{os.path.basename(path)}: the rendering program could not be determined. "
                  "That is not 'not Word' and not 'Word' - it is unknown.", file=sys.stderr)
            rc = max(rc, 3)
    return rc


def _unreadable(path):
    """Why `path` cannot be read as a file, or None. Distinguishes "no answer
    because the file is not there" from "read it, and it declares nothing"."""
    try:
        with open(path, "rb") as fh:
            fh.read(1)
    except OSError as exc:
        return f"{exc.strerror or exc}"
    return None


def _word_com_available():
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    try:
        import winreg  # pylint: disable=import-outside-toplevel
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Classes\Word.Application\CurVer"):
                    return True
            except OSError:
                continue
    except ImportError:
        return False
    return False


if __name__ == "__main__":
    sys.exit(main())
