"""L-0718: `crew_standards.py export` -- the standards published to PR-side reviewers.

    python3 -m pytest plugin/crew/tests/test_standards_export.py -q

Every fixture lives under pytest's tmp_path: a throwaway references directory
stands in for the plugin's, a throwaway repository for the opted-in one, and the
crew version is passed in. The only real files read are this repository's
generated outputs, by the last tests, and `.crew/verify.json`.
"""
import glob
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_instructions
import crew_standards as cs

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "crew_standards.py")
_REPO_ROOT = os.path.abspath(os.path.join(context._ROOT, os.pardir, os.pardir))  # pylint: disable=protected-access
V = "9.9.9"
ALL = ["review", "agents", "bugbot"]
WHY = "It broke on the night shift."
EARNED = "T-0001 r1 @abcdef12"


def _plugin_standard(sid, name):
    return (f"## {sid} {name}\n\n**Rule.** Do the {name} thing.\n\n**Why.** {WHY}\n\n"
            f"**Applies when.** Always.\n\n**Self-check.**\n1. Did you? Pass: yes.\n\n"
            f"**Earned by.**\n- {EARNED}, FIX `a.py:1`: \"broke\"\n\n"
            "**Change sets.** 3: T-0001, T-0002, T-0003\n")


def _set_file(set_name, applies, body, export=None):
    extra = f"export: {json.dumps(export)}\n" if export is not None else ""
    return (f"---\nset: {set_name}\napplies-to: {json.dumps(applies)}\n{extra}---\n\n"
            f"# {set_name}\n\n{body}")


OVERLAY_BODY = ("## REPO-01 Local\n\n**Rule.** Do the local thing.\n\n**Self-check.**\n"
                "1. Did you? Pass: yes.\n\n## Supplements GEN-01\n\nRun `grep -rn x plugin/`.\n")


@pytest.fixture(name="refs")
def _refs(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "generic.md").write_text(_set_file("GEN", ["**"], _plugin_standard("GEN-01", "One")
                                               + "\n" + _plugin_standard("GEN-02", "Two")),
                                     encoding="utf-8")
    (refs / "php.md").write_text(_set_file("PHP", ["**/*.php"],
                                           _plugin_standard("PHP-01", "Prepared")),
                                 encoding="utf-8")
    return refs


def _make_root(tmp_path, export=None, hand_agents=None):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    (root / ".crew").mkdir(exist_ok=True)
    (root / ".crew" / "standards.md").write_text(
        _set_file("REPO", ["**"], OVERLAY_BODY, export), encoding="utf-8")
    if hand_agents is not None:
        (root / "AGENTS.md").write_text(hand_agents, encoding="utf-8")
    return root


@pytest.fixture(name="root")
def _root(tmp_path):
    return _make_root(tmp_path, ALL, "# Agents\n\nHand written.\n")


def _write(root, refs):
    return cs.export_write(str(root), str(refs), V)


def _check(root, refs):
    return cs.export_check(str(root), str(refs), V)


def _outputs(root):
    found = {}
    for rel in ("REVIEW.md", ".cursor/BUGBOT.md", "AGENTS.md", *[
            f"docs/review-rules/{n}" for n in ("GEN.md", "PHP.md", "REPO.md")]):
        path = root / rel
        if path.exists():
            found[rel] = path.read_bytes()
    return found


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def _all_ids(refs, root):
    found = cs.effective_set(str(root), [], str(refs), applies=lambda globs: True)
    return [s["id"] for s in found["standards"]]


# ---- opt-in, dry run -----------------------------------------------------------

def test_dry_run_writes_nothing_and_reports_sizes(refs, root):
    code, lines = cs.export_report(str(root), str(refs), V)

    text = "\n".join(lines)
    assert code == 0
    assert (f"budget {cs.EXPORT_MAX_CHARS}" in text, "docs/review-rules/GEN.md" in text,
            ".cursor/BUGBOT.md" in text, "AGENTS.md (block)" in text,
            re.search(r"digest [0-9a-f]{64}", text) is not None) == (True,) * 5
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()


def test_a_repo_that_never_opted_in_is_not_exported(tmp_path, refs):
    root = _make_root(tmp_path, None)

    reported = cs.export_report(str(root), str(refs), V)
    written = _write(root, refs)
    checked = _check(root, refs)

    assert reported == (0, [cs.NOT_OPTED_IN])
    assert written == (0, [cs.NOT_OPTED_IN])
    assert checked == (0, [cs.NOT_OPTED_IN])
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()


