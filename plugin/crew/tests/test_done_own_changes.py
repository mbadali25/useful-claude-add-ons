"""L-0753: `/crew:done` checks 4 and 5 judge the ticket's own diff.

    python3 -m pytest plugin/crew/tests/test_done_own_changes.py -q

Each case builds a throwaway git world under tmp_path. A ticket branch makes the
ticket's change. Meanwhile main lands another PR (a workflow edit, a code change that
an existing code map cites), and the ticket then merges main. There are three moments:

  pre-land  on the ticket branch, main merged in
  landed    on a close branch at main, right after the ticket's --no-ff merge
  later     on a close branch at main after a further release (1.0.2) landed

Must-allow: another PR's workflow and stale code map are not the ticket's, and the
ticket's own `## [1.0.1]` or `[Unreleased]` CHANGELOG entry is found at every
moment. Must-block: the ticket's own workflow edit, its own stale map, and a
missing entry still refuse. When which changes are main's cannot be told (a
detached HEAD, no receipt, a receipt head outside the history), the full set is
judged, so the other PR's changes refuse again.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_docs_check
import crew_refresh_check
import scope_base

T = "T-0001"
CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-10-01\n\n- first\n"
STAGES = ("pre-land", "landed", "later")


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=str(root), check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=30).stdout.strip()


def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _commit(root, message, **files):
    for rel, text in files.items():
        _write(root, rel.replace("__", "/"), text)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _market(version):
    return json.dumps({"name": "m", "plugins": [
        {"name": "crew", "source": "./plugin/crew", "version": version}]}, indent=2) + "\n"


def _codemap(name, anchor, cited):
    return f"# {name}\nanchor: {anchor}\n\n- `{cited}:1` - cited\n"


def _changelog_with(entry, section="## [Unreleased]"):
    if section == "## [Unreleased]":
        return CHANGELOG.replace("## [Unreleased]\n", f"## [Unreleased]\n\n{entry}\n")
    return CHANGELOG.replace("## [1.0.0]", f"{section}\n\n{entry}\n\n## [1.0.0]")


def _world(tmp_path, stage, entry="- `crew` 1.0.1: app counts to two",
           section="## [1.0.1] - 2026-10-09", own_workflow=False, refresh_own_map=True,
           main_entry=None, receipt=True):
    """Build the world at `stage`. Returns the checkout to judge."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "core.autocrlf", "false")
    start = _commit(root, "fixture", **{
        ".gitignore": ".work/\n.crew/.*\n",
        ".claude-plugin__marketplace.json": _market("1.0.0"),
        "CHANGELOG.md": CHANGELOG, "SECURITY.md": "report to x\n", "TODO.md": "# TODO\n",
        "plugin__crew__hooks__scripts__app.py": "x = 1\n", "src__other.py": "y = 1\n",
        ".github__workflows__ci.yml": "on: push\n"})
    _commit(root, "maps", **{
        ".crew__codemap__app.md": _codemap("app", start, "plugin/crew/hooks/scripts/app.py"),
        ".crew__codemap__other.md": _codemap("other", start, "src/other.py")})
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-qb", "T-0001-work")
    os.makedirs(os.path.join(str(root), ".work", "tickets", T), exist_ok=True)
    assert scope_base.record(str(root), T)[1] == "recorded"
    files = {"plugin__crew__hooks__scripts__app.py": "x = 2\n"}
    if own_workflow:
        files[".github__workflows__ci.yml"] = "on: [push, pull_request]\n"
    reviewed = _commit(root, f"{T}: the change", **files)
    if refresh_own_map:
        _commit(root, f"{T}: re-anchor the app map", **{
            ".crew__codemap__app.md": _codemap("app", reviewed, "plugin/crew/hooks/scripts/app.py")})
    _git(root, "checkout", "-q", "main")
    other = {"src__other.py": "y = 2\n", ".github__workflows__ci.yml": "on: [push]\n"}
    if own_workflow:
        other.pop(".github__workflows__ci.yml")
    if main_entry:
        other["CHANGELOG.md"] = _changelog_with(main_entry)
    _commit(root, "another PR: other code and a workflow", **other)
    _git(root, "checkout", "-q", "T-0001-work")
    _git(root, "merge", "-q", "--no-edit", "main")
    version = {".claude-plugin__marketplace.json": _market("1.0.1")}
    if entry:
        version["CHANGELOG.md"] = (_changelog_with(entry, section) if not main_entry else
                                   _changelog_with(main_entry).replace(
                                       "## [Unreleased]\n", f"## [Unreleased]\n\n{entry}\n"))
    _commit(root, f"crew 1.0.1: version for {T}", **version)
    if receipt:
        _write(root, f".work/tickets/{T}/review.json",
               json.dumps({"ticket": T, "base": base, "head": reviewed}))
    if stage == "pre-land":
        return root
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "-m", "Merge pull request #1 from o/T-0001-work",
         "T-0001-work")
    if stage == "later":
        current = open(os.path.join(str(root), "CHANGELOG.md"), encoding="utf-8").read()
        at = current.index("\n## [1") + 1
        _commit(root, "crew 1.0.2: another ticket", **{
            ".claude-plugin__marketplace.json": _market("1.0.2"),
            "CHANGELOG.md": current[:at] + "## [1.0.2] - 2026-10-10\n\n- `crew` 1.0.2: more\n\n"
                            + current[at:]})
    _git(root, "checkout", "-qb", "T-0001-done")
    return root


