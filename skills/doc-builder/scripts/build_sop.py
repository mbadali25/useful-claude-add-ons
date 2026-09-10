r"""
Build a step-by-step SOP / work instruction / how-to as a .docx, on the active
brand pack's house template.

This is the python-docx OOXML path of doc-builder. It exists because the
HTML -> Word path cannot do bordered screenshots: `add_picture()` writes
neither the `a:ln` outline nor `wp:effectExtent`, so Word strokes the border
outside `wp:extent` and clips it at page top. This builder writes both.

Colours, fonts, the footer and the template come from the brand pack
(resolve_brand.py). Structural values -- indents, spacing, the effectExtent
band, the border width -- were measured from a real document set and are the
same for every brand. Do not "tidy" those numbers.

Usage
-----
    python build_sop.py spec.json --dry-run          # say what would be written, write nothing
    python build_sop.py spec.json                    # build; an existing master is backed up first
    python build_sop.py spec.json --to-pdf           # also render the PDF through Word COM
    python build_sop.py spec.json --out "C:\path\My SOP.docx" --brand neutral

    # Programmatically:
    from build_sop import SopBuilder
    import resolve_brand
    b = SopBuilder("Archiving Emails in Outlook", "M365 Outlook archiving",
                   brand=resolve_brand.resolve())
    b.para("Archiving moves older emails **out of your mailbox**.")
    b.heading("Quick steps")
    b.step("In Outlook, click **File**.")
    b.image(r"C:\path\shot.png", caption="The Archive window.")
    b.save(r"C:\path\My SOP.docx")

Inline markup, usable in the text of any text-bearing block (para, step,
bullet, tip, caption): "**bold**" spans and Markdown-style links
"[label](https://example.com)", freely mixed, e.g.
"See **the** [portal](https://example.com) for details." A bare URL as the
label -- "[https://example.com](https://example.com)" -- is the common case
and works the same way. See _split_spans() for how the two coexist and how a
malformed link is handled.

Output location, in order: --out; the spec's "output" (relative to the spec
file); else "<title>.docx" in the brand pack's masters directory. The neutral
pack has no masters directory, so one of the first two is then required.

Third-party requirement: python-docx. Microsoft Word (pywin32) only for --to-pdf.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
import uuid as _uuid

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Inches, Pt, RGBColor

import resolve_brand

# --------------------------------------------------------------------------
# Structural constants (measured -- the same for every brand; do not "tidy")
# --------------------------------------------------------------------------
STEP_INDENT = 475     # twips: hanging indent + tab stop for numbered steps
BULLET_INDENT = 403   # twips: hanging indent + tab stop for bullets
BULLET_CHAR = "\u2022"

IMAGE_BORDER_EMU = 9525    # 0.75pt picture outline
EFFECT_EXTENT_EMU = 19050  # what we WRITE: 1.5pt, the value Word itself writes
EFFECT_EXTENT_MIN = 9525   # what we ACCEPT: one full line width. Word-authored
                           # values as low as 10795 render correctly, so anything
                           # at or above this is left alone rather than rewritten.
                           # See _reserve_effect_extent().
MAX_IMAGE_WIDTH_IN = 7.5  # text column width at 0.5" side margins
MAX_IMAGE_HEIGHT_IN = 6.5 # keeps a screenshot + its caption on one page


class Style:
    """The brand-dependent half of the house style, read from brand.json.

    Attribute names are the ones the rest of the toolchain has always used
    (ACCENT_RED, HEADING_NAVY, ...) so check_conformance.py and extract_spec.py
    read them unchanged. The names describe the ROLE; the values are whatever
    the brand says. ACCENT_RED is navy in the neutral pack, and that is fine.
    """

    def __init__(self, brand):
        sop = brand.sop
        self.brand = brand
        self.ACCENT_RED = sop["accent"].upper()              # accent bar, step numbers, bullets
        self.IMAGE_BORDER_RED = sop["image_border"].upper()  # screenshot border
        self.HEADING_NAVY = sop["heading"].upper()
        self.TITLE_GREY = sop["title"].upper()
        self.CAPTION_GREY = sop["caption"].upper()
        self.LINK_BLUE = sop["link"].upper()
        self.BODY_BLACK = sop["body"].upper()
        self.HEADING_FONT = brand.fonts["heading"]
        self.BODY_FONT = brand.fonts["body"]
        self.TITLE_PT = float(sop["title_pt"])
        self.SUBTITLE_PT = float(sop["subtitle_pt"])
        self.HEADING_PT = float(sop["heading_pt"])
        self.CAPTION_PT = float(sop["caption_pt"])
        self.MARGINS_IN = dict(sop["margins_in"])
        self.FOOTER = dict(sop.get("footer") or {})
        self.TEMPLATE = brand.template


# Module-level mirror of the active Style, so `import build_sop as S; S.ACCENT_RED`
# keeps working for the checker and the spec extractor. Set by configure().
STYLE = None
ACCENT_RED = IMAGE_BORDER_RED = HEADING_NAVY = TITLE_GREY = CAPTION_GREY = None
LINK_BLUE = BODY_BLACK = HEADING_FONT = BODY_FONT = None
TITLE_PT = SUBTITLE_PT = HEADING_PT = CAPTION_PT = None


def configure(brand=None) -> Style:
    """Bind the module to one brand. Resolves the default pack when none is
    given. Call it once at the top of any script that reads the S.* constants."""
    global STYLE
    brand = brand or resolve_brand.resolve()
    STYLE = Style(brand)
    g = globals()
    for name in ("ACCENT_RED", "IMAGE_BORDER_RED", "HEADING_NAVY", "TITLE_GREY",
                 "CAPTION_GREY", "LINK_BLUE", "BODY_BLACK", "HEADING_FONT", "BODY_FONT",
                 "TITLE_PT", "SUBTITLE_PT", "HEADING_PT", "CAPTION_PT"):
        g[name] = getattr(STYLE, name)
    return STYLE


def synthesise_template(style):
    """A blank document carrying what a template file would: page size and
    margins, the Normal font, and the footer table. Used when the brand pack
    ships no .docx (the neutral pack never does)."""
    d = docx.Document()
    s = d.sections[0]
    s.orientation = WD_ORIENT.PORTRAIT
    s.page_width, s.page_height = Inches(8.5), Inches(11)
    m = style.MARGINS_IN
    s.top_margin, s.bottom_margin = Inches(m["top"]), Inches(m["bottom"])
    s.left_margin, s.right_margin = Inches(m["left"]), Inches(m["right"])
    normal = d.styles["Normal"]
    normal.font.name = style.BODY_FONT
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), style.BODY_FONT)
    normal.font.size = Pt(11)

    footer = s.footer
    tbl = footer.add_table(rows=1, cols=3, width=Inches(7.5))
    left, centre, right = tbl.rows[0].cells
    left.paragraphs[0].add_run(style.FOOTER.get("left") or "")
    centre.paragraphs[0].add_run(style.FOOTER.get("centre") or "")
    centre.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    right.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fld = _el("w:fldSimple", instr="PAGE")
    r = _el("w:r")
    t = _el("w:t")
    t.text = "1"
    r.append(t)
    fld.append(r)
    right.paragraphs[0]._p.append(fld)
    for cell in (left, centre, right):
        for run in cell.paragraphs[0].runs:
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor.from_string(style.CAPTION_GREY)
    # The footer's own default paragraph sits above the table; empty it so the
    # table is not pushed down a line.
    return d


def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn("w:" + k), str(v))
    return e


def _spacing(paragraph, before=None, after=None):
    """Set w:spacing in twips directly; the Pt-based API rounds these values."""
    pPr = paragraph._p.get_or_add_pPr()
    sp = pPr.find(qn("w:spacing"))
    if sp is None:
        sp = _el("w:spacing")
        pPr.append(sp)
    if before is not None:
        sp.set(qn("w:before"), str(before))
    if after is not None:
        sp.set(qn("w:after"), str(after))


def _hanging_indent(paragraph, twips):
    pPr = paragraph._p.get_or_add_pPr()
    tabs = _el("w:tabs")
    tabs.append(_el("w:tab", val="left", pos=twips))
    pPr.append(tabs)
    pPr.append(_el("w:ind", left=twips, hanging=twips))


def _split_bold(text):
    """Split on ** markers: "a **b** c" -> [("a ", False), ("b", True), (" c", False)]."""
    out = []
    for i, part in enumerate(text.split("**")):
        if part:
            out.append((part, i % 2 == 1))
    return out


# [label](url) -- label excludes "[" and "]" (no nested links); url excludes
# "(" and ")" (covers every URL seen in the source masters, including query
# strings with "&"; a URL containing a literal parenthesis is not supported).
_LINK_RE = re.compile(r"\[([^\[\]]*)\]\(([^()]*)\)")


def _split_spans(text):
    """Parse the inline markup shared by every text-bearing block: **bold**
    spans and [label](url) links, coexisting in one pass, e.g.
    "See **the** [portal](https://x) now".

    Returns a list of segments, each one of:
        ("text", chunk, bold)
        ("link", url, label_spans)   -- label_spans is a list of
                                         ("text", chunk, bold) tuples, so a
                                         link's label may itself contain
                                         **bold** (but not another link)

    This is the same mechanism as _split_bold, extended rather than
    duplicated: text outside (and inside) a link is still run through
    _split_bold, so "**" keeps working everywhere it always did.

    Malformed-link decision: an unclosed "[" / "]" / "(" / ")" that does not
    complete a full [label](url) match is NOT a spec error -- the literal
    bracket/paren characters fall through to _split_bold like any other text
    and render as-is. This mirrors how an unpaired "**" has always been
    tolerated (it just stops alternating bold correctly) rather than raised.
    Consequence: a spec typo drops a link rather than failing the build, so
    one bad line in a large spec cannot block generation of the whole SOP.

    But it does not do so SILENTLY. Silent loss is this set's characteristic
    failure -- a clipped screenshot border shipped for four months because
    nothing announced it -- so near-miss markup is reported on stderr. The
    build still succeeds; the operator is told which line to look at.

    What that detects: a residual "](" once the valid links are removed, i.e.
    a link whose URL half is malformed. What it deliberately does NOT detect:
    a bare "[label]" with no parens at all, because square brackets are
    ordinary prose in these documents ("[Optional]") and warning on every one
    would train the operator to ignore the warning.
    """
    # Anything still looking like link markup once the valid links are removed
    # is a typo -- an unclosed bracket or paren. Report it and carry on.
    if "](" in _LINK_RE.sub("", text):
        sys.stderr.write(
            "warning: link markup does not parse as [label](url), so it will\n"
            "         render as literal text -- check for an unclosed bracket\n"
            "         or paren in: %r\n" % text[:120])

    segments = []
    pos = 0
    for m in _LINK_RE.finditer(text):
        if m.start() > pos:
            segments.extend(
                ("text", chunk, bold) for chunk, bold in _split_bold(text[pos:m.start()])
            )
        label_spans = [("text", chunk, bold) for chunk, bold in _split_bold(m.group(1))]
        segments.append(("link", m.group(2), label_spans))
        pos = m.end()
    if pos < len(text):
        segments.extend(("text", chunk, bold) for chunk, bold in _split_bold(text[pos:]))
    return segments


class SopBuilder(object):
    """Builds one step-by-step SOP .docx on the active brand pack's house template."""

    def __init__(self, title, subtitle="", template=None, brand=None):
        self.style = configure(brand) if (brand or STYLE is None) else STYLE
        template = template or self.style.TEMPLATE
        if template:
            if not os.path.exists(template):
                raise FileNotFoundError(
                    "Template not found: %s\nRun make_template.py to regenerate it, "
                    "or remove \"template\" from brand.json to synthesise one." % template
                )
            self.doc = docx.Document(template)
        else:
            self.doc = synthesise_template(self.style)
        self._step_no = 0
        self._add_title_banner(title, subtitle)

    # -- title banner -------------------------------------------------------
    def _add_title_banner(self, title, subtitle):
        """1-row/2-col table; the 86-twip cell shaded EF483D is the accent bar."""
        tbl = _el("w:tbl")

        tblPr = _el("w:tblPr")
        tblPr.append(_el("w:tblW", w=0, type="auto"))
        tblPr.append(_el("w:jc", val="left"))
        tblPr.append(_el("w:tblLayout", type="fixed"))
        borders = _el("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(_el("w:" + side, val="none", sz=0))
        tblPr.append(borders)
        tbl.append(tblPr)

        grid = _el("w:tblGrid")
        grid.append(_el("w:gridCol", w=236))
        grid.append(_el("w:gridCol", w=10714))
        tbl.append(grid)

        tr = _el("w:tr")

        tc = _el("w:tc")
        tcPr = _el("w:tcPr")
        tcPr.append(_el("w:tcW", w=86, type="dxa"))
        tcPr.append(_el("w:shd", val="clear", color="auto", fill=self.style.ACCENT_RED))
        tc.append(tcPr)
        tc.append(_el("w:p"))
        tr.append(tc)

        tc2 = _el("w:tc")
        tcPr2 = _el("w:tcPr")
        tcPr2.append(_el("w:tcW", w=10714, type="dxa"))
        tc2.append(tcPr2)
        st = self.style
        tc2.append(self._banner_para(title, st.HEADING_FONT, st.TITLE_PT, st.TITLE_GREY, after=40))
        if subtitle:
            tc2.append(self._banner_para(subtitle, st.BODY_FONT, st.SUBTITLE_PT, st.CAPTION_GREY, before=40))
        tr.append(tc2)

        tbl.append(tr)
        self.doc.element.body.insert(0, tbl)

    @staticmethod
    def _banner_para(text, font, size_pt, color, before=None, after=None):
        p = _el("w:p")
        pPr = _el("w:pPr")
        sp = _el("w:spacing")
        if before is not None:
            sp.set(qn("w:before"), str(before))
        if after is not None:
            sp.set(qn("w:after"), str(after))
        pPr.append(sp)
        p.append(pPr)

        r = _el("w:r")
        rPr = _el("w:rPr")
        rPr.append(_el("w:rFonts", ascii=font, hAnsi=font))
        rPr.append(_el("w:b", val=0))
        rPr.append(_el("w:i", val=0))
        rPr.append(_el("w:color", val=color))
        rPr.append(_el("w:sz", val=int(size_pt * 2)))
        r.append(rPr)
        t = _el("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        r.append(t)
        p.append(r)
        return p

    # -- body blocks --------------------------------------------------------
    def _runs(self, paragraph, text, size_pt=None, color=None,
              font=None, force_bold=False, italic=False):
        """Render **bold** spans and [label](url) links inline. size_pt/font/
        force_bold apply to both plain and link runs (so a link keeps the
        block's size and, e.g., a tip's forced bold); a link's own color is
        always LINK_BLUE with a single underline regardless of `color`, since
        that is the one measured house hyperlink format."""
        color = color or self.style.BODY_BLACK
        for kind, a, b in _split_spans(text):
            if kind == "text":
                chunk, bold = a, b
                run = paragraph.add_run(chunk)
                run.bold = True if (bold or force_bold) else None
                run.italic = True if italic else None
                run.font.color.rgb = RGBColor.from_string(color)
                if size_pt:
                    run.font.size = Pt(size_pt)
                if font:
                    run.font.name = font
            else:  # "link"
                url, label_spans = a, b
                self._add_hyperlink(paragraph, url, label_spans,
                                     size_pt=size_pt, font=font,
                                     force_bold=force_bold, italic=italic,
                                     link_colour=self.style.LINK_BLUE)
        return paragraph

    @staticmethod
    def _add_hyperlink(paragraph, url, label_spans, size_pt=None, font=None,
                        force_bold=False, italic=False, link_colour="0563C1"):
        """Emit a REAL Word hyperlink: an external relationship on the
        document part (TargetMode="External", added via part.relate_to --
        never hand-written into document.xml.rels) plus a <w:hyperlink>
        carrying one <w:r> per label span, in the one measured house format:

            <w:hyperlink r:id="rIdN"><w:r><w:rPr><w:color w:val="0563C1"/>
            <w:u w:val="single"/></w:rPr><w:t>LABEL</w:t></w:r></w:hyperlink>

        python-docx has no hyperlink-run API (and the masters define no named
        Hyperlink style to reach for), so this builds the element by hand,
        the same way _add_picture_border hand-builds a:ln/effectExtent.
        `relate_to` XML-escapes the target itself (e.g. "&" -> "&amp;"), so
        URLs with query strings are safe without any manual escaping here.
        """
        r_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        hyperlink = _el("w:hyperlink")
        hyperlink.set(qn("r:id"), r_id)
        for _kind, chunk, bold in label_spans:
            r = _el("w:r")
            rPr = _el("w:rPr")
            if font:
                rPr.append(_el("w:rFonts", ascii=font, hAnsi=font))
            if bold or force_bold:
                rPr.append(_el("w:b", val=1))
            if italic:
                # CT_RPr schema order: rFonts, b, i, ... color, sz, u.
                rPr.append(_el("w:i", val=1))
            rPr.append(_el("w:color", val=link_colour))
            if size_pt:
                rPr.append(_el("w:sz", val=int(size_pt * 2)))
            rPr.append(_el("w:u", val="single"))
            r.append(rPr)
            t = _el("w:t")
            t.set(qn("xml:space"), "preserve")
            t.text = chunk
            r.append(t)
            hyperlink.append(r)
        paragraph._p.append(hyperlink)

    def para(self, text):
        """Intro / explanatory paragraph. Supports **bold** spans."""
        p = self.doc.add_paragraph()
        self._runs(p, text)
        return p

    def heading(self, text, keep_with_next=False):
        """Section heading. Resets step numbering.

        keep_with_next is OPT-IN and off by default: the measured masters carry
        no w:keepNext anywhere, so emitting it unasked would make every
        generated document differ from the set. A text-only document has no
        `width_in` to reflow with, so it is the one lever against a heading
        stranded alone at the foot of a page."""
        self._step_no = 0
        p = self.doc.add_paragraph()
        if keep_with_next:
            # Schema order puts keepNext before spacing in w:pPr; insert first.
            p._p.get_or_add_pPr().insert(0, _el("w:keepNext"))
        _spacing(p, before=240, after=100)
        st = self.style
        self._runs(p, text, size_pt=st.HEADING_PT, color=st.HEADING_NAVY,
                   font=st.HEADING_FONT, force_bold=True)
        return p

    def step(self, text, number=None):
        """Numbered step. Numbers auto-increment and reset at each heading."""
        if number is None:
            self._step_no += 1
            number = self._step_no
        else:
            self._step_no = number
        p = self.doc.add_paragraph()
        _spacing(p, after=80)
        _hanging_indent(p, STEP_INDENT)
        marker = p.add_run("%d." % number)
        marker.bold = True
        marker.font.color.rgb = RGBColor.from_string(self.style.ACCENT_RED)
        tab = p.add_run()
        tab.bold = True
        tab.font.color.rgb = RGBColor.from_string(self.style.ACCENT_RED)
        tab.add_tab()
        self._runs(p, text)
        return p

    def bullet(self, text):
        p = self.doc.add_paragraph()
        _spacing(p, after=80)
        _hanging_indent(p, BULLET_INDENT)
        marker = p.add_run(BULLET_CHAR)
        marker.font.color.rgb = RGBColor.from_string(self.style.ACCENT_RED)
        tab = p.add_run()
        tab.font.color.rgb = RGBColor.from_string(self.style.ACCENT_RED)
        tab.add_tab()
        self._runs(p, text)
        return p

    def tip(self, text):
        """Bold call-out line, e.g. "Tip: ..." or "Note: ..."."""
        p = self.doc.add_paragraph()
        _spacing(p, before=40)
        self._runs(p, text, force_bold=True)
        return p

    def image(self, path, caption="", width_in=None,
              max_width_in=MAX_IMAGE_WIDTH_IN, max_height_in=MAX_IMAGE_HEIGHT_IN):
        """Centered screenshot with the house red border, plus optional caption."""
        p = self.doc.add_paragraph()
        _spacing(p, before=360, after=40)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()

        if width_in:
            run.add_picture(path, width=Inches(width_in))
        else:
            pic = run.add_picture(path)
            # Scale down (never up) to fit the column and leave room for a caption.
            scale = min(Inches(max_width_in) / pic.width,
                        Inches(max_height_in) / pic.height, 1.0)
            if scale < 1.0:
                pic.width = Emu(int(pic.width * scale))
                pic.height = Emu(int(pic.height * scale))

        self._add_picture_border(p)
        if caption:
            self.caption(caption)
        return p

    def _add_picture_border(self, paragraph):
        """python-docx has no picture-border API -- inject a:ln into pic:spPr,
        and wp:effectExtent into wp:inline so Word reserves room for it."""
        ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        for spPr in paragraph._p.findall(".//" + qn("pic:spPr")):
            if spPr.find("{%s}ln" % ns_a) is not None:
                continue
            ln = OxmlElement("a:ln")
            ln.set("w", str(IMAGE_BORDER_EMU))
            fill = OxmlElement("a:solidFill")
            clr = OxmlElement("a:srgbClr")
            clr.set("val", self.style.IMAGE_BORDER_RED)
            fill.append(clr)
            ln.append(fill)
            spPr.append(ln)
        self._reserve_effect_extent(paragraph._p)

    @staticmethod
    def _reserve_effect_extent(element):
        """Word strokes a picture outline OUTSIDE the wp:extent box. Only
        wp:effectExtent reserves that band; python-docx never writes it, so
        without this the stroke falls outside the line box and Word clips it --
        losing the top border whenever an image sits at the top of a page.

        Raising the page's top margin does NOT fix this: it moves the boundary
        and the image together. Verified 2026-08-25 by pixel-measuring rendered
        PDFs, and by the in-repo controlled pair in "Remote Desktop using
        multiple screens.docx" (img1 effectExtent=0 -> top border clipped;
        img2 effectExtent=19050 -> top border renders).

        Returns the number of inline shapes changed."""
        changed = 0
        for inline in element.findall(".//" + qn("wp:inline")):
            extent = inline.find(qn("wp:extent"))
            if extent is None:
                continue
            ee = inline.find(qn("wp:effectExtent"))
            if ee is None:
                ee = OxmlElement("wp:effectExtent")
                inline.insert(list(inline).index(extent) + 1, ee)
            elif all(int(ee.get(s) or 0) >= EFFECT_EXTENT_MIN for s in "ltrb"):
                continue  # already adequate (e.g. Word-authored) -- leave it alone
            for side in ("l", "t", "r", "b"):
                if int(ee.get(side) or 0) < EFFECT_EXTENT_MIN:
                    ee.set(side, str(EFFECT_EXTENT_EMU))
            changed += 1
        return changed

    def caption(self, text):
        # Captions are ITALIC in the house style. Measured 2026-09-08 across
        # the whole set: 47 caption paragraphs in 17 masters are italic and
        # none are plain -- the sole exception was the one master this
        # generator had built, because the original TEMPLATE-SPEC recorded
        # caption size and colour but never italic. Same shape of defect as
        # the missing wp:effectExtent: an incomplete measurement, so the
        # generator diverged from the set and the checker validated the
        # wrong thing.
        p = self.doc.add_paragraph()
        _spacing(p, after=200)
        self._runs(p, text, size_pt=self.style.CAPTION_PT, color=self.style.CAPTION_GREY,
                   italic=True)
        return p

    def spacer(self):
        return self.doc.add_paragraph()

    def save(self, path):
        self.doc.save(path)
        return path


# --------------------------------------------------------------------------
# JSON spec driver
# --------------------------------------------------------------------------
_DISPATCH = {
    "para": lambda b, blk: b.para(blk["text"]),
    "heading": lambda b, blk: b.heading(blk["text"], bool(blk.get("keep_with_next", False))),
    "step": lambda b, blk: b.step(blk["text"], blk.get("number")),
    "bullet": lambda b, blk: b.bullet(blk["text"]),
    "tip": lambda b, blk: b.tip(blk["text"]),
    "caption": lambda b, blk: b.caption(blk["text"]),
    "spacer": lambda b, blk: b.spacer(),
    "image": lambda b, blk: b.image(blk["path"], blk.get("caption", ""), blk.get("width_in")),
}


def resolve_output(spec, base_dir, out=None, brand=None):
    """--out, else the spec's "output" (relative to the spec file), else
    "<title>.docx" in the brand pack's masters directory."""
    if out:
        return os.path.abspath(out)
    if spec.get("output"):
        o = spec["output"]
        return o if os.path.isabs(o) else os.path.normpath(os.path.join(base_dir, o))
    if brand is None or not brand.masters_dir:
        raise SystemExit(
            "No output path: the spec has no \"output\", --out was not given, and "
            "the %s brand pack has no masters directory. Pass --out."
            % (brand.name if brand else "active"))
    # Must already exist. Creating C:\...\sops_new on a machine that does not
    # have the masters checked out would write a production document nowhere
    # anyone looks.
    masters = brand.require_masters_dir()
    safe = re.sub(r'[\\/:*?"<>|]+', "-", spec["title"]).strip()
    return os.path.join(masters, safe + ".docx")


def build_from_spec(spec, base_dir=".", out=None, brand=None, dry_run=False):
    """Build a SOP from a spec dict. Relative image/output paths resolve against
    base_dir (normally the folder holding the JSON spec).

    dry_run builds the document in memory -- so a bad spec still fails -- and
    reports what WOULD be written, but writes nothing and backs nothing up.
    """
    brand = brand or resolve_brand.resolve()
    b = SopBuilder(spec["title"], spec.get("subtitle", ""), brand=brand)
    images = 0
    for blk in spec["body"]:
        kind = blk["type"]
        if kind not in _DISPATCH:
            raise ValueError("Unknown block type: %r" % kind)
        if kind == "image":
            if not os.path.isabs(blk["path"]):
                blk = dict(blk, path=os.path.normpath(os.path.join(base_dir, blk["path"])))
            if not os.path.isfile(blk["path"]):
                raise FileNotFoundError("image not found: %s" % blk["path"])
            images += 1
        _DISPATCH[kind](b, blk)
    out = resolve_output(spec, base_dir, out, brand)

    exists = os.path.exists(out)
    backup = None
    if exists:
        # Unique per RUN, not per day. A per-day folder meant the second
        # rebuild of the day replaced the original master's backup with the
        # first generated revision - the safety net held a copy of the thing
        # it was protecting against. Seconds plus a random tail cannot collide.
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + _uuid.uuid4().hex[:4]
        backup = os.path.join(os.path.dirname(out), "_backup_%s" % stamp, os.path.basename(out))
    if dry_run:
        print("DRY RUN - nothing written.")
        print("  brand   : %s" % brand.name)
        print("  blocks  : %d (%d image(s))" % (len(spec["body"]), images))
        print("  output  : %s%s" % (out, "  (EXISTS - would be backed up first)" if exists else "  (new)"))
        if backup:
            print("  backup  : %s" % backup)
        return out

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if backup:
        # Never overwrite a production master without keeping the previous
        # one. Git may not be watching the masters directory.
        if os.path.exists(backup):
            raise SystemExit("Refusing to overwrite an existing backup: %s" % backup)
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        shutil.copy2(out, backup)
        print("Backed up previous master to %s" % backup)
    return b.save(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="JSON build spec (see references/toolchain-usage.md)")
    ap.add_argument("--out", help="output .docx path (overrides the spec and the brand default)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate the spec and report the output path; write nothing")
    ap.add_argument("--to-pdf", action="store_true",
                    help="also render a PDF next to the .docx through Word COM (Windows, pywin32)")
    resolve_brand.add_brand_argument(ap)
    args = ap.parse_args(argv)

    spec_path = os.path.abspath(args.spec)
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    brand = resolve_brand.resolve(args.brand)
    out = build_from_spec(spec, base_dir=os.path.dirname(spec_path), out=args.out,
                          brand=brand, dry_run=args.dry_run)
    if args.dry_run:
        return 0
    print("Built: %s" % out)
    if args.to_pdf:
        from build_report import to_word  # pylint: disable=import-outside-toplevel
        rc = to_word(out, want_docx=False, want_pdf=True)
        if rc:
            return rc
    print('Next: python check_conformance.py "%s" -v   (Gate 1)' % out)
    if args.to_pdf:
        print('      python verify_borders.py "%s" -v   (Gate 2)' % (os.path.splitext(out)[0] + ".pdf"))
    else:
        print("      then render the PDF (--to-pdf) and run verify_borders.py on it (Gate 2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
