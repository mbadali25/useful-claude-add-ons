"""Built-in themes and densities: resolution order, identity protection,
contrast, dark-page carriage into the converted document, and the gallery.

SABOTAGE CHECKS (each was run; each turned this suite red):
  * In resolve_brand.Brand.apply_overlay, delete the `banned` pop loop ->
    test_a_theme_cannot_replace_brand_identity fails (a theme carrying a footer
    replaces Solomon's).
  * In any assets/themes/*.json, set table_head_ink equal to table_head ->
    test_every_theme_meets_contrast[...] fails for that theme.
  * Change one hex in a theme without rebuilding the gallery ->
    test_gallery_is_current fails.
"""

import json
import os
import sys
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

import build_gallery  # noqa: E402
import build_report  # noqa: E402
import house_style  # noqa: E402
import resolve_brand  # noqa: E402

SKILLS = os.path.normpath(os.path.join(SCRIPTS, os.pardir, os.pardir))
THEMES = [n for n, _, _ in resolve_brand.list_themes()]
EXPECTED_THEMES = {"professional", "corporate", "blue", "red", "modern",
                   "dark", "midnight", "high-contrast"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (resolve_brand.THEME_ENV, resolve_brand.DENSITY_ENV, resolve_brand.BRAND_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(resolve_brand.SKILLS_DIR_ENV, SKILLS)


def _resolve(brand="neutral", theme=None, density=None):
    return resolve_brand.resolve(brand, announce=False, theme=theme, density=density)


def _lum(hexv):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_expected_themes_ship():
    assert set(THEMES) == EXPECTED_THEMES


def test_densities_ship():
    assert {n for n, _ in resolve_brand.list_densities()} == {"comfortable", "compact"}


@pytest.mark.parametrize("wanted", ["High Contrast", "high_contrast", "HIGH-CONTRAST"])
def test_theme_names_are_forgiving(wanted):
    assert _resolve(theme=wanted).theme == "high-contrast"


def test_unknown_theme_names_the_available_ones():
    with pytest.raises(resolve_brand.OverlayNotFound, match="midnight"):
        _resolve(theme="sparkly")


def test_theme_from_environment(monkeypatch):
    monkeypatch.setenv(resolve_brand.THEME_ENV, "red")
    assert _resolve().theme == "red"


def test_explicit_theme_beats_environment(monkeypatch):
    monkeypatch.setenv(resolve_brand.THEME_ENV, "red")
    assert _resolve(theme="blue").theme == "blue"


def test_no_theme_keeps_the_brand_colours():
    solomon = _resolve("solomon")
    assert solomon.theme is None
    assert solomon.report["navy"] == "#0E2841"


def test_a_theme_wins_on_colour_over_the_brand():
    themed = _resolve("solomon", theme="red")
    red = resolve_brand.load_overlay("theme", "red")[1]
    assert themed.report["navy"] == red["report"]["navy"]


def test_a_theme_keeps_the_brand_identity():
    plain, themed = _resolve("solomon"), _resolve("solomon", theme="midnight")
    assert themed.fonts == plain.fonts
    assert themed.logo == plain.logo
    assert themed.sop["footer"] == plain.sop["footer"]
    assert themed.template == plain.template
    assert themed.organisation == plain.organisation


def test_a_theme_cannot_replace_brand_identity():
    brand = _resolve("solomon")
    footer = dict(brand.sop["footer"])
    brand.apply_overlay("theme", "rogue", {
        "sop": {"footer": {"left": "HIJACKED"}, "template": "x.docx", "accent": "123456"},
        "report": {"output_dir": "/elsewhere", "navy": "#123456"},
        "fonts": {"body": "Comic Sans MS"},
    })
    assert brand.sop["footer"] == footer
    assert brand.sop["accent"] == "123456"
    assert brand.report["output_dir"] != "/elsewhere"
    assert brand.report["navy"] == "#123456"
    assert brand.fonts["body"] != "Comic Sans MS"


def test_describe_names_theme_and_density():
    text = _resolve(theme="dark", density="compact").describe()
    assert "theme dark" in text and "density compact" in text


# --------------------------------------------------------------------------
# Contrast: every text/background pair a theme produces
# --------------------------------------------------------------------------

@pytest.mark.parametrize("theme", THEMES)
def test_every_theme_meets_contrast(theme):
    pal = house_style.Palette(_resolve(theme=theme))
    floor = 7.0 if theme == "high-contrast" else 4.5
    pairs = {
        "body text on page": (pal.ink, pal.page),
        "body text on row": (pal.ink, pal.row),
        "body text on zebra": (pal.ink, pal.zebra),
        "body text on panel": (pal.ink, pal.panel),
        "header text on table head": (pal.table_head_ink, pal.table_head),
        "title on band": (pal.title_ink, pal.navy),
        "org text on band": (pal.org_ink, pal.navy),
        "heading on page": (pal.heading, pal.page),
        "muted on page": (pal.muted, pal.page),
        "classification bar": ("#FFFFFF", pal.classification),
        "handling notice": (pal.handling_ink, pal.handling_bg),
    }
    bad = {k: round(contrast(*v), 2) for k, v in pairs.items() if contrast(*v) < floor}
    assert not bad, f"{theme} below {floor}:1 -> {bad}"


@pytest.mark.parametrize("theme", THEMES)
def test_every_theme_keeps_the_table_grid_visible(theme):
    """A border the same colour as the cell is no border. 1.3:1 is a floor
    for a visible non-text edge, well under WCAG's 3:1 for UI components on
    purpose: a black grid on a black page is the failure, not a subtle one."""
    pal = house_style.Palette(_resolve(theme=theme))
    assert contrast(pal.table_border, pal.row) >= 1.3


@pytest.mark.parametrize("theme", THEMES)
def test_sop_colours_meet_contrast(theme):
    b = _resolve(theme=theme)
    page = "#" + (b.sop.get("page") or "FFFFFF").lstrip("#")
    for key in ("body", "heading", "title", "link"):
        assert contrast("#" + b.sop[key].lstrip("#"), page) >= 4.5, f"{theme} sop.{key}"


# --------------------------------------------------------------------------
# Density
# --------------------------------------------------------------------------

def test_compact_tightens_the_table():
    css = house_style.stylesheet(house_style.Palette(_resolve(density="compact")), "report")
    assert "padding:3px 6px" in css and "font-size:11.5px" in css


def test_comfortable_equals_the_default():
    a = house_style.stylesheet(house_style.Palette(_resolve()), "report")
    b = house_style.stylesheet(house_style.Palette(_resolve(density="comfortable")), "report")
    assert a == b


def test_density_combines_with_any_theme():
    b = _resolve(theme="red", density="compact")
    red = resolve_brand.load_overlay("theme", "red")[1]
    assert b.report["navy"] == red["report"]["navy"]
    assert b.report["density"]["cell_pad"] == "3px 6px"


# --------------------------------------------------------------------------
# Dark pages survive conversion
# --------------------------------------------------------------------------

def test_white_page_report_is_unmarked():
    html = build_report.build(build_report.EXAMPLE, _resolve(theme="professional"))
    assert house_style.PAGE_META not in html and "bgcolor" not in html


@pytest.mark.parametrize("theme", ["midnight", "high-contrast"])
def test_dark_page_report_is_marked_three_ways(theme, tmp_path):
    pal = house_style.Palette(_resolve(theme=theme))
    html = build_report.build(build_report.EXAMPLE, _resolve(theme=theme))
    assert f"background:{pal.page}" in html
    assert f'<body bgcolor="{pal.page}">' in html
    assert f'<meta name="{house_style.PAGE_META}" content="{pal.page}">' in html
    src = tmp_path / "r.html"
    src.write_text(html, encoding="utf-8")
    h = pal.page.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    assert build_report.page_colour(str(src)) == r + (g << 8) + (b << 16)


def test_apply_to_html_marks_a_dark_guide():
    pal = house_style.Palette(_resolve(theme="midnight"))
    out = house_style.apply_to_html("<html><head><style></style></head><body><h1>x</h1></body></html>",
                                    pal, "guide")
    assert f'bgcolor="{pal.page}"' in out


@pytest.mark.parametrize("theme,dark", [("professional", False), ("midnight", True)])
def test_sop_page_colour(theme, dark, tmp_path):
    pytest.importorskip("docx")
    import build_sop  # pylint: disable=import-outside-toplevel
    brand = _resolve(theme=theme)
    b = build_sop.SopBuilder("Title", "Sub", brand=brand)
    b.para("Hello")
    out = b.save(str(tmp_path / "s.docx"))
    with zipfile.ZipFile(out) as z:
        doc = z.read("word/document.xml").decode()
        settings = z.read("word/settings.xml").decode()
    assert ("<w:background" in doc) is dark
    assert ("displayBackgroundShape" in settings) is dark
    if dark:
        assert build_report.page_colour(out) is not None


# --------------------------------------------------------------------------
# Gallery
# --------------------------------------------------------------------------

def test_gallery_covers_every_theme():
    stems = {s for s, *_ in build_gallery.samples()}
    assert set(THEMES) <= stems and "professional-compact" in stems


def test_gallery_is_current():
    assert build_gallery.main(["--check"]) == 0


def test_every_theme_file_is_self_describing():
    for name in THEMES:
        _, data = resolve_brand.load_overlay("theme", name)
        assert data.get("label") and data.get("description"), name
        assert set(data) <= {"_comment", "name", "label", "description", "sources",
                             "report", "sop"}, name
        json.dumps(data)
