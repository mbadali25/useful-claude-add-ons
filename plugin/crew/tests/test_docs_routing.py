"""`crew-house-style`'s routing table is prose, and prose is what went wrong.

The whole `docs.theme` ticket exists because two shipped files described a
pass-through to doc-builder in the present tense while no such code path
existed. Nothing parses this table at runtime -- an agent reads it and acts --
so a test is the only thing that can keep it honest about a tool it does not
import.

Two directions are checked here, and the second is the one that matters:

  * The table SAYS the things the design decided -- doc-builder is routed,
    both config keys are named and bound to a genre, and the two degraded
    paths are stated as two distinct sentences.
  * The interface it names actually EXISTS. `--brand` is asserted by running
    each script's own argparse, not by grepping for the string. A routing
    entry that names a flag the tool does not accept is the same defect the
    ticket was opened for, one layer out, and grepping a docstring that merely
    MENTIONS `--brand` would have "confirmed" it either way.
"""
import os
import re
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import pytest

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_HOUSE_STYLE = os.path.join(_PLUGIN, "skills", "crew-house-style", "SKILL.md")

# doc-builder is a SEPARATE marketplace entry, not bundled with crew, so this
# reaches out of the plugin and into the repo. That is the honest shape: the
# claim under test is precisely "crew's prose describes another entry's real
# interface", and it cannot be checked without looking at that entry.
_REPO = os.path.join(_PLUGIN, os.pardir, os.pardir)
_DOC_BUILDER_SCRIPTS = os.path.join(_REPO, "skills", "doc-builder", "scripts")

# Genre -> (script the routing table names, module it needs at import time).
#
# The second field is the difference between a test that can run anywhere and
# one that breaks CI. `build_report.py` is stdlib -- its `win32com` import is
# lazy, inside the converter function, and it touches no `docx` -- so its
# `--help` runs on any machine. `build_sop.py` imports `docx` (python-docx) at
# module level, and crew's CI installs only pytest and pyyaml, so running it
# there would fail on a MISSING DEPENDENCY and look like a routing defect.
#
# Adding python-docx to crew's CI to satisfy one assertion is the wrong trade:
# doc-builder is a separate marketplace entry and crew's job should not own its
# dependency tree. Stubbing `docx` is worse -- it needs seven submodules by
# exact name and would rot silently the moment build_sop imports an eighth.
_ROUTED_SCRIPTS = {
    "findings report": ("build_report.py", None),
    "SOP": ("build_sop.py", "docx"),
}


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _usage_line(help_text):
    """argparse's own `usage:` block, flattened to one line.

    Wrapped across several lines for a parser with many options, so the block
    runs from `usage:` to the first blank line.
    """
    after = help_text.split("usage:", 1)
    assert len(after) == 2, help_text[:300]
    block = after[1].split("\n" + "\n", 1)[0]
    return " ".join(block.split())


def _importable(module):
    """Whether `module` imports in a FRESH interpreter.

    Deliberately not `importlib.util.find_spec` in this process: the subprocess
    under test gets its own interpreter and its own sys.path, and answering
    from this one could say "available" about a module the child cannot see.
    """
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL).returncode == 0


def _requires_doc_builder():
    if not os.path.isdir(_DOC_BUILDER_SCRIPTS):
        pytest.skip(
            "doc-builder is not in this checkout at "
            f"{os.path.normpath(_DOC_BUILDER_SCRIPTS)} -- crew's tests are "
            "running outside the marketplace repo, so the cross-entry claim "
            "cannot be checked here"
        )


def _degraded_paths():
    """The two degraded-path bullets, separately.

    Returned as a pair so each can be asserted on its own. Checking the whole
    section for keywords is what let a conflated pair pass: "Word" and
    "PARTIAL" both survive rewriting the second bullet into a copy of the
    first, and that rewrite is exactly the defect.
    """
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]
    marker = "- **doc-builder is "
    parts = generating.split(marker)
    assert len(parts) == 3, (
        f"expected exactly two `{marker}...` bullets, found {len(parts) - 1}")
    return parts[1], parts[2]


def _doc_builder_bullet():
    """Just the `- `doc-builder` —` routing bullet, up to the next top-level item.

    Scoped deliberately. The genre binding lives in this bullet, and asserting it
    against the whole "Generating it" section made the test a hostage to every
    other sentence that happens to name the key -- the degraded-path rules below
    the table name both keys for unrelated reasons, and an assertion of the form
    "EVERY line mentioning reportTheme must say findings report" turns each of
    those into a false failure. Both existing sabotage mutations rewrite text
    inside this bullet, so narrowing to it costs no coverage: verified by running
    them.
    """
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]
    lines = generating.split("\n")
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("- `doc-builder` —"))
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("- `")), len(lines))
    return lines[start:end]


def test_the_routing_table_routes_doc_builder_and_names_both_keys():
    """The call site. Before this, `docs.theme` configured a tool crew's own
    documented generation path never mentioned -- the table routed DOCX and
    PDF to `anthropic-office-skills` and named doc-builder nowhere, so there
    was nothing for a `--brand` to attach to."""
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]

    # The ROUTE, not a mention. `doc-builder` appears several times in the
    # prose around the table -- in the additive-and-narrow paragraph and in
    # both degraded paths -- so `"doc-builder" in generating` passes even
    # with the routing bullet deleted. Asserted as a top-level list item,
    # which is the thing an agent reads as "route here".
    routes = [line for line in generating.split("\n")
              if line.startswith("- `")]
    assert any(line.startswith("- `doc-builder` —") for line in routes), routes

    assert "--brand" in generating
    assert "docs.theme" in generating
    assert "docs.reportTheme" in generating


