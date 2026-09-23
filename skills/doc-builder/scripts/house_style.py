#!/usr/bin/env python3
"""The house stylesheet, and the heading case that goes with it -- the ONE
place doc-builder's visual defaults live, for every path that emits HTML.

Until this module existed the defaults were report-path only: the table grid,
the header shading, the zebra rows, the meta-table key shading and the
summary-card panels all sat inside `build_report.stylesheet()`, already
palette-parameterised and already correct, and nothing but `build_report.py`
could reach them. A hand-authored page -- a narrative guide, a runbook, an
architecture write-up -- had no way to ASK for them, so whoever wrote one
copied a palette literal out of a doc and it was neutral forever. That is
exactly what happened to `docs/guides/*.html`: every one carries the neutral
`#1F4E79` and not one carries the installed pack's navy, while every one DOES
carry the print rules, because the print rules were prose a person could copy
and the brand was not. See `crew-house-style/SKILL.md` -- "the rules below
landed and the brand still didn't, because a hand-written path never calls
`resolve_brand.py`."

So: the defaults live here, they take a resolved brand, and there is a command
that emits them. Nothing hand-authored needs a hex literal again.

TWO PROFILES, ONE CONTRACT
--------------------------
`report` is what `build_report.py` emits -- byte-for-byte what it emitted
before this module was extracted; a test asserts that equality so the CSS can
never be forked into two copies that drift.

`guide` is for a hand-authored narrative page: prose sections past H2, bullet
lists, inline `<code>`, callout boxes, and a document page margin rather than a
centred web column. It carries NO masthead, because a hand-written guide has a
plain `<h1>` and not a navy band.

Both carry the contract, from the same functions, with only the selector and
the table-layout differing:

    table_css()   the grid, and the header shading, and the zebra rows
    meta_css()    the meta table, and its shaded key column
    cards_css()   the summary-card panels
    chip_css()    the severity chips
    print_css()   the page-break rules

Every rule obeys `references/word-traps.md` the same as the report path does:
literal hex and never `var()`, grouped selectors and never two class names on
one element, real `<thead>`, zebra as an explicit class. A guide that is later
converted to .docx through the same `convert()` gets the same fidelity.

HEADING CASE
------------
`title_case()` is applied by every path that emits a heading, so a heading is
cased once, mechanically, rather than by whoever typed it. A naive
`str.title()` is wrong here and is never used: it lowercases interior capitals,
turning PowerShell into Powershell, SOP into Sop and macOS into Macos, and this
repository's prose is full of such tokens. See the docstring on `title_case`
for the preserve rule.

Stdlib only.

Usage:
    house_style.py                                  # the report CSS, neutral
    house_style.py --brand solomon --profile guide  # the guide CSS, Solomon
    house_style.py --apply page.html --out out.html --profile guide
    house_style.py --title-case "the powershell SOP for macOS"
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

import resolve_brand


# --------------------------------------------------------------------------
# The palette
# --------------------------------------------------------------------------

class Palette:
    """The report colours of one brand pack, as attributes the stylesheet
    interpolates. Literal hex, never var(). See word-traps.md rule 1: `var()`
    does not degrade, it drops the whole declaration, so
    `background:var(--x); color:#fff` renders white on white."""

    def __init__(self, brand):
        r = brand.report
        self.navy = r["navy"]
        self.navy_dark = r["navy_dark"]
        self.accent = r["accent"]
        self.org_ink = r["org_ink"]
        self.classification = r["classification"]
        self.ink = r["ink"]
        self.muted = r["muted"]
        self.grid = r["grid"]
        self.zebra = r["zebra"]
        self.table_head = r["table_head"]
        self.table_head_ink = r["table_head_ink"]
        self.table_border = r["table_border"]
        self.row = r["row"]
        self.page = r["page"]
        # Headings, the lede rule and card numbers follow the band colour unless
        # a theme separates them -- a dark-page theme must, because a navy
        # heading on a near-black page is unreadable.
        self.heading = r.get("heading") or self.navy
        self.title_ink = r["title_ink"]
        self.handling_bg = r["handling_bg"]
        self.handling_ink = r["handling_ink"]
        self.d = dict(r["density"])
        self.panel = r["panel"]
        self.rule = r["rule"]
        self.font_stack = brand.fonts["report_stack"]
        # (chip background, chip text) per severity. `unverified` is its own
        # severity on purpose: a check that could not run is not a check that
        # passed, and rendering the two alike is lying by omission.
        self.severities = {k: tuple(v) for k, v in r["severity"].items()}
        # The masthead band (`.mast-band`) is filled NAVY, so the wordmark
        # that belongs there is the one measured to read on a dark background
        # - `logo_for("dark")`, never `"light"`. Getting this backwards is
        # invisible in the way a broken <img> is not: the logo would be the
        # same colour as the band it sits on. See `resolve_brand.Brand.logo_for`.
        self.logo_src = logo_uri(brand.logo_for("dark"))


def logo_uri(path):
    """`path` (from resolve_brand, already absolute) as a `file://` URI for an
    `<img src>`, or None.

    None either way a pack has no logo configured (`path` is falsy) or the
    configured file is not actually on THIS machine - `os.path.isfile` is the
    same "NOT FOUND on this machine" check `resolve_brand.py --list` already
    applies to `masters_dir`/`assets_dir`. A document renders fine with no
    logo; it must not render with a broken image reference instead.
    """
    if not path:
        return None
    if not os.path.isfile(path):
        print(f"brand: note: logo configured but not found on this machine: {path} "
              "-- rendering without one", file=sys.stderr)
        return None
    return pathlib.Path(path).resolve().as_uri()


# --------------------------------------------------------------------------
# The contract blocks. Both profiles call these, so there is exactly one copy.
# --------------------------------------------------------------------------

def table_css(pal: Palette, sel: str = "table.data", layout: str = "fixed",
              cell_scope: str | None = None) -> str:
    """The table grid, the header shading and the zebra rows.

    Every cell carries a solid `table_border` edge (black in neutral) and the
    header row is `table_head` fill with `table_head_ink` text (black/white in
    neutral) -- high contrast on screen and when printed in greyscale, where a
    pale grid and a mid-navy header both wash out.

    `sel` is the table selector. The report path writes `<table class="data">`
    because the same page also carries layout tables -- the masthead, the meta
    pairs, the cards -- that must NOT pick these rules up. A hand-authored
    guide writes plain `<table>` and every table on the page is a data table.

    `cell_scope` prefixes the CELL selectors, and defaults to `sel`. A guide
    passes "" so the cells are selected by bare element name, and that is a
    measured requirement, not a tidiness preference: LibreOffice's HTML import
    applies `th {{ background:#1F4E79 }}` and DROPS `table.z th {{ background }}`
    -- both measured on soffice 26.2.5.2 against a two-table probe, where the
    scoped rule's colour never appeared and the bare rule's did. The guides
    used bare `th` before doc-builder owned their CSS, so scoping the cells
    would have silently removed the header shading from every one of them
    on the .docx/.pdf path while leaving the browser unchanged. Same family as
    word-traps.md rules 3 and 4: the SELECTOR SHAPE, not the declaration.
    `SKILL.md` already states the general rule -- LibreOffice "applies only a
    `.class` or a bare element - and silently drops every compound or
    descendant one" -- so the probe confirmed documented behaviour rather than
    discovering it; it is recorded here because that sentence is a page away
    from the line that has to obey it.

    The report path keeps its scope. It has to -- bare `td` there would shade
    and border the masthead's own cells -- and it already loses this block
    under LibreOffice for the same reason, which `render_engine` documents and
    Word (the reference renderer) does not do.

    `layout` is separate from the contract on purpose. `table-layout:fixed`
    is only correct where the builder also emits a `<colgroup>` with measured
    widths (`build_report.column_widths`); applied to a hand-written table with
    no widths it makes every column equal, which is worse than auto for prose.
    """
    cell = sel if cell_scope is None else cell_scope
    pre = f"{cell} " if cell else ""
    return (
        f"{sel} {{ border-collapse:collapse; width:100%; table-layout:{layout};\n"
        f"             margin:8px 0 4px; }}\n"
        f"{pre}th, {pre}td {{ border:1px solid {pal.table_border}; padding:{pal.d['cell_pad']};\n"
        f"             text-align:left; vertical-align:top; overflow-wrap:break-word; }}\n"
        f"{pre}th {{ background:{pal.table_head}; color:{pal.table_head_ink}; font-weight:700;\n"
        f"             letter-spacing:0.02em; padding:{pal.d['head_pad']}; }}\n"
        "/* Every body cell carries its own fill, so a dark-page theme's tables stay\n"
        "   readable even where a renderer drops the page colour. */\n"
        f"{pre}td {{ background:{pal.row}; color:{pal.ink}; }}\n"
        "/* Zebra is an explicit class, written per row by the builder. */\n"
        f"{pre}tr.alt td {{ background:{pal.zebra}; }}\n"
    )


def meta_css(pal: Palette, sel: str = "table.meta") -> str:
    """The meta table and its shaded key column."""
    return (
        f"{sel} {{ border-collapse:collapse; width:100%; margin:0 0 14px; }}\n"
        f"{sel} td {{ border:1px solid {pal.table_border}; padding:{pal.d['cell_pad']}; "
        f"font-size:{pal.d['meta_px']}px;\n"
        f"             background:{pal.row}; color:{pal.ink}; }}\n"
        f"{sel} td.k {{ background:{pal.zebra}; font-weight:600; width:17%; }}\n"
    )


def panel_css(pal: Palette) -> str:
    """The lede panel and the handling notice."""
    return (
        f".lede {{ background:{pal.panel}; border-left:4px solid {pal.heading};\n"
        "        padding:10px 14px; margin:10px 0 4px; }\n"
        f".handling {{ background:{pal.handling_bg}; border-left:4px solid {pal.classification};\n"
        f"            padding:8px 14px; margin:10px 0; font-size:12px; color:{pal.handling_ink}; }}\n"
    )


def cards_css(pal: Palette) -> str:
    """The summary-card panels."""
    return (
        "/* Cards are a table on purpose; the number and label are real block\n"
        "   elements rather than styled spans. */\n"
        "table.cards { border-collapse:separate; border-spacing:8px 0; width:100%;\n"
        "              margin:6px 0 2px; }\n"
        f"td.card {{ background:{pal.panel}; border:1px solid {pal.grid}; padding:{pal.d['card_pad']};\n"
        "          text-align:center; }\n"
        f"div.n {{ font-size:{pal.d['card_n_px']}px; font-weight:700; color:{pal.heading}; }}\n"
        f"div.l {{ font-size:11px; color:{pal.muted}; }}\n"
    )


def chip_css(pal: Palette) -> str:
    """Severity chips.

    The shared declarations sit in a GROUPED SELECTOR, not in a base class the
    element also carries. `class="chip chip-high"` applies NEITHER rule in Word
    -- measured, both the shading and the font colour come back as
    wdColorAutomatic. Grouped selectors are fine; two classes on the element
    are not. See word-traps.md rule 4.
    """
    names = ", ".join(f".chip-{s}" for s in pal.severities)
    out = [
        f"{names} {{ display:inline-block; padding:2px 8px; font-weight:700; "
        "font-size:11px; white-space:nowrap; }"
    ]
    for sev, (bg, fg) in pal.severities.items():
        out.append(f".chip-{sev} {{ background:{bg}; color:{fg}; }}")
    return "\n".join(out)


def print_css(headings: str = "h2", body_size: str = "11pt") -> str:
    """The page-break rules.

    `headings` widens by one selector for the guide profile: a hand-authored
    page has `<h3>` sections and a heading orphaned at the foot of a page is
    the same defect at either level. The report path emits no `<h3>` at all.
    """
    return (
        "@media print {\n"
        f"  body {{ font-size:{body_size}; }}\n"
        "  .wrap { padding:0; max-width:none; }\n"
        f"  {headings} {{ page-break-after:avoid; }}\n"
        "  tr { page-break-inside:avoid; }\n"
        "  thead { display:table-header-group; }\n"
        "}\n"
    )


# --------------------------------------------------------------------------
# Profile-specific blocks
# --------------------------------------------------------------------------

def _report_base_css(pal: Palette) -> str:
    return (
        f"\nbody {{ font-family:{pal.font_stack}; font-size:{pal.d['base_px']}px;\n"
        f"       color:{pal.ink}; background:{pal.page}; margin:0; }}\n"
        ".wrap { max-width:1000px; margin:0 auto; padding:18px 22px 40px; }\n"
        "\n"
        f"h1 {{ font-size:{pal.d['h1_px']}px; margin:18px 0 2px; color:{pal.heading}; }}\n"
        f"h2 {{ font-size:{pal.d['h2_px']}px; margin:{pal.d['h2_margin']}; padding-bottom:4px;\n"
        f"     border-bottom:1px solid {pal.rule}; color:{pal.heading}; }}\n"
        "p  { margin:6px 0; }\n"
        f".sub    {{ color:{pal.muted}; font-size:12px; margin:0 0 10px; }}\n"
        f".footer {{ color:{pal.muted}; font-size:11px; margin-top:26px;\n"
        f"          border-top:1px solid {pal.rule}; padding-top:8px; }}\n"
    )


def _masthead_css(pal: Palette) -> str:
    return (
        "/* Masthead: tables with cell shading, never coloured divs. */\n"
        "table.mast { border-collapse:collapse; width:100%; margin-bottom:14px; }\n"
        f".mast-strip {{ background:{pal.accent}; height:4px; line-height:4px; font-size:1px; }}\n"
        f".mast-band  {{ background:{pal.navy}; padding:{pal.d['band_pad']}; }}\n"
        f".mast-rule  {{ background:{pal.navy_dark}; height:3px; line-height:3px; font-size:1px; }}\n"
        f".mast-cls   {{ background:{pal.classification}; color:#FFFFFF; padding:5px 18px;\n"
        "              font-size:11px; font-weight:700; letter-spacing:1.6px; }\n"
        f".mast-org   {{ color:{pal.org_ink}; font-size:11px; font-weight:600;\n"
        "              letter-spacing:1.8px; }\n"
        f".mast-title {{ color:{pal.title_ink}; font-size:{pal.d['title_px']}px; font-weight:600; }}\n"
        f".mast-subtitle {{ color:{pal.org_ink}; font-size:12px; }}\n"
        "/* Bare class, per word-traps.md rule 3/4 - the only selector shape both\n"
        "   renderers apply. Height only: no width, so the source PNG's own aspect\n"
        "   ratio (290x70 for the wordmark) is preserved rather than guessed at here. */\n"
        f".mast-logo {{ height:{pal.d['logo_px']}px; }}\n"
        "/* Logo left, heading text right: a nested table, because Word drops\n"
        "   float and flex. Bare classes only, so LibreOffice applies them too. */\n"
        ".mast-row { border-collapse:collapse; width:100%; }\n"
        f".mast-logo-cell {{ width:1%; white-space:nowrap; vertical-align:middle;\n"
        f"              padding:0 18px 0 0; border-right:1px solid {pal.org_ink}; }}\n"
        ".mast-text { vertical-align:middle; padding:0 0 0 18px; }\n"
    )


def _guide_base_css(pal: Palette) -> str:
    """A standalone document rather than a web column: a real page margin, a
    point-based type scale, and headings down to H3.

    `.wrap` is still defined, and still optional, so the print block's
    `.wrap { padding:0 }` is not a dangling selector and a guide MAY wrap its
    body the same way a report does.
    """
    return (
        f"\nbody {{ font-family:{pal.font_stack}; font-size:{pal.d['guide_pt']}pt;\n"
        f"       color:{pal.ink}; background:{pal.page}; margin:{pal.d['guide_margin']}; "
        f"line-height:{pal.d['line_height']}; }}\n"
        ".wrap { max-width:none; margin:0; padding:0; }\n"
        "\n"
        f"h1 {{ font-size:22pt; margin:0 0 4pt; color:{pal.heading}; }}\n"
        "h2 { font-size:16pt; margin:24pt 0 8pt; padding-bottom:3pt;\n"
        f"     border-bottom:1px solid {pal.rule}; color:{pal.heading}; }}\n"
        f"h3 {{ font-size:13pt; margin:16pt 0 6pt; color:{pal.heading}; }}\n"
        "p  { margin:6pt 0; }\n"
        "ul, ol { margin:4pt 0 8pt 18pt; }\n"
        "li { margin:3pt 0; }\n"
        "code { font-family:Consolas,'Courier New',monospace; font-size:9.5pt; }\n"
        f".sub    {{ color:{pal.muted}; font-size:10pt; margin:0 0 10pt; }}\n"
        f".muted  {{ color:{pal.muted}; font-size:9.5pt; }}\n"
        ".warn { color:#8A6100; }\n"
        ".fail { color:#A01B12; }\n"
        f".footer {{ color:{pal.muted}; font-size:9.5pt; margin-top:26pt;\n"
        f"          border-top:1px solid {pal.rule}; padding-top:8pt; }}\n"
        f".box {{ background:{pal.panel}; border:1px solid {pal.heading};\n"
        "        padding:8pt 10pt; margin:10pt 0; }\n"
        f".plain {{ background:{pal.panel}; border-left:4px solid {pal.heading};\n"
        "          padding:4pt 10pt; margin:8pt 0; }\n"
    )


PROFILES = ("report", "guide")


def stylesheet(pal: Palette, profile: str = "report") -> str:
    """The house stylesheet for one profile.

    `report` reproduces `build_report.stylesheet()` exactly -- that equality is
    asserted by the suite, and it is what stops the CSS being forked.
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r} - one of {', '.join(PROFILES)}")
    if profile == "report":
        return (
            _report_base_css(pal)
            + "\n" + _masthead_css(pal)
            + "\n/* Every table: real grid, real thead. Both required. */\n"
            + table_css(pal, "table.data", "fixed")
            + "\n" + meta_css(pal, "table.meta")
            + "\n" + panel_css(pal)
            + "\n" + cards_css(pal)
            + "\n" + chip_css(pal) + "\n"
            + "\n" + print_css("h2")
        )
    return (
        _guide_base_css(pal)
        + "\n/* Every table: real grid, real thead. Both required. */\n"
        + table_css(pal, "table", "auto", cell_scope="")
        + "\n" + meta_css(pal, "table.meta")
        + "\n" + panel_css(pal)
        + "\n" + cards_css(pal)
        + "\n" + chip_css(pal) + "\n"
        + "\n" + print_css("h2, h3")
    )


