"""The house stylesheet is SHARED, is branded, and survives in both profiles.

Three properties, and the first is the one that earns this file:

1. `build_report.stylesheet()` IS `house_style.stylesheet(..., "report")` --
   not a copy of it. The CSS used to live inside build_report.py and nothing
   else could reach it; the defect that made this module was a hand-authored
   page having no way to ask for the same defaults, so it copied a palette
   literal and stayed neutral forever. Re-inlining the CSS into build_report
   would restore exactly that, and `test_build_report_stylesheet_is_not_a_fork`
   goes red if anyone does.

2. Every element of the contract -- the table grid, the navy header shading,
   the zebra rows, the meta-table key shading, the summary-card panels, and
   the print rules -- appears in BOTH profiles, carrying the resolved brand's
   own hex. The expected declarations here are built from the brand JSON that
   `resolve_brand` returns, NOT from house_style, so breaking the shared CSS in
   one place goes red rather than agreeing with itself.

3. `title_case` preserves a token that already carries its own capitalisation.
   `str.title()` is wrong at every one of PowerShell, SOP, macOS, EF Core and
   doc-builder, and this repository's prose is full of such tokens.

SABOTAGE CHECK for (2): change `{pal.zebra}` in `house_style.table_css` to a
literal `#FFFFFF` and `test_zebra_rows_carry_the_brand_zebra[report]` and
`[guide]` both go red, naming the declaration that went missing.

NOT COVERED HERE: what the CSS looks like when a browser or Word renders it.
Every assertion below is on the HTML/CSS string. Fidelity in Word is
`references/word-traps.md` plus `checklist.sh`, which runs the greppable half
of it against an artifact the builder actually emitted.
"""
from __future__ import annotations

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

PROFILES = ("report", "guide")

# The table selector, and the CELL prefix, each profile uses. The report path
# also emits layout tables (masthead, meta pairs, cards) that must NOT pick the
# grid up, so it scopes both; a hand-authored guide's tables are all data
# tables and its cells are selected BARE, because LibreOffice's HTML import
# applies a bare `th { background }` and drops a table-scoped one. See
# `house_style.table_css`.
TABLE_SEL = {"report": "table.data", "guide": "table"}
CELL_PRE = {"report": "table.data ", "guide": ""}


def _brand(name):
    return resolve_brand.resolve(explicit=name, announce=False)


def _pal(name):
    return house_style.Palette(_brand(name))


@pytest.fixture(params=["neutral", "solomon"])
def brand_name(request):
    if request.param == "solomon" and not _SOLOMON_JSON.is_file():
        pytest.skip("solomon-doc-builder is not checked out as doc-builder's sibling here")
    return str(_SOLOMON_JSON) if request.param == "solomon" else "neutral"


# --------------------------------------------------------------------------
# 1. One copy of the CSS, not two
# --------------------------------------------------------------------------

def test_build_report_stylesheet_is_not_a_fork(brand_name):
    """Character for character, so a "small tweak" made in build_report.py
    rather than in the shared module cannot ship. This is the test that stops
    the CSS drifting back into two copies."""
    pal = _pal(brand_name)
    assert build_report.stylesheet(pal) == house_style.stylesheet(pal, "report")


def test_build_report_emits_the_shared_stylesheet_into_the_document(brand_name):
    """And the module-level equality is not enough on its own: `build()` has to
    actually put it in the page."""
    brand = _brand(brand_name)
    out = build_report.build({"title": "Report", "organisation": "CONTOSO"}, brand)
    assert house_style.stylesheet(house_style.Palette(brand), "report") in out


def test_an_unknown_profile_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown profile"):
        house_style.stylesheet(_pal("neutral"), "brochure")


# --------------------------------------------------------------------------
# 2. The contract, in both profiles, from the brand's own values
# --------------------------------------------------------------------------

@pytest.fixture(params=PROFILES)
def profile(request):
    return request.param


def _css(brand_name, profile):
    return house_style.stylesheet(_pal(brand_name), profile)


def test_tables_carry_the_brand_grid(brand_name, profile):
    css = _css(brand_name, profile)
    grid = _brand(brand_name).report["grid"]
    pre = CELL_PRE[profile]
    assert f"{pre}th, {pre}td {{ border:1px solid {grid};" in css


def test_table_headers_carry_the_brand_navy(brand_name, profile):
    css = _css(brand_name, profile)
    navy = _brand(brand_name).report["navy"]
    pre = CELL_PRE[profile]
    assert f"{pre}th {{ background:{navy}; color:#FFFFFF; font-weight:600; }}" in css


def test_zebra_rows_carry_the_brand_zebra(brand_name, profile):
    """Zebra is an explicit class written per row, never `:nth-child` -- Word
    drops the pseudo-class silently. word-traps.md rule 2."""
    css = _css(brand_name, profile)
    zebra = _brand(brand_name).report["zebra"]
    pre = CELL_PRE[profile]
    assert f"{pre}tr.alt td {{ background:{zebra}; }}" in css
    assert ":nth-child" not in css


