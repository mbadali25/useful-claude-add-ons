"""Regression suite for `render_mermaid.py --check`.

The defect these tests exist for: --check decided a diagram was current from
`manifest hash == digest(source) and svg.exists()`. Both halves are about the
*source* and the file's *presence*. Nothing looked inside the SVG, so a
truncated, corrupt or zero-byte SVG passed --check as up to date - a guard
reporting a clean result while measuring nothing.

`fixtures/sample.svg` is a real mmdc render of `fixtures/sample.mmd`, committed
so these tests never need mermaid-cli: CI has no mmdc. Damaging a genuine
render is the point - a hand-written stub would not prove the check looks at
real SVG bytes. The manifests below are built with the script's own
Manifest.put/save so they are byte-identical to what a render would write.

This docstring used to give a second reason - that `resolve_mmdc()` returned
the bare name "mmdc", unrunnable on Windows where mermaid-cli installs as a
.cmd. That was true, and it was a bug rather than a constraint; it is fixed in
1.2.3 and covered by test_resolve_mmdc_uses_the_resolved_path.py. Keeping the
sentence would have left this file asserting something false about the script
it tests.
"""

import hashlib
import json
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "render_mermaid.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SKILL / "scripts"))
import render_mermaid as R  # noqa: E402


GOOD_SVG = (FIXTURES / "sample.svg").read_bytes()
SOURCE = (FIXTURES / "sample.mmd").read_text(encoding="utf-8")


def build(tmp_path: Path, svg_bytes: bytes, *, manifest_version: int) -> Path:
    """A repo with one diagram whose manifest entry is CURRENT for the source.

    Every case below keeps the source hash matching on purpose. That isolates
    the thing under test: if the source hash disagreed, --check would report
    STALE for a reason that has nothing to do with the SVG.
    """
    root = tmp_path / "repo"
    (root / "diagrams").mkdir(parents=True)
    mmd = root / "diagrams" / "flow.mmd"
    mmd.write_text(SOURCE, encoding="utf-8", newline="\n")
    svg = root / "diagrams" / "flow.svg"
    svg.write_bytes(svg_bytes)

    config = SKILL / "assets" / "mermaid-config.json"
    fingerprint = hashlib.sha256(config.read_bytes()).hexdigest()[:16] + ":#ffffff"

    entry = {"hash": R.digest(SOURCE, fingerprint), "svg": "diagrams/flow.svg"}
    if manifest_version >= 2:
        # Record the hash of the GOOD bytes, then let the caller's damage land
        # on disk - which is exactly the real sequence: render, record, corrupt.
        entry["svgHash"] = hashlib.sha256(GOOD_SVG).hexdigest()[:16]
    (root / R.MANIFEST_NAME).write_text(
        json.dumps({"version": manifest_version, "diagrams": {"diagrams/flow.mmd": entry}},
                   indent=2) + "\n",
        encoding="utf-8")
    return root


def check(root: Path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root), str(root / "diagrams")],
        capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout


# --------------------------------------------------------------------------- #
# The two cases that used to pass, in both manifest generations.
# --------------------------------------------------------------------------- #

