"""A path is absolute on whichever OS AUTHORED it, at every call site - not
just inside `Brand._rel()`.

`67f6fdb5` fixed `_rel()` so a brand pack's Windows-authored `C:\\repos\\...`
resolves when the pack is read on Linux. Three sibling call sites kept the bare
`os.path.isabs()` form that fix replaced, and a *spec* is authored on Windows
for exactly the same reason a brand pack is:

  1. `build_sop.resolve_output` - the expensive one. `os.path.join()` appends a
     drive path as a single path SEGMENT, so the builder wrote one file
     literally NAMED `C:\\repos\\OnboardingSOPs\\sops_new\\Demo.docx` into the
     spec's own folder. `os.makedirs(os.path.dirname(out))` got the spec dir,
     which exists, so nothing raised: exit 0, `Built: ...` printed, and the
     master nobody could find was sitting next to the spec under a filename
     with a colon and three backslashes in it.
  2. `build_sop.build_from_spec`'s image branch - the same predicate, but the
     joined path is stat'd, so it always failed LOUDLY with
     `FileNotFoundError: image not found:`. That is the cheap failure and it
     stays loud here on purpose; `test_missing_image_still_fails_loudly` is the
     test that stops a future "fix" turning it silent.
  3. `check_conformance._load_spec_map` - the map Gate 1 looks a master up by.
     A garbage key cannot match any real master, so the lookup missed,
     `info["spec"]` read `"none"`, and Gate 1 reported PASS / exit 0 for a
     master its own spec CONTRADICTS. Measured before the fix: the identical
     master+spec pair goes `FAIL ... exit 1` when the spec's `output` is
     POSIX-spelled and `PASS ... exit 0` when it is Windows-spelled. That is
     the drift check silently not RUNNING, not running and passing - and
     `spec none` is only visible under `-v`, so the default output says
     nothing at all.

Every assertion here is on BEHAVIOUR - where a file actually landed, whether a
drift error was actually raised. A test that only asserted a non-zero exit
status would pass against a fix that still wrote the wrong file, just loudly.

All three now route through `resolve_brand.abs_or_join()`, which is the single
copy of the predicate. `test_call_sites_do_not_reintroduce_the_bare_predicate`
is the one that stops a fourth copy being written.

NO WINDOWS HOST WAS AVAILABLE. Everything below ran on Linux only. The
`os.name != "nt"` guards mark the assertions that encode the POSIX direction of
the mapping; the Windows direction (`C:\\x` staying `C:\\x`) is asserted only by
`test_abs_or_join_is_identity_on_paths_already_native`, which is trivially true
on POSIX and has NOT been observed executing on Windows.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_DOC_BUILDER_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _DOC_BUILDER_ROOT / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_sop  # noqa: E402  pylint: disable=wrong-import-position
import check_conformance  # noqa: E402  pylint: disable=wrong-import-position
import resolve_brand  # noqa: E402  pylint: disable=wrong-import-position

ON_WINDOWS = os.name == "nt"
posix_only = pytest.mark.skipif(
    ON_WINDOWS, reason="asserts the POSIX direction of the cross-OS mapping")


def _windows_spelling(path) -> str:
    """The way a Windows author's spec would spell `path`.

    Per this repo's convention (CLAUDE.md) a drive root and the Linux root are
    the same machine, so `/tmp/x/y` and `C:\\tmp\\x\\y` name one file. Building
    the fixture this way - rather than hard-coding `C:\\repos\\...` - is what
    lets the test assert the path RESOLVES to a real file, instead of only
    asserting it stopped being garbage.
    """
    return "C:" + str(path).replace("/", "\\")


# --------------------------------------------------------------------------
# the helper itself
# --------------------------------------------------------------------------
@posix_only
@pytest.mark.parametrize("value,expected", [
    ("C:\\repos\\OnboardingSOPs\\Demo.docx", "/repos/OnboardingSOPs/Demo.docx"),
    ("c:/repos/mixed/Demo.docx", "/repos/mixed/Demo.docx"),
    ("Z:\\other\\drive.docx", "/other/drive.docx"),
    ("\\\\server\\share\\Demo.docx", "//server/share/Demo.docx"),
    ("/already/posix.docx", "/already/posix.docx"),
])
def test_abs_or_join_treats_any_os_absolute_as_absolute(value, expected):
    assert resolve_brand.abs_or_join(value, "/base/dir") == expected


@posix_only
def test_a_drive_relative_path_is_a_KNOWN_GAP_not_a_silent_pass():
    """`\\bare\\path` (rooted, but no drive) is NOT handled, and this test
    exists so that is a recorded fact rather than a hole someone rediscovers.

    `_rel()`'s second branch was written to catch it via `ntpath.isabs()`, but
    Python 3.13 changed `ntpath.isabs()` to return False for a rooted
    drive-RELATIVE path, so on 3.13+ that branch never fires for this input and
    the value falls through to the join. Measured on 3.14.4.

    This is pre-existing - it predates the helper, which preserved `_rel()`'s
    behaviour deliberately and exactly - and it does NOT affect the defect this
    file is about: a drive path is matched by `_WINDOWS_DRIVE_ABS_RE` before
    `ntpath.isabs()` is ever consulted. Filed in TODO.md.

    If someone fixes the gap, this test goes red. That is the intended signal:
    delete it and move the case into the parametrised list above.
    """
    got = resolve_brand.abs_or_join("\\bare\\path\\Demo.docx", "/base/dir")

    assert got == "/base/dir/\\bare\\path\\Demo.docx"


def test_abs_or_join_still_joins_a_genuinely_relative_path():
    got = resolve_brand.abs_or_join(os.path.join("sub", "x.docx"), os.path.join(os.sep, "base"))

    assert got == os.path.normpath(os.path.join(os.sep, "base", "sub", "x.docx"))


def test_abs_or_join_is_identity_on_paths_already_native():
    native = os.path.join(os.sep, "native", "abs.docx")

    assert resolve_brand.abs_or_join(native, os.path.join(os.sep, "base")) == native


@posix_only
def test_abs_or_join_never_returns_a_drive_letter_as_a_path_segment():
    """The whole defect in one assertion: the drive path must not survive
    INSIDE the joined result."""
    got = resolve_brand.abs_or_join("C:\\repos\\x\\Demo.docx", "/base/dir")

    assert "C:" not in got
    assert "\\" not in got
    assert not got.startswith("/base/dir")


# --------------------------------------------------------------------------
# site 1 - resolve_output / build_from_spec
# --------------------------------------------------------------------------
@posix_only
def test_resolve_output_does_not_append_a_windows_path_to_base_dir():
    spec = {"title": "Demo", "output": "C:\\repos\\OnboardingSOPs\\sops_new\\Demo.docx"}

    out = build_sop.resolve_output(spec, "/tmp/specdir")

    assert out == "/repos/OnboardingSOPs/sops_new/Demo.docx"
    assert os.path.basename(out) == "Demo.docx"


@posix_only
def test_build_writes_to_the_mapped_directory_not_a_backslash_filename(tmp_path, monkeypatch):
    """The behavioural assertion, not an exit-code one: the .docx has to land
    in the masters directory the spec names, and the spec's own folder must be
    left holding nothing but the spec.

    `monkeypatch.chdir` is not decoration. A broken mapping can yield a
    RELATIVE path (`C:/tmp/...` - what `posixpath.normpath` makes of a drive
    path when the drive branch is skipped), which python-docx then writes under
    the CWD. Sabotaging the helper with pytest's CWD at the skill root created a
    real `skills/doc-builder/C:/` directory in the checkout. Anchoring the CWD
    to tmp_path keeps a failing run's debris inside the fixture.
    """
    monkeypatch.chdir(tmp_path)
    specdir = tmp_path / "specs"
    masters = tmp_path / "sops_new"
    specdir.mkdir()
    masters.mkdir()
    target = masters / "Demo.docx"

    spec = {"title": "Demo SOP", "subtitle": "repro",
            "output": _windows_spelling(target),
            "body": [{"type": "para", "text": "hello"}]}
    build_sop.build_from_spec(spec, base_dir=str(specdir),
                              brand=resolve_brand.resolve(announce=False))

    assert target.is_file()
    assert sorted(p.name for p in specdir.iterdir()) == []
    assert not [p for p in tmp_path.rglob("*") if "\\" in p.name]


@posix_only
def test_dry_run_reports_the_mapped_path(tmp_path, capsys):
    """`--dry-run` is what someone checks BEFORE writing a production master,
    so it has to show the real destination - a dry run that printed the
    garbage path would at least have been visible, and it did not."""
    masters = tmp_path / "sops_new"
    masters.mkdir()
    target = masters / "Demo.docx"

    build_sop.build_from_spec(
        {"title": "Demo SOP", "output": _windows_spelling(target),
         "body": [{"type": "para", "text": "hello"}]},
        base_dir=str(tmp_path), brand=resolve_brand.resolve(announce=False),
        dry_run=True)

    printed = capsys.readouterr().out
    assert str(target) in printed
    assert "C:" not in printed


def test_relative_output_still_resolves_against_the_spec_folder(tmp_path):
    """The regression guard on the ordinary path - the fix must not have made
    every relative output absolute."""
    spec = {"title": "Demo", "output": os.path.join("out", "Demo.docx")}

    out = build_sop.resolve_output(spec, str(tmp_path))

    assert out == os.path.normpath(str(tmp_path / "out" / "Demo.docx"))


# --------------------------------------------------------------------------
# site 2 - image paths. Lower priority: this one always failed loudly.
# --------------------------------------------------------------------------
@posix_only
def test_windows_spelled_image_resolves_to_its_posix_twin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img = tmp_path / "assets" / "shot.png"
    img.parent.mkdir()
    img.write_bytes(_ONE_PIXEL_PNG)
    out = tmp_path / "Demo.docx"

    build_sop.build_from_spec(
        {"title": "Demo", "output": str(out),
         "body": [{"type": "image", "path": _windows_spelling(img), "caption": "c"}]},
        base_dir=str(tmp_path), brand=resolve_brand.resolve(announce=False))

    assert out.is_file()


@posix_only
def test_missing_image_still_fails_loudly(tmp_path, monkeypatch):
    """This branch stat's the joined path, so it ALREADY raised before the fix.
    It must keep raising - and now name the path it actually looked for, rather
    than a base_dir-joined string nobody can act on."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError) as exc:
        build_sop.build_from_spec(
            {"title": "Demo", "output": str(tmp_path / "Demo.docx"),
             "body": [{"type": "image", "path": "C:\\nope\\missing.png"}]},
            base_dir=str(tmp_path), brand=resolve_brand.resolve(announce=False))

    message = str(exc.value)
    assert "image not found" in message
    assert "/nope/missing.png" in message
    assert str(tmp_path) not in message