def test_the_two_config_keys_are_bound_to_different_genres():
    """Otherwise `reportTheme` quietly becomes a synonym for `theme`.

    The key only earns its place if a findings report can carry a different
    brand from the surrounding docs -- a client-facing deliverable out of an
    internal repo. If the table named only `docs.theme`, or named both without
    saying which wins for a report, the second key would resolve to the first
    in every real case and nobody would ever see the difference."""
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]

    # The report genre prefers reportTheme, and says so in one sentence with
    # both names in it -- not two unrelated mentions elsewhere in the file.
    report_rule = [line for line in _doc_builder_bullet()
                   if "docs.reportTheme" in line]
    assert report_rule, "no line in the doc-builder bullet binds docs.reportTheme"

    # `"findings report"`, NOT `"report"`. Testing for "report" here was
    # tautological and shipped that way: `"docs.reportTheme".lower()` contains
    # "report", so the second assertion could not fail once the first passed,
    # and the genre binding -- the whole point of the test -- was unchecked.
    # The sabotage entry did not reveal it either, because that mutation
    # deletes the key from the sentence and so trips the FIRST assertion.
    #
    # A passing mutation proves the TEST failed, never which assertion did.
    # This phrasing fails on "for every document prefer `docs.reportTheme`",
    # which is exactly the rewrite that turns the second key into a synonym
    # for the first.
    assert all("findings report" in line for line in report_rule), report_rule

    # And null is defined, because that is what the default now is.
    assert "null theme passes no `--brand`" in generating


def test_the_two_keys_can_actually_hold_different_values():
    """The config half of the same claim. Both keys are settable in both
    layers and resolve independently -- a merge that collapsed one into the
    other would make the routing rule above undeliverable no matter how
    clearly it is written."""
    for dotted in ("docs.theme", "docs.reportTheme"):
        assert crew_config.is_global_path(dotted), dotted

    merged = crew_state.merge_defaults(
        crew_config.default_config(),
        {"docs": {"theme": "acme", "reportTheme": "acme-client"}})

    assert merged["docs"]["theme"] == "acme"
    assert merged["docs"]["reportTheme"] == "acme-client"
    assert merged["docs"]["theme"] != merged["docs"]["reportTheme"]


@pytest.mark.parametrize("genre,script,needs",
                         [(g, s, n) for g, (s, n) in sorted(
                             _ROUTED_SCRIPTS.items())])
def test_every_routed_script_exists_and_accepts_brand(genre, script, needs):
    """The direction that would have caught this ticket's original defect.

    Asserted by RUNNING each script's argparse, never by grepping the file.
    Both scripts' docstrings contain the literal string `--brand` in an
    example, so a grep passes whether or not the flag is wired to anything --
    which is exactly how a doc comes to describe an interface that does not
    exist. `--help` is the tool's own answer.

    When the script's import-time dependency is absent the check does NOT
    become a skip. It asserts that the failure is exactly that missing module
    and nothing else, so the script breaking for any other reason still fails
    here. A bare skip would be a check nobody has ever seen fail, which is the
    defect class this suite exists for."""
    _requires_doc_builder()
    path = os.path.join(_DOC_BUILDER_SCRIPTS, script)
    assert os.path.isfile(path), f"{genre}: {path}"

    proc = subprocess.run(
        [sys.executable, path, "--help"],
        capture_output=True, text=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL)

    if needs is not None and not _importable(needs):
        # The documented, expected failure -- and it must be THAT one.
        assert proc.returncode != 0, (
            f"{script} ran without {needs}; the dependency note in "
            "_ROUTED_SCRIPTS is now wrong and this test is weaker than it "
            "reads")
        assert f"No module named '{needs}'" in proc.stderr, proc.stderr[-600:]
        return

    assert proc.returncode == 0, proc.stderr

    # Asserted on argparse's GENERATED usage line, not on the help text as a
    # whole. `--help` prints the module docstring too, and both docstrings
    # carry a `--brand neutral` example -- so `"--brand" in proc.stdout`
    # passes with the flag deleted, which the sabotage suite caught by coming
    # back green. The usage line is written by argparse from the parser it
    # actually built, so it cannot say `[--brand` unless the option is there.
    usage = _usage_line(proc.stdout)
    assert "[--brand" in usage, (genre, usage)


def test_the_routed_scripts_are_the_ones_the_table_names():
    """The mapping in `_ROUTED_SCRIPTS` is only worth testing if it is the
    mapping the table actually publishes. Renaming a script in the table
    without renaming it here would leave this file happily checking two
    scripts nobody is routed to.

    Scoped to the routing bullet, not to the whole `## Generating it` section,
    and the sabotage suite measured why. The section-wide form was red until
    the HTML route was added below it; that route CITES
    `build_report.py:<line>` twice as the generator proving its print block,
    so `"build_report.py" in generating` stayed true with the routing bullet
    renamed to a script that does not exist, and the mutation came back STILL
    GREEN. A citation is not a route. The bullet is the thing an agent reads
    as "run this", which is the claim under test."""
    bullet = "\n".join(_doc_builder_bullet())

    for genre, (script, _needs) in _ROUTED_SCRIPTS.items():
        assert script in bullet, (genre, bullet)


