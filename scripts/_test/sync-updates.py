#!/usr/bin/env python3
"""Suite for scripts/sync-updates.py, the generator behind the README blocks.

Every case copies the real script into a throwaway directory, writes a small
fixture repo around it (three UPDATE.md sources, their READMEs, a root README
and a CHANGELOG.md) and runs it there as a subprocess, so ``ROOT`` resolves to
the fixture. Nothing touches this repository's own files.

The root README's "What's new" is the newest two CHANGELOG.md entries (L-1518).
It is generated so it cannot go stale, and the only thing that makes that true
is ``--check`` failing on a block that is not the current render. So the
must-block cases come first: a block left on older entries, a block missing an
entry, a hand-edited line. The must-allow case is a fresh render. The edge
cases are the shapes a changelog really has: one entry, an entry with no
``**Summary.**`` bullet, an entry with no bullet at all.

Run: python3 scripts/_test/sync-updates.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "sync-updates.py")

ENTRY_A = """### Added — `widget` 2.0.0: a dial for the widget (T-0001)

- **Summary.** The widget now has a dial you can turn.
- **What changed.** `dial.py` is new.
"""
ENTRY_B = """### Fixed — `gadget` 1.4.2: the gadget no longer squeaks (L-0002, PR A)

- **What changed.** The hinge is oiled. It stays quiet.
- **Summary.** Opening the gadget is silent again.
"""
ENTRY_C = """### Changed — `widget` 1.9.0: older change

- **Summary.** Something older.
"""
NO_SUMMARY = """### Fixed — `gizmo` 0.3.1: no summary bullet (T-0003)

- **What changed.** The gizmo starts on a cold `start()`. The rest is detail.
  It keeps going on a second line.
- **Why.** Users asked.
"""
NO_BULLET = """### Changed — repository: a heading with nothing under it (L-0004)

Prose but no bullet.
"""
LONG = """### Changed — `gizmo` 0.4.0: a long first sentence

- **What changed.** """ + "word " * 40 + "`a code span that must stay whole` " + "tail " * 20 + """end.
"""


def changelog(*entries: str) -> str:
    preamble = (
        "# Changelog\n\nPreamble prose.\n\n## How to read this\n\n"
        "### Added — `decoy` 9.9.9: not under a release heading\n\n"
        "```\n### Added — `fenced` 8.8.8: inside a code block\n```\n\n"
    )
    return preamble + "## [Unreleased]\n\n" + "\n".join(entries) + "\n## [0.1.0]\n\n" + ENTRY_C


ROOT_README = """# Root

## What's new

<!-- BEGIN CHANGELOG.md -->

<!-- END CHANGELOG.md -->

## Documentation
"""


def build(tmp: str, log: str, root_readme: str = ROOT_README) -> None:
    os.makedirs(os.path.join(tmp, "scripts"))
    shutil.copy(SCRIPT, os.path.join(tmp, "scripts", "sync-updates.py"))
    for name in ("plugin", "skills", "mcp-servers"):
        os.makedirs(os.path.join(tmp, name))
        write(tmp, f"{name}/UPDATE.md", f"# {name} updates\n\n## Unreleased\n\nNothing new in {name}.\n")
        # Already current, so a stale verdict in a case below can only be the root README's.
        write(tmp, f"{name}/README.md",
              f"# {name}\n\n<!-- BEGIN {name}/UPDATE.md -->\n\n### Unreleased\n\n"
              f"Nothing new in {name}.\n\n<!-- END {name}/UPDATE.md -->\n")
    write(tmp, "README.md", root_readme)
    write(tmp, "CHANGELOG.md", log)


def write(tmp: str, rel: str, text: str) -> None:
    with open(os.path.join(tmp, rel), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read(tmp: str, rel: str) -> str:
    with open(os.path.join(tmp, rel), encoding="utf-8") as handle:
        return handle.read()


def stale_root(result: subprocess.CompletedProcess) -> bool:
    """--check exited 1 naming the root README, and only it."""
    return result.returncode == 1 and result.stdout.splitlines() == [
        "sync-updates: README.md is stale -- run scripts/sync-updates.py"]


def run(tmp: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(tmp, "scripts", "sync-updates.py"), *args],
                          capture_output=True, text=True, check=False)


def block(tmp: str) -> list[str]:
    """The non-empty lines between the root README's CHANGELOG.md markers."""
    text = read(tmp, "README.md")
    inner = text.split("<!-- BEGIN CHANGELOG.md -->")[1].split("<!-- END CHANGELOG.md -->")[0]
    return [line for line in inner.splitlines() if line.strip()]


FULL = "Full history: [CHANGELOG.md](CHANGELOG.md)."
LINE_A = "- **widget 2.0.0**: A dial for the widget. The widget now has a dial you can turn."
LINE_B = "- **gadget 1.4.2**: The gadget no longer squeaks. Opening the gadget is silent again."
LINE_C = "- **widget 1.9.0**: Older change. Something older."