# --------------------------------------------------------------------------
# Heading case
# --------------------------------------------------------------------------

# Lowercased inside a title; capitalised when first, last, or after a colon.
SMALL_WORDS = frozenset("""
a an and as at but by for from in into nor of on onto or over per than the to
up via vs with yet
""".split())

# Tokens whose correct spelling is NOT what the algorithm would produce, keyed
# by their lowercased form. Only needed for names that are all lower case and
# carry no interior capital, no digit and no dot - anything with one of those
# is preserved mechanically and needs no entry here. Keep this SHORT: an entry
# is a claim that a word is a proper name, and a wrong claim is invisible.
PRESERVE_TOKENS = {
    "doc-builder": "doc-builder",
    "obsidian-git": "obsidian-git",
    "graphify": "graphify",
    "npm": "npm",
    "pwsh": "pwsh",
    "macos": "macOS",
    "ios": "iOS",
    "powershell": "PowerShell",
    "javascript": "JavaScript",
    "github": "GitHub",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "sharepoint": "SharePoint",
    "openshift": "OpenShift",
}

# Leading/trailing characters stripped before a token is looked up. The token
# is reassembled with them, so `(0.19.93)` and `problem,` keep their punctuation.
# `_ENUM_RE` matches a list marker -- "1.", "10)", "3:" -- which is NOT the
# first word of a title even though it is the first token.
_EDGE = "\"'`(){}[]<>.,;:!?’“”—–"
_ENUM_RE = re.compile(r"^\d+[.):]?$")