def test_the_two_degraded_paths_are_stated_separately():
    """Not-installed and installed-but-no-Word are different failures with
    different fixes, and naming the wrong one sends the reader to fix the
    wrong thing.

    Word's absence is a PARTIAL loss: `doc-builder/SKILL.md` says it costs
    `--to-docx`/`--to-pdf` and Gate 2 while HTML and `.docx` are still
    produced. So the branded artefact still exists in that case, and telling
    someone doc-builder is not installed -- or discarding a document that was
    successfully built -- is wrong twice over."""
    missing, no_word = _degraded_paths()

    # The not-installed path: route elsewhere, lose the branding, say so.
    assert "not installed" in missing
    assert "unbranded" in missing
    assert "anthropic-office-skills" in missing

    # The Word path is PARTIAL, and must name what is still produced. Checking
    # only for the word "Word" or "PARTIAL" somewhere in the section is not
    # enough -- both survive rewriting this bullet into "fall back unbranded",
    # which is the conflation the test exists to catch. The artefacts are the
    # discriminator: doc-builder without Word still emits the branded HTML
    # report and the branded SOP `.docx`, so a fallback that discards them
    # throws away a document that was successfully built.
    assert "Word" in no_word
    assert "HTML" in no_word
    assert ".docx" in no_word
    assert "PARTIAL" in no_word

    # And it must rule the not-installed message OUT by name. A bare
    # `"not installed" not in no_word` is wrong here and was: this bullet
    # quotes that message precisely in order to forbid it, so the absence of
    # the string would mean the prohibition had been deleted, not that the
    # misdiagnosis had. The prohibition itself is the thing to assert.
    assert "are both wrong" in no_word
    assert "not a fall back to unbranded" in no_word


def test_crew_is_told_not_to_detect_word_itself():
    """The rule at the top of the routing list is "Do not reimplement any of
    them", and a Word probe in crew is precisely that -- a second copy of
    doc-builder's capability check, which goes stale the moment doc-builder's
    requirements change. The condition crew is allowed to test is whether
    doc-builder is installed."""
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]

    assert "Do not detect Word yourself" in generating


def test_an_unresolvable_theme_is_relayed_and_never_falls_back():
    """A theme naming a pack doc-builder cannot find is a THIRD failure, and it
    is not either of the two above: doc-builder is installed and Word is
    irrelevant. The config is wrong.

    Falling back to unbranded here is the worst available outcome. A config that
    names a brand is an explicit instruction, so an unbranded document is wrong
    in the one way the user configured against -- and nothing in the artefact
    says so. A document that was not produced costs a minute; a wrongly-branded
    one sent to a client does not.

    Asserted against doc-builder's real behaviour rather than a paraphrase:
    BrandNotFound subclasses BrandError(SystemExit), so the script already exits
    non-zero with a message naming the installed packs.
    """
    house = _read(_HOUSE_STYLE)
    section = house.split("### When the configured theme does not resolve", 1)
    assert len(section) == 2, "no section covers an unresolvable theme"
    rule = section[1]

    # Relay, and stop. Both halves, because "do not fall back" without "relay"
    # leaves an agent with no instruction at all.
    assert "Relay doc-builder's error and stop" in rule
    assert "Do not fall back to unbranded" in rule

    # It must name the real exception, not describe one. A paraphrase goes stale
    # silently; a name can be grepped for when doc-builder changes.
    assert "BrandNotFound" in rule
    assert "resolve_brand.py" in rule

    # And it must forbid crew pre-validating the name -- the same rule as
    # "Do not detect Word yourself", which is already asserted separately.
    assert "Do not validate the theme name before calling" in rule


def test_crew_is_not_told_to_allowlist_theme_names():
    """The reason the prohibition above is not merely stylistic.

    doc-builder accepts more than pack names -- a skill directory name, a path
    to a brand.json, a directory holding one, and `neutral` whether or not a
    pack of that name exists. A crew-side allowlist built from installed pack
    names would therefore reject valid configuration, which fails in the
    expensive direction: the work is blocked and the config looks fine.

    This test reads doc-builder's own resolver, so it goes red if that widens or
    narrows and crew's prose stops matching it.
    """
    resolver = os.path.join(_DOC_BUILDER_SCRIPTS, "resolve_brand.py")
    assert os.path.exists(resolver), resolver
    src = _read(resolver)

    # The four accepted shapes, and the always-valid name.
    assert "if wanted.lower() == \"neutral\":" in src
    assert "if os.path.isfile(wanted):" in src
    assert "if os.path.isdir(wanted):" in src
    assert "skill_dir.lower()" in src
    assert "raise BrandNotFound(wanted, names)" in src

    # crew's prose has to say WHY, not just "do not" -- a bare prohibition gets
    # optimised away by the next person who thinks they are helping.
    rule = _read(_HOUSE_STYLE).split(
        "### When the configured theme does not resolve", 1)[1]
    assert "skill directory name" in rule
    assert "fail closed on correct configuration" in rule


def test_anthropic_office_skills_keeps_docx_and_pdf():
    """doc-builder's entry is additive. It must not take the general formats
    over, because its converter needs Microsoft Word through COM and
    `anthropic-office-skills` needs neither -- routing all DOCX and PDF to
    doc-builder would break crew's document path on Linux and macOS.

    This is the assertion that fails if someone later "simplifies" the table
    by giving doc-builder the formats outright."""
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]

    assert "- `anthropic-office-skills:docx` — DOCX" in generating
    assert "- `anthropic-office-skills:pdf` — PDF" in generating
    assert "fallback" in generating


