#!/usr/bin/env python3
"""Build the crew 1.0 guides -- HTML, DOCX and PDF -- from the Markdown
sources in this directory. Reproduces the commit-cbbdfca2 build (theme
`midnight`, brand `neutral`, LibreOffice on Linux), so a rebuild after any
guide edit is one command rather than a remembered ad hoc recipe.

Markdown -> HTML is python-markdown with `tables`, `fenced_code`, `sane_lists`
and `toc` -- doc-builder has no Markdown pipeline of its own (see
`skills/doc-builder/scripts/house_style.py`'s module docstring). The HTML is
then restyled by `house_style.apply_to_html` (`--profile guide`) exactly the
way a hand-authored page picks up the house stylesheet, and converted to
.docx/.pdf by `render_engine.to_soffice`, which names the renderer on every
line it prints.

Two things this script adds that plain python-markdown does not do for you:

1. **Fence dedent.** `FencedBlockPreprocessor.FENCED_BLOCK_RE`
   (`markdown/extensions/fenced_code.py`) anchors its opening/closing fence on
   `^` with no leading whitespace, so a fence indented under a list item --
   every guide source here writes one that way -- never matches. It falls
   through to the inline `` `code` `` span parser instead, which is the
   defect this build exists to fix: a fenced block rendered as a paragraph of
   body text with the fence's language word leaking into it (`bash cat
   ~/.claude/...`). `dedent_fences` strips the common leading whitespace from
   an indented fence and its body before conversion, which is a no-op for a
   fence that already starts at column 0.
2. **Appendix folding.** Three guides fold a second source in as a trailing
   section (see `README.md`'s "Built artifacts" table): the appendix's own
   headings are demoted one level first, so its top-level heading lands as an
   H2 (or H3, folded under an H2) rather than a second, competing H1.

The extra code-block CSS this script injects (`CODE_BLOCK_CSS`) uses only
BARE element selectors (`pre`, never `pre code`) on purpose: LibreOffice's
HTML importer applies only a bare `.class` or a bare element and drops every
compound or descendant selector silently (see `house_style.table_css`'s
docstring, and `references/word-traps.md`). A descendant selector here would
render in a browser and vanish from the .docx/.pdf with nothing to say so.

Usage:
    build.py                      # every guide, HTML + DOCX + PDF
    build.py --guide quickstart   # just one
    build.py --html-only          # skip the LibreOffice conversion pass
    build.py --check              # is every committed HTML current? writes nothing

`--check` (T-0048) rebuilds every guide's HTML in memory exactly as a build
does and compares it with the committed `crew-1.0-<name>.html`: exit 0 when
all match, 1 naming each stale guide, and 2 when the build cannot run at all
(no `markdown` module, or doc-builder fails to import) -- never 0, because a
check that compared nothing is not "current". DOCX and PDF are not compared:
LibreOffice's output is not byte-stable. CI does not run it (CI's Python has
no `markdown`); `.crew/verify.json` does.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

SRC = pathlib.Path(__file__).resolve().parent
GUIDES_DIR = SRC.parent
REPO_ROOT = SRC.parents[3]
DOC_BUILDER_SCRIPTS = REPO_ROOT / "skills" / "doc-builder" / "scripts"

sys.path.insert(0, str(DOC_BUILDER_SCRIPTS))
# Imported inside `main`, not here, so `--check` can report a missing module as
# "did not run" (exit 2) rather than crash before it has said anything.
house_style = resolve_brand = render_engine = None  # pylint: disable=invalid-name

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "toc"]

# name -> ordered list of source .md files folded into it (parent first).
# Matches README.md's "Built artifacts" table exactly; keep the two in sync.
GUIDES = {
    "quickstart": ["quickstart.md"],
    "daily-workflow": ["daily-workflow.md", "daily-workflow-scope.md"],
    "memory-and-obsidian": ["memory-and-obsidian.md", "memory-recall-proof.md"],
    "working-with-codex": ["working-with-codex.md"],
    "troubleshooting": ["troubleshooting.md", "auto-cycle.md"],
    "guide": ["guide.md"],
    "configuration-reference": ["configuration-reference.md"],
}

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_FENCE_OPEN_RE = re.compile(r"^([ \t]+)(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})(\s+.*)$")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_TAG_RE = re.compile(r"<[^>]+>")

# Bare selectors only -- see the module docstring. Colours come from the
# resolved Palette so the block follows whatever theme/brand was asked for
# rather than a literal baked into this script.
_CODE_BLOCK_CSS = (
    "pre {{ background:{panel}; border:1px solid {grid}; border-radius:3px;\n"
    "      padding:8pt 10pt; margin:8pt 0; overflow-x:auto; white-space:pre; }}\n"
)


def strip_frontmatter(text: str) -> str:
    """Drop a leading `---\\n...\\n---\\n` YAML block, if present. Nothing here
    is rendered -- see the built HTML's own history, where `title`/`subtitle`/
    `status` never reached the page; only the body ever did."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def dedent_fences(text: str) -> str:
    """Dedent every fenced code block (opening fence, body, closing fence) to
    column 0. See the module docstring for why this is necessary rather than
    cosmetic."""
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        m = _FENCE_OPEN_RE.match(line)
        if m:
            indent, fence_char = m.group(1), m.group(2)[0]
            out.append(line[len(indent):])
            i += 1
            while i < n:
                cur = lines[i]
                if cur.startswith(indent):
                    cur = cur[len(indent):]
                out.append(cur)
                i += 1
                stripped = cur.strip()
                if stripped and set(stripped) == {fence_char} and len(stripped) >= 3:
                    break
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def demote_headings(text: str, by: int = 1) -> str:
    """Raise every ATX heading's level by `by` (# -> ##, capped at ######),
    skipping lines inside a fenced block so a `#` in example output is never
    mistaken for a heading. Assumes `dedent_fences` has already run, so every
    fence here starts at column 0."""
    lines = text.split("\n")
    out = []
    in_fence = False
    fence_char = None
    for line in lines:
        stripped = line.strip()
        if stripped[:3] in ("```", "~~~"):
            marker = stripped[0]
            if not in_fence:
                in_fence, fence_char = True, marker
            elif marker == fence_char:
                in_fence = False
            out.append(line)
            continue
        if not in_fence:
            m = _HEADING_RE.match(line)
            if m:
                level = min(len(m.group(1)) + by, 6)
                line = ("#" * level) + m.group(2)
        out.append(line)
    return "\n".join(out)