def test_the_cli_dry_run_runs_for_a_repo_with_no_overlay(tmp_path):
    done = subprocess.run([sys.executable, "-B", _SCRIPT, "export", "--root", str(tmp_path),
                           "--dry-run"], capture_output=True, text=True, check=False)

    assert (done.returncode, cs.NOT_OPTED_IN in done.stdout) == (0, True)


def test_the_cli_wants_exactly_one_action(tmp_path):
    done = subprocess.run([sys.executable, "-B", _SCRIPT, "export", "--root", str(tmp_path)],
                          capture_output=True, text=True, check=False)

    assert (done.returncode, "exactly one of" in done.stderr) == (2, True)


@pytest.mark.parametrize("value", ['"review"', "[]", '["pdf"]', '["review", "review"]', "nope",
                                   "[1]"])
def test_an_invalid_export_value_is_refused_and_nothing_is_written(tmp_path, refs, value):
    root = _make_root(tmp_path, None)
    _edit(root / ".crew" / "standards.md", "applies-to: [\"**\"]\n",
          f"applies-to: [\"**\"]\nexport: {value}\n")

    code, lines = _write(root, refs)

    assert code == 1 and "export must be" in "\n".join(lines)
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()


def test_a_plugin_set_may_not_carry_the_export_key(tmp_path, refs):
    root = _make_root(tmp_path, ALL)
    _edit(refs / "php.md", "applies-to:", "export: [\"review\"]\napplies-to:")

    code, lines = _write(root, refs)

    assert code == 1 and "front matter line" in "\n".join(lines)
    assert not (root / "REVIEW.md").exists()


# ---- what is rendered ------------------------------------------------------------

def test_every_effective_standard_appears_exactly_once_in_its_set_file(refs, root):
    _write(root, refs)

    expected = _all_ids(refs, root)
    headings = []
    for path in sorted(glob.glob(str(root / "docs" / "review-rules" / "*.md"))):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        headings += re.findall(r"^## ([A-Z]+-\d\d) ", text, re.M)

    assert sorted(headings) == sorted(expected) and len(expected) == 4


def test_each_entry_point_carries_always_on_text_and_lists_every_id_once_and_links_an_existing_set_file(
        refs, root):
    _write(root, refs)
    expected = _all_ids(refs, root)

    for rel in ("REVIEW.md", ".cursor/BUGBOT.md", "AGENTS.md"):
        text = (root / rel).read_text(encoding="utf-8")
        if rel == "AGENTS.md":
            text = text[text.index("<!-- crew-standards-export start"):]
        listed = re.findall(r"^(?:## |- |  - )([A-Z]+-\d\d)\b", text, re.M)
        assert sorted(listed) == sorted(expected), rel
        for target in re.findall(r"\]\(([^)]+)\)", text):
            linked = (root / rel).parent / target
            assert linked.is_file(), (rel, target)
        if rel != "AGENTS.md":
            assert "Do the One thing." in text and "Do the Prepared thing." not in text, rel
            assert "Run `grep -rn x plugin/`." in text, rel
    assert "../docs/review-rules/PHP.md" in (root / ".cursor" / "BUGBOT.md").read_text("utf-8")


@pytest.mark.parametrize("targets", [["review"], ["agents"], ["bugbot"], ["review", "agents"],
                                     ["review", "bugbot"], ["agents", "bugbot"], ALL])
def test_every_allowed_target_subset_renders_valid_pointers(tmp_path, refs, targets):
    root = _make_root(tmp_path, targets, "# Agents\n")

    code, _ = _write(root, refs)

    assert code == 0
    assert _check(root, refs)[0] == 0
    written = _outputs(root)
    assert ("REVIEW.md" in written, ".cursor/BUGBOT.md" in written) == (
        "review" in targets, "bugbot" in targets)
    for rel, data in written.items():
        text = data.decode("utf-8")
        assert ("REVIEW.md" in text and rel != "REVIEW.md") <= ("review" in targets), rel
        assert "BUGBOT" not in text or "bugbot" in targets, rel
        for target in re.findall(r"\]\(([^)]+)\)", text):
            assert ((root / rel).parent / target).is_file(), (rel, target)
    assert ("crew-standards-export start" in written.get("AGENTS.md", b"").decode()) == (
        "agents" in targets)