# The HTML route's two print rules, as (selector, declaration) pairs rather
# than as one literal block. The same three declarations have to be found in
# two files written in different dialects -- crew's prose has them in plain
# CSS, `build_report.py` has them inside an f-string where every brace is
# doubled -- so a literal-substring assertion can only ever check one of them,
# and checking only crew's copy is how the prose comes loose from the
# generator that proves it works.
# The three doc-builder's generator emits, which are the three crew cites it
# for. Kept separate from the route's own set below: the report profile names
# `h2` alone and asserting the widened set against it would fail on a
# generator that is not wrong -- it emits no `h3` at all.
_GENERATOR_RULES = (
    ("h2", "page-break-after:avoid"),
    ("tr", "page-break-inside:avoid"),
    ("thead", "display:table-header-group"),
)

_PRINT_RULES = _GENERATOR_RULES + (("h3", "page-break-after:avoid"),)

# The one selector of the three that `house_style.print_css` takes as a
# PARAMETER instead of emitting literally: `stylesheet()` passes `"h2"` for the
# report profile and `"h2, h3"` for the guide profile, and the source line
# reads `f"  {headings} {{ page-break-after:avoid; }}"`. So NO source line of
# house_style.py contains the string `h2` bound to that declaration, by design
# and not by accident.
#
# Every source-TEXT check below therefore skips this selector by name and says
# it is doing so. It is checked instead against the CSS the module actually
# emits, by `test_the_generated_stylesheet_emits_the_print_rules`, which is the
# stronger of the two directions -- it survives reformatting and it proves the
# rule reaches the page. Loosening `_declares` until the source matched again
# would have deleted the check while turning the red green, which is the guard
# fix this repository's CLAUDE.md names as the failure mode.
_PARAMETERISED_SELECTOR = "h2"

# One CSS rule: a selector list, a brace, a body, a brace. The repeated `{`
# and `}` accept the doubled braces of `build_report.py`'s f-string as well as
# plain CSS, which is the whole reason these are matched as rules rather than
# compared as one literal block.
_CSS_RULE_RE = re.compile(r"([^{}]+?)\{+([^{}]*?)\}+")


def _declares(source, selector, declaration):
    """Whether `source` binds `declaration` to `selector`, in either dialect.

    The selector is looked for inside a comma-separated LIST, not as the whole
    left-hand side. crew's HTML route widens doc-builder's `h2` to `h2, h3` --
    the house style allows an H3 and doc-builder's report generator emits none
    -- and a match anchored on the entire selector would read that widening as
    the rule having been deleted.
    """
    flat = " ".join(source.split())
    for rule in _CSS_RULE_RE.finditer(flat):
        selectors = [part.strip() for part in rule.group(1).split(",")]
        if selector in selectors and declaration in rule.group(2):
            return True
    return False


def _css_from_python(source):
    """`source` with Python's string quoting taken off, so `_declares` sees CSS.

    NOT a loosening of `_declares` -- the container is what changed, not the
    thing being matched. In `house_style.py` every CSS rule is its own Python
    string literal, so between one rule's `}` and the next rule's selector the
    raw source carries `\\n` and a pair of quote characters. `_CSS_RULE_RE`
    reads those as part of the selector, so `tr` becomes `\\n" " tr` and
    matches nothing -- a false RED, on a generator that is perfectly correct.

    Two substitutions and no more: the two-character `\\n` escape becomes a
    newline, and quote characters become spaces. The doubled braces of an
    f-string are deliberately left alone, because `_declares` already accepts
    them (`\\{+` / `\\}+`) and that is where the handling belongs.
    """
    return source.replace("\\n", "\n").replace('"', " ").replace("'", " ")


def _html_route():
    """The `### HTML` subsection alone, up to the next `###`.

    Scoped for the same reason `_doc_builder_bullet` is. `<thead>` and
    `page-break` could be mentioned anywhere in a file this long -- in the
    palette, in a future section about decks -- and a whole-file search would
    call the route documented while the route itself said "HTML needs no
    skill; write the file and apply the palette above", which is the sentence
    that shipped four broken exports.
    """
    house = _read(_HOUSE_STYLE)
    after = house.split("\n### HTML\n", 1)
    assert len(after) == 2, (
        "crew-house-style has no `### HTML` subsection; the HTML route is "
        "where the print discipline lives and nothing else carries it")
    return after[1].split("\n### ", 1)[0]


def _html_rule(number):
    """One numbered rule out of the HTML route, on its own.

    Scoped to the rule rather than to the section, and the sabotage suite is
    why. The first version asserted `"<thead>" in route`, which the route
    satisfies from the PROSE UNDER the rules -- "has nothing to bind to when
    the markup has no `<thead>`" -- so rewriting rule 1 into "style the header
    row" left the test green with the requirement deleted. It came back STILL
    GREEN on the first sabotage run, which is this suite's documented failure
    mode and the reason the rule text is what gets read here.
    """
    route = _html_route()
    start = route.index(f"\n{number}. ")
    rest = route[start + 1:]
    end = re.search(r"\n\d+\. ", rest)
    return rest[:end.start()] if end else rest


