#!/usr/bin/env python3
"""
Render Mermaid diagrams to Bitbucket-Cloud-safe SVG.

Bitbucket Cloud does not render ```mermaid fenced blocks (BCLOUD-21675). This
script pre-renders diagrams to committed SVG files and rewrites Markdown to
reference them as images.

Two kinds of input:
  1. Standalone .mmd / .mermaid files       -> rendered in place (foo.mmd -> foo.svg)
  2. ```mermaid blocks inside .md files     -> source extracted to a sidecar .mmd
                                               under --out-dir, block replaced by
                                               an image link

A manifest (.mermaid-svg.json) records the hash of every diagram source so
re-runs skip unchanged files and so --check can verify staleness without
launching Chromium.

Stdlib only. Requires `mmdc` (@mermaid-js/mermaid-cli) on PATH for rendering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Bump when render settings change in a way that should invalidate every SVG.
RENDER_VERSION = "2"

MANIFEST_NAME = ".mermaid-svg.json"
# 2 = entries carry svgHash, so --check can verify the SVG and not just its
#     existence. A version-1 manifest predates that and cannot be content-checked.
MANIFEST_VERSION = 2
DEFAULT_OUT_DIR = "docs/diagrams"
DEFAULT_EXCLUDES = {".git", "node_modules", ".venv", "venv", "vendor", "dist", "build", ".tox"}

FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>```|~~~)[ \t]*mermaid[ \t]*\r?\n"
    r"(?P<body>.*?)"
    r"^(?P=indent)(?P=fence)[ \t]*\r?$\n?",
    re.MULTILINE | re.DOTALL,
)
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def normalize(src: str) -> str:
    """Whitespace-insensitive form of a diagram source, for stable hashing."""
    lines = [ln.rstrip() for ln in src.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def digest(src: str, config_fingerprint: str) -> str:
    h = hashlib.sha256()
    h.update(RENDER_VERSION.encode())
    h.update(b"\x00")
    h.update(config_fingerprint.encode())
    h.update(b"\x00")
    h.update(normalize(src).encode())
    return "sha256:" + h.hexdigest()


def svg_digest(path: Path) -> str:
    """Hash the SVG's content, so --check can tell whether the file on disk is
    still the file that was rendered. Taken AFTER postprocess(), which rewrites
    the SVG - hashing before it would record a digest the file never has.

    Line endings are normalized (CRLF/CR -> LF) before hashing, not just at
    write time. postprocess()'s write is pinned to newline="\\n", which makes
    what THIS script writes host-independent, but it does not reach a file
    that gets its line endings rewritten afterward - by git itself, on
    checkout, if a Windows clone has core.autocrlf=true and no .gitattributes
    entry marks *.svg as binary/-text (none exists in this repo as of the fix
    that added this comment). A --check run there reads back CRLF bytes for
    an SVG whose recorded svgHash was computed from the LF bytes this script
    wrote and committed, and reports DAMAGED for a diagram that has not
    changed. Normalizing here closes that: the digest is computed from the
    same logical content regardless of which line-ending convention the bytes
    on disk happen to carry when read. It does not make the committed SVG's
    raw bytes reproducible across platforms - see TODO.md - only the digest
    comparison, which is what --check actually judges."""
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()[:16]


def svg_structure_ok(path: Path) -> tuple[bool, str]:
    """A cheap integrity check that needs no recorded hash, for SVGs written by a
    version of this script that did not record one. It separates the two pre-v2
    outcomes - a file that is provably broken (DAMAGED) from one that is merely
    unproven (UNVERIFIED) - and it must stay honest about what it cannot see: a
    well-formed SVG with wrong contents passes here. Passing is why UNVERIFIED
    still exits 1; it is the absence of evidence, not evidence."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return False, f"unreadable ({exc})"
    if not raw.strip():
        return False, "file is empty"
    if b"<svg" not in raw:
        return False, "no <svg element - not an SVG at all"
    if not raw.rstrip().endswith(b"</svg>"):
        return False, "truncated - no closing </svg> tag"
    return True, ""


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].rstrip("-")


def rel(from_file: Path, to_file: Path) -> str:
    return Path(os.path.relpath(to_file, from_file.parent)).as_posix()


def walk(root: Path, suffixes: set[str]) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDES and not d.startswith(".")]
        for name in filenames:
            if Path(name).suffix.lower() in suffixes:
                found.append(Path(dirpath) / name)
    return sorted(found)


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #

