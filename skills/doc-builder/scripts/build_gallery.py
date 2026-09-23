#!/usr/bin/env python3
"""Build the theme gallery: one sample report per built-in theme, a compact
variant, and an index page that previews them side by side.

The gallery ships inside the skill (`assets/themes/gallery/`) so that when
someone asks for a document and has not picked a look, there is something to
SHOW them -- the index, or a single theme's sample -- rather than a list of
names. Every sample is rendered by the same `build_report.build()` the real
pipeline uses, against the neutral brand plus one theme, so a sample can
never look different from what that theme actually produces.

`--check` rebuilds every HTML file in memory and compares it with what is on
disk. The suite runs it, so a CSS or theme change that is not followed by a
gallery rebuild fails the tests instead of shipping previews that lie.

PNG thumbnails are optional (`--png`) and need a Chromium binary: $CHROME,
then chromium / google-chrome on PATH, then a Playwright download under
~/.cache/ms-playwright. The HTML gallery works without them; the index shows
colour swatches either way.

Stdlib only.

Usage:
    build_gallery.py            # rewrite the HTML gallery
    build_gallery.py --png      # ... and the PNG thumbnails
    build_gallery.py --check    # exit 1 if any gallery HTML is stale
"""

from __future__ import annotations

import argparse
import glob
import html
import os
import shutil
import subprocess
import sys
import tempfile

import build_report
import house_style
import resolve_brand

GALLERY_DIR = os.path.join(resolve_brand.THEMES_DIR, "gallery")
# (file stem, theme, density). The compact variant is shown once, on the
# default theme: density is independent of colour, so one sample makes the
# point and the rest would be noise.
COMPACT_SAMPLE = ("professional-compact", "professional", "compact")


def _brand(theme, density=None):
    return resolve_brand.resolve("neutral", announce=False, theme=theme, density=density)


def samples():
    """[(stem, theme, density, label, description)] in display order."""
    out = [(name, name, None, label, desc) for name, label, desc in resolve_brand.list_themes()]
    stem, theme, density = COMPACT_SAMPLE
    label = next((lab for n, lab, _ in resolve_brand.list_themes() if n == theme), theme)
    out.append((stem, theme, density, f"{label} + Compact",
                "Any theme with --density compact: tighter cells, smaller masthead."))
    return out


def sample_html(theme, density):
    return build_report.build(build_report.EXAMPLE, _brand(theme, density))


def _swatches(pal):
    rows = [("Band", pal.navy), ("Heading", pal.heading), ("Table head", pal.table_head),
            ("Zebra", pal.zebra), ("Page", pal.page), ("Accent", pal.accent)]
    cells = "".join(
        f'<td class="sw"><div class="chip" style="background:{hexv}"></div>'
        f'<div class="swl">{html.escape(name)}<br>{hexv}</div></td>'
        for name, hexv in rows)
    return f'<table class="swatches"><tr>{cells}</tr></table>'