def test_why_and_earned_by_are_not_exported(refs, root):
    _write(root, refs)

    joined = b"\n".join(_outputs(root).values()).decode("utf-8")

    assert (WHY in joined, EARNED in joined, "Earned by" in joined, "**Why.**" in joined) == (
        False,) * 4
    assert "Do the One thing." in joined


# ---- writing ---------------------------------------------------------------------

def test_write_twice_is_byte_identical(refs, root):
    _write(root, refs)
    first = _outputs(root)

    code, _ = _write(root, refs)

    assert code == 0 and _outputs(root) == first and len(first) == 6


def test_outputs_use_lf_endings(refs, root):
    _write(root, refs)

    assert all(b"\r" not in data for data in _outputs(root).values())


def test_a_failed_write_leaves_the_old_file_whole(refs, root, monkeypatch):
    _write(root, refs)
    before = _outputs(root)
    _edit(refs / "generic.md", "Do the One thing.", "Do the changed thing.")

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    code, lines = _write(root, refs)
    monkeypatch.undo()

    assert code == 1 and "FAILED part-way" in "\n".join(lines)

    assert _outputs(root) == before
    assert not list(root.rglob(".crew-export-*"))


def test_a_failed_write_reports_the_write_error_not_the_cleanup_error(refs, root, monkeypatch):
    def replace(_src, _dst):
        raise OSError("disk full")

    def remove(_path):
        raise OSError("cannot clean")

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "remove", remove)

    code, lines = _write(root, refs)

    assert code == 1 and "disk full" in "\n".join(lines) and "cannot clean" not in "\n".join(lines)


def test_a_sharing_violation_on_replace_is_retried(refs, root, monkeypatch):
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) < 3:
            raise PermissionError("in use")
        real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)

    code, _ = _write(root, refs)

    assert code == 0 and len(calls) >= 3 and _check(root, refs)[0] == 0