def _docs(root):
    return crew_docs_check.ticket_docs(str(root), T)


def _row(result, prefix):
    rows = [d for d in result["documents"] if d["doc"].startswith(prefix)]
    assert len(rows) == 1, (prefix, result)
    return rows[0]


def _maps(root):
    result = crew_refresh_check.ticket_freshness(str(root), T, which=lambda _n: None)
    return result, {a["name"]: a["status"] for a in result["artifacts"] if a["kind"] == "codemap"}


# --- (a) the CHANGELOG entry this ticket added, wherever it sits ------------------

@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("entry,section", [
    ("- `crew` 1.0.1: app counts to two", "## [1.0.1] - 2026-10-09"),
    ("### Fixed — crew 1.0.1: app counts to two", "## [Unreleased]"),
], ids=["version-section", "unreleased-bare-name"])
def test_own_changelog_entry_is_found_at_every_moment(tmp_path, stage, entry, section):
    root = _world(tmp_path, stage, entry=entry, section=section)

    row = _row(_docs(root), "CHANGELOG.md (crew")

    assert (row["doc"], row["verdict"]) == ("CHANGELOG.md (crew 1.0.1)", "updated"), row


@pytest.mark.parametrize("stage", STAGES)
def test_no_own_changelog_entry_is_missing(tmp_path, stage):
    root = _world(tmp_path, stage, entry=None)

    assert _row(_docs(root), "CHANGELOG.md (crew")["verdict"] == "MISSING"


@pytest.mark.parametrize("entry,section", [
    ("- `crew` 1.0.0: names the old version", "## [1.0.1] - 2026-10-09"),
    ("- `crew` 1.0.1: under another release's heading", "## [0.9.0] - 2026-09-01"),
], ids=["wrong-version", "wrong-section"])
def test_an_entry_for_another_version_or_section_is_missing(tmp_path, entry, section):
    root = _world(tmp_path, "landed", entry=entry, section=section)

    assert _row(_docs(root), "CHANGELOG.md (crew")["verdict"] == "MISSING"


@pytest.mark.parametrize("stage", ("pre-land", "landed"))
def test_an_entry_only_merged_main_added_is_not_the_tickets(tmp_path, stage):
    root = _world(tmp_path, stage, entry="- a line that names nothing",
                  main_entry="- `crew` 1.0.1: written by another PR")

    assert _row(_docs(root), "CHANGELOG.md (crew")["verdict"] == "MISSING"


# --- (b) SECURITY.md: only the ticket's own workflow changes ---------------------