def build_source(names: list[str]) -> str:
    """The folded Markdown for one guide: the parent verbatim (minus
    frontmatter), then each appendix demoted one level and appended as a
    trailing section."""
    parts = []
    for i, name in enumerate(names):
        text = strip_frontmatter((SRC / name).read_text(encoding="utf-8"))
        text = dedent_fences(text)
        if i > 0:
            text = demote_headings(text, by=1)
        parts.append(text.strip("\n"))
    return "\n\n".join(parts) + "\n"


def title_of(md_text: str) -> str:
    """The document title: the first H1's text, tags-and-all stripped."""
    m = _H1_RE.search(md_text)
    raw = m.group(1).strip() if m else "crew 1.0 guide"
    return _TAG_RE.sub("", raw)


def to_html_document(md_text: str) -> str:
    import markdown  # pylint: disable=import-outside-toplevel
    body = markdown.markdown(md_text, extensions=MD_EXTENSIONS)
    title = title_of(md_text)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n<style></style>\n</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )


def apply_house_style(html_text: str, pal: "house_style.Palette") -> str:
    styled = house_style.apply_to_html(html_text, pal, profile="guide")
    extra = _CODE_BLOCK_CSS.format(panel=pal.panel, grid=pal.grid)
    styled = styled.replace("</style>", extra + "</style>", 1)
    return fix_narrow_columns(styled)


# Quickstart's ten-minute checklist has one narrow numeric column (originally
# "Minutes", shortened to "Min" in the source). Even so, LibreOffice's
# Writer/Web HTML->PDF path (the filter this build actually uses) sizes that
# column to the width of its single-digit body cells and wraps the three-letter
# header into "Mi"/"n" anyway -- measured directly: neither a CSS `width` nor
# `white-space:nowrap`, on the `<th>`, on `<col>`, nor with `table-layout:fixed`,
# changed the render at all. Only the legacy HTML `width` ATTRIBUTE (not a style
# property) on the header cell does. Same family as `house_style.mark_page`'s
# `bgcolor` attribute: a value CSS carries that this converter's importer does
# not honour, restated in the one form it does.
#
# The configuration reference's six-column tables (T-0048) wrapped their short
# columns mid-word the same way ("Laye"/"r"), so its `Setting`, `Layer` and
# `Since` headers get the same attribute. Those three header words appear in
# no other guide, so no other guide's HTML moves.
_NARROW_HEADERS = {"Min": "8%", "Setting": "20%", "Layer": "11%", "Since": "9%"}