def test_a_replace_that_keeps_failing_is_raised(refs, root, monkeypatch):
    def locked(_src, _dst):
        raise PermissionError("in use")

    monkeypatch.setattr(os, "replace", locked)
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)

    code, lines = _write(root, refs)

    assert code == 1 and "PermissionError" in "\n".join(lines)
    assert not list(root.rglob(".crew-export-*"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_a_rewrite_keeps_the_targets_mode(refs, root):
    _write(root, refs)
    os.chmod(root / "REVIEW.md", 0o755)
    _edit(refs / "generic.md", "Do the One thing.", "Do the changed thing.")

    _write(root, refs)

    assert (os.stat(root / "REVIEW.md").st_mode & 0o777, os.stat(root / "AGENTS.md").st_mode
            & 0o777) == (0o755, 0o644)


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlink privilege")
def test_containment_is_by_path_components_not_a_string_prefix(tmp_path):
    real = tmp_path / "foo"
    sibling = tmp_path / "foo-bar"
    real.mkdir()
    sibling.mkdir()
    (real / "docs").symlink_to(sibling, target_is_directory=True)

    assert cs._contained(str(real), "docs/x.md") is False  # pylint: disable=protected-access
    assert cs._contained(str(real), "REVIEW.md") is True  # pylint: disable=protected-access


def test_hand_written_text_around_the_agents_block_survives_a_rewrite(tmp_path, refs):
    root = _make_root(tmp_path, ALL, "# Agents\n\nBefore.\n")
    _write(root, refs)
    path = root / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\n## After\n\nAfter text.\n", encoding="utf-8", newline="\n")
    _edit(refs / "generic.md", "Do the One thing.", "Do the changed thing.")

    code, _ = _write(root, refs)

    final = path.read_text(encoding="utf-8")
    assert code == 0 and final.startswith("# Agents\n\nBefore.\n\n<!-- crew-standards-export start")
    assert final.endswith("<!-- crew-standards-export end -->\n\n## After\n\nAfter text.\n")
    assert final.count("crew-standards-export start") == 1
    assert _check(root, refs)[0] == 0


@pytest.mark.parametrize("broken", [
    "<!-- crew-standards-export start digest=" + "a" * 64 + " crew=1 -->\nno end\n",
    "<!-- crew-standards-export end -->\n",
    ("<!-- crew-standards-export start digest=" + "a" * 64 + " crew=1 -->\n"
     "<!-- crew-standards-export end -->\n") * 2,
])
def test_malformed_markers_are_refused(tmp_path, refs, broken):
    root = _make_root(tmp_path, ALL, "# Agents\n\n" + broken)

    code, lines = _write(root, refs)

    assert code == 1 and "malformed" in "\n".join(lines)
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# Agents\n\n" + broken
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()


def test_the_agents_block_does_not_change_crew_instructions_classification(tmp_path, refs,
                                                                           root):
    before = crew_instructions.agents(str(root), check=True)

    _write(root, refs)
    after = crew_instructions.agents(str(root), check=True)

    assert cs.GENERATED_MARKER == crew_instructions.MARKER
    assert crew_instructions.MARKER not in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert after == before


def test_export_creates_agents_md_when_the_repo_has_none(tmp_path, refs):
    root = _make_root(tmp_path, ["agents"])

    code, _ = _write(root, refs)

    assert code == 0 and (root / "AGENTS.md").read_text("utf-8").startswith(
        "<!-- crew-standards-export start")
    assert _check(root, refs)[0] == 0


# ---- refusals --------------------------------------------------------------------

def test_export_refuses_a_crew_generated_agents_md(tmp_path, refs):
    root = _make_root(tmp_path, ALL, "# x\n<!-- crew:generated AGENTS.md -->\n")

    code, lines = _write(root, refs)

    assert code == 1 and "crew-generated" in "\n".join(lines)
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()


def test_export_refuses_a_crlf_agents_md(tmp_path, refs):
    root = _make_root(tmp_path, ALL)
    (root / "AGENTS.md").write_bytes(b"# x\r\nhand\r\n")

    code, lines = _write(root, refs)

    assert code == 1 and "CRLF" in "\n".join(lines)
    assert (root / "AGENTS.md").read_bytes() == b"# x\r\nhand\r\n"


def test_export_refuses_when_the_standards_set_has_problems(refs, root):
    _edit(refs / "generic.md", "**Self-check.**\n1. Did you? Pass: yes.\n\n**Earned by.**",
          "**Earned by.**")

    code, lines = _write(root, refs)
    checked = _check(root, refs)

    assert code == 1 and "has no **Self-check.** field" in "\n".join(lines)
    assert checked[0] == 1
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()


def test_export_refuses_an_unreadable_overlay(tmp_path, refs):
    root = _make_root(tmp_path, ALL)
    (root / ".crew" / "standards.md").write_bytes(b"\xff\xfe not utf8")

    code, lines = _write(root, refs)

    assert code == 1 and "not UTF-8" in "\n".join(lines)
    assert not (root / "REVIEW.md").exists()


def test_an_over_budget_set_is_refused_not_truncated(refs, root, monkeypatch):
    monkeypatch.setattr(cs, "EXPORT_MAX_CHARS", 500)

    code, lines = _write(root, refs)

    text = "\n".join(lines)
    assert code == 1 and re.search(r"docs/review-rules/GEN\.md is \d+ characters, over the 500", text)
    assert not (root / "docs").exists() and not (root / "REVIEW.md").exists()


def test_an_over_budget_agents_block_is_refused(refs, root, monkeypatch):
    monkeypatch.setattr(cs, "AGENTS_BLOCK_MAX_LINES", 5)

    code, lines = _write(root, refs)

    assert code == 1 and "over the 5-line budget" in "\n".join(lines)
    assert not (root / "REVIEW.md").exists()
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# Agents\n\nHand written.\n"


def test_a_hand_written_file_at_a_target_path_is_never_overwritten(refs, root):
    (root / "REVIEW.md").write_text("# Mine\n", encoding="utf-8")

    code, lines = _write(root, refs)

    assert code == 1 and "not crew's generated file" in "\n".join(lines)
    assert (root / "REVIEW.md").read_text(encoding="utf-8") == "# Mine\n"
    assert not (root / "docs").exists()


def _forged_mark():
    return "<!-- crew-standards-export digest=" + "a" * 64 + " crew=1.0 -->\n# forged\n"


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlink privilege")
def test_orphan_removal_never_follows_a_symlinked_directory(tmp_path, refs):
    root = _make_root(tmp_path, None)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "VICTIM.md").write_text(_forged_mark(), encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "review-rules").symlink_to(outside, target_is_directory=True)

    code, lines = _write(root, refs)

    assert code == 0, lines
    assert (outside / "VICTIM.md").read_text(encoding="utf-8") == _forged_mark()


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlink privilege")
@pytest.mark.parametrize("link", ["docs", "docs/review-rules"])
def test_an_opted_in_export_refuses_to_write_through_a_symlinked_directory(tmp_path, refs, link):
    root = _make_root(tmp_path, ALL, "# Agents\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "VICTIM.md").write_text(_forged_mark(), encoding="utf-8")
    if link == "docs":
        (root / "docs").symlink_to(outside, target_is_directory=True)
    else:
        (root / "docs").mkdir()
        (root / "docs" / "review-rules").symlink_to(outside, target_is_directory=True)

    code, lines = _write(root, refs)
    checked = _check(root, refs)

    assert code == 1 and "symlink" in "\n".join(lines) and checked[0] == 1
    assert sorted(os.listdir(outside)) == ["VICTIM.md"]
    assert not (root / "REVIEW.md").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlink privilege")
@pytest.mark.parametrize("rel", ["AGENTS.md", "REVIEW.md"])
def test_a_symlinked_output_is_refused_and_left_alone(tmp_path, refs, rel):
    root = _make_root(tmp_path, ALL)
    target = tmp_path / "elsewhere.md"
    target.write_text("# elsewhere\n", encoding="utf-8")
    (root / rel).symlink_to(target)

    code, lines = _write(root, refs)

    assert code == 1 and "symlink" in "\n".join(lines)
    assert (root / rel).is_symlink() and target.read_text(encoding="utf-8") == "# elsewhere\n"
    assert not (root / "docs").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="needs a FIFO")
def test_a_fifo_at_an_output_path_does_not_hang_the_check(tmp_path, refs):
    root = _make_root(tmp_path, ALL)
    os.mkfifo(root / "AGENTS.md")

    done = subprocess.run([sys.executable, "-B", _SCRIPT, "export", "--root", str(root),
                           "--check"], capture_output=True, text=True, timeout=20, check=False)

    assert done.returncode == 1 and "not a regular file" in done.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlink privilege")
@pytest.mark.parametrize("opted_in", [False, True])
def test_a_symlinked_file_the_export_does_not_own_is_left_alone(tmp_path, refs, opted_in):
    root = _make_root(tmp_path, ["review"] if opted_in else None)
    (root / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    (root / "AGENTS.md").symlink_to("CLAUDE.md")

    checked = _check(root, refs)
    written = _write(root, refs)

    assert checked[0] == (1 if opted_in else 0) and written[0] == 0
    assert (root / "AGENTS.md").is_symlink() and (root / "CLAUDE.md").read_text("utf-8") == "# Claude\n"
    if not opted_in:
        assert checked == (0, [cs.NOT_OPTED_IN])


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlink privilege")
def test_an_unmarked_symlink_in_the_rules_directory_does_not_block_the_export(tmp_path, refs):
    root = _make_root(tmp_path, ["review"])
    (root / "docs" / "review-rules").mkdir(parents=True)
    (root / "notes.txt").write_text("n\n", encoding="utf-8")
    (root / "docs" / "review-rules" / "NOTES.md").symlink_to("../../notes.txt")
    (root / "docs" / "review-rules" / "x.md").mkdir()

    code, lines = _write(root, refs)

    assert code == 0, lines
    assert (root / "docs" / "review-rules" / "NOTES.md").is_symlink()
    assert _check(root, refs)[0] == 0


def test_a_file_where_an_output_directory_belongs_is_refused_before_anything_is_written(
        tmp_path, refs):
    root = _make_root(tmp_path, ALL, "# Agents\n")
    (root / ".cursor").write_text("not a directory\n", encoding="utf-8")

    code, lines = _write(root, refs)

    assert code == 1 and "BUGBOT.md" in "\n".join(lines)
    assert not (root / "REVIEW.md").exists() and not (root / "docs").exists()
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# Agents\n"


def test_a_quoted_look_alike_marker_is_hand_text_not_a_block(tmp_path, refs):
    quoted = "<!-- crew-standards-export start foo -->\nIMPORTANT HAND TEXT\n"
    root = _make_root(tmp_path, ALL, "# Agents\n\n" + quoted)

    code, _ = _write(root, refs)

    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert code == 0 and text.startswith("# Agents\n\n" + quoted)
    assert text.count("crew-standards-export start digest=") == 1


def test_a_quoted_look_alike_pair_is_refused_not_replaced(tmp_path, refs):
    quoted = ("<!-- crew-standards-export start foo -->\nIMPORTANT HAND TEXT\n"
              "<!-- crew-standards-export end -->\n")
    root = _make_root(tmp_path, ALL, "# Agents\n\n" + quoted)

    code, _ = _write(root, refs)

    assert code == 1
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# Agents\n\n" + quoted


# ---- --check ---------------------------------------------------------------------

def test_check_passes_right_after_write(refs, root):
    _write(root, refs)

    code, lines = _check(root, refs)

    assert code == 0 and "current" in lines[0]


def test_check_fails_after_a_standard_is_edited(refs, root):
    _write(root, refs)
    _edit(refs / "generic.md", "Do the One thing.", "Do the changed thing.")

    code, lines = _check(root, refs)

    assert code == 1 and "stale: recorded digest" in "\n".join(lines)


def test_check_fails_after_a_text_that_is_not_exported_changes(refs, root):
    _write(root, refs)
    _edit(refs / "generic.md", WHY, "It broke on the day shift.")

    code, lines = _check(root, refs)

    assert code == 1 and "REVIEW.md: stale: recorded digest" in "\n".join(lines)


def test_check_fails_after_the_overlay_is_edited(refs, root):
    _write(root, refs)
    _edit(root / ".crew" / "standards.md", "Do the local thing.", "Do another thing.")

    code, lines = _check(root, refs)

    assert code == 1 and "stale: recorded digest" in "\n".join(lines)


def test_check_fails_when_a_set_file_is_edited_by_hand(refs, root):
    _write(root, refs)
    path = root / "docs" / "review-rules" / "GEN.md"
    path.write_text(path.read_text("utf-8") + "\nHand note.\n", encoding="utf-8", newline="\n")

    code, lines = _check(root, refs)

    text = "\n".join(lines)
    assert code == 1 and "docs/review-rules/GEN.md: differs from the standards" in text


def test_check_fails_when_the_agents_block_is_edited_by_hand(refs, root):
    _write(root, refs)
    _edit(root / "AGENTS.md", "- GEN-01 One:", "- GEN-01 Edited:")

    code, lines = _check(root, refs)

    assert code == 1 and "AGENTS.md: differs from the standards" in "\n".join(lines)


def test_check_fails_when_one_target_is_deleted(refs, root):
    _write(root, refs)
    os.remove(root / "REVIEW.md")

    code, lines = _check(root, refs)

    assert code == 1 and "REVIEW.md: missing" in "\n".join(lines)


def test_check_fails_when_every_target_is_deleted(refs, root):
    _write(root, refs)
    for name in list(_outputs(root)):
        if name != "AGENTS.md":
            os.remove(root / name)
    (root / "AGENTS.md").write_text("# Agents\n\nHand written.\n", encoding="utf-8")

    code, lines = _check(root, refs)

    text = "\n".join(lines)
    assert code == 1 and cs.NOT_OPTED_IN not in text and "missing" in text


def test_check_fails_on_a_tampered_digest(refs, root):
    _write(root, refs)
    path = root / "REVIEW.md"
    text = path.read_text("utf-8")
    path.write_text(re.sub(r"digest=[0-9a-f]{64}", "digest=" + "0" * 64, text, count=1),
                    encoding="utf-8", newline="\n")

    code, lines = _check(root, refs)

    assert code == 1 and "REVIEW.md: stale: recorded digest 00000000" in "\n".join(lines)


def test_check_fails_on_a_tampered_crew_version(refs, root):
    _write(root, refs)
    _edit(root / "docs" / "review-rules" / "REPO.md", f"crew={V}", "crew=1.0.0")

    code, lines = _check(root, refs)

    assert code == 1 and "written by crew 1.0.0, this is crew 9.9.9" in "\n".join(lines)


def test_check_fails_for_an_orphaned_target_after_it_is_removed_from_the_list(refs, root):
    _write(root, refs)
    _edit(root / ".crew" / "standards.md", '["review", "agents", "bugbot"]', '["agents"]')

    code, lines = _check(root, refs)

    text = "\n".join(lines)
    assert code == 1 and ".cursor/BUGBOT.md is orphaned" in text and "REVIEW.md is orphaned" in text


def test_check_fails_for_an_orphaned_agents_block_after_agents_is_removed(refs, root):
    _write(root, refs)
    _edit(root / ".crew" / "standards.md", '["review", "agents", "bugbot"]', '["review"]')

    code, lines = _check(root, refs)

    assert code == 1 and "carries an orphaned" in "\n".join(lines)


def test_check_fails_for_an_orphaned_set_file_after_a_set_is_removed(refs, root):
    _write(root, refs)
    os.remove(refs / "php.md")

    code, lines = _check(root, refs)

    assert code == 1 and "docs/review-rules/PHP.md is orphaned" in "\n".join(lines)


def test_check_fails_when_the_export_key_is_deleted_but_marked_files_remain(refs, root):
    _write(root, refs)
    _edit(root / ".crew" / "standards.md", 'export: ["review", "agents", "bugbot"]\n', "")

    code, lines = _check(root, refs)

    assert code == 1 and "orphaned" in "\n".join(lines) and cs.NOT_OPTED_IN not in lines


def test_write_removes_orphans_but_never_an_unmarked_file(refs, root):
    _write(root, refs)
    (root / "docs" / "review-rules" / "NOTES.md").write_text("# mine\n", encoding="utf-8")
    os.remove(refs / "php.md")
    _edit(root / ".crew" / "standards.md", '["review", "agents", "bugbot"]', '["review", "agents"]')

    code, lines = _write(root, refs)

    assert code == 0 and "removed orphan .cursor/BUGBOT.md" in lines
    assert not (root / ".cursor" / "BUGBOT.md").exists()
    assert not (root / "docs" / "review-rules" / "PHP.md").exists()
    assert (root / "docs" / "review-rules" / "NOTES.md").read_text("utf-8") == "# mine\n"
    assert _check(root, refs)[0] == 0


def test_write_strips_an_orphaned_agents_block_and_keeps_hand_text(refs, root):
    _write(root, refs)
    _edit(root / ".crew" / "standards.md", '["review", "agents", "bugbot"]', '["review"]')

    code, _ = _write(root, refs)

    assert code == 0
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# Agents\n\nHand written.\n"
    assert _check(root, refs)[0] == 0


def test_check_writes_nothing(refs, root):
    _write(root, refs)
    _edit(refs / "generic.md", "Do the One thing.", "Do the changed thing.")
    before = _outputs(root)

    _check(root, refs)

    assert _outputs(root) == before


# ---- this repository -------------------------------------------------------------

def test_this_repos_generated_files_exist_and_fit():
    sets_dir = os.path.join(_REPO_ROOT, "docs", "review-rules")
    found = cs.effective_set(_REPO_ROOT, [], applies=lambda globs: True)
    with open(os.path.join(_REPO_ROOT, "AGENTS.md"), encoding="utf-8") as fh:
        block = fh.read()
    start = block.index("<!-- crew-standards-export start")
    end = block.index("<!-- crew-standards-export end -->")

    names = sorted(os.listdir(sets_dir))

    assert names == sorted(f"{name}.md" for name in found["sets"])
    assert names == ["GEN.md", "PWSH.md", "PYTHON.md", "REPO.md"]
    for rel in [f"docs/review-rules/{n}" for n in names] + ["REVIEW.md", ".cursor/BUGBOT.md"]:
        with open(os.path.join(_REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            assert len(fh.read()) <= cs.EXPORT_MAX_CHARS, rel
    assert len(block[start:end].splitlines()) + 1 <= cs.AGENTS_BLOCK_MAX_LINES


def test_the_crew_standards_rule_runs_the_export_tests():
    with open(os.path.join(_REPO_ROOT, ".crew", "verify.json"), encoding="utf-8") as fh:
        rules = {rule["id"]: rule for rule in json.load(fh)["rules"]}

    standards = rules["crew-standards"]
    export = rules["standards-export"]

    for name in ("test_standards_export.py", "test_docs_check.py"):
        assert any(name in path for path in standards["paths"]), name
        assert any(name in command for command in standards["run"]), name
    assert export["paths"] == ["**"]
    assert any("crew_standards.py export --check" in command for command in export["run"])
