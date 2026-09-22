"""preflight must not offer a Windows-only package to a non-Windows pip.

`pip_install` sends every missing package in ONE invocation and pip resolves an
invocation all-or-nothing. pywin32 publishes Windows wheels and no sdist, so
listing it on Linux or macOS failed the whole call and left python-docx,
PyMuPDF, Pillow and numpy uninstalled too - none of which are Windows-specific.
`--install` could not succeed on any non-Windows machine.

Measured before the fix, in a clean venv on Linux:

    ERROR: Could not find a version that satisfies the requirement pywin32>=306
           (from versions: none)
    ERROR: No matching distribution found for pywin32>=306

These tests are about the EXCLUSION, in both places that have to agree: the
`applicable()` predicate that builds preflight's install list, and the PEP 508
marker in requirements.txt. Either one alone leaves a path broken - preflight
has its own PACKAGES list and does not read requirements.txt.
"""
import importlib
import pathlib
import re
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
REQUIREMENTS = SCRIPTS.parent / "requirements.txt"

# Same convention as test_resolve_brand.py:235 - preflight imports render_engine
# as a sibling, so the scripts dir has to be importable, not just readable.
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _preflight():
    return importlib.import_module("preflight")


def test_pywin32_is_not_applicable_off_windows(monkeypatch):
    pf = _preflight()
    monkeypatch.setattr(pf.os, "name", "posix")

    assert pf.applicable("pywin32") is False


def test_pywin32_is_applicable_on_windows(monkeypatch):
    pf = _preflight()
    monkeypatch.setattr(pf.os, "name", "nt")

    assert pf.applicable("pywin32") is True


@pytest.mark.parametrize("pkg", ["python-docx", "PyMuPDF", "Pillow", "numpy"])
def test_the_cross_platform_packages_are_applicable_everywhere(monkeypatch, pkg):
    pf = _preflight()
    monkeypatch.setattr(pf.os, "name", "posix")

    assert pf.applicable(pkg) is True


def test_the_install_list_off_windows_excludes_pywin32_and_keeps_the_rest(monkeypatch):
    """The list handed to pip, which is the thing that actually broke."""
    pf = _preflight()
    monkeypatch.setattr(pf.os, "name", "posix")

    installable = [name for name, _imp, _why in pf.PACKAGES if pf.applicable(name)]

    assert "pywin32" not in installable
    assert installable == ["python-docx", "PyMuPDF", "Pillow", "numpy"]


def test_requirements_marks_pywin32_windows_only():
    """Without the marker `pip install -r` fails to RESOLVE and installs nothing."""
    line = next(ln for ln in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
                if ln.strip().startswith("pywin32"))

    assert re.search(r';\s*sys_platform\s*==\s*"win32"', line), (
        "pywin32 has no PEP 508 environment marker, so `pip install -r "
        f"requirements.txt` cannot resolve off Windows. Line: {line!r}")


def test_no_cross_platform_requirement_is_marked_windows_only():
    """The neighbouring case: a marker on the wrong line silently drops a real dep."""
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = re.split(r"[<>=;\s]", stripped, maxsplit=1)[0]
        if name in ("pywin32",):
            continue
        assert "sys_platform" not in line, (
            f"{name} is not Windows-only but carries a platform marker; it would "
            f"be skipped on the platform that needs it. Line: {line!r}")


def test_packages_and_requirements_name_the_same_distributions():
    """Both files say "keep in step" in a comment. This is what enforces it."""
    pf = _preflight()
    declared = {name for name, _imp, _why in pf.PACKAGES}

    required = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        required.add(re.split(r"[<>=;\s]", stripped, maxsplit=1)[0])

    assert declared == required, (
        "preflight.PACKAGES and requirements.txt have drifted. preflight does "
        "NOT read requirements.txt, so a package in one and not the other is "
        f"installed by one path and not the other.\n  only in PACKAGES: "
        f"{sorted(declared - required)}\n  only in requirements: "
        f"{sorted(required - declared)}")