class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"version": MANIFEST_VERSION, "diagrams": {}}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
                self.data.setdefault("diagrams", {})
            except (json.JSONDecodeError, OSError) as exc:
                print(f"warn: ignoring unreadable manifest {path}: {exc}", file=sys.stderr)

    def get(self, key: str) -> dict | None:
        return self.data["diagrams"].get(key)

    def put(self, key: str, **fields) -> None:
        self.data["diagrams"][key] = fields

    def prune(self, live_keys: set[str]) -> list[str]:
        dead = [k for k in self.data["diagrams"] if k not in live_keys]
        for k in dead:
            del self.data["diagrams"][k]
        return dead

    def save(self) -> None:
        ordered = dict(sorted(self.data["diagrams"].items()))
        self.data["diagrams"] = ordered
        # newline="\n": without it, write_text translates '\n' to os.linesep at
        # write time - CRLF on Windows - so a manifest rendered there differs
        # byte-for-byte from one rendered on Linux for identical JSON content.
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8",
                              newline="\n")


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #

def find_config(explicit: str | None, root: Path) -> Path:
    """Locate mermaid-config.json.

    People vendor this script into a repo in whatever layout suits them, so try
    the plausible spots rather than insisting on one.
    """
    here = Path(__file__).resolve().parent
    if explicit:
        p = Path(explicit).resolve()
        if not p.exists():
            sys.exit(f"error: --config not found: {p}")
        return p
    candidates = [
        root / "assets" / "mermaid-config.json",
        root / ".mermaid" / "mermaid-config.json",
        root / "mermaid-config.json",
        here.parent / "assets" / "mermaid-config.json",
        here / "mermaid-config.json",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    sys.exit(
        "error: mermaid-config.json not found. Looked in:\n  "
        + "\n  ".join(str(c) for c in candidates)
        + "\nPass one with --config, or copy the skill's assets/mermaid-config.json\n"
        "into the repo. Do not just let mmdc use its defaults: they emit\n"
        "<foreignObject> labels, which are invisible in Bitbucket."
    )


def find_puppeteer_config(explicit: str, root: Path) -> Path | None:
    here = Path(__file__).resolve().parent
    for c in [Path(explicit), root / "scripts" / "puppeteer-config.json",
              here / "puppeteer-config.json"]:
        if c.exists():
            return c.resolve()
    return None


MMDC_MISSING = (
    "error: mmdc not found. Install it with:\n"
    "  npm install -g @mermaid-js/mermaid-cli\n"
    "(or make `npx` available so it can be fetched on demand)"
)


def resolve_mmdc() -> list[str]:
    """Return the launcher argv, using the path `which` resolved.

    The return value is the point, not its truthiness. This used to test
    `if shutil.which("mmdc")` and then pass the bare name "mmdc" to subprocess.
    On Windows mermaid-cli installs as `mmdc.cmd`, and `shutil.which` finds it
    because it consults PATHEXT; `subprocess` without a shell does not, so the
    bare name raised an uncaught WinError 2 on a machine where mermaid-cli was
    installed - and the message below, written for exactly that moment, never
    printed, because `which` had succeeded. A resolved absolute path to the
    .cmd runs. Both branches did it, so both are fixed.
    """
    mmdc = shutil.which("mmdc")
    if mmdc:
        return [mmdc]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", "@mermaid-js/mermaid-cli"]
    sys.exit(MMDC_MISSING)


def render(mmd_path: Path, svg_path: Path, config: Path, puppeteer: Path | None,
           background: str) -> None:
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = resolve_mmdc() + [
        "--input", str(mmd_path),
        "--output", str(svg_path),
        "--outputFormat", "svg",
        "--configFile", str(config),
        "--backgroundColor", background,
        "--quiet",
    ]
    if puppeteer and puppeteer.exists():
        cmd += ["--puppeteerConfigFile", str(puppeteer)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        # The launcher resolved on PATH and still could not be spawned - a shim
        # pointing at a deleted install, a wrong-architecture binary, a file
        # mode that lost its execute bit. From the user's side that is a
        # missing tool, so it has to end in the install message; an OSError
        # escaping here is an uncaught traceback that loses it entirely, which
        # is the defect this whole function was fixed for. sys.exit rather than
        # RuntimeError on purpose: the tool is unusable for every diagram, not
        # just this one, so retrying the rest only buries the message.
        sys.exit(f"{MMDC_MISSING}\n\n(resolved `{cmd[0]}` but could not run it: {exc})")
    if proc.returncode != 0 or not svg_path.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"mmdc failed for {mmd_path}:\n{detail}")

    postprocess(svg_path)


def postprocess(svg_path: Path) -> None:
    """Harden the SVG for Bitbucket's <img> rendering path.

    Bitbucket embeds Markdown images in an <img> tag. A browser rendering an
    SVG that way runs it in an isolated, script-free context, which means:
      - <foreignObject> content is not painted -> every label vanishes. The
        mermaid config sets htmlLabels:false to avoid producing any, but a
        diagram can re-enable it via an inline %%{init}%% directive, so check.
      - width/height must be intrinsic or the image collapses in some layouts.
      - mermaid's default `max-width` inline style makes the image render at
        its natural size only; harmless, but we normalize it.
    """
    svg = svg_path.read_text(encoding="utf-8")

    if "<foreignObject" in svg:
        raise RuntimeError(
            f"{svg_path} contains <foreignObject>; labels would be invisible in "
            f"Bitbucket. Remove any %%{{init: {{'flowchart': {{'htmlLabels': true}}}}}}%% "
            f"directive from the source."
        )

    m = re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', svg)
    if m and not re.search(r"<svg[^>]*\swidth=", svg):
        w, h = float(m.group(1)), float(m.group(2))
        svg = svg.replace("<svg ", f'<svg width="{w:.0f}" height="{h:.0f}" ', 1)

    svg = re.sub(r'(<svg[^>]*?)\sstyle="max-width:[^"]*"', r"\1", svg, count=1)
    # newline="\n": write_text's default (newline=None) translates '\n' in
    # `svg` to os.linesep at write time - CRLF on Windows. This pin only
    # guarantees that a render done by THIS script writes the same bytes
    # regardless of which host runs it - i.e. render() on Linux and render()
    # on Windows produce byte-identical SVGs for the same source. It does NOT,
    # by itself, guarantee that --check later reads those same bytes back: a
    # file this pin wrote as LF and committed can still be checked out as CRLF
    # elsewhere (git core.autocrlf, no .gitattributes entry for *.svg here),
    # and reading that back through a naive byte-hash would report DAMAGED for
    # an unchanged diagram. svg_digest() normalizes line endings before
    # hashing for exactly that reason - see its docstring - so the two fixes
    # together, not this pin alone, are what make --check content-stable
    # across hosts.
    svg_path.write_text(svg, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# markdown handling
# --------------------------------------------------------------------------- #

def heading_before(text: str, pos: int) -> str | None:
    last = None
    for m in HEADING_RE.finditer(text, 0, pos):
        last = m.group(1).strip()
    return last


def _normalize_with_offsets(raw_text: str) -> tuple[str, list[int]]:
    """Collapse every line ending in `raw_text` to '\\n' - the same
    transformation `read_text()` performs on read - while recording, for
    every character of the result, the index in `raw_text` it came from.

    `offsets[i]` is where `normalized[i]` originated; `offsets[len(normalized)]`
    is a sentinel equal to `len(raw_text)`, so `raw_text[offsets[a]:offsets[b]]`
    always slices out exactly the original bytes - CRLF, LF, CR or a missing
    trailing newline - that a span `[a, b)` of the normalized text stands for.

    process_markdown() needs both forms: `normalized` for FENCE_RE/HEADING_RE
    matching, unchanged from before; `offsets` so it can slice pass-through
    Markdown out of `raw_text` instead of `normalized` and so preserve every
    untouched line's own original terminator - rather than collapsing the
    whole file to one convention, which is the bug this replaced (a single
    CRLF line used to convert every OTHER line in the file to CRLF too).
    """
    out: list[str] = []
    offsets: list[int] = []
    i, n = 0, len(raw_text)
    while i < n:
        c = raw_text[i]
        if c == "\r":
            offsets.append(i)
            out.append("\n")
            i += 2 if (i + 1 < n and raw_text[i + 1] == "\n") else 1
        else:
            offsets.append(i)
            out.append(c)
            i += 1
    offsets.append(n)
    return "".join(out), offsets


def process_markdown(md_path: Path, root: Path, out_dir: Path) -> list[tuple[Path, str, str]]:
    """Extract fenced mermaid blocks to sidecar .mmd files and rewrite the block
    into an image link. Returns (mmd_path, source, alt) for each block found.

    Idempotent: once a block has been replaced by an image link there is no
    fenced block left to match, so re-runs are no-ops for this file.

    Every line this function does not touch keeps its own original line
    ending exactly - CRLF, LF, bare CR, or no trailing newline at all on the
    file's last line - because pass-through spans are sliced out of the raw
    bytes via `_normalize_with_offsets`'s offset map, not out of the
    LF-collapsed text used for matching. The one line this function DOES
    write - the inserted `![alt](path)` image link replacing each fenced
    block - takes the terminator that already ended the fence's closing line,
    so it blends into its immediate neighbours instead of imposing a
    file-wide convention on lines nobody asked to change.
    """
    raw_text = md_path.read_bytes().decode("utf-8")
    text, offsets = _normalize_with_offsets(raw_text)
    matches = list(FENCE_RE.finditer(text))
    if not matches:
        return []

    extracted: list[tuple[Path, str, str]] = []
    pieces: list[str] = []
    cursor = 0

    for i, m in enumerate(matches, start=1):
        source = m.group("body")
        heading = heading_before(text, m.start())
        alt = heading or f"{md_path.stem} diagram {i}"
        stem = f"{slugify(md_path.stem)}-{i:02d}"
        if heading:
            stem += f"-{slugify(heading, 30)}"
        mmd_path = out_dir / f"{stem}.mmd"
        svg_path = mmd_path.with_suffix(".svg")

        mmd_path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": normalize() already strips \r out of `source`, but an
        # unpinned write_text would just put CRLF back on Windows at write
        # time, undoing that work.
        mmd_path.write_text(normalize(source), encoding="utf-8", newline="\n")

        pieces.append(raw_text[offsets[cursor]:offsets[m.start()]])
        if m.end() > 0 and text[m.end() - 1] == "\n":
            # The regex's trailing `\n?` consumed the closing fence line's own
            # terminator; recover its exact original bytes so the inserted
            # line matches it instead of forcing "\n".
            local_terminator = raw_text[offsets[m.end() - 1]:offsets[m.end()]]
        else:
            # The fence is the last content in the file, with no trailing
            # newline in the original - match that too, rather than gaining
            # one the file never had.
            local_terminator = ""
        pieces.append(f"{m.group('indent')}![{alt}]({rel(md_path, svg_path)})" + local_terminator)
        cursor = m.end()
        extracted.append((mmd_path, source, alt))

    pieces.append(raw_text[offsets[cursor]:])
    result = "".join(pieces)
    # newline="": `result` is assembled entirely from raw_text slices (each
    # carrying its own original terminator verbatim) plus the one
    # locally-terminator-matched line above - it is already exactly the bytes
    # this function wants on disk. Any translation here, including
    # write_text's own newline=None default, would overwrite line endings
    # this function went out of its way to preserve.
    md_path.write_text(result, encoding="utf-8", newline="")
    print(f"  rewrote {md_path.relative_to(root)} ({len(extracted)} block(s) extracted)")
    return extracted


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=["."],
                    help="files or directories to process (default: current directory)")
    ap.add_argument("--root", default=".", help="repo root; manifest lives here")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                    help=f"where extracted .mmd/.svg from Markdown go (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--config", default=None,
                    help="mermaid config JSON (default: search assets/, .mermaid/, repo root)")
    ap.add_argument("--puppeteer-config", default=str(here / "puppeteer-config.json"))
    ap.add_argument("--background", default="#ffffff",
                    help="SVG background; keep it opaque so diagrams stay legible "
                         "against Bitbucket dark mode (default: #ffffff)")
    ap.add_argument("--check", action="store_true",
                    help="verify SVGs are current; do not write anything. Exits 1 if any "
                         "diagram is stale, damaged, or could not be content-verified.")
    ap.add_argument("--force", action="store_true", help="re-render even if the hash matches")
    ap.add_argument("--no-rewrite", action="store_true",
                    help="only render standalone .mmd files; leave Markdown untouched")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = (root / args.out_dir).resolve()
    config = find_config(args.config, root)
    puppeteer = find_puppeteer_config(args.puppeteer_config, root)
    manifest = Manifest(root / MANIFEST_NAME)

    config_fp = hashlib.sha256(config.read_bytes()).hexdigest()[:16] + ":" + args.background

    # ---- collect inputs ---------------------------------------------------
    md_files: list[Path] = []
    mmd_files: list[Path] = []
    for raw in args.paths:
        p = Path(raw).resolve()
        if p.is_dir():
            md_files += walk(p, {".md"})
            mmd_files += walk(p, {".mmd", ".mermaid"})
        elif p.suffix.lower() == ".md":
            md_files.append(p)
        elif p.suffix.lower() in {".mmd", ".mermaid"}:
            mmd_files.append(p)
        else:
            print(f"warn: skipping unsupported file {p}", file=sys.stderr)

    # ---- extract from Markdown -------------------------------------------
    if not args.no_rewrite:
        for md in md_files:
            if args.check:
                if FENCE_RE.search(md.read_text(encoding="utf-8")):
                    print(f"STALE: {md.relative_to(root)} still has an unrendered ```mermaid block")
                    return 1
                continue
            for mmd, _src, _alt in process_markdown(md, root, out_dir):
                if mmd not in mmd_files:
                    mmd_files.append(mmd)

    mmd_files = sorted(set(mmd_files))
    if not mmd_files:
        print("No diagrams found.")
        return 0

    # ---- render -----------------------------------------------------------
    stale, rendered, skipped, failed = [], [], [], []
    damaged: list[tuple[str, str]] = []
    unverified: list[str] = []
    for mmd in mmd_files:
        key = mmd.relative_to(root).as_posix()
        svg = mmd.with_suffix(".svg")
        want = digest(mmd.read_text(encoding="utf-8"), config_fp)
        have = manifest.get(key) or {}
        current = have.get("hash") == want and svg.exists()

        if args.check:
            if not current:
                stale.append(key)
                continue
            # The source hash matching only says the .mmd has not changed since
            # the SVG was rendered. It says nothing about the SVG, and until
            # manifest v2 nothing here looked: a truncated or zero-byte SVG
            # passed --check as current, because the only test applied to it was
            # svg.exists(). Look at the file.
            recorded = have.get("svgHash")
            if recorded:
                if svg_digest(svg) != recorded:
                    damaged.append((key, "SVG does not match what was rendered "
                                         "from this source"))
                continue
            ok, why = svg_structure_ok(svg)
            if not ok:
                damaged.append((key, why))
            else:
                unverified.append(key)
            continue
        if current and not args.force:
            skipped.append(key)
            continue

        try:
            render(mmd, svg, config, puppeteer, args.background)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            failed.append(key)
            continue
        manifest.put(key, hash=want, svg=svg.relative_to(root).as_posix(),
                     svgHash=svg_digest(svg))
        rendered.append(key)
        print(f"  rendered {key} -> {svg.relative_to(root)}")

    # ---- report -----------------------------------------------------------
    if args.check:
        # One failure block for all three findings. An earlier shape returned on
        # stale-or-damaged BEFORE the unverified section ran, so the count of
        # what could not be checked vanished from the output whenever anything
        # else was also wrong - the same "unknown collapses into a tidier
        # answer" bug in a smaller costume. Print every section, then exit once.
        if stale or damaged or unverified:
            if stale:
                print("Diagrams are out of date:")
                for k in stale:
                    print(f"  STALE: {k}")
            if damaged:
                print("Diagrams whose SVG on disk is damaged:")
                for k, why in damaged:
                    print(f"  DAMAGED: {k} - {why}")
            if unverified:
                print("Diagrams that could not be content-verified:")
                for k in unverified:
                    print(f"  UNVERIFIED: {k} - no svgHash recorded "
                          f"(manifest predates version {MANIFEST_VERSION})")
            verified = len(mmd_files) - len(stale) - len(damaged) - len(unverified)
            print(f"\n{verified} diagram(s) verified; {len(stale)} stale, "
                  f"{len(damaged)} damaged, {len(unverified)} unverified.")
            if stale or damaged:
                print("Run scripts/render_mermaid.py and commit the result.")
            if unverified:
                # UNVERIFIED is a different finding from DAMAGED and the text has
                # to keep them apart: nothing here says the SVG is wrong, only
                # that no recorded hash exists to say it is right. Exiting 1 on
                # that is the point - a green CI line meaning less than its
                # reader assumes is the defect --check was fixed for. The red is
                # one-time, and the command that ends it is named here.
                print("UNVERIFIED is not DAMAGED. These SVGs passed a structural "
                      "check - non-empty, an <svg element, a closing tag - and "
                      "nothing says they are wrong; what is missing is a recorded "
                      "hash to compare them against, so nothing says they are "
                      "right either.")
                print("Run scripts/render_mermaid.py --force once to re-render "
                      "and record their hashes (--force is required: the source "
                      "hash already matches, so a plain run would skip them). "
                      "They pass from then on.")
            return 1
        print(f"All {len(mmd_files)} diagram(s) up to date.")
        return 0

    manifest.prune({m.relative_to(root).as_posix() for m in mmd_files})
    manifest.save()
    print(f"\nrendered: {len(rendered)}  unchanged: {len(skipped)}  failed: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
