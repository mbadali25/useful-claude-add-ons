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
    report_rule = [line for line in generating.split("\n")
                   if "docs.reportTheme" in line]
    assert report_rule, "no line binds docs.reportTheme to anything"
    assert any("report" in line.lower() for line in report_rule), report_rule

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
    scripts nobody is routed to."""
    generating = _read(_HOUSE_STYLE).split("## Generating it", 1)[1]

    for genre, (script, _needs) in _ROUTED_SCRIPTS.items():
        assert script in generating, genre


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