def case_fresh_render_passes(tmp):
    build(tmp, changelog(ENTRY_A, ENTRY_B))
    wrote = run(tmp)
    check = run(tmp, "--check")
    assert wrote.returncode == 0, wrote.stderr
    assert check.returncode == 0, (check.stdout, check.stderr)
    assert block(tmp) == [LINE_A, LINE_B, FULL], block(tmp)


def case_older_entries_fail_check(tmp):
    build(tmp, changelog(ENTRY_B, ENTRY_C))
    assert run(tmp).returncode == 0
    write(tmp, "CHANGELOG.md", changelog(ENTRY_A, ENTRY_B))  # a new entry lands
    before = read(tmp, "README.md")
    check = run(tmp, "--check")
    assert stale_root(check), (check.returncode, check.stdout, check.stderr)
    assert read(tmp, "README.md") == before, "--check wrote the README"


def case_missing_entry_fails_check(tmp):
    root = ROOT_README.replace("-->\n\n<!-- END", f"-->\n\n{LINE_A}\n\n{FULL}\n\n<!-- END")
    build(tmp, changelog(ENTRY_A, ENTRY_B), root)
    check = run(tmp, "--check")
    assert stale_root(check), (check.returncode, check.stdout, check.stderr)


def case_hand_edited_line_fails_check(tmp):
    build(tmp, changelog(ENTRY_A, ENTRY_B))
    assert run(tmp).returncode == 0
    write(tmp, "README.md", read(tmp, "README.md").replace("you can turn", "you can spin"))
    check = run(tmp, "--check")
    assert stale_root(check), (check.returncode, check.stdout, check.stderr)


def case_empty_block_fails_check(tmp):
    build(tmp, changelog(ENTRY_A, ENTRY_B))
    check = run(tmp, "--check")
    assert stale_root(check), (check.returncode, check.stdout, check.stderr)


def case_one_entry(tmp):
    log = "# Changelog\n\n## [Unreleased]\n\n" + ENTRY_A
    build(tmp, log)
    assert run(tmp).returncode == 0
    assert run(tmp, "--check").returncode == 0
    assert block(tmp) == [LINE_A, FULL], block(tmp)


def case_no_summary_bullet(tmp):
    build(tmp, changelog(NO_SUMMARY, ENTRY_A))
    assert run(tmp).returncode == 0
    assert block(tmp)[0] == ("- **gizmo 0.3.1**: No summary bullet. "
                             "The gizmo starts on a cold `start()`."), block(tmp)


def case_no_bullet(tmp):
    build(tmp, changelog(NO_BULLET, ENTRY_A))
    assert run(tmp).returncode == 0
    assert block(tmp) == ["- **repository**: A heading with nothing under it.", LINE_A, FULL], block(tmp)


def case_long_sentence_is_cut_outside_code(tmp):
    build(tmp, changelog(LONG))
    assert run(tmp).returncode == 0
    line = block(tmp)[0]
    sentence = line.split("A long first sentence. ", 1)[1]
    assert sentence.endswith(" ..."), line
    assert len(sentence) <= 244, len(sentence)
    assert sentence.count("`") % 2 == 0, f"cut inside a code span: {line}"


def case_older_release_fills_in(tmp):
    build(tmp, changelog(ENTRY_A))
    assert run(tmp).returncode == 0
    assert block(tmp) == [LINE_A, LINE_C, FULL], block(tmp)


def case_no_entries_is_structural(tmp):
    build(tmp, "# Changelog\n\n## [Unreleased]\n\nNothing yet.\n")
    result = run(tmp, "--check")
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert "has no '###' entry" in result.stderr, result.stderr


def case_missing_markers_is_structural(tmp):
    build(tmp, changelog(ENTRY_A, ENTRY_B), "# Root\n\n## What's new\n")
    result = run(tmp, "--check")
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert "<!-- BEGIN CHANGELOG.md -->" in result.stderr, result.stderr


def case_root_readme_no_longer_mirrors_update_md(tmp):
    build(tmp, changelog(ENTRY_A, ENTRY_B))
    before = read(tmp, "plugin/README.md")
    write(tmp, "plugin/UPDATE.md", "# plugin updates\n\n## Unreleased\n\nA new thing.\n")
    assert run(tmp).returncode == 0
    assert read(tmp, "plugin/README.md") != before and "A new thing." in read(tmp, "plugin/README.md")
    assert "Nothing new in" not in read(tmp, "README.md") and "A new thing" not in read(tmp, "README.md")


BATCH = """### crew 1.0.345 — batch 5: T-0052, T-0057

#### Added — `crew`: plain-text rows for wave and split (L-0662)

- **What changed.** Rows were added.

#### Fixed — `crew`: one split rulebook (T-0052, 1 of 3)

- **What changed.** One rulebook.
"""

ODD_SHAPE = """### widget 2.1.0 — a heading without a kind word

- **Summary.** Still listed.
"""


def case_batch_entry_lists_its_parts(tmp):
    build(tmp, changelog(BATCH, ENTRY_A))
    assert run(tmp).returncode == 0
    assert block(tmp) == ["- **crew 1.0.345**: Plain-text rows for wave and split; one split rulebook.",
                          LINE_A, FULL], block(tmp)


