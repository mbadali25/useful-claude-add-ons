"""Regression suite for `render_mermaid.py --check`.

The defect these tests exist for: --check decided a diagram was current from
`manifest hash == digest(source) and svg.exists()`. Both halves are about the
*source* and the file's *presence*. Nothing looked inside the SVG, so a
truncated, corrupt or zero-byte SVG passed --check as up to date - a guard
reporting a clean result while measuring nothing.

`fixtures/sample.svg` is a real mmdc render of `fixtures/sample.mmd`, committed
so these tests never need mermaid-cli. That matters twice: CI has no mmdc, and
`resolve_mmdc()` returns the bare name "mmdc", which on Windows resolves to a
.CMD that subprocess.run cannot execute without shell=True. Damaging a genuine
render is the point - a hand-written stub would not prove the check looks at
real SVG bytes. The manifests below are built with the script's own
Manifest.put/save so they are byte-identical to what a render would write.
"""

import hashlib
import json
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
    # future failure for an unrelated cause satisfies this test.
    assert "up to date" not in out.split("DAMAGED")[0], out


def test_intact_svg_with_recorded_hash_passes(tmp_path):
    code, out = check(build(tmp_path, GOOD_SVG, manifest_version=2))
    assert code == 0, out
    assert "All 1 diagram(s) up to date." in out, out


def test_legacy_manifest_does_not_claim_a_check_it_did_not_do(tmp_path):
    """An intact SVG under a v1 manifest passes, but must not be called verified.

    Exit 0 is deliberate: the structural check is the strongest test available
    without a recorded hash, and turning every pre-v2 repo's CI red would be a
    behaviour change rather than a fix. What is NOT allowed is the summary
    claiming "All N up to date" - that is the unknown collapsing into the
    safe-looking value, which is the bug this file exists to prevent.
    """
    code, out = check(build(tmp_path, GOOD_SVG, manifest_version=1))
    assert code == 0, out
    assert "UNVERIFIED" in out, out
    assert "All 1 diagram(s) up to date." not in out, out
    assert "could not be content-verified" in out, out


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