def _split_edges(token: str):
    """(leading punctuation, core, trailing punctuation)."""
    lead = 0
    while lead < len(token) and token[lead] in _EDGE:
        lead += 1
    trail = len(token)
    while trail > lead and token[trail - 1] in _EDGE:
        trail -= 1
    return token[:lead], token[lead:trail], token[trail:]


def is_preserved(core: str) -> bool:
    """True when a token must be emitted exactly as written.

    Four mechanical shapes, none of which needs a list:

    * an interior capital -- PowerShell, macOS, DbContext, iPhone;
    * all capitals with two letters or more -- SOP, CLI, AD, EF, PR;
    * a digit anywhere -- 0.19.93, 4.8, PS7, 2026;
    * a dot, slash, backslash, underscore or `@` -- build_report.py, a/b, an
      email address.

    Everything else is ordinary prose and gets cased. A name that is all lower
    case and has none of these -- `doc-builder` -- cannot be told from prose by
    any rule, so it needs an entry in PRESERVE_TOKENS; that is what the list is
    for, and why it should stay short.
    """
    if not core:
        return False
    letters = [c for c in core if c.isalpha()]
    if any(c.isupper() for c in core[1:]):
        return True
    if len(letters) >= 2 and all(c.isupper() for c in letters):
        return True
    if any(c.isdigit() for c in core):
        return True
    if any(c in "./\\_@" for c in core):
        return True
    return False