def fix_narrow_columns(html_text: str) -> str:
    for header, width in _NARROW_HEADERS.items():
        html_text = html_text.replace(
            f"<th>{header}</th>", f'<th width="{width}">{header}</th>')
    return html_text


def fenced_block_count(md_text: str) -> int:
    """How many fenced blocks `dedent_fences` + python-markdown should see, for
    the pre-count vs. fenced-count check `build_all` prints."""
    dedented = dedent_fences(md_text)
    fences = re.findall(r"^(`{3,}|~{3,})", dedented, re.MULTILINE)
    return len(fences) // 2


def render_html(names: list[str], pal: "house_style.Palette") -> tuple[str, str]:
    """`(markdown, styled html)` for one guide, built in memory."""
    md_text = build_source(names)
    html_text = to_html_document(md_text)
    return md_text, apply_house_style(html_text, pal)


def build_one(name: str, names: list[str], pal: "house_style.Palette",
              html_only: bool) -> None:
    # The whole text exists before the file is opened (root CLAUDE.md,
    # Landmines: `open(p, "w")` truncates at open time).
    md_text, html_text = render_html(names, pal)

    out_html = GUIDES_DIR / f"crew-1.0-{name}.html"
    out_html.write_text(html_text, encoding="utf-8", newline="\n")

    fenced = fenced_block_count(md_text)
    pre_count = len(re.findall(r"<pre>", html_text))
    match = "OK" if pre_count == fenced else "MISMATCH"
    print(f"{name}: {fenced} fenced block(s) in source, {pre_count} <pre> "
          f"in HTML -- {match}", file=sys.stderr)

    print(f"wrote {out_html}")
    if html_only:
        return
    rc = render_engine.to_soffice(str(out_html), want_docx=True, want_pdf=True)
    if rc != 0:
        raise SystemExit(rc)


def check(pal: "house_style.Palette") -> list[str]:
    """The guide names whose committed HTML differs from a fresh in-memory build."""
    stale = []
    for name in sorted(GUIDES):
        _md, html_text = render_html(GUIDES[name], pal)
        out_html = GUIDES_DIR / f"crew-1.0-{name}.html"
        try:
            committed = out_html.read_text(encoding="utf-8")
        except FileNotFoundError:
            committed = None
        if committed != html_text:
            stale.append(name)
    return stale


def _load_builders() -> None:
    global house_style, resolve_brand, render_engine  # pylint: disable=global-statement
    import house_style as _hs  # pylint: disable=import-outside-toplevel
    import resolve_brand as _rb  # pylint: disable=import-outside-toplevel
    import render_engine as _re  # pylint: disable=import-outside-toplevel
    import markdown  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
    house_style, resolve_brand, render_engine = _hs, _rb, _re


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guide", choices=sorted(GUIDES), default=None,
                     help="build only this guide (default: every guide)")
    ap.add_argument("--brand", default="neutral")
    ap.add_argument("--theme", default="midnight")
    ap.add_argument("--html-only", action="store_true",
                     help="write the HTML only; skip the LibreOffice DOCX/PDF pass")
    ap.add_argument("--check", action="store_true",
                     help="compare every committed HTML with a fresh build; write nothing")
    args = ap.parse_args(argv)

    if args.check:
        try:
            _load_builders()
        except ImportError as exc:
            print(f"build.py --check: markdown not importable - the check DID NOT RUN "
                  f"({exc})", file=sys.stderr)
            return 2
        try:
            brand = resolve_brand.resolve(args.brand, theme=args.theme)
            stale = check(house_style.Palette(brand))
        except Exception as exc:  # pylint: disable=broad-except
            print(f"build.py --check: the check DID NOT RUN: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return 2
        for name in stale:
            print(f"stale: crew-1.0-{name}.html - rebuild with "
                  f"python3 docs/guides/crew/src/build.py --guide {name}")
        return 1 if stale else 0

    _load_builders()
    brand = resolve_brand.resolve(args.brand, theme=args.theme)
    pal = house_style.Palette(brand)

    names = [args.guide] if args.guide else sorted(GUIDES)
    for name in names:
        build_one(name, GUIDES[name], pal, args.html_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