# --------------------------------------------------------------------------
# site 3 - Gate 1's spec map
# --------------------------------------------------------------------------
def _spec_map_fixture(tmp_path, output_value):
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "demo.json").write_text(json.dumps({
        "title": "Demo SOP",
        "output": output_value,
        "body": [{"type": "para", "text": "x"}],
    }), encoding="utf-8")
    return check_conformance._load_spec_map(str(specs))


@posix_only
def test_spec_map_keys_a_windows_output_by_the_master_it_names(tmp_path):
    master = tmp_path / "sops_new" / "Demo.docx"
    master.parent.mkdir()

    mapping = _spec_map_fixture(tmp_path, _windows_spelling(master))

    key = os.path.normcase(os.path.normpath(os.path.abspath(str(master))))
    assert key in mapping, mapping
    assert not [k for k in mapping if "\\" in k or "C:" in k]


@posix_only
def test_gate_one_reports_drift_on_a_windows_authored_spec(tmp_path, monkeypatch):
    """The gate-level behaviour, end to end. The spec deliberately disagrees
    with the master, so a Gate 1 that is actually RUNNING must return an error.
    Before the fix this returned no errors and `info["spec"] == "none"`."""
    monkeypatch.chdir(tmp_path)
    masters = tmp_path / "sops_new"
    masters.mkdir()
    master = masters / "Demo.docx"
    brand = resolve_brand.resolve(announce=False)
    build_sop.build_from_spec(
        {"title": "Demo SOP", "body": [{"type": "para", "text": "actual master text"}]},
        base_dir=str(tmp_path), out=str(master), brand=brand)

    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "demo.json").write_text(json.dumps({
        "title": "Demo SOP",
        "output": _windows_spelling(master),
        "body": [{"type": "para", "text": "this text is NOT in the master"}],
    }), encoding="utf-8")

    check_conformance.S.configure(brand)
    spec_map = check_conformance._load_spec_map(str(specs))
    errors, _warnings, info = check_conformance.check(str(master), spec_map=spec_map)

    assert info["spec"] == "demo.json"
    assert any("this text is NOT in the master" in e for e in errors), errors