def _cap(word: str) -> str:
    """Capitalise the first letter and touch nothing else. Never `.title()`,
    never `.capitalize()` - both lowercase the tail, which is the whole bug."""
    for i, c in enumerate(word):
        if c.isalpha():
            return word[:i] + c.upper() + word[i + 1:]
    return word


# A possessive or a plural apostrophe is not part of the name: `obsidian-git's`
# has to find `obsidian-git` in PRESERVE_TOKENS, and `it's` must not become
# `It'S` the way `str.title()` renders it.
_POSSESSIVE = ("'s", "’s", "'S", "’S", "'", "’")


def _split_possessive(core: str):
    """(name, possessive suffix). The suffix is re-attached unchanged."""
    for suf in _POSSESSIVE:
        if len(core) > len(suf) and core.endswith(suf):
            return core[:-len(suf)], suf
    return core, ""


def _case_core(core: str) -> str:
    """Case one already-stripped token, hyphen parts included."""
    if "-" in core:
        parts = core.split("-")
        # A hyphenated compound is cased part by part -- Stop-Gate, Self-Service
        # -- unless a part is itself preserved, in which case the whole token is
        # left alone rather than half-cased into something like `EF-Core`.
        if any(is_preserved(p) for p in parts if p):
            return core
        # Inside a compound the small-word rule still applies to the middle:
        # `Fire-into-the-Void`, not `Fire-Into-The-Void`. First and last part
        # are always capitalised, the same as first and last word of a title.
        real = [i for i, part in enumerate(parts) if part]
        if not real:
            return core
        first, last = real[0], real[-1]
        out = []
        for i, part in enumerate(parts):
            if not part:
                out.append(part)
            elif i != first and i != last and part.lower() in SMALL_WORDS:
                out.append(part.lower())
            else:
                out.append(_cap(part))
        return "-".join(out)
    return _cap(core)


