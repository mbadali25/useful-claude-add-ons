"""The logo, from resolve_brand.Brand through to the emitted masthead HTML.

test_resolve_brand.py proves the resolution side: `Brand.logo_for("dark")`
finds the right file on disk. This file proves the OTHER half nothing covered
before now - that build_report.py actually asks for it, asks for the RIGHT
variant, and degrades correctly when there is none. A resolver nothing calls
is not wiring; this is the caller.

Imports build_report and resolve_brand directly against the real checkout
(same rationale as the direct-import tests at the bottom of
test_resolve_brand.py: the property under test is about the real,
committed solomon-doc-builder assets, so a copied fixture missing the
logo/*.png files would prove nothing).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_DOC_BUILDER_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _DOC_BUILDER_ROOT / "scripts"
_SOLOMON_JSON = _DOC_BUILDER_ROOT.parent / "solomon-doc-builder" / "assets" / "brand.json"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_report  # noqa: E402  pylint: disable=wrong-import-position
import house_style  # noqa: E402  pylint: disable=wrong-import-position
import resolve_brand  # noqa: E402  pylint: disable=wrong-import-position

pytestmark = pytest.mark.skipif(
    not _SOLOMON_JSON.is_file(),
    reason="solomon-doc-builder is not checked out as doc-builder's sibling here",
)


def test_palette_picks_the_on_dark_wordmark_for_solomon():
    """The masthead band (`.mast-band`) is filled navy - see stylesheet() -
    so Palette must resolve the DARK-background variant, never the light one.
    Asserted by filename, matching test_resolve_brand's
    test_logo_for_selects_the_variant_that_matches_the_background: this is
    the same property, checked at the point build_report actually reads it,
    so a later refactor that reaches for the wrong background name in either
    place goes red."""
    brand = resolve_brand.resolve(explicit=str(_SOLOMON_JSON), announce=False)
    pal = build_report.Palette(brand)
    assert pal.logo_src is not None
    assert pal.logo_src.startswith("file://")
    assert os.path.basename(pal.logo_src) == "solomon-logo-on-dark.png"


def test_palette_has_no_logo_for_the_neutral_pack():
    """The neutral pack's `logo` block is all null - Palette.logo_src must be
    None, not raise and not a broken file:// URI pointing at nothing."""
    brand = resolve_brand.resolve(explicit="neutral", announce=False)
    pal = build_report.Palette(brand)
    assert pal.logo_src is None


def test_masthead_embeds_an_img_when_a_logo_is_configured():
    html = build_report.masthead("CONTOSO", "Report Title", "subtitle", "INTERNAL",
                                 logo_src="file:///fake/logo.png")
    assert '<img class="mast-logo" src="file:///fake/logo.png" alt="CONTOSO">' in html


def test_masthead_puts_the_logo_left_of_the_heading_text():
    html = build_report.masthead("CONTOSO", "Report Title", "subtitle", "INTERNAL",
                                 logo_src="file:///fake/logo.png")
    logo_cell = html.index('<td class="mast-logo-cell">')
    text_cell = html.index('<td class="mast-text">')
    assert logo_cell < html.index('class="mast-logo"') < text_cell
    assert text_cell < html.index('<div class="mast-title">Report Title</div>')


def test_masthead_renders_with_no_img_when_there_is_no_logo():
    """The neutral case: a document with no brand logo must render fine
    without one - no <img> tag, and nothing that looks like a broken
    reference to a missing file."""
    html = build_report.masthead("CONTOSO", "Report Title", "subtitle", "INTERNAL",
                                 logo_src=None)
    assert "<img" not in html
    # The masthead's own structure is otherwise unaffected by the absent logo.
    assert '<div class="mast-org">CONTOSO</div>' in html


def test_full_build_with_solomon_brand_embeds_exactly_one_logo_img():
    brand = resolve_brand.resolve(explicit=str(_SOLOMON_JSON), announce=False)
    doc = {"title": "Report", "organisation": "CONTOSO"}
    out = build_report.build(doc, brand)
    imgs = re.findall(r"<img[^>]*>", out)
    assert len(imgs) == 1, imgs
    assert 'class="mast-logo"' in imgs[0]
    assert "solomon-logo-on-dark.png" in imgs[0]


def test_full_build_with_neutral_brand_embeds_no_img():
    brand = resolve_brand.resolve(explicit="neutral", announce=False)
    doc = {"title": "Report", "organisation": "CONTOSO"}
    out = build_report.build(doc, brand)
    assert "<img" not in out


def test_logo_configured_but_missing_on_this_machine_degrades_to_none(tmp_path, capsys):
    """A pack can be installed on a machine that is missing the logo file it
    points at (a partial checkout, a stripped-down deploy). `house_style.logo_uri`
    must
    treat that the same as no logo configured at all - never emit a src the
    browser or Word cannot load - and say so on stderr rather than staying
    silent about it."""
    missing = tmp_path / "does-not-exist.png"
    assert house_style.logo_uri(str(missing)) is None
    assert "not found on this machine" in capsys.readouterr().err


def test_logo_uri_is_a_file_uri_for_a_real_file(tmp_path):
    real = tmp_path / "logo.png"
    real.write_bytes(b"\x89PNG\r\n\x1a\n")
    uri = house_style.logo_uri(str(real))
    assert uri == real.resolve().as_uri()