@pytest.mark.parametrize("stage", STAGES)
def test_a_workflow_main_brought_in_is_not_the_tickets(tmp_path, stage):
    root = _world(tmp_path, stage)

    got = _docs(root)

    assert _row(got, "SECURITY.md")["verdict"] == "not needed", got
    assert got["status"] == "ok", got


@pytest.mark.parametrize("stage", STAGES)
def test_the_tickets_own_workflow_change_still_needs_security(tmp_path, stage):
    root = _world(tmp_path, stage, own_workflow=True)

    assert _row(_docs(root), "SECURITY.md")["verdict"] == "MISSING"


# --- (c) artifacts: only what the ticket made stale ------------------------------

@pytest.mark.parametrize("stage", STAGES)
def test_a_map_only_merged_main_made_stale_is_not_judged(tmp_path, stage):
    root = _world(tmp_path, stage)

    result, maps = _maps(root)

    assert maps == {"app": "fresh"}, result
    assert result["status"] == "fresh", result


@pytest.mark.parametrize("stage", STAGES)
def test_a_map_the_ticket_made_stale_is_stale(tmp_path, stage):
    root = _world(tmp_path, stage, refresh_own_map=False)

    result, maps = _maps(root)

    assert maps.get("app") == "stale", result
    assert "other" not in maps, result


# --- could not tell: the full set, never a narrower one --------------------------

def _detach(root):
    _git(root, "checkout", "-q", "--detach")


def _drop_receipt(root):
    os.remove(os.path.join(str(root), ".work", "tickets", T, "review.json"))


def _foreign_receipt(root):
    base = scope_base.resolve(str(root), T)[0]
    _write(root, f".work/tickets/{T}/review.json",
           json.dumps({"ticket": T, "base": base, "head": "1" * 40}))


def _other_tickets_receipt(root):
    path = os.path.join(str(root), ".work", "tickets", T, "review.json")
    with open(path, encoding="utf-8") as handle:
        receipt = json.load(handle)
    receipt["ticket"] = "T-0002"
    _write(root, f".work/tickets/{T}/review.json", json.dumps(receipt))


def _other_base_receipt(root):
    path = os.path.join(str(root), ".work", "tickets", T, "review.json")
    with open(path, encoding="utf-8") as handle:
        receipt = json.load(handle)
    receipt["base"] = _git(root, "rev-parse", "HEAD")
    _write(root, f".work/tickets/{T}/review.json", json.dumps(receipt))


def _garbled_receipt(root):
    _write(root, f".work/tickets/{T}/review.json", '{"head": ')


@pytest.mark.parametrize("stage,blind", [
    ("pre-land", _detach), ("landed", _detach), ("landed", _drop_receipt),
    ("landed", _foreign_receipt), ("landed", _garbled_receipt), ("landed", _other_tickets_receipt),
    ("landed", _other_base_receipt),
], ids=["pre-land-detached", "landed-detached", "landed-no-receipt", "landed-foreign-receipt",
        "landed-garbled-receipt", "landed-other-tickets-receipt", "landed-other-base-receipt"])
def test_could_not_tell_judges_the_full_set(tmp_path, stage, blind):
    root = _world(tmp_path, stage)
    blind(root)

    docs = _docs(root)
    result, maps = _maps(root)

    assert _row(docs, "SECURITY.md")["verdict"] == "MISSING", docs
    assert maps.get("other") == "stale", result
    assert "every path since the base is judged" in docs["reason"]
    assert "could not tell" in result["reason"]


def test_own_changes_names_the_landing_merge(tmp_path):
    root = _world(tmp_path, "landed")
    merge = _git(root, "rev-parse", "HEAD")

    base = scope_base.resolve(str(root), T)[0]
    own = crew_refresh_check.own_changes(str(root), base, T)

    assert (own["new"], own["old"], own["narrowed"]) == (
        merge, _git(root, "rev-parse", "HEAD^1"), True)
    assert own["paths"] == [".claude-plugin/marketplace.json", ".crew/codemap/app.md",
                            "CHANGELOG.md", "plugin/crew/hooks/scripts/app.py"]