def test_meta_table_key_column_is_shaded(brand_name, profile):
    css = _css(brand_name, profile)
    r = _brand(brand_name).report
    assert f"table.meta td {{ border:1px solid {r['grid']};" in css
    assert f"table.meta td.k {{ background:{r['zebra']}; font-weight:600; width:17%; }}" in css


def test_summary_cards_are_panels(brand_name, profile):
    css = _css(brand_name, profile)
    r = _brand(brand_name).report
    assert f"td.card {{ background:{r['panel']}; border:1px solid {r['grid']};" in css
    assert f"div.n {{ font-size:22px; font-weight:700; color:{r['navy']}; }}" in css


def test_severity_chips_survive_in_both_profiles(brand_name, profile):
    css = _css(brand_name, profile)
    for sev, (bg, fg) in _brand(brand_name).report["severity"].items():
        assert f".chip-{sev} {{ background:{bg}; color:{fg}; }}" in css


def test_print_rules_survive_in_both_profiles(brand_name, profile):
    css = _css(brand_name, profile)
    assert "tr { page-break-inside:avoid; }" in css
    assert "thead { display:table-header-group; }" in css
    assert "page-break-after:avoid" in css


def test_the_guide_profile_widens_the_page_break_rule_to_h3():
    """A hand-authored page has H3 sections; the report path emits none. An H3
    orphaned at the foot of a page is the same defect at either level."""
    assert "h2, h3 { page-break-after:avoid; }" in _css("neutral", "guide")
    assert "h2 { page-break-after:avoid; }" in _css("neutral", "report")


def test_no_profile_emits_anything_word_drops_silently(profile):
    """The same literals `checklist.sh` greps an emitted report for, applied to
    the stylesheet itself so the guide profile is covered too."""
    css = _css("neutral", profile)
    for trap in ("var(--", ":nth-child", ":first-child", "::before", "::after",
                 ":hover", "display:flex", "display:grid"):
        assert trap not in css, trap


# --------------------------------------------------------------------------
# The brand actually lands -- which is the defect that made this module
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _SOLOMON_JSON.is_file(),
                    reason="solomon-doc-builder is not checked out as doc-builder's sibling here")
def test_a_solomon_stylesheet_carries_solomons_navy_and_a_neutral_one_does_not(profile):
    """`docs/guides/*.html` all carried `#1F4E79` and not one carried
    `#0E2841`, because a hand-written path never called resolve_brand. Both
    halves are asserted: the Solomon render has Solomon's navy AND does not
    still have the neutral one."""
    solomon = _css(str(_SOLOMON_JSON), profile)
    neutral = _css("neutral", profile)
    assert "#0E2841" in solomon
    assert "#1F4E79" not in solomon
    assert "#1F4E79" in neutral
    assert "#0E2841" not in neutral


# --------------------------------------------------------------------------
# 3. Title case
# --------------------------------------------------------------------------

@pytest.mark.parametrize("token", [
    "PowerShell", "SOP", "macOS", "EF", "DbContext", "iOS", "JSON", "CLI",
    "0.19.93", "build_report.py", "PS7", "ADSync",
])
def test_a_token_carrying_its_own_capitalisation_is_preserved_anywhere(token):
    """The preserve rule, checked in every position a token can occupy --
    first, middle and last -- because `str.title()` gets all three wrong and a
    rule that only fired in the middle would look correct in most headings."""
    assert house_style.title_case(f"{token} notes for review") .startswith(token)
    assert token in house_style.title_case(f"notes on {token} for review")
    assert house_style.title_case(f"review notes for {token}").endswith(token)


def test_a_hyphenated_product_name_survives_unchanged():
    """`doc-builder` is all lower case and carries no interior capital, no
    digit and no dot, so no mechanical rule can tell it from prose -- it is in
    PRESERVE_TOKENS, and that is what the list is for."""
    assert house_style.title_case("the doc-builder pipeline") == "The doc-builder Pipeline"
    assert house_style.title_case("doc-builder notes") == "doc-builder Notes"
    assert house_style.title_case("notes on doc-builder") == "Notes on doc-builder"


def test_a_possessive_does_not_defeat_the_preserve_rule():
    """`obsidian-git's` has to find `obsidian-git`, and `it's` must never come
    back as `It'S` the way `str.title()` renders it."""
    assert house_style.title_case("obsidian-git's failure mode") == \
        "obsidian-git's Failure Mode"
    assert house_style.title_case("it's a known trap") == "It's a Known Trap"


def test_str_title_would_fail_every_one_of_these():
    """Stated as an assertion rather than a comment: if some future `title_case`
    quietly became `str.title()`, the tests above would go red -- and so does
    this one, which says WHY in one place."""
    for token in ("PowerShell", "SOP", "macOS", "doc-builder"):
        assert token.title() != token


def test_ordinary_words_are_cased():
    assert house_style.title_case("what the gardener does") == "What the Gardener Does"
    assert house_style.title_case("two sync mechanisms, and why both is a risk") == \
        "Two Sync Mechanisms, and Why Both Is a Risk"


def test_small_words_are_lowered_in_the_middle_only():
    """First and last word are always capitalised, small word or not."""
    assert house_style.title_case("the rise and fall of the gate") == \
        "The Rise and Fall of the Gate"
    assert house_style.title_case("a guide to") == "A Guide To"