def title_case(text: str) -> str:
    """Professional title case, preserving tokens that already carry their own
    capitalisation.

    `str.title()` is never used and would be wrong at every one of these:
    PowerShell -> Powershell, SOP -> Sop, macOS -> Macos, EF Core -> Ef Core,
    doc-builder -> Doc-Builder, 0.19.93 unchanged but `it's` -> `It'S`.

    The rules, in order of application per token:

    1. A preserved token (see `is_preserved` / PRESERVE_TOKENS) is emitted
       verbatim, wherever it sits -- including first and last.
    2. The first and the last word carrying a letter are always capitalised,
       and so is the first word after a colon or a dash.
    3. A word in SMALL_WORDS is lower cased anywhere else.
    4. Everything else is capitalised on its first letter only.

    A trailing possessive is split off before any of this, so `obsidian-git's`
    finds `obsidian-git` and `it's` never becomes `It'S`.

    Whitespace is preserved exactly, so a heading's own spacing survives.
    """
    if not text:
        return text
    parts = re.split(r"(\s+)", text)
    content = [i for i, p in enumerate(parts)
               if p.strip() and any(c.isalnum() for c in p)]
    if not content:
        return text
    # A leading enumeration marker is not the title's first word: in
    # "1. the problem" the word that must be capitalised is `the`, not `1.`.
    lead = 0
    while lead < len(content) and _ENUM_RE.match(parts[content[lead]].strip()):
        lead += 1
    if lead >= len(content):
        return text
    first, last = content[lead], content[-1]
    # When the first or last slot is held by a PRESERVED token the rule simply
    # does not fire -- nothing is promoted in its place. "6. changes 0.19.90 to
    # 0.19.92" ends on a version number, so `to` is still a middle small word,
    # and "notes for PowerShell" ends on PowerShell, so `for` is too.

    out = list(parts)
    force_next = False
    for i, token in enumerate(parts):
        if not token.strip():
            continue
        lead, core, trail = _split_edges(token)
        if core:
            name, poss = _split_possessive(core)
            trail = poss + trail
            canonical = PRESERVE_TOKENS.get(name.lower())
            if canonical is not None:
                out[i] = lead + canonical + trail
            elif is_preserved(name):
                out[i] = token
            elif i == first or i == last or force_next:
                out[i] = lead + _case_core(name) + trail
            elif name.lower() in SMALL_WORDS:
                out[i] = lead + name.lower() + trail
            else:
                out[i] = lead + _case_core(name) + trail
        # A colon or a dash ends a clause; what follows it opens one.
        force_next = token.rstrip().endswith((":", "—", "–"))
    return "".join(out)


