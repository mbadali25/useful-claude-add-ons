#!/usr/bin/env python3
"""Preflight for doc-builder: find what is missing, install it under the user
profile after ONE confirmation, then prove it imports.

Run this before the first document on any machine, and again whenever a script
fails with ModuleNotFoundError:

    python preflight.py                    # report only; asks before installing anything
    python preflight.py --install          # install missing packages without the prompt
    python preflight.py --venv             # ...into a virtual environment this skill owns (.venv/)
    python preflight.py --target "C:\\masters\\My SOP.pdf"   # also check that file is not locked

What it installs, and where. Packages go in with `python -m pip install --user`
(the per-user site-packages) or, with --venv, into `<skill>/.venv`. **Never a
bare `pip install`**: on a managed Windows workstation that writes to a system
site-packages the operator either cannot elevate into or cannot import from.
If an install fails, the exact pip output is printed and this script stops.
No retry, no fallback to a machine-wide install.

What it can only report, because pip cannot fix it:

  * Microsoft Word. The HTML -> Word path (`build_report.py --to-docx/--to-pdf`)
    and the PDF step of the SOP path (`build_sop.py --to-pdf`) need Word COM.
    Without Word, HTML and .docx are still produced; conversion and Gate 2 are
    not available and the preflight says so by name. Nothing falls back to
    pandoc or LibreOffice, which are not assumed to exist.
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

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(SCRIPTS_DIR, os.pardir))
REQUIREMENTS = os.path.join(SKILL_ROOT, "requirements.txt")
DEFAULT_VENV = os.path.join(SKILL_ROOT, ".venv")

# (pip name, import name, what breaks without it). The order is the order the
# report prints in. Keep this list and requirements.txt in step.
PACKAGES = [
    ("python-docx", "docx", "build_sop.py, check_conformance.py, fix_effect_extent.py, extract_spec.py, make_template.py"),
    ("pywin32", "win32com.client", "--to-docx / --to-pdf (Word COM) in build_report.py and build_sop.py"),
    ("PyMuPDF", "pymupdf", "verify_borders.py (Gate 2)"),
    ("Pillow", "PIL", "verify_borders.py, screenshot anonymisation"),
    ("numpy", "numpy", "verify_borders.py - the red-pixel edge measurement is array maths"),
]

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
                       capture_output=True, text=True, timeout=120)
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
        return "Word has %s open (owner file %s present)" % (os.path.basename(path), os.path.basename(owner))
    try:
        with open(path, "r+b"):
            pass
    except PermissionError as exc:
        return "%s is open in another program (%s)" % (os.path.basename(path), exc.strerror or exc)
    except OSError as exc:
        return "%s cannot be opened for writing: %s" % (os.path.basename(path), exc)
    return None


def pip_install(python, pkgs, user):
    """`python -m pip install [--user] <pkgs>`, output streamed. Returns the exit code."""
    cmd = [python, "-m", "pip", "install"] + (["--user"] if user else []) + pkgs
    print("\n$ " + " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def make_venv(path):
    if os.path.isfile(venv_python(path)):
        return 0
    print("$ %s -m venv %s" % (sys.executable, path), flush=True)
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
                    help="install whatever is missing without asking (still --user or --venv, never system-wide)")
    ap.add_argument("--venv", nargs="?", const=DEFAULT_VENV, metavar="DIR",
                    help="install into a virtual environment the skill owns (default %s) instead of --user"
                         % DEFAULT_VENV)
    ap.add_argument("--target", action="append", default=[], metavar="FILE",
                    help="a .docx/.pdf about to be written; report if a program has it locked (repeatable)")
    args = ap.parse_args(argv)

    rc = 0
    python = sys.executable
    if args.venv and os.path.isfile(venv_python(args.venv)):
        python = venv_python(args.venv)
    print("python   : %s (%s)" % (python, sys.version.split()[0]))
    print("installs : %s" % ("virtual environment %s" % args.venv if args.venv else "per-user site-packages (pip --user)"))

    # -- packages ---------------------------------------------------------------
    print("\n== Python packages ==")
    missing = []
    if args.venv and python == sys.executable:
        # The venv does not exist yet, so probing would test the WRONG
        # interpreter: a package present system-wide would be reported ok and
        # then be absent from the venv the scripts are told to run with.
        print("  (virtual environment not created yet - every package will be installed into it)")
        for pip_name, _, used_by in PACKAGES:
            print("  %-5s %-12s -> needed by %s" % ("MISSING", pip_name, used_by))
        missing = [p[0] for p in PACKAGES]
    else:
        for pip_name, import_name, used_by in PACKAGES:
            ok, info = probe(python, import_name, pip_name)
            print("  %-5s %-12s %s" % ("ok" if ok else "MISSING", pip_name, info if ok else "-> needed by " + used_by))
            if not ok:
                missing.append(pip_name)

    if missing:
        question = "Install %s with pip%s?" % (", ".join(missing), " --user" if not args.venv else " into " + (args.venv or ""))
        if args.install or confirm(question):
            if args.venv:
                if make_venv(args.venv) != 0:
                    print("\nFAILED: could not create the virtual environment. Stopping.", file=sys.stderr)
                    return 2
                python = venv_python(args.venv)
            code = pip_install(python, missing, user=not args.venv)
            if code != 0:
                print("\nFAILED: pip exited %d. The error text is above, verbatim. Stopping - "
                      "not retrying, and not falling back to a system-wide install." % code, file=sys.stderr)
                return 2
            print("\n== verifying in a fresh interpreter ==")
            for pip_name, import_name, _ in PACKAGES:
                if pip_name not in missing:
                    continue
                ok, info = probe(python, import_name, pip_name)
                print("  %-5s %-12s %s" % ("ok" if ok else "FAIL", pip_name, info))
                if not ok:
                    rc = 2
            if args.venv:
                print("\nRun the scripts with this interpreter:\n  %s <script>.py ..." % python)
        else:
            print("\nNot installed. To install under your profile:\n  %s -m pip install --user %s\n"
                  "or run this script again with --install." % (python, " ".join(missing)))
            rc = max(rc, 3)

    # -- Word --------------------------------------------------------------------
    print("\n== Microsoft Word (COM) ==")
    present, info = word_installed()
    if present:
        print("  ok    %s" % info)
    else:
        rc = max(rc, 1)
        print("  ABSENT  %s" % info)
        print("  Unavailable on this machine: build_report.py --to-docx/--to-pdf, build_sop.py --to-pdf,\n"
              "  and therefore verify_borders.py (Gate 2), which needs a rendered PDF.\n"
              "  Still available: the report HTML and the SOP .docx. Convert them on a machine with Word;\n"
              "  nothing here falls back to pandoc or LibreOffice.")

    # -- locked targets ----------------------------------------------------------
    if args.target:
        print("\n== output files ==")
        for t in args.target:
            why = locked(t)
            if why:
                rc = max(rc, 1)
                print("  LOCKED  %s\n          Close %s before converting - Word will otherwise fail \"read-only\"."
                      % (why, os.path.basename(t)))
            else:
                print("  ok      %s" % t)

    print("\n%s" % ("Ready." if rc == 0 else "Not ready - see above."))
    return rc


if __name__ == "__main__":
    sys.exit(main())