def test_the_html_route_carries_the_print_rules():
    """The defect this section exists for, and it is prose again.

    Four guides now in `docs/guides/crew/` were hand-written HTML off this route while
    it read "HTML needs no skill; write the file and apply the palette above".
    The palette is colours. Nothing on that route said anything about a page
    boundary, so all four shipped with headings stranded at the foot of a page
    and tables whose continuation carried no header row.

    Asserted per declaration, not on the block as one string, so reformatting
    the CSS does not fail the test and deleting one of the three does."""
    css = _html_rule(2)

    assert "@media print" in css, css

    for selector, declaration in _PRINT_RULES:
        assert _declares(css, selector, declaration), (selector, declaration)


def test_the_html_route_requires_a_real_thead():
    """The half that is markup, not CSS, and the half that was invisible.

    `display:table-header-group` has nothing to bind to when a table's header
    row is a bare `<tr>` of `<th>`. Measured: adding the CSS alone to these
    four files fixed the stranded headings and did NOT repeat a single table
    header, because not one of their tables had a `<thead>` element. So a route
    that carries the print block and not the markup rule reads as fixed and
    repeats nothing.

    The dependency between the two is asserted as well as the rule itself. A
    bare "use `<thead>`" gets dropped by the next person tightening the file,
    who cannot see what it was holding up."""
    # The RULE, not the section. See `_html_rule`.
    markup = _html_rule(1)
    assert "<thead>" in markup, markup
    assert "<tbody>" in markup, markup

    # And it is an instruction about every table, not an aside about one.
    assert "Every table" in markup, markup

    # The dependency, in the route's own words. Both directions: neither rule
    # is sufficient, which is why neither may be deleted as redundant.
    route = _html_route()
    assert "nothing to bind to" in route, route
    assert "does nothing at all" in route, route


def test_the_print_rules_match_the_generator_that_proves_them():
    """The cross-entry direction, the same one `--brand` is checked in.

    crew's prose cites doc-builder by path and line for these three
    declarations. doc-builder is a separate marketplace entry, so that
    citation can go stale without anything in crew changing -- and a print
    block crew invented for itself, with no working generator behind it,
    is a recommendation rather than a proven fix.

    Read out of the source rather than out of the docstring or the reference
    note: `references/word-traps.md` carries the same block in prose and would
    "confirm" it whether or not the generator still emits it.

    TWO FILES NOW, because doc-builder's stylesheet was extracted out of
    `build_report.py` into `house_style.py`. The CSS half moved; the markup
    half did not, and it is still `build_report.py`'s table emitter that
    produces the `<thead>` the CSS needs. Reading both is the honest shape --
    reading only house_style.py would leave "the rule is only true because
    something produces the element it needs" unasserted.

    `h2` is skipped in the source half and the skip is not a hole; see
    `_PARAMETERISED_SELECTOR`."""
    _requires_doc_builder()
    css_src = _read(os.path.join(_DOC_BUILDER_SCRIPTS, "house_style.py"))

    assert "@media print" in css_src

    for selector, declaration in _GENERATOR_RULES:
        if selector == _PARAMETERISED_SELECTOR:
            continue
        assert _declares(_css_from_python(css_src), selector, declaration), (
            selector, declaration)

    markup_src = _read(os.path.join(_DOC_BUILDER_SCRIPTS, "build_report.py"))

    # The stated reason crew's copy carries `h3` and doc-builder's report
    # profile does not. Asserted so the justification is checkable rather than
    # remembered: if this generator ever emits an `h3`, the block it asks
    # `print_css` for stops covering its own output and crew's prose about why
    # it differs stops being true.
    assert "<h3" not in markup_src, (
        "build_report.py now emits h3; the report profile's print block does "
        "not cover it")

    # And the markup half, from the table emitter itself -- the rule is only
    # true because something produces the element it needs.
    assert "<thead><tr>" in markup_src
    assert "</tr></thead>" in markup_src


# Emit one profile's stylesheet by importing `house_style` in a FRESH
# interpreter and calling it, for the same reason `_importable` uses one: this
# process's sys.path is crew's, and permanently prepending doc-builder's
# scripts/ to it would let `house_style` and `resolve_brand` shadow anything of
# crew's by those names for every test that runs after this one.
#
# `stylesheet()` is called directly rather than through house_style.py's CLI.
# The claim under test is "the report profile emits this rule", and going
# through argparse would let a broken `--profile` flag report itself as a
# missing print rule -- the "a failing gate names the failure, not the cause"
# trap in this repository's CLAUDE.md. `--brand neutral` is used because it
# always resolves, with or without a brand pack installed.
_EMIT_STYLESHEET = """
import sys
sys.path.insert(0, sys.argv[1])
import house_style
import resolve_brand
sys.stdout.write(house_style.stylesheet(
    house_style.Palette(resolve_brand.resolve("neutral")), sys.argv[2]))
"""


def _generated_css(profile):
    done = subprocess.run(
        [sys.executable, "-c", _EMIT_STYLESHEET, _DOC_BUILDER_SCRIPTS, profile],
        capture_output=True, text=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL)
    assert done.returncode == 0, (
        f"house_style.stylesheet(..., {profile!r}) did not run at all, so "
        "nothing below is evidence about the print rules:\n" + done.stderr)
    return done.stdout