# --------------------------------------------------------------------------
# Applying the house style to a hand-authored page
# --------------------------------------------------------------------------

_STYLE_RE = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.DOTALL | re.IGNORECASE)
_HEADING_RE = re.compile(r"(<h([123])(?:\s[^>]*)?>)(.*?)(</h\2>)", re.DOTALL | re.IGNORECASE)
_DOC_TITLE_RE = re.compile(r"(<title(?:\s[^>]*)?>)(.*?)(</title>)", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _title_case_markup(inner: str) -> str:
    """Title-case a heading's text while leaving any inline tags alone.

    The whole text is cased as ONE string and the tags spliced back in
    afterwards, because casing each run between tags separately gets the first
    and last word wrong at every tag boundary: `what the <code>PM</code> does`
    came back as "What The ... Does", with `the` promoted for being the last
    word of its own fragment. Splicing relies on the casing being
    length-preserving, which every rule here is; if some future canonical
    spelling is not, the length check falls back to per-run casing rather than
    splicing at offsets that have moved.
    """
    segs, pos = [], 0
    for m in _TAG_RE.finditer(inner):
        segs.append((True, inner[pos:m.start()]))
        segs.append((False, m.group(0)))
        pos = m.end()
    segs.append((True, inner[pos:]))

    text = "".join(seg for is_text, seg in segs if is_text)
    cased = title_case(text)
    if len(cased) != len(text):
        return "".join(title_case(seg) if is_text else seg for is_text, seg in segs)

    out, off = [], 0
    for is_text, seg in segs:
        if is_text:
            out.append(cased[off:off + len(seg)])
            off += len(seg)
        else:
            out.append(seg)
    return "".join(out)


PAGE_META = "doc-builder-page"
_BODY_RE = re.compile(r"<body(\s[^>]*)?>", re.IGNORECASE)


def mark_page(html: str, pal: Palette) -> str:
    """Carry a non-white page colour into the converted document.

    CSS `body { background }` colours the browser page, but a Word or
    LibreOffice import may drop it, and then light text lands on white paper.
    So a dark-page theme is stated three ways: the CSS, the legacy `bgcolor`
    attribute (the form Word itself writes when it saves a coloured page as
    HTML), and a `<meta name="doc-builder-page">` that `build_report.to_word`
    reads to set the page colour explicitly over COM. A white page is left
    exactly as it was -- no attribute, no meta."""
    if pal.page.upper() == "#FFFFFF":
        return html
    html = _BODY_RE.sub(lambda m: f'<body bgcolor="{pal.page}"{m.group(1) or ""}>', html, count=1)
    meta = f'<meta name="{PAGE_META}" content="{pal.page}">'
    m = re.search(r"</head>", html, re.IGNORECASE)
    if m and PAGE_META not in html:
        html = html[:m.start()] + meta + "\n" + html[m.start():]
    return html


def apply_to_html(text: str, pal: Palette, profile: str = "guide",
                  headings: bool = True) -> str:
    """Return `text` with its `<style>` block replaced by the house stylesheet
    and, unless told otherwise, its `<title>` and H1/H2/H3 text in title case.

    Replaces the CONTENTS of the first `<style>` element and leaves the rest of
    the document alone: this is a restyle, not a rewrite. A page with no
    `<style>` element gets one injected before `</head>`; a page with no
    `</head>` either is refused by name rather than silently half-styled.
    """
    css = stylesheet(pal, profile)
    text = mark_page(text, pal)
    if _STYLE_RE.search(text):
        out = _STYLE_RE.sub(lambda m: m.group(1) + css + m.group(3), text, count=1)
    else:
        m = re.search(r"</head>", text, re.IGNORECASE)
        if not m:
            raise ValueError("no <style> element and no </head> to inject one before")
        out = text[:m.start()] + f"<style>{css}</style>\n" + text[m.start():]
    if headings:
        out = _HEADING_RE.sub(
            lambda m: m.group(1) + _title_case_markup(m.group(3)) + m.group(4), out)
        # `<title>` too: it is the same heading, shown in the tab and in the
        # converted .docx's document properties, and `build_report.py` already
        # cases it. Leaving it alone is how a page ends up with a cased <h1>
        # and a sentence-case tab.
        out = _DOC_TITLE_RE.sub(
            lambda m: m.group(1) + _title_case_markup(m.group(2)) + m.group(3), out, count=1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    resolve_brand.add_brand_argument(ap)
    resolve_brand.add_theme_arguments(ap)
    ap.add_argument("--profile", choices=PROFILES, default="report",
                    help="report (build_report.py's own CSS) or guide "
                         "(a hand-authored narrative page). Default: report")
    ap.add_argument("--apply", metavar="FILE",
                    help="an existing HTML page: replace its <style> block with "
                         "the house stylesheet and title-case its headings")
    ap.add_argument("--no-title-case", action="store_true",
                    help="with --apply, restyle only and leave headings alone")
    ap.add_argument("--title-case", metavar="TEXT",
                    help="print TEXT in house title case and exit "
                         "(no brand resolution, nothing written)")
    ap.add_argument("--out", metavar="FILE",
                    help="write here instead of stdout")
    args = ap.parse_args(argv)

    if args.title_case is not None:
        print(title_case(args.title_case))
        return 0

    brand = resolve_brand.resolve(args.brand, theme=args.theme, density=args.density)
    pal = Palette(brand)

    # Compute the whole payload BEFORE opening the output file. `open(p,"w")`
    # truncates at open time, so a write whose argument expression raises leaves
    # a zero-byte file where the original was. See the repository's CLAUDE.md.
    if args.apply:
        with open(args.apply, encoding="utf-8") as fh:
            source = fh.read()
        text = apply_to_html(source, pal, args.profile,
                             headings=not args.no_title_case)
    else:
        text = stylesheet(pal, args.profile)

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
