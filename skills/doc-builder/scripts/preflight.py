#!/usr/bin/env python3
"""Preflight for doc-builder: find what is missing, install it under the user
profile after ONE confirmation, then prove it imports.

Run this before the first document on any machine, and again whenever a script
fails with ModuleNotFoundError:

    python3 preflight.py                   # report only; asks before installing anything
    python3 preflight.py --install         # install missing packages without the prompt
    python3 preflight.py --venv            # ...into a virtual environment this skill owns (.venv/)
    python3 preflight.py --target "/srv/masters/My SOP.pdf"  # also check that file is not locked

Windows spells those `python preflight.py ...` with backslashed paths; nothing
else differs.

What it installs, and where. Packages go in with `python -m pip install --user`
(the per-user site-packages) or, with --venv, into `<skill>/.venv`. **Never a
bare `pip install`**: on a managed Windows workstation that writes to a system
site-packages the operator either cannot elevate into or cannot import from.
If an install fails, the exact pip output is printed and this script stops.
No retry, no fallback to a machine-wide install.

What it can only report, because pip cannot fix it:

  * The two RENDERERS, Microsoft Word (COM) and LibreOffice (`soffice`), and
    which of them this machine would use. Word is the reference renderer and
    Microsoft ships no Word desktop app for Linux, so on Linux and macOS
    LibreOffice is not a fallback - it is the only renderer there is. Neither
    substitutes for the other silently: the engine comes from `--renderer` or an
    explicit platform branch, is printed with its reason, and is named on the
    line announcing every file it writes. See render_engine.py.
  * GATE 2, which is its own third value. verify_borders.py asks whether WORD
    clips a screenshot border. Without Word that question cannot be answered
    either way, so this reports Gate 2 as UNAVAILABLE - never as passed, and
    never merely omitted. A LibreOffice render does not make it available.
    Word is necessary and not sufficient: Gate 2 also needs the packages in
    GATE2_PACKAGES, and this reports UNAVAILABLE when any of them is absent.
    Exit 0 on Linux and macOS therefore means "provisioned", NOT "Gate 2 green" -
    Word over COM cannot exist there, so the line printed at the end says so in
    words the exit code cannot.
  * A locked output file. Word cannot save over a .pdf that a viewer has open
    or a .docx that Word itself has open, and fails "read-only". --target
    checks each named path and tells the operator which file to close.

Verification is a fresh interpreter, not this process: a module that failed to
import once is cached as failed for the life of the interpreter, so re-importing
here after an install would report a false negative.

Stdlib only, on purpose - it has to run before anything is installed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import render_engine

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(SCRIPTS_DIR, os.pardir))
REQUIREMENTS = os.path.join(SKILL_ROOT, "requirements.txt")
DEFAULT_VENV = os.path.join(SKILL_ROOT, ".venv")

# (pip name, import name, what breaks without it). The order is the order the
# report prints in. Keep this list and requirements.txt in step.
PACKAGES = [
    ("python-docx", "docx",
     "build_sop.py, check_conformance.py, fix_effect_extent.py, "
     "extract_spec.py, make_template.py"),
    ("pywin32", "win32com.client", "--to-docx / --to-pdf (Word COM) in build_report.py and build_sop.py"),
    ("PyMuPDF", "pymupdf", "verify_borders.py (Gate 2)"),
    ("Pillow", "PIL", "verify_borders.py, screenshot anonymisation"),
    ("numpy", "numpy", "verify_borders.py - the red-pixel edge measurement is array maths"),
]

# Packages that exist on Windows and nowhere else. pywin32 publishes Windows
# wheels and no sdist, so pip cannot even RESOLVE it elsewhere - and because
# `pip_install` sends every missing package in ONE invocation, and pip resolves
# an invocation all-or-nothing, listing it off Windows failed the whole install
# and left python-docx, PyMuPDF, Pillow and numpy uninstalled too. None of those
# four are Windows-specific, so `--install` could not succeed on any Linux or
# macOS machine. requirements.txt carries the same exclusion as a PEP 508
# marker; keep the two in step.
#
# These are reported `n/a`, never `MISSING`. MISSING states a fixable condition,
# and this one is not fixable on this platform by any action the operator can
# take - Word COM does not exist here. Printing MISSING sends someone looking
# for an install command that cannot exist, which is the more expensive failure.
WINDOWS_ONLY = frozenset({"pywin32"})


def applicable(pip_name):
    """Whether this package can exist on the platform we are running on."""
    return os.name == "nt" or pip_name not in WINDOWS_ONLY


# What Gate 2 needs on top of Word, by pip name. PyMuPDF, Pillow and numpy are
# top-level imports in verify_borders.py, so without any one of them it dies at
# its own import line and exits 1 - which its exit table defines as "at least one
# FAILed". python-docx carries the .docx cross-check, without which Gate 2
# reports UNAVAILABLE rather than PASS. Keep in step with PACKAGES.
GATE2_PACKAGES = ("PyMuPDF", "Pillow", "numpy", "python-docx")

# One-line probe run in a FRESH interpreter: imports the module (the real test),
# then prints the installed distribution's version from pip metadata - pywin32,
# for one, exposes no __version__ anywhere importable.
PROBE = (
    "import importlib,importlib.metadata as md,sys;"
    "importlib.import_module(sys.argv[1]);"
    "print(md.version(sys.argv[2]))"
)


def probe(python, import_name, pip_name):
    """(ok, version_or_error) by importing in a fresh interpreter."""
    r = subprocess.run([python, "-c", PROBE, import_name, pip_name],
                       capture_output=True, text=True, timeout=120,
                       check=False)
    if r.returncode == 0:
        return True, r.stdout.strip()
    err = (r.stderr.strip().splitlines() or ["(no error text)"])[-1]
    return False, err


def word_installed():
    """(present, version_text). Reads the COM registration, does not start Word."""
    if sys.platform != "win32":
        return False, "not Windows"
    try:
        import winreg  # pylint: disable=import-outside-toplevel
    except ImportError:
        return False, "winreg unavailable"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Classes\Word.Application\CurVer") as k:
                return True, winreg.QueryValueEx(k, "")[0]
        except OSError:
            continue
    return False, "Word.Application is not registered for COM"


def locked(path):
    """Why `path` cannot be overwritten right now, or None.

    A viewer holding a PDF open denies write sharing, so opening it read-write
    raises PermissionError. Word additionally leaves an owner file `~$name.docx`
    next to a document it has open.
    """
    if not os.path.exists(path):
        return None
    owner = os.path.join(os.path.dirname(path), "~$" + os.path.basename(path)[2:])
    if os.path.exists(owner):
        return f"Word has {os.path.basename(path)} open (owner file {os.path.basename(owner)} present)"
    try:
        with open(path, "r+b"):
            pass
    except PermissionError as exc:
        return f"{os.path.basename(path)} is open in another program ({exc.strerror or exc})"
    except OSError as exc:
        return f"{os.path.basename(path)} cannot be opened for writing: {exc}"
    return None


def pip_install(python, pkgs, user):
    """`python -m pip install [--user] <pkgs>`, output streamed. Returns the exit code."""
    cmd = [python, "-m", "pip", "install"] + (["--user"] if user else []) + pkgs
    print("\n$ " + " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def make_venv(path):
    if os.path.isfile(venv_python(path)):
        return 0
    print(f"$ {sys.executable} -m venv {path}", flush=True)
    return subprocess.call([sys.executable, "-m", "venv", path])


def venv_python(path):
    return os.path.join(path, "Scripts" if sys.platform == "win32" else "bin",
                        "python.exe" if sys.platform == "win32" else "python")


def confirm(question):
    if not sys.stdin.isatty():
        return False
    try:
        return input(question + " [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true",
                    help="install whatever is missing without asking "
                         "(still --user or --venv, never system-wide)")
    ap.add_argument("--venv", nargs="?", const=DEFAULT_VENV, metavar="DIR",
                    help="install into a virtual environment the skill "
                         f"owns (default {DEFAULT_VENV}) instead of --user")
    ap.add_argument("--target", action="append", default=[], metavar="FILE",
                    help="a .docx/.pdf about to be written; report if a program has it locked (repeatable)")
    args = ap.parse_args(argv)

    rc = 0
    python = sys.executable
    if args.venv and os.path.isfile(venv_python(args.venv)):
        python = venv_python(args.venv)
    print(f"python   : {python} ({sys.version.split()[0]})")
    installs = (f"virtual environment {args.venv}" if args.venv
                else "per-user site-packages (pip --user)")
    print(f"installs : {installs}")

    # -- packages ---------------------------------------------------------------
    print("\n== Python packages ==")
    missing = []
    # Which packages were PROVED importable in a fresh interpreter. Gate 2 below
    # is derived from this rather than from `missing`, because after an install
    # `missing` still names packages that are now present.
    present = set()
    if args.venv and python == sys.executable:
        # The venv does not exist yet, so probing would test the WRONG
        # interpreter: a package present system-wide would be reported ok and
        # then be absent from the venv the scripts are told to run with.
        print("  (virtual environment not created yet - every package will be installed into it)")
        for pip_name, _, used_by in PACKAGES:
            if not applicable(pip_name):
                print(f"  {'n/a'!s:<5} {pip_name!s:<12} -> Windows only; not installable here")
                continue
            print(f"  {'MISSING'!s:<5} {pip_name!s:<12} -> needed by {used_by}")
        missing = [p[0] for p in PACKAGES if applicable(p[0])]
    else:
        for pip_name, import_name, used_by in PACKAGES:
            if not applicable(pip_name):
                print(f"  {'n/a'!s:<5} {pip_name!s:<12} -> Windows only; not installable here")
                continue
            ok, info = probe(python, import_name, pip_name)
            print(f"  {'ok' if ok else 'MISSING'!s:<5} {pip_name!s:<12} {info if ok else '-> needed by ' + used_by}")
            if ok:
                present.add(pip_name)
            else:
                missing.append(pip_name)

    if missing:
        where = " --user" if not args.venv else " into " + (args.venv or "")
        question = f"Install {', '.join(missing)} with pip{where}?"
        if args.install or confirm(question):
            if args.venv:
                if make_venv(args.venv) != 0:
                    print("\nFAILED: could not create the virtual environment. Stopping.", file=sys.stderr)
                    return 2
                python = venv_python(args.venv)
            code = pip_install(python, missing, user=not args.venv)
            if code != 0:
                print(f"\nFAILED: pip exited {code:d}. The error text is above, verbatim. Stopping - "
                      "not retrying, and not falling back to a system-wide install.", file=sys.stderr)
                return 2
            print("\n== verifying in a fresh interpreter ==")
            for pip_name, import_name, _ in PACKAGES:
                if pip_name not in missing:
                    continue
                ok, info = probe(python, import_name, pip_name)
                print(f"  {'ok' if ok else 'FAIL'!s:<5} {pip_name!s:<12} {info}")
                if ok:
                    present.add(pip_name)
                else:
                    rc = 2
            if args.venv:
                print(f"\nRun the scripts with this interpreter:\n  {python} <script>.py ...")
        else:
            print(f"\nNot installed. To install under your profile:\n"
                  f"  {python} -m pip install --user "
                  f"{' '.join(missing)}\n"
                  "or run this script again with --install.")
            rc = max(rc, 3)

    # -- renderers ----------------------------------------------------------------
    print("\n== Renderers (DOCX / PDF) ==")
    word_present, word_info = word_installed()
    print(f"  {'ok' if word_present else 'ABSENT'!s:<7} Microsoft Word (COM)   {word_info}")
    soffice_version = render_engine.soffice_version()
    print(f"  {'ok' if soffice_version else 'ABSENT'!s:<7} LibreOffice (soffice)  "
          f"{soffice_version or 'not installed or not on PATH'}")
    if not soffice_version:
        print("          Debian/Ubuntu: sudo apt install libreoffice-writer\n"
              "          macOS:         brew install --cask libreoffice\n"
              "          Windows:       winget install TheDocumentFoundation.LibreOffice")

    engine, why = render_engine.choose_engine()
    print(f"  default  {engine} -- {why}")
    if engine == render_engine.WORD and not word_present:
        rc = max(rc, 1)
        print("  NOT READY  The default engine here is Word and Word is absent. Nothing falls back "
              "on its own:\n             pass --renderer libreoffice deliberately, or convert on a "
              "machine with Word.")
    if engine == render_engine.LIBREOFFICE:
        if not soffice_version:
            rc = max(rc, 1)
            print("  NOT READY  LibreOffice is the only renderer this platform can have and it is "
                  "absent.\n             The report HTML and the SOP .docx still build; nothing can "
                  "convert them here.")
        else:
            print(f"  Output will be labelled: {render_engine.engine_label(engine, soffice_version)}\n"
                  f"  {render_engine.LIBREOFFICE_FIDELITY}")

    # -- Gate 2 -------------------------------------------------------------------
    # Three values, not two - and the value has to survive into every line here,
    # the exit code included. Gate 2 needs TWO things, not one: a Word that can
    # render the PDF, and the packages verify_borders.py imports. Until
    # 2026-09-22 this printed AVAILABLE on the strength of Word alone, so a
    # machine with Word and no PyMuPDF was told the gate could run while the
    # section six lines above printed `MISSING PyMuPDF` - verify_borders.py would
    # have died at `import pymupdf` and exited 1, which its own exit table reads
    # as "at least one FAILed". That is the same unknown-collapsing-into-the-
    # safe-value bug the three-value gate was built to stop, one rung out.
    print("\n== Gate 2 (verify_borders.py) ==")
    gate2_missing = [p for p in GATE2_PACKAGES if p not in present]
    word_impossible = sys.platform != "win32"
    if word_present and not gate2_missing:
        print("  AVAILABLE    Word can render the PDF this gate measures, and every package\n"
              "               verify_borders.py imports is installed.")
    else:
        print("  UNAVAILABLE  Gate 2 cannot run on this machine. verify_borders.py will report\n"
              "               UNAVAILABLE (exit 3) and print an ADVISORY measurement of whatever "
              "render it\n"
              "               was given. That is NOT a pass, and must not be recorded as one.")
        if not word_present:
            print(f"               - Microsoft Word (COM) is absent ({word_info}), so no PDF built "
                  "here is\n                 Word-rendered.")
            if word_impossible:
                print("                 This skill drives Word over COM, which exists only on "
                      "Windows, so on this\n"
                      "                 platform that is PERMANENT - a fact about the machine, not "
                      "a provisioning\n"
                      "                 fault, and not something --install can repair.")
            else:
                # Windows with Word missing IS fixable, so it is a failure here.
                rc = max(rc, 1)
        if gate2_missing:
            rc = max(rc, 3)
            print(f"               - {', '.join(gate2_missing)} not importable, so "
                  "verify_borders.py cannot even\n"
                  "                 start. Re-run this script with --install.")
        print("               Gate 1 (check_conformance.py) is unaffected - it reads the .docx and "
              "needs\n               no renderer.")

    # -- locked targets ----------------------------------------------------------
    if args.target:
        print("\n== output files ==")
        for t in args.target:
            why = locked(t)
            if why:
                rc = max(rc, 1)
                print(f"  LOCKED  {why}\n"
                      f"          Close {os.path.basename(t)} before "
                      'converting - Word will otherwise fail "read-only".')
            else:
                print(f"  ok      {t}")

    # "Ready" means the toolchain is provisioned, and on Linux and macOS that has
    # to be reachable: Word over COM cannot exist there, so a Gate 2 that can
    # never be available was making rc=1 unconditional and printing "Not ready"
    # on a host with LibreOffice and every package installed. Exit 0 was
    # unreachable on the platform this skill was written to support, which makes
    # the exit code carry no information at all. The unknown still survives -
    # into the line below, which says in words what the 0 does not.
    if rc == 0 and not word_present:
        print("\nReady - the toolchain is provisioned. Gate 2 is UNAVAILABLE here (see above): "
              "exit 0\nmeans this machine can BUILD, it does not mean Gate 2 passed, and nothing "
              "may report\nit as though it had.")
    else:
        print(f"\n{('Ready.' if rc == 0 else 'Not ready - see above.')}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