@pytest.mark.parametrize("profile,breaks_before", [
    ("report", ("h2",)),
    ("guide", ("h2", "h3")),
])
def test_the_generated_stylesheet_emits_the_print_rules(profile, breaks_before):
    """The OUTPUT, not the source text -- the half the extraction made
    possible and then made necessary.

    `print_css` takes its heading selector as a parameter, so the rule crew
    cites cannot be read off any line of house_style.py. It can be read off
    what the module emits, and that is the better evidence anyway: it survives
    reformatting the f-string, and it proves the rule reaches a page rather
    than merely appearing in a file.

    Both profiles, and the difference between them, because crew's prose turns
    on exactly that difference -- the report profile names `h2` alone and the
    guide profile is already widened to `h2, h3`. The negative assertion is
    load-bearing: if the report profile ever gains `h3`, crew's stated reason
    for why its own block differs from doc-builder's stops being true, and
    nothing else here would notice.

    `_print_block` is used so a declaration that drifted out of `@media print`
    into the screen stylesheet fails instead of passing -- "present somewhere"
    is the shape of assertion that let the original defect ship."""
    _requires_doc_builder()
    css = _generated_css(profile)
    block = _print_block(css, f"house_style.stylesheet(..., {profile!r})")

    for selector in breaks_before:
        assert _declares(block, selector, "page-break-after:avoid"), (
            f"the {profile} profile does not emit "
            f"`{selector} {{ page-break-after:avoid }}`", block)

    for selector in ("h2", "h3"):
        if selector not in breaks_before:
            assert not _declares(block, selector, "page-break-after:avoid"), (
                f"the {profile} profile now breaks before `{selector}`; "
                "crew's prose about how the two profiles differ is stale",
                block)

    # The two literal rules, in the emitted CSS as well as in the source. The
    # source half above stays green on a `print_css` that is never called.
    assert _declares(block, "tr", "page-break-inside:avoid"), (profile, block)
    assert _declares(block, "thead", "display:table-header-group"), (profile, block)


# The `<file>.py:<line>` citations the HTML route makes, as a regex over the
# citation rather than a list of hardcoded numbers. The test reads the number
# CREW WROTE and checks the source at it; it never derives what the number
# should have been. Inferring the right line is the "checker that guesses"
# this repo's CLAUDE.md warns against -- it would rewrite a citation that was
# deliberately pointing somewhere else and call that a pass.
#
# BOTH filenames are matched, not just the one the route cites today. The
# stylesheet moved from `build_report.py` to `house_style.py` and the
# citations followed it; matching only the new name would silently stop
# checking a `build_report.py:NNN` that someone re-adds to this route, which
# is a citation going unchecked rather than going red.
#
# The repo-relative prefix is optional in the pattern and mandatory in the
# prose (asserted below). Both forms resolve by eye; only the prefixed one can
# be pasted into `git diff --name-only <anchor>..HEAD -- <path>`, which is the
# whole mechanism by which a citation gets re-checked.
_CITE_RE = re.compile(
    r"`(skills/doc-builder/scripts/)?(build_report|house_style)\.py"
    r":(\d+)(?:-(\d+))?`")

# The same, restricted to a SINGLE-line citation that quotes the text it
# cites. Applied with `finditer` and never `search`, and that is not a style
# preference: the comment these pin occurs TWICE in `house_style.py`, once per
# profile, so the route now carries two of them. A `search` would check the
# first and let the second rot unnoticed -- the "silently picks the first of
# two matches" bug moved out of the prose and into the checker.
_QUOTED_CITE_RE = re.compile(
    r"`skills/doc-builder/scripts/(build_report|house_style)\.py:(\d+)`, "
    r"\"([^\"]+)\"")


def _doc_builder_lines(filename, start, end):
    """Lines `start`..`end` of `filename` in doc-builder's `scripts/`,
    1-based and inclusive.

    Takes the filename rather than hardcoding one. The previous version was
    called `_build_report_lines` and read `build_report.py` unconditionally,
    so after the stylesheet extraction its name and its subject disagreed --
    a helper that lies about which file it reads is how a citation ends up
    checked against the wrong source.
    """
    lines = _read(os.path.join(_DOC_BUILDER_SCRIPTS, filename)).split("\n")
    assert 1 <= start <= end <= len(lines), (
        f"{filename}:{start}-{end} is out of range; the file has "
        f"{len(lines)} lines")
    return lines[start - 1:end]