def test_the_word_after_a_colon_opens_a_clause():
    assert house_style.title_case("the crew plugin: an overview for everyone") == \
        "The Crew Plugin: An Overview for Everyone"


def test_a_leading_number_does_not_consume_the_first_word_rule():
    assert house_style.title_case("1. the problem") == "1. The Problem"
    assert house_style.title_case("6. changes 0.19.90 to 0.19.92") == \
        "6. Changes 0.19.90 to 0.19.92"


def test_whitespace_and_empty_input_survive():
    assert house_style.title_case("") == ""
    assert house_style.title_case("   ") == "   "
    assert house_style.title_case("a  b") == "A  B"


def test_build_report_cases_the_title_it_renders():
    """Not a per-document edit: the builder cases every heading it emits, so a
    JSON document typed in sentence case still renders a proper title."""
    brand = _brand("neutral")
    out = build_report.build(
        {"title": "entra password posture for macOS",
         "findings": {"heading": "the findings", "columns": ["ID"], "rows": [["X"]]}},
        brand)
    assert '<div class="mast-title">Entra Password Posture for macOS</div>' in out
    assert "<h2>The Findings</h2>" in out


# --------------------------------------------------------------------------
# Applying the house style to a hand-authored page
# --------------------------------------------------------------------------

_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>A page</title>
<style>
body { font-family: Calibri; }
h1 { color: #1F4E79; }
</style>
</head><body>
<h1>the crew plugin: an overview</h1>
<h2>1. the problem</h2>
<h3>what the <code>PM</code> does</h3>
<p>Body text mentioning #1F4E79 stays put.</p>
</body></html>
"""


def test_apply_replaces_the_style_block_and_keeps_the_body():
    out = house_style.apply_to_html(_PAGE, _pal("neutral"), "guide")
    assert "font-family: Calibri;" not in out
    assert "tr.alt td { background:" in out
    assert "<p>Body text mentioning #1F4E79 stays put.</p>" in out
    assert out.count("<style>") == 1


def test_apply_title_cases_headings_and_leaves_inline_tags_alone():
    out = house_style.apply_to_html(_PAGE, _pal("neutral"), "guide")
    assert "<h1>The Crew Plugin: An Overview</h1>" in out
    assert "<h2>1. The Problem</h2>" in out
    assert "<h3>What the <code>PM</code> Does</h3>" in out


def test_apply_can_restyle_without_touching_headings():
    out = house_style.apply_to_html(_PAGE, _pal("neutral"), "guide", headings=False)
    assert "<h1>the crew plugin: an overview</h1>" in out
    assert "tr.alt td { background:" in out


def test_apply_injects_a_style_block_when_the_page_has_none():
    page = "<html><head><title>x</title></head><body><h1>a page</h1></body></html>"
    out = house_style.apply_to_html(page, _pal("neutral"), "guide")
    assert out.index("<style>") < out.index("</head>")
    assert "tr.alt td { background:" in out


def test_apply_refuses_a_page_it_cannot_style_rather_than_half_styling_it():
    with pytest.raises(ValueError, match="no <style> element and no </head>"):
        house_style.apply_to_html("<h1>fragment</h1>", _pal("neutral"), "guide")


def test_cli_emits_the_stylesheet_for_a_named_brand(capsys):
    assert house_style.main(["--brand", "neutral", "--profile", "guide"]) == 0
    out = capsys.readouterr().out
    assert out == house_style.stylesheet(_pal("neutral"), "guide")


def test_cli_title_case_needs_no_brand_and_writes_nothing(capsys):
    assert house_style.main(["--title-case", "the powershell SOP"]) == 0
    assert capsys.readouterr().out.strip() == "The PowerShell SOP"


def test_apply_cases_the_document_title_too():
    """The tab title is the same heading. `build_report.py` already cases it,
    and a page with a cased <h1> and a sentence-case <title> looks like the
    styling only half ran."""
    out = house_style.apply_to_html(_PAGE, _pal("neutral"), "guide")
    assert "<title>A Page</title>" in out


def test_apply_leaves_the_document_title_alone_with_headings_off():
    out = house_style.apply_to_html(_PAGE, _pal("neutral"), "guide", headings=False)
    assert "<title>A page</title>" in out


def test_the_guide_profile_selects_cells_bare_and_the_report_profile_scopes_them():
    """Measured, not preferred. soffice 26.2.5.2 applies `th { background }`
    and DROPS `table.z th { background }`, so scoping a guide's cells removes
    the navy header shading from its .docx and .pdf while leaving the browser
    unchanged -- invisible in the HTML, invisible in a browser, and wrong in
    the artifact anyone actually files. The report path keeps its scope because
    a bare `td` there would border and shade the masthead's own cells.
    """
    guide = _css("neutral", "guide")
    report = _css("neutral", "report")
    navy = _brand("neutral").report["navy"]
    assert f"\nth {{ background:{navy};" in guide
    assert "table th {" not in guide
    assert f"table.data th {{ background:{navy};" in report
    assert "\nth {" not in report