def test_spec_map_still_keys_a_relative_output(tmp_path):
    """The ordinary case, unchanged: a relative `output` keys off the spec's
    own folder."""
    mapping = _spec_map_fixture(tmp_path, os.path.join("..", "sops_new", "Demo.docx"))

    key = os.path.normcase(os.path.normpath(os.path.abspath(
        str(tmp_path / "sops_new" / "Demo.docx"))))
    assert key in mapping, mapping


# --------------------------------------------------------------------------
# the fourth copy
# --------------------------------------------------------------------------
def test_call_sites_do_not_reintroduce_the_bare_predicate():
    """`os.path.isabs()` is correct ONLY where the value is already known
    native. Each of the three sites below reads a path some other machine may
    have authored, so each must go through `abs_or_join`. This is a source
    assertion rather than a behavioural one, deliberately: it is the only kind
    that catches a FOURTH call site being added with the bare predicate, which
    is how these three came to exist.
    """
    offenders = []
    for name in ("build_sop.py", "check_conformance.py"):
        for lineno, line in enumerate((_SCRIPTS_DIR / name).read_text(
                encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if "os.path.isabs" in code:
                offenders.append(f"{name}:{lineno}: {line.strip()}")

    assert offenders == [], (
        "os.path.isabs() reappeared at a call site that reads an "
        "externally-authored path; use resolve_brand.abs_or_join():\n  "
        + "\n  ".join(offenders))


# A 1x1 truecolour PNG, so the image branch has a real file python-docx will
# actually parse, without shipping a binary fixture. Generated with zlib +
# struct; a hand-typed one had a bad IDAT and python-docx failed on the CRC
# rather than on anything this file is about.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63f8ffff3f0005fe02fe0def46b80000000049454e44ae"
    "426082")