def test_the_cited_lines_of_the_generator_hold_what_crew_says_they_hold():
    """The citation itself, not just the claim it supports.

    `test_the_print_rules_match_the_generator_that_proves_them` searches the
    whole file for the three declarations, so it is green whatever line
    numbers crew's prose names -- and both of them were wrong in the tree that
    test passed in: a doc-builder change inserted ten lines and moved
    `155-157` to `165-167` and `123` to `133`, with nothing going red. `123`
    had landed in the middle of the masthead CSS.

    WHAT THIS BINDS, and why it is not the same as pinning the numbers. The
    assertion is "the lines crew names contain what crew says they contain",
    read out of doc-builder at the numbers found in crew's own prose. So an
    edit anywhere in doc-builder that does not move these lines leaves this
    green, and one that does move them goes red -- which is correct, because
    at that moment the citation IS stale. There is no separate list of
    expected line numbers to keep in step with the prose.

    WHAT IT CANNOT CATCH, stated so nobody reads it as more than it is:
      * A stale citation whose new occupant happens to match -- duplicate the
        print block lower in the file and the old numbers keep "resolving".
      * Anything at all when doc-builder is not in the checkout, where the
        whole cross-entry direction skips.
      * The cost is real and is the price of citing by line: an unrelated
        doc-builder edit that inserts a line above these needs a matching edit
        here, in a separate marketplace entry, with its own version bump.

    THE SELECTOR IS A PARAMETER NOW. `house_style.print_css` emits
    `f"  {headings} {{ page-break-after:avoid; }}"`, so the cited span cannot
    contain the string `h2` and `_declares` can never match it there. That is
    checked two ways instead of loosened into one weaker way: the span must
    bind the declaration to the PARAMETER on one line (here), and the emitted
    CSS must bind it to `h2` / `h2, h3`
    (`test_the_generated_stylesheet_emits_the_print_rules`).
    """
    _requires_doc_builder()
    route = _html_route()

    cites = _CITE_RE.findall(route)
    assert len(cites) == 3, (
        "the HTML route should carry exactly three doc-builder line citations "
        "-- the print block, and the table comment once per profile. A fourth "
        "needs a rule here, or it is unchecked: " + repr(cites))

    # Repo-relative, every one of them. A bare `house_style.py:246` resolves by
    # eye and cannot be pasted into the re-verification command, which is the
    # one thing that makes a line citation worth writing down.
    for prefix, name, start, _end in cites:
        assert prefix == "skills/doc-builder/scripts/", (
            f"{name}.py:{start} is cited without its repo-relative path, so "
            "it cannot be re-checked with git diff")

    ranges = [c for c in cites if c[3]]
    singles = [c for c in cites if not c[3]]
    assert len(ranges) == 1 and len(singles) == 2, cites

    # 1. The range citation: the three declarations crew copies, and NOTHING
    #    else inside the span. Every cited line has to carry one of them, so
    #    widening the citation to `:1-400` -- which would "contain" all three
    #    and pass a naive search -- fails here instead.
    _prefix, name, start, end = ranges[0]
    span = _doc_builder_lines(f"{name}.py", int(start), int(end))
    for selector, declaration in _GENERATOR_RULES:
        if selector == _PARAMETERISED_SELECTOR:
            # The placeholder and the declaration on the SAME line, not merely
            # both somewhere in the span: a span that happened to contain a
            # stray `{headings}` three lines from the rule would otherwise
            # read as a live citation.
            assert any("{headings}" in line and declaration in line
                       for line in span), (
                f"{name}.py:{start}-{end} binds `{declaration}` to no heading "
                "parameter; the citation has rotted", span)
            continue
        assert _declares(_css_from_python("\n".join(span)),
                         selector, declaration), (
            f"{name}.py:{start}-{end} does not declare "
            f"`{selector} {{ {declaration} }}`; the citation has rotted",
            span)
    for offset, line in enumerate(span):
        assert any(declaration in line
                   for _sel, declaration in _GENERATOR_RULES), (
            f"{name}.py:{int(start) + offset} carries none of the three "
            "declarations it is cited for, so the citation is wider than the "
            "thing it names: " + repr(line))

    # 2. The single-line citations, checked against the text crew QUOTES
    #    beside each one rather than against a copy kept here. Quoting the
    #    comment and naming a line that holds something else is the failure;
    #    taking the expected text from the prose is what makes the two
    #    provably the same claim.
    #
    #    EVERY single-line citation, matched by count against `singles` before
    #    anything is checked. The comment being pinned occurs twice in
    #    house_style.py -- once in each profile branch of `stylesheet()` --
    #    so an unquoted or unmatched citation here means one of the two copies
    #    is unpinned while the section looks fully checked.
    flat = " ".join(route.split())
    quoted = list(_QUOTED_CITE_RE.finditer(flat))
    assert len(quoted) == len(singles), (
        "every single-line citation must quote the text it cites; without the "
        "quote there is nothing to check the line against",
        [(c[1], c[2]) for c in singles], [m.groups() for m in quoted])
    assert (sorted(int(m.group(2)) for m in quoted)
            == sorted(int(c[2]) for c in singles)), (
        "a quoted citation names a line no single-line citation does",
        [m.groups() for m in quoted], singles)

    # Different lines, deliberately. The two copies of the comment are one per
    # profile; citing the same line twice would leave the other profile's copy
    # unpinned while reading as though both were checked -- which is the
    # ambiguity these two citations exist to remove.
    assert len({int(c[2]) for c in singles}) == len(singles), (
        "two single-line citations name the same line, so one profile's copy "
        "of the comment is not pinned by anything", singles)

    for match in quoted:
        cited_file, line_no, expected = (
            match.group(1) + ".py", int(match.group(2)), match.group(3))
        cited_line = " ".join(
            _doc_builder_lines(cited_file, line_no, line_no)[0].split())
        assert expected in cited_line, (
            f"{cited_file}:{line_no} does not contain the text crew quotes "
            f"from it.\n  quoted: {expected!r}\n  line:   {cited_line!r}")