def case_heading_without_kind_word_is_not_skipped(tmp):
    build(tmp, changelog(ODD_SHAPE, ENTRY_A))
    assert run(tmp).returncode == 0
    assert block(tmp) == ["- Widget 2.1.0 — a heading without a kind word. Still listed.",
                          LINE_A, FULL], block(tmp)


def batch_log(heading: str, *lines: str) -> str:
    return changelog("\n".join((heading, "", *lines, "")), ENTRY_A)


def case_batch_heading_with_hyphen_or_no_dash(tmp):
    for heading in ("### crew 1.0.346 - batch 6: T-1, T-2", "### crew 1.0.346 batch 6: T-1, T-2"):
        build(tmp, batch_log(heading, "#### Added \u2014 `crew`: thing one (T-1)", "", "- x"))
        assert run(tmp).returncode == 0
        assert block(tmp)[0] == "- **crew 1.0.346**: Thing one.", (heading, block(tmp))
        shutil.rmtree(tmp)
        os.makedirs(tmp)


def case_batch_with_summary_bullet(tmp):
    build(tmp, batch_log("### crew 1.0.346 \u2014 batch 6: T-1, T-2", "- **Summary.** Two fixes.", "",
                         "#### Fixed \u2014 `crew`: one (T-1)", "", "- x"))
    assert run(tmp).returncode == 0
    assert block(tmp)[0] == "- **crew 1.0.346**: Two fixes.", block(tmp)


def case_long_part_list_ends_in_one_ellipsis(tmp):
    parts = [f"#### Added \u2014 `crew`: a fairly long part title number {n} for the list (T-{n})"
             for n in range(8)]
    build(tmp, batch_log("### crew 1.0.346 \u2014 batch 6: T-0", *parts))
    assert run(tmp).returncode == 0
    line = block(tmp)[0]
    assert line.endswith(" ...") and not line.endswith("...."), line


def case_empty_and_deep_part_headings(tmp):
    build(tmp, batch_log("### crew 1.0.346 \u2014 batch 6: T-1, T-2", "#### Added", "",
                         "#### Fixed \u2014 `crew`: two (T-2)", "", "##### deep", "",
                         "#### Added \u2014 `crew`: after deep (T-1)"))
    assert run(tmp).returncode == 0
    assert block(tmp)[0] == "- **crew 1.0.346**: Added; two; after deep.", block(tmp)


def case_batch_mode_word_is_not_a_batch(tmp):
    build(tmp, changelog("### Fixed \u2014 `crew` 1.0.3: batch-mode retries\n\n- **Summary.** S.\n\n"
                         "#### Notes\n\n- n\n", ENTRY_A))
    assert run(tmp).returncode == 0
    assert block(tmp)[0] == "- **crew 1.0.3**: Batch-mode retries. S.", block(tmp)


CASES = [
    ("must-allow: a fresh render passes --check", case_fresh_render_passes),
    ("must-block: a block left on older entries fails --check and is not written",
     case_older_entries_fail_check),
    ("must-block: a block missing the second entry fails --check", case_missing_entry_fails_check),
    ("must-block: a hand-edited line fails --check", case_hand_edited_line_fails_check),
    ("must-block: an empty block fails --check", case_empty_block_fails_check),
    ("edge: one entry renders one line and the history link", case_one_entry),
    ("edge: no Summary bullet uses the first bullet's first sentence", case_no_summary_bullet),
    ("edge: no bullet at all renders the heading alone", case_no_bullet),
    ("edge: a long first sentence is cut at a space outside code", case_long_sentence_is_cut_outside_code),
    ("edge: an older release's entry fills the second line", case_older_release_fills_in),
    ("must-allow: a batch entry lists its #### parts", case_batch_entry_lists_its_parts),
    ("must-block: a ### heading without a kind word is still an entry, not skipped",
     case_heading_without_kind_word_is_not_skipped),
    ("edge: a batch heading with a hyphen or no dash still lists its parts",
     case_batch_heading_with_hyphen_or_no_dash),
    ("edge: a batch entry's own Summary bullet wins over its part list", case_batch_with_summary_bullet),
    ("edge: a cut part list ends in one ellipsis, not four dots", case_long_part_list_ends_in_one_ellipsis),
    ("edge: an empty #### keeps its kind word and a ##### drops no later part",
     case_empty_and_deep_part_headings),
    ("must-block: a normal entry saying \"batch-mode\" keeps its normal line",
     case_batch_mode_word_is_not_a_batch),
    ("structural: a changelog with no entry exits 2", case_no_entries_is_structural),
    ("structural: a root README without the markers exits 2", case_missing_markers_is_structural),
    ("the root README carries no UPDATE.md mirror", case_root_readme_no_longer_mirrors_update_md),
]


def main() -> int:
    passed = failed = 0
    for label, case in CASES:
        tmp = tempfile.mkdtemp(prefix="sync-updates-")
        try:
            case(tmp)
        except (AssertionError, IndexError, OSError) as error:
            failed += 1
            print(f"  FAIL {label}\n       {type(error).__name__}: {error}")
        else:
            passed += 1
            print(f"  ok   {label}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nsync-updates: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