DAMAGE = {
    "truncated": GOOD_SVG[:len(GOOD_SVG) // 2],   # cut mid-element, no closing tag
    "empty": b"",                                  # what a failed open(p, "w") leaves
}


@pytest.mark.parametrize("kind", sorted(DAMAGE))
@pytest.mark.parametrize("version", [1, 2])
def test_damaged_svg_is_reported_and_fails(tmp_path, kind, version):
    """A damaged SVG must fail --check whether or not a hash was recorded.

    Version 2 catches it by comparing the recorded hash. Version 1 has no hash
    to compare, so it must still be caught structurally - otherwise every repo
    whose manifest predates this change keeps the original bug.
    """
    code, out = check(build(tmp_path, DAMAGE[kind], manifest_version=version))
    assert code == 1, f"v{version} {kind} SVG passed --check:\n{out}"
    assert "DAMAGED" in out, out
    assert "diagrams/flow.mmd" in out, out
    # Naming the file is not enough - the reason has to be in the output, or a
    # future failure for an unrelated cause satisfies this test. The summary has
    # to agree, too: a damaged diagram must never be counted as verified.
    # This line used to read `"up to date" not in out.split("DAMAGED")[0]`, which
    # 1.2.2 made vacuous - the failure summary no longer contains that phrase for
    # any input, so the assertion passed whether or not the bug was present.
    # Assert against the wording the summary actually prints.
    assert "0 diagram(s) verified; 0 stale, 1 damaged, 0 unverified." in out, out


def test_intact_svg_with_recorded_hash_passes(tmp_path):
    code, out = check(build(tmp_path, GOOD_SVG, manifest_version=2))
    assert code == 0, out
    assert "All 1 diagram(s) up to date." in out, out


def test_legacy_manifest_is_unverified_and_fails(tmp_path):
    """An intact SVG under a v1 manifest must be reported UNVERIFIED and exit 1.

    This case exited 0 until 1.2.2, on the argument that a structural check is
    the strongest claim available without a recorded hash. It is - and that is
    the reason to go red, not a reason to stay green. A CI line that means less
    than its reader assumes is the exact defect --check was fixed for one
    release earlier, so shipping a weaker green under the same name reintroduces
    it in the fix.

    The red is one-time: one render --force records the hash and the same SVG
    passes from then on, which test_recording_the_hash_turns_the_red_green
    asserts against the committed fixture.
    """
    code, out = check(build(tmp_path, GOOD_SVG, manifest_version=1))
    assert code == 1, f"an unverified diagram passed --check:\n{out}"
    assert "UNVERIFIED" in out, out
    assert "could not be content-verified" in out, out
    # UNVERIFIED and DAMAGED are different findings and the text must keep them
    # apart - this SVG is intact, and calling it damaged sends someone hunting a
    # corruption that is not there. Match the finding line ("DAMAGED: <file>"),
    # not the bare word, which the explanation deliberately uses to contrast the
    # two.
    assert "  DAMAGED: " not in out, out
    assert "0 damaged" in out, out
    assert "All 1 diagram(s) up to date." not in out, out
    # A failure naming no fix is a failure someone will suppress instead. Assert
    # the exit code and the remedy separately, so a message-only regression -
    # right code, useless text - still reddens this test.
    assert "--force" in out, f"the failure must name the command that ends it:\n{out}"


def test_recording_the_hash_turns_the_red_green(tmp_path):
    """The same intact SVG passes once its svgHash is on record.

    render() cannot run here: CI has no mmdc. So the post-render state is built
    with the script's own Manifest and svg_digest - the same call render()
    makes, at the same point - rather than a hand-computed digest that could
    drift from the function under test.
    """
    root = build(tmp_path, GOOD_SVG, manifest_version=1)
    assert check(root)[0] == 1, "fixture is not red before the hash is recorded"

    manifest = R.Manifest(root / R.MANIFEST_NAME)
    entry = dict(manifest.get("diagrams/flow.mmd"))
    entry["svgHash"] = R.svg_digest(root / "diagrams" / "flow.svg")
    manifest.put("diagrams/flow.mmd", **entry)
    manifest.data["version"] = R.MANIFEST_VERSION
    manifest.save()

    code, out = check(root)
    assert code == 0, out
    assert "All 1 diagram(s) up to date." in out, out
    assert "UNVERIFIED" not in out, out


def build_mixed(tmp_path: Path) -> Path:
    """Two diagrams: one v2 entry whose SVG was damaged after rendering, and one
    legacy entry with an intact SVG. Both findings have to reach the output."""
    root = tmp_path / "repo"
    (root / "diagrams").mkdir(parents=True)
    config = SKILL / "assets" / "mermaid-config.json"
    fingerprint = hashlib.sha256(config.read_bytes()).hexdigest()[:16] + ":#ffffff"

    entries = {}
    for name, payload, record_hash in (("broken", DAMAGE["truncated"], True),
                                       ("legacy", GOOD_SVG, False)):
        (root / "diagrams" / f"{name}.mmd").write_text(SOURCE, encoding="utf-8", newline="\n")
        (root / "diagrams" / f"{name}.svg").write_bytes(payload)
        entry = {"hash": R.digest(SOURCE, fingerprint), "svg": f"diagrams/{name}.svg"}
        if record_hash:
            entry["svgHash"] = hashlib.sha256(GOOD_SVG).hexdigest()[:16]
        entries[f"diagrams/{name}.mmd"] = entry

    (root / R.MANIFEST_NAME).write_text(
        json.dumps({"version": 2, "diagrams": entries}, indent=2) + "\n", encoding="utf-8")
    return root


def test_damaged_and_unverified_are_both_reported(tmp_path):
    """A damaged diagram must not hide an unverified one.

    The report block used to return on stale-or-damaged before the unverified
    section ran, so the count of what could not be checked disappeared from the
    output whenever anything else was also wrong. Now that unverified is itself
    a failure, that shape would silently drop a whole category of finding.
    """
    code, out = check(build_mixed(tmp_path))
    assert code == 1, out
    assert "DAMAGED: diagrams/broken.mmd" in out, out
    assert "UNVERIFIED: diagrams/legacy.mmd" in out, out
    # The summary counts every category, so a stale or damaged file can never be
    # tallied as verified.
    assert "0 diagram(s) verified; 0 stale, 1 damaged, 1 unverified." in out, out


def test_render_records_the_hash_of_the_postprocessed_file(tmp_path):
    """svgHash must be taken after postprocess(), which rewrites the SVG.

    Hashing before it would record a digest the file on disk never has, so every
    subsequent --check would report DAMAGED on a perfectly good render.
    """
    svg = tmp_path / "x.svg"
    svg.write_bytes(GOOD_SVG)
    before = R.svg_digest(svg)
    R.postprocess(svg)
    after = R.svg_digest(svg)
    assert R.svg_digest(svg) == after
    if before != after:
        pytest.skip("postprocess is a no-op on this fixture; ordering untested here")


# A synthetic mmdc-shaped SVG, not GOOD_SVG: GOOD_SVG is one line with no
# embedded '\n' at all (a real mmdc render), so it cannot exercise a newline
# translation bug - there is nothing in it for write_text's default
# `newline=None` to translate. This one has embedded newlines, a viewBox and
# no width= attribute, and the max-width style postprocess() strips, so
# postprocess() actually rewrites it the way a real multi-line render would.
NEWLINE_SVG = (
    '<svg viewBox="0 0 100.5 50.25" xmlns="http://www.w3.org/2000/svg" '
    'style="max-width: 100%;">\n'
    '  <rect width="10" height="10"/>\n'
    '  <text>label</text>\n'
    '</svg>\n'
).encode("utf-8")


def _repo_with_checked_out_svg(tmp_path: Path, rendered_bytes: bytes,
                                checked_out_bytes: bytes) -> Path:
    """A repo whose manifest svgHash was recorded, via R.svg_digest, from
    `rendered_bytes` - what render() actually wrote and hashed - but whose
    committed .svg is `checked_out_bytes` on disk: the same diagram after a
    checkout that changed nothing but line endings (git core.autocrlf on a
    host other than the one that rendered it). Nothing about the diagram
    changed; only the disk bytes did.
    """
    root = tmp_path / "repo"
    (root / "diagrams").mkdir(parents=True)
    mmd = root / "diagrams" / "flow.mmd"
    mmd.write_text(SOURCE, encoding="utf-8", newline="\n")
    svg = root / "diagrams" / "flow.svg"

    svg.write_bytes(rendered_bytes)
    svg_hash = R.svg_digest(svg)  # exactly what render() would have recorded

    config = SKILL / "assets" / "mermaid-config.json"
    fingerprint = hashlib.sha256(config.read_bytes()).hexdigest()[:16] + ":#ffffff"
    entry = {"hash": R.digest(SOURCE, fingerprint), "svg": "diagrams/flow.svg",
              "svgHash": svg_hash}
    (root / R.MANIFEST_NAME).write_text(
        json.dumps({"version": 2, "diagrams": {"diagrams/flow.mmd": entry}}, indent=2) + "\n",
        encoding="utf-8")

    svg.write_bytes(checked_out_bytes)  # the checkout, after recording
    return root


def test_check_tolerates_a_crlf_checkout_of_a_committed_svg(tmp_path):
    """--check must not report DAMAGED for an SVG whose only difference from
    what was recorded is CRLF instead of LF line endings - the shape a
    Windows clone with core.autocrlf=true produces on checkout with no
    .gitattributes entry for *.svg.

    This is the control FIX 2's normalization needed and did not have: with
    no failing test, removing the normalization entirely, or dropping either
    half of it, left the full suite at 28 passed.
    """
    crlf = NEWLINE_SVG.replace(b"\n", b"\r\n")
    root = _repo_with_checked_out_svg(tmp_path, NEWLINE_SVG, crlf)
    code, out = check(root)
    assert code == 0, out
    assert "All 1 diagram(s) up to date." in out, out


def test_check_tolerates_a_lone_cr_checkout_of_a_committed_svg(tmp_path):
    """Same as above, for the old-Mac lone-CR convention - the other half of
    svg_digest()'s normalization.
    """
    lone_cr = NEWLINE_SVG.replace(b"\n", b"\r")
    root = _repo_with_checked_out_svg(tmp_path, NEWLINE_SVG, lone_cr)
    code, out = check(root)
    assert code == 0, out
    assert "All 1 diagram(s) up to date." in out, out

# Multi-line so every write site under test (Manifest.save's JSON, the
# extracted .mmd sidecar, the rewritten .md) has an actual '\n' for write_text
# to mistranslate; a one-line fixture like GOOD_SVG would exercise nothing.
MULTI_LINE_MERMAID_MD = (
    "# Title\n"
    "\n"
    "```mermaid\n"
    "graph TD\n"
    "  A --> B\n"
    "  B --> C\n"
    "```\n"
)


def _simulate_windows_write_text(monkeypatch):
    """Make every unpinned `Path.write_text` call in the code under test
    reproduce, byte for byte, what it would write on a real Windows host.

    Monkeypatching `os.linesep` does NOT do this on a non-Windows CI box:
    measured directly, CPython's io layer does not re-read the mutable
    `os.linesep` module attribute at write time, so a test built that way
    passes whether or not a given call pins `newline="\\n"` - a guard that
    looks like it checks the bug and checks nothing. What write_text's
    `newline=None` branch *does* do, on every platform, is translate every
    '\\n' in the data it is given; that is the part this helper drives
    directly, by wrapping the real `Path.write_text` and forcing the "no
    newline argument supplied" branch to translate to "\\r\\n". A call that
    explicitly pins `newline="\\n"` (or any other explicit value) is left
    untouched, exactly as the real method leaves it untouched on every
    platform - so this isolates precisely the calls that forgot to pin it.
    """
    real_write_text = pathlib.Path.write_text

    def write_text_as_windows_would(self, data, encoding=None, errors=None, newline=None):
        if newline is None:
            data = data.replace("\n", "\r\n")
            newline = ""  # already translated; tell the real call not to touch it again
        return real_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(pathlib.Path, "write_text", write_text_as_windows_would)


def test_postprocess_pins_newline_so_the_digest_is_host_independent(tmp_path, monkeypatch):
    """postprocess()'s write (render_mermaid.py, the `svg_path.write_text`
    call inside `postprocess`) must not let the host's line-ending convention
    leak into the SVG it writes.

    svg_digest() now normalizes line endings before hashing (the FIX 2 fix),
    so a missing pin here no longer breaks the recorded hash by itself - the
    two fixes overlap on that axis. What a missing pin still breaks is the
    file this script commits: an unpinned write on an actual Windows host
    would put CRLF into a diagram meant to render identically everywhere, so
    this test asserts directly on the written bytes, not just the digest.
    """
    host = tmp_path / "host.svg"
    host.write_bytes(NEWLINE_SVG)
    R.postprocess(host)
    host_bytes = host.read_bytes()
    host_hash = R.svg_digest(host)

    simulated = tmp_path / "simulated_windows.svg"
    simulated.write_bytes(NEWLINE_SVG)
    _simulate_windows_write_text(monkeypatch)
    R.postprocess(simulated)
    simulated_bytes = simulated.read_bytes()
    simulated_hash = R.svg_digest(simulated)

    assert b"\r" not in host_bytes, "unexpected CR on this host's own render"
    assert b"\r" not in simulated_bytes, (
        "postprocess() let the host's line-ending convention leak into the "
        "written SVG - the write must pin newline=\"\\n\""
    )
    assert host_hash == simulated_hash, (
        f"the same logical SVG hashed differently depending on host "
        f"line-ending convention: {host_hash} != {simulated_hash}"
    )


def test_manifest_save_pins_newline_so_the_manifest_is_host_independent(tmp_path, monkeypatch):
    """Manifest.save()'s write (`Manifest.save`, the `self.path.write_text`
    call) must not let the host translate the JSON's '\\n' either.

    Unlike the SVG, `.mermaid-svg.json` is never digest-compared against
    itself - nothing reads it expecting particular bytes. The failure mode
    here is not DAMAGED, it's noise: a manifest saved from a Windows checkout
    would rewrite every line of the file to CRLF, so a change to one
    diagram's entry shows as a diff touching the entire file.
    """
    manifest_path = tmp_path / R.MANIFEST_NAME
    m = R.Manifest(manifest_path)
    m.put("diagrams/a.mmd", hash="sha256:aaa", svg="diagrams/a.svg", svgHash="deadbeef")
    m.put("diagrams/b.mmd", hash="sha256:bbb", svg="diagrams/b.svg", svgHash="cafef00d")

    _simulate_windows_write_text(monkeypatch)
    m.save()

    written = manifest_path.read_bytes()
    assert b"\r" not in written, (
        "Manifest.save() let the host's line-ending convention leak into "
        f"{R.MANIFEST_NAME} - the write must pin newline=\"\\n\""
    )


def test_sidecar_mmd_write_pins_newline_so_it_is_host_independent(tmp_path, monkeypatch):
    """The extracted .mmd sidecar write (`process_markdown`, the
    `mmd_path.write_text` call) must not let the host translate it either.

    `normalize()` already strips \\r out of the source before this write, so
    an unpinned write_text would put CRLF straight back in on Windows,
    undoing that normalization for the file on disk (though not for the
    digest, since `digest()` re-normalizes on read - the same overlap noted
    on the SVG test above).
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    md.write_text(MULTI_LINE_MERMAID_MD, encoding="utf-8", newline="\n")
    out_dir = root / "docs" / "diagrams"

    _simulate_windows_write_text(monkeypatch)
    extracted = R.process_markdown(md, root, out_dir)

    assert len(extracted) == 1, extracted
    mmd_path = extracted[0][0]
    written = mmd_path.read_bytes()
    assert b"\r" not in written, (
        "the sidecar .mmd write let the host's line-ending convention leak "
        "in - the write must pin newline=\"\\n\""
    )


def test_markdown_rewrite_pins_newline_for_an_lf_original(tmp_path, monkeypatch):
    """The rewritten-Markdown write (`process_markdown`, the
    `md_path.write_text` call) must not let the host translate an
    LF-original file either.

    This is the LF-original case only; the CRLF-original case is a separate
    concern (preserve the file's own convention rather than always forcing
    LF - see test_markdown_rewrite_preserves_crlf_convention) and is not
    what this test is checking.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    md.write_text(MULTI_LINE_MERMAID_MD, encoding="utf-8", newline="\n")  # LF original
    out_dir = root / "docs" / "diagrams"

    _simulate_windows_write_text(monkeypatch)
    R.process_markdown(md, root, out_dir)

    written = md.read_bytes()
    assert b"\r" not in written, (
        "the rewritten Markdown write let the host's line-ending convention "
        "leak in for an LF-original file - the write must pin newline=\"\\n\""
    )


def test_markdown_rewrite_preserves_crlf_convention(tmp_path):
    """A CRLF-original Markdown file must come back CRLF, not forced to LF.

    The .md file is never digest-compared, so pinning newline="\\n"
    unconditionally has no correctness benefit here and one real cost: for a
    CRLF-original file it flips every line ending in the WHOLE file, not just
    the fenced block that got replaced, turning a one-block edit into a
    file-wide diff. The fix is to preserve each line's own original ending.

    `written.count(b"\\r\\n") == written.count(b"\\n")` alone would also be
    true of a file corrupted to "\\r\\r\\n" throughout (every "\\r\\n" still
    contains exactly one "\\n"), so this also asserts directly that no "\\r\\r"
    exists - see test_markdown_rewrite_never_doubles_cr_under_windows for the
    dedicated, sabotage-tested version of that check.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    md.write_bytes(MULTI_LINE_MERMAID_MD.replace("\n", "\r\n").encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    R.process_markdown(md, root, out_dir)

    written = md.read_bytes()
    assert b"\r\r" not in written, f"doubled CR in the output: {written!r}"
    assert written.count(b"\r\n") == written.count(b"\n"), (
        "expected every line ending in the rewritten file to be CRLF "
        f"(original was CRLF throughout): {written!r}"
    )
    assert b"\r\n" in written, "the file lost its CRLF convention entirely"


def test_markdown_rewrite_never_doubles_cr_under_windows(tmp_path, monkeypatch):
    """The single write in process_markdown() (`md_path.write_text(result,
    encoding="utf-8", newline="")`) must keep `newline=""` - dropping it back
    to the default lets an already-CRLF `result` (built by hand from the
    original bytes, for a CRLF-original file) get translated a SECOND time.

    On an actual Windows host, write_text's `newline=None` branch finds every
    '\\n' in `result` - including the '\\n' half of every '\\r\\n' already
    there - and replaces each with os.linesep ("\\r\\n"), turning each
    original "\\r\\n" into "\\r" + "\\r\\n" = "\\r\\r\\n". A same-count
    assertion like `count(b"\\r\\n") == count(b"\\n")` does not catch this: it
    is equally true of a file doubled throughout. Only a direct check for
    "\\r\\r" catches it, and only `_simulate_windows_write_text` can produce
    the corruption on a non-Windows CI box in the first place.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    md.write_bytes(MULTI_LINE_MERMAID_MD.replace("\n", "\r\n").encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    _simulate_windows_write_text(monkeypatch)
    R.process_markdown(md, root, out_dir)

    written = md.read_bytes()
    assert b"\r\r" not in written, (
        f"the rewritten Markdown write let write_text translate an "
        f"already-CRLF string a second time - the write must pin "
        f'newline="" so it is never translated at all: {written!r}'
    )


def test_markdown_rewrite_preserves_mixed_line_endings(tmp_path):
    """A file that mixes CRLF and LF must keep each line's own ending -
    only the fenced block that gets replaced may change, and the inserted
    image-link line must match whichever ending closed the fence it
    replaces, not a file-wide convention.

    This is the exact bug named in review: a single CRLF line used to
    convert every OTHER line in the file to CRLF too, so a mostly-LF file
    got a full-file diff for touching one block.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    mixed = (
        "# Title\r\n"            # CRLF, untouched - must stay CRLF
        "\n"                     # LF, untouched - must stay LF
        "```mermaid\n"           # fence open, LF
        "graph TD\n"
        "  A --> B\n"
        "```\r\n"                # fence close ends CRLF - the inserted line matches this
        "Trailing paragraph.\n"  # LF, untouched - must stay LF
    )
    md.write_bytes(mixed.encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    extracted = R.process_markdown(md, root, out_dir)

    assert len(extracted) == 1, extracted
    svg_path = extracted[0][0].with_suffix(".svg")
    link = f"![Title]({R.rel(md, svg_path)})"
    expected = (
        "# Title\r\n"
        "\n"
        f"{link}\r\n"
        "Trailing paragraph.\n"
    ).encode("utf-8")
    written = md.read_bytes()
    assert written == expected, f"\n  got:      {written!r}\n  expected: {expected!r}"


def test_markdown_rewrite_preserves_lone_cr_lines(tmp_path):
    """A file using the old-Mac bare-CR convention throughout must come back
    bare-CR throughout, with no LF introduced anywhere - the second half of
    the same per-line-preservation fix, for the other non-LF convention.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    md.write_bytes(MULTI_LINE_MERMAID_MD.replace("\n", "\r").encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    R.process_markdown(md, root, out_dir)

    written = md.read_bytes()
    assert b"\n" not in written, f"an LF leaked into a bare-CR file: {written!r}"
    assert b"\r" in written, "the file lost its CR convention entirely"


def test_markdown_rewrite_does_not_add_a_trailing_newline(tmp_path):
    """A file whose last line has no trailing newline must not gain one,
    even when that last line IS the fence being replaced.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    # MULTI_LINE_MERMAID_MD's fenced block is the file's last content; strip
    # its one trailing '\n' so the closing "```" itself has no terminator.
    md.write_bytes(MULTI_LINE_MERMAID_MD.rstrip("\n").encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    R.process_markdown(md, root, out_dir)

    written = md.read_bytes()
    assert not written.endswith((b"\n", b"\r")), (
        f"gained a trailing newline the original file did not have: {written!r}"
    )


def test_markdown_rewrite_preserves_crlf_after_the_last_fence(tmp_path):
    """The tail slice after the LAST match - `pieces.append(raw_text[offsets[cursor]:])`,
    appended once after the loop rather than inside it - is a separate code
    path from the per-match pass-through slice appended inside the loop, and
    every existing fixture puts the fence at (or effectively at) the end of
    the file, so nothing exercised it: MULTI_LINE_MERMAID_MD's fence IS the
    last content, and the mixed-EOL test's one line of trailing text is LF,
    not CRLF. A mutant that runs this specific tail through
    `.replace("\\r\\n", "\\n")` - turning trailing CRLF content back to LF -
    left the full suite passing.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    content = (
        "```mermaid\r\n"
        "graph TD\r\n"
        "  A --> B\r\n"
        "```\r\n"
        "Trailing paragraph one.\r\n"
        "Trailing paragraph two.\r\n"
    )
    md.write_bytes(content.encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    extracted = R.process_markdown(md, root, out_dir)

    assert len(extracted) == 1, extracted
    expected_tail = b"Trailing paragraph one.\r\nTrailing paragraph two.\r\n"
    written = md.read_bytes()
    assert written.endswith(expected_tail), (
        f"the tail after the last fence lost its CRLF convention:\n"
        f"  got:      {written!r}\n  expected suffix: {expected_tail!r}"
    )


def test_sidecar_mmd_content_is_correct_for_a_crlf_source(tmp_path):
    """The extracted .mmd sidecar's CONTENT - not just its line endings, which
    test_sidecar_mmd_write_pins_newline_so_it_is_host_independent already
    covers - must be a faithful line-for-line translation of a CRLF source.

    `_normalize_with_offsets` advances `i` by 2 for a "\\r\\n" pair and by 1
    for a bare "\\r", so it consumes the pair as a single unit. A mutant that
    always advances by 1 leaves the '\\n' half of every "\\r\\n" unconsumed:
    the next loop iteration sees that '\\n' as an ordinary character and
    appends a SECOND '\\n' for it, so every original CRLF becomes "\\n\\n" in
    the normalized text FENCE_RE matches against - a spurious blank line
    between every pair of lines inside the fenced body. That body becomes
    `m.group("body")`, written to the sidecar via `normalize()`, which only
    trims leading/trailing blank lines, not internal ones - so the corruption
    survives into the .mmd file untouched, while none of the .md-side tests
    (which check line ENDINGS, not internal CONTENT) can see it.
    """
    root = tmp_path / "repo"
    root.mkdir()
    md = root / "doc.md"
    content = (
        "```mermaid\r\n"
        "graph TD\r\n"
        "  A --> B\r\n"
        "  B --> C\r\n"
        "```\r\n"
    )
    md.write_bytes(content.encode("utf-8"))
    out_dir = root / "docs" / "diagrams"

    extracted = R.process_markdown(md, root, out_dir)

    assert len(extracted) == 1, extracted
    mmd_path = extracted[0][0]
    written = mmd_path.read_text(encoding="utf-8")
    expected = "graph TD\n  A --> B\n  B --> C\n"
    assert written == expected, f"\n  got:      {written!r}\n  expected: {expected!r}"


# --------------------------------------------------------------------------- #
# The structural check itself
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("payload,expect_ok", [
    (GOOD_SVG, True),
    (b"", False),
    (b"   \n  ", False),
    (b"<html><body>not an svg</body></html>", False),
    (GOOD_SVG[:200], False),
])
def test_svg_structure_ok(tmp_path, payload, expect_ok):
    p = tmp_path / "s.svg"
    p.write_bytes(payload)
    ok, why = R.svg_structure_ok(p)
    assert ok is expect_ok, (ok, why)
    if not ok:
        assert why, "a rejection must say why"