# The documents the defect was reported against. Named one by one rather
# than globbed: a glob asserts a rule about whatever happens to be in the
# directory, so deleting the file that shipped broken would turn the test
# green by removing its subject.
#
# Reaching out of the plugin and into the repo for the same reason
# `_DOC_BUILDER_SCRIPTS` does, and the reason is stronger here, not weaker.
# The `### HTML` route is the one route on the list with NO generator behind
# it -- every other format is produced by a tool with its own tests -- so the
# artefacts are the only place the rule can be observed holding. The previous
# author deferred this to TODO.md as "coupling crew's suite to repo docs";
# that is true of this whole file by design (see the module docstring), and
# three tests asserting crew's PROSE while the files the user complained about
# went unchecked is the exact shape this suite exists to refuse. They skip
# when the repo is not in the checkout, like every other cross-entry check
# here.
#
# `crew-overview.html`, `crew-capabilities.html` and `crew-technical-reference`
# were retired in favour of the `crew-1.0-*` guide family (which has a
# generator -- `docs/guides/crew/src/build.py` -- and its own coverage) and
# removed from this tuple along with them. The dated progress report was
# archived, not deleted, so it stays here at its new path: it still has no
# generator, and archiving is not regenerating.
_GUIDES_DIR = os.path.join(_REPO, "docs", "guides", "crew")
_GUIDES = (
    "archive/crew-progress-report-2026-09-20.html",
)


def _requires_guides():
    # Skip only when the MARKETPLACE REPO is absent (crew's tests running from an
    # installed copy). Inside the repo a missing guides folder is a failure: the
    # guides moved into docs/guides/crew/ once already, and a skip keyed on the
    # folder itself would let the next move turn all eight checks into silent
    # skips.
    if not os.path.isfile(os.path.join(_REPO, ".claude-plugin", "marketplace.json")):
        pytest.skip(
            f"not inside the marketplace repo ({os.path.normpath(_REPO)}) -- "
            "crew's tests are running from an installed copy, so the artefacts "
            "the HTML route produced cannot be checked here")
    assert os.path.isdir(_GUIDES_DIR), (
        f"the marketplace repo is here but {os.path.normpath(_GUIDES_DIR)} is "
        "not -- the crew guides moved; update _GUIDES_DIR rather than letting "
        "these checks skip")


def _print_block(html, name):
    """The body of the document's `@media print { ... }` rule, brace-matched.

    Scoped rather than handed the whole file, because `_declares` reads every
    CSS rule in whatever it is given. A whole-file search accepts
    `thead { display:table-header-group; }` sitting in the SCREEN stylesheet,
    where it does nothing a printer can see -- and "the declaration is present
    somewhere" was already the shape of the assertion that let this ship.
    """
    start = html.find("@media print")
    assert start != -1, f"{name} has no `@media print` block at all"
    opened = html.find("{", start)
    assert opened != -1, name
    depth = 0
    for index in range(opened, len(html)):
        if html[index] == "{":
            depth += 1
        elif html[index] == "}":
            depth -= 1
            if depth == 0:
                return html[opened + 1:index]
    raise AssertionError(f"{name}: unterminated `@media print` block")


@pytest.mark.parametrize("name", _GUIDES)
def test_every_shipped_guide_carries_the_print_block(name):
    """The artefact, not the prose that describes it.

    Nothing else in this suite looks at a produced document. Regenerate or
    hand-edit these four without the block and every other test here stays
    green, which is how the defect reached a reader in the first place.

    Asserted per declaration and inside the print block, so reformatting the
    CSS passes, moving a declaration out to the screen stylesheet fails, and
    dropping one of the four fails."""
    _requires_guides()
    path = os.path.join(_GUIDES_DIR, name)
    assert os.path.isfile(path), path

    block = _print_block(_read(path), name)

    # The WIDENED set -- these files are written off crew's route, not
    # doc-builder's, and `h3` is the widening the route calls not optional.
    # Two of them carry `<h3>`s.
    for selector, declaration in _PRINT_RULES:
        assert _declares(block, selector, declaration), (
            name, selector, declaration, block)


@pytest.mark.parametrize("name", _GUIDES)
def test_every_table_in_every_shipped_guide_has_a_real_thead(name):
    """The markup half, per table rather than per file.

    Counting `<table>` against `<thead>` is not this assertion: one table with
    two theads and another with none balances, and the one with none is the
    table whose header vanishes at the page break. Each `<table>` element is
    checked on its own.

    `display:table-header-group` has nothing to bind to without this, so a
    file passing the test above and failing this one is a file where the print
    block reads as fixed and repeats nothing."""
    _requires_guides()
    html = _read(os.path.join(_GUIDES_DIR, name))

    tables = re.findall(r"<table\b.*?</table>", html, re.S | re.I)

    # The floor, not a count. "Every table has a thead" is vacuously true of a
    # document with no tables, so deleting the tables would pass a test whose
    # whole subject is what those tables do at a page boundary.
    assert tables, f"{name} contains no <table>; this test would be vacuous"

    for table in tables:
        head = re.search(r"<thead\b.*?</thead>", table, re.S | re.I)
        assert head, (
            f"{name}: a <table> has no <thead>, so its header row does not "
            "repeat at a page break: " + " ".join(table.split())[:160])
        # A `<thead>` wrapped around nothing is the same defect with the
        # element added, and it is what a careless fix produces.
        assert re.search(r"<th\b", head.group(0), re.I), (
            f"{name}: a <thead> contains no <th>: "
            + " ".join(head.group(0).split())[:160])
        assert re.search(r"<tbody\b", table, re.I), (
            f"{name}: a <table> has a <thead> but no <tbody>; rule 1 of the "
            "HTML route requires both: " + " ".join(table.split())[:160])