def index_html():
    cards = []
    for stem, theme, density, label, desc in samples():
        pal = house_style.Palette(_brand(theme, density))
        png = f"{stem}.png"
        thumb = (f'<a href="{stem}.html"><img class="thumb" src="{png}" alt="{html.escape(label)} preview"></a>'
                 if os.path.isfile(os.path.join(GALLERY_DIR, png)) else "")
        flags = f"--theme {theme}" + (f" --density {density}" if density else "")
        cards.append(
            '<div class="card">'
            f'<h2><a href="{stem}.html">{html.escape(label)}</a></h2>'
            f'<p class="desc">{html.escape(desc)}</p>'
            f"{thumb}{_swatches(pal)}"
            f'<p class="cmd"><code>{html.escape(flags)}</code></p>'
            "</div>")
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
        "<title>doc-builder themes</title>\n<style>\n"
        "body { font-family:'Segoe UI',Calibri,Arial,sans-serif; margin:0; background:#F3F4F6;"
        " color:#111827; }\n"
        ".wrap { max-width:1280px; margin:0 auto; padding:24px 16px 48px; }\n"
        "h1 { margin:0 0 4px; font-size:24px; }\n"
        ".lead { color:#4B5563; margin:0 0 20px; }\n"
        ".grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:16px; }\n"
        ".card { background:#FFFFFF; border:1px solid #D1D5DB; border-radius:8px; padding:14px; }\n"
        ".card h2 { margin:0 0 4px; font-size:17px; }\n"
        ".card h2 a { color:#111827; text-decoration:none; }\n"
        ".desc { margin:0 0 10px; color:#4B5563; font-size:13px; min-height:34px; }\n"
        ".thumb { width:100%; border:1px solid #D1D5DB; display:block; margin-bottom:10px; }\n"
        ".swatches { border-collapse:collapse; width:100%; }\n"
        ".sw { text-align:center; padding:2px; vertical-align:top; }\n"
        ".chip { height:26px; border:1px solid #9CA3AF; border-radius:4px; }\n"
        ".swl { font-size:10px; color:#4B5563; margin-top:3px; }\n"
        ".cmd { margin:10px 0 0; font-size:12px; }\n"
        "code { background:#F3F4F6; padding:2px 6px; border-radius:4px; }\n"
        "</style></head><body><div class=\"wrap\">\n"
        "<h1>doc-builder themes</h1>\n"
        "<p class=\"lead\">Each sample is the same report rendered with the neutral brand and one "
        "theme. With a brand pack installed, the theme sets the colours and the brand keeps its "
        "logo, fonts and footer. Pass the flags shown to <code>build_report.py</code>, "
        "<code>build_sop.py</code> or <code>house_style.py</code>.</p>\n"
        f"<div class=\"grid\">\n{chr(10).join(cards)}\n</div>\n</div></body></html>\n"
    )


def expected_files():
    """{filename: text} for every HTML file the gallery should contain."""
    files = {f"{stem}.html": sample_html(theme, density)
             for stem, theme, density, _, _ in samples()}
    files["index.html"] = index_html()
    return files


def find_chrome():
    cands = [os.environ.get("CHROME")] + [shutil.which(n) for n in (
        "chromium", "chromium-browser", "google-chrome", "chrome")]
    cands += sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium*/chrome-*/chrome*")), reverse=True)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def render_png(chrome, html_path, png_path):
    # A snap-packaged Chromium cannot read or write outside $HOME, so render from
    # a private temp directory and copy the result back.
    with tempfile.TemporaryDirectory(dir=os.path.expanduser("~")) as tmp:
        src = os.path.join(tmp, "page.html")
        shutil.copyfile(html_path, src)
        out = os.path.join(tmp, "shot.png")
        subprocess.run([chrome, "--headless", "--no-sandbox", "--hide-scrollbars",
                        "--window-size=1100,820", f"--screenshot={out}",
                        "file://" + src], check=False, capture_output=True, timeout=120)
        if not os.path.isfile(out) or os.path.getsize(out) == 0:
            return False
        shutil.copyfile(out, png_path)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="compare the gallery on disk with a fresh build; exit 1 on drift")
    ap.add_argument("--png", action="store_true", help="also render PNG thumbnails")
    args = ap.parse_args(argv)

    files = expected_files()
    if args.check:
        stale = []
        for name, text in files.items():
            path = os.path.join(GALLERY_DIR, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    if fh.read() != text:
                        stale.append(name)
            except OSError:
                stale.append(name)
        if stale:
            print("gallery is stale: " + ", ".join(stale)
                  + " -- run scripts/build_gallery.py --png", file=sys.stderr)
            return 1
        print(f"gallery current ({len(files)} files)")
        return 0

    os.makedirs(GALLERY_DIR, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(GALLERY_DIR, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {os.path.join(GALLERY_DIR, name)}")

    if args.png:
        chrome = find_chrome()
        if not chrome:
            print("no Chromium found ($CHROME, PATH, ~/.cache/ms-playwright) -- "
                  "PNG thumbnails NOT rendered", file=sys.stderr)
            return 1
        for stem, *_ in samples():
            png = os.path.join(GALLERY_DIR, f"{stem}.png")
            if not render_png(chrome, os.path.join(GALLERY_DIR, f"{stem}.html"), png):
                print(f"FAILED to render {png} with {chrome}", file=sys.stderr)
                return 1
            print(f"wrote {png}")
        # The index embeds thumbnails only when they exist, so rewrite it now.
        with open(os.path.join(GALLERY_DIR, "index.html"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(index_html())
    return 0


if __name__ == "__main__":
    sys.exit(main())
