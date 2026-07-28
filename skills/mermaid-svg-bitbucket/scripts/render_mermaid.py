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
import tempfile
from pathlib import Path

# Bump when render settings change in a way that should invalidate every SVG.
RENDER_VERSION = "2"

MANIFEST_NAME = ".mermaid-svg.json"
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
        self.data = {"version": 1, "diagrams": {}}
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
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")


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


def resolve_mmdc() -> list[str]:
    if shutil.which("mmdc"):
        return ["mmdc"]
    if shutil.which("npx"):
        return ["npx", "--yes", "@mermaid-js/mermaid-cli"]
    sys.exit(
        "error: mmdc not found. Install it with:\n"
        "  npm install -g @mermaid-js/mermaid-cli\n"
        "(or make `npx` available so it can be fetched on demand)"
    )


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

    proc = subprocess.run(cmd, capture_output=True, text=True)
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
    svg_path.write_text(svg, encoding="utf-8")


# --------------------------------------------------------------------------- #
# markdown handling
# --------------------------------------------------------------------------- #

def heading_before(text: str, pos: int) -> str | None:
    last = None
    for m in HEADING_RE.finditer(text, 0, pos):
        last = m.group(1).strip()
    return last


def process_markdown(md_path: Path, root: Path, out_dir: Path) -> list[tuple[Path, str, str]]:
    """Extract fenced mermaid blocks to sidecar .mmd files and rewrite the block
    into an image link. Returns (mmd_path, source, alt) for each block found.

    Idempotent: once a block has been replaced by an image link there is no
    fenced block left to match, so re-runs are no-ops for this file.
    """
    text = md_path.read_text(encoding="utf-8")
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
        mmd_path.write_text(normalize(source), encoding="utf-8")

        pieces.append(text[cursor:m.start()])
        pieces.append(f"{m.group('indent')}![{alt}]({rel(md_path, svg_path)})\n")
        cursor = m.end()
        extracted.append((mmd_path, source, alt))

    pieces.append(text[cursor:])
    md_path.write_text("".join(pieces), encoding="utf-8")
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
                    help="verify SVGs are current; do not write anything. Exits 1 if stale.")
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
        if current and not args.force:
            skipped.append(key)
            continue

        try:
            render(mmd, svg, config, puppeteer, args.background)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            failed.append(key)
            continue
        manifest.put(key, hash=want, svg=svg.relative_to(root).as_posix())
        rendered.append(key)
        print(f"  rendered {key} -> {svg.relative_to(root)}")

    # ---- report -----------------------------------------------------------
    if args.check:
        if stale:
            print("Diagrams are out of date:")
            for k in stale:
                print(f"  STALE: {k}")
            print("\nRun scripts/render_mermaid.py and commit the result.")
            return 1
        print(f"All {len(mmd_files)} diagram(s) up to date.")
        return 0

    manifest.prune({m.relative_to(root).as_posix() for m in mmd_files})
    manifest.save()
    print(f"\nrendered: {len(rendered)}  unchanged: {len(skipped)}  failed: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
